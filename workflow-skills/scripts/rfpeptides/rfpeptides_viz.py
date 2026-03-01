#!/usr/bin/env python3
"""
RFpeptides Pipeline Visualization Script

Generates separate figures after binder design workflow:
1. Binding Energy (ddG) - Bar chart of ddG scores sorted by value
2. Interface iPAE - Bar chart of iPAE scores sorted ascending
3. Quality Scatter - ddG vs iPAE colored by composite score
4. Design Ranking - Horizontal bar chart by composite score
5. Metrics Table - Top designs with all metrics and pass/fail
6. Execution Timeline - Gantt chart of 5 pipeline stages

Each figure is saved as a separate 4x4 inch file.
A merged 2x3 summary figure can also be generated.
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
DIV_PALETTE = sns.color_palette("BrBG_r", 100)
SEQ_PALETTE = sns.cubehelix_palette(100, start=0.5, rot=-0.75)
GRAY = [0.5, 0.5, 0.5]

# Figure size for individual plots
FIGSIZE = (4, 4)

# Quality thresholds for RFpeptides pipeline
QUALITY_THRESHOLDS = {
    'ddg_good': -50,
    'ddg_acceptable': -30,
    'ipae_good': 0.15,
    'ipae_acceptable': 0.20,
    'plddt_good': 0.70,
    'plddt_acceptable': 0.50,
    'sap_good': 25,
    'sap_acceptable': 35,
    'cms_good': 400,
    'cms_acceptable': 300,
}

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


def load_design_metrics(results_dir: Path) -> pd.DataFrame:
    """Load design metrics from RFpeptides pipeline results directory."""
    results_dir = Path(results_dir)

    # Priority 1: final_summary.csv (pipeline output)
    possible_names = [
        "final_summary.csv",
        "design_metrics.csv",
        "metrics.csv",
    ]

    for name in possible_names:
        csv_path = results_dir / name
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            df = normalize_column_names(df)
            print(f"Loaded metrics from {csv_path} ({len(df)} designs)")
            return df

    # Search subdirectories
    for subdir in results_dir.iterdir():
        if subdir.is_dir():
            for name in possible_names:
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

    column_mapping = {
        'design': 'design_id',
        'name': 'design_id',
        'design_name': 'design_id',
        'DDG': 'ddg',
        'dG': 'ddg',
        'SAP': 'sap',
        'CMS': 'cms',
        'ipae': 'iPAE',
        'IPAE': 'iPAE',
        'i_pae': 'iPAE',
        'plddt': 'pLDDT',
        'PLDDT': 'pLDDT',
    }

    for old_name, new_name in column_mapping.items():
        if old_name in df.columns and new_name not in df.columns:
            df[new_name] = df[old_name]

    # Ensure design_id exists
    if 'design_id' not in df.columns:
        df['design_id'] = [f'd{i:02d}' for i in range(len(df))]

    # Filter out rows with sentinel values (iPAE=999 means AfCycDesign failed)
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
        # Strip common prefixes
        if name.startswith('design_'):
            return name.replace('design_', '').lstrip('0') or '0'
        return name
    return str(name)


def generate_mock_data(n_designs=8) -> pd.DataFrame:
    """Generate mock data for demonstration."""
    np.random.seed(42)

    designs = []
    for i in range(n_designs):
        ddg = np.random.normal(-35, 15)
        designs.append({
            'design_id': f'd{i:02d}',
            'sequence': ''.join(np.random.choice(list('ADEFGHIKLMNPQRSTVWY'), 12)),
            'length': 12,
            'iPAE': np.random.beta(2, 8) * 0.5,
            'pLDDT': np.random.beta(5, 2),
            'ddg': ddg,
            'sap': np.random.normal(25, 8),
            'cms': np.random.normal(350, 60),
            'passes_physics': ddg < -30,
        })

    df = pd.DataFrame(designs)
    df['ddg'] = df['ddg'].clip(-80, 0)
    df['iPAE'] = df['iPAE'].clip(0.05, 0.5)
    df['pLDDT'] = df['pLDDT'].clip(0.3, 0.99)
    df['sap'] = df['sap'].clip(5, 60)
    df['cms'] = df['cms'].clip(100, 600)

    return df


def calculate_composite_score(df: pd.DataFrame) -> pd.Series:
    """Calculate composite quality score for ranking designs.

    Score = 0.3 * ddG_norm + 0.25 * iPAE_norm + 0.2 * pLDDT_norm
            + 0.15 * CMS_norm + 0.1 * SAP_norm

    All normalized 0-1; ddG/iPAE/SAP inverted since lower=better.
    """
    scores = pd.DataFrame(index=df.index)

    # ddG: lower (more negative) is better. Normalize: -80 to 0 range
    if 'ddg' in df.columns:
        scores['ddg'] = ((-df['ddg']).clip(0, 80) / 80)

    # iPAE: lower is better. Normalize: 0 to 0.5 range
    if 'iPAE' in df.columns:
        scores['iPAE'] = (1 - (df['iPAE'] / 0.5).clip(0, 1))

    # pLDDT: higher is better (0-1 scale)
    if 'pLDDT' in df.columns:
        scores['pLDDT'] = df['pLDDT'].clip(0, 1)

    # CMS: higher is better. Normalize: 0 to 600 range
    if 'cms' in df.columns:
        scores['cms'] = (df['cms'] / 600).clip(0, 1)

    # SAP: lower is better. Normalize: 0 to 60 range
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


# ============================================================
# Figure 1: Binding Energy (ddG)
# ============================================================

def plot_ddg_comparison(df: pd.DataFrame, output_path: str = None):
    """Plot 1: Bar chart of ddG scores sorted by value (more negative = better)."""
    fig, ax = simple_ax(figsize=FIGSIZE)

    df_sorted = df.sort_values('ddg', ascending=True).reset_index(drop=True)
    n_designs = len(df_sorted)
    x_pos = np.arange(n_designs)

    colors = [get_color_for_value(v, QUALITY_THRESHOLDS['ddg_good'],
                                   QUALITY_THRESHOLDS['ddg_acceptable'],
                                   higher_is_better=False)
              for v in df_sorted['ddg']]

    ax.bar(x_pos, df_sorted['ddg'], color=colors, alpha=0.9, width=0.7)

    ax.axhline(y=QUALITY_THRESHOLDS['ddg_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.7, linewidth=1,
               label=f"Good (<{QUALITY_THRESHOLDS['ddg_good']})")
    ax.axhline(y=QUALITY_THRESHOLDS['ddg_acceptable'], color=CAT_PALETTE[1],
               linestyle='--', alpha=0.7, linewidth=1,
               label=f"Acceptable (<{QUALITY_THRESHOLDS['ddg_acceptable']})")

    ax.set_title('Binding Energy (ddG)', fontsize=12, fontweight='bold', pad=10)
    ax.set_ylabel('ddG (REU, more negative = better)', fontsize=10)
    ax.set_xlabel('Design', fontsize=10)
    ax.set_xticks(x_pos)

    labels = [simplify_design_id(name) for name in df_sorted['design_id']]
    ax.set_xticklabels(labels, fontsize=8, rotation=45, ha='right')

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
# Figure 3: Quality Scatter (ddG vs iPAE)
# ============================================================

def plot_quality_scatter(df: pd.DataFrame, output_path: str = None):
    """Plot 3: Scatter plot of ddG vs iPAE colored by composite score."""
    fig, ax = simple_ax(figsize=FIGSIZE)

    scores = calculate_composite_score(df)

    scatter = ax.scatter(df['ddg'], df['iPAE'], c=scores, cmap='viridis',
                        s=80, alpha=0.8, edgecolors='white', linewidth=0.5)

    # Good zone: low ddG (more negative) AND low iPAE
    ddg_min = min(df['ddg'].min() * 1.1, -80)
    rect_good = Rectangle((ddg_min, 0),
                          QUALITY_THRESHOLDS['ddg_good'] - ddg_min,
                          QUALITY_THRESHOLDS['ipae_good'],
                          linewidth=0, facecolor=CAT_PALETTE[2], alpha=0.1)
    ax.add_patch(rect_good)

    ax.axvline(x=QUALITY_THRESHOLDS['ddg_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.5, linewidth=1)
    ax.axhline(y=QUALITY_THRESHOLDS['ipae_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.5, linewidth=1)

    # Add design labels
    for _, row in df.iterrows():
        label = simplify_design_id(row['design_id'])
        ax.annotate(label, (row['ddg'], row['iPAE']),
                   fontsize=7, alpha=0.7,
                   xytext=(3, 3), textcoords='offset points')

    ax.set_title('Quality Distribution', fontsize=12, fontweight='bold', pad=10)
    ax.set_xlabel('ddG (REU, more negative = better)', fontsize=10)
    ax.set_ylabel('iPAE (lower is better)', fontsize=10)

    cbar = plt.colorbar(scatter, ax=ax, shrink=0.8)
    cbar.set_label('Composite Score', fontsize=9)

    ax.text(QUALITY_THRESHOLDS['ddg_good'] - 5, QUALITY_THRESHOLDS['ipae_good'] - 0.01,
            'Good Zone', fontsize=8, color=CAT_PALETTE[2], alpha=0.8,
            fontweight='bold', ha='right')

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

    # Color by passes_physics if available
    if 'passes_physics' in df_sorted.columns:
        colors = [CAT_PALETTE[2] if p else CAT_PALETTE[3]
                  for p in df_sorted['passes_physics']]
    else:
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

    # Add legend if passes_physics available
    if 'passes_physics' in df_sorted.columns:
        legend_elements = [
            mpatches.Patch(facecolor=CAT_PALETTE[2], alpha=0.9, label='Passes filters'),
            mpatches.Patch(facecolor=CAT_PALETTE[3], alpha=0.9, label='Fails filters'),
        ]
        ax.legend(handles=legend_elements, loc='lower right', fontsize=8)

    plt.tight_layout()

    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")

    return fig


# ============================================================
# Figure 5: Metrics Table
# ============================================================

def plot_metrics_table(df: pd.DataFrame, output_path: str = None):
    """Plot 5: Table showing top designs with ddG, iPAE, pLDDT, SAP, CMS, pass/fail."""
    fig = plt.figure(figsize=FIGSIZE)
    ax = fig.add_subplot(111)
    ax.axis('off')
    ax.set_title('Design Metrics Summary', fontsize=12, fontweight='bold', pad=10)

    # Columns to display
    display_cols = ['design_id']
    metric_cols = []
    col_headers = ['Design']

    metric_defs = [
        ('ddg', 'ddG'),
        ('iPAE', 'iPAE'),
        ('pLDDT', 'pLDDT'),
        ('sap', 'SAP'),
        ('cms', 'CMS'),
    ]
    for col, header in metric_defs:
        if col in df.columns:
            display_cols.append(col)
            metric_cols.append(col)
            col_headers.append(header)

    # Add pass/fail column
    has_passes = 'passes_physics' in df.columns
    if has_passes:
        display_cols.append('passes_physics')
        col_headers.append('Pass')

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

    # Fill data
    for i, (_, row) in enumerate(df_sorted.iterrows()):
        for j, col in enumerate(display_cols):
            cell = table[(i+1, j)]
            val = row[col]
            if col == 'design_id':
                text = simplify_design_id(val)
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
            elif col == 'passes_physics':
                text = 'PASS' if val else 'FAIL'
                cell.set_facecolor('#D4EDDA' if val else '#F8D7DA')
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
            f'(ddG={best.get("ddg", 0):.1f}, iPAE={best.get("iPAE", 0):.3f})',
            ha='center', va='bottom', transform=ax.transAxes,
            fontsize=9, fontweight='bold')

    plt.tight_layout()

    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")

    return fig


# ============================================================
# Figure 6: Execution Timeline
# ============================================================

def parse_pipeline_log(log_path: Path) -> list:
    """Parse pipeline.log to extract stage start times and durations.

    Expected log format: [HH:MM:SS] STAGE N: Description
    """
    if not log_path.exists():
        return None

    stage_times = {}
    time_pattern = re.compile(r'^\[(\d{2}:\d{2}:\d{2})\]\s+(.*)$')

    with open(log_path) as f:
        lines = f.readlines()

    first_time = None
    prev_time = None

    for line in lines:
        m = time_pattern.match(line.strip())
        if not m:
            continue
        time_str, content = m.groups()
        t = datetime.strptime(time_str, '%H:%M:%S')

        # Handle day rollover
        if prev_time and t < prev_time:
            t = t.replace(day=2)
        if first_time is None:
            first_time = t
        prev_time = t

        # Check for stage markers
        stage_match = re.match(r'STAGE\s+(\d+):', content)
        if stage_match:
            stage_num = int(stage_match.group(1))
            stage_times[stage_num] = {'start': t}

    if not stage_times or first_time is None:
        return None

    # Calculate durations: each stage ends when the next starts, or at last log entry
    sorted_stages = sorted(stage_times.keys())
    last_time = prev_time

    steps = []
    for i, stage_num in enumerate(sorted_stages):
        start = stage_times[stage_num]['start']
        if i + 1 < len(sorted_stages):
            end = stage_times[sorted_stages[i + 1]]['start']
        else:
            end = last_time

        start_min = (start - first_time).total_seconds() / 60
        duration = max((end - start).total_seconds() / 60, 0.5)

        stage_idx = stage_num - 1
        name = PIPELINE_STAGES[stage_idx] if stage_idx < len(PIPELINE_STAGES) else f'Stage {stage_num}'
        steps.append({
            'name': name,
            'start': round(start_min, 1),
            'duration': round(duration, 1),
        })

    return steps if steps else None


def plot_execution_timeline(results_dir: Path, output_path: str = None):
    """Plot 6: Gantt chart of 5 RFpeptides pipeline stages."""
    fig, ax = simple_ax(figsize=FIGSIZE)
    ax.set_title('Execution Timeline', fontsize=12, fontweight='bold', pad=10)

    # Default timeline for RFpeptides pipeline
    default_steps = [
        {'name': 'Stage 1: Backbone Gen.', 'start': 0, 'duration': 30},
        {'name': 'Stage 2: Seq. Design', 'start': 30, 'duration': 120},
        {'name': 'Stage 3: DL Validation', 'start': 150, 'duration': 60},
        {'name': 'Stage 4: Physics Filter', 'start': 210, 'duration': 30},
        {'name': 'Stage 5: Clustering', 'start': 240, 'duration': 5},
    ]

    steps = None

    # Try to load from pipeline.log
    results_dir = Path(results_dir)
    log_candidates = [
        results_dir / "pipeline.log",
        results_dir.parent / "pipeline.log",
    ]
    for log_path in log_candidates:
        if log_path.exists():
            steps = parse_pipeline_log(log_path)
            if steps:
                print(f"Loaded timeline from {log_path} ({len(steps)} stages)")
                break

    if steps is None:
        steps = default_steps
        print("Using default timeline (no pipeline.log found)")

    total_time = max(s['start'] + s['duration'] for s in steps)

    colors = [CAT_PALETTE[i % len(CAT_PALETTE)] for i in range(len(steps))]
    y_positions = list(range(len(steps)-1, -1, -1))

    for i, (step, y_pos) in enumerate(zip(steps, y_positions)):
        ax.barh(y_pos, step['duration'], left=step['start'], height=0.6,
                color=colors[i], edgecolor='white', linewidth=0.5)
        ax.text(-0.5, y_pos, step['name'], ha='right', va='center', fontsize=8)

    # Total time bar
    if total_time >= 60:
        total_label = f"Total: ~{total_time/60:.1f} hours"
    else:
        total_label = f"Total: ~{int(total_time)} min"
    ax.barh(-1, total_time, left=0, height=0.6, color=GRAY, alpha=0.8)
    ax.text(-0.5, -1, total_label, ha='right', va='center',
            fontsize=8, fontweight='bold')

    ax.set_xlabel('Time (minutes)', fontsize=10)
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
# Separate figures entry point
# ============================================================

def create_separate_figures(results_dir: str, output_prefix: str = None):
    """Create 6 separate visualization figures for RFpeptides pipeline.

    Args:
        results_dir: Path to results directory
        output_prefix: Path prefix for saving (without extension)

    Returns:
        list: Paths to saved figures
    """
    results_dir = Path(results_dir)

    if output_prefix is None:
        output_prefix = str(results_dir / "rfpeptides")

    set_pub_plot_context(context="talk")

    df = load_design_metrics(results_dir)
    if df.empty:
        print("Error: No design metrics found in", results_dir)
        return None

    saved_files = []

    # Figure 1: ddG comparison
    fig1 = plot_ddg_comparison(df, f"{output_prefix}_ddg_comparison")
    saved_files.append(f"{output_prefix}_ddg_comparison.png")
    plt.close(fig1)

    # Figure 2: iPAE comparison
    if 'iPAE' in df.columns:
        fig2 = plot_ipae_comparison(df, f"{output_prefix}_ipae_comparison")
        saved_files.append(f"{output_prefix}_ipae_comparison.png")
        plt.close(fig2)

    # Figure 3: Quality scatter
    if 'iPAE' in df.columns:
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

    # Figure 6: Execution timeline
    fig6 = plot_execution_timeline(results_dir, f"{output_prefix}_execution_timeline")
    saved_files.append(f"{output_prefix}_execution_timeline.png")
    plt.close(fig6)

    print(f"\nGenerated {len(saved_files)} separate figures:")
    for f in saved_files:
        print(f"  - {f}")

    return saved_files


# ============================================================
# Merged 2x3 figure
# ============================================================

def _plot_ddg_comparison_ax(ax, df):
    """Internal: Plot ddG comparison on given axis."""
    df_sorted = df.sort_values('ddg', ascending=True).reset_index(drop=True)
    n_designs = len(df_sorted)
    x_pos = np.arange(n_designs)

    colors = [get_color_for_value(v, QUALITY_THRESHOLDS['ddg_good'],
                                   QUALITY_THRESHOLDS['ddg_acceptable'],
                                   higher_is_better=False)
              for v in df_sorted['ddg']]

    ax.bar(x_pos, df_sorted['ddg'], color=colors, alpha=0.9, width=0.7)
    ax.axhline(y=QUALITY_THRESHOLDS['ddg_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.7, linewidth=1)
    ax.axhline(y=QUALITY_THRESHOLDS['ddg_acceptable'], color=CAT_PALETTE[1],
               linestyle='--', alpha=0.7, linewidth=1)

    ax.set_title('Binding Energy (ddG)', fontsize=10, fontweight='bold', pad=8)
    ax.set_ylabel('ddG (REU)', fontsize=9)
    ax.set_xlabel('Design', fontsize=9)
    ax.set_xticks(x_pos)
    labels = [simplify_design_id(name) for name in df_sorted['design_id']]
    ax.set_xticklabels(labels, fontsize=8)
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

    scatter = ax.scatter(df['ddg'], df['iPAE'], c=scores, cmap='viridis',
                        s=60, alpha=0.8, edgecolors='white', linewidth=0.5)

    ddg_min = min(df['ddg'].min() * 1.1, -80)
    rect_good = Rectangle((ddg_min, 0),
                          QUALITY_THRESHOLDS['ddg_good'] - ddg_min,
                          QUALITY_THRESHOLDS['ipae_good'],
                          linewidth=0, facecolor=CAT_PALETTE[2], alpha=0.1)
    ax.add_patch(rect_good)

    ax.axvline(x=QUALITY_THRESHOLDS['ddg_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.5, linewidth=1)
    ax.axhline(y=QUALITY_THRESHOLDS['ipae_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.5, linewidth=1)

    ax.set_title('Quality Distribution', fontsize=10, fontweight='bold', pad=8)
    ax.set_xlabel('ddG (REU)', fontsize=9)
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

    if 'passes_physics' in df_sorted.columns:
        colors = [CAT_PALETTE[2] if p else CAT_PALETTE[3]
                  for p in df_sorted['passes_physics']]
    else:
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

    for col, header in [('ddg', 'ddG'), ('iPAE', 'iPAE'), ('pLDDT', 'pLDDT'),
                        ('sap', 'SAP'), ('cms', 'CMS')]:
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
            cell.set_text_props(text=text, fontsize=7)

    table.auto_set_font_size(False)
    for key, cell in table.get_celld().items():
        cell.set_edgecolor('#CCCCCC')
        cell.set_height(0.12)


def _plot_execution_timeline_ax(ax, results_dir):
    """Internal: Plot execution timeline on given axis."""
    ax.set_title('Execution Timeline', fontsize=10, fontweight='bold', pad=8)

    default_steps = [
        {'name': 'Backbone Gen.', 'start': 0, 'duration': 30},
        {'name': 'Seq. Design', 'start': 30, 'duration': 120},
        {'name': 'DL Validation', 'start': 150, 'duration': 60},
        {'name': 'Physics Filter', 'start': 210, 'duration': 30},
        {'name': 'Clustering', 'start': 240, 'duration': 5},
    ]

    steps = None
    results_dir = Path(results_dir)
    for log_path in [results_dir / "pipeline.log", results_dir.parent / "pipeline.log"]:
        if log_path.exists():
            steps = parse_pipeline_log(log_path)
            if steps:
                # Shorten names for merged view
                for s in steps:
                    s['name'] = s['name'].replace('Stage ', 'S').split(': ')[-1] if ': ' in s['name'] else s['name']
                break

    if steps is None:
        steps = default_steps

    total_time = max(s['start'] + s['duration'] for s in steps)
    colors = [CAT_PALETTE[i % len(CAT_PALETTE)] for i in range(len(steps))]
    y_positions = list(range(len(steps)-1, -1, -1))

    for i, (step, y_pos) in enumerate(zip(steps, y_positions)):
        ax.barh(y_pos, step['duration'], left=step['start'], height=0.6,
                color=colors[i], edgecolor='white', linewidth=0.5)
        ax.text(-0.5, y_pos, step['name'], ha='right', va='center', fontsize=7)

    if total_time >= 60:
        total_label = f"Total: ~{total_time/60:.1f}h"
    else:
        total_label = f"Total: ~{int(total_time)}m"
    ax.barh(-1, total_time, left=0, height=0.6, color=GRAY, alpha=0.8)
    ax.text(-0.5, -1, total_label, ha='right', va='center', fontsize=7, fontweight='bold')

    ax.set_xlabel('Time (minutes)', fontsize=9)
    ax.set_xlim(-1, total_time * 1.1)
    ax.set_ylim(-2, len(steps))
    ax.set_yticks([])
    ax.xaxis.grid(True, linestyle='--', alpha=0.4)
    ax.spines['left'].set_visible(False)


def create_merged_figure(results_dir: str, output_prefix: str = None):
    """Create a single merged figure with all 6 panels in 2x3 grid.

    Layout:
        Row 1: ddG comparison, iPAE comparison, Quality scatter
        Row 2: Design ranking, Metrics table, Execution timeline

    Args:
        results_dir: Path to results directory
        output_prefix: Path prefix for saving (without extension)

    Returns:
        str: Path to saved merged figure
    """
    results_dir = Path(results_dir)

    if output_prefix is None:
        output_prefix = str(results_dir / "rfpeptides_summary")

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

    _plot_ddg_comparison_ax(ax1, df)

    if 'iPAE' in df.columns:
        _plot_ipae_comparison_ax(ax2, df)
        _plot_quality_scatter_ax(ax3, df)
    else:
        ax2.text(0.5, 0.5, 'iPAE data\nnot available', ha='center', va='center',
                transform=ax2.transAxes, fontsize=10)
        ax2.axis('off')
        ax3.text(0.5, 0.5, 'iPAE data\nnot available', ha='center', va='center',
                transform=ax3.transAxes, fontsize=10)
        ax3.axis('off')

    _plot_design_ranking_ax(ax4, df)
    _plot_metrics_table_ax(ax5, df)
    _plot_execution_timeline_ax(ax6, results_dir)

    plt.tight_layout()

    save_for_pub(fig, output_prefix, include_raster=True)
    plt.close(fig)

    print(f"\nSaved merged figure: {output_prefix}.png, {output_prefix}.pdf")
    return f"{output_prefix}.png"


# ============================================================
# Display results (notebook/GUI)
# ============================================================

def display_results(results_dir: str, show_all: bool = True, block: bool = True):
    """Display RFpeptides pipeline results in an interactive environment.

    Shows the generated figures either inline (Jupyter/IPython)
    or in a GUI window (terminal/script).

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
        ("ddg_comparison", "Binding Energy (ddG)"),
        ("ipae_comparison", "Interface iPAE"),
        ("quality_scatter", "Quality Distribution"),
        ("design_ranking", "Design Ranking"),
        ("metrics_table", "Design Metrics Summary"),
        ("execution_timeline", "Execution Timeline"),
    ]

    if not show_all:
        figure_files = figure_files[:3]

    if in_notebook:
        from IPython.display import display, Image as IPImage
        for fig_name, title in figure_files:
            png_path = results_dir / f"rfpeptides_{fig_name}.png"
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
            png_path = results_dir / f"rfpeptides_{fig_name}.png"
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
    csv_path = results_dir / "final_summary.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        df = normalize_column_names(df)
        # Filter out invalid entries
        if 'iPAE' in df.columns:
            df = df[df['iPAE'] < 900]
        df['score'] = calculate_composite_score(df)
        df_sorted = df.sort_values('score', ascending=False)

        print("\n" + "="*60)
        print("RFPEPTIDES PIPELINE SUMMARY")
        print("="*60)
        print(f"Total designs: {len(df)}")

        if 'passes_physics' in df.columns:
            n_pass = df['passes_physics'].sum()
            print(f"Passing physics filters: {n_pass}/{len(df)}")

        print(f"\nTop 3 designs by composite score:")
        for i, (_, row) in enumerate(df_sorted.head(3).iterrows()):
            name = simplify_design_id(row.get('design_id', f'd{i}'))
            ddg = row.get('ddg', float('nan'))
            ipae = row.get('iPAE', float('nan'))
            plddt = row.get('pLDDT', float('nan'))
            print(f"  {i+1}. {name}: ddG={ddg:.1f}, iPAE={ipae:.3f}, "
                  f"pLDDT={plddt:.2f}, score={row['score']:.2f}")
        print("="*60)

    return figures


# ============================================================
# CLI entry point
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='Generate RFpeptides pipeline visualization figures')
    parser.add_argument('results_dir', type=str,
                        help='Path to pipeline results directory (containing final_summary.csv)')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='Output prefix (default: results_dir/rfpeptides)')
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
