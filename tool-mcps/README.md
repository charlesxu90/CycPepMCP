# CycPepMCP Tool MCPs

This directory contains all MCP (Model Context Protocol) servers available in CycPepMCP. Each MCP wraps a scientific software package as a FastMCP server for use with Claude Code, Gemini CLI, or any MCP-compatible client.

## Quick Reference

| # | MCP | Description | Runtime | GPU |
|---|-----|-------------|---------|-----|
| 1 | [afcycdesign_mcp](#afcycdesign_mcp) | AlphaFold-based cyclic peptide design (structure prediction, hallucination, binder design) | Docker | Yes |
| 2 | [alphafold3_mcp](#alphafold3_mcp) | AlphaFold3 biomolecular structure prediction | Docker | Yes |
| 3 | [amber_mcp](#amber_mcp) | Amber MD simulations and free energy calculations | Docker | Yes |
| 4 | [adcp_mcp](#adcp_mcp) | AutoDock CrankPep conformational sampling and analysis | Conda | No |
| 5 | [boltz_mcp](#boltz_mcp) | Boltz2 protein structure and affinity prediction | Docker | Yes |
| 6 | [boltzgen_mcp](#boltzgen_mcp) | BoltzGen protein binder design | Docker | Yes |
| 7 | [cpmp_mcp](#cpmp_mcp) | Cyclic peptide membrane permeability prediction (MAT deep learning) | Docker | Yes |
| 8 | [cyc_builder_mcp](#cyc_builder_mcp) | Structure-based cyclic peptide design with MCTS and fragment assembly | Conda | No |
| 9 | [cyclicchamp_mcp](#cyclicchamp_mcp) | Heuristic energy-based cyclic peptide design | UV | No |
| 10 | [cyclicpeptide_mcp](#cyclicpeptide_mcp) | Cyclic peptide drug design and virtual screening toolkit | Conda | No |
| 11 | [cycpeptmp_mcp](#cycpeptmp_mcp) | Multi-level feature membrane permeability prediction with data augmentation | Conda | No |
| 12 | [gromacs_mcp](#gromacs_mcp) | GROMACS molecular dynamics simulations | Docker | Yes |
| 13 | [haddock3_mcp](#haddock3_mcp) | HADDOCK3 integrative modeling for biomolecular docking | UV | No |
| 14 | [helm_gpt_mcp](#helm_gpt_mcp) | GPT-based de novo macrocyclic peptide design with HELM support | Docker | Yes |
| 15 | [highfold3_mcp](#highfold3_mcp) | AlphaFold3-based prediction with CycPOEM and Cyclization Switch | Docker | Yes |
| 16 | [highfold_med_mcp](#highfold_med_mcp) | Fine-tuned AlphaFold for cyclic peptide structure prediction | Docker | Yes |
| 17 | [highplay_mcp](#highplay_mcp) | RL-based cyclic peptide sequence design using MCTS | UV | No |
| 18 | [ligandmpnn_mcp](#ligandmpnn_mcp) | LigandMPNN for structure-aware sequence design | Docker | Yes |
| 19 | [multicycgt_mcp](#multicycgt_mcp) | GCN+Transformer multimodal membrane permeability prediction | UV | No |
| 20 | [multicycpermea_mcp](#multicycpermea_mcp) | Multimodal membrane permeability prediction (images + SMILES) | UV | No |
| 21 | [pepflow_mcp](#pepflow_mcp) | PEPFlow optimization analysis workflow | UV | No |
| 22 | [pepflowww_mcp](#pepflowww_mcp) | Full-atom peptide design using multi-modal flow matching (ICML 2024) | Conda | No |
| 23 | [pharmpapp_mcp](#pharmpapp_mcp) | Peptide permeability prediction across Caco-2, RRCK, and PAMPA | UV | No |
| 24 | [proteinmpnn_mcp](#proteinmpnn_mcp) | ProteinMPNN inverse folding for protein/peptide sequence design | Docker | Yes |
| 25 | [rfpeptides_mcp](#rfpeptides_mcp) | RFDiffusion All-Atom for cyclic peptide backbone generation | Docker | Yes |
| 26 | [rosetta_kic_mcp](#rosetta_kic_mcp) | Rosetta KIC/GeneralizedKIC for cyclic peptide modeling | Docker | Yes |

**Runtime types:** Docker (GPU containerized), Conda (local conda env), UV (lightweight uv venv)

---

## MCPs by Category

### Structure Prediction

| MCP | Method | Input | Output |
|-----|--------|-------|--------|
| afcycdesign_mcp | AlphaFold + ColabDesign | Sequence | 3D structure, pLDDT, iPAE |
| alphafold3_mcp | AlphaFold3 | Sequence / complex | 3D structure |
| boltz_mcp | Boltz2 | Sequence | Structure, affinity |
| highfold3_mcp | AlphaFold3 + CycPOEM | Cyclic peptide sequence | 3D structure with cyclization |
| highfold_med_mcp | Fine-tuned AlphaFold | Cyclic peptide sequence | 3D structure |

### Backbone & Binder Design

| MCP | Method | Input | Output |
|-----|--------|-------|--------|
| rfpeptides_mcp | RFDiffusion All-Atom | Target PDB + hotspots | Cyclic peptide backbones |
| afcycdesign_mcp | ColabDesign hallucination/binder | Length or target PDB | Backbone + sequence |
| boltzgen_mcp | BoltzGen | Target protein | Binder designs |
| cyc_builder_mcp | MCTS + fragment assembly | Target structure | Cyclic peptide structures |

### Sequence Design (Inverse Folding)

| MCP | Method | Input | Output |
|-----|--------|-------|--------|
| proteinmpnn_mcp | ProteinMPNN | Backbone PDB | Designed sequences |
| ligandmpnn_mcp | LigandMPNN | Backbone PDB + ligand | Context-aware sequences |
| helm_gpt_mcp | GPT generative model | HELM notation / constraints | Novel macrocyclic sequences |
| highplay_mcp | RL + MCTS | Design objectives | Optimized sequences |
| cyclicchamp_mcp | Heuristic energy | Design constraints | Cyclic peptide sequences |

### Molecular Dynamics & Modeling

| MCP | Method | Input | Output |
|-----|--------|-------|--------|
| amber_mcp | Amber | PDB + parameters | MD trajectories, free energy |
| gromacs_mcp | GROMACS | PDB + topology | MD trajectories |
| rosetta_kic_mcp | Rosetta KIC/GenKIC | PDB | Relaxed structures, ddG, interface metrics |
| haddock3_mcp | HADDOCK3 | PDB + restraints | Docked complexes |
| adcp_mcp | AutoDock CrankPep | Peptide + receptor | Docked conformations |

### Permeability & Properties

| MCP | Method | Input | Output |
|-----|--------|-------|--------|
| cpmp_mcp | MAT deep learning | SMILES | Permeability score |
| cycpeptmp_mcp | Multi-level features + augmentation | SMILES / sequence | Permeability prediction |
| multicycgt_mcp | GCN + Transformer | SMILES + graph | Permeability prediction |
| multicycpermea_mcp | Multimodal (image + SMILES) | SMILES | Permeability prediction |
| pharmpapp_mcp | Ensemble models | SMILES | Caco-2, RRCK, PAMPA permeability |
| cyclicpeptide_mcp | Cheminformatics toolkit | SMILES / sequence | Properties, virtual screening |

### Generative Design

| MCP | Method | Input | Output |
|-----|--------|-------|--------|
| pepflowww_mcp | Multi-modal flow matching | Constraints | Full-atom peptide structures |
| pepflow_mcp | PEPFlow | Optimization objectives | Performance analysis |

---

## Installation

### Install a single MCP

```bash
cpmcp install <mcp_name>
```

### Install with specific options

```bash
# Skip environment setup (use existing)
cpmcp install <mcp_name> --skip-env

# Install without registering with Claude Code
cpmcp install <mcp_name> --no-register
```

### Manual setup

```bash
cd tool-mcps/<mcp_name>
bash quick_setup.sh
```

### Docker-based MCPs

Docker MCPs pull pre-built images from `ghcr.io/macronex/` and require:
- Docker with GPU support (`nvidia-container-toolkit`)
- Sufficient GPU memory (varies by tool)

---

## MCP Details

### afcycdesign_mcp
**AlphaFold-based cyclic peptide design** | Docker (GPU)

Wraps ColabDesign for cyclic peptide structure prediction, de novo hallucination, fixed-backbone sequence design, and binder design against target proteins. Uses AlphaFold with cyclic offset constraints.

Source: [macronex/afcycdesign_mcp](https://github.com/macronex/afcycdesign_mcp)

### alphafold3_mcp
**AlphaFold3 biomolecular structure prediction** | Docker (GPU)

Full AlphaFold3 for predicting structures of proteins, nucleic acids, small molecules, ions, and their complexes.

Source: [macronex/alphafold3_mcp](https://github.com/macronex/alphafold3_mcp)

### amber_mcp
**Amber molecular dynamics** | Docker (GPU)

Amber force field simulations including MD, free energy perturbation, and thermodynamic integration for cyclic peptide systems.

Source: [macronex/amber_mcp](https://github.com/macronex/amber_mcp)

### adcp_mcp
**AutoDock CrankPep** | Conda

Conformational sampling and docking of cyclic peptides to protein targets using AutoDock CrankPep.

### boltz_mcp
**Boltz2 structure and affinity prediction** | Docker (GPU)

Boltz2 for protein structure prediction and binding affinity estimation.

Source: [macronex/boltz_mcp](https://github.com/macronex/boltz_mcp)

### boltzgen_mcp
**BoltzGen binder design** | Docker (GPU)

Generative model for designing protein binders using Boltzmann-inspired generation.

Source: [macronex/boltzgen_mcp](https://github.com/macronex/boltzgen_mcp)

### cpmp_mcp
**Cyclic peptide membrane permeability (MAT)** | Docker (GPU)

Deep learning model using Molecular Attention Transformer for predicting membrane permeability of cyclic peptides.

Source: [macronex/cpmp_mcp](https://github.com/macronex/cpmp_mcp)

### cyc_builder_mcp
**CYC_BUILDER structure-based design** | Conda

Monte Carlo Tree Search with fragment assembly for structure-based cyclic peptide design.

Source: [wfh1998/CYC_BUILDER_v1.0](https://github.com/wfh1998/CYC_BUILDER_v1.0)

### cyclicchamp_mcp
**CyclicChamp heuristic design** | UV

Energy-based heuristic approach for cyclic peptide design.

Source: [qiyaozhu/CyclicPeptide](https://github.com/qiyaozhu/CyclicPeptide)

### cyclicpeptide_mcp
**Cyclic peptide cheminformatics toolkit** | Conda

Python package for cyclic peptide drug design, property calculation, and virtual screening.

Source: [dfwlab/cyclicpeptide](https://github.com/dfwlab/cyclicpeptide)

### cycpeptmp_mcp
**CycPeptMP permeability prediction** | Conda

Multi-level feature extraction with data augmentation for membrane permeability prediction.

Source: [akiyamalab/cycpeptmp](https://github.com/akiyamalab/cycpeptmp)

### gromacs_mcp
**GROMACS molecular dynamics** | Docker (GPU)

GROMACS for molecular dynamics simulations of peptide systems.

Source: [macronex/gromacs_mcp](https://github.com/macronex/gromacs_mcp)

### haddock3_mcp
**HADDOCK3 biomolecular docking** | UV

Integrative modeling platform for docking biomolecules using experimental data and computational predictions.

Source: [macronex/haddock3_mcp](https://github.com/macronex/haddock3_mcp)

### helm_gpt_mcp
**HELM-GPT macrocyclic peptide design** | Docker (GPU)

GPT-based generative model for de novo design of macrocyclic peptides using HELM notation. Supports prior model training, sequence optimization, and scoring.

Source: [macronex/helm_gpt_mcp](https://github.com/macronex/helm_gpt_mcp)

### highfold3_mcp
**HighFold3 with CycPOEM** | Docker (GPU)

AlphaFold3-based structure prediction enhanced with CycPOEM (Cyclic Peptide Offset Embedding Module) and Cyclization Switch for improved cyclic peptide modeling.

Source: [macronex/highfold3_mcp](https://github.com/macronex/highfold3_mcp)

### highfold_med_mcp
**HighFold-Med fine-tuned AlphaFold** | Docker (GPU)

AlphaFold model fine-tuned specifically for cyclic peptide structure prediction with improved accuracy.

Source: [macronex/highfold_med_mcp](https://github.com/macronex/highfold_med_mcp)

### highplay_mcp
**HighPlay RL sequence design** | UV

Reinforcement learning with Monte Carlo Tree Search for cyclic peptide sequence design and optimization.

Source: [hongliangduan/HighPlay](https://github.com/hongliangduan/HighPlay)

### ligandmpnn_mcp
**LigandMPNN sequence design** | Docker (GPU)

LigandMPNN for structure-aware protein sequence design, accounting for ligand and small molecule context.

Source: [macronex/ligandmpnn_mcp](https://github.com/macronex/ligandmpnn_mcp)

### multicycgt_mcp
**Multi_CycGT permeability prediction** | UV

GCN + Transformer multimodal model combining graph and sequence features for membrane permeability prediction.

Source: [hongliangduan/Multi_CycGT](https://github.com/hongliangduan/Multi_CycGT)

### multicycpermea_mcp
**MultiCycPermea permeability prediction** | UV

Multimodal approach using molecular images and SMILES strings for membrane permeability prediction.

Source: [viko-3/MultiCycPermea](https://github.com/viko-3/MultiCycPermea)

### pepflow_mcp
**PEPFlow optimization** | UV

Performance Estimation Problem workflow for peptide optimization analysis.

Source: [pepflow-lib/PEPFlow](https://github.com/pepflow-lib/PEPFlow)

### pepflowww_mcp
**PepFlowww full-atom design** | Conda

Full-atom peptide structure and sequence co-design using multi-modal flow matching (ICML 2024).

Source: [Ced3-han/PepFlowww](https://github.com/Ced3-han/PepFlowww)

### pharmpapp_mcp
**PharmPapp permeability prediction** | UV

Peptide apparent permeability prediction across multiple assays: Caco-2, RRCK, and PAMPA.

Source: [ifyoungnet/PharmPapp](https://github.com/ifyoungnet/PharmPapp)

### proteinmpnn_mcp
**ProteinMPNN inverse folding** | Docker (GPU)

ProteinMPNN for protein and peptide sequence design from backbone structures. Supports simple design, constrained design, CA-only design, sequence scoring, and batch processing.

Source: [macronex/proteinmpnn_mcp](https://github.com/macronex/proteinmpnn_mcp)

### rfpeptides_mcp
**RFpeptides backbone generation** | Docker (GPU)

RFDiffusion All-Atom adapted for cyclic peptide backbone generation against protein targets. Core tool in the binder design workflow.

Source: [macronex/rfpeptides_mcp](https://github.com/macronex/rfpeptides_mcp)

### rosetta_kic_mcp
**Rosetta KIC/GenKIC modeling** | Docker (GPU)

Rosetta Kinematic Closure and GeneralizedKIC protocols for cyclic peptide loop modeling, relaxation, and interface energy analysis (ddG, SAP, CMS).

Source: [macronex/rosetta_kic_mcp](https://github.com/macronex/rosetta_kic_mcp)

---

## Runtime Summary

| Runtime | Count | Description |
|---------|-------|-------------|
| Docker | 14 | GPU-accelerated, containerized with pre-built images |
| UV | 7 | Lightweight, pip-only dependencies via uv |
| Conda | 5 | Local conda/mamba environment with compiled dependencies |

## See Also

- [CycPepMCP main README](../README.md) for project overview, CLI usage, and workflow skills
- [Workflow skills](../workflow-skills/) for multi-MCP orchestration protocols
- `cpmcp avail` to list all available MCPs from the command line
- `cpmcp status` to check which MCPs are currently installed
