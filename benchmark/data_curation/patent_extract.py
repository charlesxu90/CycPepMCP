"""Extract peptide / macrocycle activity tables from patents.

This is the manual-review-heavy step in the HELM-GPT data curation pipeline.
The HELM-GPT paper relied on 2,757 KRAS Kd values curated from a single patent
(US20240158446A1) — there is no automated tool that reproduces that quality,
so this script provides a structured INTAKE format only.

Workflow
--------
1. Identify candidate patents per target (Google Patents, Espacenet, etc.).
2. For each patent, manually transcribe / OCR the activity tables into the
   per-patent CSV under `benchmark/data_curation/datasets/raw/patents/<patent_id>.csv`
   with the columns documented below.
3. Run this script with `--merge` to concatenate per-patent CSVs into a single
   target-level raw file, with provenance preserved.

Per-patent CSV schema (columns the curator must populate):
    patent_id        e.g. US20240158446A1
    compound_id      patent-internal identifier (e.g. "Compound 12")
    smiles           canonical SMILES (or DRAW if structure-only and a chemist must redraw)
    helm             optional HELM string (often left blank; will be derived in normalize)
    modality         cyclic peptide | stapled peptide | macrocycle | peptidomimetic | peptide
    endpoint_type    Kd | Ki | IC50 | EC50
    endpoint_value   numeric, original units
    endpoint_unit    nM | uM | mM | pM
    assay_type       binding | biochemical | cell-based | functional
    assay_descr      one-line description; keep short
    target_name      e.g. PD-L1
"""
from __future__ import annotations

import argparse
import csv
import sys
from glob import glob
from pathlib import Path

REQUIRED_COLS = [
    "patent_id", "compound_id", "smiles", "helm", "modality",
    "endpoint_type", "endpoint_value", "endpoint_unit",
    "assay_type", "assay_descr", "target_name",
]


def merge_patent_csvs(patents_dir: Path, output: Path, target_name: str | None = None) -> int:
    """Concatenate every CSV in `patents_dir` into `output`. Validates schema."""
    files = sorted(glob(str(patents_dir / "*.csv")))
    if not files:
        print(f"error: no per-patent CSVs under {patents_dir}", file=sys.stderr)
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    n_kept = 0
    with output.open("w", newline="") as fout:
        w = csv.DictWriter(fout, fieldnames=REQUIRED_COLS)
        w.writeheader()
        for fp in files:
            with open(fp) as fin:
                r = csv.DictReader(fin)
                missing = set(REQUIRED_COLS) - set(r.fieldnames or [])
                if missing:
                    print(f"warn: {fp} missing columns {missing}; skipping",
                          file=sys.stderr)
                    continue
                for row in r:
                    if target_name and row.get("target_name", "").strip() != target_name:
                        continue
                    w.writerow({c: row.get(c, "").strip() for c in REQUIRED_COLS})
                    n_kept += 1
    print(f"merged {len(files)} patent files -> {output} ({n_kept} rows)")
    return 0


def init_template(patent_id: str, output: Path) -> int:
    """Write an empty per-patent CSV template that the curator fills in."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        print(f"error: {output} exists; not overwriting", file=sys.stderr)
        return 1
    with output.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REQUIRED_COLS)
        w.writeheader()
        w.writerow({c: f"<{c}>" for c in REQUIRED_COLS})
    print(f"template written: {output} (replace placeholder row with real data)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Create an empty per-patent CSV template")
    p_init.add_argument("--patent_id", required=True)
    p_init.add_argument("--output", required=True, type=Path)

    p_merge = sub.add_parser("merge", help="Concatenate per-patent CSVs for a target")
    p_merge.add_argument("--patents_dir", required=True, type=Path,
                         help="Directory of per-patent CSVs")
    p_merge.add_argument("--output", required=True, type=Path)
    p_merge.add_argument("--target_name", default=None,
                         help="Filter rows by target_name column")

    args = p.parse_args(argv)
    if args.cmd == "init":
        return init_template(args.patent_id, args.output)
    if args.cmd == "merge":
        return merge_patent_csvs(args.patents_dir, args.output, args.target_name)
    return 1


if __name__ == "__main__":
    sys.exit(main())
