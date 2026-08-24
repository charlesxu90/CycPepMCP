# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CycPepMCP is a cyclic peptide engineering toolkit built on the Model Context Protocol (MCP). It provides two CLI tools (`cpmcp` for MCP server management, `cpskill` for workflow skill management) and orchestrates 28 MCP servers and 9 public MCPs for computational peptide design, structure prediction, and property optimization. Three workflow skills define end-to-end design protocols (RFpeptides, AfCycDesign, HELM-GPT).

## Installation & Setup

```bash
mamba env create -f environment.yml -y
mamba activate cycpepmcp
pip install -r requirements.txt
pip install -e .
```

Each MCP server has its own setup: `cd tool-mcps/<mcp_name> && bash quick_setup.sh`

## CLI Commands

### cpmcp (MCP management)

- `cpmcp avail` - List available MCP servers (`--local` or `--public`)
- `cpmcp install <name>` - Install and register MCP with Claude Code (`--no-register`, `--cli gemini`)
- `cpmcp uninstall <name>` - Unregister MCP (`--remove-files`)
- `cpmcp status` - Show installed/registered MCPs (`--refresh`)
- `cpmcp info <name>` - Show MCP details (runtime, path, cache, docker image)
- `cpmcp search <query>` - Search MCPs by name/description
- `cpmcp create -g <github_url> -d tool-mcps/<name>` - Auto-create MCP from a repo
- `cpmcp cache` - Show cache directory info and configured MCP subpaths
- `cpmcp sync` - Sync registry with filesystem

### cpskill (workflow management)

- `cpskill avail` - List available workflow skills
- `cpskill status` - Show installation status
- `cpskill info <name>` - Show skill details and required MCPs
- `cpskill install <name>` - Install skill and its required MCPs
- `cpskill execute <name>` - Step-by-step workflow guidance
- `cpskill uninstall <name>` - Remove skill and cleanup
- `cpskill create init <name>` - Initialize a new skill
- `cpskill create add-step <name>` - Add a workflow step
- `cpskill create list-steps <name>` - List defined steps
- `cpskill create generate <name>` - Generate skill markdown from steps
- `cpskill create from-steps <name>` - Create skill directly from step definitions

## Architecture

### Two-Layer System

1. **MCP Servers** (`tool-mcps/`): 28 individual computational tools, each wrapping a scientific software package (RFdiffusion, ProteinMPNN, Rosetta, AlphaFold, etc.) as an MCP server using FastMCP. Each server runs `python src/server.py` and has its own conda/uv env in `env/`.

2. **Workflow Skills** (`workflow-skills/`): Markdown-based multi-step protocols that orchestrate multiple MCP servers into complete design workflows. Registered as Claude Code slash commands via `.claude/skills/` or `.claude/commands/`.

### Source Code (`src/`)

```
src/
  mcp_cli.py          # `cpmcp` entry point (Click CLI)
  skill_cli.py         # `cpskill` entry point (Click CLI)
  utils.py             # Shared utilities (ProgressSpinner, run_command, Claude streaming)
  cycpep_mcp/
    mcp.py             # MCP class (data model, ~20 attributes)
    mcp_manager.py     # Registry operations, YAML loading
    install_mcp.py     # Install/uninstall/register with Claude Code CLI
    create_mcp.py      # Auto-create MCP from GitHub repo (8-step pipeline)
    mcp_creator.py     # Claude-powered MCP generation helpers
    status_cache.py    # Cached status checks (5-min TTL, file-locked)
    configs/
      mcps.yaml        # MCP server registry (28 entries)
      public_mcps.yaml # Public MCP registry (9 entries)
  skill/
    skill.py           # Skill class (data model)
    skill_manager.py   # Install/uninstall skills
    create_skill.py    # Interactive skill creation
    configs.yaml       # Skill registry (5 entries)
```

### MCP Server Pattern

All GPU-intensive MCP servers (rfpeptides, proteinmpnn, rosetta_kic, afcycdesign, boltz, helmgpt, etc.) share the same async job architecture:
- `src/server.py` - FastMCP server with tool definitions
- `src/jobs/manager.py` - FIFO job queue (one GPU job at a time), thread-safe, file-locking on metadata.json
- Job lifecycle: `submit_*()` returns `job_id` -> poll `get_job_status()` -> `get_job_result()`
- Jobs stored in filesystem with metadata.json, stdout/stderr logs, output files

### Runtime Types

| Runtime | Use Case | Example MCPs |
|---------|----------|--------------|
| `docker` | GPU, complex deps | afcycdesign, rfpeptides, boltz, rosetta, alphafold3 |
| `uv` | Lightweight CPU | cyclicchamp, haddock3, multicycgt, pharmpapp |
| `python` | Conda-based | ADCP, cyc_builder, cyclicpeptide, rosetta_kic |

### Config Flow

MCP registry (`src/cycpep_mcp/configs/mcps.yaml`) maps each MCP name to its path, runtime, server command, and setup script. `cpmcp install` runs `quick_setup.sh` then registers the server in Claude Code's `~/.claude.json`.

## Centralized Cache System

MCP data and model weights are stored under a single cache root controlled by the `MACROMNEX_CACHE` env var (default: `~/.macromnex/cache`).

```
$MACROMNEX_CACHE/          # default: ~/.macromnex/cache
├── data/                  # databases, reference data (per-MCP subpaths)
└── model/                 # ML model weights (per-MCP subpaths)
    ├── boltz/
    ├── alphafold2/params/
    ├── alphafold3/
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

## Workflow Skills

Three workflow skills in `workflow-skills/`, each registered as a Claude Code slash command:

### RFpeptides Binder Design (5 Stages)

File: `workflow-skills/binder_design_rfpeptides.md`
Required MCPs: rfpeptides_mcp, proteinmpnn_mcp, rosetta_kic_mcp, afcycdesign_mcp

1. **Backbone Generation** - RFpeptides generates cyclic peptide backbones against target (with optional hotspot residues)
2. **Iterative Sequence Design** - 4 rounds of ProteinMPNN CA-only design + Rosetta FastRelax (with PeptideCyclizeMover)
3. **DL Validation** - AfCycDesign reprediction for iPAE, RMSD, pLDDT
4. **Physics Filtering** - Rosetta interface metrics (ddG, SAP, CMS)
5. **Clustering & Selection** - RMSD-based clustering, ranked by composite score

Key parameters:
- ProteinMPNN CA-only: `model="v_48_020"`, `temperature=0.0001`, `omit_AAs="C"`, `chains="A"`
- Rosetta FastRelax: `rounds=4` with PeptideCyclizeMover
- Composite score: `0.3*ddG_norm + 0.25*iPAE_norm + 0.2*pLDDT_norm + 0.15*CMS_norm + 0.1*SAP_norm`

Automated pipeline: `workflow-skills/scripts/rfpeptides/run_pipeline.py` (parallel CPU/GPU workers, checkpoint resume)

### AfCycDesign Binder Design (7 Stages)

File: `workflow-skills/binder_design_afcycdesign.md`
Required MCPs: afcycdesign_mcp

1. **Validate Target** - Check input PDB, identify chains
2. **Submit Binder Design** - AF2-guided optimization with optional hotspot targeting
3. **Monitor Progress** - Poll status; expect 2-5 min JAX compilation delay
4. **Collect Results** - Extract PDB, logs, metadata, output_metrics.json
5. **Analyze Results** - Parse sequence/metrics, create summary CSV
6. **Re-predict Complexes** - AF-multimer (6 recycles) per design for iPAE and unbiased pLDDT; ~90 s/design
7. **Visualize** - Generate 6 publication-quality figures from the re-predicted table

Key parameters:
- Optimizer: `pssm_semigreedy` (recommended) or `3stage` (120 logits + 60 soft + 10 hard iterations)
- Binder length: 8-16 residues
- Composite score: `0.50*pLDDT + 0.50*(1 - iPAE)` on re-predicted metrics
- Classification (nested): Excellent pLDDT>0.90 & iPAE<0.11; Good >0.85 & <0.15; Acceptable >0.70 & <0.30
- Chain convention: target=Chain A, binder=Chain B (opposite from RFpeptides)
- Design-time metrics are the optimizer's objective and are optimistic; classify on Step 6 values only

### HELM-GPT KRAS Binder Design (3 Phases)

File: `workflow-skills/binder_design_helmgpt.md`
Required MCPs: helm_gpt_mcp, boltz_mcp, alphafold3_mcp, gnina_mcp

1. **RL Co-optimization** - HELM-GPT generates macrocyclic peptides with dual reward: XGBoost KRAS binding (KD) + RF permeability. Local scoring models (fast). `loss_type="reinvent_cpl"`, `n_steps=500`, `batch_size=32`.
2. **Structural Evaluation** - Heavy-atom routing at 128 atoms:
   - ≤128 atoms: Boltz-2 SMILES affinity (3-head ensemble) + AF3 + Gnina docking
   - >128 atoms: AF3 + Gnina docking only (Boltz-2 ligand limit)
3. **Final Selection** - Track-dependent composite scoring with different weight schemes

Quality thresholds: KRAS KD <10 uM, permeability >-6.0 log cm/s, AF3 iPTM >0.60, Gnina CNN >6.0 pKd

### Quality Thresholds (RFpeptides)

| Metric | Good | Description |
|--------|------|-------------|
| ddG | < -30 REU | Binding energy |
| SAP | < 35 | Aggregation propensity |
| CMS | > 300 A^2 | Contact surface area |
| iPAE | < 0.20 | Interface confidence |
| RMSD | < 1.5 A | Reprediction fidelity |
| pLDDT | > 0.70 | Per-residue confidence |

## Visualization Scripts

Publication-quality figure generation in `workflow-skills/scripts/`:

- `afcycdesign/afcycdesign_viz.py` - 6-panel (pLDDT, iPAE, scatter, ranking, table, iPTM)
- `rfpeptides/rfpeptides_viz.py` - 9-panel (ddG, iPAE, pLDDT, SAP, CMS, scatter, composite, table, timeline)
- `helmgpt/helmgpt_viz.py` - 12-panel (KD, perm, scatter, AF3, Gnina CNN/Vina, Boltz, composite, radar, table, timeline)

Usage: `python workflow-skills/scripts/<workflow>/<script>.py <results_dir> [--merged] [--output <prefix>]`

## Auto-Creation Pipeline

`cpmcp create -g <github_url> -d tool-mcps/<name>` runs an 8-step Claude-powered pipeline:

1. Setup project directory structure
2. Clone repository (with submodules)
3. Setup conda env & scan use cases
4. Execute use cases (with automated debugging)
5. Write reusable function scripts
6. Extract MCP tools & wrap in FastMCP server
7. Test Claude & Gemini integration
8. Create README + generate `quick_setup.sh`

Options: `--rerun-from-step N`, `--clear-markers-from-step N`, `--runtime uv|conda|auto`
Checkpoints via marker files in `.pipeline/` allow resume from any step.

## Known Issues

- **afcycdesign_mcp Python path**: `manager.py` must use `sys.executable` instead of hardcoded `"python"`. Server needs restart after code changes.
- **Resubmit race condition**: Parallel resubmits can cause `[Errno 2]` on `metadata.json.tmp`. Submit resubmits sequentially.
- **FIFO queues**: Each MCP server processes one GPU job at a time. Long-running jobs (10-90 min) block the queue.

## Example Data

Three case studies in `examples/`:

- `case1_mdm2_binder_afcycdesign/` - MDM2 binder (AfCycDesign), target: `4HFZ_MDM2.pdb`, hotspots: [54, 56, 58, 61, 67, 96, 99, 100]
- `case2_RbtA_binder_rfpeptides/` - RbtA binder (RFpeptides full protocol), flat beta-helix surface
- `case3_kras_perm_opt_helmgpt/` - KRAS binder (HELM-GPT), RL co-optimization with ncAA macrocycles

## Dev Dependencies

Testing and linting (from `setup.py` extras): `pytest`, `pytest-asyncio`, `black`, `ruff`
