"""Aggregate per-run summaries + traces + candidate CSVs into the four roll-up
tables consumed by `make_figures.py`:

    benchmark/summary/task_summary.csv       — one row per (task, run)
    benchmark/summary/candidate_summary.csv  — every candidate from every run
    benchmark/summary/agent_summary.csv      — agent process metrics per run
    benchmark/summary/llm_comparison.csv     — paired metrics on the 9-task LLM grid

Run after each batch of benchmark runs:
    python -m benchmark.scripts.aggregate_metrics

The aggregator reads `benchmark/runs/<run_id>/{summary.json,candidate_metrics.csv,agent_trace.jsonl}`
for every run dir present, regardless of mode. Mock-mode runs are flagged via
the `mode` column so analyses can filter them out.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / "benchmark" / "configs" / "thresholds.py").is_file():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break

from benchmark.configs import thresholds as cfg
from benchmark.scripts.workflow_runners.base import find_project_root


def _load_traces(trace_path: Path) -> list[dict]:
    if not trace_path.is_file():
        return []
    return [json.loads(l) for l in trace_path.read_text().splitlines() if l.strip()]


def agent_metrics_from_trace(events: list[dict]) -> dict[str, Any]:
    """Compute the per-run process metrics from docs/benchmark_plan.md section 6.1."""
    if not events:
        return {}
    tool_calls = [e for e in events if e["event_type"] == "tool_call"]
    tool_results = [e for e in events if e["event_type"] == "tool_result"]
    errors = [e for e in events if e["event_type"] == "error"]
    retries = [e for e in events if e["event_type"] == "retry"]
    interventions = [e for e in events if e.get("user_intervention")]

    compute_time = sum(e.get("wall_time_sec", 0) or 0 for e in tool_results)
    token_input = sum(e.get("token_input", 0) or 0 for e in events)
    token_output = sum(e.get("token_output", 0) or 0 for e in events)

    # Self-recovery: error followed by retry of the same tool that later succeeds.
    failures = [e for e in events if e.get("status") == "failure"]
    recovered = 0
    for f in failures:
        # Look for a successful tool_result on the same tool *after* this event.
        f_idx = events.index(f)
        for later in events[f_idx + 1:]:
            if (later.get("tool_name") == f.get("tool_name")
                    and later.get("status") == "success"
                    and later["event_type"] == "tool_result"):
                recovered += 1
                break

    final_reports = [e for e in events if e["event_type"] == "final_report"]
    open_evt = next((e for e in events if e["event_type"] == "trace_open"), None)
    close_evt = next((e for e in reversed(events) if e["event_type"] == "trace_close"), None)
    return {
        "n_events": len(events),
        "n_tool_calls": len(tool_calls),
        "n_errors": len(errors),
        "n_retries": len(retries),
        "n_interventions": len(interventions),
        "compute_time_sec": round(compute_time, 2),
        "token_input": token_input,
        "token_output": token_output,
        "self_recovery_rate": round(recovered / len(failures), 3) if failures else None,
        "no_intervention_success": bool(final_reports) and len(interventions) == 0,
        "first_timestamp": open_evt["timestamp"] if open_evt else None,
        "last_timestamp": close_evt["timestamp"] if close_evt else None,
    }


def aggregate(runs_dir: Path, summary_dir: Path) -> dict[str, int]:
    summary_dir.mkdir(parents=True, exist_ok=True)

    task_rows = []
    cand_rows = []
    agent_rows = []
    llm_grid_rows = []

    grid_tasks = {t for ts in cfg.llm_grid().values() for t in ts}

    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        summary_p = run_dir / "summary.json"
        if not summary_p.is_file():
            continue
        s = json.loads(summary_p.read_text())
        run_id = s["run_id"]
        task_id = s["task_id"]

        # Task-level rollup (one row per run_id).
        task_rows.append({
            "run_id": run_id,
            "task_id": task_id,
            "workflow": s["workflow"],
            "llm_backend": s["llm_backend"],
            "mode": s["mode"],
            "n_candidates": s.get("n_candidates", 0),
            "n_pass": s.get("n_pass", 0),
            "n_fail": s.get("n_fail", 0),
            "top_composite": s.get("top_composite"),
            "wall_time_sec": s.get("wall_time_sec"),
        })

        # Candidate-level rollup.
        cand_p = run_dir / "candidate_metrics.csv"
        if cand_p.is_file():
            with cand_p.open() as f:
                cand_rows.extend(list(csv.DictReader(f)))

        # Agent-level rollup.
        events = _load_traces(run_dir / "agent_trace.jsonl")
        agent_m = agent_metrics_from_trace(events)
        agent_m.update({"run_id": run_id, "task_id": task_id, "workflow": s["workflow"],
                        "llm_backend": s["llm_backend"], "mode": s["mode"],
                        "wall_time_sec": s.get("wall_time_sec")})
        agent_rows.append(agent_m)

        # LLM-grid subset.
        if task_id in grid_tasks:
            llm_grid_rows.append({
                "run_id": run_id, "task_id": task_id, "workflow": s["workflow"],
                "llm_backend": s["llm_backend"], "mode": s["mode"],
                "n_pass": s.get("n_pass", 0),
                "top_composite": s.get("top_composite"),
                "wall_time_sec": s.get("wall_time_sec"),
                "compute_time_sec": agent_m.get("compute_time_sec"),
                "n_errors": agent_m.get("n_errors"),
                "self_recovery_rate": agent_m.get("self_recovery_rate"),
                "no_intervention_success": agent_m.get("no_intervention_success"),
                "token_total": (agent_m.get("token_input", 0) or 0) + (agent_m.get("token_output", 0) or 0),
            })

    _write_csv(summary_dir / "task_summary.csv", task_rows)
    _write_csv(summary_dir / "candidate_summary.csv", cand_rows)
    _write_csv(summary_dir / "agent_summary.csv", agent_rows)
    _write_csv(summary_dir / "llm_comparison.csv", llm_grid_rows)

    return {
        "n_runs": len(task_rows),
        "n_candidates": len(cand_rows),
        "n_grid_runs": len(llm_grid_rows),
    }


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("# (no rows)\n")
        return
    keys = list({k for r in rows for k in r})
    keys.sort()
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs-dir", default=None, type=Path)
    p.add_argument("--summary-dir", default=None, type=Path)
    args = p.parse_args(argv)

    root = find_project_root()
    runs_dir = args.runs_dir or root / "benchmark" / "runs"
    summary_dir = args.summary_dir or root / "benchmark" / "summary"
    counts = aggregate(runs_dir, summary_dir)
    print(f"aggregated: runs={counts['n_runs']}  candidates={counts['n_candidates']}  "
          f"llm_grid_runs={counts['n_grid_runs']}")
    print(f"  -> {summary_dir}/task_summary.csv")
    print(f"  -> {summary_dir}/candidate_summary.csv")
    print(f"  -> {summary_dir}/agent_summary.csv")
    print(f"  -> {summary_dir}/llm_comparison.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
