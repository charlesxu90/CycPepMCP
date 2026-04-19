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

## Software availability

CycPepMCP is implemented in Python (>= 3.10) and distributed under the MIT License. Core dependencies include Click (>= 8.0) for CLI interfaces, PyYAML (>= 6.0) for configuration management, FastMCP (>= 2.0) for MCP server implementation, and requests (>= 2.28) for HTTP operations. Docker images for GPU-accelerated MCP servers are hosted on the GitHub Container Registry (ghcr.io/macronex/*). The source code, installation instructions, workflow skill definitions, example datasets, and visualization scripts are available at https://github.com/macronex/CycPepMCP.
