# RbtA Cyclic Peptide Binder Design Configuration

> RFpeptides pipeline configuration for designing cyclic peptide binders against RbtA from *Acinetobacter baumannii*
>
> **Workflow:** Follow `workflow-skills/binder_design_rfpeptides.md`. This file specifies only RbtA-specific parameters and threshold adjustments.

## Target Information

| Property | Value |
|----------|-------|
| Protein | RbtA (rhamnosyltransferase subunit A) |
| Organism | *Acinetobacter baumannii* |
| Source | NCBI GenBank PXA52927.1 |
| PDB (AF2 predicted) | `examples/binder_rbta/RbtA_monomer.pdb` |
| Reference structures | 9CDV (apo), 9CDU (complex with RBB_D10) |
| Chain | A |
| Residue range | 20-460 (441 residues) |
| Domain of interest | N-terminal beta-helix domain (residues 20-459) |

### Binding Site Characteristics

- **Surface topology:** Flat binding surface (beta-helix fold)
- **Design challenge:** Flat surfaces lack deep pockets, requiring extended loop-like peptide conformations that maximize contact area
- **Strategy:** Use longer binder lengths (12-16 residues) and hotspot-guided generation to ensure sufficient interface contacts

### Hotspot Residues

| Residue | Type | Rationale |
|---------|------|-----------|
| 144 | LEU | Hydrophobic anchor on beta-helix surface |
| 202 | PHE | Aromatic residue, pi-stacking potential |
| 204 | PHE | Aromatic residue, pi-stacking potential |
| 206 | TYR | Aromatic + H-bond donor/acceptor |
| 208 | VAL | Hydrophobic surface patch |
| 231 | LEU | Hydrophobic anchor, extends binding site |
| 269 | ALA | Hydrophobic surface, flanking position |

---

## RbtA-Specific Parameters

### Stage 1: Backbone Generation

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `target_pdb` | `examples/binder_rbta/RbtA_monomer.pdb` | |
| `hotspot_residues` | [144, 202, 204, 206, 208, 231, 269] | 7 residues spanning the beta-helix surface |
| `target_chain` | "A" | |
| `binder_length` | 12 | Variable length 12-16 for flat surface coverage |
| `binder_length_max` | 16 | |
| `num_designs` | 50 | Large pool; flat surfaces have lower hit rates (~10-20%) |
| `diffusion_steps` | 50 | |

### Stages 2-3: Sequence Design & Validation

Use standard workflow parameters (chains="A", model="v_48_020", temperature=0.0001, omit_AAs="C", 4 rounds). No RbtA-specific overrides needed.

### Adjusted Quality Thresholds (Stages 3-4)

Relaxed thresholds for flat binding surface — tighten if many designs pass.

| Metric | Standard | RbtA-adjusted | Rationale |
|--------|----------|---------------|-----------|
| iPAE | < 0.20 | < 0.25 | Flat surfaces yield weaker confidence scores |
| RMSD | < 1.5 A | < 2.0 A | Flexible loop binders on flat surface |
| pLDDT | > 0.70 | > 0.60 | Extended conformations score lower |
| ddG | < -30 REU | < -25 REU | Flat surfaces yield weaker binding energies |
| SAP | < 35 | < 40 | Allow slightly higher hydrophobicity |
| CMS | > 300 A^2 | > 250 A^2 | Flat interfaces have moderate contact areas |

### Stage 4: Combined Filtering

```
IF iPAE < 0.25 AND ddG < -25 AND SAP < 40 AND CMS > 250:
    -> HIGH PRIORITY
ELSE IF iPAE < 0.30 AND ddG < -15 AND CMS > 200:
    -> MEDIUM PRIORITY
ELSE:
    -> LOW PRIORITY
```

### Stage 5: Clustering

RMSD cutoff: 1.5 A. Target 5-10 diverse designs for experimental testing. Prioritize extended loop-like conformations that wrap the flat surface.

---

## Notes

- **AF2 predicted structure**: Not an experimental crystal structure. Reference 9CDV/9CDU can be used for cross-validation of binding site geometry.
- **Flat surface challenge**: Expect lower hit rates than groove/pocket targets. If initial results are poor, consider:
  - Running campaigns with different binder lengths (fixed 10, fixed 14, variable 12-16)
  - Trying hotspot subsets:
    - Aromatic cluster: [202, 204, 206] (compact, pi-stacking rich)
    - Extended hydrophobic: [144, 202, 204, 206, 208] (central patch)
    - Full set: [144, 202, 204, 206, 208, 231, 269] (maximum coverage)
