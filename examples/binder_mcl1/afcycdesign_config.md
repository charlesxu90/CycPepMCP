# MCL1 Cyclic Peptide Binder Design — AfCycDesign Configuration

> AfCycDesign pipeline configuration for designing cyclic peptide binders against MCL1 (induced myeloid leukemia cell differentiation protein 1), the BH3-binding groove.
>
> **Workflow:** Follow `workflow-skills/binder_design_afcycdesign.md`. This file specifies only MCL1-specific parameters.

## Target Information

| Property | Value |
|----------|-------|
| Protein | MCL1 (anti-apoptotic BCL-2 family) |
| Source | Human (UniProt Q07820) |
| PDB | `examples/binder_mcl1/2PQK_MCL1.pdb` |
| Reference | PDB 2PQK (X-ray, MCL1 + BIM BH3 peptide complex) |
| Chain | A |
| Residue range | 172-321 (BH3-binding groove in main domain) |
| Binder length | 12 residues (variable 8-16) |

### Binding Site Characteristics

- **Surface topology:** Concave pocket (BH3-binding groove)
- **Design challenge:** Well-defined pocket with known hot residues — tractable target
- **Strategy:** Hotspot-guided AF2-Multimer optimization targeting the BH3-binding residues

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

### MCP Tool: `afcycdesign_mcp.cyclic_binder_design`

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `pdb` | `examples/binder_mcl1/2PQK_MCL1.pdb` | |
| `target_chain` | `A` | |
| `binder_len` | 12 | Standard pocket-binder length |
| `hotspot` | `228,231,267,270,271,274` | 6 residues defining the BH3 groove |
| `optimizer` | `pssm_semigreedy` | Recommended (faster, robust); 3stage as alternative |
| `num_models` | 2 | Standard |
| `num_recycles` | 0 | Default for binder_design (skip recycles for speed) |
| `ipae_threshold` | 0.15 | Standard quality gate |

### Quality Thresholds

Standard AfCycDesign primary PASS gate from `benchmark/configs/workflows.yaml`:

| Metric | Primary gate | Excellent | Source |
|--------|--------------|-----------|--------|
| pLDDT | ≥ 0.70 | ≥ 0.85 | workflows.yaml |
| iPTM | ≥ 0.50 | ≥ 0.70 | workflows.yaml |
| iPAE | ≤ 0.20 | ≤ 0.15 | workflows.yaml |
| pTM | ≥ 0.60 | ≥ 0.80 | workflows.yaml |

### Composite Score

`0.30·pLDDT + 0.30·iPAE_inv + 0.25·iPTM + 0.15·pTM` (centralized in `workflows.yaml`).

### Production Run Parameters

For the 13-task benchmark (per `benchmark/configs/targets.csv`):
- `num_designs` = 10 (default override via `--num-designs N`)
- Expected wall time: ~4-7 min per design × 10 = ~40-70 min on a single A100

---

## Notes

- **X-ray crystal structure**: 2PQK is an experimental structure (not AF2 prediction), giving credible target geometry.
- **Cross-workflow comparison**: The same MCL1 target is also benchmarked under RFpeptides (`examples/binder_mcl1/`). Different workflow → different binder distributions for the same pocket.
- **Crystal contact peptide (chain B, BIM BH3)** removed before benchmarking — only MCL1 (chain A) is used as target.
