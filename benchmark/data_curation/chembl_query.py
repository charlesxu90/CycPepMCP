"""Pull peptide / cyclic-peptide / macrocycle activity records from ChEMBL for a target.

Output schema matches the per-target curated dataset format described in
docs/benchmark_plan.md section 5.1 / HELM-GPT plan section 6 — but is INCOMPLETE
(no patent records, no manual scaffold review). Treat the output as a raw
candidate table that goes into `normalize_endpoints.py` next.

Dependencies (data-curator env, not the main CycPepMCP env):
    pip install chembl-webresource-client pandas

Example:
    python -m benchmark.data_curation.chembl_query \\
        --target_chembl_id CHEMBL3582 \\
        --target_name PD-L1 \\
        --output benchmark/data_curation/datasets/raw/pd1_pdl1_chembl_raw.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Iterable


PEPTIDE_MODALITY_KEYWORDS = {
    "peptide", "cyclic peptide", "macrocycle", "macrocyclic",
    "stapled peptide", "peptidomimetic", "peptide-like", "lariat",
}

ALLOWED_ENDPOINTS = {"Kd", "Ki", "IC50", "EC50"}


def fetch_chembl_records(target_chembl_id: str, *, max_records: int = 5000) -> Iterable[dict]:
    """Yield raw ChEMBL activity records. Uses the official client.

    The caller is responsible for rate-limiting and pagination — the client
    handles that internally but very large pulls may take minutes.
    """
    try:
        from chembl_webresource_client.new_client import new_client
    except ImportError as e:
        raise RuntimeError(
            "chembl_webresource_client not installed; "
            "`pip install chembl-webresource-client`"
        ) from e
    activities = new_client.activity
    qs = activities.filter(
        target_chembl_id=target_chembl_id,
        standard_type__in=list(ALLOWED_ENDPOINTS),
        standard_relation="=",
    ).only(
        "molecule_chembl_id", "canonical_smiles", "standard_type",
        "standard_value", "standard_units", "assay_type", "assay_description",
        "molecule_pref_name", "document_chembl_id",
    )
    for i, rec in enumerate(qs):
        if i >= max_records:
            break
        yield rec


def is_peptide_like(rec: dict) -> bool:
    """Best-effort filter for peptide / macrocycle / stapled-peptide records.

    This is INTENTIONALLY conservative — it accepts anything whose pref_name or
    assay description mentions a peptide-modality keyword. Manual review is
    required afterwards.
    """
    name = (rec.get("molecule_pref_name") or "").lower()
    descr = (rec.get("assay_description") or "").lower()
    return any(k in name or k in descr for k in PEPTIDE_MODALITY_KEYWORDS)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target_chembl_id", required=True,
                   help="ChEMBL target ID (e.g. CHEMBL3582 for PD-L1)")
    p.add_argument("--target_name", required=True,
                   help="Short human-readable target name (e.g. PD-L1)")
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--max_records", type=int, default=5000)
    p.add_argument("--no_modality_filter", action="store_true",
                   help="Disable peptide-modality keyword filter (return all hits).")
    args = p.parse_args(argv)

    args.output.parent.mkdir(parents=True, exist_ok=True)

    cols = ["target_name", "target_chembl_id", "molecule_chembl_id",
            "molecule_pref_name", "canonical_smiles", "standard_type",
            "standard_value", "standard_units", "assay_type",
            "assay_description", "document_chembl_id", "modality_match"]

    n_total = n_kept = 0
    with args.output.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for rec in fetch_chembl_records(args.target_chembl_id, max_records=args.max_records):
            n_total += 1
            modality_match = is_peptide_like(rec)
            if not args.no_modality_filter and not modality_match:
                continue
            n_kept += 1
            w.writerow({
                "target_name": args.target_name,
                "target_chembl_id": args.target_chembl_id,
                "molecule_chembl_id": rec.get("molecule_chembl_id", ""),
                "molecule_pref_name": rec.get("molecule_pref_name", "") or "",
                "canonical_smiles": rec.get("canonical_smiles", "") or "",
                "standard_type": rec.get("standard_type", ""),
                "standard_value": rec.get("standard_value", ""),
                "standard_units": rec.get("standard_units", ""),
                "assay_type": rec.get("assay_type", ""),
                "assay_description": (rec.get("assay_description") or "")[:200],
                "document_chembl_id": rec.get("document_chembl_id", ""),
                "modality_match": modality_match,
            })
    print(f"fetched {n_total} records; kept {n_kept} after modality filter -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
