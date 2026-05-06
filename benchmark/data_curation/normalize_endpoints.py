"""Normalize per-target raw activity tables into the unified curated schema.

Input: a CSV with at minimum {smiles, endpoint_type, endpoint_value,
endpoint_unit, modality, target_name, source}. Multiple inputs (ChEMBL +
patent extracts + literature transcriptions) can be passed and concatenated.

Output: a single curated CSV matching docs/HELM-GPT plan section 6 schema:
    target_name, target_id, molecule_id, smiles, helm, modality,
    endpoint_type, endpoint_value, endpoint_unit, p_activity, assay_type,
    source

`p_activity` is the negative log10 of the activity in molar units
(e.g. 12.5 nM Kd -> pKd 7.90), suitable for regression reward training.

Dependencies (data-curator env):
    pip install rdkit pandas

Example:
    python -m benchmark.data_curation.normalize_endpoints \\
        --inputs benchmark/data_curation/datasets/raw/pd1_pdl1_chembl_raw.csv \\
                 benchmark/data_curation/datasets/raw/pd1_pdl1_patents_merged.csv \\
        --target_id Q9NZQ7 \\
        --output benchmark/data_curation/datasets/pd1_pdl1.csv
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Optional


# Endpoint -> molarity multiplier (everything goes to molar before -log10).
UNIT_TO_MOLAR = {
    "M": 1.0, "mM": 1e-3, "uM": 1e-6, "μM": 1e-6, "nM": 1e-9, "pM": 1e-12,
}

# Endpoint type families that are treated as comparable for pActivity.
ALLOWED_ENDPOINTS = {"Kd", "Ki", "IC50", "EC50"}


def to_p_activity(value: float, unit: str) -> Optional[float]:
    """Convert e.g. (12.5, 'nM') -> 7.90 (pKd / pIC50 / etc., higher = stronger)."""
    mult = UNIT_TO_MOLAR.get(unit.strip())
    if mult is None:
        return None
    if value is None or value <= 0:
        return None
    molar = value * mult
    return round(-math.log10(molar), 3)


def canonicalize_smiles(s: str) -> Optional[str]:
    try:
        from rdkit import Chem
    except ImportError as e:
        raise RuntimeError("rdkit not installed; `pip install rdkit`") from e
    mol = Chem.MolFromSmiles(s)
    if mol is None:
        return None
    return Chem.MolToSmiles(mol, canonical=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--inputs", nargs="+", required=True, type=Path)
    p.add_argument("--target_id", required=True,
                   help="UniProt or ChEMBL target ID (recorded in every row)")
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--allowed_endpoints", nargs="+", default=sorted(ALLOWED_ENDPOINTS))
    p.add_argument("--require_modality", action="store_true",
                   help="Drop rows whose modality is empty or not peptide-like")
    args = p.parse_args(argv)

    try:
        import pandas as pd
    except ImportError as e:
        raise RuntimeError("pandas not installed; `pip install pandas`") from e

    frames = []
    for fp in args.inputs:
        df = pd.read_csv(fp)
        df["__source_file"] = fp.name
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)
    n_in = len(raw)

    out_rows = []
    n_drop_endpoint = n_drop_unit = n_drop_smiles = n_drop_modality = 0
    for i, r in raw.iterrows():
        ep_type = str(r.get("endpoint_type", r.get("standard_type", ""))).strip()
        if ep_type not in args.allowed_endpoints:
            n_drop_endpoint += 1
            continue
        ep_value_raw = r.get("endpoint_value", r.get("standard_value", ""))
        try:
            ep_value = float(ep_value_raw)
        except (TypeError, ValueError):
            n_drop_unit += 1
            continue
        ep_unit = str(r.get("endpoint_unit", r.get("standard_units", ""))).strip()
        p_act = to_p_activity(ep_value, ep_unit)
        if p_act is None:
            n_drop_unit += 1
            continue
        smiles_raw = str(r.get("smiles", r.get("canonical_smiles", ""))).strip()
        smiles = canonicalize_smiles(smiles_raw) if smiles_raw else None
        if not smiles:
            n_drop_smiles += 1
            continue
        modality = str(r.get("modality", "")).strip().lower()
        if args.require_modality and not any(k in modality for k in
                                              ("peptide", "macrocycle", "stapled")):
            n_drop_modality += 1
            continue
        out_rows.append({
            "target_name": r.get("target_name", ""),
            "target_id": args.target_id,
            "molecule_id": r.get("molecule_chembl_id", r.get("compound_id", f"row_{i}")),
            "smiles": smiles,
            "helm": r.get("helm", ""),
            "modality": modality or "unspecified",
            "endpoint_type": ep_type,
            "endpoint_value": ep_value,
            "endpoint_unit": ep_unit,
            "p_activity": p_act,
            "assay_type": r.get("assay_type", ""),
            "source": r.get("source", r.get("document_chembl_id",
                                            r.get("patent_id", r["__source_file"]))),
        })

    # Deduplicate by (smiles, endpoint_type) — keep median activity per pair.
    df_out = pd.DataFrame(out_rows)
    if len(df_out):
        df_out["p_activity"] = df_out.groupby(["smiles", "endpoint_type"])["p_activity"].transform("median")
        df_out = df_out.drop_duplicates(subset=["smiles", "endpoint_type"], keep="first")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(args.output, index=False)
    print(f"in={n_in}  endpoint_drop={n_drop_endpoint}  unit_drop={n_drop_unit}  "
          f"smiles_drop={n_drop_smiles}  modality_drop={n_drop_modality}  "
          f"out={len(df_out)} -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
