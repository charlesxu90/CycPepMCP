# MDM2 Cyclic Peptide Binder Design — RFpeptides Configuration

> RFpeptides pipeline (RFdiffusion → ProteinMPNN-CA → Rosetta FastRelax → AfCycDesign reprediction → Rosetta interface metrics → RMSD clustering) for designing cyclic peptide binders against MDM2 (the p53-binding pocket).
>
> **Workflow:** Follow `workflow-skills/binder_design_rfpeptides.md`.

## Target Information

| Property | Value |
|----------|-------|
| Protein | MDM2 (E3 ubiquitin ligase; p53 negative regulator) |
| Source | Human (UniProt Q00987) |
| PDB | `examples/binder_mdm2/4HFZ_MDM2.pdb` |
| Reference | PDB 4HFZ (X-ray, MDM2 + p53 N-terminal peptide) |
| Chain | A |
| Binder length | 12 residues |

### Binding Site Characteristics

- **Surface topology:** Concave pocket (p53-binding cleft)
- **Design challenge:** Tight, hydrophobic, well-validated PPI target — high baseline difficulty but lots of structural data
- **Strategy:** Hotspot-guided RFdiffusion backbone generation; tight iPAE gate (0.30) for concave pocket

### Hotspot Residues

Same set used for the AfCycDesign MDM2 case (see `examples/binder_mdm2/`):

| Residue | Role |
|---------|------|
| 54 | F19 (p53) anchor pocket |
| 56 | Hydrophobic pocket |
| 58 | Hydrophobic pocket |
| 61 | W23 (p53) anchor pocket |
| 67 | L26 (p53) anchor pocket |
| 96 | Pocket rim |
| 99 | Pocket rim |
| 100 | Pocket rim |

---

## MDM2-Specific Parameters

### Stage 1: Backbone Generation (rfpeptides_mcp)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `target_pdb` | `examples/binder_mdm2/4HFZ_MDM2.pdb` | |
| `target_chain` | `A` | |
| `hotspot_residues` | `[54, 56, 58, 61, 67, 96, 99, 100]` | p53-binding pocket |
| `binder_length` | 12 | Standard pocket binder |
| `num_designs` | 5000 | Production scale (paper) — 200-500 for pilot |
| `diffusion_steps` | 50 | Standard |

### Stages 2-3: Sequence Design & Validation

Standard parameters (no MDM2-specific override):
- ProteinMPNN-CA: `model=v_48_020`, `temperature=0.0001`, `omit_AAs=C`, `chains=A`, 4 rounds
- Rosetta FastRelax with PeptideCyclizeMover
- AfCycDesign reprediction for iPAE / pLDDT / iPTM

### Quality Thresholds (Paper-faithful, MDM2-specific)

Per `benchmark/configs/workflows.yaml` `rfpeptides.per_target_thresholds.mdm2`:

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| iPAE | < 0.30 | Concave pocket — paper's MDM2 threshold |
| ddG | **< -50 REU** | **MDM2-specific, tighter than -30 default (paper Methods 2.4)** |
| pLDDT | > 0.70 | Standard |
| SAP | < 35 | Standard |
| CMS | > 300 Å² | Standard |
| RMSD | < 1.5 Å | Standard |

### Composite Score

Centralized in `workflows.yaml`:
`0.30·ddG_norm + 0.25·iPAE_norm + 0.20·pLDDT_norm + 0.15·CMS_norm + 0.10·SAP_norm`

---

## Notes

- **Tighter ddG gate**: MDM2's hydrophobic p53 pocket consistently produces low ddG values; the paper used -50 REU instead of -30 to discriminate top binders.
- **Cross-workflow comparison**: The same MDM2 target is benchmarked under AfCycDesign (`examples/binder_mdm2/`). Comparing the two distributions shows whether end-to-end design (RFpeptides) outperforms direct sequence optimization (AfCycDesign) on the same target.
- **Paper benchmark**: Olsen et al. (Nat Chem Biol 2025) tested ~10,000 backbones for MDM2 with hit rates ~5-10%. At 5000-design scale, expect ~250-500 PASS.
