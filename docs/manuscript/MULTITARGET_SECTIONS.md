# Multi-target evaluation — new and revised manuscript text

Drafted against `CycPepMCP_v6.docx` (paragraph numbers in brackets refer to that
file) and `CycPepMCP-SI-v4.docx`. Figures referenced:

| Manuscript label | File |
|---|---|
| Figure 5 | `results/figures/figure5_benchmark-01.png` |
| Extended Data Fig. 5 | `results/figures/afcycdesign_benchmark_summary.pdf` |
| Extended Data Fig. 6 | `results/figures/rfpeptides_benchmark_figure.pdf` |
| Extended Data Fig. 7 | `results/figures/helmgpt_benchmark_figure.pdf` |

All values below were recomputed from the campaign records on 2026-11-09 and
agree with the rendered panels, with one exception: **the predicted K_d axis of
Extended Data Fig. 7a is mislabelled nM and should read µM** (Figure 5 itself
shows no K_d axis and is unaffected). The text below is written in the corrected
unit; the panel needs relabelling before submission.

---

## 1. Results — new section

Insert as a new Heading 2 after [158] (end of the HELM-GPT case study) and
before the Discussion [159].

### Multi-target evaluation across targets and workflows

The three case studies above each establish that a workflow runs end to end, but
a single target cannot distinguish a protocol that generalizes from one that
happened to suit its example. We therefore executed each workflow over a panel of
independent targets under fixed settings, scoring every design on independently
re-predicted structural metrics rather than on the quantities the optimizers
themselves minimize (Figure 5). In total, 2,000 RFpeptides designs (four targets
× 500), 4,000 AfCycDesign designs (four targets × two binder lengths × 500) and
approximately 32,700 HELM-GPT macrocycles (three targets, of which the top 20 per
target advanced to structural evaluation) were generated and scored, requiring no
user intervention beyond the initial natural-language instruction for each arm.

The dominant source of variance was the target, not the protocol. Within the
AfCycDesign campaign alone, run under identical settings, the fraction of designs
reaching the *Acceptable* tier (re-predicted pLDDT > 0.70 and iPAE < 0.30) ranged
from 81.0% for RbtA to 0% for PCSK9 (Figure 5A, Extended Data Fig. 5a,b). The
RFpeptides campaign spanned a similar range on its own panel, from 5.2% for MDM2
to 0% for PD-L1 (Figure 5B, Extended Data Fig. 6d,e). PCSK9 yielded no acceptable
design in 1,000 attempts, with a best-case iPAE of 0.329; we report this as a
negative result rather than a run failure, since the pipeline completed normally
and the same code produced the campaign's best arm on a different target. The
practical consequence is that a workflow's reported performance is inseparable
from the targets it was demonstrated on, which is the motivation for reporting a
panel rather than an exemplar.

Scoring on re-predicted rather than design-time values proved essential. Every
AfCycDesign arm was overstated by its own optimizer: design-time pLDDT exceeded
the independently re-predicted value by 0.07 to 0.36, and design-time iPAE
understated it by 0.13 to 0.39 (Supplementary Table 6.2). Once that optimism was
removed, no arm in the campaign reached the *Good* (pLDDT > 0.85, iPAE < 0.15) or
*Excellent* (pLDDT > 0.90, iPAE < 0.11) tier, although individual designs did —
the best Bcl-xL design reached pLDDT 0.95 at iPAE 0.20 (Extended Data Fig. 5d).
Because the optimizer selects on precisely the quantities that are inflated, a
ranking computed on design-time metrics is not a reliable guide to re-predicted
quality, and the two generations of metric should not be pooled.

Two further controls bound these values. A positive control against MDM2 reached
pLDDT 0.927, iPAE 0.101 and iPTM 0.878 under the same re-prediction protocol,
confirming that the pipeline resolves a confident peptide–target complex when one
exists; no production design in the campaign reached that tier. Conversely, two
of the four AfCycDesign targets were presented in cropped form — PCSK9 reduced
from 496 to 107 residues and RbtA from 441 to 166 — and re-predicting identical
peptides against both forms shows the effect to be large: median interface PAE
rises by 0.51–0.52 for RbtA and by 0.15–0.17 for PCSK9 when the intact protein is
restored (Extended Data Fig. 5c). The apparent advantage of these two arms in
Figure 5A is therefore substantially an artifact of target size. As run, the four
targets are of comparable extent (89–175 residues), so comparison between arms
remains internally consistent, but the absolute confidence values for PCSK9 and
RbtA should not be read as transferable to the intact proteins.

For RFpeptides, the deep-learning and physics-based filters behaved as close to
independent criteria. Recomputed interface energy correlated with contact
molecular surface as expected (within-target *r* = −0.25 to −0.77) but only
marginally with AlphaFold interface confidence (*r* = +0.05 to +0.09), so burying
substantial surface did not imply a confident predicted complex (Extended Data
Fig. 6a,c,d). PD-L1 illustrates the point directly: it produced more
physics-passing designs than any other target (130 of 500) while yielding none
that also satisfied the structural thresholds. Across the entire 2,000-design
panel only two designs satisfied both sets of criteria, one against MDM2 and one
against GABARAP, and both clear the interface-energy threshold by less than two
of their own replicate standard deviations, so both are marginal. Interface
energetics were computed in three independent replicates (6,000 evaluations) for
this reason; replicate spread is modest for aggregation propensity and contact
surface but non-negligible for interface energy (median SD 0.53–0.94 REU, with
individual designs exceeding 6 REU), and single-replicate values should not be
compared at finer resolution than a few REU.

Where no design clears a gate, the measured tail still constrains how much
sampling would be required to reach one. Extrapolating each arm's yield curve to
its acceptance threshold indicates that 10 jointly passing RFpeptides designs
would require of order 5,000 attempts for MDM2 and GABARAP but approximately
1.4 × 10^5 for PD-L1 (Extended Data Fig. 6g), and that 10 AfCycDesign designs
below iPAE 0.20 would require approximately 1,000 attempts for Bcl-xL and RbtA
against 2.3 × 10^5 for PCSK9 (Extended Data Fig. 5, sampling-yield panel). These
projections assume the measured log-linear tail continues to the gate and should
be read as order-of-magnitude guidance for allocating compute, not as predictions
for individual targets.

The HELM-GPT campaign occupies a different metric space and is not comparable on
structural confidence. Its three targets differed chiefly in predicted affinity:
median predicted K_d over the 20 advanced candidates was 4.59 µM for KRAS-G12D
and 4.35 µM for MDM2/p53, but 45.73 µM for PD-1/PD-L1 (Figure 5C, Extended Data
Fig. 7a). Applying the workflow's own 10 µM affinity threshold jointly with the
permeability threshold retains 1,991 macrocycles for KRAS-G12D and 1,354 for
MDM2/p53 but none at all for PD-1/PD-L1, whose best single candidate is predicted
at 22.12 µM. The PD-1/PD-L1 arm therefore advanced 20 candidates to structural
evaluation that do not satisfy the affinity gate, and the campaign is in effect
two targets rather than three. Notably, PD-1/PD-L1 nonetheless presented the
highest median structural confidence of the three arms (Boltz-2 ligand iPTM 0.85;
Figure 5C), and its reward model showed top-decile enrichment of only 0.33, so
its structural agreement should not be read as independent confirmation of
binding. MDM2/p53 was the only target on which all four orthogonal criteria
concurred, clearing both the interface-confidence and the Gnina CNN threshold for
all 20 candidates while also achieving the best docking score of the campaign
(−9.61 kcal mol⁻¹).

Two limitations bound the interpretation of this benchmark and are stated here
rather than in the Discussion because they constrain what Figure 5 can be used
for. First, the three workflows were not run on a shared target panel — only MDM2
appears in more than one arm, and in different roles — so Figure 5 compares
workflow–target arms and does not license a ranking of one protocol against
another. The three rows also report different quantities: the composite scores in
the right-hand column are three distinct formulas over three distinct metric
sets, and are commensurable only within a row. Second, the interface energetics
reported here supersede an earlier set of Stage-4 values produced by a silent
fallback to a synthetic metric generator after PyRosetta failed to load on the
compute nodes; because that stage returned a success code, the substitution was
not surfaced at run time. The affected values influenced only Stage-4 filtering
and the downstream composite ranking, all designs have since been recomputed, and
Stages 1–3 were unaffected. The episode is reported in full in Supplementary
Note 6 because it bears directly on how an agentic framework should treat
tool-level success codes, and it motivated three corrections to the
interface-metrics tool: the fallback now aborts rather than emitting synthetic
data, the contact-surface filter follows the declared peptide chain rather than
assuming the peptide is the first chain in the file, and the random seed is fixed
with replicate variance reported.

Taken together, the panel supports a narrower and more useful claim than the
single-target case studies alone: CycPepMCP executes each of the three protocols
reproducibly and without intervention across multiple targets, and the resulting
data are informative enough to show where each protocol fails. It does not
support a claim that any of the three protocols succeeds generally, and the
benchmark's main practical finding is that target difficulty, measured as the
sampling depth required to clear a workflow's own acceptance gates, varies by
more than two orders of magnitude across targets that are superficially similar.

---

## 2. Figure 5 caption

> **Figure 5 | Multi-target evaluation of the three CycPepMCP workflows.**
> Each row is one workflow run over its own target panel under fixed settings;
> rows are not comparable to one another, because the panels share no target and
> the composite scores in the right-hand column are three distinct formulas over
> three distinct metric sets (Methods). In every panel the violin shows the
> kernel density, the dark bar the interquartile range, the open circle and
> printed value the median, and each point one design.
> **A**, AfCycDesign, four targets at 500 designs per binder length pooled over
> lengths 14 and 16 (*n* = 1,000 per target; 4,000 total). Left, re-predicted
> interface PAE; middle, re-predicted pLDDT; right, composite score
> 0.50·pLDDT + 0.50·(1 − iPAE). All values are from an independent AF-multimer
> re-prediction, not from the optimizer's own objective. RbtA and PCSK9 were run
> against cropped targets and are not on the same footing as XIAP and Bcl-xL
> (Extended Data Fig. 5c).
> **B**, RFpeptides, four targets at 500 designs each (*n* = 2,000). Left,
> re-predicted interface PAE; middle, re-predicted pLDDT; right, the five-term
> Stage-5 composite score on recomputed interface energetics.
> **C**, HELM-GPT, three targets with the top 20 candidates per target advanced
> to structural evaluation (*n* = 60). Left, predicted membrane permeability;
> middle, Boltz-2 ligand iPTM; right, the Phase-3 composite score. These 20 per
> target were already selected on the Phase-1 reward, so each distribution is a
> truncated one.
> No acceptance line is drawn in any panel: the usable threshold is
> target-dependent, and a single shared gate would misrepresent the comparison.
> Per-target gate performance, attrition and the best design of each arm are
> given in Extended Data Figs. 5–7 and Supplementary Note 6.

---

## 3. Methods — revised subsection

Replace [191]–[192] ("Workflow benchmarking and visualization") with the
following two Heading 2 subsections.

### Workflow benchmarking and visualization

The three case studies were chosen to exercise distinct dimensions of the agentic
action space: AfCycDesign exercises single-MCP rapid optimization on a
well-defined pocket (MDM2); RFpeptides exercises multi-MCP heterogeneous
orchestration with deep-learning and physics-based filtering for canonical-AA
design (MCL1); and HELM-GPT exercises RL-driven multi-objective optimization with
ncAA chemistry and intracellular-target permeability (KRAS-G12D). Each skill
ships a standalone visualization pipeline that renders publication-quality,
colorblind-palette figures. All benchmark figures were generated with synthetic
smoke-test records excluded (`--skip-mock`).

### Multi-target benchmark

To characterize workflow behavior beyond the single-target case studies, each
protocol was executed over a panel of independent targets using the parameters
specified in the corresponding protocol sections above, with no per-target
tuning.

**Panels and sample sizes.** The RFpeptides protocol was run against MDM2, MCL1,
PD-L1 and GABARAP at 500 designs per target (2,000 total). The AfCycDesign
protocol was run against Bcl-xL, PCSK9, RbtA and XIAP at two binder lengths (14
and 16 residues) and 500 designs per arm (4,000 total). The HELM-GPT protocol was
run against KRAS-G12D, MDM2/p53 and PD-1/PD-L1, each sampling approximately
11,000 unique parseable macrocycles, from which the top 20 by Phase-1 composite
reward entered structural evaluation (60 total). Targets were selected to span
pocket geometries rather than to be shared across workflows; only MDM2 appears in
more than one panel, and in different roles (as a protein target for RFpeptides,
and as the MDM2/p53 interface for HELM-GPT). The benchmark consequently compares
workflow–target arms and does not license a direct ranking of protocols.

**Scoring basis.** Structural confidence is the common basis of comparison between
the two peptide-backbone workflows. For RFpeptides, designs were scored by
AfCycDesign re-prediction and counted as passing the structural criteria at
iPAE < 0.20 and pLDDT > 0.70. For AfCycDesign, designs were classified on Step-6
re-predicted values only; the design-time metrics are the optimizer's own
objective and are correspondingly optimistic, and the *Acceptable* tier
corresponds to pLDDT > 0.70 and iPAE < 0.30. Design-time and re-predicted metrics
are reported separately and were never pooled. For HELM-GPT, which operates in a
distinct metric space, no structural comparison to the other two workflows is
drawn; its arms are compared on predicted affinity, predicted permeability,
Boltz-2 ligand iPTM and Gnina CNN affinity.

**Interface energetics.** Rosetta interface metrics for all 2,000 RFpeptides
designs were recomputed in three independent replicates with a fixed seed (6,000
evaluations) using PyRosetta 2026.3 with the `beta_nov16` score function
(`beta_nov16_cart` for minimization), the protocol in
`configs/rosetta_interface_metrics.xml`, and `PeptideCyclizeMover` applied before
and after interface minimization. Values are reported as the replicate mean with
standard deviation. The ddG filter used `jump=1`, `repeats=5`, `repack=1`,
`relax_mover=min` and `extreme_value_removal=1`. Interface energies are reported
in Rosetta Energy Units (REU) and are not calibrated free energies.

**Sampling-yield projection.** For arms in which few or no designs clear the
acceptance gate, the required sampling depth was estimated by sweeping the
interface PAE cut-off from 0.70 to the gate while holding the remaining criteria
fixed, fitting a log-linear model to the measured tail, and extrapolating to the
gate. Measured and extrapolated regions are drawn as solid and dashed lines
respectively. These projections assume the measured tail continues to the gate
and are intended as order-of-magnitude guidance for compute allocation.

**Chain and target conventions.** RFpeptides Stage-2 complexes assign the peptide
to chain A and the target to chain B; AfCycDesign re-predictions reverse this.
Two RFpeptides arms (MCL1 and PD-L1) were scored by Rosetta and by AlphaFold
against targets of different extent (119 against 145 residues, and 59 against 117
residues, respectively), so their energetic and confidence metrics do not describe
the same complex; these arms are marked wherever a joint criterion is applied. Two
AfCycDesign targets were cropped for the campaign (PCSK9, 496 → 107 residues;
RbtA, 441 → 166), and every design in those arms was additionally re-predicted
against the intact protein to quantify the effect.

Also revise, in the existing Methods text:

- **[182]**, RFpeptides Stage-3 criteria: delete the `Cα-RMSD < 1.5 Å` clause (no
  per-candidate RMSD was ever computed; the only RMSD produced is pairwise
  between designs for Stage-5 clustering) and write the confidence threshold on
  the 0–1 scale used everywhere else: "deep-learning validation via AfCycDesign
  (iPAE < 0.30, pLDDT > 0.70)".
- **[185]**: "predicted ddG −40.8 kcal mol⁻¹" → "a Rosetta InterfaceAnalyzer
  interface energy of −40.8 REU". Never express REU as kcal mol⁻¹ without a
  calibration against measured affinities.
- **[180]**: "pLDDT > 70" → "pLDDT > 0.70", for consistency with [178] and all
  plotted axes.

---

## 4. Supplementary Information — new note

Append to `CycPepMCP-SI-v4.docx`, which currently ends at Note 5.

### Supplementary Note 6 | Multi-target benchmark

#### 6.1 Campaign definition

Each workflow was executed over an independent target panel with no per-target
tuning. Settings are those of the corresponding Methods protocol sections.
Per-design records, per-replicate interface energetics and the top-design
structure exports are distributed with the code.

**Supplementary Table 6.1 | Multi-target benchmark of the RFpeptides and
AfCycDesign workflows.** Medians over 500 designs per arm, best single design in
parentheses. Passing denotes the structural criteria only (RFpeptides,
iPAE < 0.20 and pLDDT > 0.70; AfCycDesign *Acceptable*, iPAE < 0.30 and
pLDDT > 0.70).

| Workflow | Target (length) | pLDDT median (max) | iPAE median (min) | Passing designs |
|---|---|---|---|---|
| RFpeptides | MDM2 | 0.550 (0.918) | 0.353 (0.099) | 26/500 (5.2%) |
| | MCL1 | 0.469 (0.845) | 0.463 (0.169) | 1/500 (0.2%) |
| | PD-L1 | 0.383 (0.649) | 0.578 (0.336) | 0/500 (0%) |
| | GABARAP | 0.403 (0.872) | 0.536 (0.164) | 1/500 (0.2%) |
| AfCycDesign | RbtA (14) | 0.848 (0.911) | 0.261 (0.204) | 405/500 (81.0%) |
| | RbtA (16) | 0.834 (0.923) | 0.270 (0.195) | 375/500 (75.0%) |
| | Bcl-xL (14) | 0.514 (0.951) | 0.503 (0.200) | 60/500 (12.0%) |
| | Bcl-xL (16) | 0.476 (0.874) | 0.535 (0.266) | 6/500 (1.2%) |
| | XIAP (14) | 0.517 (0.880) | 0.473 (0.223) | 21/500 (4.2%) |
| | XIAP (16) | 0.511 (0.862) | 0.490 (0.228) | 6/500 (1.2%) |
| | PCSK9 (14) | 0.588 (0.713) | 0.474 (0.383) | 0/500 (0%) |
| | PCSK9 (16) | 0.634 (0.749) | 0.432 (0.329) | 0/500 (0%) |

No AfCycDesign arm reached the *Good* (pLDDT > 0.85, iPAE < 0.15) or *Excellent*
(pLDDT > 0.90, iPAE < 0.11) tier on re-predicted values. The 14-residue binder
outperformed the 16-residue binder on every AfCycDesign target that produced any
acceptable design, by factors of 3.5 to 10; with three such targets this is
suggestive rather than established, and length was not varied in the other two
workflows.

#### 6.2 Design-time optimism in AfCycDesign

Every AfCycDesign arm carries both the optimizer's own metrics and an independent
AF-multimer re-prediction of the same designs, which permits the optimism to be
quantified directly.

**Supplementary Table 6.2 | AfCycDesign design-time versus re-predicted
confidence.** Medians over 500 designs per arm. Runtime is median wall-clock per
design on one GPU, over the subset of records carrying timing (*n* = 258).

| Arm | Design pLDDT | Re-predicted pLDDT | Design iPAE | Re-predicted iPAE | Runtime (min) |
|---|---|---|---|---|---|
| Bcl-xL (14) | 0.783 | 0.514 | 0.176 | 0.503 | 7.0 |
| Bcl-xL (16) | 0.840 | 0.476 | 0.147 | 0.535 | 7.0 |
| PCSK9 (14) | 0.880 | 0.588 | 0.173 | 0.474 | 3.9 |
| PCSK9 (16) | 0.920 | 0.634 | 0.152 | 0.432 | 4.0 |
| RbtA (14) | 0.907 | 0.848 | 0.129 | 0.261 | 6.1 |
| RbtA (16) | 0.916 | 0.834 | 0.119 | 0.270 | 6.7 |
| XIAP (14) | 0.807 | 0.517 | 0.156 | 0.473 | 3.5 |
| XIAP (16) | 0.785 | 0.511 | 0.163 | 0.490 | 3.6 |

Re-predicted pLDDT and interface PAE are near-collinear within every target
(*r* = −0.92 to −0.99), so they constitute approximately one axis of information
rather than two independent criteria, and the two-term composite in Figure 5A
should be read accordingly.

#### 6.3 Target cropping control

Bcl-xL (175 residues) and XIAP (89 residues) were used intact. PCSK9 was cropped
from 496 to 107 residues and RbtA from 441 to 166. Re-predicting identical
peptides against both forms gives, for RbtA, pLDDT 0.558 → 0.379 and iPAE
0.477 → 0.744; and for PCSK9, pLDDT 0.585 → 0.319 and iPAE 0.469 → 0.762. Median
interface PAE over each full arm rises by 0.51–0.52 (RbtA) and 0.15–0.17 (PCSK9).
A hotspot ablation was also performed on PCSK9 and XIAP but with only two designs
per condition; it is reported as exploratory and no conclusion is drawn from it.

#### 6.4 RFpeptides interface energetics

**Supplementary Table 6.3 | Rosetta interface metrics for the RFpeptides panel.**
Medians over 500 designs per target. Physics criteria are ddG < −30 REU,
SAP < 35 and CMS > 300 Å².

| Target | ddG median (best) | Median ddG SD | SAP median | CMS median | Passing physics | Passing physics and structure |
|---|---|---|---|---|---|---|
| MDM2 | −21.53 (−41.67) | 0.81 | 22.03 | 268.55 | 16/500 | 1/500 |
| MCL1 | −22.61 (−47.06) | 0.53 | 22.20 | 281.21 | 83/500 | 0/500 |
| PD-L1 | −25.55 (−124.08) | 0.54 | 26.56 | 311.82 | 130/500 | 0/500 |
| GABARAP | −12.72 (−35.86) | 0.94 | 16.26 | 194.09 | 2/500 | 1/500 |

The PD-L1 best value of −124.08 REU is reproducible across seeds but implausible
for a 12-residue macrocycle and is accompanied by an unremarkable contact
surface; it is treated as a minimization artifact and excluded from
interpretation. Within-target correlations are *r* = −0.25 to −0.77 between ddG
and contact molecular surface, and *r* = +0.05 to +0.09 between ddG and interface
PAE, so the physics and structural gates are close to orthogonal.

#### 6.5 HELM-GPT three-target campaign

**Supplementary Table 6.4 | HELM-GPT three-target campaign.** Phase-1 counts are
over all unique parseable macrocycles; all other values are over the 20
candidates per target that entered structural evaluation. Predicted K_d is
reported in µM, the unit of the HELM-GPT affinity predictor's training target.

| | KRAS-G12D | MDM2/p53 | PD-1/PD-L1 |
|---|---|---|---|
| Unique valid HELM | 11,049 | 10,941 | 10,684 |
| Pass, permeability > −6 | 6,698 | 9,432 | 9,980 |
| Pass, K_d < 10 µM | 3,325 | 1,471 | 0 |
| Pass, both gates jointly | 1,991 | 1,354 | 0 |
| K_d, best / median (µM) | 2.53 / 4.59 | 2.88 / 4.35 | 22.12 / 45.73 |
| Permeability, median (log cm s⁻¹) | −5.55 | −4.65 | −4.67 |
| Heavy atoms, range | 57–98 | 81–90 | 77–90 |
| Boltz-2 affinity, median | −0.203 | −0.534 | −0.574 |
| Boltz-2 binary probability, median | 0.41 | 0.54 | 0.61 |
| Boltz-2 ligand iPTM, median | 0.78 | 0.84 | 0.85 |
| AlphaFold3 iPTM, median (number ≥ 0.60) | 0.58 (9/20) | 0.70 (20/20) | 0.80 (20/20) |
| Gnina CNN, median pK_d (number > 6.0) | 7.41 (19/20) | 7.63 (20/20) | 7.46 (20/20) |
| Gnina Vina, median / best (kcal mol⁻¹) | −5.97 / −8.55 | −6.36 / −9.61 | −5.52 / −6.71 |
| Best composite | 0.726 | 0.635 | 0.689 |

Five caveats qualify this table.

1. **The affinity gate is load-bearing and was applied too loosely in the run.**
   The affinity predictor emits log₁₀(K_d/µM). Under the workflow's stated 10 µM
   threshold, PD-1/PD-L1 retains no candidates at all, and its best single
   candidate is predicted at 22.12 µM; the 20 PD-1/PD-L1 candidates that entered
   structural evaluation therefore do not satisfy the affinity gate, and the
   campaign is effectively two targets rather than three. The attrition panel of
   Extended Data Fig. 7 shows the affinity gate removing almost nothing, which
   reflects the threshold as applied in the run rather than the molecules.
2. **Boltz-2 is extrapolating.** Its affinity head was trained on ligands of up to
   56 heavy atoms, whereas every candidate here exceeds that, so its values are
   directional rather than calibrated.
3. **AlphaFold3 fell back.** It could not construct an RDKit reference conformer
   for these macrocycles, so its iPTM is a useful orthogonal check but not a clean
   ligand prediction. Phase-3 routing prefers the Boltz-2 ligand iPTM where both
   exist; the two are effectively uncorrelated within target (*r* = −0.23 to
   +0.45) with Boltz-2 higher on 50 of 60 complexes (median offset +0.12), so the
   composite reads the more optimistic of the two throughout. Both are reported
   per candidate.
4. **Permeability is not an independent assessment.** It is a prediction from the
   same scorer that shaped the reinforcement-learning reward, so it measures
   consistency with the objective.
5. **PD-1/PD-L1 structural confidence is not confirmation.** It presented the
   highest median ligand iPTM of the three arms despite the weakest affinity
   distribution, and its reward model showed top-decile enrichment of only 0.33.

#### 6.6 Synthetic Stage-4 metric episode

The interface energetics in §6.4 supersede an earlier set of Stage-4 values. On
the compute nodes used for the campaign, PyRosetta failed to load and the
interface-metrics tool fell back silently to a synthetic metric generator,
returning a success code. The substitution was therefore not surfaced at run
time, and the synthetic values are identifiable in retrospect: they are uniform
on [−60, −10] REU and uncorrelated with the recomputed energies (*r* = −0.008;
Extended Data Fig. 6). The correction is not a constant offset and changes the
ordering of the panel — the number of GABARAP designs passing the physics
criteria falls from 111 to 2 while PD-L1 rises from 94 to 130 — so the original
counts also ranked the four targets incorrectly. Of the three MDM2 Stage-5
cluster representatives selected on the synthetic values, all three fall in the
lower half of their own arm by recomputed interface energy, and the design that
is in fact best by recomputed energy was never selected.

The affected values influenced only Stage-4 filtering and the downstream
composite ranking; Stages 1–3 were unaffected and were carried through unchanged,
and all 2,000 designs have since been recomputed. Three corrections were made to
the tool: the fallback now aborts rather than emitting synthetic data; the
contact-surface filter follows the declared peptide chain rather than assuming
the peptide is the first chain in the file; and the random seed is fixed with
replicate variance reported. We report the episode in full because it bears on a
general property of agentic frameworks: an agent that routes on tool exit codes
will propagate a silent fallback without surfacing it, so scientific tools
invoked by agents should fail loudly rather than degrade.

#### 6.7 Provenance

RFdiffusion was run with `seed=None` in the RFpeptides campaign, so backbone
generation is not seed-reproducible and per-candidate seeds cannot be recovered
retroactively; an explicit seed is set in the current code. Structure exports for
the best design of each arm, with their targets and a per-file inventory, are
distributed with the code; chain assignments differ between the Rosetta and
re-predicted complexes as described in Methods.

---

## 5. Extended Data figure captions

> **Extended Data Fig. 5 | AfCycDesign multi-target campaign.**
> Four targets × two binder lengths × 500 designs (*n* = 4,000). **a**, **b**,
> Re-predicted pLDDT and interface PAE for all 1,000 designs per target, shown as
> violin, interquartile bar and per-design jitter, with the open circle and
> printed value giving the median. No acceptance line is drawn: the usable
> threshold is target-dependent, and a single shared gate would misrepresent the
> comparison. Asterisks mark the two arms run against cropped targets, which are
> not on the same footing as the other two. **c**, Median interface PAE for the
> same designs re-predicted against the cropped target used during the campaign
> and against the intact protein. Cropping lowers median interface PAE by
> 0.15–0.17 for PCSK9 (107 of 496 residues retained) and by 0.51–0.52 for RbtA
> (166 of 441), so the apparent advantage of these arms in **a** and **b** is
> substantially an artifact of target size. **d**, Best design per arm by the
> composite score 0.50·pLDDT + 0.50·(1 − iPAE) on re-predicted values.
> Design-time versus re-predicted confidence, the iPTM and composite
> distributions, and the sampling-yield projection are provided as separate
> panels with the source data.

> **Extended Data Fig. 6 | RFpeptides multi-target evaluation.**
> Four targets × 500 designs (*n* = 2,000). **a**–**f**, Distributions of
> recomputed interface energy (ddG), recomputed aggregation propensity (SAP),
> recomputed contact molecular surface (CMS), re-predicted interface PAE,
> re-predicted pLDDT and the five-term Stage-5 composite score, shown as violin,
> interquartile bar and per-design jitter, with the open circle and printed value
> giving the median. Interface energy is reported in Rosetta Energy Units and is
> not a calibrated free energy. Designs falling outside the plotted range are not
> drawn; 19 designs lie outside the ddG axis and one outside the CMS axis,
> the former including PD-L1's extreme value of
> −124.08 REU, which is reproducible across seeds but implausible for a
> 12-residue macrocycle and is treated as a minimization artifact. Medians and
> interquartile ranges are computed over the whole arm, including designs outside
> the plotted range. **g**, Designs clearing both the physics and the structural
> criteria as the interface PAE cut-off is swept toward the gate at 0.20, with
> the remaining criteria held fixed; solid lines are measured, dashed lines are
> log-linear extrapolations, and the legend gives the sampling depth each arm's
> tail implies for 10 jointly passing designs. Asterisks mark the two arms whose
> Rosetta and AlphaFold stages did not see the same target, so that their joint
> curve combines metrics from two different complexes. **h**, Highest-composite
> design of each target on the recomputed metrics, with the criteria it clears.
> Across the whole panel only two designs clear both sets of criteria, one
> against MDM2 and one against GABARAP.

> **Extended Data Fig. 7 | HELM-GPT three-target permeability campaign.**
> Approximately 11,000 unique parseable macrocycles per target, of which the top
> 20 per target advanced to structural evaluation (*n* = 60). **a**–**d**,
> Distributions of predicted K_d, predicted permeability, Boltz-2 ligand iPTM and
> Gnina CNN affinity over the 20 candidates of each arm, shown as violin,
> interquartile bar and per-candidate jitter, with the open circle and printed
> value giving the median. These 20 were already selected on the Phase-1
> composite, so each spread is a truncated one. **e**, Attrition from generation
> to structural evaluation. The permeability term is the only Phase-1 filter that
> binds as applied: the affinity-gate row sits flush with the parsed row because
> the threshold was applied 10³-fold too loosely in the run; under the workflow's
> stated 10 µM gate the counts are 3,325, 1,471 and 0 (Supplementary Table 6.4).
> **f**, Highest-composite candidate of each target, with the number of the four
> quality gates it clears. AlphaFold3 iPTM is reported per candidate; Phase-3
> routing prefers the Boltz-2 ligand iPTM wherever both exist, and the two are
> effectively uncorrelated within target.
