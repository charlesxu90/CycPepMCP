# HELM-GPT Generative-to-Physics Binder Design Workflow

> Cyclic peptide binder design integrating HELM-GPT generative optimization with Boltz-2 structural feedback, HighFold3 + Gnina docking validation, and MD simulation final evaluation

## Overview

This skill implements a three-phase pipeline for designing synthesizable macrocyclic peptide binders. The workflow uses HELM-GPT as the generative engine with a multi-objective RL loop that incorporates Boltz-2 complex structure prediction metrics (iPAE, iPTM) and permeability scoring as real-time rewards, followed by HighFold3 structure prediction + Gnina docking for binding validation, and MD simulations for final evaluation.

**Key Design Choices:**
- The prior model is already pre-trained with permeability optimization (no separate permeability step needed)
- Boltz-2 is used for **complex structure prediction** — supported scores: `ipae_scores`, `iptm_scores`, `affinity_pic50`, `complex_ipde_scores`
- Boltz-2 input should be **protein sequences** (target + peptide), NOT SMILES — protein sequence input produces significantly better complex structures
- iPAE and iPTM from Boltz-2 complex prediction are the primary RL feedback metrics
- HELM-to-SMILES conversion is only needed for permeability scoring (RF model), not for Boltz-2
- All Boltz-2 DL metrics feed directly back as RL rewards — no separate validation phase

**Protocol Architecture:**
```
PHASE 1: RL-Guided Generation with DL Feedback (HELM-GPT + Boltz-2)
    HELM-GPT generates → HELM→SMILES → score permeability (RF model)
                       → HELM→amino acid sequence → Boltz-2 complex prediction → iPAE, iPTM
                       → combined reward → update GPT model
    ↓
PHASE 1b: Boltz-2 SMILES Affinity Prediction
    HELM→SMILES → Boltz-2 affinity prediction (peptide as small molecule ligand)
    → 3-head ensemble affinity + confidence metrics → ensemble consensus filtering
    ↓
PHASE 2: Structure Prediction & Docking Validation (HighFold3 + Gnina)
    HighFold3 cyclic peptide structure prediction (CycPOEM) → Gnina docking against target → filtering
    ↓
PHASE 3: MD Simulation Final Evaluation
    MD simulations of top binders → binding stability, RMSD, interaction analysis → final selection
```

## Prerequisites

### Required MCP Servers
| MCP Server | Purpose | Phase(s) |
|------------|---------|----------|
| `helmgpt_mcp` | Sequence generation, RL optimization, permeability scoring, HELM→SMILES, Boltz-2 server scoring | 1, 1b |
| `boltz_mcp` | Complex structure prediction (iPAE, iPTM) via protein-chain input; SMILES affinity prediction (3-head ensemble) via ligand input | 1, 1b |
| `highfold3_mcp` | AlphaFold3-based cyclic peptide structure prediction with CycPOEM and Cyclization Switch | 2 |
| `gnina_mcp` | CNN-based molecular docking scoring (Gnina/Vina) — **not yet implemented** | 2 |
| `gromacs_mcp` / `amber_mcp` | MD simulations for binding stability evaluation | 3 |

### GPU Assignment Strategy

To avoid GPU memory conflicts and eliminate redundant model reloading, assign each compute-intensive service to a dedicated GPU:

| GPU | Service | Purpose | Notes |
|-----|---------|---------|-------|
| GPU 0 | HELM-GPT (RL optimization) | Sequence generation + permeability scoring | Start `helmgpt_mcp` server with `CUDA_VISIBLE_DEVICES=0` |
| GPU 1 | Boltz-2 server | Complex structure prediction (iPAE, iPTM) | Start Boltz-2 scoring server with `CUDA_VISIBLE_DEVICES=1` |

> **Why separate GPUs:** HELM-GPT RL training keeps the GPT model loaded continuously. Boltz-2 structure prediction is called for every batch as a scoring server. Running both on the same GPU causes OOM errors or forces repeated model unloading/reloading. Dedicated GPUs ensure both models stay resident in memory.
>
> **Note:** The `device` parameter in `submit_optimize_peptides` only accepts `"auto"`, `"cpu"`, or `"cuda"` — NOT `"cuda:0"`. GPU selection must be done via `CUDA_VISIBLE_DEVICES` environment variable when starting the MCP server process.

### Input Requirements
- Target protein PDB file (properly formatted) or target protein sequence
- Prior model file (`.pt`) for HELM-GPT — default: `examples/data/models/prior/perm_agent_final.pt` (permeability-pretrained, vocab=76, n_embd=256, 8-layer GPT). Requires matching `.json` config file at same path.
- Boltz-2 scoring server running and accessible (on dedicated GPU)
- Desired binder length (typically 7-20 residues)

---

## Phase 1: RL-Guided Generation with DL Feedback

HELM-GPT generates synthesizable macrocyclic peptides via reinforcement learning, using Boltz-2 structural metrics and permeability scores as combined rewards. The HELM monomer library (3,104+ monomers) naturally constrains all outputs to synthesizable chemical space, including non-canonical amino acids (ncAAs).

**RL Loop (each step):**
```
1. HELM-GPT generates batch of HELM sequences
2. Convert HELM → SMILES (for permeability scoring via RF model)
3. Score permeability via RF model (fast, ~33 seq/s)
4. Extract amino acid sequence from HELM → feed to Boltz-2 as protein sequence input
5. Boltz-2 complex structure prediction (target + peptide as protein chains) → iPAE, iPTM
6. Compute combined reward = f(permeability, iPAE, iPTM)
7. Update GPT model via REINVENT + CPL loss
```

> **Why protein sequence input for Boltz-2 (not SMILES):** Boltz-2 produces significantly better complex structures when both target and peptide are provided as protein sequences rather than treating the peptide as a SMILES ligand. This is because the protein sequence input leverages Boltz-2's full coevolutionary and structural modeling capabilities, including cyclic-offset positional encodings for head-to-tail cyclization.

### Step 1.1: Check Optimization Requirements

**Tool:** `mcp__helmgpt_mcp__check_optimization_requirements`

**Expected Output:**
- `repo_available`: HELM-GPT repository accessible
- `permeability_model`: Permeability scoring model available
- `kras_model`: KRAS scoring model available
- `cuda_available`: GPU availability
- `python_version`: Current Python version
- `available_prior_models`: List of prior model `.pt` files

**Action:** Ensure prior model, scoring models, and GPU are available before proceeding.

### Step 1.2: Verify Boltz-2 Server Connectivity

**Tool:** `mcp__helmgpt_mcp__get_server_scorer_info`

**Expected Output:**
- `available_scorers`: Should include `"boltz2"`
- `boltz2.default_server`: Server URL and configuration
- `boltz2.supported_scores`: iptm_scores, ipae_scores, affinity_pic50, complex_ipde_scores

**Action:** Confirm Boltz-2 server is accessible. If not, configure `server_host` before proceeding.

### Step 1.3: Review Available Optimization Tasks

**Tool:** `mcp__helmgpt_mcp__get_optimization_tasks`

**Expected Output:**
- Available tasks and their scoring functions
- Default parameters for each task
- Loss function options: `reinvent`, `cpl`, `reinvent_cpl`

### Step 1.4: Submit RL Optimization Job

Start from the permeability-pretrained prior and optimize with multi-objective reward that includes Boltz-2 structural feedback.

**Tool:** `mcp__helmgpt_mcp__submit_optimize_peptides`

**Parameters:**
| Parameter | Recommended | Description |
|-----------|-------------|-------------|
| `prior_model` | Default: `examples/data/models/prior/perm_agent_final.pt` | Path to permeability-pretrained prior `.pt` file (must have matching `.json` config) |
| `task` | `"kras_perm"` | Multi-objective task. Options: `"permeability"`, `"kras_kd"`, `"kras_perm"` |
| `output_dir` | (required) | Directory for results, checkpoints, generated sequences |
| `agent_model` | null | Optional path to existing agent model for continued training |
| `n_steps` | 500-1000 | RL optimization steps |
| `batch_size` | 32 | Sequences generated per step |
| `sigma` | 60 | Augmented likelihood sigma |
| `learning_rate` | 1e-4 | Learning rate for GPT update |
| `loss_type` | `"reinvent_cpl"` | Combined REINVENT + CPL loss (recommended) |
| `alpha` | 1.0 | Alpha weight for CPL component |
| `max_len` | 140 | Maximum HELM sequence length |
| `device` | `"cuda"` | Device for training. Options: `"auto"`, `"cpu"`, `"cuda"`. GPU selection via `CUDA_VISIBLE_DEVICES` env var (see GPU Assignment Strategy) |
| `job_name` | null | Optional job tracking name |

**RL Reward Components:**

| Component | Source | Input Format | Metric | Weight Guidance |
|-----------|--------|--------------|--------|-----------------|
| Permeability | HELM-GPT RF model | SMILES (from HELM) | log cm/s (higher = better) | Maintain from prior |
| Interface confidence | Boltz-2 complex prediction | Protein sequences | iPAE (lower = better) | Primary structural signal |
| Interface quality | Boltz-2 complex prediction | Protein sequences | iPTM (higher = better) | Secondary structural signal |

**Why iPAE and iPTM as primary Boltz-2 metrics:**
- **iPAE** (ipae_scores) directly measures the confidence of the predicted peptide-target interface — the most relevant signal for binder design
- **iPTM** (iptm_scores) measures interface predicted TM-score (0-1), assessing the overall quality of the predicted complex
- Both are reliable outputs from Boltz-2 complex structure prediction when using protein sequence input
- Additional available scores: `affinity_pic50` (predicted binding affinity), `complex_ipde_scores` (interface distance error)

**Note on Contrastive Preference Learning (CPL):**
CPL learns binary preferences between pairs of generated peptides within each batch, reducing the likelihood of low-scoring molecules more effectively than standard REINVENT alone.

### Step 1.5: Monitor RL Training

**Tools:**
- `mcp__helmgpt_mcp__get_job_status` - Check job state
- `mcp__helmgpt_mcp__get_job_log` - View training logs and reward progression

**Monitoring Strategy:**
1. Check status every 30-60 seconds
2. Watch for reward convergence in logs
3. Monitor individual score components:
   - Permeability scores (target: > -6.0 log cm/s)
   - iPAE scores (target: < 0.30, lower is better)
   - iPTM scores (target: > 0.80, higher is better)
4. Continue until `completed` or `failed`

**Log Interpretation:**
- Increasing average reward = optimization progressing
- Plateau in reward = convergence (may stop early or increase `n_steps`)
- Decreasing diversity = mode collapse (reduce `sigma` or increase temperature)

### Step 1.6: Retrieve Generated Sequences

**Tool:** `mcp__helmgpt_mcp__get_job_result`

**Expected Output:**
- Optimized HELM sequences in output directory (CSV with HELM column)
- Training logs with reward progression
- Agent model checkpoint (for potential further optimization)

### Step 1.7: Post-RL Quality Filtering

After RL completes, apply explicit filters to select top candidates for Phase 2.

#### Step 1.7a: Validate HELM Notation

**Tool:** `mcp__helmgpt_mcp__validate_helm_notation`

**Parameters:**
- `helm_input`: HELM string to validate

**Action:** Remove any sequences that fail HELM validation (rare with properly trained prior).

#### Step 1.7b: Convert HELM to SMILES (batch)

**Tool:** `mcp__helmgpt_mcp__helm_to_smiles` (synchronous) or `mcp__helmgpt_mcp__submit_helm_to_smiles_batch` (async, for >1000 sequences)

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `helm_input` | null | Single HELM string to convert (alternative to input_file) |
| `input_file` | null | CSV file with HELM sequences from RL output |
| `output_file` | null | Path to save results with SMILES column |
| `helm_column` | "HELM" | Column name in CSV |
| `limit` | null | Maximum number of sequences to process |

> Note: Either `helm_input` or `input_file` should be provided (mutually exclusive).

#### Step 1.7c: Score Permeability (explicit verification)

**Tool:** `mcp__helmgpt_mcp__predict_permeability` (synchronous) or `mcp__helmgpt_mcp__submit_permeability_batch` (async, for >1000 sequences)

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `helm_input` | null | Single HELM string to predict (alternative to input_file) |
| `input_file` | null | CSV file with HELM sequences |
| `output_file` | null | Path to save permeability predictions |
| `helm_column` | "HELM" | Column name in CSV |
| `limit` | null | Maximum number of sequences to process |
| `include_statistics` | true | Include summary statistics |

> Note: Either `helm_input` or `input_file` should be provided.

**Threshold:** Permeability > -6.0 log cm/s

#### Step 1.7d: Score with Boltz-2 (explicit verification)

Use Boltz-2 complex structure prediction with **protein sequence input** (not SMILES) for both the target protein and the cyclic peptide. This produces significantly better complex structures.

**Tool:** `mcp__helmgpt_mcp__score_with_server` (synchronous) or `mcp__helmgpt_mcp__submit_server_scoring` (async, for large batches)

**Parameters:**
| Parameter | Value | Description |
|-----------|-------|-------------|
| `helm_input` | null | Single HELM or amino acid sequence (alternative to input_file) |
| `input_file` | null | CSV with amino acid sequences (extracted from HELM) |
| `scorer_type` | `"boltz2"` | Use Boltz-2 complex structure prediction (default is `"rosetta"` — must set explicitly) |
| `server_host` | null | Boltz-2 server URL (uses config default) |
| `server_api` | null | API endpoint override (default: /biology/mit/boltz2/predict) |
| `target_scores` | null | JSON string of score configurations, e.g. `'{"iptm_scores": {"weight": 1.0}, "ipae_scores": {"weight": 1.0}}'` |
| `output_file` | null | Path to save scoring results |
| `timeout` | 300 | Request timeout in seconds |
| `include_raw_scores` | true | Include raw iPAE, iPTM scores |
| `limit` | null | Maximum number of sequences to process |

> **Important:** Feed the peptide as an amino acid sequence (protein chain), NOT as SMILES. The target protein and peptide should both be provided as protein sequences to Boltz-2. This leverages Boltz-2's coevolutionary modeling and cyclic-offset positional encodings.

**Key Boltz-2 Metrics (from complex structure prediction):**

| Metric | Threshold | Description |
|--------|-----------|-------------|
| iPAE (ipae_scores) | < 0.30 | Interface predicted aligned error (primary, lower is better) |
| iPTM (iptm_scores) | > 0.80 | Interface predicted TM-score (0-1, higher is better) |
| affinity_pic50 | informational | Predicted binding affinity as pIC50 (higher is stronger) |
| complex_ipde_scores | informational | Complex interface predicted distance error |

### Step 1.8: Select Top Candidates

```
For each generated sequence:
    IF HELM valid
       AND permeability > -6.0 log cm/s
       AND iPAE < 0.30
       AND iPTM > 0.80:
        → PASS: Proceed to Phase 2
    ELSE IF iPAE < 0.40 AND iPTM > 0.70:
        → MARGINAL: Consider for Phase 2 with lower priority
    ELSE:
        → DISCARD
```

**Recommended:** Select top 20-50 candidates for Phase 2 affinity validation.

---

## Phase 1b: Boltz-2 SMILES Affinity Prediction

After Phase 1 DL filtering (iPAE/iPTM from protein-chain input), candidates undergo Boltz-2 affinity prediction using **SMILES ligand input** to properly model non-canonical amino acid chemistry (N-methylation, D-amino acids, piperidine caps) that protein-chain input cannot represent.

### Step 1b.1: Convert HELM to SMILES

**Tool:** `mcp__helmgpt_mcp__helm_to_smiles`

**Purpose:** Convert HELM notation to SMILES, preserving ncAA chemistry (stereochemistry, N-methylation, D-amino acids, sidechain cyclization, piperidine caps).

### Step 1b.2: Submit Boltz-2 Affinity Prediction (SMILES mode)

**Tool:** `mcp__boltz_mcp__submit_affinity_prediction`

**Parameters:**
| Parameter | Value | Description |
|-----------|-------|-------------|
| `protein_sequence` | Target protein sequence | Full-length target (e.g., KRAS 165 aa) |
| `ligand_smiles` | Cyclic peptide SMILES | From HELM→SMILES conversion (Step 1b.1) |
| `use_msa_server` | true | MSA for better accuracy |
| `output_format` | "pdb" | PDB output for downstream use |
| `accelerator` | "gpu" | GPU acceleration |

> **Why SMILES input:** Boltz-2 protein-chain input treats the peptide as canonical amino acids, ignoring ncAA modifications. SMILES input treats the peptide as a small molecule ligand, preserving the exact chemistry (N-methylated backbone, D-stereochemistry, non-standard caps). This gives complementary affinity predictions.

> **MSA reuse:** For screening multiple peptides against the same target, compute MSA once and reuse via `msa_path` parameter (saves ~5-10 min per job).

### Step 1b.3: Collect Boltz-2 Ensemble Affinity Metrics

Boltz-2 affinity prediction produces **three independent affinity prediction heads** (ensemble) plus confidence metrics:

**Affinity Metrics (from `affinity_*.json`):**

| Metric | Description | Interpretation |
|--------|-------------|----------------|
| `affinity_pred_value` | Primary affinity prediction (pKd-like) | Higher = stronger binding |
| `affinity_probability_binary` | Primary binding probability (0-1) | > 0.5 = likely binder |
| `affinity_pred_value1` | Secondary affinity head prediction | Higher = stronger binding |
| `affinity_probability_binary1` | Secondary binding probability | Ensemble consistency check |
| `affinity_pred_value2` | Tertiary affinity head prediction | Higher = stronger binding |
| `affinity_probability_binary2` | Tertiary binding probability | Ensemble consistency check |

**Confidence Metrics (from `confidence_*.json`):**

| Metric | Description | Interpretation |
|--------|-------------|----------------|
| `confidence_score` | Overall model confidence | Higher is better |
| `iptm` / `ligand_iptm` | Interface predicted TM-score | Higher = better complex |
| `ptm` | Predicted TM-score | Higher = better fold |
| `complex_plddt` | Complex per-residue confidence | Higher is better |
| `complex_iplddt` | Interface per-residue confidence | Higher = better interface |
| `complex_ipde` | Interface predicted distance error | Lower = more accurate |

### Step 1b.4: Ensemble Affinity Filtering

Use consensus across the three affinity heads for robust filtering:

```
For each candidate:
    # Ensemble affinity consensus
    avg_affinity = mean(affinity_pred_value, affinity_pred_value1, affinity_pred_value2)
    avg_prob = mean(affinity_probability_binary, affinity_probability_binary1, affinity_probability_binary2)
    n_heads_positive = count(head > 0 for head in [pred_value, pred_value1, pred_value2])

    IF avg_prob > 0.5 AND n_heads_positive >= 2 AND ligand_iptm > 0.70:
        → HIGH CONFIDENCE BINDER: Proceed to Phase 2
    ELSE IF avg_prob > 0.4 AND n_heads_positive >= 1 AND ligand_iptm > 0.60:
        → MARGINAL: Consider for Phase 2
    ELSE:
        → DISCARD: Weak predicted affinity
```

**Recommended:** Select top 10-30 candidates for Phase 2 structure prediction & docking.

---

## Phase 2: Structure Prediction & Docking Validation (HighFold3 + Gnina)

Top candidates from Phase 1b are subjected to HighFold3 cyclic peptide structure prediction and Gnina docking scoring for independent binding validation.

### Step 2.1: HighFold3 Cyclic Peptide Structure Prediction

**Tool:** `mcp__highfold3_mcp__submit_cyclic_peptide_prediction`

Predicts the 3D structure of each cyclic peptide candidate using AlphaFold3-based HighFold3 with **CycPOEM** (Cyclic Position Offset Encoding Matrix) and **Cyclization Switch** for head-to-tail cyclization modeling.

**Parameters:**
| Parameter | Value | Description |
|-----------|-------|-------------|
| `sequence` | Amino acid sequence | One-letter codes (e.g., "AVVFLAD") |
| `output_dir` | (optional) | Custom output directory |
| `name` | (optional) | Name for the prediction |
| `config` | (optional) | Custom config file path |
| `job_name` | (optional) | Job tracking name |

**Runtime:** 15-60 minutes per peptide

> **Note on complex prediction:** HighFold3 also provides `submit_cyclic_peptide_protein_complex_prediction` for peptide-protein complexes, but currently supports limited protein types (PDZ_domain, SH3_domain, WW_domain). For arbitrary targets like KRAS, use `submit_cyclic_peptide_prediction` for peptide structure, then Gnina docking against the target PDB.

**Batch submission:**
For multiple candidates, use `mcp__highfold3_mcp__submit_batch_peptide_prediction` (max 20 per batch):
```
sequences = ["AVVFLAD", "AGFFLVLLGVF", "ATFFILLD", ...]
prediction_type = "cyclic"
```

### Step 2.2: Monitor HighFold3 Jobs

**Tools:**
- `mcp__highfold3_mcp__get_job_status` — Check progress with elapsed time and ETA
- `mcp__highfold3_mcp__get_job_log` — View execution logs
- `mcp__highfold3_mcp__list_jobs` — List all submitted jobs

### Step 2.3: Gnina Docking Scoring

**Tool:** `gnina_mcp` (TODO: MCP not yet implemented — see below for planned interface)

**Purpose:**
1. Dock HighFold3-predicted cyclic peptide structures against target protein PDB
2. Score binding poses using Gnina's CNN scoring function (trained on PDBBind)
3. Provides physics-informed binding affinity estimates complementary to DL predictions

**Planned Parameters:**
| Parameter | Value | Description |
|-----------|-------|-------------|
| `receptor_pdb` | Target PDB file | KRAS or other target protein |
| `ligand_pdb` | Peptide PDB from HighFold3 | Cyclic peptide structure |
| `exhaustiveness` | 8-32 | Search thoroughness |
| `num_modes` | 9 | Number of binding modes to generate |
| `cnn_scoring` | "rescore" | Use CNN for rescoring Vina poses |

**Expected Output Metrics:**
| Metric | Description | Direction |
|--------|-------------|-----------|
| CNN score | Gnina CNN binding score | Higher = better |
| CNN affinity (pKd) | Predicted -log(Kd) | Higher = stronger binding |
| Vina score (kcal/mol) | AutoDock Vina energy | More negative = better |

> **Gnina MCP Status:** Not yet implemented. To proceed without Gnina, use Boltz-2 ensemble affinity + HighFold3 confidence as Phase 2 filters. Gnina can be added later as an additional orthogonal validation.

### Step 2.4: Phase 2 Filtering & Ranking

```
For each candidate:
    # HighFold3 structure quality
    IF HighFold3 pLDDT > 0.70:
        → Structure is reliable for docking

    # Gnina docking (when available)
    IF CNN_affinity > 6.0 (pKd) AND Vina_score < -7.0 kcal/mol:
        → HIGH PRIORITY: Strong docking hit
    ELSE IF CNN_affinity > 5.0 AND Vina_score < -5.0:
        → MEDIUM PRIORITY: Moderate docking hit

    # Combined ensemble filter (Boltz-2 affinity + HighFold3 + Gnina)
    Rank by: ensemble_affinity_score × HighFold3_confidence × Gnina_CNN_score
```

**Recommended:** Select top 5-15 candidates for Phase 3 MD evaluation.

---

## Phase 3: MD Simulation Final Evaluation

Top candidates from Phase 2 are subjected to molecular dynamics simulations to evaluate binding stability and dynamics.

### Step 3.1: System Preparation & MD Simulation

**Tool:** `mcp__gromacs_mcp__submit_*` or `mcp__amber_mcp__submit_*` (TODO: confirm tool names)

**Purpose:**
1. Prepare peptide-target complex for MD (solvation, ion addition, energy minimization)
2. Run production MD (recommended: 100-500 ns) to assess binding stability
3. Evaluate RMSD, interaction persistence, binding free energy estimates

### Step 3.2: MD Analysis & Final Selection

**Evaluation Criteria:**
- **Binding stability:** Peptide RMSD relative to initial binding pose (< 3 Å = stable)
- **Interaction persistence:** Key hydrogen bonds and contacts maintained > 80% of trajectory
- **Binding free energy:** MM-PBSA or MM-GBSA estimates (more negative = better)
- **Conformational sampling:** Peptide maintains cyclic conformation throughout simulation

### Combined Ranking

Rank final candidates using a composite score across all phases:

| Metric | Weight | Source | Phase | Direction |
|--------|--------|--------|-------|-----------|
| iPAE (protein input) | 0.10 | Boltz-2 | 1 | Lower is better |
| iPTM (protein input) | 0.10 | Boltz-2 | 1 | Higher is better |
| Permeability | 0.10 | HELM-GPT | 1 | Higher is better |
| Ensemble avg affinity | 0.15 | Boltz-2 SMILES | 1b | Higher is better |
| Ensemble avg prob | 0.10 | Boltz-2 SMILES | 1b | Higher is better |
| Gnina CNN affinity | 0.15 | Gnina | 2 | Higher is better |
| MD binding stability | 0.15 | GROMACS/Amber | 3 | Lower RMSD is better |
| MM-PBSA ΔG | 0.15 | GROMACS/Amber | 3 | Lower is better |

### Selection Strategy
- Select top 5-10 designs for experimental testing
- Ensure structural diversity (different binding modes / ncAA compositions)
- Prioritize designs with stable MD trajectories and strong docking scores
- Include 1-2 designs with novel ncAA scaffolds for chemical diversity

---

## Quality Thresholds Reference Table

| Metric | Excellent | Good | Acceptable | Source | Phase |
|--------|-----------|------|------------|--------|-------|
| Permeability | > -5.0 | > -6.0 | > -6.5 | HELM-GPT RF | 1 |
| iPAE (protein input) | < 0.20 | < 0.30 | < 0.40 | Boltz-2 | 1 |
| iPTM (protein input) | > 0.90 | > 0.80 | > 0.70 | Boltz-2 | 1 |
| Ensemble avg affinity | > 0.5 | > 0.0 | > -0.3 | Boltz-2 SMILES | 1b |
| Ensemble avg prob | > 0.6 | > 0.5 | > 0.4 | Boltz-2 SMILES | 1b |
| Ligand iPTM (SMILES) | > 0.80 | > 0.70 | > 0.60 | Boltz-2 SMILES | 1b |
| Complex iPLDDT (SMILES) | > 0.70 | > 0.50 | > 0.35 | Boltz-2 SMILES | 1b |
| Complex iPDE (SMILES) | < 1.5 | < 2.5 | < 3.5 | Boltz-2 SMILES | 1b |
| HighFold3 pLDDT | > 0.85 | > 0.70 | > 0.60 | HighFold3 | 2 |
| Gnina CNN affinity (pKd) | > 7.0 | > 6.0 | > 5.0 | Gnina | 2 |
| Gnina Vina score | < -8.0 | < -7.0 | < -5.0 | Gnina | 2 |
| MD peptide RMSD | < 2.0 Å | < 3.0 Å | < 5.0 Å | GROMACS/Amber | 3 |
| MM-PBSA ΔG | < -30 | < -20 | < -10 | GROMACS/Amber | 3 |

---

## Output Format

Present final results in this format:

```markdown
## HELM-GPT Binder Design Results

### Job Summary
| Parameter | Value |
|-----------|-------|
| Target | {target_name} |
| Prior Model | {prior_model_path} |
| RL Steps | {n_steps} |
| Loss Type | {loss_type} |
| Sequences Generated | {total_generated} |
| Phase 1 Passed | {phase1_passed} |
| Phase 2 Passed (docking) | {phase2_passed} |
| Phase 3 Passed (MD) | {phase3_passed} |

### Top Designs

#### Design 1: {design_id}
| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| HELM | `{helm_sequence}` | - | - |
| Permeability | {value} log cm/s | > -6.0 | PASS/FAIL |
| iPAE (protein) | {value} | < 0.30 | PASS/FAIL |
| iPTM (protein) | {value} | > 0.80 | PASS/FAIL |
| Ensemble avg affinity | {value} | > 0.0 | PASS/FAIL |
| Ensemble avg prob | {value} | > 0.5 | PASS/FAIL |
| Ligand iPTM (SMILES) | {value} | > 0.70 | PASS/FAIL |
| Gnina CNN affinity | {value} pKd | > 6.0 | PASS/FAIL |
| MD RMSD | {value} Å | < 3.0 | PASS/FAIL |
| MM-PBSA ΔG | {value} kcal/mol | < -20 | PASS/FAIL |

**Contains ncAAs:** {yes/no}
**Output File:** `{output_path}`

[Repeat for additional designs]

### Recommended for Synthesis
1. {design_id_1} - Best composite score
2. {design_id_2} - Best iPAE + ddG
3. {design_id_3} - Most novel ncAA scaffold
```

---

## Error Handling

### Phase 1: RL + Boltz-2 Scoring Issues
- **No convergence:** Increase `n_steps`, reduce `learning_rate`, or try `loss_type="reinvent"` first
- **GPU OOM:** Reduce `batch_size` to 16 or 8
- **Prior model not found:** Use `check_optimization_requirements` to locate available models
- **Boltz-2 server unreachable:** Check `server_host` with `get_server_scorer_info`; verify server is running
- **High iPAE across all designs:** Target may be challenging; consider different target region or longer peptide
- **Low diversity / mode collapse:** Reduce `sigma` or increase `batch_size`

### Phase 1b: Boltz-2 SMILES Affinity Issues
- **HELM→SMILES conversion failure:** Check HELM syntax; ensure cyclization link format is correct (`1:R1-N:R3`)
- **All affinity heads negative:** Peptide may not bind as small molecule; check SMILES validity with RDKit
- **Inconsistent ensemble heads:** Low confidence in prediction; rely more on protein-chain iPAE/iPTM
- **MSA timeout:** Use pre-computed MSA via `msa_path` parameter for faster reruns

### Phase 2: HighFold3 + Gnina Issues
- **Low HighFold3 pLDDT:** Peptide structure may be poorly predicted; try different peptide lengths or check sequence
- **HighFold3 complex prediction limited:** Only PDZ/SH3/WW domains supported for complex; use standalone cyclic peptide prediction + Gnina docking instead
- **Poor docking score:** Binding pose may be unfavorable; consider alternative binding regions or increase `exhaustiveness`
- **Gnina scoring failure:** Check ligand/receptor PDB formatting and chain assignments

### Phase 3: MD Simulation Issues
- **High RMSD drift:** Peptide dissociates during MD; binding pose unstable — discard candidate
- **System preparation failure:** Check protonation states, missing atoms, or force field compatibility
- **Simulation crash:** Reduce timestep, check for steric clashes, or extend equilibration

---

## Example Usage

### Standard Binder Design
```
Design synthesizable cyclic peptide binders using HELM-GPT:
- Prior model: models/permeability_prior.pt (pre-trained with permeability)
- 1000 RL steps with reinvent_cpl loss
- Boltz-2 complex prediction (protein sequence input) for iPAE, iPTM as RL rewards
- Filter: permeability > -6.0, iPAE < 0.30, iPTM > 0.80
- Validate top 30 with HighFold3 structure prediction + Gnina docking
- Run MD simulations on top 10 for final binding stability evaluation
```

### ncAA-Enriched Design
```
Design ncAA-containing cyclic peptide binders:
- Use HELM-GPT with full 3104-monomer library
- 500 RL steps with Boltz-2 structural feedback (protein sequence input)
- HighFold3 + Gnina docking validation
- MD simulation of top candidates
- Select top 10 diverse designs for synthesis
```

### High-Throughput Screening
```
Generate diverse binder candidates using HELM-GPT:
- 2000 RL steps, batch_size=64
- Boltz-2 iPAE + iPTM + permeability as rewards
- Select top 50 by DL metrics
- HighFold3 + Gnina docking filtering
- MD simulation of top 10-20
- Cluster and select top 10 diverse designs
```

---

## MCP Tools Quick Reference

| Phase | MCP Server | Tool | Purpose |
|-------|------------|------|---------|
| 1 | helmgpt_mcp | `check_optimization_requirements` | Verify setup |
| 1 | helmgpt_mcp | `get_server_scorer_info` | Verify Boltz-2 server |
| 1 | helmgpt_mcp | `get_optimization_tasks` | List available tasks |
| 1 | helmgpt_mcp | `submit_optimize_peptides` | RL optimization with DL feedback |
| 1 | helmgpt_mcp | `get_job_status` / `get_job_log` | Monitor training |
| 1 | helmgpt_mcp | `get_job_result` | Retrieve optimized sequences |
| 1 | helmgpt_mcp | `validate_helm_notation` | HELM validity check |
| 1 | helmgpt_mcp | `helm_to_smiles` | Convert HELM to SMILES |
| 1 | helmgpt_mcp | `predict_permeability` | Permeability verification |
| 1 | helmgpt_mcp | `score_with_server` (boltz2) | Boltz-2 iPAE/iPTM scoring (protein seq input) |
| 1b | boltz_mcp | `submit_affinity_prediction` | SMILES affinity prediction (3-head ensemble) |
| 1b | boltz_mcp | `get_job_status` / `get_job_result` | Monitor & retrieve affinity results |
| 2 | highfold3_mcp | `submit_cyclic_peptide_prediction` | Cyclic peptide structure (CycPOEM) |
| 2 | highfold3_mcp | `submit_batch_peptide_prediction` | Batch cyclic peptide structures |
| 2 | gnina_mcp | (TODO — not yet implemented) | CNN docking scoring |
| 2 | highfold3_mcp | `get_job_status` / `get_job_result` | Monitor & retrieve |
| 3 | gromacs_mcp / amber_mcp | `submit_*` | MD simulation |
| 3 | gromacs_mcp / amber_mcp | `get_job_status` / `get_job_result` | Monitor & retrieve |

---

## Key Differences from RFpeptides Workflow

| Aspect | RFpeptides Workflow | HELM-GPT Workflow |
|--------|--------------------|--------------------|
| Sequence space | Canonical amino acids only | 3,104+ monomers (incl. ncAAs) |
| Design engine | ProteinMPNN (structure-based) | HELM-GPT RL (generative) |
| Backbone source | RFdiffusion de novo | Boltz-2 structure prediction |
| Permeability | Not optimized | Pre-trained prior + RL reward |
| Synthesizability | Requires post-hoc check | Built-in via HELM library |
| DL feedback | AfCycDesign reprediction (post-hoc) | Boltz-2 iPAE/iPTM (in-loop, protein seq input) |
| Structural scoring | AfCycDesign iPAE | Boltz-2 iPAE + iPTM (complex prediction) |
| Affinity validation | - | Boltz-2 SMILES 3-head ensemble affinity |
| Structure prediction | - | HighFold3 CycPOEM cyclic peptide structures |
| Docking validation | - | Gnina CNN docking scoring |
| Final evaluation | - | MD simulations (GROMACS/Amber) |
| Workflow phases | 5 phases | 3 phases (1, 1b, 2, 3) |

---

## Related Workflows

- `binder_design_rfpeptides.md` - RFpeptides backbone-first binder design (5-stage)
- `binder_design_afcycdesign.md` - AfCycDesign-only binder design

## References

- HELM-GPT: GPT-based generative model for macrocyclic peptide design with HELM notation
- Boltz-2: Biomolecular complex structure prediction (iPAE, iPTM) and SMILES-based affinity prediction (3-head ensemble)
- HighFold3: AlphaFold3-based structure prediction with CycPOEM cyclic positional encoding and Cyclization Switch
- Gnina: CNN-based molecular docking with learned scoring functions (Vina + CNN)
- GROMACS / Amber: Molecular dynamics simulation suites for binding stability evaluation
- CycPeptMPDB: Cyclic peptide membrane permeability database
- REINVENT + CPL: Reinforcement learning with contrastive preference learning for molecular optimization
