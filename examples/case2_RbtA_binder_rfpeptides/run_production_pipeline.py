#!/usr/bin/env python3
"""
RbtA Production Pipeline: Full 5-stage binder design for 50 backbones.

Stage 2: 4 rounds of ProteinMPNN CA-only + Rosetta FastRelax
Stage 3: AfCycDesign complex prediction validation
Stage 4: Rosetta interface metrics (ddG, SAP, CMS)
Stage 5: Ranking and summary

Usage:
    python run_production_pipeline.py 2>&1 | tee pipeline.log
"""

import os
import sys
import csv
import json
import time
import glob
import subprocess
from pathlib import Path
from datetime import datetime

# ============================================================
# Configuration
# ============================================================
BASE_DIR = Path("/home/xux/Desktop/AgentMCP/CycPepMCP/examples/case2_RbtA_binder_rfpeptides")
BACKBONE_DIR = BASE_DIR / "results" / "prod_backbones"
RESULTS_DIR = BASE_DIR / "results" / "prod_pipeline"
TARGET_PDB = BASE_DIR / "RbtA_monomer_relaxed.pdb"

# Tool paths
MPNN_PYTHON = "/mnt/data/done_projects/2026/BioMolMCP/ProteinMCP/tool-mcps/proteinmpnn_mcp/env/bin/python3.10"
MPNN_SCRIPT = "/mnt/data/done_projects/2026/BioMolMCP/ProteinMCP/tool-mcps/proteinmpnn_mcp/repo/ProteinMPNN/protein_mpnn_run.py"
MPNN_WEIGHTS = "/mnt/data/done_projects/2026/BioMolMCP/ProteinMCP/tool-mcps/proteinmpnn_mcp/examples/data/ca_model_weights"

ROSETTA_PYTHON = "/mnt/data/done_projects/2026/BioMolMCP/CycPepMCP/tool-mcps/rosetta_kic_mcp/env/bin/python"
ROSETTA_RELAX = "/mnt/data/done_projects/2026/BioMolMCP/CycPepMCP/tool-mcps/rosetta_kic_mcp/scripts/cycpep_fast_relax.py"
ROSETTA_METRICS = "/mnt/data/done_projects/2026/BioMolMCP/CycPepMCP/tool-mcps/rosetta_kic_mcp/scripts/interface_metrics.py"

AFCYC_PYTHON = "/mnt/data/done_projects/2026/BioMolMCP/CycPepMCP/tool-mcps/afcycdesign_mcp/env/bin/python"
AFCYC_SCRIPT = "/mnt/data/done_projects/2026/BioMolMCP/CycPepMCP/tool-mcps/afcycdesign_mcp/scripts/cycpep_target_complex_pred.py"

# Design parameters
NUM_ROUNDS = 4
MPNN_TEMP = 0.0001
MPNN_MODEL = "v_48_020"
OMIT_AAS = "C"

# Amino acid 1-to-3 letter map
AA_MAP = {
    'A': 'ALA', 'R': 'ARG', 'N': 'ASN', 'D': 'ASP', 'E': 'GLU',
    'Q': 'GLN', 'G': 'GLY', 'H': 'HIS', 'I': 'ILE', 'L': 'LEU',
    'K': 'LYS', 'M': 'MET', 'F': 'PHE', 'P': 'PRO', 'S': 'SER',
    'T': 'THR', 'W': 'TRP', 'Y': 'TYR', 'V': 'VAL', 'X': 'ALA',
}


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def thread_sequence(input_pdb, output_pdb, sequence, chain='A'):
    """Thread a designed sequence onto a backbone PDB."""
    seq_idx = 0
    prev_resnum = None
    with open(input_pdb) as f, open(output_pdb, 'w') as out:
        for line in f:
            if line.startswith(('ATOM', 'HETATM')):
                ch = line[21]
                resnum = line[22:26].strip()
                if ch == chain:
                    if resnum != prev_resnum:
                        prev_resnum = resnum
                        if seq_idx < len(sequence):
                            new_res = AA_MAP[sequence[seq_idx]]
                            seq_idx += 1
                        else:
                            new_res = line[17:20]
                    line = line[:17] + f"{new_res:>3}" + line[20:]
                out.write(line)
            else:
                out.write(line)
    return seq_idx


def run_proteinmpnn(input_pdb, output_dir):
    """Run ProteinMPNN CA-only design. Returns designed sequence or None."""
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        MPNN_PYTHON, MPNN_SCRIPT,
        "--pdb_path", str(input_pdb),
        "--pdb_path_chains", "A",
        "--out_folder", str(output_dir),
        "--num_seq_per_target", "1",
        "--sampling_temp", str(MPNN_TEMP),
        "--seed", "37",
        "--model_name", MPNN_MODEL,
        "--batch_size", "1",
        "--path_to_model_weights", MPNN_WEIGHTS,
        "--ca_only",
        "--omit_AAs", OMIT_AAS,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        log(f"  ProteinMPNN FAILED: {result.stderr[-200:]}")
        return None

    # Parse FASTA output
    fa_files = glob.glob(os.path.join(output_dir, "seqs", "*.fa"))
    if not fa_files:
        log("  No FASTA output found")
        return None

    sequences = []
    with open(fa_files[0]) as f:
        for line in f:
            if not line.startswith(">"):
                sequences.append(line.strip())

    # Return the designed sequence (second entry; first is the input GLY sequence)
    if len(sequences) >= 2:
        return sequences[1]
    elif sequences:
        return sequences[0]
    return None


def run_rosetta_relax(input_pdb, output_dir, rounds=4):
    """Run Rosetta FastRelax with PeptideCyclizeMover. Returns path to best relaxed PDB."""
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        ROSETTA_PYTHON, ROSETTA_RELAX,
        "--input", str(input_pdb),
        "--output", str(output_dir),
        "--rounds", str(rounds),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    if result.returncode != 0:
        log(f"  Rosetta relax FAILED: {result.stderr[-300:]}")
        return None

    # Find the last round PDB (best relaxed)
    stem = Path(input_pdb).stem
    round_pdbs = sorted(glob.glob(os.path.join(output_dir, f"{stem}_round*.pdb")))
    if round_pdbs:
        return round_pdbs[-1]  # Last round = most relaxed

    # Fallback: any PDB in output
    all_pdbs = sorted(glob.glob(os.path.join(output_dir, "*.pdb")))
    return all_pdbs[-1] if all_pdbs else None


def run_afcycdesign(sequence, output_pdb):
    """Run AfCycDesign complex prediction. Returns metrics dict or None."""
    cmd = [
        AFCYC_PYTHON, AFCYC_SCRIPT,
        "--pdb", str(TARGET_PDB),
        "--target_chain", "A",
        "--peptide_seq", sequence,
        "--num_recycles", "6",
        "--num_models", "2",
        "--save_json",
        "--output", str(output_pdb),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        log(f"  AfCycDesign FAILED: {result.stderr[-200:]}")
        return None

    # Parse JSON metrics
    json_path = str(output_pdb).replace(".pdb", ".json")
    if os.path.exists(json_path):
        with open(json_path) as f:
            return json.load(f)
    return None


def run_interface_metrics(input_pdbs, output_dir, peptide_chain="A"):
    """Run Rosetta interface metrics on a batch of PDBs. Returns CSV path."""
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        ROSETTA_PYTHON, ROSETTA_METRICS,
        "--input",
    ] + [str(p) for p in input_pdbs] + [
        "--output", str(output_dir),
        "--peptide_chain", peptide_chain,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        log(f"  Interface metrics FAILED: {result.stderr[-300:]}")
        return None

    csv_path = os.path.join(output_dir, "interface_metrics.csv")
    return csv_path if os.path.exists(csv_path) else None


def get_checkpoint():
    """Load checkpoint to resume from."""
    ckpt_path = RESULTS_DIR / "checkpoint.json"
    if ckpt_path.exists():
        with open(ckpt_path) as f:
            return json.load(f)
    return {"stage2": {}, "stage3": {}, "stage4_done": False}


def save_checkpoint(ckpt):
    """Save checkpoint for resumability."""
    with open(RESULTS_DIR / "checkpoint.json", "w") as f:
        json.dump(ckpt, f, indent=2)


# ============================================================
# Main Pipeline
# ============================================================
def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # Get all backbone PDBs
    backbones = sorted(glob.glob(str(BACKBONE_DIR / "*.pdb")))
    n_designs = len(backbones)
    log(f"Starting production pipeline: {n_designs} backbones")

    ckpt = get_checkpoint()

    # ============================================================
    # STAGE 2: Iterative Sequence Design (4 rounds)
    # ============================================================
    log("=" * 60)
    log("STAGE 2: Iterative Sequence Design (4 rounds)")
    log("=" * 60)

    stage2_dir = RESULTS_DIR / "stage2"
    os.makedirs(stage2_dir, exist_ok=True)

    # Track sequences and final structures per design
    final_sequences = {}
    final_structures = {}

    for i, backbone in enumerate(backbones):
        design_name = Path(backbone).stem
        design_id = f"d{i:02d}"

        # Check checkpoint
        if design_id in ckpt["stage2"] and ckpt["stage2"][design_id].get("completed"):
            log(f"[{i+1}/{n_designs}] {design_id} - SKIPPED (checkpoint)")
            final_sequences[design_id] = ckpt["stage2"][design_id]["sequence"]
            final_structures[design_id] = ckpt["stage2"][design_id]["structure"]
            continue

        log(f"[{i+1}/{n_designs}] {design_id} ({design_name})")

        try:
            current_pdb = backbone
            current_seq = None

            for rnd in range(1, NUM_ROUNDS + 1):
                rnd_dir = stage2_dir / design_id / f"round{rnd}"

                # Step A: ProteinMPNN
                mpnn_dir = rnd_dir / "mpnn"
                seq = run_proteinmpnn(current_pdb, mpnn_dir)
                if seq is None:
                    log(f"  Round {rnd}: ProteinMPNN failed, stopping this design")
                    break
                # Replace any 'X' residues with 'A' (alanine)
                seq = seq.replace('X', 'A')
                current_seq = seq
                log(f"  Round {rnd}: MPNN -> {seq}")

                # Thread sequence
                threaded_pdb = rnd_dir / f"{design_id}_r{rnd}_threaded.pdb"
                thread_sequence(current_pdb, threaded_pdb, seq, chain='A')

                # Step B: Rosetta FastRelax
                relax_dir = rnd_dir / "relax"
                relaxed_pdb = run_rosetta_relax(threaded_pdb, relax_dir, rounds=4)
                if relaxed_pdb is None:
                    log(f"  Round {rnd}: Rosetta relax failed, using threaded PDB")
                    current_pdb = str(threaded_pdb)
                else:
                    current_pdb = relaxed_pdb
                    log(f"  Round {rnd}: Relaxed -> {Path(relaxed_pdb).name}")
        except Exception as e:
            log(f"  ERROR: {e}")
            current_seq = None

        if current_seq:
            final_sequences[design_id] = current_seq
            final_structures[design_id] = current_pdb

            # Copy final structure
            final_pdb = stage2_dir / f"{design_id}_final.pdb"
            import shutil
            shutil.copy2(current_pdb, final_pdb)
            final_structures[design_id] = str(final_pdb)

            # Save checkpoint
            ckpt["stage2"][design_id] = {
                "completed": True,
                "sequence": current_seq,
                "structure": str(final_pdb),
            }
            save_checkpoint(ckpt)
            log(f"  FINAL: {current_seq}")
        else:
            log(f"  FAILED: No sequence designed for {design_id}")

    # Save sequence summary
    seq_csv = stage2_dir / "sequences.csv"
    with open(seq_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["design_id", "sequence", "length", "structure"])
        for did in sorted(final_sequences):
            seq = final_sequences[did]
            w.writerow([did, seq, len(seq), final_structures.get(did, "")])
    log(f"Stage 2 complete: {len(final_sequences)}/{n_designs} designs with sequences")
    log(f"Sequences saved to {seq_csv}")

    # ============================================================
    # STAGE 3: AfCycDesign Validation
    # ============================================================
    log("=" * 60)
    log("STAGE 3: AfCycDesign DL Validation")
    log("=" * 60)

    stage3_dir = RESULTS_DIR / "stage3"
    os.makedirs(stage3_dir, exist_ok=True)

    afcyc_results = {}
    for i, (design_id, seq) in enumerate(sorted(final_sequences.items())):
        # Check checkpoint
        if design_id in ckpt["stage3"] and ckpt["stage3"][design_id].get("completed"):
            log(f"[{i+1}/{len(final_sequences)}] {design_id} - SKIPPED (checkpoint)")
            afcyc_results[design_id] = ckpt["stage3"][design_id]["metrics"]
            continue

        log(f"[{i+1}/{len(final_sequences)}] {design_id}: {seq}")
        output_pdb = stage3_dir / f"{design_id}_afcyc.pdb"
        metrics = run_afcycdesign(seq, output_pdb)

        if metrics:
            afcyc_results[design_id] = metrics
            log(f"  iPAE={metrics.get('iPAE', 'N/A'):.4f}, pLDDT={metrics.get('pLDDT', 'N/A'):.4f}")
            ckpt["stage3"][design_id] = {"completed": True, "metrics": metrics}
        else:
            log(f"  AfCycDesign FAILED for {design_id}")
            afcyc_results[design_id] = {"iPAE": 999, "pLDDT": 0}
            ckpt["stage3"][design_id] = {"completed": True, "metrics": afcyc_results[design_id]}
        save_checkpoint(ckpt)

    # Save AfCycDesign results
    afcyc_csv = stage3_dir / "afcycdesign_results.csv"
    with open(afcyc_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["design_id", "sequence", "iPAE", "pLDDT", "pTM", "ipTM", "i_con"])
        for did in sorted(afcyc_results):
            m = afcyc_results[did]
            w.writerow([
                did, final_sequences.get(did, ""),
                m.get("iPAE", ""), m.get("pLDDT", ""),
                m.get("pTM", ""), m.get("ipTM", ""),
                m.get("i_con", ""),
            ])
    log(f"Stage 3 complete. Results saved to {afcyc_csv}")

    # ============================================================
    # STAGE 4: Rosetta Interface Metrics
    # ============================================================
    log("=" * 60)
    log("STAGE 4: Rosetta Interface Metrics (ddG, SAP, CMS)")
    log("=" * 60)

    stage4_dir = RESULTS_DIR / "stage4"
    os.makedirs(stage4_dir, exist_ok=True)

    if not ckpt.get("stage4_done"):
        # Collect all final structures
        input_pdbs = []
        for did in sorted(final_structures):
            pdb_path = final_structures[did]
            if os.path.exists(pdb_path):
                input_pdbs.append(pdb_path)

        if input_pdbs:
            log(f"Running interface metrics on {len(input_pdbs)} structures...")
            metrics_csv = run_interface_metrics(input_pdbs, stage4_dir, peptide_chain="A")
            if metrics_csv:
                log(f"Interface metrics saved to {metrics_csv}")
                ckpt["stage4_done"] = True
                save_checkpoint(ckpt)
            else:
                log("Interface metrics FAILED")
        else:
            log("No structures to analyze")
    else:
        log("Stage 4 SKIPPED (checkpoint)")
        metrics_csv = str(stage4_dir / "interface_metrics.csv")

    # ============================================================
    # STAGE 5: Final Ranking & Summary
    # ============================================================
    log("=" * 60)
    log("STAGE 5: Final Ranking & Summary")
    log("=" * 60)

    # Load interface metrics
    physics_metrics = {}
    metrics_csv_path = stage4_dir / "interface_metrics.csv"
    if metrics_csv_path.exists():
        with open(metrics_csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Map filename back to design_id
                name = row.get("name", "")
                for did in final_structures:
                    if did in name:
                        physics_metrics[did] = {
                            "ddg": float(row.get("ddg", 999)),
                            "sap": float(row.get("sap", 999)),
                            "cms": float(row.get("cms", 0)),
                            "passes": row.get("passes_filter", "False") == "True",
                        }
                        break

    # Merge all metrics
    summary = []
    for did in sorted(final_sequences):
        seq = final_sequences[did]
        afm = afcyc_results.get(did, {})
        phm = physics_metrics.get(did, {})
        summary.append({
            "design_id": did,
            "sequence": seq,
            "length": len(seq),
            "iPAE": afm.get("iPAE", 999),
            "pLDDT": afm.get("pLDDT", 0),
            "ddg": phm.get("ddg", 999),
            "sap": phm.get("sap", 999),
            "cms": phm.get("cms", 0),
            "passes_physics": phm.get("passes", False),
            "structure": final_structures.get(did, ""),
        })

    # Rank by ddG (primary), then iPAE (secondary)
    summary.sort(key=lambda x: (x["ddg"], x["iPAE"]))

    # Save full summary
    summary_csv = RESULTS_DIR / "final_summary.csv"
    with open(summary_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=summary[0].keys())
        w.writeheader()
        w.writerows(summary)

    # Print top results
    log(f"\n{'='*80}")
    log("FINAL RESULTS (ranked by ddG)")
    log(f"{'='*80}")
    log(f"{'Rank':<5} {'ID':<6} {'Sequence':<18} {'Len':<4} {'ddG':>8} {'SAP':>6} {'CMS':>7} {'iPAE':>7} {'pLDDT':>7} {'Pass'}")
    log("-" * 80)
    for rank, d in enumerate(summary[:20], 1):
        log(f"{rank:<5} {d['design_id']:<6} {d['sequence']:<18} {d['length']:<4} "
            f"{d['ddg']:>8.2f} {d['sap']:>6.2f} {d['cms']:>7.1f} "
            f"{d['iPAE']:>7.4f} {d['pLDDT']:>7.4f} {'YES' if d['passes_physics'] else 'no'}")

    n_pass = sum(1 for d in summary if d["passes_physics"])
    log(f"\nTotal: {len(summary)} designs, {n_pass} pass physics filters")
    log(f"Full summary: {summary_csv}")
    log("PIPELINE COMPLETE")


if __name__ == "__main__":
    main()
