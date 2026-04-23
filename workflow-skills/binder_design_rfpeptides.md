# RFpeptides Full Protocol Workflow

> Complete cyclic peptide binder design protocol using RFpeptides with iterative sequence optimization and multi-layer validation

## Overview

This skill implements the complete RFpeptides protocol for designing high-affinity cyclic peptide binders. The workflow combines deep learning-based backbone generation, iterative sequence design with structural refinement, and comprehensive validation using both DL and physics-based metrics.

**Protocol Architecture:**
```
STAGE 1: Backbone Generation (RFpeptides)
    ↓
STAGE 2: Iterative Sequence Design (4 rounds of ProteinMPNN + Rosetta Relax)
    ↓
STAGE 3: DL-Based Validation (AfCycDesign reprediction)
    ↓
STAGE 4: Physics-Based Quality Filtering (Rosetta ddG, SAP, CMS)
    ↓
STAGE 5: Structural Diversity & Final Selection (RMSD clustering)
```

## Prerequisites

### Required MCP Servers
| MCP Server | Purpose | Stage(s) |
|------------|---------|----------|
| `rfpeptides_mcp` | Backbone generation | 1 |
| `proteinmpnn_mcp` | Sequence design | 2 |
| `rosetta_kic_mcp` | Structure refinement & metrics | 2, 4 |
| `afcycdesign_mcp` | DL validation | 3 |

### Input Requirements
- Target protein PDB file (properly formatted)
- Target chain ID
- Optional: Hotspot residues for epitope-specific design
- Binder length (typically 7-16 residues)

---

## Stage 1: Backbone Generation (RFpeptides)

Generate cyclic peptide backbone structures that are geometrically compatible with the target binding site.

### Target Difficulty & Design Scale

The RFpeptides paper (Nat Chem Biol 2025, s41589-025-01929-w) reports that in-silico pass rates depend strongly on target surface topology. Concave pockets yield iPAE distributions centered near the pass threshold; flat surfaces produce distributions peaked near iPAE ~0.9 with only a thin low-iPAE tail. Generate designs at scale that matches target difficulty.

| Target class | Example | num_designs (paper) | Raw iPAE pass rate |
|--------------|---------|---------------------|---------------------|
| Concave pocket | MCL1 | 9,965 backbones | ~8% pass iPAE < 0.30 |
| Concave pocket | MDM2 | 40,000 | ~19% pass iPAE < 0.30 |
| Shallow groove | GABARAP | 80,000 (20k backbones × seqs) | ~2% pass iPAE < 0.13 |
| Flat β-helix | RbtA | 80,000 | ~2% pass iPAE < 0.40 |

**Practical guidance:**
- Concave pocket targets: 2,000–10,000 designs typically sufficient to find hits
- Flat / β-sheet / groove targets: 20,000–80,000 designs; relax iPAE threshold (see Stage 3)
- Small pilot runs (< 200 designs) cannot be expected to yield passing candidates on flat targets — the paper's 98% failure rate on RbtA implies ~1 expected pass per 50 designs even at relaxed thresholds.

### Step 1.1: Validate Target Structure

**Tool:** `mcp__rfpeptides_mcp__validate_pdb_file`

**Parameters:**
- `file_path`: Absolute path to target PDB file

**Expected Output:**
- `valid`: Should be `true`
- `chains`: List of available chain IDs
- `residues_per_chain`: Residue count per chain

**Action:** If validation fails, fix PDB issues before proceeding.

### Step 1.2: Submit Backbone Generation Job

Choose the appropriate submission tool based on design requirements:

#### Option A: Basic Binder Design

**Tool:** `mcp__rfpeptides_mcp__submit_cyclic_binder`

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `target_pdb` | (required) | Path to target PDB file |
| `binder_length` | (required) | Cyclic peptide length (7-20 residues typical) |
| `num_designs` | (required) | Number of backbones to generate (2k–10k pockets; 20k–80k flat surfaces) |
| `target_chain` | "A" | Target protein chain ID |
| `binder_length_max` | null | Max length for variable-length generation |
| `target_start_residue` | null | Start residue of target to include |
| `target_end_residue` | null | End residue of target to include |
| `diffusion_steps` | 50 | Number of diffusion timesteps |
| `cyclic` | true | Generate cyclic peptide binders |
| `job_name` | null | Optional job identifier |

#### Option B: Epitope-Specific Design (Recommended)

**Tool:** `mcp__rfpeptides_mcp__submit_cyclic_binder_with_hotspots`

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `target_pdb` | (required) | Path to target PDB file |
| `hotspot_residues` | (required) | List of integer residue numbers (e.g., `[54, 56, 58, 61]`) |
| `binder_length` | (required) | Cyclic peptide length |
| `num_designs` | (required) | Number of backbones to generate (2k–10k pockets; 20k–80k flat surfaces) |
| `target_chain` | "A" | Target chain ID |
| `binder_length_max` | null | Max length for variable-length generation |
| `diffusion_steps` | 50 | Number of diffusion timesteps |
| `cyclic` | true | Generate cyclic peptide binders |
| `job_name` | null | Optional identifier |

**Hotspot Selection Tips:**
- Use known binding epitopes from literature
- Include residues critical for protein function
- Aim for 3-8 hotspot residues
- Example for MDM2: `hotspot_residues=[54, 56, 58, 61, 67, 96, 99, 100]`

### Step 1.3: Monitor Job Progress

**Tools:**
- `mcp__rfpeptides_mcp__get_job_status` - Check job state
- `mcp__rfpeptides_mcp__get_job_log` - View generation logs

**Status Values:**
- `pending`: Queued
- `running`: Actively generating
- `completed`: Successfully finished
- `failed`: Error occurred

**Monitoring Strategy:**
1. Check status every 30-60 seconds
2. View logs to track diffusion progress
3. Continue until `completed` or `failed`

### Step 1.4: Retrieve Backbone Results

**Tool:** `mcp__rfpeptides_mcp__get_job_result`

**Parameters:**
- `job_id`: Job ID from Step 1.2

**Output:**
- Multiple backbone-only PDB files (N, CA, C, O atoms)
- All residues are glycine (sequence to be designed in Stage 2)
- Files named: `design_0.pdb`, `design_1.pdb`, etc.
- **Chain assignments:** Binder = Chain A, Target = Chain B

**Important:** These are backbone-only structures - sequence design is required in Stage 2. When using ProteinMPNN, design Chain A (binder) while fixing Chain B (target).

---

## Stage 2: Iterative Sequence Design (4 Rounds)

This stage iteratively optimizes sequences through 4 rounds of ProteinMPNN design followed by Rosetta relaxation. The relaxation step introduces local backbone changes that enable more diverse sequences in subsequent rounds.

### Round Structure (Repeat 4 Times)

```
For each backbone from Stage 1:
    For round = 1 to 4:
        A. ProteinMPNN: Design sequences for current backbone
        B. Rosetta Relax: Refine structure (creates backbone diversity)
        Use relaxed structure as input for next round
```

### Step 2.A: ProteinMPNN Sequence Design

**Tool:** `mcp__proteinmpnn_mcp__ca_only_design`

> **Critical:** Use `ca_only_design` because RFpeptides outputs backbone-only structures. Standard ProteinMPNN requires full side chains.

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `input_file` | (required) | Path to backbone PDB |
| `chains` | null | Space-separated chain IDs to design (e.g., "A" for binder) |
| `model` | "v_48_020" | CA-only model version |
| `num_sequences` | 3 | Number of sequences to generate |
| `temperature` | 0.1 | Sampling temperature (use 0.0001 for deterministic) |
| `backbone_noise` | 0.0 | Gaussian noise std dev for backbone atoms |
| `omit_AAs` | null | Amino acids to exclude (e.g., "C" to avoid disulfides) |
| `output_dir` | null | Optional directory to save outputs |

> **Note:** For cyclic peptide design, recommended settings:
> - `temperature=0.0001` for near-deterministic sampling (most confident predictions)
> - `omit_AAs="C"` to exclude cysteine and avoid unwanted disulfide bonds
> - `backbone_noise=0` to preserve the designed backbone geometry
> - For diversity, use higher temperature (0.1-0.3) or generate more sequences

**Round-Specific Strategy:**
- Round 1-2: Generate more sequences (num_sequences=5) for diversity
- Round 3-4: Use relaxed backbones which naturally produce different sequences
- Select best-scoring sequences from each round

**Output:**
- FASTA file with designed sequences
- Per-residue scores
- Global sequence recovery metrics

**Cyclic Peptide Design Tips:**
- **Exclude Cysteine:** Use `omit_AAs="C"` to prevent unwanted disulfide bonds that can disrupt cyclic topology
- **Low Temperature:** Use `temperature=0.0001` for deterministic, high-confidence sequences
- **No Backbone Noise:** Use `backbone_noise=0` to maintain the designed cyclic geometry
- **Higher Diversity:** For exploring sequence space, increase temperature to 0.1-0.3

### Step 2.B: Rosetta Relax Refinement

**Tool:** `mcp__rosetta_kic_mcp__submit_cycpep_fast_relax`

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `input_file` | (required) | PDB with designed sequence (cyclic peptide-target complex) |
| `rounds` | 4 | Number of FastRelax rounds with PeptideCyclizeMover |
| `xml` | null | Optional path to custom RosettaScripts XML |
| `job_name` | null | Optional job identifier |

**Purpose of Relaxation:**
1. Introduce local backbone changes
2. Enable more diverse sequences in next round
3. Resolve steric clashes from sequence design
4. Optimize side chain rotamers
5. Maintain cyclic peptide bond via PeptideCyclizeMover

**Output:**
- Refined PDB structures (one per round)
- Energy scores (Rosetta REU)
- Select lowest-energy structure for next round

### Iterative Loop Implementation

```
For each design_i.pdb from Stage 1:
    current_structure = design_i.pdb

    For round = 1 to 4:
        # Step 2.A: Sequence Design
        # Note: RFpeptides outputs binder on chain A, target on chain B
        sequences = ca_only_design(
            input_file=current_structure,
            chains="A",  # Design the binder chain (A), not the target (B)
            model="v_48_020",
            num_sequences=5,
            temperature=0.0001,  # Near-deterministic for best sequence
            backbone_noise=0,    # Preserve backbone geometry
            omit_AAs="C"         # Exclude cysteine (no disulfides)
        )

        # Apply best sequence to structure (requires custom script or manual editing)
        # This step mutates GLY residues to the designed sequence
        best_sequence_pdb = apply_sequence(current_structure, sequences[0])  # pseudocode

        # Step 2.B: Rosetta Relax (cyclic peptide-aware)
        relaxed_job = submit_cycpep_fast_relax(
            input_file=best_sequence_pdb,
            rounds=4
        )
        # Wait for job completion, then retrieve results
        relaxed_structures = get_job_result(relaxed_job["job_id"])

        # Select best relaxed structure for next round
        # Parse Rosetta output and select structure with lowest total_score
        current_structure = select_lowest_energy(relaxed_structures)  # pseudocode

    # Save final round 4 structure for validation
    save(current_structure, f"round4_design_{i}.pdb")
```

---

## Stage 3: DL-Based Validation (AfCycDesign)

Validate designed complexes using AlphaFold-based binder design with the designed sequence as initial input.

### Step 3.1: Submit Binder Validation

**Tool:** `mcp__afcycdesign_mcp__submit_binder_design`

> **Note:** Use `submit_binder_design` with the designed sequence (`binder_seq`) to validate binding. The tool will repredict the complex and provide confidence metrics.

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `target_pdb` | (required) | Path to target protein PDB |
| `binder_len` | (required) | Length of the binder peptide |
| `binder_seq` | (required) | Designed binder sequence from Stage 2 |
| `target_chain` | "A" | Target chain ID |
| `hotspot` | null | Restrict binding positions (e.g., "1-10,12,15") |
| `num_recycles` | 0 | Number of AlphaFold recycles |
| `num_models` | 2 | Number of AF2 models to use |
| `optimizer` | "pssm_semigreedy" | Optimization method |
| `ipae_threshold` | 0.15 | Interface PAE quality threshold |
| `use_multimer` | false | Use AlphaFold-multimer |
| `job_name` | null | Optional job identifier |

**Alternative: Cyclic Peptide Structure Prediction Only**

**Tool:** `mcp__afcycdesign_mcp__submit_structure_prediction`

Use this to predict the isolated binder structure (without target) to assess folding propensity:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `sequence` | (required) | Designed binder sequence |
| `num_recycles` | 6 | AlphaFold recycles (6 recommended) |
| `add_rg` | false | Add radius of gyration constraint |
| `rg_weight` | 0.1 | Weight for Rg loss |
| `soft_iters` | 0 | Soft optimization iterations |
| `job_name` | null | Optional identifier |

**Purpose:**
- Validate binder-target complex using AlphaFold
- Extract interface confidence metrics (iPAE)
- Compare repredicted structure to designed structure

### Step 3.2: Monitor and Retrieve Results

**Tools:**
- `mcp__afcycdesign_mcp__get_job_status`
- `mcp__afcycdesign_mcp__get_job_result`

### Step 3.3: Extract DL Validation Metrics

**Key Metrics to Calculate:**

#### iPAE (Interface Predicted Aligned Error)
```
iPAE = mean PAE at binder-target interface residues
```
- Lower is better
- **Target-specific thresholds (from RFpeptides paper):**
  - MCL1 / MDM2: iPAE < 0.30 (concave pocket)
  - GABARAP: iPAE < 0.13 (shallow groove)
  - RbtA: iPAE < 0.40 (flat β-helix — paper explicitly raised threshold)
  - General pocket: iPAE < 0.20
  - General flat surface: iPAE < 0.35

#### Structural RMSD
```
RMSD = Cα RMSD between designed and repredicted binder
```
- Compare binder backbone in original vs repredicted complex
- **Threshold:** Cα RMSD < 1.5 Å
- Lower RMSD = higher confidence in design

#### pLDDT (Predicted Local Distance Difference Test)
```
pLDDT = mean per-residue confidence score
```
- From B-factor column of output PDB
- **Thresholds:**
  - Excellent: > 0.90
  - Good: > 0.70
  - Acceptable: > 0.50

### Validation Decision Tree

```
IF iPAE < threshold AND RMSD < 1.5 Å AND pLDDT > 0.70:
    → PASS: Proceed to Stage 4
ELSE IF iPAE < threshold AND (RMSD > 1.5 Å OR pLDDT < 0.70):
    → UNCERTAIN: Consider for Stage 4 with lower priority
ELSE:
    → FAIL: Discard design
```

---

## Stage 4: Physics-Based Quality Filtering (Rosetta)

Apply physics-based metrics to validate binding and structural quality.

### Step 4.1: Compute Interface Metrics (ddG, SAP, CMS)

**Tool:** `mcp__rosetta_kic_mcp__submit_interface_metrics`

Compute physics-based interface metrics for cyclic peptide-target complexes. The tool applies PeptideCyclizeMover and Cartesian minimization, then computes ddG, SAP, and CMS in a single job.

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `input_files` | (required) | List of PDB file paths (complexes from Stage 2/3) |
| `peptide_chain` | "A" | Peptide chain ID in the PDB |
| `ddg_threshold` | -40.0 | ddG filter threshold (more negative = better) |
| `sap_threshold` | 35.0 | SAP filter threshold (lower = better solubility) |
| `cms_threshold` | 300.0 | CMS filter threshold in Å² (higher = more contact) |
| `job_name` | null | Optional job identifier |

**Output:**
- Per-structure ddG, SAP, CMS values
- Pass/fail status per structure
- CSV file with all metrics
- Summary of how many designs pass filters

#### Metric Descriptions

**ddG (Interface Binding Energy)**
- Computed via Rosetta ddG filter with InterfaceAnalyzer protocol
- **Thresholds (REU):**
  - Excellent: ddG < -50
  - Good: ddG < -30
  - Acceptable: ddG < -20

**SAP (Spatial Aggregation Propensity)**
- Measures surface hydrophobicity
- **Threshold:** SAP < 35
- Lower SAP = better solubility

**CMS (Contact Molecular Surface)**
- Interface contact area
- **Threshold:** CMS > 300 Å²
- Higher CMS = more extensive interface

### Step 4.2: Optional Structure Refinement

**Tool:** `mcp__rosetta_kic_mcp__submit_cycpep_fast_relax`

Use this to further refine complex structures before or after metric computation:

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `input_file` | (required) | Complex PDB file |
| `rounds` | 4 | Number of FastRelax rounds |
| `xml` | null | Custom XML protocol |
| `job_name` | null | Optional identifier |

### Stage 4 Filtering Workflow

```
For each validated design from Stage 3:
    # Compute interface metrics (ddG, SAP, CMS)
    metrics_job = submit_interface_metrics(
        input_files=[complex_pdb],
        peptide_chain="A"
    )
    # Wait for completion, then retrieve results
    metrics = get_job_result(metrics_job["job_id"])

    # Use iPAE from Stage 3 + physics metrics for filtering
    IF iPAE < 0.15 AND ddG < -30 AND SAP < 35 AND CMS > 300:
        → HIGH PRIORITY: Strong predicted binder
    ELSE IF iPAE < 0.20 AND ddG < -20:
        → MEDIUM PRIORITY: Acceptable predicted binder
    ELSE:
        → LOW PRIORITY: Weak binding predicted
```

---

## Stage 5: Structural Diversity & Final Selection

Select diverse, high-quality designs for experimental validation.

### Step 5.1: RMSD Computation

**Tool:** `mcp__rosetta_kic_mcp__submit_rmsd_benchmark`

Compute backbone heavy-atom RMSD between predicted and reference structures, or between pairs of designs for clustering.

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `input_file` | null | Predicted PDB file (single mode) |
| `native_file` | null | Native/reference PDB file (single mode) |
| `input_dir` | null | Directory of predicted PDBs (batch mode) |
| `native_dir` | null | Directory of native PDBs (batch mode, matched by filename) |
| `rmsd_cutoff` | 2.0 | RMSD pass/fail cutoff in Angstroms |
| `job_name` | null | Optional job identifier |

**Clustering Strategy:**

1. Calculate pairwise Cα RMSD between all passing designs using batch mode
2. Cluster with RMSD cutoff (typically 1.0-2.0 Å)
3. Identify cluster representatives

### Step 5.2: Ranking Within Clusters

For each cluster, rank designs by:
1. **Primary:** ddG (more negative = better)
2. **Secondary:** iPAE (lower = better)
3. **Tertiary:** pLDDT (higher = better)

### Step 5.3: Final Selection

**Recommended Selection Strategy:**
- Select top 1-2 designs from each structural cluster
- Prioritize designs with:
  - ddG < -30 kcal/mol
  - iPAE < 0.20
  - RMSD < 1.5 Å
  - pLDDT > 0.70
- Aim for 5-10 diverse designs for experimental testing

---

## Stage 6: Visualize Results

Generate publication-quality figures summarizing the pipeline results.

### Step 6.1: Generate Visualization Figures

**Script:** `workflow-skills/scripts/rfpeptides/rfpeptides_viz.py`

**Input:** `final_summary.csv` from the pipeline output directory

**Usage:**

```bash
# Generate 6 separate figures (default)
python workflow-skills/scripts/rfpeptides/rfpeptides_viz.py <results_dir>

# Generate a single merged 2x3 summary figure
python workflow-skills/scripts/rfpeptides/rfpeptides_viz.py <results_dir> --merged

# Custom output prefix
python workflow-skills/scripts/rfpeptides/rfpeptides_viz.py <results_dir> --output results/my_prefix
```

**Example:**

```bash
python workflow-skills/scripts/rfpeptides/rfpeptides_viz.py results/case2_RbtA_v2/prod_pipeline --merged
```

### Generated Figures

| Panel | Title | Type | Description |
|-------|-------|------|-------------|
| 1 | Binding Energy (ddG) | Bar chart | Designs sorted by ddG (more negative = better), thresholds at -30/-50 |
| 2 | Interface iPAE | Bar chart | Sorted ascending (lower = better), thresholds at 0.15/0.20 |
| 3 | Quality Scatter | Scatter plot | ddG vs iPAE, colored by composite score, "good zone" shaded |
| 4 | Design Ranking | Horizontal bar | Composite score ranking, colored by pass/fail |
| 5 | Metrics Table | Table | Top designs with ddG, iPAE, pLDDT, SAP, CMS, pass/fail |
| 6 | Execution Timeline | Gantt chart | 5 pipeline stages from pipeline.log timestamps |

### Composite Score Formula

Designs are ranked by a weighted composite score (0-1, higher = better):

```
Score = 0.3 * ddG_norm + 0.25 * iPAE_norm + 0.2 * pLDDT_norm + 0.15 * CMS_norm + 0.1 * SAP_norm
```

All metrics are normalized to 0-1; ddG/iPAE/SAP are inverted since lower values are better.

### Programmatic Access

For Jupyter notebooks or scripts, use the `display_results()` function:

```python
from workflow_skills.scripts.rfpeptides.rfpeptides_viz import display_results

# Display figures inline (notebook) or in GUI window (terminal)
figures = display_results("results/case2_RbtA_v2/prod_pipeline")
```

---

## Quality Thresholds Reference Table

| Metric | Excellent | Good | Acceptable | Description |
|--------|-----------|------|------------|-------------|
| iPAE | < 0.13 | < 0.20 | < 0.30 | Interface confidence |
| RMSD | < 1.0 Å | < 1.5 Å | < 2.0 Å | Reprediction fidelity |
| pLDDT | > 0.90 | > 0.70 | > 0.50 | Per-residue confidence |
| ddG | < -50 | < -30 | < -20 | Binding energy (kcal/mol) |
| SAP | < 25 | < 35 | < 45 | Aggregation propensity |
| CMS | > 400 | > 300 | > 200 | Contact surface (Å²) |

### Target-Specific iPAE Thresholds

Thresholds reported in the RFpeptides paper (Nat Chem Biol 2025) vary substantially by target. The authors explicitly raised thresholds for flat surfaces where most designs fail confidence filters (paper p.1955: "adjustments to filtering thresholds were required on the basis of the shape and chemical composition of the target pocket").

| Target | Strict | Relaxed | Surface Type |
|--------|--------|---------|--------------|
| MCL1 | 0.20 | 0.30 | Concave pocket |
| MDM2 | 0.20 | 0.30 | Concave pocket |
| GABARAP | 0.13 | 0.20 | Shallow groove |
| RbtA | 0.30 | 0.40 | Flat β-helix surface |
| General pocket | 0.15 | 0.25 | — |
| General flat | 0.25 | 0.35 | — |

---

## Output Format

Present final results in this format:

```markdown
## RFpeptides Design Results

### Job Summary
| Parameter | Value |
|-----------|-------|
| Target | {target_name} (Chain {chain}) |
| Binder Length | {length} residues |
| Designs Generated | {num_backbones} |
| Designs Validated | {num_passed} |

### Top Designs

#### Design 1: {design_id}
| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Sequence | `{sequence}` | - | - |
| iPAE | {value} | < 0.20 | PASS/FAIL |
| RMSD | {value} Å | < 1.5 Å | PASS/FAIL |
| pLDDT | {value} | > 0.70 | PASS/FAIL |
| ddG | {value} kcal/mol | < -30 | PASS/FAIL |

**Output File:** `{output_path}`

[Repeat for additional designs]

### Clustering Summary
| Cluster | Designs | Representative | ddG |
|---------|---------|----------------|-----|
| 1 | {n} | {design_id} | {ddG} |
| 2 | {n} | {design_id} | {ddG} |

### Recommended for Experimental Testing
1. {design_id_1} - Best overall metrics
2. {design_id_2} - Best ddG
3. {design_id_3} - Most diverse structure
```

---

## Error Handling

### Stage 1: Backbone Generation Fails
- Check target PDB format
- Verify chain ID exists
- Reduce num_designs if GPU memory issues
- Retry with different random seed

### Stage 2: Sequence Design Issues
- **All glycines:** Ensure using `ca_only_design` not standard design
- **Poor scores:** Increase temperature slightly
- **Relax failures:** Check for severe clashes, reduce cycles

### Stage 3: Validation Failures
- **High iPAE:** Design may not bind as intended. For flat surfaces, expect most designs to have iPAE 0.7–0.9 — this is consistent with the paper (Supp Fig. 4). Scale up generation (≥20k) and use target-appropriate threshold.
- **High RMSD:** Backbone may have changed significantly
- **Low pLDDT:** Binder region may be disordered. Common for extended loop-like binders on flat surfaces; use pLDDT > 0.60 for flat targets instead of 0.70.
- **Very low pass rate (<2%):** Normal for flat/difficult targets. Confirm `num_designs` is large enough (see Target Difficulty & Design Scale in Stage 1).

### Stage 4: Poor ddG
- Interface may be unfavorable
- Try different hotspot residues
- Consider longer binder length

---

## Example Usage

### Basic Design for MDM2
```
Design a cyclic peptide binder for @examples/4HFZ_MDM2.pdb using RFpeptides:
- Binder length: 12 residues
- Generate 10 backbone designs
- Target chain A
- Run full 4-round iterative sequence design
- Validate with AfCycDesign
- Filter by ddG < -30 kcal/mol
```

### Epitope-Specific Design for GABARAP
```
Design cyclic peptide binders for @examples/GABARAP.pdb:
- Target hotspot residues: [21, 24, 25, 28, 49, 50, 51, 52]
- Binder length: 14 residues
- Generate 20 backbones for diversity
- Use strict iPAE threshold of 0.13
- Cluster final designs by RMSD
```

### High-Throughput Screening
```
Design diverse binders for @target.pdb:
- Generate 50 backbone designs
- Run 4 rounds of sequence optimization
- Validate all designs with AfCycDesign
- Apply physics filters (ddG < -20, SAP < 35)
- Cluster and select top 10 diverse designs
```

---

## MCP Tools Quick Reference

| Stage | MCP Server | Tool | Purpose |
|-------|------------|------|---------|
| 1 | rfpeptides_mcp | `validate_pdb_file` | Validate target |
| 1 | rfpeptides_mcp | `submit_cyclic_binder` | Basic backbone generation |
| 1 | rfpeptides_mcp | `submit_cyclic_binder_with_hotspots` | Epitope-specific generation |
| 1 | rfpeptides_mcp | `get_job_status` | Monitor job |
| 1 | rfpeptides_mcp | `get_job_result` | Retrieve backbones |
| 2 | proteinmpnn_mcp | `ca_only_design` | Sequence design (CA-only) |
| 2 | rosetta_kic_mcp | `submit_cycpep_fast_relax` | Backbone relaxation with PeptideCyclizeMover |
| 3 | afcycdesign_mcp | `submit_binder_design` | Complex validation (with binder_seq) |
| 3 | afcycdesign_mcp | `submit_structure_prediction` | Isolated binder folding |
| 4 | rosetta_kic_mcp | `submit_interface_metrics` | ddG, SAP, CMS interface metrics |
| 4 | rosetta_kic_mcp | `submit_cycpep_fast_relax` | Optional structure refinement |
| 5 | rosetta_kic_mcp | `submit_rmsd_benchmark` | Structural RMSD for clustering |

---

## Automated Pipeline Script

For production runs with many backbones, use the unified pipeline script that automates Stages 2-5 with parallel processing and checkpoint-based resume.

**Location:** `workflow-skills/scripts/rfpeptides/run_pipeline.py`

### Basic Usage

```bash
python workflow-skills/scripts/rfpeptides/run_pipeline.py \
    --stage1_dir /path/to/rfpeptides/backbones \
    --target_pdb /path/to/target.pdb \
    --output_dir results/pipeline_output
```

### CLI Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--stage1_dir` | (required) | Directory with RFpeptides backbone PDBs |
| `--target_pdb` | (required) | Target protein PDB file |
| `--output_dir` | `results/pipeline_output` | Output directory |
| `--num_rounds` | 4 | ProteinMPNN + Relax iterations |
| `--workers` | 20 | CPU workers for Stage 2 (parallel) |
| `--gpu_workers` | 4 | GPU workers for Stage 3 (AfCycDesign) |
| `--num_gpus` | 2 | GPUs for AfCycDesign rotation |
| `--ipae_threshold` | 0.3 | iPAE filter threshold (use 0.4 for flat surfaces like RbtA) |
| `--ddg_threshold` | -50.0 | ddG filter threshold (REU) |
| `--sap_threshold` | 35.0 | SAP filter threshold |
| `--cms_threshold` | 300.0 | CMS filter threshold (A^2) |
| `--rmsd_cutoff` | 2.0 | RMSD clustering cutoff (A) |
| `--start_stage` | 2 | Resume from stage (2-5) |
| `--max_designs` | None | Limit designs (for testing) |
| `--sequential` | (flag) | Disable parallelism |

### Output Directory Structure

```
results/pipeline_output/
├── pipeline.log              # Full execution log
├── pipeline_config.json      # Run configuration
├── checkpoint.json           # Resume checkpoint
├── final_summary.csv         # Ranked results table
├── stage2/                   # ProteinMPNN + Relax outputs
│   ├── sequences.csv         # All designed sequences
│   └── <design_id>/          # Per-design round directories
├── stage3/                   # AfCycDesign validation
│   ├── afcycdesign_results.csv
│   └── <design_id>_afcyc.*   # PDB + JSON per design
├── stage4/                   # Interface metrics
│   └── interface_metrics.csv
└── stage5/                   # Clustering + final selection
    ├── clusters.json
    └── cluster*_rep_*.pdb    # Cluster representative PDBs
```

### Example: Production Run

```bash
# Full parallel run on 50 backbones
python workflow-skills/scripts/rfpeptides/run_pipeline.py \
    --stage1_dir results/backbones \
    --target_pdb examples/case1_cycpep_design/4HFZ_MDM2.pdb \
    --output_dir results/mdm2_production \
    --workers 20 --gpu_workers 4 --num_gpus 2

# Resume from Stage 3 after crash
python workflow-skills/scripts/rfpeptides/run_pipeline.py \
    --stage1_dir results/backbones \
    --target_pdb examples/case1_cycpep_design/4HFZ_MDM2.pdb \
    --output_dir results/mdm2_production \
    --start_stage 3

# Quick test with 2 designs, sequential
python workflow-skills/scripts/rfpeptides/run_pipeline.py \
    --stage1_dir results/backbones \
    --target_pdb examples/case1_cycpep_design/4HFZ_MDM2.pdb \
    --output_dir results/test_run \
    --max_designs 2 --sequential
```

### Key Features

- **Auto-detect tool paths** — Resolves ProteinMPNN, Rosetta, and AfCycDesign from `tool-mcps/`
- **Parallel processing** — ProcessPoolExecutor for CPU (Stage 2) and GPU (Stage 3) work
- **Checkpoint resume** — Per-design tracking; restart from any stage without re-running completed work
- **JSON recovery** — Recovers Stage 3 results from existing JSON files after crashes
- **GPU rotation** — Distributes AfCycDesign jobs across available GPUs
- **RMSD clustering** — Greedy structural clustering of passing designs (Stage 5)

---

## Related Workflows

- `binder_design_afcycdesign.md` - AfCycDesign-only binder design
- `structure_prediction.md` - Structure prediction from sequence
- `sequence_optimization.md` - Advanced sequence refinement

## References

- RFpeptides paper: De novo design of high-affinity binders
- ProteinMPNN: Robust deep learning for protein sequence design
- AfCycDesign: AlphaFold-based cyclic peptide optimization
- Rosetta: Macromolecular modeling suite
