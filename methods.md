# Methods

## System architecture and design principles

CycPepMCP implements a two-layer architecture for AI-orchestrated cyclic peptide engineering built on the Model Context Protocol (MCP). The tool layer comprises 28 MCP servers, each encapsulating a single scientific software package as a set of remotely callable tool endpoints. The orchestration layer consists of markdown-based workflow skills that define multi-step computational protocols, executed by an AI agent (Claude Code, Anthropic) through natural language interaction. This separation of concerns enables modular composition: individual tools can be developed, tested, and deployed independently, while workflow skills encode domain expertise about how to chain tools together for complete design campaigns.

Two command-line interfaces manage the system lifecycle. The `cpmcp` CLI handles MCP server installation, registration, status monitoring, and auto-creation from external repositories. The `cpskill` CLI manages workflow skills, including installation of required MCP dependencies and step-by-step execution guidance. Both tools operate on YAML-based registries (`mcps.yaml` for 28 local MCP servers; `public_mcps.yaml` for 9 third-party database MCPs) that map each server to its runtime environment, installation path, Docker image, environment variables, and cache configuration.

A centralized cache system manages shared model weights and reference databases across all MCP servers. The cache root directory (controlled by the `MACROMNEX_CACHE` environment variable; default `~/.macromnex/cache`) is organized into `data/` (databases, reference datasets) and `model/` (machine learning model weights) subdirectories, with per-server subpaths configured in the registry. For Docker-based servers, cache directories are automatically mounted as read-only volumes; for non-containerized servers, the cache root is passed as an environment variable. This architecture eliminates redundant downloads and ensures consistency of model weights across tools (for example, AlphaFold2 parameters are shared between AfCycDesign and other AlphaFold-dependent servers).

The AI agent orchestrates workflows by interpreting natural language instructions, invoking the appropriate MCP tool endpoints, parsing structured outputs, and making decisions based on encoded quality thresholds and scoring criteria. Workflow skills are registered as Claude Code slash commands (e.g., `/binder-design-rfpeptides`), enabling users to invoke complete multi-stage design protocols through conversational interaction.

## MCP server implementation

Each MCP server wraps a scientific software package using the FastMCP Python framework, exposing computational functions as JSON-RPC tool endpoints accessible via standard input/output (stdio) transport. Servers are implemented as standalone Python modules (`src/server.py`) with typed function signatures, docstrings for parameter documentation, and structured return values.

Three runtime environments are supported to accommodate diverse dependency requirements. Docker containers (14 servers) encapsulate GPU-accelerated tools with complex dependency chains, including CUDA libraries, scientific computing frameworks, and pre-compiled binaries. Docker images are based on `nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04` with `PYTHONUNBUFFERED=1` for real-time log streaming. UV virtual environments (6 servers) provide lightweight, fast-installing isolation for CPU-only tools with pure Python dependencies. Conda environments (6 servers) accommodate tools requiring platform-specific packages (e.g., RDKit, AmberTools) not available through pip.

GPU-intensive MCP servers share an asynchronous job queue architecture to manage long-running computations (typically 10-90 minutes per job). Each server maintains a first-in-first-out (FIFO) queue processing one GPU job at a time, with thread-safe metadata management via file-level locking (`fcntl.flock`) on `metadata.json`. The job lifecycle follows a submit-poll-retrieve pattern: `submit_*()` functions return a job identifier immediately, `get_job_status()` reports queue position and execution state, and `get_job_result()` returns structured outputs upon completion. Job artifacts (output files, stdout/stderr logs, metadata) are persisted in the filesystem for post-hoc inspection.

The 28 MCP servers collectively wrap the following scientific software packages: RFdiffusion All-Atom for backbone generation; ProteinMPNN and LigandMPNN for inverse folding sequence design; Rosetta (FastRelax, GenKIC, InterfaceAnalyzer) for structure refinement and physics-based scoring; AlphaFold2 (via AfCycDesign) and AlphaFold3 for structure prediction; Boltz-2 for structure and affinity prediction; HELM-GPT for generative macrocyclic peptide design; GROMACS and Amber for molecular dynamics simulation; Gnina for CNN-based molecular docking; and several specialized property predictors for membrane permeability (CycPepTMP, MultiCycPermea, PharmPApp, CPMP, MultiCycGT), conformational sampling (ADCP, PepFlow), and cyclic peptide design (CyclicChamp, CycBuilder, HighFold3, HighPlay, BoltzGen, HADDOCK3).

## Workflow skill system

Workflow skills are defined as structured Markdown documents that encode multi-step computational protocols. Each skill specifies: required MCP servers, input requirements and validation criteria, ordered sequences of MCP tool calls with recommended parameters, quality thresholds for filtering intermediate results, decision trees for branching logic, composite scoring formulas for final ranking, and output file structures with visualization specifications.

A critical function of the skill system is managing chain convention inconsistencies across tools. Different software packages assign peptide and target chains differently (for example, RFpeptides outputs the binder as Chain A and the target as Chain B, while AfCycDesign reverses this assignment). Skills encode the necessary chain swaps and parameter remappings to ensure correct data flow between pipeline stages.

Skills define composite scoring formulas that normalize heterogeneous metrics to a common [0, 1] scale and compute weighted sums. Metrics where lower values indicate better quality (e.g., binding energy, interface alignment error) are inverted before normalization. The weights reflect the relative importance of each metric for the specific design objective, as determined by domain expertise and empirical calibration.

Three workflow skills have been implemented, covering complementary design strategies: backbone-first design with physics-based refinement (RFpeptides protocol), end-to-end deep learning optimization (AfCycDesign protocol), and reinforcement learning with non-canonical amino acid support (HELM-GPT protocol). Each skill includes a publication-quality visualization pipeline generating distribution plots, quality scatter plots, ranking charts, metrics tables, and execution timelines.

## RFpeptides backbone-first binder design protocol

The RFpeptides protocol implements a five-stage pipeline that combines deep learning backbone generation with iterative physics-based refinement, deep learning validation, and structural diversity analysis.

**Stage 1: Backbone generation.** RFdiffusion All-Atom generates three-dimensional cyclic peptide backbone structures geometrically complementary to a target protein surface. The diffusion model operates on Ca/N/C/O backbone atoms, producing glycine-only scaffolds (sequence to be designed in subsequent stages). Users specify target PDB coordinates, binder length (typically 8-16 residues), number of designs, and optionally hotspot residues defining the target epitope. The output assigns the binder to Chain A and the target to Chain B.

**Stage 2: Iterative sequence design.** Each backbone undergoes four rounds of sequence optimization, alternating between ProteinMPNN CA-only inverse folding and Rosetta FastRelax structure refinement. ProteinMPNN parameters are: model `v_48_020`, sampling temperature 0.0001, omitted amino acids "C" (to avoid unpaired cysteines), and designable chains "A". Rosetta FastRelax applies 4 rounds of gradient-based energy minimization with the PeptideCyclizeMover enforcing head-to-tail backbone cyclization via peptide bond formation between the N-terminus and C-terminus. Each round's relaxed structure serves as input for the subsequent round, enabling progressive sequence-structure co-optimization.

**Stage 3: Deep learning validation.** Designed sequences are validated by independent structure reprediction using AfCycDesign with the `pssm_semigreedy` optimizer. The repredicted complex is compared against the designed structure to extract: interface predicted aligned error (iPAE), backbone root-mean-square deviation (RMSD) over Ca atoms, and per-residue local distance difference test (pLDDT) confidence scores. Designs with iPAE > 0.20, RMSD > 1.5 A, or pLDDT < 0.70 are filtered.

**Stage 4: Physics-based quality filtering.** Rosetta InterfaceAnalyzer computes three interface metrics on the relaxed complex structure: binding free energy (ddG, in Rosetta energy units), spatial aggregation propensity (SAP), and contact molecular surface area (CMS). Designs are filtered using thresholds: ddG < -30 REU, SAP < 35, CMS > 300 A^2. These thresholds may be relaxed for challenging targets (e.g., flat binding surfaces).

**Stage 5: Clustering and selection.** Surviving designs are clustered by pairwise Ca RMSD using a greedy algorithm with a distance cutoff of 1.0-2.0 A. Designs are ranked within and across clusters by a composite score:

*S* = 0.30 *ddG*_norm + 0.25 *iPAE*_norm + 0.20 *pLDDT*_norm + 0.15 *CMS*_norm + 0.10 *SAP*_norm

where each metric is min-max normalized to [0, 1] and metrics where lower is better (ddG, iPAE, SAP) are inverted. The top 5-10 structurally diverse designs are selected for experimental characterization. An automated pipeline script (`run_pipeline.py`) parallelizes CPU-bound stages (Stage 2) across multiple workers and rotates GPU-bound stages (Stage 3) across available GPUs, with checkpoint-based resume capability.

## AfCycDesign end-to-end optimization protocol

The AfCycDesign protocol performs single-stage, end-to-end cyclic peptide binder design using AlphaFold2-based structure prediction as both the design engine and the evaluation metric, implemented as a six-stage workflow.

**Stages 1-3: Target validation, job submission, and monitoring.** The input target PDB is validated for chain assignments and structural completeness. A binder design job is submitted to the AfCycDesign MCP server with parameters specifying binder chain length (8-16 residues), optimizer type, number of AlphaFold2 models (recommended: 2), and number of recycling iterations (0-3). A 2-5 minute silent period during initial JAX compilation is expected before optimization progress is reported.

**Optimization.** The recommended optimizer, `pssm_semigreedy`, maintains a position-specific scoring matrix (PSSM) and iteratively samples sequences by combining greedy and stochastic mutations. The alternative `3stage` optimizer applies three sequential phases: logits-level optimization (120 iterations), softmax-level optimization (60 iterations), and one-hot hard optimization (10 iterations), with temperature annealing from 1.0 to 0.01. Both optimizers minimize a composite AlphaFold2 loss combining predicted interface confidence (iPAE), structural confidence (pLDDT), and predicted template modelling score (pTM).

**Stages 4-6: Result collection, analysis, and visualization.** Output PDB files (target as Chain A, binder as Chain B) are collected with per-design metrics: loss, interface contacts (i_con), pLDDT, pTM, iPTM, and iPAE. Designs are ranked by composite score:

*S* = 0.30 *pLDDT* + 0.30 *iPAE*_inv + 0.25 *iPTM* + 0.15 *pTM*

where *iPAE*_inv = 1 - iPAE. Quality thresholds for candidate selection: pLDDT > 0.70 (good) or > 0.90 (excellent), iPAE < 0.15 (good) or < 0.11 (excellent), iPTM > 0.60 (good) or > 0.80 (excellent). Six publication-quality figures are generated: pLDDT distribution, iPAE bar chart, pLDDT-vs-iPAE scatter colored by composite score, design ranking, top-designs metrics table, and iPTM distribution.

## HELM-GPT reinforcement learning protocol for ncAA macrocycles

The HELM-GPT protocol enables design of synthesizable macrocyclic peptides incorporating non-canonical amino acids (ncAAs), using reinforcement learning (RL) co-optimization followed by multi-modal structural validation with heavy-atom-based routing.

**Phase 1: RL co-optimization.** A GPT-based generative model produces macrocyclic peptide sequences in HELM (Hierarchical Editing Language for Macromolecules) notation, supporting a 3,104-monomer library that includes N-methylated amino acids, D-amino acids, non-standard caps, and other ncAA building blocks. The model is trained using REINVENT with Contrastive Preference Learning (CPL) loss (`loss_type="reinvent_cpl"`) to maximize a dual-objective reward combining KRAS binding affinity predicted by a local XGBoost model (target: KD < 10 uM) and membrane permeability predicted by a local Random Forest model (target: > -6.0 log cm/s). Training parameters: 500 optimization steps, batch size 32, learning rate 1 x 10^-4, sigma 60. Both scoring models are pre-trained and execute locally, enabling fast reward computation (~ms per candidate) without external GPU server dependencies during RL training.

Post-RL candidate selection applies sequential filters: HELM notation validation, HELM-to-SMILES conversion (preserving ncAA chemistry), explicit permeability and binding affinity verification against RL predictions, and heavy-atom counting for downstream routing. Candidates are capped at 100 for structural evaluation.

**Phase 2: Structural evaluation.** Candidates are routed to parallel evaluation tracks based on heavy-atom count, reflecting the 128-atom ligand limit of Boltz-2. Track A (candidates with <= 128 heavy atoms): Boltz-2 predicts binding affinity using SMILES-based ligand input with a 3-head ensemble, producing per-head affinity scores and binding probability estimates. Gnina molecular docking is applied to the predicted complex structures, yielding CNN affinity (pKd) and Vina docking scores. Track B (all candidates): AlphaFold3 predicts protein-ligand complex structures using `ligand_smiles` input (preserving exact ncAA chemistry without conversion to canonical sequences), with pre-computed multiple sequence alignments (A3M format) for the KRAS target to bypass the computationally expensive MMseqs2 search step (~30-60 minutes). Output metrics include pLDDT, pTM, and iPTM confidence scores. Gnina docking is applied to all AlphaFold3-predicted structures.

**Phase 3: Final selection.** Track-dependent composite scoring accounts for the different metrics available for each heavy-atom class. For candidates with <= 128 heavy atoms:

*S* = 0.20 *KD*_norm + 0.15 *Perm*_norm + 0.15 *Boltz_aff*_norm + 0.10 *Boltz_prob*_norm + 0.10 *AF3_iPTM*_norm + 0.15 *Gnina_CNN*_norm + 0.15 *Gnina_Vina*_norm

For candidates with > 128 heavy atoms:

*S* = 0.25 *KD*_norm + 0.20 *Perm*_norm + 0.15 *AF3_iPTM*_norm + 0.20 *Gnina_CNN*_norm + 0.20 *Gnina_Vina*_norm

Quality thresholds for final candidate selection: KRAS KD < 10 uM (good), permeability > -6.0 log cm/s (good), AF3 iPTM > 0.60 (good), Gnina CNN affinity > 6.0 pKd (good), Gnina Vina score < -7.0 kcal/mol (good). The top 5-10 structurally diverse candidates are selected for experimental characterization, prioritizing designs with strong docking scores, high AF3 confidence, and diverse ncAA compositions.

## Automated MCP server creation pipeline

CycPepMCP includes an eight-step, AI-assisted pipeline (`cpmcp create`) that automates the transformation of scientific software repositories into functional MCP servers. The pipeline employs Claude Code as a code analysis and generation engine, with checkpoint-based recovery enabling restart from any step.

Step 1 creates a standardized project directory structure (`repo/`, `scripts/`, `src/`, `examples/`, `claude_outputs/`). Step 2 clones the target GitHub repository with submodule support (falling back to shallow then plain clone strategies). Step 3 analyses the repository to detect environment requirements, creates a conda or UV virtual environment with the appropriate Python version, and identifies common use cases from documentation and example scripts. Step 4 executes identified use cases with automated debugging, generating execution reports. Step 5 produces reusable Python function wrappers from the tested use cases. Step 6 extracts functions as MCP tool definitions and wraps them in a FastMCP server (`src/server.py`) with input validation and error handling. Step 7 validates the server through integration testing with Claude Code and Gemini CLI. Step 8 generates comprehensive documentation (README) and a runtime-appropriate setup script (`quick_setup.sh`).

Runtime auto-detection distinguishes between conda (for repositories requiring RDKit, PyTorch, CUDA toolkit, or AmberTools) and UV (for lightweight pip-installable packages) environments. The completed server is automatically registered in the YAML-based MCP registry. Marker files in a `.pipeline/` directory track completion of each step, and the `--rerun-from-step` flag enables selective re-execution.

## Visualization and reporting

Each workflow skill includes a visualization pipeline implemented as a standalone Python script (`workflow-skills/scripts/`) that generates publication-quality figures using matplotlib and seaborn. Figures are rendered at 300 DPI with colorblind-friendly palettes and transparent backgrounds.

The RFpeptides workflow produces nine panels: distribution plots for ddG, iPAE, pLDDT, SAP, and CMS; a ddG-vs-iPAE quality scatter plot colored by composite score; a composite score distribution; a top-designs metrics table in three-line academic style; and an execution timeline (Gantt chart) of the five pipeline stages. The AfCycDesign workflow produces six panels covering pLDDT, iPAE, quality scatter, design ranking, metrics table, and iPTM distributions. The HELM-GPT workflow produces twelve panels spanning KD distribution, permeability distribution, KD-vs-permeability scatter, AF3 iPTM, Gnina CNN affinity, Gnina Vina score, Boltz-2 affinity, Boltz-2 probability, composite score, radar chart of top candidates, metrics table, and execution timeline. All visualizations support both individual panel export and merged multi-panel layouts (`--merged` flag).

Composite scores are computed by min-max normalization of each metric to the [0, 1] interval, inversion of metrics where lower values indicate better quality, and weighted summation with domain-informed weights as specified in each protocol section.

## Case studies

Three case studies demonstrate the application of CycPepMCP across diverse design scenarios.

**MDM2 binder design (AfCycDesign).** A cyclic peptide binder targeting the p53-binding pocket of human MDM2 (PDB: 4HFZ) was designed using the AfCycDesign protocol with 12-residue binder length and hotspot residues [54, 56, 58, 61, 67, 96, 99, 100] defining the binding interface. This case demonstrates rapid single-stage optimization for targets with well-defined binding pockets.

**RbtA binder design (RFpeptides).** A cyclic peptide targeting rhamnosyltransferase A (RbtA) from *Acinetobacter baumannii* was designed using the full five-stage RFpeptides protocol with 12-16 residue binder length and 7 hotspot residues spanning the beta-helix surface. Quality thresholds were relaxed (iPAE < 0.25, ddG < -25 REU, pLDDT > 0.60) to accommodate the challenging flat binding surface geometry lacking deep pockets.

**KRAS binder design (HELM-GPT).** Macrocyclic peptides incorporating non-canonical amino acids were designed against KRAS using the HELM-GPT protocol with dual-objective RL co-optimization for binding affinity and membrane permeability. Twenty-two candidates were evaluated through the heavy-atom routing pipeline, with structural validation by AlphaFold3, Boltz-2 (for candidates <= 128 heavy atoms), and Gnina docking.

## Multi-target benchmark

To characterise the behaviour of the three workflows beyond the single-target case studies, each protocol was executed on a panel of independent targets. The RFpeptides protocol was run against MDM2, MCL1, PD-L1 and GABARAP (500 designs per target, 2,000 total). The AfCycDesign protocol was run against Bcl-xL, PCSK9, RbtA and XIAP at two binder lengths (14 and 16 residues; 500 designs per arm, 4,000 total). The HELM-GPT protocol was run against KRAS-G12D, MDM2/p53 and PD-1/PD-L1, each sampling approximately 11,000 unique parseable macrocycles from which the top 20 by composite reward entered structural evaluation. All runs used the parameters specified in the corresponding protocol sections above.

Structural confidence provides the common basis for comparison between the two peptide-backbone workflows. For RFpeptides, designs were scored by AfCycDesign reprediction and counted as passing at iPAE < 0.20 and pLDDT > 0.70. For AfCycDesign, designs were classified on Step-6 re-predicted values only, since the design-time metrics are the optimiser's own objective and are correspondingly optimistic; the *Acceptable* tier corresponds to pLDDT > 0.70 and iPAE < 0.30.

**Table 1.** Multi-target benchmark of the RFpeptides and AfCycDesign workflows. Values are medians over 500 designs per arm, with the best single design in parentheses.

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

Three observations follow. First, outcome is governed far more by target than by protocol: pass rates span 0% to 81% across arms, and the two extremes (RbtA, PCSK9) occur within a single workflow run under identical settings. PCSK9 yielded no acceptable design across 1,000 attempts, with a minimum iPAE of 0.329, which is reported here as a negative result rather than a run failure. Second, the shorter 14-residue binder outperformed the 16-residue binder on every AfCycDesign target that produced any acceptable design, by factors of 3.5 to 10. Third, no AfCycDesign arm reached the *Good* (pLDDT > 0.85, iPAE < 0.15) or *Excellent* (pLDDT > 0.90, iPAE < 0.11) tiers once design-time optimism was removed by reprediction, which underscores the importance of scoring on independently repredicted values.

![AfCycDesign multi-target benchmark](results/figures/afcycdesign_benchmark_summary.png)

**Figure 1.** AfCycDesign four-target campaign (4 targets × 2 binder lengths × 500 designs). (**a**, **b**) Re-predicted pLDDT and interface PAE for all 1,000 designs per target, shown as violin, interquartile bar and per-design jitter, with the open marker and the printed value giving the median. No acceptance line is drawn across these panels: the usable threshold is target-dependent, and a single shared gate would misrepresent the comparison. The two arms marked with an asterisk were run against cropped targets and are not on the same footing as the other two, as panel **c** shows. (**c**) Median interface PAE for the same designs re-predicted against the cropped target used during the campaign and against the intact protein. Cropping lowers median interface PAE by 0.15–0.17 for PCSK9 (107 of 496 residues retained) and by 0.51–0.52 for RbtA (166 of 441), so the apparent advantage of these two arms in panels a and b is substantially an artifact of target size. (**d**) Best design per arm by the composite score 0.50·pLDDT + 0.50·(1 − iPAE), on re-predicted values.

Re-predicted pLDDT and interface PAE are near-collinear within every target (*r* = −0.92 to −0.99), so they constitute approximately one axis of information rather than two independent criteria; the iPTM and composite distributions, the design-time versus re-predicted comparison, and the sampling-yield projection are kept as standalone panels rather than on the sheet for this reason. The sampling-yield panel (`afcycdesign/afcycdesign_benchmark_sampling_yield.pdf`) sweeps the interface PAE cut-off toward the gate at 0.20, drawing the measured region solid and the log-linear extrapolation dashed, and gives the sampling depth each arm's tail implies for 10 designs below the gate: 1,111 for RbtA, ~985 for Bcl-xL, ~7,885 for XIAP and ~230,257 for PCSK9.

The magnitude of that design-time optimism can be quantified directly, because every AfCycDesign arm carries both the optimiser's own metrics and an independent AF-multimer reprediction of the same design (Table 2). Across the eight arms, design-time pLDDT exceeds the repredicted value by 0.07 to 0.36, and design-time iPAE understates it by 0.13 to 0.39. The gap is smallest for RbtA (pLDDT 0.907 to 0.848) and largest for Bcl-xL and XIAP, where repredicted pLDDT falls below 0.52 from design-time values above 0.78. Because the optimiser is selecting on precisely these quantities, the ranking it produces is not a reliable guide to repredicted quality, and the two should never be pooled.

**Table 2.** AfCycDesign design-time versus re-predicted confidence, medians over 500 designs per arm. Runtime is the median wall-clock per design on one GPU, from the subset of records carrying timing (n = 258).

| Arm | Design pLDDT | Repredicted pLDDT | Design iPAE | Repredicted iPAE | Runtime (min) |
|---|---|---|---|---|---|
| Bcl-xL (14) | 0.783 | 0.514 | 0.176 | 0.503 | 7.0 |
| Bcl-xL (16) | 0.840 | 0.476 | 0.147 | 0.535 | 7.0 |
| PCSK9 (14) | 0.880 | 0.588 | 0.173 | 0.474 | 3.9 |
| PCSK9 (16) | 0.920 | 0.634 | 0.152 | 0.432 | 4.0 |
| RbtA (14) | 0.907 | 0.848 | 0.129 | 0.261 | 6.1 |
| RbtA (16) | 0.916 | 0.834 | 0.119 | 0.270 | 6.7 |
| XIAP (14) | 0.807 | 0.517 | 0.156 | 0.473 | 3.5 |
| XIAP (16) | 0.785 | 0.511 | 0.163 | 0.490 | 3.6 |

Two controls bound the interpretation of these values. A positive control against MDM2 reaches pLDDT 0.927, iPAE 0.101 and iPTM 0.878 under the same reprediction protocol, confirming that the pipeline resolves a confident peptide-target complex when one exists; no production design in the campaign reached that tier. Conversely, the targets were not all presented at full length. Bcl-xL (175 residues) and XIAP (89 residues) were used intact, whereas PCSK9 was cropped from 496 to 107 residues and RbtA from 441 to 166. Repredicting an identical peptide against both forms shows the effect is substantial: for RbtA, pLDDT falls from 0.558 on the 166-residue span to 0.379 on the full protein while iPAE rises from 0.477 to 0.744, and for PCSK9 from 0.585 to 0.319 and 0.469 to 0.762 respectively. The four targets are of comparable size as run (89 to 175 residues), so the comparison between arms remains internally consistent, but absolute confidence values for PCSK9 and RbtA are optimistic relative to the intact proteins and should not be read as transferable to them. A small hotspot ablation was also performed on PCSK9 and XIAP, but with only two designs per condition it is reported as exploratory and no conclusion is drawn from it.

For HELM-GPT, which operates in a distinct metric space, the three targets differed chiefly in predicted affinity rather than in structural agreement. Median Kd over the top 20 candidates was 4.59 µM for KRAS-G12D, 4.35 µM for MDM2/p53 and 45.73 µM for PD-1/PD-L1, and under the workflow's stated 10 µM gate PD-1/PD-L1 retained no candidates at all (against 1,991 and 1,354 for the other two), its best single candidate being predicted at 22.12 µM. MDM2/p53 was the only target on which all four orthogonal methods concurred, clearing both the AF3 iPTM (20/20) and Gnina CNN (20/20) thresholds while also achieving the best docking score of the campaign (−9.61 kcal/mol). PD-1/PD-L1 presented the highest median AF3 iPTM (0.80) despite the weakest affinity distribution, and its reward model showed top-decile enrichment of only 0.33; its structural agreement should therefore not be read as independent confirmation.

**Table 3.** HELM-GPT three-target campaign. Phase-1 counts are over all unique parseable macrocycles; all other values are over the top 20 candidates per target that entered structural evaluation.

| | KRAS-G12D | MDM2/p53 | PD-1/PD-L1 |
|---|---|---|---|
| Unique valid HELM | 11,049 | 10,941 | 10,684 |
| Pass, permeability > −6 | 6,698 | 9,432 | 9,980 |
| Pass, Kd < 10 µM | 3,325 | 1,471 | 0 |
| Pass, both gates jointly | 1,991 | 1,354 | 0 |
| Kd, best / median (µM) | 2.53 / 4.59 | 2.88 / 4.35 | 22.12 / 45.73 |
| Permeability, median (log cm/s) | −5.55 | −4.65 | −4.67 |
| Heavy atoms, range | 57–98 | 81–90 | 77–90 |
| Boltz-2 affinity, median | −0.203 | −0.534 | −0.574 |
| Boltz-2 binary probability, median | 0.41 | 0.54 | 0.61 |
| Boltz-2 ligand iPTM, median | 0.78 | 0.84 | 0.85 |
| AF3 iPTM, median (number ≥ 0.60) | 0.58 (9/20) | 0.70 (20/20) | 0.80 (20/20) |
| Gnina CNN, median pKd (number > 6.0) | 7.41 (19/20) | 7.63 (20/20) | 7.46 (20/20) |
| Gnina Vina, median / best (kcal/mol) | −5.97 / −8.55 | −6.36 / −9.61 | −5.52 / −6.71 |
| Best composite | 0.726 | 0.635 | 0.689 |

Four caveats qualify Table 3. The Kd gate is load-bearing and was applied too loosely in the run: the affinity predictor emits log10(Kd/µM), so the 10 µM threshold corresponds to a cut at 10 on that scale, whereas the campaign applied a cut at 10,000. Under the stated 10 µM gate PD-1/PD-L1 retains no candidates, making the campaign two targets rather than three; the attrition panel of Figure 2 therefore shows the affinity gate removing almost nothing, which reflects the threshold as applied rather than the molecules. Boltz-2 is extrapolating, since its affinity head was trained on ligands of up to 56 heavy atoms while every candidate here exceeds that, so its values are directional rather than calibrated. AlphaFold3 could not construct an RDKit reference conformer for these macrocycles and fell back, so its iPTM is a useful orthogonal check but not a clean ligand prediction. Finally, permeability is a model prediction from the same scorer that shaped the reinforcement-learning reward, so it measures consistency with the objective rather than providing an independent assessment of the molecules.

![HELM-GPT three-target benchmark](results/figures/helmgpt_benchmark_figure.png)

**Figure 2.** HELM-GPT three-target permeability campaign (12,000 sampled macrocycles per target; 20 per target advanced to structural evaluation). (**a**-**d**) Distribution of predicted Kᵈ, predicted permeability, Boltz-2 ligand iPTM and Gnina CNN affinity over the 20 candidates of each arm, shown as violin, interquartile bar and per-candidate jitter, with the open marker and the printed value giving the median. These 20 were already selected on the Phase-1 composite, so each spread is a truncated one. (**e**) Attrition from generation to structural evaluation. The permeability term is the only Phase-1 filter that binds as applied: the Kᵈ gate row sits flush with the parsed row because the threshold was applied 10³-fold too loosely in the run; under the workflow's stated 10 µM gate the counts are 3,325, 1,471 and 0 (Table 3). (**f**) Highest-composite candidate of each target, with the number of the four quality gates it clears. Phase-3 routing prefers the Boltz-2 ligand iPTM over the AlphaFold3 value whenever one is available, and the two are effectively uncorrelated within target (*r* = −0.23 to +0.45) with Boltz-2 higher on 50 of 60 complexes (median offset +0.12), so the composite reads the more optimistic of the two throughout; the AlphaFold3 value is reported per candidate in the table.

Rosetta interface energetics were computed for all 2,000 RFpeptides designs in three independent replicates (6,000 evaluations), and are reported as the replicate mean with standard deviation (Table 4). Replicate spread is modest for SAP and CMS but non-negligible for ddG (median SD 0.53–0.94 REU, with individual designs exceeding 6 REU), so single-replicate ddG values should not be compared at finer resolution than a few REU.

**Table 4.** Rosetta interface metrics for the RFpeptides panel, medians over 500 designs per target.

| Target | ddG median (best) | median ddG SD | SAP median | CMS median | Passing physics | Passing physics and structure |
|---|---|---|---|---|---|---|
| MDM2 | −21.53 (−41.67) | 0.81 | 22.03 | 268.55 | 16/500 | 1/500 |
| MCL1 | −22.61 (−47.06) | 0.53 | 22.20 | 281.21 | 83/500 | 0/500 |
| PD-L1 | −25.55 (−124.08) | 0.54 | 26.56 | 311.82 | 130/500 | 0/500 |
| GABARAP | −12.72 (−35.86) | 0.94 | 16.26 | 194.09 | 2/500 | 1/500 |

Physics criteria are ddG < −30 REU, SAP < 35 and CMS > 300 Å². The PD-L1 best value of −124.08 REU is reproducible across seeds but implausible for a 12-residue macrocycle and is accompanied by an unremarkable contact surface; it is treated as a minimisation artifact and excluded from interpretation.

Across all four targets the physics and structural filters are close to orthogonal: ddG correlates with contact molecular surface as expected (r = −0.25 to −0.77) but only weakly with AlphaFold interface confidence (r = +0.05 to +0.09). Targets that bury substantial surface need not yield confident predicted complexes, and the two criteria are therefore not redundant. PD-L1 illustrates this directly, producing the most physics-passing designs of any target (130/500) while yielding none that also satisfy the structural thresholds. Only two designs in the entire 2,000-design panel satisfy both sets of criteria, one against MDM2 and one against GABARAP, and both lie within approximately one to two replicate standard deviations of the ddG threshold, so both should be regarded as marginal.

![RFpeptides multi-target benchmark](results/figures/rfpeptides_benchmark_figure.png)

**Figure 3.** RFpeptides multi-target evaluation (2,000 designs; 500 per target). (**a**-**f**) Distribution of recomputed PyRosetta ddG, recomputed SAP, recomputed CMS, re-predicted interface PAE, re-predicted pLDDT and the five-term Stage-5 composite score across the 500 designs of each arm, shown as violin, interquartile bar and per-design jitter, with the open marker and the printed value giving the median. Designs falling outside the plotted range are not drawn; 19 designs lie outside the ddG axis and one outside the CMS axis, the former including PD-L1's extreme value of −124.08 REU, which is reproducible across seeds but implausible for a 12-residue macrocycle and is treated as a minimisation artifact. Medians and interquartile bars are computed over the whole arm, including the designs outside the plotted range. (**g**) Designs clearing both the physics and the structural criteria as the interface PAE cut-off is swept from 0.70 toward the gate at 0.20, with the physics criteria held fixed; solid lines are measured, dashed lines are log-linear extrapolations of the measured tail, and the legend gives the sampling depth each arm implies for 10 jointly passing designs (5,000 for GABARAP and MDM2, ~9,607 for MCL1, ~138,589 for PD-L1). Asterisks mark the two arms whose Rosetta and AlphaFold stages did not see the same target, so that their joint curve combines metrics from two different complexes. (**h**) Highest-composite design of each target on the recomputed metrics, with the criteria it actually clears.

Interface PAE is the binding constraint in every arm: measured as the median distance to the gate in units of the arm's own standard deviation, it is the furthest-away metric for all four targets (GABARAP 4.92, MDM2 1.88, MCL1 4.99, PD-L1 5.40), with pLDDT second and SAP already satisfied. This supersedes an earlier reading of these data in which each target appeared to be blocked by a different metric.

Two limitations bound the interpretation of this benchmark. The workflows were not run on a shared target panel, so Table 1 compares workflow–target arms and does not license a direct ranking of one protocol against another. Second, the interface energetics reported here supersede an earlier set of Stage-4 values that were produced by a silent fallback to a synthetic metric generator after PyRosetta failed to load on the compute nodes; because that stage returned a success code, the substitution was not surfaced at run time. The affected values influenced only Stage-4 filtering and the downstream composite ranking, and all designs have since been recomputed. Stages 1 to 3 were unaffected and were carried through unchanged. The episode motivated three corrections to the interface-metrics tool that are reflected in the values above: the fallback now aborts rather than emitting synthetic data, the contact-surface filter now follows the declared peptide chain rather than assuming the peptide is the first chain in the file, and the random seed is fixed and replicate variance reported.

## Software availability

CycPepMCP is implemented in Python (>= 3.10) and distributed under the MIT License. Core dependencies include Click (>= 8.0) for CLI interfaces, PyYAML (>= 6.0) for configuration management, FastMCP (>= 2.0) for MCP server implementation, and requests (>= 2.28) for HTTP operations. Docker images for GPU-accelerated MCP servers are hosted on the GitHub Container Registry (ghcr.io/macronex/*). The source code, installation instructions, workflow skill definitions, example datasets, and visualization scripts are available at https://github.com/macronex/CycPepMCP.
