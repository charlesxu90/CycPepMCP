"""Pull bioactivity records from PubChem for a UniProt target.

Strategy:
  1. Fetch the protein's concise bioactivity table (CSV) — one HTTP call returns
     every (AID, SID, CID, activity_type, value_uM, assay_name, pmid) row.
  2. Collect unique CIDs and batch-fetch CanonicalSMILES (max 200 per call).
  3. Convert values to nM and emit the canonical raw-CSV schema.

Endpoints:
  - https://pubchem.ncbi.nlm.nih.gov/rest/pug/protein/accession/{uniprot}/concise/CSV
  - https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{c1,c2,...}/property/CanonicalSMILES/JSON

Example:
    python -m benchmark.data_curation.pubchem_query \\
        --target_uniprot Q00987 --target_name MDM2 \\
        --output benchmark/data_curation/datasets/raw/mdm2_p53_pubchem.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
import time
from pathlib import Path

import requests


COLS = [
    "target_name", "target_chembl_id", "molecule_chembl_id",
    "molecule_pref_name", "canonical_smiles", "standard_type",
    "standard_value", "standard_units", "assay_type",
    "assay_description", "document_chembl_id", "modality_match", "source",
]

ALLOWED_TYPES = {"Kd", "Ki", "IC50", "EC50"}


def fetch_concise_csv(uniprot: str, timeout: int = 120) -> list[dict]:
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/protein/accession/{uniprot}/concise/CSV"
    print(f"  GET {url}", file=sys.stderr)
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.text)))


def fetch_smiles_for_cids(cids: list[int], batch: int = 200, timeout: int = 60,
                          sleep_sec: float = 0.3) -> dict[int, str]:
    """Batch-fetch stereo-aware SMILES per CID. PubChem renamed CanonicalSMILES
    to ConnectivitySMILES (no stereo) and made `SMILES` the isomeric form;
    requesting the `IsomericSMILES` property name returns the stereo SMILES
    under the response key `SMILES`."""
    out: dict[int, str] = {}
    for i in range(0, len(cids), batch):
        chunk = cids[i:i + batch]
        cid_str = ",".join(str(c) for c in chunk)
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid_str}/property/IsomericSMILES/JSON"
        try:
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            for entry in r.json().get("PropertyTable", {}).get("Properties", []):
                cid = entry.get("CID")
                # Tolerate both old and new response keys.
                smi = (entry.get("SMILES") or entry.get("CanonicalSMILES")
                       or entry.get("IsomericSMILES") or "")
                if cid is not None and smi:
                    out[int(cid)] = smi
        except Exception as e:
            print(f"  warn: SMILES batch {i//batch + 1} failed: {e}", file=sys.stderr)
        time.sleep(sleep_sec)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target_uniprot", required=True)
    p.add_argument("--target_name", required=True)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args(argv)

    args.output.parent.mkdir(parents=True, exist_ok=True)

    rows_in = fetch_concise_csv(args.target_uniprot)
    print(f"  fetched {len(rows_in)} bioactivity rows for {args.target_name}", file=sys.stderr)

    # Filter to endpoint types we care about (some rows have other Activity Name values like "Activity")
    rows_in = [r for r in rows_in if r.get("Activity Name", "").strip() in ALLOWED_TYPES]
    print(f"  after endpoint filter (Kd/Ki/IC50/EC50): {len(rows_in)}", file=sys.stderr)
    if not rows_in:
        print(f"  no usable rows; writing empty CSV", file=sys.stderr)
        args.output.write_text(",".join(COLS) + "\n")
        return 0

    cids = sorted({int(r["CID"]) for r in rows_in if r.get("CID","").strip().isdigit()})
    print(f"  unique CIDs: {len(cids)}", file=sys.stderr)
    smiles_map = fetch_smiles_for_cids(cids)
    print(f"  fetched SMILES for {len(smiles_map)} CIDs", file=sys.stderr)

    n_kept = n_skip_no_smiles = n_skip_no_value = 0
    seen: set = set()
    with args.output.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows_in:
            try:
                cid = int(r["CID"])
            except (ValueError, KeyError):
                continue
            smi = smiles_map.get(cid)
            if not smi:
                n_skip_no_smiles += 1
                continue
            value_uM = r.get("Activity Value [uM]", "").strip()
            if not value_uM:
                n_skip_no_value += 1
                continue
            try:
                value_nM = float(value_uM) * 1000.0
            except ValueError:
                n_skip_no_value += 1
                continue
            key = (cid, r.get("Activity Name",""), value_nM)
            if key in seen:
                continue
            seen.add(key)
            w.writerow({
                "target_name": args.target_name,
                "target_chembl_id": args.target_uniprot,
                "molecule_chembl_id": f"CID:{cid}",
                "molecule_pref_name": "",
                "canonical_smiles": smi,
                "standard_type": r.get("Activity Name","").strip(),
                "standard_value": f"{value_nM:.6g}",
                "standard_units": "nM",
                "assay_type": r.get("Assay Type", "")[:50],
                "assay_description": r.get("Assay Name","")[:200],
                "document_chembl_id": f"PMID:{r.get('PubMed ID','')}" if r.get('PubMed ID','').strip() else "",
                "modality_match": False,
                "source": "pubchem",
            })
            n_kept += 1
    print(f"in_rows={len(rows_in)}  no_smiles={n_skip_no_smiles}  no_value={n_skip_no_value}  "
          f"kept={n_kept} -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
