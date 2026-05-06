"""Reward-model evaluation metrics.

Reports Spearman, Pearson, RMSE, MAE, R^2, top-k enrichment. Spearman is the
metric used to enforce the workflows.yaml `helmgpt.pass_gates.reward_model`
gate (>=0.4 to allow RL).

Standalone CLI:
    python -m benchmark.reward_models.eval_metrics \\
        --predictions benchmark/reward_models/trained/pd1_pdl1_predictions.csv

The CSV must have columns `y_true,y_pred`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

import numpy as np


def _spearman(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Simple Spearman without scipy (for envs that don't have it)."""
    def ranks(x: np.ndarray) -> np.ndarray:
        order = np.argsort(x)
        r = np.empty_like(order, dtype=float)
        r[order] = np.arange(1, len(x) + 1)
        # Average ties
        for v in np.unique(x):
            mask = x == v
            if mask.sum() > 1:
                r[mask] = r[mask].mean()
        return r
    rt = ranks(np.asarray(y_true, dtype=float))
    rp = ranks(np.asarray(y_pred, dtype=float))
    if rt.std() == 0 or rp.std() == 0:
        return 0.0
    return float(np.corrcoef(rt, rp)[0, 1])


def _pearson(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    a = np.asarray(y_true, dtype=float)
    b = np.asarray(y_pred, dtype=float)
    if a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def top_k_enrichment(y_true: np.ndarray, y_pred: np.ndarray, k_frac: float = 0.1) -> float:
    """Fraction of top-k predicted that are in the top-k of true (k = k_frac * n)."""
    n = len(y_true)
    k = max(1, int(round(k_frac * n)))
    top_pred = set(np.argsort(-np.asarray(y_pred))[:k])
    top_true = set(np.argsort(-np.asarray(y_true))[:k])
    return len(top_pred & top_true) / float(k)


def compute_metrics(y_true: Iterable[float], y_pred: Iterable[float]) -> dict[str, float]:
    yt = np.asarray(list(y_true), dtype=float)
    yp = np.asarray(list(y_pred), dtype=float)
    if len(yt) == 0:
        return {}
    rmse = float(np.sqrt(np.mean((yt - yp) ** 2)))
    mae = float(np.mean(np.abs(yt - yp)))
    ss_res = float(np.sum((yt - yp) ** 2))
    ss_tot = float(np.sum((yt - yt.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {
        "n": int(len(yt)),
        "spearman": _spearman(yt, yp),
        "pearson": _pearson(yt, yp),
        "rmse": rmse,
        "mae": mae,
        "r2": r2,
        "top_10pct_enrichment": top_k_enrichment(yt, yp, k_frac=0.1),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--predictions", required=True, type=Path,
                   help="CSV with columns y_true,y_pred")
    p.add_argument("--output_json", default=None, type=Path)
    args = p.parse_args(argv)

    import csv
    with args.predictions.open() as f:
        rows = list(csv.DictReader(f))
    if not rows or "y_true" not in rows[0] or "y_pred" not in rows[0]:
        print("error: input CSV must have y_true and y_pred columns", file=sys.stderr)
        return 1
    yt = [float(r["y_true"]) for r in rows]
    yp = [float(r["y_pred"]) for r in rows]
    m = compute_metrics(yt, yp)
    print(json.dumps(m, indent=2, default=float))
    if args.output_json:
        args.output_json.write_text(json.dumps(m, indent=2, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
