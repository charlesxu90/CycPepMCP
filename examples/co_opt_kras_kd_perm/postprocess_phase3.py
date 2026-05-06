#!/usr/bin/env python3
"""Phase 3: composite-score ranking for case3 KRAS-G12D candidates.

Inputs (all under <run_dir>):
  phase2_candidates.csv        (Phase-1 metrics: kd_um, raw_permeability, ...)
  phase2_track_a/track_a_results.csv  (Boltz-2 affinity + confidence)
  phase2_gnina/gnina_results.csv      (Gnina CNN + Vina)

Output:
  phase3_final_ranking.csv     (per-candidate composite + sub-ranks)
  phase3_summary.json          (top-5 with full metric breakdown)

Composite scoring (Track A, ≤128 atoms — all candidates fall here):
  KRAS KD (0.20) + permeability (0.15)
  + Boltz-2 affinity (0.15) + Boltz-2 affinity_prob (0.10)
  + Boltz-2 iPTM (0.10)   [substitutes AF3 iPTM since AF3 unavailable]
  + Gnina CNN (0.15)      + Gnina Vina (0.15)

Each metric is min-max normalized across the candidate set so the seven
sub-scores combine on a common 0-1 scale; lower-is-better metrics (KD,
Vina) are inverted.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Centralized composite-score weights (single source of truth: benchmark/configs/workflows.yaml).
_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / "benchmark" / "configs" / "thresholds.py").is_file():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break
from benchmark.configs import thresholds as cfg  # noqa: E402

WEIGHTS = dict(cfg.HELMGPT_COMPOSITE_WEIGHTS)


def normalize(s: pd.Series, higher_is_better: bool = True) -> pd.Series:
    s = s.astype(float)
    lo, hi = s.min(), s.max()
    if hi == lo:
        return pd.Series([0.5] * len(s), index=s.index)
    n = (s - lo) / (hi - lo)
    return n if higher_is_better else 1.0 - n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    args = ap.parse_args()
    run = Path(args.run_dir)

    cands = pd.read_csv(run / "phase2_candidates.csv")
    track_a = pd.read_csv(run / "phase2_track_a" / "track_a_results.csv")
    gnina = pd.read_csv(run / "phase2_gnina" / "gnina_results.csv")

    df = cands.merge(track_a, on="rank", how="left", suffixes=("", "_a"))
    df = df.merge(gnina, on="rank", how="left", suffixes=("", "_g"))

    n_kd   = normalize(df["kd_um"], higher_is_better=False)
    n_perm = normalize(df["raw_permeability"], higher_is_better=True)
    n_aff  = normalize(df["aff_affinity_pred_value"].fillna(df["aff_affinity_pred_value"].min()), higher_is_better=True)
    n_prob = normalize(df["aff_affinity_probability_binary"].fillna(df["aff_affinity_probability_binary"].min()), higher_is_better=True)
    n_iptm = normalize(df["conf_iptm"].fillna(df["conf_iptm"].min()), higher_is_better=True)
    n_cnn  = normalize(df["cnn_affinity"].fillna(df["cnn_affinity"].min()), higher_is_better=True)
    n_vina = normalize(df["vina_affinity"].fillna(df["vina_affinity"].max()), higher_is_better=False)

    df["n_kd"]   = n_kd
    df["n_perm"] = n_perm
    df["n_aff"]  = n_aff
    df["n_prob"] = n_prob
    df["n_iptm"] = n_iptm
    df["n_cnn"]  = n_cnn
    df["n_vina"] = n_vina

    df["composite"] = (
        WEIGHTS["kd"]   * n_kd   +
        WEIGHTS["perm"] * n_perm +
        WEIGHTS["aff"]  * n_aff  +
        WEIGHTS["prob"] * n_prob +
        WEIGHTS["iptm"] * n_iptm +
        WEIGHTS["cnn"]  * n_cnn  +
        WEIGHTS["vina"] * n_vina
    )
    df = df.sort_values("composite", ascending=False).reset_index(drop=True)
    df["final_rank"] = df.index + 1

    keep = [
        "final_rank", "rank", "helm_seqs", "smiles", "n_heavy_atoms",
        "kd_um", "raw_permeability",
        "aff_affinity_pred_value", "aff_affinity_probability_binary",
        "conf_iptm", "conf_complex_plddt",
        "cnn_affinity", "vina_affinity",
        "n_kd", "n_perm", "n_aff", "n_prob", "n_iptm", "n_cnn", "n_vina",
        "composite",
    ]
    keep = [k for k in keep if k in df.columns]
    out = run / "phase3_final_ranking.csv"
    df[keep].to_csv(out, index=False)

    top = df.head(5)
    summary = {
        "run_dir": str(run),
        "n_candidates": int(len(df)),
        "weights": WEIGHTS,
        "best_composite": float(df["composite"].iloc[0]),
        "top_5": [
            {
                "final_rank": int(r["final_rank"]),
                "phase1_rank": int(r["rank"]),
                "helm": r["helm_seqs"],
                "kd_um": float(r["kd_um"]),
                "perm": float(r["raw_permeability"]),
                "boltz_affinity": None if pd.isna(r.get("aff_affinity_pred_value")) else float(r["aff_affinity_pred_value"]),
                "boltz_prob": None if pd.isna(r.get("aff_affinity_probability_binary")) else float(r["aff_affinity_probability_binary"]),
                "boltz_iptm": None if pd.isna(r.get("conf_iptm")) else float(r["conf_iptm"]),
                "gnina_cnn": None if pd.isna(r.get("cnn_affinity")) else float(r["cnn_affinity"]),
                "gnina_vina": None if pd.isna(r.get("vina_affinity")) else float(r["vina_affinity"]),
                "composite": float(r["composite"]),
            }
            for _, r in top.iterrows()
        ],
    }
    sum_path = run / "phase3_summary.json"
    sum_path.write_text(json.dumps(summary, indent=2))

    print(f"wrote: {out}")
    print(f"wrote: {sum_path}")
    print()
    print(f"{'rk':>3} {'kd':>6} {'perm':>6} {'aff':>7} {'prob':>5} {'iPTM':>5} {'CNN':>5} {'Vina':>6} {'comp':>5}")
    for _, r in df.head(10).iterrows():
        kd  = r["kd_um"]
        prm = r["raw_permeability"]
        af  = r.get("aff_affinity_pred_value", np.nan)
        prb = r.get("aff_affinity_probability_binary", np.nan)
        ip  = r.get("conf_iptm", np.nan)
        cn  = r.get("cnn_affinity", np.nan)
        vn  = r.get("vina_affinity", np.nan)
        cm  = r["composite"]
        print(f"{int(r['final_rank']):>3} {kd:>6.2f} {prm:>6.2f} {af:>7.3f} {prb:>5.2f} {ip:>5.2f} {cn:>5.2f} {vn:>6.2f} {cm:>5.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
