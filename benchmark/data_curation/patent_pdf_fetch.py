"""Download patent PDFs from Google Patents.

For each patent ID (e.g. WO2014151634A1), scrape the Google Patents page for
the embedded PDF URL on patentimages.storage.googleapis.com, then download to
`benchmark/data_curation/datasets/raw/patents/<id>.pdf`.

Usage:
    python -m benchmark.data_curation.patent_pdf_fetch \\
        --patent_ids WO2014151634A1 WO2016039749A1 \\
        --out_dir benchmark/data_curation/datasets/raw/patents
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import requests

GOOGLE_PATENT_URL = "https://patents.google.com/patent/{pid}/en"
USER_AGENT = "Mozilla/5.0"


def resolve_pdf_url(patent_id: str, timeout: int = 30) -> str | None:
    r = requests.get(GOOGLE_PATENT_URL.format(pid=patent_id),
                     headers={"User-Agent": USER_AGENT}, timeout=timeout)
    if r.status_code != 200:
        return None
    m = re.search(r'href=["\']([^"\'>]+\.pdf)["\']', r.text)
    return m.group(1) if m else None


def download_pdf(url: str, dest: Path, timeout: int = 120) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout, stream=True)
    r.raise_for_status()
    n = 0
    with dest.open("wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)
            n += len(chunk)
    return n


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--patent_ids", nargs="+", required=True)
    p.add_argument("--out_dir", required=True, type=Path)
    args = p.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    rc = 0
    for pid in args.patent_ids:
        dest = args.out_dir / f"{pid}.pdf"
        if dest.is_file() and dest.stat().st_size > 100_000:
            print(f"  {pid}: already cached ({dest.stat().st_size} bytes)")
            continue
        url = resolve_pdf_url(pid)
        if not url:
            print(f"  {pid}: no PDF URL found on Google Patents", file=sys.stderr)
            rc = 1
            continue
        try:
            n = download_pdf(url, dest)
            print(f"  {pid}: {n:,} bytes -> {dest}")
        except Exception as e:
            print(f"  {pid}: download failed: {e}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
