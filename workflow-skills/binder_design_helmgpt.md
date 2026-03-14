# HELM-GPT KRAS Binder Design Workflow

> Cyclic peptide KRAS binder design using HELM-GPT RL co-optimization (permeability + KRAS binding), heavy-atom-routed structural evaluation (Boltz-2 / AlphaFold3 / Gnina), and composite scoring for final selection

## Overview

This workflow implements a streamlined three-phase pipeline for designing synthesizable macrocyclic peptide binders against KRAS. HELM-GPT drives RL optimization using **fast local scoring models** (XGBoost KRAS binding + RF permeability) — no external Boltz-2 server needed during training. Candidates are then routed by heavy atom count for structural evaluation: small peptides (≤128 heavy atoms) get Boltz-2 SMILES affinity + AlphaFold3 + Gnina; larger peptides get AlphaFold3 + Gnina only.

**Key Design Choices:**
- RL rewards are fast local models (XGBoost + RF), not slow DL servers — 1 GPU sufficient for Phase 1
- Heavy atom routing at 128 atoms: Boltz-2 SMILES affinity has a 128-atom ligand limit
- AlphaFold3 runs for ALL candidates via `ligand_smiles` input (captures exact ncAA chemistry)
- Gnina docking runs for ALL candidates on predicted complex structures
- No MD simulation phase — structural evaluation is sufficient for candidate prioritization

**Protocol Architecture:**
```
PHASE 1: RL Co-optimization (HELM-GPT kras_perm task)
    HELM-GPT generates → XGBoost KRAS KD scoring (fast, local)
                       → RF permeability scoring (fast, local)
                       → combined reward → update GPT model
    ↓
POST-PHASE 1: Candidate Selection & Filtering
    Validate HELM → HELM→SMILES → verify permeability (>-6.0) → verify KD (<10 μM)
    → calculate heavy atom count → route candidates → cap at ≤100 for AF3
    ↓
PHASE 2: Structural Evaluation (Two Parallel Tracks)
    Track A (≤128 heavy atoms): Boltz-2 SMILES affinity → Gnina docking
    Track B (ALL candidates):   AlphaFold3 complex prediction → Gnina docking
    ↓
PHASE 3: Final Selection & Ranking
    Composite scoring (track-dependent weights) → top 5-10 designs
```

## Prerequisites

### Required MCP Servers

| MCP Server | Purpose | Phase(s) |
|------------|---------|----------|
| `helm_gpt_mcp` | RL optimization (`kras_perm`), permeability/KD scoring, HELM→SMILES conversion | 1, Post-1 |
| `boltz_mcp` | SMILES affinity prediction (3-head ensemble), ligand SMILES validation | 2A |
| `alphafold3_mcp` | Protein-ligand complex structure prediction | 2B |
| `gnina_mcp` | CNN-based molecular docking scoring (Gnina + Vina) | 2A, 2B |

### GPU Assignment Strategy

| GPU | Service | Phase | Notes |
|-----|---------|-------|-------|
| GPU 0 | HELM-GPT (RL optimization) | 1 | 1 GPU sufficient — scoring is local (XGBoost + RF) |
| GPU 1 | Boltz-2 (SMILES affinity) | 2A | Only for ≤128 heavy atom candidates |
| GPU 2 | AlphaFold3 (complex prediction) | 2B | All candidates; set `device=2` |

> **Why 1 GPU for Phase 1:** Unlike the old workflow that required a dedicated Boltz-2 scoring server during RL, the `kras_perm` task uses fast local XGBoost and RF models. No external server needed.
>
> **Note:** The `device` parameter in `submit_optimize_peptides` only accepts `"auto"`, `"cpu"`, or `"cuda"` — NOT `"cuda:0"`. GPU selection must be done via `CUDA_VISIBLE_DEVICES` environment variable when starting the MCP server process.

### Input Requirements

- **KRAS target PDB file** — properly formatted protein structure
- **KRAS protein sequence** — for Boltz-2 and AlphaFold3 input
- **Pre-computed KRAS MSA** (`.a3m` file) — pre-computed A3M alignment of the KRAS target sequence. Providing this skips the slow MSA search step (~30-60 min) in both Boltz-2 and AlphaFold3, dramatically speeding up Phase 2. Generate once with MMseqs2 or the AF3 data pipeline.
- **Prior model file** (`.pt`) — default: `examples/data/models/prior/perm_agent_final.pt` (permeability-pretrained, vocab=76, n_embd=256, 8-layer GPT). Requires matching `.json` config file at same path.
- Desired binder length (typically 7-20 residues)

---

## Phase 1: RL Co-optimization (HELM-GPT `kras_perm`)

HELM-GPT generates synthesizable macrocyclic peptides via reinforcement learning, using the `kras_perm` multi-objective task that co-optimizes KRAS binding affinity (XGBoost model) and membrane permeability (RF model). Both scoring models are fast and local — no external server needed.

**RL Loop (each step):**
```
1. HELM-GPT generates batch of HELM sequences
2. Score KRAS binding via XGBoost model (fast, local) → KD in μM
3. Score permeability via RF model (fast, local) → log cm/s
4. Compute combined reward = f(KRAS_KD, permeability)
5. Update GPT model via REINVENT + CPL loss
```

### Step 1.1: Check Optimization Requirements

**Tool:** `mcp__helmgpt_mcp__check_optimization_requirements`

**Expected Output:**
- `repo_available`: HELM-GPT repository accessible
- `kras_model`: KRAS XGBoost scoring model available
- `permeability_model`: Permeability RF scoring model available
- `cuda_available`: GPU availability
- `python_version`: Current Python version
- `available_prior_models`: List of prior model `.pt` files

**Action:** Ensure prior model, both scoring models (`kras_model` + `permeability_model`), and GPU are available before proceeding.

### Step 1.2: Review Available Optimization Tasks

**Tool:** `mcp__helmgpt_mcp__get_optimization_tasks`

**Expected Output:**
- Available tasks including `kras_perm` (multi-objective KRAS + permeability)
- Other options: `permeability`, `kras_kd`
- Default parameters and loss function options

**Action:** Confirm `kras_perm` task is available. This is the recommended task for KRAS binder design as it co-optimizes both binding and permeability.

### Step 1.3: Submit RL Optimization Job

**Tool:** `mcp__helmgpt_mcp__submit_optimize_peptides`

**Parameters:**

| Parameter | Recommended | Description |
|-----------|-------------|-------------|
| `prior_model` | Default: `examples/data/models/prior/perm_agent_final.pt` | Path to permeability-pretrained prior `.pt` file (must have matching `.json` config) |
| `task` | `"kras_perm"` | Multi-objective task: KRAS KD + permeability |
| `output_dir` | (required) | Directory for results, checkpoints, generated sequences |
| `agent_model` | null | Optional path to existing agent model for continued training |
| `n_steps` | 500 (max 1000) | RL steps. Start with 500; only increase to 1000 if reward has not converged |
| `batch_size` | 32 | Sequences generated per step |
| `sigma` | 60 | Augmented likelihood sigma |
| `learning_rate` | 1e-4 | Learning rate for GPT update |
| `loss_type` | `"reinvent_cpl"` | Combined REINVENT + CPL loss (recommended) |
| `alpha` | 1.0 | Alpha weight for CPL component |
| `max_len` | 140 | Maximum HELM sequence length |
| `device` | `"cuda"` | Device for training. Options: `"auto"`, `"cpu"`, `"cuda"`. GPU selection via `CUDA_VISIBLE_DEVICES` env var |
| `job_name` | null | Optional job tracking name |

**RL Reward Components:**

| Component | Source | Model Type | Metric | Target |
|-----------|--------|------------|--------|--------|
| KRAS binding | HELM-GPT local | XGBoost | KD (μM, lower = better) | < 10 μM |
| Permeability | HELM-GPT local | Random Forest | log cm/s (higher = better) | > -6.0 |

> **No Boltz-2 server params needed:** Unlike the old workflow, `kras_perm` uses local scoring models only. No `scorer_type`, `server_host`, or `target_scores` parameters.

**Note on Contrastive Preference Learning (CPL):**
CPL learns binary preferences between pairs of generated peptides within each batch, reducing the likelihood of low-scoring molecules more effectively than standard REINVENT alone.

### Step 1.4: Monitor RL Training

**Tools:**
- `mcp__helmgpt_mcp__get_job_status` — Check job state
- `mcp__helmgpt_mcp__get_job_log` — View training logs and reward progression

**Monitoring Strategy:**
1. Check status every 30-60 seconds
2. Watch for reward convergence in logs
3. Monitor individual score components:
   - KRAS KD (target: < 10 μM, lower is better)
   - Permeability (target: > -6.0 log cm/s, higher is better)
4. Continue until `completed` or `failed`

**Log Interpretation:**
- Increasing average reward = optimization progressing
- Plateau in reward = convergence reached — 500 steps is often sufficient. Only extend to 1000 if reward is still improving
- Decreasing diversity = mode collapse (reduce `sigma` or increase temperature)

### Step 1.5: Retrieve Generated Sequences

**Tool:** `mcp__helmgpt_mcp__get_job_result`

**Expected Output:**
- Optimized HELM sequences in output directory (CSV with HELM column)
- Training logs with reward progression
- Agent model checkpoint (for potential further optimization)

---

## Post-Phase 1: Candidate Selection & Filtering

Sequential filtering pipeline using `helm_gpt_mcp` local tools to select top candidates for structural evaluation.

### Step P1.1: Validate HELM Notation

**Tool:** `mcp__helmgpt_mcp__validate_helm_notation`

**Parameters:**
- `helm_input`: HELM string to validate

**Action:** Remove any sequences that fail HELM validation (rare with properly trained prior).

### Step P1.2: Convert HELM to SMILES

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

### Step P1.3: Score Permeability (explicit verification)

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

### Step P1.4: Score KRAS Binding (explicit verification)

**Tool:** `mcp__helmgpt_mcp__predict_kras_binding` (synchronous) or `mcp__helmgpt_mcp__submit_kras_binding_batch` (async, for >1000 sequences)

**Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `helm_input` | null | Single HELM string to predict (alternative to input_file) |
| `input_file` | null | CSV file with HELM sequences |
| `output_file` | null | Path to save KRAS binding predictions |
| `helm_column` | "HELM" | Column name in CSV |
| `limit` | null | Maximum number of sequences to process |

**Output Fields:**
- `binding_score`: Raw XGBoost binding score
- `kd_value_um`: Predicted dissociation constant in μM
- `interpretation`: Human-readable binding classification

**Threshold:** KD < 10 μM

### Step P1.5: Filter Candidates

```
For each generated sequence:
    IF HELM valid
       AND permeability > -6.0 log cm/s
       AND KD < 10 μM:
        → PASS: Proceed to Phase 2
    ELSE IF permeability > -6.5 AND KD < 100 μM:
        → MARGINAL: Consider for Phase 2 with lower priority
    ELSE:
        → DISCARD
```

### Step P1.6: Calculate Heavy Atom Count & Route Candidates

Use `mcp__boltz_mcp__validate_ligand_smiles` to determine heavy atom count for each candidate's SMILES. This tool returns `num_atoms` (heavy atoms from RDKit `GetNumAtoms()`).

**Tool:** `mcp__boltz_mcp__validate_ligand_smiles`

**Parameters:**
- `smiles`: Cyclic peptide SMILES string (from Step P1.2)

**Routing Logic:**
```
For each passing candidate:
    heavy_atoms = validate_ligand_smiles(smiles).num_atoms

    IF heavy_atoms ≤ 128:
        → Track A (Boltz-2 SMILES affinity) + Track B (AlphaFold3)
    ELSE:
        → Track B (AlphaFold3) only

    All candidates → Gnina docking (on predicted complex structures)
```

> **Why 128 atoms?** Boltz-2 SMILES affinity prediction has a practical limit of ~128 heavy atoms for the ligand. Larger macrocyclic peptides exceed this and should be evaluated via AlphaFold3 only.

### Step P1.7: Cap Candidates for Phase 2 (≤100 for AF3)

AlphaFold3 is computationally expensive (~15-60 min per prediction). To keep Phase 2 tractable, cap the total number of candidates entering Track B (AF3) at **100**.

```
# After routing, if total candidates > 100:
#   1. Rank all PASS candidates by composite score = normalized(KD) + normalized(permeability)
#   2. Keep top 100 candidates
#   3. Ensure both heavy-atom classes are represented proportionally

all_candidates = sorted(pass_candidates, key=composite_score, ascending=False)
phase2_candidates = all_candidates[:100]

# Track A subset: phase2_candidates where heavy_atoms ≤ 128
# Track B: all phase2_candidates (≤100, within AF3 budget)
```

> **Why ≤100?** At ~15-60 min per AF3 prediction, 100 candidates = 25-100 GPU-hours. This balances coverage with compute budget. Adjust based on available resources.

**Recommended:** Select top 20-50 candidates if compute is limited; up to 100 if GPU time allows.

---

## Phase 2: Structural Evaluation (Two Parallel Tracks)

Candidates are evaluated through two parallel structural prediction and docking tracks. Track A (Boltz-2 SMILES affinity) runs only for candidates with ≤128 heavy atoms. Track B (AlphaFold3) runs for ALL candidates. Both tracks include Gnina docking on predicted complex structures.

### Track A: Boltz-2 SMILES Affinity (candidates ≤128 heavy atoms)

Boltz-2 affinity prediction treats the cyclic peptide as a small molecule ligand (SMILES input), preserving exact ncAA chemistry (N-methylation, D-amino acids, non-standard caps) that protein-chain input cannot represent. Produces 3-head ensemble affinity predictions.

#### Step 2A.1: Submit Boltz-2 Affinity Prediction

**Tool:** `mcp__boltz_mcp__submit_affinity_prediction`

**Parameters:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `protein_sequence` | KRAS protein sequence (165 aa) | Full-length target sequence |
| `ligand_smiles` | Cyclic peptide SMILES | From HELM→SMILES conversion (Step P1.2) |
| `use_msa_server` | false | Set to false when providing pre-computed MSA |
| `msa_path` | Path to pre-computed KRAS `.a3m` | Pre-computed target MSA (from Prerequisites) |
| `output_format` | `"pdb"` | PDB output for downstream Gnina docking |
| `accelerator` | `"gpu"` | GPU acceleration |
| `job_name` | (optional) | Candidate tracking name |

> **Pre-computed MSA:** Provide the pre-computed KRAS `.a3m` file (from Prerequisites) via `msa_path` for all candidates. This skips the slow MSA server query and reduces per-candidate runtime from ~8-15 min to ~2-5 min. Set `use_msa_server=false` since `msa_path` takes precedence.

#### Step 2A.2: Monitor & Collect Affinity Metrics

**Tools:**
- `mcp__boltz_mcp__get_job_status` — Check job progress
- `mcp__boltz_mcp__get_job_result` — Retrieve results when completed

**Affinity Metrics (from `affinity_*.json` — 3-head ensemble):**

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
| `complex_plddt` | Complex per-residue confidence | Higher is better |
| `complex_iplddt` | Interface per-residue confidence | Higher = better interface |
| `complex_ipde` | Interface predicted distance error | Lower = more accurate |

#### Step 2A.3: Gnina Docking on Boltz-2 Complex Structures

Dock the ligand from Boltz-2 output against the receptor to get physics-based binding scores.

**Tool:** `mcp__gnina_mcp__submit_molecular_docking`

**Parameters:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `receptor_file` | KRAS target PDB file | Or receptor extracted from Boltz-2 complex |
| `ligand_file` | Ligand PDB/SDF from Boltz-2 output | Cyclic peptide structure |
| `autobox_ligand` | Same ligand file | Auto-detect binding site from Boltz-2 pose |
| `num_modes` | 9 | Number of docking poses |
| `exhaustiveness` | 8 | Search thoroughness (increase to 16-32 for difficult cases) |
| `cnn_scoring` | true | Use CNN-enhanced scoring |
| `job_name` | (optional) | Candidate tracking name |

**Alternative (fast rescoring):** For quick scoring of Boltz-2 poses without re-docking:

**Tool:** `mcp__gnina_mcp__score_protein_ligand`

| Parameter | Value | Description |
|-----------|-------|-------------|
| `receptor_file` | KRAS target PDB | Receptor structure |
| `ligand_file` | Ligand from Boltz-2 output | Already in binding pose |

**Monitor & Retrieve:**
- `mcp__gnina_mcp__get_job_status` — Check docking progress
- `mcp__gnina_mcp__get_job_result` — Retrieve docking results

---

### Track B: AlphaFold3 Complex Prediction (ALL candidates)

AlphaFold3 predicts the protein-ligand complex structure for all candidates. Using `ligand_smiles` input captures exact ncAA chemistry (N-methylation, D-amino acids, piperidine caps, sidechain cyclization) without being limited to canonical amino acids.

#### Step 2B.1: Prepare AF3 Input with Pre-computed MSA

Each candidate needs an `input.json` that references the pre-computed KRAS MSA (`.a3m` file from Prerequisites) and includes the cyclic peptide as a ligand SMILES. This avoids re-running the slow MSA search for every candidate.

**Input JSON template** (one per candidate):
```json
{
  "name": "candidate_001",
  "sequences": [
    {
      "protein": {
        "id": "A",
        "sequence": "KRAS_SEQUENCE_HERE",
        "unpairedMsaPath": "/path/to/kras_target.a3m"
      }
    },
    {
      "ligand": {
        "id": "B",
        "smiles": "CYCLIC_PEPTIDE_SMILES_HERE"
      }
    }
  ]
}
```

> **Why `ligand_smiles` input?** AF3's protein chain input only handles canonical amino acids. SMILES input treats the cyclic peptide as a small molecule ligand, preserving the exact chemistry of ncAAs. This works for both canonical and non-canonical peptides.

> **Macrocyclic SMILES fallback:** If AF3's internal RDKit fails on complex macrocyclic SMILES (ring perception issues), use `userCCD` definitions in the `input.json`. Convert SMILES → 3D coordinates via OpenBabel → CCD CIF format for AF3 input.

#### Step 2B.2: Submit AF3 Prediction (single candidate)

**Tool:** `mcp__alphafold3_mcp__af3_predict_structure`

**Parameters:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `data_path` | Path to `input.json` or its parent directory | Input with pre-computed MSA reference |
| `mode` | `"a3m"` | Use pre-computed A3M MSA (skips MSA search) |
| `run_template_search` | true | Still search for structural templates |
| `device` | 2 | GPU device (see GPU Assignment) |
| `flash_attention_implementation` | `"triton"` | Use `"xla"` for non-A100 GPUs |

> **Why `mode="a3m"`?** This tells AF3 to read the MSA from the `unpairedMsaPath` in `input.json` instead of running MMseqs2 search. Saves ~30-60 min per candidate. Template search still runs (fast) unless disabled.

#### Step 2B.3: Batch Processing (recommended for ≤100 candidates)

Prepare `input.json` files in per-candidate subdirectories, each referencing the same pre-computed KRAS MSA. Use batch prediction to process all candidates efficiently (model loaded once, reused across predictions).

**Tool:** `mcp__alphafold3_mcp__af3_predict_batch`

**Parameters:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `input_dir` | Directory with variant subdirectories | Each subdirectory contains an `input.json` |
| `device` | 2 | GPU device number |
| `skip_existing` | true | Skip already-completed predictions |
| `run_template_search` | true | Search for structural templates |
| `flash_attention_implementation` | `"triton"` | Use `"xla"` for non-A100 GPUs |

**Expected directory structure (≤100 candidates):**
```
af3_inputs/
├── candidate_001/
│   └── input.json    # references kras_target.a3m via unpairedMsaPath
├── candidate_002/
│   └── input.json
└── ...
    └── input.json    # max 100 candidates (capped in Step P1.7)
```

#### Step 2B.4: Collect AF3 Confidence Metrics

**Key metrics from AF3 output:**

| Metric | Description | Interpretation |
|--------|-------------|----------------|
| pLDDT | Per-residue confidence | > 0.70 = reliable structure |
| pTM | Predicted TM-score | Overall fold quality |
| iPTM | Interface predicted TM-score | Interface quality (primary metric) |
| PAE | Predicted aligned error | Lower = more accurate positioning |

#### Step 2B.5: Gnina Docking on AF3 Complex Structures

**Tool:** `mcp__gnina_mcp__submit_molecular_docking`

**Parameters:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `receptor_file` | KRAS PDB or receptor from AF3 output | Target protein structure |
| `ligand_file` | Ligand extracted from AF3 complex output | Cyclic peptide structure |
| `autobox_ligand` | Same ligand file | Binding site from AF3 predicted pose |
| `num_modes` | 9 | Number of docking poses |
| `exhaustiveness` | 8 | Search thoroughness |
| `cnn_scoring` | true | CNN-enhanced scoring |
| `job_name` | (optional) | Candidate tracking name |

**Monitor & Retrieve:**
- `mcp__gnina_mcp__get_job_status` / `mcp__gnina_mcp__get_job_result`

---

## Phase 3: Final Selection & Ranking

### Composite Scoring

Two scoring tables depending on heavy atom routing:

**Candidates ≤128 heavy atoms (Boltz-2 + AF3 + Gnina):**

| Metric | Weight | Source | Direction |
|--------|--------|--------|-----------|
| KRAS KD (μM) | 0.20 | HELM-GPT XGBoost | Lower is better |
| Permeability (log cm/s) | 0.15 | HELM-GPT RF | Higher is better |
| Boltz-2 ensemble avg affinity | 0.15 | Boltz-2 SMILES | Higher is better |
| Boltz-2 ensemble avg prob | 0.10 | Boltz-2 SMILES | Higher is better |
| AF3 iPTM | 0.10 | AlphaFold3 | Higher is better |
| Gnina CNN affinity (best of Track A/B) | 0.15 | Gnina | Higher is better |
| Gnina Vina score (best of Track A/B) | 0.15 | Gnina | More negative is better |

**Candidates >128 heavy atoms (AF3 + Gnina only):**

| Metric | Weight | Source | Direction |
|--------|--------|--------|-----------|
| KRAS KD (μM) | 0.25 | HELM-GPT XGBoost | Lower is better |
| Permeability (log cm/s) | 0.20 | HELM-GPT RF | Higher is better |
| AF3 iPTM | 0.15 | AlphaFold3 | Higher is better |
| Gnina CNN affinity | 0.20 | Gnina | Higher is better |
| Gnina Vina score | 0.20 | Gnina | More negative is better |

### Selection Strategy

- Select top 5-10 designs for experimental testing
- Ensure structural diversity (different binding modes / ncAA compositions)
- Prioritize designs with strong Gnina docking scores AND good AF3 confidence
- Include 1-2 designs with novel ncAA scaffolds for chemical diversity

---

## Quality Thresholds Reference Table

| Metric | Excellent | Good | Acceptable | Source |
|--------|-----------|------|------------|--------|
| KRAS KD | < 1 μM | < 10 μM | < 100 μM | HELM-GPT XGBoost |
| Permeability | > -5.0 | > -6.0 | > -6.5 | HELM-GPT RF |
| Boltz-2 ensemble avg affinity | > 0.5 | > 0.0 | > -0.3 | Boltz-2 SMILES |
| Boltz-2 ensemble avg prob | > 0.6 | > 0.5 | > 0.4 | Boltz-2 SMILES |
| Ligand iPTM (Boltz-2) | > 0.80 | > 0.70 | > 0.60 | Boltz-2 SMILES |
| AF3 pLDDT | > 0.85 | > 0.70 | > 0.60 | AlphaFold3 |
| AF3 iPTM | > 0.80 | > 0.60 | > 0.40 | AlphaFold3 |
| Gnina CNN affinity (pKd) | > 7.0 | > 6.0 | > 5.0 | Gnina |
| Gnina Vina score (kcal/mol) | < -8.0 | < -7.0 | < -5.0 | Gnina |

---

## Output Format

Present final results in this format:

```markdown
## HELM-GPT KRAS Binder Design Results

### Job Summary
| Parameter | Value |
|-----------|-------|
| Target | KRAS |
| Prior Model | {prior_model_path} |
| Task | kras_perm |
| RL Steps | {n_steps} |
| Loss Type | {loss_type} |
| Sequences Generated | {total_generated} |
| Post-Phase 1 Passed | {post_phase1_passed} |
| ≤128 atoms (Track A+B) | {track_a_count} |
| >128 atoms (Track B only) | {track_b_only_count} |

### Top Designs

#### Design 1: {design_id} (≤128 atoms / >128 atoms)
| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| HELM | `{helm_sequence}` | - | - |
| SMILES | `{smiles}` | - | - |
| Heavy atoms | {n_atoms} | - | - |
| KRAS KD | {value} μM | < 10 | PASS/FAIL |
| Permeability | {value} log cm/s | > -6.0 | PASS/FAIL |
| Boltz-2 ensemble avg affinity | {value} | > 0.0 | PASS/FAIL/N/A |
| Boltz-2 ensemble avg prob | {value} | > 0.5 | PASS/FAIL/N/A |
| AF3 iPTM | {value} | > 0.60 | PASS/FAIL |
| AF3 pLDDT | {value} | > 0.70 | PASS/FAIL |
| Gnina CNN affinity | {value} pKd | > 6.0 | PASS/FAIL |
| Gnina Vina score | {value} kcal/mol | < -7.0 | PASS/FAIL |

**Contains ncAAs:** {yes/no}
**Output Files:** `{output_path}`

[Repeat for additional designs]

### Recommended for Synthesis
1. {design_id_1} - Best composite score
2. {design_id_2} - Best Gnina + AF3 consensus
3. {design_id_3} - Most novel ncAA scaffold
```

---

## Error Handling

### Phase 1: RL Optimization Issues
- **No convergence at 500 steps:** Extend to 1000 (maximum). If still not converging, reduce `learning_rate` or try `loss_type="reinvent"` first
- **GPU OOM:** Reduce `batch_size` to 16 or 8
- **Prior model not found:** Use `check_optimization_requirements` to locate available models
- **High KD across all designs:** Target may be challenging; consider longer peptide or different prior
- **Low diversity / mode collapse:** Reduce `sigma` or increase `batch_size`

### Post-Phase 1: Filtering Issues
- **HELM→SMILES conversion failure:** Check HELM syntax; ensure cyclization link format is correct (`1:R1-N:R3`)
- **All candidates filtered out:** Relax thresholds (KD < 100 μM, permeability > -6.5)
- **validate_ligand_smiles failure:** SMILES may contain invalid chemistry; check RDKit parsing

### Phase 2A: Boltz-2 SMILES Affinity Issues
- **All affinity heads negative:** Peptide may not bind as small molecule; rely on AF3 Track B results
- **Inconsistent ensemble heads:** Low confidence in prediction; weight AF3 + Gnina more heavily
- **MSA timeout:** Use pre-computed MSA via `msa_path` parameter for faster reruns
- **Ligand too large:** Should have been routed to Track B only (>128 heavy atoms)

### Phase 2B: AlphaFold3 Issues
- **Low pLDDT:** Peptide structure may be poorly predicted; try different peptide lengths
- **Macrocyclic SMILES parsing failure:** Use `af3_predict_structure` with custom `input.json` and `userCCD` definitions (SMILES → OpenBabel 3D coords → CCD CIF format)
- **GPU memory error:** Reduce `buckets` parameter or use a GPU with more memory

### Phase 2 (Gnina): Docking Issues
- **Poor docking scores across all candidates:** Check receptor PDB formatting and binding site definition
- **Gnina scoring failure:** Verify ligand/receptor PDB formatting and that ligand has 3D coordinates
- **No binding site found:** Provide explicit `center` and `size` parameters instead of `autobox_ligand`

---

## Example Usage

### Standard KRAS Binder Design
```
Design synthesizable cyclic peptide KRAS binders using HELM-GPT:
- Task: kras_perm (co-optimize KRAS binding + permeability)
- Prior model: examples/data/models/prior/perm_agent_final.pt
- 500 RL steps with reinvent_cpl loss, batch_size=32 (extend to 1000 only if not converged)
- Filter: KD < 10 μM, permeability > -6.0
- Route by heavy atoms: ≤128 → Boltz-2 + AF3 + Gnina; >128 → AF3 + Gnina
- Select top 10 diverse designs
```

### ncAA-Enriched Design
```
Design ncAA-containing cyclic peptide KRAS binders:
- Use HELM-GPT with full 3104-monomer library
- Task: kras_perm, 500 RL steps
- Focus on candidates with ncAA scaffolds (N-methylation, D-amino acids)
- AF3 + Gnina validation for all candidates
- Select top 10 diverse designs including novel ncAA scaffolds
```

### High-Throughput Screening
```
Generate diverse KRAS binder candidates using HELM-GPT:
- 2000 RL steps, batch_size=64
- Filter top 50 by KD + permeability
- Run both Boltz-2 (≤128 atoms) and AF3 (all) in parallel
- Gnina docking on all predicted complexes
- Composite score ranking → top 10 diverse designs
```

---

## MCP Tools Quick Reference

| Phase | MCP Server | Tool | Purpose |
|-------|------------|------|---------|
| 1 | helm_gpt_mcp | `check_optimization_requirements` | Verify setup and models |
| 1 | helm_gpt_mcp | `get_optimization_tasks` | List available tasks (confirm `kras_perm`) |
| 1 | helm_gpt_mcp | `submit_optimize_peptides` | RL optimization with local scoring |
| 1 | helm_gpt_mcp | `get_job_status` / `get_job_log` | Monitor training |
| 1 | helm_gpt_mcp | `get_job_result` | Retrieve optimized sequences |
| Post-1 | helm_gpt_mcp | `validate_helm_notation` | HELM validity check |
| Post-1 | helm_gpt_mcp | `helm_to_smiles` / `submit_helm_to_smiles_batch` | Convert HELM to SMILES |
| Post-1 | helm_gpt_mcp | `predict_permeability` / `submit_permeability_batch` | Permeability verification |
| Post-1 | helm_gpt_mcp | `predict_kras_binding` / `submit_kras_binding_batch` | KRAS KD verification |
| Post-1 | boltz_mcp | `validate_ligand_smiles` | Heavy atom count for routing |
| 2A | boltz_mcp | `submit_affinity_prediction` | SMILES affinity (3-head ensemble) |
| 2A | boltz_mcp | `get_job_status` / `get_job_result` | Monitor & retrieve affinity |
| 2A | gnina_mcp | `submit_molecular_docking` | Dock on Boltz-2 complexes |
| 2B | alphafold3_mcp | `af3_predict_structure` (mode=a3m) | Protein-ligand complex with pre-computed MSA |
| 2B | alphafold3_mcp | `af3_predict_batch` | Batch complex predictions |
| 2B | gnina_mcp | `submit_molecular_docking` | Dock on AF3 complexes |
| 2A/2B | gnina_mcp | `score_protein_ligand` | Fast rescoring (no re-docking) |
| 2A/2B | gnina_mcp | `get_job_status` / `get_job_result` | Monitor & retrieve docking |

---

## Key Differences from Old Workflow

| Aspect | Old Workflow | New Workflow |
|--------|-------------|-------------|
| RL reward | Boltz-2 iPAE/iPTM (slow, requires dedicated GPU server) | KRAS XGBoost + permeability RF (fast, local) |
| Phase 1 GPUs | 2 (HELM-GPT + Boltz-2 server) | 1 (HELM-GPT only) |
| Post-RL filter | iPAE < 0.30, iPTM > 0.80 | KD < 10 μM, permeability > -6.0 |
| Structure prediction | HighFold3 (CycPOEM) | AlphaFold3 (`ligand_smiles` input) |
| Boltz-2 role | RL reward (all candidates) + Phase 1b affinity (all) | Phase 2A affinity only (≤128 heavy atoms) |
| Heavy atom routing | Not considered | ≤128 → Boltz-2 + AF3 + Gnina; >128 → AF3 + Gnina |
| MD simulation | Full GROMACS/Amber phase | Removed |
| Gnina docking | TODO / not implemented | Fully integrated with real tool interfaces |
| Workflow phases | 4 phases (1, 1b, 2, 3) | 3 phases (1, Post-1 filter, 2 parallel tracks, 3 ranking) |

---

## Related Workflows

- `binder_design_rfpeptides.md` — RFpeptides backbone-first binder design (5-stage, canonical AAs only)
- `binder_design_afcycdesign.md` — AfCycDesign-only binder design

## References

- **HELM-GPT**: GPT-based generative model for macrocyclic peptide design with HELM notation (3,104+ monomer library)
- **Boltz-2**: Biomolecular complex structure prediction and SMILES-based affinity prediction (3-head ensemble)
- **AlphaFold3**: Protein-ligand complex structure prediction with `ligand_smiles` input
- **Gnina**: CNN-based molecular docking with learned scoring functions (Vina + CNN, trained on PDBBind)
- **CycPeptMPDB**: Cyclic peptide membrane permeability database
- **REINVENT + CPL**: Reinforcement learning with contrastive preference learning for molecular optimization
