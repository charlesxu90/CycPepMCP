#!/usr/bin/env python3
"""
RFpeptides Pipeline Visualization Script

Generates separate figures after binder design workflow:
1. ddG Distribution - Violin + strip of binding energy
2. iPAE Distribution - Violin + strip of interface PAE
3. pLDDT Distribution - Violin + strip of predicted confidence
4. SAP Distribution - Violin + strip of aggregation propensity
5. CMS Distribution - Violin + strip of contact molecular surface
6. Quality Scatter - ddG vs iPAE colored by composite score
7. Composite Score Distribution - Violin + strip
8. Metrics Table - Top designs with three-line academic style
9. Execution Timeline - Gantt chart of 5 pipeline stages

Every figure is saved as a print-sized PDF only (no PNG/SVG), styled through
`workflow-skills/scripts/plot_style_utils.py`: Arial at 6-7 pt, 0.3 pt axes,
2 pt data markers, mm-accurate Nature column widths, and `pdf.fonttype=42` so
all text stays editable in Illustrator.
A merged summary figure can also be generated.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Rectangle
from matplotlib.table import Table
import numpy as np
import pandas as pd

# Shared Nature-style figure vocabulary (fonts, line widths, dot size, sizes).
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from plot_style_utils import (  # noqa: E402
    BAR_EDGE_LW, BASE_FONTSIZE, CAT_PALETTE, CONTEXT_LW,
    DEFAULT_FIGURE_RCPARAMS, DOT_ALPHA, DOT_SIZE, GATE_LW, GRAY,
    MERGED_3x3_SIZE, PANEL_SIZE, RULE_LW, SCATTER_SIZE, TABLE_FONTSIZE,
    TABLE_SIZE, TIMELINE_SIZE, TITLE_FONTSIZE, XLABEL_FONTSIZE,
    annotate_offscale, apply_nature_rcparams, mm_size, prettify_ax, save_pdf,
    simple_ax, stat_box, style_axis_hbar, style_axis_vbar, style_box,
    style_colorbar, style_violin, thin_legend, tier_color,
)

# Figure size for individual distribution plots (45 x 40 mm print size).
FIGSIZE = PANEL_SIZE

# Print size for the top-designs table, narrower than the shared TABLE_MM
# (89 x 34) so the panel drops into a 65 mm figure slot. Saved with
# bbox_inches=None so the PDF page is exactly this size.
METRICS_TABLE_MM = (65.0, 38.0)
METRICS_TABLE_SIZE = mm_size(*METRICS_TABLE_MM)
# Clearance above the top rule and below the bottom rule. Flush against the page
# edge the strokes read as clipped, so they get this much white to sit against.
METRICS_TABLE_RULE_INSET_MM = 0.6

# Centralized PASS-gate thresholds (single source of truth: benchmark/configs/workflows.yaml).
# Per-target iPAE/ddG come from rfpeptides.per_target_thresholds; uniform metrics
# (pLDDT, SAP, CMS) come from the primary/excellent gates.
import sys as _sys
_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / "benchmark" / "configs" / "thresholds.py").is_file():
        if str(_p) not in _sys.path:
            _sys.path.insert(0, str(_p))
        break
from benchmark.configs import thresholds as cfg  # noqa: E402

_RF_PRIMARY = cfg.RFPEPTIDES_PASS_GATE.primary
_RF_EXCELLENT = cfg.RFPEPTIDES_PASS_GATE.excellent
_RF_PER_TARGET = cfg.RFPEPTIDES_PASS_GATE.extras['per_target_thresholds']


def _build_paper_thresholds(per_target: dict, primary: dict) -> dict:
    """Materialize the per-target PAPER_THRESHOLDS structure expected by the
    rest of the viz from the centralized config.

    Labels carry the metric name only — the plot helpers append the numeric
    cutoff, and the target is named in the caption/stdout — so legends stay
    short enough not to widen a 45 mm panel.
    """
    out = {}
    for tgt, vals in per_target.items():
        out[tgt] = {
            'ipae':  (vals['ipae'], 'Paper iPAE'),
            'ddg':   (vals['ddg'], 'Paper ddG'),
            'sap':   (primary['sap_max'], 'Paper SAP'),
            'cms':   (primary['cms_min'], 'Paper CMS'),
            'plddt': (primary['plddt_min'], 'Paper pLDDT'),
        }
    return out


PAPER_THRESHOLDS = _build_paper_thresholds(_RF_PER_TARGET, _RF_PRIMARY)

# Active thresholds (set by configure_thresholds() based on detected target).
# `_good` => excellent gate (tighter context line); `_acceptable` => primary PASS gate
# that gets overwritten with the per-target value in configure_thresholds().
QUALITY_THRESHOLDS = {
    'ddg_good':        _RF_EXCELLENT['ddg_max'],
    'ddg_acceptable':  _RF_PRIMARY['ddg_max_default'],
    'ipae_good':       _RF_EXCELLENT['ipae_max'],
    'ipae_acceptable': _RF_PRIMARY['ipae_max_default'],
    'plddt_good':      _RF_EXCELLENT['plddt_min'],
    'plddt_acceptable': _RF_PRIMARY['plddt_min'],
    'sap_good':        _RF_EXCELLENT['sap_max'],
    'sap_acceptable':  _RF_PRIMARY['sap_max'],
    'cms_good':        _RF_EXCELLENT['cms_min'],
    'cms_acceptable':  _RF_PRIMARY['cms_min'],
}

# Fixed axis ranges for the ddG-vs-iPAE scatter. Auto-scaling made the same
# design land at a different position in every batch, so the panel is pinned
# instead and stays visually comparable across runs. annotate_offscale() flags
# any design the window excludes.
SCATTER_DDG_XLIM = (-80.0, -10.0)
SCATTER_IPAE_YLIM = (0.0, 0.6)

# Active threshold labels, populated by configure_thresholds().
THRESHOLD_LABELS = {
    'ipae': 'Paper threshold',
    'ddg':  'Paper threshold',
    'sap':  'Paper threshold',
    'cms':  'Paper threshold',
    'plddt':'Paper threshold',
}


def detect_target(results_dir) -> str:
    """Infer target name from the results path. Keys mirror per_target_thresholds in workflows.yaml."""
    path = str(results_dir).lower()
    for key in ('mcl1', 'mdm2', 'gabarap', 'rbta', 'pdl1'):
        if key in path:
            return key
    return 'general'


def configure_thresholds(target: str) -> None:
    """Populate global QUALITY_THRESHOLDS and THRESHOLD_LABELS for a target.

    Sets the 'acceptable' tier to the paper's per-target threshold (the one
    actually used for filtering); the 'good' tier remains a tighter context line.
    """
    paper = PAPER_THRESHOLDS.get(target, PAPER_THRESHOLDS['general'])
    QUALITY_THRESHOLDS['ipae_acceptable']  = paper['ipae'][0]
    QUALITY_THRESHOLDS['ddg_acceptable']   = paper['ddg'][0]
    QUALITY_THRESHOLDS['sap_acceptable']   = paper['sap'][0]
    QUALITY_THRESHOLDS['cms_acceptable']   = paper['cms'][0]
    QUALITY_THRESHOLDS['plddt_acceptable'] = paper['plddt'][0]
    THRESHOLD_LABELS['ipae']  = paper['ipae'][1]
    THRESHOLD_LABELS['ddg']   = paper['ddg'][1]
    THRESHOLD_LABELS['sap']   = paper['sap'][1]
    THRESHOLD_LABELS['cms']   = paper['cms'][1]
    THRESHOLD_LABELS['plddt'] = paper['plddt'][1]

# RFpeptides pipeline stages
PIPELINE_STAGES = [
    'Stage 1: Backbone Generation',
    'Stage 2: Sequence Design',
    'Stage 3: DL Validation',
    'Stage 4: Physics Filtering',
    'Stage 5: Clustering & Selection',
]


def set_pub_plot_context(context=None):
    """Apply the Nature print rcParams (Arial, 7 pt titles, 6 pt body)."""
    apply_nature_rcparams(DEFAULT_FIGURE_RCPARAMS)


def save_for_pub(fig, path, bbox_inches='tight'):
    """Save figure as a single editable-text PDF.

    Pass ``bbox_inches=None`` for figures whose page must stay at the exact
    authored mm size rather than being cropped to the drawn content.
    """
    return save_pdf(fig, path, bbox_inches=bbox_inches)


def get_color_for_value(value, threshold_good, threshold_acceptable, higher_is_better=True):
    """Quality-tier colour for a metric value (see plot_style_utils.tier_color)."""
    return tier_color(value, threshold_good, threshold_acceptable,
                      higher_is_better=higher_is_better)


def simplify_design_id(name: str) -> str:
    """Simplify design ID for table display.

    Strips RFpeptides' verbose `_cyclic_epitope` / `_cyclic` infix while keeping
    the target prefix and design index intact. Examples:
        2PQK_MCL1_cyclic_epitope_75      -> 2PQK_MCL1_75
        RbtA_monomer_relaxed_cyclic_75   -> RbtA_monomer_relaxed_75
        design_007                        -> 7
    """
    if not isinstance(name, str):
        return str(name)
    if name.startswith('design_'):
        return name.replace('design_', '').lstrip('0') or '0'
    # Strip the longer pattern first to avoid leaving a stray '_epitope'.
    for token in ('_cyclic_epitope', '_cyclic', '_epitope'):
        name = name.replace(token, '')
    return name



def compact_design_id(name: str) -> str:
    """Trailing design index for narrow table panels (RbtA_monomer_relaxed_39 -> 39)."""
    simple = simplify_design_id(name)
    tail = simple.rsplit('_', 1)[-1]
    return tail if tail.isdigit() else simple

# ============================================================
# Data Loading
# ============================================================

def load_design_metrics(results_dir: Path) -> pd.DataFrame:
    """Load design metrics from RFpeptides pipeline results directory."""
    results_dir = Path(results_dir)

    for name in ["final_summary.csv", "design_metrics.csv", "metrics.csv"]:
        csv_path = results_dir / name
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            df = normalize_column_names(df)
            print(f"Loaded metrics from {csv_path} ({len(df)} designs)")
            return df

    # Search subdirectories
    for subdir in sorted(results_dir.iterdir()):
        if subdir.is_dir():
            for name in ["final_summary.csv", "design_metrics.csv", "metrics.csv"]:
                csv_path = subdir / name
                if csv_path.exists():
                    df = pd.read_csv(csv_path)
                    df = normalize_column_names(df)
                    print(f"Loaded metrics from {csv_path} ({len(df)} designs)")
                    return df

    print("No metrics file found, generating mock data for demonstration")
    return generate_mock_data()


def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names to standard format."""
    df = df.copy()
    mapping = {
        'design': 'design_id', 'name': 'design_id', 'design_name': 'design_id',
        'DDG': 'ddg', 'dG': 'ddg',
        'SAP': 'sap', 'CMS': 'cms',
        'ipae': 'iPAE', 'IPAE': 'iPAE', 'i_pae': 'iPAE',
        'plddt': 'pLDDT', 'PLDDT': 'pLDDT',
    }
    for old, new in mapping.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]
    if 'design_id' not in df.columns:
        df['design_id'] = [f'd{i:02d}' for i in range(len(df))]
    # Filter sentinel iPAE values
    if 'iPAE' in df.columns:
        n_before = len(df)
        df = df[df['iPAE'] < 900].reset_index(drop=True)
        n_filtered = n_before - len(df)
        if n_filtered > 0:
            print(f"  Filtered {n_filtered} designs with invalid iPAE (>900)")
    return df


def generate_mock_data(n_designs=8) -> pd.DataFrame:
    """Generate mock data for demonstration."""
    np.random.seed(42)
    designs = []
    for i in range(n_designs):
        ddg = np.random.normal(-35, 15)
        designs.append({
            'design_id': f'd{i:02d}',
            'sequence': ''.join(np.random.choice(list('ADEFGHIKLMNPQRSTVWY'), 12)),
            'length': 12, 'iPAE': np.clip(np.random.beta(2, 8) * 0.5, 0.05, 0.5),
            'pLDDT': np.clip(np.random.beta(5, 2), 0.3, 0.99),
            'ddg': np.clip(ddg, -80, 0),
            'sap': np.clip(np.random.normal(25, 8), 5, 60),
            'cms': np.clip(np.random.normal(350, 60), 100, 600),
            'passes_physics': ddg < -30,
        })
    return pd.DataFrame(designs)


def calculate_composite_score(df: pd.DataFrame) -> pd.Series:
    """Calculate composite quality score for ranking designs."""
    scores = pd.DataFrame(index=df.index)
    if 'ddg' in df.columns:
        scores['ddg'] = ((-df['ddg']).clip(0, 80) / 80)
    if 'iPAE' in df.columns:
        scores['iPAE'] = (1 - (df['iPAE'] / 0.5).clip(0, 1))
    if 'pLDDT' in df.columns:
        scores['pLDDT'] = df['pLDDT'].clip(0, 1)
    if 'cms' in df.columns:
        scores['cms'] = (df['cms'] / 600).clip(0, 1)
    if 'sap' in df.columns:
        scores['sap'] = (1 - (df['sap'] / 60).clip(0, 1))

    weights = {'ddg': 0.3, 'iPAE': 0.25, 'pLDDT': 0.2, 'cms': 0.15, 'sap': 0.1}
    composite = pd.Series(0.0, index=df.index)
    total_weight = 0
    for col, weight in weights.items():
        if col in scores.columns:
            composite += scores[col] * weight
            total_weight += weight
    if total_weight > 0:
        composite /= total_weight
    return composite


# ============================================================
# Core violin + strip plot helper
# ============================================================

def plot_violin_strip(values, title, ylabel, thresholds, higher_is_better=True,
                      palette_idx=0, output_path=None,
                      threshold_labels=('Excellent (tighter)', 'Paper threshold')):
    """Create a violin + strip + box distribution plot.

    `thresholds` is (good, acceptable). `threshold_labels` is the legend text
    for each line — second label is shown bold (the paper-aligned cutoff).
    """
    fig, ax = simple_ax(figsize=FIGSIZE)
    style_axis_vbar(ax)

    parts = ax.violinplot(values, positions=[0], showmeans=False,
                          showmedians=False, showextrema=False)
    style_violin(parts, CAT_PALETTE[palette_idx])

    bp = ax.boxplot(values, positions=[0], widths=0.15, patch_artist=True,
                    showfliers=False, zorder=2)
    style_box(bp)

    jitter = np.random.default_rng(42).uniform(-0.12, 0.12, len(values))
    colors = [get_color_for_value(v, thresholds[0], thresholds[1],
                                   higher_is_better=higher_is_better)
              for v in values]
    ax.scatter(jitter, values, c=colors, s=DOT_SIZE, alpha=DOT_ALPHA,
               linewidths=0, zorder=3)

    # Paper-aligned cutoff (solid, prominent); excellent context line (dashed, faint).
    ax.axhline(y=thresholds[1], color=CAT_PALETTE[1], linestyle='-', alpha=0.9,
               linewidth=GATE_LW, label=f"{threshold_labels[1]} ({thresholds[1]:g})")
    ax.axhline(y=thresholds[0], color=CAT_PALETTE[2], linestyle='--', alpha=0.7,
               linewidth=CONTEXT_LW, label=f"{threshold_labels[0]} ({thresholds[0]:g})")
    thin_legend(ax, loc='best')

    median = np.median(values)
    mean = np.mean(values)
    stat_box(ax, f'n={len(values)}\nmedian={median:.2f}\nmean={mean:.2f}')

    ax.set_title(title, fontsize=TITLE_FONTSIZE, pad=4)
    ax.set_ylabel(ylabel)
    ax.set_xlim(-0.5, 0.5)
    ax.set_xticks([])

    plt.tight_layout()
    if output_path:
        save_for_pub(fig, output_path)
    return fig


def _plot_violin_strip_ax(ax, values, title, ylabel, thresholds, higher_is_better=True,
                           palette_idx=0,
                           threshold_labels=('Excellent', 'Paper threshold')):
    """Internal: Plot violin + strip distribution on a given axis (for merged figure)."""
    style_axis_vbar(ax)

    parts = ax.violinplot(values, positions=[0], showmeans=False,
                          showmedians=False, showextrema=False)
    style_violin(parts, CAT_PALETTE[palette_idx])

    bp = ax.boxplot(values, positions=[0], widths=0.15, patch_artist=True,
                    showfliers=False, zorder=2)
    style_box(bp)

    jitter = np.random.default_rng(42).uniform(-0.12, 0.12, len(values))
    colors = [get_color_for_value(v, thresholds[0], thresholds[1],
                                   higher_is_better=higher_is_better)
              for v in values]
    ax.scatter(jitter, values, c=colors, s=DOT_SIZE, alpha=DOT_ALPHA,
               linewidths=0, zorder=3)

    ax.axhline(y=thresholds[1], color=CAT_PALETTE[1], linestyle='-', alpha=0.9,
               linewidth=GATE_LW, label=f"{threshold_labels[1]} ({thresholds[1]:g})")
    ax.axhline(y=thresholds[0], color=CAT_PALETTE[2], linestyle='--', alpha=0.7,
               linewidth=CONTEXT_LW, label=f"{threshold_labels[0]} ({thresholds[0]:g})")
    thin_legend(ax, loc='best')

    median = np.median(values)
    mean = np.mean(values)
    stat_box(ax, f'n={len(values)}\nmed={median:.2f}\nmean={mean:.2f}')

    ax.set_title(title, fontsize=TITLE_FONTSIZE, pad=4)
    ax.set_ylabel(ylabel)
    ax.set_xlim(-0.5, 0.5)
    ax.set_xticks([])


# ============================================================
# Individual figure functions
# ============================================================

def plot_ddg_distribution(df, output_path=None):
    """Plot 1: ddG distribution."""
    return plot_violin_strip(
        df['ddg'].values, 'Binding energy (ddG)',
        'ddG (REU, more negative = better)',
        (QUALITY_THRESHOLDS['ddg_good'], QUALITY_THRESHOLDS['ddg_acceptable']),
        higher_is_better=False, palette_idx=0, output_path=output_path,
        threshold_labels=('Excellent ddG', THRESHOLD_LABELS['ddg']))


def plot_ipae_distribution(df, output_path=None):
    """Plot 2: iPAE distribution."""
    if 'iPAE' not in df.columns:
        return None
    values = df['iPAE'].dropna().values
    if len(values) == 0:
        return None
    return plot_violin_strip(
        values, 'Interface iPAE',
        'iPAE (lower is better)',
        (QUALITY_THRESHOLDS['ipae_good'], QUALITY_THRESHOLDS['ipae_acceptable']),
        higher_is_better=False, palette_idx=1, output_path=output_path,
        threshold_labels=('Strict iPAE', THRESHOLD_LABELS['ipae']))


def plot_plddt_distribution(df, output_path=None):
    """Plot 3: pLDDT distribution."""
    if 'pLDDT' not in df.columns:
        return None
    values = df['pLDDT'].dropna().values
    if len(values) == 0:
        return None
    fig = plot_violin_strip(
        values, 'pLDDT distribution',
        'pLDDT (higher is better)',
        (QUALITY_THRESHOLDS['plddt_good'], QUALITY_THRESHOLDS['plddt_acceptable']),
        higher_is_better=True, palette_idx=2, output_path=output_path,
        threshold_labels=('Excellent pLDDT', THRESHOLD_LABELS['plddt']))
    fig.axes[0].set_ylim(min(values) - 0.05, 1.05)
    if output_path:
        save_for_pub(fig, output_path)
    return fig


def plot_sap_distribution(df, output_path=None):
    """Plot 4: SAP distribution."""
    if 'sap' not in df.columns:
        return None
    values = df['sap'].dropna().values
    if len(values) == 0:
        return None
    return plot_violin_strip(
        values, 'Aggregation propensity (SAP)',
        'SAP (lower is better)',
        (QUALITY_THRESHOLDS['sap_good'], QUALITY_THRESHOLDS['sap_acceptable']),
        higher_is_better=False, palette_idx=3, output_path=output_path,
        threshold_labels=('Strict SAP', THRESHOLD_LABELS['sap']))


def plot_cms_distribution(df, output_path=None):
    """Plot 5: CMS distribution."""
    if 'cms' not in df.columns:
        return None
    values = df['cms'].dropna().values
    if len(values) == 0:
        return None
    return plot_violin_strip(
        values, 'Contact molecular surface (CMS)',
        'CMS (\u00c5\u00b2, higher is better)',
        (QUALITY_THRESHOLDS['cms_good'], QUALITY_THRESHOLDS['cms_acceptable']),
        higher_is_better=True, palette_idx=4, output_path=output_path,
        threshold_labels=('Excellent CMS', THRESHOLD_LABELS['cms']))


def plot_quality_scatter(df, output_path=None):
    """Plot 6: Scatter plot of ddG vs iPAE colored by composite score."""
    if 'iPAE' not in df.columns:
        return None
    fig, ax = simple_ax(figsize=SCATTER_SIZE)
    style_axis_vbar(ax)
    scores = calculate_composite_score(df)

    scatter = ax.scatter(df['ddg'], df['iPAE'], c=scores, cmap='viridis',
                        s=DOT_SIZE, alpha=DOT_ALPHA, linewidths=0)

    # Shaded region = passes BOTH paper-aligned cutoffs (ddG and iPAE).
    ddg_min, ddg_max = SCATTER_DDG_XLIM
    ipae_min, ipae_max = SCATTER_IPAE_YLIM
    ddg_cut = QUALITY_THRESHOLDS['ddg_acceptable']
    ipae_cut = QUALITY_THRESHOLDS['ipae_acceptable']
    rect_good = Rectangle((ddg_min, ipae_min),
                          ddg_cut - ddg_min, ipae_cut - ipae_min,
                          linewidth=0, facecolor=CAT_PALETTE[2], alpha=0.10)
    ax.add_patch(rect_good)

    ax.axvline(x=ddg_cut, color=CAT_PALETTE[2], linestyle='-', alpha=0.9,
               linewidth=GATE_LW, label=f"{THRESHOLD_LABELS['ddg']} ({ddg_cut:g})")
    ax.axhline(y=ipae_cut, color=CAT_PALETTE[1], linestyle='-', alpha=0.9,
               linewidth=GATE_LW, label=f"{THRESHOLD_LABELS['ipae']} ({ipae_cut:g})")
    thin_legend(ax, loc='upper right')

    ax.set_title('ddG vs iPAE', fontsize=TITLE_FONTSIZE, pad=4)
    ax.set_xlabel('ddG (REU, more negative = better)', fontsize=XLABEL_FONTSIZE)
    ax.set_ylabel('iPAE (lower is better)')
    ax.set_xlim(ddg_min, ddg_max)
    ax.set_ylim(ipae_min, ipae_max)
    annotate_offscale(ax, df['ddg'], df['iPAE'],
                       SCATTER_DDG_XLIM, SCATTER_IPAE_YLIM)

    cbar = plt.colorbar(scatter, ax=ax, shrink=0.85, aspect=22, pad=0.03)
    style_colorbar(cbar, 'Composite score')

    plt.tight_layout()
    if output_path:
        save_for_pub(fig, output_path)
    return fig


def plot_composite_distribution(df, output_path=None):
    """Plot 7: Composite score distribution."""
    scores = calculate_composite_score(df).values
    fig = plot_violin_strip(
        scores, 'Composite score distribution',
        'Score', (0.7, 0.5),
        higher_is_better=True, palette_idx=4, output_path=output_path)
    ax = fig.axes[0]
    # Replace with viridis-colored points
    for coll in list(ax.collections):
        if hasattr(coll, 'get_offsets') and len(coll.get_offsets()) == len(scores):
            coll.remove()
            break
    jitter = np.random.default_rng(42).uniform(-0.12, 0.12, len(scores))
    ax.scatter(jitter, scores, c=scores, cmap='viridis', s=DOT_SIZE,
               alpha=DOT_ALPHA, linewidths=0, zorder=3)
    if output_path:
        save_for_pub(fig, output_path)
    return fig


def plot_metrics_table(df, output_path=None, top_n=6):
    """Plot 8: Top designs table with three-line academic style."""
    fig = plt.figure(figsize=METRICS_TABLE_SIZE)
    # Axes covers the whole page: the table *is* the figure, so there are no
    # outer margins to trim later.
    ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
    ax.axis('off')

    df = df.copy()
    df['score'] = calculate_composite_score(df)

    col_defs = [('design_id', 'Design')]
    for col, header in [('ddg', 'ddG'), ('iPAE', 'iPAE'), ('pLDDT', 'pLDDT'),
                         ('sap', 'SAP'), ('cms', 'CMS')]:
        if col in df.columns:
            col_defs.append((col, header))
    col_defs.append(('score', 'Score'))

    df_sorted = df.sort_values('score', ascending=False).head(top_n).reset_index(drop=True)
    n_rows = len(df_sorted) + 1
    n_cols = len(col_defs)

    # One bbox for both the table and its three rules, so they cannot drift.
    # Full width, inset vertically so the top and bottom rules read as edges
    # rather than as strokes clipped by the page boundary.
    rule_pad = METRICS_TABLE_RULE_INSET_MM / METRICS_TABLE_MM[1]
    bbox = [0.0, rule_pad, 1.0, 1.0 - 2 * rule_pad]
    table = ax.table(cellText=[['']*n_cols for _ in range(n_rows)],
                     loc='center', cellLoc='center', bbox=bbox)
    # Size columns to their content: design IDs (2PQK_MCL1_75) are far wider
    # than a numeric cell and get clipped under equal-width columns.
    table.auto_set_column_width(col=list(range(n_cols)))

    for j, (col, header) in enumerate(col_defs):
        cell = table[(0, j)]
        cell.set_text_props(text=header, fontsize=BASE_FONTSIZE)
        cell.set_facecolor('white')

    for i, (_, row) in enumerate(df_sorted.iterrows()):
        for j, (col, header) in enumerate(col_defs):
            cell = table[(i+1, j)]
            val = row[col]
            if col == 'design_id':
                text = simplify_design_id(val)
            elif pd.isna(val):
                text = '-'
            elif col == 'ddg':
                text = f'{val:.1f}'
            elif col == 'iPAE':
                text = f'{val:.3f}'
            elif col == 'pLDDT':
                text = f'{val:.2f}'
            elif col == 'sap':
                text = f'{val:.1f}'
            elif col == 'cms':
                text = f'{val:.0f}'
            else:
                text = f'{val:.2f}'
            cell.set_text_props(text=text, fontsize=TABLE_FONTSIZE)

    # Three-line style with alternating row shading
    table.auto_set_font_size(False)
    for (row_idx, col_idx), cell in table.get_celld().items():
        cell.set_edgecolor('white')
        cell.set_linewidth(0)
        cell.set_height(0.11)
        if row_idx > 0 and row_idx % 2 == 0:
            cell.set_facecolor('#F7F7F7')
        elif row_idx > 0:
            cell.set_facecolor('white')

    # Three-line rules: above the header, under the header, under the last row.
    x_left, x_right = bbox[0], bbox[0] + bbox[2]
    y_bottom, y_top = bbox[1], bbox[1] + bbox[3]
    row_h = bbox[3] / n_rows
    y_header_bottom = y_top - row_h

    line_kwargs = dict(color='#333333', linewidth=RULE_LW,
                       transform=ax.transAxes, clip_on=False)
    ax.plot([x_left, x_right], [y_top, y_top], **line_kwargs)
    ax.plot([x_left, x_right], [y_header_bottom, y_header_bottom], **line_kwargs)
    ax.plot([x_left, x_right], [y_bottom, y_bottom], **line_kwargs)

    # No tight_layout: it would re-inset the full-bleed axes and bring the
    # margins back.
    if output_path:
        # bbox_inches=None: keep the page at METRICS_TABLE_MM exactly.
        save_for_pub(fig, output_path, bbox_inches=None)
    return fig


# ============================================================
# Timeline
# ============================================================

def parse_pipeline_log(log_path: Path) -> list:
    """Parse pipeline.log to extract stage start times and durations.

    Handles both log prefixes the pipeline has emitted: the bare `[HH:MM:SS]`
    form and the current `YYYY-MM-DD HH:MM:SS [LEVEL]` form. Stage headers are
    matched anywhere in the message body (`... [INFO] STAGE 3: ...`).
    """
    if not log_path.exists():
        return None
    # group 1 = clock-only prefix, group 2 = full timestamp prefix, group 3 = body
    time_pattern = re.compile(
        r'^(?:\[(\d{2}:\d{2}:\d{2})\]|(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}))\s+(.*)$')
    with open(log_path) as f:
        lines = f.readlines()

    # Stage headers in the order they appear. A resumed run re-emits a header
    # (e.g. stage 3 with more recycles after stage 5), so segments are keyed by
    # position in the log, not by stage number — keying by number would let a
    # rerun overwrite the original start time and scramble the ordering.
    headers = []
    first_time = prev_time = None
    for line in lines:
        m = time_pattern.match(line.strip())
        if not m:
            continue
        clock_str, stamp_str, content = m.groups()
        if stamp_str:
            t = datetime.strptime(stamp_str, '%Y-%m-%d %H:%M:%S')
        else:
            t = datetime.strptime(clock_str, '%H:%M:%S')
            # Clock-only logs wrap at midnight; push past-midnight lines to day 2.
            if prev_time and t < prev_time:
                t = t.replace(day=2)
        if first_time is None:
            first_time = t
        prev_time = t
        stage_match = re.search(r'STAGE\s+(\d+):', content)
        if stage_match:
            headers.append((int(stage_match.group(1)), t))
    if not headers or first_time is None:
        return None

    seen = {}
    steps = []
    for i, (stage_no, start) in enumerate(headers):
        end = headers[i + 1][1] if i + 1 < len(headers) else prev_time
        idx = stage_no - 1
        name = PIPELINE_STAGES[idx] if idx < len(PIPELINE_STAGES) else f'Stage {stage_no}'
        seen[stage_no] = seen.get(stage_no, 0) + 1
        if seen[stage_no] > 1:
            name = f'{name} (rerun {seen[stage_no] - 1})'
        steps.append({
            'name': name,
            'start': round((start - first_time).total_seconds() / 60, 1),
            'duration': round(max((end - start).total_seconds() / 60, 0.5), 1),
        })
    reruns = [n for n, c in seen.items() if c > 1]
    if reruns:
        print(f"  Note: log contains re-run stage(s) {sorted(reruns)}; "
              "timeline shows them as separate chronological segments")
    return steps


def plot_execution_timeline(results_dir, output_path=None):
    """Plot 9: Gantt chart of pipeline stages."""
    fig, ax = simple_ax(figsize=TIMELINE_SIZE)
    style_axis_hbar(ax)
    ax.set_title('Execution timeline', fontsize=TITLE_FONTSIZE, pad=4)

    default_steps = [
        {'name': 'Stage 1: Backbone Gen.', 'start': 0, 'duration': 30},
        {'name': 'Stage 2: Seq. Design', 'start': 30, 'duration': 120},
        {'name': 'Stage 3: DL Validation', 'start': 150, 'duration': 60},
        {'name': 'Stage 4: Physics Filter', 'start': 210, 'duration': 30},
        {'name': 'Stage 5: Clustering', 'start': 240, 'duration': 5},
    ]

    steps = None
    results_dir = Path(results_dir)
    for log_path in [results_dir / "pipeline.log", results_dir.parent / "pipeline.log"]:
        if log_path.exists():
            steps = parse_pipeline_log(log_path)
            if steps:
                print(f"Loaded timeline from {log_path} ({len(steps)} stages)")
                break
    if steps is None:
        steps = default_steps

    total_time = max(s['start'] + s['duration'] for s in steps)
    colors = [CAT_PALETTE[i % len(CAT_PALETTE)] for i in range(len(steps))]
    y_positions = list(range(len(steps)-1, -1, -1))

    for i, (step, y_pos) in enumerate(zip(steps, y_positions)):
        ax.barh(y_pos, step['duration'], left=step['start'], height=0.55,
                color=colors[i], edgecolor='white', linewidth=BAR_EDGE_LW)
        ax.text(-total_time * 0.015, y_pos, step['name'], ha='right',
                va='center', fontsize=BASE_FONTSIZE)

    total_label = f"Total: ~{total_time/60:.1f} hours" if total_time >= 60 else f"Total: ~{int(total_time)} min"
    ax.barh(-1, total_time, left=0, height=0.55, color=GRAY, alpha=0.8,
            edgecolor='white', linewidth=BAR_EDGE_LW)
    ax.text(-total_time * 0.015, -1, total_label, ha='right', va='center',
            fontsize=BASE_FONTSIZE)

    ax.set_xlabel('Time (minutes)', fontsize=XLABEL_FONTSIZE)
    ax.set_xlim(0, total_time * 1.03)
    ax.set_ylim(-2, len(steps))
    ax.set_yticks([])
    ax.spines['left'].set_visible(False)

    plt.tight_layout()
    if output_path:
        save_for_pub(fig, output_path)
    return fig


# ============================================================
# Entry Points
# ============================================================

def create_separate_figures(results_dir: str, output_prefix: str = None,
                             target: str = None):
    """Create separate visualization figures for RFpeptides pipeline."""
    results_dir = Path(results_dir)
    if output_prefix is None:
        output_prefix = str(results_dir / "rfpeptides")

    target = target or detect_target(results_dir)
    configure_thresholds(target)
    print(f"Using paper thresholds for target: {target}")

    set_pub_plot_context(context="talk")
    df = load_design_metrics(results_dir)
    if df.empty:
        print("Error: No design metrics found in", results_dir)
        return None

    saved_files = []

    def _save(fig, name):
        if fig is not None:
            saved_files.append(f"{output_prefix}_{name}.pdf")
            plt.close(fig)

    _save(plot_ddg_distribution(df, f"{output_prefix}_ddg_distribution"), "ddg_distribution")
    _save(plot_ipae_distribution(df, f"{output_prefix}_ipae_distribution"), "ipae_distribution")
    _save(plot_plddt_distribution(df, f"{output_prefix}_plddt_distribution"), "plddt_distribution")
    _save(plot_sap_distribution(df, f"{output_prefix}_sap_distribution"), "sap_distribution")
    _save(plot_cms_distribution(df, f"{output_prefix}_cms_distribution"), "cms_distribution")
    _save(plot_quality_scatter(df, f"{output_prefix}_quality_scatter"), "quality_scatter")
    _save(plot_composite_distribution(df, f"{output_prefix}_composite_score"), "composite_score")
    _save(plot_metrics_table(df, f"{output_prefix}_metrics_table"), "metrics_table")
    _save(plot_execution_timeline(results_dir, f"{output_prefix}_execution_timeline"), "execution_timeline")

    print(f"\nGenerated {len(saved_files)} figures:")
    for f in saved_files:
        print(f"  - {f}")
    return saved_files


def create_merged_figure(results_dir: str, output_prefix: str = None,
                          target: str = None):
    """Create a single merged figure with key panels in 3x3 grid.

    Layout:
        Row 1: ddG distribution, iPAE distribution, Quality scatter
        Row 2: pLDDT distribution, SAP distribution, CMS distribution
        Row 3: Composite score, Top designs table, Timeline
    """
    results_dir = Path(results_dir)
    if output_prefix is None:
        output_prefix = str(results_dir / "rfpeptides_summary")

    target = target or detect_target(results_dir)
    configure_thresholds(target)
    print(f"Using paper thresholds for target: {target}")

    set_pub_plot_context(context="talk")
    df = load_design_metrics(results_dir)
    if df.empty:
        print("Error: No design metrics found in", results_dir)
        return None

    fig = plt.figure(figsize=MERGED_3x3_SIZE)
    axes = [fig.add_subplot(3, 3, i+1) for i in range(9)]
    for ax in axes:
        prettify_ax(ax)

    # Row 1
    _plot_violin_strip_ax(axes[0], df['ddg'].values, 'ddG distribution',
                          'ddG (REU)',
                          (QUALITY_THRESHOLDS['ddg_good'], QUALITY_THRESHOLDS['ddg_acceptable']),
                          higher_is_better=False, palette_idx=0,
                          threshold_labels=('Excellent ddG', THRESHOLD_LABELS['ddg']))

    if 'iPAE' in df.columns:
        _plot_violin_strip_ax(axes[1], df['iPAE'].dropna().values, 'iPAE distribution',
                              'iPAE',
                              (QUALITY_THRESHOLDS['ipae_good'], QUALITY_THRESHOLDS['ipae_acceptable']),
                              higher_is_better=False, palette_idx=1,
                              threshold_labels=('Strict iPAE', THRESHOLD_LABELS['ipae']))
    else:
        axes[1].text(0.5, 0.5, 'No iPAE data', ha='center', va='center', transform=axes[1].transAxes)
        axes[1].axis('off')

    # Quality scatter — paper-aligned cutoffs (solid lines + legend).
    if 'iPAE' in df.columns:
        scores = calculate_composite_score(df)
        style_axis_vbar(axes[2])
        scatter = axes[2].scatter(df['ddg'], df['iPAE'], c=scores, cmap='viridis',
                                  s=DOT_SIZE, alpha=DOT_ALPHA, linewidths=0)
        ddg_cut = QUALITY_THRESHOLDS['ddg_acceptable']
        ipae_cut = QUALITY_THRESHOLDS['ipae_acceptable']
        axes[2].axvline(x=ddg_cut, color=CAT_PALETTE[2], linestyle='-', alpha=0.9,
                        linewidth=GATE_LW, label=f"ddG<{ddg_cut:g}")
        axes[2].axhline(y=ipae_cut, color=CAT_PALETTE[1], linestyle='-', alpha=0.9,
                        linewidth=GATE_LW, label=f"iPAE<{ipae_cut:g}")
        thin_legend(axes[2], loc='upper right')
        axes[2].set_title('ddG vs iPAE (paper cutoffs)', fontsize=TITLE_FONTSIZE, pad=4)
        axes[2].set_xlabel('ddG', fontsize=XLABEL_FONTSIZE)
        axes[2].set_ylabel('iPAE')
        axes[2].set_xlim(*SCATTER_DDG_XLIM)
        axes[2].set_ylim(*SCATTER_IPAE_YLIM)
        annotate_offscale(axes[2], df['ddg'], df['iPAE'],
                           SCATTER_DDG_XLIM, SCATTER_IPAE_YLIM)
        style_colorbar(plt.colorbar(scatter, ax=axes[2], shrink=0.85, aspect=22,
                                    pad=0.03), 'Score')
    else:
        axes[2].text(0.5, 0.5, 'No data', ha='center', va='center', transform=axes[2].transAxes)
        axes[2].axis('off')

    # Row 2
    if 'pLDDT' in df.columns:
        vals = df['pLDDT'].dropna().values
        _plot_violin_strip_ax(axes[3], vals, 'pLDDT', 'pLDDT',
                              (QUALITY_THRESHOLDS['plddt_good'], QUALITY_THRESHOLDS['plddt_acceptable']),
                              higher_is_better=True, palette_idx=2,
                              threshold_labels=('Excellent pLDDT', THRESHOLD_LABELS['plddt']))
        axes[3].set_ylim(min(vals) - 0.05, 1.05)
    else:
        axes[3].text(0.5, 0.5, 'No data', ha='center', va='center', transform=axes[3].transAxes)
        axes[3].axis('off')

    if 'sap' in df.columns:
        _plot_violin_strip_ax(axes[4], df['sap'].dropna().values, 'SAP', 'SAP',
                              (QUALITY_THRESHOLDS['sap_good'], QUALITY_THRESHOLDS['sap_acceptable']),
                              higher_is_better=False, palette_idx=3,
                              threshold_labels=('Strict SAP', THRESHOLD_LABELS['sap']))
    else:
        axes[4].text(0.5, 0.5, 'No data', ha='center', va='center', transform=axes[4].transAxes)
        axes[4].axis('off')

    if 'cms' in df.columns:
        _plot_violin_strip_ax(axes[5], df['cms'].dropna().values, 'CMS', 'CMS (\u00c5\u00b2)',
                              (QUALITY_THRESHOLDS['cms_good'], QUALITY_THRESHOLDS['cms_acceptable']),
                              higher_is_better=True, palette_idx=4,
                              threshold_labels=('Excellent CMS', THRESHOLD_LABELS['cms']))
    else:
        axes[5].text(0.5, 0.5, 'No data', ha='center', va='center', transform=axes[5].transAxes)
        axes[5].axis('off')

    # Row 3: Composite score
    scores = calculate_composite_score(df)
    _plot_violin_strip_ax(axes[6], scores.values, 'Composite score', 'Score',
                          (0.7, 0.5), higher_is_better=True, palette_idx=4)

    # Table (three-line style)
    axes[7].axis('off')
    axes[7].set_title('Top designs', fontsize=TITLE_FONTSIZE, pad=4)
    df_t = df.copy()
    df_t['score'] = scores
    col_defs = [('design_id', 'ID')]
    for col, h in [('ddg', 'ddG'), ('iPAE', 'iPAE'), ('pLDDT', 'pLDDT')]:
        if col in df_t.columns:
            col_defs.append((col, h))
    col_defs.append(('score', 'Score'))
    df_top = df_t.sort_values('score', ascending=False).head(6).reset_index(drop=True)
    n_rows = len(df_top) + 1
    n_cols = len(col_defs)
    table = axes[7].table(cellText=[['']*n_cols for _ in range(n_rows)],
                          loc='center', cellLoc='center', bbox=[0.0, 0.05, 1.0, 0.9])
    table.auto_set_column_width(col=list(range(n_cols)))
    for j, (col, header) in enumerate(col_defs):
        cell = table[(0, j)]
        cell.set_text_props(text=header, fontsize=BASE_FONTSIZE)
        cell.set_facecolor('white')
    for i, (_, row) in enumerate(df_top.iterrows()):
        for j, (col, h) in enumerate(col_defs):
            cell = table[(i+1, j)]
            val = row[col]
            if col == 'design_id':
                text = compact_design_id(val)
            elif pd.isna(val):
                text = '-'
            elif col == 'ddg':
                text = f'{val:.1f}'
            elif col == 'iPAE':
                text = f'{val:.3f}'
            else:
                text = f'{val:.2f}'
            cell.set_text_props(text=text, fontsize=TABLE_FONTSIZE)
    table.auto_set_font_size(False)
    for (row_idx, col_idx), cell in table.get_celld().items():
        cell.set_edgecolor('white')
        cell.set_linewidth(0)
        cell.set_height(0.11)
        if row_idx > 0 and row_idx % 2 == 0:
            cell.set_facecolor('#F7F7F7')
        elif row_idx > 0:
            cell.set_facecolor('white')
    bbox_t = [0.0, 0.05, 1.0, 0.9]
    xl, xr = bbox_t[0], bbox_t[0] + bbox_t[2]
    yb, yt = bbox_t[1], bbox_t[1] + bbox_t[3]
    rh = bbox_t[3] / n_rows
    lkw = dict(color='#333333', linewidth=RULE_LW,
               transform=axes[7].transAxes, clip_on=False)
    axes[7].plot([xl, xr], [yt, yt], **lkw)
    axes[7].plot([xl, xr], [yt - rh, yt - rh], **lkw)
    axes[7].plot([xl, xr], [yb, yb], **lkw)

    # Timeline
    style_axis_hbar(axes[8])
    axes[8].set_title('Timeline', fontsize=TITLE_FONTSIZE, pad=4)
    default_steps = [
        {'name': 'Backbone', 'start': 0, 'duration': 30},
        {'name': 'Seq Design', 'start': 30, 'duration': 120},
        {'name': 'DL Valid.', 'start': 150, 'duration': 60},
        {'name': 'Physics', 'start': 210, 'duration': 30},
        {'name': 'Cluster', 'start': 240, 'duration': 5},
    ]
    steps = None
    rd = Path(results_dir)
    for lp in [rd / "pipeline.log", rd.parent / "pipeline.log"]:
        if lp.exists():
            steps = parse_pipeline_log(lp)
            if steps:
                for s in steps:
                    s['name'] = s['name'].split(': ')[-1] if ': ' in s['name'] else s['name']
                break
    if steps is None:
        steps = default_steps
    total_time = max(s['start'] + s['duration'] for s in steps)
    colors_t = [CAT_PALETTE[i % len(CAT_PALETTE)] for i in range(len(steps))]
    yp_t = list(range(len(steps)-1, -1, -1))
    for i, (step, yp) in enumerate(zip(steps, yp_t)):
        axes[8].barh(yp, step['duration'], left=step['start'], height=0.55,
                     color=colors_t[i], edgecolor='white', linewidth=BAR_EDGE_LW)
        axes[8].text(-total_time * 0.015, yp, step['name'], ha='right',
                     va='center', fontsize=BASE_FONTSIZE)
    axes[8].barh(-1, total_time, left=0, height=0.55, color=GRAY, alpha=0.8,
                 edgecolor='white', linewidth=BAR_EDGE_LW)
    tl = f"~{total_time/60:.1f}h" if total_time >= 60 else f"~{int(total_time)}m"
    axes[8].text(-total_time * 0.015, -1, tl, ha='right', va='center',
                 fontsize=BASE_FONTSIZE)
    axes[8].set_xlabel('Time (min)', fontsize=XLABEL_FONTSIZE)
    axes[8].set_xlim(0, total_time * 1.03)
    axes[8].set_ylim(-2, len(steps))
    axes[8].set_yticks([])
    axes[8].spines['left'].set_visible(False)

    plt.tight_layout()
    save_for_pub(fig, output_prefix)
    plt.close(fig)
    print(f"\nSaved merged figure: {output_prefix}.pdf")
    return f"{output_prefix}.pdf"


# ============================================================
# CLI entry point
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='Generate RFpeptides pipeline visualization figures')
    parser.add_argument('results_dir', type=str,
                        help='Path to pipeline results directory')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='Output prefix (default: results_dir/rfpeptides)')
    parser.add_argument('--merged', '-m', action='store_true',
                        help='Create merged 3x3 summary figure instead of separate figures')
    parser.add_argument('--target', '-t', type=str, default=None,
                        choices=['mcl1', 'mdm2', 'gabarap', 'rbta', 'general'],
                        help='Target name for paper-faithful thresholds '
                             '(default: auto-detect from results path)')

    args = parser.parse_args()

    if args.merged:
        output_file = create_merged_figure(args.results_dir, args.output, target=args.target)
        if output_file:
            print(f"\nVisualization complete: {output_file}")
        else:
            print("\nVisualization failed")
            exit(1)
    else:
        output_files = create_separate_figures(args.results_dir, args.output, target=args.target)
        if output_files:
            print(f"\nVisualization complete!")
        else:
            print("\nVisualization failed")
            exit(1)


if __name__ == '__main__':
    main()
