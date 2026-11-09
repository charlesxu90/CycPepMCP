#!/usr/bin/env python3
"""HELM-GPT multi-target benchmark figures.

The campaign is 3 targets, each sampling ~12,000 macrocycles down to the 20
that reached structural evaluation. Each panel is drawn as a standalone
print-sized PDF and nine of them are composed onto a 3x3 summary sheet, in the
same visual vocabulary and the same sheet layout as the AfCycDesign and
RFpeptides benchmark figures: violin + box + strip for every per-target
distribution, one colour per target throughout, centred plain panel titles,
three-line table, Arial at 6-7 pt, 0.3 pt axes.

Sheet panels:

  a  predicted Kd by target        - over the 20 that reached Phase 2
  b  predicted permeability by target
  c  AlphaFold3 iPTM by target
  d  Gnina CNN affinity by target
  e  what the RL actually optimised, in objective space - the two reward
     terms move together for one target, barely at all for another
  f  where the ~12,000 generated macrocycles went: the permeability gate does
     all the filtering and the affinity gate removes almost nothing
  g  whether the Phase-1 reward survives independent structural evaluation -
     the top 20 are reordered substantially by Phase 2
  h  whether the two structure predictors agree on the same complexes - they
     do not, and the composite score uses only the more optimistic of them
  i  best candidate per target, three-line table

The gate strip over all five quality metrics stays standalone: it needs the
full page width. Panels a-d carry no threshold line and no best-candidate
marker, so an arm is read through its distribution rather than through its
single luckiest candidate; the strip is where the thresholds live.

Panels g and h use emphasis against the identity line, because there the
subject is the disagreement rather than the identity of the targets.

Usage: python3 helmgpt_benchmark_figure.py [--results-root DIR] [--outdir DIR]
"""
import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import (  # noqa: E402
    LogLocator, NullFormatter, ScalarFormatter)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plot_style_utils import (  # noqa: E402
    ANNOT_FONTSIZE, BASE_FONTSIZE, CAT_PALETTE, DOT_ALPHA,
    DOT_SIZE, MEDIAN_LW, MERGED_2x3_MM, RULE_LW,
    TABLE_FONTSIZE, TABLE_SIZE, TIER_PASS, TITLE_FONTSIZE, XLABEL_FONTSIZE,
    apply_nature_rcparams, mm_size, prettify_ax, restyle_panel_title,
    save_pdf, simple_ax, style_axis_vbar, style_violin, thin_legend,
)

# Per-target panels at the standalone size. Wider than PANEL_SIZE because
# KRAS-G12D and PD-1/PD-L1 are long tick labels, which collide at 45 mm; this
# is the width the same panel gets in a cell of the 3x3 sheet.
WIDE_PANEL = mm_size(55.0, 42.0)

DEFAULT_ROOT = "/home/xux/Desktop/AgentMCP/CycPepMCP/results/helmgpt_3target"
RUN = "phase1_20261102_192136"

# Display order is worst-to-best up the y axis, on the campaign's own headline
# metric (predicted affinity of the selected candidates).
ORDER = ["pd1pdl1", "kras", "mdm2p53"]
LABEL = {"kras": "KRAS-G12D", "mdm2p53": "MDM2/p53", "pd1pdl1": "PD-1/PD-L1"}
KD_COL = {"kras": "raw_kras_kd", "mdm2p53": "raw_mdm2p53_kd",
          "pd1pdl1": "raw_pd1pdl1_kd"}

# Phase-1 reward gates and Phase-2 quality thresholds (CLAUDE.md, HELM-GPT).
GATES = {"kd_nm": 10000.0, "perm": -6.0, "iptm": 0.60, "cnn": 6.0}

INK = "#333333"
MUTED = "#8A8A8A"
COLOUR = {"kras": CAT_PALETTE[0], "mdm2p53": CAT_PALETTE[2],
          "pd1pdl1": CAT_PALETTE[4]}


def load(root):
    """Phase-1 population, Phase-1/2/3 funnel counts, and the final 20 per target.

    Track A (Boltz-2) and track B (AlphaFold3) are joined back onto the Phase-3
    ranking through the Phase-2 candidate rank, which is the only key the three
    files share - the ranking table carries no SMILES hash.
    """
    pop, final, funnel = {}, [], {}
    for target in ORDER:
        run = os.path.join(root, f"{target}_perm", RUN)
        agg = pd.read_csv(os.path.join(run, "phase1_aggregated.csv"))
        agg["kd_nm"] = 10.0 ** agg[KD_COL[target]]
        pop[target] = agg

        summary = json.load(open(os.path.join(run, "phase1_summary.json")))
        rank = pd.read_csv(os.path.join(run, "phase3_final_ranking.csv"))
        track_a = pd.read_csv(os.path.join(run, "phase2_track_a",
                                           "track_a_results.csv"))
        track_b = pd.read_csv(os.path.join(run, "phase2_track_b",
                                           "track_b_results.csv"))
        merged = (rank
                  .merge(track_a[["rank", "smiles_hash"]], on="rank")
                  .merge(track_b[["smiles_hash", "iptm", "ptm"]],
                         on="smiles_hash"))
        if len(merged) != len(rank):
            raise SystemExit(f"{target}: track join lost rows "
                             f"({len(merged)} of {len(rank)})")
        merged["target"] = target
        final.append(merged)

        kd_ok = int((agg.kd_nm < GATES["kd_nm"]).sum())
        funnel[target] = {
            "generated": summary["rows_total"],
            "parsed": summary["rows_unique_valid"],
            "kd_only": kd_ok,
            "both": summary["rows_pass_phase1_thresholds"],
            "selected": len(merged),
        }
    return pop, pd.concat(final, ignore_index=True), funnel


# --------------------------------------------------------------------------
# Where the ~12,000 generated macrocycles went
# --------------------------------------------------------------------------
# Left edge of the funnel's log x axis, and the left edge of its bars.
XMIN = 8.0

STAGES = [("generated", "generated"), ("parsed", "parsed"),
          ("kd_only", "$K_\\mathrm{d}$ gate"), ("both", "both gates"),
          ("selected", "to Phase 2")]


def panel_funnel(ax, funnel):
    """Attrition from generation to structural evaluation, per target.

    Bars only: with the per-bar counts removed the stage axis and the log x
    axis carry the shape of the funnel, which is what the panel is for. The
    exact numbers are in the campaign summary and in the manuscript text.

    The target key is a horizontal strip above the axes rather than a block
    inside them, and the panel carries no title of its own - on the sheet the
    letter is added above the key, and standalone the caption does the naming.
    """
    height = 0.26
    for i, target in enumerate(ORDER):
        counts = np.array([funnel[target][key] for key, _ in STAGES],
                          dtype=float)
        ys = np.arange(len(STAGES)) + (i - 1) * height
        # Bars start at the axis minimum, not at 0: on a log axis 0 maps to
        # -inf, which matplotlib writes into the PDF as a coordinate near
        # -33,000 pt. That is past Illustrator's canvas limit, so the panel
        # cannot be pasted into another document ("the requested
        # transformation would make some objects too large"). Starting at
        # XMIN is visually identical, since the axis is clipped there anyway.
        ax.barh(ys, counts - XMIN, left=XMIN, height=height * 0.92,
                color=COLOUR[target], linewidth=0, alpha=0.85, zorder=3,
                label=LABEL[target])

    thin_legend(ax, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3,
                columnspacing=1.2)

    ax.set_xscale("log")
    ax.set_xlim(XMIN, 6.0e4)
    ax.set_yticks(range(len(STAGES)))
    ax.set_yticklabels([name for _, name in STAGES], fontsize=BASE_FONTSIZE)
    ax.set_ylim(-0.6, len(STAGES) - 0.35)
    ax.invert_yaxis()
    ax.set_xlabel("macrocycles", fontsize=XLABEL_FONTSIZE)
    prettify_ax(ax)
    ax.yaxis.grid(False)


# --------------------------------------------------------------------------
# Per-metric jitter by target (standalone panels)
# --------------------------------------------------------------------------
def jitter_by_target(ax, final, column, ylabel, title, logy=False):
    """Violin + strip of one metric, one column per target.

    No gate line: the gate strip panel carries all five thresholds together,
    and repeating one here would suggest this metric decides on its own. Every
    column is the whole arm (n = 20), not a sample, but those 20 were already
    selected on the Phase-1 composite, so the spread is a truncated one.
    """
    style_axis_vbar(ax)
    rng = np.random.default_rng(42)
    for x, target in enumerate(ORDER):
        values = final.loc[final.target == target, column].to_numpy()
        colour = COLOUR[target]
        parts = ax.violinplot(values, positions=[x], widths=0.72,
                              showmeans=False, showmedians=False,
                              showextrema=False)
        style_violin(parts, colour)
        ax.scatter(x + rng.uniform(-0.16, 0.16, len(values)), values,
                   color=colour, s=DOT_SIZE, alpha=DOT_ALPHA, linewidths=0,
                   zorder=3)
        q1, med, q3 = np.percentile(values, [25, 50, 75])
        ax.plot([x, x], [q1, q3], color=INK, lw=1.4, solid_capstyle="round",
                zorder=4)
        ax.scatter([x], [med], s=DOT_SIZE * 2.4, color="white",
                   edgecolors=INK, linewidths=MEDIAN_LW, zorder=5)
        fmt = "{:.2f}" if abs(med) < 10 else "{:.1f}"
        ax.annotate(fmt.format(med), (x, med), textcoords="offset points",
                    xytext=(8, 0), ha="left", va="center",
                    fontsize=ANNOT_FONTSIZE, color=INK, zorder=6)

    if logy:
        ax.set_yscale("log")
        # A plain decade locator labels only 10 over this 3-50 nM range, so
        # the panel would carry a single tick. 1-3 subdivisions, spelled out
        # rather than in exponent form at this scale.
        ax.yaxis.set_major_locator(LogLocator(base=10.0, subs=(1.0, 3.0)))
        ax.yaxis.set_major_formatter(ScalarFormatter())
        ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xticks(range(len(ORDER)))
    ax.set_xticklabels([LABEL[t] for t in ORDER], fontsize=BASE_FONTSIZE)
    ax.set_xlim(-0.65, len(ORDER) - 0.35)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=TITLE_FONTSIZE, pad=4)
    ax.xaxis.grid(False)


METRIC_PANELS = [
    ("kd", "kd_nm", "predicted $K_\\mathrm{d}$ (nM)", "Predicted $K_d$ by target", True),
    ("permeability", "raw_permeability", "permeability (log cm s$^{-1}$)",
     "Permeability by target", False),
    ("boltz_iptm", "conf_iptm", "Boltz-2 ligand iPTM",
     "Boltz-2 iPTM by target", False),
    ("gnina_cnn", "cnn_affinity", "Gnina CNN (pKd)", "Gnina CNN by target", False),
    ("vina", "vina_affinity", "Vina affinity (kcal mol$^{-1}$)",
     "Vina affinity by target", False),
]


def make_metric_panel(column, ylabel, title, logy):
    def draw(ax, final):
        jitter_by_target(ax, final, column, ylabel, title, logy)
    return draw


# --------------------------------------------------------------------------
# f - Phase-3 composite score by target (standalone panel)
# --------------------------------------------------------------------------
def panel_composite(ax, final):
    """Phase-3 composite, one column per target, over the 20 candidates.

    No acceptance line: the composite only orders candidates within a target,
    and its weights mix metrics on different scales, so a shared cut-off across
    targets would not mean anything. n = 20 per column, so the strip is the
    whole population of each arm rather than a sample of it.
    """
    style_axis_vbar(ax)
    rng = np.random.default_rng(42)
    for x, target in enumerate(ORDER):
        values = final.loc[final.target == target, "composite"].to_numpy()
        colour = COLOUR[target]
        parts = ax.violinplot(values, positions=[x], widths=0.72,
                              showmeans=False, showmedians=False,
                              showextrema=False)
        style_violin(parts, colour)
        ax.scatter(x + rng.uniform(-0.16, 0.16, len(values)), values,
                   color=colour, s=DOT_SIZE, alpha=DOT_ALPHA, linewidths=0,
                   zorder=3)
        q1, med, q3 = np.percentile(values, [25, 50, 75])
        ax.plot([x, x], [q1, q3], color=INK, lw=1.4, solid_capstyle="round",
                zorder=4)
        ax.scatter([x], [med], s=DOT_SIZE * 2.4, color="white",
                   edgecolors=INK, linewidths=MEDIAN_LW, zorder=5)
        ax.annotate(f"{med:.2f}", (x, med), textcoords="offset points",
                    xytext=(8, 0), ha="left", va="center",
                    fontsize=ANNOT_FONTSIZE, color=INK, zorder=6)

    ax.set_xticks(range(len(ORDER)))
    ax.set_xticklabels([LABEL[t] for t in ORDER], fontsize=BASE_FONTSIZE)
    ax.set_xlim(-0.65, len(ORDER) - 0.35)
    ax.set_ylabel("Phase-3 composite score")
    ax.set_title("Composite score by target", fontsize=TITLE_FONTSIZE, pad=4)
    ax.xaxis.grid(False)


# --------------------------------------------------------------------------
# i - best candidate per target
# --------------------------------------------------------------------------
def panel_table(ax, final):
    """Highest-composite candidate of each arm, with the gates it clears.

    The HELM string and the SMILES are both far too long for a panel cell, so
    the candidate is identified by the Phase-1 rank it entered Phase 2 with;
    all three of these were reordered to final rank 1, which is itself the
    point of the rank-shift panel. The Clears column counts the four quality
    thresholds, and is what keeps the table from reading as three clean hits:
    KRAS-G12D's best candidate misses the AlphaFold3 one.
    """
    ax.axis("off")
    ax.set_title("Best candidate per target", fontsize=TITLE_FONTSIZE, pad=4)

    best = pd.concat([final[final.target == t].nlargest(1, "composite")
                      for t in ORDER]).sort_values("composite", ascending=False)

    headers = ["Target", "$K_\\mathrm{d}$ nM", "perm.", "AF3", "CNN", "Clears"]
    rows = []
    for r in best.itertuples():
        clears = int(r.kd_nm < GATES["kd_nm"]) + int(r.raw_permeability > GATES["perm"]) \
            + int(r.iptm > GATES["iptm"]) + int(r.cnn_affinity > GATES["cnn"])
        rows.append([LABEL[r.target], f"{r.kd_nm:.1f}",
                     f"{r.raw_permeability:.2f}", f"{r.iptm:.2f}",
                     f"{r.cnn_affinity:.2f}", f"{clears}/4"])

    n_rows, n_cols = len(rows) + 1, len(headers)
    bbox = [0.0, 0.10, 1.0, 0.76]
    widths = [0.245, 0.165, 0.145, 0.13, 0.145, 0.17]
    table = ax.table(cellText=[[""] * n_cols for _ in range(n_rows)],
                     loc="center", cellLoc="center", bbox=bbox,
                     colWidths=widths)

    for j, label in enumerate(headers):
        cell = table[(0, j)]
        cell.set_text_props(text=label, fontsize=BASE_FONTSIZE)
        cell.set_facecolor("white")
    for i, row in enumerate(rows):
        for j, text in enumerate(row):
            colour = TIER_PASS if j == 5 and text == "4/4" else "black"
            table[(i + 1, j)].set_text_props(
                text=text, fontsize=TABLE_FONTSIZE - (1.0 if j == 0 else 0),
                color=colour)

    table.auto_set_font_size(False)
    for (row_idx, _), cell in table.get_celld().items():
        cell.set_edgecolor("white")
        cell.set_linewidth(0)
        cell.set_height(0.2)
        if row_idx > 0:
            cell.set_facecolor("#F7F7F7" if row_idx % 2 == 0 else "white")

    x_left, x_right = bbox[0], bbox[0] + bbox[2]
    y_bottom, y_top = bbox[1], bbox[1] + bbox[3]
    y_header = y_top - bbox[3] / n_rows
    line_kw = dict(color=INK, linewidth=RULE_LW, transform=ax.transAxes,
                   clip_on=False)
    for y in (y_top, y_header, y_bottom):
        ax.plot([x_left, x_right], [y, y], **line_kw)

    ax.text(0.0, y_bottom - 0.12,
            "gates: $K_\\mathrm{d}$ < 10 $\\mu$M, perm. > $-$6.0, "
            "AF3 iPTM > 0.60, CNN > 6.0",
            transform=ax.transAxes, ha="left", va="top",
            fontsize=ANNOT_FONTSIZE, color=MUTED)


# --------------------------------------------------------------------------
# Structure export (for ChimeraX)
# --------------------------------------------------------------------------
def export_top_structures(final, results_root, outdir):
    """Copy the best candidate per target into outdir/structures.

    Both predictors are exported for every candidate, not just the one the
    composite reads. Panel d is the reason: Boltz-2 and AlphaFold3 disagree on
    these complexes (within-target r = -0.23 to +0.45, Boltz-2 higher on 50 of
    60), and the composite uses Boltz-2 alone. Rendering only the Boltz-2 pose
    would show the more confident of two estimates without saying so.

    The Gnina pose is a third, independent placement: a rigid docking of the
    same macrocycle into the predicted receptor, so it is the one to compare
    against when the two predicted complexes differ.
    """
    dest = Path(outdir, "structures")
    dest.mkdir(parents=True, exist_ok=True)
    manifest = []

    for target in ORDER:
        best = final[final.target == target].nlargest(1, "composite").iloc[0]
        cdir = f"c_{int(best['rank']):02d}_{best.smiles_hash}"
        run = Path(results_root, f"{target}_perm", RUN)
        stem = f"{target}_{cdir}"

        sources = {
            "boltz2_complex": (run / "phase2_track_a" / cdir / "boltz_results_input"
                               / "predictions" / "input" / "input_model_0.pdb",
                               f"{stem}_boltz2.pdb"),
            "af3_complex": (run / "phase2_track_b" / cdir / f"{cdir}_model.cif",
                            f"{stem}_af3.cif"),
            "gnina_receptor": (run / "phase2_gnina" / cdir / "receptor.pdb",
                               f"{stem}_gnina_receptor.pdb"),
            "gnina_pose": (run / "phase2_gnina" / cdir / "docked.sdf",
                           f"{stem}_gnina_docked.sdf"),
        }
        copied = {}
        for role, (src, name) in sources.items():
            if src.is_file():
                shutil.copy2(src, dest / name)
                copied[role] = name

        manifest.append({
            "target": LABEL[target], "candidate_dir": cdir,
            "phase1_rank": int(best["rank"]),
            "final_rank": int(best.final_rank),
            "helm": best.helm_seqs, "smiles": best.smiles,
            "n_heavy_atoms": int(best.n_heavy_atoms),
            "kd_nm": round(float(best.kd_nm), 2),
            "permeability": round(float(best.raw_permeability), 3),
            "boltz2_iptm": round(float(best.conf_iptm), 3),
            "af3_iptm": round(float(best.iptm), 3),
            "gnina_cnn": round(float(best.cnn_affinity), 3),
            "vina": round(float(best.vina_affinity), 2),
            "composite": round(float(best.composite), 3),
            **{k: copied.get(k) for k in sources},
        })

    pd.DataFrame(manifest).to_csv(dest / "top_candidates_manifest.csv",
                                  index=False)
    rows = "\n".join(
        f"  {m['target']:<11} Boltz-2 iPTM {m['boltz2_iptm']:.2f}   "
        f"AF3 iPTM {m['af3_iptm']:.2f}   gap {m['boltz2_iptm'] - m['af3_iptm']:+.2f}"
        for m in manifest)
    (dest / "README.txt").write_text(
        "HELM-GPT best candidate per target, by the Phase-3 composite.\n\n"
        "Files per candidate:\n"
        "  *_boltz2.pdb           Boltz-2 complex. Protein is a polymer chain,\n"
        "                         the macrocycle is a HETATM ligand.\n"
        "  *_af3.cif              AlphaFold3 top-ranked model of the same pair.\n"
        "  *_gnina_receptor.pdb   receptor used for docking.\n"
        "  *_gnina_docked.sdf     Gnina docked pose of the macrocycle; open it\n"
        "                         WITH the matching receptor, it has no protein.\n\n"
        "These are macrocyclic peptides with non-canonical residues, so the\n"
        "ligand is chemistry, not a protein chain: in ChimeraX style it with\n"
        "`style stick` and colour by heteroatom rather than by secondary\n"
        "structure.\n\n"
        "THE TWO PREDICTORS DISAGREE on these complexes, and the Phase-3\n"
        "composite reads Boltz-2 only:\n\n"
        + rows + "\n\n"
        "Rendering the Boltz-2 pose alone shows the more confident of two\n"
        "estimates. Open the AF3 model alongside it before concluding anything\n"
        "about the binding mode - for KRAS-G12D in particular the two place\n"
        "the macrocycle differently.\n\n"
        "AlphaFold3 could not build an RDKit reference conformer for these\n"
        "macrocycles and fell back, so its iPTM is an orthogonal check rather\n"
        "than a clean ligand prediction.\n\n"
        "Metrics for each candidate are in top_candidates_manifest.csv.\n")

    print(f"\nStructures -> {dest}")
    for m in manifest:
        print(f"  {m['target']:<11} {m['candidate_dir']:<16}"
              f" Kd {m['kd_nm']:6.2f} nM  Boltz-2 iPTM {m['boltz2_iptm']:.2f}"
              f"  AF3 iPTM {m['af3_iptm']:.2f}  CNN {m['gnina_cnn']:.2f}")
    return dest


# --------------------------------------------------------------------------
# Sheet composition
# --------------------------------------------------------------------------
def lettered(ax, letter):
    """Prefix a panel's title with its sheet letter.

    The letter lives here rather than in the panel, so re-ordering the sheet
    cannot leave a panel captioned with a letter it no longer occupies, and
    the standalone PDFs carry no letter at all.
    """
    for loc in ("center", "left", "right"):
        text = ax.get_title(loc=loc)
        if text:
            ax.set_title(f"{letter}   {text}", loc=loc,
                         fontsize=TITLE_FONTSIZE, pad=4)
            return
    # A panel that carries no title of its own still needs its letter. The
    # pad clears the horizontal legend the funnel puts above its axes.
    ax.set_title(letter, fontsize=TITLE_FONTSIZE, pad=12, loc="center")


# --------------------------------------------------------------------------
# Standalone panels
# --------------------------------------------------------------------------
# The merged sheet gives each panel half of a 183 mm page. Annotation offsets
# are in points, so re-emitting a panel at a narrower size collapses them onto
# the data; the standalone size therefore matches the cell it was composed for.
def create_subpanels(pop, final, funnel, outdir, prefix="helmgpt_benchmark"):
    """Each panel as its own print-sized PDF, under outdir/helmgpt/."""
    os.makedirs(outdir, exist_ok=True)
    singles = [
        ("funnel", lambda ax: panel_funnel(ax, funnel), WIDE_PANEL),
        ("top_candidates", lambda ax: panel_table(ax, final), TABLE_SIZE),
        ("composite_by_target", lambda ax: panel_composite(ax, final),
         WIDE_PANEL),
    ] + [(f"metric_{key}_by_target",
          (lambda d: lambda ax: d(ax, final))(
              make_metric_panel(col, ylabel, title, logy)), WIDE_PANEL)
         for key, col, ylabel, title, logy in METRIC_PANELS]
    saved = []
    for name, draw, size in singles:
        fig, ax = (plt.subplots(figsize=size) if name == "top_candidates"
                   else simple_ax(figsize=size))
        draw(ax)
        restyle_panel_title(ax, bold=False, loc='center')
        fig.tight_layout(pad=0.4)
        stem = os.path.join(outdir, f"{prefix}_{name}")
        # bbox_inches=None keeps the page at the authored mm size instead of
        # cropping to content, so every per-target panel comes out exactly
        # the same size and they can be placed on a grid in Illustrator
        # rather than nudged into alignment. tight_layout above has already
        # fitted the content inside the canvas.
        save_pdf(fig, stem, bbox_inches=None)
        plt.close(fig)
        saved.append(f"{stem}.pdf")

    return saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-root", default=DEFAULT_ROOT,
                    help="directory holding <target>_perm/<run>/phase*.csv")
    ap.add_argument("--outdir", default="results/figures")
    ap.add_argument("--merged", "-m", action="store_true",
                    help="only build the merged sheet, skip the subpanels")
    ap.add_argument("--structures", action="store_true",
                    help="also copy the best candidate per target into "
                         "<outdir>/helmgpt/structures")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    subdir = os.path.join(args.outdir, "helmgpt")

    apply_nature_rcparams()
    pop, final, funnel = load(args.results_root)

    # 2x3 in the AfCycDesign vocabulary: the four per-target distributions of
    # the Phase-2 quality metrics, then where the population went, then the
    # table.
    fig = plt.figure(figsize=mm_size(*MERGED_2x3_MM), layout="constrained")
    fig.get_layout_engine().set(w_pad=0.02, h_pad=0.02, wspace=0.05,
                                hspace=0.06)
    axes = fig.subplots(2, 3).ravel()
    for ax in axes:
        prettify_ax(ax)

    for ax, (_, col, ylabel, title, logy) in zip(axes, METRIC_PANELS[:4]):
        jitter_by_target(ax, final, col, ylabel, title, logy)
    panel_funnel(axes[4], funnel)
    panel_table(axes[5], final)
    for ax, letter in zip(axes, "abcdef"):
        lettered(ax, letter)

    stem = os.path.join(args.outdir, "helmgpt_benchmark_figure")
    save_pdf(fig, stem)
    plt.close(fig)

    if not args.merged:
        for path in create_subpanels(pop, final, funnel, subdir):
            print(f"  - {path}")
    if args.structures:
        export_top_structures(final, args.results_root, subdir)
    print(f"wrote {stem}.pdf   (n={len(final)} candidates)")
    for target in ORDER:
        f, g = funnel[target], final[final.target == target]
        print(f"  {LABEL[target]:<11} {f['generated']:,} -> {f['both']:,}"
              f" -> {f['selected']}   median Kd {g.kd_nm.median():7.2f} nM"
              f"   AF3 iPTM >= 0.60: {int((g.iptm >= GATES['iptm']).sum())}/20")


if __name__ == "__main__":
    main()
