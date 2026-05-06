#!/bin/bash
#SBATCH --job-name=RF_RBTA_R1_CLAUDE
#SBATCH --output=/home/xux/Desktop/AgentMCP/CycPepMCP/benchmark/runs/RF_RBTA_R1_CLAUDE/sbatch.log
#SBATCH --error=/home/xux/Desktop/AgentMCP/CycPepMCP/benchmark/runs/RF_RBTA_R1_CLAUDE/sbatch.log
#SBATCH --partition=batch
#SBATCH --time=48:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gpus=2
#SBATCH --mem=128G
#SBATCH --constraint=a100
#SBATCH --account=TEST

set -euo pipefail
cd /home/xux/Desktop/AgentMCP/CycPepMCP

# (no module loads)

# Single-source-of-truth env: prefer the project's own python (created by
# the top-level `mamba env create -f environment.yml`).
PROJECT_PY=/home/xux/Desktop/AgentMCP/CycPepMCP/env/bin/python
if [ ! -x "$PROJECT_PY" ]; then
    echo "ERROR: project env not found at $PROJECT_PY" >&2
    echo "Run 'mamba env create -f environment.yml' on the login node first" >&2
    exit 2
fi

# Verify required tool-mcp envs exist for this workflow.
[ -d "/home/xux/Desktop/AgentMCP/CycPepMCP/tool-mcps/rfpeptides_mcp/env" ] || { echo "ERROR: tool-mcps/rfpeptides_mcp/env missing on this node" >&2; exit 2; }
    [ -d "/home/xux/Desktop/AgentMCP/CycPepMCP/tool-mcps/proteinmpnn_mcp/env" ] || { echo "ERROR: tool-mcps/proteinmpnn_mcp/env missing on this node" >&2; exit 2; }
    [ -d "/home/xux/Desktop/AgentMCP/CycPepMCP/tool-mcps/rosetta_kic_mcp/env" ] || { echo "ERROR: tool-mcps/rosetta_kic_mcp/env missing on this node" >&2; exit 2; }
    [ -d "/home/xux/Desktop/AgentMCP/CycPepMCP/tool-mcps/afcycdesign_mcp/env" ] || { echo "ERROR: tool-mcps/afcycdesign_mcp/env missing on this node" >&2; exit 2; }

# GPU pinning: Slurm's CUDA_VISIBLE_DEVICES is already correct; the runner
# always asks for GPU 0 internally.
export BENCHMARK_GPU_ID=0
echo "[$(date)] start RF_RBTA_R1_CLAUDE on $(hostname) GPU=$CUDA_VISIBLE_DEVICES"
"$PROJECT_PY" -m benchmark.scripts.run_benchmark \
    --task RF_RBTA --llm claude --seed 1 --mode real 
echo "[$(date)] finished RF_RBTA_R1_CLAUDE"
