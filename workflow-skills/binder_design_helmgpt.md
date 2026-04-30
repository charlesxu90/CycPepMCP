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

- **Target FASTA file** (`target.fasta`) — single-record FASTA of the target's catalytic domain (case3 ships `examples/case3_kras_perm_opt_helmgpt/target.fasta` for KRAS-G12D 1-165). Step 0 below uses this to generate the pre-computed MSA via Boltz-2 + MMseqs2; the resulting `target.a3m` is reused by every Phase-2 Boltz-2 / AF3 call so they skip the slow MSA search (~30-60 min savings per candidate).
- **Target PDB file** — properly formatted protein structure (used as Gnina receptor in Phase 2). Boltz-2 also writes a predicted PDB during Step 0 if you don't have one already.
- **Run / output directory** — defaults to `results/<case_name>/` (case3: `results/case3_kras_helmgpt/`). All Step-0/Phase-1/Phase-2/Phase-3 artifacts land here so the run is self-contained.
- **Prior model file** (`.pt`) — case3 ships a permeability-pretrained prior at `examples/case3_kras_perm_opt_helmgpt/perm_prior/gpt_model_final_0.105.pt` (vocab=76, n_embd=256, 8-layer GPT, matching `.json` config alongside). Stage it into the MCP cache via Step 1.0 below.
- **Predictor models & monomer library** — case3 also includes `rl_predictors/{kras_kd,perm}/*.pkl` and `monomer_library.csv`. These are byte-identical (md5-verified) to the predictors baked into `helm_gpt_mcp`'s container, so RL optimization picks them up automatically — no extra staging required. The `setup_case3.py` helper verifies parity. If you ever swap in a different predictor pickle, pass its container path via the `model_path` argument exposed on `predict_permeability`, `predict_kras_binding`, and the matching `submit_*_batch` tools.
- Desired binder length (typically 7-20 residues)

---

## Step 0: Generate Target MSA (`target.a3m`)

Run a **single** Boltz-2 prediction with the MSA server enabled to fetch the target's MMseqs2 alignment from `api.colabfold.com`. Boltz-2 writes the merged a3m alongside its output structure; we copy it out to a stable name for reuse. This step costs ~5-10 min once (MSA fetch ~5-60 s + structure inference ~15 s + I/O); after that, every Phase-2 Boltz-2 / AF3 call passes `msa_path=target.a3m` instead of querying MMseqs2 again.

**Inputs**
- `target.fasta` (single-record FASTA, the target's catalytic-domain sequence — case3: KRAS-G12D 1-165)
- Output directory (default `results/case3_kras_helmgpt/`)

**Helper (case3-bundled)** — runs Boltz-2 directly via the MCP's local env, extracts the merged a3m, and copies it to `<output_dir>/target.a3m`:

```bash
bash examples/case3_kras_perm_opt_helmgpt/run_target_msa.sh \
  examples/case3_kras_perm_opt_helmgpt/target.fasta \
  results/case3_kras_helmgpt
```

**MCP-tool equivalent** (when the `boltz_mcp` container is available): call `mcp__boltz_mcp__simple_structure_prediction` with `sequence=<target FASTA seq>`, `use_msa_server=True`, `output_dir=results/case3_kras_helmgpt/target_msa_run`, then locate the resulting `boltz_results_*/msa/*_unpaired_tmp_env/bfd.mgnify30.metaeuk30.smag30.a3m` and copy it to `results/case3_kras_helmgpt/target.a3m`.

**Outputs**
- `results/case3_kras_helmgpt/target.a3m` — query record's first line is the `target.fasta` sequence; followed by ~9 000-15 000 homolog records. Pass this to Phase 2 via `msa_path=` (Boltz-2) and `unpairedMsaPath` (AF3 input.json).
- `results/case3_kras_helmgpt/target_msa_run/boltz_results_*/predictions/...` — predicted target PDB (free byproduct, usable as Gnina receptor in Phase 2).

> **Sanity check:** `awk 'NR==2 {print substr($0,12,1); exit}' results/case3_kras_helmgpt/target.a3m` should print the residue at position 12 of your target — `D` for KRAS-G12D, `G` for WT KRAS. A mismatch with `target.fasta` means the wrong query was used.

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

### Step 1.0: Stage Case3 Prior into the MCP Cache

The case3 prior `gpt_model_final_0.105.pt` lives on the host but the `helm_gpt_mcp` server runs in Docker. The container reads-only-mounts `$MACROMNEX_CACHE/model/helmgpt/` at `/app/models/helmgpt/` (see `mcps.yaml` `cache_model` entry), so any `.pt`/`.json` placed in the host cache becomes visible to RL training.

**Action:** run the helper script once:

```bash
python examples/case3_kras_perm_opt_helmgpt/setup_case3.py
```

It will:
1. Copy `perm_prior/gpt_model_final_0.105.{pt,json}` into `$MACROMNEX_CACHE/model/helmgpt/` (idempotent via md5 check).
2. Verify the case3 predictor pickles and `monomer_library.csv` match the baked-in MCP defaults.
3. Print the **container path** to use for `prior_model` in Step 1.3: `/app/models/helmgpt/gpt_model_final_0.105.pt`.

If parity verification reports a `[DIFF]`, the case3 predictors have diverged from the in-container defaults; in that case Step P1.3 / P1.4 below should pass `model_path=...` pointing at the case3 pickle to override.

### Step 1.1: Check Optimization Requirements

**Tool:** `mcp__helmgpt_mcp__check_optimization_requirements`

**Expected Output:**
- `repo_available`: HELM-GPT repository accessible
- `kras_model`: KRAS XGBoost scoring model available
- `permeability_model`: Permeability RF scoring model available
- `cuda_available`: GPU availability
- `python_version`: Current Python version
- `available_prior_models`: List of prior model `.pt` files

**Action:** Ensure `gpt_model_final_0.105.pt` appears in `available_prior_models` (it will, once Step 1.0 has staged it into `MODELS_CACHE_DIR=/app/models/helmgpt`). Confirm both scoring models (`kras_model` + `permeability_model`) and GPU are also available before proceeding.

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
| `prior_model` | `/app/models/helmgpt/gpt_model_final_0.105.pt` (case3) | Container path to the permeability-pretrained prior `.pt` file. Staged via Step 1.0; matching `.json` config sits alongside. |
| `task` | `"kras_perm"` | Multi-objective task: KRAS KD + permeability |
| `output_dir` | `results/case3_kras_helmgpt/phase1_<YYYYMMDD_HHMMSS>` (default) | Directory for step CSVs, checkpoints, top sequences. Use a timestamped subdir under `results/<case_name>/` so multiple Phase-1 runs coexist; `postprocess_phase1.py` reads back from this same dir. |
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

### Step P1.2: Convert HELM to SMILES + Heavy-Atom Routing

**Recommended (case3 path):** run the bundled helper which combines HELM→SMILES, heavy-atom counting, Track A/B routing, and top-N capping in one shot:

```bash
tool-mcps/helm_gpt_mcp/env_py3.7/bin/python \
  examples/case3_kras_perm_opt_helmgpt/postprocess_phase2_prep.py \
  results/case3_kras_helmgpt/phase1_<timestamp> --top 20
```

This calls the upstream `utils.helm_utils.get_cycpep_smi_from_helm` function directly (with the correct `cwd` swap so the 3105-monomer library loads), then RDKit for `mol.GetNumHeavyAtoms()`, then writes `phase2_candidates.csv` + `phase2_routing_summary.json`.

**MCP-tool path** — `mcp__helmgpt_mcp__helm_to_smiles` (synchronous) or `mcp__helmgpt_mcp__submit_helm_to_smiles_batch` (async, for >1000 sequences):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `helm_input` | null | Single HELM string to convert (alternative to input_file) |
| `input_file` | null | CSV file with HELM sequences from RL output |
| `output_file` | null | Path to save results with SMILES column |
| `helm_column` | "HELM" | Column name in CSV |
| `limit` | null | Maximum number of sequences to process |

> Note: Either `helm_input` or `input_file` should be provided (mutually exclusive).
>
> **Known issue with the standalone CLI script:** `tool-mcps/helm_gpt_mcp/scripts/helm_to_smiles.py` invoked as `python scripts/helm_to_smiles.py …` silently falls back to a stub HELM→SMILES converter (the `lib.helm_utils_repo._load_repo_functions` import path doesn't trip when run as `__main__`), producing the same trivial 35-char SMILES (`CC(C)C[C@H](N)C(=O)N[C@@H](C)C(=O)N`) for every input. Use the `postprocess_phase2_prep.py` helper above (which imports the upstream function explicitly) **or** call the function via Python rather than CLI:
> ```python
> import sys, os; sys.path.insert(0, 'tool-mcps/helm_gpt_mcp/repo/helm-gpt')
> os.chdir('tool-mcps/helm_gpt_mcp/repo/helm-gpt')  # for monomer_library.csv
> from utils.helm_utils import get_cycpep_smi_from_helm
> ```

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
| `model_path` | null | Override path to RF predictor pickle. Leave null to use the bundled default; for case3, only set if `setup_case3.py` reports a `[DIFF]` — e.g. `/app/examples/data/regression_rf.pkl` if you mounted the case3 pickle into `cache_data`. |

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
| `model_path` | null | Override path to XGBoost predictor pickle. Leave null to use the bundled default; for case3, only set if `setup_case3.py` reports a `[DIFF]`. |

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

> **Track B optional when all candidates ≤128 atoms.** Boltz-2 affinity prediction (Track A) **also writes a complex PDB plus per-residue confidence** (`iptm`, `ligand_iptm`, `complex_plddt`). For small peptides this is functionally equivalent to AF3's complex output, so Track B is **redundant and can be skipped** if every passing candidate is already routed to Track A (which is the case in case3: 20 candidates, max 93 heavy atoms). In that mode, use Boltz-2's `iptm` in place of AF3's iPTM in the Phase-3 composite, and run Gnina on the Boltz-2 complex.
>
> **AF3 local install caveat.** The `tool-mcps/alphafold3_mcp/repo/alphafold3` clone needs its `alphafold3.cpp` C extension built (`cd repo/alphafold3 && cmake -B build && cmake --build build`) — without it `from alphafold3.cpp import cif_dict` fails and Track B aborts. The Docker image bakes this in; the local env does not by default. If Track B is essential (e.g. >128-atom candidates), build the extension or use the Docker image.

### Track A: Boltz-2 SMILES Affinity (candidates ≤128 heavy atoms)

Boltz-2 affinity prediction treats the cyclic peptide as a small molecule ligand (SMILES input), preserving exact ncAA chemistry (N-methylation, D-amino acids, non-standard caps) that protein-chain input cannot represent. Produces 3-head ensemble affinity predictions.

#### Step 2A.1: Submit Boltz-2 Affinity Prediction

**Tool:** `mcp__boltz_mcp__submit_affinity_prediction`

**Parameters:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `protein_sequence` | Target sequence (case3: KRAS-G12D 1-165, 165 aa — read from `target.fasta`) | Full-length target sequence |
| `ligand_smiles` | Cyclic peptide SMILES | From HELM→SMILES conversion (Step P1.2) |
| `use_msa_server` | false | Set to false when providing pre-computed MSA |
| `msa_path` | `results/case3_kras_helmgpt/target.a3m` | Pre-computed target MSA generated in Step 0 |
| `output_dir` | `results/case3_kras_helmgpt/phase2_track_a/<candidate_id>` | Per-candidate output dir under the run root |
| `output_format` | `"pdb"` | PDB output for downstream Gnina docking |
| `accelerator` | `"gpu"` | GPU acceleration |
| `job_name` | (optional) | Candidate tracking name |

> **Pre-computed MSA:** Provide the Step-0 `.a3m` file via `msa_path` for all candidates. This skips the MSA server query and reduces per-candidate runtime from ~8-15 min to ~2-5 min. Set `use_msa_server=false` since `msa_path` takes precedence. The first record of `target.a3m` MUST match the `protein_sequence` argument — if you use a different target variant, regenerate the a3m via Step 0 first.

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

Each candidate needs an `input.json` that references the **Step-0 target MSA** (`results/<case>/target.a3m`) and includes the cyclic peptide as a ligand SMILES. This avoids re-running the slow MSA search for every candidate.

**Input JSON template** (one per candidate; case3 paths shown):
```json
{
  "name": "candidate_001",
  "sequences": [
    {
      "protein": {
        "id": "A",
        "sequence": "MTEYKLVVVGADGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQVVIDGETCLLDILDTAGQEEYSAMRDQYMRTGEGFLCVFAINNTKSFEDIHHYREQIKRVKDSEDVPMVLVGNKCDLPSRTVDTKQAQDLARSYGIPFIETSAKTRQRVEDAFYTLVREIRQ",
        "unpairedMsaPath": "results/case3_kras_helmgpt/target.a3m"
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

Prepare `input.json` files in per-candidate subdirectories, each referencing the same Step-0 `target.a3m`. Use batch prediction to process all candidates efficiently (model loaded once, reused across predictions).

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
results/case3_kras_helmgpt/
├── target.a3m                # Step 0 output, referenced by every input.json
└── phase2_track_b/af3_inputs/
    ├── candidate_001/
    │   └── input.json        # unpairedMsaPath -> ../../target.a3m
    ├── candidate_002/
    │   └── input.json
    └── ...                   # max 100 candidates (capped in Step P1.7)
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

Two weight schemes depending on heavy-atom routing. **`postprocess_phase3.py` implements the ≤128-atom scheme**, which is also what the visualization reads from `phase3_final_ranking.csv`'s `composite` column. Each metric is min-max normalized within the candidate set before the weighted sum, so the final composite is on a 0–1 scale (1 = best on every metric in this run, 0 = worst on every metric).

**Candidates ≤128 heavy atoms (Boltz-2 + AF3 + Gnina) — also used as fallback when AF3 is skipped (Boltz-2 iPTM substitutes for AF3 iPTM):**

| Metric | Weight | Source | Direction |
|--------|--------|--------|-----------|
| KRAS KD (μM) | 0.20 | HELM-GPT XGBoost | Lower is better |
| Permeability (log cm/s) | 0.15 | HELM-GPT RF | Higher is better |
| Boltz-2 ensemble avg affinity | 0.15 | Boltz-2 SMILES | Higher is better |
| Boltz-2 ensemble avg prob | 0.10 | Boltz-2 SMILES | Higher is better |
| AF3 iPTM (or Boltz-2 ligand_iptm fallback) | 0.10 | AlphaFold3 / Boltz-2 | Higher is better |
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

> **Single source of truth.** `helmgpt_viz.py.calculate_composite_score` first looks for the `composite` column in the input dataframe (written by `postprocess_phase3.py`) and uses that directly; the viz only recomputes when the column is absent (legacy / partial runs). This avoids the previous discrepancy between the table's `Score` cell and `phase3_summary.json`'s composite values — they're now identical by construction.

### Selection Strategy

- Select top 5-10 designs for experimental testing
- Ensure structural diversity (different binding modes / ncAA compositions)
- Prioritize designs with strong Gnina docking scores AND good Boltz-2 / AF3 confidence
- Include 1-2 designs with novel ncAA scaffolds for chemical diversity

---

## Phase 3.5: Visualization

After Phase 3 ranking, generate publication-quality figures with `workflow-skills/scripts/helmgpt/helmgpt_viz.py`. The script reads `phase3_final_ranking.csv` (consolidated case3 schema) or the legacy multi-file layout and emits PDF + PNG for every panel. Threshold lines on every distribution plot are pulled directly from the **Quality Thresholds Reference Table** below — solid prominent line = workflow PASS gate, dashed faint line = "Excellent" tier — keeping the figures self-documenting.

**Invocation:**

```bash
# Separate per-metric figures (default)
python workflow-skills/scripts/helmgpt/helmgpt_viz.py \
  results/<case_name>/phase1_<timestamp>

# Single 3x3 summary panel
python workflow-skills/scripts/helmgpt/helmgpt_viz.py \
  results/<case_name>/phase1_<timestamp> --merged
```

**Figures produced** (each as `helmgpt_<name>.{png,pdf}`):

| # | File suffix | Content |
|---|---|---|
| 1 | `kd_distribution` | KD violin + strip with workflow gate at 10 μM and Excellent line at 1 μM |
| 2 | `perm_distribution` | Permeability violin + strip with workflow gate at −6.0 and Excellent line at −5.0 |
| 3 | `quality_scatter` | KD vs permeability scatter, points colored by composite score; PASS region shaded |
| 4 | `af3_iptm` | AF3 iPTM (or Boltz-2 ligand iPTM substitute when AF3 wasn't run) |
| 5 | `gnina_cnn` | Gnina CNN affinity (pKd) with workflow gate at 6.0, Excellent at 7.0 |
| 6 | `gnina_vina` | Gnina Vina (kcal/mol) with workflow gate at −7.0, Excellent at −8.0 |
| 7 | `boltz_affinity` | Boltz-2 ensemble affinity with workflow gate at 0.0, Excellent at 0.5 |
| 8 | `boltz_probability` | Boltz-2 binding probability with workflow gate at 0.5, Excellent at 0.6 |
| 9 | `composite_score` | Final composite score distribution (Phase 3 ranking) |
| 10 | **`radar_chart`** | **Spider/radar of top 5 candidates across all 7 composite metrics — see below** |
| 11 | `metrics_table` | Three-line academic-style table of top 6 by composite |
| 12 | `execution_timeline` | Gantt of pipeline phases (Phase 1 → Phase 3) |
| 13 | `summary` | Combined 3×3 panel of the most informative subset (use `--merged`) |

### Radar Chart (Spider Plot) — Top Candidates Multi-Metric Profile

Renders the top-N (default 5) candidates as overlapping polygons across the **5 strongest discriminating metrics**: **KD, Permeability, AF3 iPTM (or Boltz iPTM substitute), Gnina CNN, Gnina Vina**. (Boltz-2 affinity / probability are excluded — they're noisy ensemble heads that overlap with the Gnina + iPTM information already on the chart, and adding them clutters the polygon without adding orthogonal signal. They remain on their own per-metric distribution plots.)

**Normalization:** each axis is min-max normalized **across the full candidate set** (not against absolute thresholds), so each metric uses the full 0–1 radial range and small differences between top hits remain visible. Lower-is-better metrics (KD, Vina) are inverted so **outer edge = better** on every axis.

**Reference polygon:** a faint gray dashed polygon shows the **set median** on each axis — at-a-glance "is this candidate above or below the pack?"

**Interpretation:**
- A polygon hugging the outer edge on most axes is a balanced top design.
- An asymmetric polygon (e.g. excellent Gnina but poor Boltz prob) flags risk of single-method bias — check the underlying scores in `phase3_final_ranking.csv`.
- The set-median reference shows which axes are tightly clustered (median near outer ring = all candidates are good there) vs. spread out (median near center = differentiating axis).

This view complements the individual distribution plots (Figures 1–8) by showing **per-candidate balance across all metrics simultaneously** — useful for the final "which 5–10 to synthesize?" decision in Phase 3.

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

## Reproducible Scripts (case3-bundled)

All helpers live under `examples/case3_kras_perm_opt_helmgpt/` and are pure Python or bash with no extra deps beyond what each MCP's local env already installs. Run them in order from the project root:

| # | Script | Phase | Purpose |
|---|---|---|---|
| 0 | `setup_case3.py` | Pre-Phase 1 | Stages the case3 prior `gpt_model_final_0.105.{pt,json}` into `$MACROMNEX_CACHE/model/helmgpt/` (mounted into the helm_gpt_mcp container at `/app/models/helmgpt/`); md5-verifies the bundled predictor pickles + monomer library against the in-MCP defaults. Idempotent. |
| 0 | `run_target_msa.sh <target.fasta> <out_dir>` | Step 0 | Wraps Boltz-2 (`tool-mcps/boltz_mcp/env/bin/boltz predict --use_msa_server`) on a target FASTA, extracts the merged `bfd.mgnify30.metaeuk30.smag30.a3m`, and copies it to `<out_dir>/target.a3m`. Produces a predicted target PDB as a free byproduct. |
| 1 | (built-in MCP tool) `submit_optimize_peptides` | Phase 1 | RL co-optimization. Output dir conventionally `results/<case>/phase1_<YYYYMMDD_HHMMSS>`. |
| 1 | `postprocess_phase1.py <run_dir>` | Post-Phase 1 | Aggregates all `step_*_aa_seqs.csv`, drops parser-failed rows (sentinel `raw_permeability=-10` / `raw_kras_kd=5`), deduplicates by HELM, applies the workflow PASS gate (perm > −6, KD < 10 μM), writes `phase1_aggregated.csv` + `phase1_filtered.csv` + `phase1_summary.json`. |
| 1 | `postprocess_phase2_prep.py <run_dir> --top N` | Post-Phase 1 | HELM→SMILES via upstream `get_cycpep_smi_from_helm`, heavy-atom count via RDKit, Track A/B routing at 128-atom threshold, capping to top-N (default 20). Writes `phase2_candidates.csv` + `phase2_routing_summary.json`. **Bypasses the broken `helm_to_smiles.py` CLI wrapper** (see Step P1.2). |
| 2A | `run_phase2_track_a.sh <run_dir>` | Phase 2 Track A | Boltz-2 affinity prediction × N candidates with `msa_path=target.a3m`. Per-candidate YAML + `boltz predict` invocation; ~2 min/candidate cached, ~40 min for 20. Writes `phase2_track_a/c_<rank>_<smi8>/boltz_results_input/...` + aggregate `track_a_results.csv`. |
| 2B | `run_phase2_track_b.sh <run_dir> [device]` | Phase 2 Track B | AF3 prediction × N candidates with `unpairedMsaPath=target.a3m`. **Requires AF3 cpp extension built** (Docker image or local rebuild). Skipped automatically when all candidates ≤128 atoms (Track A's Boltz-2 complex covers it). |
| 2 | `run_phase2_gnina.sh <run_dir> [device]` | Phase 2 docking | Splits chain A (receptor) and chain B/HETATM (ligand) from the Boltz-2 PDB, runs Gnina with `--autobox_ligand --num_modes 9 --exhaustiveness 8 --cnn_scoring rescore`. Per-candidate `docked.sdf` + parsed `gnina_results.csv` (CNN affinity, Vina, CNN pose). Sets `LD_LIBRARY_PATH` to bundle the env-local `libcudnn.so.9` (otherwise Gnina dies with "cannot open shared object"). |
| 3 | `postprocess_phase3.py <run_dir>` | Phase 3 | Merges Phase-1 metrics + Track A + Gnina, min-max normalizes each, applies the workflow's composite weights (KD 0.20, perm 0.15, Boltz aff 0.15, Boltz prob 0.10, iPTM 0.10, CNN 0.15, Vina 0.15), writes `phase3_final_ranking.csv` + `phase3_summary.json`. |
| 3.5 | `workflow-skills/scripts/helmgpt/helmgpt_viz.py <run_dir>` | Visualization | 12 individual figures + optional `--merged` 3×3 summary. Reads `phase3_final_ranking.csv` directly when present. See **Phase 3.5** above. |

> **One-shot recipe** (after `setup_case3.py` and `run_target_msa.sh`):
> ```bash
> RUN=results/case3_kras_helmgpt/phase1_$(date +%Y%m%d_%H%M%S)
> # Phase 1 (via MCP tool, ~40 min for 500 steps)
> # ... call submit_optimize_peptides with prior_model=/app/models/helmgpt/gpt_model_final_0.105.pt, output_dir=$RUN
> python  examples/case3_kras_perm_opt_helmgpt/postprocess_phase1.py            "$RUN"
> tool-mcps/helm_gpt_mcp/env_py3.7/bin/python \
>         examples/case3_kras_perm_opt_helmgpt/postprocess_phase2_prep.py        "$RUN" --top 20
> bash    examples/case3_kras_perm_opt_helmgpt/run_phase2_track_a.sh             "$RUN"     # ~40 min
> bash    examples/case3_kras_perm_opt_helmgpt/run_phase2_gnina.sh               "$RUN" 0   # ~10 min
> # (optional) bash examples/case3_kras_perm_opt_helmgpt/run_phase2_track_b.sh   "$RUN" 1   # only if AF3 needed
> python  examples/case3_kras_perm_opt_helmgpt/postprocess_phase3.py             "$RUN"
> python  workflow-skills/scripts/helmgpt/helmgpt_viz.py                         "$RUN"
> ```
> End-to-end wallclock for 20 top candidates with cached MSA: ~1.5 hours on a single A100.

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
