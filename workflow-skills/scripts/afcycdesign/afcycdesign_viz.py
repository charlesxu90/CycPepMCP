#!/usr/bin/env python3
"""
AfCycDesign Pipeline Visualization Script

Generates separate figures after binder design workflow:
1. pLDDT Scores - Bar chart of pLDDT sorted descending
2. Interface iPAE - Bar chart of iPAE scores sorted ascending
3. Quality Scatter - pLDDT vs iPAE colored by composite score
4. Design Ranking - Horizontal bar chart by composite score
5. Metrics Table - Top designs with all metrics
6. iPTM Scores - Bar chart of interface pTM scores

Every figure is saved as a print-sized PDF only (no PNG/SVG), styled through
`workflow-skills/scripts/plot_style_utils.py`: Arial at 6-7 pt, 0.3 pt axes,
2 pt data markers, mm-accurate Nature column widths, and `pdf.fonttype=42` so
all text stays editable in Illustrator.
A merged 2x3 summary figure can also be generated.
"""

import argparse
import json
import os
import sys
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
    ANNOT_FONTSIZE, BAR_EDGE_LW, BAR_MM, BASE_FONTSIZE, CAT_PALETTE,
    CONTEXT_LW, DEFAULT_FIGURE_RCPARAMS, DOT_ALPHA, DOT_SIZE, GATE_LW,
    MERGED_2x3_SIZE, PANEL_SIZE, RULE_LW, SCATTER_SIZE, TABLE_FONTSIZE,
    TABLE_SIZE, TITLE_FONTSIZE, XLABEL_FONTSIZE, annotate_offscale,
    apply_nature_rcparams, mm_size, prettify_ax, save_pdf, simple_ax, stat_box,
    style_axis_vbar, style_box, style_colorbar, style_violin, thin_legend,
    tier_color,
)

# Centralized PASS-gate thresholds (single source of truth: benchmark/configs/workflows.yaml).
_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / "benchmark" / "configs" / "thresholds.py").is_file():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break
from benchmark.configs import thresholds as cfg  # noqa: E402

# Figure size for individual distribution plots (45 x 40 mm print size).
FIGSIZE = PANEL_SIZE


# Adaptive figure size based on number of designs
def adaptive_figsize(n_designs, base_mm=BAR_MM):
    """Print width for a per-design bar chart, widened for large design sets.

    Starts at the single-column width and grows by 1.5 mm per design past 40,
    capped at double-column width so the page stays printable.
    """
    width_mm, height_mm = base_mm
    if n_designs > 40:
        width_mm = min(183.0, width_mm + (n_designs - 40) * 1.5)
    return mm_size(width_mm, height_mm)

# Quality thresholds for AfCycDesign pipeline.
# `_good` => excellent gate (tighter line); `_acceptable` => primary PASS gate.
# All values are pulled from workflows.yaml so the viz reflects the locked spec.
_AF_PRIMARY = cfg.AFCYCDESIGN_PASS_GATE.primary
_AF_EXCELLENT = cfg.AFCYCDESIGN_PASS_GATE.excellent
QUALITY_THRESHOLDS = {
    'plddt_good':       _AF_EXCELLENT['mean_plddt_min'],
    'plddt_acceptable': _AF_PRIMARY['mean_plddt_min'],
    'ipae_good':        _AF_EXCELLENT['ipae_max'],
    'ipae_acceptable':  _AF_PRIMARY['ipae_max'],
    'iptm_good':        _AF_EXCELLENT['iptm_min'],
    'iptm_acceptable':  _AF_PRIMARY['iptm_min'],
    'ptm_good':         _AF_EXCELLENT['ptm_min'],
    'ptm_acceptable':   _AF_PRIMARY['ptm_min'],
}

# Three-tier pLDDT/iPAE classification. workflows.yaml carries a two-tier gate
# (primary / excellent); these tiers are declared locally so the benchmark gates
# used by other workflows stay untouched. Tiers are nested: Excellent < Good <
# Acceptable. pLDDT is on the 0-1 scale used in afcycdesign_results.csv.
DESIGN_CLASSES = (
    ('Excellent',  {'plddt_min': 0.90, 'ipae_max': 0.11}),
    ('Good',       {'plddt_min': 0.85, 'ipae_max': 0.15}),
    ('Acceptable', {'plddt_min': 0.70, 'ipae_max': 0.30}),
)

# Threshold lines drawn on the pLDDT and iPAE panels follow the classification
# above: '_good' is the tightest line (Excellent), '_acceptable' the outer gate.
QUALITY_THRESHOLDS.update({
    'plddt_good':       DESIGN_CLASSES[0][1]['plddt_min'],
    'plddt_acceptable': DESIGN_CLASSES[2][1]['plddt_min'],
    'ipae_good':        DESIGN_CLASSES[0][1]['ipae_max'],
    'ipae_acceptable':  DESIGN_CLASSES[2][1]['ipae_max'],
})


def classify_designs(df):
    """Assign each design its highest matching tier from DESIGN_CLASSES.

    Returns a Series of class names; designs meeting no tier are 'Unclassified'.
    Requires pLDDT and iPAE columns -- returns all 'Unclassified' without them.
    """
    if 'pLDDT' not in df.columns or 'iPAE' not in df.columns:
        return pd.Series(['Unclassified'] * len(df), index=df.index)

    out = pd.Series(['Unclassified'] * len(df), index=df.index)
    for name, gate in reversed(DESIGN_CLASSES):
        hit = (df['pLDDT'] > gate['plddt_min']) & (df['iPAE'] < gate['ipae_max'])
        out[hit] = name
    return out

# AF2 hallucination loss has no gate in workflows.yaml; these are the
# viz-internal context lines used when a run predates iPAE reporting.
LOSS_THRESHOLDS = {'good': 2.0, 'acceptable': 3.0}

# Fixed axis ranges for the quality scatter. Auto-scaling made the same design
# land at a different position in every batch, so the panel is pinned instead
# and stays visually comparable across runs. annotate_offscale() flags any
# design the window excludes.
SCATTER_XLIM = (0.5, 1.0)                      # pLDDT
SCATTER_YLIM = {'iPAE': (0.0, 0.5), 'loss': (1.5, 2.75)}


def set_pub_plot_context(context=None):
    """Apply the Nature print rcParams (Arial, 7 pt titles, 6 pt body)."""
    apply_nature_rcparams(DEFAULT_FIGURE_RCPARAMS)


def save_for_pub(fig, path):
    """Save figure as a single editable-text PDF."""
    return save_pdf(fig, path)


def get_color_for_value(value, threshold_good, threshold_acceptable, higher_is_better=True):
    """Quality-tier colour for a metric value (see plot_style_utils.tier_color)."""
    return tier_color(value, threshold_good, threshold_acceptable,
                      higher_is_better=higher_is_better)


def load_afcyc_json_files(results_dir: Path) -> pd.DataFrame:
    """Load individual *_afcyc.json result files into a DataFrame.

    Each JSON file contains metrics from a single AfCycDesign run:
    {sequence, pLDDT, iPAE, iPTM, pTM, i_con, loss, ...}
    """
    results_dir = Path(results_dir)
    json_files = sorted(results_dir.glob("*_afcyc.json"))

    if not json_files:
        # Also check for result_*.json pattern
        json_files = sorted(results_dir.glob("result_*.json"))

    if not json_files:
        return pd.DataFrame()

    records = []
    for jf in json_files:
        try:
            with open(jf) as f:
                data = json.load(f)
            # Use filename stem as design_id if not present
            if 'design_id' not in data:
                data['design_id'] = jf.stem.replace('_afcyc', '')
            records.append(data)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  Warning: Could not parse {jf.name}: {e}")

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    print(f"Loaded {len(df)} designs from individual JSON files in {results_dir}")
    return df


def load_design_metrics(results_dir: Path) -> pd.DataFrame:
    """Load design metrics from AfCycDesign results directory."""
    results_dir = Path(results_dir)

    # Priority 1: CSV files
    possible_names = [
        "afcycdesign_results.csv",
        "design_metrics.csv",
        "metrics.csv",
        "final_summary.csv",
    ]

    for name in possible_names:
        csv_path = results_dir / name
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            df = normalize_column_names(df)
            print(f"Loaded metrics from {csv_path} ({len(df)} designs)")
            return df

    # Priority 2: Individual JSON files
    df = load_afcyc_json_files(results_dir)
    if not df.empty:
        df = normalize_column_names(df)
        return df

    # Priority 3: Search subdirectories
    if not results_dir.exists():
        print("No metrics file found, generating mock data for demonstration")
        return generate_mock_data()

    for subdir in sorted(results_dir.iterdir()):
        if subdir.is_dir():
            for name in possible_names:
                csv_path = subdir / name
                if csv_path.exists():
                    df = pd.read_csv(csv_path)
                    df = normalize_column_names(df)
                    print(f"Loaded metrics from {csv_path} ({len(df)} designs)")
                    return df
            # Try JSON files in subdirectory
            df = load_afcyc_json_files(subdir)
            if not df.empty:
                df = normalize_column_names(df)
                return df

    print("No metrics file found, generating mock data for demonstration")
    return generate_mock_data()


def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names to standard format."""
    df = df.copy()

    column_mapping = {
        'design': 'design_id',
        'name': 'design_id',
        'design_name': 'design_id',
        'ipae': 'iPAE',
        'IPAE': 'iPAE',
        'i_pae': 'iPAE',
        'plddt': 'pLDDT',
        'PLDDT': 'pLDDT',
        'iptm': 'iPTM',
        'IPTM': 'iPTM',
        'i_ptm': 'iPTM',
        'ptm': 'pTM',
        'PTM': 'pTM',
        'i_con': 'i_con',
        'icon': 'i_con',
    }

    for old_name, new_name in column_mapping.items():
        if old_name in df.columns and new_name not in df.columns:
            df[new_name] = df[old_name]

    # Ensure design_id exists
    if 'design_id' not in df.columns:
        df['design_id'] = [f'd{i:02d}' for i in range(len(df))]

    # Filter out rows with sentinel values (iPAE=999 means job failed)
    if 'iPAE' in df.columns:
        n_before = len(df)
        df = df[df['iPAE'] < 900].reset_index(drop=True)
        n_filtered = n_before - len(df)
        if n_filtered > 0:
            print(f"  Filtered {n_filtered} designs with invalid iPAE (>900)")

    return df


def simplify_design_id(name: str) -> str:
    """Simplify design ID for display."""
    if isinstance(name, str):
        if name.startswith('design_'):
            return name.replace('design_', '').lstrip('0') or '0'
        return name
    return str(name)


def generate_mock_data(n_designs=8) -> pd.DataFrame:
    """Generate mock data for demonstration."""
    np.random.seed(42)

    designs = []
    for i in range(n_designs):
        designs.append({
            'design_id': f'd{i:02d}',
            'sequence': ''.join(np.random.choice(list('ADEFGHIKLMNPQRSTVWY'), 12)),
            'pLDDT': np.random.beta(5, 2),
            'iPAE': np.random.beta(2, 8) * 0.5,
            'iPTM': np.random.beta(4, 3),
            'pTM': np.random.beta(6, 2),
            'i_con': np.random.uniform(0.5, 2.0),
            'loss': np.random.uniform(1.0, 4.0),
        })

    df = pd.DataFrame(designs)
    df['pLDDT'] = df['pLDDT'].clip(0.3, 0.99)
    df['iPAE'] = df['iPAE'].clip(0.05, 0.5)
    df['iPTM'] = df['iPTM'].clip(0.2, 0.95)
    df['pTM'] = df['pTM'].clip(0.3, 0.99)

    return df


def calculate_composite_score(df: pd.DataFrame) -> pd.Series:
    """Calculate composite quality score for ranking designs.

    Score = 0.50 * pLDDT + 0.50 * (1 - iPAE)

    pLDDT and iPAE are the two metrics that gate design selection, so the score
    weights them equally and drops the iPTM/pTM terms, which are near-collinear
    with them (r > 0.96 on the MDM2 set) and shifted ranks by <1 position.

    When iPAE is unavailable the loss proxy (1 - loss/5) is substituted, as
    before, so runs predating iPAE reporting still rank.
    """
    scores = pd.DataFrame(index=df.index)

    # pLDDT: higher is better (0-1 scale)
    if 'pLDDT' in df.columns:
        scores['pLDDT'] = df['pLDDT'].clip(0, 1)

    # iPAE: lower is better. Normalize: 0 to 0.5 range
    if 'iPAE' in df.columns:
        scores['iPAE'] = (1 - df['iPAE'].clip(0, 1))
    elif 'loss' in df.columns:
        # Fallback: use loss as proxy for iPAE (normalize: 0-5 range)
        scores['iPAE'] = (1 - (df['loss'] / 5.0).clip(0, 1))

    # iPTM: higher is better (0-1 scale)
    if 'iPTM' in df.columns:
        scores['iPTM'] = df['iPTM'].clip(0, 1)

    # pTM: higher is better (0-1 scale)
    if 'pTM' in df.columns:
        scores['pTM'] = df['pTM'].clip(0, 1)

    weights = {'pLDDT': 0.50, 'iPAE': 0.50}

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
# Shared violin + strip panel
# ============================================================

def plot_violin_strip(values, title, ylabel, thresholds, higher_is_better=True,
                      palette_idx=0, output_path=None, legend_loc='lower left',
                      ylim=None, threshold_labels=('Excellent', 'Acceptable')):
    """Violin + box + strip distribution panel at print size.

    `thresholds` is (excellent, acceptable): the acceptable gate is drawn solid
    and prominent, the tighter excellent tier dashed and faint.
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

    ax.axhline(y=thresholds[1], color=CAT_PALETTE[1], linestyle='-', alpha=0.9,
               linewidth=GATE_LW,
               label=f"{threshold_labels[1]} ({thresholds[1]:g})")
    ax.axhline(y=thresholds[0], color=CAT_PALETTE[2], linestyle='--', alpha=0.7,
               linewidth=CONTEXT_LW,
               label=f"{threshold_labels[0]} ({thresholds[0]:g})")
    thin_legend(ax, loc=legend_loc)

    median = np.median(values)
    mean = np.mean(values)
    stat_box(ax, f'n={len(values)}\nmedian={median:.2f}\nmean={mean:.2f}')

    ax.set_title(title, fontsize=TITLE_FONTSIZE, pad=4)
    ax.set_ylabel(ylabel)
    ax.set_xlim(-0.5, 0.5)
    ax.set_xticks([])
    if ylim is not None:
        ax.set_ylim(*ylim)

    plt.tight_layout()
    if output_path:
        save_for_pub(fig, output_path)
    return fig


# ============================================================
# Figure 1: pLDDT Scores
# ============================================================

def plot_plddt_comparison(df: pd.DataFrame, output_path: str = None):
    """Plot 1: Distribution of pLDDT scores using violin + strip plot."""
    values = df['pLDDT'].values
    return plot_violin_strip(
        values, 'pLDDT distribution', 'pLDDT (higher is better)',
        (QUALITY_THRESHOLDS['plddt_good'], QUALITY_THRESHOLDS['plddt_acceptable']),
        higher_is_better=True, palette_idx=0, output_path=output_path,
        legend_loc='lower right', ylim=(min(values) - 0.05, 1.05),
        threshold_labels=('Excellent pLDDT', 'PASS gate pLDDT'))


# ============================================================
# Figure 2: Interface iPAE
# ============================================================

def plot_ipae_comparison(df: pd.DataFrame, output_path: str = None):
    """Plot 2: Bar chart of iPAE scores sorted ascending (lower = better)."""
    n_designs = len(df)
    figsize = adaptive_figsize(n_designs)
    fig, ax = simple_ax(figsize=figsize)
    style_axis_vbar(ax)

    df_sorted = df.sort_values('iPAE', ascending=True).reset_index(drop=True)
    x_pos = np.arange(n_designs)

    colors = [get_color_for_value(v, QUALITY_THRESHOLDS['ipae_good'],
                                   QUALITY_THRESHOLDS['ipae_acceptable'],
                                   higher_is_better=False)
              for v in df_sorted['iPAE']]

    ax.bar(x_pos, df_sorted['iPAE'], color=colors, width=0.8,
           edgecolor='white', linewidth=BAR_EDGE_LW)

    ax.axhline(y=QUALITY_THRESHOLDS['ipae_acceptable'], color=CAT_PALETTE[1],
               linestyle='-', alpha=0.9, linewidth=GATE_LW,
               label=f"PASS gate iPAE (<{QUALITY_THRESHOLDS['ipae_acceptable']})")
    ax.axhline(y=QUALITY_THRESHOLDS['ipae_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.7, linewidth=CONTEXT_LW,
               label=f"Excellent iPAE (<{QUALITY_THRESHOLDS['ipae_good']})")

    ax.set_title('Interface iPAE', fontsize=TITLE_FONTSIZE, pad=4)
    ax.set_ylabel('iPAE (lower is better)')
    ax.set_xlabel('Design', fontsize=XLABEL_FONTSIZE)
    ax.set_xticks(x_pos)

    labels = [simplify_design_id(name) for name in df_sorted['design_id']]
    ax.set_xticklabels(labels, fontsize=ANNOT_FONTSIZE, rotation=90, ha='center')
    ax.set_xlim(-0.8, n_designs - 0.2)

    thin_legend(ax, loc='upper left')

    plt.tight_layout()

    if output_path:
        save_for_pub(fig, output_path)

    return fig


# ============================================================
# Figure 2b: Loss Scores (fallback when iPAE is unavailable)
# ============================================================

def plot_loss_comparison(df: pd.DataFrame, output_path: str = None):
    """Plot 2b: Distribution of loss scores using violin + strip plot."""
    return plot_violin_strip(
        df['loss'].values, 'Loss distribution', 'Loss (lower is better)',
        (LOSS_THRESHOLDS['good'], LOSS_THRESHOLDS['acceptable']),
        higher_is_better=False, palette_idx=0, output_path=output_path,
        legend_loc='upper left',
        threshold_labels=('Excellent loss', 'Acceptable loss'))


# ============================================================
# Figure 3: Quality Scatter (pLDDT vs iPAE)
# ============================================================

def plot_quality_scatter(df: pd.DataFrame, output_path: str = None):
    """Plot 3: Scatter plot of pLDDT vs iPAE (or loss) colored by composite score."""
    fig, ax = simple_ax(figsize=SCATTER_SIZE)
    style_axis_vbar(ax)

    scores = calculate_composite_score(df)

    # Determine y-axis metric: prefer iPAE, fall back to loss
    if 'iPAE' in df.columns:
        y_metric = 'iPAE'
        y_label = 'iPAE (lower is better)'
        y_thresh_good = QUALITY_THRESHOLDS['ipae_good']
    elif 'loss' in df.columns:
        y_metric = 'loss'
        y_label = 'Loss (lower is better)'
        y_thresh_good = LOSS_THRESHOLDS['good']
    else:
        y_metric = None

    if y_metric is None:
        ax.text(0.5, 0.5, 'Scatter data\nnot available', ha='center', va='center',
                transform=ax.transAxes, fontsize=BASE_FONTSIZE)
        ax.axis('off')
    else:
        x_lo, x_hi = SCATTER_XLIM
        y_lo, y_hi = SCATTER_YLIM[y_metric]

        scatter = ax.scatter(df['pLDDT'], df[y_metric], c=scores, cmap='viridis',
                            s=DOT_SIZE, alpha=DOT_ALPHA, linewidths=0)

        # Good zone
        rect_good = Rectangle((QUALITY_THRESHOLDS['plddt_good'], y_lo),
                              x_hi - QUALITY_THRESHOLDS['plddt_good'],
                              y_thresh_good - y_lo,
                              linewidth=0, facecolor=CAT_PALETTE[2], alpha=0.10)
        ax.add_patch(rect_good)

        ax.axvline(x=QUALITY_THRESHOLDS['plddt_good'], color=CAT_PALETTE[2],
                   linestyle='--', alpha=0.7, linewidth=CONTEXT_LW)
        ax.axhline(y=y_thresh_good, color=CAT_PALETTE[2],
                   linestyle='--', alpha=0.7, linewidth=CONTEXT_LW)

        ax.set_title('Quality distribution', fontsize=TITLE_FONTSIZE, pad=4)
        ax.set_xlabel('pLDDT (higher is better)', fontsize=XLABEL_FONTSIZE)
        ax.set_ylabel(y_label)
        ax.set_xlim(x_lo, x_hi)
        ax.set_ylim(y_lo, y_hi)
        annotate_offscale(ax, df['pLDDT'], df[y_metric],
                          SCATTER_XLIM, SCATTER_YLIM[y_metric])

        cbar = plt.colorbar(scatter, ax=ax, shrink=0.85, aspect=22, pad=0.03)
        style_colorbar(cbar, 'Composite score')

        ax.text(QUALITY_THRESHOLDS['plddt_good'] + 0.01,
                y_lo + (y_thresh_good - y_lo) * 0.06,
                'Good zone', fontsize=ANNOT_FONTSIZE, color=CAT_PALETTE[2],
                ha='left')

    plt.tight_layout()

    if output_path:
        save_for_pub(fig, output_path)

    return fig


# ============================================================
# Figure 4: Design Ranking
# ============================================================

def plot_design_ranking(df: pd.DataFrame, output_path: str = None):
    """Plot 4: Distribution of composite scores using violin + strip plot."""
    fig, ax = simple_ax(figsize=SCATTER_SIZE)
    style_axis_vbar(ax)

    df = df.copy()
    df['score'] = calculate_composite_score(df)
    values = df['score'].values

    parts = ax.violinplot(values, positions=[0], showmeans=False,
                          showmedians=False, showextrema=False)
    style_violin(parts, CAT_PALETTE[4])

    bp = ax.boxplot(values, positions=[0], widths=0.15, patch_artist=True,
                    showfliers=False, zorder=2)
    style_box(bp)

    # Strip plot (jittered, colored by score)
    jitter = np.random.default_rng(42).uniform(-0.12, 0.12, len(values))
    scatter = ax.scatter(jitter, values, c=values, cmap='viridis',
                         s=DOT_SIZE, alpha=DOT_ALPHA, linewidths=0, zorder=3)

    cbar = plt.colorbar(scatter, ax=ax, shrink=0.85, aspect=22, pad=0.05)
    style_colorbar(cbar, 'Score')

    median = np.median(values)
    mean = np.mean(values)
    stat_box(ax, f'n={len(values)}\nmedian={median:.2f}\nmean={mean:.2f}')

    ax.set_title('Composite score distribution', fontsize=TITLE_FONTSIZE, pad=4)
    ax.set_ylabel('Composite score')
    ax.set_xlim(-0.5, 0.5)
    ax.set_xticks([])

    plt.tight_layout()

    if output_path:
        save_for_pub(fig, output_path)

    return fig


# ============================================================
# Figure 5: Metrics Table
# ============================================================

def plot_metrics_table(df: pd.DataFrame, output_path: str = None, top_n: int = 6):
    """Plot 5: Table showing top designs with pLDDT, iPTM, and composite score."""
    fig = plt.figure(figsize=TABLE_SIZE)
    ax = fig.add_subplot(111)
    ax.axis('off')
    ax.set_title('Top designs', fontsize=TITLE_FONTSIZE, pad=4)

    df = df.copy()
    df['score'] = calculate_composite_score(df)

    display_cols = ['design_id', 'pLDDT', 'iPTM', 'score']
    col_headers = ['Design', 'pLDDT', 'iPTM', 'Score']

    # Keep only available columns
    display_cols = [c for c in display_cols if c in df.columns or c == 'design_id']
    col_headers = [col_headers[i] for i, c in enumerate(['design_id', 'pLDDT', 'iPTM', 'score']) if c in df.columns or c == 'design_id']

    df_sorted = df.sort_values('score', ascending=False).head(top_n).reset_index(drop=True)

    n_rows = len(df_sorted) + 1  # +1 for header
    n_cols = len(display_cols)

    table = ax.table(
        cellText=[['']*n_cols for _ in range(n_rows)],
        loc='center',
        cellLoc='center',
        bbox=[0.05, 0.05, 0.90, 0.85]
    )
    # Size columns to content so long design IDs are not clipped.
    table.auto_set_column_width(col=list(range(n_cols)))

    # Style header
    for j, label in enumerate(col_headers):
        cell = table[(0, j)]
        cell.set_text_props(text=label, fontsize=BASE_FONTSIZE)
        cell.set_facecolor('white')

    # Fill data
    for i, (_, row) in enumerate(df_sorted.iterrows()):
        for j, col in enumerate(display_cols):
            cell = table[(i+1, j)]
            val = row[col]
            if col == 'design_id':
                text = simplify_design_id(val)
            elif col == 'pLDDT':
                text = f'{val:.2f}'
            elif col == 'iPTM':
                text = f'{val:.2f}'
            elif col == 'score':
                text = f'{val:.2f}'
            else:
                text = f'{val:.2f}'
            cell.set_text_props(text=text, fontsize=TABLE_FONTSIZE)

    # Academic three-line style: remove all cell borders, add alternating row shading
    table.auto_set_font_size(False)
    for (row_idx, col_idx), cell in table.get_celld().items():
        cell.set_edgecolor('white')
        cell.set_linewidth(0)
        cell.set_height(0.11)
        # Alternate row shading (data rows only)
        if row_idx > 0 and row_idx % 2 == 0:
            cell.set_facecolor('#F7F7F7')
        elif row_idx > 0:
            cell.set_facecolor('white')

    # Draw three horizontal lines: top, below header, bottom
    bbox = [0.05, 0.05, 0.90, 0.85]
    x_left = bbox[0]
    x_right = bbox[0] + bbox[2]
    y_bottom = bbox[1]
    y_top = bbox[1] + bbox[3]
    row_h = bbox[3] / n_rows
    y_header_bottom = y_top - row_h

    line_kwargs = dict(color='#333333', linewidth=RULE_LW,
                       transform=ax.transAxes, clip_on=False)
    ax.plot([x_left, x_right], [y_top, y_top], **line_kwargs)           # top line
    ax.plot([x_left, x_right], [y_header_bottom, y_header_bottom], **line_kwargs)  # below header
    ax.plot([x_left, x_right], [y_bottom, y_bottom], **line_kwargs)     # bottom line

    plt.tight_layout()

    if output_path:
        save_for_pub(fig, output_path)

    return fig


# ============================================================
# Figure 6: iPTM Scores
# ============================================================

def plot_iptm_comparison(df: pd.DataFrame, output_path: str = None):
    """Plot 6: Distribution of iPTM scores using violin + strip plot."""
    values = df['iPTM'].values
    return plot_violin_strip(
        values, 'iPTM distribution', 'iPTM (higher is better)',
        (QUALITY_THRESHOLDS['iptm_good'], QUALITY_THRESHOLDS['iptm_acceptable']),
        higher_is_better=True, palette_idx=0, output_path=output_path,
        legend_loc='lower right', ylim=(min(values) - 0.05, 1.05),
        threshold_labels=('Excellent iPTM', 'PASS gate iPTM'))


# ============================================================
# Separate figures entry point
# ============================================================

def create_separate_figures(results_dir: str, output_prefix: str = None):
    """Create 6 separate visualization figures for AfCycDesign pipeline.

    Args:
        results_dir: Path to results directory
        output_prefix: Path prefix for saving (without extension)

    Returns:
        list: Paths to saved figures
    """
    results_dir = Path(results_dir)

    if output_prefix is None:
        output_prefix = str(results_dir / "afcycdesign")

    set_pub_plot_context(context="talk")

    df = load_design_metrics(results_dir)
    if df.empty:
        print("Error: No design metrics found in", results_dir)
        return None

    saved_files = []

    # Figure 1: pLDDT comparison
    if 'pLDDT' in df.columns:
        fig1 = plot_plddt_comparison(df, f"{output_prefix}_plddt_scores")
        saved_files.append(f"{output_prefix}_plddt_scores.pdf")
        plt.close(fig1)

    # Figure 2: iPAE comparison (or loss if iPAE unavailable)
    if 'iPAE' in df.columns:
        fig2 = plot_ipae_comparison(df, f"{output_prefix}_ipae_comparison")
        saved_files.append(f"{output_prefix}_ipae_comparison.pdf")
        plt.close(fig2)
    elif 'loss' in df.columns:
        fig2 = plot_loss_comparison(df, f"{output_prefix}_loss_comparison")
        saved_files.append(f"{output_prefix}_loss_comparison.pdf")
        plt.close(fig2)

    # Figure 3: Quality scatter (supports iPAE or loss fallback)
    if 'pLDDT' in df.columns and ('iPAE' in df.columns or 'loss' in df.columns):
        fig3 = plot_quality_scatter(df, f"{output_prefix}_quality_scatter")
        saved_files.append(f"{output_prefix}_quality_scatter.pdf")
        plt.close(fig3)

    # Figure 4: Design ranking
    fig4 = plot_design_ranking(df, f"{output_prefix}_design_ranking")
    saved_files.append(f"{output_prefix}_design_ranking.pdf")
    plt.close(fig4)

    # Figure 5: Metrics table
    fig5 = plot_metrics_table(df, f"{output_prefix}_metrics_table")
    saved_files.append(f"{output_prefix}_metrics_table.pdf")
    plt.close(fig5)

    # Figure 6: iPTM comparison
    if 'iPTM' in df.columns:
        fig6 = plot_iptm_comparison(df, f"{output_prefix}_iptm_scores")
        saved_files.append(f"{output_prefix}_iptm_scores.pdf")
        plt.close(fig6)

    print(f"\nGenerated {len(saved_files)} separate figures:")
    for f in saved_files:
        print(f"  - {f}")

    return saved_files


# ============================================================
# Merged 2x3 figure
# ============================================================

def _plot_violin_strip_ax(ax, values, title, ylabel, thresholds, higher_is_better=True,
                          palette_idx=0):
    """Internal: Plot violin + strip distribution on given axis."""
    style_axis_vbar(ax)

    parts = ax.violinplot(values, positions=[0], showmeans=False,
                          showmedians=False, showextrema=False)
    style_violin(parts, CAT_PALETTE[palette_idx])

    bp = ax.boxplot(values, positions=[0], widths=0.15, patch_artist=True,
                    showfliers=False, zorder=2)
    style_box(bp)

    # Strip (jittered points)
    jitter = np.random.default_rng(42).uniform(-0.12, 0.12, len(values))
    colors = [get_color_for_value(v, thresholds[0], thresholds[1],
                                   higher_is_better=higher_is_better)
              for v in values]
    ax.scatter(jitter, values, c=colors, s=DOT_SIZE, alpha=DOT_ALPHA,
               linewidths=0, zorder=3)

    # Threshold lines: PASS gate solid, tighter excellent tier dashed.
    ax.axhline(y=thresholds[1], color=CAT_PALETTE[1], linestyle='-', alpha=0.9,
               linewidth=GATE_LW)
    ax.axhline(y=thresholds[0], color=CAT_PALETTE[2], linestyle='--', alpha=0.7,
               linewidth=CONTEXT_LW)

    # Stats
    median = np.median(values)
    mean = np.mean(values)
    stat_box(ax, f'n={len(values)}\nmed={median:.2f}\nmean={mean:.2f}')

    ax.set_title(title, fontsize=TITLE_FONTSIZE, pad=4)
    ax.set_ylabel(ylabel)
    ax.set_xlim(-0.5, 0.5)
    ax.set_xticks([])


def _plot_quality_scatter_ax(ax, df):
    """Internal: Plot quality scatter on given axis (supports loss fallback)."""
    scores = calculate_composite_score(df)

    if 'iPAE' in df.columns:
        y_metric, y_label, y_thresh = 'iPAE', 'iPAE', QUALITY_THRESHOLDS['ipae_good']
    elif 'loss' in df.columns:
        y_metric, y_label, y_thresh = 'loss', 'Loss', LOSS_THRESHOLDS['good']
    else:
        ax.text(0.5, 0.5, 'Scatter data\nnot available', ha='center', va='center',
                transform=ax.transAxes, fontsize=BASE_FONTSIZE)
        ax.axis('off')
        return

    style_axis_vbar(ax)
    scatter = ax.scatter(df['pLDDT'], df[y_metric], c=scores, cmap='viridis',
                        s=DOT_SIZE, alpha=DOT_ALPHA, linewidths=0)

    x_lo, x_hi = SCATTER_XLIM
    y_lo, y_hi = SCATTER_YLIM[y_metric]

    rect_good = Rectangle((QUALITY_THRESHOLDS['plddt_good'], y_lo),
                          x_hi - QUALITY_THRESHOLDS['plddt_good'],
                          y_thresh - y_lo,
                          linewidth=0, facecolor=CAT_PALETTE[2], alpha=0.10)
    ax.add_patch(rect_good)

    ax.axvline(x=QUALITY_THRESHOLDS['plddt_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.7, linewidth=CONTEXT_LW)
    ax.axhline(y=y_thresh, color=CAT_PALETTE[2],
               linestyle='--', alpha=0.7, linewidth=CONTEXT_LW)

    ax.set_title('Quality distribution', fontsize=TITLE_FONTSIZE, pad=4)
    ax.set_xlabel('pLDDT', fontsize=XLABEL_FONTSIZE)
    ax.set_ylabel(y_label)
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_lo, y_hi)
    annotate_offscale(ax, df['pLDDT'], df[y_metric],
                      SCATTER_XLIM, SCATTER_YLIM[y_metric])

    cbar = plt.colorbar(scatter, ax=ax, shrink=0.85, aspect=22, pad=0.03)
    style_colorbar(cbar, 'Score')


def _plot_metrics_table_ax(ax, df):
    """Internal: Plot top-6 metrics table with three-line academic style."""
    ax.axis('off')
    ax.set_title('Top designs', fontsize=TITLE_FONTSIZE, pad=4)

    df = df.copy()
    df['score'] = calculate_composite_score(df)

    display_cols = ['design_id', 'pLDDT', 'iPTM', 'score']
    col_headers = ['Design', 'pLDDT', 'iPTM', 'Score']
    display_cols = [c for c in display_cols if c in df.columns or c == 'design_id']
    col_headers = [col_headers[i] for i, c in enumerate(['design_id', 'pLDDT', 'iPTM', 'score'])
                   if c in df.columns or c == 'design_id']

    df_sorted = df.sort_values('score', ascending=False).head(6).reset_index(drop=True)

    n_rows = len(df_sorted) + 1
    n_cols = len(display_cols)

    table = ax.table(cellText=[['']*n_cols for _ in range(n_rows)],
                     loc='center', cellLoc='center', bbox=[0.0, 0.05, 1.0, 0.9])
    table.auto_set_column_width(col=list(range(n_cols)))

    for j, label in enumerate(col_headers):
        cell = table[(0, j)]
        cell.set_text_props(text=label, fontsize=BASE_FONTSIZE)
        cell.set_facecolor('white')

    for i, (_, row) in enumerate(df_sorted.iterrows()):
        for j, col in enumerate(display_cols):
            cell = table[(i+1, j)]
            val = row[col]
            if col == 'design_id':
                text = simplify_design_id(val)
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

    # Three-line style
    bbox = [0.0, 0.05, 1.0, 0.9]
    x_left, x_right = bbox[0], bbox[0] + bbox[2]
    y_bottom, y_top = bbox[1], bbox[1] + bbox[3]
    row_h = bbox[3] / n_rows
    y_header_bottom = y_top - row_h

    line_kw = dict(color='#333333', linewidth=RULE_LW, transform=ax.transAxes,
                   clip_on=False)
    ax.plot([x_left, x_right], [y_top, y_top], **line_kw)
    ax.plot([x_left, x_right], [y_header_bottom, y_header_bottom], **line_kw)
    ax.plot([x_left, x_right], [y_bottom, y_bottom], **line_kw)


def create_merged_figure(results_dir: str, output_prefix: str = None):
    """Create a single merged figure with all 6 panels in 2x3 grid.

    Layout:
        Row 1: pLDDT distribution, Loss/iPAE distribution, Quality scatter
        Row 2: Composite score distribution, Top designs table, iPTM distribution

    Args:
        results_dir: Path to results directory
        output_prefix: Path prefix for saving (without extension)

    Returns:
        str: Path to saved merged figure
    """
    results_dir = Path(results_dir)

    if output_prefix is None:
        output_prefix = str(results_dir / "afcycdesign_summary")

    set_pub_plot_context(context="talk")

    df = load_design_metrics(results_dir)
    if df.empty:
        print("Error: No design metrics found in", results_dir)
        return None

    fig = plt.figure(figsize=MERGED_2x3_SIZE)

    ax1 = fig.add_subplot(2, 3, 1)
    prettify_ax(ax1)
    ax2 = fig.add_subplot(2, 3, 2)
    prettify_ax(ax2)
    ax3 = fig.add_subplot(2, 3, 3)
    prettify_ax(ax3)
    ax4 = fig.add_subplot(2, 3, 4)
    prettify_ax(ax4)
    ax5 = fig.add_subplot(2, 3, 5)
    ax6 = fig.add_subplot(2, 3, 6)
    prettify_ax(ax6)

    # Panel 1: pLDDT distribution
    if 'pLDDT' in df.columns:
        _plot_violin_strip_ax(ax1, df['pLDDT'].values, 'pLDDT distribution',
                              'pLDDT (higher is better)',
                              [QUALITY_THRESHOLDS['plddt_good'],
                               QUALITY_THRESHOLDS['plddt_acceptable']],
                              higher_is_better=True)
        ax1.set_ylim(df['pLDDT'].min() - 0.05, 1.05)
    else:
        ax1.text(0.5, 0.5, 'pLDDT data\nnot available', ha='center', va='center',
                transform=ax1.transAxes, fontsize=BASE_FONTSIZE)
        ax1.axis('off')

    # Panel 2: Loss or iPAE distribution
    if 'iPAE' in df.columns:
        _plot_violin_strip_ax(ax2, df['iPAE'].values, 'iPAE distribution',
                              'iPAE (lower is better)',
                              [QUALITY_THRESHOLDS['ipae_good'],
                               QUALITY_THRESHOLDS['ipae_acceptable']],
                              higher_is_better=False)
    elif 'loss' in df.columns:
        _plot_violin_strip_ax(ax2, df['loss'].values, 'Loss distribution',
                              'Loss (lower is better)',
                              [2.0, 3.0], higher_is_better=False)
    else:
        ax2.text(0.5, 0.5, 'Loss/iPAE data\nnot available', ha='center', va='center',
                transform=ax2.transAxes, fontsize=BASE_FONTSIZE)
        ax2.axis('off')

    # Panel 3: Quality scatter
    if 'pLDDT' in df.columns and ('iPAE' in df.columns or 'loss' in df.columns):
        _plot_quality_scatter_ax(ax3, df)
    else:
        ax3.text(0.5, 0.5, 'Scatter data\nnot available', ha='center', va='center',
                transform=ax3.transAxes, fontsize=BASE_FONTSIZE)
        ax3.axis('off')

    # Panel 4: Composite score distribution
    scores = calculate_composite_score(df)
    _plot_violin_strip_ax(ax4, scores.values, 'Composite score',
                          'Score', [0.7, 0.5], higher_is_better=True,
                          palette_idx=4)

    # Panel 5: Top designs table
    _plot_metrics_table_ax(ax5, df)

    # Panel 6: iPTM distribution
    if 'iPTM' in df.columns:
        _plot_violin_strip_ax(ax6, df['iPTM'].values, 'iPTM distribution',
                              'iPTM (higher is better)',
                              [QUALITY_THRESHOLDS['iptm_good'],
                               QUALITY_THRESHOLDS['iptm_acceptable']],
                              higher_is_better=True)
        ax6.set_ylim(df['iPTM'].min() - 0.05, 1.05)
    else:
        ax6.text(0.5, 0.5, 'iPTM data\nnot available', ha='center', va='center',
                transform=ax6.transAxes, fontsize=BASE_FONTSIZE)
        ax6.axis('off')

    plt.tight_layout()

    save_for_pub(fig, output_prefix)
    plt.close(fig)

    print(f"\nSaved merged figure: {output_prefix}.pdf")
    return f"{output_prefix}.pdf"


# ============================================================
# Display results (notebook/GUI)
# ============================================================

def display_results(results_dir: str, show_all: bool = True, block: bool = True):
    """Report the AfCycDesign figures on disk and print a ranking summary.

    The figures are vector PDFs (no rasters are written), so this lists the
    files rather than compositing bitmaps. In a notebook the merged summary
    sheet is embedded inline when present.

    Args:
        results_dir: Path to results directory containing the generated figures
        show_all: If True, list all figures. If False, only the main metrics.
        block: Unused; kept for call-site compatibility.

    Returns:
        dict: Dictionary with figure paths for further reference
    """
    results_dir = Path(results_dir)

    # Check if we're in a notebook environment
    in_notebook = False
    try:
        from IPython import get_ipython
        ipython = get_ipython()
        if ipython is not None and 'IPKernelApp' in ipython.config:
            in_notebook = True
    except (ImportError, AttributeError):
        pass

    figures = {}
    figure_files = [
        ("plddt_scores", "pLDDT scores"),
        ("ipae_comparison", "Interface iPAE"),
        ("loss_comparison", "Loss distribution"),
        ("quality_scatter", "Quality distribution"),
        ("design_ranking", "Design ranking"),
        ("metrics_table", "Design metrics summary"),
        ("iptm_scores", "iPTM scores"),
    ]

    if not show_all:
        figure_files = figure_files[:3]

    print("\nFigures (PDF):")
    for fig_name, title in figure_files:
        pdf_path = results_dir / f"afcycdesign_{fig_name}.pdf"
        if pdf_path.exists():
            print(f"  {title}: {pdf_path}")
            figures[fig_name] = str(pdf_path)

    summary_pdf = results_dir / "afcycdesign_summary.pdf"
    if summary_pdf.exists():
        figures['summary'] = str(summary_pdf)
        print(f"  Merged summary: {summary_pdf}")
        if in_notebook:
            from IPython.display import IFrame, display
            display(IFrame(str(summary_pdf), width='100%', height=600))

    if not figures:
        print(f"  none found in {results_dir} — run create_separate_figures() first")

    # Print summary
    df = load_design_metrics(results_dir)
    if not df.empty:
        df['score'] = calculate_composite_score(df)
        df_sorted = df.sort_values('score', ascending=False)

        print("\n" + "="*60)
        print("AFCYCDESIGN PIPELINE SUMMARY")
        print("="*60)
        print(f"Total designs: {len(df)}")

        print(f"\nTop 3 designs by composite score:")
        for i, (_, row) in enumerate(df_sorted.head(3).iterrows()):
            name = simplify_design_id(row.get('design_id', f'd{i}'))
            plddt = row.get('pLDDT', float('nan'))
            ipae = row.get('iPAE', float('nan'))
            iptm = row.get('iPTM', float('nan'))
            print(f"  {i+1}. {name}: pLDDT={plddt:.2f}, iPAE={ipae:.3f}, "
                  f"iPTM={iptm:.2f}, score={row['score']:.2f}")
        print("="*60)

    return figures


# ============================================================
# CLI entry point
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='Generate AfCycDesign pipeline visualization figures')
    parser.add_argument('results_dir', type=str,
                        help='Path to results directory (containing afcycdesign_results.csv or *_afcyc.json files)')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='Output prefix (default: results_dir/afcycdesign)')
    parser.add_argument('--merged', '-m', action='store_true',
                        help='Create merged 2x3 summary figure instead of separate figures')

    args = parser.parse_args()

    if args.merged:
        output_file = create_merged_figure(args.results_dir, args.output)
        if output_file:
            print(f"\nVisualization complete: {output_file}")
        else:
            print("\nVisualization failed")
            exit(1)
    else:
        output_files = create_separate_figures(args.results_dir, args.output)
        if output_files:
            print(f"\nVisualization complete!")
        else:
            print("\nVisualization failed")
            exit(1)


if __name__ == '__main__':
    main()
