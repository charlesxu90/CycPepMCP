#!/usr/bin/env python3
"""AfCycDesign multi-target benchmark figures.

The campaign is 4 targets x 2 binder lengths x 500 designs. This script draws
each panel as a standalone print-sized PDF, in the same visual vocabulary as
`afcycdesign_viz.py` (violin + box + strip, stat block, three-line table, Arial
at 6-7 pt, 0.3 pt axes), and then composes the same six panels into a 2x3
summary sheet.

Panels:
  a  pLDDT by target          - jitter over all 1,000 designs per target
  b  interface PAE by target  - jitter over all 1,000 designs per target
  c  pLDDT vs iPAE            - the two metrics are near-collinear
  d  design-time vs re-predicted - how optimistic the optimiser's own metrics are
  e  cropped vs full-length target - why two arms are not comparable to the rest
  f  top designs              - three-line table

Panels a and b carry no threshold lines. A single gate drawn across four
targets would imply one shared acceptance criterion; in this campaign the
usable threshold is target-dependent, so the distributions are shown bare and
the comparison is left to the reader.

Metric convention: panels a-d and f use the re-prediction against the *as-run*
target, which is what `afcyc_campaign` reports per arm and what the manuscript
tables quote. PCSK9 and RbtA were run against cropped targets, so their as-run
numbers are not on the same footing as Bcl-xL and XIAP; panel e quantifies
exactly that and is the reason the other panels must not be read as a ranking.

Usage:
  python3 afcycdesign_benchmark_figure.py <campaign_dir> [--outdir DIR] [--merged]
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

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from plot_style_utils import (  # noqa: E402
    ANNOT_FONTSIZE, BASE_FONTSIZE, CAT_PALETTE, CONTEXT_LW, DOT_SIZE,
    GATE_LW, MEDIAN_LW, RULE_LW, SCATTER_SIZE,
    TABLE_FONTSIZE, TABLE_SIZE, TITLE_FONTSIZE, XLABEL_FONTSIZE,
    apply_nature_rcparams, mm_size, prettify_ax, restyle_panel_title,
    save_pdf, simple_ax, style_axis_vbar, style_violin, thin_legend,
)

# Display order is worst-to-best on re-predicted pLDDT, so the eye travels in
# one direction across every per-target panel in the sheet.
ORDER = ["rbta", "xiap", "bclxl", "pcsk9"]
LABEL = {"bclxl": "Bcl-xL", "pcsk9": "PCSK9", "rbta": "RbtA", "xiap": "XIAP"}
COLOUR = {"bclxl": CAT_PALETTE[0], "xiap": CAT_PALETTE[4],
          "pcsk9": CAT_PALETTE[2], "rbta": CAT_PALETTE[3]}
CROPPED = {"pcsk9", "rbta"}

# As-run target size, residues. Bcl-xL and XIAP were used intact.
TARGET_RESIDUES = {"bclxl": 175, "xiap": 89, "pcsk9": 107, "rbta": 166}
FULL_RESIDUES = {"pcsk9": 496, "rbta": 441}

INK = "#333333"
MUTED = "#8A8A8A"
NEUTRAL = "#BFBFBF"
ACCENT = "#D55E00"

MERGED_2x3_MM = (183.0, 118.0)

# Per-target panels at the standalone size, shared with the RFpeptides and
# HELM-GPT benchmark scripts so a panel from any of the three campaigns drops
# onto the same grid. Wider than PANEL_SIZE, which left these panels visibly
# smaller than their counterparts in the other two figures.
WIDE_PANEL = mm_size(55.0, 42.0)


# ============================================================
# Data
# ============================================================

def load_campaign(campaign_dir) -> pd.DataFrame:
    """One row per design, carrying design-time, as-run and full-length metrics.

    `plddt`/`i_pae`/`i_ptm` are the re-prediction against the target the design
    was actually run against. `full_*` is the re-prediction against the intact
    target, present only for the two cropped arms. `d_*` are the optimiser's
    own design-time values, which are a different quantity and must never be
    pooled with the re-predicted ones.
    """
    records = sorted(Path(campaign_dir, "records").glob("*.json"))
    if not records:
        raise SystemExit(f"no records/*.json under {campaign_dir}")

    rows = []
    for path in records:
        name = re.match(r"(\w+?)_L(\d+)_(\d+)\.json", path.name)
        if not name:
            continue
        rec = json.loads(path.read_text())
        asrun, full = rec.get("repredict"), rec.get("repredict_full")
        if not asrun or asrun.get("i_pae") is None:
            continue
        design = rec.get("design_metrics") or {}
        rows.append({
            "design_id": rec.get("design_id", path.stem),
            "target": name.group(1),
            "length": int(name.group(2)),
            "sequence": rec.get("sequence"),
            "plddt": asrun["plddt"], "i_pae": asrun["i_pae"],
            "i_ptm": asrun["i_ptm"], "ptm": asrun["ptm"],
            "full_plddt": (full or {}).get("plddt"),
            "full_i_pae": (full or {}).get("i_pae"),
            "d_plddt": design.get("plddt"), "d_i_pae": design.get("i_pae"),
            "elapsed_s": rec.get("elapsed_s"),
            # The target actually used, which for two arms is a crop.
            "repredict_target": rec.get("repredict_target"),
        })

    df = pd.DataFrame(rows)
    missing = set(ORDER) - set(df.target)
    if missing:
        raise SystemExit(f"records are missing targets: {sorted(missing)}")
    print(f"Loaded {len(df):,} designs from {campaign_dir}/records")
    return df


def composite_score(df: pd.DataFrame) -> pd.Series:
    """0.50 * pLDDT + 0.50 * (1 - iPAE), the AfCycDesign ranking score."""
    return 0.5 * df.plddt.clip(0, 1) + 0.5 * (1 - df.i_pae.clip(0, 1))


# ============================================================
# Shared per-target jitter panel
# ============================================================

def _jitter_by_target(ax, df, column, ylabel, title, ylim=None):
    """Violin + box + strip of one metric, one column per target.

    Deliberately carries no threshold line: see the module docstring.
    """
    style_axis_vbar(ax)
    rng = np.random.default_rng(42)

    for x, target in enumerate(ORDER):
        values = df.loc[df.target == target, column].to_numpy()
        colour = COLOUR[target]

        parts = ax.violinplot(values, positions=[x], widths=0.72,
                              showmeans=False, showmedians=False,
                              showextrema=False)
        style_violin(parts, colour)

        jitter = rng.uniform(-0.17, 0.17, len(values))
        ax.scatter(x + jitter, values, color=colour, s=DOT_SIZE,
                   alpha=0.28, linewidths=0, zorder=3)

        q1, med, q3 = np.percentile(values, [25, 50, 75])
        ax.plot([x, x], [q1, q3], color=INK, lw=1.4, solid_capstyle="round",
                zorder=4)
        ax.scatter([x], [med], s=DOT_SIZE * 2.4, color="white",
                   edgecolors=INK, linewidths=MEDIAN_LW, zorder=5)
        ax.annotate(f"{med:.2f}", (x, med), textcoords="offset points",
                    xytext=(8, 0), ha="left", va="center",
                    fontsize=ANNOT_FONTSIZE, color=INK, zorder=6)

    ax.set_xticks(range(len(ORDER)))
    ax.set_xticklabels([LABEL[t] + ("*" if t in CROPPED else "")
                        for t in ORDER], fontsize=BASE_FONTSIZE)
    ax.set_xlim(-0.65, len(ORDER) - 0.35)
    if ylim is not None:
        ax.set_ylim(*ylim)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=TITLE_FONTSIZE, pad=4)
    ax.text(0.0, -0.17, "* cropped target - see panel c",
            transform=ax.transAxes, ha="left", va="top",
            fontsize=ANNOT_FONTSIZE, color=MUTED)
    ax.xaxis.grid(False)


def panel_plddt(ax, df):
    _jitter_by_target(ax, df, "plddt", "pLDDT (re-predicted)",
                      "a   pLDDT by target", ylim=(0.0, 1.0))


def panel_ipae(ax, df):
    _jitter_by_target(ax, df, "i_pae", "interface PAE (re-predicted)",
                      "b   Interface PAE by target", ylim=(0.0, 1.0))


def panel_iptm(ax, df):
    _jitter_by_target(ax, df, "i_ptm", "iPTM (re-predicted)",
                      "iPTM by target", ylim=(0.0, 1.0))


def panel_composite(ax, df):
    """Composite score by target.

    No acceptance line, for the same reason as panels a and b: the composite
    orders designs within a target, and the usable cut-off is target-dependent.
    """
    _jitter_by_target(ax, df.assign(score=composite_score(df)), "score",
                      "composite score", "Composite score by target",
                      ylim=(0.0, 1.0))


# ============================================================
# e - cropping
# ============================================================

def panel_cropping(ax, df):
    """Same designs, re-predicted against the cropped and the intact target."""
    style_axis_vbar(ax)
    arms = [(t, length) for t in ORDER if t in CROPPED for length in (14, 16)]

    for y, (target, length) in enumerate(arms):
        g = df[(df.target == target) & (df.length == length)]
        crop, full = g.i_pae.median(), g.full_i_pae.median()
        ax.plot([crop, full], [y, y], color=NEUTRAL, lw=1.4,
                solid_capstyle="round", zorder=2)
        ax.scatter([crop], [y], s=DOT_SIZE * 3.0, color=CAT_PALETTE[2],
                   linewidths=0, zorder=4)
        ax.scatter([full], [y], s=DOT_SIZE * 3.0, color=ACCENT, linewidths=0,
                   zorder=4)
        ax.text((crop + full) / 2, y - 0.3, f"+{full - crop:.2f}",
                ha="center", va="bottom", fontsize=ANNOT_FONTSIZE, color=ACCENT)

    for y, (target, length) in enumerate(arms):
        ax.text(0.02, y + 0.26,
                f"{LABEL[target]} {length}   "
                f"{TARGET_RESIDUES[target]} $\\rightarrow$ "
                f"{FULL_RESIDUES[target]} res",
                ha="left", va="center", fontsize=ANNOT_FONTSIZE, color=MUTED)

    ax.scatter([], [], s=DOT_SIZE * 3.0, color=CAT_PALETTE[2], linewidths=0,
               label="cropped target (as run)")
    ax.scatter([], [], s=DOT_SIZE * 3.0, color=ACCENT, linewidths=0,
               label="full-length target")
    thin_legend(ax, loc="lower right")

    ax.set_yticks([])
    ax.set_ylim(-0.75, len(arms) - 0.25)
    ax.invert_yaxis()
    ax.set_xlim(0.0, 1.0)
    ax.set_xlabel("median interface PAE", fontsize=XLABEL_FONTSIZE)
    ax.set_title("c   Cropping the target inflates confidence",
                 fontsize=TITLE_FONTSIZE, pad=4)
    prettify_ax(ax)
    ax.yaxis.grid(False)
    ax.spines["left"].set_visible(False)


# ============================================================
# Sampling-yield panel (SI)
# ============================================================
# Measured tail of the iPAE distribution plus a log-linear extrapolation to
# the gate, which converts "no design passes" into "how many designs it would
# take". The RFpeptides script carries the same panel; the two differ only in
# what is swept, because the gate that binds differs between the campaigns.
IPAE_GATE = 0.20          # campaign QUALITY_GATES, and the RFpeptides gate
CUTS = np.arange(0.70, 0.19, -0.05)
TAIL_POINTS = 4           # fit the extreme tail, not the whole curve
MAX_EXTRAPOLATION = 0.15  # iPAE units; past this the fit is not worth drawing


def panel_sampling_yield(ax, df):
    """How many designs each target would need to put 10 under the iPAE gate.

    Uses the as-run re-prediction, like the other panels, so RbtA and PCSK9
    are scored against their cropped targets and are starred accordingly. For
    RbtA in particular the reach shown here is a property of the cropped
    target, not of the protein; the cropping panel is the correction.

    Solid is measured, dashed is projected past the last design that passed.
    """
    per_arm = int(df.groupby("target").size().max())
    handles, notes = {}, {}
    floor = 1.0   # lowest projected yield drawn, used to set the y range

    for target in ORDER:
        values = df.loc[df.target == target, "i_pae"].to_numpy()
        counts = np.array([(values < c).sum() for c in CUTS], dtype=float)
        seen = counts > 0
        xs, ys = CUTS[seen], counts[seen]
        if len(xs) == 0:
            continue
        handles[target], = ax.plot(xs, ys, "-o", color=COLOUR[target], lw=0.8,
                                   ms=2.2, mew=0, zorder=3)

        # If the gate is actually reached, the measured rate is the answer and
        # no fit is needed. On this data the tail fit would overstate RbtA's
        # yield 2.6-fold (428 against the observed 1,111), so extrapolating
        # where a measurement exists would flatter the best target most.
        observed = int((values < IPAE_GATE).sum())
        if observed > 0:
            notes[target] = f"{10 * len(values) / observed:,.0f}"
            continue

        tail_x, tail_y = xs[-TAIL_POINTS:], ys[-TAIL_POINTS:]
        if len(tail_x) < 3:
            notes[target] = "-"
            continue
        slope, intercept = np.polyfit(tail_x, np.log(tail_y), 1)
        rate = float(np.exp(intercept + slope * IPAE_GATE)) / len(values)

        # Dashed from the last measured point only, anchored to it, so solid
        # meets dashed without a step and the line style marks exactly where
        # measurement ends. Drawn only when the reach is short enough.
        if tail_x[-1] - IPAE_GATE <= MAX_EXTRAPOLATION and rate > 0:
            grid = np.linspace(tail_x[-1], IPAE_GATE, 40)
            anchored = tail_y[-1] * np.exp(slope * (grid - tail_x[-1]))
            ax.plot(grid, anchored, ls=(0, (1.6, 1.6)), color=COLOUR[target],
                    lw=0.6, zorder=2)
            rate = float(anchored[-1]) / len(values)
            floor = min(floor, float(anchored[-1]))
            notes[target] = f"~{10 / rate:,.0f}"
        else:
            notes[target] = "$\\gg$10$^4$"

    ax.axvline(IPAE_GATE, color=INK, lw=GATE_LW, zorder=4)
    ax.axhline(1.0, color=INK, lw=CONTEXT_LW, ls=(0, (2.4, 2.4)), zorder=2)
    # Just left of the gate line: the legend holds the lower left here, so
    # the RFpeptides panel's placement would land on the legend title.
    ax.text(0.225, 1.2, f"1 design in {per_arm:,}", ha="right", va="bottom",
            fontsize=ANNOT_FONTSIZE, color=INK)

    ax.set_yscale("log")
    ax.set_ylim(min(0.5, floor * 0.6), per_arm * 2.2)
    ax.set_xlim(0.72, 0.17)          # reversed: tighter cut-offs to the right
    ax.set_xlabel(f"interface PAE cut-off   (gate {IPAE_GATE:.2f})",
                  fontsize=XLABEL_FONTSIZE)
    ax.set_ylabel(f"designs below cut-off (of {per_arm:,})",
                  fontsize=XLABEL_FONTSIZE)
    prettify_ax(ax)
    ax.yaxis.grid(True, color="#EAEAEA", lw=0.55, zorder=0)

    shown = [t for t in ORDER if t in handles]
    legend = ax.legend(
        [handles[t] for t in shown],
        [f"{LABEL[t]}{'*' if t in CROPPED else ''}   {notes.get(t, '-')}"
         for t in shown],
        title="designs needed for 10 passes", loc="lower left",
        fontsize=ANNOT_FONTSIZE, title_fontsize=ANNOT_FONTSIZE, frameon=True,
        facecolor="white", edgecolor="none", framealpha=0.8, handlelength=1.6,
        handletextpad=0.5, borderpad=0.2, labelspacing=0.3)
    legend.get_frame().set_linewidth(0)


# ============================================================
# f - top designs table
# ============================================================

def panel_table(ax, df, top_n=6):
    ax.axis("off")
    ax.set_title("d   Best design per arm, by composite score",
                 fontsize=TITLE_FONTSIZE, pad=4)

    scored = df.assign(score=composite_score(df))
    best = (scored.sort_values("score", ascending=False)
                  .groupby(["target", "length"], as_index=False).first()
                  .sort_values("score", ascending=False).head(top_n))

    headers = ["Arm", "Sequence", "pLDDT", "iPAE", "Score"]
    rows = [[f"{LABEL[r.target]} {r.length}", r.sequence,
             f"{r.plddt:.2f}", f"{r.i_pae:.2f}", f"{r.score:.2f}"]
            for r in best.itertuples()]

    n_rows, n_cols = len(rows) + 1, len(headers)
    bbox = [0.0, 0.05, 1.0, 0.86]
    widths = [0.18, 0.43, 0.135, 0.12, 0.135]
    table = ax.table(cellText=[[""] * n_cols for _ in range(n_rows)],
                     loc="center", cellLoc="center", bbox=bbox,
                     colWidths=widths)

    for j, label in enumerate(headers):
        cell = table[(0, j)]
        cell.set_text_props(text=label, fontsize=BASE_FONTSIZE)
        cell.set_facecolor("white")
    for i, row in enumerate(rows):
        for j, text in enumerate(row):
            size = TABLE_FONTSIZE - 0.8 if j == 1 else TABLE_FONTSIZE
            table[(i + 1, j)].set_text_props(text=text, fontsize=size)

    table.auto_set_font_size(False)
    for (row_idx, _), cell in table.get_celld().items():
        cell.set_edgecolor("white")
        cell.set_linewidth(0)
        cell.set_height(0.12)
        if row_idx > 0:
            cell.set_facecolor("#F7F7F7" if row_idx % 2 == 0 else "white")

    x_left, x_right = bbox[0], bbox[0] + bbox[2]
    y_bottom, y_top = bbox[1], bbox[1] + bbox[3]
    y_header = y_top - bbox[3] / n_rows
    line_kw = dict(color=INK, linewidth=RULE_LW, transform=ax.transAxes,
                   clip_on=False)
    for y in (y_top, y_header, y_bottom):
        ax.plot([x_left, x_right], [y, y], **line_kw)


# ============================================================
# Structure export (for ChimeraX)
# ============================================================

def _pdb_chains(path):
    """(chains, n_models, n_CA) read from the file, so the README cannot drift.

    Worth reading rather than assuming: the re-predicted complexes are always
    A/B, but the standalone XIAP target carries chain C, which breaks a naive
    `match #2/A to #1/A` in ChimeraX.
    """
    chains, models, n_ca = {}, 0, 0
    with open(path) as handle:
        for line in handle:
            if line.startswith("MODEL"):
                models += 1
            elif line.startswith("ATOM"):
                chains[line[21]] = True
                if line[12:16] == " CA " and models <= 1:
                    n_ca += 1
    return "".join(sorted(chains)), max(models, 1), n_ca


def export_top_structures(df, campaign_dir, outdir):
    """Copy the best design per target, with its target, into outdir/structures.

    "Best" is the highest composite score on the as-run re-prediction, i.e. the
    same ordering as the figures. For each target three things are copied where
    they exist: the as-run re-predicted complex, the re-prediction of the same
    design against the full-length target, and the target structure itself.

    Both re-predictions are exported for the cropped arms on purpose. The
    as-run complex is the one the campaign scored and the one that looks good;
    the full-length complex is the same peptide against the real protein, and
    for RbtA it is a different result entirely (iPAE 0.20 against 0.77). A
    figure built from the cropped complex alone would not be defensible.
    """
    src = Path(campaign_dir, "repredict")
    targets_dir = Path(campaign_dir, "targets")
    dest = Path(outdir, "structures")
    dest.mkdir(parents=True, exist_ok=True)

    scored = df.assign(score=composite_score(df))
    manifest = []
    for target in ORDER:
        best = scored[scored.target == target].nlargest(1, "score").iloc[0]
        did = best.design_id

        copied = {}
        for label, name in (("as_run", f"{did}.pdb"), ("full", f"{did}_full.pdb")):
            path = src / name
            if path.is_file():
                shutil.copy2(path, dest / name)
                copied[label] = name

        target_pdb = best.repredict_target
        if target_pdb and (targets_dir / target_pdb).is_file():
            shutil.copy2(targets_dir / target_pdb, dest / target_pdb)

        manifest.append({
            "target": LABEL[target], "design_id": did,
            "binder_len": int(best.length), "sequence": best.sequence,
            "plddt_as_run": round(float(best.plddt), 3),
            "ipae_as_run": round(float(best.i_pae), 3),
            "iptm_as_run": round(float(best.i_ptm), 3),
            "composite": round(float(best.score), 3),
            "plddt_full": (None if pd.isna(best.full_plddt)
                           else round(float(best.full_plddt), 3)),
            "ipae_full": (None if pd.isna(best.full_i_pae)
                          else round(float(best.full_i_pae), 3)),
            "target_pdb": target_pdb,
            "target_cropped": target in CROPPED,
            "pdb_as_run": copied.get("as_run"),
            "pdb_full": copied.get("full"),
        })

    table = pd.DataFrame(manifest)
    table.to_csv(dest / "top_designs_manifest.csv", index=False)
    inventory = "\n".join(
        f"  {name:<26} chains {chains:<3} models {models}  {n_ca} CA"
        for name, (chains, models, n_ca) in sorted(
            (f.name, _pdb_chains(f)) for f in dest.glob("*.pdb")))
    (dest / "README.txt").write_text(
        "AfCycDesign top design per target, re-predicted complexes.\n\n"
        "Files:    <design>.pdb        re-predicted against the as-run target\n"
        "          <design>_full.pdb   same design against the FULL-LENGTH target\n"
        "                              (cropped arms only: PCSK9, RbtA)\n"
        "          <target>.pdb        the target structure that was used\n\n"
        "In every re-predicted complex chain A is the target and chain B is the\n"
        "cyclic peptide. The standalone target files do NOT all match: read the\n"
        "inventory below before superimposing, since xiap_target.pdb is chain C.\n\n"
        "Each re-predicted PDB holds 2 AF-multimer models. ChimeraX opens both,\n"
        "so use #1.1 unless you mean to compare them.\n\n"
        + inventory + "\n\n"
        "PCSK9 and RbtA were designed against cropped targets. Their as-run\n"
        "complexes are the ones the campaign scored, but they are not the same\n"
        "binding problem as the intact protein - compare <design>_full.pdb\n"
        "before drawing any conclusion from the as-run complex. For RbtA the\n"
        "difference is the whole result: iPAE 0.195 cropped, 0.767 full-length.\n\n"
        "Metrics for each file are in top_designs_manifest.csv.\n")

    print(f"\nStructures -> {dest}")
    for row in manifest:
        extra = ("" if row["ipae_full"] is None
                 else f"   full-length iPAE {row['ipae_full']:.3f}")
        print(f"  {row['target']:<7} {row['design_id']:<14} {row['sequence']:<17}"
              f" pLDDT {row['plddt_as_run']:.3f}  iPAE {row['ipae_as_run']:.3f}{extra}")
    return dest


# ============================================================
# Standalone figures and merged sheet
# ============================================================

PANELS = [
    ("plddt_by_target", panel_plddt, WIDE_PANEL),
    ("ipae_by_target", panel_ipae, WIDE_PANEL),
    ("target_cropping", panel_cropping, SCATTER_SIZE),
    ("top_designs", panel_table, TABLE_SIZE),
    ("iptm_by_target", panel_iptm, WIDE_PANEL),
    ("composite_by_target", panel_composite, WIDE_PANEL),
    ("sampling_yield", panel_sampling_yield, SCATTER_SIZE),
]


def create_separate_figures(df, outdir, prefix="afcycdesign_benchmark"):
    """Each panel as its own print-sized PDF, under outdir/afcycdesign/."""
    os.makedirs(outdir, exist_ok=True)
    saved = []
    for name, draw, size in PANELS:
        fig, ax = (plt.subplots(figsize=size) if name == "top_designs"
                   else simple_ax(figsize=size))
        draw(ax, df)
        restyle_panel_title(ax, bold=False, loc='center')
        fig.tight_layout(pad=0.4)
        stem = os.path.join(outdir, f"{prefix}_{name}")
        # bbox_inches=None keeps the page at the authored mm size instead of
        # cropping to content, so panels of the same kind come out exactly
        # the same size across all three benchmark scripts and can be placed
        # on a grid rather than nudged into alignment.
        save_pdf(fig, stem, bbox_inches=None)
        plt.close(fig)
        saved.append(f"{stem}.pdf")
    return saved


def create_merged_figure(df, outdir, prefix="afcycdesign_benchmark"):
    """The four argument-carrying panels on one 2x2 sheet.

    iPTM and the composite are left off: both are near-collinear with the two
    metrics in panels a and b, so they would spend a quarter of the page
    repeating them. Both stay available as standalone PDFs.
    """
    fig = plt.figure(figsize=mm_size(MERGED_2x3_MM[0] * 2 / 3,
                                     MERGED_2x3_MM[1]), layout="constrained")
    fig.get_layout_engine().set(w_pad=0.02, h_pad=0.02, wspace=0.05,
                                hspace=0.06)
    axes = fig.subplots(2, 2).ravel()
    for ax in axes:
        prettify_ax(ax)

    panel_plddt(axes[0], df)
    panel_ipae(axes[1], df)
    panel_cropping(axes[2], df)
    panel_table(axes[3], df)

    stem = os.path.join(outdir, f"{prefix}_summary")
    save_pdf(fig, stem)
    plt.close(fig)
    return f"{stem}.pdf"


def main():
    ap = argparse.ArgumentParser(
        description="AfCycDesign multi-target benchmark figures")
    ap.add_argument("campaign_dir",
                    help="afcyc_campaign directory containing records/")
    ap.add_argument("--outdir", default="results/figures")
    ap.add_argument("--merged", "-m", action="store_true",
                    help="only build the 2x3 summary sheet")
    ap.add_argument("--structures", action="store_true",
                    help="also copy the best design per target, and its "
                         "target, into <outdir>/afcycdesign/structures")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    subdir = os.path.join(args.outdir, "afcycdesign")

    apply_nature_rcparams()
    df = load_campaign(args.campaign_dir)

    if not args.merged:
        for path in create_separate_figures(df, subdir):
            print(f"  - {path}")
    print(f"  - {create_merged_figure(df, args.outdir)}")

    if args.structures:
        export_top_structures(df, args.campaign_dir, subdir)

    for target in ORDER:
        g = df[df.target == target]
        crop = " (cropped target)" if target in CROPPED else ""
        print(f"  {LABEL[target]:<7} n={len(g):,}  pLDDT {g.plddt.median():.3f}"
              f"  iPAE {g.i_pae.median():.3f}"
              f"  design-time pLDDT {g.d_plddt.median():.3f}{crop}")


if __name__ == "__main__":
    main()
