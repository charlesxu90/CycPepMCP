# Dataset Source Survey for PD-1/PD-L1 and MDM2/p53 Predictive Modeling

**Author:** Manus AI  
**Project:** CycPepMCP: Democratizing Cyclic Peptide Design with Agentic AI  
**Date:** 11 May 2026

## Executive summary

This survey identifies literature, patents, and public dataset sources that can supplement the currently available ChEMBL data for building predictive models around **PD-1/PD-L1** and **MDM2/p53 or MDM2/MDMX/p53** peptide inhibitors. For immediate dataset expansion, the strongest sources are analog-rich papers and patent families where peptide identities and assay values are reported in tables. Public databases such as **BindingDB**, **PubChem**, **RCSB PDB**, and the **PDL1Binder** dataset can then be used for cross-checking identifiers, structural annotations, and binder/non-binder labels.[^1] [^2] [^3] [^4]

> **Recommended extraction order:** first extract analog-level tables from the papers and patents listed as **high priority**, then normalize assay values by target, target side, assay format, protein construct, and measurement type. For PD-1/PD-L1, Bristol Myers Squibb macrocyclic peptide patents and cyclic peptide papers are likely the most productive sources. For MDM2/p53, PMI/PMI-N8A mutational papers, D-peptide papers, stapled peptide papers, and Aileron/Harvard/Merck patent families are likely to yield the highest-quality labeled examples.

## Suggested extraction schema

The same schema can be used for both targets, with target-specific fields added where needed. A consistent schema will make it easier to merge ChEMBL, paper-derived, patent-derived, and database-derived records.

| Field group | Recommended fields |
| --- | --- |
| Molecule identity | `source_id`, `compound_or_peptide_name`, `sequence`, `sequence_with_modifications`, `cyclization_type`, `staple_or_linker`, `D_or_L_configuration`, `N_terminal_modification`, `C_terminal_modification`, `SMILES_or_HELM_if_available` |
| Target and assay | `target_axis`, `target_protein_bound`, `protein_construct`, `species`, `assay_type`, `assay_readout`, `assay_partner`, `cell_line_if_cellular`, `serum_condition` |
| Activity labels | `activity_type`, `activity_value`, `activity_unit`, `relation`, `converted_nM`, `negative_or_inactive_label`, `tested_concentration`, `percent_inhibition_or_blocking` |
| Source provenance | `paper_or_patent`, `doi_or_patent_number`, `table_or_example_number`, `page_or_figure`, `url`, `notes` |
| Modeling annotations | `train_val_test_group`, `duplicate_group`, `same_sequence_different_assay_flag`, `structure_available_pdb`, `confidence_score` |

## PD-1/PD-L1 papers and reviews

The PD-1/PD-L1 peptide literature is smaller than the MDM2/p53 literature, so patents and reviews are especially important. The highest-value starting point is the **J. Med. Chem.** paper on cyclic peptide inhibitors targeting PD-L1, which contains a macrocyclization scan of CLP-2-derived peptides and reports blocking data, IC50 values, and stability/selectivity measurements.[^5]

| Priority | Source | Link | What to extract |
| --- | --- | --- | --- |
| High | Discovery of Cyclic Peptide Inhibitors Targeting PD-L1 for Cancer Immunotherapy | [PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC10671706/); [DOI](https://doi.org/10.1021/acs.jmedchem.2c00539); [PubMed](https://pubmed.ncbi.nlm.nih.gov/36067356/) | Parent CLP-2 and cyclic analogs C1–C22; cyclic linkage/modification; blocking efficiency at 5 μM; IC50 for selected peptides such as C7/C12; serum stability and selectivity data.[^5] |
| High | Bioactive macrocyclic inhibitors of the PD-1/PD-L1 immune checkpoint | [PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC6400216/) | BMS macrocyclic peptide classes; PD-L1 binding and antagonism data; structural context for BMS-57/BMS-71-like macrocycles.[^6] |
| High | Development of the Inhibitors That Target the PD-1/PD-L1 Interaction—small molecules, peptides and macrocycles | [PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC6600339/) | Review tables and cited primary sources for AUNP-12, BMS macrocyclic peptides, BMS-986189, and assay types; useful map to patents and structures.[^7] |
| Medium | Structural Characterization of a Macrocyclic Peptide Inhibitor Modulating the PD-1/PD-L1 Immune Checkpoint | [MDPI full text](https://www.mdpi.com/1420-3049/26/16/4848) | Structural and binding interpretation for macrocyclic peptide inhibitors; use to annotate binding mode rather than as main potency source.[^8] |
| Medium | Target-templated de novo design of macrocyclic D-/L-peptides: discovery of drug-like inhibitors of PD-1 | [RSC full text](https://pubs.rsc.org/en/content/articlehtml/2021/sc/d1sc01031j) | D/L macrocyclic peptide design; extract peptide structures/sequences and PD-1/PD-L1 inhibition data if tabulated.[^9] |
| Medium | Blocking of the PD-1/PD-L1 interaction by a novel cyclic peptide inhibitor for cancer immunotherapy | [Springer article](https://link.springer.com/article/10.1007/s11427-020-1740-8) | Cyclic peptide inhibitor data and validation assays; likely useful for positive examples.[^10] |
| Medium | Structure-based derivation and intramolecular cyclization of peptide inhibitors from PD-1/PD-L1 complex interface | [ScienceDirect article](https://www.sciencedirect.com/science/article/pii/S0301462219302108) | Peptide derivation from interface, cyclization designs, and inhibition data.[^11] |
| Medium | Peptide-based inhibitors targeting the PD-1/PD-L1 axis | [PMC/PubMed landing](https://pmc.ncbi.nlm.nih.gov/articles/PMC10877416/); [PubMed](https://pubmed.ncbi.nlm.nih.gov/38359715/) | PD-L1-derived or PD-1-targeting peptides; likely useful for linear peptide positives and model generalization.[^12] |
| Medium | Structure-Guided Discovery of PD-1/PD-L1 Interaction Inhibitors | [ACS article](https://pubs.acs.org/doi/10.1021/acs.jcim.3c01500) | Phage-display and computationally modified peptide inhibitor data, potentially with analog tables.[^13] |
| Medium | Rational design of potent peptide inhibitors of the PD-1:PD-L1 interaction for cancer immunotherapy | [ACS/JACS article](https://pubs.acs.org/doi/abs/10.1021/jacs.1c08132) | Potent designed peptides and binding/blocking data, useful for non-cyclic and possibly engineered peptide examples.[^14] |
| Lower | Discovery of low-molecular weight anti-PD-L1 peptides for cancer immunotherapy | [Journal for ImmunoTherapy of Cancer](https://link.springer.com/article/10.1186/s40425-019-0705-y) | Low-molecular-weight anti-PD-L1 peptides such as CLP001; useful for additional positives and negative controls if available.[^15] |

## PD-1/PD-L1 patents and patent reviews

PD-1/PD-L1 macrocyclic peptide patents are likely to provide the largest number of examples beyond ChEMBL. The BMS macrocyclic peptide families are particularly important because review articles report numerous examples and HTRF/ELISA-type PD-1/PD-L1 assay values.[^16] [^17]

| Priority | Patent or review | Link | What to extract |
| --- | --- | --- | --- |
| High | Macrocyclic inhibitors of the PD-1/PD-L1 and CD80(B7-1)/PD-L1 protein/protein interactions, WO2014151634A1 | [Google Patents](https://patents.google.com/patent/WO2014151634A1/en); [PDF](https://patentimages.storage.googleapis.com/4f/81/be/db293d9819407a/WO2014151634A1.pdf) | BMS macrocyclic peptide examples, assay descriptions, HTRF/PD-1/PD-L1 inhibition values, CD80/PD-L1 data, structural/chemical definitions.[^16] |
| High | Macrocyclic inhibitors of the PD-1/PD-L1 and CD80(B7-1)/PD-L1 interactions, WO2016039749A1 | [Google Patents](https://patents.google.com/patent/WO2016039749A1/en); [PDF](https://patentimages.storage.googleapis.com/69/2c/ab/0e82a60c2a1b04/WO2016039749A1.pdf) | Follow-on BMS macrocyclic peptide examples; likely expanded SAR and assay values.[^17] |
| High | A patent review on PD-1/PD-L1 antagonists: small molecules, peptides and macrocycles (2015–2018) | [PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC6323140/); [DOI](https://doi.org/10.1080/13543776.2018.1512706) | Patent-family roadmap; identifies BMS macrocyclic peptide examples and reports that BMS example 68 reached low-nM IC50 in HTRF assay.[^18] |
| Medium | An updated patent review on PD-1/PD-L1 antagonists (2022–present) | [Taylor & Francis full text](https://www.tandfonline.com/doi/full/10.1080/13543776.2024.2368237) | Newer patent families after 2022; use to avoid missing recent cyclic peptide or peptidomimetic filings.[^19] |
| Medium | PD-L1 binding peptide and use thereof, KR-102150419-B1 | [PubChem patent summary](https://pubchem.ncbi.nlm.nih.gov/patent/KR-102150419-B1) | PD-L1 binding peptide patent; useful for sequence/claim extraction and possible activity examples.[^20] |
| Medium | Patent US-2019092863-A1 | [PubChem patent summary](https://pubchem.ncbi.nlm.nih.gov/patent/US-2019092863-A1) | PubChem patent summary potentially connected to PD-1/PD-L1 inhibitors; inspect for assay examples and linked substances.[^21] |
| Medium | Process Development of a Macrocyclic Peptide Inhibitor of PD-L1 | [ACS JOC article](https://pubs.acs.org/doi/10.1021/acs.joc.4c00430) | Process-development source for BMS-986189; use mainly to confirm identity and manufacturing route rather than analog activity.[^22] |

## MDM2/p53 and MDM2/MDMX papers

The MDM2/p53 peptide literature contains several well-structured datasets with peptide sequences and quantitative Kd values. These are immediately useful for supervised regression or classification, particularly if the model includes MDMX as a second target label.[^23] [^24]

| Priority | Source | Link | What to extract |
| --- | --- | --- | --- |
| High | Systematic Mutational Analysis of Peptide Inhibition of the p53-MDM2/MDMX Interactions | [PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC2856455/) | PMI, PMI analogs, p53(17–28) analogs, truncation analogs; Kd values for both MDM2 and MDMX; one of the best structured peptide datasets.[^23] |
| High | A left handed solution to peptide inhibition of the p53-MDM2 interaction | [PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC3359147/) | D-PMI-alpha, D-PMI-beta, alanine/substitution analogs; Table 1 contains sequences and MDM2 Kd values.[^24] |
| High | Structural basis for high-affinity peptide inhibition of p53 interactions with MDM2 and MDMX | [PNAS article](https://www.pnas.org/doi/10.1073/pnas.0900947106) | PMI and related high-affinity MDM2/MDMX peptide data; structural basis and binding constants.[^25] |
| High | Stapled α-helical peptide drug development: ATSP-7041 | [PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC3767549/) | ATSP-7041 and related stapled peptide optimization; nanomolar MDM2/MDMX affinities, cellular activity, and structural data.[^26] |
| High | Discovery of Sulanemadlin (ALRN-6924), the First Cell-Permeating Stapled Peptide Clinical Candidate | [ACS J. Med. Chem.](https://pubs.acs.org/doi/10.1021/acs.jmedchem.3c00623); [PubMed](https://pubmed.ncbi.nlm.nih.gov/37439511/) | Likely the most important ALRN-6924 optimization paper; extract analog-level binding, cellular, and developability tables.[^27] |
| High | Design of stapled peptide-based PROTACs for MDM2/MDMX atypical degradation and tumor suppression | [PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC9516243/) | SPMI-based stapled peptide PROTACs; FP binding assays for MDM2/MDMX, cellular killing, degradation, and PK data.[^28] |
| Medium | Angler Peptides: Macrocyclic Conjugates Inhibit p53:MDM2/X | [ACS Chemical Biology](https://pubs.acs.org/doi/10.1021/acschembio.0c00988); [author PDF](https://espace.library.uq.edu.au/view/UQ:995c6c0/Angler_espace.pdf) | cTAT/KD3 macrocyclic conjugates; MDM2/MDMX binding affinity, cell entry, and p53-pathway reactivation data.[^29] |
| Medium | Artificial Macrocycles as Potent p53–MDM2 Inhibitors | [ACS Med. Chem. Lett.](https://pubs.acs.org/doi/10.1021/acsmedchemlett.7b00219) | Artificial macrocyclic inhibitor library; useful for non-stapled macrocycle examples and inhibition values.[^30] |
| Medium | Study on the design, synthesis, and activity of anti-tumor MDM2/MDMX staple peptides | [Frontiers full text](https://www.frontiersin.org/journals/chemistry/articles/10.3389/fchem.2024.1403473/full) | PMI-M3-based dual-targeting stapled peptide series; extract binding and cell activity values.[^31] |
| Medium | Structure-based designing efficient peptides based on p53 binding site residues to disrupt p53-MDM2/X interaction | [Nature Scientific Reports](https://www.nature.com/articles/s41598-020-67510-8) | Computational and experimental design of MDM2/MDMX dual-targeting peptides; useful for additional designed sequence examples.[^32] |
| Medium | Design and development of high affinity dual anticancer peptide-inhibitors against p53-MDM2/X interaction | [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0024320520301053) | Large-scale peptide mutation screening and candidate dual inhibitors; potentially useful if tables are accessible.[^33] |
| Lower | Phase 1 Trial of ALRN-6924 | [PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC9401461/) | Clinical translation and pharmacodynamic biomarker data; not analog-rich, but useful as validated clinical positive reference.[^34] |
| Lower | Binding Ensembles of p53-MDM2 Peptide Inhibitors | [PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC7795311/) | Smaller peptide set and structural ensemble modeling; useful for benchmarking computational features.[^35] |

## MDM2/p53 and MDM2/MDMX patents and patent reviews

For MDM2/p53, patents are especially useful for stapled peptides and all-D peptidomimetic macrocycles. The Aileron, Harvard/Dana-Farber, and Merck/A*STAR/Organon families should be inspected in detail because they contain many example compounds and assay descriptions.[^36] [^37] [^38]

| Priority | Patent or review | Link | What to extract |
| --- | --- | --- | --- |
| High | P53 activator peptidomimetic macrocycles, WO2020257133A1 | [Google Patents](https://patents.google.com/patent/WO2020257133A1/en); [PDF](https://patentimages.storage.googleapis.com/2c/a7/9d/551bd3e5a7cb47/WO2020257133A1.pdf) | All-D peptidomimetic macrocycles binding MDM2/MDMX; likely examples, affinity bins, cell permeability, p53 activation data.[^36] |
| High | Peptidomimetic macrocycles, US10967042B2 | [Google Patents](https://patents.google.com/patent/US10967042B2/en); [PDF](https://patentimages.storage.googleapis.com/2c/93/eb/74b95f8b735987/US10967042.pdf) | Aileron/Roche peptidomimetic macrocycles; many example structures and likely MDM2/MDMX assay values.[^37] |
| High | Stabilized p53 peptides and uses thereof, US9527896B2 | [Google Patents](https://patents.google.com/patent/US9527896B2/en); [PDF](https://patentimages.storage.googleapis.com/8b/91/45/96c1c143da45cb/US9527896.pdf) | Harvard/Dana-Farber stapled p53 peptides; fluorescence-polarization assays to MDM2/MDMX, sequences, and cellular examples.[^38] |
| Medium | Inhibitors of the interaction between p53 and MDM2, US7083983B2 | [Google Patents](https://patents.google.com/patent/US7083983B2/en) | Earlier MDM2-binding inhibitor patent; mainly useful for background and small-molecule/peptidomimetic comparator data.[^39] |
| Medium | An update patent review of MDM2-p53 interaction inhibitors (2019–2023) | [PubMed](https://pubmed.ncbi.nlm.nih.gov/39435470/); [Taylor & Francis](https://www.tandfonline.com/doi/abs/10.1080/13543776.2024.2419836) | Roadmap to newer patent families, including peptidomimetic macrocycles and assay formats.[^40] |
| Medium | A therapeutic patent overview of MDM2/X-targeted therapies (2014–2018) | [Taylor & Francis](https://www.tandfonline.com/doi/abs/10.1080/13543776.2019.1582645) | Earlier patent landscape covering peptidomimetics and MDM2/X therapies.[^41] |

## Public databases and structured datasets beyond ChEMBL

These sources should not replace manual extraction from PDFs, because peptide modifications and macrocyclization details are often lost or inconsistently represented in structured databases. However, they are valuable for cross-validation, duplicate detection, target/protein IDs, and structural annotations.

| Source | Link | How to use it |
| --- | --- | --- |
| BindingDB | [Home](https://www.bindingdb.org/) | Query MDM2/MDM4/PD-L1 targets and export Ki/IC50/Kd rows. Search results show MDM2 ligand pages, MDM2/MDM4 TR-FRET records, and PD-L1 macrocyclic peptide examples.[^1] |
| BindingDB MDM2 example record | [BDBM50237739 / CHEMBL4091801](https://www.bindingdb.org/bind/chemsearch/marvin/MolStructure.jsp?monomerid=50237739) | Example of BindingDB activity record for MDM2 inhibition; use as an entry point for related ligand-target pairs.[^42] |
| BindingDB MDM2/p53-MDM4 TR-FRET search | [BindingDB search result](https://bindingdb.org/rwd/jsp/dbsearch/PrimarySearch_ki.jsp?polymerid=10191,3720,8690,776,629,494,400,8689&complexid=213,50004308,50004102,50003613&blastSeq=UNIPROT:Q00987&tag=blastic50&column=IC50&energyterm=kcal%2Fmole&startPg=0&Increment=50&submit=Search) | Potential exportable set for p53-MDM2 and p53-MDM4 TR-FRET inhibition records.[^43] |
| BindingDB PD-L1 macrocyclic peptide example | [BDBM581055](https://bindingdb.org/rwd/bind/chemsearch/marvin/MolStructure.jsp?monomerid=581055&column=KI&sort=yes&energyterm=kJ/mole) | Search result identifies a PD-L1 macrocyclic peptide patent example assayed by PD-1/PD-L1 HTRF.[^44] |
| PubChem | [Home](https://pubchem.ncbi.nlm.nih.gov/) | Search patent numbers and assay IDs; useful for linked substances and patent summaries, especially for PD-L1 peptide patents.[^2] |
| RCSB PDB | [Home](https://www.rcsb.org/) | Add structure-availability annotations. Examples include [PD-L1 macrocyclic inhibitor complex 5O45](https://www.rcsb.org/structure/5o45) and [MDM2/p53 peptide complex 4HFZ](https://www.rcsb.org/structure/4HFZ).[^3] [^45] [^46] |
| PDL1Binder dataset and server | [Web server](http://i.uestc.edu.cn/pdl1binder/cgi-bin/PDL1Binder.pl); [paper](https://www.frontiersin.org/journals/microbiology/articles/10.3389/fmicb.2022.928774/full) | Useful for PD-L1 binding peptide classification. The paper reports a positive dataset of 80 PD-L1 binding peptides from next-generation phage display and non-binding/control peptides.[^4] |
| iPPI-DB | [Database](https://ippidb.pasteur.fr/) | Curated PPI inhibitor database, primarily small molecules rather than peptides; useful for MDM2/p53 small-molecule comparators and PPI benchmark context.[^47] |

## Practical extraction priorities

For **PD-1/PD-L1**, the first extraction pass should focus on the cyclic peptide inhibitor paper, the BMS macrocyclic peptide patents, and the macrocyclic peptide review/structure papers. This combination should provide positive examples with potency values, inactive or weaker analogs from SAR tables, and structure labels. The **PDL1Binder** dataset is valuable for sequence-level binder/non-binder pretraining, but it should be treated separately from cyclic peptide potency data because its labels come from phage-display enrichment and classifier construction rather than standardized biochemical IC50 measurements.[^4] [^5] [^16] [^17]

For **MDM2/p53**, begin with the systematic PMI mutational paper and D-PMI paper because they already contain clean peptide sequence-to-Kd tables. Next, extract stapled peptide and peptidomimetic macrocycle data from ATSP-7041, ALRN-6924, and the Aileron/Harvard/Merck patent families. These sources should give a broader modality range, including linear peptides, all-D peptides, hydrocarbon-stapled peptides, artificial macrocycles, and peptide-PROTACs.[^23] [^24] [^26] [^27] [^36] [^37] [^38]

## References

[^1]: [BindingDB](https://www.bindingdb.org/), public binding-affinity database.
[^2]: [PubChem](https://pubchem.ncbi.nlm.nih.gov/), public compound, substance, assay, and patent database.
[^3]: [RCSB Protein Data Bank](https://www.rcsb.org/), structural biology database.
[^4]: [PDL1Binder: Identifying programmed cell death ligand 1 binding peptides](https://www.frontiersin.org/journals/microbiology/articles/10.3389/fmicb.2022.928774/full).
[^5]: [Discovery of Cyclic Peptide Inhibitors Targeting PD-L1 for Cancer Immunotherapy](https://pmc.ncbi.nlm.nih.gov/articles/PMC10671706/).
[^6]: [Bioactive macrocyclic inhibitors of the PD-1/PD-L1 immune checkpoint](https://pmc.ncbi.nlm.nih.gov/articles/PMC6400216/).
[^7]: [Development of the Inhibitors That Target the PD-1/PD-L1 Interaction](https://pmc.ncbi.nlm.nih.gov/articles/PMC6600339/).
[^8]: [Structural Characterization of a Macrocyclic Peptide Inhibitor Modulating the PD-1/PD-L1 Immune Checkpoint](https://www.mdpi.com/1420-3049/26/16/4848).
[^9]: [Target-templated de novo design of macrocyclic D-/L-peptides](https://pubs.rsc.org/en/content/articlehtml/2021/sc/d1sc01031j).
[^10]: [Blocking of the PD-1/PD-L1 interaction by a novel cyclic peptide inhibitor](https://link.springer.com/article/10.1007/s11427-020-1740-8).
[^11]: [Structure-based derivation and intramolecular cyclization of peptide inhibitors from PD-1/PD-L1 complex interface](https://www.sciencedirect.com/science/article/pii/S0301462219302108).
[^12]: [Peptide-based inhibitors targeting the PD-1/PD-L1 axis](https://pubmed.ncbi.nlm.nih.gov/38359715/).
[^13]: [Structure-Guided Discovery of PD-1/PD-L1 Interaction Inhibitors](https://pubs.acs.org/doi/10.1021/acs.jcim.3c01500).
[^14]: [Rational design of potent peptide inhibitors of the PD-1:PD-L1 interaction](https://pubs.acs.org/doi/abs/10.1021/jacs.1c08132).
[^15]: [Discovery of low-molecular weight anti-PD-L1 peptides for cancer immunotherapy](https://link.springer.com/article/10.1186/s40425-019-0705-y).
[^16]: [WO2014151634A1, Macrocyclic inhibitors of the PD-1/PD-L1 and CD80(B7-1)/PD-L1 interactions](https://patents.google.com/patent/WO2014151634A1/en).
[^17]: [WO2016039749A1, Macrocyclic inhibitors of the PD-1/PD-L1 and CD80(B7-1)/PD-L1 interactions](https://patents.google.com/patent/WO2016039749A1/en).
[^18]: [A patent review on PD-1/PD-L1 antagonists: small molecules, peptides and macrocycles (2015–2018)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6323140/).
[^19]: [An updated patent review on PD-1/PD-L1 antagonists (2022–present)](https://www.tandfonline.com/doi/full/10.1080/13543776.2024.2368237).
[^20]: [PubChem patent KR-102150419-B1, PD-L1 binding peptide and use thereof](https://pubchem.ncbi.nlm.nih.gov/patent/KR-102150419-B1).
[^21]: [PubChem patent US-2019092863-A1](https://pubchem.ncbi.nlm.nih.gov/patent/US-2019092863-A1).
[^22]: [Process Development of a Macrocyclic Peptide Inhibitor of PD-L1](https://pubs.acs.org/doi/10.1021/acs.joc.4c00430).
[^23]: [Systematic Mutational Analysis of Peptide Inhibition of the p53-MDM2/MDMX Interactions](https://pmc.ncbi.nlm.nih.gov/articles/PMC2856455/).
[^24]: [A left handed solution to peptide inhibition of the p53-MDM2 interaction](https://pmc.ncbi.nlm.nih.gov/articles/PMC3359147/).
[^25]: [Structural basis for high-affinity peptide inhibition of p53 interactions with MDM2 and MDMX](https://www.pnas.org/doi/10.1073/pnas.0900947106).
[^26]: [Stapled α-helical peptide drug development: ATSP-7041](https://pmc.ncbi.nlm.nih.gov/articles/PMC3767549/).
[^27]: [Discovery of Sulanemadlin (ALRN-6924)](https://pubs.acs.org/doi/10.1021/acs.jmedchem.3c00623).
[^28]: [Design of stapled peptide-based PROTACs for MDM2/MDMX atypical degradation](https://pmc.ncbi.nlm.nih.gov/articles/PMC9516243/).
[^29]: [Angler Peptides: Macrocyclic Conjugates Inhibit p53:MDM2/X](https://pubs.acs.org/doi/10.1021/acschembio.0c00988).
[^30]: [Artificial Macrocycles as Potent p53–MDM2 Inhibitors](https://pubs.acs.org/doi/10.1021/acsmedchemlett.7b00219).
[^31]: [Study on the design, synthesis, and activity of anti-tumor MDM2/MDMX staple peptides](https://www.frontiersin.org/journals/chemistry/articles/10.3389/fchem.2024.1403473/full).
[^32]: [Structure-based designing efficient peptides based on p53 binding site residues](https://www.nature.com/articles/s41598-020-67510-8).
[^33]: [Design and development of high affinity dual anticancer peptide-inhibitors against p53-MDM2/X interaction](https://www.sciencedirect.com/science/article/pii/S0024320520301053).
[^34]: [Phase 1 Trial of ALRN-6924](https://pmc.ncbi.nlm.nih.gov/articles/PMC9401461/).
[^35]: [Binding Ensembles of p53-MDM2 Peptide Inhibitors](https://pmc.ncbi.nlm.nih.gov/articles/PMC7795311/).
[^36]: [WO2020257133A1, P53 activator peptidomimetic macrocycles](https://patents.google.com/patent/WO2020257133A1/en).
[^37]: [US10967042B2, Peptidomimetic macrocycles](https://patents.google.com/patent/US10967042B2/en).
[^38]: [US9527896B2, Stabilized p53 peptides and uses thereof](https://patents.google.com/patent/US9527896B2/en).
[^39]: [US7083983B2, Inhibitors of the interaction between p53 and MDM2](https://patents.google.com/patent/US7083983B2/en).
[^40]: [An update patent review of MDM2-p53 interaction inhibitors (2019–2023)](https://pubmed.ncbi.nlm.nih.gov/39435470/).
[^41]: [A therapeutic patent overview of MDM2/X-targeted therapies (2014–2018)](https://www.tandfonline.com/doi/abs/10.1080/13543776.2019.1582645).
[^42]: [BindingDB record BDBM50237739](https://www.bindingdb.org/bind/chemsearch/marvin/MolStructure.jsp?monomerid=50237739).
[^43]: [BindingDB MDM2/p53-MDM4 TR-FRET search](https://bindingdb.org/rwd/jsp/dbsearch/PrimarySearch_ki.jsp?polymerid=10191,3720,8690,776,629,494,400,8689&complexid=213,50004308,50004102,50003613&blastSeq=UNIPROT:Q00987&tag=blastic50&column=IC50&energyterm=kcal%2Fmole&startPg=0&Increment=50&submit=Search).
[^44]: [BindingDB record BDBM581055](https://bindingdb.org/rwd/bind/chemsearch/marvin/MolStructure.jsp?monomerid=581055&column=KI&sort=yes&energyterm=kJ/mole).
[^45]: [RCSB PDB 5O45](https://www.rcsb.org/structure/5o45).
[^46]: [RCSB PDB 4HFZ](https://www.rcsb.org/structure/4HFZ).
[^47]: [iPPI-DB](https://ippidb.pasteur.fr/).
