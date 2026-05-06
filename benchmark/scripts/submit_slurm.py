"""Generate sbatch scripts for the CycPepMCP benchmark on KAUST iBex / Shaheen.

For each task in `targets.csv` (or a subset), writes a self-contained sbatch
script under `benchmark/slurm/<run_id>.sbatch` that:
  1. Sources the per-MCP conda env (no cluster modules required).
  2. Runs `benchmark.scripts.run_benchmark` for that task in real mode.
  3. Pipes all output into `benchmark/runs/<run_id>/sbatch.log`.
  4. Honors per-cluster Slurm conventions (partition, gres, account).

Use:
    # Generate sbatch scripts for all 10 structural tasks (single seed, claude)
    python -m benchmark.scripts.submit_slurm \\
        --cluster ibex --account <kaust-acct> --seed 1 --llm claude \\
        --workflow afcycdesign rfpeptides

    # Then submit:
    cd benchmark/slurm/
    for s in *.sbatch; do sbatch "$s"; done

    # Single task variant (smoke test on iBex)
    python -m benchmark.scripts.submit_slurm --cluster ibex --task AF_MDM2 --seed 1

Pre-flight (run on the login node):
    python -m benchmark.scripts.stage_pdbs           # internet required
    python -m benchmark.configs.thresholds           # config self-check
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from textwrap import dedent

_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / "benchmark" / "configs" / "thresholds.py").is_file():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break

from benchmark.configs import thresholds as cfg
from benchmark.scripts.workflow_runners.base import find_project_root, load_targets, make_run_id


# --------------------------------------------------------------------------
# Cluster profiles. Tune `partition`, `gres`, `time`, `mem` per workflow.
# Values reflect KAUST defaults as of 2026-05; adjust if the user's allocation
# differs. The runner's actual GPU pinning uses the BENCHMARK_GPU_ID env var.
# --------------------------------------------------------------------------

CLUSTER_PROFILES = {
    "ibex": {
        # iBex: typical GPU partition `batch`, single-node A100 (40 GB) or V100.
        "partition_default": "batch",
        "constraint": "a100",
        "scratch_root": "/ibex/scratch/${USER}",
        "module_lines": [],
        "extras": ["#SBATCH --constraint=a100"],
    },
    "shaheen": {
        # Shaheen III: GPU partition typically `gpu`; H100 / MI250X depending on
        # build. The user should verify their allocation's correct partition name.
        "partition_default": "gpu",
        "constraint": "",
        "scratch_root": "/scratch/${USER}",
        "module_lines": [],
        "extras": [],
    },
    "local": {
        # Local sbatch test (Slurm running on the workstation, if installed).
        "partition_default": "debug",
        "constraint": "",
        "scratch_root": "${HOME}/scratch",
        "module_lines": [],
        "extras": [],
    },
}


# Per-workflow resource hints. The user should tune these against their
# allocation; defaults err on the generous side.
WORKFLOW_RESOURCES = {
    "afcycdesign": {"time": "08:00:00", "mem": "64G", "gpus": 1},
    "rfpeptides":  {"time": "48:00:00", "mem": "128G", "gpus": 2},  # multi-stage; can checkpoint
    "helmgpt":     {"time": "24:00:00", "mem": "96G", "gpus": 1},
}


SBATCH_TEMPLATE = dedent("""\
    #!/bin/bash
    #SBATCH --job-name={run_id}
    #SBATCH --output={log_path}
    #SBATCH --error={log_path}
    #SBATCH --partition={partition}
    #SBATCH --time={time}
    #SBATCH --nodes=1
    #SBATCH --ntasks=1
    #SBATCH --cpus-per-task=8
    #SBATCH --gpus={gpus}
    #SBATCH --mem={mem}
    {extras}
    {account_line}

    set -euo pipefail
    cd {repo_root}

    {module_lines}

    # Single-source-of-truth env: prefer the project's own python (created by
    # the top-level `mamba env create -f environment.yml`).
    PROJECT_PY={repo_root}/env/bin/python
    if [ ! -x "$PROJECT_PY" ]; then
        echo "ERROR: project env not found at $PROJECT_PY" >&2
        echo "Run 'mamba env create -f environment.yml' on the login node first" >&2
        exit 2
    fi

    # Verify required tool-mcp envs exist for this workflow.
    {tool_check_lines}

    # GPU pinning: Slurm's CUDA_VISIBLE_DEVICES is already correct; the runner
    # always asks for GPU 0 internally.
    export BENCHMARK_GPU_ID=0
    echo "[$(date)] start {run_id} on $(hostname) GPU=$CUDA_VISIBLE_DEVICES"
    "$PROJECT_PY" -m benchmark.scripts.run_benchmark \\
        --task {task_id} --llm {llm} --seed {seed} --mode real {extra_args}
    echo "[$(date)] finished {run_id}"
""")


def _tool_check(workflow: str, repo_root: Path) -> str:
    """Bash lines that abort with a clear error if a required MCP env is missing."""
    deps = {
        "afcycdesign": ["afcycdesign_mcp"],
        "rfpeptides":  ["rfpeptides_mcp", "proteinmpnn_mcp", "rosetta_kic_mcp", "afcycdesign_mcp"],
        "helmgpt":     ["helm_gpt_mcp", "boltz_mcp", "alphafold3_mcp", "gnina_mcp"],
    }[workflow]
    lines = []
    for d in deps:
        lines.append(f'[ -d "{repo_root}/tool-mcps/{d}/env" ] || '
                     f'{{ echo "ERROR: tool-mcps/{d}/env missing on this node" >&2; exit 2; }}')
    return "\n    ".join(lines)


def render_sbatch(*, task_id: str, run_id: str, workflow: str,
                  cluster: str, llm: str, seed: int, account: str | None,
                  partition: str | None, time_override: str | None,
                  num_designs: int | None, extra_args: str = "") -> str:
    profile = CLUSTER_PROFILES.get(cluster)
    if profile is None:
        raise KeyError(f"unknown cluster {cluster!r}; expected {list(CLUSTER_PROFILES)}")
    res = WORKFLOW_RESOURCES[workflow]

    repo_root = find_project_root()
    log_path = repo_root / "benchmark" / "runs" / run_id / "sbatch.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    extras = list(profile.get("extras", []))
    if num_designs is not None:
        ea_extra = f"{extra_args} --num-designs {num_designs}".strip()
    else:
        ea_extra = extra_args

    account_line = f"#SBATCH --account={account}" if account else "# (no --account; using default)"

    return SBATCH_TEMPLATE.format(
        run_id=run_id,
        task_id=task_id,
        log_path=log_path,
        partition=partition or profile["partition_default"],
        time=time_override or res["time"],
        gpus=res["gpus"],
        mem=res["mem"],
        extras="\n".join(extras),
        account_line=account_line,
        repo_root=repo_root,
        module_lines="\n    ".join(profile["module_lines"]) or "# (no module loads)",
        tool_check_lines=_tool_check(workflow, repo_root),
        llm=llm,
        seed=seed,
        extra_args=ea_extra,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cluster", required=True, choices=sorted(CLUSTER_PROFILES))
    p.add_argument("--task", action="append", default=None,
                   help="Specific task_id (repeat for several); omit to use --workflow / --llm-grid / all")
    p.add_argument("--workflow", action="append", default=None,
                   choices=["afcycdesign", "rfpeptides", "helmgpt"],
                   help="Generate scripts for every task in these workflows")
    p.add_argument("--llm-grid", action="store_true",
                   help="Generate scripts for the 9-task LLM-comparison grid only")
    p.add_argument("--llm", default="claude", choices=["claude", "gpt", "gemini", "mock"])
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--account", default=None, help="Slurm --account (e.g. KAUST project ID)")
    p.add_argument("--partition", default=None, help="Override cluster partition default")
    p.add_argument("--time", default=None, help="Override Slurm --time (e.g. 12:00:00)")
    p.add_argument("--num-designs", type=int, default=None)
    p.add_argument("--out-dir", default=None, type=Path,
                   help="Where to write the .sbatch files (default: benchmark/slurm/)")
    args = p.parse_args(argv)

    targets = load_targets()
    selected: list[str]
    if args.task:
        selected = list(args.task)
    elif args.workflow:
        selected = [t for t, r in targets.items() if r.workflow in args.workflow]
    elif args.llm_grid:
        selected = [t for ts in cfg.llm_grid().values() for t in ts]
    else:
        selected = sorted(targets)

    out_dir = args.out_dir or find_project_root() / "benchmark" / "slurm"
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for task_id in selected:
        if task_id not in targets:
            print(f"  SKIP unknown task: {task_id}", file=sys.stderr)
            continue
        target = targets[task_id]
        run_id = make_run_id(task_id, args.seed, args.llm)
        sbatch_text = render_sbatch(
            task_id=task_id, run_id=run_id, workflow=target.workflow,
            cluster=args.cluster, llm=args.llm, seed=args.seed,
            account=args.account, partition=args.partition, time_override=args.time,
            num_designs=args.num_designs,
        )
        out_path = out_dir / f"{run_id}.sbatch"
        out_path.write_text(sbatch_text)
        out_path.chmod(0o755)
        try:
            display = out_path.relative_to(find_project_root())
        except ValueError:
            display = out_path
        print(f"  wrote {display}  workflow={target.workflow}")
        written += 1
    print(f"\ndone: {written} sbatch script(s) under {out_dir}")
    print(f"submit with: cd {out_dir} && for s in *.sbatch; do sbatch \"$s\"; done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
