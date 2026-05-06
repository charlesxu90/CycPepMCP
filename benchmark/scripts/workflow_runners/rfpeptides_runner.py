"""RFpeptides workflow runner.

Real mode: thin wrapper around the existing
`workflow-skills/scripts/rfpeptides/run_pipeline.py` (which already implements
checkpointing, parallel CPU/GPU workers, and 5-stage execution). This wrapper
adds: (a) tracer events around the major pipeline calls, (b) per-target
threshold resolution from `targets.csv` / `workflows.yaml`, and (c) an output
candidate_metrics.csv in the unified schema.

Mock mode: generates synthetic top candidates from `final_summary.csv`-shaped
data so we can validate plumbing without RFdiffusion / ProteinMPNN / Rosetta
running.

Stages (deferred to run_pipeline.py for real mode):
  1. Backbone Generation (RFdiffusion)
  2. Iterative ProteinMPNN + Rosetta FastRelax (4 rounds)
  3. AfCycDesign reprediction
  4. Rosetta interface metrics (ddG, SAP, CMS)
  5. RMSD clustering
"""
from __future__ import annotations

import csv
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

from benchmark.configs import thresholds as cfg
from benchmark.scripts.agent_trace import ErrorType
from benchmark.scripts.workflow_runners.base import WorkflowRunner, find_project_root


class RFpeptidesRunner(WorkflowRunner):
    workflow_name = "rfpeptides"

    # ------------------------------------------------------------------
    @staticmethod
    def _norm(c: dict[str, Any]) -> dict[str, Any]:
        """Canonicalize RFpeptides final_summary.csv columns. The pipeline
        ships {design_id|design, sequence, length, iPAE|ipae, pLDDT|plddt,
        ddg, sap, cms, passes_physics, structure, composite_score}."""
        n = {k.lower(): v for k, v in c.items()}
        return {
            "design": n.get("design_id") or n.get("design") or "",
            "sequence": n.get("sequence", ""),
            "ipae": n.get("ipae", n.get("i_pae", 0)),
            "plddt": n.get("plddt", 0),
            "ddg": n.get("ddg", 0),
            "sap": n.get("sap", ""),
            "cms": n.get("cms", ""),
            "composite_score": n.get("composite_score", ""),
            "passes_physics": n.get("passes_physics", ""),
        }

    def apply_primary_gate(self, c: dict[str, Any]) -> tuple[bool, str]:
        gate = cfg.RFPEPTIDES_PASS_GATE.primary
        # Per-target iPAE/ddG: targets.csv override > workflows.yaml per_target > default.
        per_target = cfg.rfpeptides_target_threshold(self.ctx.target.target_short)
        ipae_max = self.ctx.target.ipae_pass_gate or per_target["ipae"]
        ddg_max = self.ctx.target.ddg_pass_gate or per_target["ddg"]
        n = self._norm(c)
        try:
            plddt = float(n["plddt"])
            ipae = float(n["ipae"])
            ddg = float(n["ddg"])
            sap = float(n["sap"]) if n["sap"] != "" else gate["sap_max"] + 1
            cms = float(n["cms"]) if n["cms"] != "" else gate["cms_min"] - 1
        except (TypeError, ValueError):
            return False, "non-numeric metric"
        if plddt < gate["plddt_min"]:
            return False, f"pLDDT={plddt:.2f}<{gate['plddt_min']}"
        if ipae > ipae_max:
            return False, f"iPAE={ipae:.2f}>{ipae_max}"
        if ddg > ddg_max:
            return False, f"ddG={ddg:.1f}>{ddg_max}"
        if sap > gate["sap_max"]:
            return False, f"SAP={sap:.1f}>{gate['sap_max']}"
        if cms < gate["cms_min"]:
            return False, f"CMS={cms:.0f}<{gate['cms_min']}"
        return True, "pass"

    def composite_score(self, c: dict[str, Any]) -> float:
        """Read pre-computed composite_score from the pipeline if available; else recompute."""
        n = self._norm(c)
        try:
            return round(float(n["composite_score"]), 4)
        except (KeyError, TypeError, ValueError):
            return self._recompute_composite(n)

    def _recompute_composite(self, c: dict[str, Any]) -> float:
        """Min-max normalize each metric across `_all_rows` and apply weights."""
        # Note: proper normalization requires the full population. This fallback
        # uses target-specific gates as anchors so single-row scores remain stable.
        w = cfg.RFPEPTIDES_COMPOSITE_WEIGHTS
        gate = cfg.RFPEPTIDES_PASS_GATE.primary
        excl = cfg.RFPEPTIDES_PASS_GATE.excellent
        # Linear interpolation between gate (=0) and excellent (=1) for each metric.
        def normb(value: float, gate_v: float, excl_v: float, higher_better: bool) -> float:
            if higher_better:
                return max(0.0, min(1.0, (value - gate_v) / (excl_v - gate_v + 1e-9)))
            return max(0.0, min(1.0, (gate_v - value) / (gate_v - excl_v + 1e-9)))
        plddt_n = normb(float(c.get("plddt", 0)), gate["plddt_min"], excl["plddt_min"], True)
        ipae_n = normb(float(c.get("ipae", 1)), gate["ipae_max_default"], excl["ipae_max"], False)
        ddg_n = normb(float(c.get("ddg", 0)), gate["ddg_max_default"], excl["ddg_max"], False)
        sap_n = normb(float(c.get("sap", gate["sap_max"])), gate["sap_max"], excl["sap_max"], False)
        cms_n = normb(float(c.get("cms", gate["cms_min"])), gate["cms_min"], excl["cms_min"], True)
        return round(w["plddt_norm"] * plddt_n + w["ipae_norm"] * ipae_n
                     + w["ddg_norm"] * ddg_n + w["sap_norm"] * sap_n
                     + w["cms_norm"] * cms_n, 4)

    # ------------------------------------------------------------------
    # Real mode — delegate to run_pipeline.py
    # ------------------------------------------------------------------
    def run_real(self) -> dict[str, Any]:
        t = self.ctx.target
        root = find_project_root()
        pipeline = root / "workflow-skills" / "scripts" / "rfpeptides" / "run_pipeline.py"
        if not pipeline.is_file():
            raise RuntimeError(f"missing pipeline script: {pipeline}")

        # Stage 1 backbone generation runs separately (rfpeptides_mcp), produces stage1_dir.
        # For a benchmark run we expect the user to point us at an existing stage1_dir
        # (or we trigger it via cpmcp). If stage1 is checkpointed, skip the directory
        # check entirely — the pilot may be reusing case-study outputs that don't
        # have a stage1_backbones/ folder under our run_dir.
        stage1_dir = self.out_dir / "stage1_backbones"
        if not self.stage_completed("stage1"):
            self.tracer.log_planning(
                f"backbone generation for {t.target_short} (binder_len={t.binder_length}, "
                f"num_designs={t.num_designs})"
            )
            with self.tracer.tool_call(
                "rfpeptides_mcp.submit_cyclic_binder_with_hotspots",
                input_artifact=t.target_pdb,
                notes=f"hotspots={t.hotspots} num_designs={t.num_designs}",
            ) as call:
                # In a real run this call returns a job_id; the pilot integration
                # in W2(a) is responsible for invoking this MCP and pointing the
                # runner at the resulting backbones via --stage1_dir.
                call.notes = "stage1_dir expected at: " + str(stage1_dir)
                if not stage1_dir.is_dir() or not any(stage1_dir.glob("*.pdb")):
                    raise RuntimeError(
                        f"stage1 backbones missing at {stage1_dir}. "
                        f"Run rfpeptides_mcp first (e.g. via the workflow skill) "
                        f"and place backbones into this directory before continuing."
                    )
            self.save_checkpoint("stage1", stage1_dir=str(stage1_dir))

        # Stages 2-5 via run_pipeline.py
        if not self.stage_completed("stages_2_to_5"):
            self.tracer.log_planning("invoke run_pipeline.py for stages 2-5")
            cmd = [
                sys.executable, str(pipeline),
                "--stage1_dir", str(stage1_dir),
                "--target_pdb", str(root / t.target_pdb),
                "--output_dir", str(self.out_dir / "pipeline"),
            ]
            with self.tracer.tool_call(
                "rfpeptides.run_pipeline",
                input_artifact=str(stage1_dir),
            ) as call:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=259200)  # 72h
                (self.out_dir / "pipeline_stdout.log").write_text(proc.stdout)
                (self.out_dir / "pipeline_stderr.log").write_text(proc.stderr)
                if proc.returncode != 0:
                    call.status = "failure"
                    call.error_type = ErrorType.RUNTIME.value
                    call.notes = f"return_code={proc.returncode}"
                    raise RuntimeError(f"run_pipeline.py failed (rc={proc.returncode})")
                call.output_artifact = str(self.out_dir / "pipeline" / "final_summary.csv")
            self.save_checkpoint("stages_2_to_5")

        return self._collect_and_score(self.out_dir / "pipeline" / "final_summary.csv")

    # ------------------------------------------------------------------
    # Mock mode
    # ------------------------------------------------------------------
    def run_mock(self) -> dict[str, Any]:
        if not self.stage_completed("stage1"):
            self.tracer.log_target_qc(self.ctx.target.target_pdb, ok=True, notes="mock skip")
            self.save_checkpoint("stage1")

        if not self.stage_completed("stages_2_to_5"):
            self.tracer.log_planning(f"[mock] rfpeptides pipeline for {self.ctx.target.target_short}")
            rng = random.Random(self.ctx.seed * 6151 + hash(self.ctx.target.task_id) % 1000)
            per_target = cfg.rfpeptides_target_threshold(self.ctx.target.target_short)
            with self.tracer.tool_call(
                "rfpeptides.run_pipeline",
                input_artifact="mock_stage1_backbones",
            ) as call:
                rows = []
                for i in range(20):
                    plddt = round(rng.gauss(0.80, 0.08), 3)
                    # iPAE distribution centered at the target's gate so half pass.
                    ipae = round(max(0.05, rng.gauss(per_target["ipae"], 0.10)), 3)
                    ddg = round(rng.gauss(-35, 12), 1)
                    sap = round(rng.gauss(28, 6), 1)
                    cms = round(rng.gauss(330, 60), 0)
                    rows.append({
                        "design": f"design_{i:03d}",
                        "sequence": "".join(rng.choices("ACDEFGHIKLMNPQRSTVWY", k=self.ctx.target.binder_length or 14)),
                        "ddg": ddg, "ipae": ipae, "plddt": plddt, "sap": sap, "cms": cms,
                        "composite_score": "",  # let runner recompute
                    })
                results_dir = self.out_dir / "pipeline"
                results_dir.mkdir(parents=True, exist_ok=True)
                results_csv = results_dir / "final_summary.csv"
                with results_csv.open("w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=["design", "sequence", "ddg", "ipae", "plddt", "sap", "cms", "composite_score"])
                    w.writeheader()
                    w.writerows(rows)
                call.output_artifact = str(results_csv)
                call.notes = f"mock generated {len(rows)} synthetic candidates"
            self.save_checkpoint("stages_2_to_5", n_synthetic=20)

        return self._collect_and_score(self.out_dir / "pipeline" / "final_summary.csv")

    # ------------------------------------------------------------------
    def _collect_and_score(self, summary_csv: Path) -> dict[str, Any]:
        if not summary_csv.is_file():
            raise FileNotFoundError(f"missing {summary_csv}; rfpeptides pipeline produced no output")
        with summary_csv.open() as f:
            raw = list(csv.DictReader(f))
        n_in = len(raw)

        rows_out = []
        n_pass = n_fail = 0
        for i, c in enumerate(raw):
            passes, reason = self.apply_primary_gate(c)
            score = self.composite_score(c)
            n = self._norm(c)
            rows_out.append({
                "task_id": self.ctx.target.task_id,
                "target_id": f"{self.ctx.target.target_short}_{Path(self.ctx.target.target_pdb).stem}",
                "workflow": self.workflow_name,
                "run_id": self.ctx.run_id,
                "candidate_id": n["design"] or f"design_{i:03d}",
                "sequence_or_helm": n["sequence"],
                "rank": 0,
                "pass_status": passes,
                "pass_reason": reason,
                "plddt": n["plddt"],
                "iptm": "",
                "ipae": n["ipae"],
                "ddg": n["ddg"],
                "gnina_cnn_pkd": "",
                "predicted_kd_um": "",
                "logpapp": "",
                "composite_score": score,
                "cluster_id": "",
            })
            if passes:
                n_pass += 1
            else:
                n_fail += 1

        rows_out.sort(key=lambda r: r["composite_score"], reverse=True)
        for rank, r in enumerate(rows_out, start=1):
            r["rank"] = rank

        with self._candidate_csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
            w.writeheader()
            w.writerows(rows_out)

        self.tracer.log_filter(n_in=n_in, n_pass=n_pass, n_fail=n_fail,
                               reason="rfpeptides primary gate (pLDDT/iPAE/ddG/SAP/CMS)")
        self.save_checkpoint("collect", n_pass=n_pass, n_fail=n_fail)
        return {
            "n_candidates": n_in,
            "n_pass": n_pass,
            "n_fail": n_fail,
            "top_composite": rows_out[0]["composite_score"] if rows_out else None,
            "candidate_csv": str(self._candidate_csv),
        }
