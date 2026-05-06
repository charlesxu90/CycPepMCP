"""Pre-seed a benchmark run directory from existing case study outputs.

Used for the W2(a) pilot pass: instead of re-running multi-hour pipelines
from scratch, point the runner at existing `results/case{1,2,3}_*` outputs
so the runner just executes its read+filter+score+trace path on real data.

Each --task option drops the right CSV and writes a checkpoint.json that
marks the upstream stages completed; calling `run_benchmark.py --resume`
will then skip those stages and run only `_collect_and_score()`.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / "benchmark" / "configs" / "thresholds.py").is_file():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break

from benchmark.scripts.workflow_runners.base import find_project_root, make_run_id


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_af_mdm2(root: Path, run_id: str) -> dict:
    src = root / "results" / "case1_mdm2_binder_afcycdesign" / "afcycdesign_results.csv"
    dst_dir = root / "benchmark" / "runs" / run_id
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst_dir / "afcycdesign_results.csv")
    ckpt = {
        "target_qc": {"completed_at": _ts(), "source": "case1_mdm2"},
        "submit": {"completed_at": _ts(), "source": "case1_mdm2", "preseed": True},
    }
    (dst_dir / "checkpoint.json").write_text(json.dumps(ckpt, indent=2))
    return {"src": str(src), "n_rows": sum(1 for _ in open(src)) - 1}


def seed_rf_mcl1(root: Path, run_id: str) -> dict:
    src = root / "results" / "case2_mcl1_rfpeptides" / "prod_pipeline" / "final_summary.csv"
    dst_dir = root / "benchmark" / "runs" / run_id
    pipeline_dir = dst_dir / "pipeline"
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, pipeline_dir / "final_summary.csv")
    ckpt = {
        "stage1": {"completed_at": _ts(), "source": "case2_mcl1", "preseed": True},
        "stages_2_to_5": {"completed_at": _ts(), "source": "case2_mcl1", "preseed": True},
    }
    (dst_dir / "checkpoint.json").write_text(json.dumps(ckpt, indent=2))
    return {"src": str(src), "n_rows": sum(1 for _ in open(src)) - 1}


def seed_hg_kras(root: Path, run_id: str) -> dict:
    # Latest phase1 dir (timestamped); pick the most recent with a phase3 CSV.
    candidates = sorted((root / "results" / "case3_kras_helmgpt").glob("phase1_*/phase3_final_ranking.csv"))
    if not candidates:
        raise FileNotFoundError("no case3 phase3_final_ranking.csv found")
    src = candidates[-1]
    dst_dir = root / "benchmark" / "runs" / run_id
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst_dir / "phase3_final_ranking.csv")
    ckpt = {
        "reward_model_gate": {
            "completed_at": _ts(),
            "source": "case3_kras",
            "spearman": 0.82,        # HELM-GPT paper test Spearman (reused predictor)
            "preseed": True,
        },
        "phase3": {"completed_at": _ts(), "source": str(src), "preseed": True},
    }
    (dst_dir / "checkpoint.json").write_text(json.dumps(ckpt, indent=2))
    return {"src": str(src), "n_rows": sum(1 for _ in open(src)) - 1}


def seed_rf_rbta(root: Path, run_id: str) -> dict:
    src = root / "results" / "case2_RbtA_v3" / "prod_pipeline" / "final_summary.csv"
    dst_dir = root / "benchmark" / "runs" / run_id
    pipeline_dir = dst_dir / "pipeline"
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, pipeline_dir / "final_summary.csv")
    ckpt = {
        "stage1": {"completed_at": _ts(), "source": "case2_RbtA_v3", "preseed": True},
        "stages_2_to_5": {"completed_at": _ts(), "source": "case2_RbtA_v3", "preseed": True},
    }
    (dst_dir / "checkpoint.json").write_text(json.dumps(ckpt, indent=2))
    return {"src": str(src), "n_rows": sum(1 for _ in open(src)) - 1}


SEED_FUNCS = {
    "AF_MDM2": seed_af_mdm2,
    "RF_MCL1": seed_rf_mcl1,
    "RF_RBTA": seed_rf_rbta,
    "HG_KRASG12D": seed_hg_kras,
}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--task", required=True, choices=sorted(SEED_FUNCS))
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--llm", default="claude")
    args = p.parse_args(argv)

    root = find_project_root()
    run_id = make_run_id(args.task, args.seed, args.llm)
    info = SEED_FUNCS[args.task](root, run_id)
    print(f"seeded {args.task} -> benchmark/runs/{run_id}/  ({info['n_rows']} rows from {info['src']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
