# BCL-xL Cyclic Peptide Binder Design — AfCycDesign Configuration

> AfCycDesign pipeline configuration for designing cyclic peptide binders against BCL-xL (B-cell lymphoma extra-large), the BH3-binding hydrophobic groove.
>
> **Workflow:** Follow `workflow-skills/binder_design_afcycdesign.md`.

## Target Information

| Property | Value |
|----------|-------|
| Protein | BCL-xL (anti-apoptotic BCL-2 family) |
| Source | Human (UniProt Q07817) |
| PDB | `examples/binder_bclxl/1G5J_BCLxL.pdb` |
| Reference | PDB 1G5J (X-ray, BCL-xL + BAD BH3 peptide complex, 2.2 Å) |
| Chain | A (175 residues) |

### Binding Site Characteristics

- **Surface topology:** Concave hydrophobic groove (canonical BH3 binding cleft)
- **Design challenge:** Closely related to MCL1 groove but distinct selectivity determinants — useful negative control / cross-selectivity comparison
- **Strategy:** Hotspot-guided AF2-Multimer optimization targeting BH3 h1-h4 anchor pockets

### Hotspot Residues

Hotspot map per Acoca et al. (PMC4025761) and BAD-BH3 contact analysis on 1G5J:

| Residue | Type | Role |
|---------|------|------|
| 97 | PHE | h2 pocket, hydrophobic core |
| 100 | ASP | h2 pocket rim, electrostatic |
| 104 | ALA | h3 pocket floor |
| 105 | PHE | h3 pocket, key hydrophobic anchor |
| 130 | LEU/VAL | h4 pocket |
| 146 | PHE | groove floor, conserved BH3 anchor |

---

## BCL-xL-Specific Parameters

### MCP Tool: `afcycdesign_mcp.cyclic_binder_design`

| Parameter | Value |
|-----------|-------|
| `pdb` | `examples/binder_bclxl/1G5J_BCLxL.pdb` |
| `target_chain` | `A` |
| `binder_len` | 12 |
| `hotspot` | `97,100,104,105,130,146` |
| `optimizer` | `pssm_semigreedy` |
| `num_models` | 2 |
| `ipae_threshold` | 0.15 |

### Quality Thresholds & Composite Score

Standard AfCycDesign gates from `benchmark/configs/workflows.yaml`:
- pLDDT ≥ 0.70, iPTM ≥ 0.50, iPAE ≤ 0.20, pTM ≥ 0.60
- Composite: `0.30·pLDDT + 0.30·iPAE_inv + 0.25·iPTM + 0.15·pTM`

---

## Notes

- **Crystal contact peptide (chain B, BAD BH3)** present in 1G5J — strip before benchmarking if the workflow doesn't auto-handle it.
- **Cross-target selectivity**: When candidates from this run are evaluated against MCL1 (case_mcl1_afcycdesign), an MCL1-selective binder would show low predicted affinity here (high iPAE) and vice-versa.
