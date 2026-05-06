#!/usr/bin/env python3
"""Take Phase-1 PASS candidates, convert HELM->SMILES via the upstream HELM-GPT
function, count heavy atoms via RDKit, route into Track A (Boltz-2 affinity,
<=128 atoms) and Track B (AF3, all candidates), and cap to a budget.

Inputs:  <run_dir>/phase1_filtered.csv (produced by postprocess_phase1.py)
Outputs: <run_dir>/phase2_candidates.csv (top-N, with smiles, n_heavy, track)
         <run_dir>/phase2_routing_summary.json

Run from the project root with the helm_gpt env_py3.7 interpreter:
  tool-mcps/helm_gpt_mcp/env_py3.7/bin/python \\
    examples/case3_kras_perm_opt_helmgpt/postprocess_phase2_prep.py \\
    <run_dir> --top 20
"""
import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HELM_REPO = REPO_ROOT / "tool-mcps" / "helm_gpt_mcp" / "repo" / "helm-gpt"


def load_upstream_helm_utils():
    """Import upstream get_cycpep_smi_from_helm with cwd swap (it loads
    monomer_library.csv via a relative path at module import time)."""
    sys.path.insert(0, str(HELM_REPO))
    cwd = os.getcwd()
    os.chdir(str(HELM_REPO))
    try:
        from utils.helm_utils import get_cycpep_smi_from_helm, is_helm_valid
        return get_cycpep_smi_from_helm, is_helm_valid
    finally:
        os.chdir(cwd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--top", type=int, default=20, help="Cap for Phase-2 (AF3 budget)")
    ap.add_argument("--threshold", type=int, default=128, help="Heavy-atom threshold for Track A")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    flt = run_dir / "phase1_filtered.csv"
    if not flt.exists():
        print(f"error: {flt} missing — run postprocess_phase1.py first", file=sys.stderr)
        return 1

    df = pd.read_csv(flt)
    print(f"Input PASS candidates : {len(df)}")

    get_smi, is_valid = load_upstream_helm_utils()
    from rdkit import Chem

    smiles, heavy = [], []
    n_smiles_fail = 0
    n_helm_invalid = 0
    for h in df["helm_seqs"]:
        if not is_valid(h):
            smiles.append(None); heavy.append(None); n_helm_invalid += 1
            continue
        try:
            s = get_smi(h)
        except Exception:
            s = None
        if not s:
            smiles.append(None); heavy.append(None); n_smiles_fail += 1
            continue
        try:
            mol = Chem.MolFromSmiles(s)
            n = mol.GetNumHeavyAtoms() if mol is not None else None
        except Exception:
            n = None
        smiles.append(s); heavy.append(n)

    df = df.assign(smiles=smiles, n_heavy_atoms=heavy)
    pre = len(df)
    df = df.dropna(subset=["smiles", "n_heavy_atoms"]).reset_index(drop=True)
    print(f"  HELM invalid     : {n_helm_invalid}")
    print(f"  SMILES fail      : {n_smiles_fail}")
    print(f"  RDKit/heavy fail : {pre - len(df) - n_smiles_fail - n_helm_invalid}")
    print(f"Valid candidates with SMILES : {len(df)}")

    df["track"] = df["n_heavy_atoms"].apply(lambda n: "A+B" if n <= args.threshold else "B")
    df = df.sort_values("sum", ascending=False).reset_index(drop=True)
    df_top = df.head(args.top).copy().reset_index(drop=True)
    df_top["rank"] = df_top.index + 1

    out = run_dir / "phase2_candidates.csv"
    df_top.to_csv(out, index=False)

    summary = {
        "run_dir": str(run_dir),
        "input_pass": int(pre),
        "with_valid_smiles": int(len(df)),
        "track_a_plus_b": int((df["track"] == "A+B").sum()),
        "track_b_only": int((df["track"] == "B").sum()),
        "top_cap": args.top,
        "selected": len(df_top),
        "selected_track_a_plus_b": int((df_top["track"] == "A+B").sum()),
        "selected_track_b_only": int((df_top["track"] == "B").sum()),
        "heavy_atom_threshold": args.threshold,
        "heavy_atoms_distribution_top": {
            "min": int(df_top["n_heavy_atoms"].min()),
            "median": float(df_top["n_heavy_atoms"].median()),
            "max": int(df_top["n_heavy_atoms"].max()),
        },
    }
    sum_path = run_dir / "phase2_routing_summary.json"
    sum_path.write_text(json.dumps(summary, indent=2))

    print()
    for k, v in summary.items():
        print(f"  {k:30s}: {v}")
    print(f"\nwrote: {out}")
    print(f"wrote: {sum_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
