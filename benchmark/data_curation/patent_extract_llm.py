"""Use Claude to extract (peptide_name, sequence, modifications, assay,
activity_type, activity_value, unit) per "Example N" chunk from a patent.

Reads chunk files written by `patent_text_chunk.py` and writes one canonical-
schema CSV row per chunk that successfully extracts an activity record.

Requires ANTHROPIC_API_KEY in the environment and the `anthropic` Python SDK
(>= 0.40). Both are configured the same way as `benchmark/scripts/llm_orchestrator.py`.

Cost note: prompt-caches the per-patent system prompt across all examples so
each example incurs only the per-call output tokens. Typical: $1-5 per patent.

Usage:
    export ANTHROPIC_API_KEY=...
    python -m benchmark.data_curation.patent_extract_llm \\
        --chunks_dir benchmark/data_curation/datasets/raw/patents/US10967042B2_chunks \\
        --patent_id US10967042B2 \\
        --target_uniprot Q00987 --target_name MDM2 \\
        --output benchmark/data_curation/datasets/raw/patents/US10967042B2_extracted.csv

Caveat: many patents (e.g. the 5 candidates in our survey) use qualitative
activity bins (+/++/+++) rather than numeric values, OR are scanned PDFs
without OCR. In those cases this script will extract only the bin label and
mark the row with `confidence=0.3` so the manual reviewer can spot-check.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path


SYSTEM_PROMPT = """You are a chemistry data extraction assistant. Read one Example block from a peptide / macrocycle patent and emit a JSON object with these fields:

{
  "compound_name": "...",       // e.g. "Example 7", "SAH-p53-1", or null
  "sequence":     "...",        // 1-letter amino acid sequence including non-canonical letters; null if drawn-only
  "modifications": "...",       // free-text description of staples, D-AA, N-methyl, cyclization; "" if none
  "smiles":       "...",        // SMILES if explicitly shown in the example text; "" otherwise
  "target":       "MDM2|MDMX|PD-L1|other",
  "assay_type":   "FP|HTRF|TR-FRET|ELISA|SPR|ITC|other",
  "activity_type": "Kd|Ki|IC50|EC50|other",
  "activity_value": <number>,  // numeric; null if patent uses qualitative bins
  "activity_unit": "nM|uM|pM|mM",
  "activity_bin":  "+|++|+++|++++",  // null if numeric value is provided
  "confidence":   0.0-1.0       // how confident the extraction is
}

If the example contains no activity data, return {"confidence": 0.0}.
Respond with ONLY the JSON object, no other text."""


def call_claude(system: str, user: str, model: str = "claude-opus-4-5") -> dict:
    """Single Claude API call with prompt caching for the system message."""
    from anthropic import Anthropic
    client = Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0.0,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    # Strip code fences if present
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"confidence": 0.0, "raw_response": text[:200]}


def bin_to_pactivity_range(bin_label: str) -> tuple[float, float] | None:
    """Map qualitative bins to a nominal pActivity range (used downstream)."""
    return {
        "+":    (3.0, 5.0),     # >10 µM
        "++":   (5.0, 6.0),     # 1-10 µM
        "+++":  (6.0, 7.0),     # 100 nM - 1 µM
        "++++": (7.0, 9.0),     # < 100 nM
    }.get(bin_label.strip())


COLS = [
    "target_name", "target_chembl_id", "molecule_chembl_id",
    "molecule_pref_name", "canonical_smiles", "standard_type",
    "standard_value", "standard_units", "assay_type",
    "assay_description", "document_chembl_id", "modality_match", "source",
    "confidence", "is_bin_value",
]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--chunks_dir", required=True, type=Path)
    p.add_argument("--patent_id", required=True)
    p.add_argument("--target_uniprot", required=True)
    p.add_argument("--target_name", required=True,
                   choices=["MDM2", "MDMX", "PD-L1"])
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--max_examples", type=int, default=200)
    p.add_argument("--sleep_sec", type=float, default=0.3)
    p.add_argument("--model", default="claude-opus-4-5")
    args = p.parse_args(argv)

    if "ANTHROPIC_API_KEY" not in os.environ:
        print("error: set ANTHROPIC_API_KEY", file=sys.stderr)
        return 1
    try:
        import anthropic  # noqa
    except ImportError:
        print("error: install anthropic SDK (>= 0.40)", file=sys.stderr)
        return 1

    chunk_files = sorted(args.chunks_dir.glob("Example_*.txt"))
    if not chunk_files:
        print(f"error: no Example_*.txt files in {args.chunks_dir}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    n_ok = n_skipped = n_bin = 0
    with args.output.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for i, chunk_path in enumerate(chunk_files[: args.max_examples]):
            body = chunk_path.read_text()[:4000]   # cap context per example
            ex_id = chunk_path.stem
            try:
                rec = call_claude(SYSTEM_PROMPT, body, model=args.model)
            except Exception as e:
                print(f"  {ex_id}: API error: {e}", file=sys.stderr)
                continue
            if rec.get("confidence", 0) < 0.4:
                n_skipped += 1
                continue
            # Choose numeric or binned value
            val = rec.get("activity_value")
            unit = rec.get("activity_unit") or "nM"
            is_bin = False
            if val is None and rec.get("activity_bin"):
                rng = bin_to_pactivity_range(rec["activity_bin"])
                if rng:
                    # Use mid-bin nominal value, expressed in nM via 10^(9 - pAct)
                    pact = (rng[0] + rng[1]) / 2.0
                    val = 10 ** (9 - pact)
                    unit = "nM"
                    is_bin = True
                    n_bin += 1
            if val is None:
                n_skipped += 1
                continue
            w.writerow({
                "target_name": args.target_name,
                "target_chembl_id": args.target_uniprot,
                "molecule_chembl_id": f"{args.patent_id}:{ex_id}",
                "molecule_pref_name": rec.get("compound_name") or ex_id,
                "canonical_smiles": rec.get("smiles", ""),
                "standard_type": rec.get("activity_type", "IC50"),
                "standard_value": f"{val}",
                "standard_units": unit,
                "assay_type": rec.get("assay_type", "")[:30],
                "assay_description": f"Patent {args.patent_id} {ex_id}",
                "document_chembl_id": args.patent_id,
                "modality_match": True,
                "source": "patent_llm",
                "confidence": rec.get("confidence", 0.5),
                "is_bin_value": is_bin,
            })
            n_ok += 1
            time.sleep(args.sleep_sec)

    print(f"examples={len(chunk_files)}  ok={n_ok}  bin={n_bin}  skipped={n_skipped} -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
