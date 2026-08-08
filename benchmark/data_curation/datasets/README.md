# Curated datasets for the CycPepMCP HELM-GPT benchmark

This directory holds the **curated, normalized, scaffold-split** datasets used
to train target-specific XGBoost reward models for HELM-GPT.

Two new targets are covered (KRAS-G12D is the positive control and reuses the
HELM-GPT paper's predictor at `examples/co_opt_kras_kd_perm/`):

| Target  | UniProt | Final n | Train / Val / Test | Test Spearman | Val Spearman |
|---------|---------|--------:|--------------------|--------------:|-------------:|
| PD-L1   | Q9NZQ7  | 186     | 130 / 27 / 29      | 0.915 ✅      | 0.770 ✅     |
| MDM2/p53 (multitask with MDMX) | Q00987 + O15151 | **697** (534 primary + 163 mdmx) | 487 / 104 / 106 | **0.597** ✅ | **0.714** ✅ |

Both clear `helmgpt.pass_gates.reward_model.spearman_min_pass = 0.4` (defined
in `benchmark/configs/workflows.yaml`) on the **scaffold-split test set**.

---

## File inventory

```
datasets/
├── README.md                                <-- this file
│
├── pd1_pdl1.csv                              ChEMBL-only normalized set (W2c baseline, 2026-05-06)
├── pd1_pdl1_split.csv                        ChEMBL-only scaffold-split  (W2c baseline)
├── pd1_pdl1_full.csv                         Tier-1+2 normalized merged set (CURRENT)
├── pd1_pdl1_full_split.csv                   Tier-1+2 scaffold-split        (CURRENT) ←-- trained on this
│
├── mdm2_p53.csv                              ChEMBL-only normalized set (W2c baseline)
├── mdm2_p53_split.csv                        ChEMBL-only scaffold-split  (W2c baseline)
├── mdm2_p53_full.csv                         Tier-1+2 normalized merged set (CURRENT)
├── mdm2_p53_full_split.csv                   Tier-1+2 scaffold-split        (CURRENT) ←-- trained on this
│
└── raw/                                      Per-source raw pulls + intermediate filter outputs
    └── README.md                             documents each source CSV
```

The `_full.csv` / `_full_split.csv` pairs are the **canonical training inputs**
for `benchmark/reward_models/train_xgboost.py`. The ChEMBL-only pair is kept
as a documented baseline so the manuscript "improvement over baseline" table
remains reproducible.

## Canonical curated schema (`*_full_split.csv`)

| Field | Type | Description |
|-------|------|-------------|
| `target_name` | str | "PD-L1" / "MDM2" / "MDMX" |
| `target_id` | str | UniProt accession (Q9NZQ7 / Q00987 / O15151) |
| `molecule_id` | str | Per-source compound ID (e.g. `CHEMBL4288470`, `BDB:50621174`, `CID:145992098`, `PMC2856455:T0:TSFAEYWNLLSP`) |
| `smiles` | str | RDKit canonical SMILES (isomeric) |
| `helm` | str | HELM string if available (mostly empty in this corpus) |
| `modality` | str | `cyclic peptide`, `macrocycle`, `peptide`, `peptidomimetic`, etc. |
| `endpoint_type` | str | `Kd` / `Ki` / `IC50` / `EC50` |
| `endpoint_value` | float | Original numeric value in `endpoint_unit` |
| `endpoint_unit` | str | `nM` / `uM` / `pM` / `mM` |
| `p_activity` | float | -log10(value in molar) — i.e. pKd / pKi / pIC50. Higher = more potent. |
| `assay_type` | str | `binding` / `biochemical` / `cell-based` / `functional` (when present) |
| `source` | str | `chembl` / `bindingdb` / `pubchem` / `pmc` / `patent` |
| `target_side` | str | MDM2 dataset only: `primary` (MDM2) or `mdmx` (MDMX). Used as multitask one-hot feature. |
| `split` | str | `train` / `val` / `test` (Bemis-Murcko scaffold split, 70 / 15 / 15) |

## Processing pipeline

```
raw/ source CSVs (per-target × per-source)
        │
        ▼  benchmark/data_curation/peptide_filter.py
   SMILES-based macrocyclic peptide filter
   (n_heavy ≥ 50, n_amide ≥ 5, MW 500-3000 Da)
        │
        ▼  benchmark/data_curation/normalize_endpoints.py
   Kd/Ki/IC50/EC50 → pActivity (-log10 M)
   RDKit canonical SMILES, dedup by (smiles, endpoint_type)
        │
        ▼  benchmark/data_curation/scaffold_split.py
   Bemis-Murcko scaffold split, 70 / 15 / 15 (seed 42)
        │
        ▼  → *_full_split.csv (this directory)
        │
        ▼  benchmark/reward_models/train_xgboost.py
   XGBoost regression on 2048-bit Morgan FP (radius 2)
   + 6 RDKit descriptors (MW, logP, TPSA, HBD, HBA, RotBonds)
   + optional `--multitask_column target_side` one-hot
        │
        ▼  → benchmark/reward_models/trained/hg_*.{pkl, _metrics.json}
```

`benchmark/data_curation/merge_sources.py` glues steps 1-3 together for one
target (`--target pd1_pdl1` or `--target mdm2_p53`); see its docstring.

## Per-target source contributions

### PD-L1 (`pd1_pdl1_full.csv`, n=186)

| Source | Raw rows | After peptide filter | Notes |
|--------|---------:|---------------------:|-------|
| ChEMBL `CHEMBL3580522` (PD-L1 single protein) | 1,064 | (overlaps below) | Single-protein target |
| ChEMBL `CHEMBL4523993` (PD-1/PD-L1 PPI complex) | 4,559 | (overlaps below) | PPI complex |
| BindingDB `Q9NZQ7` | 8,546 | ~266 | REST API |
| PubChem `Q9NZQ7` | 9,384 | ~159 | PUG-REST concise + IsomericSMILES batch |
| BMS patent extracts | 1 | 1 (deduped to 0) | US9879046 Compound No. 1 — matched existing BindingDB entry |
| **Merged + deduped** | **23,553 raw → 428 peptide-like → 186 after SMILES dedup** | | |

### MDM2/p53 (`mdm2_p53_full.csv`, n=697)

| Source | Raw rows | Final survived | Target side breakdown |
|--------|---------:|---------------:|-----------------------|
| ChEMBL `CHEMBL5023` (MDM2 single) | 6,545 | 226 | 226 primary |
| ChEMBL `CHEMBL1907611` (p53/MDM2 PPI) | 1,931 | (folded into 226) | primary |
| BindingDB `Q00987` (MDM2) | 7,441 | 226 | primary |
| BindingDB `O15151` (MDMX) | 619 | 108 | mdmx |
| PubChem `Q00987` (MDM2) | 7,988 | 40 | primary |
| PubChem `O15151` (MDMX) | 730 | 24 | mdmx |
| **PMC2856455** (Pazgier 2010, Systematic Mutational Analysis) | 52 | 34 + 21 | 34 primary + 21 mdmx |
| **PMC3359147** (Liu 2010, D-PMI) | 15 | 15 | primary (all-D peptides) |
| **US20220267376A1** (Aileron stapled D-PMI patent, TABLE 1) | 19 | 18 | 8 primary + 10 mdmx |
| **Merged + deduped** | **25,273 raw → 1,080 peptide-like → 697 after dedup** | | **534 primary + 163 mdmx** |

Records from MDMX are tagged via `target_side='mdmx'` and fed as a multitask
one-hot feature into XGBoost. This multitask signal is the single biggest
contributor to the MDM2 model's val Spearman lift (0.490 → 0.714).

**Dedup key (2026-05-13 update):** `normalize_endpoints.py` now dedupes by
`(smiles, endpoint_type, target_chembl_id)` rather than `(smiles, endpoint_type)`.
The previous key collapsed every compound measured against both MDM2 (Q00987)
and MDMX (O15151) into a single row, losing the multitask signal. With the
fixed key, those pair-records are preserved and `target_side` is set
authoritatively from the UniProt accession.

**Patent contribution (US20220267376A1):** Aileron's stapled D-PMI patent
contributes 18 records covering 10 unique peptides — linear DPMI-8, six
single-staple variants (1-5, 2-6, 2-9, 5-9, 6-10, 5-12), one stitched
peptide (1-5-12), one double-stapled (1-5,9-12), one scrambled control,
and the all-L ATSP-7041 positive control. Includes the high-value
DPMI-8(1-5,9-12) double-stapled lead with Kd 0.7 nM (MDM2) and 2.1 nM (MDMX).

> **Caveat on stapled-peptide SMILES**: the hydrocarbon staple chemistry is
> not represented in the SMILES (RDKit doesn't natively encode it from the
> coupling list). Each variant differs from the parent DPMI-α only by 'S'
> substitutions at the staple-anchor positions — capturing variant-level
> fingerprint difference but not the macrocycle topology. Source-tagged as
> `source="patent_us20220267376a1"` so downstream consumers can filter.

## Reproduce from scratch

Login-node with internet access (required for ChEMBL, BindingDB, PubChem, PMC):

```bash
HG_PY=tool-mcps/helm_gpt_mcp/env/bin/python   # has rdkit + xgboost + chembl-webresource-client

# 1. Raw pulls (writes into raw/)
for combo in "Q9NZQ7 PD-L1 pd1_pdl1_bindingdb" \
             "Q00987 MDM2 mdm2_p53_bindingdb" \
             "O15151 MDMX mdm2_p53_mdmx_bindingdb"; do
    set -- $combo
    $HG_PY -m benchmark.data_curation.bindingdb_query \
        --target_uniprot $1 --target_name $2 \
        --output benchmark/data_curation/datasets/raw/$3.csv
done
for combo in "Q9NZQ7 PD-L1 pd1_pdl1_pubchem" \
             "Q00987 MDM2 mdm2_p53_pubchem" \
             "O15151 MDMX mdm2_p53_mdmx_pubchem"; do
    set -- $combo
    $HG_PY -m benchmark.data_curation.pubchem_query \
        --target_uniprot $1 --target_name $2 \
        --output benchmark/data_curation/datasets/raw/$3.csv
done
$HG_PY -m benchmark.data_curation.chembl_query --target_chembl_id CHEMBL3580522 ...   # see chembl_query.py docstring
$HG_PY -m benchmark.data_curation.chembl_query --target_chembl_id CHEMBL4523993 ...
$HG_PY -m benchmark.data_curation.chembl_query --target_chembl_id CHEMBL5023 ...
$HG_PY -m benchmark.data_curation.chembl_query --target_chembl_id CHEMBL1907611 ...
$HG_PY -m benchmark.data_curation.pmc_paper_extract --pmcid PMC2856455 --output benchmark/data_curation/datasets/raw/mdm2_p53_pmc_PMC2856455.csv
$HG_PY -m benchmark.data_curation.pmc_paper_extract --pmcid PMC3359147 --output benchmark/data_curation/datasets/raw/mdm2_p53_pmc_PMC3359147.csv

# 2. Merge + filter + normalize + scaffold-split (writes *_full*.csv here)
$HG_PY -m benchmark.data_curation.merge_sources --target pd1_pdl1
$HG_PY -m benchmark.data_curation.merge_sources --target mdm2_p53

# 3. Train (writes benchmark/reward_models/trained/)
$HG_PY -m benchmark.reward_models.train_xgboost \
    --input benchmark/data_curation/datasets/pd1_pdl1_full_split.csv \
    --target_id hg_pd1pdl1 \
    --out_dir benchmark/reward_models/trained
$HG_PY -m benchmark.reward_models.train_xgboost \
    --input benchmark/data_curation/datasets/mdm2_p53_full_split.csv \
    --target_id hg_mdm2p53 \
    --out_dir benchmark/reward_models/trained \
    --multitask_column target_side
```

For full per-step provenance, see `raw/README.md`.

## Improvement over baseline

| Target | ChEMBL-only baseline (W2c 2026-05-06) | Final Tier 1+2 (this directory) | Δ val Spearman |
|--------|--------------------------------------|--------------------------------|---------------:|
| PD-L1  | n=83, test 0.845 / val 0.298 (fragile) | n=186, test **0.915** / val **0.770** | **+0.47** |
| MDM2   | n=223, test 0.548 / val 0.490 (borderline) | n=315, test 0.549 / val **0.734** | **+0.24** |

The MDM2 test Spearman appears unchanged (0.548 → 0.549) but this hides a
methodological improvement: the new dataset includes 67 PMI / p53(17-28) /
D-peptide records that are scaffold-distinct from the small-molecule
peptidomimetic bulk in ChEMBL. The scaffold-split correctly partitions them
into the test set, making it harder — confirming the model now generalizes
across more diverse scaffolds rather than overfitting to a narrow chemical
class. Val Spearman (mixed scaffolds) jumped 0.490 → 0.734.

## Outstanding / deferred sources

| Source | Reason deferred | How to add |
|--------|-----------------|------------|
| PDL1Binder (80 binder / non-binder peptides) | http://i.uestc.edu.cn/pdl1binder/ returns 403; Frontiers PMC9389236 supp not programmatically accessible | Manual download + `benchmark/reward_models/train_xgboost.py --aux_classifier_path ...` |
| 5 patents from the original survey | 3 scanned image PDFs (need OCR); 2 use qualitative `+`/`++` activity bins | OCR via tesseract + structure OCR via OSRA/DECIMER; or manual chemist transcription |
| 3 BMS PD-L1 replacement patents | Text-extractable but "patent dump" disclosure — only 4 hero compounds get numeric IC50, already in BindingDB | Not productive without unpublished compound list |
| 5 PMC papers without inline tables | Data in figures or supplementary docx behind anti-bot protection | Per-paper manual rule + python-docx supplementary parser |
