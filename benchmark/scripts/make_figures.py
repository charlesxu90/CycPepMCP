"""Reproduce manuscript Figures 2-5 from the aggregated benchmark CSVs.

Inputs (must exist; run `aggregate_metrics.py` first):
  benchmark/summary/task_summary.csv
  benchmark/summary/candidate_summary.csv
  benchmark/summary/agent_summary.csv
  benchmark/summary/llm_comparison.csv

Outputs (under `benchmark/figures/`):
  fig2_benchmark_design.{png,pdf}     panel: targets x workflows x metrics
  fig3_workflow_success.{png,pdf}     PASS heatmap + top-composite per target
  fig4_diversity_pareto.{png,pdf}     candidate score scatter + workflow-wise distributions
  fig5_agent_performance.{png,pdf}    agent metrics per workflow + LLM grid

Usage:
  python -m benchmark.scripts.make_figures            # all 4 figures
  python -m benchmark.scripts.make_figures --fig 3 5  # just 3 and 5
  python -m benchmark.scripts.make_figures --skip-mock  # exclude mock-mode runs
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / "benchmark" / "configs" / "thresholds.py").is_file():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break

from benchmark.configs import thresholds as cfg
from benchmark.scripts.workflow_runners.base import find_project_root


WORKFLOW_COLORS = {"afcycdesign": "#1f77b4", "rfpeptides": "#2ca02c", "helmgpt": "#d62728"}
LLM_COLORS = {"claude": "#7d4cdb", "gpt": "#10a37f", "gemini": "#1a73e8", "mock": "#888888"}


def _read_csv(path: Path) -> list[dict]:
    if not path.is_file() or path.read_text().startswith("# (no rows)"):
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def _filter_runs(rows: list[dict], skip_mock: bool) -> list[dict]:
    if not skip_mock:
        return rows
    return [r for r in rows if r.get("mode", "real") != "mock"]


def _placeholder_fig(out_path: Path, message: str) -> None:
    """Emit a placeholder PNG/PDF so figure counts stay consistent across mock/real."""
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=14,
            transform=ax.transAxes, color="#888")
    ax.set_axis_off()
    _save(fig, out_path)


def _save(fig: plt.Figure, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path.with_suffix(".png"), dpi=200, bbox_inches="tight")
    fig.savefig(out_path.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    # Print relative-to-repo when possible, else absolute (handles --out-dir outside repo).
    png = out_path.with_suffix(".png")
    try:
        display = png.relative_to(find_project_root())
    except ValueError:
        display = png
    print(f"  wrote {display}")


def fig2_design(summary_dir: Path, out_dir: Path) -> None:
    """Panel: target x workflow heatmap colored by PASS rate."""
    rows = _read_csv(summary_dir / "task_summary.csv")
    if not rows:
        print("  fig2: no task_summary.csv rows; skipping")
        return
    # Use latest non-mock run per task.
    by_task = {}
    for r in rows:
        if r.get("mode") == "mock":
            continue
        existing = by_task.get(r["task_id"])
        # Prefer a run with non-zero wall_time (real GPU run) over schema-mapped (~0s).
        if existing is None:
            by_task[r["task_id"]] = r
        else:
            try:
                if float(r.get("wall_time_sec") or 0) > float(existing.get("wall_time_sec") or 0):
                    by_task[r["task_id"]] = r
            except ValueError:
                pass
    targets = sorted(by_task)
    workflows = sorted({r["workflow"] for r in by_task.values()})
    fig, ax = plt.subplots(figsize=(max(6, 0.5 * len(targets)), 4))
    pass_pct = []
    labels = []
    colors = []
    for t in targets:
        r = by_task[t]
        n = int(r.get("n_candidates") or 0)
        p = int(r.get("n_pass") or 0)
        pct = 100.0 * p / n if n else 0
        pass_pct.append(pct)
        labels.append(f"{t}\nn={n}")
        colors.append(WORKFLOW_COLORS.get(r["workflow"], "#888"))
    bars = ax.bar(range(len(targets)), pass_pct, color=colors)
    ax.set_xticks(range(len(targets)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("PASS rate (%)")
    ax.set_title("Figure 2 — PASS rate per benchmark target")
    ax.set_ylim(0, 105)
    for i, (bar, r) in enumerate(zip(bars, [by_task[t] for t in targets])):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{int(r.get('n_pass') or 0)}", ha="center", fontsize=8)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in [WORKFLOW_COLORS[w] for w in workflows]]
    ax.legend(handles, workflows, loc="upper right", fontsize=8)
    _save(fig, out_dir / "fig2_benchmark_design")


def fig3_success(summary_dir: Path, out_dir: Path) -> None:
    """PASS heatmap + top-composite scatter."""
    rows = _read_csv(summary_dir / "task_summary.csv")
    if not rows:
        _placeholder_fig(out_dir / "fig3_workflow_success", "Figure 3 — no task_summary.csv")
        return
    real = [r for r in rows if r.get("mode") != "mock"]
    if not real:
        _placeholder_fig(out_dir / "fig3_workflow_success",
                         "Figure 3 — no real-mode runs yet (mock data only)")
        return
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    # Left: PASS rate per workflow (boxplot of per-task PASS%).
    by_wf = defaultdict(list)
    for r in real:
        n = int(r.get("n_candidates") or 0)
        p = int(r.get("n_pass") or 0)
        if n:
            by_wf[r["workflow"]].append(100.0 * p / n)
    workflows = sorted(by_wf)
    axes[0].boxplot([by_wf[w] for w in workflows], tick_labels=workflows)
    axes[0].set_ylabel("PASS rate per task (%)")
    axes[0].set_title("Workflow-level PASS distribution")
    axes[0].grid(True, alpha=0.3)

    # Right: top composite per task.
    by_task = {}
    for r in real:
        try:
            tc = float(r.get("top_composite") or 0)
        except ValueError:
            continue
        by_task[r["task_id"]] = (r["workflow"], tc)
    tasks = sorted(by_task)
    colors = [WORKFLOW_COLORS.get(by_task[t][0], "#888") for t in tasks]
    scores = [by_task[t][1] for t in tasks]
    axes[1].bar(range(len(tasks)), scores, color=colors)
    axes[1].set_xticks(range(len(tasks)))
    axes[1].set_xticklabels(tasks, rotation=45, ha="right", fontsize=8)
    axes[1].set_ylabel("top composite score")
    axes[1].set_title("Top candidate per task")
    axes[1].set_ylim(0, 1.0)
    axes[1].grid(True, alpha=0.3, axis="y")

    fig.suptitle("Figure 3 — Workflow success & candidate quality")
    fig.tight_layout()
    _save(fig, out_dir / "fig3_workflow_success")


def fig4_diversity(summary_dir: Path, out_dir: Path) -> None:
    """Candidate-level distributions: composite score per workflow."""
    rows = _read_csv(summary_dir / "candidate_summary.csv")
    if not rows:
        print("  fig4: skipping (no candidate_summary)")
        return
    real = [r for r in rows if r.get("workflow")]
    by_wf = defaultdict(list)
    for r in real:
        try:
            by_wf[r["workflow"]].append(float(r.get("composite_score") or 0))
        except ValueError:
            continue
    workflows = sorted(by_wf)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.violinplot([by_wf[w] for w in workflows], showmeans=True, showmedians=True)
    ax.set_xticks(range(1, len(workflows) + 1))
    ax.set_xticklabels(workflows)
    ax.set_ylabel("composite score")
    ax.set_title(f"Figure 4 — Candidate composite-score distribution by workflow "
                 f"(N={sum(len(v) for v in by_wf.values())})")
    ax.grid(True, alpha=0.3, axis="y")
    _save(fig, out_dir / "fig4_diversity_pareto")


def fig5_agent(summary_dir: Path, out_dir: Path) -> None:
    """Agent process metrics: wall time, errors, intervention rate."""
    rows = _read_csv(summary_dir / "agent_summary.csv")
    if not rows:
        _placeholder_fig(out_dir / "fig5_agent_performance", "Figure 5 — no agent_summary.csv")
        return
    real = [r for r in rows if r.get("mode") != "mock"]
    if not real:
        _placeholder_fig(out_dir / "fig5_agent_performance",
                         "Figure 5 — no real-mode runs yet (mock data only)")
        return

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    # Panel A: wall time per workflow.
    by_wf_wall = defaultdict(list)
    for r in real:
        try:
            t = float(r.get("wall_time_sec") or 0)
            if t > 0:
                by_wf_wall[r["workflow"]].append(t)
        except ValueError:
            continue
    if any(by_wf_wall.values()):
        wfs = sorted(by_wf_wall)
        axes[0].boxplot([by_wf_wall[w] for w in wfs], tick_labels=wfs)
        axes[0].set_ylabel("wall time (s)")
        axes[0].set_title("End-to-end wall time")
        axes[0].grid(True, alpha=0.3)
        axes[0].set_yscale("log")
    else:
        axes[0].text(0.5, 0.5, "no wall-time data", ha="center", transform=axes[0].transAxes)

    # Panel B: errors + interventions by run.
    n_errors = [int(r.get("n_errors") or 0) for r in real]
    n_inter = [int(r.get("n_interventions") or 0) for r in real]
    runs = list(range(len(real)))
    axes[1].bar(runs, n_errors, label="errors", color="#d62728")
    axes[1].bar(runs, n_inter, bottom=n_errors, label="interventions", color="#ff9800")
    axes[1].set_xlabel("run index")
    axes[1].set_ylabel("event count")
    axes[1].set_title("Errors + user interventions per run")
    axes[1].legend(fontsize=8)

    # Panel C: LLM-grid token + success comparison.
    grid = _read_csv(summary_dir / "llm_comparison.csv")
    if grid:
        by_llm_tokens = defaultdict(list)
        by_llm_pass = defaultdict(list)
        for r in grid:
            if r.get("mode") == "mock":
                continue
            try:
                by_llm_tokens[r["llm_backend"]].append(float(r.get("token_total") or 0))
                by_llm_pass[r["llm_backend"]].append(int(r.get("n_pass") or 0))
            except ValueError:
                continue
        llms = sorted(by_llm_tokens)
        x = np.arange(len(llms))
        if llms:
            axes[2].bar(x - 0.2, [np.mean(by_llm_pass[l]) for l in llms],
                        width=0.4, label="mean PASS", color="#2ca02c")
            ax2 = axes[2].twinx()
            ax2.bar(x + 0.2, [np.mean(by_llm_tokens[l]) for l in llms],
                    width=0.4, label="mean tokens", color="#1f77b4")
            ax2.set_ylabel("mean tokens")
            axes[2].set_xticks(x)
            axes[2].set_xticklabels(llms)
            axes[2].set_ylabel("mean PASS / 9 tasks")
            axes[2].set_title("LLM grid (3 LLMs × 9 tasks)")
        else:
            axes[2].text(0.5, 0.5, "LLM grid empty (mock only)", ha="center",
                         transform=axes[2].transAxes)
    else:
        axes[2].text(0.5, 0.5, "no llm_comparison.csv", ha="center", transform=axes[2].transAxes)

    fig.suptitle("Figure 5 — Agent execution performance")
    fig.tight_layout()
    _save(fig, out_dir / "fig5_agent_performance")


_FIG_FUNCS = {2: fig2_design, 3: fig3_success, 4: fig4_diversity, 5: fig5_agent}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fig", nargs="+", type=int, default=[2, 3, 4, 5])
    p.add_argument("--summary-dir", default=None, type=Path)
    p.add_argument("--out-dir", default=None, type=Path)
    args = p.parse_args(argv)

    root = find_project_root()
    summary_dir = args.summary_dir or root / "benchmark" / "summary"
    out_dir = args.out_dir or root / "benchmark" / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    for f in args.fig:
        if f not in _FIG_FUNCS:
            print(f"  skip unknown fig {f}", file=sys.stderr)
            continue
        print(f"figure {f}:")
        _FIG_FUNCS[f](summary_dir, out_dir)
    print(f"\ndone -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
