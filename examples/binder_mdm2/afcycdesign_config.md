# MDM2 Cyclic Peptide Binder Design — AfCycDesign Configuration

> AfCycDesign pipeline configuration for designing cyclic peptide binders against MDM2 (the p53-binding pocket).
>
> **Workflow:** Follow `workflow-skills/binder_design_afcycdesign.md`. This is the canonical AfCycDesign reference case (case1).

## Target Information

| Property | Value |
|----------|-------|
| Protein | MDM2 (E3 ubiquitin ligase; p53 negative regulator) |
| Source | Human (UniProt Q00987) |
| PDB | `examples/binder_mdm2/4HFZ_MDM2.pdb` |
| Reference | PDB 4HFZ (X-ray, MDM2 + p53 N-terminal peptide) |
| Chain | A |
| Binder length | 12 |

### Binding Site Characteristics

- **Surface topology:** Concave pocket (p53-binding cleft)
- **Design challenge:** Tight, hydrophobic, well-validated PPI target
- **Strategy:** Hotspot-guided AF2-Multimer optimization

### Hotspot Residues

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

### MCP Tool: `afcycdesign_mcp.cyclic_binder_design`

| Parameter | Value |
|-----------|-------|
| `pdb` | `examples/binder_mdm2/4HFZ_MDM2.pdb` |
| `target_chain` | `A` |
| `binder_len` | 12 |
| `hotspot` | `54,56,58,61,67,96,99,100` |
| `optimizer` | `pssm_semigreedy` |
| `num_models` | 2 |
| `ipae_threshold` | 0.15 |

### Quality Thresholds & Composite Score

Standard AfCycDesign gates from `benchmark/configs/workflows.yaml`:
- pLDDT ≥ 0.70, iPTM ≥ 0.50, iPAE ≤ 0.20, pTM ≥ 0.60
- Composite: `0.30·pLDDT + 0.30·iPAE_inv + 0.25·iPTM + 0.15·pTM`

---

## Notes

- **Reference run**: this directory holds `afcycdesign_results.csv` (50 candidates) from the original case study, used to seed `Run 0` for the benchmark via `benchmark/scripts/seed_pilot_from_case.py --task AF_MDM2`.
- **Cross-workflow comparison**: same MDM2 target is also benchmarked under RFpeptides (`examples/binder_mdm2/`) and HELM-GPT (`examples/co_opt_mdm2p53_kd_perm/`) — three different design strategies on identical biology.
- **Manuscript figures**: this case is referenced in `docs/benchmark_plan.md` Appendix A as the canonical AfCycDesign demonstrator.
