#!/bin/bash
# Phase 2 Gnina: re-dock each candidate's ligand against the predicted
# receptor (extracted from the Boltz-2 complex), with autobox seeded from
# the Boltz-2 ligand pose. Produces CNN + Vina scores per candidate.
#
# Usage:
#   bash run_phase2_gnina.sh <run_dir> [device]
#
# Requires Track A complete (Boltz-2 PDBs).
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GNINA_ENV="$REPO_ROOT/tool-mcps/gnina_mcp/env"
GNINA="$GNINA_ENV/bin/gnina"
export LD_LIBRARY_PATH="$GNINA_ENV/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

if [ -z "${1:-}" ]; then echo "Usage: $0 <run_dir> [device]" >&2; exit 1; fi
RUN_DIR="$1"
DEVICE="${2:-0}"
TRACK_A="$RUN_DIR/phase2_track_a"
[ -d "$TRACK_A" ] || { echo "Missing $TRACK_A" >&2; exit 1; }

OUT="$RUN_DIR/phase2_gnina"
mkdir -p "$OUT"

CSV="$OUT/gnina_results.csv"
echo "rank,smiles_hash,rc,elapsed_s,cnn_affinity,minimized_affinity,vina_affinity" > "$CSV"

for cdir in "$TRACK_A"/c_*/; do
  pdb=$(find "$cdir/boltz_results_input/predictions/input" -name "input_model_0.pdb" | head -1)
  if [ -z "$pdb" ] || [ ! -f "$pdb" ]; then echo "skip $cdir (no PDB)"; continue; fi
  base=$(basename "$cdir")
  rank=$(echo "$base" | sed -E 's/c_0?([0-9]+)_.*/\1/')
  hash=$(echo "$base" | sed -E 's/c_[0-9]+_(.*)\//\1/; s|/$||')
  hash=${hash%/}

  cd_out="$OUT/$base"
  mkdir -p "$cd_out"

  # Split protein (chain A) and ligand (chain B / HETATM LIG) from Boltz PDB.
  # Use python+rdkit/biopython-free approach with awk to keep deps minimal.
  rec="$cd_out/receptor.pdb"
  lig="$cd_out/ligand.pdb"
  awk '/^ATOM/ && substr($0,22,1)=="A"' "$pdb" > "$rec"
  awk '/^HETATM/ && substr($0,22,1)=="B"' "$pdb" > "$lig"

  log="$cd_out/gnina.log"
  out_sdf="$cd_out/docked.sdf"

  start=$(date +%s)
  "$GNINA" \
    -r "$rec" \
    -l "$lig" \
    --autobox_ligand "$lig" \
    --num_modes 9 \
    --exhaustiveness 8 \
    --cnn_scoring rescore \
    --device "$DEVICE" \
    --out "$out_sdf" \
    > "$log" 2>&1
  rc=$?
  elapsed=$(( $(date +%s) - start ))

  cnn=$(awk '/^   1[ \t]/ {print $3; exit}' "$log")     # mode 1, CNNscore col
  vina=$(awk '/^   1[ \t]/ {print $2; exit}' "$log")    # mode 1, vina affinity (kcal/mol)
  cnnaff=$(awk '/^   1[ \t]/ {print $4; exit}' "$log")  # CNNaffinity
  echo "$rank,$hash,$rc,$elapsed,$cnnaff,$vina,$cnn" | tee -a "$CSV"
done

echo
echo "wrote: $CSV"
