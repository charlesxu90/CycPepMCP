# GABARAP Cyclic Peptide Binder Design — RFpeptides Configuration

> RFpeptides pipeline for designing cyclic peptide binders against GABARAP (LIR-docking site).
>
> **Workflow:** Follow `workflow-skills/binder_design_rfpeptides.md`.

## Target Information

| Property | Value |
|----------|-------|
| Protein | GABARAP (Gamma-aminobutyric acid receptor-associated protein; ATG8 family autophagy adapter) |
| Source | Human (UniProt O95166) |
| PDB | `examples/binder_gabarap/1KOT_GABARAP.pdb` |
| Reference | PDB 1KOT (X-ray, apo GABARAP, 1.75 Å) |
| Chain | A |
| Binder length | 12 |

### Binding Site Characteristics

- **Surface topology:** **Shallow groove** (LIR docking site, LDS) — the tightest iPAE gate in the panel
- **Design challenge:** GABARAP discriminates LIR partners via subtle non-canonical residues; small, shallow target makes confident interface predictions hard
- **Strategy:** Tight iPAE gate (0.13, paper-faithful) reflects the shallow nature of the binding site

### Hotspot Residues

LIR docking site (LDS) per Wirth et al. (PMC6499816) and ATG8 family review (Tandfonline 27694127):

| Residue | Role |
|---------|------|
| 46 | K46 — adjacent to HP1 (canonical hydrophobic pocket 1) |
| 49 | Y49 — HP2 floor |
| 51 | V51 — HP2 sidewall |
| 55 | L55 — HP2 |
| 62 | F62 — adjacent HP1; F62W mutation increases affinity |
| 104 | F104 — groove floor, conserved across ATG8 family |

---

## GABARAP-Specific Parameters

### Stage 1: Backbone Generation

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `target_pdb` | `examples/binder_gabarap/1KOT_GABARAP.pdb` | |
| `target_chain` | `A` | |
| `hotspot_residues` | `[46, 49, 51, 55, 62, 104]` | LIR docking site HP1+HP2 |
| `binder_length` | 12 | LIR motifs are short (Θ-X-X-Γ); 12-mer cyclic gives 1-2 anchor turns |
| `num_designs` | 5000 | Paper scale |

### Stages 2-3: Sequence Design & Validation

Standard parameters; no GABARAP-specific override.

### Quality Thresholds (Paper-faithful, GABARAP-specific)

Per `benchmark/configs/workflows.yaml` `rfpeptides.per_target_thresholds.gabarap`:

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| iPAE | **< 0.13** | **Tightest gate in panel — shallow groove, paper Methods 2.4** |
| ddG | < -30 REU | Standard |
| pLDDT | > 0.70 | Standard |
| SAP | < 35 | Standard |
| CMS | > 300 Å² | Standard |

### Composite Score

Centralized in `workflows.yaml` (RFpeptides default formula).

---

## Notes

- **Hardest of the 5 RFpeptides targets**: the iPAE 0.13 gate is half the MCL1/MDM2 threshold and a third of RbtA/PD-L1. Expect single-digit PASS rates even with 5000 designs.
- **Why include**: provides the harshest specificity test in the benchmark — validates that the workflow can fail gracefully on tight targets without producing false positives.
