"""Pull binding-affinity records from BindingDB for a UniProt target.

BindingDB REST API:
    https://www.bindingdb.org/rest/getLigandsByUniprots?uniprot=<ID>&cutoff=<NM>&response=application/json

Returns Ki / Kd / IC50 / EC50 records up to the cutoff (in nM). The peptide
filter `peptide_filter.py` should be run downstream to keep only peptide-like
SMILES.

Dependencies (curation env): pandas, requests (stdlib urllib also works).

Example:
    python -m benchmark.data_curation.bindingdb_query \\
        --target_uniprot Q9NZQ7 --target_name PD-L1 \\
        --output benchmark/data_curation/datasets/raw/pd1_pdl1_bindingdb.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import requests


# Output schema matches chembl_query.py so downstream filters / normalize / merge
# don't have to special-case the source.
COLS = [
    "target_name", "target_chembl_id", "molecule_chembl_id",
    "molecule_pref_name", "canonical_smiles", "standard_type",
    "standard_value", "standard_units", "assay_type",
    "assay_description", "document_chembl_id", "modality_match", "source",
]


def fetch_bindingdb(uniprot: str, cutoff_nM: int = 1_000_000, timeout: int = 60) -> list[dict]:
    """Hit the REST endpoint and return the affinity-record list (may be very long)."""
    url = "https://www.bindingdb.org/rest/getLigandsByUniprots"
    params = {"uniprot": uniprot, "cutoff": str(cutoff_nM), "response": "application/json"}
    print(f"  GET {url}?uniprot={uniprot}&cutoff={cutoff_nM}", file=sys.stderr)
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    body = r.text
    # The endpoint sometimes wraps the payload as
    # {"getLindsByUniprotsResponse": {"affinities": [...]}}
    # tolerate either shape.
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        # The API occasionally responds with HTML on error; surface that.
        snippet = body[:400].replace("\n", " ")
        raise RuntimeError(f"BindingDB response was not JSON: {snippet}") from e
    if isinstance(payload, dict):
        # peel one or two levels of wrapping
        for k in ("getLindsByUniprotsResponse", "getLigandsByUniprotsResponse"):
            if k in payload:
                payload = payload[k]
                break
        if isinstance(payload, dict) and "affinities" in payload:
            payload = payload["affinities"]
    if not isinstance(payload, list):
        raise RuntimeError(f"unexpected BindingDB payload shape: {type(payload).__name__}")
    return payload


def to_canonical_row(rec: dict, *, target_name: str, target_uniprot: str) -> dict:
    """Map a BindingDB record into the canonical raw-CSV schema."""
    aff_type = (rec.get("affinity_type") or "").strip()
    aff_value = rec.get("affinity") or ""
    pmid = rec.get("pmid") or ""
    doi = rec.get("doi") or ""
    return {
        "target_name": target_name,
        "target_chembl_id": target_uniprot,
        "molecule_chembl_id": f"BDB:{rec.get('monomerid', '')}",
        "molecule_pref_name": "",
        "canonical_smiles": (rec.get("smile") or "").strip(),
        "standard_type": aff_type,
        "standard_value": str(aff_value).strip(),
        "standard_units": "nM",   # BindingDB REST returns nM by convention
        "assay_type": "",
        "assay_description": rec.get("query", target_name)[:200],
        "document_chembl_id": f"PMID:{pmid}" if pmid else (f"DOI:{doi}" if doi else ""),
        "modality_match": False,
        "source": "bindingdb",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target_uniprot", required=True,
                   help="UniProt accession (e.g. Q9NZQ7 for PD-L1)")
    p.add_argument("--target_name", required=True)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--cutoff_nM", type=int, default=1_000_000,
                   help="Affinity cutoff in nM (default 1 mM)")
    p.add_argument("--sleep_sec", type=float, default=0.5,
                   help="Sleep between API calls (BindingDB has loose rate limits)")
    args = p.parse_args(argv)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    records = fetch_bindingdb(args.target_uniprot, cutoff_nM=args.cutoff_nM)
    print(f"  fetched {len(records)} affinity records for {args.target_name}", file=sys.stderr)
    time.sleep(args.sleep_sec)

    n_total = n_kept = n_skip_no_smiles = 0
    with args.output.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        seen = set()
        for rec in records:
            n_total += 1
            row = to_canonical_row(rec, target_name=args.target_name,
                                   target_uniprot=args.target_uniprot)
            if not row["canonical_smiles"]:
                n_skip_no_smiles += 1
                continue
            key = (row["molecule_chembl_id"], row["standard_type"], row["standard_value"])
            if key in seen:
                continue
            seen.add(key)
            w.writerow(row)
            n_kept += 1
    print(f"fetched={n_total}  no_smiles_skip={n_skip_no_smiles}  kept={n_kept} -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
