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
    """Plot 1: Bar chart of pLDDT scores sorted descending (higher = better)."""
    fig, ax = simple_ax(figsize=FIGSIZE)

    df_sorted = df.sort_values('pLDDT', ascending=False).reset_index(drop=True)
    n_designs = len(df_sorted)
    x_pos = np.arange(n_designs)

    colors = [get_color_for_value(v, QUALITY_THRESHOLDS['plddt_good'],
                                   QUALITY_THRESHOLDS['plddt_acceptable'],
                                   higher_is_better=True)
              for v in df_sorted['pLDDT']]

    ax.bar(x_pos, df_sorted['pLDDT'], color=colors, alpha=0.9, width=0.7)

    ax.axhline(y=QUALITY_THRESHOLDS['plddt_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.7, linewidth=1,
               label=f"Good (>{QUALITY_THRESHOLDS['plddt_good']})")
    ax.axhline(y=QUALITY_THRESHOLDS['plddt_acceptable'], color=CAT_PALETTE[1],
               linestyle='--', alpha=0.7, linewidth=1,
               label=f"Acceptable (>{QUALITY_THRESHOLDS['plddt_acceptable']})")

    ax.set_title('pLDDT Scores', fontsize=12, fontweight='bold', pad=10)
    ax.set_ylabel('pLDDT (higher is better)', fontsize=10)
    ax.set_xlabel('Design', fontsize=10)
    ax.set_xticks(x_pos)

    labels = [simplify_design_id(name) for name in df_sorted['design_id']]
    ax.set_xticklabels(labels, fontsize=8, rotation=45, ha='right')

    ax.set_ylim(0, 1.05)
    ax.yaxis.grid(True, linestyle='--', alpha=0.4)
    ax.legend(loc='lower right', fontsize=8)

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
    fig, ax = simple_ax(figsize=FIGSIZE)

    df_sorted = df.sort_values('iPAE', ascending=True).reset_index(drop=True)
    n_designs = len(df_sorted)
    x_pos = np.arange(n_designs)

    colors = [get_color_for_value(v, QUALITY_THRESHOLDS['ipae_good'],
                                   QUALITY_THRESHOLDS['ipae_acceptable'],
                                   higher_is_better=False)
              for v in df_sorted['iPAE']]

    ax.bar(x_pos, df_sorted['iPAE'], color=colors, alpha=0.9, width=0.7)

    ax.axhline(y=QUALITY_THRESHOLDS['ipae_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.7, linewidth=1,
               label=f"Good (<{QUALITY_THRESHOLDS['ipae_good']})")
    ax.axhline(y=QUALITY_THRESHOLDS['ipae_acceptable'], color=CAT_PALETTE[1],
               linestyle='--', alpha=0.7, linewidth=1,
               label=f"Acceptable (<{QUALITY_THRESHOLDS['ipae_acceptable']})")

    ax.set_title('Interface iPAE', fontsize=12, fontweight='bold', pad=10)
    ax.set_ylabel('iPAE (lower is better)', fontsize=10)
    ax.set_xlabel('Design', fontsize=10)
    ax.set_xticks(x_pos)

    labels = [simplify_design_id(name) for name in df_sorted['design_id']]
    ax.set_xticklabels(labels, fontsize=8, rotation=45, ha='right')

    ax.yaxis.grid(True, linestyle='--', alpha=0.4)
    ax.legend(loc='upper right', fontsize=8)

    plt.tight_layout()

    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")

    return fig


# ============================================================
# Figure 3: Quality Scatter (pLDDT vs iPAE)
# ============================================================

def plot_quality_scatter(df: pd.DataFrame, output_path: str = None):
    """Plot 3: Scatter plot of pLDDT vs iPAE colored by composite score."""
    fig, ax = simple_ax(figsize=FIGSIZE)

    scores = calculate_composite_score(df)

    scatter = ax.scatter(df['pLDDT'], df['iPAE'], c=scores, cmap='viridis',
                        s=80, alpha=0.8, edgecolors='white', linewidth=0.5)

    # Good zone: high pLDDT AND low iPAE
    rect_good = Rectangle((QUALITY_THRESHOLDS['plddt_good'], 0),
                          1.0 - QUALITY_THRESHOLDS['plddt_good'],
                          QUALITY_THRESHOLDS['ipae_good'],
                          linewidth=0, facecolor=CAT_PALETTE[2], alpha=0.1)
    ax.add_patch(rect_good)

    ax.axvline(x=QUALITY_THRESHOLDS['plddt_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.5, linewidth=1)
    ax.axhline(y=QUALITY_THRESHOLDS['ipae_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.5, linewidth=1)

    # Add design labels
    for _, row in df.iterrows():
        label = simplify_design_id(row['design_id'])
        ax.annotate(label, (row['pLDDT'], row['iPAE']),
                   fontsize=7, alpha=0.7,
                   xytext=(3, 3), textcoords='offset points')

    ax.set_title('Quality Distribution', fontsize=12, fontweight='bold', pad=10)
    ax.set_xlabel('pLDDT (higher is better)', fontsize=10)
    ax.set_ylabel('iPAE (lower is better)', fontsize=10)

    cbar = plt.colorbar(scatter, ax=ax, shrink=0.8)
    cbar.set_label('Composite Score', fontsize=9)

    ax.text(QUALITY_THRESHOLDS['plddt_good'] + 0.05,
            QUALITY_THRESHOLDS['ipae_good'] - 0.01,
            'Good Zone', fontsize=8, color=CAT_PALETTE[2], alpha=0.8,
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
    """Plot 4: Horizontal bar chart ranking designs by composite score."""
    fig, ax = simple_ax(figsize=FIGSIZE)

    df = df.copy()
    df['score'] = calculate_composite_score(df)
    df_sorted = df.sort_values('score', ascending=True).reset_index(drop=True)

    n_designs = len(df_sorted)
    y_pos = np.arange(n_designs)

    colors = [CAT_PALETTE[i % len(CAT_PALETTE)] for i in range(n_designs)][::-1]

    bars = ax.barh(y_pos, df_sorted['score'], color=colors, alpha=0.9, height=0.7)

    ax.set_title('Design Ranking', fontsize=12, fontweight='bold', pad=10)
    ax.set_xlabel('Composite Score', fontsize=10)
    ax.set_yticks(y_pos)

    labels = []
    for i, (_, row) in enumerate(df_sorted.iterrows()):
        rank = n_designs - i
        name = simplify_design_id(row['design_id'])
        labels.append(f"#{rank}: {name}")
    ax.set_yticklabels(labels, fontsize=9)

    ax.set_xlim(0, 1)
    ax.xaxis.grid(True, linestyle='--', alpha=0.4)

    for bar, (_, row) in zip(bars, df_sorted.iterrows()):
        width = bar.get_width()
        ax.text(width + 0.02, bar.get_y() + bar.get_height()/2,
                f'{row["score"]:.2f}', va='center', fontsize=8)

    plt.tight_layout()

    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")

    return fig


# ============================================================
# Figure 5: Metrics Table
# ============================================================

def plot_metrics_table(df: pd.DataFrame, output_path: str = None):
    """Plot 5: Table showing top designs with pLDDT, iPAE, iPTM, pTM, i_con."""
    fig = plt.figure(figsize=FIGSIZE)
    ax = fig.add_subplot(111)
    ax.axis('off')
    ax.set_title('Design Metrics Summary', fontsize=12, fontweight='bold', pad=10)

    display_cols = ['design_id']
    col_headers = ['Design']

    metric_defs = [
        ('pLDDT', 'pLDDT'),
        ('iPAE', 'iPAE'),
        ('iPTM', 'iPTM'),
        ('pTM', 'pTM'),
        ('i_con', 'i_con'),
    ]
    for col, header in metric_defs:
        if col in df.columns:
            display_cols.append(col)
            col_headers.append(header)

    df = df.copy()
    df['score'] = calculate_composite_score(df)

    # Sort by composite score, show top 8
    df_sorted = df.sort_values('score', ascending=False).head(8).reset_index(drop=True)

    n_rows = len(df_sorted) + 1  # +1 for header
    n_cols = len(display_cols)

    table = ax.table(
        cellText=[['']*n_cols for _ in range(n_rows)],
        loc='center',
        cellLoc='center',
        bbox=[0.0, 0.05, 1.0, 0.9]
    )

    # Style header
    for j, label in enumerate(col_headers):
        cell = table[(0, j)]
        cell.set_text_props(text=label, fontweight='bold', fontsize=8)
        cell.set_facecolor('#E8E8E8')

    # Fill data with color coding
    for i, (_, row) in enumerate(df_sorted.iterrows()):
        for j, col in enumerate(display_cols):
            cell = table[(i+1, j)]
            val = row[col]
            if col == 'design_id':
                text = simplify_design_id(val)
            elif col == 'pLDDT':
                text = f'{val:.2f}'
                if val >= QUALITY_THRESHOLDS['plddt_good']:
                    cell.set_facecolor('#D4EDDA')
                elif val < QUALITY_THRESHOLDS['plddt_acceptable']:
                    cell.set_facecolor('#F8D7DA')
            elif col == 'iPAE':
                text = f'{val:.3f}'
                if val <= QUALITY_THRESHOLDS['ipae_good']:
                    cell.set_facecolor('#D4EDDA')
                elif val > QUALITY_THRESHOLDS['ipae_acceptable']:
                    cell.set_facecolor('#F8D7DA')
            elif col == 'iPTM':
                text = f'{val:.2f}'
                if val >= QUALITY_THRESHOLDS['iptm_good']:
                    cell.set_facecolor('#D4EDDA')
                elif val < QUALITY_THRESHOLDS['iptm_acceptable']:
                    cell.set_facecolor('#F8D7DA')
            elif col == 'pTM':
                text = f'{val:.2f}'
                if val >= QUALITY_THRESHOLDS['ptm_good']:
                    cell.set_facecolor('#D4EDDA')
                elif val < QUALITY_THRESHOLDS['ptm_acceptable']:
                    cell.set_facecolor('#F8D7DA')
            elif col == 'i_con':
                text = f'{val:.2f}'
            else:
                text = f'{val:.2f}'
            cell.set_text_props(text=text, fontsize=8)

    table.auto_set_font_size(False)
    for key, cell in table.get_celld().items():
        cell.set_edgecolor('#CCCCCC')
        cell.set_height(0.1)

    # Best design annotation
    best = df_sorted.iloc[0]
    ax.text(0.5, 0.01,
            f'Best: {simplify_design_id(best["design_id"])} '
            f'(pLDDT={best.get("pLDDT", 0):.2f}, iPAE={best.get("iPAE", 0):.3f})',
            ha='center', va='bottom', transform=ax.transAxes,
            fontsize=9, fontweight='bold')

    plt.tight_layout()

    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")

    return fig


# ============================================================
# Figure 6: iPTM Scores
# ============================================================

def plot_iptm_comparison(df: pd.DataFrame, output_path: str = None):
    """Plot 6: Bar chart of iPTM scores sorted descending (higher = better)."""
    fig, ax = simple_ax(figsize=FIGSIZE)

    df_sorted = df.sort_values('iPTM', ascending=False).reset_index(drop=True)
    n_designs = len(df_sorted)
    x_pos = np.arange(n_designs)

    colors = [get_color_for_value(v, QUALITY_THRESHOLDS['iptm_good'],
                                   QUALITY_THRESHOLDS['iptm_acceptable'],
                                   higher_is_better=True)
              for v in df_sorted['iPTM']]

    ax.bar(x_pos, df_sorted['iPTM'], color=colors, alpha=0.9, width=0.7)

    ax.axhline(y=QUALITY_THRESHOLDS['iptm_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.7, linewidth=1,
               label=f"Good (>{QUALITY_THRESHOLDS['iptm_good']})")
    ax.axhline(y=QUALITY_THRESHOLDS['iptm_acceptable'], color=CAT_PALETTE[1],
               linestyle='--', alpha=0.7, linewidth=1,
               label=f"Acceptable (>{QUALITY_THRESHOLDS['iptm_acceptable']})")

    ax.set_title('Interface pTM (iPTM)', fontsize=12, fontweight='bold', pad=10)
    ax.set_ylabel('iPTM (higher is better)', fontsize=10)
    ax.set_xlabel('Design', fontsize=10)
    ax.set_xticks(x_pos)

    labels = [simplify_design_id(name) for name in df_sorted['design_id']]
    ax.set_xticklabels(labels, fontsize=8, rotation=45, ha='right')

    ax.set_ylim(0, 1.05)
    ax.yaxis.grid(True, linestyle='--', alpha=0.4)
    ax.legend(loc='lower right', fontsize=8)

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

    # Figure 2: iPAE comparison
    if 'iPAE' in df.columns:
        fig2 = plot_ipae_comparison(df, f"{output_prefix}_ipae_comparison")
        saved_files.append(f"{output_prefix}_ipae_comparison.png")
        plt.close(fig2)

    # Figure 3: Quality scatter
    if 'pLDDT' in df.columns and 'iPAE' in df.columns:
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

def _plot_plddt_comparison_ax(ax, df):
    """Internal: Plot pLDDT comparison on given axis."""
    df_sorted = df.sort_values('pLDDT', ascending=False).reset_index(drop=True)
    n_designs = len(df_sorted)
    x_pos = np.arange(n_designs)

    colors = [get_color_for_value(v, QUALITY_THRESHOLDS['plddt_good'],
                                   QUALITY_THRESHOLDS['plddt_acceptable'],
                                   higher_is_better=True)
              for v in df_sorted['pLDDT']]

    ax.bar(x_pos, df_sorted['pLDDT'], color=colors, alpha=0.9, width=0.7)
    ax.axhline(y=QUALITY_THRESHOLDS['plddt_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.7, linewidth=1)
    ax.axhline(y=QUALITY_THRESHOLDS['plddt_acceptable'], color=CAT_PALETTE[1],
               linestyle='--', alpha=0.7, linewidth=1)

    ax.set_title('pLDDT Scores', fontsize=10, fontweight='bold', pad=8)
    ax.set_ylabel('pLDDT', fontsize=9)
    ax.set_xlabel('Design', fontsize=9)
    ax.set_xticks(x_pos)
    labels = [simplify_design_id(name) for name in df_sorted['design_id']]
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.yaxis.grid(True, linestyle='--', alpha=0.4)


def _plot_ipae_comparison_ax(ax, df):
    """Internal: Plot iPAE comparison on given axis."""
    df_sorted = df.sort_values('iPAE', ascending=True).reset_index(drop=True)
    n_designs = len(df_sorted)
    x_pos = np.arange(n_designs)

    colors = [get_color_for_value(v, QUALITY_THRESHOLDS['ipae_good'],
                                   QUALITY_THRESHOLDS['ipae_acceptable'],
                                   higher_is_better=False)
              for v in df_sorted['iPAE']]

    ax.bar(x_pos, df_sorted['iPAE'], color=colors, alpha=0.9, width=0.7)
    ax.axhline(y=QUALITY_THRESHOLDS['ipae_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.7, linewidth=1)
    ax.axhline(y=QUALITY_THRESHOLDS['ipae_acceptable'], color=CAT_PALETTE[1],
               linestyle='--', alpha=0.7, linewidth=1)

    ax.set_title('Interface iPAE', fontsize=10, fontweight='bold', pad=8)
    ax.set_ylabel('iPAE (lower is better)', fontsize=9)
    ax.set_xlabel('Design', fontsize=9)
    ax.set_xticks(x_pos)
    labels = [simplify_design_id(name) for name in df_sorted['design_id']]
    ax.set_xticklabels(labels, fontsize=8)
    ax.yaxis.grid(True, linestyle='--', alpha=0.4)


def _plot_quality_scatter_ax(ax, df):
    """Internal: Plot quality scatter on given axis."""
    scores = calculate_composite_score(df)

    scatter = ax.scatter(df['pLDDT'], df['iPAE'], c=scores, cmap='viridis',
                        s=60, alpha=0.8, edgecolors='white', linewidth=0.5)

    rect_good = Rectangle((QUALITY_THRESHOLDS['plddt_good'], 0),
                          1.0 - QUALITY_THRESHOLDS['plddt_good'],
                          QUALITY_THRESHOLDS['ipae_good'],
                          linewidth=0, facecolor=CAT_PALETTE[2], alpha=0.1)
    ax.add_patch(rect_good)

    ax.axvline(x=QUALITY_THRESHOLDS['plddt_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.5, linewidth=1)
    ax.axhline(y=QUALITY_THRESHOLDS['ipae_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.5, linewidth=1)

    ax.set_title('Quality Distribution', fontsize=10, fontweight='bold', pad=8)
    ax.set_xlabel('pLDDT', fontsize=9)
    ax.set_ylabel('iPAE', fontsize=9)

    cbar = plt.colorbar(scatter, ax=ax, shrink=0.8)
    cbar.set_label('Score', fontsize=8)


def _plot_design_ranking_ax(ax, df):
    """Internal: Plot design ranking on given axis."""
    df = df.copy()
    df['score'] = calculate_composite_score(df)
    df_sorted = df.sort_values('score', ascending=True).reset_index(drop=True)

    n_designs = len(df_sorted)
    y_pos = np.arange(n_designs)

    colors = [CAT_PALETTE[i % len(CAT_PALETTE)] for i in range(n_designs)][::-1]

    ax.barh(y_pos, df_sorted['score'], color=colors, alpha=0.9, height=0.7)

    ax.set_title('Design Ranking', fontsize=10, fontweight='bold', pad=8)
    ax.set_xlabel('Composite Score', fontsize=9)
    ax.set_yticks(y_pos)

    labels = []
    for i, (_, row) in enumerate(df_sorted.iterrows()):
        rank = n_designs - i
        name = simplify_design_id(row['design_id'])
        labels.append(f"#{rank}: {name}")
    ax.set_yticklabels(labels, fontsize=8)

    ax.set_xlim(0, 1)
    ax.xaxis.grid(True, linestyle='--', alpha=0.4)


def _plot_metrics_table_ax(ax, df):
    """Internal: Plot metrics table on given axis."""
    ax.axis('off')
    ax.set_title('Metrics Summary', fontsize=10, fontweight='bold', pad=8)

    display_cols = ['design_id']
    col_headers = ['Design']

    for col, header in [('pLDDT', 'pLDDT'), ('iPAE', 'iPAE'),
                        ('iPTM', 'iPTM'), ('pTM', 'pTM'), ('i_con', 'i_con')]:
        if col in df.columns:
            display_cols.append(col)
            col_headers.append(header)

    df = df.copy()
    df['score'] = calculate_composite_score(df)

    df_sorted = df.sort_values('score', ascending=False).head(6).reset_index(drop=True)

    n_rows = len(df_sorted) + 1
    n_cols = len(display_cols)

    table = ax.table(cellText=[['']*n_cols for _ in range(n_rows)],
                     loc='center', cellLoc='center', bbox=[0.0, 0.05, 1.0, 0.9])

    for j, label in enumerate(col_headers):
        cell = table[(0, j)]
        cell.set_text_props(text=label, fontweight='bold', fontsize=7)
        cell.set_facecolor('#E8E8E8')

    for i, (_, row) in enumerate(df_sorted.iterrows()):
        for j, col in enumerate(display_cols):
            cell = table[(i+1, j)]
            val = row[col]
            if col == 'design_id':
                text = simplify_design_id(val)
            elif col == 'iPAE':
                text = f'{val:.3f}'
            elif col == 'i_con':
                text = f'{val:.2f}'
            else:
                text = f'{val:.2f}'
            cell.set_text_props(text=text, fontsize=7)

    table.auto_set_font_size(False)
    for key, cell in table.get_celld().items():
        cell.set_edgecolor('#CCCCCC')
        cell.set_height(0.12)


def _plot_iptm_comparison_ax(ax, df):
    """Internal: Plot iPTM comparison on given axis."""
    df_sorted = df.sort_values('iPTM', ascending=False).reset_index(drop=True)
    n_designs = len(df_sorted)
    x_pos = np.arange(n_designs)

    colors = [get_color_for_value(v, QUALITY_THRESHOLDS['iptm_good'],
                                   QUALITY_THRESHOLDS['iptm_acceptable'],
                                   higher_is_better=True)
              for v in df_sorted['iPTM']]

    ax.bar(x_pos, df_sorted['iPTM'], color=colors, alpha=0.9, width=0.7)
    ax.axhline(y=QUALITY_THRESHOLDS['iptm_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.7, linewidth=1)
    ax.axhline(y=QUALITY_THRESHOLDS['iptm_acceptable'], color=CAT_PALETTE[1],
               linestyle='--', alpha=0.7, linewidth=1)

    ax.set_title('iPTM Scores', fontsize=10, fontweight='bold', pad=8)
    ax.set_ylabel('iPTM', fontsize=9)
    ax.set_xlabel('Design', fontsize=9)
    ax.set_xticks(x_pos)
    labels = [simplify_design_id(name) for name in df_sorted['design_id']]
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.yaxis.grid(True, linestyle='--', alpha=0.4)


def create_merged_figure(results_dir: str, output_prefix: str = None):
    """Create a single merged figure with all 6 panels in 2x3 grid.

    Layout:
        Row 1: pLDDT scores, iPAE comparison, Quality scatter
        Row 2: Design ranking, Metrics table, iPTM scores

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

    fig = plt.figure(figsize=(12, 8))

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

    if 'pLDDT' in df.columns:
        _plot_plddt_comparison_ax(ax1, df)
    else:
        ax1.text(0.5, 0.5, 'pLDDT data\nnot available', ha='center', va='center',
                transform=ax1.transAxes, fontsize=10)
        ax1.axis('off')

    if 'iPAE' in df.columns:
        _plot_ipae_comparison_ax(ax2, df)
    else:
        ax2.text(0.5, 0.5, 'iPAE data\nnot available', ha='center', va='center',
                transform=ax2.transAxes, fontsize=10)
        ax2.axis('off')

    if 'pLDDT' in df.columns and 'iPAE' in df.columns:
        _plot_quality_scatter_ax(ax3, df)
    else:
        ax3.text(0.5, 0.5, 'Scatter data\nnot available', ha='center', va='center',
                transform=ax3.transAxes, fontsize=10)
        ax3.axis('off')

    _plot_design_ranking_ax(ax4, df)
    _plot_metrics_table_ax(ax5, df)

    if 'iPTM' in df.columns:
        _plot_iptm_comparison_ax(ax6, df)
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
