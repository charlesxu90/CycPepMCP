#!/usr/bin/env python3
"""
RFpeptides Full Pipeline: Stages 2-5
=====================================
Unified cyclic peptide binder design pipeline with parallel processing.

Stage 2: Iterative ProteinMPNN CA-only + Rosetta FastRelax (4 rounds)
Stage 3: AfCycDesign complex prediction validation
Stage 4: Rosetta interface metrics (ddG, SAP, CMS)
Stage 5: RMSD clustering + final selection

Usage:
    python run_pipeline.py \\
        --stage1_dir /path/to/rfpeptides/backbones \\
        --target_pdb /path/to/target.pdb \\
        --output_dir results/pipeline_output \\
        --workers 20 --gpu_workers 4 --num_gpus 2

    # Sequential mode for debugging:
    python run_pipeline.py \\
        --stage1_dir /path/to/backbones \\
        --target_pdb /path/to/target.pdb \\
        --sequential --max_designs 2

    # Resume from Stage 3:
    python run_pipeline.py \\
        --stage1_dir /path/to/backbones \\
        --target_pdb /path/to/target.pdb \\
        --output_dir results/pipeline_output \\
        --start_stage 3
"""

import argparse
import csv
import glob
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ==============================================================================
# Auto-detect tool paths
# ==============================================================================
def _find_project_root() -> Path:
    """Walk up from this script to find the CycPepMCP project root."""
    d = Path(__file__).resolve().parent
    for _ in range(10):
        if (d / "tool-mcps").is_dir():
            return d
        d = d.parent
    raise RuntimeError("Cannot find project root (expected tool-mcps/ directory)")


def _resolve_tool_paths() -> dict:
    """Resolve all tool Python binaries and scripts from tool-mcps/."""
    root = _find_project_root()

    # ProteinMPNN — may live in a sibling project (ProteinMCP)
    mpnn_base = root / "tool-mcps" / "proteinmpnn_mcp"
    if not mpnn_base.is_dir():
        # Check sibling ProteinMCP layout
        for candidate in [root.parent / "ProteinMCP" / "tool-mcps" / "proteinmpnn_mcp"]:
            if candidate.is_dir():
                mpnn_base = candidate
                break

    mpnn_env = mpnn_base / "env"
    mpnn_python = str(next(mpnn_env.glob("bin/python*"), mpnn_env / "bin" / "python"))
    mpnn_repo = mpnn_base / "repo" / "ProteinMPNN"
    mpnn_script = str(mpnn_repo / "protein_mpnn_run.py")

    # CA model weights — check repo first, then examples/data
    mpnn_weights = mpnn_repo / "ca_model_weights"
    if not mpnn_weights.is_dir():
        mpnn_weights = mpnn_base / "examples" / "data" / "ca_model_weights"

    # Rosetta KIC
    rosetta_base = root / "tool-mcps" / "rosetta_kic_mcp"
    rosetta_python = str(rosetta_base / "env" / "bin" / "python")
    rosetta_scripts = rosetta_base / "scripts"

    # AfCycDesign
    afcyc_base = root / "tool-mcps" / "afcycdesign_mcp"
    afcyc_python = str(afcyc_base / "env" / "bin" / "python")
    afcyc_scripts = afcyc_base / "scripts"

    return {
        "mpnn_python": mpnn_python,
        "mpnn_script": mpnn_script,
        "mpnn_repo": str(mpnn_repo),
        "mpnn_weights": str(mpnn_weights),
        "rosetta_python": rosetta_python,
        "rosetta_relax": str(rosetta_scripts / "cycpep_fast_relax.py"),
        "rosetta_metrics": str(rosetta_scripts / "interface_metrics.py"),
        "rosetta_rmsd": str(rosetta_scripts / "rmsd_benchmark.py"),
        "rosetta_scripts_dir": str(rosetta_scripts),
        "afcyc_python": afcyc_python,
        "afcyc_script": str(afcyc_scripts / "cycpep_target_complex_pred.py"),
    }


# Module-level globals set in main() before spawning workers.
# ProcessPoolExecutor (fork) inherits these automatically.
PATHS: dict = {}
TARGET_PDB: str = ""

# Design parameters
NUM_ROUNDS = 4
MPNN_TEMP = 0.0001
MPNN_MODEL = "v_48_020"
OMIT_AAS = "C"
NUM_GPUS = 2

AA_MAP = {
    "A": "ALA", "R": "ARG", "N": "ASN", "D": "ASP", "E": "GLU",
    "Q": "GLN", "G": "GLY", "H": "HIS", "I": "ILE", "L": "LEU",
    "K": "LYS", "M": "MET", "F": "PHE", "P": "PRO", "S": "SER",
    "T": "THR", "W": "TRP", "Y": "TYR", "V": "VAL", "X": "ALA",
}


# ==============================================================================
# Logging
# ==============================================================================
def setup_logging(output_dir: Path) -> logging.Logger:
    """Set up dual file + console logger."""
    logger = logging.getLogger("rfpeptides_pipeline")
    logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler(output_dir / "pipeline.log")
    fh.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def log(msg):
    """Simple timestamped print for worker processes (no logger access)."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ==============================================================================
# Checkpoint Manager
# ==============================================================================
class CheckpointManager:
    """Track per-design, per-stage completion for resume support."""

    def __init__(self, checkpoint_file: Path):
        self.file = checkpoint_file
        self.data = self._load()

    def _load(self) -> dict:
        if self.file.exists():
            with open(self.file) as f:
                return json.load(f)
        return {"stage2": {}, "stage3": {}, "stage4_done": False, "stage5_done": False}

    def save(self):
        with open(self.file, "w") as f:
            json.dump(self.data, f, indent=2)

    def is_done(self, stage: str, design_id: str) -> bool:
        return self.data.get(stage, {}).get(design_id, {}).get("completed", False)

    def mark_done(self, stage: str, design_id: str, info: dict):
        if stage not in self.data:
            self.data[stage] = {}
        self.data[stage][design_id] = {"completed": True, **info}
        self.save()

    def get_info(self, stage: str, design_id: str) -> dict:
        return self.data.get(stage, {}).get(design_id, {})


# ==============================================================================
# Helper functions
# ==============================================================================
def find_backbone_pdbs(stage1_dir: Path) -> List[Path]:
    """Find backbone PDB files from RFpeptides output."""
    patterns = ["*_cyclic_epitope_*.pdb", "*_cyclic_*.pdb", "design_*.pdb", "*.pdb"]
    for pat in patterns:
        pdbs = sorted(stage1_dir.glob(pat))
        pdbs = [p for p in pdbs if p.suffix == ".pdb"]
        if pdbs:
            return pdbs
    return []


def thread_sequence(input_pdb: str, output_pdb: str, sequence: str, chain: str = "A"):
    """Thread a designed sequence onto a backbone PDB via string manipulation.

    Fast, no PyRosetta dependency. Replaces residue names in ATOM records
    for the specified chain.
    """
    seq_idx = 0
    prev_resnum = None
    new_res = "GLY"
    with open(input_pdb) as f, open(output_pdb, "w") as out:
        for line in f:
            if line.startswith(("ATOM", "HETATM")):
                ch = line[21]
                resnum = line[22:26].strip()
                if ch == chain:
                    if resnum != prev_resnum:
                        prev_resnum = resnum
                        if seq_idx < len(sequence):
                            new_res = AA_MAP.get(sequence[seq_idx], "ALA")
                            seq_idx += 1
                        else:
                            new_res = line[17:20]
                    line = line[:17] + f"{new_res:>3}" + line[20:]
                out.write(line)
            else:
                out.write(line)


def run_proteinmpnn(input_pdb: str, output_dir: str) -> Optional[str]:
    """Run ProteinMPNN CA-only design. Returns designed binder sequence or None."""
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        PATHS["mpnn_python"], PATHS["mpnn_script"],
        "--pdb_path", str(input_pdb),
        "--pdb_path_chains", "A",
        "--out_folder", str(output_dir),
        "--num_seq_per_target", "1",
        "--sampling_temp", str(MPNN_TEMP),
        "--seed", "37",
        "--model_name", MPNN_MODEL,
        "--batch_size", "1",
        "--path_to_model_weights", PATHS["mpnn_weights"],
        "--ca_only",
        "--omit_AAs", OMIT_AAS,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        return None

    fa_files = glob.glob(os.path.join(output_dir, "seqs", "*.fa"))
    if not fa_files:
        return None

    sequences = []
    with open(fa_files[0]) as f:
        for line in f:
            if not line.startswith(">"):
                seq = line.strip()
                if seq:
                    sequences.append(seq)

    # First entry is the input (GLY) sequence; second is the designed sequence
    if len(sequences) >= 2:
        return sequences[1].replace("X", "A")
    elif sequences:
        return sequences[0].replace("X", "A")
    return None


def run_rosetta_relax(input_pdb: str, output_dir: str, rounds: int = 4) -> Optional[str]:
    """Run Rosetta FastRelax with PeptideCyclizeMover. Returns best relaxed PDB path."""
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        PATHS["rosetta_python"], PATHS["rosetta_relax"],
        "--input", str(input_pdb),
        "--output", str(output_dir),
        "--rounds", str(rounds),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        return None

    stem = Path(input_pdb).stem
    round_pdbs = sorted(glob.glob(os.path.join(output_dir, f"{stem}_round*.pdb")))
    if round_pdbs:
        return round_pdbs[-1]
    all_pdbs = sorted(glob.glob(os.path.join(output_dir, "*.pdb")))
    return all_pdbs[-1] if all_pdbs else None


# ==============================================================================
# Stage 2 worker: runs all rounds for one design
# ==============================================================================
def process_single_design(args) -> Tuple[str, Optional[str], Optional[str]]:
    """Process one design through all ProteinMPNN + Relax rounds.

    Returns (design_id, final_sequence, final_pdb_path).
    """
    design_id, backbone_pdb, stage2_dir, num_rounds = args

    current_pdb = backbone_pdb
    current_seq = None

    for rnd in range(1, num_rounds + 1):
        rnd_dir = Path(stage2_dir) / design_id / f"round{rnd}"

        # Step A: ProteinMPNN CA-only
        mpnn_dir = str(rnd_dir / "mpnn")
        seq = run_proteinmpnn(current_pdb, mpnn_dir)
        if seq is None:
            log(f"  {design_id} R{rnd}: MPNN failed")
            break
        current_seq = seq

        # Step B: Thread sequence onto backbone
        threaded_pdb = str(rnd_dir / f"{design_id}_r{rnd}_threaded.pdb")
        os.makedirs(str(rnd_dir), exist_ok=True)
        thread_sequence(current_pdb, threaded_pdb, seq, chain="A")

        # Step C: Rosetta FastRelax
        relax_dir = str(rnd_dir / "relax")
        relaxed_pdb = run_rosetta_relax(threaded_pdb, relax_dir, rounds=4)
        if relaxed_pdb is None:
            log(f"  {design_id} R{rnd}: Relax failed, using threaded")
            current_pdb = threaded_pdb
        else:
            current_pdb = relaxed_pdb

    if current_seq:
        final_pdb = str(Path(stage2_dir) / f"{design_id}_final.pdb")
        shutil.copy2(current_pdb, final_pdb)
        log(f"  {design_id}: DONE -> {current_seq}")
        return (design_id, current_seq, final_pdb)
    else:
        log(f"  {design_id}: FAILED")
        return (design_id, None, None)


# ==============================================================================
# Stage 3 worker: AfCycDesign validation for one design
# ==============================================================================
def process_single_afcyc(args) -> Tuple[str, Dict]:
    """Run AfCycDesign complex prediction for one design.

    Returns (design_id, metrics_dict).
    """
    design_id, sequence, output_pdb, gpu_id = args
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)

    cmd = [
        PATHS["afcyc_python"], PATHS["afcyc_script"],
        "--pdb", TARGET_PDB,
        "--target_chain", "A",
        "--peptide_seq", sequence,
        "--num_recycles", "1",
        "--num_models", "2",
        "--save_json",
        "--output", str(output_pdb),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)

    json_path = str(output_pdb).replace(".pdb", ".json")
    if result.returncode == 0 and os.path.exists(json_path):
        with open(json_path) as f:
            raw = json.load(f)
        m = raw.get("metrics", raw)  # Handle both nested and flat JSON formats
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
        stderr_tail = result.stderr[-200:] if result.stderr else ""
        log(f"  {design_id}: AfCycDesign FAILED {stderr_tail}")
        return (design_id, {"iPAE": 999, "pLDDT": 0})


# ==============================================================================
# Stage 5: RMSD clustering
# ==============================================================================
def run_rmsd_clustering(
    design_pdbs: List[str],
    output_dir: Path,
    rmsd_cutoff: float = 2.0,
    logger: logging.Logger = None,
) -> List[Dict]:
    """Greedy pairwise RMSD clustering using Rosetta rmsd_benchmark.py."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    clusters: List[Dict] = []

    for pdb in design_pdbs:
        assigned = False
        for cluster in clusters:
            rep = cluster["representative"]
            cmd = [
                PATHS["rosetta_python"],
                PATHS["rosetta_rmsd"],
                "--input", str(pdb),
                "--native", str(rep),
                "--output", str(output_dir / "rmsd_tmp"),
                "--rmsd_cutoff", str(rmsd_cutoff),
            ]
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=300,
                    cwd=PATHS["rosetta_scripts_dir"],
                )
            except subprocess.TimeoutExpired:
                continue

            if result.returncode == 0:
                rmsd_val = None
                for line in (result.stdout + result.stderr).split("\n"):
                    match = re.search(r"RMSD[:\s=]+([0-9.]+)", line, re.IGNORECASE)
                    if match:
                        rmsd_val = float(match.group(1))
                        break

                if rmsd_val is not None and rmsd_val < rmsd_cutoff:
                    cluster["members"].append(str(pdb))
                    assigned = True
                    break

        if not assigned:
            clusters.append({
                "representative": str(pdb),
                "members": [str(pdb)],
            })

    if logger:
        logger.info(f"Clustering: {len(design_pdbs)} designs -> {len(clusters)} clusters")

    return clusters


# ==============================================================================
# Main Pipeline
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="RFpeptides binder design pipeline (Stages 2-5)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--stage1_dir", required=True,
                        help="Directory with RFpeptides backbone PDBs")
    parser.add_argument("--target_pdb", required=True,
                        help="Target protein PDB file")
    parser.add_argument("--output_dir", default="results/pipeline_output",
                        help="Output directory (default: results/pipeline_output)")
    parser.add_argument("--num_rounds", type=int, default=4,
                        help="ProteinMPNN + Relax iterations (default: 4)")
    parser.add_argument("--workers", type=int, default=20,
                        help="CPU workers for Stage 2 (default: 20)")
    parser.add_argument("--gpu_workers", type=int, default=4,
                        help="GPU workers for Stage 3 (default: 4)")
    parser.add_argument("--num_gpus", type=int, default=2,
                        help="Number of GPUs for AfCycDesign rotation (default: 2)")
    parser.add_argument("--ipae_threshold", type=float, default=0.3,
                        help="iPAE filter threshold (default: 0.3)")
    parser.add_argument("--ddg_threshold", type=float, default=-50.0,
                        help="ddG filter threshold (default: -50.0)")
    parser.add_argument("--sap_threshold", type=float, default=35.0,
                        help="SAP filter threshold (default: 35.0)")
    parser.add_argument("--cms_threshold", type=float, default=300.0,
                        help="CMS filter threshold (default: 300.0)")
    parser.add_argument("--rmsd_cutoff", type=float, default=2.0,
                        help="RMSD clustering cutoff in Angstroms (default: 2.0)")
    parser.add_argument("--start_stage", type=int, default=2,
                        help="Stage to resume from (default: 2)")
    parser.add_argument("--max_designs", type=int, default=None,
                        help="Max designs to process (for testing)")
    parser.add_argument("--sequential", action="store_true",
                        help="Disable parallelism (run everything sequentially)")

    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Set module-level globals BEFORE any ProcessPoolExecutor fork
    # ------------------------------------------------------------------
    global PATHS, TARGET_PDB, NUM_ROUNDS, NUM_GPUS
    PATHS = _resolve_tool_paths()
    TARGET_PDB = str(Path(args.target_pdb).resolve())
    NUM_ROUNDS = args.num_rounds
    NUM_GPUS = args.num_gpus

    # Directories
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stage2_dir = output_dir / "stage2"
    stage3_dir = output_dir / "stage3"
    stage4_dir = output_dir / "stage4"
    stage5_dir = output_dir / "stage5"
    for d in [stage2_dir, stage3_dir, stage4_dir, stage5_dir]:
        d.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(output_dir)
    ckpt = CheckpointManager(output_dir / "checkpoint.json")

    logger.info("=" * 70)
    logger.info("RFpeptides Pipeline - Production Run")
    logger.info("=" * 70)
    logger.info(f"Stage 1 dir:     {args.stage1_dir}")
    logger.info(f"Target PDB:      {TARGET_PDB}")
    logger.info(f"Output dir:      {output_dir}")
    logger.info(f"Rounds:          {args.num_rounds}")
    logger.info(f"Workers (CPU):   {args.workers}")
    logger.info(f"Workers (GPU):   {args.gpu_workers}")
    logger.info(f"Num GPUs:        {args.num_gpus}")
    logger.info(f"Parallel:        {not args.sequential}")
    logger.info(f"iPAE threshold:  {args.ipae_threshold}")
    logger.info(f"ddG threshold:   {args.ddg_threshold}")
    logger.info(f"SAP threshold:   {args.sap_threshold}")
    logger.info(f"CMS threshold:   {args.cms_threshold}")
    logger.info(f"RMSD cutoff:     {args.rmsd_cutoff}")

    # Save config
    config = {**vars(args), "start_time": datetime.now().isoformat(), "paths": PATHS}
    with open(output_dir / "pipeline_config.json", "w") as f:
        json.dump(config, f, indent=2, default=str)

    # ------------------------------------------------------------------
    # Discover backbone PDBs
    # ------------------------------------------------------------------
    backbones = find_backbone_pdbs(Path(args.stage1_dir))
    if args.max_designs:
        backbones = backbones[: args.max_designs]
    n_designs = len(backbones)
    logger.info(f"Found {n_designs} backbone PDBs from Stage 1")
    if not backbones:
        logger.error("No backbone PDBs found! Check --stage1_dir.")
        return 1

    # ==================================================================
    # STAGE 2: Iterative ProteinMPNN + Rosetta FastRelax
    # ==================================================================
    final_sequences: Dict[str, str] = {}
    final_structures: Dict[str, str] = {}

    if args.start_stage <= 2:
        logger.info("")
        logger.info("=" * 70)
        logger.info(f"STAGE 2: Iterative Sequence Design ({args.num_rounds} rounds)")
        logger.info("=" * 70)

        # Load checkpoint hits
        for did, info in ckpt.data.get("stage2", {}).items():
            if info.get("completed"):
                final_sequences[did] = info["sequence"]
                final_structures[did] = info["structure"]

        # Build pending task list
        pending_tasks = []
        for i, backbone in enumerate(backbones):
            design_id = backbone.stem
            if design_id in final_sequences:
                logger.info(f"  {design_id}: SKIPPED (checkpoint)")
                continue
            pending_tasks.append(
                (design_id, str(backbone), str(stage2_dir), args.num_rounds)
            )

        if pending_tasks:
            logger.info(
                f"Processing {len(pending_tasks)} designs"
                + (f" with {args.workers} parallel workers" if not args.sequential else " sequentially")
            )
            t0 = datetime.now()

            if args.sequential:
                for task in pending_tasks:
                    did, seq, pdb_path = process_single_design(task)
                    if seq:
                        final_sequences[did] = seq
                        final_structures[did] = pdb_path
                        ckpt.mark_done("stage2", did, {"sequence": seq, "structure": pdb_path})
            else:
                with ProcessPoolExecutor(max_workers=args.workers) as pool:
                    futures = {
                        pool.submit(process_single_design, task): task[0]
                        for task in pending_tasks
                    }
                    for future in as_completed(futures):
                        design_id = futures[future]
                        try:
                            did, seq, pdb_path = future.result()
                            if seq:
                                final_sequences[did] = seq
                                final_structures[did] = pdb_path
                                ckpt.mark_done("stage2", did, {"sequence": seq, "structure": pdb_path})
                        except Exception as e:
                            logger.error(f"  {design_id}: EXCEPTION {e}")

            elapsed = (datetime.now() - t0).total_seconds()
            logger.info(
                f"Stage 2 complete: {len(final_sequences)}/{n_designs} designs in {elapsed/60:.1f} min"
            )
        else:
            logger.info("Stage 2: All designs already completed")

        # Save sequence summary CSV
        seq_csv = stage2_dir / "sequences.csv"
        with open(seq_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["design_id", "sequence", "length", "structure"])
            for did in sorted(final_sequences):
                seq = final_sequences[did]
                w.writerow([did, seq, len(seq), final_structures.get(did, "")])
    else:
        # Load Stage 2 results from checkpoint
        for did, info in ckpt.data.get("stage2", {}).items():
            if info.get("completed"):
                final_sequences[did] = info["sequence"]
                final_structures[did] = info["structure"]
        logger.info(f"Loaded {len(final_sequences)} Stage 2 results from checkpoint")

    # ==================================================================
    # STAGE 3: AfCycDesign Validation (parallel GPU)
    # ==================================================================
    afcyc_results: Dict[str, Dict] = {}

    if args.start_stage <= 3 and final_sequences:
        logger.info("")
        logger.info("=" * 70)
        logger.info(f"STAGE 3: AfCycDesign DL Validation (iPAE < {args.ipae_threshold})")
        logger.info("=" * 70)

        # Load checkpoint hits
        for did, info in ckpt.data.get("stage3", {}).items():
            if info.get("completed"):
                afcyc_results[did] = info.get("metrics", {})

        # Recover results from existing JSON files not yet in checkpoint
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
                    ckpt.mark_done("stage3", did, {"metrics": metrics})
                    recovered += 1
                except Exception:
                    pass
        if recovered:
            logger.info(f"  Recovered {recovered} results from existing JSON files")

        # Build pending tasks with GPU rotation
        pending_afcyc = []
        for i, (did, seq) in enumerate(sorted(final_sequences.items())):
            if did in afcyc_results:
                logger.info(f"  {did}: SKIPPED (checkpoint)")
                continue
            output_pdb = str(stage3_dir / f"{did}_afcyc.pdb")
            gpu_id = i % args.num_gpus
            pending_afcyc.append((did, seq, output_pdb, gpu_id))

        if pending_afcyc:
            logger.info(
                f"Validating {len(pending_afcyc)} designs"
                + (f" with {args.gpu_workers} GPU workers" if not args.sequential else " sequentially")
            )
            t0 = datetime.now()

            if args.sequential:
                for task in pending_afcyc:
                    did, metrics = process_single_afcyc(task)
                    afcyc_results[did] = metrics
                    ckpt.mark_done("stage3", did, {"metrics": metrics})
            else:
                with ProcessPoolExecutor(max_workers=args.gpu_workers) as pool:
                    futures = {
                        pool.submit(process_single_afcyc, task): task[0]
                        for task in pending_afcyc
                    }
                    for future in as_completed(futures):
                        design_id = futures[future]
                        try:
                            did, metrics = future.result()
                            afcyc_results[did] = metrics
                            ckpt.mark_done("stage3", did, {"metrics": metrics})
                        except Exception as e:
                            logger.error(f"  {design_id}: EXCEPTION {e}")
                            afcyc_results[design_id] = {"iPAE": 999, "pLDDT": 0}

            elapsed = (datetime.now() - t0).total_seconds()
            logger.info(f"Stage 3 complete in {elapsed/60:.1f} min")
        else:
            logger.info("Stage 3: All designs already validated")

        # Save AfCycDesign results CSV
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
    else:
        # Load Stage 3 results from checkpoint
        for did, info in ckpt.data.get("stage3", {}).items():
            if info.get("completed"):
                afcyc_results[did] = info.get("metrics", {})

    # ==================================================================
    # STAGE 4: Rosetta Interface Metrics (batch)
    # ==================================================================
    if args.start_stage <= 4 and final_structures:
        logger.info("")
        logger.info("=" * 70)
        logger.info("STAGE 4: Rosetta Interface Metrics (ddG, SAP, CMS)")
        logger.info(f"  Thresholds: ddG < {args.ddg_threshold}, SAP < {args.sap_threshold}, CMS > {args.cms_threshold}")
        logger.info("=" * 70)

        if not ckpt.data.get("stage4_done"):
            input_pdbs = [
                final_structures[did]
                for did in sorted(final_structures)
                if os.path.exists(final_structures[did])
            ]
            if input_pdbs:
                logger.info(f"Computing metrics for {len(input_pdbs)} structures...")
                t0 = datetime.now()

                cmd = [
                    PATHS["rosetta_python"], PATHS["rosetta_metrics"],
                    "--input",
                ] + input_pdbs + [
                    "--output", str(stage4_dir),
                    "--peptide_chain", "A",
                    "--ddg_threshold", str(args.ddg_threshold),
                    "--sap_threshold", str(args.sap_threshold),
                    "--cms_threshold", str(args.cms_threshold),
                ]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=7200,
                    cwd=PATHS["rosetta_scripts_dir"],
                )

                elapsed = (datetime.now() - t0).total_seconds()
                if result.returncode == 0:
                    logger.info(f"Stage 4 complete in {elapsed/60:.1f} min")
                    ckpt.data["stage4_done"] = True
                    ckpt.save()
                else:
                    logger.error(f"Interface metrics FAILED: {result.stderr[-300:]}")
            else:
                logger.warning("No structures available for interface metrics")
        else:
            logger.info("Stage 4: Already completed (checkpoint)")

    # Parse interface metrics CSV
    physics_metrics: Dict[str, Dict] = {}
    metrics_csv = stage4_dir / "interface_metrics.csv"
    if metrics_csv.exists():
        with open(metrics_csv) as f:
            for row in csv.DictReader(f):
                name = row.get("name", "")
                # interface_metrics writes name as "{design_id}_final" (see Stage 2);
                # substring match would collide on shared prefixes (e.g., "_1" in "_10")
                did = name[:-len("_final")] if name.endswith("_final") else name
                if did in final_structures:
                    physics_metrics[did] = {
                        "ddg": float(row.get("ddg", 999)),
                        "sap": float(row.get("sap", 999)),
                        "cms": float(row.get("cms", 0)),
                        "passes": row.get("passes_filter", "False") == "True",
                    }

    # ==================================================================
    # STAGE 5: RMSD Clustering + Final Summary
    # ==================================================================
    if args.start_stage <= 5 and final_sequences:
        logger.info("")
        logger.info("=" * 70)
        logger.info("STAGE 5: RMSD Clustering + Final Ranking")
        logger.info("=" * 70)

        # Build merged summary
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

        # Rank by ddG (primary), then iPAE (secondary)
        summary.sort(key=lambda x: (x["ddg"], x["iPAE"]))

        # RMSD clustering on designs that pass thresholds
        passing_pdbs = [
            d["structure"] for d in summary
            if d["passes_physics"]
            and d["iPAE"] < args.ipae_threshold
            and os.path.exists(d["structure"])
        ]

        clusters = []
        if passing_pdbs:
            logger.info(f"Clustering {len(passing_pdbs)} passing designs (RMSD cutoff={args.rmsd_cutoff} A)...")
            clusters = run_rmsd_clustering(
                passing_pdbs, stage5_dir, rmsd_cutoff=args.rmsd_cutoff, logger=logger,
            )

            # Save cluster info
            with open(stage5_dir / "clusters.json", "w") as f:
                json.dump(clusters, f, indent=2)
        else:
            logger.warning("No designs pass all thresholds for clustering")

        # Save full summary CSV
        summary_csv = output_dir / "final_summary.csv"
        if summary:
            with open(summary_csv, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=summary[0].keys())
                w.writeheader()
                w.writerows(summary)

        # Print ranked table
        n_pass = sum(1 for d in summary if d["passes_physics"])
        n_ipae = sum(1 for d in summary if d["iPAE"] < args.ipae_threshold)

        logger.info(f"\n{'='*90}")
        logger.info("FINAL RESULTS (ranked by ddG)")
        logger.info(f"{'='*90}")
        logger.info(
            f"{'Rank':<5} {'ID':<25} {'Sequence':<20} {'Len':<4} "
            f"{'ddG':>8} {'SAP':>6} {'CMS':>7} {'iPAE':>7} {'pLDDT':>7} {'Pass'}"
        )
        logger.info("-" * 90)
        for rank, d in enumerate(summary[:30], 1):
            logger.info(
                f"{rank:<5} {d['design_id']:<25} {d['sequence']:<20} {d['length']:<4} "
                f"{d['ddg']:>8.2f} {d['sap']:>6.2f} {d['cms']:>7.1f} "
                f"{d['iPAE']:>7.4f} {d['pLDDT']:>7.4f} "
                f"{'YES' if d['passes_physics'] else 'no'}"
            )

        logger.info(f"\nTotal: {len(summary)} designs")
        logger.info(f"  iPAE < {args.ipae_threshold}: {n_ipae}")
        logger.info(f"  Pass physics filters: {n_pass}")
        logger.info(f"  Structural clusters: {len(clusters)}")
        logger.info(f"Full summary: {summary_csv}")

        # Copy top cluster representatives to stage5
        for c_idx, cluster in enumerate(clusters):
            rep = cluster["representative"]
            if os.path.exists(rep):
                dst = stage5_dir / f"cluster{c_idx+1}_rep_{Path(rep).name}"
                shutil.copy2(rep, dst)

    # ==================================================================
    # Done
    # ==================================================================
    logger.info("")
    logger.info("=" * 70)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Output:     {output_dir}")
    logger.info(f"Checkpoint: {output_dir / 'checkpoint.json'}")
    logger.info(f"Log:        {output_dir / 'pipeline.log'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
