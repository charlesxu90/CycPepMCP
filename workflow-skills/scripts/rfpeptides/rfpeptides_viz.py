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

Each figure is saved as a separate PNG + PDF file.
A merged summary figure can also be generated.
"""

import argparse
import json
import os
import re
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
import seaborn as sns

# Color palettes
CAT_PALETTE = sns.color_palette('colorblind')
GRAY = [0.5, 0.5, 0.5]

# Figure size for individual plots
FIGSIZE = (5, 5)

# Quality thresholds — paper-faithful values from RFpeptides (Nat Chem Biol 2025).
# Paper Methods 2.4 + Supp. Fig. 4: iPAE / ddG cutoffs vary by target topology;
# CMS, SAP, pLDDT, RMSD are uniform across targets.
#
# Each entry below is annotated with (paper_value, label) so plots can show what
# the line means. `general` is the fallback when target cannot be auto-detected.
PAPER_THRESHOLDS = {
    'mcl1': {
        'ipae':  (0.30, 'Paper iPAE<0.30 (MCL1, concave pocket)'),
        'ddg':   (-30, 'Paper ddG<-30 REU'),
        'sap':   (35,  'Paper SAP<35'),
        'cms':   (300, 'Paper CMS>300 Å²'),
        'plddt': (0.70, 'Paper pLDDT>0.70'),
    },
    'mdm2': {
        'ipae':  (0.30, 'Paper iPAE<0.30 (MDM2, concave pocket)'),
        'ddg':   (-50, 'Paper ddG<-50 REU (MDM2-specific)'),
        'sap':   (35,  'Paper SAP<35'),
        'cms':   (300, 'Paper CMS>300 Å²'),
        'plddt': (0.70, 'Paper pLDDT>0.70'),
    },
    'gabarap': {
        'ipae':  (0.13, 'Paper iPAE<0.13 (GABARAP, shallow groove)'),
        'ddg':   (-30, 'Paper ddG<-30 REU'),
        'sap':   (35,  'Paper SAP<35'),
        'cms':   (300, 'Paper CMS>300 Å²'),
        'plddt': (0.70, 'Paper pLDDT>0.70'),
    },
    'rbta': {
        'ipae':  (0.40, 'Paper iPAE<0.40 (RbtA, flat β-helix)'),
        'ddg':   (-30, 'Paper ddG<-30 REU'),
        'sap':   (35,  'Paper SAP<35'),
        'cms':   (300, 'Paper CMS>300 Å²'),
        'plddt': (0.70, 'Paper pLDDT>0.70'),
    },
    'general': {
        'ipae':  (0.30, 'Paper iPAE<0.30 (concave default)'),
        'ddg':   (-30, 'Paper ddG<-30 REU'),
        'sap':   (35,  'Paper SAP<35'),
        'cms':   (300, 'Paper CMS>300 Å²'),
        'plddt': (0.70, 'Paper pLDDT>0.70'),
    },
}

# Active thresholds (set by configure_thresholds() based on detected target).
QUALITY_THRESHOLDS = {
    'ddg_good': -50,         # tighter "excellent" line, for context
    'ddg_acceptable': -30,   # paper threshold (will be overwritten)
    'ipae_good': 0.15,
    'ipae_acceptable': 0.30,
    'plddt_good': 0.90,
    'plddt_acceptable': 0.70,
    'sap_good': 25,
    'sap_acceptable': 35,
    'cms_good': 400,
    'cms_acceptable': 300,
}

# Active threshold labels, populated by configure_thresholds().
THRESHOLD_LABELS = {
    'ipae': 'Paper threshold',
    'ddg':  'Paper threshold',
    'sap':  'Paper threshold',
    'cms':  'Paper threshold',
    'plddt':'Paper threshold',
}


def detect_target(results_dir) -> str:
    """Infer target name (mcl1/mdm2/gabarap/rbta) from the results path."""
    path = str(results_dir).lower()
    for key in ('mcl1', 'mdm2', 'gabarap', 'rbta'):
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


def prettify_ax(ax):
    """Make axes more pleasant to look at."""
    for i, spine in enumerate(ax.spines.values()):
        if i == 3 or i == 1:
            spine.set_visible(False)
    ax.set_frameon = True
    ax.tick_params(direction='out', length=3, color='k')
    ax.set_axisbelow(True)


def simple_ax(figsize=FIGSIZE, **kwargs):
    """Shortcut to make and 'prettify' a simple figure with 1 axis."""
    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(111, **kwargs)
    prettify_ax(ax)
    return fig, ax


def set_pub_plot_context(context="talk"):
    """Set publication-quality plot context."""
    sns.set(style="white", context=context)


def save_for_pub(fig, path, dpi=300, include_raster=True):
    """Save figure in publication-ready formats."""
    fig.savefig(path + ".pdf", dpi=dpi, bbox_inches='tight', transparent=True)
    if include_raster:
        fig.savefig(path + ".png", dpi=dpi, bbox_inches='tight', transparent=True)


def get_color_for_value(value, threshold_good, threshold_acceptable, higher_is_better=True):
    """Get color based on quality thresholds."""
    if higher_is_better:
        if value >= threshold_good:
            return CAT_PALETTE[2]
        elif value >= threshold_acceptable:
            return CAT_PALETTE[1]
        else:
            return CAT_PALETTE[3]
    else:
        if value <= threshold_good:
            return CAT_PALETTE[2]
        elif value <= threshold_acceptable:
            return CAT_PALETTE[1]
        else:
            return CAT_PALETTE[3]


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

    parts = ax.violinplot(values, positions=[0], showmeans=False,
                          showmedians=False, showextrema=False)
    for pc in parts['bodies']:
        pc.set_facecolor(CAT_PALETTE[palette_idx])
        pc.set_alpha(0.2)

    bp = ax.boxplot(values, positions=[0], widths=0.15, patch_artist=True,
                    showfliers=False, zorder=2)
    bp['boxes'][0].set_facecolor('white')
    bp['boxes'][0].set_alpha(0.8)
    bp['medians'][0].set_color('black')
    bp['medians'][0].set_linewidth(1.5)

    jitter = np.random.default_rng(42).uniform(-0.12, 0.12, len(values))
    colors = [get_color_for_value(v, thresholds[0], thresholds[1],
                                   higher_is_better=higher_is_better)
              for v in values]
    ax.scatter(jitter, values, c=colors, s=40, alpha=0.7, edgecolors='white',
               linewidth=0.5, zorder=3)

    # Paper-aligned cutoff (solid, prominent); excellent context line (dashed, faint).
    ax.axhline(y=thresholds[1], color=CAT_PALETTE[1], linestyle='-', alpha=0.85,
               linewidth=1.4, label=f"{threshold_labels[1]} ({thresholds[1]:g})")
    ax.axhline(y=thresholds[0], color=CAT_PALETTE[2], linestyle='--', alpha=0.55,
               linewidth=1.0, label=f"{threshold_labels[0]} ({thresholds[0]:g})")
    ax.legend(loc='lower left', fontsize=7, frameon=True, framealpha=0.9)

    median = np.median(values)
    mean = np.mean(values)
    ax.text(0.95, 0.97, f'n={len(values)}\nmedian={median:.2f}\nmean={mean:.2f}',
            transform=ax.transAxes, fontsize=9, va='top', ha='right',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    ax.set_title(title, fontsize=14, fontweight='bold', pad=12)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_xlim(-0.5, 0.5)
    ax.set_xticks([])
    ax.yaxis.grid(True, linestyle='--', alpha=0.4)

    plt.tight_layout()
    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")
    return fig


def _plot_violin_strip_ax(ax, values, title, ylabel, thresholds, higher_is_better=True,
                           palette_idx=0,
                           threshold_labels=('Excellent', 'Paper threshold')):
    """Internal: Plot violin + strip distribution on a given axis (for merged figure)."""
    parts = ax.violinplot(values, positions=[0], showmeans=False,
                          showmedians=False, showextrema=False)
    for pc in parts['bodies']:
        pc.set_facecolor(CAT_PALETTE[palette_idx])
        pc.set_alpha(0.2)

    bp = ax.boxplot(values, positions=[0], widths=0.15, patch_artist=True,
                    showfliers=False, zorder=2)
    bp['boxes'][0].set_facecolor('white')
    bp['boxes'][0].set_alpha(0.8)
    bp['medians'][0].set_color('black')
    bp['medians'][0].set_linewidth(1.5)

    jitter = np.random.default_rng(42).uniform(-0.12, 0.12, len(values))
    colors = [get_color_for_value(v, thresholds[0], thresholds[1],
                                   higher_is_better=higher_is_better)
              for v in values]
    ax.scatter(jitter, values, c=colors, s=30, alpha=0.7, edgecolors='white',
               linewidth=0.4, zorder=3)

    ax.axhline(y=thresholds[1], color=CAT_PALETTE[1], linestyle='-', alpha=0.85,
               linewidth=1.2, label=f"{threshold_labels[1]} ({thresholds[1]:g})")
    ax.axhline(y=thresholds[0], color=CAT_PALETTE[2], linestyle='--', alpha=0.55,
               linewidth=0.9, label=f"{threshold_labels[0]} ({thresholds[0]:g})")
    ax.legend(loc='lower left', fontsize=6, frameon=True, framealpha=0.9)

    median = np.median(values)
    mean = np.mean(values)
    ax.text(0.95, 0.97, f'n={len(values)}\nmed={median:.2f}\nmean={mean:.2f}',
            transform=ax.transAxes, fontsize=7, va='top', ha='right',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8))

    ax.set_title(title, fontsize=10, fontweight='bold', pad=8)
    ax.set_ylabel(ylabel, fontsize=8)
    ax.set_xlim(-0.5, 0.5)
    ax.set_xticks([])
    ax.yaxis.grid(True, linestyle='--', alpha=0.4)


# ============================================================
# Individual figure functions
# ============================================================

def plot_ddg_distribution(df, output_path=None):
    """Plot 1: ddG distribution."""
    return plot_violin_strip(
        df['ddg'].values, 'Binding Energy (ddG)',
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
        values, 'pLDDT Distribution',
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
        values, 'Aggregation Propensity (SAP)',
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
        values, 'Contact Molecular Surface (CMS)',
        'CMS (\u00c5\u00b2, higher is better)',
        (QUALITY_THRESHOLDS['cms_good'], QUALITY_THRESHOLDS['cms_acceptable']),
        higher_is_better=True, palette_idx=4, output_path=output_path,
        threshold_labels=('Excellent CMS', THRESHOLD_LABELS['cms']))


def plot_quality_scatter(df, output_path=None):
    """Plot 6: Scatter plot of ddG vs iPAE colored by composite score."""
    if 'iPAE' not in df.columns:
        return None
    fig, ax = simple_ax(figsize=(6, 5))
    scores = calculate_composite_score(df)

    scatter = ax.scatter(df['ddg'], df['iPAE'], c=scores, cmap='viridis',
                        s=80, alpha=0.8, edgecolors='white', linewidth=0.5)

    # Shaded region = passes BOTH paper-aligned cutoffs (ddG and iPAE).
    ddg_min = min(df['ddg'].min() * 1.1, -80)
    ddg_cut = QUALITY_THRESHOLDS['ddg_acceptable']
    ipae_cut = QUALITY_THRESHOLDS['ipae_acceptable']
    rect_good = Rectangle((ddg_min, 0),
                          ddg_cut - ddg_min, ipae_cut,
                          linewidth=0, facecolor=CAT_PALETTE[2], alpha=0.12)
    ax.add_patch(rect_good)

    ax.axvline(x=ddg_cut, color=CAT_PALETTE[2], linestyle='-', alpha=0.85,
               linewidth=1.4, label=f"{THRESHOLD_LABELS['ddg']} ({ddg_cut:g})")
    ax.axhline(y=ipae_cut, color=CAT_PALETTE[1], linestyle='-', alpha=0.85,
               linewidth=1.4, label=f"{THRESHOLD_LABELS['ipae']} ({ipae_cut:g})")
    ax.legend(loc='upper right', fontsize=7, frameon=True, framealpha=0.9)

    ax.set_title('ddG vs iPAE', fontsize=14, fontweight='bold', pad=12)
    ax.set_xlabel('ddG (REU, more negative = better)', fontsize=11)
    ax.set_ylabel('iPAE (lower is better)', fontsize=11)

    cbar = plt.colorbar(scatter, ax=ax, shrink=0.8)
    cbar.set_label('Composite Score', fontsize=10)

    plt.tight_layout()
    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")
    return fig


def plot_composite_distribution(df, output_path=None):
    """Plot 7: Composite score distribution."""
    scores = calculate_composite_score(df).values
    fig = plot_violin_strip(
        scores, 'Composite Score Distribution',
        'Score', (0.7, 0.5),
        higher_is_better=True, palette_idx=4, output_path=output_path)
    ax = fig.axes[0]
    # Replace with viridis-colored points
    for coll in list(ax.collections):
        if hasattr(coll, 'get_offsets') and len(coll.get_offsets()) == len(scores):
            coll.remove()
            break
    jitter = np.random.default_rng(42).uniform(-0.12, 0.12, len(scores))
    ax.scatter(jitter, scores, c=scores, cmap='viridis', s=40, alpha=0.7,
               edgecolors='white', linewidth=0.5, zorder=3)
    if output_path:
        save_for_pub(fig, output_path)
    return fig


def plot_metrics_table(df, output_path=None, top_n=6):
    """Plot 8: Top designs table with three-line academic style."""
    fig = plt.figure(figsize=(6, 4))
    ax = fig.add_subplot(111)
    ax.axis('off')
    ax.set_title('Top Designs', fontsize=14, fontweight='bold', pad=12)

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

    table = ax.table(cellText=[['']*n_cols for _ in range(n_rows)],
                     loc='center', cellLoc='center', bbox=[0.02, 0.05, 0.96, 0.85])

    for j, (col, header) in enumerate(col_defs):
        cell = table[(0, j)]
        cell.set_text_props(text=header, fontweight='bold', fontsize=9)
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
            cell.set_text_props(text=text, fontsize=8)

    # Three-line style with alternating row shading
    table.auto_set_font_size(False)
    for (row_idx, col_idx), cell in table.get_celld().items():
        cell.set_edgecolor('white')
        cell.set_linewidth(0)
        cell.set_height(0.11)
        if row_idx > 0 and row_idx % 2 == 0:
            cell.set_facecolor('#F5F5F5')
        elif row_idx > 0:
            cell.set_facecolor('white')

    bbox = [0.02, 0.05, 0.96, 0.85]
    x_left, x_right = bbox[0], bbox[0] + bbox[2]
    y_bottom, y_top = bbox[1], bbox[1] + bbox[3]
    row_h = bbox[3] / n_rows
    y_header_bottom = y_top - row_h

    line_kwargs = dict(color='black', linewidth=1.2, transform=ax.transAxes, clip_on=False)
    ax.plot([x_left, x_right], [y_top, y_top], **line_kwargs)
    ax.plot([x_left, x_right], [y_header_bottom, y_header_bottom], **line_kwargs)
    ax.plot([x_left, x_right], [y_bottom, y_bottom], **line_kwargs)

    plt.tight_layout()
    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")
    return fig


# ============================================================
# Timeline
# ============================================================

def parse_pipeline_log(log_path: Path) -> list:
    """Parse pipeline.log to extract stage start times and durations."""
    if not log_path.exists():
        return None
    stage_times = {}
    time_pattern = re.compile(r'^\[(\d{2}:\d{2}:\d{2})\]\s+(.*)$')
    with open(log_path) as f:
        lines = f.readlines()
    first_time = prev_time = None
    for line in lines:
        m = time_pattern.match(line.strip())
        if not m:
            continue
        time_str, content = m.groups()
        t = datetime.strptime(time_str, '%H:%M:%S')
        if prev_time and t < prev_time:
            t = t.replace(day=2)
        if first_time is None:
            first_time = t
        prev_time = t
        stage_match = re.match(r'STAGE\s+(\d+):', content)
        if stage_match:
            stage_times[int(stage_match.group(1))] = {'start': t}
    if not stage_times or first_time is None:
        return None
    sorted_stages = sorted(stage_times.keys())
    steps = []
    for i, sn in enumerate(sorted_stages):
        start = stage_times[sn]['start']
        end = stage_times[sorted_stages[i+1]]['start'] if i+1 < len(sorted_stages) else prev_time
        start_min = (start - first_time).total_seconds() / 60
        duration = max((end - start).total_seconds() / 60, 0.5)
        idx = sn - 1
        name = PIPELINE_STAGES[idx] if idx < len(PIPELINE_STAGES) else f'Stage {sn}'
        steps.append({'name': name, 'start': round(start_min, 1), 'duration': round(duration, 1)})
    return steps if steps else None


def plot_execution_timeline(results_dir, output_path=None):
    """Plot 9: Gantt chart of pipeline stages."""
    fig, ax = simple_ax(figsize=FIGSIZE)
    ax.set_title('Execution Timeline', fontsize=14, fontweight='bold', pad=12)

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
        ax.barh(y_pos, step['duration'], left=step['start'], height=0.6,
                color=colors[i], edgecolor='white', linewidth=0.5)
        ax.text(-0.5, y_pos, step['name'], ha='right', va='center', fontsize=8)

    total_label = f"Total: ~{total_time/60:.1f} hours" if total_time >= 60 else f"Total: ~{int(total_time)} min"
    ax.barh(-1, total_time, left=0, height=0.6, color=GRAY, alpha=0.8)
    ax.text(-0.5, -1, total_label, ha='right', va='center', fontsize=8, fontweight='bold')

    ax.set_xlabel('Time (minutes)', fontsize=11)
    ax.set_xlim(-1, total_time * 1.1)
    ax.set_ylim(-2, len(steps))
    ax.set_yticks([])
    ax.xaxis.grid(True, linestyle='--', alpha=0.4)
    ax.spines['left'].set_visible(False)

    plt.tight_layout()
    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")
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
            saved_files.append(f"{output_prefix}_{name}.png")
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

    fig = plt.figure(figsize=(15, 13))
    axes = [fig.add_subplot(3, 3, i+1) for i in range(9)]
    for ax in axes:
        prettify_ax(ax)

    # Row 1
    _plot_violin_strip_ax(axes[0], df['ddg'].values, 'ddG Distribution',
                          'ddG (REU)',
                          (QUALITY_THRESHOLDS['ddg_good'], QUALITY_THRESHOLDS['ddg_acceptable']),
                          higher_is_better=False, palette_idx=0,
                          threshold_labels=('Excellent ddG', THRESHOLD_LABELS['ddg']))

    if 'iPAE' in df.columns:
        _plot_violin_strip_ax(axes[1], df['iPAE'].dropna().values, 'iPAE Distribution',
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
        scatter = axes[2].scatter(df['ddg'], df['iPAE'], c=scores, cmap='viridis',
                                  s=40, alpha=0.8, edgecolors='white', linewidth=0.4)
        ddg_cut = QUALITY_THRESHOLDS['ddg_acceptable']
        ipae_cut = QUALITY_THRESHOLDS['ipae_acceptable']
        axes[2].axvline(x=ddg_cut, color=CAT_PALETTE[2], linestyle='-', alpha=0.85,
                        linewidth=1.2, label=f"ddG<{ddg_cut:g}")
        axes[2].axhline(y=ipae_cut, color=CAT_PALETTE[1], linestyle='-', alpha=0.85,
                        linewidth=1.2, label=f"iPAE<{ipae_cut:g}")
        axes[2].legend(loc='upper right', fontsize=6, frameon=True, framealpha=0.9)
        axes[2].set_title('ddG vs iPAE (paper cutoffs)', fontsize=10, fontweight='bold', pad=8)
        axes[2].set_xlabel('ddG', fontsize=8)
        axes[2].set_ylabel('iPAE', fontsize=8)
        plt.colorbar(scatter, ax=axes[2], shrink=0.8, label='Score')
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
    _plot_violin_strip_ax(axes[6], scores.values, 'Composite Score', 'Score',
                          (0.7, 0.5), higher_is_better=True, palette_idx=4)

    # Table (three-line style)
    axes[7].axis('off')
    axes[7].set_title('Top Designs', fontsize=10, fontweight='bold', pad=8)
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
    for j, (col, header) in enumerate(col_defs):
        cell = table[(0, j)]
        cell.set_text_props(text=header, fontweight='bold', fontsize=8)
        cell.set_facecolor('white')
    for i, (_, row) in enumerate(df_top.iterrows()):
        for j, (col, h) in enumerate(col_defs):
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
            else:
                text = f'{val:.2f}'
            cell.set_text_props(text=text, fontsize=7)
    table.auto_set_font_size(False)
    for (row_idx, col_idx), cell in table.get_celld().items():
        cell.set_edgecolor('white')
        cell.set_linewidth(0)
        cell.set_height(0.11)
        if row_idx > 0 and row_idx % 2 == 0:
            cell.set_facecolor('#F5F5F5')
        elif row_idx > 0:
            cell.set_facecolor('white')
    bbox_t = [0.0, 0.05, 1.0, 0.9]
    xl, xr = bbox_t[0], bbox_t[0] + bbox_t[2]
    yb, yt = bbox_t[1], bbox_t[1] + bbox_t[3]
    rh = bbox_t[3] / n_rows
    lkw = dict(color='black', linewidth=1.0, transform=axes[7].transAxes, clip_on=False)
    axes[7].plot([xl, xr], [yt, yt], **lkw)
    axes[7].plot([xl, xr], [yt - rh, yt - rh], **lkw)
    axes[7].plot([xl, xr], [yb, yb], **lkw)

    # Timeline
    axes[8].set_title('Timeline', fontsize=10, fontweight='bold', pad=8)
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
        axes[8].barh(yp, step['duration'], left=step['start'], height=0.6,
                     color=colors_t[i], edgecolor='white', linewidth=0.5)
        axes[8].text(-0.5, yp, step['name'], ha='right', va='center', fontsize=7)
    axes[8].barh(-1, total_time, left=0, height=0.6, color=GRAY, alpha=0.8)
    tl = f"~{total_time/60:.1f}h" if total_time >= 60 else f"~{int(total_time)}m"
    axes[8].text(-0.5, -1, tl, ha='right', va='center', fontsize=7, fontweight='bold')
    axes[8].set_xlabel('Time (min)', fontsize=8)
    axes[8].set_xlim(-1, total_time * 1.1)
    axes[8].set_ylim(-2, len(steps))
    axes[8].set_yticks([])
    axes[8].xaxis.grid(True, linestyle='--', alpha=0.4)
    axes[8].spines['left'].set_visible(False)

    plt.tight_layout()
    save_for_pub(fig, output_prefix, include_raster=True)
    plt.close(fig)
    print(f"\nSaved merged figure: {output_prefix}.png, {output_prefix}.pdf")
    return f"{output_prefix}.png"


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
