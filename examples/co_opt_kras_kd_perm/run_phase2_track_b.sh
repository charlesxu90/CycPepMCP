#!/bin/bash
# Phase 2 Track B: AlphaFold3 protein-ligand complex prediction for each
# top-N candidate. Uses the pre-computed target.a3m via input.json's
# msa_path field to skip the slow MSA search.
#
# Usage:
#   bash run_phase2_track_b.sh <run_dir> [device]
#
# Defaults:
#   device = 1   (use GPU 1; Track A runs on GPU 0)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AF3_PY="$REPO_ROOT/tool-mcps/alphafold3_mcp/env/bin/python"
AF3_RUNNER="$REPO_ROOT/tool-mcps/alphafold3_mcp/scripts/alphafold3_runner.py"
A3M="$REPO_ROOT/results/case3_kras_helmgpt/target.a3m"

if [ -z "${1:-}" ]; then echo "Usage: $0 <run_dir> [device]" >&2; exit 1; fi
RUN_DIR="$1"
DEVICE="${2:-1}"
CSV="$RUN_DIR/phase2_candidates.csv"
[ -f "$CSV" ] || { echo "Missing $CSV — run postprocess_phase2_prep.py first" >&2; exit 1; }
[ -f "$A3M" ] || { echo "Missing $A3M — run Step 0 first" >&2; exit 1; }
[ -x "$AF3_PY" ] || { echo "Missing AF3 env python: $AF3_PY" >&2; exit 1; }

OUT="$RUN_DIR/phase2_track_b"
mkdir -p "$OUT"

# Read query sequence from the a3m (line 2)
SEQ=$(awk 'NR==2 {print; exit}' "$A3M")

"$AF3_PY" - "$CSV" "$OUT" "$A3M" "$SEQ" "$AF3_RUNNER" "$DEVICE" <<'PY'
import csv, hashlib, json, os, subprocess, sys, time
from pathlib import Path

csv_path, out_root, a3m, seq, runner, device = sys.argv[1:7]
out_root = Path(out_root)
a3m = str(Path(a3m).resolve())
device = int(device)

with open(csv_path) as f:
    rows = list(csv.DictReader(f))

print(f"Track B: {len(rows)} candidates, AF3 on GPU {device}, msa cached")
print(f"  out_root: {out_root}")
sys.stdout.flush()

# Import runner (relative path in repo); it's importable as a module.
sys.path.insert(0, str(Path(runner).parent))
from alphafold3_runner import run_with_a3m  # noqa: E402

results = []
t0 = time.time()
for r in rows:
    rank = int(r["rank"])
    smi  = r["smiles"]
    h8   = hashlib.md5(smi.encode()).hexdigest()[:8]
    cdir = out_root / f"c_{rank:02d}_{h8}"
    cdir.mkdir(parents=True, exist_ok=True)

    inj = cdir / "input.json"
    inj.write_text(json.dumps({
        "name": f"c_{rank:02d}_{h8}",
        "sequences": [
            {"protein": {"id": ["A"], "sequence": seq, "msa_path": a3m}},
            {"ligand":  {"id": ["B"], "smiles": smi}},
        ],
        "modelSeeds": [42],
        "dialect": "alphafold3",
        "version": 1,
    }, indent=2))

    log = cdir / "af3.log"
    t = time.time()
    try:
        rc = run_with_a3m(
            data_path=str(cdir),
            device=device,
            run_template_search=False,            # speed: skip templates
            run_inference=True,
            flash_attention_implementation="triton",
        )
        ok = bool(rc) if rc is not None else True
    except Exception as e:
        log.write_text(f"exception: {e}\n")
        ok = False
    elapsed = time.time() - t

    summary = next(cdir.glob(f"c_{rank:02d}_{h8}/*summary_confidences.json"), None) \
              or next(cdir.glob("**/*summary_confidences.json"), None)
    rec = {"rank": rank, "smiles_hash": h8, "ok": ok, "elapsed_s": round(elapsed, 1)}
    if summary and summary.exists():
        try:
            d = json.loads(summary.read_text())
            for k in ("ptm", "iptm", "ranking_score", "fraction_disordered"):
                if k in d: rec[k] = d[k]
        except Exception:
            pass
    results.append(rec)
    print(f"  [{rank:02d}] ok={ok} {elapsed:5.1f}s  iptm={rec.get('iptm','?')}  ptm={rec.get('ptm','?')}")
    sys.stdout.flush()

print(f"\nTotal {time.time()-t0:.1f}s")
out_csv = out_root / "track_b_results.csv"
keys = sorted({k for r in results for k in r.keys()})
with open(out_csv, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(results)
print(f"\nwrote: {out_csv}")
PY
