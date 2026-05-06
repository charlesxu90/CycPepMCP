# PD-L1 Cyclic Peptide Binder Design — RFpeptides Configuration

> RFpeptides pipeline for designing cyclic peptide binders against PD-L1 (the PD-1 binding face).
>
> **Workflow:** Follow `workflow-skills/binder_design_rfpeptides.md`.

## Target Information

| Property | Value |
|----------|-------|
| Protein | PD-L1 (Programmed death-ligand 1; immune checkpoint) |
| Source | Human (UniProt Q9NZQ7) |
| PDB | `examples/binder_pdl1/5IUS_PDL1.pdb` |
| Reference | PDB 5IUS (X-ray, PD-1 / PD-L1 complex, 2.45 Å) |
| **Chain** | **B** (PD-L1; chain A in 5IUS is PD-1) |
| Binder length | 14 |

### Binding Site Characteristics

- **Surface topology:** **Flat IGV-like interface** — paper-class flat-surface stress test
- **Design challenge:** PD-L1's PD-1-binding face is mostly featureless β-sheet; small molecules / peptides historically struggle here
- **Strategy:** Longer binder (14-mer) for surface coverage; relaxed iPAE gate (0.40) per the flat-target convention

### Hotspot Residues

Per Hatakeyama et al. (Sci Rep 2019, PMC6853875) — fragment molecular orbital analysis of the PD-1/PD-L1 hot spot:

| Residue | Role |
|---------|------|
| 54 | I54 — hydrophobic core (β-sheet) |
| 56 | Y56 — primary anchor for PD-1 binding |
| 113 | R113 — electrostatic anchor |
| 115 | M115 — stabilizes hot-spot region |
| 121 | A121 — surface contact |
| 122 | D122 — electrostatic anchor |
| 123 | Y123 — anchor residue |

---

## PD-L1-Specific Parameters

### Stage 1: Backbone Generation

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `target_pdb` | `examples/binder_pdl1/5IUS_PDL1.pdb` | |
| `target_chain` | **`B`** | PD-L1 is chain B; chain A is PD-1 |
| `hotspot_residues` | `[54, 56, 113, 115, 121, 122, 123]` | PD-1-binding face (Y56/R113/A121/D122/Y123 = optimal anchor combination) |
| `binder_length` | 14 | Longer than 12-mer default for flat-surface coverage |
| `num_designs` | 5000 | Paper scale |

### Stages 2-3: Sequence Design & Validation

Standard parameters.

### Quality Thresholds (Flat-Surface, RbtA-class)

Per `benchmark/configs/workflows.yaml` `rfpeptides.per_target_thresholds.pdl1`:

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| iPAE | < 0.40 | Flat IGV-like surface; same class as RbtA (paper handles flat targets with relaxed iPAE) |
| ddG | < -30 REU | Standard |
| pLDDT | > 0.70 | Standard |
| SAP | < 35 | Standard |
| CMS | > 300 Å² | Standard |

### Composite Score

Centralized in `workflows.yaml`.

---

## Notes

- **Chain matters**: PD-L1 is chain B in 5IUS. The runner reads `target_chain` from `targets.csv`; targets.csv already has B.
- **Therapeutic relevance**: PD-L1 inhibition is the mechanism behind atezolizumab/durvalumab/avelumab (mAbs). A cyclic peptide alternative is highly publication-relevant.
- **Flat-interface stress test**: low PASS rates expected (similar to RbtA). Useful for showing the workflow's failure mode on targets the paper notes as harder.
