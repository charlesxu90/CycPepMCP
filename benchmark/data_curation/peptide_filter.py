"""SMILES-based peptide / macrocycle filter.

Replaces the keyword-based filter in `chembl_query.py` (which was unreliable
because ChEMBL assay descriptions like "MDM2/p53 fluorescence peptide assay"
include the word 'peptide' even when the assayed compound is a small molecule).

A row is kept iff its SMILES looks peptide-like:
  - parseable by RDKit
  - molecular weight in [500, 3000] Da (typical macrocycle range)
  - heavy-atom count >= MIN_HEAVY (default 35)
  - >= MIN_AMIDE peptide amide bonds (N-C(=O) where the N is not aromatic)

Usage:
    python -m benchmark.data_curation.peptide_filter \\
        --inputs raw/pd1_pdl1_CHEMBL*.csv \\
        --output raw/pd1_pdl1_peptides.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Iterable

DEFAULT_MIN_HEAVY = 35
DEFAULT_MIN_AMIDE = 3
DEFAULT_MW_RANGE = (500.0, 3000.0)


def _count_amide_bonds(mol) -> int:
    """Count peptide-like amide bonds: N-C(=O) where N is sp3 (not aromatic)."""
    from rdkit import Chem
    patt = Chem.MolFromSmarts("[N;!$(N=*);!$(N#*);!a]-[C;!a](=[O;!a])")
    if patt is None:
        return 0
    matches = mol.GetSubstructMatches(patt)
    return len(matches)


def is_peptide_like(smiles: str, min_heavy: int = DEFAULT_MIN_HEAVY,
                    min_amide: int = DEFAULT_MIN_AMIDE,
                    mw_range: tuple = DEFAULT_MW_RANGE) -> bool:
    from rdkit import Chem
    from rdkit.Chem import Descriptors
    if not smiles:
        return False
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return False
    n_heavy = mol.GetNumHeavyAtoms()
    if n_heavy < min_heavy:
        return False
    mw = Descriptors.MolWt(mol)
    if not (mw_range[0] <= mw <= mw_range[1]):
        return False
    n_amide = _count_amide_bonds(mol)
    if n_amide < min_amide:
        return False
    return True


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--inputs", nargs="+", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--min_heavy", type=int, default=DEFAULT_MIN_HEAVY)
    p.add_argument("--min_amide", type=int, default=DEFAULT_MIN_AMIDE)
    p.add_argument("--mw_min", type=float, default=DEFAULT_MW_RANGE[0])
    p.add_argument("--mw_max", type=float, default=DEFAULT_MW_RANGE[1])
    args = p.parse_args(argv)

    n_in = 0
    n_out = 0
    n_smi_drop = 0
    n_size_drop = 0
    n_amide_drop = 0
    n_mw_drop = 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fout = args.output.open("w", newline="")
    w = None

    for fp in args.inputs:
        if not fp.is_file():
            print(f"  warn: missing {fp}", file=sys.stderr)
            continue
        with fp.open() as fin:
            r = csv.DictReader(fin)
            for row in r:
                n_in += 1
                if w is None:
                    w = csv.DictWriter(fout, fieldnames=r.fieldnames)
                    w.writeheader()
                # Re-classify via SMILES properties (importing RDKit each call is fine)
                from rdkit import Chem
                from rdkit.Chem import Descriptors
                smi = row.get("canonical_smiles", "")
                if not smi:
                    n_smi_drop += 1
                    continue
                mol = Chem.MolFromSmiles(smi)
                if mol is None:
                    n_smi_drop += 1
                    continue
                n_heavy = mol.GetNumHeavyAtoms()
                if n_heavy < args.min_heavy:
                    n_size_drop += 1
                    continue
                mw = Descriptors.MolWt(mol)
                if not (args.mw_min <= mw <= args.mw_max):
                    n_mw_drop += 1
                    continue
                n_amide = _count_amide_bonds(mol)
                if n_amide < args.min_amide:
                    n_amide_drop += 1
                    continue
                # Mark provenance — set modality_match=True to feed into normalize_endpoints
                row["modality_match"] = True
                w.writerow(row)
                n_out += 1
    fout.close()

    print(f"in={n_in}  smi_drop={n_smi_drop}  size_drop={n_size_drop}  "
          f"mw_drop={n_mw_drop}  amide_drop={n_amide_drop}  out={n_out} -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
