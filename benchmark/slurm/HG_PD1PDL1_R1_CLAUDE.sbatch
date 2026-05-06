#!/bin/bash
#SBATCH --job-name=HG_PD1PDL1_R1_CLAUDE
#SBATCH --output=/home/xux/Desktop/AgentMCP/CycPepMCP/benchmark/runs/HG_PD1PDL1_R1_CLAUDE/sbatch.log
#SBATCH --error=/home/xux/Desktop/AgentMCP/CycPepMCP/benchmark/runs/HG_PD1PDL1_R1_CLAUDE/sbatch.log
#SBATCH --partition=batch
#SBATCH --time=24:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gpus=1
#SBATCH --mem=96G
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
[ -d "/home/xux/Desktop/AgentMCP/CycPepMCP/tool-mcps/helm_gpt_mcp/env" ] || { echo "ERROR: tool-mcps/helm_gpt_mcp/env missing on this node" >&2; exit 2; }
    [ -d "/home/xux/Desktop/AgentMCP/CycPepMCP/tool-mcps/boltz_mcp/env" ] || { echo "ERROR: tool-mcps/boltz_mcp/env missing on this node" >&2; exit 2; }
    [ -d "/home/xux/Desktop/AgentMCP/CycPepMCP/tool-mcps/alphafold3_mcp/env" ] || { echo "ERROR: tool-mcps/alphafold3_mcp/env missing on this node" >&2; exit 2; }
    [ -d "/home/xux/Desktop/AgentMCP/CycPepMCP/tool-mcps/gnina_mcp/env" ] || { echo "ERROR: tool-mcps/gnina_mcp/env missing on this node" >&2; exit 2; }

# GPU pinning: Slurm's CUDA_VISIBLE_DEVICES is already correct; the runner
# always asks for GPU 0 internally.
export BENCHMARK_GPU_ID=0
echo "[$(date)] start HG_PD1PDL1_R1_CLAUDE on $(hostname) GPU=$CUDA_VISIBLE_DEVICES"
"$PROJECT_PY" -m benchmark.scripts.run_benchmark \
    --task HG_PD1PDL1 --llm claude --seed 1 --mode real 
echo "[$(date)] finished HG_PD1PDL1_R1_CLAUDE"
