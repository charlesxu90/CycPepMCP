# PCSK9 Cyclic Peptide Binder Design — AfCycDesign Configuration

> AfCycDesign pipeline configuration for designing cyclic peptide binders against PCSK9 (proprotein convertase subtilisin/kexin type 9), the LDLR-binding interface.
>
> **Workflow:** Follow `workflow-skills/binder_design_afcycdesign.md`.

## Target Information

| Property | Value |
|----------|-------|
| Protein | PCSK9 (cholesterol regulation; cardiovascular target) |
| Source | Human (UniProt Q8NBP7) |
| PDB | `examples/binder_pcsk9/3P5C_PCSK9.pdb` |
| Reference | PDB 3P5C (LDLR / PCSK9 complex, 3.30 Å — extended LDLR conformation) |
| Chain | A (PCSK9 catalytic + C-terminal domains, 496 residues) |
| Note | Chain L is LDLR; chain P is the prodomain. Do NOT include them as the binder target. |

### Binding Site Characteristics

- **Surface topology:** Discontinuous surface around the catalytic-domain LDLR-EGF-A interface; partly flat
- **Design challenge:** PCSK9 is therapeutically validated (LDL-lowering); a cyclic peptide that blocks LDLR binding is a real disease-relevant binder
- **Strategy:** Target the canonical D374 hot-spot region (gain-of-function mutation D374Y dramatically increases LDLR affinity)

### Hotspot Residues

Hotspot map per Lo Surdo et al. (PMC2538846; LDLR / PCSK9 complex paper) plus EGF-A footprint analysis:

| Residue | Type | Role |
|---------|------|------|
| 153 | SER | LDLR-EGF-A footprint |
| 194 | ARG | Ca-bridge to LDLR D310 (key salt bridge) |
| 238 | ASP | LDLR-EGF-A footprint |
| 374 | ASP | Gain-of-function hot-spot (D374Y dramatically increases LDLR affinity) |
| 377 | THR | Adjacent to D374 H-bond network |
| 379 | PHE | F379 hydrophobic anchor (mutation reduces LDLR binding) |

---

## PCSK9-Specific Parameters

### MCP Tool: `afcycdesign_mcp.cyclic_binder_design`

| Parameter | Value |
|-----------|-------|
| `pdb` | `examples/binder_pcsk9/3P5C_PCSK9.pdb` |
| `target_chain` | `A` |
| `binder_len` | 12 |
| `hotspot` | `153,194,238,374,377,379` |
| `optimizer` | `pssm_semigreedy` |
| `num_models` | 2 |
| `ipae_threshold` | 0.15 |

### Quality Thresholds & Composite Score

Standard AfCycDesign gates from `benchmark/configs/workflows.yaml` (no PCSK9-specific override).

---

## Notes

- **Therapeutic relevance**: PCSK9-LDLR antagonism is the mechanism behind evolocumab/alirocumab (mAbs); a cyclic peptide alternative would be a strong manuscript talking point.
- **Disease-relevant**: Out of the 5 AfCycDesign benchmark targets, PCSK9 is the most clinically translationally interesting. Include in the LLM-comparison grid (per `targets.csv`).
- **PDB cleanup**: 3P5C contains chains A (PCSK9), L (LDLR fragment), P (prodomain). Make sure the runner only sees PCSK9 catalytic domain — strip the others if the workflow doesn't auto-handle multi-chain inputs.
