# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CycPepMCP is a cyclic peptide engineering toolkit built on the Model Context Protocol (MCP). It provides two CLI tools (`cpmcp` for MCP server management, `cpskill` for workflow skill management) and orchestrates ~30 MCP servers for computational peptide design, structure prediction, and property optimization.

## Installation & Setup

```bash
mamba env create -f environment.yml -y
mamba activate cycpepmcp
pip install -r requirements.txt
pip install -e .
```

Each MCP server has its own setup: `cd tool-mcps/<mcp_name> && bash quick_setup.sh`

## CLI Commands

- `cpmcp avail` - List available MCP servers
- `cpmcp install <name>` - Install and register MCP with Claude Code
- `cpmcp status` - Show installed/registered MCPs
- `cpmcp create -g <github_url> -d tool-mcps/<name>` - Auto-create MCP from a repo
- `cpmcp cache` - Show cache directory info and configured MCP subpaths
- `cpmcp sync` - Sync registry with filesystem
- `cpskill avail` - List available workflow skills
- `cpskill install <name>` - Install skill and its required MCPs
- `cpskill execute <name>` - Step-by-step workflow guidance

## Architecture

### Two-Layer System

1. **MCP Servers** (`tool-mcps/`): Individual computational tools, each wrapping a scientific software package (RFdiffusion, ProteinMPNN, Rosetta, AlphaFold, etc.) as an MCP server using FastMCP. Each server runs `python src/server.py` and has its own conda env in `env/`.

2. **Workflow Skills** (`workflow-skills/`): Markdown-based multi-step protocols that orchestrate multiple MCP servers into complete design workflows. Registered as Claude Code slash commands via `.claude/skills/` or `.claude/commands/`.

### Source Code (`src/`)

```
src/
  mcp_cli.py          # `cpmcp` entry point (Click CLI)
  skill_cli.py         # `cpskill` entry point (Click CLI)
  utils.py             # Shared utilities
  cycpep_mcp/
    mcp.py             # MCP class (data model)
    mcp_manager.py     # Registry operations, YAML loading
    install_mcp.py     # Install/uninstall/register with Claude Code CLI
    create_mcp.py      # Auto-create MCP from GitHub repo (8-step pipeline)
    mcp_creator.py     # Claude-powered MCP generation helpers
    status_cache.py    # Cached status checks
    configs/
      mcps.yaml        # MCP server registry (~30 entries)
      public_mcps.yaml # Public MCP registry
  skill/
    skill.py           # Skill class (data model)
    skill_manager.py   # Install/uninstall skills
    create_skill.py    # Interactive skill creation
    configs.yaml       # Skill registry (5 entries)
```

### MCP Server Pattern

All GPU-intensive MCP servers (rfpeptides, proteinmpnn, rosetta_kic, afcycdesign) share the same async job architecture:
- `src/server.py` - FastMCP server with tool definitions
- `src/jobs/manager.py` - FIFO job queue (one GPU job at a time), thread-safe, file-locking on metadata.json
- Job lifecycle: `submit_*()` returns `job_id` -> poll `get_job_status()` -> `get_job_result()`
- Jobs stored in filesystem with metadata.json, stdout/stderr logs, output files

### Config Flow

MCP registry (`src/cycpep_mcp/configs/mcps.yaml`) maps each MCP name to its path, runtime, server command, and setup script. `cpmcp install` runs `quick_setup.sh` then registers the server in Claude Code's `~/.claude.json`.

## Centralized Cache System

MCP data and model weights are stored under a single cache root controlled by the `MACROMNEX_CACHE` env var (default: `~/.macromnex/cache`).

```
$MACROMNEX_CACHE/          # default: ~/.macromnex/cache
├── data/                  # databases, reference data (per-MCP subpaths)
└── model/                 # ML model weights (per-MCP subpaths)
    ├── boltz/
    ├── afcycdesign/
    └── ...
```

Per-MCP config in `mcps.yaml` uses nested dicts:
- `cache_data: {subpath, mount}` - subpath under `data/` and container mount point
- `cache_model: {subpath, mount}` - subpath under `model/` and container mount point

Docker MCPs get cache dirs auto-mounted as volumes. Non-Docker MCPs (python, uv) receive the `MACROMNEX_CACHE` env var. Cache dirs are auto-created during `cpmcp install`. Use `cpmcp cache` to inspect.

## Chain Conventions (Critical)

Different tools use different chain assignments for peptide-target complexes:

| Tool | Binder (peptide) | Target (protein) |
|------|------------------|-------------------|
| RFpeptides output | Chain A | Chain B |
| ProteinMPNN | design chains="A" | fixed |
| Rosetta interface metrics | peptide_chain="A" | - |
| AfCycDesign binder_design | Chain B (output) | Chain A |

## RFpeptides Binder Design Workflow (5 Stages)

The primary workflow in `workflow-skills/binder_design_rfpeptides.md`:

1. **Backbone Generation** - RFpeptides generates cyclic peptide backbones against target (with optional hotspot residues)
2. **Iterative Sequence Design** - 4 rounds of ProteinMPNN CA-only design + Rosetta FastRelax (with PeptideCyclizeMover)
3. **DL Validation** - AfCycDesign reprediction for iPAE, RMSD, pLDDT
4. **Physics Filtering** - Rosetta interface metrics (ddG, SAP, CMS)
5. **Clustering & Selection** - RMSD-based clustering, ranked by ddG/iPAE/pLDDT

### Key Parameters

- ProteinMPNN CA-only: `model="v_48_020"`, `temperature=0.0001`, `omit_AAs="C"`, `chains="A"`
- Rosetta FastRelax: `rounds=4` with PeptideCyclizeMover

### Quality Thresholds

| Metric | Good | Description |
|--------|------|-------------|
| ddG | < -30 REU | Binding energy |
| SAP | < 35 | Aggregation propensity |
| CMS | > 300 A^2 | Contact surface area |
| iPAE | < 0.20 | Interface confidence |
| RMSD | < 1.5 A | Reprediction fidelity |
| pLDDT | > 0.70 | Per-residue confidence |

## Known Issues

- **afcycdesign_mcp Python path**: `manager.py` must use `sys.executable` instead of hardcoded `"python"`. Server needs restart after code changes.
- **Resubmit race condition**: Parallel resubmits can cause `[Errno 2]` on `metadata.json.tmp`. Submit resubmits sequentially.
- **FIFO queues**: Each MCP server processes one GPU job at a time. Long-running jobs (10-90 min) block the queue.

## Example Data

- Target PDB: `examples/case1_cycpep_design/4HFZ_MDM2.pdb` (MDM2 protein)
- MDM2 hotspot residues: `[54, 56, 58, 61, 67, 96, 99, 100]`

## Dev Dependencies

Testing and linting (from `setup.py` extras): `pytest`, `pytest-asyncio`, `black`, `ruff`
