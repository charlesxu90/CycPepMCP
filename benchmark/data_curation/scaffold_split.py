"""Bemis-Murcko scaffold split for HELM-GPT reward-model training.

Takes a curated CSV (output of normalize_endpoints.py) and writes
a `split` column ('train' / 'val' / 'test') based on Bemis-Murcko scaffolds
so that no scaffold appears in more than one split — a standard practice
for binding-affinity model evaluation.

Default split: 70% train / 15% val / 15% test by scaffold-group count.

Dependencies (data-curator env):
    pip install rdkit pandas

Example:
    python -m benchmark.data_curation.scaffold_split \\
        --input  benchmark/data_curation/datasets/pd1_pdl1.csv \\
        --output benchmark/data_curation/datasets/pd1_pdl1_split.csv \\
        --train 0.70 --val 0.15 --test 0.15 --seed 42
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path


def murcko_scaffold(smiles: str) -> str:
    from rdkit import Chem
    from rdkit.Chem.Scaffolds import MurckoScaffold
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return ""
    sc = MurckoScaffold.GetScaffoldForMol(mol)
    return Chem.MolToSmiles(sc, canonical=True) if sc else ""


def split_by_scaffold(records: list[dict], train: float, val: float, test: float,
                      seed: int = 42) -> dict[int, str]:
    """Return {row_index: 'train'|'val'|'test'} where scaffolds don't cross splits."""
    if not 0.99 < train + val + test < 1.01:
        raise ValueError(f"split fractions must sum to 1.0 (got {train+val+test})")

    by_scaffold: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(records):
        sc = r.get("__scaffold", "")
        by_scaffold[sc].append(i)

    # Sort scaffolds by group size (desc), then assign greedily so the largest
    # groups fill the smallest target first — keeps split sizes accurate.
    rng = random.Random(seed)
    scaffolds = sorted(by_scaffold.items(), key=lambda kv: -len(kv[1]))
    n_total = sum(len(g) for _, g in scaffolds)
    targets = {"train": int(n_total * train), "val": int(n_total * val), "test": n_total}
    targets["test"] = n_total - targets["train"] - targets["val"]

    counts = {"train": 0, "val": 0, "test": 0}
    assignment: dict[int, str] = {}
    for sc, idxs in scaffolds:
        # Pick the split that has the most remaining capacity.
        room = sorted(targets.items(), key=lambda kv: -(kv[1] - counts[kv[0]]))
        chosen = room[0][0]
        # If two splits tie, randomize to avoid systematic skew.
        ties = [k for k, _ in room if (targets[k] - counts[k]) == (targets[chosen] - counts[chosen])]
        chosen = rng.choice(ties)
        for i in idxs:
            assignment[i] = chosen
        counts[chosen] += len(idxs)

    return assignment


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--train", type=float, default=0.70)
    p.add_argument("--val", type=float, default=0.15)
    p.add_argument("--test", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)

    try:
        import pandas as pd
    except ImportError as e:
        raise RuntimeError("pandas not installed; `pip install pandas`") from e

    df = pd.read_csv(args.input)
    if "smiles" not in df.columns:
        raise ValueError(f"input {args.input} missing 'smiles' column")

    df["__scaffold"] = df["smiles"].fillna("").map(murcko_scaffold)
    records = df.to_dict("records")
    assignment = split_by_scaffold(records, args.train, args.val, args.test, seed=args.seed)
    df["split"] = [assignment.get(i, "test") for i in range(len(df))]
    df = df.drop(columns=["__scaffold"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)

    counts = df["split"].value_counts().to_dict()
    print(f"in={len(df)}  splits={counts} -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
