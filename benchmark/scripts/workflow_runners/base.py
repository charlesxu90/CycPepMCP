"""Common base class for workflow runners.

Each workflow runner (afcycdesign / rfpeptides / helmgpt) implements the same
contract: take a row from `targets.csv`, run the workflow end-to-end, write
candidate metrics into `benchmark/runs/{run_id}/candidate_metrics.csv`, and
emit `agent_trace.jsonl` events along the way.

A runner supports two execution modes:
  - real: invoke the underlying MCP / CLI tooling. Needs GPU and installed MCPs.
  - mock: generate deterministic synthetic candidates so we can test the
    plumbing (configs, tracer, aggregator, viz) without a GPU.

Checkpointing: each runner writes `<run_dir>/checkpoint.json` after each major
stage. On `--resume`, the runner reads the checkpoint and skips completed
stages. Resume semantics are stage-level — an in-progress stage is restarted.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Ensure benchmark.* imports work regardless of cwd.
_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / "benchmark" / "configs" / "thresholds.py").is_file():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break

from benchmark.configs import thresholds as cfg  # noqa: E402
from benchmark.scripts.agent_trace import AgentTracer, ErrorType  # noqa: E402


# ---------------------------------------------------------------------------
# Target row + run context
# ---------------------------------------------------------------------------

@dataclass
class TargetRow:
    """One row from `benchmark/configs/targets.csv` after type coercion."""
    task_id: str
    target_short: str
    target_full: str
    workflow: str
    target_pdb: str
    target_chain: str
    hotspots: list[int]
    binder_length: Optional[int]
    num_designs: Optional[int]
    ipae_pass_gate: Optional[float]
    ddg_pass_gate: Optional[float]
    target_dataset: str
    reward_model: str
    rl_n_steps: Optional[int]
    rl_batch_size: Optional[int]
    in_llm_grid: bool
    notes: str

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> "TargetRow":
        def _opt_int(v: str) -> Optional[int]:
            return int(v) if v.strip() else None
        def _opt_float(v: str) -> Optional[float]:
            return float(v) if v.strip() else None
        def _hotspot_list(v: str) -> list[int]:
            v = v.strip()
            if not v or v.startswith("TBD"):
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return cls(
            task_id=row["task_id"].strip(),
            target_short=row["target_short"].strip(),
            target_full=row["target_full"].strip(),
            workflow=row["workflow"].strip(),
            target_pdb=row["target_pdb"].strip(),
            target_chain=row["target_chain"].strip(),
            hotspots=_hotspot_list(row["hotspots"]),
            binder_length=_opt_int(row["binder_length"]),
            num_designs=_opt_int(row["num_designs"]),
            ipae_pass_gate=_opt_float(row["ipae_pass_gate"]),
            ddg_pass_gate=_opt_float(row["ddg_pass_gate"]),
            target_dataset=row["target_dataset"].strip(),
            reward_model=row["reward_model"].strip(),
            rl_n_steps=_opt_int(row["rl_n_steps"]),
            rl_batch_size=_opt_int(row["rl_batch_size"]),
            in_llm_grid=row["in_llm_grid"].strip().upper() == "TRUE",
            notes=row["notes"].strip(),
        )


@dataclass
class RunContext:
    """Per-run state passed into a runner."""
    target: TargetRow
    run_id: str               # e.g. AF_MDM2_R1_CLAUDE
    seed: int                 # repeat seed (1, 2, 3...)
    llm_backend: str          # 'claude' / 'gpt' / 'gemini' / 'mock'
    out_dir: Path             # benchmark/runs/{run_id}/
    mode: str                 # 'real' / 'mock'
    resume: bool              # if True, honor checkpoint.json
    project_root: Path        # CycPepMCP repo root


# ---------------------------------------------------------------------------
# Runner base
# ---------------------------------------------------------------------------

class WorkflowRunner:
    """Subclasses implement run_real() and run_mock(). Stages and metrics are
    emitted via self.tracer."""

    workflow_name: str = ""   # 'afcycdesign' / 'rfpeptides' / 'helmgpt'

    def __init__(self, ctx: RunContext):
        self.ctx = ctx
        self.out_dir = Path(ctx.out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._checkpoint_path = self.out_dir / "checkpoint.json"
        self._candidate_csv = self.out_dir / "candidate_metrics.csv"
        self._summary_json = self.out_dir / "summary.json"
        self._tracer: Optional[AgentTracer] = None
        self._t_start: float = 0.0

    # --- Lifecycle ---------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """Main entry. Opens tracer, dispatches to run_real/run_mock, writes summary."""
        self._tracer = AgentTracer.open(
            run_id=self.ctx.run_id,
            task_id=self.ctx.target.task_id,
            llm_backend=self.ctx.llm_backend,
            out_path=self.out_dir / "agent_trace.jsonl",
        )
        self._t_start = time.perf_counter()
        try:
            if self.ctx.mode == "mock":
                summary = self.run_mock()
            elif self.ctx.mode == "real":
                summary = self.run_real()
            else:
                raise ValueError(f"unknown mode {self.ctx.mode!r}; expected 'real'/'mock'")
        except Exception as e:
            self._tracer.log_error(self.workflow_name, ErrorType.RUNTIME,
                                   f"runner crashed: {type(e).__name__}: {e}")
            self._tracer.close()
            raise
        wall_time = round(time.perf_counter() - self._t_start, 2)
        summary["wall_time_sec"] = wall_time
        summary["run_id"] = self.ctx.run_id
        summary["task_id"] = self.ctx.target.task_id
        summary["workflow"] = self.workflow_name
        summary["mode"] = self.ctx.mode
        summary["llm_backend"] = self.ctx.llm_backend
        self._summary_json.write_text(json.dumps(summary, indent=2, default=str))
        self._tracer.log_final_report(str(self._summary_json))
        self._tracer.close()
        return summary

    # --- Subclass hooks ----------------------------------------------------

    def run_real(self) -> dict[str, Any]:
        raise NotImplementedError

    def run_mock(self) -> dict[str, Any]:
        raise NotImplementedError

    # --- Checkpoint helpers ------------------------------------------------

    def _read_checkpoint_file(self) -> dict[str, Any]:
        """Read checkpoint.json from disk regardless of resume mode."""
        if self._checkpoint_path.is_file():
            return json.loads(self._checkpoint_path.read_text())
        return {}

    def load_checkpoint(self) -> dict[str, Any]:
        """Return checkpoint state for stage_completed() checks. Respects --resume:
        if resume is False, the runner sees an empty checkpoint and re-runs every stage,
        though completed stages still get persisted to disk so a later --resume works.
        """
        if self.ctx.resume:
            return self._read_checkpoint_file()
        return {}

    def save_checkpoint(self, stage: str, **payload: Any) -> None:
        """Persist this stage to disk. Always merges with existing on-disk state."""
        ckpt = self._read_checkpoint_file()
        ckpt[stage] = {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        self._checkpoint_path.write_text(json.dumps(ckpt, indent=2, default=str))

    def stage_completed(self, stage: str) -> bool:
        return stage in self.load_checkpoint()

    # --- Tracer accessor ---------------------------------------------------

    @property
    def tracer(self) -> AgentTracer:
        if self._tracer is None:
            raise RuntimeError("tracer not initialized; call .run() instead of using directly")
        return self._tracer

    # --- PASS-gate helpers (centralized via thresholds.py) -----------------

    def apply_primary_gate(self, candidate_row: dict[str, Any]) -> tuple[bool, str]:
        """Return (passes, reason). Subclasses override if they need richer logic."""
        return True, "default base gate (subclass should override)"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_project_root(start: Optional[Path] = None) -> Path:
    """Walk up from `start` (or this file) to find the CycPepMCP project root."""
    p = (start or Path(__file__)).resolve()
    for _ in range(10):
        if (p / "tool-mcps").is_dir() and (p / "benchmark" / "configs" / "thresholds.py").is_file():
            return p
        p = p.parent
    raise RuntimeError(f"cannot find project root from {start or __file__}")


def load_targets() -> dict[str, TargetRow]:
    """Read benchmark/configs/targets.csv into a dict keyed by task_id."""
    import csv
    csv_path = cfg.TARGETS_CSV
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    return {r["task_id"].strip(): TargetRow.from_csv_row(r) for r in rows}


def make_run_id(task_id: str, seed: int, llm_backend: str) -> str:
    """Per Appendix A of docs/benchmark_plan.md: `{TASK}_R{n}_{LLM}` (TASK already encodes WF)."""
    return f"{task_id}_R{seed}_{llm_backend.upper()}"
