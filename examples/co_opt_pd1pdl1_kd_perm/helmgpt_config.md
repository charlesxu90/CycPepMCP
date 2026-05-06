# PD-1/PD-L1 ncAA Macrocycle Design — HELM-GPT Configuration

> HELM-GPT pipeline (RL with target-specific reward model + permeability co-optimization, then structural eval) for designing ncAA macrocyclic peptides that block PD-1 / PD-L1 signaling.
>
> **Workflow:** Follow `workflow-skills/binder_design_helmgpt.md`. **Important:** unlike AfCycDesign / RFpeptides, HELM-GPT requires a **target-specific trained reward model** before RL can run. See "Required preflight" below.

## Target Information

| Property | Value |
|----------|-------|
| Protein | PD-L1 (Programmed death-ligand 1) |
| Source | Human (UniProt Q9NZQ7) — full sequence in `target.fasta` (290 aa) |
| Target side | We design binders that bind PD-L1 (the cancer-associated side); they block PD-L1 / PD-1 engagement |
| Predicted complex | Boltz-2 / AlphaFold3 against the binder + PD-L1 sequence |

The PD-L1 / PD-1 inhibitor space is the strongest macrocyclic-peptide PPI benchmark candidate per the HELM-GPT target-specific plan (`docs/HELM-GPT Target-Specific Benchmark Plan for CycPepMCP.md` §4.2).

---

## Required preflight (W2c data curation + reward model)

HELM-GPT cannot use a generic predictor for a new target. You must complete the data-curation pipeline before invoking the runner:

```bash
# 1. ChEMBL pull (peptide / macrocycle modality only)
python -m benchmark.data_curation.chembl_query \
    --target_chembl_id CHEMBL3582 --target_name PD-L1 \
    --output benchmark/data_curation/datasets/raw/pd1_pdl1_chembl_raw.csv

# 2. Patent extraction (manual transcription)
#    BMS / Aurigene macrocyclic peptide patents are the richest source.
#    See `docs/HELM-GPT Target-Specific Benchmark Plan for CycPepMCP.md` §4.2 for citations.
python -m benchmark.data_curation.patent_extract init \
    --patent_id <PATENT_ID> --output benchmark/data_curation/datasets/raw/patents/<PATENT_ID>.csv
# (transcribe activity tables...)
python -m benchmark.data_curation.patent_extract merge \
    --patents_dir benchmark/data_curation/datasets/raw/patents/ \
    --output benchmark/data_curation/datasets/raw/pd1_pdl1_patents_merged.csv \
    --target_name PD-L1

# 3. Normalize endpoints
python -m benchmark.data_curation.normalize_endpoints \
    --inputs benchmark/data_curation/datasets/raw/pd1_pdl1_chembl_raw.csv \
             benchmark/data_curation/datasets/raw/pd1_pdl1_patents_merged.csv \
    --target_id Q9NZQ7 \
    --output benchmark/data_curation/datasets/pd1_pdl1.csv

# 4. Scaffold split (70/15/15)
python -m benchmark.data_curation.scaffold_split \
    --input  benchmark/data_curation/datasets/pd1_pdl1.csv \
    --output benchmark/data_curation/datasets/pd1_pdl1_split.csv

# 5. Train + validate XGBoost reward model
python -m benchmark.reward_models.train_xgboost \
    --input benchmark/data_curation/datasets/pd1_pdl1_split.csv \
    --target_id hg_pd1pdl1 \
    --out_dir benchmark/reward_models/trained
# Output: benchmark/reward_models/trained/hg_pd1pdl1.pkl
#         benchmark/reward_models/trained/hg_pd1pdl1_metrics.json
```

The runner gates on `scaffold_split_spearman ≥ 0.4` (per `workflows.yaml` `helmgpt.pass_gates.reward_model.spearman_min_pass`). If the trained model falls below the gate, **promote a backup target** (MCL1 / CXCR4 / SSTR2 — see plan §5).

**Recommended target dataset sizes** (per HELM-GPT plan §3 feasibility gates):
- Preferred: > 1000 curated peptide / macrocycle records
- Minimum acceptable: 300-500
- KRAS positive control had 2,757 records → Spearman 0.82

---

## PD-L1-Specific Parameters

### Phase 1: RL Co-optimization

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `task` | `pd1_pdl1_perm` (custom — mirror `kras_perm` template) | Co-optimize binding KD + permeability |
| `reward_model_path` | `benchmark/reward_models/trained/hg_pd1pdl1.pkl` | Target-specific XGBoost (preflight above) |
| `permeability_model` | (shared — same RF as case3 KRAS) | Permeability is target-agnostic |
| `n_steps` | 500 | Standard from case3 KRAS |
| `batch_size` | 32 | Standard |
| `prior_model` | (same HELM-GPT prior as case3) | LLM-agnostic prior |
| `loss_type` | `reinvent_cpl` | Default in benchmark plan §2.3 |

### Phase 2: Structural Evaluation

Routed by heavy-atom count (`workflows.yaml` `helmgpt.structural_routing.heavy_atom_threshold = 128`):

- **≤ 128 atoms** (Track A): Boltz-2 SMILES affinity (3-head ensemble) + AlphaFold3 + Gnina docking against the PD-L1 monomer.
- **\> 128 atoms** (Track B): AlphaFold3 + Gnina only (Boltz-2 ligand limit).

### Phase 3: Composite Scoring

Centralized weights from `workflows.yaml` `helmgpt.composite_weights`:

`0.20·KD + 0.15·perm + 0.15·boltz_aff + 0.10·boltz_prob + 0.10·boltz_iptm + 0.15·gnina_cnn + 0.15·gnina_vina`

### Quality Thresholds (PASS Gate)

Per `workflows.yaml` `helmgpt.pass_gates.primary`:

| Metric | Primary gate | Excellent |
|--------|--------------|-----------|
| KD | < 10 μM | < 1 μM |
| Permeability | > -6.0 log cm/s | > -5.0 |
| Boltz-2 ligand iPTM | ≥ 0.70 | ≥ 0.80 |
| AF3 ligand iPTM | ≥ 0.60 | ≥ 0.80 |
| Gnina CNN pKd | ≥ 6.0 | ≥ 7.0 |
| Gnina Vina | ≤ -7.0 kcal/mol | ≤ -8.0 |

---

## Notes

- **No PDB target file**: HELM-GPT operates on the FASTA + structural prediction (Boltz-2 / AF3) for binding mode evaluation. The structural input for Phase 2 is the FASTA in this directory.
- **MSA**: Phase 2 AF3 prediction needs an MSA. Pre-compute on a login node:
  ```bash
  bash workflow-skills/scripts/helmgpt/run_target_msa.sh examples/co_opt_pd1pdl1_kd_perm/target.fasta
  ```
  (mirror `examples/co_opt_kras_kd_perm/run_target_msa.sh`)
- **Why PD-L1 (not PD-1)**: PD-L1 is the cancer-side; clinical mAbs (atezolizumab, durvalumab, avelumab) all target PD-L1. A macrocyclic alternative is the publication-relevant story.
