#!/bin/bash
# Step 0: Generate the target's pre-computed MSA (.a3m) via Boltz-2 + MMseqs2
# (ColabFold api.colabfold.com). Reused by all Phase-2 Boltz-2 / AF3 calls so
# they skip the slow MSA search step.
#
# Usage:
#   bash run_target_msa.sh [target.fasta] [output_dir]
#
# Defaults:
#   target.fasta  -> ./target.fasta (case3 ships KRAS-G12D 1-165)
#   output_dir    -> ../../results/case3_kras_helpgpt
#
# Produces:
#   <output_dir>/target.a3m              ← canonical handle for Phase 2
#   <output_dir>/target_msa_run/...       ← raw Boltz output tree (MSA + structure)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

FASTA="${1:-$SCRIPT_DIR/target.fasta}"
OUT_DIR="${2:-$REPO_ROOT/results/case3_kras_helpgpt}"

BOLTZ_BIN="$REPO_ROOT/tool-mcps/boltz_mcp/env/bin/boltz"
BOLTZ_CACHE="${MACROMNEX_CACHE:-$HOME/.macromnex/cache}/model/boltz"

if [ ! -x "$BOLTZ_BIN" ]; then
  echo "Error: $BOLTZ_BIN not found. Run boltz_mcp's quick_setup.sh or use the Docker image." >&2
  exit 1
fi
if [ ! -f "$FASTA" ]; then
  echo "Error: target FASTA not found: $FASTA" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
SEQ=$(awk '!/^>/{printf "%s", $0}' "$FASTA")
NAME=$(awk '/^>/{sub(/^>/,""); split($0,a,"|"); print a[1]; exit}' "$FASTA")
[ -z "$NAME" ] && NAME="target"

YAML="$OUT_DIR/${NAME}_input.yaml"
RUN_SUBDIR="$OUT_DIR/target_msa_run"
LOG="$OUT_DIR/target_msa_run.log"

cat > "$YAML" <<EOF
version: 1
sequences:
  - protein:
      id: A
      sequence: $SEQ
EOF

echo "Running Boltz-2 (MSA server enabled) for target $NAME (length $(echo -n "$SEQ" | wc -c))..."
echo "  fasta : $FASTA"
echo "  yaml  : $YAML"
echo "  out   : $RUN_SUBDIR"
echo "  log   : $LOG"
mkdir -p "$RUN_SUBDIR"

"$BOLTZ_BIN" predict \
  --out_dir "$RUN_SUBDIR" \
  --cache "$BOLTZ_CACHE" \
  --use_msa_server \
  --output_format pdb \
  --accelerator gpu \
  "$YAML" >"$LOG" 2>&1

YAML_BASE="$(basename "$YAML" .yaml)"
A3M_SRC=$(find "$RUN_SUBDIR/boltz_results_${YAML_BASE}/msa" -name 'bfd.mgnify30.metaeuk30.smag30.a3m' | head -n1)
if [ -z "$A3M_SRC" ]; then
  echo "Error: a3m not found under $RUN_SUBDIR (check $LOG)." >&2
  exit 2
fi

A3M_DST="$OUT_DIR/target.a3m"
cp "$A3M_SRC" "$A3M_DST"

QUERY_LEN=$(awk 'NR==2 {print length($0); exit}' "$A3M_DST")
HOMOLOGS=$(awk '/^>/' "$A3M_DST" | wc -l)

echo
echo "=== Step 0 complete ==="
echo "target.a3m : $A3M_DST"
echo "  query length : $QUERY_LEN aa"
echo "  homologs     : $HOMOLOGS records"
echo
echo "Use this a3m in Phase 2:"
echo "  msa_path=\"$A3M_DST\"   (Boltz-2 submit_affinity_prediction)"
echo "  unpairedMsaPath in af3_inputs/<candidate>/input.json"
