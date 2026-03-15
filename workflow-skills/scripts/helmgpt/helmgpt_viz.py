#!/usr/bin/env python3
"""
HELM-GPT KRAS Binder Design Visualization Script

Generates separate figures after the HELM-GPT binder design workflow:
1. KRAS KD Distribution - Violin + strip of KD scores
2. Permeability Distribution - Violin + strip of permeability scores
3. Quality Scatter - KD vs Permeability colored by composite score
4. AF3 iPTM Distribution - Violin + strip of AF3 iPTM scores
5. Gnina CNN Affinity Distribution - Violin + strip
6. Gnina Vina Score Distribution - Violin + strip
7. Boltz-2 Ensemble Affinity Distribution - Violin + strip
8. Boltz-2 Binding Probability Distribution - Violin + strip
9. Composite Score Distribution - Violin + strip
10. Metrics Table - Top designs with three-line academic style
11. Execution Timeline - Gantt chart of pipeline phases

Each figure is saved as a separate PNG + PDF file.
A merged summary figure can also be generated.
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
import numpy as np
import pandas as pd
import seaborn as sns

# Color palettes
CAT_PALETTE = sns.color_palette('colorblind')
GRAY = [0.5, 0.5, 0.5]

# Figure size for individual plots
FIGSIZE = (5, 5)

# Quality thresholds for HELM-GPT KRAS binder pipeline
QUALITY_THRESHOLDS = {
    'kd_excellent': 1,
    'kd_good': 10,
    'kd_acceptable': 100,
    'perm_excellent': -5.0,
    'perm_good': -6.0,
    'perm_acceptable': -6.5,
    'af3_iptm_excellent': 0.80,
    'af3_iptm_good': 0.60,
    'af3_iptm_acceptable': 0.40,
    'boltz_avg_aff_good': 0.0,
    'boltz_avg_aff_acceptable': -0.3,
    'boltz_avg_prob_good': 0.5,
    'boltz_avg_prob_acceptable': 0.4,
    'gnina_cnn_excellent': 7.0,
    'gnina_cnn_good': 6.0,
    'gnina_cnn_acceptable': 5.0,
    'gnina_vina_excellent': -8.0,
    'gnina_vina_good': -7.0,
    'gnina_vina_acceptable': -5.0,
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


# ============================================================
# Data Loading
# ============================================================

def load_helmgpt_results(results_dir: Path) -> pd.DataFrame:
    """Load and merge all HELM-GPT pipeline results into a single DataFrame."""
    results_dir = Path(results_dir)

    # 1. Load candidate CSV
    df = None
    for pattern in ['top*_phase2.csv', 'top*_routed.csv', 'top*_candidates.csv']:
        matches = sorted(results_dir.glob(pattern))
        if matches:
            df = pd.read_csv(matches[0])
            print(f"Loaded candidates from {matches[0]} ({len(df)} designs)")
            break

    if df is None:
        print("No candidate CSV found, generating mock data")
        return generate_mock_data()

    df = df.reset_index(drop=True)
    df['design_id'] = [f'c{i:02d}' for i in range(len(df))]

    # 2. Merge AF3 results
    af3_path = results_dir / 'af3_results.csv'
    if af3_path.exists():
        af3 = pd.read_csv(af3_path)
        for col in ['af3_iptm', 'af3_ptm', 'af3_ranking_score']:
            if col in af3.columns:
                df[col] = af3[col].values[:len(df)]
        print(f"  Merged AF3 results ({len(af3)} entries)")

    # 3. Load Boltz-2 results
    boltz_dir = results_dir / 'boltz2_results'
    if boltz_dir.exists():
        boltz_affs = {}
        boltz_confs = {}
        for cand_dir in sorted(boltz_dir.iterdir()):
            if not cand_dir.is_dir():
                continue
            try:
                cand_idx = int(cand_dir.name.replace('cand', ''))
            except ValueError:
                continue

            aff_file = cand_dir / 'affinity_temp_affinity.json'
            if aff_file.exists():
                with open(aff_file) as f:
                    boltz_affs[cand_idx] = json.load(f)

            conf_file = cand_dir / 'confidence_temp_affinity_model_0.json'
            if conf_file.exists():
                with open(conf_file) as f:
                    boltz_confs[cand_idx] = json.load(f)

        for col in ['boltz_avg_aff', 'boltz_avg_prob', 'boltz_ligand_iptm',
                     'boltz_confidence', 'boltz_complex_plddt']:
            df[col] = np.nan

        for idx, aff in boltz_affs.items():
            if idx < len(df):
                avg_aff = np.mean([aff.get('affinity_pred_value', 0),
                                   aff.get('affinity_pred_value1', 0),
                                   aff.get('affinity_pred_value2', 0)])
                avg_prob = np.mean([aff.get('affinity_probability_binary', 0),
                                    aff.get('affinity_probability_binary1', 0),
                                    aff.get('affinity_probability_binary2', 0)])
                df.loc[idx, 'boltz_avg_aff'] = avg_aff
                df.loc[idx, 'boltz_avg_prob'] = avg_prob

        for idx, conf in boltz_confs.items():
            if idx < len(df):
                df.loc[idx, 'boltz_ligand_iptm'] = conf.get('ligand_iptm', np.nan)
                df.loc[idx, 'boltz_confidence'] = conf.get('confidence_score', np.nan)
                df.loc[idx, 'boltz_complex_plddt'] = conf.get('complex_plddt', np.nan)

        print(f"  Merged Boltz-2 results ({len(boltz_affs)} candidates)")

    # 4. Load Gnina results from SDF files
    gnina_dir = results_dir / 'gnina_results'
    if gnina_dir.exists():
        for col in ['gnina_best_cnn', 'gnina_best_vina', 'gnina_mean_cnn']:
            df[col] = np.nan

        for sdf_file in sorted(gnina_dir.glob('cand*_docked.sdf')):
            name = sdf_file.stem
            try:
                cand_idx = int(name.split('_')[0].replace('cand', ''))
            except ValueError:
                continue

            if cand_idx >= len(df):
                continue

            cnn_affinities = []
            vina_affinities = []
            try:
                from rdkit import Chem
                suppl = Chem.SDMolSupplier(str(sdf_file))
                for mol in suppl:
                    if mol is None:
                        continue
                    props = mol.GetPropsAsDict()
                    if 'CNNaffinity' in props:
                        cnn_affinities.append(float(props['CNNaffinity']))
                    if 'minimizedAffinity' in props:
                        vina_affinities.append(float(props['minimizedAffinity']))
            except ImportError:
                import re
                with open(sdf_file) as f:
                    content = f.read()
                for m in re.finditer(r'>.*CNNaffinity.*\n([\d\.\-]+)', content):
                    cnn_affinities.append(float(m.group(1)))
                for m in re.finditer(r'>.*minimizedAffinity.*\n([\d\.\-]+)', content):
                    vina_affinities.append(float(m.group(1)))

            if cnn_affinities:
                df.loc[cand_idx, 'gnina_best_cnn'] = max(cnn_affinities)
                df.loc[cand_idx, 'gnina_mean_cnn'] = np.mean(cnn_affinities)
            if vina_affinities:
                df.loc[cand_idx, 'gnina_best_vina'] = min(vina_affinities)

        n_gnina = df['gnina_best_cnn'].notna().sum()
        print(f"  Merged Gnina results ({n_gnina} candidates)")

    return df


def generate_mock_data(n_designs=10) -> pd.DataFrame:
    """Generate mock data for demonstration."""
    np.random.seed(42)
    designs = []
    for i in range(n_designs):
        designs.append({
            'design_id': f'c{i:02d}',
            'helm_seqs': f'PEPTIDE1{{mock_seq_{i}}}',
            'raw_kras_kd': np.random.uniform(0.5, 5.0),
            'raw_permeability': np.random.uniform(-7.5, -6.0),
            'heavy_atoms': np.random.randint(75, 100),
            'af3_iptm': np.random.beta(3, 3),
            'af3_ptm': np.random.beta(4, 2),
            'boltz_avg_aff': np.random.normal(0, 0.5),
            'boltz_avg_prob': np.random.beta(5, 3),
            'boltz_ligand_iptm': np.random.beta(5, 2),
            'gnina_best_cnn': np.random.uniform(5, 9),
            'gnina_best_vina': np.random.uniform(-9, -4),
        })
    return pd.DataFrame(designs)


def calculate_composite_score(df: pd.DataFrame) -> pd.Series:
    """Calculate composite quality score for ranking designs."""
    scores = pd.Series(0.0, index=df.index)

    def _norm(s, lo, hi, higher_better=True):
        n = (s - lo) / (hi - lo) if hi != lo else 0.5
        n = np.clip(n, 0, 1)
        return n if higher_better else 1 - n

    if 'raw_kras_kd' in df.columns:
        scores += 0.20 * _norm(df['raw_kras_kd'],
                               df['raw_kras_kd'].min(), df['raw_kras_kd'].max(),
                               higher_better=False)
    if 'raw_permeability' in df.columns:
        scores += 0.15 * _norm(df['raw_permeability'],
                               df['raw_permeability'].min(), df['raw_permeability'].max(),
                               higher_better=True)
    if 'af3_iptm' in df.columns:
        vals = df['af3_iptm'].fillna(0)
        scores += 0.15 * _norm(vals, vals.min(), vals.max(), higher_better=True)
    if 'gnina_best_cnn' in df.columns:
        vals = df['gnina_best_cnn'].fillna(0)
        scores += 0.15 * _norm(vals, vals.min(), vals.max(), higher_better=True)
    if 'gnina_best_vina' in df.columns:
        vals = df['gnina_best_vina'].fillna(0)
        scores += 0.15 * _norm(vals, vals.min(), vals.max(), higher_better=False)
    if 'boltz_avg_aff' in df.columns:
        vals = df['boltz_avg_aff'].fillna(0)
        scores += 0.10 * _norm(vals, vals.min(), vals.max(), higher_better=True)
    if 'boltz_avg_prob' in df.columns:
        vals = df['boltz_avg_prob'].fillna(0)
        scores += 0.10 * _norm(vals, vals.min(), vals.max(), higher_better=True)

    return scores


# ============================================================
# Core violin + strip plot helper
# ============================================================

def plot_violin_strip(values, title, ylabel, thresholds, higher_is_better=True,
                      palette_idx=0, output_path=None, figsize=FIGSIZE):
    """Create a violin + strip + box distribution plot.

    Args:
        values: array of metric values (NaN-dropped before calling)
        title: figure title
        ylabel: y-axis label
        thresholds: (good, acceptable) threshold pair
        higher_is_better: threshold direction
        palette_idx: colorblind palette index for violin fill
        output_path: if set, save to this path (without extension)
        figsize: figure size tuple
    """
    fig, ax = simple_ax(figsize=figsize)

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
    ax.scatter(jitter, values, c=colors, s=40, alpha=0.7, edgecolors='white',
               linewidth=0.5, zorder=3)

    # Threshold lines
    ax.axhline(y=thresholds[0], color=CAT_PALETTE[2], linestyle='--', alpha=0.7, linewidth=1)
    ax.axhline(y=thresholds[1], color=CAT_PALETTE[1], linestyle='--', alpha=0.7, linewidth=1)

    # Summary stats
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
                           palette_idx=0):
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

    ax.axhline(y=thresholds[0], color=CAT_PALETTE[2], linestyle='--', alpha=0.7, linewidth=1)
    ax.axhline(y=thresholds[1], color=CAT_PALETTE[1], linestyle='--', alpha=0.7, linewidth=1)

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

def plot_kd_distribution(df, output_path=None):
    """Plot 1: KRAS KD distribution."""
    values = df['raw_kras_kd'].dropna().values
    return plot_violin_strip(
        values, 'KRAS Binding Affinity (KD)',
        'KD (\u03bcM, lower is better)',
        (QUALITY_THRESHOLDS['kd_excellent'], QUALITY_THRESHOLDS['kd_good']),
        higher_is_better=False, palette_idx=0, output_path=output_path)


def plot_permeability_distribution(df, output_path=None):
    """Plot 2: Permeability distribution."""
    values = df['raw_permeability'].dropna().values
    return plot_violin_strip(
        values, 'Membrane Permeability',
        'log Perm (cm/s, higher is better)',
        (QUALITY_THRESHOLDS['perm_good'], QUALITY_THRESHOLDS['perm_acceptable']),
        higher_is_better=True, palette_idx=1, output_path=output_path)


def plot_quality_scatter(df, output_path=None):
    """Plot 3: Scatter plot of KD vs Permeability colored by composite score."""
    fig, ax = simple_ax(figsize=(6, 5))
    scores = calculate_composite_score(df)

    scatter = ax.scatter(df['raw_kras_kd'], df['raw_permeability'], c=scores,
                        cmap='viridis', s=80, alpha=0.8, edgecolors='white', linewidth=0.5)

    # Good zone
    rect_good = Rectangle((0, QUALITY_THRESHOLDS['perm_good']),
                          QUALITY_THRESHOLDS['kd_good'],
                          0 - QUALITY_THRESHOLDS['perm_good'],
                          linewidth=0, facecolor=CAT_PALETTE[2], alpha=0.1)
    ax.add_patch(rect_good)

    ax.axvline(x=QUALITY_THRESHOLDS['kd_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.5, linewidth=1)
    ax.axhline(y=QUALITY_THRESHOLDS['perm_good'], color=CAT_PALETTE[2],
               linestyle='--', alpha=0.5, linewidth=1)

    ax.set_title('KD vs Permeability', fontsize=14, fontweight='bold', pad=12)
    ax.set_xlabel('KRAS KD (\u03bcM, lower is better)', fontsize=11)
    ax.set_ylabel('Permeability (log cm/s, higher is better)', fontsize=11)

    cbar = plt.colorbar(scatter, ax=ax, shrink=0.8)
    cbar.set_label('Composite Score', fontsize=10)

    plt.tight_layout()
    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")
    return fig


def plot_af3_iptm_distribution(df, output_path=None):
    """Plot 4: AF3 iPTM distribution."""
    if 'af3_iptm' not in df.columns:
        return None
    values = df['af3_iptm'].dropna().values
    if len(values) == 0:
        return None
    fig = plot_violin_strip(
        values, 'AlphaFold3 Interface iPTM',
        'iPTM (higher is better)',
        (QUALITY_THRESHOLDS['af3_iptm_good'], QUALITY_THRESHOLDS['af3_iptm_acceptable']),
        higher_is_better=True, palette_idx=2, output_path=output_path)
    fig.axes[0].set_ylim(min(values) - 0.05, 1.05)
    if output_path:
        save_for_pub(fig, output_path)
    return fig


def plot_gnina_cnn_distribution(df, output_path=None):
    """Plot 5: Gnina CNN affinity distribution."""
    if 'gnina_best_cnn' not in df.columns:
        return None
    values = df['gnina_best_cnn'].dropna().values
    if len(values) == 0:
        return None
    return plot_violin_strip(
        values, 'Gnina CNN Affinity',
        'pKd (higher is better)',
        (QUALITY_THRESHOLDS['gnina_cnn_good'], QUALITY_THRESHOLDS['gnina_cnn_acceptable']),
        higher_is_better=True, palette_idx=3, output_path=output_path)


def plot_gnina_vina_distribution(df, output_path=None):
    """Plot 6: Gnina Vina score distribution."""
    if 'gnina_best_vina' not in df.columns:
        return None
    values = df['gnina_best_vina'].dropna().values
    if len(values) == 0:
        return None
    return plot_violin_strip(
        values, 'Gnina Vina Score',
        'kcal/mol (more negative is better)',
        (QUALITY_THRESHOLDS['gnina_vina_good'], QUALITY_THRESHOLDS['gnina_vina_acceptable']),
        higher_is_better=False, palette_idx=4, output_path=output_path)


def plot_boltz_affinity_distribution(df, output_path=None):
    """Plot 7: Boltz-2 ensemble affinity distribution."""
    if 'boltz_avg_aff' not in df.columns:
        return None
    values = df['boltz_avg_aff'].dropna().values
    if len(values) == 0:
        return None
    return plot_violin_strip(
        values, 'Boltz-2 Ensemble Affinity',
        'Avg Affinity (higher is better)',
        (QUALITY_THRESHOLDS['boltz_avg_aff_good'], QUALITY_THRESHOLDS['boltz_avg_aff_acceptable']),
        higher_is_better=True, palette_idx=0, output_path=output_path)


def plot_boltz_probability_distribution(df, output_path=None):
    """Plot 8: Boltz-2 binding probability distribution."""
    if 'boltz_avg_prob' not in df.columns:
        return None
    values = df['boltz_avg_prob'].dropna().values
    if len(values) == 0:
        return None
    fig = plot_violin_strip(
        values, 'Boltz-2 Binding Probability',
        'Avg Probability (higher is better)',
        (QUALITY_THRESHOLDS['boltz_avg_prob_good'], QUALITY_THRESHOLDS['boltz_avg_prob_acceptable']),
        higher_is_better=True, palette_idx=1, output_path=output_path)
    fig.axes[0].set_ylim(min(0, min(values) - 0.05), 1.05)
    if output_path:
        save_for_pub(fig, output_path)
    return fig


def plot_composite_distribution(df, output_path=None):
    """Plot 9: Composite score distribution."""
    scores = calculate_composite_score(df).values
    fig = plot_violin_strip(
        scores, 'Composite Score Distribution',
        'Score', (0.7, 0.5),
        higher_is_better=True, palette_idx=4, output_path=output_path)
    # Add viridis-colored points on top
    ax = fig.axes[0]
    # Re-scatter with viridis coloring
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
    """Plot 10: Top designs table with three-line academic style."""
    fig = plt.figure(figsize=(6, 4))
    ax = fig.add_subplot(111)
    ax.axis('off')
    ax.set_title('Top Designs', fontsize=14, fontweight='bold', pad=12)

    df = df.copy()
    df['score'] = calculate_composite_score(df)

    # Select columns to display
    col_defs = [('design_id', 'Design')]
    optional = [
        ('raw_kras_kd', 'KD(\u03bcM)'),
        ('raw_permeability', 'Perm'),
        ('af3_iptm', 'AF3 iPTM'),
        ('gnina_best_cnn', 'CNN pKd'),
    ]
    for col, header in optional:
        if col in df.columns:
            col_defs.append((col, header))
    col_defs.append(('score', 'Score'))

    df_sorted = df.sort_values('score', ascending=False).head(top_n).reset_index(drop=True)

    n_rows = len(df_sorted) + 1
    n_cols = len(col_defs)

    table = ax.table(
        cellText=[['']*n_cols for _ in range(n_rows)],
        loc='center', cellLoc='center',
        bbox=[0.02, 0.05, 0.96, 0.85]
    )

    # Header
    for j, (col, header) in enumerate(col_defs):
        cell = table[(0, j)]
        cell.set_text_props(text=header, fontweight='bold', fontsize=9)
        cell.set_facecolor('white')

    # Data
    for i, (_, row) in enumerate(df_sorted.iterrows()):
        for j, (col, header) in enumerate(col_defs):
            cell = table[(i+1, j)]
            val = row[col]
            if col == 'design_id':
                text = str(val)
            elif pd.isna(val):
                text = '-'
            elif col == 'raw_kras_kd':
                text = f'{val:.2f}'
            elif col == 'raw_permeability':
                text = f'{val:.2f}'
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

    # Draw three horizontal lines
    bbox = [0.02, 0.05, 0.96, 0.85]
    x_left = bbox[0]
    x_right = bbox[0] + bbox[2]
    y_bottom = bbox[1]
    y_top = bbox[1] + bbox[3]
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


def plot_execution_timeline(output_path=None):
    """Plot 11: Gantt chart of HELM-GPT pipeline phases."""
    fig, ax = simple_ax(figsize=FIGSIZE)
    ax.set_title('Execution Timeline', fontsize=14, fontweight='bold', pad=12)

    steps = [
        {'name': 'Phase 1: RL Opt.', 'start': 0, 'duration': 60},
        {'name': 'Post-1: Filtering', 'start': 60, 'duration': 5},
        {'name': '2A: Boltz-2 Affinity', 'start': 65, 'duration': 15},
        {'name': '2B: AlphaFold3', 'start': 65, 'duration': 20},
        {'name': '2: Gnina Docking', 'start': 85, 'duration': 15},
        {'name': 'Phase 3: Ranking', 'start': 100, 'duration': 1},
    ]

    total_time = max(s['start'] + s['duration'] for s in steps)
    colors = [CAT_PALETTE[i % len(CAT_PALETTE)] for i in range(len(steps))]
    y_positions = list(range(len(steps)-1, -1, -1))

    for i, (step, y_pos) in enumerate(zip(steps, y_positions)):
        ax.barh(y_pos, step['duration'], left=step['start'], height=0.6,
                color=colors[i], edgecolor='white', linewidth=0.5)
        ax.text(-0.5, y_pos, step['name'], ha='right', va='center', fontsize=8)

    ax.annotate('parallel', xy=(75, 3.5), fontsize=7, color='gray',
                fontstyle='italic', ha='center')

    total_label = f"Total: ~{total_time/60:.1f} hours"
    ax.barh(-1, total_time, left=0, height=0.6, color=GRAY, alpha=0.8)
    ax.text(-0.5, -1, total_label, ha='right', va='center',
            fontsize=8, fontweight='bold')

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

def create_separate_figures(results_dir: str, output_prefix: str = None):
    """Create separate visualization figures for HELM-GPT pipeline."""
    results_dir = Path(results_dir)
    if output_prefix is None:
        output_prefix = str(results_dir / "helmgpt")

    set_pub_plot_context(context="talk")
    df = load_helmgpt_results(results_dir)
    if df.empty:
        print("Error: No design metrics found in", results_dir)
        return None

    saved_files = []

    def _save(fig, name):
        if fig is not None:
            saved_files.append(f"{output_prefix}_{name}.png")
            plt.close(fig)

    # Core distributions
    _save(plot_kd_distribution(df, f"{output_prefix}_kd_distribution"), "kd_distribution")

    if 'raw_permeability' in df.columns:
        _save(plot_permeability_distribution(df, f"{output_prefix}_perm_distribution"), "perm_distribution")

    # Quality scatter
    _save(plot_quality_scatter(df, f"{output_prefix}_quality_scatter"), "quality_scatter")

    # AF3
    _save(plot_af3_iptm_distribution(df, f"{output_prefix}_af3_iptm"), "af3_iptm")

    # Gnina (separate figures)
    _save(plot_gnina_cnn_distribution(df, f"{output_prefix}_gnina_cnn"), "gnina_cnn")
    _save(plot_gnina_vina_distribution(df, f"{output_prefix}_gnina_vina"), "gnina_vina")

    # Boltz-2 (separate figures)
    _save(plot_boltz_affinity_distribution(df, f"{output_prefix}_boltz_affinity"), "boltz_affinity")
    _save(plot_boltz_probability_distribution(df, f"{output_prefix}_boltz_probability"), "boltz_probability")

    # Composite score
    _save(plot_composite_distribution(df, f"{output_prefix}_composite_score"), "composite_score")

    # Metrics table
    _save(plot_metrics_table(df, f"{output_prefix}_metrics_table"), "metrics_table")

    # Timeline
    _save(plot_execution_timeline(f"{output_prefix}_execution_timeline"), "execution_timeline")

    print(f"\nGenerated {len(saved_files)} figures:")
    for f in saved_files:
        print(f"  - {f}")

    return saved_files


def create_merged_figure(results_dir: str, output_prefix: str = None):
    """Create a single merged figure with key panels in 3x3 grid.

    Layout:
        Row 1: KD distribution, Permeability distribution, Quality scatter
        Row 2: AF3 iPTM, Gnina CNN, Boltz-2 probability
        Row 3: Composite score, Top designs table, Timeline
    """
    results_dir = Path(results_dir)
    if output_prefix is None:
        output_prefix = str(results_dir / "helmgpt_summary")

    set_pub_plot_context(context="talk")
    df = load_helmgpt_results(results_dir)
    if df.empty:
        print("Error: No design metrics found in", results_dir)
        return None

    fig = plt.figure(figsize=(15, 13))

    # Row 1
    ax1 = fig.add_subplot(3, 3, 1); prettify_ax(ax1)
    ax2 = fig.add_subplot(3, 3, 2); prettify_ax(ax2)
    ax3 = fig.add_subplot(3, 3, 3); prettify_ax(ax3)
    # Row 2
    ax4 = fig.add_subplot(3, 3, 4); prettify_ax(ax4)
    ax5 = fig.add_subplot(3, 3, 5); prettify_ax(ax5)
    ax6 = fig.add_subplot(3, 3, 6); prettify_ax(ax6)
    # Row 3
    ax7 = fig.add_subplot(3, 3, 7); prettify_ax(ax7)
    ax8 = fig.add_subplot(3, 3, 8)
    ax9 = fig.add_subplot(3, 3, 9); prettify_ax(ax9)

    # Panel 1: KD
    _plot_violin_strip_ax(ax1, df['raw_kras_kd'].dropna().values,
                          'KD Distribution', 'KD (\u03bcM)',
                          (QUALITY_THRESHOLDS['kd_excellent'], QUALITY_THRESHOLDS['kd_good']),
                          higher_is_better=False, palette_idx=0)

    # Panel 2: Permeability
    if 'raw_permeability' in df.columns:
        _plot_violin_strip_ax(ax2, df['raw_permeability'].dropna().values,
                              'Permeability', 'log cm/s',
                              (QUALITY_THRESHOLDS['perm_good'], QUALITY_THRESHOLDS['perm_acceptable']),
                              higher_is_better=True, palette_idx=1)
    else:
        ax2.text(0.5, 0.5, 'No data', ha='center', va='center', transform=ax2.transAxes)
        ax2.axis('off')

    # Panel 3: Quality scatter
    scores = calculate_composite_score(df)
    scatter = ax3.scatter(df['raw_kras_kd'], df['raw_permeability'], c=scores,
                         cmap='viridis', s=40, alpha=0.8, edgecolors='white', linewidth=0.4)
    ax3.axvline(x=QUALITY_THRESHOLDS['kd_good'], color=CAT_PALETTE[2], linestyle='--', alpha=0.5)
    ax3.axhline(y=QUALITY_THRESHOLDS['perm_good'], color=CAT_PALETTE[2], linestyle='--', alpha=0.5)
    ax3.set_title('KD vs Permeability', fontsize=10, fontweight='bold', pad=8)
    ax3.set_xlabel('KD (\u03bcM)', fontsize=8)
    ax3.set_ylabel('Perm', fontsize=8)
    plt.colorbar(scatter, ax=ax3, shrink=0.8, label='Score')

    # Panel 4: AF3 iPTM
    if 'af3_iptm' in df.columns and df['af3_iptm'].notna().sum() > 0:
        vals = df['af3_iptm'].dropna().values
        _plot_violin_strip_ax(ax4, vals, 'AF3 iPTM', 'iPTM',
                              (QUALITY_THRESHOLDS['af3_iptm_good'],
                               QUALITY_THRESHOLDS['af3_iptm_acceptable']),
                              higher_is_better=True, palette_idx=2)
        ax4.set_ylim(min(vals) - 0.05, 1.05)
    else:
        ax4.text(0.5, 0.5, 'No AF3 data', ha='center', va='center', transform=ax4.transAxes)
        ax4.axis('off')

    # Panel 5: Gnina CNN
    if 'gnina_best_cnn' in df.columns and df['gnina_best_cnn'].notna().sum() > 0:
        _plot_violin_strip_ax(ax5, df['gnina_best_cnn'].dropna().values,
                              'Gnina CNN Affinity', 'pKd',
                              (QUALITY_THRESHOLDS['gnina_cnn_good'],
                               QUALITY_THRESHOLDS['gnina_cnn_acceptable']),
                              higher_is_better=True, palette_idx=3)
    else:
        ax5.text(0.5, 0.5, 'No Gnina data', ha='center', va='center', transform=ax5.transAxes)
        ax5.axis('off')

    # Panel 6: Boltz-2 probability
    if 'boltz_avg_prob' in df.columns and df['boltz_avg_prob'].notna().sum() > 0:
        vals = df['boltz_avg_prob'].dropna().values
        _plot_violin_strip_ax(ax6, vals, 'Boltz-2 Bind Prob', 'Probability',
                              (QUALITY_THRESHOLDS['boltz_avg_prob_good'],
                               QUALITY_THRESHOLDS['boltz_avg_prob_acceptable']),
                              higher_is_better=True, palette_idx=1)
        ax6.set_ylim(min(0, min(vals) - 0.05), 1.05)
    else:
        ax6.text(0.5, 0.5, 'No Boltz data', ha='center', va='center', transform=ax6.transAxes)
        ax6.axis('off')

    # Panel 7: Composite score
    _plot_violin_strip_ax(ax7, scores.values, 'Composite Score', 'Score',
                          (0.7, 0.5), higher_is_better=True, palette_idx=4)

    # Panel 8: Top designs table (three-line style)
    ax8.axis('off')
    ax8.set_title('Top Designs', fontsize=10, fontweight='bold', pad=8)

    df_t = df.copy()
    df_t['score'] = scores
    col_defs = [('design_id', 'ID')]
    for col, h in [('raw_kras_kd', 'KD'), ('af3_iptm', 'iPTM'), ('gnina_best_cnn', 'CNN')]:
        if col in df_t.columns:
            col_defs.append((col, h))
    col_defs.append(('score', 'Score'))

    df_top = df_t.sort_values('score', ascending=False).head(6).reset_index(drop=True)
    n_rows = len(df_top) + 1
    n_cols = len(col_defs)

    table = ax8.table(cellText=[['']*n_cols for _ in range(n_rows)],
                     loc='center', cellLoc='center', bbox=[0.0, 0.05, 1.0, 0.9])
    for j, (col, header) in enumerate(col_defs):
        cell = table[(0, j)]
        cell.set_text_props(text=header, fontweight='bold', fontsize=8)
        cell.set_facecolor('white')

    for i, (_, row) in enumerate(df_top.iterrows()):
        for j, (col, h) in enumerate(col_defs):
            cell = table[(i+1, j)]
            val = row[col]
            text = str(val) if col == 'design_id' else ('-' if pd.isna(val) else f'{val:.2f}')
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
    line_kw = dict(color='black', linewidth=1.0, transform=ax8.transAxes, clip_on=False)
    ax8.plot([xl, xr], [yt, yt], **line_kw)
    ax8.plot([xl, xr], [yt - rh, yt - rh], **line_kw)
    ax8.plot([xl, xr], [yb, yb], **line_kw)

    # Panel 9: Timeline
    ax9.set_title('Timeline', fontsize=10, fontweight='bold', pad=8)
    steps = [
        {'name': 'RL Opt.', 'start': 0, 'duration': 60},
        {'name': 'Filter', 'start': 60, 'duration': 5},
        {'name': 'Boltz-2', 'start': 65, 'duration': 15},
        {'name': 'AF3', 'start': 65, 'duration': 20},
        {'name': 'Gnina', 'start': 85, 'duration': 15},
    ]
    total_time = max(s['start'] + s['duration'] for s in steps)
    colors_t = [CAT_PALETTE[i % len(CAT_PALETTE)] for i in range(len(steps))]
    y_pos_t = list(range(len(steps)-1, -1, -1))
    for i, (step, yp) in enumerate(zip(steps, y_pos_t)):
        ax9.barh(yp, step['duration'], left=step['start'], height=0.6,
                color=colors_t[i], edgecolor='white', linewidth=0.5)
        ax9.text(-0.5, yp, step['name'], ha='right', va='center', fontsize=7)
    ax9.barh(-1, total_time, left=0, height=0.6, color=GRAY, alpha=0.8)
    ax9.text(-0.5, -1, f"~{total_time/60:.1f}h", ha='right', va='center',
             fontsize=7, fontweight='bold')
    ax9.set_xlabel('Time (min)', fontsize=8)
    ax9.set_xlim(-1, total_time * 1.1)
    ax9.set_ylim(-2, len(steps))
    ax9.set_yticks([])
    ax9.xaxis.grid(True, linestyle='--', alpha=0.4)
    ax9.spines['left'].set_visible(False)

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
        description='Generate HELM-GPT KRAS binder design visualization figures')
    parser.add_argument('results_dir', type=str,
                        help='Path to pipeline results directory')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='Output prefix (default: results_dir/helmgpt)')
    parser.add_argument('--merged', '-m', action='store_true',
                        help='Create merged 3x3 summary figure instead of separate figures')

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
