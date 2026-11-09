"""Nature-journal figure style for the CycPepMCP workflow visualizations.

Single source of truth for fonts, line widths, marker sizes and print figure
sizes across `afcycdesign_viz.py`, `rfpeptides_viz.py` and `helmgpt_viz.py`.

The rcParams block, the `AXIS_LW` / `DOT_SIZE` / grid constants and the
`apply_nature_rcparams()` / `save_figure()` / `prettify_ax()` API are kept
byte-compatible with `AlphaVariant/Benchmark/utils/plot_style_utils.py` so
figures from both projects sit in the same manuscript without restyling.

Everything below the "CycPepMCP additions" banner is extra vocabulary these
workflows need (print panel sizes in mm, quality-tier colours, the element
line widths used by the violin + strip panels).
"""
import os

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

CAT_PALETTE = sns.color_palette('colorblind')
DIV_PALETTE = sns.color_palette("BrBG_r", 100)
SEQ_PALETTE = sns.cubehelix_palette(100, start=0.5, rot=-0.75)
GRAY = [0.5, 0.5, 0.5]

# ---------------------------------------------------------------------------
# Nature-journal rcParams (single source of truth for all figure scripts).
#
# Font fallback chain ensures text renders as editable glyphs in both Adobe
# Illustrator (via pdf.fonttype=42 / svg.fonttype='none') and on Linux systems
# that lack Arial (Liberation Sans covers that gap).
# ---------------------------------------------------------------------------
AXIS_LW = 0.3          # spines + tick marks, in points (all figures)
# Data marker shared by every scatter/strip panel so the figure families stay
# visually locked together. DOT_SIZE is the scatter() area in points^2 for a
# DOT_DIAMETER_PT-wide marker; scatters must pass linewidths=0, or the default
# 1.5 pt edge stroke inflates the marker.
DOT_DIAMETER_PT = 2.0
DOT_SIZE = DOT_DIAMETER_PT ** 2
DOT_DIAMETER_MM = DOT_DIAMETER_PT * 25.4 / 72  # ~0.71 mm
GRID_DASH = (0, (1.8, 1.8))  # dash pattern for gridlines at tick values
# Light enough to stay in the background, dark enough to survive CMYK offset
# print at 0.55 pt (#EEEEEE and lighter tends to drop out).
GRID_COLOR = "#EAEAEA"

NATURE_RCPARAMS: dict = {
    # Font
    "font.family": "sans-serif",
    "font.sans-serif": [
        "Arial", "Helvetica", "DejaVu Sans", "Liberation Sans", "sans-serif"
    ],
    "font.size": 5.5,
    # Vector export — keep text as editable objects in Illustrator
    "pdf.fonttype": 42,   # embed TrueType; text stays selectable
    "ps.fonttype": 42,
    "svg.fonttype": "none",  # <text> nodes, not outlined paths
    # Math text ($...$) otherwise renders in DejaVu Sans, embedding a second
    # font family. mathtext.rm needs a concrete font name (it rejects the
    # "sans-serif" alias), so Arial is named directly; on hosts without Arial
    # matplotlib falls back through font.sans-serif with a warning.
    "mathtext.fontset": "custom",
    "mathtext.rm": "Arial",
    "mathtext.it": "Arial:italic",
    "mathtext.bf": "Arial:bold",
    "mathtext.default": "regular",
    # Axes & ticks
    "axes.linewidth": AXIS_LW,
    "axes.labelsize": 8.0,
    "axes.titlesize": 8.8,
    "xtick.labelsize": 7.0,
    "ytick.labelsize": 7.0,
    "xtick.major.width": AXIS_LW,
    "ytick.major.width": AXIS_LW,
    "xtick.minor.width": AXIS_LW,
    "ytick.minor.width": AXIS_LW,
    # Resolution
    "figure.dpi": 120,
    "savefig.dpi": 600,
}

# ---------------------------------------------------------------------------
# Default figure font scheme (7pt panel titles + x-axis labels, 6pt for
# everything else, no bold). Standing default for new print figures — pass to
# apply_nature_rcparams(). axes.labelsize governs y-labels/tick labels here;
# x-axis labels sit one point larger than that shared default, so call
# ax.set_xlabel(..., fontsize=XLABEL_FONTSIZE) explicitly per-axis.
# ---------------------------------------------------------------------------
TITLE_FONTSIZE = 7.0
XLABEL_FONTSIZE = 7.0
BASE_FONTSIZE = 6.0

DEFAULT_FIGURE_RCPARAMS: dict = {
    "font.size": BASE_FONTSIZE,
    "axes.titlesize": TITLE_FONTSIZE,
    "axes.titleweight": "normal",
    "axes.labelsize": BASE_FONTSIZE,
    "axes.labelweight": "normal",
    "xtick.labelsize": BASE_FONTSIZE,
    "ytick.labelsize": BASE_FONTSIZE,
    "font.weight": "normal",
}


def apply_nature_rcparams(overrides: dict | None = None) -> None:
    """Apply Nature-journal-style rcParams for publication-ready figures.

    Covers the font fallback chain, Illustrator-editable vector export
    (pdf.fonttype=42 / svg.fonttype='none'), and standard axis/tick sizes.

    Args:
        overrides: Optional dict of additional rcParams merged on top of the
            defaults. Use to adjust per-script sizes without duplicating the
            full block, e.g. ``apply_nature_rcparams({'axes.labelsize': 8.2})``.
    """
    params = dict(NATURE_RCPARAMS)
    if overrides:
        params.update(overrides)
    mpl.rcParams.update(params)


def save_figure(
    fig,
    outdir: str,
    prefix: str,
    formats: tuple = ("pdf",),
    dpi: int = 600,
    transparent: bool = True,
    bbox_inches: str | None = "tight",
) -> list:
    """Save a matplotlib figure as a publication PDF.

    Uses settings that keep text editable in Adobe Illustrator, inheriting
    ``pdf.fonttype=42`` / ``svg.fonttype='none'`` from ``apply_nature_rcparams``.

    Args:
        fig:         The matplotlib Figure to save.
        outdir:      Output directory (created if it does not exist).
        prefix:      Filename stem without extension.
        formats:     Extensions to write; default ``('pdf',)``.
        dpi:         Raster resolution (default 600 for print quality).
        transparent: Transparent background (default True).
        bbox_inches: ``'tight'`` (default) crops the page to the drawn content.
            Pass ``None`` to keep the page exactly ``fig.get_size_inches()`` —
            required when the figure is authored at a fixed print size in mm.

    Returns:
        List of saved file paths.
    """
    os.makedirs(outdir, exist_ok=True)
    paths = []
    for ext in formats:
        p = os.path.join(outdir, f"{prefix}.{ext}")
        fig.savefig(p, dpi=dpi, bbox_inches=bbox_inches, pad_inches=0.03,
                    transparent=transparent)
        print(f"  Saved: {p}")
        paths.append(p)
    return paths


def prettify_ax(ax):
    """Nature-style axis: remove top/right spines, styled ticks, grid below data."""
    for sp in ["top", "right"]:
        ax.spines[sp].set_visible(False)
    for sp in ["left", "bottom"]:
        ax.spines[sp].set_color("#333333")
        ax.spines[sp].set_linewidth(AXIS_LW)
    ax.tick_params(axis="both", length=2.4, width=AXIS_LW, color="#333333", pad=2)
    ax.set_axisbelow(True)


def style_axis_hbar(ax, xlim=None, xticks=None):
    """Horizontal dot/raincloud axis: x-gridlines, no y-gridlines, clean spines."""
    prettify_ax(ax)
    ax.xaxis.grid(True, color=GRID_COLOR, linewidth=0.55, linestyle=GRID_DASH,
                  zorder=0)
    ax.yaxis.grid(False)
    if xlim is not None:
        ax.set_xlim(*xlim)
    if xticks is not None:
        ax.set_xticks(xticks)


def style_axis_vbar(ax):
    """Distribution/time-series axis: y-gridlines, no x-gridlines, clean spines."""
    prettify_ax(ax)
    ax.yaxis.grid(True, color=GRID_COLOR, linewidth=0.55, linestyle=GRID_DASH,
                  zorder=0)
    ax.xaxis.grid(False)


def simple_ax(figsize=(6, 4), **kwargs):
    """
    Shortcut to make and 'prettify' a simple figure with 1 axis
    """
    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(111, **kwargs)
    prettify_ax(ax)
    return fig, ax


# ===========================================================================
# CycPepMCP additions
# ===========================================================================

# --- Print figure sizes -----------------------------------------------------
# Authored in mm against Nature column widths (89 mm single, 183 mm double) so
# the figures drop into the manuscript at 100% scale with 6-7 pt type intact.
MM_TO_IN = 1 / 25.4
SINGLE_COL_MM = 89.0
DOUBLE_COL_MM = 183.0


def mm_size(width_mm: float, height_mm: float) -> tuple:
    """Convert a (width, height) print size in mm to matplotlib inches."""
    return (width_mm * MM_TO_IN, height_mm * MM_TO_IN)


# One-panel standalone figures: two of these sit side by side in one column.
PANEL_MM = (45.0, 40.0)          # violin + strip distribution
SCATTER_MM = (58.0, 44.0)        # 2-metric scatter with colorbar
BAR_MM = (89.0, 42.0)            # per-design bar chart (single column)
TABLE_MM = (89.0, 34.0)          # top-designs table
TIMELINE_MM = (89.0, 40.0)       # Gantt chart
RADAR_MM = (62.0, 56.0)          # polar multi-metric profile
# Merged summary sheets, full double-column width.
MERGED_2x3_MM = (183.0, 104.0)
MERGED_3x3_MM = (183.0, 152.0)

PANEL_SIZE = mm_size(*PANEL_MM)
SCATTER_SIZE = mm_size(*SCATTER_MM)
BAR_SIZE = mm_size(*BAR_MM)
TABLE_SIZE = mm_size(*TABLE_MM)
TIMELINE_SIZE = mm_size(*TIMELINE_MM)
RADAR_SIZE = mm_size(*RADAR_MM)
MERGED_2x3_SIZE = mm_size(*MERGED_2x3_MM)
MERGED_3x3_SIZE = mm_size(*MERGED_3x3_MM)

# --- Type sizes below the 6 pt base ---------------------------------------
ANNOT_FONTSIZE = 5.0     # in-panel n/median/mean stat block
LEGEND_FONTSIZE = 5.0    # threshold-line keys
TABLE_FONTSIZE = 5.5     # table body; header uses BASE_FONTSIZE
CBAR_FONTSIZE = 5.5      # colorbar label + ticks

# --- Element line widths --------------------------------------------------
# Everything an artist draws on top of the AXIS_LW frame. Kept together so a
# single edit rescales the whole family.
GATE_LW = 0.6        # PASS-gate threshold line (solid, prominent)
CONTEXT_LW = 0.5     # "excellent" tier line (dashed, faint)
MEDIAN_LW = 0.6      # boxplot median bar
BOX_LW = 0.4         # boxplot box + whisker
BAR_EDGE_LW = 0.3    # bar / Gantt outline
RULE_LW = 0.5        # table three-line rules
RADAR_LW = 0.7       # radar polygon outline
GRID_LW = 0.55       # matches style_axis_vbar/hbar

# --- Quality-tier colours -------------------------------------------------
# Semantic, not decorative: a design's marker colour states which gate tier it
# clears. Values are the colorblind palette entries the workflows already used.
TIER_PASS = "#029E73"      # clears the tighter "excellent" gate
TIER_MARGINAL = "#DE8F05"  # clears the primary PASS gate only
TIER_FAIL = "#D55E00"      # clears neither
VIOLIN_ALPHA = 0.18        # density body fill
DOT_ALPHA = 0.75           # strip / scatter markers


def tier_color(value, threshold_excellent, threshold_pass, higher_is_better=True):
    """Return the quality-tier colour for one metric value.

    Args:
        value:               The metric value.
        threshold_excellent: Tighter context gate.
        threshold_pass:      Primary PASS gate.
        higher_is_better:    Direction of the metric.
    """
    if higher_is_better:
        if value >= threshold_excellent:
            return TIER_PASS
        return TIER_MARGINAL if value >= threshold_pass else TIER_FAIL
    if value <= threshold_excellent:
        return TIER_PASS
    return TIER_MARGINAL if value <= threshold_pass else TIER_FAIL


def style_violin(parts, facecolor):
    """Flat, edgeless violin body at the shared fill alpha."""
    for pc in parts['bodies']:
        pc.set_facecolor(facecolor)
        pc.set_edgecolor('none')
        pc.set_alpha(VIOLIN_ALPHA)
        pc.set_linewidth(0)


def style_box(bp):
    """Thin white-filled box with a dark median bar, sized for 6 pt panels."""
    for box in bp['boxes']:
        box.set_facecolor('white')
        box.set_edgecolor('#333333')
        box.set_linewidth(BOX_LW)
        box.set_alpha(0.9)
    for element in ('whiskers', 'caps'):
        for artist in bp.get(element, []):
            artist.set_color('#333333')
            artist.set_linewidth(BOX_LW)
    for median in bp['medians']:
        median.set_color('#333333')
        median.set_linewidth(MEDIAN_LW)


def thin_legend(ax, loc='lower left', **kwargs):
    """Small legend with tight spacing and a borderless white backing.

    The backing (no edge, no shadow) keeps 5 pt labels readable where they land
    over a gridline or a strip of data points; it reads as frameless in print.
    """
    legend = ax.legend(loc=loc, fontsize=LEGEND_FONTSIZE, frameon=True,
                       facecolor='white', edgecolor='none', framealpha=0.8,
                       handlelength=1.6, handletextpad=0.5,
                       borderpad=0.2, labelspacing=0.3, **kwargs)
    legend.get_frame().set_linewidth(0)
    return legend


def stat_box(ax, text):
    """Top-right n/median/mean annotation, white backing, no border."""
    return ax.text(0.97, 0.97, text, transform=ax.transAxes,
                   fontsize=ANNOT_FONTSIZE, va='top', ha='right', linespacing=1.3,
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                             edgecolor='none', alpha=0.75))


def annotate_offscale(ax, x, y, xlim, ylim):
    """Flag how many points a fixed axis window leaves out (silent if none).

    Scatter panels with pinned limits stay comparable across runs, but they can
    also drop an outlier without a trace; this keeps the omission on the figure.
    """
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    inside = ((x >= xlim[0]) & (x <= xlim[1]) &
              (y >= ylim[0]) & (y <= ylim[1]))
    n_out = int((~inside).sum())
    if not n_out:
        return None
    return ax.text(0.02, 0.02, f'{n_out} outside axis range',
                   transform=ax.transAxes, fontsize=ANNOT_FONTSIZE, color=GRAY,
                   ha='left', va='bottom')


def style_colorbar(cbar, label):
    """Thin colorbar with hairline outline and small label."""
    cbar.set_label(label, fontsize=CBAR_FONTSIZE)
    cbar.ax.tick_params(labelsize=CBAR_FONTSIZE, length=1.8, width=AXIS_LW,
                        pad=1.5)
    cbar.outline.set_linewidth(AXIS_LW)
    cbar.outline.set_edgecolor('#333333')


def save_pdf(fig, path_prefix: str, bbox_inches: str | None = "tight") -> list:
    """Save `fig` as `<path_prefix>.pdf` only (no PNG, no SVG).

    Convenience wrapper over `save_figure()` for call sites that carry a full
    path stem rather than a (outdir, prefix) pair. Pass ``bbox_inches=None`` to
    keep the page at the authored mm size instead of cropping to content.
    """
    outdir = os.path.dirname(path_prefix) or '.'
    prefix = os.path.basename(path_prefix)
    return save_figure(fig, outdir, prefix, formats=("pdf",),
                       bbox_inches=bbox_inches)


def restyle_panel_title(ax, bold=True, loc="left"):
    """Move a panel's title to `loc`, dropping any leading 'a  ' panel letter.

    Used when a panel drawn for a merged sheet is re-emitted as a standalone
    figure, where the letter is meaningless. Matplotlib keeps one Text per
    title location, so the title is looked up across all three rather than
    through the default (centre) accessor - reading only the centre one and
    writing back would blank a title that was set with loc='left'.
    """
    import re as _re
    for src in ("center", "left", "right"):
        text = ax.get_title(loc=src)
        if text:
            ax.set_title("", loc=src)
            ax.set_title(_re.sub(r"^[a-z]\s{2,}", "", text), loc=loc,
                         fontsize=TITLE_FONTSIZE, pad=4,
                         fontweight="bold" if bold else "normal")
            return
