# Cyclic Peptide Binder Design Workflow

> Automated workflow for designing cyclic peptide binders using AfCycDesign MCP

## Overview

This skill automates the complete cyclic peptide binder design workflow using the AfCycDesign MCP server. It designs cyclic peptides that bind to target protein structures using AlphaFold-based optimization.

## Prerequisites

- AfCycDesign MCP server must be running and accessible
- Target protein PDB file (local file or 4-letter PDB code)

## Workflow Steps

### Step 1: Validate Target Structure

Before submitting a design job, validate the target PDB file to ensure it's properly formatted and identify available chains.

**Tool:** `mcp__afcycdesign_mcp__validate_pdb_file`

**Parameters:**
- `file_path`: Absolute path to the target PDB file

**Expected Output:**
- `valid_pdb`: Should be `true`
- `chains`: List of available chain IDs
- `residues_per_chain`: Number of residues per chain
- `total_residues`: Total residue count

**Action:** If validation fails, inform the user about the issue. If successful, note the available chains and proceed.

### Step 2: Submit Binder Design Job

Submit the binder design job with the validated target structure.

**Tool:** `mcp__afcycdesign_mcp__submit_binder_design`

**Required Parameters:**
- `target_pdb`: Path to validated PDB file (or 4-letter PDB code)
- `binder_len`: Length of binder peptide (typically 8-16 residues)

**Optional Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `target_chain` | "A" | Chain ID of target protein |
| `binder_seq` | null | Initial binder sequence (for seeded design) |
| `hotspot` | null | Target hotspot residues (e.g., "50-60,70-75") |
| `target_flexible` | false | Allow target backbone flexibility |
| `use_multimer` | false | Use AlphaFold-multimer |
| `optimizer` | "pssm_semigreedy" | Optimization method |
| `num_recycles` | 0 | Number of AlphaFold recycles |
| `num_models` | 2 | Number of AF2 models to use |
| `ipae_threshold` | 0.15 | Interface PAE quality threshold (0.11 for strict) |
| `job_name` | null | Optional name for tracking |

**Optimizer Options:**
- `pssm_semigreedy` (recommended): PSSM-guided semi-greedy optimization
- `3stage`: Three-stage logits/soft/hard optimization
- `semigreedy`: Semi-greedy sequence optimization
- `pssm`: PSSM-based optimization
- `logits`, `soft`, `hard`: Single-stage optimizers

**Expected Output:**
- `job_id`: Unique identifier for tracking
- `queue_position`: Position in job queue

### Step 3: Monitor Job Progress

Poll job status periodically until completion. Check logs for optimization progress.

**Tools:**
- `mcp__afcycdesign_mcp__get_job_status` - Check job state
- `mcp__afcycdesign_mcp__get_job_log` - View optimization logs

**Status Values:**
- `pending`: Job queued, waiting to start
- `running`: Job actively executing
- `completed`: Job finished successfully
- `failed`: Job encountered an error
- `cancelled`: Job was cancelled

**Monitoring Strategy:**
1. Check status every 10-15 seconds initially
2. When status is `running`, check logs periodically (tail=30) to show progress
3. Look for key metrics in logs: `loss`, `plddt`, `ptm`, `i_ptm`
4. Continue until status is `completed` or `failed`

**Log Interpretation:**
```
iteration models recycles hard soft temp loss i_con plddt ptm i_ptm
```
- `loss`: Lower is better (target < 2.0)
- `plddt`: Predicted Local Distance Difference Test (target > 0.85)
- `ptm`: Predicted TM-score (target > 0.80)
- `i_ptm`: Interface pTM (target > 0.75)

### Step 4: Retrieve Results

Once the job completes successfully, retrieve the results.

**Tool:** `mcp__afcycdesign_mcp__get_job_result`

**Parameters:**
- `job_id`: The job ID from Step 2

**Expected Output:**
- `output_file`: Path to output PDB file containing target-binder complex
- `success`: Should be `true`

### Step 5: Analyze Results

Read the output PDB file to extract the designed binder sequence and quality metrics.

**Analysis Tasks:**
1. Identify binder chain (usually Chain B)
2. Extract designed amino acid sequence
3. Report per-residue pLDDT scores (B-factor column)
4. Summarize final optimization metrics from logs

**Quality Thresholds:**
| Metric | Excellent | Good | Acceptable |
|--------|-----------|------|------------|
| pLDDT | > 0.90 | > 0.70 | > 0.50 |
| iPTM | > 0.80 | > 0.60 | > 0.40 |
| iPAE | < 0.11 | < 0.15 | < 0.20 |

### Step 6: Visualize Results

Generate publication-quality figures to compare and evaluate designs.

**Script:** `workflow-skills/scripts/afcycdesign/afcycdesign_viz.py`

**Usage:**
```bash
# Generate 6 separate figures
python workflow-skills/scripts/afcycdesign/afcycdesign_viz.py <results_dir>

# Generate merged 2x3 summary figure
python workflow-skills/scripts/afcycdesign/afcycdesign_viz.py <results_dir> --merged

# Custom output prefix
python workflow-skills/scripts/afcycdesign/afcycdesign_viz.py <results_dir> --output my_prefix
```

**Input:** Auto-detects `afcycdesign_results.csv`, individual `*_afcyc.json` files, or `design_metrics.csv` in the results directory.

**Generated Figures:**
| Panel | Title | Description |
|-------|-------|-------------|
| 1 | pLDDT Scores | Bar chart sorted descending, thresholds at 0.70/0.50 |
| 2 | Interface iPAE | Bar chart sorted ascending, thresholds at 0.15/0.20 |
| 3 | Quality Scatter | pLDDT vs iPAE colored by composite score with "good zone" |
| 4 | Design Ranking | Horizontal bar chart by composite score |
| 5 | Metrics Table | Top designs: pLDDT, iPAE, iPTM, pTM, i_con |
| 6 | iPTM Scores | Interface pTM bar chart, thresholds at 0.60/0.40 |

**Composite Score:** `0.30 * pLDDT + 0.30 * iPAE_inv + 0.25 * iPTM + 0.15 * pTM`

## Output Format

Present results in this format:

```markdown
## Binder Design Results

### Job Summary
| Parameter | Value |
|-----------|-------|
| Job ID | {job_id} |
| Target | {target_pdb} (Chain {chain}) |
| Binder Length | {length} residues |
| Status | Completed |

### Designed Cyclic Peptide Binder
**Sequence:** `{sequence}`

### Per-Residue Confidence (pLDDT)
| Position | Residue | pLDDT |
|----------|---------|-------|
| 1 | {AA} | {score} |
...

### Quality Metrics
- **Final Loss:** {loss}
- **pLDDT:** {plddt}
- **pTM:** {ptm}
- **iPTM:** {i_ptm}

### Output File
`{output_path}`
```

## Error Handling

### Job Failed
If job status is `failed`:
1. Check job logs for error messages: `get_job_log(job_id, tail=100)`
2. Common issues:
   - Invalid PDB format
   - Missing chain
   - GPU memory issues
3. Option to resubmit: `mcp__afcycdesign_mcp__resubmit_job`

### Job Stalled
If job shows no progress for extended time:
1. Check queue info: `mcp__afcycdesign_mcp__get_queue_info`
2. Option to cancel: `mcp__afcycdesign_mcp__cancel_job`

## Example Usage

### Basic Binder Design
```
Design a 12-residue cyclic peptide binder for @path/to/target.pdb
```

### With Hotspot Specification
```
Design a 14-mer binder for @target.pdb targeting residues 50-65 on chain A
```

### With Initial Sequence
```
Design a binder starting from sequence "RVKDGYPFAA" for @target.pdb
```

### Strict Quality Filtering
```
Design a high-quality binder for @target.pdb with iPAE threshold 0.11
```

## Recommended Parameters

### Quick Testing
- `binder_len`: 8-10
- `optimizer`: "3stage"
- `num_models`: 1

### Standard Design
- `binder_len`: 12-14
- `optimizer`: "pssm_semigreedy"
- `num_models`: 2

### High-Quality Production
- `binder_len`: 12-16
- `optimizer`: "pssm_semigreedy"
- `num_models`: 2
- `ipae_threshold`: 0.11
- `num_recycles`: 1-3

## Related Tools

- `submit_structure_prediction`: Predict structure from sequence
- `submit_fixbb_design`: Redesign sequence for existing backbone
- `submit_hallucination`: De novo cyclic peptide generation
- `validate_pdb_file`: Validate PDB structure
- `list_jobs`: View all submitted jobs
- `get_queue_info`: Check queue status
