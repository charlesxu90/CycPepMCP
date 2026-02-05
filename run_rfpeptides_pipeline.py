#!/usr/bin/env python3
"""
RFpeptides Full Pipeline Orchestration
=======================================
Complete 5-stage cyclic peptide binder design workflow.

Stage 1: RFpeptides backbone generation (via MCP or pre-computed)
Stage 2: Iterative ProteinMPNN CA-only + Rosetta FastRelax (4 rounds)
Stage 3: AfCycDesign validation (iPAE filtering)
Stage 4: Rosetta interface metrics (ddG, SAP, CMS)
Stage 5: RMSD clustering + final selection

Usage:
    python run_rfpeptides_pipeline.py \\
        --stage1_dir /path/to/rfpeptides/job/output \\
        --target_pdb /path/to/target.pdb \\
        --output_dir results/mdm2_10k_production \\
        --num_rounds 4 \\
        --ipae_threshold 0.3 \\
        --ddg_threshold -50 \\
        --cms_threshold 300 \\
        --sap_threshold 35
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
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# ==============================================================================
# Environment Configuration
# ==============================================================================
PROTEINMPNN_ENV = Path("/mnt/data/done_projects/2026/BioMolMCP/ProteinMCP/tool-mcps/proteinmpnn_mcp/env")
PROTEINMPNN_PYTHON = PROTEINMPNN_ENV / "bin" / "python"
PROTEINMPNN_REPO = Path("/mnt/data/done_projects/2026/BioMolMCP/ProteinMCP/tool-mcps/proteinmpnn_mcp/repo/ProteinMPNN")
PROTEINMPNN_SCRIPT = Path("/mnt/data/done_projects/2026/BioMolMCP/ProteinMCP/tool-mcps/proteinmpnn_mcp/scripts/ca_only_design.py")
PROTEINMPNN_CA_WEIGHTS = PROTEINMPNN_REPO / "ca_model_weights"

ROSETTA_ENV = Path("/mnt/data/done_projects/2026/BioMolMCP/CycPepMCP/tool-mcps/rosetta_kic_mcp/env")
ROSETTA_PYTHON = ROSETTA_ENV / "bin" / "python"
ROSETTA_SCRIPTS_DIR = Path("/mnt/data/done_projects/2026/BioMolMCP/CycPepMCP/tool-mcps/rosetta_kic_mcp/scripts")
ROSETTA_RELAX_SCRIPT = ROSETTA_SCRIPTS_DIR / "cycpep_fast_relax.py"
ROSETTA_METRICS_SCRIPT = ROSETTA_SCRIPTS_DIR / "interface_metrics.py"
ROSETTA_RMSD_SCRIPT = ROSETTA_SCRIPTS_DIR / "rmsd_benchmark.py"

AFCYCDESIGN_ENV = Path("/mnt/data/done_projects/2026/BioMolMCP/CycPepMCP/tool-mcps/afcycdesign_mcp/env")
AFCYCDESIGN_PYTHON = AFCYCDESIGN_ENV / "bin" / "python"
AFCYCDESIGN_SCRIPTS_DIR = Path("/mnt/data/done_projects/2026/BioMolMCP/CycPepMCP/tool-mcps/afcycdesign_mcp/scripts")
AFCYCDESIGN_BINDER_SCRIPT = AFCYCDESIGN_SCRIPTS_DIR / "cyclic_binder_design.py"

# ==============================================================================
# Logging Setup
# ==============================================================================
def setup_logging(output_dir: Path) -> logging.Logger:
    logger = logging.getLogger("rfpeptides_pipeline")
    logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler(output_dir / "pipeline.log")
    fh.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


# ==============================================================================
# Checkpoint Management
# ==============================================================================
class CheckpointManager:
    """Track which designs have completed each stage for resume support."""

    def __init__(self, checkpoint_file: Path):
        self.file = checkpoint_file
        self.data = self._load()

    def _load(self) -> dict:
        if self.file.exists():
            with open(self.file) as f:
                return json.load(f)
        return {"stage2": {}, "stage3": {}, "stage4": {}, "stage5": {}}

    def save(self):
        with open(self.file, "w") as f:
            json.dump(self.data, f, indent=2)

    def is_done(self, stage: str, design_id: str) -> bool:
        return self.data.get(stage, {}).get(design_id, {}).get("done", False)

    def mark_done(self, stage: str, design_id: str, info: dict = None):
        if stage not in self.data:
            self.data[stage] = {}
        self.data[stage][design_id] = {"done": True, "timestamp": datetime.now().isoformat(), **(info or {})}
        self.save()

    def get_info(self, stage: str, design_id: str) -> dict:
        return self.data.get(stage, {}).get(design_id, {})


# ==============================================================================
# Helper Functions
# ==============================================================================
def find_backbone_pdbs(stage1_dir: Path) -> List[Path]:
    """Find all backbone PDB files from RFpeptides output."""
    patterns = ["*_cyclic_epitope_*.pdb", "*_cyclic_*.pdb", "design_*.pdb", "*.pdb"]
    pdbs = []
    for pat in patterns:
        pdbs = sorted(stage1_dir.glob(pat))
        # Filter out .trb files and non-PDB
        pdbs = [p for p in pdbs if p.suffix == ".pdb"]
        if pdbs:
            break
    return pdbs


def parse_fasta(fasta_file: Path) -> List[Tuple[str, str]]:
    """Parse FASTA file, return list of (header, sequence) tuples."""
    sequences = []
    header = ""
    seq_lines = []
    with open(fasta_file) as f:
        for line in f:
            line = line.strip()
            if line.startswith(">"):
                if header:
                    sequences.append((header, "".join(seq_lines)))
                header = line[1:]
                seq_lines = []
            else:
                seq_lines.append(line)
    if header:
        sequences.append((header, "".join(seq_lines)))
    return sequences


def extract_binder_sequence(fasta_file: Path, binder_chain_idx: int = 0) -> Optional[str]:
    """Extract the best designed binder sequence from ProteinMPNN FASTA output.

    ProteinMPNN outputs sequences for all chains separated by '/'.
    The binder (Chain A) is the first chain (index 0).
    We skip the first entry (wild-type/reference) and take the best designed sequence.
    """
    sequences = parse_fasta(fasta_file)
    if len(sequences) < 2:
        # Only wild-type, no designed sequences
        return None

    # sequences[0] is wild-type/reference, sequences[1:] are designed
    # Each sequence may contain multiple chains separated by '/'
    best_header, best_seq = sequences[1]  # First designed sequence (best score)

    # Split by chain separator
    chains = best_seq.split("/")
    if binder_chain_idx < len(chains):
        return chains[binder_chain_idx]
    return best_seq  # Single chain case


def run_subprocess(cmd: list, cwd: str = None, env: dict = None,
                   timeout: int = 7200, logger: logging.Logger = None) -> subprocess.CompletedProcess:
    """Run a subprocess with logging and error handling."""
    cmd_str = " ".join(str(c) for c in cmd)
    if logger:
        logger.debug(f"Running: {cmd_str}")
        logger.debug(f"  CWD: {cwd}")

    try:
        result = subprocess.run(
            cmd, cwd=cwd, env=env,
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            if logger:
                logger.error(f"Command failed (rc={result.returncode})")
                if result.stderr:
                    logger.error(f"STDERR: {result.stderr[-2000:]}")
                if result.stdout:
                    logger.debug(f"STDOUT: {result.stdout[-1000:]}")
        return result
    except subprocess.TimeoutExpired:
        if logger:
            logger.error(f"Command timed out after {timeout}s: {cmd_str}")
        raise
    except Exception as e:
        if logger:
            logger.error(f"Command error: {e}")
        raise


# ==============================================================================
# STAGE 2: Iterative ProteinMPNN + Rosetta FastRelax
# ==============================================================================
def run_proteinmpnn_ca_only(
    input_pdb: Path, output_dir: Path,
    chains: str = "A", temperature: float = 0.0001,
    num_sequences: int = 1, omit_AAs: str = "C",
    logger: logging.Logger = None
) -> Optional[Path]:
    """Run ProteinMPNN CA-only design on a backbone PDB.

    Returns path to output FASTA file, or None on failure.
    """
    output_dir = Path(output_dir).resolve()  # Always use absolute path
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(PROTEINMPNN_PYTHON),
        str(PROTEINMPNN_REPO / "protein_mpnn_run.py"),
        "--pdb_path", str(Path(input_pdb).resolve()),
        "--pdb_path_chains", chains,
        "--out_folder", str(output_dir),
        "--num_seq_per_target", str(num_sequences),
        "--sampling_temp", str(temperature),
        "--seed", "37",
        "--model_name", "v_48_020",
        "--batch_size", "1",
        "--path_to_model_weights", str(PROTEINMPNN_CA_WEIGHTS),
        "--ca_only",
    ]
    if omit_AAs:
        cmd.extend(["--omit_AAs", omit_AAs])

    result = run_subprocess(cmd, cwd=str(PROTEINMPNN_REPO), timeout=300, logger=logger)

    if result.returncode != 0:
        return None

    # Find output FASTA
    fasta_files = list(output_dir.glob("seqs/*.fa"))
    if not fasta_files:
        fasta_files = list(output_dir.glob("**/*.fa"))
    return fasta_files[0] if fasta_files else None


def thread_sequence_onto_backbone(
    backbone_pdb: Path, sequence: str, output_pdb: Path,
    binder_chain: str = "A", logger: logging.Logger = None
) -> bool:
    """Thread a designed sequence onto a backbone PDB using PyRosetta.

    Mutates each residue in the binder chain from GLY to the designed amino acid
    and rebuilds side chains.
    """
    thread_script = f'''
import sys
sys.path.insert(0, "{ROSETTA_SCRIPTS_DIR}")
from pyrosetta import *
from pyrosetta.rosetta.protocols.simple_moves import MutateResidue

init("-beta_nov16 -mute all")

pose = pose_from_pdb("{backbone_pdb}")
sequence = "{sequence}"
binder_chain = "{binder_chain}"

# Find residues in binder chain
chain_id = ord(binder_chain) - ord("A") + 1
binder_residues = []
for i in range(1, pose.total_residue() + 1):
    if pose.chain(i) == chain_id:
        binder_residues.append(i)

if len(binder_residues) != len(sequence):
    print(f"ERROR: Binder has {{len(binder_residues)}} residues but sequence has {{len(sequence)}} residues")
    sys.exit(1)

# Map 1-letter to 3-letter codes
aa_map = {{
    "A": "ALA", "R": "ARG", "N": "ASN", "D": "ASP", "C": "CYS",
    "E": "GLU", "Q": "GLN", "G": "GLY", "H": "HIS", "I": "ILE",
    "L": "LEU", "K": "LYS", "M": "MET", "F": "PHE", "P": "PRO",
    "S": "SER", "T": "THR", "W": "TRP", "Y": "TYR", "V": "VAL",
}}

for res_idx, aa in zip(binder_residues, sequence):
    if aa in aa_map:
        mutator = MutateResidue(res_idx, aa_map[aa])
        mutator.apply(pose)

pose.dump_pdb("{output_pdb}")
print(f"SUCCESS: Threaded {{len(sequence)}} residues onto {{len(binder_residues)}} positions")
'''
    # Write temp script
    tmp_script = output_pdb.parent / f"_thread_{output_pdb.stem}.py"
    with open(tmp_script, "w") as f:
        f.write(thread_script)

    result = run_subprocess(
        [str(ROSETTA_PYTHON), str(tmp_script)],
        cwd=str(ROSETTA_SCRIPTS_DIR),
        timeout=120,
        logger=logger
    )

    # Cleanup temp script
    tmp_script.unlink(missing_ok=True)

    if result.returncode != 0:
        if logger:
            logger.error(f"Threading failed: {result.stderr[-500:]}")
        return False

    return output_pdb.exists()


def run_rosetta_fast_relax(
    input_pdb: Path, output_dir: Path,
    rounds: int = 1,
    logger: logging.Logger = None
) -> Optional[Path]:
    """Run Rosetta FastRelax with PeptideCyclizeMover.

    Returns path to best relaxed PDB, or None on failure.
    """
    output_dir = Path(output_dir).resolve()  # Always use absolute path
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(ROSETTA_PYTHON),
        str(ROSETTA_RELAX_SCRIPT),
        "--input", str(Path(input_pdb).resolve()),
        "--output", str(output_dir),
        "--rounds", str(rounds),
    ]

    result = run_subprocess(cmd, cwd=str(ROSETTA_SCRIPTS_DIR), timeout=3600, logger=logger)

    if result.returncode != 0:
        return None

    # Find best relaxed PDB (lowest score from last round)
    relaxed_pdbs = sorted(output_dir.glob("*_round*.pdb"))
    if not relaxed_pdbs:
        relaxed_pdbs = sorted(output_dir.glob("*.pdb"))
    return relaxed_pdbs[-1] if relaxed_pdbs else None  # Last round is best (most refined)


def run_stage2_for_design(
    backbone_pdb: Path, design_id: str,
    stage2_dir: Path, num_rounds: int = 4,
    logger: logging.Logger = None,
    checkpoint: CheckpointManager = None,
) -> Optional[Dict]:
    """Run full Stage 2 (4 rounds of ProteinMPNN + Relax) for a single design."""

    design_dir = Path(stage2_dir).resolve() / design_id
    design_dir.mkdir(parents=True, exist_ok=True)

    current_pdb = backbone_pdb
    best_sequence = None

    for round_num in range(1, num_rounds + 1):
        round_id = f"{design_id}_round{round_num}"
        round_dir = design_dir / f"round{round_num}"

        # Check if this round already completed
        if checkpoint and checkpoint.is_done("stage2_rounds", round_id):
            info = checkpoint.get_info("stage2_rounds", round_id)
            prev_pdb = info.get("output_pdb")
            if prev_pdb and Path(prev_pdb).exists():
                current_pdb = Path(prev_pdb)
                best_sequence = info.get("sequence")
                if logger:
                    logger.info(f"  Round {round_num}: SKIPPED (checkpoint)")
                continue

        if logger:
            logger.info(f"  Round {round_num}: ProteinMPNN CA-only design...")

        # Step A: ProteinMPNN CA-only design
        mpnn_dir = round_dir / "mpnn"
        fasta_file = run_proteinmpnn_ca_only(
            input_pdb=current_pdb,
            output_dir=mpnn_dir,
            chains="A",
            temperature=0.0001,
            num_sequences=1,
            omit_AAs="C",
            logger=logger,
        )

        if not fasta_file:
            if logger:
                logger.error(f"  Round {round_num}: ProteinMPNN FAILED")
            return None

        # Extract designed binder sequence
        sequence = extract_binder_sequence(fasta_file, binder_chain_idx=0)
        if not sequence:
            if logger:
                logger.error(f"  Round {round_num}: No designed sequence found")
            return None

        best_sequence = sequence
        if logger:
            logger.info(f"  Round {round_num}: Designed sequence: {sequence}")

        # Step B: Thread sequence onto backbone
        threaded_pdb = round_dir / f"{design_id}_threaded_r{round_num}.pdb"
        success = thread_sequence_onto_backbone(
            backbone_pdb=current_pdb,
            sequence=sequence,
            output_pdb=threaded_pdb,
            binder_chain="A",
            logger=logger,
        )
        if not success:
            if logger:
                logger.error(f"  Round {round_num}: Sequence threading FAILED")
            return None

        # Step C: Rosetta FastRelax (1 relax round per iteration, not 4 sub-rounds)
        if logger:
            logger.info(f"  Round {round_num}: Rosetta FastRelax...")

        relax_dir = round_dir / "relax"
        relaxed_pdb = run_rosetta_fast_relax(
            input_pdb=threaded_pdb,
            output_dir=relax_dir,
            rounds=1,  # Single relax round per iteration
            logger=logger,
        )

        if not relaxed_pdb:
            if logger:
                logger.warning(f"  Round {round_num}: Relax FAILED, using threaded PDB")
            relaxed_pdb = threaded_pdb

        current_pdb = relaxed_pdb

        # Checkpoint this round
        if checkpoint:
            checkpoint.mark_done("stage2_rounds", round_id, {
                "output_pdb": str(relaxed_pdb),
                "sequence": sequence,
            })

        if logger:
            logger.info(f"  Round {round_num}: Complete -> {relaxed_pdb.name}")

    # Save final output
    final_pdb = design_dir / f"{design_id}_final.pdb"
    shutil.copy2(current_pdb, final_pdb)

    return {
        "design_id": design_id,
        "final_pdb": str(final_pdb),
        "sequence": best_sequence,
        "num_rounds": num_rounds,
    }


# ==============================================================================
# STAGE 3: AfCycDesign Validation
# ==============================================================================
def run_afcycdesign_validation(
    target_pdb: Path, binder_sequence: str, binder_len: int,
    output_pdb: Path, ipae_threshold: float = 0.3,
    logger: logging.Logger = None
) -> Optional[Dict]:
    """Run AfCycDesign binder design for validation.

    Returns dict with iPAE, RMSD, pLDDT metrics or None on failure.
    """
    cmd = [
        str(AFCYCDESIGN_PYTHON),
        str(AFCYCDESIGN_BINDER_SCRIPT),
        "--pdb", str(Path(target_pdb).resolve()),
        "--target_chain", "A",
        "--binder_len", str(binder_len),
        "--binder_seq", binder_sequence,
        "--output", str(Path(output_pdb).resolve()),
        "--num_recycles", "1",
        "--num_models", "2",
        "--optimizer", "pssm_semigreedy",
        "--ipae_threshold", str(ipae_threshold),
        # Note: NOT using --quiet so we can parse metrics from output
    ]

    result = run_subprocess(
        cmd, cwd=str(AFCYCDESIGN_SCRIPTS_DIR), timeout=1800, logger=logger
    )

    if result.returncode != 0:
        if logger:
            logger.error(f"AfCycDesign failed: {result.stderr[-500:]}")
        return None

    # Parse output for metrics
    metrics = {"ipae": None, "rmsd": None, "plddt": None}
    output_text = result.stdout + result.stderr
    for line in output_text.split("\n"):
        # AfCycDesign outputs "iPAE (Interface PAE): 0.123" format
        if "i_pae" in line.lower() or "ipae" in line.lower():
            # Match patterns like "i_pae: 0.123" or "iPAE (Interface PAE): 0.123"
            match = re.search(r"i_?pae[^:]*:\s*([0-9.]+)", line, re.IGNORECASE)
            if match:
                metrics["ipae"] = float(match.group(1))
        if "rmsd" in line.lower() and ":" in line:
            match = re.search(r"rmsd[^:]*:\s*([0-9.]+)", line, re.IGNORECASE)
            if match:
                metrics["rmsd"] = float(match.group(1))
        if "plddt" in line.lower() and ":" in line:
            match = re.search(r"plddt[^:]*:\s*([0-9.]+)", line, re.IGNORECASE)
            if match:
                metrics["plddt"] = float(match.group(1))

    # Also check for score.sc file
    score_file = output_pdb.parent / "score.sc"
    if score_file.exists():
        try:
            with open(score_file) as f:
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) >= 2:
                        try:
                            metrics["ipae"] = float(parts[1]) if metrics["ipae"] is None else metrics["ipae"]
                            metrics["rmsd"] = float(parts[2]) if len(parts) > 2 and metrics["rmsd"] is None else metrics["rmsd"]
                        except (ValueError, IndexError):
                            pass
        except Exception:
            pass

    return metrics


# ==============================================================================
# STAGE 4: Rosetta Interface Metrics
# ==============================================================================
def run_interface_metrics(
    input_pdbs: List[Path], output_dir: Path,
    peptide_chain: str = "A",
    ddg_threshold: float = -50.0,
    sap_threshold: float = 35.0,
    cms_threshold: float = 300.0,
    logger: logging.Logger = None,
) -> Optional[Dict]:
    """Run Rosetta interface metrics on a batch of PDB files."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Process in batches to avoid command line length issues
    batch_size = 50
    all_results = []

    for i in range(0, len(input_pdbs), batch_size):
        batch = input_pdbs[i:i + batch_size]
        batch_str = " ".join(str(p) for p in batch)

        cmd = [
            str(ROSETTA_PYTHON),
            str(ROSETTA_METRICS_SCRIPT),
            "--input",
        ] + [str(p) for p in batch] + [
            "--output", str(output_dir),
            "--peptide_chain", peptide_chain,
            "--ddg_threshold", str(ddg_threshold),
            "--sap_threshold", str(sap_threshold),
            "--cms_threshold", str(cms_threshold),
        ]

        result = run_subprocess(cmd, cwd=str(ROSETTA_SCRIPTS_DIR), timeout=7200, logger=logger)

        if result.returncode != 0:
            if logger:
                logger.warning(f"Interface metrics batch {i//batch_size} failed")
            continue

    # Parse results CSV
    csv_file = output_dir / "interface_metrics.csv"
    if csv_file.exists():
        with open(csv_file) as f:
            reader = csv.DictReader(f)
            all_results = list(reader)

    return {
        "metrics": all_results,
        "csv_file": str(csv_file),
        "n_pass": sum(1 for r in all_results if r.get("passes_filter") == "True"),
        "n_total": len(all_results),
    }


# ==============================================================================
# STAGE 5: RMSD Clustering and Final Selection
# ==============================================================================
def run_rmsd_clustering(
    design_pdbs: List[Path], output_dir: Path,
    rmsd_cutoff: float = 2.0,
    logger: logging.Logger = None,
) -> List[Dict]:
    """Simple greedy clustering by pairwise RMSD."""
    # For large sets, do greedy sequential clustering
    # Each PDB is assigned to the first cluster within rmsd_cutoff
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    clusters = []  # List of {"representative": pdb, "members": [pdbs]}

    for pdb in design_pdbs:
        assigned = False
        for cluster in clusters:
            # Compare with cluster representative using Rosetta RMSD
            rep = cluster["representative"]
            cmd = [
                str(ROSETTA_PYTHON),
                str(ROSETTA_RMSD_SCRIPT),
                "--input", str(pdb),
                "--native", str(rep),
                "--output", str(output_dir / "rmsd_tmp"),
                "--rmsd_cutoff", str(rmsd_cutoff),
            ]
            result = run_subprocess(cmd, cwd=str(ROSETTA_SCRIPTS_DIR), timeout=300, logger=logger)

            if result.returncode == 0:
                # Parse RMSD from output
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

    return clusters


# ==============================================================================
# Main Pipeline
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--stage1_dir", required=True, help="Directory with RFpeptides backbone PDBs")
    parser.add_argument("--target_pdb", required=True, help="Target protein PDB file")
    parser.add_argument("--output_dir", default="results/mdm2_10k_production", help="Output directory")
    parser.add_argument("--num_rounds", type=int, default=4, help="Number of ProteinMPNN+Relax rounds (default: 4)")
    parser.add_argument("--ipae_threshold", type=float, default=0.3, help="iPAE filter threshold (default: 0.3)")
    parser.add_argument("--ddg_threshold", type=float, default=-50.0, help="ddG filter threshold (default: -50)")
    parser.add_argument("--cms_threshold", type=float, default=300.0, help="CMS filter threshold (default: 300)")
    parser.add_argument("--sap_threshold", type=float, default=35.0, help="SAP filter threshold (default: 35)")
    parser.add_argument("--rmsd_cutoff", type=float, default=2.0, help="RMSD clustering cutoff (default: 2.0)")
    parser.add_argument("--start_stage", type=int, default=2, help="Stage to start from (default: 2)")
    parser.add_argument("--max_designs", type=int, default=None, help="Max designs to process (for testing)")
    parser.add_argument("--binder_length", type=int, default=12, help="Binder peptide length (default: 12)")

    args = parser.parse_args()

    # Setup - always use absolute paths
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    stage2_dir = output_dir / "stage2_designed"
    stage3_dir = output_dir / "stage3_validated"
    stage4_dir = output_dir / "stage4_filtered"
    stage5_dir = output_dir / "stage5_final"
    for d in [stage2_dir, stage3_dir, stage4_dir, stage5_dir]:
        d.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(output_dir)
    checkpoint = CheckpointManager(output_dir / "checkpoint.json")

    logger.info("=" * 70)
    logger.info("RFpeptides Full Pipeline - Production Run")
    logger.info("=" * 70)
    logger.info(f"Stage 1 dir:     {args.stage1_dir}")
    logger.info(f"Target PDB:      {args.target_pdb}")
    logger.info(f"Output dir:      {output_dir}")
    logger.info(f"Rounds:          {args.num_rounds}")
    logger.info(f"iPAE threshold:  {args.ipae_threshold}")
    logger.info(f"ddG threshold:   {args.ddg_threshold}")
    logger.info(f"CMS threshold:   {args.cms_threshold}")
    logger.info(f"SAP threshold:   {args.sap_threshold}")
    logger.info(f"RMSD cutoff:     {args.rmsd_cutoff}")
    logger.info(f"Binder length:   {args.binder_length}")

    # Save config
    config = vars(args)
    config["start_time"] = datetime.now().isoformat()
    with open(output_dir / "pipeline_config.json", "w") as f:
        json.dump(config, f, indent=2)

    # =========================================================================
    # Find backbone PDBs from Stage 1
    # =========================================================================
    backbone_pdbs = find_backbone_pdbs(Path(args.stage1_dir))
    if args.max_designs:
        backbone_pdbs = backbone_pdbs[:args.max_designs]

    logger.info(f"Found {len(backbone_pdbs)} backbone PDBs from Stage 1")
    if not backbone_pdbs:
        logger.error("No backbone PDBs found! Check stage1_dir.")
        return 1

    # =========================================================================
    # STAGE 2: Iterative ProteinMPNN + Rosetta FastRelax
    # =========================================================================
    if args.start_stage <= 2:
        logger.info("")
        logger.info("=" * 70)
        logger.info("STAGE 2: Iterative ProteinMPNN + Rosetta FastRelax")
        logger.info(f"  {len(backbone_pdbs)} designs x {args.num_rounds} rounds = {len(backbone_pdbs) * args.num_rounds} total models")
        logger.info("=" * 70)

        stage2_results = []
        for idx, backbone_pdb in enumerate(backbone_pdbs):
            design_id = backbone_pdb.stem
            logger.info(f"\n[{idx+1}/{len(backbone_pdbs)}] Processing {design_id}")

            if checkpoint.is_done("stage2", design_id):
                info = checkpoint.get_info("stage2", design_id)
                stage2_results.append(info)
                logger.info(f"  SKIPPED (checkpoint)")
                continue

            result = run_stage2_for_design(
                backbone_pdb=backbone_pdb,
                design_id=design_id,
                stage2_dir=stage2_dir,
                num_rounds=args.num_rounds,
                logger=logger,
                checkpoint=checkpoint,
            )

            if result:
                checkpoint.mark_done("stage2", design_id, result)
                stage2_results.append(result)
                logger.info(f"  COMPLETE: {result['sequence']}")
            else:
                logger.error(f"  FAILED: {design_id}")

        # Collect Stage 2 outputs
        logger.info(f"\nStage 2 Summary: {len(stage2_results)}/{len(backbone_pdbs)} designs completed")

    # =========================================================================
    # Collect Stage 2 results for downstream stages
    # =========================================================================
    stage2_data = []
    for design_id, info in checkpoint.data.get("stage2", {}).items():
        if info.get("done") and info.get("final_pdb") and Path(info["final_pdb"]).exists():
            stage2_data.append(info)

    logger.info(f"Stage 2 designs available for validation: {len(stage2_data)}")

    # =========================================================================
    # STAGE 3: AfCycDesign Validation
    # =========================================================================
    if args.start_stage <= 3 and stage2_data:
        logger.info("")
        logger.info("=" * 70)
        logger.info(f"STAGE 3: AfCycDesign Validation (iPAE < {args.ipae_threshold})")
        logger.info(f"  {len(stage2_data)} designs to validate")
        logger.info("=" * 70)

        target_pdb = Path(args.target_pdb)
        stage3_passed = []

        for idx, design_info in enumerate(stage2_data):
            design_id = design_info["design_id"]
            sequence = design_info["sequence"]

            logger.info(f"\n[{idx+1}/{len(stage2_data)}] Validating {design_id}: {sequence}")

            if checkpoint.is_done("stage3", design_id):
                info = checkpoint.get_info("stage3", design_id)
                if info.get("passed"):
                    stage3_passed.append(info)
                logger.info(f"  SKIPPED (checkpoint) - iPAE={info.get('ipae', 'N/A')}")
                continue

            output_pdb = stage3_dir / design_id / f"{design_id}_afcyc.pdb"
            output_pdb.parent.mkdir(parents=True, exist_ok=True)

            metrics = run_afcycdesign_validation(
                target_pdb=target_pdb,
                binder_sequence=sequence,
                binder_len=args.binder_length,
                output_pdb=output_pdb,
                ipae_threshold=args.ipae_threshold,
                logger=logger,
            )

            if metrics:
                ipae = metrics.get("ipae")
                passed = ipae is not None and ipae < args.ipae_threshold

                result_info = {
                    **design_info,
                    **metrics,
                    "passed": passed,
                    "afcyc_pdb": str(output_pdb) if output_pdb.exists() else None,
                }

                checkpoint.mark_done("stage3", design_id, result_info)

                if passed:
                    stage3_passed.append(result_info)
                    logger.info(f"  PASS: iPAE={ipae:.4f}, RMSD={metrics.get('rmsd', 'N/A')}")
                else:
                    logger.info(f"  FAIL: iPAE={ipae}")
            else:
                checkpoint.mark_done("stage3", design_id, {**design_info, "passed": False, "error": "validation_failed"})
                logger.error(f"  FAILED: AfCycDesign error")

        logger.info(f"\nStage 3 Summary: {len(stage3_passed)}/{len(stage2_data)} designs passed (iPAE < {args.ipae_threshold})")

    # =========================================================================
    # Collect Stage 3 results
    # =========================================================================
    stage3_passed = []
    for design_id, info in checkpoint.data.get("stage3", {}).items():
        if info.get("done") and info.get("passed"):
            stage3_passed.append(info)

    # =========================================================================
    # STAGE 4: Rosetta Interface Metrics
    # =========================================================================
    if args.start_stage <= 4 and stage3_passed:
        logger.info("")
        logger.info("=" * 70)
        logger.info(f"STAGE 4: Rosetta Interface Metrics")
        logger.info(f"  Thresholds: ddG < {args.ddg_threshold}, SAP < {args.sap_threshold}, CMS > {args.cms_threshold}")
        logger.info(f"  {len(stage3_passed)} designs to evaluate")
        logger.info("=" * 70)

        # Collect PDB files for metrics computation
        pdbs_for_metrics = []
        for info in stage3_passed:
            pdb_path = info.get("final_pdb")
            if pdb_path and Path(pdb_path).exists():
                pdbs_for_metrics.append(Path(pdb_path))

        if pdbs_for_metrics:
            metrics_result = run_interface_metrics(
                input_pdbs=pdbs_for_metrics,
                output_dir=stage4_dir,
                peptide_chain="A",
                ddg_threshold=args.ddg_threshold,
                sap_threshold=args.sap_threshold,
                cms_threshold=args.cms_threshold,
                logger=logger,
            )

            if metrics_result:
                # Merge metrics with design info
                for metric_entry in metrics_result["metrics"]:
                    design_id = Path(metric_entry.get("pdb", "")).stem.replace("_final", "")
                    checkpoint.mark_done("stage4", design_id, metric_entry)

                logger.info(f"\nStage 4 Summary: {metrics_result['n_pass']}/{metrics_result['n_total']} designs passed all filters")
        else:
            logger.warning("No PDB files available for interface metrics")

    # =========================================================================
    # Collect Stage 4 results
    # =========================================================================
    stage4_passed = []
    for design_id, info in checkpoint.data.get("stage4", {}).items():
        if info.get("done") and info.get("passes_filter") in [True, "True"]:
            stage4_passed.append(info)

    # =========================================================================
    # STAGE 5: RMSD Clustering and Final Selection
    # =========================================================================
    if args.start_stage <= 5 and stage4_passed:
        logger.info("")
        logger.info("=" * 70)
        logger.info("STAGE 5: RMSD Clustering and Final Selection")
        logger.info(f"  {len(stage4_passed)} designs for clustering")
        logger.info("=" * 70)

        # Get PDB files
        final_pdbs = []
        for info in stage4_passed:
            pdb = info.get("pdb")
            if pdb and Path(pdb).exists():
                final_pdbs.append(Path(pdb))

        if final_pdbs:
            clusters = run_rmsd_clustering(
                design_pdbs=final_pdbs,
                output_dir=stage5_dir,
                rmsd_cutoff=args.rmsd_cutoff,
                logger=logger,
            )

            # Rank within clusters by ddG
            for cluster in clusters:
                cluster["members_info"] = []
                for member_pdb in cluster["members"]:
                    member_id = Path(member_pdb).stem
                    # Find metrics from stage4
                    for info in stage4_passed:
                        if info.get("pdb") and Path(info["pdb"]).stem == member_id:
                            cluster["members_info"].append(info)
                            break

                cluster["members_info"].sort(key=lambda x: float(x.get("ddg", 0)))

            # Save clustering results
            with open(stage5_dir / "clusters.json", "w") as f:
                json.dump(clusters, f, indent=2, default=str)

            # Generate final report
            report_lines = [
                "# RFpeptides Design Results",
                "",
                "## Job Summary",
                f"| Parameter | Value |",
                f"|-----------|-------|",
                f"| Target | {args.target_pdb} |",
                f"| Binder Length | {args.binder_length} residues |",
                f"| Backbones Generated | {len(backbone_pdbs)} |",
                f"| Stage 2 Completed | {len(stage2_data)} |",
                f"| Stage 3 Passed (iPAE < {args.ipae_threshold}) | {len(stage3_passed)} |",
                f"| Stage 4 Passed (ddG/SAP/CMS) | {len(stage4_passed)} |",
                f"| Structural Clusters | {len(clusters)} |",
                "",
                "## Top Designs",
                "",
            ]

            # Select top designs from each cluster
            top_designs = []
            for c_idx, cluster in enumerate(clusters):
                report_lines.append(f"### Cluster {c_idx+1} ({len(cluster['members'])} members)")
                rep = cluster.get("representative", "N/A")
                report_lines.append(f"Representative: {Path(rep).name}")
                report_lines.append("")

                for m_info in cluster["members_info"][:2]:  # Top 2 per cluster
                    report_lines.append(f"| Metric | Value |")
                    report_lines.append(f"|--------|-------|")
                    report_lines.append(f"| PDB | {m_info.get('name', 'N/A')} |")
                    report_lines.append(f"| ddG | {m_info.get('ddg', 'N/A')} |")
                    report_lines.append(f"| SAP | {m_info.get('sap', 'N/A')} |")
                    report_lines.append(f"| CMS | {m_info.get('cms', 'N/A')} |")
                    report_lines.append("")
                    top_designs.append(m_info)

            # Save report
            with open(stage5_dir / "final_report.md", "w") as f:
                f.write("\n".join(report_lines))

            # Copy top design PDBs to final directory
            for idx, design in enumerate(top_designs):
                src = design.get("pdb")
                if src and Path(src).exists():
                    dst = stage5_dir / f"top_{idx+1}_{Path(src).name}"
                    shutil.copy2(src, dst)

            logger.info(f"\nStage 5 Summary:")
            logger.info(f"  Clusters: {len(clusters)}")
            logger.info(f"  Top designs: {len(top_designs)}")
            logger.info(f"  Report: {stage5_dir / 'final_report.md'}")

    # =========================================================================
    # Final Summary
    # =========================================================================
    logger.info("")
    logger.info("=" * 70)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Checkpoint file:  {output_dir / 'checkpoint.json'}")
    logger.info(f"Pipeline log:     {output_dir / 'pipeline.log'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
