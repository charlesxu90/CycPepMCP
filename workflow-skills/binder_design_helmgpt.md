# HELM-GPT Generative-to-Physics Binder Design Workflow

> Cyclic peptide binder design integrating HELM-GPT generative optimization with Boltz-2 structural feedback and Rosetta physics-based validation

## Overview

This skill implements a two-phase "Generative-to-Physics" pipeline for designing synthesizable macrocyclic peptide binders. The workflow uses HELM-GPT as the generative engine with a multi-objective RL loop that incorporates Boltz-2 complex structure prediction metrics (iPAE, iPTM) and permeability scoring as real-time rewards, followed by Rosetta physics-based filtering for final candidate selection.

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
PHASE 2: Physics-Based Validation & Final Selection (Rosetta)
    FastRelax with PeptideCyclizeMover → ddG, SAP, CMS filtering → ranking
```

## Prerequisites

### Required MCP Servers
| MCP Server | Purpose | Phase(s) |
|------------|---------|----------|
| `helmgpt_mcp` | Sequence generation, RL optimization, permeability scoring, Boltz-2 server scoring | 1 |
| `boltz_mcp` | Complex structure prediction (iPAE, iPTM) — accessed via `helmgpt_mcp` `score_with_server` (scorer_type="boltz2"), or directly for standalone prediction | 1 |
| `rosetta_kic_mcp` | Structure refinement, interface metrics (ddG, SAP, CMS) | 2 |

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
- Prior model file (`.pt`) for HELM-GPT (pre-trained on ChEMBL/CycPeptMPDB with permeability optimization)
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
| `prior_model` | (required) | Path to permeability-pretrained prior `.pt` file |
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

**Recommended:** Select top 20-50 candidates for Phase 2 Rosetta validation.

---

## Phase 2: Physics-Based Validation & Final Selection (Rosetta)

Top candidates from Phase 1 are subjected to Rosetta physics-based refinement and interface metric computation to identify the final designs for synthesis.

### Step 2.1: Rosetta FastRelax with PeptideCyclizeMover

**Tool:** `mcp__rosetta_kic_mcp__submit_cycpep_fast_relax`

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `input_file` | (required) | PDB file from Boltz-2 structure prediction |
| `rounds` | 4 | Number of FastRelax rounds |
| `xml` | null | Optional custom RosettaScripts XML |
| `job_name` | null | Job identifier |

**Purpose:**
1. Minimize the complex using the beta_nov16 score function
2. Apply PeptideCyclizeMover before and after FastRelax to maintain the terminal peptide bond
3. Peptide chain fully movable; target interface sidechains repack; non-interface residues frozen
4. Resolve steric clashes from structure prediction

> **Note:** The input PDB should come from the Boltz-2 structure prediction output during Phase 1 scoring. Verify chain assignments before submission.

### Step 2.2: Monitor Relaxation

**Tools:**
- `mcp__rosetta_kic_mcp__get_job_status`
- `mcp__rosetta_kic_mcp__get_job_log`

### Step 2.3: Compute Interface Metrics (ddG, SAP, CMS)

**Tool:** `mcp__rosetta_kic_mcp__submit_interface_metrics`

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `input_files` | (required) | List of relaxed PDB file paths |
| `peptide_chain` | "A" | Peptide chain ID in PDB |
| `ddg_threshold` | -40.0 | ddG filter (more negative = better) |
| `sap_threshold` | 35.0 | SAP filter (lower = better) |
| `cms_threshold` | 300.0 | CMS filter in Angstroms squared (higher = better) |
| `job_name` | null | Job identifier |

> **Chain Convention:** Verify the chain assignment from Boltz-2 output. Adjust `peptide_chain` if Boltz-2 places the peptide on a chain other than A.

### Step 2.4: Retrieve and Evaluate Metrics

**Tool:** `mcp__rosetta_kic_mcp__get_job_result`

**Output:**
- Per-structure ddG, SAP, CMS values
- Pass/fail status per structure
- CSV with all metrics

#### Metric Descriptions

**ddG (Interface Binding Energy)**
- Rosetta ddG via InterfaceAnalyzer protocol
- **Thresholds:**
  - Excellent: ddG < -50 REU
  - Good: ddG < -30 REU
  - Acceptable: ddG < -20 REU

**SAP (Spatial Aggregation Propensity)**
- Measures surface hydrophobicity / aggregation risk
- **Threshold:** SAP < 35
- Lower = better solubility, less aggregation

**CMS (Contact Molecular Surface)**
- Interface contact surface area
- **Threshold:** CMS > 300 Angstroms squared
- Higher = more extensive binding interface

### Step 2.5: Final Filtering & Ranking

```
For each relaxed design:
    IF ddG < -30 AND SAP < 35 AND CMS > 300:
        → HIGH PRIORITY: Strong predicted binder for synthesis
    ELSE IF ddG < -20 AND SAP < 45 AND CMS > 200:
        → MEDIUM PRIORITY: Acceptable candidate
    ELSE:
        → LOW PRIORITY: Discard or redesign
```

### Combined Ranking

Rank final candidates using a composite score across both phases:

| Metric | Weight | Source | Direction |
|--------|--------|--------|-----------|
| ddG | 0.30 | Rosetta | Lower is better |
| iPAE | 0.25 | Boltz-2 | Lower is better |
| Permeability | 0.20 | HELM-GPT | Higher is better |
| iPTM | 0.15 | Boltz-2 | Higher is better |
| SAP | 0.10 | Rosetta | Lower is better |

### Selection Strategy
- Select top 5-10 designs for experimental testing
- Ensure structural diversity (different binding modes / ncAA compositions)
- Prioritize designs passing all strict thresholds
- Include 1-2 designs with novel ncAA scaffolds for chemical diversity

---

## Quality Thresholds Reference Table

| Metric | Excellent | Good | Acceptable | Source |
|--------|-----------|------|------------|--------|
| Permeability | > -5.0 | > -6.0 | > -6.5 | HELM-GPT RF |
| iPAE (ipae_scores) | < 0.20 | < 0.30 | < 0.40 | Boltz-2 |
| iPTM (iptm_scores) | > 0.90 | > 0.80 | > 0.70 | Boltz-2 |
| ddG | < -50 REU | < -30 REU | < -20 REU | Rosetta |
| SAP | < 25 | < 35 | < 45 | Rosetta |
| CMS | > 400 sq A | > 300 sq A | > 200 sq A | Rosetta |

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
| Phase 2 Passed | {phase2_passed} |

### Top Designs

#### Design 1: {design_id}
| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| HELM | `{helm_sequence}` | - | - |
| Permeability | {value} log cm/s | > -6.0 | PASS/FAIL |
| iPAE | {value} | < 0.30 | PASS/FAIL |
| iPTM | {value} | > 0.80 | PASS/FAIL |
| ddG | {value} REU | < -30 | PASS/FAIL |
| SAP | {value} | < 35 | PASS/FAIL |
| CMS | {value} sq A | > 300 | PASS/FAIL |

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

### Phase 2: Rosetta Issues
- **Poor ddG:** Interface may be unfavorable; consider longer peptide or different binding region
- **High SAP:** Too many exposed hydrophobic residues; designs may be aggregation-prone
- **Low CMS:** Insufficient contact surface; try longer binder length
- **Relax crash:** Check for severe clashes in input PDB; reduce `rounds`
- **Chain assignment mismatch:** Verify Boltz-2 output chain IDs match Rosetta `peptide_chain` parameter

---

## Example Usage

### Standard Binder Design
```
Design synthesizable cyclic peptide binders using HELM-GPT:
- Prior model: models/permeability_prior.pt (pre-trained with permeability)
- 1000 RL steps with reinvent_cpl loss
- Boltz-2 complex prediction (protein sequence input) for iPAE, iPTM as RL rewards
- Filter: permeability > -6.0, iPAE < 0.30, iPTM > 0.80
- Validate top 30 with Rosetta ddG < -30, SAP < 35, CMS > 300
```

### ncAA-Enriched Design
```
Design ncAA-containing cyclic peptide binders:
- Use HELM-GPT with full 3104-monomer library
- 500 RL steps with Boltz-2 structural feedback (protein sequence input)
- Rank by composite score (ddG + iPAE + permeability)
- Select top 10 diverse designs for synthesis
```

### High-Throughput Screening
```
Generate diverse binder candidates using HELM-GPT:
- 2000 RL steps, batch_size=64
- Boltz-2 iPAE + iPTM + permeability as rewards
- Select top 50 by DL metrics
- Apply Rosetta physics filters
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
| 2 | rosetta_kic_mcp | `submit_cycpep_fast_relax` | Structure relaxation |
| 2 | rosetta_kic_mcp | `submit_interface_metrics` | ddG, SAP, CMS metrics |
| 2 | rosetta_kic_mcp | `get_job_status` / `get_job_result` | Monitor & retrieve |

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
| Physics validation | Rosetta (same) | Rosetta (same) |
| Workflow phases | 5 phases | 2 phases |

---

## Related Workflows

- `binder_design_rfpeptides.md` - RFpeptides backbone-first binder design (5-stage)
- `binder_design_afcycdesign.md` - AfCycDesign-only binder design

## References

- HELM-GPT: GPT-based generative model for macrocyclic peptide design with HELM notation
- Boltz-2: Biomolecular complex structure prediction (iPAE, iPTM — protein sequence input preferred over SMILES)
- Rosetta: Macromolecular modeling suite with PeptideCyclizeMover
- CycPeptMPDB: Cyclic peptide membrane permeability database
- REINVENT + CPL: Reinforcement learning with contrastive preference learning for molecular optimization
