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

Each figure is saved as a separate 4x4 inch file.
A merged 2x3 summary figure can also be generated.
"""

import argparse
import json
import os
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
DIV_PALETTE = sns.color_palette("BrBG_r", 100)
SEQ_PALETTE = sns.cubehelix_palette(100, start=0.5, rot=-0.75)
GRAY = [0.5, 0.5, 0.5]

# Figure size for individual plots
FIGSIZE = (4, 4)

# Adaptive figure size based on number of designs
def adaptive_figsize(n_designs, base=(4, 4)):
    """Return a figure size that scales with number of designs."""
    if n_designs <= 10:
        return base
    w = max(base[0], n_designs * 0.28)
    h = max(base[1], 5)
    return (w, h)

# Quality thresholds for AfCycDesign pipeline
QUALITY_THRESHOLDS = {
    'plddt_good': 0.70,
    'plddt_acceptable': 0.50,
    'ipae_good': 0.15,
    'ipae_acceptable': 0.20,
    'iptm_good': 0.60,
    'iptm_acceptable': 0.40,
    'ptm_good': 0.80,
    'ptm_acceptable': 0.60,
}


def prettify_ax(ax):
    """Make axes more pleasant to look at."""
    for i, spine in enumerate(ax.spines.values()):
        if i == 3 or i == 1:  # top and right
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
            return CAT_PALETTE[2]  # Green
        elif value >= threshold_acceptable:
            return CAT_PALETTE[1]  # Orange
        else:
            return CAT_PALETTE[3]  # Red
    else:
        if value <= threshold_good:
            return CAT_PALETTE[2]  # Green
        elif value <= threshold_acceptable:
            return CAT_PALETTE[1]  # Orange
        else:
            return CAT_PALETTE[3]  # Red


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

    Score = 0.30 * pLDDT + 0.30 * iPAE_inv + 0.25 * iPTM + 0.15 * pTM

    All normalized 0-1; iPAE inverted since lower=better.
    """
    scores = pd.DataFrame(index=df.index)

    # pLDDT: higher is better (0-1 scale)
    if 'pLDDT' in df.columns:
        scores['pLDDT'] = df['pLDDT'].clip(0, 1)

    # iPAE: lower is better. Normalize: 0 to 0.5 range
    if 'iPAE' in df.columns:
        scores['iPAE'] = (1 - (df['iPAE'] / 0.5).clip(0, 1))
    elif 'loss' in df.columns:
        # Fallback: use loss as proxy for iPAE (normalize: 0-5 range)
        scores['iPAE'] = (1 - (df['loss'] / 5.0).clip(0, 1))

    # iPTM: higher is better (0-1 scale)
    if 'iPTM' in df.columns:
        scores['iPTM'] = df['iPTM'].clip(0, 1)

    # pTM: higher is better (0-1 scale)
    if 'pTM' in df.columns:
        scores['pTM'] = df['pTM'].clip(0, 1)

    weights = {'pLDDT': 0.30, 'iPAE': 0.30, 'iPTM': 0.25, 'pTM': 0.15}

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
# Figure 1: pLDDT Scores
# ============================================================

def plot_plddt_comparison(df: pd.DataFrame, output_path: str = None):
    """Plot 1: Distribution of pLDDT scores using violin + strip plot."""
    fig, ax = simple_ax(figsize=(5, 5))

    values = df['pLDDT'].values

    # Violin plot for density
    parts = ax.violinplot(values, positions=[0], showmeans=False,
                          showmedians=False, showextrema=False)
    for pc in parts['bodies']:
        pc.set_facecolor(CAT_PALETTE[0])
        pc.set_alpha(0.2)

    # Box plot overlay (thin)
    bp = ax.boxplot(values, positions=[0], widths=0.15, patch_artist=True,
                    showfliers=False, zorder=2)
    bp['boxes'][0].set_facecolor('white')
    bp['boxes'][0].set_alpha(0.8)
    bp['medians'][0].set_color('black')
    bp['medians'][0].set_linewidth(1.5)

    # Strip plot (jittered individual points)
    jitter = np.random.default_rng(42).uniform(-0.12, 0.12, len(values))
    colors = [get_color_for_value(v, QUALITY_THRESHOLDS['plddt_good'],
                                   QUALITY_THRESHOLDS['plddt_acceptable'],
                                   higher_is_better=True)
              for v in values]
    ax.scatter(jitter, values, c=colors, s=40, alpha=0.7, edgecolors='white',
               linewidth=0.5, zorder=3)

    # Threshold lines
    ax.axhline(y=QUALITY_THRESHOLDS['plddt_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.7, linewidth=1,
               label=f"Good (>{QUALITY_THRESHOLDS['plddt_good']})")
    ax.axhline(y=QUALITY_THRESHOLDS['plddt_acceptable'], color=CAT_PALETTE[1],
               linestyle='--', alpha=0.7, linewidth=1,
               label=f"Acceptable (>{QUALITY_THRESHOLDS['plddt_acceptable']})")

    # Summary stats annotation
    median = np.median(values)
    mean = np.mean(values)
    ax.text(0.95, 0.97, f'n={len(values)}\nmedian={median:.2f}\nmean={mean:.2f}',
            transform=ax.transAxes, fontsize=9, va='top', ha='right',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    ax.set_title('pLDDT Distribution', fontsize=14, fontweight='bold', pad=12)
    ax.set_ylabel('pLDDT (higher is better)', fontsize=11)
    ax.set_xlim(-0.5, 0.5)
    ax.set_xticks([])
    ax.set_ylim(min(values) - 0.05, 1.05)
    ax.yaxis.grid(True, linestyle='--', alpha=0.4)
    ax.legend(loc='lower right', fontsize=9)

    plt.tight_layout()

    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")

    return fig


# ============================================================
# Figure 2: Interface iPAE
# ============================================================

def plot_ipae_comparison(df: pd.DataFrame, output_path: str = None):
    """Plot 2: Bar chart of iPAE scores sorted ascending (lower = better)."""
    n_designs = len(df)
    figsize = adaptive_figsize(n_designs)
    fig, ax = simple_ax(figsize=figsize)

    df_sorted = df.sort_values('iPAE', ascending=True).reset_index(drop=True)
    x_pos = np.arange(n_designs)

    colors = [get_color_for_value(v, QUALITY_THRESHOLDS['ipae_good'],
                                   QUALITY_THRESHOLDS['ipae_acceptable'],
                                   higher_is_better=False)
              for v in df_sorted['iPAE']]

    ax.bar(x_pos, df_sorted['iPAE'], color=colors, alpha=0.9, width=0.8)

    ax.axhline(y=QUALITY_THRESHOLDS['ipae_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.7, linewidth=1,
               label=f"Good (<{QUALITY_THRESHOLDS['ipae_good']})")
    ax.axhline(y=QUALITY_THRESHOLDS['ipae_acceptable'], color=CAT_PALETTE[1],
               linestyle='--', alpha=0.7, linewidth=1,
               label=f"Acceptable (<{QUALITY_THRESHOLDS['ipae_acceptable']})")

    ax.set_title('Interface iPAE', fontsize=14, fontweight='bold', pad=12)
    ax.set_ylabel('iPAE (lower is better)', fontsize=11)
    ax.set_xlabel('Design', fontsize=11)
    ax.set_xticks(x_pos)

    labels = [simplify_design_id(name) for name in df_sorted['design_id']]
    tick_fontsize = max(5, min(8, 200 // n_designs))
    ax.set_xticklabels(labels, fontsize=tick_fontsize, rotation=90, ha='center')

    ax.yaxis.grid(True, linestyle='--', alpha=0.4)
    ax.legend(loc='upper right', fontsize=9)

    plt.tight_layout()

    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")

    return fig


# ============================================================
# Figure 2b: Loss Scores (fallback when iPAE is unavailable)
# ============================================================

def plot_loss_comparison(df: pd.DataFrame, output_path: str = None):
    """Plot 2b: Distribution of loss scores using violin + strip plot."""
    fig, ax = simple_ax(figsize=(5, 5))

    values = df['loss'].values

    # Violin plot for density
    parts = ax.violinplot(values, positions=[0], showmeans=False,
                          showmedians=False, showextrema=False)
    for pc in parts['bodies']:
        pc.set_facecolor(CAT_PALETTE[0])
        pc.set_alpha(0.2)

    # Box plot overlay
    bp = ax.boxplot(values, positions=[0], widths=0.15, patch_artist=True,
                    showfliers=False, zorder=2)
    bp['boxes'][0].set_facecolor('white')
    bp['boxes'][0].set_alpha(0.8)
    bp['medians'][0].set_color('black')
    bp['medians'][0].set_linewidth(1.5)

    # Strip plot (jittered individual points)
    jitter = np.random.default_rng(42).uniform(-0.12, 0.12, len(values))
    colors = [get_color_for_value(v, 2.0, 3.0, higher_is_better=False)
              for v in values]
    ax.scatter(jitter, values, c=colors, s=40, alpha=0.7, edgecolors='white',
               linewidth=0.5, zorder=3)

    # Threshold lines
    ax.axhline(y=2.0, color=CAT_PALETTE[2],
               linestyle='--', alpha=0.7, linewidth=1,
               label='Good (<2.0)')
    ax.axhline(y=3.0, color=CAT_PALETTE[1],
               linestyle='--', alpha=0.7, linewidth=1,
               label='Acceptable (<3.0)')

    # Summary stats
    median = np.median(values)
    mean = np.mean(values)
    ax.text(0.95, 0.97, f'n={len(values)}\nmedian={median:.2f}\nmean={mean:.2f}',
            transform=ax.transAxes, fontsize=9, va='top', ha='right',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    ax.set_title('Loss Distribution', fontsize=14, fontweight='bold', pad=12)
    ax.set_ylabel('Loss (lower is better)', fontsize=11)
    ax.set_xlim(-0.5, 0.5)
    ax.set_xticks([])
    ax.yaxis.grid(True, linestyle='--', alpha=0.4)
    ax.legend(loc='upper right', fontsize=9)

    plt.tight_layout()

    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")

    return fig


# ============================================================
# Figure 3: Quality Scatter (pLDDT vs iPAE)
# ============================================================

def plot_quality_scatter(df: pd.DataFrame, output_path: str = None):
    """Plot 3: Scatter plot of pLDDT vs iPAE (or loss) colored by composite score."""
    fig, ax = simple_ax(figsize=(6, 5))

    scores = calculate_composite_score(df)

    # Determine y-axis metric: prefer iPAE, fall back to loss
    if 'iPAE' in df.columns:
        y_metric = 'iPAE'
        y_label = 'iPAE (lower is better)'
        y_thresh_good = QUALITY_THRESHOLDS['ipae_good']
    elif 'loss' in df.columns:
        y_metric = 'loss'
        y_label = 'Loss (lower is better)'
        y_thresh_good = 2.0
    else:
        y_metric = None

    if y_metric is None:
        ax.text(0.5, 0.5, 'Scatter data\nnot available', ha='center', va='center',
                transform=ax.transAxes, fontsize=12)
        ax.axis('off')
    else:
        scatter = ax.scatter(df['pLDDT'], df[y_metric], c=scores, cmap='viridis',
                            s=80, alpha=0.8, edgecolors='white', linewidth=0.5)

        # Good zone
        y_min = df[y_metric].min() * 0.95
        rect_good = Rectangle((QUALITY_THRESHOLDS['plddt_good'], y_min),
                              1.0 - QUALITY_THRESHOLDS['plddt_good'],
                              y_thresh_good - y_min,
                              linewidth=0, facecolor=CAT_PALETTE[2], alpha=0.1)
        ax.add_patch(rect_good)

        ax.axvline(x=QUALITY_THRESHOLDS['plddt_good'], color=CAT_PALETTE[2],
                   linestyle='--', alpha=0.5, linewidth=1)
        ax.axhline(y=y_thresh_good, color=CAT_PALETTE[2],
                   linestyle='--', alpha=0.5, linewidth=1)

        ax.set_title('Quality Distribution', fontsize=14, fontweight='bold', pad=12)
        ax.set_xlabel('pLDDT (higher is better)', fontsize=11)
        ax.set_ylabel(y_label, fontsize=11)

        cbar = plt.colorbar(scatter, ax=ax, shrink=0.8)
        cbar.set_label('Composite Score', fontsize=10)

        ax.text(QUALITY_THRESHOLDS['plddt_good'] + 0.02,
                y_min + (y_thresh_good - y_min) * 0.1,
                'Good Zone', fontsize=9, color=CAT_PALETTE[2], alpha=0.8,
                fontweight='bold', ha='left')

    plt.tight_layout()

    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")

    return fig


# ============================================================
# Figure 4: Design Ranking
# ============================================================

def plot_design_ranking(df: pd.DataFrame, output_path: str = None):
    """Plot 4: Distribution of composite scores using violin + strip plot."""
    fig, ax = simple_ax(figsize=(5, 5))

    df = df.copy()
    df['score'] = calculate_composite_score(df)
    values = df['score'].values

    # Violin plot for density
    parts = ax.violinplot(values, positions=[0], showmeans=False,
                          showmedians=False, showextrema=False)
    for pc in parts['bodies']:
        pc.set_facecolor(CAT_PALETTE[4])
        pc.set_alpha(0.2)

    # Box plot overlay
    bp = ax.boxplot(values, positions=[0], widths=0.15, patch_artist=True,
                    showfliers=False, zorder=2)
    bp['boxes'][0].set_facecolor('white')
    bp['boxes'][0].set_alpha(0.8)
    bp['medians'][0].set_color('black')
    bp['medians'][0].set_linewidth(1.5)

    # Strip plot (jittered, colored by score)
    jitter = np.random.default_rng(42).uniform(-0.12, 0.12, len(values))
    scatter = ax.scatter(jitter, values, c=values, cmap='viridis',
                         s=40, alpha=0.7, edgecolors='white',
                         linewidth=0.5, zorder=3)

    cbar = plt.colorbar(scatter, ax=ax, shrink=0.7, pad=0.08)
    cbar.set_label('Score', fontsize=9)

    # Summary stats
    median = np.median(values)
    mean = np.mean(values)
    ax.text(0.95, 0.97, f'n={len(values)}\nmedian={median:.2f}\nmean={mean:.2f}',
            transform=ax.transAxes, fontsize=9, va='top', ha='right',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    ax.set_title('Composite Score Distribution', fontsize=14, fontweight='bold', pad=12)
    ax.set_ylabel('Composite Score', fontsize=11)
    ax.set_xlim(-0.5, 0.5)
    ax.set_xticks([])
    ax.yaxis.grid(True, linestyle='--', alpha=0.4)

    plt.tight_layout()

    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")

    return fig


# ============================================================
# Figure 5: Metrics Table
# ============================================================

def plot_metrics_table(df: pd.DataFrame, output_path: str = None, top_n: int = 6):
    """Plot 5: Table showing top designs with pLDDT, iPTM, and composite score."""
    fig = plt.figure(figsize=(5, 4))
    ax = fig.add_subplot(111)
    ax.axis('off')
    ax.set_title('Top Designs', fontsize=14, fontweight='bold', pad=12)

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

    # Style header
    for j, label in enumerate(col_headers):
        cell = table[(0, j)]
        cell.set_text_props(text=label, fontweight='bold', fontsize=10)
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
            cell.set_text_props(text=text, fontsize=9)

    # Academic three-line style: remove all cell borders, add alternating row shading
    table.auto_set_font_size(False)
    for (row_idx, col_idx), cell in table.get_celld().items():
        cell.set_edgecolor('white')
        cell.set_linewidth(0)
        cell.set_height(0.11)
        # Alternate row shading (data rows only)
        if row_idx > 0 and row_idx % 2 == 0:
            cell.set_facecolor('#F5F5F5')
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

    line_kwargs = dict(color='black', linewidth=1.2, transform=ax.transAxes, clip_on=False)
    ax.plot([x_left, x_right], [y_top, y_top], **line_kwargs)           # top line
    ax.plot([x_left, x_right], [y_header_bottom, y_header_bottom], **line_kwargs)  # below header
    ax.plot([x_left, x_right], [y_bottom, y_bottom], **line_kwargs)     # bottom line

    plt.tight_layout()

    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")

    return fig


# ============================================================
# Figure 6: iPTM Scores
# ============================================================

def plot_iptm_comparison(df: pd.DataFrame, output_path: str = None):
    """Plot 6: Distribution of iPTM scores using violin + strip plot."""
    fig, ax = simple_ax(figsize=(5, 5))

    values = df['iPTM'].values

    # Violin plot for density
    parts = ax.violinplot(values, positions=[0], showmeans=False,
                          showmedians=False, showextrema=False)
    for pc in parts['bodies']:
        pc.set_facecolor(CAT_PALETTE[0])
        pc.set_alpha(0.2)

    # Box plot overlay
    bp = ax.boxplot(values, positions=[0], widths=0.15, patch_artist=True,
                    showfliers=False, zorder=2)
    bp['boxes'][0].set_facecolor('white')
    bp['boxes'][0].set_alpha(0.8)
    bp['medians'][0].set_color('black')
    bp['medians'][0].set_linewidth(1.5)

    # Strip plot (jittered individual points)
    jitter = np.random.default_rng(42).uniform(-0.12, 0.12, len(values))
    colors = [get_color_for_value(v, QUALITY_THRESHOLDS['iptm_good'],
                                   QUALITY_THRESHOLDS['iptm_acceptable'],
                                   higher_is_better=True)
              for v in values]
    ax.scatter(jitter, values, c=colors, s=40, alpha=0.7, edgecolors='white',
               linewidth=0.5, zorder=3)

    # Threshold lines
    ax.axhline(y=QUALITY_THRESHOLDS['iptm_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.7, linewidth=1,
               label=f"Good (>{QUALITY_THRESHOLDS['iptm_good']})")
    ax.axhline(y=QUALITY_THRESHOLDS['iptm_acceptable'], color=CAT_PALETTE[1],
               linestyle='--', alpha=0.7, linewidth=1,
               label=f"Acceptable (>{QUALITY_THRESHOLDS['iptm_acceptable']})")

    # Summary stats
    median = np.median(values)
    mean = np.mean(values)
    ax.text(0.95, 0.97, f'n={len(values)}\nmedian={median:.2f}\nmean={mean:.2f}',
            transform=ax.transAxes, fontsize=9, va='top', ha='right',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    ax.set_title('iPTM Distribution', fontsize=14, fontweight='bold', pad=12)
    ax.set_ylabel('iPTM (higher is better)', fontsize=11)
    ax.set_xlim(-0.5, 0.5)
    ax.set_xticks([])
    ax.set_ylim(min(values) - 0.05, 1.05)
    ax.yaxis.grid(True, linestyle='--', alpha=0.4)
    ax.legend(loc='lower right', fontsize=9)

    plt.tight_layout()

    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")

    return fig


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
        saved_files.append(f"{output_prefix}_plddt_scores.png")
        plt.close(fig1)

    # Figure 2: iPAE comparison (or loss if iPAE unavailable)
    if 'iPAE' in df.columns:
        fig2 = plot_ipae_comparison(df, f"{output_prefix}_ipae_comparison")
        saved_files.append(f"{output_prefix}_ipae_comparison.png")
        plt.close(fig2)
    elif 'loss' in df.columns:
        fig2 = plot_loss_comparison(df, f"{output_prefix}_loss_comparison")
        saved_files.append(f"{output_prefix}_loss_comparison.png")
        plt.close(fig2)

    # Figure 3: Quality scatter (supports iPAE or loss fallback)
    if 'pLDDT' in df.columns and ('iPAE' in df.columns or 'loss' in df.columns):
        fig3 = plot_quality_scatter(df, f"{output_prefix}_quality_scatter")
        saved_files.append(f"{output_prefix}_quality_scatter.png")
        plt.close(fig3)

    # Figure 4: Design ranking
    fig4 = plot_design_ranking(df, f"{output_prefix}_design_ranking")
    saved_files.append(f"{output_prefix}_design_ranking.png")
    plt.close(fig4)

    # Figure 5: Metrics table
    fig5 = plot_metrics_table(df, f"{output_prefix}_metrics_table")
    saved_files.append(f"{output_prefix}_metrics_table.png")
    plt.close(fig5)

    # Figure 6: iPTM comparison
    if 'iPTM' in df.columns:
        fig6 = plot_iptm_comparison(df, f"{output_prefix}_iptm_scores")
        saved_files.append(f"{output_prefix}_iptm_scores.png")
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
    # Violin
    parts = ax.violinplot(values, positions=[0], showmeans=False,
                          showmedians=False, showextrema=False)
    for pc in parts['bodies']:
        pc.set_facecolor(CAT_PALETTE[palette_idx])
        pc.set_alpha(0.2)

    # Box overlay
    bp = ax.boxplot(values, positions=[0], widths=0.15, patch_artist=True,
                    showfliers=False, zorder=2)
    bp['boxes'][0].set_facecolor('white')
    bp['boxes'][0].set_alpha(0.8)
    bp['medians'][0].set_color('black')
    bp['medians'][0].set_linewidth(1.5)

    # Strip (jittered points)
    jitter = np.random.default_rng(42).uniform(-0.12, 0.12, len(values))
    colors = [get_color_for_value(v, thresholds[0], thresholds[1],
                                   higher_is_better=higher_is_better)
              for v in values]
    ax.scatter(jitter, values, c=colors, s=30, alpha=0.7, edgecolors='white',
               linewidth=0.4, zorder=3)

    # Threshold lines
    good_label = f'>{thresholds[0]}' if higher_is_better else f'<{thresholds[0]}'
    acc_label = f'>{thresholds[1]}' if higher_is_better else f'<{thresholds[1]}'
    ax.axhline(y=thresholds[0], color=CAT_PALETTE[2], linestyle='--', alpha=0.7, linewidth=1)
    ax.axhline(y=thresholds[1], color=CAT_PALETTE[1], linestyle='--', alpha=0.7, linewidth=1)

    # Stats
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


def _plot_quality_scatter_ax(ax, df):
    """Internal: Plot quality scatter on given axis (supports loss fallback)."""
    scores = calculate_composite_score(df)

    if 'iPAE' in df.columns:
        y_metric, y_label, y_thresh = 'iPAE', 'iPAE', QUALITY_THRESHOLDS['ipae_good']
    elif 'loss' in df.columns:
        y_metric, y_label, y_thresh = 'loss', 'Loss', 2.0
    else:
        ax.text(0.5, 0.5, 'Scatter data\nnot available', ha='center', va='center',
                transform=ax.transAxes, fontsize=9)
        ax.axis('off')
        return

    scatter = ax.scatter(df['pLDDT'], df[y_metric], c=scores, cmap='viridis',
                        s=40, alpha=0.8, edgecolors='white', linewidth=0.4)

    y_min = df[y_metric].min() * 0.95
    rect_good = Rectangle((QUALITY_THRESHOLDS['plddt_good'], y_min),
                          1.0 - QUALITY_THRESHOLDS['plddt_good'],
                          y_thresh - y_min,
                          linewidth=0, facecolor=CAT_PALETTE[2], alpha=0.1)
    ax.add_patch(rect_good)

    ax.axvline(x=QUALITY_THRESHOLDS['plddt_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.5, linewidth=1)
    ax.axhline(y=y_thresh, color=CAT_PALETTE[2],
               linestyle='--', alpha=0.5, linewidth=1)

    ax.set_title('Quality Distribution', fontsize=10, fontweight='bold', pad=8)
    ax.set_xlabel('pLDDT', fontsize=8)
    ax.set_ylabel(y_label, fontsize=8)

    cbar = plt.colorbar(scatter, ax=ax, shrink=0.8)
    cbar.set_label('Score', fontsize=7)


def _plot_metrics_table_ax(ax, df):
    """Internal: Plot top-6 metrics table with three-line academic style."""
    ax.axis('off')
    ax.set_title('Top Designs', fontsize=10, fontweight='bold', pad=8)

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

    for j, label in enumerate(col_headers):
        cell = table[(0, j)]
        cell.set_text_props(text=label, fontweight='bold', fontsize=8)
        cell.set_facecolor('white')

    for i, (_, row) in enumerate(df_sorted.iterrows()):
        for j, col in enumerate(display_cols):
            cell = table[(i+1, j)]
            val = row[col]
            if col == 'design_id':
                text = simplify_design_id(val)
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

    # Three-line style
    bbox = [0.0, 0.05, 1.0, 0.9]
    x_left, x_right = bbox[0], bbox[0] + bbox[2]
    y_bottom, y_top = bbox[1], bbox[1] + bbox[3]
    row_h = bbox[3] / n_rows
    y_header_bottom = y_top - row_h

    line_kw = dict(color='black', linewidth=1.0, transform=ax.transAxes, clip_on=False)
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

    fig = plt.figure(figsize=(14, 9))

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
        _plot_violin_strip_ax(ax1, df['pLDDT'].values, 'pLDDT Distribution',
                              'pLDDT (higher is better)',
                              [QUALITY_THRESHOLDS['plddt_good'],
                               QUALITY_THRESHOLDS['plddt_acceptable']],
                              higher_is_better=True)
        ax1.set_ylim(df['pLDDT'].min() - 0.05, 1.05)
    else:
        ax1.text(0.5, 0.5, 'pLDDT data\nnot available', ha='center', va='center',
                transform=ax1.transAxes, fontsize=10)
        ax1.axis('off')

    # Panel 2: Loss or iPAE distribution
    if 'iPAE' in df.columns:
        _plot_violin_strip_ax(ax2, df['iPAE'].values, 'iPAE Distribution',
                              'iPAE (lower is better)',
                              [QUALITY_THRESHOLDS['ipae_good'],
                               QUALITY_THRESHOLDS['ipae_acceptable']],
                              higher_is_better=False)
    elif 'loss' in df.columns:
        _plot_violin_strip_ax(ax2, df['loss'].values, 'Loss Distribution',
                              'Loss (lower is better)',
                              [2.0, 3.0], higher_is_better=False)
    else:
        ax2.text(0.5, 0.5, 'Loss/iPAE data\nnot available', ha='center', va='center',
                transform=ax2.transAxes, fontsize=10)
        ax2.axis('off')

    # Panel 3: Quality scatter
    if 'pLDDT' in df.columns and ('iPAE' in df.columns or 'loss' in df.columns):
        _plot_quality_scatter_ax(ax3, df)
    else:
        ax3.text(0.5, 0.5, 'Scatter data\nnot available', ha='center', va='center',
                transform=ax3.transAxes, fontsize=10)
        ax3.axis('off')

    # Panel 4: Composite score distribution
    scores = calculate_composite_score(df)
    _plot_violin_strip_ax(ax4, scores.values, 'Composite Score',
                          'Score', [0.7, 0.5], higher_is_better=True,
                          palette_idx=4)

    # Panel 5: Top designs table
    _plot_metrics_table_ax(ax5, df)

    # Panel 6: iPTM distribution
    if 'iPTM' in df.columns:
        _plot_violin_strip_ax(ax6, df['iPTM'].values, 'iPTM Distribution',
                              'iPTM (higher is better)',
                              [QUALITY_THRESHOLDS['iptm_good'],
                               QUALITY_THRESHOLDS['iptm_acceptable']],
                              higher_is_better=True)
        ax6.set_ylim(df['iPTM'].min() - 0.05, 1.05)
    else:
        ax6.text(0.5, 0.5, 'iPTM data\nnot available', ha='center', va='center',
                transform=ax6.transAxes, fontsize=10)
        ax6.axis('off')

    plt.tight_layout()

    save_for_pub(fig, output_prefix, include_raster=True)
    plt.close(fig)

    print(f"\nSaved merged figure: {output_prefix}.png, {output_prefix}.pdf")
    return f"{output_prefix}.png"


# ============================================================
# Display results (notebook/GUI)
# ============================================================

def display_results(results_dir: str, show_all: bool = True, block: bool = True):
    """Display AfCycDesign pipeline results in an interactive environment.

    Args:
        results_dir: Path to results directory containing the generated figures
        show_all: If True, display all figures. If False, only display main metrics.
        block: If True (default), block until figure window is closed.

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
        ("plddt_scores", "pLDDT Scores"),
        ("ipae_comparison", "Interface iPAE"),
        ("quality_scatter", "Quality Distribution"),
        ("design_ranking", "Design Ranking"),
        ("metrics_table", "Design Metrics Summary"),
        ("iptm_scores", "iPTM Scores"),
    ]

    if not show_all:
        figure_files = figure_files[:3]

    if in_notebook:
        from IPython.display import display, Image as IPImage
        for fig_name, title in figure_files:
            png_path = results_dir / f"afcycdesign_{fig_name}.png"
            if png_path.exists():
                print(f"\n{title}:")
                display(IPImage(filename=str(png_path)))
                figures[fig_name] = str(png_path)
            else:
                print(f"Warning: {png_path} not found")
    else:
        try:
            matplotlib.use('TkAgg')
        except Exception:
            try:
                matplotlib.use('Qt5Agg')
            except Exception:
                pass

        from PIL import Image

        plt.ion()

        fig, axes = plt.subplots(2, 3, figsize=(14, 9))
        axes = axes.flatten()

        for i, (fig_name, title) in enumerate(figure_files):
            png_path = results_dir / f"afcycdesign_{fig_name}.png"
            if png_path.exists():
                img = Image.open(png_path)
                axes[i].imshow(img)
                axes[i].axis('off')
                figures[fig_name] = str(png_path)
            else:
                axes[i].text(0.5, 0.5, f"{fig_name}\nnot found",
                            ha='center', va='center', transform=axes[i].transAxes)
                axes[i].axis('off')

        plt.tight_layout()
        figures['combined_figure'] = fig
        plt.show(block=block)

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
