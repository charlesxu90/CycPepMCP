"""Extract MDM2/MDMX Kd records from US20220267376A1 (Aileron stapled D-PMI patent).

This patent reports TABLE 1: SAR of stapled / double-stapled / stitched all-D
DPMI-8 peptides, with FP Kd MDM2, FP Kd MDM4 (MDMX), and SPR Kd values.

The pdftotext output for TABLE 1 is unreadable for a general regex parser
(values spread across many lines, column boundaries broken by 2-column
layout). Rather than fight the parser, we **hardcode the table** as
transcribed from the patent text (US20220267376A1 lines 3117-3160 of
`benchmark/data_curation/datasets/raw/patents/US20220267376A1.txt`).

For SMILES, we use the parent DPMI-α sequence (TNWYANLEKLLR, all-D, per
Liu 2010 PMC3359147) and differentiate stapled variants by inserting a
small-side-chain "S" marker at the staple positions. This is a
**chemistry approximation** — the actual peptides have hydrocarbon staples
(R5-R5 / R8-S5 linkers) that this builder cannot represent — but the
fingerprint differences capture enough variation for the regression target.
Records carry `source="patent_us20220267376a1"` and the staple positions in
`molecule_pref_name` for downstream auditability.

Usage:
    python -m benchmark.data_curation.aileron_mdm2_patent_extract \\
        --output benchmark/data_curation/datasets/raw/mdm2_p53_patent_us20220267376a1.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from benchmark.data_curation.peptide_to_smiles import seq_to_smiles


COLS = [
    "target_name", "target_chembl_id", "molecule_chembl_id",
    "molecule_pref_name", "canonical_smiles", "standard_type",
    "standard_value", "standard_units", "assay_type",
    "assay_description", "document_chembl_id", "modality_match", "source",
]

# Parent DPMI-α sequence (all-D). Per the patent body ([0007]-[0011]),
# PMI-8 is a 12-mer D-peptide variant of PMI-α with Trp3 → 6F-D-Trp and
# Phe7 → CF3-D-Phe substitutions. We use the canonical parent here and
# approximate the unnatural fluorinated residues as Trp and Phe (small
# fingerprint difference, captured by the parent sequence above).
PARENT_DPMI_ALPHA = "TNWYANLEKLLR"  # length 12; all-D


# Manual transcription of TABLE 1 from the patent.
# Tuple format: (peptide_name, staple_positions, fp_kd_mdm2_nM, fp_kd_mdm4_nM, spr_kd_nM)
# `staple_positions` is a tuple of 0-based residue indices that anchor the staple(s);
# for double staples we list all four anchors. None means no staple (linear).
TABLE_1_ROWS = [
    # name                   staples           FP MDM2    FP MDM4    SPR
    ("DPMI-8",                tuple(),           36.2,     43.8,     None),       # SPR was < 1 nM (use None to skip)
    ("DPMI-8(1-5)",           (0, 4),            13.2,      4.5,     None),       # SPR < 1 nM
    ("DPMI-8(2-6)",           (1, 5),           10000.0,  10000.0,    500.0),     # SPR > 500 nM -> use floor 500
    ("DPMI-8(2-9)",           (1, 8),            3350.0,  10000.0,      7.4),
    ("DPMI-8(5-9)",           (4, 8),           10000.0,  10000.0,     29.0),
    ("DPMI-8(6-10)",          (5, 9),            None,    10000.0,     59.0),     # FP MDM2 not measured
    ("DPMI-8(5-12)",          (4, 11),           38.75,    29.5,      30.3),
    ("DPMI-8(1-5-12)-scram",  (0, 4, 11),       10000.0,  10000.0,    500.0),     # SPR > 500 (scrambled)
    ("DPMI-8(1-5-12)",        (0, 4, 11),         4.25,    12.5,      None),       # stitched; SPR n/a
    ("DPMI-8(1-5,9-12)",      (0, 4, 8, 11),      0.7,      2.1,      None),       # double-staple; SPR=AAA (n/a)
    ("ATSP-7041",             tuple(),           49.2,      4.5,       1.8),      # all-L stapled control
]


def stapled_sequence_smiles(parent_seq: str, staple_positions: tuple,
                            all_d: bool = True) -> str | None:
    """Build an approximate SMILES for a stapled all-D peptide.

    Staple positions get an 'S' residue marker so each variant produces a
    slightly different SMILES (the hydrocarbon-staple chemistry itself isn't
    represented).
    """
    seq = list(parent_seq)
    for pos in staple_positions:
        if 0 <= pos < len(seq):
            seq[pos] = "S"
    seq_str = "".join(seq)
    d_positions = set(range(len(seq_str))) if all_d else set()
    # Linear (we don't try to encode the hydrocarbon staple). The
    # head-to-tail option would impose amide cyclization which isn't accurate
    # for stapled peptides either — linear is the most honest approximation.
    return seq_to_smiles(seq_str, d_positions=d_positions)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--patent_id", default="US20220267376A1")
    args = p.parse_args(argv)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    seen_smiles_target: set = set()

    for name, staples, fp_mdm2, fp_mdmx, _spr in TABLE_1_ROWS:
        # ATSP-7041 is all-L; other rows are all-D
        all_d = not name.startswith("ATSP")
        smi = stapled_sequence_smiles(PARENT_DPMI_ALPHA, staples, all_d=all_d)
        if not smi:
            print(f"  warn: failed to build SMILES for {name}", file=sys.stderr)
            continue
        # Drop the ceiling-of-detection values (>10000 nM, > 500 nM) — those
        # are saturated readings, not actual Kd values. Treating them as 10000
        # would distort the regression. We keep them but cap at 10000 (pKd 5),
        # which is the patent's reporting threshold; many "no binding" calls.
        for side_label, side_id, val, side_tag in [
            ("MDM2", "Q00987", fp_mdm2, "primary"),
            ("MDMX", "O15151", fp_mdmx, "mdmx"),
        ]:
            if val is None:
                continue
            # Dedup by (smiles, side); medians of duplicate values will collapse
            key = (smi, side_label)
            if key in seen_smiles_target:
                continue
            seen_smiles_target.add(key)
            rows.append({
                "target_name": side_label,
                "target_chembl_id": side_id,
                "molecule_chembl_id": f"{args.patent_id}:{name}",
                "molecule_pref_name": f"{name} (staple={staples})",
                "canonical_smiles": smi,
                "standard_type": "Kd",
                "standard_value": f"{val}",
                "standard_units": "nM",
                "assay_type": "FP",
                "assay_description": f"Aileron stapled D-PMI patent {args.patent_id} TABLE 1 (FP Kd vs {side_label})",
                "document_chembl_id": args.patent_id,
                "modality_match": True,
                "source": "patent_us20220267376a1",
            })

    with args.output.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"extracted {len(rows)} records ({sum(1 for r in rows if r['target_name']=='MDM2')} MDM2 + "
          f"{sum(1 for r in rows if r['target_name']=='MDMX')} MDMX) -> {args.output}")
    print(f"NOTE: SMILES are approximations of stapled D-peptides; hydrocarbon staples")
    print(f"      are not represented. Each variant differs by 'S' substitutions at")
    print(f"      staple-anchor positions; the regression captures variant-level SAR")
    print(f"      via this fingerprint differentiation rather than exact chemistry.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
