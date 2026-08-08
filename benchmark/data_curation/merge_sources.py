"""Merge per-source raw CSVs into a single per-target dataset.

Runs the full pipeline: concat raw sources → SMILES peptide filter →
normalize_endpoints → scaffold_split.

Inputs scanned from `benchmark/data_curation/datasets/raw/`:
  <target>_chembl_*.csv      (ChEMBL pulls, multiple files for compound + complex targets)
  <target>_bindingdb*.csv    (BindingDB)
  <target>_pubchem.csv       (PubChem)
  <target>_mdmx_bindingdb.csv  (MDMX, MDM2 only)
  <target>_mdmx_pubchem.csv    (MDMX, MDM2 only)
  <target>_pmc_*.csv         (PMC paper extracts, Tier 2)
  patents/<target>_*_extracted.csv  (Patent LLM extracts, Tier 3)

Outputs:
  datasets/<target>_full.csv          (merged + normalized)
  datasets/<target>_full_split.csv    (scaffold split 70/15/15)

For MDM2 the merge auto-detects MDMX records (target_chembl_id starts with
`O15151` or `CHEMBL1907611`, target_name contains 'MDMX' or 'MDM4') and adds a
`target_side` column so the regression can use it as a multitask feature.

Usage:
    python -m benchmark.data_curation.merge_sources --target pd1_pdl1
    python -m benchmark.data_curation.merge_sources --target mdm2_p53
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / "benchmark" / "configs" / "thresholds.py").is_file():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break


MDMX_MARKERS = ("O15151", "CHEMBL1907611", "MDMX", "MDM4")


def _is_mdmx(row: dict) -> bool:
    blob = " ".join(str(row.get(k, "")) for k in
                    ("target_chembl_id", "target_name", "assay_description"))
    return any(m in blob for m in MDMX_MARKERS)


def collect_raw(target: str, raw_dir: Path) -> list[Path]:
    """Glob raw CSVs that belong to this target. Case-insensitive on suffix part."""
    found = []
    target_lower = target.lower()
    suffix_markers = ("chembl", "bindingdb", "pubchem", "pmc",
                      "mdmx_bindingdb", "mdmx_pubchem", "patent")
    for p in raw_dir.glob(f"{target}_*.csv"):
        stem_low = p.stem.lower()
        if any(m in stem_low for m in suffix_markers):
            # Skip prior peptide-filtered or merged outputs
            if stem_low.endswith(("_peptides", "_merged_raw", "_merged_peptides", "_filtered", "_all")):
                continue
            found.append(p)
    # Patents (Tier 3) subdir
    patents_dir = raw_dir / "patents"
    if patents_dir.is_dir():
        found.extend(sorted(patents_dir.glob(f"{target}_*_extracted.csv")))
    return sorted(set(found))


def concat_csvs(paths: list[Path], out_path: Path) -> int:
    """Concatenate CSVs that share the canonical raw schema. Writes a unified header."""
    n = 0
    cols: list[str] | None = None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as fout:
        w = None
        for fp in paths:
            with fp.open() as fin:
                r = csv.DictReader(fin)
                if cols is None:
                    cols = list(r.fieldnames or [])
                    if "source" not in cols:
                        cols.append("source")
                    if "target_side" not in cols:
                        cols.append("target_side")
                    w = csv.DictWriter(fout, fieldnames=cols)
                    w.writeheader()
                for row in r:
                    # Add missing columns
                    if "source" not in row or not row["source"]:
                        # Infer from filename
                        if "chembl" in fp.name.lower():
                            row["source"] = "chembl"
                        elif "bindingdb" in fp.name.lower():
                            row["source"] = "bindingdb"
                        elif "pubchem" in fp.name.lower():
                            row["source"] = "pubchem"
                        elif "pmc" in fp.name.lower():
                            row["source"] = "pmc"
                        elif "patent" in fp.name.lower() or "patents" in str(fp.parent).lower():
                            row["source"] = "patent"
                        else:
                            row["source"] = "unknown"
                    if "target_side" not in row or not row["target_side"]:
                        row["target_side"] = "mdmx" if _is_mdmx(row) else "primary"
                    w.writerow({c: row.get(c, "") for c in cols})
                    n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", required=True, choices=["pd1_pdl1", "mdm2_p53"])
    p.add_argument("--data_dir", default="benchmark/data_curation/datasets", type=Path)
    p.add_argument("--target_id_for_norm", default=None,
                   help="UniProt ID for normalize_endpoints --target_id (default: Q9NZQ7 / Q00987)")
    p.add_argument("--peptide_min_heavy", type=int, default=50)
    p.add_argument("--peptide_min_amide", type=int, default=5)
    args = p.parse_args(argv)

    raw_dir = args.data_dir / "raw"
    target_id = args.target_id_for_norm or ("Q9NZQ7" if args.target == "pd1_pdl1" else "Q00987")
    concat_path = raw_dir / f"{args.target}_merged_raw.csv"
    peptides_path = raw_dir / f"{args.target}_merged_peptides.csv"
    normalized_path = args.data_dir / f"{args.target}_full.csv"
    split_path = args.data_dir / f"{args.target}_full_split.csv"

    # 1. Concat
    paths = collect_raw(args.target, raw_dir)
    if not paths:
        print(f"error: no raw CSVs found for {args.target} under {raw_dir}", file=sys.stderr)
        return 1
    print(f"merging {len(paths)} raw source CSVs:")
    for fp in paths:
        nl = sum(1 for _ in fp.open()) - 1
        print(f"  {fp.relative_to(args.data_dir.parent.parent if args.data_dir.is_absolute() else args.data_dir.parent)}  ({nl} rows)")
    n_concat = concat_csvs(paths, concat_path)
    print(f"  -> {concat_path}  ({n_concat} rows)")

    # 2. Peptide filter (re-use existing module via subprocess)
    print(f"\npeptide filter (min_heavy={args.peptide_min_heavy}, min_amide={args.peptide_min_amide}):")
    rc = subprocess.run([
        sys.executable, "-m", "benchmark.data_curation.peptide_filter",
        "--inputs", str(concat_path),
        "--output", str(peptides_path),
        "--min_heavy", str(args.peptide_min_heavy),
        "--min_amide", str(args.peptide_min_amide),
    ], cwd=args.data_dir.parent.parent.parent if args.data_dir.is_absolute() else Path.cwd())
    if rc.returncode != 0:
        print("peptide_filter failed", file=sys.stderr)
        return rc.returncode

    # 3. Normalize endpoints
    print(f"\nnormalize endpoints (target_id={target_id}):")
    rc = subprocess.run([
        sys.executable, "-m", "benchmark.data_curation.normalize_endpoints",
        "--inputs", str(peptides_path),
        "--target_id", target_id,
        "--output", str(normalized_path),
    ])
    if rc.returncode != 0:
        return rc.returncode

    # 4. Carry the target_side column through normalize (it doesn't preserve unknown
    # columns), so we re-join from the peptide-filtered intermediate.
    _carry_target_side(peptides_path, normalized_path)

    # 5. Scaffold split
    print(f"\nscaffold split:")
    rc = subprocess.run([
        sys.executable, "-m", "benchmark.data_curation.scaffold_split",
        "--input", str(normalized_path),
        "--output", str(split_path),
    ])
    return rc.returncode


def _carry_target_side(peptides_csv: Path, normalized_csv: Path) -> None:
    """Attach `target_side` to each normalized row. The normalize step keeps
    `target_chembl_id` as a pass-through column, so we map UniProt accession
    → side directly (more reliable than a SMILES join, which collapses
    multi-target compounds)."""
    import csv as _csv

    rows = []
    fieldnames: list[str] = []
    with normalized_csv.open() as f:
        r = _csv.DictReader(f)
        fieldnames = list(r.fieldnames or [])
        if "target_side" not in fieldnames:
            fieldnames.append("target_side")
        for row in r:
            # Authoritative routing: UniProt accession → side
            uniprot = (row.get("target_chembl_id") or "").strip()
            name = (row.get("target_name") or "").strip().upper()
            if uniprot == "O15151" or "MDMX" in name or "MDM4" in name:
                row["target_side"] = "mdmx"
            else:
                row["target_side"] = "primary"
            rows.append(row)
    with normalized_csv.open("w", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    sys.exit(main())
