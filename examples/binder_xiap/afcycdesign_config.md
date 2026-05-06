# XIAP-BIR3 Cyclic Peptide Binder Design — AfCycDesign Configuration

> AfCycDesign pipeline configuration for designing cyclic peptide binders against the XIAP BIR3 domain (Smac/DIABLO binding cleft).
>
> **Workflow:** Follow `workflow-skills/binder_design_afcycdesign.md`.

## Target Information

| Property | Value |
|----------|-------|
| Protein | XIAP BIR3 domain (X-linked inhibitor of apoptosis) |
| Source | Human (UniProt P98170, residues 252-356) |
| PDB | `examples/binder_xiap/1G73_XIAP.pdb` |
| Reference | PDB 1G73 (X-ray, XIAP BIR3 + Smac AVPI N-terminal peptide, 2.0 Å) |
| **Chain** | **C** (BIR3 domain; full-length XIAP numbering 256-344) |
| Note | Chains A/B in this PDB are full Smac/DIABLO (residues 1-157 local numbering) — do NOT use chain A |

### Binding Site Characteristics

- **Surface topology:** Surface groove with four sub-pockets P1-P4
- **Design challenge:** Smaller binder length (10) tests parameter robustness vs. the 12-mer default
- **Strategy:** Target the AVPI-recognition groove

### Hotspot Residues (Liu et al. 2000, structural basis paper)

| Residue | Type | Role |
|---------|------|------|
| 292 | LEU | P4 pocket floor |
| 297 | LYS | P4 pocket sidewall |
| 299 | LYS | P4 pocket sidewall |
| 307 | LEU | P2 pocket |
| 314 | GLU | P1 pocket (N-terminus electrostatic anchor) |
| 323 | TRP | P3 pocket floor |

---

## XIAP-Specific Parameters

### MCP Tool: `afcycdesign_mcp.cyclic_binder_design`

| Parameter | Value |
|-----------|-------|
| `pdb` | `examples/binder_xiap/1G73_XIAP.pdb` |
| `target_chain` | `C` |
| `binder_len` | **10** (smaller than default 12 — tests parameter robustness) |
| `hotspot` | `292,297,299,307,314,323` |
| `optimizer` | `pssm_semigreedy` |
| `num_models` | 2 |
| `ipae_threshold` | 0.15 |

### Quality Thresholds & Composite Score

Standard AfCycDesign gates from `benchmark/configs/workflows.yaml` (no XIAP-specific override).

---

## Notes

- **Chain C is critical**: The earlier benchmark draft incorrectly used chain A; the runner failed with "positions 292 and chain A not found" because chain A is Smac (locally numbered 1-157), not BIR3. Always use chain C with full-length XIAP numbering.
- **Smaller binder length (10)**: deliberately probes the AfCycDesign optimizer at a smaller-than-default size; useful for showing parameter generalization in the manuscript.
