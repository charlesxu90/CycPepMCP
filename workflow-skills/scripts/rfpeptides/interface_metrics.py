#!/usr/bin/env python3
"""
Script: interface_metrics.py
Description: Compute interface metrics (ddG, SAP, CMS) for cyclic peptide-target complexes

Based on the RFpeptides pipeline (Rettie et al., Nature Chemical Biology 2025).
Applies PeptideCyclizeMover, Cartesian minimization, then computes ddG, SAP, and CMS.
XML config: configs/rosetta_interface_metrics.xml

Usage:
    python scripts/interface_metrics.py --input <complex.pdb> --output <output_dir>

Example:
    python scripts/interface_metrics.py --input complex.pdb --output results/metrics --peptide_chain B
"""

# ==============================================================================
# Minimal Imports (only essential packages)
# ==============================================================================
import argparse
import csv
import os
import sys
import random
import time
from pathlib import Path
from typing import Union, Optional, Dict, Any, List

# Optional PyRosetta (with graceful fallback)
try:
    from pyrosetta import *
    from pyrosetta.rosetta import protocols, core
    PYROSETTA_AVAILABLE = True
except ImportError:
    PYROSETTA_AVAILABLE = False

# ==============================================================================
# Configuration
# ==============================================================================
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIGS_DIR = SCRIPT_DIR.parent / "configs"
XML_FILE = CONFIGS_DIR / "rosetta_interface_metrics.xml"

DEFAULT_CONFIG = {
    "xml_file": str(XML_FILE),
    "peptide_chain": "B",
    "score_function": "beta_nov16",
    "filtering": {
        "ddg_threshold": -40.0,
        "sap_threshold": 35.0,
        "cms_threshold": 300.0,
    },
}

# ==============================================================================
# Inlined Utility Functions
# ==============================================================================
def validate_pdb_file(file_path: Union[str, Path]) -> bool:
    """Validate that input file exists and has .pdb extension."""
    file_path = Path(file_path)
    return file_path.exists() and file_path.suffix.lower() == '.pdb'


def generate_demo_metrics(input_pdbs: List[str], output_dir: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate demonstration output when PyRosetta is not available."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating demo interface metrics for {len(input_pdbs)} structure(s)")

    results = []
    for pdb in input_pdbs:
        name = Path(pdb).stem
        time.sleep(0.05)

        ddg = round(random.uniform(-60.0, -10.0), 2)
        sap = round(random.uniform(15.0, 50.0), 2)
        cms = round(random.uniform(150.0, 500.0), 2)

        thresholds = config.get("filtering", DEFAULT_CONFIG["filtering"])
        passes = (
            ddg < thresholds["ddg_threshold"]
            and sap < thresholds["sap_threshold"]
            and cms > thresholds["cms_threshold"]
        )

        entry = {
            "name": name,
            "pdb": pdb,
            "ddg": ddg,
            "sap": sap,
            "cms": cms,
            "passes_filter": passes,
            "source": "SYNTHETIC_DEMO",
        }
        results.append(entry)
        status = "PASS" if passes else "FAIL"
        print(f"  {name}: ddG={ddg:.1f}  SAP={sap:.1f}  CMS={cms:.1f}  [{status}]")

    # Write scores file
    scores_file = output_dir / "interface_metrics.csv"
    with open(scores_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "pdb", "ddg", "sap", "cms", "passes_filter", "source"])
        writer.writeheader()
        writer.writerows(results)

    # Write summary
    n_pass = sum(1 for r in results if r["passes_filter"])
    summary_file = output_dir / "metrics_summary.txt"
    with open(summary_file, "w") as f:
        f.write("# Interface Metrics Summary (RFpeptides-style filtering)\n")
        f.write(f"# Total structures: {len(results)}\n")
        f.write(f"# Passing filters: {n_pass}\n")
        thresholds = config.get("filtering", DEFAULT_CONFIG["filtering"])
        f.write(f"# Thresholds: ddG < {thresholds['ddg_threshold']}, "
                f"SAP < {thresholds['sap_threshold']}, "
                f"CMS > {thresholds['cms_threshold']}\n")

    return {
        "metrics": results,
        "scores_file": str(scores_file),
        "summary_file": str(summary_file),
        "n_pass": n_pass,
        "n_total": len(results),
        "output_directory": str(output_dir),
    }


# ==============================================================================
# Core Function
# ==============================================================================
def run_interface_metrics(
    input_files: Union[str, Path, List[Union[str, Path]]],
    output_file: Optional[Union[str, Path]] = None,
    config: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Compute Rosetta interface metrics for cyclic peptide-target complexes.

    Applies PeptideCyclizeMover, Cartesian interface minimization, then
    computes ddG (5 repeats, extreme value removal), SAP, and CMS.

    Args:
        input_files: Path to PDB or list of PDB paths
        output_file: Path to output directory (optional)
        config: Configuration dict (uses DEFAULT_CONFIG if not provided)
        **kwargs: Override specific config parameters

    Returns:
        Dict containing result, output_file, and metadata.

    Example:
        >>> result = run_interface_metrics("complex.pdb", "output_dir")
        >>> print(result['result']['metrics'])
    """
    config = {**DEFAULT_CONFIG, **(config or {}), **kwargs}

    # Normalize input to list
    if isinstance(input_files, (str, Path)):
        input_files = [input_files]
    input_files = [str(Path(f)) for f in input_files]

    for f in input_files:
        if not validate_pdb_file(f):
            raise FileNotFoundError(f"Input PDB file not found or invalid: {f}")

    if output_file is None:
        output_dir = Path("interface_metrics_results")
    else:
        output_dir = Path(output_file)

    # No silent fallback: a failure here must stop the pipeline rather than emit
    # synthetic numbers that are indistinguishable from computed ones downstream.
    # Demo output is opt-in only and is never reachable from a production run.
    if config.get("allow_demo"):
        print("WARNING: --allow-demo set - emitting SYNTHETIC metrics, not for analysis")
        result = generate_demo_metrics(input_files, str(output_dir), config)
    elif not PYROSETTA_AVAILABLE:
        raise RuntimeError(
            "PyRosetta is not available, so interface metrics cannot be computed. "
            "Install PyRosetta in this environment, or pass --allow-demo to emit "
            "clearly-labelled synthetic values for testing."
        )
    else:
        result = execute_pyrosetta_metrics(input_files, str(output_dir), config)

    return {
        "result": result,
        "output_file": str(output_dir),
        "metadata": {
            "input_files": input_files,
            "config": config,
            "pyrosetta_available": PYROSETTA_AVAILABLE,
        },
    }


def _get_chain_order(pdb_path: str) -> List[str]:
    """Read a PDB file and return chain IDs in order of first appearance."""
    seen = []
    with open(pdb_path, "r") as f:
        for line in f:
            if line.startswith(("ATOM", "HETATM")):
                ch = line[21]
                if ch not in seen:
                    seen.append(ch)
    return seen


def _map_peptide_chain_to_selector(pdb_path: str, peptide_chain: str) -> str:
    """Map a PDB chain letter to the XML selector name (A or B).

    The XML defines chainA=chains '1' (first chain) and chainB=chains '2'
    (second chain). This function determines whether the peptide chain
    letter corresponds to the first or second chain in the PDB file and
    returns the matching selector suffix ('A' or 'B').
    """
    chain_order = _get_chain_order(pdb_path)
    if peptide_chain not in chain_order:
        raise ValueError(
            f"Peptide chain '{peptide_chain}' not found in {pdb_path}. "
            f"Available chains: {chain_order}"
        )
    idx = chain_order.index(peptide_chain)
    if idx == 0:
        return "A"
    elif idx == 1:
        return "B"
    else:
        raise ValueError(
            f"Peptide chain '{peptide_chain}' is chain #{idx + 1} in {pdb_path}, "
            f"but the XML only supports 2-chain complexes (target + peptide)."
        )


def execute_pyrosetta_metrics(input_pdbs: List[str], output_dir: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Execute actual Rosetta interface metrics calculation."""
    print("PyRosetta available - computing interface metrics")

    seed = config.get("seed")
    init_flags = "-beta_nov16"
    if seed is not None:
        init_flags += f" -constant_seed -jran {int(seed)}"
    init(init_flags)

    xml_path = config.get("xml_file", str(XML_FILE))
    if not Path(xml_path).exists():
        raise FileNotFoundError(f"XML config not found: {xml_path}")

    peptide_chain = config.get("peptide_chain", "B")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for pdb_path in input_pdbs:
        name = Path(pdb_path).stem
        print(f"  Processing: {name}")

        # Map the PDB chain letter to the XML selector name
        selector_suffix = _map_peptide_chain_to_selector(pdb_path, peptide_chain)
        print(f"    Peptide chain '{peptide_chain}' -> XML selector 'chain{selector_suffix}'")

        # Read XML and substitute template variable with the selector suffix
        with open(xml_path, "r") as f:
            xml_content = f.read()
        xml_content = xml_content.replace("%%chain%%", selector_suffix)
        # CMS is asymmetric: binder_selector must be the peptide, target_selector
        # the partner chain. Substituted alongside %%chain%% so the filter follows
        # --peptide_chain instead of assuming the peptide is the first chain.
        xml_content = xml_content.replace(
            "%%target%%", "B" if selector_suffix == "A" else "A"
        )

        objs = protocols.rosetta_scripts.XmlObjects.create_from_string(xml_content)

        pcm = objs.get_mover("pcm")
        minimize_interface = objs.get_mover("minimize_interface")
        ddg_filter = objs.get_filter("ddg")
        cms_filter = objs.get_filter("contact_molecular_surface")
        sap_metric = objs.get_simple_metric("sap_score")

        pose = pose_from_pdb(pdb_path)

        # Apply protocol: pcm -> minimize -> pcm -> compute metrics
        pcm.apply(pose)
        minimize_interface.apply(pose)
        pcm.apply(pose)

        ddg_val = ddg_filter.report_sm(pose)
        cms_val = cms_filter.report_sm(pose)
        sap_val = sap_metric.calculate(pose)

        thresholds = config.get("filtering", DEFAULT_CONFIG["filtering"])
        passes = (
            ddg_val < thresholds["ddg_threshold"]
            and sap_val < thresholds["sap_threshold"]
            and cms_val > thresholds["cms_threshold"]
        )

        entry = {
            "name": name,
            "pdb": pdb_path,
            "ddg": round(ddg_val, 2),
            "sap": round(sap_val, 2),
            "cms": round(cms_val, 2),
            "passes_filter": passes,
            "source": "pyrosetta",
        }
        results.append(entry)
        status = "PASS" if passes else "FAIL"
        print(f"    ddG={ddg_val:.1f}  SAP={sap_val:.1f}  CMS={cms_val:.1f}  [{status}]")

    # Write scores file
    scores_file = output_dir / "interface_metrics.csv"
    with open(scores_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "pdb", "ddg", "sap", "cms", "passes_filter", "source"])
        writer.writeheader()
        writer.writerows(results)

    n_pass = sum(1 for r in results if r["passes_filter"])

    return {
        "metrics": results,
        "scores_file": str(scores_file),
        "n_pass": n_pass,
        "n_total": len(results),
        "output_directory": str(output_dir),
    }


# ==============================================================================
# CLI Interface
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", "-i", required=True, nargs="+", help="Input PDB file(s) (cyclic peptide-target complexes)")
    parser.add_argument("--output", "-o", help="Output directory path")
    parser.add_argument("--config", "-c", help="Config file (JSON)")
    parser.add_argument("--peptide_chain", default="B", help="Peptide chain ID (default: B)")
    parser.add_argument("--xml", help="Path to RosettaScripts XML (default: configs/rosetta_interface_metrics.xml)")
    parser.add_argument("--ddg_threshold", type=float, default=-40.0, help="ddG filter threshold (default: -40)")
    parser.add_argument("--sap_threshold", type=float, default=35.0, help="SAP filter threshold (default: 35)")
    parser.add_argument("--cms_threshold", type=float, default=300.0, help="CMS filter threshold (default: 300)")
    parser.add_argument("--seed", type=int, help="Fixed PyRosetta RNG seed (-constant_seed -jran); omit for a random seed")
    parser.add_argument("--allow-demo", dest="allow_demo", action="store_true",
                        help="Emit SYNTHETIC random metrics instead of computing them. Testing only - never for analysis.")

    args = parser.parse_args()

    config = None
    if args.config:
        import json
        with open(args.config) as f:
            config = json.load(f)

    extra_kwargs = {
        "peptide_chain": args.peptide_chain,
        "seed": args.seed,
        "allow_demo": args.allow_demo,
        "filtering": {
            "ddg_threshold": args.ddg_threshold,
            "sap_threshold": args.sap_threshold,
            "cms_threshold": args.cms_threshold,
        },
    }
    if args.xml:
        extra_kwargs["xml_file"] = args.xml

    # Handle comma-separated input files (from MCP job manager)
    input_files = []
    for item in args.input:
        input_files.extend(item.split(","))
    input_files = [f.strip() for f in input_files if f.strip()]

    try:
        result = run_interface_metrics(
            input_files=input_files,
            output_file=args.output,
            config=config,
            **extra_kwargs,
        )

        n_pass = result["result"]["n_pass"]
        n_total = result["result"]["n_total"]
        print(f"Success: {n_pass}/{n_total} designs pass filters -> {result['output_file']}")
        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
