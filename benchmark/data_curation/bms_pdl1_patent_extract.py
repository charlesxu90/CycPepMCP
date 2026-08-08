"""Extract per-compound IC50/HTRF records from the 3 BMS macrocyclic PD-L1 patents.

Targets: US10538555, US9879046, US9850283 (BMS macrocyclic peptide patents).

These patents follow a "patent dump" disclosure pattern:
  - Thousands of synthesis examples per patent (compound preparations)
  - Numeric IC50 values ONLY for a few hero compounds (typically 1, 2, 71, 99)
  - Other compounds disclosed under generic "IC50 ≤ 200 nM" claims

This extractor:
  1. Parses `Compound No. X IC50 Y nM` patterns (tolerating OCR-garbled spacing
     like `CompoundNo.1IC50202nM`).
  2. Maps each Compound No. to its Example chunk for sequence reconstruction.
  3. Reads the Fmoc-AA-OH coupling sequence from the Example chunk and
     reconstructs a 1-letter sequence (with `X` for non-canonical residues).
  4. Emits canonical-schema rows.

Run after patent_text_chunk.py has produced the chunks.

Usage:
    python -m benchmark.data_curation.bms_pdl1_patent_extract \\
        --patents_dir benchmark/data_curation/datasets/raw/patents \\
        --output benchmark/data_curation/datasets/raw/pd1_pdl1_patents_bms.csv
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

from benchmark.data_curation.peptide_to_smiles import seq_to_smiles


COLS = [
    "target_name", "target_chembl_id", "molecule_chembl_id",
    "molecule_pref_name", "canonical_smiles", "standard_type",
    "standard_value", "standard_units", "assay_type",
    "assay_description", "document_chembl_id", "modality_match", "source",
]

# Approximation map for non-canonical residues when reconstructing SMILES from
# patent text. Nle ≈ Leu (both 4-carbon aliphatic), Aib ≈ Ala (small aliphatic),
# Sar ≈ Gly (no side chain), etc. This is lossy — the resulting SMILES has the
# right backbone length and approximately-right Morgan FP for a regression
# reward model but is NOT the exact structure.
NONCANON_APPROX = {"X": "L"}  # Nle → Leu (substituted at extract step)

# IC50 pattern — tolerates the OCR-garbled spacing common in BMS patents
IC50_RE = re.compile(
    r"Compound\s*No\.?\s*([0-9]+)\s*IC[ ]?50\s*([0-9]+(?:[,.][0-9]+)?)\s*nM",
    re.IGNORECASE,
)

# Fmoc residue label, allowing optional [N-Me] prefix and side-chain protections
FMOC_RE = re.compile(r"Fmoc[-\s]+(?:\[N[-\s]*Me\][-\s]*)?([A-Z][a-z][a-z])[\s(]")

# 3-letter → 1-letter codes (standard + a few common non-canonical mapped to X
# so the regex picks them up but they don't break peptide_to_smiles).
THREE_TO_ONE = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C",
    "Gln": "Q", "Glu": "E", "Gly": "G", "His": "H", "Ile": "I",
    "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P",
    "Ser": "S", "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V",
    # Common non-canonical aa in BMS PD-L1 patents
    "Nle": "X",   # norleucine
    "Nva": "X",   # norvaline
    "Aib": "X",   # 2-aminoisobutyric acid
    "Sar": "X",   # sarcosine (N-methyl glycine)
    "Pen": "X",   # penicillamine
    "Hyp": "X",   # hydroxyproline
}


def extract_ic50_records(patent_text: str, patent_id: str) -> list[tuple[str, float]]:
    """Return list of (compound_no, ic50_nM) tuples; dedup by (compound, value)."""
    seen: set = set()
    out: list[tuple[str, float]] = []
    for m in IC50_RE.finditer(patent_text):
        cnum = m.group(1)
        val_str = m.group(2).replace(",", "")
        try:
            val = float(val_str)
        except ValueError:
            continue
        key = (cnum, val)
        if key in seen:
            continue
        seen.add(key)
        out.append((cnum, val))
    return out


def extract_sequence_from_example(chunk_text: str) -> str | None:
    """Parse Fmoc-AA-OH coupling list in synthesis order. Return 1-letter seq
    (with 'X' for unmapped residues). Returns None if no Fmoc residues found."""
    letters: list[str] = []
    for m in FMOC_RE.finditer(chunk_text):
        three = m.group(1)
        # Capitalize first letter, lowercase rest (Fmoc text may have varying case)
        three_cap = three[0].upper() + three[1:].lower()
        one = THREE_TO_ONE.get(three_cap, "X")
        letters.append(one)
    if not letters:
        return None
    # Patent SPPS adds C → N, so the first Fmoc-AA coupled is the C-terminal
    # residue; the LAST coupled is the N-terminal. Reverse to read N→C.
    return "".join(reversed(letters))


def find_example_for_compound(chunks_dir: Path, compound_no: str) -> Path | None:
    """Search chunks for "Synthesis of Compound No. X" header."""
    if not chunks_dir.is_dir():
        return None
    target_re = re.compile(rf"Synthesis\s+of\s+Compound\s+No\.?\s*{compound_no}\b")
    for chunk in sorted(chunks_dir.glob("Example_*.txt")):
        text = chunk.read_text()
        if target_re.search(text):
            return chunk
    return None


def find_synthesis_block(patent_text: str, compound_no: str,
                         block_len: int = 4000) -> str | None:
    """Search the full patent text for the synthesis block of Compound No. X.
    Returns the text from the marker through the next 'Example' marker (or
    `block_len` chars, whichever is shorter)."""
    target_re = re.compile(rf"Synthesis\s+of\s+Compound\s+No\.?\s*{compound_no}\b")
    m = target_re.search(patent_text)
    if not m:
        return None
    start = m.start()
    # Look for the next 'Synthesis of Compound No' or 'Example N' marker after start
    after = patent_text[start + 10:]
    next_marker = re.search(r"Synthesis\s+of\s+Compound\s+No\.?\s+\d+|Example\s+\d+", after)
    if next_marker:
        end = start + 10 + next_marker.start()
    else:
        end = min(len(patent_text), start + block_len)
    return patent_text[start: min(end, start + block_len)]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--patents_dir", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--patent_ids", nargs="+",
                   default=["US10538555", "US9879046", "US9850283"])
    args = p.parse_args(argv)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    seen_smiles: set = set()
    for pid in args.patent_ids:
        txt_path = args.patents_dir / f"{pid}.txt"
        chunks_dir = args.patents_dir / f"{pid}_chunks"
        if not txt_path.is_file():
            print(f"  {pid}: missing {txt_path}", file=sys.stderr)
            continue
        patent_text = txt_path.read_text()
        ic50_records = extract_ic50_records(patent_text, pid)
        print(f"  {pid}: {len(ic50_records)} IC50 records "
              f"(unique compounds: {len({c for c,_ in ic50_records})})")
        for cnum, val in ic50_records:
            block = find_synthesis_block(patent_text, cnum)
            if block is None:
                # No synthesis text in this patent — skip; the compound's
                # SMILES is likely in another patent or BindingDB already.
                continue
            seq = extract_sequence_from_example(block)
            if not seq or len(seq) < 6:
                continue
            # Approximate non-canonical residues to nearest canonical so SMILES
            # builds (Nle→Leu, etc.). Lossy but yields fingerprintable structures.
            seq_approx = "".join(NONCANON_APPROX.get(c, c) for c in seq)
            # BMS PD-L1 macrocycles are head-to-side-chain (chloroacetyl-Cys
            # thioether). Our peptide_to_smiles supports head-to-tail only —
            # use head-to-tail as a SMILES proxy (good for fingerprint-based
            # similarity but lossy on exact topology).
            smi = seq_to_smiles(seq_approx, cyclize="head-to-tail")
            if not smi:
                smi = seq_to_smiles(seq_approx)
            if not smi:
                continue
            if smi in seen_smiles:
                continue
            seen_smiles.add(smi)
            rows.append({
                "target_name": "PD-L1",
                "target_chembl_id": "Q9NZQ7",
                "molecule_chembl_id": f"{pid}:Compound{cnum}",
                "molecule_pref_name": f"BMS-Compound-{cnum}",
                "canonical_smiles": smi,
                "standard_type": "IC50",
                "standard_value": f"{val}",
                "standard_units": "nM",
                "assay_type": "HTRF",
                "assay_description": f"BMS PD-L1 macrocyclic peptide patent {pid} Compound No. {cnum}",
                "document_chembl_id": pid,
                "modality_match": True,
                "source": "patent",
            })

    with args.output.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"\nextracted {len(rows)} unique-SMILES records -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
