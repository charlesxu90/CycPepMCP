"""Pre-stage every target PDB into `benchmark/data/pdbs/` so HPC compute nodes
(iBex / Shaheen) — which usually have no internet — can run the benchmark
without hitting the AfCycDesign `--pdb_code` auto-download fallback.

Run on the login node (where internet is available) BEFORE submitting jobs:

    python -m benchmark.scripts.stage_pdbs

What it does:
  1. Reads `benchmark/configs/targets.csv`.
  2. For every row whose `target_pdb` is a 4-letter PDB code (e.g. `1G5J.pdb`)
     OR a path under `benchmark/data/pdbs/` that doesn't yet exist on disk,
     downloads the structure from RCSB.
  3. Verifies the chain ID listed in `target_chain` is actually present.
  4. Reports a summary; exits non-zero if anything is missing/unverifiable.

Idempotent — running twice is a no-op when files already exist.
"""
from __future__ import annotations

import argparse
import csv
import sys
import urllib.request
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / "benchmark" / "configs" / "thresholds.py").is_file():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break

from benchmark.scripts.workflow_runners.base import find_project_root


def _is_pdb_code(stem: str) -> bool:
    return len(stem) == 4 and stem.isalnum()


def _extract_pdb_code(stem: str) -> Optional[str]:
    """Extract a 4-letter PDB code from `stem`. Handles both bare codes ('1G5J')
    and `XXXX_PROTEIN` naming ('1G5J_BCLxL'). Returns None if neither pattern matches.
    """
    if _is_pdb_code(stem):
        return stem.upper()
    # `XXXX_*` pattern
    if "_" in stem:
        head = stem.split("_", 1)[0]
        if _is_pdb_code(head):
            return head.upper()
    return None


def _download_pdb(pdb_id: str, dest: Path) -> None:
    url = f"https://files.rcsb.org/download/{pdb_id.upper()}.pdb"
    print(f"  downloading {url}", flush=True)
    with urllib.request.urlopen(url, timeout=30) as r, dest.open("wb") as f:
        f.write(r.read())


def _verify_chain(pdb_path: Path, chain: str) -> bool:
    """Return True if `chain` appears in any ATOM record of `pdb_path`."""
    if not pdb_path.is_file() or not chain:
        return False
    for line in pdb_path.read_text().splitlines():
        if line.startswith("ATOM") and len(line) > 22 and line[21:22] == chain:
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--targets-csv", default=None, type=Path)
    p.add_argument("--out-dir", default=None, type=Path,
                   help="Where to put downloaded PDBs (default: benchmark/data/pdbs/)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    root = find_project_root()
    targets_csv = args.targets_csv or root / "benchmark" / "configs" / "targets.csv"
    out_dir = args.out_dir or root / "benchmark" / "data" / "pdbs"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = list(csv.DictReader(targets_csv.open()))
    n_ok = n_downloaded = n_chain_fail = n_skip = 0
    missing = []

    for r in rows:
        target_pdb = r["target_pdb"].strip()
        chain = r["target_chain"].strip()
        if not target_pdb or r["workflow"].strip() == "helmgpt":
            n_skip += 1   # HELM-GPT targets don't have a structural PDB
            continue
        # Resolve the local path the runner will read.
        local_path = root / target_pdb
        if local_path.is_file():
            if _verify_chain(local_path, chain):
                print(f"  OK     {r['task_id']:12s}  {local_path.relative_to(root)}  chain={chain}")
                n_ok += 1
            else:
                print(f"  CHAIN  {r['task_id']:12s}  {local_path.relative_to(root)}  "
                      f"chain {chain!r} not in PDB", file=sys.stderr)
                n_chain_fail += 1
                missing.append(r["task_id"])
            continue

        # Local file missing — try to extract a 4-letter PDB code from the filename
        # (handles both bare '1G5J.pdb' and protein-named '1G5J_BCLxL.pdb' forms).
        stem = Path(target_pdb).stem
        pdb_code = _extract_pdb_code(stem)
        if not pdb_code:
            print(f"  MISS   {r['task_id']:12s}  {target_pdb} -- no 4-letter PDB code in filename",
                  file=sys.stderr)
            n_chain_fail += 1
            missing.append(r["task_id"])
            continue

        # Download directly to the path targets.csv specifies (so the runner's
        # path resolution succeeds without further moves).
        dest = local_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        if args.dry_run:
            print(f"  DRY    {r['task_id']:12s}  would download {pdb_code} -> {dest}")
            continue
        try:
            _download_pdb(pdb_code, dest)
        except Exception as e:
            print(f"  FAIL   {r['task_id']:12s}  download failed: {e}", file=sys.stderr)
            missing.append(r["task_id"])
            continue
        if _verify_chain(dest, chain):
            n_downloaded += 1
            print(f"  DL OK  {r['task_id']:12s}  {dest.relative_to(root)}  chain={chain}")
        else:
            print(f"  CHAIN  {r['task_id']:12s}  downloaded {dest} but chain {chain!r} absent",
                  file=sys.stderr)
            missing.append(r["task_id"])
            n_chain_fail += 1

    print()
    print(f"summary: ok={n_ok}  downloaded={n_downloaded}  helmgpt_skip={n_skip}  "
          f"failed={n_chain_fail + (len(missing) - n_chain_fail)}")
    if missing:
        print(f"missing/unverifiable: {missing}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
