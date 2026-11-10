# HELM-GPT campaign execution audit — 2026-11-10

This audit inspects the actual `20261102_192136` campaign under
`/home/xux/Desktop/AgentMCP/CycPepMCP/results/helmgpt_3target/`, together with the
external source checkout that launched it. It verifies saved scores, reward
arithmetic and selection, without rerunning RL or structural inference.

## 1. Reward-model units: nM

The campaign used the upstream KRAS predictor and target-specific
`hg_mdm2p53_kras_recipe.pkl` / `hg_pd1pdl1_kras_recipe.pkl` models. The actual
training script `benchmark/reward_models/train_xgboost_kras_recipe.py` converts
curated activity using `log10(Kd/nM) = 9 - p_activity`; its model metadata also
records this unit. `agent/scoring/target_kd.py` inherits the KRAS scoring path
and explicitly records the same scale. The upstream KRAS notebook labels its
experimental and predicted values in log Kd (nM).

Thus, if the raw reward-model output is x:

- Kd in nM = 10^x.
- Kd in µM = 10^(x − 3).
- x < 1 means Kd < 10 nM.
- x < 4 means Kd < 10,000 nM = 10 µM.

The earlier refined manuscript incorrectly assigned µM to 10^x. That conclusion
is superseded by this audit. The current workspace's generic training script and
postprocessor do not establish the units of the different models actually used
by this external production campaign.

## 2. RL actually executed

`examples/run_helmgpt_3target.sh` launched 500 steps, batch size 24 and
`loss_type=reinvent`, using the shared permeability prior. Task definitions in
`train_agent.py` select permeability and the appropriate target-affinity scorer,
with equal weights and sum aggregation. Boltz was not part of this RL reward.

For x = raw log10(Kd/nM) and p = raw log permeability (cm/s), the implemented
reward is:

    R_affinity = 1 / (1 + 10^((x − 1)/2))
    R_permeability = 1 / (1 + 10^(−(p + 6)/4))
    R_total = R_affinity + R_permeability

The affinity reward has midpoint 10 nM; permeability has midpoint −6. These
continuous transformations do not impose hard pass/fail cutoffs. Recomputing the
reward from all 32,674 unique valid records reproduces stored sums with maximum
absolute error below 1.7 × 10^−7 across the three panels. The model-trainer code
uses a prior-regularized REINVENT objective; the launch disables CPL.

## 3. Post-RL selection actually applied

Saved `phase1_summary.json` records a 10,000 nM affinity cutoff and permeability
> −6. Recomputed counts from `phase1_aggregated.csv` agree with the saved applied
selection counts. `phase2_candidates.csv` contains the 20 advanced candidates per
target. All 60 satisfy both applied gates.

| Quantity | KRAS-G12D | MDM2/p53 | PD-1/PD-L1 |
|---|---:|---:|---:|
| Unique valid records | 11,049 | 10,941 | 10,684 |
| Permeability > −6 | 6,698 | 9,432 | 9,980 |
| Kd < 10 µM (applied gate) | 11,049 | 10,856 | 10,684 |
| Both applied gates | 6,698 | 9,381 | 9,980 |
| Kd < 10 nM (stricter analysis) | 3,325 | 1,471 | 0 |
| Permeability and Kd < 10 nM | 1,991 | 1,354 | 0 |
| Advanced candidates meeting both applied gates | 20/20 | 20/20 | 20/20 |
| Best selected Kd (nM) | 2.53 | 2.88 | 22.12 |
| Median selected Kd (nM) | 4.59 | 4.35 | 45.73 |

PD-1/PD-L1 therefore fails the stricter 10 nM criterion, not the executed 10 µM
criterion. Its best selected prediction is 0.02212 µM, and its median is
0.04573 µM. Calling these 22.12 and 45.73 µM creates a 1,000-fold error.
The softer applied gate and stronger RL reward midpoint should be documented
separately; neither should be silently substituted for the other.

## 4. Boltz prediction provenance and assessment thresholds

The campaign's `run_phase2_track_a.sh` provides each macrocycle as a SMILES ligand
(chain B), a protein target (chain A) and target-specific precomputed MSA, with
an affinity property for binder B. It invokes Boltz prediction and collects native
JSON scores. For all 60 candidates, saved `aff_affinity_pred_value` and
`conf_iptm` match raw affinity and confidence JSONs exactly. The latter is read
from the native `iptm` field. This checks score provenance, not the physical
validity or calibration of the predicted complexes.

Boltz affinity is a separate predictor from the RL affinity model. Official
[Boltz prediction documentation](https://github.com/jwohlwend/boltz/blob/main/docs/prediction.md)
defines `affinity_pred_value` as log10(IC50/µM), with **lower** values indicating
stronger predicted binding. Its binary binding probability and iPTM are
higher-is-better. An affinity value of −0.574 is therefore approximately
0.267 µM on Boltz's predicted IC50 scale, not the RL model's Kd.

The production Phase-3 script ranks all advanced candidates without applying
hard Boltz acceptance cutoffs. The central configuration lists iPTM ≥ 0.70 and
binary probability ≥ 0.50 as assessment gates, but these do not filter the
campaign's Phase-3 table. Its affinity minimum of 0.0 has the wrong direction
for the native affinity scale. A desired native affinity cutoff needs to be
specified as a maximum; no corrected hard affinity cutoff was imposed here.

| Retrospective assessment of 20 candidates | KRAS-G12D | MDM2/p53 | PD-1/PD-L1 |
|---|---:|---:|---:|
| Boltz iPTM ≥ 0.70 | 15 | 19 | 19 |
| Boltz binding probability ≥ 0.50 | 6 | 12 | 20 |
| Boltz native affinity ≤ 0 (IC50 ≤ 1 µM; illustrative only) | 14 | 20 | 20 |
| Median Boltz native affinity | −0.203 | −0.534 | −0.574 |
| Median Boltz binding probability | 0.410 | 0.542 | 0.615 |
| Median Boltz iPTM | 0.776 | 0.840 | 0.852 |

The figure's four-gate assessment instead uses affinity < 10, permeability > −6,
iPTM > 0.60 and Gnina CNN > 6.0; it is an analysis convention, not proof that
these gates were enforced during execution. Its current affinity unit and funnel
are inconsistent with the executed reward predictors. AF3 iPTM ≥ 0.60 and
Boltz iPTM ≥ 0.70 are also distinct configured assessment thresholds.

All candidates have 57–98 heavy atoms. Boltz documentation discourages affinity
prediction for ligands significantly beyond its 56-atom training size limit
(counted using its documented RDKit convention). Macrocycle affinity values
therefore require particular caution. Both structural tracks were run; Phase 3
uses the Boltz track when available, rather than maximizing iPTM across tracks.

## 5. Confirmed Phase-3 scoring-direction error

The production `postprocess_phase3.py` min–max normalizes the native Boltz
`aff_affinity_pred_value` as higher-is-better, with weight 0.15. The native value
has not been negated or converted to a higher-is-better quantity. This reverses
the intended affinity preference. The same direction error is present in the
workspace copy of that postprocessor.

Reversing this term alone while retaining every other saved normalized term gives
`corrected_composite = original_composite + 0.15*(1 − 2*n_aff)`.
This sensitivity calculation changes the best candidate in every panel:

| Target | Original best Phase-1 candidate rank | Best after affinity-direction correction alone |
|---|---:|---:|
| KRAS-G12D | 4 | 1 |
| MDM2/p53 | 6 | 17 |
| PD-1/PD-L1 | 16 | 5 |

This is a downstream ranking error, not evidence of a failed Boltz inference or
an incorrect RL objective. No production records were overwritten and no pipeline
code was changed during this audit. Before submission, correct the direction and
regenerate composite rankings, representative-structure exports and corresponding
panels. Restore nM labels for the RL predictor and use the actual 10,000 nM gate
in executed-selection funnels; label any 10 nM analysis separately.

## Evidence locations

Paths below are relative to `/home/xux/Desktop/AgentMCP/CycPepMCP/`:

- `benchmark/reward_models/train_xgboost_kras_recipe.py`: target conversion and model recipe.
- `benchmark/reward_models/trained/hg_*_kras_recipe_metrics.json`: deployed model unit metadata.
- `tool-mcps/helm_gpt_mcp/repo/helm-gpt/agent/scoring/{kras,target_kd,permeability,transformation}.py`: prediction scale and reward transformations.
- `tool-mcps/helm_gpt_mcp/repo/helm-gpt/train_agent.py`: task scoring definitions.
- `examples/run_helmgpt_3target.sh`: RL launch settings.
- `examples/co_opt_kras_kd_perm/postprocess_phase{1,2_prep,3}.py`: filtering, routing and ranking.
- `examples/co_opt_kras_kd_perm/run_phase2_track_a.sh`: Boltz inputs and output-field extraction.
- `results/helmgpt_3target/<target>_perm/phase1_20261102_192136/`: saved train logs, Phase-1 records, Phase-2 candidates, raw Boltz JSONs and Phase-3 tables.
