"""AfCycDesign workflow runner.

Real mode: invokes `afcycdesign_mcp/scripts/cycpep_target_complex_pred.py`
(the same script the MCP server wraps) via subprocess, polling for completion
and reading back `afcycdesign_results.csv`. The MCP layer is bypassed for
benchmark determinism (matching the existing `run_pipeline.py` pattern).

Mock mode: emits 10 synthetic candidates with realistic-shaped score
distributions so the rest of the pipeline (tracer, aggregator, viz) can be
smoke-tested without GPU work.

Stages
------
1. target_qc   — verify input PDB exists and chain ID is present
2. submit      — kick off binder design (real: subprocess; mock: synthesize)
3. monitor     — wait for completion / read job log
4. collect     — parse `afcycdesign_results.csv`, materialize candidate_metrics.csv
5. filter      — apply primary PASS gate from workflows.yaml
6. score       — compute composite score per workflows.yaml weights
"""
from __future__ import annotations

import csv
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from benchmark.configs import thresholds as cfg
from benchmark.scripts.agent_trace import ErrorType
from benchmark.scripts.workflow_runners.base import WorkflowRunner, find_project_root


class AfCycDesignRunner(WorkflowRunner):
    workflow_name = "afcycdesign"

    # ------------------------------------------------------------------
    # Column normalization
    # ------------------------------------------------------------------
    @staticmethod
    def _norm(c: dict[str, Any]) -> dict[str, Any]:
        """Canonicalize AfCycDesign result columns. The tool's CSV ships
        {design, sequence, loss, i_con, plddt, ptm, i_ptm}. `i_con` is
        interface-contact density (~1.5-3.0 range), NOT iPAE — we keep it
        only as informational and gate on pLDDT + iPTM instead."""
        n = {k.lower(): v for k, v in c.items()}
        return {
            "design": n.get("design") or n.get("design_id") or "",
            "sequence": n.get("sequence", ""),
            "loss": n.get("loss", ""),
            "plddt": n.get("plddt", 0),
            "ptm": n.get("ptm", 0),
            "iptm": n.get("i_ptm", n.get("iptm", 0)),
            "i_con": n.get("i_con", ""),
        }

    # ------------------------------------------------------------------
    # PASS gate (overrides base; reads from centralized config)
    # ------------------------------------------------------------------
    def apply_primary_gate(self, c: dict[str, Any]) -> tuple[bool, str]:
        gate = cfg.AFCYCDESIGN_PASS_GATE.primary
        n = self._norm(c)
        try:
            plddt = float(n["plddt"])
            iptm = float(n["iptm"])
        except (TypeError, ValueError):
            return False, "non-numeric metric"
        if plddt < gate["mean_plddt_min"]:
            return False, f"pLDDT={plddt:.2f}<{gate['mean_plddt_min']}"
        if iptm < gate["iptm_min"]:
            return False, f"iPTM={iptm:.2f}<{gate['iptm_min']}"
        return True, "pass"

    def composite_score(self, c: dict[str, Any]) -> float:
        # AfCycDesign output lacks a true 0-1 iPAE channel, so we substitute
        # the existing pTM/iPTM signal for the "ipae_inv" weight and keep the
        # other weights identical to workflows.yaml.
        w = cfg.AFCYCDESIGN_COMPOSITE_WEIGHTS
        n = self._norm(c)
        plddt = float(n["plddt"])
        iptm = float(n["iptm"])
        ptm = float(n["ptm"])
        ipae_inv = iptm  # proxy: AfCycDesign doesn't emit a 0-1 iPAE
        return round(w["plddt"] * plddt + w["iptm"] * iptm + w["ptm"] * ptm + w["ipae_inv"] * ipae_inv, 4)

    # ------------------------------------------------------------------
    # Real mode
    # ------------------------------------------------------------------
    def run_real(self) -> dict[str, Any]:
        t = self.ctx.target
        root = find_project_root()
        afcyc_base = root / "tool-mcps" / "afcycdesign_mcp"
        afcyc_python = str(afcyc_base / "env" / "bin" / "python")
        # `cyclic_binder_design.py` is the correct entry point for de novo binder
        # design. `cycpep_target_complex_pred.py` is structure-prediction-given-
        # sequence and does not generate new binders.
        afcyc_script = str(afcyc_base / "scripts" / "cyclic_binder_design.py")
        if not Path(afcyc_python).is_file() or not Path(afcyc_script).is_file():
            raise RuntimeError(
                f"afcycdesign tool not installed; expected {afcyc_python} and {afcyc_script}. "
                "Run `cpmcp install afcycdesign_mcp` first."
            )

        # Stage 1: target QC
        if not self.stage_completed("target_qc"):
            self._target_qc(root)
            self.save_checkpoint("target_qc")

        # Stage 2: submit N independent binder design runs (one per design;
        # the AfCycDesign optimizer is stateful per-call). Number of designs
        # comes from targets.csv `num_designs` — defaults to 10 for AfCycDesign.
        n_designs = self.ctx.target.num_designs or 10
        gpu_id = int(os.environ.get("BENCHMARK_GPU_ID", "0"))
        designs_dir = self.out_dir / "designs"
        designs_dir.mkdir(parents=True, exist_ok=True)

        if not self.stage_completed("submit"):
            self.tracer.log_planning(
                f"submit {n_designs} afcycdesign binder design jobs: target={t.target_short} "
                f"binder_len={t.binder_length} optimizer=pssm_semigreedy gpu={gpu_id}"
            )
            for design_idx in range(n_designs):
                if (designs_dir / f"design_{design_idx:03d}.pdb").is_file():
                    continue   # already done in a prior partial run
                with self.tracer.tool_call(
                    "afcycdesign_mcp.cyclic_binder_design",
                    input_artifact=t.target_pdb,
                    notes=f"design {design_idx+1}/{n_designs}",
                ) as call:
                    cmd = [
                        afcyc_python, afcyc_script,
                        "--target_chain", t.target_chain,
                        "--binder_len", str(t.binder_length or 12),
                        "--num_models", "2",
                        "--optimizer", "pssm_semigreedy",
                        "--gpu", str(gpu_id),
                        "--output", str(designs_dir / f"design_{design_idx:03d}.pdb"),
                        "--ipae_threshold", "0.15",
                        "--quiet",
                    ]
                    # Resolve PDB source: local file > 4-letter PDB code auto-download.
                    pdb_local = root / t.target_pdb
                    if pdb_local.is_file():
                        cmd += ["--pdb", str(pdb_local)]
                    else:
                        # target_pdb like "1G5J.pdb" → use --pdb_code 1G5J
                        stem = Path(t.target_pdb).stem
                        if len(stem) == 4 and stem.isalnum():
                            cmd += ["--pdb_code", stem]
                        else:
                            raise FileNotFoundError(
                                f"target PDB not found at {pdb_local} and "
                                f"target_pdb {t.target_pdb!r} is not a 4-letter PDB code"
                            )
                    if t.hotspots:
                        cmd += ["--hotspot", ",".join(map(str, t.hotspots))]
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
                    log_path = designs_dir / f"design_{design_idx:03d}.log"
                    log_path.write_text(f"# stdout\n{proc.stdout}\n# stderr\n{proc.stderr}")
                    if proc.returncode != 0:
                        call.status = "failure"
                        call.error_type = ErrorType.RUNTIME.value
                        call.notes = f"design {design_idx} rc={proc.returncode}; see {log_path.name}"
                        raise RuntimeError(
                            f"cyclic_binder_design.py failed (design={design_idx}, rc={proc.returncode}). "
                            f"See {log_path}"
                        )
                    call.output_artifact = str(designs_dir / f"design_{design_idx:03d}.pdb")
            # Aggregate per-design logs into afcycdesign_results.csv (the format
            # the existing viz expects). The skill md documents the parser.
            self._build_results_csv(designs_dir)
            self.save_checkpoint("submit", n_designs=n_designs)

        return self._collect_and_score()

    def _build_results_csv(self, designs_dir: Path) -> None:
        """Parse final-iteration metrics from each per-design log + sequence from PDB."""
        import re
        binder_len = int(self.ctx.target.binder_length or 12)
        rows = []
        for log_path in sorted(designs_dir.glob("design_*.log")):
            metrics = {"design": log_path.stem, "sequence": "", "loss": "",
                       "i_con": "", "plddt": "", "ptm": "", "i_ptm": ""}
            text = log_path.read_text()
            for line in reversed(text.splitlines()):
                m = re.match(r".*loss\s+(\S+)\s+i_con\s+(\S+)\s+plddt\s+(\S+)\s+ptm\s+(\S+)\s+i_ptm\s+(\S+)", line)
                if m:
                    metrics.update({"loss": m.group(1), "i_con": m.group(2),
                                    "plddt": m.group(3), "ptm": m.group(4),
                                    "i_ptm": m.group(5)})
                    break
            # Sequence extraction: cyclic_binder_design.py emits the binder as the
            # first `binder_length` residues of the output PDB (chain A or B).
            pdb_path = designs_dir / f"{log_path.stem}.pdb"
            if pdb_path.is_file():
                metrics["sequence"] = self._binder_seq_from_pdb(pdb_path, binder_len)
            rows.append(metrics)
        with (self.out_dir / "afcycdesign_results.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["design", "sequence", "loss", "i_con",
                                              "plddt", "ptm", "i_ptm"])
            w.writeheader()
            w.writerows(rows)

    @staticmethod
    def _binder_seq_from_pdb(pdb_path: Path, binder_len: int) -> str:
        """Extract the first `binder_len` residues from the first chain of `pdb_path`."""
        three_to_one = {
            "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
            "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
            "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
            "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
        }
        seen = []
        for line in pdb_path.read_text().splitlines():
            if not line.startswith(("ATOM", "HETATM")):
                continue
            resname = line[17:20].strip()
            chain = line[21:22]
            try:
                resi = int(line[22:26])
            except ValueError:
                continue
            key = (chain, resi)
            if key in seen:
                continue
            seen.append(key)
            if len(seen) >= binder_len:
                break
        # Re-walk the file collecting one residue per (chain, resi) in seen order.
        ordered = sorted(set(seen), key=lambda kr: (kr[0], kr[1]))[:binder_len]
        seq_map: dict[tuple, str] = {}
        for line in pdb_path.read_text().splitlines():
            if not line.startswith(("ATOM", "HETATM")):
                continue
            resname = line[17:20].strip()
            try:
                key = (line[21:22], int(line[22:26]))
            except ValueError:
                continue
            if key in ordered and key not in seq_map:
                seq_map[key] = three_to_one.get(resname, "X")
        return "".join(seq_map[k] for k in ordered)

    # ------------------------------------------------------------------
    # Mock mode
    # ------------------------------------------------------------------
    def run_mock(self) -> dict[str, Any]:
        if not self.stage_completed("target_qc"):
            self.tracer.log_target_qc(self.ctx.target.target_pdb, ok=True, notes="mock skip")
            self.save_checkpoint("target_qc")

        if not self.stage_completed("submit"):
            self.tracer.log_planning(
                f"[mock] submit afcycdesign binder design for {self.ctx.target.target_short}"
            )
            rng = random.Random(self.ctx.seed * 7919 + hash(self.ctx.target.task_id) % 1000)
            with self.tracer.tool_call(
                "afcycdesign_mcp.cycpep_target_complex_pred",
                input_artifact=self.ctx.target.target_pdb,
            ) as call:
                # Synthesize 10 candidates with realistic distributions
                rows = []
                for i in range(10):
                    plddt = round(rng.gauss(0.78, 0.08), 3)
                    iptm = round(rng.gauss(0.55, 0.12), 3)
                    ptm = round(rng.gauss(0.72, 0.08), 3)
                    ipae = round(max(0.05, rng.gauss(0.18, 0.06)), 3)
                    loss = round(rng.gauss(2.5, 0.4), 3)
                    rows.append({
                        "design": f"binder_{i:03d}",
                        "sequence": "".join(rng.choices("ACDEFGHIKLMNPQRSTVWY", k=self.ctx.target.binder_length or 12)),
                        "loss": loss,
                        "i_con": ipae,
                        "plddt": plddt,
                        "ptm": ptm,
                        "i_ptm": iptm,
                    })
                # Write the synthetic results in the same format the real script produces.
                results_csv = self.out_dir / "afcycdesign_results.csv"
                with results_csv.open("w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=["design", "sequence", "loss", "i_con", "plddt", "ptm", "i_ptm"])
                    w.writeheader()
                    w.writerows(rows)
                call.output_artifact = str(results_csv)
                call.notes = f"mock generated {len(rows)} synthetic candidates"
            self.save_checkpoint("submit", n_synthetic=10)

        return self._collect_and_score()

    # ------------------------------------------------------------------
    # Common collect/filter/score (shared between real and mock)
    # ------------------------------------------------------------------
    def _target_qc(self, root: Path) -> None:
        pdb_path = root / self.ctx.target.target_pdb
        if pdb_path.is_file():
            self.tracer.log_target_qc(str(pdb_path), ok=True, notes=f"local file: {pdb_path}")
            return
        # Local file missing — accept if target_pdb is a bare 4-letter PDB code
        # (cyclic_binder_design.py will download via --pdb_code).
        stem = Path(self.ctx.target.target_pdb).stem
        if len(stem) == 4 and stem.isalnum():
            self.tracer.log_target_qc(str(pdb_path), ok=True,
                                      notes=f"will auto-download PDB code {stem}")
            return
        notes = f"missing PDB: {pdb_path}; not a downloadable PDB code"
        self.tracer.log_target_qc(str(pdb_path), ok=False, notes=notes)
        raise FileNotFoundError(notes)

    def _collect_and_score(self) -> dict[str, Any]:
        results_csv = self.out_dir / "afcycdesign_results.csv"
        if not results_csv.is_file():
            raise FileNotFoundError(f"missing {results_csv}; afcycdesign did not produce output")
        with results_csv.open() as f:
            raw = list(csv.DictReader(f))
        n_in = len(raw)

        # Filter + score
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
                "candidate_id": n["design"] or f"binder_{i:03d}",
                "sequence_or_helm": n["sequence"],
                "rank": 0,
                "pass_status": passes,
                "pass_reason": reason,
                "plddt": n["plddt"],
                "iptm": n["iptm"],
                "ipae": n["i_con"],   # informational; not gated on
                "ddg": "",
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

        # Sort by composite score desc and assign rank
        rows_out.sort(key=lambda r: r["composite_score"], reverse=True)
        for rank, r in enumerate(rows_out, start=1):
            r["rank"] = rank

        # Write candidate_metrics.csv
        with self._candidate_csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
            w.writeheader()
            w.writerows(rows_out)

        self.tracer.log_filter(n_in=n_in, n_pass=n_pass, n_fail=n_fail,
                               reason="afcycdesign primary gate (pLDDT/iPTM/iPAE)")
        self.save_checkpoint("collect", n_pass=n_pass, n_fail=n_fail)

        return {
            "n_candidates": n_in,
            "n_pass": n_pass,
            "n_fail": n_fail,
            "top_composite": rows_out[0]["composite_score"] if rows_out else None,
            "candidate_csv": str(self._candidate_csv),
        }
