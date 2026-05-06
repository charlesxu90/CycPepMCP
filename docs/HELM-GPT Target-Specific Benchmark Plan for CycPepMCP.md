# HELM-GPT Target-Specific Benchmark Plan for CycPepMCP

**Author:** Manus AI  
**Project:** CycPepMCP: Democratizing Cyclic Peptide Design with Agentic AI  
**Purpose:** This document proposes an executable benchmark plan for extending the CycPepMCP manuscript from a small number of case studies to a systematic **target-specific HELM-GPT benchmark**. The central question is whether HELM-GPT-style reinforcement learning can be evaluated across multiple biologically meaningful targets that have sufficient peptide, cyclic peptide, stapled peptide, or macrocycle activity data to support target-specific reward models.

## 1. Executive Summary

The proposed benchmark is feasible, but it should be framed carefully. HELM-GPT cannot be applied equally well to arbitrary targets, because its target-specific reinforcement learning depends on a **trained property predictor** that serves as the reward function. In the original HELM-GPT study, KRAS binding optimization was possible because the authors curated **2,757 KRAS-related peptide Kd values from a patent**, trained a target-specific predictor, and used that predictor as the reinforcement learning feedback function.[1]

For CycPepMCP, the safest strategy is to construct a benchmark containing **one validated positive-control case** and **four newly curated target-specific cases**. The recommended five cases are **KRAS, PD-1/PD-L1, MDM2/p53, MCL1 or BCL-xL, and CXCR4**. This panel is large enough to show that CycPepMCP is not merely a single-target demonstration, while still remaining realistic from a data-curation perspective.

| Tier | Target Case | Recommended Role | Data Confidence | Main Data Source Type | Expected Use in Manuscript |
|---|---|---|---|---|---|
| P0 | **KRAS** | Positive-control and reproducibility case | Very high | Published HELM-GPT workflow plus patent-derived Kd data | Main benchmark |
| P0 | **PD-1/PD-L1** | Macrocyclic peptide PPI case | High | BMS/Aurigene patents, literature, ChEMBL | Main benchmark |
| P0 | **MDM2/p53** | Classical intracellular PPI peptide case | High | ChEMBL, BindingDB, stapled peptide literature, patents | Main benchmark |
| P0/P1 | **MCL1 or BCL-xL** | BCL-2 family alpha-helical PPI case | Medium-high to high | ChEMBL, BindingDB, BH3/stapled peptide literature | Main or extended benchmark |
| P1 | **CXCR4** | GPCR/cyclic peptide antagonist case | Medium-high | ChEMBL, BindingDB, T140/LY2510924-related literature | Extended benchmark or fifth main case |

The conclusion is that **five cases can likely be assembled**, provided that the benchmark allows patent and supplementary table extraction rather than relying only on already-standardized public database records. If one of the new targets fails the data-quality threshold after curation, **SSTR2, GLP-1R, integrin αvβ3/RGD, or PCSK9** can be used as backups.

## 2. Rationale and Benchmark Objective

The current CycPepMCP manuscript can be strengthened by upgrading isolated demonstrations into a systematic benchmark. A convincing benchmark should answer three questions. First, can CycPepMCP identify targets with enough peptide-like data to build reward models? Second, can the platform train target-specific predictors with acceptable test performance? Third, can HELM-GPT reinforcement learning improve predicted target affinity while maintaining validity, novelty, diversity, and synthetic plausibility?

> The key methodological constraint is that HELM-GPT requires a reliable property predictor. A target with many small-molecule ligands but few peptide or macrocycle records is not necessarily suitable for HELM-GPT target-specific reinforcement learning.

In the original HELM-GPT workflow, generated HELM sequences are converted to SMILES and evaluated by predictive models. These predictive scores are then used as feedback to update the generative model.[1] The KRAS experiment therefore provides a template for a broader benchmark: for each target, CycPepMCP should curate target-specific peptide activity data, train a reward model, run a fixed-budget HELM-GPT optimization, and compare generated candidates against prior models and baseline optimization methods.

## 3. Feasibility Criteria for Including a Target

A target should be included in the main benchmark only if it passes both **data feasibility** and **model feasibility** gates. The purpose of these gates is to avoid weak benchmarks in which HELM-GPT appears to optimize a poorly validated predictor.

| Criterion | Preferred Threshold | Minimum Acceptable Threshold | Rationale |
|---|---:|---:|---|
| Curated target-specific peptide/macrocycle records | >1,000 | 300–500 | Regression reward models need enough structure–activity variation. |
| Quantitative endpoint consistency | Kd/Ki/IC50 dominant | Mixed endpoints acceptable with labels | Endpoint mixing can weaken predictor reliability. |
| Structure availability | SMILES/HELM/direct chemical structure | Extractable from patent/literature figures or tables | HELM-GPT requires molecular structures for reward prediction. |
| Peptide relevance | Cyclic, stapled, peptide-like, or macrocyclic records dominate | Mixed peptide and peptidomimetic records | Pure small-molecule data are not ideal for HELM-GPT. |
| Predictor performance | Spearman >0.6 desirable | Spearman >0.4 minimum | Weak predictors produce unreliable RL optimization. |
| Chemical diversity | Multiple scaffolds or series | At least several congeneric series | A single narrow analog series may overfit. |

For the manuscript, targets passing the preferred thresholds should be reported as **main benchmark cases**. Targets passing only the minimum threshold should be reported as **extended benchmark cases** or used for sensitivity analysis.

## 4. Recommended Five-Target Benchmark Panel

### 4.1 KRAS

KRAS should be retained as the benchmark's positive-control case. The original HELM-GPT paper used a patent-derived KRAS peptide dataset containing **2,757 Kd values**, trained multiple predictors, selected an XGBoost model using molecular fingerprints, and reported a test Spearman correlation of **0.82**.[1] This makes KRAS the most reliable case for validating that the CycPepMCP implementation can reproduce a known HELM-GPT target-specific optimization workflow.

The recommended use of KRAS is not merely to show a new example, but to establish the benchmark baseline. CycPepMCP should reproduce the KRAS reward model and run the same fixed-budget generation protocol used for all other targets. The manuscript can then present KRAS as the calibration case against which new targets are compared.

| Item | Recommendation |
|---|---|
| Benchmark role | Positive-control and reproducibility case |
| Primary endpoint | Kd or transformed pKd |
| Reward model | XGBoost or random forest with molecular fingerprints; optional graph model comparison |
| Expected quality | High; already demonstrated in HELM-GPT |
| Main risk | Ensuring patent-derived structures and activity values are fully reproducible |

### 4.2 PD-1/PD-L1

PD-1/PD-L1 is the strongest new macrocyclic peptide PPI benchmark candidate. The target has a rich patent landscape, especially from BMS and related programs, including macrocyclic peptides and peptidomimetics that inhibit the PD-1/PD-L1 interaction. A patent review describes multiple PD-1/PD-L1 antagonist modalities, including peptides and macrocycles, and reports that some BMS macrocyclic examples achieved low-nanomolar activity in biochemical assays.[2]

This target is valuable because it directly supports the manuscript's claim that CycPepMCP can democratize cyclic peptide design for therapeutically relevant protein–protein interactions. The main work required is patent extraction and endpoint harmonization. ChEMBL contains a substantial number of PD-L1-related quantitative records, but the peptide/macrocycle subset must be curated carefully rather than assumed from the total record count.[3]

| Item | Recommendation |
|---|---|
| Benchmark role | New macrocyclic PPI inhibitor case |
| Primary endpoint | IC50 or pIC50 for PD-1/PD-L1 binding blockade; Kd/Ki if available |
| Reward model | Start with fingerprint-based XGBoost; compare with graph neural network if data size permits |
| Expected quality | High if patent examples are extracted successfully |
| Main risk | Assay heterogeneity across HTRF, binding, cell binding, and functional assays |

### 4.3 MDM2/p53

MDM2/p53 is a highly suitable benchmark case because it is a canonical intracellular protein–protein interaction with a long history of peptide, stapled peptide, and peptidomimetic inhibitor development. It is also familiar to reviewers in chemical biology and peptide therapeutics. ChEMBL contains thousands of quantitative MDM2-related activity records, although the relevant peptide subset must be separated from the small-molecule subset.[3]

This case should be positioned as a classical PPI peptide-design benchmark. It complements KRAS by representing a different PPI interface and complements PD-1/PD-L1 by shifting from an immune checkpoint surface interaction to an intracellular oncogenic PPI. The main curation task is to extract p53-derived peptides, stapled peptides, cyclic peptides, and peptide mimetics with consistent MDM2 binding or inhibition endpoints.

| Item | Recommendation |
|---|---|
| Benchmark role | Classical intracellular PPI peptide case |
| Primary endpoint | Kd, Ki, IC50, or pIC50 for MDM2/p53 disruption |
| Reward model | Fingerprint-based XGBoost as primary; multitask model if MDM4 data are included |
| Expected quality | High after peptide subset curation |
| Main risk | Mixed small-molecule and peptide records if filtering is not strict |

### 4.4 MCL1 or BCL-xL

The BCL-2 family provides a strong fourth case because anti-apoptotic proteins such as MCL1 and BCL-xL bind alpha-helical BH3 motifs, and many peptide, stapled peptide, and peptidomimetic inhibitors have been reported. This target family is mechanistically distinct from KRAS and MDM2 but still fits the **intracellular PPI** narrative.

The recommended primary target is **MCL1**, with **BCL-xL** as an alternative or related auxiliary task. If individual target-specific peptide data are insufficient, a practical strategy is to build a BCL-2-family multitask predictor and then fine-tune or evaluate target-specific rewards for MCL1 or BCL-xL. This approach can improve data efficiency while preserving target-specific evaluation.

| Item | Recommendation |
|---|---|
| Benchmark role | Alpha-helical PPI / apoptosis case |
| Primary endpoint | Kd, Ki, IC50, or pIC50 for target binding or BH3 displacement |
| Reward model | Target-specific model if enough data; otherwise family-level multitask pretraining plus target fine-tuning |
| Expected quality | Medium-high to high |
| Main risk | Selectivity and subtype annotation across BCL-2, BCL-xL, MCL1, and BCL-w |

### 4.5 CXCR4

CXCR4 is recommended as the fifth case because it broadens the benchmark beyond intracellular PPIs. It is a chemokine receptor with a substantial history of peptide and cyclic peptide antagonists, including T140-derived compounds and peptide-like CXCR4 inhibitors. The case can demonstrate that CycPepMCP is not restricted to one target class.

The primary risk is assay heterogeneity. CXCR4 data can include receptor binding, calcium flux, chemotaxis, HIV entry inhibition, and other functional endpoints. Therefore, this case should undergo a stricter data-feasibility check before being locked as a main benchmark target. If the curated peptide/cyclic peptide subset falls below the minimum threshold, CXCR4 should be moved to an extended benchmark and replaced by SSTR2 or GLP-1R.

| Item | Recommendation |
|---|---|
| Benchmark role | GPCR/cyclic peptide antagonist case |
| Primary endpoint | Binding IC50/Ki/Kd preferred; functional IC50 accepted if separated by assay type |
| Reward model | Endpoint-specific model; avoid pooling very different assays without labels |
| Expected quality | Medium-high if cyclic peptide subset is sufficient |
| Main risk | Heterogeneous functional assays and mixed antagonist mechanisms |

## 5. Backup Targets

Backup targets should be curated in parallel during the first feasibility stage. This avoids a situation in which the manuscript depends on a fifth target that later fails model-quality criteria.

| Backup Target | Feasibility | Main Advantage | Main Concern | Recommended Use |
|---|---|---|---|---|
| **SSTR2** | Medium-high | Mature cyclic peptide ligand space, including somatostatin analogs | Chemical space may be narrow | Backup for CXCR4 or extended benchmark |
| **GLP-1R** | Medium-high | Very rich peptide therapeutic data | Mostly linear or modified peptides rather than macrocycles | Peptide-therapeutics benchmark if scope is broadened |
| **Integrin αvβ3/RGD** | Medium-high | Extensive cyclic RGD literature | Target annotation and endpoint formats are fragmented | Strong backup if manual curation effort is available |
| **PCSK9** | Medium | Therapeutically important protein interaction target | Public peptide-specific data may be modest | Secondary backup |
| **IL-17A** | Low-medium | Notable macrocyclic peptide binders exist | Public quantitative data may be too limited | Better as a case study than an RL benchmark |

## 6. Data-Curation Workflow

The benchmark should be implemented as a two-stage funnel. The first stage identifies feasible targets. The second stage performs reward-model training and HELM-GPT optimization only for targets that pass pre-defined gates.

| Step | Task | Output | Recommended Owner |
|---|---|---|---|
| 1 | Query ChEMBL, BindingDB, PubChem BioAssay, and literature for target-specific quantitative records | Raw candidate activity tables | Data curator |
| 2 | Search Google Patents and patent reviews for peptide/macrocycle series | Patent tables and extracted structures | Data curator plus chemistry reviewer |
| 3 | Filter for peptide, cyclic peptide, stapled peptide, macrocycle, and peptide-like molecules | Target-specific peptide/macrocycle subset | Data curator |
| 4 | Normalize endpoints to pKd, pKi, pIC50, or pEC50 | Harmonized activity table | Data scientist |
| 5 | Standardize structures as SMILES and, where possible, HELM | Structure table with molecule IDs | Cheminformatics lead |
| 6 | Deduplicate compounds and aggregate repeated measurements | Final curated target dataset | Data scientist |
| 7 | Split data by scaffold or time, not only randomly | Train/validation/test split | Data scientist |

The final dataset for each target should use a consistent schema. This schema should be saved and released with the benchmark whenever licensing allows.

| Field | Description | Example |
|---|---|---|
| `target_name` | Standard target name | `KRAS`, `PD-L1`, `MDM2` |
| `target_id` | UniProt, ChEMBL target ID, or custom target identifier | `P01116` |
| `molecule_id` | Internal unique molecule identifier | `KRAS_PAT_000123` |
| `smiles` | Standardized canonical SMILES | `C1...` |
| `helm` | HELM representation if available or generated | `PEPTIDE1{...}` |
| `modality` | Peptide class | `cyclic peptide`, `stapled peptide`, `peptidomimetic` |
| `endpoint_type` | Activity endpoint | `Kd`, `Ki`, `IC50` |
| `endpoint_value` | Original activity value | `12.5` |
| `endpoint_unit` | Original unit | `nM` |
| `p_activity` | Normalized negative log activity | `7.90` |
| `assay_type` | Binding, biochemical, cell-based, or functional | `binding` |
| `source` | Patent, paper, ChEMBL, BindingDB, etc. | `US20240158446A1` |
| `split` | Train, validation, or test | `train` |

## 7. Reward-Model Training Plan

For each target, at least three model families should be trained so that the benchmark does not depend on a single modeling assumption. The simplest reliable baseline should be retained even if neural models are tested.

| Model Type | Input Representation | Role | When to Use |
|---|---|---|---|
| XGBoost | Morgan fingerprints plus descriptors | Primary robust baseline | All targets |
| Random forest or ExtraTrees | Fingerprints plus descriptors | Secondary baseline | All targets |
| MLP | Fingerprints, descriptors, or learned embeddings | Lightweight neural baseline | Targets with >500 records |
| Graph neural network | Molecular graph | Optional advanced model | Targets with >1,000 records |
| Sequence/HELM transformer | HELM tokens or peptide sequence | Optional representation-specific model | Targets with reliable HELM strings |

Model evaluation should be reported with both ranking and regression metrics. Because HELM-GPT uses the predictor to rank and reward generated molecules, **Spearman correlation** is especially important. However, RMSE and MAE should also be reported to detect calibration problems.

| Metric | Purpose | Recommended Threshold |
|---|---|---:|
| Spearman correlation | Ranking quality for RL reward | >0.6 preferred; >0.4 minimum |
| Pearson correlation | Linear agreement | >0.5 preferred |
| RMSE | Regression error | Target-dependent |
| Top-k enrichment | Ability to identify high-affinity compounds | Compare against random and prior baseline |
| Scaffold split performance | Generalization across chemical series | Required for main benchmark claims |

## 8. HELM-GPT Optimization Protocol

Once a target passes the reward-model gate, the HELM-GPT optimization protocol should be standardized across targets. This is essential for making the benchmark credible.

| Parameter | Recommended Setting |
|---|---|
| Prior model | Same HELM-GPT prior across all targets, optionally target-finetuned on known peptide series |
| Generated molecules per run | At least 10,000 valid molecules per target for reporting; larger internal exploration if compute permits |
| RL budget | Fixed number of steps and batch size across targets |
| Repeats | At least 3 random seeds per target |
| Reward | Target affinity predictor score, optionally combined with permeability and synthetic accessibility |
| Filters | Valid HELM, convertible SMILES, no duplicate molecules, allowed monomer set, synthetic accessibility threshold |
| Baselines | Prior sampling, best training-set analogs, SMILES GA, graph GA, and/or LSTM hill-climbing if feasible |

The output should not be judged only by predicted affinity. A good benchmark should show whether optimization improves target-specific predicted activity while preserving chemical diversity and novelty.

| Output Metric | Definition | Manuscript Use |
|---|---|---|
| Validity | Fraction of generated HELM strings convertible to valid molecules | General generation quality |
| Uniqueness | Fraction of non-duplicate valid molecules | Diversity and exploration |
| Novelty | Fraction absent from training set | De novo design claim |
| Diversity | Pairwise fingerprint diversity | Avoid mode collapse |
| SNN | Similarity to nearest training molecule | Detect memorization |
| Predicted activity | Reward-model score | Target optimization outcome |
| PASS count | Number passing predefined activity threshold | Practical library-design relevance |
| Synthetic accessibility | SA score or monomer availability | Experimental plausibility |
| Permeability score | Optional co-optimization score | Particularly relevant for intracellular targets |

## 9. Go/No-Go Decision Framework

Each target should be evaluated using a transparent Go/No-Go matrix before being included in the main benchmark. This protects the manuscript from overclaiming.

| Decision Level | Requirement | Recommended Action |
|---|---|---|
| **Go: Main benchmark** | >500–1,000 curated peptide/macrocycle records; Spearman >0.6 or strong top-k enrichment; stable RL improvement across seeds | Include in main results figure and benchmark table |
| **Conditional Go: Extended benchmark** | 300–500 records; Spearman 0.4–0.6; qualitative RL improvement | Include in supplementary benchmark or exploratory section |
| **No-Go for RL benchmark** | <300 usable records or predictor Spearman <0.4 | Use only as qualitative case study or exclude |

This framework should be explicitly described in the Methods or Supplementary Methods. It will make the benchmark more defensible because the reader can see that targets were not cherry-picked after observing favorable results.

## 10. Recommended Manuscript Figures and Tables

The benchmark should produce a compact set of figures that clearly upgrades the manuscript from case study to systematic benchmark.

| Figure/Table | Content | Main Message |
|---|---|---|
| Figure 1 | Benchmark workflow from target selection to data curation, reward-model training, HELM-GPT RL, and candidate filtering | CycPepMCP supports a systematic target-specific design workflow |
| Figure 2 | Target panel table or heatmap showing data size, endpoint type, model performance, and RL success | Multiple targets pass objective feasibility criteria |
| Figure 3 | Reward-model performance for each target, including scatter plots and Spearman values | RL rewards are based on validated predictors |
| Figure 4 | RL optimization curves across targets and seeds | HELM-GPT improves predicted affinity across target classes |
| Figure 5 | Generated candidate distributions for predicted activity, novelty, diversity, and synthetic accessibility | Optimization does not collapse to memorized or unrealistic molecules |
| Supplementary Table 1 | Full curated dataset statistics | Dataset transparency |
| Supplementary Table 2 | Target-specific model hyperparameters and metrics | Reproducibility |
| Supplementary Table 3 | Top generated candidates per target | Practical design output |

## 11. Suggested Timeline

A realistic timeline depends on the depth of patent extraction. A minimal benchmark can be completed in approximately four to six weeks if the team focuses on five to seven candidate targets in parallel and uses robust baseline predictors rather than complex neural models for every target.

| Week | Milestone | Deliverable |
|---|---|---|
| Week 1 | Target data feasibility screen | Candidate target table with raw record counts and data sources |
| Week 2 | Patent and supplementary table extraction | Curated preliminary datasets for KRAS, PD-1/PD-L1, MDM2, MCL1/BCL-xL, CXCR4, and backups |
| Week 3 | Structure standardization and endpoint normalization | Final training tables and train/validation/test splits |
| Week 4 | Reward-model training and validation | Predictor performance table and Go/No-Go decision |
| Week 5 | HELM-GPT RL runs | Generated candidate libraries and optimization curves |
| Week 6 | Analysis and manuscript integration | Figures, tables, Methods text, and Supplementary Data package |

## 12. Final Recommendation

The benchmark should be presented as a **target-specific cyclic peptide design benchmark powered by CycPepMCP**, not merely as an extension of HELM-GPT. The central claim should be that CycPepMCP enables an agentic workflow that can identify data-rich targets, curate activity datasets, train reward models, run HELM-GPT optimization, and evaluate generated cyclic peptide candidates in a reproducible manner.

The recommended main panel is **KRAS, PD-1/PD-L1, MDM2/p53, MCL1 or BCL-xL, and CXCR4**. This set is scientifically coherent, technically feasible, and sufficiently diverse to support a stronger manuscript. The highest-risk component is not HELM-GPT itself, but the **data-curation and reward-model validation step**. Therefore, the project should begin with a fast feasibility sprint across the five main targets and at least two backups before committing to the full benchmark.

## References

[1]: https://academic.oup.com/bioinformatics/article/40/6/btae364/7691994 "HELM-GPT: de novo macrocyclic peptide design using generative pre-trained transformer"

[2]: https://pmc.ncbi.nlm.nih.gov/articles/PMC6323140/ "A patent review on PD-1/PD-L1 antagonists: small molecules, peptides and macrocycles"

[3]: https://www.ebi.ac.uk/chembl/ "ChEMBL Database"

[4]: https://pmc.ncbi.nlm.nih.gov/articles/PMC11056021/ "CyclicPepedia: a comprehensive database of cyclic peptides"
