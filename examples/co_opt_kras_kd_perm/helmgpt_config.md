# KRAS-G12D ncAA Macrocycle Design — HELM-GPT Configuration

> HELM-GPT pipeline (RL with target-specific reward model + permeability co-optimization, then structural eval) for designing ncAA macrocyclic peptides that bind KRAS-G12D.
>
> **Workflow:** Follow `workflow-skills/binder_design_helmgpt.md`. This is the canonical HELM-GPT positive-control case (case3) — reward model is already pre-trained.

## Target Information

| Property | Value |
|----------|-------|
| Protein | KRAS-G12D (oncogenic mutant; pancreatic / colorectal / lung cancers) |
| Source | Human (UniProt P01116) — full sequence in `target.fasta` (165 aa) |
| Mutation | G12D (driver mutation; standard intracellular target) |
| Predicted complex | Boltz-2 / AlphaFold3 against the binder + KRAS-G12D sequence |

This case reproduces the HELM-GPT paper's KRAS-G12D experiment (Bioinformatics 2024, btae364) and serves as the **positive-control / reproducibility benchmark** in the CycPepMCP panel — the reward model is validated (Spearman ≈ 0.82 on scaffold-split test).

---

## Pre-built artifacts (already in this directory)

| Path | Purpose |
|------|---------|
| `target.fasta` | KRAS-G12D sequence |
| `KRAS-G12D.a3m` | Pre-computed multiple-sequence alignment (~2.1 MB) |
| `monomer_library.csv` | Allowed ncAA monomers (HELM extended set) |
| `monomer_library_helm_vocab.csv` | HELM vocab mapping for the monomer set |
| `perm_prior/` | Pre-trained HELM-GPT permeability prior (gpt_model_final_*.pt + .json) |
| `rl_predictors/` | Pre-trained KRAS-G12D affinity predictor (XGBoost MorganFP) |
| `setup_case3.py` | One-shot environment + data setup script |
| `run_target_msa.sh` | MSA computation script (already executed; output is `KRAS-G12D.a3m`) |
| `run_phase2_track_a.sh` | Phase 2 Track A (Boltz-2 + AF3 + Gnina; ≤128 atoms) |
| `run_phase2_track_b.sh` | Phase 2 Track B (AF3 + Gnina only; >128 atoms) |
| `run_phase2_gnina.sh` | Gnina docking inner runner |
| `postprocess_phase1.py` | Aggregate + filter Phase 1 RL outputs |
| `postprocess_phase2_prep.py` | Phase 2 input prep |
| `postprocess_phase3.py` | Composite-score ranking → `phase3_final_ranking.csv` |

Unlike the other HELM-GPT cases (`case_pd1pdl1_helmgpt/`, `case_mdm2p53_helmgpt/`), the W2c data-curation pipeline does **not** need to run for this case — the predictors are already trained.

---

## KRAS-G12D-Specific Parameters

### Phase 1: RL Co-optimization

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `task` | `kras_perm` | Co-optimize KRAS-G12D KD + permeability |
| `reward_model_path` | `examples/co_opt_kras_kd_perm/rl_predictors/` | Pretrained XGBoost on 2,757 patent records |
| `permeability_model` | `examples/co_opt_kras_kd_perm/perm_prior/gpt_model_final_0.105.pt` | Permeability prior (HELM-GPT default) |
| `n_steps` | 500 | Standard from HELM-GPT paper |
| `batch_size` | 32 | Standard |
| `loss_type` | `reinvent_cpl` | Default in benchmark plan §2.3 |

### Phase 2: Structural Evaluation

Routed by heavy-atom count (`workflows.yaml` `helmgpt.structural_routing.heavy_atom_threshold = 128`):
- **≤ 128 atoms** (Track A): Boltz-2 SMILES affinity (3-head ensemble) + AlphaFold3 + Gnina docking
- **\> 128 atoms** (Track B): AlphaFold3 + Gnina only (Boltz-2 ligand limit)

The provided `run_phase2_*.sh` scripts wrap the per-track invocations.

### Phase 3: Composite Scoring

Centralized in `workflows.yaml` `helmgpt.composite_weights`:

`0.20·KD + 0.15·perm + 0.15·boltz_aff + 0.10·boltz_prob + 0.10·boltz_iptm + 0.15·gnina_cnn + 0.15·gnina_vina`

Output: `phase3_final_ranking.csv` (per-candidate composite + sub-ranks; consumed by `helmgpt_viz.py`).

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

## Reference run

Pre-existing outputs at `results/case3_kras_helmgpt/phase1_20260428_150906/phase3_final_ranking.csv`
(20 candidates after composite ranking). Re-seedable via:

```bash
python -m benchmark.scripts.seed_pilot_from_case --task HG_KRASG12D
python -m benchmark.scripts.run_benchmark --task HG_KRASG12D --llm claude --mode real --resume
```

Reference Run 0 produced 7/20 PASS, top composite 0.6639.

---

## Notes

- **Positive-control role**: KRAS-G12D is the calibration case for HELM-GPT in the CycPepMCP benchmark — the validated reward model (Spearman 0.82) lets us isolate workflow performance from data-curation effects when comparing against the new HG_PD1PDL1 / HG_MDM2P53 cases.
- **Cross-target peer**: same HELM-GPT pipeline, different reward model, on PD-1/PD-L1 (`case_pd1pdl1_helmgpt/`) and MDM2/p53 (`case_mdm2p53_helmgpt/`) targets.
