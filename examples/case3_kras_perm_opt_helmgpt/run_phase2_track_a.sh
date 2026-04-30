#!/bin/bash
# Phase 2 Track A: Boltz-2 affinity prediction for each top-N candidate
# (peptide as ligand SMILES) against KRAS-G12D using the pre-computed
# target.a3m to skip MMseqs2 calls.
#
# Usage:
#   bash run_phase2_track_a.sh <run_dir>
#
# Inputs:
#   <run_dir>/phase2_candidates.csv  (rank, helm_seqs, smiles, n_heavy_atoms, ...)
#   results/case3_kras_helmgpt/target.a3m
#
# Outputs (per candidate):
#   <run_dir>/phase2_track_a/c_<rank>_<smiles_hash8>/boltz_results_*/...
#   <run_dir>/phase2_track_a/track_a_results.csv (aggregate)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BOLTZ_BIN="$REPO_ROOT/tool-mcps/boltz_mcp/env/bin/boltz"
BOLTZ_CACHE="${MACROMNEX_CACHE:-$HOME/.macromnex/cache}/model/boltz"
A3M="$REPO_ROOT/results/case3_kras_helmgpt/target.a3m"

if [ -z "${1:-}" ]; then
  echo "Usage: $0 <run_dir>" >&2; exit 1
fi
RUN_DIR="$1"
CSV="$RUN_DIR/phase2_candidates.csv"
[ -f "$CSV" ] || { echo "Missing $CSV — run postprocess_phase2_prep.py first" >&2; exit 1; }
[ -f "$A3M" ] || { echo "Missing $A3M — run Step 0 first" >&2; exit 1; }

OUT="$RUN_DIR/phase2_track_a"
mkdir -p "$OUT"

# Read query sequence from the a3m (line 2)
SEQ=$(awk 'NR==2 {print; exit}' "$A3M")

# Build per-candidate yaml + run Boltz, in series (single GPU)
N=$(awk -F, 'NR>1' "$CSV" | wc -l)
echo "Track A: $N candidates"
echo "  out_root: $OUT"
echo "  msa     : $A3M"
echo

"$BOLTZ_BIN" predict --help >/dev/null 2>&1 || { echo "boltz CLI broken at $BOLTZ_BIN" >&2; exit 2; }

python3 - "$CSV" "$OUT" "$A3M" "$SEQ" "$BOLTZ_BIN" "$BOLTZ_CACHE" <<'PY'
import csv, hashlib, json, os, subprocess, sys, time
from pathlib import Path

csv_path, out_root, a3m, seq, boltz_bin, cache = sys.argv[1:7]
out_root = Path(out_root)
results = []

with open(csv_path) as f:
    rows = list(csv.DictReader(f))

print(f"Running {len(rows)} candidates with Boltz-2 affinity_prediction (msa cached)...")
t0 = time.time()
for r in rows:
    rank = int(r["rank"])
    smi  = r["smiles"]
    helm = r["helm_seqs"]
    h8 = hashlib.md5(smi.encode()).hexdigest()[:8]
    cdir = out_root / f"c_{rank:02d}_{h8}"
    cdir.mkdir(parents=True, exist_ok=True)
    yaml = cdir / "input.yaml"
    yaml.write_text(
        "version: 1\n"
        "sequences:\n"
        "  - protein:\n"
        "      id: A\n"
        f"      sequence: {seq}\n"
        f"      msa: {a3m}\n"
        "  - ligand:\n"
        "      id: B\n"
        f"      smiles: '{smi}'\n"
        "properties:\n"
        "  - affinity:\n"
        "      binder: B\n"
    )
    log = cdir / "boltz.log"
    cmd = [
        boltz_bin, "predict",
        "--out_dir", str(cdir),
        "--cache", cache,
        "--output_format", "pdb",
        "--accelerator", "gpu",
        str(yaml),
    ]
    t = time.time()
    rc = subprocess.run(cmd, stdout=open(log, "w"), stderr=subprocess.STDOUT).returncode
    elapsed = time.time() - t
    aff_json = next(cdir.glob("boltz_results_input/predictions/input/affinity_input.json"), None)
    conf_json = next(cdir.glob("boltz_results_input/predictions/input/confidence_input_model_0.json"), None)
    rec = {"rank": rank, "smiles_hash": h8, "rc": rc, "elapsed_s": round(elapsed, 1)}
    if aff_json and aff_json.exists():
        try: rec.update({f"aff_{k}": v for k, v in json.loads(aff_json.read_text()).items()})
        except Exception: pass
    if conf_json and conf_json.exists():
        try:
            d = json.loads(conf_json.read_text())
            rec.update({"conf_iptm": d.get("iptm"), "conf_complex_plddt": d.get("complex_plddt")})
        except Exception: pass
    results.append(rec)
    aff_val = rec.get("aff_affinity_pred_value", "?")
    print(f"  [{rank:02d}] rc={rc} {elapsed:5.1f}s  affinity_pred={aff_val}")

print(f"\nTotal {time.time()-t0:.1f}s")
out_csv = out_root / "track_a_results.csv"
keys = sorted({k for r in results for k in r.keys()})
with open(out_csv, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(results)
print(f"\nwrote: {out_csv}")
PY
