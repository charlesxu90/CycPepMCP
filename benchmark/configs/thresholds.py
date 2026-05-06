"""Centralized PASS-gate, composite-weight, and run-parameter constants.

Single source of truth for the benchmark. All consumers — workflow runners,
postprocess scripts (`examples/case3_*/postprocess_phase{1,3}.py`), and the three
viz scripts (`workflow-skills/scripts/*/_viz.py`) — must import from this module
instead of redefining constants locally. The module loads `workflows.yaml` and
exposes typed constants and helpers.

Locked W1 of the benchmark plan (docs/benchmark_plan.md). Edits propagate from
`workflows.yaml`; do not hardcode overrides here.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIGS_DIR = Path(__file__).resolve().parent
WORKFLOWS_YAML = CONFIGS_DIR / "workflows.yaml"
TARGETS_CSV = CONFIGS_DIR / "targets.csv"
LLM_BACKENDS_YAML = CONFIGS_DIR / "llm_backends.yaml"


@lru_cache(maxsize=1)
def _load_workflows() -> dict[str, Any]:
    with WORKFLOWS_YAML.open() as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def _load_llm_backends() -> dict[str, Any]:
    with LLM_BACKENDS_YAML.open() as f:
        return yaml.safe_load(f)


def workflow_config(workflow: str) -> dict[str, Any]:
    """Return the full config block for a workflow ('afcycdesign' / 'rfpeptides' / 'helmgpt')."""
    cfg = _load_workflows()
    if workflow not in cfg:
        raise KeyError(f"unknown workflow: {workflow!r}; expected one of "
                       f"{[k for k in cfg if k not in ('version', 'locked_at', 'repeatability_reruns')]}")
    return cfg[workflow]


# ---------------------------------------------------------------------------
# Pass gates
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PassGate:
    """Workflow PASS gate. Field set varies by workflow; missing fields are None."""
    primary: dict[str, Any]
    excellent: dict[str, Any]
    extras: dict[str, Any]   # e.g. reward_model gate for HELM-GPT, phase1_gate


def pass_gate(workflow: str) -> PassGate:
    cfg = workflow_config(workflow)
    gates = cfg.get("pass_gates", {})
    primary = dict(gates.get("primary", {}))
    excellent = dict(gates.get("excellent", {}))
    extras: dict[str, Any] = {}
    if "reward_model" in gates:
        extras["reward_model"] = dict(gates["reward_model"])
    if workflow == "helmgpt" and "phase1_gate" in cfg:
        extras["phase1_gate"] = dict(cfg["phase1_gate"])
    if workflow == "rfpeptides":
        extras["per_target_thresholds"] = {
            k: dict(v) for k, v in cfg.get("per_target_thresholds", {}).items()
        }
    return PassGate(primary=primary, excellent=excellent, extras=extras)


def rfpeptides_target_threshold(target_short: str) -> dict[str, float]:
    """Resolve per-target iPAE/ddG threshold for RFpeptides.

    Falls back to the 'general' bucket if target name does not match any of
    {mcl1, mdm2, gabarap, rbta, pdl1}.
    """
    cfg = workflow_config("rfpeptides")
    table = cfg.get("per_target_thresholds", {})
    key = target_short.lower().replace("-", "").replace("_", "")
    if key in table:
        return dict(table[key])
    return dict(table.get("general", {"ipae": 0.30, "ddg": -30}))


# ---------------------------------------------------------------------------
# Composite-score weights
# ---------------------------------------------------------------------------

def composite_weights(workflow: str) -> dict[str, float]:
    """Composite-score weights for a workflow. Sum should equal 1.0."""
    return dict(workflow_config(workflow).get("composite_weights", {}))


def composite_weights_validated(workflow: str) -> dict[str, float]:
    """Same as composite_weights() but asserts weights sum to 1.0 (within 1e-6)."""
    w = composite_weights(workflow)
    total = sum(w.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"composite weights for {workflow!r} sum to {total!r}, expected 1.0")
    return w


# ---------------------------------------------------------------------------
# Convenience top-level constants (back-compat with existing code that expects
# module-level dicts). Prefer the functional API above for new code.
# ---------------------------------------------------------------------------

AFCYCDESIGN_PASS_GATE = pass_gate("afcycdesign")
RFPEPTIDES_PASS_GATE = pass_gate("rfpeptides")
HELMGPT_PASS_GATE = pass_gate("helmgpt")

AFCYCDESIGN_COMPOSITE_WEIGHTS = composite_weights("afcycdesign")
RFPEPTIDES_COMPOSITE_WEIGHTS = composite_weights("rfpeptides")
HELMGPT_COMPOSITE_WEIGHTS = composite_weights("helmgpt")

# Phase 1 HELM-GPT sentinels (matches existing postprocess_phase1.py constants)
_phase1 = HELMGPT_PASS_GATE.extras.get("phase1_gate", {})
PERM_PASS_THRESHOLD = _phase1.get("perm_pass_threshold", -6.0)
KD_PASS_LOG_THRESHOLD = _phase1.get("kd_pass_log_threshold", 1.0)
PERM_FAIL_SENTINEL = _phase1.get("perm_fail_sentinel", -10.0)
KD_FAIL_SENTINEL = _phase1.get("kd_fail_sentinel", 5.0)


# ---------------------------------------------------------------------------
# LLM backends
# ---------------------------------------------------------------------------

def llm_backends() -> dict[str, dict[str, Any]]:
    return dict(_load_llm_backends().get("backends", {}))


def llm_grid() -> dict[str, list[str]]:
    """Tasks that should run on all three LLM backends, keyed by workflow."""
    return {k: list(v) for k, v in _load_llm_backends().get("llm_grid", {}).items()}


def repeatability_reruns() -> list[dict[str, Any]]:
    """Tasks (with seed lists) that should be rerun for repeatability."""
    return list(_load_workflows().get("repeatability_reruns", []))


# ---------------------------------------------------------------------------
# Self-check: run as a script to validate config integrity.
# ---------------------------------------------------------------------------

def _self_check() -> None:
    """Validate weights sum to 1.0 and all expected workflows are present."""
    for wf in ("afcycdesign", "rfpeptides", "helmgpt"):
        w = composite_weights_validated(wf)
        gate = pass_gate(wf)
        print(f"{wf:14s}  weights_sum=1.000  primary_keys={sorted(gate.primary)}")
    grid = llm_grid()
    n_grid_tasks = sum(len(v) for v in grid.values())
    print(f"llm_grid_tasks={n_grid_tasks} (expected 9)")
    assert n_grid_tasks == 9, f"expected 9 tasks in llm_grid, got {n_grid_tasks}"
    backends = llm_backends()
    print(f"llm_backends={list(backends)}")
    assert set(backends) == {"claude", "gpt", "gemini"}, f"unexpected backends: {list(backends)}"
    reruns = repeatability_reruns()
    print(f"repeatability_reruns={[r['task_id'] for r in reruns]}")
    assert len(reruns) == 3, f"expected 3 repeatability reruns, got {len(reruns)}"
    print("OK: configs are internally consistent")


if __name__ == "__main__":
    _self_check()
