#!/usr/bin/env python3
"""
RbtA Production Pipeline (Parallel Version)

Parallelizes the 5-stage binder design pipeline:
- Stage 2: N_WORKERS designs processed in parallel (MPNN + Rosetta relax × 4 rounds)
- Stage 3: GPU_WORKERS AfCycDesign validations in parallel
- Stage 4: Rosetta interface metrics (batch, single call)
- Stage 5: Ranking and summary

Resumes from checkpoint (compatible with sequential pipeline checkpoint).

Usage:
    python run_production_pipeline_parallel.py 2>&1 | tee pipeline_parallel.log
"""

import os
import sys
import csv
import json
import glob
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed

# ============================================================
# Configuration
# ============================================================
BASE_DIR = Path("/home/xux/Desktop/AgentMCP/CycPepMCP/examples/case2_RbtA_binder_rfpeptides")
BACKBONE_DIR = BASE_DIR / "results" / "prod_backbones"
RESULTS_DIR = BASE_DIR / "results" / "prod_pipeline"
TARGET_PDB = str(BASE_DIR / "RbtA_monomer_relaxed.pdb")

# Parallelism settings
N_WORKERS = 20       # Parallel Rosetta relax workers (CPU-bound, ~2 cores each)
GPU_WORKERS = 4      # Parallel AfCycDesign workers (GPU-bound)

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
                            new_res = AA_MAP.get(sequence[seq_idx], 'ALA')
                            seq_idx += 1
                        else:
                            new_res = line[17:20]
                    line = line[:17] + f"{new_res:>3}" + line[20:]
                out.write(line)
            else:
                out.write(line)


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
        return None
    fa_files = glob.glob(os.path.join(output_dir, "seqs", "*.fa"))
    if not fa_files:
        return None
    sequences = []
    with open(fa_files[0]) as f:
        for line in f:
            if not line.startswith(">"):
                sequences.append(line.strip())
    if len(sequences) >= 2:
        return sequences[1].replace('X', 'A')
    elif sequences:
        return sequences[0].replace('X', 'A')
    return None


def run_rosetta_relax(input_pdb, output_dir, rounds=4):
    """Run Rosetta FastRelax. Returns path to best relaxed PDB or None."""
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        ROSETTA_PYTHON, ROSETTA_RELAX,
        "--input", str(input_pdb),
        "--output", str(output_dir),
        "--rounds", str(rounds),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    if result.returncode != 0:
        return None
    stem = Path(input_pdb).stem
    round_pdbs = sorted(glob.glob(os.path.join(output_dir, f"{stem}_round*.pdb")))
    if round_pdbs:
        return round_pdbs[-1]
    all_pdbs = sorted(glob.glob(os.path.join(output_dir, "*.pdb")))
    return all_pdbs[-1] if all_pdbs else None


# ============================================================
# Per-design worker: runs all 4 rounds for one design
# ============================================================
def process_single_design(args) -> Tuple[str, Optional[str], Optional[str]]:
    """Process one design through all 4 rounds. Returns (design_id, final_seq, final_pdb)."""
    design_id, backbone_pdb, stage2_dir = args

    current_pdb = backbone_pdb
    current_seq = None

    for rnd in range(1, NUM_ROUNDS + 1):
        rnd_dir = Path(stage2_dir) / design_id / f"round{rnd}"

        # ProteinMPNN
        mpnn_dir = rnd_dir / "mpnn"
        seq = run_proteinmpnn(current_pdb, mpnn_dir)
        if seq is None:
            log(f"  {design_id} R{rnd}: MPNN failed")
            break
        current_seq = seq

        # Thread sequence
        threaded_pdb = rnd_dir / f"{design_id}_r{rnd}_threaded.pdb"
        thread_sequence(current_pdb, str(threaded_pdb), seq, chain='A')

        # Rosetta FastRelax
        relax_dir = rnd_dir / "relax"
        relaxed_pdb = run_rosetta_relax(str(threaded_pdb), str(relax_dir), rounds=4)
        if relaxed_pdb is None:
            log(f"  {design_id} R{rnd}: Relax failed, using threaded")
            current_pdb = str(threaded_pdb)
        else:
            current_pdb = relaxed_pdb

    if current_seq:
        final_pdb = Path(stage2_dir) / f"{design_id}_final.pdb"
        shutil.copy2(current_pdb, final_pdb)
        log(f"  {design_id}: DONE -> {current_seq}")
        return (design_id, current_seq, str(final_pdb))
    else:
        log(f"  {design_id}: FAILED")
        return (design_id, None, None)


def process_single_afcyc(args) -> Tuple[str, Dict]:
    """Run AfCycDesign for one design. Returns (design_id, metrics)."""
    design_id, sequence, output_pdb, gpu_id = args
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)

    cmd = [
        AFCYC_PYTHON, AFCYC_SCRIPT,
        "--pdb", TARGET_PDB,
        "--target_chain", "A",
        "--peptide_seq", sequence,
        "--num_recycles", "6",
        "--num_models", "2",
        "--save_json",
        "--output", str(output_pdb),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)

    json_path = str(output_pdb).replace(".pdb", ".json")
    if result.returncode == 0 and os.path.exists(json_path):
        with open(json_path) as f:
            raw = json.load(f)
        m = raw.get("metrics", raw)  # Handle both nested and flat formats
        metrics = {
            "iPAE": float(m.get("i_pae", m.get("iPAE", 999))),
            "pLDDT": float(m.get("plddt", m.get("pLDDT", 0))),
            "pTM": float(m.get("ptm", m.get("pTM", 0))),
            "ipTM": float(m.get("i_ptm", m.get("ipTM", 0))),
            "i_con": float(m.get("i_con", 0)),
        }
        log(f"  {design_id}: iPAE={metrics['iPAE']:.4f}, pLDDT={metrics['pLDDT']:.4f}")
        return (design_id, metrics)
    else:
        log(f"  {design_id}: AfCycDesign FAILED")
        return (design_id, {"iPAE": 999, "pLDDT": 0})


def get_checkpoint():
    ckpt_path = RESULTS_DIR / "checkpoint.json"
    if ckpt_path.exists():
        with open(ckpt_path) as f:
            return json.load(f)
    return {"stage2": {}, "stage3": {}, "stage4_done": False}


def save_checkpoint(ckpt):
    with open(RESULTS_DIR / "checkpoint.json", "w") as f:
        json.dump(ckpt, f, indent=2)


# ============================================================
# Main Pipeline
# ============================================================
def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    backbones = sorted(glob.glob(str(BACKBONE_DIR / "*.pdb")))
    n_designs = len(backbones)
    log(f"Production pipeline (PARALLEL): {n_designs} backbones, {N_WORKERS} workers")

    ckpt = get_checkpoint()

    # ============================================================
    # STAGE 2: Parallel Iterative Sequence Design
    # ============================================================
    log("=" * 60)
    log(f"STAGE 2: Iterative Sequence Design ({N_WORKERS} parallel workers)")
    log("=" * 60)

    stage2_dir = RESULTS_DIR / "stage2"
    os.makedirs(stage2_dir, exist_ok=True)

    final_sequences = {}
    final_structures = {}

    # Load completed from checkpoint
    for did, info in ckpt.get("stage2", {}).items():
        if info.get("completed"):
            final_sequences[did] = info["sequence"]
            final_structures[did] = info["structure"]

    # Find designs that still need processing
    pending_tasks = []
    for i, backbone in enumerate(backbones):
        design_id = f"d{i:02d}"
        if design_id in final_sequences:
            log(f"  {design_id}: SKIPPED (checkpoint) -> {final_sequences[design_id]}")
            continue
        pending_tasks.append((design_id, backbone, str(stage2_dir)))

    if pending_tasks:
        log(f"Processing {len(pending_tasks)} remaining designs with {N_WORKERS} parallel workers...")
        t0 = datetime.now()

        with ProcessPoolExecutor(max_workers=N_WORKERS) as pool:
            futures = {pool.submit(process_single_design, task): task[0] for task in pending_tasks}

            for future in as_completed(futures):
                design_id = futures[future]
                try:
                    did, seq, pdb_path = future.result()
                    if seq:
                        final_sequences[did] = seq
                        final_structures[did] = pdb_path
                        ckpt["stage2"][did] = {
                            "completed": True,
                            "sequence": seq,
                            "structure": pdb_path,
                        }
                        save_checkpoint(ckpt)
                except Exception as e:
                    log(f"  {design_id}: EXCEPTION {e}")

        elapsed = (datetime.now() - t0).total_seconds()
        log(f"Stage 2 complete: {len(final_sequences)}/{n_designs} designs in {elapsed/60:.1f} min")
    else:
        log("Stage 2: All designs already completed")

    # Save sequence summary
    seq_csv = stage2_dir / "sequences.csv"
    with open(seq_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["design_id", "sequence", "length", "structure"])
        for did in sorted(final_sequences):
            seq = final_sequences[did]
            w.writerow([did, seq, len(seq), final_structures.get(did, "")])

    # ============================================================
    # STAGE 3: Parallel AfCycDesign Validation
    # ============================================================
    log("=" * 60)
    log(f"STAGE 3: AfCycDesign DL Validation ({GPU_WORKERS} parallel workers)")
    log("=" * 60)

    stage3_dir = RESULTS_DIR / "stage3"
    os.makedirs(stage3_dir, exist_ok=True)

    afcyc_results = {}
    # Load completed from checkpoint
    for did, info in ckpt.get("stage3", {}).items():
        if info.get("completed"):
            afcyc_results[did] = info["metrics"]

    # Recover existing JSON files not yet in checkpoint
    recovered = 0
    for did in sorted(final_sequences):
        if did in afcyc_results:
            continue
        json_path = stage3_dir / f"{did}_afcyc.json"
        if json_path.exists():
            try:
                with open(json_path) as f:
                    raw = json.load(f)
                m = raw.get("metrics", raw)
                metrics = {
                    "iPAE": float(m.get("i_pae", m.get("iPAE", 999))),
                    "pLDDT": float(m.get("plddt", m.get("pLDDT", 0))),
                    "pTM": float(m.get("ptm", m.get("pTM", 0))),
                    "ipTM": float(m.get("i_ptm", m.get("ipTM", 0))),
                    "i_con": float(m.get("i_con", 0)),
                }
                afcyc_results[did] = metrics
                ckpt["stage3"][did] = {"completed": True, "metrics": metrics}
                recovered += 1
            except Exception:
                pass  # Will re-run
    if recovered:
        save_checkpoint(ckpt)
        log(f"  Recovered {recovered} results from existing JSON files")

    # Find pending
    pending_afcyc = []
    for i, (did, seq) in enumerate(sorted(final_sequences.items())):
        if did in afcyc_results:
            log(f"  {did}: SKIPPED (checkpoint)")
            continue
        output_pdb = str(stage3_dir / f"{did}_afcyc.pdb")
        gpu_id = i % 2  # Alternate between 2 GPUs
        pending_afcyc.append((did, seq, output_pdb, gpu_id))

    if pending_afcyc:
        log(f"Validating {len(pending_afcyc)} designs with {GPU_WORKERS} parallel workers...")
        t0 = datetime.now()

        with ProcessPoolExecutor(max_workers=GPU_WORKERS) as pool:
            futures = {pool.submit(process_single_afcyc, task): task[0] for task in pending_afcyc}

            for future in as_completed(futures):
                design_id = futures[future]
                try:
                    did, metrics = future.result()
                    afcyc_results[did] = metrics
                    ckpt["stage3"][did] = {"completed": True, "metrics": metrics}
                    save_checkpoint(ckpt)
                except Exception as e:
                    log(f"  {design_id}: EXCEPTION {e}")
                    afcyc_results[design_id] = {"iPAE": 999, "pLDDT": 0}

        elapsed = (datetime.now() - t0).total_seconds()
        log(f"Stage 3 complete in {elapsed/60:.1f} min")
    else:
        log("Stage 3: All designs already validated")

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

    # ============================================================
    # STAGE 4: Rosetta Interface Metrics (batch)
    # ============================================================
    log("=" * 60)
    log("STAGE 4: Rosetta Interface Metrics (batch)")
    log("=" * 60)

    stage4_dir = RESULTS_DIR / "stage4"
    os.makedirs(stage4_dir, exist_ok=True)

    if not ckpt.get("stage4_done"):
        input_pdbs = [final_structures[did] for did in sorted(final_structures)
                      if os.path.exists(final_structures[did])]

        if input_pdbs:
            log(f"Computing metrics for {len(input_pdbs)} structures...")
            t0 = datetime.now()
            cmd = [
                ROSETTA_PYTHON, ROSETTA_METRICS,
                "--input",
            ] + input_pdbs + [
                "--output", str(stage4_dir),
                "--peptide_chain", "A",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
            elapsed = (datetime.now() - t0).total_seconds()

            if result.returncode == 0:
                log(f"Stage 4 complete in {elapsed/60:.1f} min")
                ckpt["stage4_done"] = True
                save_checkpoint(ckpt)
            else:
                log(f"Interface metrics FAILED: {result.stderr[-300:]}")
    else:
        log("Stage 4: Already completed (checkpoint)")

    # ============================================================
    # STAGE 5: Final Ranking & Summary
    # ============================================================
    log("=" * 60)
    log("STAGE 5: Final Ranking & Summary")
    log("=" * 60)

    physics_metrics = {}
    metrics_csv = stage4_dir / "interface_metrics.csv"
    if metrics_csv.exists():
        with open(metrics_csv) as f:
            for row in csv.DictReader(f):
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

    summary = []
    for did in sorted(final_sequences):
        seq = final_sequences[did]
        afm = afcyc_results.get(did, {})
        phm = physics_metrics.get(did, {})
        summary.append({
            "design_id": did,
            "sequence": seq,
            "length": len(seq),
            "iPAE": float(afm.get("iPAE", 999)),
            "pLDDT": float(afm.get("pLDDT", 0)),
            "ddg": float(phm.get("ddg", 999)),
            "sap": float(phm.get("sap", 999)),
            "cms": float(phm.get("cms", 0)),
            "passes_physics": phm.get("passes", False),
            "structure": final_structures.get(did, ""),
        })

    summary.sort(key=lambda x: (x["ddg"], x["iPAE"]))

    summary_csv = RESULTS_DIR / "final_summary.csv"
    with open(summary_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=summary[0].keys())
        w.writeheader()
        w.writerows(summary)

    log(f"\n{'='*90}")
    log("FINAL RESULTS (ranked by ddG)")
    log(f"{'='*90}")
    log(f"{'Rank':<5} {'ID':<6} {'Sequence':<20} {'Len':<4} {'ddG':>8} {'SAP':>6} {'CMS':>7} {'iPAE':>7} {'pLDDT':>7} {'Pass'}")
    log("-" * 90)
    for rank, d in enumerate(summary, 1):
        log(f"{rank:<5} {d['design_id']:<6} {d['sequence']:<20} {d['length']:<4} "
            f"{d['ddg']:>8.2f} {d['sap']:>6.2f} {d['cms']:>7.1f} "
            f"{d['iPAE']:>7.4f} {d['pLDDT']:>7.4f} {'YES' if d['passes_physics'] else 'no'}")

    n_pass = sum(1 for d in summary if d["passes_physics"])
    log(f"\nTotal: {len(summary)} designs, {n_pass} pass physics filters")
    log(f"Full summary: {summary_csv}")
    log("PIPELINE COMPLETE")


if __name__ == "__main__":
    main()
