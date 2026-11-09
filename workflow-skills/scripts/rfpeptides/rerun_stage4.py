#!/usr/bin/env python3
"""
Script: rerun_stage4.py
Description: Re-run RFpeptides Stage 4 (Rosetta interface metrics) with PyRosetta.

The original production Stage 4 fell back to a synthetic metric generator because
PyRosetta failed to import, and the pipeline only checked the return code. This
driver recomputes ddG / SAP / CMS for real, over several RNG seeds, and writes a
new summary alongside the originals without overwriting them.

Stages 1-3 (sequence design, AlphaFold reprediction) are untouched; their iPAE and
pLDDT values are carried through from the existing final_summary.csv.

Usage:
    python rerun_stage4.py --results-root <dir> [--targets mdm2 mcl1 ...]
                           [--seeds 1 2 3] [--workers 48] [--chunk-size 25]
                           [--limit N] [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import statistics
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
METRICS_SCRIPT = SCRIPT_DIR / "interface_metrics.py"
XML_FILE = SCRIPT_DIR / "rosetta_interface_metrics.xml"

# PyRosetta lives in the rosetta_kic_mcp environment.
DEFAULT_PYTHON = (
    "/home/xux/Desktop/AgentMCP/CycPepMCP/tool-mcps/rosetta_kic_mcp/env/bin/python"
)
DEFAULT_TARGETS = ("mdm2", "mcl1", "pdl1", "gabarap")
PEPTIDE_CHAIN = "A"  # RFpeptides convention: binder = chain A, target = chain B
OUTPUT_DIRNAME = "stage4_pyrosetta"
SUMMARY_NAME = "final_summary_pyrosetta.csv"


@dataclass(frozen=True)
class Chunk:
    """One worker unit: a slice of structures evaluated under a single seed."""

    target: str
    seed: int
    index: int
    pdbs: tuple[str, ...]
    out_dir: Path
    python: str


def chunked(items: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def run_chunk(chunk: Chunk) -> tuple[Chunk, int, str]:
    """Invoke interface_metrics.py for one chunk. Returns (chunk, returncode, stderr)."""
    chunk.out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        chunk.python,
        str(METRICS_SCRIPT),
        "--input",
        *chunk.pdbs,
        "--output",
        str(chunk.out_dir),
        "--peptide_chain",
        PEPTIDE_CHAIN,
        "--xml",
        str(XML_FILE),
        "--seed",
        str(chunk.seed),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10800)
    return chunk, proc.returncode, proc.stderr[-2000:]


def collect_structures(run_dir: Path, limit: int | None) -> list[str]:
    pdbs = sorted(str(p) for p in (run_dir / "stage2").glob("*_final.pdb"))
    return pdbs[:limit] if limit else pdbs


def read_chunk_rows(out_dir: Path) -> list[dict]:
    csv_path = out_dir / "interface_metrics.csv"
    if not csv_path.exists():
        return []
    with open(csv_path) as f:
        return list(csv.DictReader(f))


def aggregate_target(target_root: Path, seeds: list[int], n_chunks: int) -> dict[str, dict]:
    """Collect per-seed rows and reduce to mean/SD per design."""
    per_design: dict[str, dict[str, list[float]]] = {}
    for seed in seeds:
        for idx in range(n_chunks):
            for row in read_chunk_rows(target_root / f"seed{seed}" / f"chunk{idx:04d}"):
                if row.get("source") != "pyrosetta":
                    raise RuntimeError(
                        f"Non-PyRosetta row in {target_root} seed{seed} chunk{idx}: "
                        f"source={row.get('source')!r}"
                    )
                name = row["name"]
                acc = per_design.setdefault(name, {"ddg": [], "sap": [], "cms": []})
                for key in ("ddg", "sap", "cms"):
                    acc[key].append(float(row[key]))

    out: dict[str, dict] = {}
    for name, acc in per_design.items():
        entry: dict[str, object] = {"n_replicates": len(acc["ddg"])}
        for key, values in acc.items():
            entry[f"{key}_mean"] = round(statistics.mean(values), 2)
            entry[f"{key}_sd"] = round(
                statistics.stdev(values) if len(values) > 1 else 0.0, 2
            )
        out[name] = entry
    return out


def write_summary(run_dir: Path, agg: dict[str, dict]) -> Path:
    """Join recomputed metrics onto the authentic iPAE/pLDDT columns."""
    src = run_dir / "final_summary.csv"
    with open(src) as f:
        rows = list(csv.DictReader(f))

    keep = ["design_id", "sequence", "length", "iPAE", "pLDDT", "structure"]
    new_cols = [
        "ddg_mean", "ddg_sd", "sap_mean", "sap_sd", "cms_mean", "cms_sd",
        "n_replicates", "metrics_source",
    ]

    out_path = run_dir / SUMMARY_NAME
    missing = 0
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keep + new_cols)
        writer.writeheader()
        for row in rows:
            rec = {k: row.get(k, "") for k in keep}
            metrics = agg.get(f"{row['design_id']}_final") or agg.get(row["design_id"])
            if metrics is None:
                missing += 1
                rec.update({c: "" for c in new_cols})
                rec["metrics_source"] = "MISSING"
            else:
                rec.update({k: metrics[k] for k in new_cols if k in metrics})
                rec["metrics_source"] = "pyrosetta"
            writer.writerow(rec)

    if missing:
        print(f"  WARNING: {missing}/{len(rows)} designs had no recomputed metrics")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results-root", required=True,
                    help="Directory holding prod/<target>/run/ (rfpeptides_out)")
    ap.add_argument("--targets", nargs="+", default=list(DEFAULT_TARGETS))
    ap.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    ap.add_argument("--workers", type=int, default=48)
    ap.add_argument("--chunk-size", type=int, default=25)
    ap.add_argument("--limit", type=int, help="Only the first N structures per target (smoke test)")
    ap.add_argument("--python", default=DEFAULT_PYTHON, help="Interpreter with PyRosetta")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not METRICS_SCRIPT.exists():
        print(f"ERROR: {METRICS_SCRIPT} not found", file=sys.stderr)
        return 1

    # Fail before launching hundreds of workers if the interpreter lacks PyRosetta.
    probe = subprocess.run([args.python, "-c", "import pyrosetta"],
                           capture_output=True, text=True)
    if probe.returncode != 0:
        print(f"ERROR: no PyRosetta in {args.python}\n{probe.stderr[-500:]}", file=sys.stderr)
        return 1

    root = Path(args.results_root).resolve()
    chunks: list[Chunk] = []
    plan: dict[str, int] = {}

    for target in args.targets:
        run_dir = root / "prod" / target / "run"
        if not run_dir.is_dir():
            print(f"ERROR: {run_dir} not found", file=sys.stderr)
            return 1
        pdbs = collect_structures(run_dir, args.limit)
        if not pdbs:
            print(f"ERROR: no *_final.pdb under {run_dir}/stage2", file=sys.stderr)
            return 1
        groups = list(chunked(pdbs, args.chunk_size))
        plan[target] = len(groups)
        for seed in args.seeds:
            for idx, group in enumerate(groups):
                chunks.append(Chunk(
                    target=target, seed=seed, index=idx, pdbs=tuple(group),
                    out_dir=run_dir / OUTPUT_DIRNAME / f"seed{seed}" / f"chunk{idx:04d}",
                    python=args.python,
                ))

    total_evals = sum(len(c.pdbs) for c in chunks)
    print(f"Targets      : {', '.join(args.targets)}")
    print(f"Seeds        : {args.seeds}")
    print(f"Chunks       : {len(chunks)} (size {args.chunk_size})")
    print(f"Evaluations  : {total_evals}")
    print(f"Workers      : {args.workers}")
    print(f"Est. wall    : ~{total_evals * 7.9 / args.workers / 60:.0f} min")
    if args.dry_run:
        print("(dry run - nothing executed)")
        return 0

    failures: list[tuple[Chunk, str]] = []
    done = 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_chunk, c): c for c in chunks}
        for fut in as_completed(futures):
            chunk, rc, err = fut.result()
            done += 1
            if rc != 0:
                failures.append((chunk, err))
                print(f"[{done}/{len(chunks)}] FAIL {chunk.target} seed{chunk.seed} "
                      f"chunk{chunk.index:04d}: {err.strip()[-200:]}")
            elif done % 10 == 0 or done == len(chunks):
                print(f"[{done}/{len(chunks)}] ok")

    if failures:
        print(f"\n{len(failures)} chunk(s) failed - summaries NOT written.", file=sys.stderr)
        return 1

    print("\nAggregating...")
    for target in args.targets:
        run_dir = root / "prod" / target / "run"
        agg = aggregate_target(run_dir / OUTPUT_DIRNAME, args.seeds, plan[target])
        out = write_summary(run_dir, agg)
        ddgs = [v["ddg_mean"] for v in agg.values()]
        sds = [v["ddg_sd"] for v in agg.values()]
        print(f"  {target:9s} n={len(agg):4d}  ddG median={statistics.median(ddgs):7.2f}  "
              f"median SD={statistics.median(sds):5.2f}  -> {out.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
