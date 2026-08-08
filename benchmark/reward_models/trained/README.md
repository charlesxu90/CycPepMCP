# Trained HELM-GPT reward models

XGBoost regressors that predict pActivity for cyclic peptide candidates
during HELM-GPT Phase 1 reinforcement learning. One model per HELM-GPT
benchmark target.

The runner (`benchmark/scripts/workflow_runners/helmgpt_runner.py`) reads the
companion `*_metrics.json` and enforces the **Spearman ≥ 0.4 gate** before
allowing RL to start; below that floor the run aborts with
`error_type=scientific`.

## File inventory

| File | Size | Purpose |
|------|-----:|---------|
| `hg_pd1pdl1.pkl` | ~770 KB | XGBoost regressor for PD-L1 |
| `hg_pd1pdl1_metrics.json` | ~600 B | Per-split metrics (Spearman, Pearson, RMSE, MAE, R², top-10% enrichment) |
| `hg_mdm2p53.pkl` | ~790 KB | XGBoost regressor for MDM2 / MDMX (multitask) |
| `hg_mdm2p53_metrics.json` | ~600 B | Per-split metrics |

The KRAS-G12D positive-control predictor lives at
`examples/co_opt_kras_kd_perm/rl_predictors/` (reused from the HELM-GPT paper)
and is **not retrained here** — it goes directly into the runner.

## Current metrics

| Target | n_train / n_val / n_test | Test Spearman | Val Spearman | Test R² | Excellent (≥0.6)? |
|--------|--------------------------|--------------:|-------------:|--------:|:-----------------:|
| **hg_pd1pdl1** (PD-L1) | 130 / 27 / 29 | **0.915** | **0.770** | 0.86 | ✅ both splits |
| **hg_mdm2p53** (MDM2 + MDMX multitask) | **487 / 104 / 106** | **0.597** | **0.714** | 0.40 | ✅ test + val |

Both pass the workflows.yaml `helmgpt.pass_gates.reward_model.spearman_min_pass = 0.4`
gate; PD-L1 also clears the "excellent" tier in both splits.

## Model architecture

```
input SMILES
    │
    ▼  RDKit
2048-bit Morgan fingerprint (radius 2)  +  6 RDKit descriptors
                                          (MolWt, MolLogP, TPSA, NumHDonors,
                                           NumHAcceptors, NumRotatableBonds)
    │
    ▼  optional (MDM2 only)
+ one-hot for target_side ∈ {primary=MDM2, mdmx=MDMX}     <-- multitask head
    │
    ▼
xgb.XGBRegressor(
    n_estimators=400,
    max_depth=6,
    learning_rate=0.05,
    objective="reg:squarederror",
    tree_method="hist",
    random_state=42,
)
    │
    ▼
predicted pActivity (= -log10(IC50 in molar); higher → more potent)
```

The trainer also exposes `--aux_classifier_path <path>` for an external
binder/non-binder probability feature (e.g. the deferred PDL1Binder
auxiliary classifier); currently unused.

## metrics.json schema

```json
{
  "target_id": "hg_pd1pdl1",
  "n_train": 130,
  "n_val": 27,
  "n_test": 29,
  "test_spearman": 0.915,
  "test_pearson": 0.94,
  "test_rmse": 0.346,
  "test_mae": 0.27,
  "test_r2": 0.86,
  "test_top_10pct_enrichment": 0.67,
  "scaffold_split_spearman": 0.915,
  "val_spearman": 0.770,
  ...
}
```

The runner specifically reads `scaffold_split_spearman` (alias of
`test_spearman` for backwards compatibility with the helm_gpt_mcp interface).

## How they were trained

```bash
HG_PY=tool-mcps/helm_gpt_mcp/env/bin/python

# PD-L1
$HG_PY -m benchmark.reward_models.train_xgboost \
    --input benchmark/data_curation/datasets/pd1_pdl1_full_split.csv \
    --target_id hg_pd1pdl1 \
    --out_dir benchmark/reward_models/trained

# MDM2/MDMX multitask
$HG_PY -m benchmark.reward_models.train_xgboost \
    --input benchmark/data_curation/datasets/mdm2_p53_full_split.csv \
    --target_id hg_mdm2p53 \
    --out_dir benchmark/reward_models/trained \
    --multitask_column target_side
```

The training CSV must contain `smiles`, `p_activity`, `split`, plus
`target_side` for MDM2. See `../../data_curation/datasets/README.md` for how
the inputs are produced.

## Loading at inference time

```python
import pickle
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors
from rdkit.DataStructs import ConvertToNumpyArray

with open("benchmark/reward_models/trained/hg_pd1pdl1.pkl", "rb") as f:
    payload = pickle.load(f)
model = payload["model"]
feature_dim = payload["feature_dim"]   # 2054 = 2048 FP + 6 descriptors (no multitask)

def featurize(smiles):
    mol = Chem.MolFromSmiles(smiles)
    fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
    arr = np.zeros((2048,), dtype=np.uint8)
    ConvertToNumpyArray(fp, arr)
    descs = np.array([
        Descriptors.MolWt(mol), Descriptors.MolLogP(mol),
        Descriptors.TPSA(mol), Descriptors.NumHDonors(mol),
        Descriptors.NumHAcceptors(mol), Descriptors.NumRotatableBonds(mol),
    ], dtype=np.float32)
    return np.concatenate([arr.astype(np.float32), descs])

X = featurize("CC(=O)N[C@@H](Cc1ccccc1)C(=O)NCC(=O)O").reshape(1, -1)  # one peptide
predicted_pActivity = model.predict(X)[0]
# higher → more potent.  e.g. pKd 9 = 1 nM,  pKd 6 = 1 µM
```

For the MDM2 multitask model, append a 2-element one-hot `[1, 0]` for
`target_side='mdmx'` or `[0, 1]` for `'primary'`:

```python
target_side_onehot = np.array([0, 1], dtype=np.float32)   # 'primary' = MDM2
X = np.concatenate([X, target_side_onehot.reshape(1, -1)], axis=1)
predicted_pActivity = model.predict(X)[0]
```

The `feature_dim` field in the pickled payload tells you the expected width
(2054 for PD-L1, 2056 for MDM2 with multitask).

## How the runner consumes these models

`benchmark/scripts/workflow_runners/helmgpt_runner.py::check_reward_model`:

1. Reads `target.reward_model` path from `targets.csv`
   (e.g. `benchmark/reward_models/trained/hg_pd1pdl1.pkl`).
2. Resolves the companion metrics at `<pkl_dir>/<task_id_lower>_metrics.json`.
3. Reads `scaffold_split_spearman`, compares to
   `workflows.yaml::helmgpt.pass_gates.reward_model.spearman_min_pass = 0.4`.
4. If below the gate → emits `error_type=scientific` and aborts before RL.
5. Otherwise → marks `reward_model_gate` complete in `checkpoint.json` and
   advances to Phase 1.

## Improvement over the W2c baseline

| Target | W2c baseline (ChEMBL only) | Current (Tier 1+2+3 merged) | Δ val Spearman |
|--------|---------------------------|------------------------------|---------------:|
| PD-L1  | n=83, val Spearman 0.298 (below 0.4 gate floor, fragile) | n=186, val Spearman **0.770** | **+0.47** |
| MDM2   | n=223, val Spearman 0.490 (borderline) | **n=697**, val Spearman **0.714** | **+0.22** |

## Retraining

Re-merge sources first if any raw CSVs changed:

```bash
$HG_PY -m benchmark.data_curation.merge_sources --target pd1_pdl1
$HG_PY -m benchmark.data_curation.merge_sources --target mdm2_p53
```

Then retrain. The trainer prints to stdout the test/val metrics and writes
the .pkl + _metrics.json atomically.

After retraining, verify the runner still passes the gate:

```bash
python -m benchmark.scripts.run_benchmark --task HG_PD1PDL1 --llm claude --mode real
python -m benchmark.scripts.run_benchmark --task HG_MDM2P53  --llm claude --mode real
# expected: both runners proceed past the reward-model gate (no error_type=scientific),
# then bail at NotImplementedError because Phase 1 wiring to consume custom predictors
# is W3 production work (not in this curation pipeline).
```
