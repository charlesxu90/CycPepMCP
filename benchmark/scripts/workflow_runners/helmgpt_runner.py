"""HELM-GPT workflow runner.

Real mode: orchestrates the three phases used by `examples/co_opt_kras_kd_perm/`:
  Phase 1: HELM-GPT RL with target-specific reward model (helm_gpt_mcp).
  Phase 2: Structural evaluation, routed by heavy-atom count:
           <=128 atoms => Boltz-2 + AF3 + Gnina (Track A)
           > 128 atoms => AF3 + Gnina only (Track B)
  Phase 3: Composite scoring + ranking via existing postprocess_phase3.py.

Reward-model gate: before Phase 1 starts, the runner checks that the target's
trained XGBoost predictor reports scaffold-split test Spearman >= 0.4
(workflows.yaml `helmgpt.pass_gates.reward_model.spearman_min_pass`). Below
that threshold the run aborts with `error_type=scientific` so the agent eval
correctly logs a reward-model failure.

Mock mode: synthesizes 20 phase3-like candidates so we can validate plumbing.
"""
from __future__ import annotations

import csv
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from benchmark.configs import thresholds as cfg
from benchmark.scripts.agent_trace import ErrorType
from benchmark.scripts.workflow_runners.base import WorkflowRunner, find_project_root


class HelmGPTRunner(WorkflowRunner):
    workflow_name = "helmgpt"

    # ------------------------------------------------------------------
    @staticmethod
    def _norm(c: dict[str, Any]) -> dict[str, Any]:
        """Canonicalize HELM-GPT phase3 columns. The case3 reference CSV ships
        {final_rank, rank, helm_seqs, smiles, n_heavy_atoms, kd_um,
         raw_permeability, aff_affinity_pred_value, aff_affinity_probability_binary,
         conf_iptm, conf_complex_plddt, cnn_affinity, vina_affinity,
         n_kd, n_perm, n_aff, n_prob, n_iptm, n_cnn, n_vina, composite}. The mock
        runner emits a different (simpler) schema; we map both into the same shape."""
        n = {k.lower(): v for k, v in c.items()}
        return {
            "design_id": n.get("design_id") or f"helm_{n.get('rank', n.get('final_rank', 0))}",
            "helm": n.get("helm_seqs") or n.get("helm", ""),
            "smiles": n.get("smiles", ""),
            "kd_um": n.get("kd_um", n.get("predicted_kd_um", "")),
            "permeability": n.get("raw_permeability", n.get("permeability", n.get("logpapp", ""))),
            "boltz_aff": n.get("aff_affinity_pred_value", n.get("boltz_avg_aff", "")),
            "boltz_prob": n.get("aff_affinity_probability_binary", n.get("boltz_avg_prob", "")),
            "boltz_iptm": n.get("conf_iptm", n.get("boltz_iptm", n.get("af3_iptm", ""))),
            "af3_plddt": n.get("conf_complex_plddt", n.get("af3_plddt", "")),
            "gnina_cnn": n.get("cnn_affinity", n.get("gnina_cnn_pkd", n.get("gnina_cnn", ""))),
            "gnina_vina": n.get("vina_affinity", n.get("gnina_vina", "")),
            "composite": n.get("composite", n.get("composite_score", "")),
        }

    def apply_primary_gate(self, c: dict[str, Any]) -> tuple[bool, str]:
        gate = cfg.HELMGPT_PASS_GATE.primary
        n = self._norm(c)
        try:
            kd_um = float(n["kd_um"])
            perm = float(n["permeability"])
            af3_iptm = float(n["boltz_iptm"])      # case3 uses Boltz-2 iPTM as the structural-eval iPTM
            cnn = float(n["gnina_cnn"])
            vina = float(n["gnina_vina"])
        except (TypeError, ValueError):
            return False, "non-numeric metric"
        # Phase-1 gate: Phase-1 sentinels mean parser failed (perm=-10, KD=10**5 uM).
        if perm <= cfg.PERM_FAIL_SENTINEL + 1e-9:
            return False, "phase1 parser sentinel (no scored permeability)"
        if kd_um > gate["kd_um_max"]:
            return False, f"KD={kd_um:.2f}uM>{gate['kd_um_max']}"
        if perm < gate["perm_logpapp_min"]:
            return False, f"perm={perm:.2f}<{gate['perm_logpapp_min']}"
        if af3_iptm < gate["boltz_iptm_min"]:
            return False, f"struct_iPTM={af3_iptm:.2f}<{gate['boltz_iptm_min']}"
        if cnn < gate["gnina_cnn_min"]:
            return False, f"GninaCNN={cnn:.2f}<{gate['gnina_cnn_min']}"
        if vina > gate["gnina_vina_max"]:
            return False, f"GninaVina={vina:.2f}>{gate['gnina_vina_max']}"
        return True, "pass"

    def composite_score(self, c: dict[str, Any]) -> float:
        """Reads precomputed `composite` from postprocess_phase3.py output if present."""
        n = self._norm(c)
        try:
            return round(float(n["composite"]), 4)
        except (TypeError, ValueError):
            return 0.0

    # ------------------------------------------------------------------
    # Reward-model Spearman gate (per workflows.yaml helmgpt.pass_gates.reward_model)
    # ------------------------------------------------------------------
    def check_reward_model(self) -> None:
        """Raise if reward-model Spearman < workflows.yaml threshold."""
        rm_path = self.ctx.target.reward_model
        if not rm_path:
            return  # KRAS positive control reuses pretrained predictor; skip
        # `reward_model` in targets.csv is the path to the trained .pkl; the
        # companion metrics.json sits next to it under benchmark/reward_models/trained/.
        rm_pkl = find_project_root() / rm_path
        metrics_json = rm_pkl.parent / f"{self.ctx.target.task_id.lower()}_metrics.json"
        gate = cfg.HELMGPT_PASS_GATE.extras["reward_model"]
        threshold = gate["spearman_min_pass"]
        if not metrics_json.is_file():
            self.tracer.log_error(
                "reward_model_gate", ErrorType.SCIENTIFIC,
                f"missing {metrics_json}; cannot verify Spearman>={threshold}",
            )
            raise RuntimeError(
                f"reward-model metrics missing for {self.ctx.target.task_id}: {metrics_json}"
            )
        m = json.loads(metrics_json.read_text())
        spearman = float(m.get("scaffold_split_spearman", m.get("spearman", -1)))
        if spearman < threshold:
            self.tracer.log_error(
                "reward_model_gate", ErrorType.SCIENTIFIC,
                f"Spearman={spearman:.3f} < {threshold} (gate); aborting before RL",
            )
            raise RuntimeError(
                f"reward model for {self.ctx.target.task_id} fails Spearman gate "
                f"({spearman:.3f} < {threshold}); promote a backup target"
            )
        self.tracer.tracer = None  # no-op for clarity
        self.save_checkpoint("reward_model_gate", spearman=spearman)

    # ------------------------------------------------------------------
    def run_real(self) -> dict[str, Any]:
        # Stage 0: reward model gate (skipped for KRAS positive control).
        if not self.stage_completed("reward_model_gate"):
            self.tracer.log_planning(
                f"verify reward model for {self.ctx.target.task_id} "
                f"(Spearman gate from workflows.yaml)"
            )
            self.check_reward_model()

        # Phases 1-3 (RL + structural eval). For KRAS positive control, the
        # canonical reference run lives in `examples/co_opt_kras_kd_perm/`
        # with outputs under `results/case3_kras_helmgpt/`. Pre-seed
        # `<run_dir>/phase3_final_ranking.csv` and the `phase3` checkpoint to
        # reuse those outputs without re-running the multi-hour phase chain.
        # New targets (PD-1/PD-L1, MDM2/p53) require a curated reward model from
        # W2(c) and a per-target Phase 1-3 setup; this branch raises until that
        # path is wired.
        if not self.stage_completed("phase3"):
            root = find_project_root()
            required_tool_dirs = [
                root / "tool-mcps" / "helm_gpt_mcp",
                root / "tool-mcps" / "boltz_mcp",
                root / "tool-mcps" / "alphafold3_mcp",
                root / "tool-mcps" / "gnina_mcp",
            ]
            missing = [str(p) for p in required_tool_dirs if not p.is_dir()]
            if missing:
                self.tracer.log_error("helmgpt.environment", ErrorType.ENVIRONMENT,
                                      f"missing tool-mcp dirs: {missing}")
                raise RuntimeError(
                    f"helmgpt runner requires installed MCP tools; missing: {missing}. "
                    "Run `cpmcp install helm_gpt_mcp boltz_mcp alphafold3_mcp gnina_mcp` first."
                )
            raise NotImplementedError(
                f"helmgpt fresh real-mode RL + structural eval not yet wired for "
                f"{self.ctx.target.task_id}. To reuse case3 outputs for KRAS, "
                f"pre-seed <run_dir>/phase3_final_ranking.csv and mark the 'phase3' "
                f"stage in checkpoint.json. New targets (PD-1/PDL1, MDM2/p53) need "
                f"the W2(c) data-curation pipeline to complete first."
            )

        return self._collect_and_score(self.out_dir / "phase3_final_ranking.csv")

    # ------------------------------------------------------------------
    def run_mock(self) -> dict[str, Any]:
        if not self.stage_completed("reward_model_gate"):
            self.tracer.log_planning(f"[mock] reward-model gate for {self.ctx.target.task_id}")
            self.tracer.log_filter(n_in=0, n_pass=0, n_fail=0,
                                   reason=f"mock spearman=0.85 >= 0.4 gate")
            self.save_checkpoint("reward_model_gate", spearman=0.85)

        if not self.stage_completed("phase3"):
            self.tracer.log_planning(f"[mock] helm-gpt RL + structural eval for {self.ctx.target.target_short}")
            rng = random.Random(self.ctx.seed * 4099 + hash(self.ctx.target.task_id) % 1000)
            with self.tracer.tool_call(
                "helmgpt.full_pipeline",
                input_artifact=self.ctx.target.target_dataset or "case3_kras_dataset",
            ) as call:
                rows = []
                for i in range(20):
                    kd_um = round(max(0.05, rng.lognormvariate(0.5, 1.0)), 3)
                    perm = round(rng.gauss(-5.6, 0.8), 3)
                    aff = round(rng.gauss(0.3, 0.4), 3)
                    prob = round(min(1.0, max(0.0, rng.gauss(0.55, 0.18))), 3)
                    boltz_iptm = round(min(1.0, max(0.0, rng.gauss(0.72, 0.12))), 3)
                    af3_iptm = round(min(1.0, max(0.0, rng.gauss(0.65, 0.15))), 3)
                    cnn = round(rng.gauss(6.5, 1.2), 3)
                    vina = round(rng.gauss(-7.5, 1.2), 3)
                    composite = round(rng.gauss(0.55, 0.12), 3)
                    rows.append({
                        "design_id": f"helm_{i:03d}",
                        "helm": f"PEPTIDE1{{[ac].A.G.{rng.choice(['F','W','Y'])}.K.[am]}}$$$$",
                        "kd_um": kd_um, "permeability": perm,
                        "boltz_avg_aff": aff, "boltz_avg_prob": prob,
                        "boltz_iptm": boltz_iptm, "af3_iptm": af3_iptm,
                        "gnina_cnn_pkd": cnn, "gnina_vina": vina,
                        "composite": composite,
                    })
                phase3_csv = self.out_dir / "phase3_final_ranking.csv"
                with phase3_csv.open("w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                    w.writeheader()
                    w.writerows(rows)
                call.output_artifact = str(phase3_csv)
                call.notes = f"mock generated {len(rows)} synthetic candidates"
            self.save_checkpoint("phase3", n_synthetic=20)

        return self._collect_and_score(self.out_dir / "phase3_final_ranking.csv")

    # ------------------------------------------------------------------
    def _collect_and_score(self, phase3_csv: Path) -> dict[str, Any]:
        if not phase3_csv.is_file():
            raise FileNotFoundError(f"missing {phase3_csv}; helmgpt phase 3 produced no output")
        with phase3_csv.open() as f:
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
                "target_id": self.ctx.target.target_short,
                "workflow": self.workflow_name,
                "run_id": self.ctx.run_id,
                "candidate_id": n["design_id"] or f"helm_{i:03d}",
                "sequence_or_helm": n["helm"],
                "rank": 0,
                "pass_status": passes,
                "pass_reason": reason,
                "plddt": n["af3_plddt"],
                "iptm": n["boltz_iptm"],
                "ipae": "",
                "ddg": "",
                "gnina_cnn_pkd": n["gnina_cnn"],
                "predicted_kd_um": n["kd_um"],
                "logpapp": n["permeability"],
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
                               reason="helmgpt primary gate (KD/perm/iPTM/Gnina)")
        self.save_checkpoint("collect", n_pass=n_pass, n_fail=n_fail)
        return {
            "n_candidates": n_in,
            "n_pass": n_pass,
            "n_fail": n_fail,
            "top_composite": rows_out[0]["composite_score"] if rows_out else None,
            "candidate_csv": str(self._candidate_csv),
        }
