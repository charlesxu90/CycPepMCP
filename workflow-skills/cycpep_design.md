# Cyclic Peptide Design Skill

Design cyclic peptides with various cyclization strategies including head-to-tail, disulfide bridges, and side-chain linkages

---

## Prerequisites

Before running this workflow, install the skill and all required MCPs:

```bash
cpskill install cycpep_design
```

This will install the following MCP servers:
- `cycpep_design_mcp` - Cyclic Peptide Design MCP server
- `cycpep_struct_mcp` - Cyclic Peptide Structure Prediction MCP server

**Verify MCPs are installed:**
```bash
cpmcp status
```

---

## Configuration Parameters

```yaml
# Required Inputs
LINEAR_SEQUENCE: "GRGDSP"                      # Linear peptide sequence to cyclize
CYCLIZATION_TYPE: "head_to_tail"               # Options: head_to_tail, disulfide, side_chain, thioether

# Output Settings
RESULTS_DIR: "@results/cycpep_design"          # Output directory for all results
NUM_VARIANTS: 5                                 # Number of variants to generate

# Optional Settings
N_TERMINUS_RESIDUE: null                        # For side-chain cyclization (1-indexed)
C_TERMINUS_RESIDUE: null                        # For side-chain cyclization (1-indexed)
ALLOWED_MUTATIONS: null                         # List of allowed amino acids for variants
```

**Sequence Requirements:**
- Use standard one-letter amino acid codes (ACDEFGHIKLMNPQRSTVWY)
- Minimum length: 4 residues for cyclization
- For disulfide cyclization: include at least 2 cysteine (C) residues
- For side-chain lactam: include lysine (K) and aspartate/glutamate (D/E)

**Directory Structure:**
```
RESULTS_DIR/                     # All outputs go here
├── design_results.json          # Designed cyclic peptide info
├── cyclization_analysis.json    # Cyclization site analysis
├── variants/                    # Generated variant sequences
│   ├── variant_1.json
│   └── ...
└── properties.json              # Predicted properties
```

---

## Step 1: Explore Example Sequences

**Description**: List available example cyclic peptide sequences to understand different cyclization strategies.

**Prompt:**
> Can you list the example cyclic peptide sequences available in the cycpep_design_mcp server? Show me the different cyclization types and their properties.

**Implementation Notes:**
- Use `mcp__cycpep_design_mcp__list_example_sequences` tool
- Returns examples of different cyclization strategies
- Use these as templates or for testing the workflow

**Expected Output:**
- List of example sequences with cyclization types
- Descriptions of each example peptide

---

## Step 2: Analyze Cyclization Sites

**Description**: Analyze your peptide sequence for potential cyclization sites before designing.

**Prompt:**
> Can you analyze the peptide sequence {LINEAR_SEQUENCE} for potential cyclization sites? Check all cyclization types (head_to_tail, disulfide, and side_chain).

**Implementation Notes:**
- Use `mcp__cycpep_design_mcp__analyze_cyclization_sites` tool
- Parameters:
  - `sequence`: Your linear peptide sequence
  - `cyclization_type`: "all" to check all options
- Identifies favorable positions for each cyclization strategy

**Expected Output:**
- Head-to-tail feasibility and favorability
- Disulfide bridge possibilities (cysteine positions)
- Side-chain lactam possibilities (Lys/Asp/Glu positions)

---

## Step 3: Setup Results Directory

**Description**: Create the output directory structure for the design workflow.

**Prompt:**
> Please create the results directory at {RESULTS_DIR} for the cyclic peptide design workflow. Set up the necessary subdirectories.

**Implementation Notes:**
```bash
mkdir -p {RESULTS_DIR}/variants
```

**Expected Output:**
- `{RESULTS_DIR}/` directory created
- `{RESULTS_DIR}/variants/` subdirectory

---

## Step 4: Design Cyclic Peptide

**Description**: Design the cyclic peptide using your chosen cyclization strategy.

**Prompt:**
> Can you design a cyclic peptide from the sequence {LINEAR_SEQUENCE} using {CYCLIZATION_TYPE} cyclization? Save the results to {RESULTS_DIR}/design_results.json.

**Implementation Notes:**
- Use `mcp__cycpep_design_mcp__design_cyclic_peptide` tool
- Parameters:
  - `sequence`: Linear peptide sequence
  - `cyclization_type`: Your chosen cyclization method
  - `n_terminus_residue`: Required for side_chain type
  - `c_terminus_residue`: Required for side_chain type
  - `output_file`: Path for results

**Expected Output:**
- `{RESULTS_DIR}/design_results.json` - Cyclic peptide design info
- Cyclization sites and bond type information

---

## Step 5: Predict Properties

**Description**: Predict physicochemical properties of the designed cyclic peptide.

**Prompt:**
> Can you predict the properties of the cyclic peptide {LINEAR_SEQUENCE} with {CYCLIZATION_TYPE} cyclization? I want to know the molecular weight, charge, and solubility predictions.

**Implementation Notes:**
- Use `mcp__cycpep_design_mcp__predict_cyclic_peptide_properties` tool
- Parameters:
  - `sequence`: The cyclic peptide sequence
  - `cyclization_type`: The cyclization method used
- Returns MW, charge, GRAVY score, composition, and predictions

**Expected Output:**
- Molecular weight
- Net charge at pH 7
- Hydropathy (GRAVY) score
- Amino acid composition breakdown
- Solubility and membrane interaction predictions

---

## Step 6: Generate Variants

**Description**: Generate variant sequences for optimization or screening.

**Prompt:**
> Can you generate {NUM_VARIANTS} variants of the cyclic peptide {LINEAR_SEQUENCE}? Use conservative amino acid substitutions to maintain the overall properties.

**Implementation Notes:**
- Use `mcp__cycpep_design_mcp__generate_cyclic_variants` tool
- Parameters:
  - `sequence`: Base cyclic peptide sequence
  - `num_variants`: Number of variants to generate
  - `allowed_mutations`: Optional list of allowed substitutions
- Each variant has 1-3 mutations from the parent

**Expected Output:**
- List of variant sequences with mutations
- Variant IDs for tracking
- Number of mutations per variant

---

## Step 7: Analyze Variant Properties

**Description**: Predict properties for each generated variant.

**Prompt:**
> Can you predict the properties for each of the generated cyclic peptide variants? Compare them to the parent sequence and identify the most promising candidates.

**Implementation Notes:**
- Loop through variants and call `predict_cyclic_peptide_properties` for each
- Compare MW, charge, hydropathy across variants
- Identify variants with improved solubility or membrane interaction

**Expected Output:**
- Property comparison table
- Ranking of variants by target property
- Recommendations for further optimization

---

## Step 8: Save Final Results

**Description**: Compile and save all design results.

**Prompt:**
> Please save all the cyclic peptide design results to {RESULTS_DIR}. Create a summary file with the parent design, variants, and property comparisons.

**Implementation Notes:**
- Save design_results.json, variants/*.json, and properties.json
- Create summary.md with key findings
- Include recommendations for experimental validation

**Expected Output:**
- Complete results in {RESULTS_DIR}
- Summary document with recommendations

---

---

## Troubleshooting

### Common Issues

1. **Invalid Amino Acid Codes**
   - Ensure you're using standard one-letter codes
   - Check for lowercase letters (should be uppercase)
   - Non-natural amino acids require the nnaa_mcp server

2. **Disulfide Cyclization Fails**
   - Sequence needs at least 2 cysteine residues
   - Check cysteine positions are appropriate for bridging
   - Optimal spacing is 3-6 residues between cysteines

3. **Side-chain Cyclization Fails**
   - Needs at least one lysine (K) and one Asp (D) or Glu (E)
   - Specify n_terminus_residue and c_terminus_residue

4. **Sequence Too Short**
   - Minimum 4 residues for head-to-tail cyclization
   - Longer sequences (6-12) often more stable

5. **Low Predicted Solubility**
   - Consider adding polar residues (S, T, N, Q)
   - Reduce hydrophobic content (I, L, V, F, W)

6. **MCP Connection Errors**
   - Verify MCP is registered: `cpmcp status`
   - Reinstall if needed: `cpmcp install cycpep_design_mcp`

---

## References

- Craik, D.J. et al. (2013). The Future of Peptide-based Drugs. Chem. Biol. Drug Des.
- White, C.J. & Yudin, A.K. (2011). Contemporary strategies for peptide macrocyclization. Nat. Chem.
- Driggers, E.M. et al. (2008). The exploration of macrocycles for drug discovery. Nat. Rev. Drug Discov.
- Hill, T.A. et al. (2014). Constraining cyclic peptides to mimic protein structure motifs. Angew. Chem.

---

## Cleanup

When you're done with the workflow, uninstall the skill and all its MCPs:

```bash
cpskill uninstall cycpep_design
```
