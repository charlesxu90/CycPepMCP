#!/bin/bash
# CycPepMCP - Batch MCP Creation Script
# Run with: python run_commands.py
# This script contains cpmcp create commands for cyclic peptide tools
#
# Priority: P0 = High priority, P1 = Medium priority, (no priority) = Lower priority
# Tools are organized by category

# ==============================================================================
# STRUCTURE PREDICTION / GENERATION - P0
# ==============================================================================

# AfCycDesign - AlphaFold2-based framework for cyclic peptide structure prediction and sequence redesign
# cpmcp create --github-url https://github.com/sokrypton/ColabDesign --mcp-dir tool-mcps/afcycdesign_mcp --use-case-filter 'cyclic peptide structure prediction using AfCycDesign, head-to-tail cyclization, sequence redesign for cyclic peptides'

# CyclicBoltz1 - Adaptation of Boltz1 for fast cyclic peptide structure prediction including ncAAs
# cpmcp create --github-url https://github.com/jwohlwend/boltz --mcp-dir tool-mcps/cyclicboltz1_mcp --use-case-filter 'cyclic peptide structure prediction using CyclicBoltz1, non-canonical amino acid support, cyclic peptide monomer and multimer prediction'

# HighFold-MeD - Rosetta distillation model for N-methylation and D-amino acids
# cpmcp create --github-url https://github.com/hongliangduan/HighFold-MeD --mcp-dir tool-mcps/highfold_med_mcp --use-case-filter 'cyclic peptide structure prediction with N-methylation and D-amino acids using HighFold-MeD'

# HighFold3 - Enhanced AlphaFold 3 with Cyclization Switch for unnatural amino acids
# cpmcp create --github-url https://github.com/hongliangduan/HighFold3 --mcp-dir tool-mcps/highfold3_mcp --use-case-filter 'cyclic peptide 3D structure prediction with unnatural amino acids using HighFold3 Cyclization Switch'

# RFpeptides - Diffusion-based cyclic peptide backbone generation for protein binding pockets
# cpmcp create --github-url https://github.com/baker-laboratory/rf_diffusion_all_atom --mcp-dir tool-mcps/rfpeptides_mcp --use-case-filter 'cyclic peptide backbone generation conditioned on protein binding pockets using RFdiffusion, peptide-specific constraints'

# ==============================================================================
# UTILITY TOOLS - P0
# ==============================================================================

# cyclicpeptide - Python toolkit for cyclic peptide preprocessing and analysis
cpmcp create --github-url https://github.com/dfwlab/cyclicpeptide --mcp-dir tool-mcps/cyclicpeptide_mcp --use-case-filter 'Structure2Sequence, Sequence2Structure, GraphAlignment, PropertyAnalysis for cyclic peptides, preprocessing and standardization'

# ==============================================================================
# PERMEABILITY PREDICTION - P0
# ==============================================================================

# CycPeptMP - Multi-level feature fusion for cyclic peptide permeability prediction
cpmcp create --github-url https://github.com/akiyamalab/cycpeptmp --mcp-dir tool-mcps/cycpeptmp_mcp --use-case-filter 'cyclic peptide membrane permeability prediction using deep learning, atom-level and monomer-level features'

# ==============================================================================
# SEQUENCE DESIGN - P0
# ==============================================================================

# HELM-GPT - GPT-style generative model for macrocyclic peptide design
cpmcp create --github-url https://github.com/charlesxu90/helm-gpt --mcp-dir tool-mcps/helm_gpt_mcp --use-case-filter 'macrocyclic peptide design using HELM-GPT, HELM notation generation, peptide optimization'

# ==============================================================================
# DOCKING / BINDING PREDICTION - P0
# ==============================================================================

# AutoDock CrankPep (ADCP) - Automated cyclic peptide docking
cpmcp create --github-url https://github.com/ccsb-scripps/AutoDock-CrankPep --mcp-dir tool-mcps/adcp_mcp --use-case-filter 'automated cyclic peptide docking using AutoDock CrankPep, conformer generation, flexible backbone handling'

# HADDOCK3 - Information-driven docking for cyclic peptides
cpmcp create --github-url https://github.com/haddocking/haddock3 --mcp-dir tool-mcps/haddock3_mcp --use-case-filter 'cyclic peptide docking using HADDOCK, information-driven docking protocol, protein-peptide interactions'

# ==============================================================================
# CLASSICAL MODELING - P0
# ==============================================================================

# Rosetta KIC/GenKIC - Backbone sampling and cyclic peptide closure
cpmcp create --github-url https://github.com/RosettaCommons/rosetta --mcp-dir tool-mcps/rosetta_kic_mcp --use-case-filter 'cyclic peptide closure using KIC and GenKIC protocols, backbone sampling, physics-based scoring for cyclic peptides'

# ==============================================================================
# PERMEABILITY PREDICTION - P1
# ==============================================================================

# CPMP - Molecular Attention Transformer for membrane permeability
cpmcp create --github-url https://github.com/panda1103/CPMP --mcp-dir tool-mcps/cpmp_mcp --use-case-filter 'cyclic peptide membrane permeability prediction using MAT, PAMPA Caco-2 RRCK MDCK assays'

# ==============================================================================
# SEQUENCE DESIGN - P1
# ==============================================================================

# HighPlay - Reinforcement learning with HighFold for cyclic peptide design
cpmcp create --github-url https://github.com/hongliangduan/HighPlay --mcp-dir tool-mcps/highplay_mcp --use-case-filter 'cyclic peptide sequence design using HighPlay MCTS reinforcement learning, target protein binding'

# ==============================================================================
# STRUCTURE PREDICTION - ADDITIONAL
# ==============================================================================

# CYC_BUILDER - Reinforcement learning for fragment assembly and cyclization
cpmcp create --github-url https://github.com/wfh1998/CYC_BUILDER_v1.0 --mcp-dir tool-mcps/cyc_builder_mcp --use-case-filter 'cyclic peptide design using CYC_BUILDER Monte Carlo Tree Search, fragment assembly, target-specific binders'

# CyclicChamp - Heuristic energy-based pipeline for cyclic peptide backbone sampling
cpmcp create --github-url https://github.com/qiyaozhu/CyclicPeptide --mcp-dir tool-mcps/cyclicchamp_mcp --use-case-filter 'cyclic peptide backbone sampling using CyclicChamp simulated annealing, large rings up to 24 residues, mixed chirality'

# HighFold2 - AlphaFold-Multimer based cyclic peptide prediction
cpmcp create --github-url https://github.com/hongliangduan/HighFold2 --mcp-dir tool-mcps/highfold2_mcp --use-case-filter 'cyclic peptide structure prediction using HighFold2 AlphaFold-Multimer'

# HighFold - AlphaFold-style prediction for cyclic peptides with disulfide bridges
cpmcp create --github-url https://github.com/hongliangduan/HighFold --mcp-dir tool-mcps/highfold_mcp --use-case-filter 'cyclic peptide structure prediction with head-to-tail cyclization and disulfide bridges using HighFold'

# PepFlow - Hypernetwork-conditioned diffusion for peptide conformational sampling
cpmcp create --github-url https://github.com/pepflow-lib/PEPFlow --mcp-dir tool-mcps/pepflow_mcp --use-case-filter 'peptide conformational sampling using PepFlow diffusion, cyclization constraints, ensemble generation'

# PepFlowww - Peptide flow model
cpmcp create --github-url https://github.com/Ced3-han/PepFlowww --mcp-dir tool-mcps/pepflowww_mcp --use-case-filter 'peptide structure generation using PepFlowww'

# ==============================================================================
# PERMEABILITY PREDICTION - ADDITIONAL
# ==============================================================================

# MultiCycPermea - Multimodal deep learning for cyclic peptide permeability
cpmcp create --github-url https://github.com/viko-3/MultiCycPermea --mcp-dir tool-mcps/multicycpermea_mcp --use-case-filter 'cyclic peptide membrane permeability prediction using MultiCycPermea, 2D image and 1D sequence features'

# MultiCycGT - GCN and transformer for cyclic peptide permeability
cpmcp create --github-url https://github.com/hongliangduan/Multi_CycGT --mcp-dir tool-mcps/multicycgt_mcp --use-case-filter 'cyclic peptide membrane permeability prediction using MultiCycGT GCN transformer'

# PharmPapp - Graph Convolutional Networks for permeability
cpmcp create --github-url https://github.com/ifyoungnet/PharmPapp --mcp-dir tool-mcps/pharmpapp_mcp --use-case-filter 'cyclic peptide permeability prediction using PharmPapp GCN'

# ==============================================================================
# DATASETS (for reference, may need manual integration)
# ==============================================================================

# MacroConf - Experimental conformational ensemble dataset
# cpmcp create --github-url https://github.com/bigginlab/macroconf --mcp-dir tool-mcps/macroconf_mcp --use-case-filter 'cyclic peptide conformational ensemble data loading and analysis from MacroConf dataset'

# CPSea dataset - Large-scale cyclic peptide-protein complex dataset
# cpmcp create --github-url https://github.com/YZY010418/CPSea --mcp-dir tool-mcps/cpsea_mcp --use-case-filter 'cyclic peptide-protein complex dataset loading from CPSea, structure fidelity metrics'

# ==============================================================================
# NOT YET RELEASED (commented for future use)
# ==============================================================================

# CpSDE - Harmonic SDE-based generative model (Not released)
# NS-Pep - Non-standard amino acid peptide framework (Not released)
# PepEVOLVE - Position-aware evolutionary optimization (Not released)
# PepThink-R1 - LLM reasoning with RL for cyclic peptide optimization (Not released)
