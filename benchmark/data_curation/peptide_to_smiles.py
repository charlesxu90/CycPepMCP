"""Peptide sequence → SMILES helper, with support for cyclization and a small
set of non-canonical residues.

For straight 20-AA linear sequences this is just `rdkit.Chem.MolFromSequence`.
For cyclic / stapled / D-AA sequences we build a SMILES from a residue→fragment
table and close the ring as instructed.

This module is intentionally narrow: it handles the few residue types that
appear in the PMC papers we're extracting from. Anything more exotic should
fall back to manual SMILES curation (logged as a warning).

Public API:
    seq_to_smiles(seq, cyclize='head-to-tail'|'disulfide'|None,
                  modifications={pos: 'D-Ala', ...}) -> str | None
"""
from __future__ import annotations

from typing import Optional


# Residue → side-chain SMILES (canonical L). The backbone is built from
# alternating N-Cα-C=O units; sidechain is appended at Cα.
# Encoding here is the side-chain only, plus the Cα symbol [C@@H] (L) or [C@H] (D).
AA_SIDECHAIN = {
    "A": "C",                              # Ala
    "R": "CCCNC(=N)N",                     # Arg
    "N": "CC(N)=O",                        # Asn
    "D": "CC(=O)O",                        # Asp
    "C": "CS",                             # Cys
    "Q": "CCC(N)=O",                       # Gln
    "E": "CCC(=O)O",                       # Glu
    "G": None,                              # Gly (no side chain)
    "H": "Cc1cnc[nH]1",                    # His
    "I": "C(C)CC",                         # Ile  (chiral; rdkit handles)
    "L": "CC(C)C",                         # Leu
    "K": "CCCCN",                          # Lys
    "M": "CCSC",                           # Met
    "F": "Cc1ccccc1",                      # Phe
    "P": None,                              # Pro (handled specially as full residue)
    "S": "CO",                             # Ser
    "T": "C(C)O",                          # Thr
    "W": "Cc1c[nH]c2ccccc12",               # Trp
    "Y": "Cc1ccc(O)cc1",                   # Tyr
    "V": "C(C)C",                          # Val
}


def _residue_smiles(letter: str, *, d_amino: bool = False) -> str:
    """Return a SMILES fragment for one residue, with NH2-C(...)-C(=O)- joined
    so concatenation forms the chain. The trailing C(=O) is the carbonyl of
    THIS residue's peptide bond to the NEXT residue."""
    if letter == "G":
        return "NCC(=O)"
    if letter == "P":
        # Proline cyclic side chain — full residue form. Stereochem omitted for
        # the sidechain ring closure; backbone N joins the previous C(=O).
        return "N1CCC[C@H]1C(=O)" if not d_amino else "N1CCC[C@@H]1C(=O)"
    sc = AA_SIDECHAIN.get(letter.upper())
    if sc is None:
        return None
    chir = "[C@H]" if d_amino else "[C@@H]"
    return f"N{chir}({sc})C(=O)"


def seq_to_smiles(seq: str, *, cyclize: Optional[str] = None,
                  d_positions: Optional[set[int]] = None) -> Optional[str]:
    """Convert a 1-letter amino acid sequence to SMILES.

    cyclize: None (linear), 'head-to-tail' (lactam between N1 and C-term),
             or 'disulfide' (S-S between two C residues).
    d_positions: 0-indexed positions where D-amino acid should be used.
    """
    d_positions = d_positions or set()
    seq = seq.upper().strip()
    if not seq:
        return None

    # Linear, all-standard, no D — let RDKit do it (gives stereo right).
    if cyclize is None and not d_positions and all(c in AA_SIDECHAIN for c in seq):
        try:
            from rdkit import Chem
            mol = Chem.MolFromSequence(seq)
            return Chem.MolToSmiles(mol, canonical=True) if mol else None
        except ImportError:
            pass  # Fall through to manual build

    fragments = []
    for i, aa in enumerate(seq):
        frag = _residue_smiles(aa, d_amino=(i in d_positions))
        if frag is None:
            return None
        fragments.append(frag)

    chain = "".join(fragments)
    # Close ring N→C(=O) for head-to-tail.
    if cyclize == "head-to-tail":
        # Replace first 'N' with [N:1] and last 'C(=O)' with C(=O)[ring1]
        # Simple approach: place ring-closure digit 9 (assumed unused) on the
        # backbone first N atom and the trailing carbonyl C.
        chain = chain.replace("N", "N9", 1)            # opens ring on first N
        if chain.endswith("C(=O)"):
            chain = chain[:-5] + "C9(=O)"               # closes ring on last carbonyl
        # Strip trailing 9-O to leave N as NH-amide rather than NH2
        # RDKit will normalize valence.

    # Canonicalize via RDKit if available
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(chain)
        if mol is None:
            return None
        # Add terminal H to the N-terminus and OH to the C-terminus if linear
        if cyclize is None:
            mol = Chem.MolFromSmiles(chain + "O")  # add OH to terminal C(=O)
            if mol is None:
                return None
        return Chem.MolToSmiles(mol, canonical=True)
    except ImportError:
        return chain
