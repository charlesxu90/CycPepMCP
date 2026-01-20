# De Novo Cyclic Peptide Binder Design Workflow for MCL1

Design cyclic peptide binders targeting MCL1 (PDB: 5KU9) through an 8-step computational workflow using multiple MCP servers.

---

## Prerequisites

Before running this workflow, install the skill and all required MCPs:

```bash
cpskill install mcl1_cycpep_design
```

This will install the following MCP servers:
- `rf_diffusion_all_atom_mcp` - RFDiffusion All-Atom for backbone generation
- `CYC_BUILDER_v1.0_mcp` - Structure-based cyclic peptide design
- `ligandmpnn_mcp` - LigandMPNN for sequence design
- `HighPlay_mcp` - RL-based cyclic peptide sequence design
- `boltz_mcp` - Biomolecular structure prediction (Boltz-1/2)
- `HighFold3_mcp` - AlphaFold3-based structure prediction
- `haddock3_mcp` - HADDOCK3 integrative docking
- `CPMP_mcp` - Cyclic peptide membrane permeability prediction
- `MultiCycPermea_mcp` - Multimodal permeability prediction
- `gromacs_mcp` - GROMACS molecular dynamics simulations
- `amber_mcp` - Amber MD simulations and free energy calculations

**Verify MCPs are installed:**
```bash
cpmcp status
```

---

## Configuration Parameters

```yaml
# Target Information (MCL1)
TARGET:
  pdb_id: "5KU9"
  pdb_file: "examples/case1_cycpep_design_MCL1/mcl1_5ku9.pdb"
  chain: "A"
  binding_pocket_residues: [224, 227, 228, 231, 234, 248, 249, 250, 252, 253, 255, 256, 263, 266, 267, 270]
  binding_site_center: [30.5, 45.2, 55.8]  # Angstrom
  binding_site_radius: 15.0  # Angstrom

# Design Parameters
DESIGN:
  peptide_length_min: 8        # residues
  peptide_length_max: 16       # residues
  cyclization_type: "head_to_tail"
  num_backbones: 20
  sequences_per_backbone: 5
  predictions_per_sequence: 3

# Output Settings
RESULTS_DIR: "@results/mcl1_cycpep_design"

# Selection Criteria
SELECTION:
  binding_affinity_threshold: -8.0   # kcal/mol
  permeability_threshold: 1e-6       # cm/s
  stability_rmsd_threshold: 2.0      # Angstrom
  top_candidates: 5

# MD Simulation Parameters
MD_SIMULATION:
  time_ns: 100
  temperature_K: 298.15
  pressure_atm: 1.0
  force_field: "AMBER99SB"
  water_model: "TIP3P"
```

**Binding Pocket Residues:**
HIS224, ALA227, PHE228, MET231, LYS234, ARG248, VAL249, MET250, HIS252, VAL253, SER255, ASP256, ARG263, THR266, LEU267, PHE270

**Directory Structure:**
```
RESULTS_DIR/
├── step1_target/                    # Target preparation outputs
│   ├── mcl1_prepared.pdb
│   └── binding_pocket_info.json
├── step2_backbones/                 # Generated backbone structures
│   ├── backbone_001.pdb
│   └── ...
├── step3_sequences/                 # Designed sequences
│   ├── designed_sequences.fasta
│   └── sequence_design_scores.csv
├── step4_structures/                # Predicted structures
│   ├── structure_001.pdb
│   └── structure_confidence.csv
├── step5_docking/                   # Docking results
│   ├── docked_poses/
│   └── binding_affinity_predictions.csv
├── step6_permeability/              # Permeability predictions
│   └── permeability_predictions.csv
├── step7_md_simulation/             # MD simulation results
│   ├── trajectories/
│   └── binding_free_energy_results.csv
└── step8_final/                     # Final candidates
    ├── final_candidates.pdb
    └── final_report.md
```

---

## Step 1: Target Preparation

**Purpose:** Prepare the MCL1 target structure and define the binding pocket for cyclic peptide design.

**Input:** MCL1 structure (PDB: 5KU9)
**Output:** Prepared target structure + binding pocket information

**Prompt:**
> Can you prepare the MCL1 target from examples/case1_cycpep_design_MCL1/mcl1_5ku9.pdb? Extract chain A, identify the binding pocket residues (224, 227, 228, 231, 234, 248, 249, 250, 252, 253, 255, 256, 263, 266, 267, 270), and save the prepared structure and binding pocket info to {RESULTS_DIR}/step1_target/.

**Implementation Notes:**
- Load the PDB structure (5KU9)
- Extract chain A (MCL1 protein)
- Identify binding pocket residues within 5 Angstrom of the reference ligand
- Calculate binding site center coordinates
- Save prepared structure and binding pocket information

**Reference Files:**
- `examples/case1_cycpep_design_MCL1/mcl1_5ku9.pdb` - Original structure
- `examples/case1_cycpep_design_MCL1/mcl1_target_chainA.pdb` - Pre-extracted chain A
- `examples/case1_cycpep_design_MCL1/mcl1_binding_pocket.txt` - Binding pocket info
- `examples/case1_cycpep_design_MCL1/step1_target_preparation_config.json` - Configuration

**Expected Output:**
- `{RESULTS_DIR}/step1_target/mcl1_prepared.pdb` - Prepared target structure
- `{RESULTS_DIR}/step1_target/binding_pocket_info.json` - Binding pocket residues and center

---

## Step 2: Backbone Generation

**Purpose:** Generate diverse cyclic peptide backbones targeting the MCL1 binding pocket.

**MCP Tools:**
- Primary: `rf_diffusion_all_atom_mcp` (RFDiffusion All-Atom)
- Alternative: `CYC_BUILDER_v1.0_mcp` (MCTS-based)

**Prompt:**
> Using rf_diffusion_all_atom_mcp, generate 20 diverse cyclic peptide backbones for MCL1 binding. Use head-to-tail cyclization with peptide lengths between 8-16 residues. Target the binding pocket centered at [30.5, 45.2, 55.8] with radius 15 Angstrom. Save the backbone structures to {RESULTS_DIR}/step2_backbones/.

**Implementation Notes:**
- Use `mcp__rf_diffusion_all_atom_mcp__generate_cyclic_backbone` tool
- Parameters:
  - `target_pdb`: Path to prepared MCL1 structure
  - `hotspot_residues`: [224, 227, 228, 231, 234, 248, 249, 250, 252, 253, 255, 256, 263, 266, 267, 270]
  - `peptide_length_range`: [8, 16]
  - `cyclization_type`: "head_to_tail"
  - `num_designs`: 20
  - `diversity_sampling`: true
- Alternative: Use `mcp__CYC_BUILDER_v1.0_mcp__build_cyclic_peptide` for MCTS-based generation

**Reference Files:**
- `examples/case1_cycpep_design_MCL1/step2_backbone_generation_config.json` - Configuration

**Expected Output:**
- 20 PDB files: `{RESULTS_DIR}/step2_backbones/backbone_001.pdb` to `backbone_020.pdb`
- `{RESULTS_DIR}/step2_backbones/backbone_summary.json` - Summary of generated backbones

---

## Step 3: Sequence Design

**Purpose:** Design amino acid sequences for each generated backbone optimized for MCL1 binding.

**MCP Tools:**
- Primary: `ligandmpnn_mcp` (LigandMPNN)
- Alternative: `HighPlay_mcp` (RL-based MCTS)

**Prompt:**
> Using ligandmpnn_mcp, design 5 sequences for each of the 20 backbone structures. Focus on interface residues that interact with MCL1. Save the designed sequences to {RESULTS_DIR}/step3_sequences/designed_sequences.fasta and scores to {RESULTS_DIR}/step3_sequences/sequence_design_scores.csv.

**Implementation Notes:**
- Use `mcp__ligandmpnn_mcp__design_sequence` tool
- Parameters:
  - `backbone_pdb`: Path to each backbone structure
  - `target_pdb`: Path to MCL1 structure
  - `num_sequences`: 5
  - `design_strategy`: "interface_focused"
  - `temperature`: 0.1 (for diversity)
- Process all 20 backbones: 20 backbones x 5 sequences = 100 total sequences
- Calculate design scores (pLDDT, interface energy, etc.)

**Alternative Implementation:**
- Use `mcp__HighPlay_mcp__design_cyclic_sequence` for RL-based optimization
- Parameters:
  - `backbone_pdb`: Path to backbone
  - `target_binding_residues`: MCL1 binding pocket residues
  - `optimization_target`: "binding_affinity"

**Reference Files:**
- `examples/case1_cycpep_design_MCL1/step3_sequence_design_config.json` - Configuration
- `examples/case1_cycpep_design_MCL1/designed_sequences_001-100.fasta` - Example output
- `examples/case1_cycpep_design_MCL1/sequence_design_scores.csv` - Example scores

**Expected Output:**
- `{RESULTS_DIR}/step3_sequences/designed_sequences.fasta` - 100 sequences in FASTA format
- `{RESULTS_DIR}/step3_sequences/sequence_design_scores.csv` - Design scores for each sequence

**FASTA Format:**
```
>SEQ_001|BACKBONE_001|LEN_12
ACDEFGHIKLMN
>SEQ_002|BACKBONE_001|LEN_12
ACDEFGHIKLMP
...
```

---

## Step 4: Structure Prediction

**Purpose:** Predict 3D structures for all designed sequences and filter by confidence.

**MCP Tools:**
- Primary: `boltz_mcp` (Boltz-1/2)
- Alternative: `HighFold3_mcp` (AlphaFold3-based)

**Prompt:**
> Using boltz_mcp, predict 3 structures for each of the 100 designed sequences. Filter structures with confidence score > 0.7. Save predicted structures to {RESULTS_DIR}/step4_structures/ and confidence scores to {RESULTS_DIR}/step4_structures/structure_confidence.csv.

**Implementation Notes:**
- Use `mcp__boltz_mcp__predict_structure` tool
- Parameters:
  - `sequence`: Cyclic peptide sequence
  - `cyclization_type`: "head_to_tail"
  - `num_predictions`: 3
  - `return_confidence`: true
- Process all 100 sequences: 100 sequences x 3 predictions = 300 structures
- Filter by confidence threshold (pLDDT > 0.7 or pTM > 0.7)

**Alternative Implementation:**
- Use `mcp__HighFold3_mcp__predict_cyclic_structure` for AlphaFold3-based prediction
- Includes CycPOEM and Cyclization Switch for improved cyclic peptide prediction

**Reference Files:**
- `examples/case1_cycpep_design_MCL1/step4_structure_prediction_config.json` - Configuration

**Expected Output:**
- Up to 300 PDB files: `{RESULTS_DIR}/step4_structures/structure_001.pdb` to `structure_300.pdb`
- `{RESULTS_DIR}/step4_structures/structure_confidence.csv` - Confidence scores

**Confidence CSV Format:**
```csv
structure_id,sequence_id,backbone_id,pLDDT,pTM,confidence,pass_filter
structure_001,SEQ_001,BACKBONE_001,0.85,0.82,0.835,true
...
```

---

## Step 5: Docking & Binding Analysis

**Purpose:** Dock predicted structures to MCL1 and predict binding affinities.

**MCP Tools:**
- Primary: `haddock3_mcp` (HADDOCK3)
- Alternative: `rosetta_mcp` (Rosetta)

**Prompt:**
> Using haddock3_mcp, dock all structures that passed the confidence filter to MCL1. Use the binding pocket residues as restraints. Calculate binding affinities and select top 50 poses with affinity < -8.0 kcal/mol. Save results to {RESULTS_DIR}/step5_docking/.

**Implementation Notes:**
- Use `mcp__haddock3_mcp__dock_peptide` tool
- Parameters:
  - `receptor_pdb`: Path to MCL1 structure
  - `ligand_pdb`: Path to cyclic peptide structure
  - `active_residues`: MCL1 binding pocket residues
  - `num_poses`: 10
  - `scoring_function`: "haddock_score"
- Process all filtered structures
- Calculate binding affinity using scoring function
- Filter by affinity threshold: < -8.0 kcal/mol
- Select top 50 poses

**Reference Files:**
- `examples/case1_cycpep_design_MCL1/step5_docking_binding_config.json` - Configuration
- `examples/case1_cycpep_design_MCL1/binding_affinity_predictions.csv` - Example output

**Expected Output:**
- `{RESULTS_DIR}/step5_docking/docked_poses/` - Top 50 docked pose PDB files
- `{RESULTS_DIR}/step5_docking/binding_affinity_predictions.csv` - Binding affinity results

**Binding Affinity CSV Format:**
```csv
pose_id,structure_id,sequence,binding_affinity_kcal_mol,haddock_score,vdw_energy,elec_energy,desolv_energy,pass_filter
pose_001,structure_023,ACDEFGHIKLMN,-9.5,-125.3,-45.2,-35.1,-45.0,true
...
```

---

## Step 6: Permeability Analysis

**Purpose:** Predict membrane permeability for candidate cyclic peptides.

**MCP Tools:**
- Primary: `CPMP_mcp` (CPMP)
- Alternative: `MultiCycPermea_mcp` (Multimodal)

**Prompt:**
> Using CPMP_mcp, predict MDCK cell permeability for all top 50 docked candidates. Filter for permeability > 1e-6 cm/s. Save results to {RESULTS_DIR}/step6_permeability/permeability_predictions.csv.

**Implementation Notes:**
- Use `mcp__CPMP_mcp__predict_permeability` tool
- Parameters:
  - `sequence`: Cyclic peptide sequence
  - `cyclization_type`: "head_to_tail"
  - `cell_type`: "MDCK"
- Process all top 50 candidates
- Filter by permeability threshold: > 1e-6 cm/s

**Alternative Implementation:**
- Use `mcp__MultiCycPermea_mcp__predict_permeability` for multimodal prediction
- Uses both structure (images) and sequence (SMILES) for prediction

**Reference Files:**
- `examples/case1_cycpep_design_MCL1/step6_permeability_analysis_config.json` - Configuration
- `examples/case1_cycpep_design_MCL1/permeability_predictions.csv` - Example output

**Expected Output:**
- `{RESULTS_DIR}/step6_permeability/permeability_predictions.csv` - Permeability predictions

**Permeability CSV Format:**
```csv
candidate_id,sequence,permeability_cm_s,logP,PSA,HBD,HBA,MW,rule_of_5,pass_filter
candidate_001,ACDEFGHIKLMN,2.5e-6,-1.2,180.5,4,8,1450.2,true,true
...
```

---

## Step 7: MD Simulation

**Purpose:** Run molecular dynamics simulations to assess conformational stability and calculate binding free energies.

**MCP Tools:**
- Primary: `gromacs_mcp` (GROMACS)
- Alternative: `amber_mcp` (Amber)

**Prompt:**
> Using gromacs_mcp, run 100 ns MD simulations for candidates that passed the permeability filter. Use AMBER99SB force field, TIP3P water model, at 298.15 K and 1 atm. Calculate RMSD stability and binding free energy using MM-PBSA. Filter for RMSD < 2.0 Angstrom. Save results to {RESULTS_DIR}/step7_md_simulation/.

**Implementation Notes:**
- Use `mcp__gromacs_mcp__run_md_simulation` tool
- Parameters:
  - `complex_pdb`: Path to MCL1-peptide complex
  - `force_field`: "AMBER99SB"
  - `water_model`: "TIP3P"
  - `simulation_time_ns`: 100
  - `temperature_K`: 298.15
  - `pressure_atm`: 1.0
- Use `mcp__gromacs_mcp__calculate_binding_energy` for MM-PBSA
- Calculate backbone RMSD over trajectory
- Filter by stability threshold: RMSD < 2.0 Angstrom

**Alternative Implementation:**
- Use `mcp__amber_mcp__run_md_simulation` with Amber force fields
- Use `mcp__amber_mcp__calculate_mmpbsa` for free energy calculation

**Reference Files:**
- `examples/case1_cycpep_design_MCL1/step7_md_simulation_config.json` - Configuration
- `examples/case1_cycpep_design_MCL1/binding_free_energy_results.csv` - Example output

**Expected Output:**
- `{RESULTS_DIR}/step7_md_simulation/trajectories/` - MD trajectory files
- `{RESULTS_DIR}/step7_md_simulation/binding_free_energy_results.csv` - Binding free energies and stability

**Free Energy CSV Format:**
```csv
candidate_id,sequence,binding_dG_kcal_mol,vdw_contribution,elec_contribution,polar_solvation,nonpolar_solvation,avg_rmsd_angstrom,pass_filter
candidate_001,ACDEFGHIKLMN,-12.5,-25.3,-15.2,20.1,-7.9,1.5,true
...
```

---

## Step 8: Final Selection

**Purpose:** Combine all criteria to select top 5 candidates for experimental validation.

**Prompt:**
> Combine all analysis results to select the top 5 cyclic peptide candidates for MCL1 binding. Rank by: binding free energy (primary), permeability, and stability. Generate a final report with candidate structures, predicted properties, and recommendations. Save to {RESULTS_DIR}/step8_final/.

**Implementation Notes:**
- Load all prediction results from previous steps
- Apply multi-criteria selection:
  1. Binding affinity < -8.0 kcal/mol
  2. Permeability > 1e-6 cm/s
  3. Stability RMSD < 2.0 Angstrom
- Rank candidates by binding free energy (most negative first)
- Select top 5 candidates
- Generate visualization and report

**Selection Algorithm:**
```python
# Pseudo-code for final selection
candidates = merge_all_results(docking, permeability, md_results)
filtered = candidates[
    (candidates['binding_dG'] < -8.0) &
    (candidates['permeability'] > 1e-6) &
    (candidates['rmsd'] < 2.0)
]
ranked = filtered.sort_values('binding_dG', ascending=True)
top_5 = ranked.head(5)
```

**Reference Files:**
- `examples/case1_cycpep_design_MCL1/step8_final_selection_config.json` - Configuration

**Expected Output:**
- `{RESULTS_DIR}/step8_final/final_candidates.pdb` - Top 5 candidate structures (multi-model PDB)
- `{RESULTS_DIR}/step8_final/final_report.md` - Detailed report with recommendations

**Final Report Format:**
```markdown
# MCL1 Cyclic Peptide Binder - Final Candidates

## Summary
- Total designs evaluated: 100
- Structures predicted: 300
- Docking poses analyzed: 50
- Candidates passing all filters: [N]
- Final candidates selected: 5

## Top 5 Candidates

### Candidate 1: [SEQUENCE]
- Binding Free Energy: -X.X kcal/mol
- Permeability: X.Xe-6 cm/s
- RMSD Stability: X.X Angstrom
- Recommendations: [...]

[Continue for all 5 candidates]

## Experimental Validation Recommendations
1. Synthesize top 5 candidates
2. Measure binding affinity (ITC/SPR)
3. Assess cell permeability (PAMPA/Caco-2)
4. Evaluate proteolytic stability
```

---

## Troubleshooting

### Common Issues

1. **MCP Connection Errors**
   - Verify MCP is installed: `cpmcp status`
   - Reinstall if needed: `cpmcp install <mcp_name>`
   - Check logs: `cpmcp logs <mcp_name>`

2. **Backbone Generation Fails**
   - Ensure target PDB is properly formatted
   - Check binding pocket coordinates are correct
   - Try alternative MCP (CYC_BUILDER_v1.0_mcp)

3. **Low Confidence Structures**
   - Increase number of predictions per sequence
   - Try alternative structure predictor (HighFold3_mcp)
   - Check sequence for incompatible residue combinations

4. **Poor Binding Affinities**
   - Verify binding pocket residues
   - Adjust docking restraints
   - Consider redesigning with different backbone length

5. **Low Permeability Predictions**
   - Reduce peptide length (8-10 residues optimal)
   - Incorporate N-methylation (use nnaa_mcp)
   - Consider hydrophobic amino acid substitutions

6. **MD Simulation Crashes**
   - Check complex structure for clashes
   - Verify force field compatibility
   - Increase energy minimization steps

7. **No Candidates Pass All Filters**
   - Relax selection thresholds slightly
   - Generate more backbones (increase num_backbones)
   - Design more sequences per backbone

---

## Workflow Summary

| Step | Input | Output | Primary MCP | Alternative MCP |
|------|-------|--------|-------------|-----------------|
| 1 | PDB 5KU9 | Prepared target | (manual) | alphafold3_mcp |
| 2 | Target + pocket | 20 backbones | rf_diffusion_all_atom_mcp | CYC_BUILDER_v1.0_mcp |
| 3 | 20 backbones | 100 sequences | ligandmpnn_mcp | HighPlay_mcp |
| 4 | 100 sequences | 300 structures | boltz_mcp | HighFold3_mcp |
| 5 | Structures | 50 docked poses | haddock3_mcp | rosetta_mcp |
| 6 | 50 candidates | Permeability | CPMP_mcp | MultiCycPermea_mcp |
| 7 | Filtered candidates | MD results | gromacs_mcp | amber_mcp |
| 8 | All results | Top 5 candidates | (Python script) | - |

---

## References

**RFpeptides/RFDiffusion All-Atom:**
Rettie, S.A., Juergens, D., Adebomi, V., et al. (2025). "Accurate de novo design of high-affinity protein-binding macrocycles using deep learning." *Nature Chemical Biology*, 21, 1948-1956.

**LigandMPNN:**
Dauparas, J., et al. (2022). "Robust deep learning-based protein sequence design using ProteinMPNN." *Science*, 378(6615), 49-56.

**AlphaFold3:**
Abramson, J., et al. (2024). "Accurate structure prediction of biomolecular interactions with AlphaFold 3." *Nature*, 630, 493-500.

**HADDOCK3:**
Dominguez, C., Boelens, R., & Bonvin, A. M. (2003). "HADDOCK: A protein-protein docking approach." *JACS*, 125(7), 1731-1737.

**MCL1 Target:**
Johannes, J.W., Bates, S., Beigie, C., et al. (2017). "Structure Based Design of Non-Natural Peptidic Macrocyclic Mcl-1 Inhibitors." *ACS Medicinal Chemistry Letters*, 8(3), 239-244.

---

## Cleanup

When done with the workflow, uninstall the skill and all its MCPs:

```bash
cpskill uninstall mcl1_cycpep_design
```
