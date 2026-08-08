"""Extract peptide-activity tables from a PMC paper via the EUtils efetch API.

Per-paper extraction rules are encoded inline (in `EXTRACTORS` below) rather
than YAML — each paper has its own quirks (column names, modifications,
cyclization conventions) that are simpler to express in code.

After extraction:
  - sequences → canonical SMILES via `peptide_to_smiles.seq_to_smiles`
  - rows written to `<output>` in the canonical raw schema (matches
    chembl_query.py / bindingdb_query.py / pubchem_query.py output)
  - run `peptide_filter.py` afterwards to drop anything that didn't yield a
    plausible peptide SMILES (e.g. structures-as-figures, parser errors).

Currently supported PMCs:
  - PMC2856455 — Systematic Mutational Analysis (PMI + p53(17-28) → MDM2/MDMX)
  - PMC3359147 — D-PMI left-handed solution (D-peptide MDM2 binders)
  - PMC10671706 — Cyclic Peptide Inhibitors Targeting PD-L1 (CLP-2 cyclic analogs)

Usage:
    python -m benchmark.data_curation.pmc_paper_extract \\
        --pmcid PMC2856455 \\
        --output benchmark/data_curation/datasets/raw/mdm2_p53_pmc_PMC2856455.csv
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from benchmark.data_curation.peptide_to_smiles import seq_to_smiles


COLS = [
    "target_name", "target_chembl_id", "molecule_chembl_id",
    "molecule_pref_name", "canonical_smiles", "standard_type",
    "standard_value", "standard_units", "assay_type",
    "assay_description", "document_chembl_id", "modality_match", "source",
]


def fetch_pmc_xml(pmcid: str, timeout: int = 60) -> ET.Element:
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    r = requests.get(url, params={"db": "pmc", "id": pmcid, "rettype": "xml"},
                     timeout=timeout)
    r.raise_for_status()
    return ET.fromstring(r.text)


def _cells_in_table(tw: ET.Element) -> list[list[str]]:
    """Return one [cell-text, ...] list per <tr> row."""
    rows: list[list[str]] = []
    for tr in tw.iter("tr"):
        row = []
        for cell in tr:
            if cell.tag in ("td", "th"):
                row.append(" ".join(cell.itertext()).strip())
        rows.append(row)
    return rows


# ----------------------------------------------------------------------
# Per-paper extractors. Each returns a list of canonical-schema dicts.
# ----------------------------------------------------------------------

def extract_pmc2856455(root: ET.Element, pmcid: str) -> list[dict]:
    """Systematic Mutational Analysis (Liu/Lu/Pazgier 2010).
    Tables 1 and 3 carry the (sequence, Kd-MDM2, Kd-MDMX) records.

    Each data row layout (18 cells):
       [c0, c1, ..., c11, kd_mdm2_M, ratio_mdm2, ddG_mdm2, kd_mdmx_M, ratio_mdmx, ddG_mdmx]
    where c0..c11 are single-letter residue strings forming the 12-mer sequence.
    Kd values are in scientific notation in Molar (e.g. "3.1×10^-8").
    """
    out: list[dict] = []
    tables = list(root.iter("table-wrap"))
    for tw_idx, tw in enumerate(tables):
        caption = tw.find(".//caption")
        cap_text = " ".join(caption.itertext()).strip() if caption is not None else ""
        # Match "Kd" with or without whitespace from subscript markup
        if not (re.search(r"K\s*d", cap_text) and "MDM" in cap_text):
            continue
        rows = _cells_in_table(tw)
        if not rows or len(rows) < 4:
            continue

        # Detect peptide-length sub-table: data rows are wide (~18 cells)
        # and start with single-letter cells. Find the modal peptide length.
        data_rows = [r for r in rows if len(r) >= 14
                     and all(len(c.strip()) == 1 and c.strip().isalpha() for c in r[:6])]
        if not data_rows:
            continue
        # All sequences in the table share a length; infer it by counting
        # consecutive 1-letter cells at the start of the first data row.
        first = data_rows[0]
        seq_len = 0
        for c in first:
            if len(c.strip()) == 1 and c.strip().isalpha():
                seq_len += 1
            else:
                break
        if not (6 <= seq_len <= 20):
            continue

        # Decide whether this table is the "P53-..." (table 3) or "PMI-..." (table 1)
        # by reading row[0] (header row); the column names follow "PMI-MDM2"/"P53-MDM2".
        is_p53 = "P53" in (" ".join(rows[0])).upper()

        for r in data_rows:
            if len(r) < seq_len + 6:
                continue
            seq = "".join(c.strip() for c in r[:seq_len]).upper()
            if not (6 <= len(seq) <= 20) or not seq.isalpha():
                continue
            # Extract the two Kd values (in Molar) — first numeric cell in each block
            kd_mdm2_cell = r[seq_len]
            kd_mdmx_cell = r[seq_len + 3] if len(r) > seq_len + 3 else ""

            for cell, side in [(kd_mdm2_cell, "primary"), (kd_mdmx_cell, "mdmx")]:
                if not cell.strip():
                    continue
                # Parse "3.1 × 10−8" / "3.1×10^-8" / "3.1E-8" / "3.1e-8"
                # Strip spaces and unicode minus / multiplication signs
                clean = (cell.replace("×", "x")
                              .replace("−", "-").replace("−", "-")
                              .replace("\xa0", " ").strip())
                m = re.search(
                    r"([0-9]+\.?[0-9]*)\s*(?:[xX]\s*10\s*[\^]?\s*|[eE])\s*(-?[0-9]+)",
                    clean)
                if m:
                    try:
                        val_M = float(m.group(1)) * (10 ** int(m.group(2)))
                    except ValueError:
                        continue
                else:
                    # Maybe plain decimal in Molar
                    m2 = re.match(r"\s*([0-9]+\.?[0-9]*(?:[eE]-?\d+)?)", clean)
                    if not m2:
                        continue
                    try:
                        val_M = float(m2.group(1))
                    except ValueError:
                        continue
                val_nm = val_M * 1e9  # M → nM
                if val_nm <= 0 or val_nm > 1e9:
                    continue

                smi = seq_to_smiles(seq)
                if not smi:
                    continue
                out.append({
                    "target_name": "MDM2" if side == "primary" else "MDMX",
                    "target_chembl_id": "Q00987" if side == "primary" else "O15151",
                    "molecule_chembl_id": f"PMC2856455:T{tw_idx}:{seq}",
                    "molecule_pref_name": seq,
                    "canonical_smiles": smi,
                    "standard_type": "Kd",
                    "standard_value": f"{val_nm:.4g}",
                    "standard_units": "nM",
                    "assay_type": "FP" if not is_p53 else "FP",
                    "assay_description": cap_text[:200],
                    "document_chembl_id": f"PMC:{pmcid}",
                    "modality_match": True,
                    "source": "pmc",
                })
    return out


def extract_pmc3359147(root: ET.Element, pmcid: str) -> list[dict]:
    """D-PMI left-handed solution paper. The table has 4 columns:
       [Name, Sequence, Kd ± SD (nM), ΔΔG (kcal/mol)]
    The 'Name' tells us the chirality: "D PMI-α" / "D PMI-β" → all-D peptide;
    "PMI" / "17-28 p53" → all-L. Mutants like "N2A-D PMI-α" keep all-D."""
    out: list[dict] = []
    for tw in root.iter("table-wrap"):
        caption = tw.find(".//caption")
        cap_text = " ".join(caption.itertext()).strip() if caption is not None else ""
        if not re.search(r"K\s*d", cap_text):
            continue
        rows = _cells_in_table(tw)
        if not rows:
            continue
        # Header row should look like Name | Sequence | Kd ± SD | ΔΔG
        header = None
        header_idx = 0
        for i, r in enumerate(rows):
            joined = " | ".join(r).lower()
            if "sequence" in joined and ("k" in joined and "d" in joined):
                header = r; header_idx = i; break
        if not header:
            continue
        try:
            name_col = 0
            seq_col = next(i for i, c in enumerate(header) if "sequence" in c.lower())
            kd_col = next(i for i, c in enumerate(header) if re.search(r"K\s*d", c))
        except StopIteration:
            continue

        for r in rows[header_idx + 1:]:
            if len(r) <= max(seq_col, kd_col):
                continue
            name = r[name_col].strip()
            seq = re.sub(r"[^A-Za-z]", "", r[seq_col]).upper()
            if not (6 <= len(seq) <= 20):
                continue
            kd_cell = r[kd_col].strip()
            # Pull number + unit; unit may follow the ± part
            m = re.match(r"\s*([0-9]+\.?[0-9]*)\s*(?:[*])?\s*(?:±\s*[0-9.]+)?\s*(nM|µM|μM|uM)?",
                         kd_cell)
            if not m:
                continue
            try:
                val = float(m.group(1))
            except ValueError:
                continue
            unit = (m.group(2) or "nM").replace("µ", "u").replace("μ", "u")
            if unit.lower() == "um":
                val *= 1000
            # Decide chirality from name
            is_d = bool(re.search(r"\bD\b|\bD\s*PMI", name))
            d_positions = set(range(len(seq))) if is_d else set()
            smi = seq_to_smiles(seq, d_positions=d_positions)
            if not smi:
                continue
            out.append({
                "target_name": "MDM2",
                "target_chembl_id": "Q00987",
                "molecule_chembl_id": f"PMC3359147:{name}",
                "molecule_pref_name": name,
                "canonical_smiles": smi,
                "standard_type": "Kd",
                "standard_value": f"{val:.4g}",
                "standard_units": "nM",
                "assay_type": "FP",
                "assay_description": cap_text[:200],
                "document_chembl_id": f"PMC:{pmcid}",
                "modality_match": True,
                "source": "pmc",
            })
    return out


def extract_pmc10671706(root: ET.Element, pmcid: str) -> list[dict]:
    """Cyclic Peptide Inhibitors Targeting PD-L1 (J Med Chem 2022).
    Tables are in supplementary materials; the main XML body has activity
    snippets but limited structured tables. We scan the body for sequence/
    IC50 patterns and the supplementary tags."""
    out: list[dict] = []
    # The CLP-2 series uses sequence patterns like "C1-C22" with a parent.
    # Scan inline text for patterns like "C7 ... IC50 = 138 nM"
    body_text = " ".join(t for t in root.itertext())
    # Look for "C<n> ... <number> nM" patterns
    matches = re.findall(
        r"\b(C\d{1,2})\b[^.]{0,200}?(?:IC50|IC\s*50)[^.]{0,40}?([0-9]+\.?[0-9]*)\s*(nM|µM|μM|uM)\b",
        body_text)
    seen_id: set[str] = set()
    for compound_id, val_str, unit in matches:
        if compound_id in seen_id:
            continue
        seen_id.add(compound_id)
        val = float(val_str)
        u = unit.replace("µ", "u").replace("μ", "u").lower()
        if u == "um": val *= 1000
        out.append({
            "target_name": "PD-L1",
            "target_chembl_id": "Q9NZQ7",
            "molecule_chembl_id": f"PMC10671706:{compound_id}",
            "molecule_pref_name": compound_id,
            "canonical_smiles": "",  # SMILES not derivable without structure;
                                       # downstream filter will drop these unless
                                       # the supplementary provides the structure
            "standard_type": "IC50",
            "standard_value": f"{val}",
            "standard_units": "nM",
            "assay_type": "HTRF",
            "assay_description": f"PD-1/PD-L1 blocking; compound {compound_id} from CLP-2 series",
            "document_chembl_id": f"PMC:{pmcid}",
            "modality_match": True,
            "source": "pmc",
        })
    return out


EXTRACTORS = {
    "PMC2856455":  extract_pmc2856455,
    "PMC3359147":  extract_pmc3359147,
    "PMC10671706": extract_pmc10671706,
}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pmcid", required=True, help="PMC identifier (e.g. PMC2856455)")
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args(argv)

    extractor = EXTRACTORS.get(args.pmcid)
    if extractor is None:
        print(f"error: no extractor registered for {args.pmcid}; "
              f"available: {list(EXTRACTORS)}", file=sys.stderr)
        return 1

    print(f"  fetching {args.pmcid} ...", file=sys.stderr)
    root = fetch_pmc_xml(args.pmcid)
    rows = extractor(root, args.pmcid)
    # Drop rows without SMILES (they won't pass the peptide filter anyway)
    rows_with_smiles = [r for r in rows if r["canonical_smiles"]]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows_with_smiles)
    print(f"extracted={len(rows)}  with_smiles={len(rows_with_smiles)} -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
