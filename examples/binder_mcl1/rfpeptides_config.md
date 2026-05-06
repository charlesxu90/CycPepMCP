# MCL1 Cyclic Peptide Binder Design Configuration

> RFpeptides pipeline configuration for designing cyclic peptide binders against MCL1 (induced myeloid leukemia cell differentiation protein 1), the BH3-binding groove.
>
> **Workflow:** Follow `workflow-skills/binder_design_rfpeptides.md`. This file specifies only MCL1-specific parameters.

## Target Information

| Property | Value |
|----------|-------|
| Protein | MCL1 (anti-apoptotic BCL-2 family) |
| Source | Human (UniProt Q07820) |
| PDB | `examples/case3_MCL1_binder_rfpeptides/2PQK_MCL1.pdb` |
| Reference | PDB 2PQK (X-ray, MCL1 + BIM BH3 peptide complex) |
| Chain | A |
| Residue range | 172-321 (BH3-binding groove in main domain) |
| Binder length | 12-16 residues |

### Binding Site Characteristics

- **Surface topology:** Concave pocket (BH3-binding groove)
- **Design challenge:** Well-defined pocket with known hot residues — tractable target
- **Strategy:** Hotspot-guided generation targeting the BH3-binding residues

### Hotspot Residues (from RFpeptides paper, Methods 2.2.2)

| Residue | Type | Role |
|---------|------|------|
| 228 | PHE | Hydrophobic core, BH3 anchor |
| 231 | MET | Hydrophobic pocket floor |
| 267 | LEU | BH3 P1 pocket |
| 270 | LEU | BH3 P2 pocket |
| 271 | GLY | Pocket flexibility |
| 274 | VAL | Hydrophobic surface |

---

## MCL1-Specific Parameters

### Stage 1: Backbone Generation

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `target_pdb` | `examples/case3_MCL1_binder_rfpeptides/2PQK_MCL1.pdb` | |
| `hotspot_residues` | [228, 231, 267, 270, 271, 274] | 6 residues defining BH3 groove |
| `target_chain` | "A" | |
| `binder_length` | 12 | Variable length 12-16 (paper setting) |
| `binder_length_max` | 16 | |
| `num_designs` | 200 | Demo-scale. Paper used ~10,000 for MCL1. |
| `diffusion_steps` | 50 | |

### Stages 2-3: Sequence Design & Validation

Use standard workflow parameters. No MCL1-specific overrides.

### Quality Thresholds (Stage 3-4)

Standard thresholds from `workflow-skills/binder_design_rfpeptides.md` apply — MCL1 is a concave pocket target. Paper uses iPAE<0.3.

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| iPAE | < 0.30 | Concave pocket — paper's MCL1 threshold |
| RMSD | < 1.5 A | Standard |
| pLDDT | > 0.70 | Standard |
| ddG | < -30 REU | Standard |
| SAP | < 35 | Standard |
| CMS | > 300 A^2 | Standard |

### Stage 4: Combined Filtering

```
IF iPAE < 0.3 AND ddG < -30 AND SAP < 35 AND CMS > 300:
    -> HIGH PRIORITY
ELSE IF iPAE < 0.4 AND ddG < -20:
    -> MEDIUM PRIORITY
```

### Stage 5: Clustering

RMSD cutoff 1.5 A. Expected 5-10 diverse designs at 200-scale.

---

## Notes

- **X-ray crystal structure**: 2PQK is an experimental structure (unlike RbtA's AF2 prediction), giving more credible target geometry.
- **Paper benchmark**: 9,965 backbones in the paper; 27 experimentally tested; 3 binders (best Kd ~2 uM). At 200-design scale, expect ~16 iPAE<0.3 passes (8% pass rate per paper Supp Fig. 4), enough for clustering demo.
- **Crystal contact peptide (chain B, BIM BH3)** was removed from the input PDB — only MCL1 (chain A) is used as the target.
