# MDM2/p53 ncAA Macrocycle Design — HELM-GPT Configuration

> HELM-GPT pipeline for designing ncAA macrocyclic peptides that disrupt the MDM2 / p53 interaction.
>
> **Workflow:** Follow `workflow-skills/binder_design_helmgpt.md`. **Important:** unlike AfCycDesign / RFpeptides, HELM-GPT requires a **target-specific trained reward model** before RL can run. See "Required preflight" below.

## Target Information

| Property | Value |
|----------|-------|
| Protein | MDM2 (E3 ubiquitin ligase; p53 negative regulator) |
| Source | Human (UniProt Q00987) — full sequence in `target.fasta` (491 aa) |
| Target side | We design binders that bind MDM2 (preventing it from polyubiquitinating p53) |
| Predicted complex | Boltz-2 / AlphaFold3 against the binder + MDM2 N-terminal domain |

The MDM2 / p53 inhibitor space is the canonical intracellular PPI peptide-design benchmark per the HELM-GPT target-specific plan (`docs/HELM-GPT Target-Specific Benchmark Plan for CycPepMCP.md` §4.3). Decades of stapled peptide / peptidomimetic literature provide a rich data source.

---

## Required preflight (W2c data curation + reward model)

```bash
# 1. ChEMBL pull (peptide / stapled peptide / macrocycle modality only)
python -m benchmark.data_curation.chembl_query \
    --target_chembl_id CHEMBL5023 --target_name MDM2 \
    --output benchmark/data_curation/datasets/raw/mdm2_p53_chembl_raw.csv

# 2. Patent + literature extraction
#    Stapled peptides (ATSP-7041, ALRN-6924), spirooxindole peptidomimetics — rich literature.
#    Use the patent_extract template; transcribe activity tables.
python -m benchmark.data_curation.patent_extract init \
    --patent_id <PATENT_ID> --output benchmark/data_curation/datasets/raw/patents/<PATENT_ID>.csv
python -m benchmark.data_curation.patent_extract merge \
    --patents_dir benchmark/data_curation/datasets/raw/patents/ \
    --output benchmark/data_curation/datasets/raw/mdm2_p53_patents_merged.csv \
    --target_name MDM2

# 3. Normalize endpoints
python -m benchmark.data_curation.normalize_endpoints \
    --inputs benchmark/data_curation/datasets/raw/mdm2_p53_chembl_raw.csv \
             benchmark/data_curation/datasets/raw/mdm2_p53_patents_merged.csv \
    --target_id Q00987 \
    --output benchmark/data_curation/datasets/mdm2_p53.csv \
    --require_modality   # Filter to peptide / macrocycle / stapled subset

# 4. Scaffold split
python -m benchmark.data_curation.scaffold_split \
    --input  benchmark/data_curation/datasets/mdm2_p53.csv \
    --output benchmark/data_curation/datasets/mdm2_p53_split.csv

# 5. Train + validate XGBoost reward model
python -m benchmark.reward_models.train_xgboost \
    --input benchmark/data_curation/datasets/mdm2_p53_split.csv \
    --target_id hg_mdm2p53 \
    --out_dir benchmark/reward_models/trained
# Output: benchmark/reward_models/trained/hg_mdm2p53.pkl
#         benchmark/reward_models/trained/hg_mdm2p53_metrics.json
```

The runner gates on `scaffold_split_spearman ≥ 0.4`. **Critical filtering note**: ChEMBL has thousands of MDM2 records, but most are **small molecules** (Nutlin-3a, RG7388, idasanutlin etc.). Use `--require_modality` to drop the small-molecule subset; the resulting peptide-only set should be 500-1500 records.

If the trained model falls below the gate, **promote a backup target** (MCL1 / CXCR4 / SSTR2).

---

## MDM2-Specific Parameters

### Phase 1: RL Co-optimization

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `task` | `mdm2_p53_perm` (custom — mirror `kras_perm` template) | Co-optimize MDM2 binding + permeability (intracellular target) |
| `reward_model_path` | `benchmark/reward_models/trained/hg_mdm2p53.pkl` | Target-specific (preflight above) |
| `permeability_model` | (shared) | Permeability is target-agnostic |
| `n_steps` | 500 | Standard from case3 KRAS |
| `batch_size` | 32 | Standard |
| `prior_model` | (same HELM-GPT prior as case3) | |
| `loss_type` | `reinvent_cpl` | |

### Phase 2: Structural Evaluation

Routed by heavy-atom count. Boltz-2 / AF3 / Gnina against MDM2 monomer.

For best AF3 prediction, **truncate to the N-terminal p53-binding domain** (residues ~17-125, ~110 aa) before Phase 2. Full-length 491-aa MDM2 has multiple disordered regions that hurt confidence scores. The truncated domain is what crystal structures use (e.g. 4HFZ).

### Phase 3: Composite Scoring

Centralized weights from `workflows.yaml` `helmgpt.composite_weights`.

### Quality Thresholds (PASS Gate)

Same as `workflows.yaml` `helmgpt.pass_gates.primary` — see `examples/co_opt_pd1pdl1_kd_perm/PDL1_config.md` for the full table.

---

## Notes

- **Intracellular target**: permeability co-optimization is essential. The target is inside the cell (regulating p53), so candidates need to cross the membrane.
- **Stapled-peptide literature**: ATSP-7041 (Aileron), ALRN-6924 are well-characterized stapled peptide MDM2 inhibitors with published Kd / IC50 values — primary patent + literature source for the curated dataset.
- **Cross-workflow comparison**: MDM2 is also the target of `examples/binder_mdm2/` (cyclic peptide via RFpeptides) and `examples/binder_mdm2/` (cyclic peptide via AfCycDesign). The HELM-GPT case explores ncAA macrocycles for the same target — a 3-way workflow comparison on identical biology.
- **MSA precomputation**: same as PD-L1 case; run on login node before HPC submission.
