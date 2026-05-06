# CycPepMCP Benchmark

Reproducibility package for the CycPepMCP benchmark. Configs and scripts are
designed to run identically on a local workstation and on KAUST iBex / Shaheen.

> Single source of truth: every PASS gate, composite-score weight, target row,
> and LLM-backend setting lives in `benchmark/configs/`. Runners and viz scripts
> all read from there — no duplicated thresholds.

## Layout

```
benchmark/
  configs/
    targets.csv         # 13 benchmark targets (locked)
    workflows.yaml      # PASS gates + composite weights for the 3 workflows
    thresholds.py       # Python loader; all consumers import from here
    llm_backends.yaml   # Claude / GPT / Gemini config + 9-task LLM grid
  data_curation/        # HELM-GPT per-target dataset curation (chembl, patents, normalize, split)
  reward_models/        # Trained per-target XGBoost predictors + metrics.json
  scripts/
    run_benchmark.py    # Top-level dispatcher
    workflow_runners/   # Per-workflow runners (afcycdesign, rfpeptides, helmgpt)
    seed_pilot_from_case.py  # Pre-seed run dirs from existing case study outputs
    stage_pdbs.py       # Download + verify all target PDBs (login-node only)
    submit_slurm.py     # Generate sbatch scripts for iBex / Shaheen
    aggregate_metrics.py  # Roll up runs/ into summary CSVs
    agent_trace.py      # JSONL event logger
    llm_orchestrator.py # Claude / OpenAI / Gemini SDK adapters
  runs/<run_id>/        # One per benchmark run; agent_trace.jsonl + candidate_metrics.csv + summary.json + checkpoint.json
  summary/              # Aggregated CSVs (task / candidate / agent / llm_comparison)
  figures/              # Reproduced manuscript figures (fig2-5; png + pdf)
  slurm/                # Generated sbatch scripts (gitignored typically)
  README.md             # this file
  READINESS.md          # Implementation readiness manifest + smoke-test sequence
examples/               # Per-task input bundles. Each folder = one task; config name = workflow.
  case1_mdm2_binder_afcycdesign/      AF_MDM2     (4HFZ_MDM2.pdb         + afcycdesign_config.md)
  case2_MCL1_binder_rfpeptides/       RF_MCL1     (2PQK_MCL1.pdb         + rfpeptides_config.md)
  case2_RbtA_binder_rfpeptides/       RF_RBTA     (RbtA_monomer_relaxed.pdb + rfpeptides_config.md)
  case3_kras_perm_opt_helmgpt/        HG_KRASG12D (target.fasta + setup  + helmgpt_config.md)
  case_mcl1_afcycdesign/              AF_MCL1     (2PQK_MCL1.pdb         + afcycdesign_config.md)
  case_bclxl_afcycdesign/             AF_BCLXL    (1G5J_BCLxL.pdb        + afcycdesign_config.md)
  case_xiap_afcycdesign/              AF_XIAP     (1G73_XIAP.pdb chain C + afcycdesign_config.md)
  case_pcsk9_afcycdesign/             AF_PCSK9    (3P5C_PCSK9.pdb        + afcycdesign_config.md)
  case_mdm2_rfpeptides/               RF_MDM2     (4HFZ_MDM2.pdb         + rfpeptides_config.md)
  case_gabarap_rfpeptides/            RF_GABARAP  (1KOT_GABARAP.pdb      + rfpeptides_config.md)
  case_pdl1_rfpeptides/               RF_PDL1     (5IUS_PDL1.pdb chain B + rfpeptides_config.md)
  case_pd1pdl1_helmgpt/               HG_PD1PDL1  (target.fasta          + helmgpt_config.md)
  case_mdm2p53_helmgpt/               HG_MDM2P53  (target.fasta          + helmgpt_config.md)
```

Every case directory is a self-contained input bundle: structural target (PDB or
FASTA) + a workflow-specific config (`afcycdesign_config.md`, `rfpeptides_config.md`,
or `helmgpt_config.md`) documenting hotspots, parameters, PASS gates, and (for
HELM-GPT) the data-curation preflight. The 4 original case dirs (case1/2/3) keep
their historical naming; the 9 new cases use `case_<target>_<workflow>/`.

## Run ID convention

`{TASK}_R{seed}_{LLM}` per Appendix A of `docs/benchmark_plan.md`.

  - `TASK` already encodes workflow: AF_*, RF_*, HG_*
  - `seed` ∈ {1, 2, 3, ...} (seeds 2 and 3 reserved for repeatability reruns)
  - `LLM` ∈ {CLAUDE, GPT, GEMINI, MOCK}

Examples: `AF_MDM2_R1_CLAUDE`, `RF_MCL1_R2_GPT`, `HG_KRASG12D_R1_GEMINI`.

## Quick start (local workstation)

```bash
# 1. Activate the project env
mamba activate cycpepmcp

# 2. One-time setup (idempotent)
python -m benchmark.configs.thresholds          # config self-check
python -m benchmark.scripts.stage_pdbs          # download missing PDBs
                                                #   verifies chain IDs

# 3. Smoke test in mock mode (no GPU)
python -m benchmark.scripts.run_benchmark --all --mode mock --llm mock

# 4. One real run on local GPU
python -m benchmark.scripts.run_benchmark --task AF_MDM2 --llm claude \
    --mode real --seed 1 --num-designs 10
```

`--num-designs N` overrides the targets.csv default (useful for shorter pilots
than the production 10/5000/etc.). On a 2× A100 box, 10 AfCycDesign designs
take ~30-50 min depending on target size.

## HPC deployment (iBex / Shaheen)

Compute nodes typically have **no internet**, so PDB downloads MUST happen on
the login node before any sbatch submission.

```bash
# === On the login node ===
cd /ibex/scratch/$USER       # or /scratch/$USER on Shaheen
git clone <repo-url> CycPepMCP
cd CycPepMCP
mamba env create -f environment.yml
mamba activate cycpepmcp

# One-time per-MCP setup (skip the ones you don't need; setup_script in mcps.yaml)
for mcp in afcycdesign_mcp rfpeptides_mcp proteinmpnn_mcp rosetta_kic_mcp \
           helm_gpt_mcp boltz_mcp alphafold3_mcp gnina_mcp; do
    cd tool-mcps/$mcp && bash quick_setup.sh && cd -
done

# Pre-stage every PDB (login node = has internet)
python -m benchmark.scripts.stage_pdbs

# Generate sbatch scripts for the 13-task primary pass on Claude
python -m benchmark.scripts.submit_slurm \
    --cluster ibex --account <PROJ> --seed 1 --llm claude
# (writes 13 scripts under benchmark/slurm/)

# Submit
cd benchmark/slurm/
for s in *.sbatch; do sbatch "$s"; done

# Monitor
squeue -u $USER
```

Resource hints baked into the sbatch templates (tune via `--time`):

| Workflow     | Default --time | --gpus | --mem  |
|--------------|----------------|--------|--------|
| afcycdesign  | 08:00:00       | 1      | 64 G   |
| rfpeptides   | 48:00:00       | 2      | 128 G  |
| helmgpt      | 24:00:00       | 1      | 96 G   |

Cluster profiles (in `submit_slurm.py`):

  - `ibex`:    `--partition=batch --constraint=a100`
  - `shaheen`: `--partition=gpu`  (verify your allocation's actual partition name)
  - `local`:   `--partition=debug`

If a job is killed mid-run, just re-submit with `--resume`:

```bash
python -m benchmark.scripts.run_benchmark --task RF_MCL1 --llm claude \
    --mode real --seed 1 --resume
```

The runner writes `<run_dir>/checkpoint.json` after each major stage; resume
skips completed stages and re-runs only the stage that was interrupted.

## Aggregation + figures

After every batch of runs:

```bash
python -m benchmark.scripts.aggregate_metrics
# writes benchmark/summary/{task,candidate,agent,llm_comparison}_summary.csv

python -m benchmark.scripts.make_figures --fig 2 3 4 5
# regenerates manuscript figures from the summary CSVs
```

Per-workflow figures (existing scripts, pre-existing the benchmark layer):

```bash
# AfCycDesign target panel (with --merged for multi-target)
python workflow-skills/scripts/afcycdesign/afcycdesign_viz.py \
    benchmark/runs/AF_MDM2_R1_CLAUDE --output mdm2

# RFpeptides timeline + composite
python workflow-skills/scripts/rfpeptides/rfpeptides_viz.py \
    benchmark/runs/RF_MCL1_R1_CLAUDE/pipeline --output mcl1

# HELM-GPT 12-panel + radar
python workflow-skills/scripts/helmgpt/helmgpt_viz.py \
    benchmark/runs/HG_KRASG12D_R1_CLAUDE --output kras
```

All three viz scripts read thresholds from `benchmark/configs/workflows.yaml`
via `benchmark/configs/thresholds.py` — see W1 centralization.

## HELM-GPT data curation (W2c → W3b)

HELM-GPT targets other than KRAS-G12D require a target-specific reward model.
Each new target goes through the data-curation pipeline:

```bash
# 1. ChEMBL pull (modality filter on)
python -m benchmark.data_curation.chembl_query \
    --target_chembl_id CHEMBL3582 --target_name PD-L1 \
    --output benchmark/data_curation/datasets/raw/pd1_pdl1_chembl_raw.csv

# 2. Patent extraction (manual; init template, transcribe, merge)
python -m benchmark.data_curation.patent_extract init \
    --patent_id US20240158446A1 \
    --output benchmark/data_curation/datasets/raw/patents/US20240158446A1.csv
# ... (data curator transcribes patent activity tables) ...
python -m benchmark.data_curation.patent_extract merge \
    --patents_dir benchmark/data_curation/datasets/raw/patents/ \
    --output benchmark/data_curation/datasets/raw/pd1_pdl1_patents_merged.csv \
    --target_name PD-L1

# 3. Normalize endpoints & SMILES
python -m benchmark.data_curation.normalize_endpoints \
    --inputs benchmark/data_curation/datasets/raw/pd1_pdl1_chembl_raw.csv \
             benchmark/data_curation/datasets/raw/pd1_pdl1_patents_merged.csv \
    --target_id Q9NZQ7 \
    --output benchmark/data_curation/datasets/pd1_pdl1.csv

# 4. Scaffold split
python -m benchmark.data_curation.scaffold_split \
    --input  benchmark/data_curation/datasets/pd1_pdl1.csv \
    --output benchmark/data_curation/datasets/pd1_pdl1_split.csv

# 5. Train + validate XGBoost
python -m benchmark.reward_models.train_xgboost \
    --input benchmark/data_curation/datasets/pd1_pdl1_split.csv \
    --target_id hg_pd1pdl1 \
    --out_dir benchmark/reward_models/trained
```

The runner enforces `Spearman ≥ 0.4` (workflows.yaml `helmgpt.pass_gates.reward_model.spearman_min_pass`)
on the scaffold-split test set before allowing RL — failing targets log
`error_type=scientific` and abort cleanly. Promote a backup target if a
predictor falls below the gate.

A separate Python env is recommended for data curation (heavy deps):

```bash
mamba create -n cycpep_curation python=3.11 -y
mamba activate cycpep_curation
pip install rdkit chembl-webresource-client xgboost scikit-learn pandas scipy numpy
```

## Reference traces (Run 0)

Schema-mapped from the existing case studies — useful as a sanity check for
new HPC runs:

| run_id                  | n   | PASS | top composite | source                               |
|-------------------------|-----|------|---------------|--------------------------------------|
| AF_MDM2_R1_CLAUDE       | 50  | 49   | 0.867         | results/case1_mdm2_binder_afcycdesign |
| RF_MCL1_R1_CLAUDE       | 200 | 4    | 0.6753        | results/case2_mcl1_rfpeptides         |
| RF_RBTA_R1_CLAUDE       | 200 | 0    | 0.386         | results/case2_RbtA_v3                 |
| HG_KRASG12D_R1_CLAUDE   | 20  | 7    | 0.6639        | results/case3_kras_helmgpt            |

Re-seed any of these from a fresh checkout with:

```bash
python -m benchmark.scripts.seed_pilot_from_case --task AF_MDM2
python -m benchmark.scripts.run_benchmark --task AF_MDM2 --llm claude \
    --mode real --resume
```

## Troubleshooting

**`reward-model metrics missing`** — Spearman gate firing for a HELM-GPT
target whose XGBoost has not been trained. Run the data-curation pipeline
above and verify `<task>_metrics.json` reports `scaffold_split_spearman ≥ 0.4`.

**`stage1 backbones missing at <path>`** — RFpeptides runner expected
RFdiffusion outputs at `<run_dir>/stage1_backbones/*.pdb`. Either invoke
`rfpeptides_mcp.submit_cyclic_binder_with_hotspots` separately and copy the
backbones in, or pre-seed via `seed_pilot_from_case.py`.

**`afcycdesign tool not installed`** — `tool-mcps/afcycdesign_mcp/env/` is
missing. Run `cpmcp install afcycdesign_mcp` (or `cd tool-mcps/afcycdesign_mcp
&& bash quick_setup.sh`) on the cluster login node first.

**Compute node has no internet** — pre-stage with `python -m
benchmark.scripts.stage_pdbs` on the login node before submitting any sbatch.

**Jax / TF / CUDA mismatch** — every tool-mcp ships its own conda env under
`tool-mcps/<name>/env/`; the runner picks them up automatically. Cluster
modules are NOT loaded by the sbatch templates by default.
