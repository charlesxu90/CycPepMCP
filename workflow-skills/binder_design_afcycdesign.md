# Cyclic Peptide Binder Design Workflow

> Automated workflow for designing cyclic peptide binders using AfCycDesign MCP

## Overview

This skill automates the complete cyclic peptide binder design workflow using the AfCycDesign MCP server. It designs cyclic peptides that bind to target protein structures using AlphaFold-based optimization, then re-predicts each design independently to obtain the iPAE and unbiased pLDDT on which classification and ranking depend.

Seven steps: validate target, submit design, monitor, collect artifacts, analyze, re-predict (Step 6), visualize. Steps 1-5 produce designs; Step 6 produces the metrics that decide which of them are real.

## Prerequisites

- AfCycDesign MCP server must be running and accessible
- Target protein PDB file (local file or 4-letter PDB code)

### Docker Setup Requirements

The AfCycDesign MCP runs inside a Docker container. Before first use, verify the container has all required directories:

```bash
# Check container is running
docker ps | grep afcyc

# Verify required directories exist inside the container
docker exec <container_id> ls /app/scripts/   # Design scripts
docker exec <container_id> ls /app/params/    # AlphaFold model weights
```

**Common setup issues:**
- **Missing `/app/scripts/`**: The Dockerfile must include `COPY --chmod=755 scripts/ scripts/`. If missing, copy manually: `docker cp tool-mcps/afcycdesign_mcp/scripts <container_id>:/app/scripts`
- **Missing `/app/params/`**: AF model weights (e.g. `params_model_1_ptm.npz`) must be at `/app/params/`. Copy from host: `docker cp tool-mcps/afcycdesign_mcp/params/params_model_1_ptm.npz <container_id>:/app/params/`
- **Symlinked MCP directory**: If `tool-mcps/afcycdesign_mcp` is a symlink, Docker bind mounts cannot follow it for nested paths. The host project mount sees the top-level listing but cannot access files inside the symlinked directory. Copy required files directly into the container instead.

**Minimum params needed by `num_models` setting:**
- `num_models=1`: `params_model_1_ptm.npz` (~356MB)
- `num_models=2`: also needs `params_model_2_ptm.npz`

## Workflow Parameters

Before starting, gather these from the user:

| Parameter | Required | Example |
|-----------|----------|---------|
| Target PDB | Yes | `examples/case1_mdm2_binder_afcycdesign/4HFZ_MDM2.pdb` |
| Output directory | No | User-specified, or auto-derived (see below) |
| Binder length | No (default 12) | 8-16 |
| Target chain | No (default "A") | "A" |
| Hotspot residues | No | "50-60,70-75" |
| Quality level | No (default standard) | quick / standard / production |

**Output directory** collects all artifacts from the run. It is resolved as follows:
1. If the user specifies a path, use it as-is (relative to cwd or absolute)
2. If not specified, auto-derive from the target PDB: `results/<pdb_stem>_afcycdesign/`
   - Example: target `4HFZ_MDM2.pdb` → `results/4HFZ_MDM2_afcycdesign/`

Create it at the start:
```bash
mkdir -p <output_dir>
```

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
- `3stage`: Three-stage logits/soft/hard optimization (120 logits + 60 soft + 10 hard = 190 iterations)
- `semigreedy`: Semi-greedy sequence optimization
- `pssm`: PSSM-based optimization
- `logits`, `soft`, `hard`: Single-stage optimizers

**Expected Output:**
- `job_id`: Unique identifier for tracking
- `queue_position`: Position in job queue

### Step 3: Monitor Job Progress

Poll job status periodically until completion.

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

> **IMPORTANT:** The `get_job_log` MCP tool may return stale/buffered output (e.g. only 2 lines while the actual log has 100+). To get real-time progress, read the log file directly from the Docker container:
> ```bash
> docker exec <container_id> tail -20 /app/jobs/<job_id>/job.log
> docker exec <container_id> wc -l /app/jobs/<job_id>/job.log
> ```

1. After submitting, check `get_job_status` to confirm the job is `running`
2. **Expect a silent period (2-5 minutes)** after the job starts — this is JAX compiling the AlphaFold model and loading weights. The log will only show matplotlib warnings during this time. Do NOT assume the job has stalled.
3. Once iterations begin appearing in the log, check progress using `docker exec <container_id> tail -10 /app/jobs/<job_id>/job.log`
4. Continue until `get_job_status` returns `completed` or `failed`

**Log Interpretation:**
```
iteration models recycles hard soft temp loss i_con plddt ptm i_ptm
```
- `loss`: Lower is better (target < 2.0)
- `plddt`: Predicted Local Distance Difference Test (target > 0.85)
- `ptm`: Predicted TM-score (target > 0.80)
- `i_ptm`: Interface pTM (target > 0.75)

**3-Stage Optimizer Phases:**
| Phase | Iterations | `hard` | `soft` | `temp` | Description |
|-------|-----------|--------|--------|--------|-------------|
| Logits | 1-120 | 0 | increasing 0→1 | 1 | Explore sequence space via logits |
| Soft | 121-180 | 0 | 1 | decreasing 1→0.01 | Anneal soft probabilities |
| Hard | 181-190 | 1 | 1 | 0.01 | Finalize discrete sequence |

**Typical behavior:** Loss drops rapidly in logits phase (5→2), metrics may dip slightly during soft annealing as probabilities sharpen, then stabilize in hard phase. The final hard-phase metrics (not the best logits-phase metrics) reflect the actual designed sequence.

### Step 4: Collect Results to Output Directory

Once the job completes, collect all artifacts from the Docker container into the user-specified output directory.

**Tool:** `mcp__afcycdesign_mcp__get_job_result` to confirm success, then copy files.

**Collect these files:**
```bash
# 1. Output PDB (target-binder complex)
docker cp <container_id>:/app/jobs/<job_id>/output.pdb <output_dir>/binder_<job_id>.pdb

# 2. Full optimization log
docker cp <container_id>:/app/jobs/<job_id>/job.log <output_dir>/binder_<job_id>.log

# 3. Job metadata
docker cp <container_id>:/app/jobs/<job_id>/metadata.json <output_dir>/binder_<job_id>_metadata.json

# 4. Best-checkpoint metrics, including iPAE (not present in the log)
docker cp <container_id>:/app/jobs/<job_id>/output_metrics.json <output_dir>/binder_<job_id>_metrics.json
```

**Expected output directory after this step:**
```
<output_dir>/
  binder_<job_id>.pdb           # Designed complex structure
  binder_<job_id>.log           # Full optimization log
  binder_<job_id>_metadata.json # Job parameters and timestamps
  binder_<job_id>_metrics.json  # pLDDT, PAE, iPAE, iPTM, pTM at the best checkpoint
```

For multiple design runs targeting the same protein, repeat Steps 2-4 with different parameters. All outputs accumulate in the same output directory, each prefixed with its job ID.

### Step 5: Analyze Results

Extract the designed binder sequence and quality metrics from the output PDB.

**Chain Convention:**
- Chain A = target protein (preserved from input)
- Chain B = designed cyclic peptide binder

**PDB Parsing:**

> **IMPORTANT:** Use fixed-width PDB format parsing, NOT space-delimited parsing. Negative coordinates shift columns and break `awk '{print $N}'` approaches.

```python
# Correct: fixed-width PDB format parsing (run on the collected PDB)
python3 -c "
with open('<output_dir>/binder_<job_id>.pdb') as f:
    for line in f:
        if line.startswith('ATOM') and line[21] == 'B' and line[12:16].strip() == 'CA':
            resname = line[17:20].strip()
            resnum = int(line[22:26])
            bfactor = float(line[60:66])
            print(f'{resnum:3d} {resname:3s} {bfactor:6.2f}')
"
```

**Save a summary CSV** to the output directory for downstream visualization:
```python
# Write afcycdesign_results.csv with metrics from all designs in <output_dir>
python3 -c "
import os, csv

output_dir = '<output_dir>'
rows = []
aa3to1 = {'ALA':'A','ARG':'R','ASN':'N','ASP':'D','CYS':'C','GLU':'E','GLN':'Q',
           'GLY':'G','HIS':'H','ILE':'I','LEU':'L','LYS':'K','MET':'M','PHE':'F',
           'PRO':'P','SER':'S','THR':'T','TRP':'W','TYR':'Y','VAL':'V'}

for f in sorted(os.listdir(output_dir)):
    if not f.endswith('.log'): continue
    job_id = f.replace('binder_','').replace('.log','')
    pdb_file = os.path.join(output_dir, f'binder_{job_id}.pdb')
    if not os.path.exists(pdb_file): continue

    # Parse final metrics from log (last iteration line)
    # Log format: '190 models [0] recycles 0 hard 1 soft 1 temp 0.01 loss 2.78 i_con 2.75 plddt 0.69 ptm 0.82 i_ptm 0.64'
    metrics = {}
    with open(os.path.join(output_dir, f)) as lf:
        for line in lf:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[0].isdigit():
                d = {}
                for i in range(len(parts)-1):
                    if parts[i] in ('loss','i_con','plddt','ptm','i_ptm'):
                        d[parts[i]] = parts[i+1]
                if d:
                    metrics = d

    # Parse binder sequence from PDB (first model only)
    seq = []
    with open(pdb_file) as pf:
        for line in pf:
            if line.startswith('ENDMDL'):
                break
            if line.startswith('ATOM') and line[21] == 'B' and line[12:16].strip() == 'CA':
                seq.append(aa3to1.get(line[17:20].strip(), 'X'))

    rows.append({'design': f'binder_{job_id}', 'sequence': ''.join(seq), **metrics})

with open(os.path.join(output_dir, 'afcycdesign_results.csv'), 'w', newline='') as cf:
    w = csv.DictWriter(cf, fieldnames=['design','sequence','loss','i_con','plddt','ptm','i_ptm'])
    w.writeheader()
    w.writerows(rows)
print(f'Wrote {len(rows)} designs to {output_dir}/afcycdesign_results.csv')
"
```

**Design Classification:**

Designs are classified on pLDDT and iPAE, the two metrics that gate selection. Tiers are nested (Excellent implies Good implies Acceptable); a design is reported at the highest tier it meets.

| Class | pLDDT | iPAE |
|-------|-------|------|
| Excellent | > 0.90 | < 0.11 |
| Good | > 0.85 | < 0.15 |
| Acceptable | > 0.70 | < 0.30 |

Designs meeting none of the three are Unclassified and should not be carried forward.

pLDDT is on the **0-1 scale** used in `afcycdesign_results.csv` and the optimization log. The PDB B-factor column stores the same quantity x 100, so a threshold of 0.90 here equals 90 in the deposited structure.

**Ranking Score:**

```
Score = 0.50 * pLDDT + 0.50 * (1 - iPAE)
```

Equal weight on the two gating metrics. iPTM and pTM are not included: on the MDM2 reference set they correlate with pLDDT and iPAE at r > 0.96, and removing them shifted ranks by a mean of 0.8 positions. They remain in the results table as reported metrics.

**iPAE is required for both.** iPAE is *not* emitted by `submit_binder_design`. The design script computes it but ColabDesign filters it out of the streaming log (it carries no loss weight), so it never reaches `job.log` or the summary CSV. Two sources supply it:

1. `<job_dir>/output_metrics.json`, written by `cyclic_binder_design.py` alongside `output.pdb` — collect it in Step 4 (see below).
2. Re-prediction of the designed sequence via `submit_complex_prediction` / `cycpep_target_complex_pred.py --save_json`, which is the stricter and preferred evaluation.

Without iPAE, `afcycdesign_viz.py` substitutes a `1 - loss/5` proxy. The proxy ranks designs differently from true iPAE — on the MDM2 set the top-ranked design changed identity — so classification must not be reported off the proxy.

**Note on which metrics describe the saved structure:** `model.save_pdb()` writes the **best** checkpoint, and `output_metrics.json` reports that same checkpoint. The final log line reports the **last** iteration, which is generally worse. Prefer `output_metrics.json`; if parsing the log instead, be aware its values may not describe the deposited coordinates.

**Note on re-prediction:** design-time metrics are optimistic and must not be used for classification. Step 6 obtains the values that are.


### Step 6: Re-predict Designed Complexes (required for classification)

Design-time metrics are the quantity the optimizer maximised, not an independent assessment. Re-predict each designed sequence against the target to obtain iPAE and an unbiased pLDDT.

**Why this step exists.** On the MDM2 reference set of 50 designs:

| | design-time | re-predicted |
|---|---|---|
| pLDDT mean | 0.865 | 0.664 |
| pLDDT SD | 0.054 | 0.127 (5.6x the variance) |
| correlation between the two | r = 0.227 | |

The design-time distribution is compressed into 0.85-0.92 because that is where `pssm_semigreedy` stops finding improvements — a ceiling artefact of the search, not a property of the designs. Re-prediction restores discrimination: 44 of 50 designs fell, but the 6 that rose were exactly the 6 best by iPAE, and the change in pLDDT correlates with re-predicted iPAE at r = -0.896. Ranking on design-time values selected a different top design (rank 1 became rank 7) than ranking on re-predicted ones.

**Tool:** `mcp__afcycdesign_mcp__submit_complex_prediction`, or `cycpep_target_complex_pred.py --save_json` directly.

**Settings:** AlphaFold-multimer with `num_recycles=6`, `num_models=2`, `target_flexible=True`. These are deliberately stricter than the design-time forward pass (`num_recycles=0`, AF2-ptm weights); the point is an independent test, not a repeat of the optimisation.

Run one invocation per sequence rather than the script's `--peptide_seqs` batch mode: `predict_complex` calls `clear_mem()` and rebuilds the model for every sequence anyway, so batching saves nothing, but its `batch_summary.json` is written only after all sequences finish and one crash loses the whole set. Per-sequence invocation is resumable.

```bash
# Re-predict every design in <output_dir>; skips sequences already done.
# Reads design,sequence pairs from afcycdesign_results.csv (Step 5).
OUT=<output_dir>/repredict
mkdir -p "$OUT"
PDB=<absolute path to target pdb>

tail -n +2 <output_dir>/afcycdesign_results.csv | while IFS=, read -r design sequence rest; do
    [ -f "$OUT/${design}.json" ] && { echo "$design SKIP"; continue; }
    python <afcycdesign_mcp>/scripts/cycpep_target_complex_pred.py \
        --pdb "$PDB" --target_chain A \
        --peptide_seq "$sequence" \
        --num_recycles 6 --num_models 2 \
        --output "$OUT/${design}.pdb" --save_json > "$OUT/${design}.log" 2>&1 \
      && echo "$design DONE" || echo "$design FAILED"
done
```

Each sequence yields `<design>.json` carrying `plddt`, `pae`, `i_pae`, `i_con`, `ptm`, and `i_ptm`. Budget roughly 90 s per design on an A100 (50 designs ~ 75 min).

**Merge into the results table.** The merged CSV keeps both generations so the shift is auditable, and uses column names the visualization normalises (`i_pae` -> `iPAE`, `plddt` -> `pLDDT`):

```python
python3 - <<'EOF'
import csv, json, os
OUT = '<output_dir>/repredict'
orig = {r['design']: r for r in csv.DictReader(open('<output_dir>/afcycdesign_results.csv'))}

rows, missing = [], []
for design, o in orig.items():
    jf = os.path.join(OUT, f'{design}.json')
    if not os.path.exists(jf):
        missing.append(design); continue
    m = json.load(open(jf))['metrics']
    rows.append({'design': design, 'sequence': o['sequence'],
                 'plddt': round(m['plddt'], 4), 'i_pae': round(m['i_pae'], 4),
                 'i_ptm': round(m['i_ptm'], 4), 'ptm': round(m['ptm'], 4),
                 'i_con': round(m['i_con'], 4), 'pae': round(m['pae'], 4),
                 'design_plddt': o['plddt'], 'design_iptm': o['i_ptm'],
                 'design_ptm': o['ptm'], 'loss': o['loss']})

rows.sort(key=lambda r: r['i_pae'])
with open(os.path.join(OUT, 'afcycdesign_results.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(f'wrote {len(rows)} designs')
if missing: print(f'MISSING {len(missing)}: {", ".join(sorted(missing))}')
EOF
```

**Known issue.** `cycpep_target_complex_pred.py` reads the iPTM key as `metrics.get("i_pTM", metrics.get("iptm", 0))`. ColabDesign emits `i_ptm`, so unpatched copies silently record `i_ptm: 0.0` for every design; the true value appears only in the run log. Verify a non-zero `i_ptm` in the first JSON before running the full set. The patched lookup tries `i_ptm` first.

### Step 7: Visualize Results

Generate publication-quality figures in the output directory.

**Script:** `workflow-skills/scripts/afcycdesign/afcycdesign_viz.py`

**Usage:**
```bash
# Generate 6 separate figures (run on the Step 6 output)
python workflow-skills/scripts/afcycdesign/afcycdesign_viz.py <output_dir>/repredict

# Generate merged 2x3 summary figure
python workflow-skills/scripts/afcycdesign/afcycdesign_viz.py <output_dir>/repredict --merged

# Custom output prefix
python workflow-skills/scripts/afcycdesign/afcycdesign_viz.py <output_dir>/repredict --output <output_dir>/summary
```

**Point the script at the re-predicted table, not the design-time one.** The script auto-detects `afcycdesign_results.csv` in the directory it is given. Run against `<output_dir>/repredict` it finds the merged table from Step 6 and uses the real iPAE; run against `<output_dir>` it finds the design-time table, which has no iPAE column, and silently substitutes the `1 - loss/5` proxy.

**How to tell which was used.** Panel 2 is written as `afcycdesign_ipae_comparison.pdf` when true iPAE is present and `afcycdesign_loss_comparison.pdf` when the proxy was substituted. If you see the latter, the figures are not classification-grade — the proxy ranks designs differently from true iPAE (on the MDM2 set it put a different design in first place).

**Generated Figures (saved to output directory):**
| Panel | Title | Description |
|-------|-------|-------------|
| 1 | pLDDT Scores | Bar chart sorted descending, thresholds at 0.90/0.70 |
| 2 | Interface iPAE | Bar chart sorted ascending, thresholds at 0.11/0.30 |
| 3 | Quality Scatter | pLDDT vs iPAE colored by composite score with "good zone" |
| 4 | Design Ranking | Horizontal bar chart by composite score |
| 5 | Metrics Table | Top designs: pLDDT, iPAE, iPTM, pTM, i_con |
| 6 | iPTM Scores | Interface pTM bar chart, thresholds at 0.60/0.40 |

**Composite Score:** `0.50 * pLDDT + 0.50 * (1 - iPAE)` (see Design Classification in Step 5)

**Final output directory structure:**
```
<output_dir>/
  binder_<job_id_1>.pdb              # Complex PDB
  binder_<job_id_1>.log              # Optimization log
  binder_<job_id_1>_metadata.json    # Job metadata
  binder_<job_id_2>.pdb              # (if multiple runs)
  binder_<job_id_2>.log
  binder_<job_id_2>_metadata.json
  afcycdesign_results.csv            # Design-time metrics table (Step 5)
  repredict/                         # Step 6 re-prediction
    <design>.pdb                     #   re-predicted complex per design
    <design>.json                    #   plddt, pae, i_pae, i_ptm, ptm, i_con
    <design>.log                     #   prediction log
    afcycdesign_results.csv          #   merged table -- input to Step 7
  afcycdesign_plddt_scores.pdf       # Visualization figures (vector PDF only)
  afcycdesign_ipae_comparison.pdf    # (or _loss_comparison.pdf when iPAE absent)
  afcycdesign_quality_scatter.pdf
  afcycdesign_design_ranking.pdf
  afcycdesign_metrics_table.pdf
  afcycdesign_iptm_scores.pdf
  afcycdesign_summary.pdf            # (if --merged)
```

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
| Output Directory | {output_dir} |
| Status | Completed |

### Designed Cyclic Peptide Binder
**Sequence:** `{sequence}`

### Per-Residue Confidence (pLDDT)
| Position | Residue | pLDDT |
|----------|---------|-------|
| 1 | {AA} | {score} |
...

### Quality Metrics
- **pLDDT:** {plddt}
- **iPAE:** {i_pae}
- **Class:** {Excellent | Good | Acceptable | Unclassified}
- **Score:** {0.50 * plddt + 0.50 * (1 - i_pae)}
- **pTM:** {ptm}
- **iPTM:** {i_ptm}
- **Final Loss:** {loss}

### Output Files
- Complex PDB: `{output_dir}/binder_{job_id}.pdb`
- Optimization log: `{output_dir}/binder_{job_id}.log`
- Results CSV: `{output_dir}/afcycdesign_results.csv`
- Figures: `{output_dir}/afcycdesign_*.pdf`
```

## Error Handling

### Job Failed
If job status is `failed`:
1. Check job logs for error messages: `get_job_log(job_id, tail=100)` or `docker exec <container_id> cat /app/jobs/<job_id>/job.log`
2. Common issues:

| Error | Cause | Fix |
|-------|-------|-----|
| `No such file or directory: '/app/scripts'` | Dockerfile missing `COPY scripts/` | `docker cp tool-mcps/afcycdesign_mcp/scripts <container_id>:/app/scripts` |
| `ERROR: no model params defined` / `'model_1_ptm' not found` | AF weights missing from container | `docker cp tool-mcps/afcycdesign_mcp/params/params_model_1_ptm.npz <container_id>:/app/params/` |
| `Permission denied: '/.config'` | Matplotlib cache dir (benign warning) | Ignore — does not affect results |
| GPU OOM | Target too large or too many models | Reduce `num_models=1` or use smaller target |

3. After fixing, resubmit: `mcp__afcycdesign_mcp__resubmit_job`

### Job Appears Stalled
If the job status is `running` but logs show no iteration progress:
1. **First 2-5 minutes are normal** — JAX is compiling the model. Check GPU memory usage: `nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader`. A process using 10-30+ GB confirms the model is loading.
2. If no GPU activity after 5 minutes, check queue: `mcp__afcycdesign_mcp__get_queue_info`
3. Option to cancel: `mcp__afcycdesign_mcp__cancel_job`

## Example Usage

### Basic Binder Design (auto-derived output dir)
```
Design a 12-residue cyclic peptide binder for @path/to/target.pdb
```
→ Results saved to `results/target_afcycdesign/`

### With Explicit Output Directory
```
Design a 12-residue cyclic peptide binder for @path/to/target.pdb, save to my_output_dir
```
→ Results saved to `my_output_dir/`

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
