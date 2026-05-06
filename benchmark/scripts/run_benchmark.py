"""Top-level CycPepMCP benchmark dispatcher.

Routes a task_id from `benchmark/configs/targets.csv` to the correct workflow
runner, opens the agent_trace, and writes outputs into
`benchmark/runs/{run_id}/`.

Examples
--------
    # Smoke test (mock mode, no GPU): all 13 tasks
    python -m benchmark.scripts.run_benchmark --all --mode mock

    # One real Claude run on MDM2 (AfCycDesign), seed 1
    python -m benchmark.scripts.run_benchmark --task AF_MDM2 --llm claude --seed 1

    # Resume a partial run after a crash
    python -m benchmark.scripts.run_benchmark --task RF_MCL1 --llm claude --resume
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# Bootstrap import path so this module is runnable as a script too.
_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / "benchmark" / "configs" / "thresholds.py").is_file():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break

from benchmark.configs import thresholds as cfg  # noqa: E402
from benchmark.scripts.workflow_runners.base import (  # noqa: E402
    RunContext, find_project_root, load_targets, make_run_id,
)
from benchmark.scripts.workflow_runners.afcycdesign_runner import AfCycDesignRunner  # noqa: E402
from benchmark.scripts.workflow_runners.rfpeptides_runner import RFpeptidesRunner  # noqa: E402
from benchmark.scripts.workflow_runners.helmgpt_runner import HelmGPTRunner  # noqa: E402


_RUNNER_CLASSES = {
    "afcycdesign": AfCycDesignRunner,
    "rfpeptides": RFpeptidesRunner,
    "helmgpt": HelmGPTRunner,
}


def run_one(task_id: str, *, llm_backend: str, seed: int, mode: str, resume: bool,
            out_root: Path, num_designs_override: int | None = None) -> dict[str, Any]:
    """Run one (task_id, seed, llm_backend) tuple and return the summary."""
    targets = load_targets()
    if task_id not in targets:
        raise KeyError(f"unknown task_id {task_id!r}; expected one of {sorted(targets)}")
    target = targets[task_id]
    if num_designs_override is not None:
        target.num_designs = num_designs_override   # for pilots/smoke
    runner_cls = _RUNNER_CLASSES.get(target.workflow)
    if runner_cls is None:
        raise KeyError(f"unknown workflow {target.workflow!r} for task {task_id}")
    run_id = make_run_id(task_id, seed, llm_backend)
    ctx = RunContext(
        target=target,
        run_id=run_id,
        seed=seed,
        llm_backend=llm_backend,
        out_dir=out_root / run_id,
        mode=mode,
        resume=resume,
        project_root=find_project_root(),
    )
    runner = runner_cls(ctx)
    return runner.run()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sel = p.add_mutually_exclusive_group(required=True)
    sel.add_argument("--task", help="Single task_id from targets.csv (e.g. AF_MDM2)")
    sel.add_argument("--all", action="store_true", help="Run every task in targets.csv")
    sel.add_argument("--llm-grid", action="store_true",
                     help="Run only the 9-task LLM grid (3 per workflow)")
    p.add_argument("--llm", default="claude", choices=["claude", "gpt", "gemini", "mock"],
                   help="LLM backend label written into traces (default: claude)")
    p.add_argument("--seed", type=int, default=1, help="Repeat seed (default: 1)")
    p.add_argument("--mode", default="mock", choices=["mock", "real"],
                   help="mock: synthesize candidates (no GPU); real: call MCP/CLI tools (default: mock)")
    p.add_argument("--resume", action="store_true", help="Resume from checkpoint.json if present")
    p.add_argument("--out-root", default=None, help="Output root (default: benchmark/runs)")
    p.add_argument("--num-designs", type=int, default=None,
                   help="Override num_designs from targets.csv (useful for smoke tests)")
    args = p.parse_args(argv)

    out_root = Path(args.out_root) if args.out_root else find_project_root() / "benchmark" / "runs"
    out_root.mkdir(parents=True, exist_ok=True)

    # Resolve which tasks to run.
    if args.task:
        tasks = [args.task]
    elif args.all:
        tasks = sorted(load_targets())
    else:  # --llm-grid
        tasks = [t for ts in cfg.llm_grid().values() for t in ts]

    print(f"[run_benchmark] mode={args.mode} llm={args.llm} seed={args.seed} "
          f"out_root={out_root}")
    print(f"[run_benchmark] running {len(tasks)} task(s): {tasks}")

    summaries = []
    t_start = time.perf_counter()
    for task_id in tasks:
        print(f"\n=== {task_id} ===")
        try:
            summary = run_one(task_id, llm_backend=args.llm, seed=args.seed,
                              mode=args.mode, resume=args.resume, out_root=out_root,
                              num_designs_override=args.num_designs)
            summaries.append(summary)
            print(f"  -> n_candidates={summary['n_candidates']} "
                  f"pass={summary['n_pass']} fail={summary['n_fail']} "
                  f"top_composite={summary.get('top_composite')} "
                  f"wall={summary['wall_time_sec']}s")
        except Exception as e:
            print(f"  !! {type(e).__name__}: {e}")
            summaries.append({"task_id": task_id, "error": f"{type(e).__name__}: {e}"})

    total = round(time.perf_counter() - t_start, 2)
    print(f"\n[run_benchmark] done in {total}s; {len(summaries)} run(s) attempted")
    # Stream a one-line summary index.
    index_path = out_root / "_dispatch_index.jsonl"
    with index_path.open("a") as f:
        for s in summaries:
            f.write(json.dumps(s, default=str) + "\n")
    print(f"[run_benchmark] index appended to {index_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
