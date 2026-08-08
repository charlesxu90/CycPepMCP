"""Train an XGBoost reward model for HELM-GPT target-specific RL.

Inputs a curated, scaffold-split CSV (output of `scaffold_split.py`) and
writes a pickled regressor + companion metrics JSON. The metrics JSON is what
`benchmark/scripts/workflow_runners/helmgpt_runner.py` reads to enforce the
Spearman >= 0.4 reward-model gate before allowing RL to start.

Features: 2048-bit Morgan fingerprint (radius 2) + a small set of RDKit
descriptors. This matches the HELM-GPT paper's KRAS predictor recipe.

Dependencies (data-curator env):
    pip install rdkit xgboost scikit-learn pandas numpy scipy

Example:
    python -m benchmark.reward_models.train_xgboost \\
        --input  benchmark/data_curation/datasets/pd1_pdl1_split.csv \\
        --target_id pd1_pdl1 \\
        --out_dir benchmark/reward_models/trained
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np


MORGAN_RADIUS = 2
MORGAN_NBITS = 2048


def featurize(smiles_list: list[str]) -> np.ndarray:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors

    rows = []
    for s in smiles_list:
        mol = Chem.MolFromSmiles(s)
        if mol is None:
            rows.append(np.zeros(MORGAN_NBITS + 6))
            continue
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, MORGAN_RADIUS, nBits=MORGAN_NBITS)
        arr = np.zeros((MORGAN_NBITS,), dtype=np.uint8)
        from rdkit.DataStructs import ConvertToNumpyArray
        ConvertToNumpyArray(fp, arr)
        descs = np.array([
            Descriptors.MolWt(mol),
            Descriptors.MolLogP(mol),
            Descriptors.TPSA(mol),
            Descriptors.NumHDonors(mol),
            Descriptors.NumHAcceptors(mol),
            Descriptors.NumRotatableBonds(mol),
        ], dtype=np.float32)
        rows.append(np.concatenate([arr.astype(np.float32), descs]))
    return np.vstack(rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--target_id", required=True,
                   help="Lower-case identifier used in the model filename (e.g. pd1_pdl1)")
    p.add_argument("--out_dir", required=True, type=Path)
    p.add_argument("--n_estimators", type=int, default=400)
    p.add_argument("--max_depth", type=int, default=6)
    p.add_argument("--learning_rate", type=float, default=0.05)
    p.add_argument("--multitask_column", default=None,
                   help="Column with categorical target-side label (e.g. 'target_side' for "
                        "MDM2/MDMX). When set, one-hot features are appended to Morgan FP.")
    p.add_argument("--aux_classifier_path", default=None,
                   help="Optional path to a pickled sklearn-style classifier with a "
                        "predict_proba(SMILES)->probability output. Its probability is "
                        "appended as one extra feature to every row.")
    args = p.parse_args(argv)

    try:
        import pandas as pd
        import xgboost as xgb
    except ImportError as e:
        raise RuntimeError(
            "pandas + xgboost required; `pip install pandas xgboost`"
        ) from e
    from benchmark.reward_models.eval_metrics import compute_metrics

    df = pd.read_csv(args.input)
    for col in ("smiles", "p_activity", "split"):
        if col not in df.columns:
            raise ValueError(f"input {args.input} missing required column {col!r}")
    df = df.dropna(subset=["smiles", "p_activity"])

    X_all = featurize(df["smiles"].tolist())
    y_all = df["p_activity"].astype(float).values
    splits = df["split"].values

    # Optional multitask one-hot (e.g. MDM2 vs MDMX target_side).
    if args.multitask_column and args.multitask_column in df.columns:
        labels = df[args.multitask_column].fillna("unknown").astype(str).values
        unique = sorted(set(labels))
        idx = {lab: i for i, lab in enumerate(unique)}
        onehot = np.zeros((len(labels), len(unique)), dtype=np.float32)
        for i, lab in enumerate(labels):
            onehot[i, idx[lab]] = 1.0
        X_all = np.concatenate([X_all, onehot], axis=1)
        print(f"  multitask one-hot: {unique}  (added {len(unique)} features)")

    # Optional auxiliary classifier (binder/non-binder prior) — append its
    # predicted probability as one extra feature.
    if args.aux_classifier_path:
        import pickle as _pickle
        with open(args.aux_classifier_path, "rb") as f:
            aux = _pickle.load(f)
        # Aux must expose either predict_proba(smiles_list) or predict_proba(featurized matrix)
        if hasattr(aux, "predict_proba_smiles"):
            probs = aux.predict_proba_smiles(df["smiles"].tolist())
        else:
            # Featurize the same way and call predict_proba directly
            probs = aux.predict_proba(X_all[:, :MORGAN_NBITS])[:, 1]
        X_all = np.concatenate([X_all, probs.reshape(-1, 1).astype(np.float32)], axis=1)
        print(f"  aux classifier scores appended ({args.aux_classifier_path})")

    train_mask = splits == "train"
    val_mask = splits == "val"
    test_mask = splits == "test"
    if train_mask.sum() < 30:
        raise RuntimeError(
            f"only {train_mask.sum()} train rows; need >=30 for a sane reward model"
        )

    # n_jobs capped to keep multi-process spawns from thrashing (12+ cores on
    # this small a dataset just add overhead, not speed).
    model = xgb.XGBRegressor(
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        learning_rate=args.learning_rate,
        objective="reg:squarederror",
        tree_method="hist",
        random_state=42,
        n_jobs=4,
    )
    # Skip eval_set — it doubled wall time without changing the saved model.
    # Per-iteration eval can be re-added with `--with-eval-set` if needed.
    model.fit(X_all[train_mask], y_all[train_mask], verbose=False)

    metrics = {"target_id": args.target_id, "n_train": int(train_mask.sum()),
               "n_val": int(val_mask.sum()), "n_test": int(test_mask.sum())}
    if test_mask.any():
        y_pred = model.predict(X_all[test_mask])
        m = compute_metrics(y_all[test_mask], y_pred)
        metrics.update({f"test_{k}": v for k, v in m.items()})
        # Compatibility key consumed by helmgpt_runner.check_reward_model().
        metrics["scaffold_split_spearman"] = m["spearman"]
    if val_mask.any():
        y_pred = model.predict(X_all[val_mask])
        metrics.update({f"val_{k}": v for k, v in compute_metrics(y_all[val_mask], y_pred).items()})

    args.out_dir.mkdir(parents=True, exist_ok=True)
    pkl_path = args.out_dir / f"{args.target_id}.pkl"
    with pkl_path.open("wb") as f:
        pickle.dump({"model": model, "feature_dim": X_all.shape[1]}, f)
    metrics_path = args.out_dir / f"{args.target_id}_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, default=float))
    print(f"model -> {pkl_path}")
    print(f"metrics -> {metrics_path}")
    print(json.dumps({k: v for k, v in metrics.items() if "spearman" in k or "rmse" in k},
                     indent=2, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
