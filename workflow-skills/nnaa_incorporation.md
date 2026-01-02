# Non-Natural Amino Acid Incorporation Skill

Incorporate non-natural amino acids (NNAAs) into peptide sequences for enhanced properties

---

## Prerequisites

Before running this workflow, install the skill and all required MCPs:

```bash
cpskill install nnaa_incorporation
```

This will install the following MCP servers:
- `nnaa_mcp` - Non-Natural Amino Acid MCP server
- `peptide_stability_mcp` - Peptide Stability Prediction MCP server

**Verify MCPs are installed:**
```bash
cpmcp status
```

---

## Configuration Parameters

```yaml
# Required Inputs
PEPTIDE_SEQUENCE: "GRGDSP"                     # Base peptide sequence
TARGET_POSITIONS: [2, 4]                        # Positions for NNAA incorporation (1-indexed)

# Output Settings
RESULTS_DIR: "@results/nnaa_incorporation"     # Output directory

# Optional Settings
NNAA_TYPE: "D-amino"                           # Options: D-amino, N-methyl, alpha-methyl, beta-amino
OPTIMIZATION_GOAL: "stability"                  # Options: stability, permeability, binding
```

**Supported NNAA Types:**
- D-amino acids (stereochemistry inversion)
- N-methylated amino acids (backbone modification)
- Alpha-methylated amino acids (conformational constraint)
- Beta-amino acids (backbone extension)

---

## Step 1: Analyze Peptide for NNAA Sites

**Description**: Identify optimal positions for non-natural amino acid incorporation.

**Prompt:**
> Can you analyze the peptide sequence {PEPTIDE_SEQUENCE} for optimal positions to incorporate non-natural amino acids? Consider the sequence context and suggest positions that would most benefit from modification.

**Implementation Notes:**
- Use analysis tools from nnaa_mcp
- Consider positions based on optimization goal
- Avoid critical functional residues

**Expected Output:**
- Recommended positions for NNAA incorporation
- Rationale for each position

---

## Step 2: Select NNAA Modifications

**Description**: Choose appropriate non-natural amino acids for each target position.

**Prompt:**
> For positions {TARGET_POSITIONS} in the peptide {PEPTIDE_SEQUENCE}, what non-natural amino acids would you recommend for {OPTIMIZATION_GOAL} optimization? Please show the available options and their expected effects.

**Implementation Notes:**
- Different NNAAs have different effects:
  - D-amino acids: proteolytic stability
  - N-methyl: permeability, stability
  - Alpha-methyl: conformational constraint
  - Beta-amino: backbone modification

**Expected Output:**
- NNAA options for each position
- Expected property improvements

---

## Step 3: Generate Modified Sequences

**Description**: Create the peptide sequences with incorporated NNAAs.

**Prompt:**
> Please generate the modified peptide sequences incorporating {NNAA_TYPE} modifications at positions {TARGET_POSITIONS} of {PEPTIDE_SEQUENCE}. Use standard notation for non-natural amino acids.

**Implementation Notes:**
- Standard NNAA notation:
  - D-amino: lowercase (e.g., "d" for D-Asp)
  - N-methyl: prefix "Nme" (e.g., "NmeA")
  - Alpha-methyl: prefix "aMe"
  - Beta-amino: prefix "b"

**Expected Output:**
- Modified sequence with NNAA notation
- Structural implications of modifications

---

## Step 4: Predict Stability Improvements

**Description**: Predict the stability improvements from NNAA incorporation.

**Prompt:**
> Can you predict the proteolytic stability of the modified peptide with NNAAs compared to the original sequence {PEPTIDE_SEQUENCE}? Show the expected half-life improvement.

**Implementation Notes:**
- Use peptide_stability_mcp for predictions
- Compare modified vs. unmodified sequences
- Consider specific protease susceptibility

**Expected Output:**
- Stability score comparison
- Predicted half-life improvement
- Protected cleavage sites

---

## Step 5: Evaluate Trade-offs

**Description**: Assess any trade-offs from NNAA incorporation.

**Prompt:**
> What are the potential trade-offs from incorporating NNAAs into the peptide? Consider synthesis complexity, cost, and any potential loss of activity.

**Implementation Notes:**
- Trade-offs may include:
  - Synthesis complexity/cost
  - Potential activity changes
  - Solubility effects
  - Binding affinity changes

**Expected Output:**
- Trade-off analysis
- Recommendations for optimization

---

## Troubleshooting

### Common Issues

1. **NNAA Not Supported**
   - Check available NNAA types in the MCP
   - Some modifications require specific synthesis routes

2. **Position Not Modifiable**
   - Some positions may be critical for activity
   - Consider alternative positions

3. **Synthesis Feasibility**
   - Complex NNAAs may have limited availability
   - Consult synthesis feasibility before finalizing design

---

## References

- Blaskovich, M.A. (2016). Unusual amino acids in medicinal chemistry. J. Med. Chem.
- Chatterjee, J. et al. (2012). N-Methylation of peptides: a new perspective in medicinal chemistry. Acc. Chem. Res.
- Sagan, S. et al. (2004). Cell penetrating peptides: a reevaluation of the mechanism of cellular uptake. Pharm. Res.

---

## Cleanup

When you're done with the workflow, uninstall the skill and all its MCPs:

```bash
cpskill uninstall nnaa_incorporation
```
