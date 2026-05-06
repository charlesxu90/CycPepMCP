#!/usr/bin/env python3
"""Aggregate, deduplicate, and filter HELM-GPT Phase 1 outputs against the
case3 quality thresholds (permeability > -6.0 log cm/s, KD < 10 μM).

Reads every `step_*_aa_seqs.csv` under the supplied run directory, drops
parser-failed rows (sentinel values raw_permeability=-10 / raw_kras_kd=5),
deduplicates by HELM string, applies the workflow PASS gate, and writes:

  phase1_aggregated.csv   — every unique scored HELM
  phase1_filtered.csv     — PASS subset, sorted by composite reward
  phase1_summary.json     — counts at each filter step
"""
import argparse
import json
import sys
from glob import glob
from pathlib import Path

import pandas as pd

# Centralized PASS-gate constants (single source of truth: benchmark/configs/workflows.yaml).
# Walk up to the repo root so `from benchmark.configs import thresholds` works regardless of cwd.
_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / "benchmark" / "configs" / "thresholds.py").is_file():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break
from benchmark.configs import thresholds as cfg  # noqa: E402

PERM_FAIL_SENTINEL = cfg.PERM_FAIL_SENTINEL
KD_FAIL_SENTINEL = cfg.KD_FAIL_SENTINEL
PERM_PASS_THRESHOLD = cfg.PERM_PASS_THRESHOLD       # raw log cm/s; higher is better
KD_PASS_LOG_THRESHOLD = cfg.KD_PASS_LOG_THRESHOLD   # raw_kras_kd is log10(KD μM); KD<10 μM => log<1.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", help="Phase 1 RL output directory containing step_*_aa_seqs.csv")
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"error: not a directory: {run_dir}", file=sys.stderr)
        return 1

    step_files = sorted(glob(str(run_dir / "step_*_aa_seqs.csv")))
    if not step_files:
        print(f"error: no step_*_aa_seqs.csv under {run_dir}", file=sys.stderr)
        return 1

    frames = []
    for fp in step_files:
        try:
            frames.append(pd.read_csv(fp))
        except Exception as e:
            print(f"  warn: skip {fp}: {e}", file=sys.stderr)
    df = pd.concat(frames, ignore_index=True)
    n_total = len(df)

    n_parser_failed = (
        (df["raw_permeability"] == PERM_FAIL_SENTINEL)
        | (df["raw_kras_kd"] == KD_FAIL_SENTINEL)
    ).sum()
    df_valid = df[
        (df["raw_permeability"] != PERM_FAIL_SENTINEL)
        & (df["raw_kras_kd"] != KD_FAIL_SENTINEL)
    ].copy()

    df_unique = (
        df_valid.sort_values("sum", ascending=False)
        .drop_duplicates(subset=["helm_seqs"], keep="first")
        .reset_index(drop=True)
    )
    n_unique = len(df_unique)

    df_pass = df_unique[
        (df_unique["raw_permeability"] > PERM_PASS_THRESHOLD)
        & (df_unique["raw_kras_kd"] < KD_PASS_LOG_THRESHOLD)
    ].copy()
    df_pass["kd_um"] = 10 ** df_pass["raw_kras_kd"]
    df_pass = df_pass.sort_values("sum", ascending=False).reset_index(drop=True)
    n_pass = len(df_pass)

    agg_path = run_dir / "phase1_aggregated.csv"
    flt_path = run_dir / "phase1_filtered.csv"
    sum_path = run_dir / "phase1_summary.json"

    df_unique.to_csv(agg_path, index=False)
    df_pass.to_csv(flt_path, index=False)

    summary = {
        "run_dir": str(run_dir),
        "step_files": len(step_files),
        "rows_total": int(n_total),
        "rows_parser_failed": int(n_parser_failed),
        "rows_unique_valid": int(n_unique),
        "rows_pass_phase1_thresholds": int(n_pass),
        "thresholds": {
            "permeability_log_cm_s_min": PERM_PASS_THRESHOLD,
            "kras_kd_um_max": 10 ** KD_PASS_LOG_THRESHOLD,
        },
        "best_pass_examples": [
            {
                "helm": row["helm_seqs"],
                "permeability": float(row["raw_permeability"]),
                "kd_um": float(row["kd_um"]),
                "composite": float(row["sum"]),
            }
            for _, row in df_pass.head(10).iterrows()
        ],
    }
    sum_path.write_text(json.dumps(summary, indent=2))

    print(f"step files               : {len(step_files)}")
    print(f"total rows               : {n_total}")
    print(f"parser-failed rows       : {n_parser_failed}")
    print(f"unique valid HELM        : {n_unique}")
    print(f"PASS (perm>-6, KD<10 μM) : {n_pass}")
    print(f"\nwrote: {agg_path}")
    print(f"wrote: {flt_path}")
    print(f"wrote: {sum_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
