# CycPepMCP Benchmark & Agent Evaluation Plan

## Context

**Why this exists.** The current CycPepMCP manuscript shows three end-to-end case studies. To target Nature Communications / Advanced Science / Genome Biology tier journals, the evidence must move from "representative case studies" to "systematic benchmark + quantitative agentic execution evaluation." This plan operationalizes that upgrade.

**Source documents.** This plan synthesizes two prior strategy documents in `docs/`:
- `CycPepMCP_Benchmark_and_Agent_Evaluation_Plan.docx` (Manus AI v1.0, 2026-05-05) — overall benchmark + agent-eval design.
- `HELM-GPT Target-Specific Benchmark Plan for CycPepMCP.md` (Manus AI) — HELM-GPT-specific constraint that each target requires curated peptide activity data and a target-specific reward model with Spearman ≥0.4.

**Locked scope (per user, 2026-05-05):**
- **Asymmetric 13-task panel**: 5 AfCycDesign + 5 RFpeptides + 3 HELM-GPT. The HELM-GPT panel is reduced from 5 to 3 because each new target requires ~300–1500 curated activity records and reward-model validation; pretending we can drop in 5 new HELM-GPT targets in 6 weeks is dishonest.
- **LLM panel**: Claude + GPT + Gemini, 3 models × 9 tasks (3 per workflow).
- **Repeatability**: n=2 reruns on 1 task per workflow (3 reruns total) on Claude.
- **Plan emphasis**: both infra-build and experiment-execution.
- **Language**: English (manuscript-aligned).

**Intended outcome.** Two new Results sections in the manuscript: (i) "Benchmarking CycPepMCP across diverse cyclic peptide design tasks" and (ii) "Quantitative evaluation of agentic orchestration." A reproducibility package (configs + agent traces + candidate metrics + figure scripts) released alongside.

---

## 1. Run Inventory

| Run class | Count | LLM | Reruns | Notes |
|-----------|------:|-----|-------:|-------|
| Primary 13-task pass on Claude | 13 | Claude | 1 | All targets, all 3 workflows |
| GPT panel | 9 | GPT-4-class | 1 | 3 targets × 3 workflows |
| Gemini panel | 9 | Gemini-Pro-class | 1 | Same 3×3 grid |
| Repeatability reruns | 3 | Claude | 2nd & 3rd seeds | 1 task per workflow |
| **Total runs** | **34** | — | — | — |

LLM-panel target subset (the 9-grid): MDM2 (AfCycDesign), MCL1 (RFpeptides), KRAS-G12D (HELM-GPT), one shared and two distinct per workflow — final picks in §2.

---

## 2. Benchmark Target Panels

### 2.1 AfCycDesign (5 targets — pocket/groove binders, fast)

| Target | PDB | Hotspot residues | binder_len | Optimizer | Rationale |
|--------|-----|------------------|-----------:|-----------|-----------|
| MDM2 | 4HFZ | 54,56,58,61,67,96,99,100 | 12 | pssm_semigreedy | Reuse `examples/binder_mdm2/` as canonical |
| MCL1 | 5W89 (BH3 groove) | 220,234,253,256,260,267 | 12 | pssm_semigreedy | Classical PPI; cross-comparable with RFpeptides MCL1 |
| BCL-xL | 1G5J | BH3 groove residues | 12 | pssm_semigreedy | Apoptosis family; well-characterized groove |
| XIAP-BIR3 | 1G73 | Smac/DIABLO interface | 10 | pssm_semigreedy | Smaller binder length probes parameter robustness |
| PCSK9 | 2P4E | LDLR interface | 12 | pssm_semigreedy | Extracellular target; broadens panel |

### 2.2 RFpeptides (5 targets — de novo cyclic binders)

| Target | PDB | Hotspots | binder_length | num_designs | iPAE PASS gate | Rationale |
|--------|-----|----------|--------------:|------------:|---------------:|-----------|
| MCL1 | 5W89 | BH3 groove | 14 | 5000 | 0.20 | Reuse `examples/binder_mcl1/` |
| MDM2 | 4HFZ | p53 groove | 12 | 5000 | 0.20 | Cross-workflow comparison vs AfCycDesign MDM2 |
| GABARAP | 1KOT | LIR groove | 12 | 5000 | 0.13 | Tighter groove; tightest iPAE gate |
| RbtA | repo PDB | flat β-helix surface | 14 | 5000 | 0.40 | Reuse `examples/binder_rbta/`; flat-interface stress test |
| PD-L1 | 5IUS | PD-1-binding face | 14 | 5000 | 0.30 | Flat IGV interface; hard target |

Stage parameters per the existing skill (`workflow-skills/binder_design_rfpeptides.md`): ProteinMPNN CA-only `model=v_48_020`, `temperature=0.0001`, `omit_AAs=C`; 4 rounds of FastRelax with PeptideCyclizeMover; AfCycDesign reprediction; Rosetta interface metrics; RMSD clustering.

### 2.3 HELM-GPT (3 targets — only those with viable reward models)

| Target | Data source | Reward model | n_records target | Role |
|--------|-------------|--------------|-----------------:|------|
| **KRAS-G12D** | Existing 2,757-record patent set (HELM-GPT paper) | XGBoost MorganFP (Spearman ≈ 0.82, already validated) | 2,757 | **Positive control / reproducibility case** — reuse `examples/co_opt_kras_kd_perm/` |
| **PD-1/PD-L1** | BMS/Aurigene patents + ChEMBL peptide subset | XGBoost MorganFP (curate + train) | 500–1,500 | Macrocyclic PPI inhibitor case |
| **MDM2/p53** | ChEMBL + BindingDB peptide subset + stapled-peptide literature | XGBoost MorganFP (curate + train) | 500–1,500 | Classical intracellular PPI |

**Backups** (curated in parallel as insurance against failed feasibility): MCL1, CXCR4, SSTR2. If PD-1/PD-L1 or MDM2 fails the Spearman ≥ 0.4 gate (§5.2), promote the strongest backup.

**Co-optimization reward**: predicted Kd × permeability (existing `kras_perm` task template), with the Kd predictor swapped per target.

---

## 3. Repository Inventory — Reuse vs. Build

### 3.1 Reuse (already built and production-quality)

| Asset | Path | Use as-is for |
|-------|------|---------------|
| RFpeptides 5-stage pipeline | `workflow-skills/scripts/rfpeptides/run_pipeline.py` | All 5 RFpeptides tasks; has full checkpoint/resume, parallel CPU/GPU workers |
| AfCycDesign viz | `workflow-skills/scripts/afcycdesign/afcycdesign_viz.py` | Reads `afcycdesign_results.csv`; supports `--merged` |
| RFpeptides viz | `workflow-skills/scripts/rfpeptides/rfpeptides_viz.py` | Reads `final_summary.csv`; Gantt timeline from `pipeline.log` |
| HELM-GPT viz | `workflow-skills/scripts/helmgpt/helmgpt_viz.py` | Reads `phase3_final_ranking.csv`; 13-panel + radar |
| 3 workflow skill markdowns | `workflow-skills/binder_design_*.md` | Orchestration spec; LLM-agnostic |
| MCP per-job `metadata.json` | All `tool-mcps/*/jobs/*/metadata.json` | ISO-8601 `submitted_at` / `started_at` / `completed_at` for runtime stats |
| Existing case outputs | `examples/case{1,2,3}_*/` | Seed Run 0 of benchmark; validate scripts before re-running |
| HELM-GPT phase-3 composite scoring | `examples/co_opt_kras_kd_perm/postprocess_phase3.py` | Composite formula reuse; centralize per §3.2 |

### 3.2 Build (new infrastructure)

Layout under a new top-level `benchmark/` directory:

```
benchmark/
├── configs/
│   ├── targets.csv               # 13 targets; columns per §4.1
│   ├── workflows.yaml            # Per-workflow params + PASS gates + composite weights
│   ├── llm_backends.yaml         # Claude / GPT / Gemini endpoints + model IDs + token-counter hooks
│   └── thresholds.py             # SINGLE source of truth for PASS gates (replaces duplication
│                                 #   in skill markdown, postprocess_phase*.py, viz scripts)
├── data_curation/                # HELM-GPT only
│   ├── chembl_query.py           # Pull peptide-modality records by target_id
│   ├── patent_extract.py         # Patent table extraction (Google Patents, with manual review pass)
│   ├── normalize_endpoints.py    # → pKd / pKi / pIC50; canonical SMILES; HELM where derivable
│   ├── scaffold_split.py         # 70/15/15 scaffold-based split
│   └── datasets/                 # Per-target curated CSV (schema in §5.1)
├── reward_models/                # HELM-GPT only
│   ├── train_xgboost.py          # Morgan FP + descriptors → pKd
│   ├── eval_metrics.py           # Spearman, Pearson, RMSE, top-k enrichment, scaffold-split perf
│   └── trained/                  # Pickled models per target
├── runs/
│   └── {run_id}/                 # run_id format: {WF}_{TARGET}_R{n}_{LLM}  (e.g. AF_MDM2_R1_CLAUDE)
│       ├── agent_trace.jsonl     # Event stream (schema in §6)
│       ├── candidate_metrics.csv # Per-candidate (schema in §5.1)
│       ├── pipeline.log          # Plain-text stage log (compat with existing viz)
│       ├── artifacts/            # PDBs, intermediate files
│       └── summary.json          # Run-level rollup (totals, PASS counts, durations)
├── scripts/
│   ├── run_benchmark.py          # Top-level: run_id → invokes correct workflow runner
│   ├── workflow_runners/
│   │   ├── afcycdesign_runner.py # NEW — wraps afcycdesign_mcp w/ checkpoint, mirrors run_pipeline.py
│   │   ├── rfpeptides_runner.py  # Thin wrapper around existing run_pipeline.py
│   │   └── helmgpt_runner.py     # NEW — wraps RL + post-filter + structural eval w/ checkpoint
│   ├── agent_trace.py            # JSONL event-logger middleware around MCP tool calls
│   ├── llm_orchestrator.py       # LLM-agnostic invocation (Claude / OpenAI / Gemini SDKs)
│   ├── aggregate_metrics.py      # task-/target-/workflow-/agent-level rollups → summary CSVs
│   └── make_figures.py           # Reproduces manuscript Fig 2-5 from runs/
├── summary/
│   ├── task_summary.csv          # 13 rows × {success, PASS count, runtime, tokens, ...}
│   ├── candidate_summary.csv     # All candidates × all runs
│   ├── llm_comparison.csv        # 3 LLMs × 9 tasks paired metrics
│   └── agent_summary.csv         # Per-run agent process metrics
└── README.md                     # Run instructions, schema docs, figure recipes
```

### 3.3 Critical files to modify (consolidation work)

| File | Change | Why |
|------|--------|-----|
| `examples/co_opt_kras_kd_perm/postprocess_phase1.py:24` | Read threshold from `benchmark/configs/thresholds.py` | Eliminate duplicated `permeability > -6.0`, `KD < 10 μM` |
| `examples/co_opt_kras_kd_perm/postprocess_phase3.py:32-40` | Read composite weights from `thresholds.py` | Eliminate duplicated 7-metric weighting |
| `workflow-skills/scripts/*/<wf>_viz.py` | Read threshold lines from `thresholds.py` | Eliminate duplicated threshold constants |
| `workflow-skills/scripts/rfpeptides/run_pipeline.py` | Add `--agent-trace-out <path>` flag | Emit JSONL events alongside existing log |
| `tool-mcps/afcycdesign_mcp/src/jobs/manager.py` | Verify `sys.executable` fix per CLAUDE.md "Known Issues" | Prevent env-related failures during 13-run campaign |

---

## 4. Standard Task Lifecycle

Every benchmark task runs as a deterministic 6-step pipeline driven by `benchmark/scripts/run_benchmark.py`:

| Step | Input | Action | Output | Logged events |
|------|-------|--------|--------|---------------|
| 1. Target prep | PDB/UniProt + chain + hotspots from `targets.csv` | Download, clean, residue/chain QC | Standardized target PDB | `target_qc` |
| 2. Workflow execution | workflow config + LLM backend | Agent invokes MCP tools per skill markdown | Raw candidates + intermediates | `prompt`, `planning`, `tool_call`, `tool_result`, `error`, `retry` |
| 3. Filtering | Raw candidates | Apply workflow PASS gates (§5) | Passing candidates + reasons | `candidate_filter` |
| 4. Scoring | Passing candidates | Composite score (§5.3) | Ranked top-k | `candidate_score` |
| 5. Diversity | Ranked candidates | Sequence + RMSD clustering | Cluster table | `cluster` |
| 6. Report | Summary metrics | Auto-generate per-task report + figures | task report MD + PNGs | `final_report` |

User natural-language prompts are still allowed but resolve to a fixed `workflows.yaml` configuration so runs are reproducible.

---

## 5. PASS Gates, Schemas, and Composite Scoring

### 5.1 Candidate-level CSV (unified core schema, all workflows)

| Field | Type | Example |
|-------|------|---------|
| `task_id` | str | `AF_MDM2_001` |
| `target_id` | str | `MDM2_4HFZ_A` |
| `workflow` | str | `afcycdesign` / `rfpeptides` / `helmgpt` |
| `run_id` | str | `AF_MDM2_R1_CLAUDE` |
| `candidate_id` | str | `binder_3dc03c60` |
| `sequence_or_helm` | str | `cyclic(RYGDFESIEAIA)` |
| `rank` | int | 1 |
| `pass_status` | bool | TRUE |
| `pass_reason` | str | `pLDDT/iPTM passed` |
| `plddt` / `iptm` / `ipae` / `ddg` | float | per-workflow availability |
| `gnina_cnn_pkd` / `predicted_kd_um` / `logpapp` | float | HELM-GPT only |
| `composite_score` | float | 0.664 |
| `cluster_id` | str | `C03` |

### 5.2 PASS gates per workflow

| Workflow | Primary PASS gate | Excellent gate | Notes |
|----------|-------------------|----------------|-------|
| AfCycDesign | mean pLDDT ≥ 70, iPTM ≥ 0.50, iPAE ≤ 15, no fatal error | pLDDT ≥ 85, iPTM ≥ 0.70, iPAE ≤ 8 | |
| RFpeptides | valid cyclic backbone, pLDDT ≥ 0.70, iPAE ≤ workflow-specific (0.13–0.40 by target), Rosetta ddG < 0 | pLDDT ≥ 0.85, iPAE ≤ 8, ddG ≤ −20 kcal/mol, high CMS | iPAE gate per `targets.csv` to reflect interface flatness |
| HELM-GPT | valid HELM, pred Kd < 10 μM, logPapp > −6, iPTM ≥ 0.50, GNINA non-catastrophic | Kd < 1 μM, logPapp > −5, iPTM ≥ 0.70, high GNINA CNN | Pareto-front reporting required |
| **HELM-GPT reward-model gate** | Spearman ≥ 0.4 on scaffold-split test set | Spearman ≥ 0.6 | **Pre-RL gate**: a target whose reward model fails 0.4 is moved to backup |

### 5.3 Composite scoring (centralized in `thresholds.py`)

| Workflow | Formula |
|----------|---------|
| AfCycDesign | `0.30·pLDDT + 0.30·iPAE_inv + 0.25·iPTM + 0.15·pTM` |
| RFpeptides | `0.30·ddG_norm + 0.25·iPAE_norm + 0.20·pLDDT_norm + 0.15·CMS_norm + 0.10·SAP_norm` |
| HELM-GPT | `0.20·KD + 0.15·perm + 0.15·boltz_aff + 0.10·boltz_prob + 0.10·boltz_iPTM + 0.15·gnina_cnn + 0.15·gnina_vina` |

All formulae preserved verbatim from existing code/skills; centralization removes the three current copies.

### 5.4 Manuscript phrasing rule

Candidates are **computationally prioritized** or **high-confidence predicted** — never **validated** or **high-affinity binders**, since no wet-lab confirmation is in scope.

---

## 6. Agent Trace Logging Schema

`agent_trace.jsonl` — one event per line, written by `benchmark/scripts/agent_trace.py`. Events tap MCP tool calls via a context manager wrapping every `submit_*` / `get_job_status` / `get_job_result` invocation in the workflow runners.

| Field | Type | Example |
|-------|------|---------|
| `event_id` | str | `evt_000123` |
| `run_id` | str | `RF_MCL1_R1_CLAUDE` |
| `task_id` | str | `RF_MCL1_001` |
| `timestamp` | ISO 8601 | `2026-05-05T10:15:22Z` |
| `event_type` | enum | `prompt` / `planning` / `tool_call` / `tool_result` / `error` / `retry` / `user_intervention` / `candidate_filter` / `final_report` |
| `llm_backend` | str | `claude` / `gpt-4` / `gemini-pro` |
| `tool_name` | str | `rfpeptides_mcp.submit_cyclic_binder` |
| `input_artifact` | str | `target_clean.pdb` |
| `output_artifact` | str | `relaxed_001.pdb` |
| `status` | enum | `success` / `failure` / `retry` |
| `error_type` | enum | `environment` / `schema` / `runtime` / `scientific` / `agent_decision` |
| `token_input` / `token_output` | int | 1320 / 410 |
| `wall_time_sec` | float | 18.5 |
| `user_intervention` | bool | FALSE |
| `notes` | str | `adjusted chain ID` |

### 6.1 Agent process metrics (rolled up per run)

| Metric | Definition | Target |
|--------|------------|--------|
| End-to-end wall time | last − first event timestamp | report median per workflow |
| Compute time | sum of MCP `tool_call` `wall_time_sec` | separate from wall time |
| Agent overhead | wall − compute | report ratio |
| Total tokens | Σ input + output | per task |
| Tool-call count | # `tool_call` events | descriptive |
| Failure count | # `error` events | report all |
| Self-recovery rate | recovered / total failures | **target > 50%** |
| User intervention count | # `user_intervention=TRUE` | **target median = 0** |
| No-intervention success rate | zero-intervention success tasks / all tasks | **target > 70%** |
| Final report completion rate | reports generated / all tasks | **target > 90%** |

### 6.2 Failure mode taxonomy (used in `error_type`)

| Class | Definition | Recovery policy |
|-------|------------|-----------------|
| Environment | Conda env, GPU, CUDA OOM, path | Auto-retry, log |
| Schema/format | Chain ID, JSON shape mismatch | Agent self-repair |
| Runtime | Timeout, queue failure | Retry or downgrade params |
| Scientific | No candidates pass gate | Log as honest scientific failure — never disguise as success |
| Agent decision | Wrong tool, wrong params | Track separately for LLM comparison |

---

## 7. LLM Comparison (3 backends × 9 tasks)

| LLM tier | Role | Backend | Tasks |
|----------|------|---------|-------|
| Strong | Reference / upper bound | Claude (claude-opus-4-7) | 13 (full panel) + 3 reruns |
| Mid-cost | Cost/performance midpoint | GPT-4-class | 9 (3 per workflow) |
| Fast | Low-cost feasibility | Gemini-Pro-class | 9 (3 per workflow) |

The 9-grid (one row per workflow): MDM2 (AF), MCL1 (AF), PCSK9 (AF) for AfCycDesign; MCL1 (RF), MDM2 (RF), RbtA (RF) for RFpeptides; KRAS-G12D, PD-1/PD-L1, MDM2/p53 for HELM-GPT. Identical prompts, workflow skills, MCP servers, PASS gates across LLMs.

Reported as a compact main-text table:

| Metric | Claude | GPT | Gemini |
|--------|:------:|:---:|:------:|
| Task success rate | | | |
| No-intervention success rate | | | |
| Median total tokens | | | |
| Median wall time | | | |
| Self-recovery rate | | | |
| Median top-1 composite score | | | |

Failure-mode breakdown goes into Supplementary.

---

## 8. Manuscript Figures

| Figure | Title | Source | Reproducer |
|--------|-------|--------|-----------|
| Fig 2 | Systematic benchmark design of CycPepMCP workflows | `targets.csv` + `workflows.yaml` schema visualization | `make_figures.py --fig 2` |
| Fig 3 | Workflow success and candidate quality across targets | `task_summary.csv` + `candidate_summary.csv` | `make_figures.py --fig 3` |
| Fig 4 | Multi-objective and diversity analysis | `candidate_summary.csv` + cluster table | `make_figures.py --fig 4` |
| Fig 5 | Agentic execution performance | `agent_summary.csv` + `llm_comparison.csv` | `make_figures.py --fig 5` |

The three existing per-workflow viz scripts feed the per-target figure subpanels via their `--merged` mode.

---

## 9. Execution Timeline (6 weeks)

| Week | Tracks (parallel) | Deliverables |
|------|-------------------|--------------|
| W1 | (a) Lock targets.csv & workflows.yaml & thresholds.py; (b) Build `agent_trace.py` + `llm_orchestrator.py`; (c) Centralize PASS gates / composite formulas | Frozen configs, working trace logger, 1 pilot task per workflow runs end-to-end |
| W2 | (a) Run 3 pilot tasks (MDM2-AF, MCL1-RF, KRAS-HG) on Claude; (b) Build AfCycDesign + HELM-GPT runners with checkpointing; (c) Begin HELM-GPT data curation for PD-1/PD-L1 + MDM2 | 3 reference traces, 2 new runners, raw curation tables |
| W3 | (a) Run remaining 10 Claude tasks; (b) Train + validate XGBoost reward models for PD-1/PD-L1, MDM2; apply Spearman ≥ 0.4 gate (promote backup if fail) | 13 Claude runs, 2 reward models with metrics |
| W4 | (a) Run 3 reruns on Claude (repeatability); (b) Run GPT 9-task panel; (c) Iterate on any failed Claude task | 16 Claude runs total + GPT panel done |
| W5 | (a) Run Gemini 9-task panel; (b) Aggregation scripts; (c) Pareto-front + diversity analysis | All 34 runs complete, summary CSVs generated |
| W6 | (a) Generate Fig 2-5 + supplementary; (b) Methods + Results text drafts; (c) Reproducibility package (Zenodo-ready) | Manuscript-ready figures, text, package |

If any HELM-GPT reward model fails the 0.4 Spearman gate by mid-W3, escalate to backup target (MCL1 → CXCR4 → SSTR2) — adds ~3–5 days.

---

## 10. Verification

End-to-end checks that must pass before declaring the benchmark complete:

1. **Pilot smoke test** (end of W1): one task per workflow runs to completion, emits a non-empty `agent_trace.jsonl`, produces `candidate_metrics.csv` matching §5.1 schema, and `pipeline.log` parses by the existing viz Gantt logic.
2. **Threshold consistency** (W1): `thresholds.py` constants match the values currently in `postprocess_phase1.py:24`, `postprocess_phase3.py:32-40`, and the three viz scripts. Any drift is reconciled and consolidated.
3. **Reference reproduction** (W2): rerun `examples/binder_mdm2/` and `examples/binder_rbta/` through the new runners — final composite-score-ranked top-5 must overlap by ≥ 4 of 5 with the existing committed outputs (modulo seed).
4. **Reward-model gate** (W3): for each new HELM-GPT target, scaffold-split test Spearman ≥ 0.4 reported in `benchmark/reward_models/trained/<target>_metrics.json`. Any target failing → escalate per §9.
5. **Aggregation correctness** (W5): `aggregate_metrics.py` produces a `task_summary.csv` with exactly 13 rows × 1+ run each, no NaN PASS counts, and `agent_summary.csv` with all four target agent metrics in §6.1 populated.
6. **Figure reproducibility** (W6): `make_figures.py --fig {2,3,4,5}` regenerates all four manuscript figures from `benchmark/runs/` and `benchmark/summary/` with no manual editing.
7. **Reproducibility package** (W6): a fresh clone + `pip install -e .` + `python benchmark/scripts/run_benchmark.py --task AF_MDM2 --llm claude --dry-run` produces a valid agent trace and candidate CSV without manual intervention.

---

## 11. Risks and Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------:|-----------|
| HELM-GPT new target fails Spearman 0.4 gate | Medium | Curate 3 backups (MCL1, CXCR4, SSTR2) in parallel from W2; promote highest-Spearman |
| RFpeptides 5000-design runs blow GPU queue (FIFO, 1 job at a time) | High | Sequence the 5 RF targets across the 4-week run window; launch overnight |
| AfCycDesign manager.py `sys.executable` regression (per CLAUDE.md known issues) | Medium | Verify fix in W1; restart server before pilot |
| LLM-orchestrator API changes during run window | Low | Pin SDK versions in `llm_backends.yaml`; record version in each trace |
| Cherry-picking accusation from reviewer | Medium | Pre-register `targets.csv` + PASS gates as a frozen artifact in repo before W3 launch; commit hash referenced in Methods |
| 6-week timeline slippage | Medium | Phased fallback: ship Phase A with 11 tasks (drop PD-1/PD-L1 or MDM2 from HELM-GPT) for first submission; complete in revision |

---

## 12. Priority Checklist

| Priority | Item | Risk if not done |
|---------:|------|------------------|
| P0 | Lock `targets.csv` + `workflows.yaml` + `thresholds.py` | Drift during execution; cherry-picking exposure |
| P0 | `agent_trace.jsonl` event logger | No quantitative agent claim possible |
| P0 | 13-task primary pass on Claude | Still a case-study paper |
| P0 | Full success/failure stats (no censoring) | Cherry-picking accusation |
| P0 | Runtime / token / failure / intervention metrics | Agentic-AI claim unsupported |
| P0 | HELM-GPT reward-model Spearman ≥ 0.4 gate | Reward-model RL is not credible |
| P1 | 3-LLM panel (9 tasks each) | LLM-agnostic claim weakened |
| P1 | n=2 reruns on 3 key tasks | Robustness evidence weak |
| P1 | Reproducibility package on Zenodo | Open-source impact reduced |
| P2 | Expansion to 24+ tasks | Defer to revision round if requested |

---

## Appendix A — Run ID Naming

`{WF}_{TARGET}_R{n}_{LLM}` — e.g. `AF_MDM2_R1_CLAUDE`, `RF_MCL1_R2_GPT`, `HG_KRASG12D_R1_GEMINI`.

`WF` ∈ {`AF`, `RF`, `HG`}, `TARGET` is an UPPER snake-case short name from `targets.csv`, `R{n}` is the seed/repeat index (1-based), `LLM` ∈ {`CLAUDE`, `GPT`, `GEMINI`}.

## Appendix B — Files to Create (concrete checklist)

- [ ] `benchmark/configs/targets.csv` (13 rows)
- [ ] `benchmark/configs/workflows.yaml` (3 workflows × params + PASS gates)
- [ ] `benchmark/configs/llm_backends.yaml` (3 backends + token-counter hook config)
- [ ] `benchmark/configs/thresholds.py` (centralized PASS gates + composite weights)
- [ ] `benchmark/scripts/agent_trace.py` (JSONL event logger + MCP tool middleware)
- [ ] `benchmark/scripts/llm_orchestrator.py` (Claude / OpenAI / Gemini SDK adapters)
- [ ] `benchmark/scripts/run_benchmark.py` (top-level dispatcher)
- [ ] `benchmark/scripts/workflow_runners/afcycdesign_runner.py` (NEW pipeline w/ checkpoint)
- [ ] `benchmark/scripts/workflow_runners/rfpeptides_runner.py` (thin wrapper around existing `run_pipeline.py`)
- [ ] `benchmark/scripts/workflow_runners/helmgpt_runner.py` (NEW pipeline w/ checkpoint)
- [ ] `benchmark/scripts/aggregate_metrics.py` (rollups → 4 summary CSVs)
- [ ] `benchmark/scripts/make_figures.py` (Fig 2-5 reproducer)
- [ ] `benchmark/data_curation/{chembl_query,patent_extract,normalize_endpoints,scaffold_split}.py`
- [ ] `benchmark/reward_models/{train_xgboost,eval_metrics}.py`
- [ ] `benchmark/README.md`
- [ ] Edits to `examples/case3_*/postprocess_phase{1,3}.py` to read from `thresholds.py`
- [ ] Edits to `workflow-skills/scripts/*/_viz.py` to read from `thresholds.py`
- [ ] `--agent-trace-out` flag added to `workflow-skills/scripts/rfpeptides/run_pipeline.py`

## Appendix C — Final Manuscript Claim Template

> CycPepMCP was evaluated on a pre-registered benchmark panel of 13 cyclic peptide design tasks spanning three workflows (AfCycDesign, RFpeptides, HELM-GPT) and multiple target classes (intracellular PPIs, immune checkpoints, GPCR-adjacent, flat protein interfaces). Across these tasks, the system generated ranked cyclic peptide candidates with systematically recorded structural, binding, permeability, and diversity metrics. In parallel, agentic execution traces across three LLM backends showed that CycPepMCP completed most workflows without human intervention, recovered from common tool-level failures, and maintained acceptable token and runtime overhead — supporting the claim of an open, LLM-agnostic agentic AI platform for autonomous cyclic peptide design.
