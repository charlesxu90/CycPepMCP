#!/usr/bin/env python3
"""RFpeptides multi-target benchmark figures.

The campaign is 4 targets x 500 designs. Each panel is drawn as a standalone
print-sized PDF and six of them are composed onto a 2x3 summary sheet, in the
same visual vocabulary and the same sheet layout as
`afcycdesign/afcycdesign_benchmark_figure.py`: violin + box + strip for every
per-target distribution, one colour per target carried across the whole figure,
centred plain panel titles, three-line table, Arial at 6-7 pt, 0.3 pt axes.

Sheet panels:

  a  pLDDT by target        - jitter over the 500 designs of each arm
  b  interface PAE by target
  c  recomputed ddG against interface PAE - the physics and the structure gate
     reject different designs, and their joint pass box holds 2 of 2,000
  d  recomputed ddG against the value Stage 4 originally reported - the
     reported metric carried no physics
  e  what that did to selection: the three MDM2 cluster representatives move
     from "best in panel" to mid-pack once the ddG is real
  f  best design per target, three-line table

Two further panels stay standalone, because neither is a per-target
distribution and both need more width than a sheet cell gives: the replicate
spread of ddG across 3 seeds, and the five-gate strip.

Panels a-c and f score on the recomputed PyRosetta metrics; d and e are the
only place the original Stage-4 values appear, and they appear there as the
subject rather than as a measurement.

Usage: python3 rfpeptides_benchmark_figure.py [--results-root DIR] [--outdir DIR]
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plot_style_utils import (  # noqa: E402
    ANNOT_FONTSIZE, BASE_FONTSIZE, CAT_PALETTE, CONTEXT_LW, DOT_SIZE,
    GATE_LW, MEDIAN_LW, MERGED_3x3_MM, RULE_LW, SCATTER_SIZE,
    TABLE_FONTSIZE, TABLE_SIZE, TIER_PASS, TITLE_FONTSIZE, XLABEL_FONTSIZE,
    apply_nature_rcparams, mm_size, prettify_ax, restyle_panel_title,
    save_pdf, simple_ax, style_axis_vbar, style_violin,
)

# The Stage-5 ranking score, reused verbatim from the workflow's own viz so the
# figure cannot drift from the score the pipeline actually ranks on.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rfpeptides_viz import calculate_composite_score  # noqa: E402

DEFAULT_ROOT = "/home/xux/Desktop/AgentMCP/CycPepMCP/results/rfpeptides_out/prod"

# Display order is worst-to-best up the y axis, so the eye lands on the target
# that comes closest to the physics gate last.
ORDER = ["gabarap", "mdm2", "mcl1", "pdl1"]
LABEL = {"mdm2": "MDM2", "mcl1": "MCL1", "pdl1": "PD-L1", "gabarap": "GABARAP"}

# Stage-4 / Stage-3 acceptance gates (CLAUDE.md "Quality Thresholds").
GATES = {"ddg": -30.0, "sap": 35.0, "cms": 300.0, "ipae": 0.20, "plddt": 0.70}

INK = "#333333"
MUTED = "#8A8A8A"       # annotation ink: present, but behind the data

# Shared by panels d and e, so a target carries one colour across the figure.
COLOUR = {"mdm2": CAT_PALETTE[0], "mcl1": CAT_PALETTE[4],
          "pdl1": CAT_PALETTE[2], "gabarap": CAT_PALETTE[3]}

# Per-target panels at the standalone size. Wider than PANEL_SIZE because
# GABARAP and PD-L1 are long tick labels, which collide at 45 mm; this is the
# width the same panel gets in a cell of the 3x3 sheet.
WIDE_PANEL = mm_size(55.0, 42.0)


def load(root):
    """One row per design, carrying both the original and recomputed metrics.

    `ddg`/`sap`/`cms` are what Stage 4 originally wrote (synthetic draws from a
    silent fallback); `*_mean`/`*_sd` are the PyRosetta recomputation over 3
    seeds. They are deliberately kept side by side - panels a and b are exactly
    the comparison between them.
    """
    frames = []
    for target in ORDER:
        run = os.path.join(root, target, "run")
        new = pd.read_csv(os.path.join(run, "final_summary_pyrosetta.csv"))
        old = pd.read_csv(os.path.join(run, "final_summary.csv"))
        merged = new.merge(old[["design_id", "ddg", "sap", "cms"]],
                           on="design_id", suffixes=("", "_syn"))
        merged["target"] = target
        frames.append(merged)
    df = pd.concat(frames, ignore_index=True)

    if (df["metrics_source"] != "pyrosetta").any():
        raise SystemExit("refusing to plot: some rows are not PyRosetta output")

    df["pass_physics"] = ((df.ddg_mean < GATES["ddg"]) &
                          (df.sap_mean < GATES["sap"]) &
                          (df.cms_mean > GATES["cms"]))
    df["pass_struct"] = (df.iPAE < GATES["ipae"]) & (df.pLDDT > GATES["plddt"])
    return df


# --------------------------------------------------------------------------
# Per-metric jitter by target (standalone panels)
# --------------------------------------------------------------------------
def jitter_by_target(ax, df, column, ylabel, title, ylim, higher_is_better):
    """Violin + strip of one metric, one column per target.

    No gate line and no best-design marker: the gate strip panel carries all
    five thresholds together, and repeating one here would imply this metric
    decides on its own, while an extreme marker invites the arm to be read
    through its single luckiest design. The panel reports the distribution and
    its median, which is what the arms can be compared on.

    Values outside `ylim` are not drawn and are not counted on the panel;
    ddG in particular has a long minimisation tail, so the ddG panel hides
    designs at both ends. The quartile bar and the printed median are
    computed over the whole arm, not over the visible subset.
    """
    style_axis_vbar(ax)
    rng = np.random.default_rng(42)
    lo, hi = ylim

    for x, target in enumerate(ORDER):
        values = df.loc[df.target == target, column].to_numpy()
        inside = values[(values >= lo) & (values <= hi)]
        colour = COLOUR[target]

        parts = ax.violinplot(inside, positions=[x], widths=0.72,
                              showmeans=False, showmedians=False,
                              showextrema=False)
        style_violin(parts, colour)
        ax.scatter(x + rng.uniform(-0.17, 0.17, len(inside)), inside,
                   color=colour, s=DOT_SIZE, alpha=0.28, linewidths=0, zorder=3)

        q1, med, q3 = np.percentile(values, [25, 50, 75])
        ax.plot([x, x], [q1, q3], color=INK, lw=1.4, solid_capstyle="round",
                zorder=4)
        ax.scatter([x], [med], s=DOT_SIZE * 2.4, color="white",
                   edgecolors=INK, linewidths=MEDIAN_LW, zorder=5)
        fmt = "{:.2f}" if abs(med) < 10 else "{:.0f}"
        ax.annotate(fmt.format(med), (x, med), textcoords="offset points",
                    xytext=(8, 0), ha="left", va="center",
                    fontsize=ANNOT_FONTSIZE, color=INK, zorder=6)

    ax.set_xticks(range(len(ORDER)))
    ax.set_xticklabels([LABEL[t] for t in ORDER], fontsize=BASE_FONTSIZE)
    ax.set_xlim(-0.65, len(ORDER) - 0.35)
    ax.set_ylim(lo, hi)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=TITLE_FONTSIZE, pad=4)
    ax.xaxis.grid(False)


METRIC_PANELS = [
    ("ddg", "ddg_mean", "ddG, recomputed (REU)", "ddG by target",
     (-60.0, 5.0), False),
    ("sap", "sap_mean", "SAP, recomputed", "SAP by target", (0.0, 65.0), False),
    ("cms", "cms_mean", "CMS, recomputed ($\\AA^2$)", "CMS by target",
     (0.0, 600.0), True),
    ("ipae", "iPAE", "interface PAE (re-predicted)", "Interface PAE by target",
     (0.0, 1.0), False),
    ("plddt", "pLDDT", "pLDDT (re-predicted)", "pLDDT by target",
     (0.0, 1.0), True),
]


def make_metric_panel(column, ylabel, title, ylim, higher):
    def draw(ax, df):
        jitter_by_target(ax, df, column, ylabel, title, ylim, higher)
    return draw


# --------------------------------------------------------------------------
# f - composite score by target (standalone panel)
# --------------------------------------------------------------------------
def panel_composite(ax, df):
    """Stage-5 composite score, on the recomputed metrics, one column per arm.

    No acceptance line: the composite has no gate of its own, it only orders
    designs within a target.
    """
    style_axis_vbar(ax)
    rng = np.random.default_rng(42)
    scored = df.assign(score=composite(df))

    for x, target in enumerate(ORDER):
        values = scored.loc[scored.target == target, "score"].to_numpy()
        colour = COLOUR[target]
        parts = ax.violinplot(values, positions=[x], widths=0.72,
                              showmeans=False, showmedians=False,
                              showextrema=False)
        style_violin(parts, colour)
        ax.scatter(x + rng.uniform(-0.17, 0.17, len(values)), values,
                   color=colour, s=DOT_SIZE, alpha=0.28, linewidths=0, zorder=3)
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
    ax.set_ylabel("composite score")
    ax.set_title("Composite score by target", fontsize=TITLE_FONTSIZE, pad=4)
    ax.xaxis.grid(False)


def composite(df):
    """Composite over the RECOMPUTED metrics, in the column names the viz wants.

    The frame also carries the original synthetic `ddg`/`sap`/`cms` columns, so
    the recomputed ones are selected explicitly rather than renamed in place -
    a rename alone would collide and silently score the fabricated values.
    """
    metrics = df[["ddg_mean", "sap_mean", "cms_mean", "iPAE", "pLDDT"]].rename(
        columns={"ddg_mean": "ddg", "sap_mean": "sap", "cms_mean": "cms"})
    return calculate_composite_score(metrics)


# --------------------------------------------------------------------------
# Sampling-yield projection (SI)
# --------------------------------------------------------------------------
# Measured tail of the joint pass-rate plus a log-linear extrapolation to the
# gate, which converts "no design passes" into "how many designs it would
# take". The construction follows afcycdesign_benchmark_figure.py; the swept
# quantity differs, see below.
#
# Interface PAE is the blocker here too, and measurably so: the median design
# of every arm sits further from the iPAE gate than from any other, by 1.9 SD
# (MDM2), 4.9 (GABARAP), 5.0 (MCL1) and 5.4 (PD-L1) of that arm's own spread.
# ddG is 0.2-1.6 SD away, CMS -0.1 to 1.7, and the median design already
# clears SAP in all four arms. So iPAE is the axis to sweep.
#
# The physics gate is held fixed while it is swept, so the curve is the yield
# of designs clearing both the physics criteria and iPAE - the acceptance the
# pipeline actually applies, and where the 2-of-2,000 result comes from.
#
# pLDDT is deliberately NOT held: it is the same AlphaFold confidence that
# iPAE measures, it is the second-furthest gate in every arm, and holding it
# flattens MCL1 and PD-L1 to zero at every cut-off, leaving two arms with no
# curve at all. Holding it would therefore price the same constraint twice.
CUTS = np.arange(0.70, 0.19, -0.05)
TAIL_POINTS = 4           # fit the extreme tail, not the whole curve
MAX_EXTRAPOLATION = 0.15  # iPAE units; past this the fit is not worth drawing

# The two arms whose Rosetta and AlphaFold stages did not see the same target
# (see the structure export README): their joint curve combines metrics from
# two different complexes, so it is marked rather than silently plotted.
MISMATCHED = {"mcl1", "pdl1"}


def panel_sampling_yield(ax, df):
    """How many designs each target would need for 10 joint passes.

    A target with no passing design is not thereby shown to be impossible;
    what the panel reports is the sampling depth its own measured tail implies.
    Where the gate is actually reached the measured rate is used, because a
    tail fit extrapolated past a measurement would flatter the best arms.
    """
    per_arm = int(df.groupby("target").size().max())
    handles, notes = {}, {}
    floor = 1.0   # lowest projected yield drawn, used to set the y range

    for target in ORDER:
        g = df[df.target == target]
        counts = np.array([(g.pass_physics & (g.iPAE < c)).sum() for c in CUTS],
                          dtype=float)
        seen = counts > 0
        xs, ys = CUTS[seen], counts[seen]
        if len(xs) == 0:
            notes[target] = "-"
            continue
        handles[target], = ax.plot(xs, ys, "-o", color=COLOUR[target], lw=0.8,
                                   ms=2.2, mew=0, zorder=3)

        observed = int((g.pass_physics & (g.iPAE < GATES["ipae"])).sum())
        if observed > 0:
            notes[target] = f"{10 * len(g) / observed:,.0f}"
            continue

        tail_x, tail_y = xs[-TAIL_POINTS:], ys[-TAIL_POINTS:]
        if len(tail_x) < 3:
            notes[target] = "-"
            continue
        slope, intercept = np.polyfit(tail_x, np.log(tail_y), 1)
        rate = float(np.exp(intercept + slope * GATES["ipae"])) / len(g)

        # Dashed, because it is an extrapolation rather than a measurement,
        # and drawn only when the reach to the gate is short enough to
        # believe. It starts at the last measured point, not at the start of
        # the fitting window: a dashed line laid over the measured range
        # would blur exactly the distinction the line style is making. The
        # segment is anchored to that measured point so solid meets dashed
        # without a step, and the fit supplies only its slope.
        if tail_x[-1] - GATES["ipae"] <= MAX_EXTRAPOLATION and rate > 0:
            grid = np.linspace(tail_x[-1], GATES["ipae"], 40)
            anchored = tail_y[-1] * np.exp(slope * (grid - tail_x[-1]))
            ax.plot(grid, anchored, ls=(0, (1.6, 1.6)), color=COLOUR[target],
                    lw=0.6, zorder=2)
            rate = float(anchored[-1]) / len(g)
            floor = min(floor, float(anchored[-1]))
            notes[target] = f"~{10 / rate:,.0f}"
        else:
            notes[target] = "$\\gg$10$^4$"

    ax.axvline(GATES["ipae"], color=INK, lw=GATE_LW, zorder=4)
    ax.axhline(1.0, color=INK, lw=CONTEXT_LW, ls=(0, (2.4, 2.4)), zorder=2)
    ax.text(0.68, 1.2, f"1 design in {per_arm:,}", ha="left", va="bottom",
            fontsize=ANNOT_FONTSIZE, color=INK)

    ax.set_yscale("log")
    # The axis reaches down to the lowest projected yield, so a dashed line
    # runs all the way to the gate instead of leaving the frame part way
    # there. For PD-L1 that endpoint is 0.04 designs per 500, which is the
    # substance of its projection and should be on the page.
    ax.set_ylim(min(0.5, floor * 0.6), per_arm * 2.2)
    ax.set_xlim(0.72, 0.17)          # reversed: tighter cut-offs to the right
    # Short enough to fit the 58 mm panel; that the physics gate is held
    # fixed while this one is swept is stated by the y label and the caption.
    ax.set_xlabel(f"interface PAE cut-off   (gate {GATES['ipae']:.2f})",
                  fontsize=XLABEL_FONTSIZE)
    # "both" rather than "physics + iPAE": the longer wording does not fit
    # the 44 mm height and is clipped. The caption carries the definition.
    ax.set_ylabel(f"designs clearing both (of {per_arm:,})",
                  fontsize=XLABEL_FONTSIZE)
    prettify_ax(ax)
    ax.yaxis.grid(True, color="#EAEAEA", lw=0.55, zorder=0)

    shown = [t for t in ORDER if t in handles]
    legend = ax.legend(
        [handles[t] for t in shown],
        [f"{LABEL[t]}{'*' if t in MISMATCHED else ''}   {notes.get(t, '-')}"
         for t in shown],
        # Upper right, not the lower left AfCycDesign uses: on this data the
        # curves run down into the lower left, and the tight-cut-off corner
        # above the gate line is the empty one.
        title="designs needed for 10 passes", loc="upper right",
        fontsize=ANNOT_FONTSIZE, title_fontsize=ANNOT_FONTSIZE, frameon=True,
        facecolor="white", edgecolor="none", framealpha=0.8, handlelength=1.6,
        handletextpad=0.5, borderpad=0.2, labelspacing=0.3)
    legend.get_frame().set_linewidth(0)


# --------------------------------------------------------------------------
# f - best design per target
# --------------------------------------------------------------------------
def panel_table(ax, df):
    """Highest-composite design of each arm, with the gates it actually clears.

    The gate column is the point of the table rather than decoration: the
    pipeline's own ranking puts a design at the top of every arm, but only two
    of the four tops clear anything, and PD-L1's is the -124 REU minimisation
    artifact the text sets aside. A table of composite winners without that
    column would read as four hits.
    """
    ax.axis("off")
    ax.set_title("Best design per target",
                 fontsize=TITLE_FONTSIZE, pad=4)

    scored = df.assign(score=composite(df))
    best = pd.concat([scored[scored.target == t].nlargest(1, "score")
                      for t in ORDER]).sort_values("score", ascending=False)

    headers = ["Target", "Sequence", "ddG", "iPAE", "Clears"]
    rows = []
    for r in best.itertuples():
        gates = ("both" if r.pass_physics and r.pass_struct
                 else "physics" if r.pass_physics
                 else "structure" if r.pass_struct else "neither")
        rows.append([LABEL[r.target], r.sequence, f"{r.ddg_mean:.1f}",
                     f"{r.iPAE:.2f}", gates])

    n_rows, n_cols = len(rows) + 1, len(headers)
    bbox = [0.0, 0.08, 1.0, 0.80]
    # GABARAP and the 14-residue sequences set the two wide columns; the
    # numeric ones only have to hold "-124.1". pLDDT is left out rather than
    # squeezed in: at sheet-cell width six columns collide, and the structural
    # side of the gate is already carried by iPAE and by the Clears column.
    widths = [0.21, 0.335, 0.14, 0.115, 0.20]
    table = ax.table(cellText=[[""] * n_cols for _ in range(n_rows)],
                     loc="center", cellLoc="center", bbox=bbox,
                     colWidths=widths)

    for j, label in enumerate(headers):
        cell = table[(0, j)]
        cell.set_text_props(text=label, fontsize=BASE_FONTSIZE)
        cell.set_facecolor("white")
    for i, row in enumerate(rows):
        for j, text in enumerate(row):
            size = TABLE_FONTSIZE - (2.0 if j == 1 else 1.0 if j == 0 else 0)
            colour = (TIER_PASS if j == 4 and text == "both"
                      else MUTED if j == 4 and text == "neither" else "black")
            table[(i + 1, j)].set_text_props(text=text, fontsize=size,
                                             color=colour)

    table.auto_set_font_size(False)
    for (row_idx, _), cell in table.get_celld().items():
        cell.set_edgecolor("white")
        cell.set_linewidth(0)
        cell.set_height(0.16)
        if row_idx > 0:
            cell.set_facecolor("#F7F7F7" if row_idx % 2 == 0 else "white")

    x_left, x_right = bbox[0], bbox[0] + bbox[2]
    y_bottom, y_top = bbox[1], bbox[1] + bbox[3]
    y_header = y_top - bbox[3] / n_rows
    line_kw = dict(color=INK, linewidth=RULE_LW, transform=ax.transAxes,
                   clip_on=False)
    for y in (y_top, y_header, y_bottom):
        ax.plot([x_left, x_right], [y, y], **line_kw)

    ax.text(0.0, y_bottom - 0.10,
            "PD-L1: ddG $-$124 REU is a minimisation artifact, see the text",
            transform=ax.transAxes, ha="left", va="top",
            fontsize=ANNOT_FONTSIZE, color=MUTED)


# --------------------------------------------------------------------------
# Structure export (for ChimeraX)
# --------------------------------------------------------------------------
# Unbound target structures, which the run configs point at on iBex.
EXAMPLE_TARGETS = {
    "mdm2": "binder_mdm2/4HFZ_MDM2.pdb", "mcl1": "binder_mcl1/2PQK_MCL1.pdb",
    "pdl1": "binder_pdl1/5IUS_PDL1.pdb",
    "gabarap": "binder_gabarap/1KOT_GABARAP.pdb",
}
DEFAULT_EXAMPLES = "/home/xux/Desktop/AgentMCP/CycPepMCP/examples"


def _pdb_chains(path):
    """(chains, n_models, {chain: n_CA in model 1}) read from the file."""
    chains, models, residues = {}, 0, {}
    with open(path) as handle:
        for line in handle:
            if line.startswith("MODEL"):
                models += 1
            elif line.startswith("ATOM"):
                chains[line[21]] = True
                if line[12:16] == " CA " and models <= 1:
                    residues[line[21]] = residues.get(line[21], 0) + 1
    return "".join(sorted(chains)), max(models, 1), residues


def _target_residues(path, chain):
    """CA count of `chain` in model 1 - the size of the target as that stage saw it."""
    return _pdb_chains(path)[2].get(chain)


def export_top_structures(df, results_root, outdir, examples=DEFAULT_EXAMPLES):
    """Copy the best design per target into outdir/structures.

    Two designs are exported per target where they differ:

      composite  the pipeline's own Stage-5 ranking on the recomputed metrics;
      credible   the best design that also clears both the physics and the
                 structural gates.

    They are not the same design, and for two targets the credible one does not
    exist at all. PD-L1 is the sharpest case: its composite-best is the design
    whose ddG of -124 REU the manuscript treats as a minimisation artifact, and
    the composite still ranks it first because the ddG term saturates. Shipping
    only the composite-best would therefore hand ChimeraX an artifact for one
    target in four.
    """
    dest = Path(outdir, "structures")
    dest.mkdir(parents=True, exist_ok=True)
    scored = df.assign(score=composite(df))
    manifest = []

    for target in ORDER:
        arm = scored[scored.target == target]
        picks = {"composite": arm.nlargest(1, "score").iloc[0]}
        passing = arm[arm.pass_physics & arm.pass_struct]
        if len(passing):
            best = passing.nlargest(1, "score").iloc[0]
            if best.design_id != picks["composite"].design_id:
                picks["credible"] = best

        run = Path(results_root, target, "run")
        for role, row in picks.items():
            did = row.design_id
            copied = {}
            for label, src in (("rosetta", run / "stage2" / f"{did}_final.pdb"),
                               ("repredicted",
                                run / "stage3" / f"{did}_afcyc.pdb")):
                if src.is_file():
                    shutil.copy2(src, dest / src.name)
                    copied[label] = src.name
            manifest.append({
                "target": LABEL[target], "role": role, "design_id": did,
                "sequence": row.sequence,
                "ddg": round(float(row.ddg_mean), 2),
                "ddg_sd": round(float(row.ddg_sd), 2),
                "sap": round(float(row.sap_mean), 2),
                "cms": round(float(row.cms_mean), 1),
                "ipae": round(float(row.iPAE), 3),
                "plddt": round(float(row.pLDDT), 3),
                "composite": round(float(row.score), 3),
                "passes_physics": bool(row.pass_physics),
                "passes_structure": bool(row.pass_struct),
                "pdb_rosetta": copied.get("rosetta"),
                "pdb_repredicted": copied.get("repredicted"),
                # Read from the files, because the two stages do not always
                # use the same target: see the README note.
                "target_res_rosetta": _target_residues(
                    dest / copied["rosetta"], "B") if "rosetta" in copied else None,
                "target_res_repredicted": _target_residues(
                    dest / copied["repredicted"], "A")
                if "repredicted" in copied else None,
            })

        src = Path(examples, EXAMPLE_TARGETS[target])
        if src.is_file():
            shutil.copy2(src, dest / src.name)

    pd.DataFrame(manifest).to_csv(dest / "top_designs_manifest.csv", index=False)

    inventory = "\n".join(
        f"  {f.name:<42} chains {c:<3} models {m}  "
        + " ".join(f"{k}:{v}res" for k, v in sorted(res.items()))
        for f, (c, m, res) in sorted(
            ((f, _pdb_chains(f)) for f in dest.glob("*.pdb")),
            key=lambda item: item[0].name))
    (dest / "README.txt").write_text(
        "RFpeptides best design per target.\n\n"
        "Files:    <design>_final.pdb   the Stage-2 complex, i.e. the one the\n"
        "                               recomputed Rosetta metrics describe\n"
        "          <design>_afcyc.pdb   AfCycDesign re-prediction of the same\n"
        "                               design, where iPAE and pLDDT come from\n"
        "          <PDB>_<NAME>.pdb     the unbound target\n\n"
        "CHAIN IDS ARE SWAPPED BETWEEN THE TWO COMPLEXES.\n"
        "  *_final.pdb  chain A = cyclic peptide, chain B = target\n"
        "  *_afcyc.pdb  chain A = target,         chain B = cyclic peptide\n"
        "A single `match` command will not work on both; check the inventory.\n"
        "The *_afcyc.pdb files also hold 2 models - use #1.1.\n\n"
        + inventory + "\n\n"
        "Two roles per target where they differ (see the manifest):\n"
        "  composite  highest Stage-5 composite on the recomputed metrics.\n"
        "  credible   best design also clearing the physics and structural\n"
        "             gates. Only MDM2 and GABARAP have one; MCL1 and PD-L1\n"
        "             have no design passing both, so their composite-best is\n"
        "             all there is.\n\n"
        "PD-L1 WARNING: its composite-best carries ddG -124 REU, which is\n"
        "reproducible across seeds but implausible for a 12-residue macrocycle\n"
        "and is treated as a minimisation artifact. Its iPAE is 0.554 and its\n"
        "pLDDT 0.418, so the complex should not be rendered as a binder.\n\n"
        "THE TWO STAGES DID NOT ALWAYS USE THE SAME TARGET. Chain sizes, read\n"
        "from the exported files (target_res_* in the manifest):\n"
        "\n"
        "  MDM2     Rosetta  83 res   re-predicted  83 res   consistent\n"
        "  GABARAP  Rosetta 119 res   re-predicted 119 res   consistent\n"
        "  MCL1     Rosetta 119 res   re-predicted 145 res   DIFFERENT\n"
        "  PD-L1    Rosetta  59 res   re-predicted 117 res   DIFFERENT\n"
        "\n"
        "So for MCL1 and PD-L1 the ddG/SAP/CMS columns and the iPAE/pLDDT\n"
        "columns do not describe the same complex, and for PD-L1 the Rosetta\n"
        "side saw about half the protein. Treat cross-metric statements on\n"
        "those two arms as provisional until the targets are reconciled.\n\n"
        "Metrics for each file are in top_designs_manifest.csv.\n")

    print(f"\nStructures -> {dest}")
    for row in manifest:
        gates = ("physics+structure" if row["passes_physics"] and row["passes_structure"]
                 else "physics" if row["passes_physics"]
                 else "structure" if row["passes_structure"] else "neither")
        print(f"  {row['target']:<8} {row['role']:<10} {row['design_id']:<34}"
              f" {row['sequence']:<15} ddG {row['ddg']:8.2f}"
              f"  iPAE {row['ipae']:.3f}  passes: {gates}")
    return dest


# --------------------------------------------------------------------------
# Sheet composition
# --------------------------------------------------------------------------
def lettered(ax, letter):
    """Prefix a panel's title with its sheet letter.

    The letter lives here rather than in the panel, so that re-ordering the
    sheet cannot leave a panel captioned with a letter it no longer occupies,
    and so the standalone PDFs carry no letter at all.
    """
    for loc in ("center", "left", "right"):
        text = ax.get_title(loc=loc)
        if text:
            ax.set_title(f"{letter}   {text}", loc=loc,
                         fontsize=TITLE_FONTSIZE, pad=4)
            return
    # A panel that carries no title of its own - the sampling-yield panel -
    # still needs its letter, or the sheet skips a letter silently.
    ax.set_title(letter, fontsize=TITLE_FONTSIZE, pad=4, loc="center")


# --------------------------------------------------------------------------
# Standalone panels
# --------------------------------------------------------------------------
# The merged sheet gives each panel half of a 183 mm page. Annotation offsets
# are in points, so re-emitting a panel at a narrower size collapses them onto
# the data; the standalone size therefore matches the cell it was composed for.
SUBPANELS = [
    ("top_designs", panel_table, TABLE_SIZE),
    ("sampling_yield", panel_sampling_yield, SCATTER_SIZE),
    ("composite_by_target", panel_composite, WIDE_PANEL),
] + [(f"metric_{key}_by_target",
      make_metric_panel(col, ylabel, title, ylim, higher), WIDE_PANEL)
     for key, col, ylabel, title, ylim, higher in METRIC_PANELS]


def create_subpanels(df, outdir, prefix="rfpeptides_benchmark"):
    """Each panel as its own print-sized PDF, under outdir/rfpeptides/."""
    os.makedirs(outdir, exist_ok=True)
    saved = []
    for name, draw, size in SUBPANELS:
        fig, ax = (plt.subplots(figsize=size) if name == "top_designs"
                   else simple_ax(figsize=size))
        draw(ax, df)
        restyle_panel_title(ax, bold=False, loc='center')
        fig.tight_layout(pad=0.4)
        stem = os.path.join(outdir, f"{prefix}_{name}")
        # bbox_inches=None: see the note in the HELM-GPT script. Panels of
        # the same kind then match exactly across all three campaigns.
        save_pdf(fig, stem, bbox_inches=None)
        plt.close(fig)
        saved.append(f"{stem}.pdf")

    return saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-root", default=DEFAULT_ROOT,
                    help="directory holding <target>/run/final_summary*.csv")
    ap.add_argument("--outdir", default="results/figures")
    ap.add_argument("--merged", "-m", action="store_true",
                    help="only build the merged sheet, skip the subpanels")
    ap.add_argument("--structures", action="store_true",
                    help="also copy the best design per target into "
                         "<outdir>/rfpeptides/structures")
    ap.add_argument("--examples", default=DEFAULT_EXAMPLES,
                    help="CycPepMCP examples/ dir, for the unbound targets")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    subdir = os.path.join(args.outdir, "rfpeptides")

    apply_nature_rcparams()
    df = load(args.results_root)

    # 3x3: the five gating metrics as per-target distributions, then the
    # Stage-5 composite they feed, then the sampling projection, then the
    # table. The table spans the last two cells rather than leaving a hole,
    # since eight panels do not fill a nine-cell grid.
    fig = plt.figure(figsize=mm_size(*MERGED_3x3_MM), layout="constrained")
    fig.get_layout_engine().set(w_pad=0.02, h_pad=0.02, wspace=0.05,
                                hspace=0.06)
    # Six columns so the table can span two cells. The slots are listed
    # explicitly rather than generated and trimmed: a comprehension over the
    # full 3x3 would add the two axes the table replaces, and matplotlib
    # draws them as empty 0-1 frames behind it.
    grid = fig.add_gridspec(3, 6)
    slots = [(0, 0), (0, 2), (0, 4), (1, 0), (1, 2), (1, 4), (2, 0)]
    cells = [fig.add_subplot(grid[r, c:c + 2]) for r, c in slots]
    cells.append(fig.add_subplot(grid[2, 2:]))
    for ax in cells:
        prettify_ax(ax)

    for ax, (_, col, ylabel, title, ylim, higher) in zip(cells, METRIC_PANELS):
        jitter_by_target(ax, df, col, ylabel, title, ylim, higher)
    panel_composite(cells[5], df)
    panel_sampling_yield(cells[6], df)
    panel_table(cells[7], df)
    for ax, letter in zip(cells, "abcdefgh"):
        lettered(ax, letter)

    stem = os.path.join(args.outdir, "rfpeptides_benchmark_figure")
    save_pdf(fig, stem)
    plt.close(fig)

    if not args.merged:
        for path in create_subpanels(df, subdir):
            print(f"  - {path}")
    if args.structures:
        export_top_structures(df, args.results_root, subdir, args.examples)
    print(f"wrote {stem}.pdf   (n={len(df):,})")
    for target in ORDER:
        g = df[df.target == target]
        print(f"  {LABEL[target]:<8} physics {g.pass_physics.sum():3d}"
              f"  structure {g.pass_struct.sum():3d}"
              f"  both {(g.pass_physics & g.pass_struct).sum()}")


if __name__ == "__main__":
    main()
