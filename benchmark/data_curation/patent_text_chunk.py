"""Convert a patent PDF to text and chunk by "Example N" markers.

For text-extractable patents (USPTO B2/B1 grants typically are; PCT WO
applications often aren't — they're scanned to image at filing time), we
shell out to `pdftotext` (Poppler) and split on regex markers.

For image-only patents this script will report a near-zero character count
and exit non-zero so the caller knows to fall back to OCR.

Usage:
    python -m benchmark.data_curation.patent_text_chunk \\
        --pdf benchmark/data_curation/datasets/raw/patents/US10967042B2.pdf \\
        --out_dir benchmark/data_curation/datasets/raw/patents
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


EXAMPLE_RE = re.compile(r"^\s*(Example\s+\d+[a-zA-Z]?)\b", re.MULTILINE)


def pdftotext(pdf: Path) -> str:
    proc = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                          capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {proc.stderr[:200]}")
    return proc.stdout


def chunk_by_examples(text: str) -> list[tuple[str, str]]:
    """Return [(example_id, body_text), ...] for every Example N block."""
    out = []
    matches = list(EXAMPLE_RE.finditer(text))
    if not matches:
        return out
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((m.group(1), text[start:end]))
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pdf", required=True, type=Path)
    p.add_argument("--out_dir", required=True, type=Path)
    p.add_argument("--min_chars_per_page", type=float, default=200.0,
                   help="If avg chars/page below this, treat as image-only and exit 2")
    args = p.parse_args(argv)

    text = pdftotext(args.pdf)
    n_chars = len(text)
    # Cheap page-count estimate from form-feed characters
    n_pages = text.count("\f") or 1
    avg_chars = n_chars / n_pages
    print(f"  {args.pdf.name}: {n_chars:,} chars over ~{n_pages} pages "
          f"(avg {avg_chars:.1f} chars/page)")
    if avg_chars < args.min_chars_per_page:
        print(f"  WARNING: avg chars/page < {args.min_chars_per_page} "
              f"-- likely an image-based PDF; OCR required",
              file=sys.stderr)
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.pdf.stem
    full_txt = args.out_dir / f"{stem}.txt"
    full_txt.write_text(text)
    print(f"  full text -> {full_txt}")

    chunks = chunk_by_examples(text)
    if not chunks:
        print(f"  no Example markers found", file=sys.stderr)
        return 3
    chunked_dir = args.out_dir / f"{stem}_chunks"
    chunked_dir.mkdir(exist_ok=True)
    for ex_id, body in chunks:
        # Sanitize filename
        fname = re.sub(r"[^A-Za-z0-9_]", "_", ex_id) + ".txt"
        (chunked_dir / fname).write_text(body)
    print(f"  {len(chunks)} example chunks -> {chunked_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
