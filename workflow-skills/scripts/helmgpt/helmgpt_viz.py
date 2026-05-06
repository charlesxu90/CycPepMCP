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
10. Radar Chart - Top 5 candidates across normalized metrics
11. Metrics Table - Top designs with three-line academic style
12. Execution Timeline - Gantt chart of pipeline phases

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

# Centralized PASS-gate thresholds (single source of truth: benchmark/configs/workflows.yaml).
# Each entry is (excellent_value, gate_value, label); gate_value is the primary PASS gate,
# excellent_value is the tighter context line.
import sys as _sys
from pathlib import Path as _Path
_HERE = _Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / "benchmark" / "configs" / "thresholds.py").is_file():
        if str(_p) not in _sys.path:
            _sys.path.insert(0, str(_p))
        break
from benchmark.configs import thresholds as cfg  # noqa: E402

_HG_PRIMARY = cfg.HELMGPT_PASS_GATE.primary
_HG_EXCELLENT = cfg.HELMGPT_PASS_GATE.excellent

WORKFLOW_THRESHOLDS = {
    'kd':         (_HG_EXCELLENT['kd_um_max'],         _HG_PRIMARY['kd_um_max'],         f"Workflow gate KD<{_HG_PRIMARY['kd_um_max']} uM (PASS, lower is better)"),
    'perm':       (_HG_EXCELLENT['perm_logpapp_min'],  _HG_PRIMARY['perm_logpapp_min'],  f"Workflow gate perm>{_HG_PRIMARY['perm_logpapp_min']} log cm/s (PASS)"),
    'boltz_aff':  (_HG_EXCELLENT['boltz_aff_min'],     _HG_PRIMARY['boltz_aff_min'],     f"Workflow gate Boltz-2 affinity>{_HG_PRIMARY['boltz_aff_min']}"),
    'boltz_prob': (_HG_EXCELLENT['boltz_prob_min'],    _HG_PRIMARY['boltz_prob_min'],    f"Workflow gate Boltz-2 binding prob>{_HG_PRIMARY['boltz_prob_min']}"),
    'boltz_iptm': (_HG_EXCELLENT['boltz_iptm_min'],    _HG_PRIMARY['boltz_iptm_min'],    f"Workflow gate Boltz-2 ligand iPTM>{_HG_PRIMARY['boltz_iptm_min']}"),
    'af3_iptm':   (_HG_EXCELLENT['af3_iptm_min'],      _HG_PRIMARY['af3_iptm_min'],      f"Workflow gate AF3 iPTM>{_HG_PRIMARY['af3_iptm_min']}"),
    'af3_plddt':  (_HG_EXCELLENT['af3_plddt_min'],     _HG_PRIMARY['af3_plddt_min'],     f"Workflow gate AF3 pLDDT>{_HG_PRIMARY['af3_plddt_min']}"),
    'gnina_cnn':  (_HG_EXCELLENT['gnina_cnn_min'],     _HG_PRIMARY['gnina_cnn_min'],     f"Workflow gate Gnina CNN pKd>{_HG_PRIMARY['gnina_cnn_min']}"),
    'gnina_vina': (_HG_EXCELLENT['gnina_vina_max'],    _HG_PRIMARY['gnina_vina_max'],    f"Workflow gate Gnina Vina<{_HG_PRIMARY['gnina_vina_max']} kcal/mol"),
}

EXCELLENT_LABEL = {
    'kd':         'Excellent KD<1 μM',
    'perm':       'Excellent perm>-5.0',
    'boltz_aff':  'Excellent Boltz-2 affinity>0.5',
    'boltz_prob': 'Excellent Boltz-2 prob>0.6',
    'boltz_iptm': 'Excellent Boltz-2 iPTM>0.80',
    'af3_iptm':   'Excellent AF3 iPTM>0.80',
    'af3_plddt':  'Excellent AF3 pLDDT>0.85',
    'gnina_cnn':  'Excellent Gnina CNN pKd>7.0',
    'gnina_vina': 'Excellent Gnina Vina<-8.0',
}

# Back-compat: scalar dict keyed like the older code expected.
QUALITY_THRESHOLDS = {
    'kd_excellent': WORKFLOW_THRESHOLDS['kd'][0],
    'kd_good': WORKFLOW_THRESHOLDS['kd'][1],
    'kd_acceptable': 100,
    'perm_excellent': WORKFLOW_THRESHOLDS['perm'][0],
    'perm_good': WORKFLOW_THRESHOLDS['perm'][1],
    'perm_acceptable': -6.5,
    'af3_iptm_excellent': WORKFLOW_THRESHOLDS['af3_iptm'][0],
    'af3_iptm_good': WORKFLOW_THRESHOLDS['af3_iptm'][1],
    'af3_iptm_acceptable': 0.40,
    'boltz_avg_aff_good': WORKFLOW_THRESHOLDS['boltz_aff'][1],
    'boltz_avg_aff_acceptable': -0.3,
    'boltz_avg_prob_good': WORKFLOW_THRESHOLDS['boltz_prob'][1],
    'boltz_avg_prob_acceptable': 0.4,
    'gnina_cnn_excellent': WORKFLOW_THRESHOLDS['gnina_cnn'][0],
    'gnina_cnn_good': WORKFLOW_THRESHOLDS['gnina_cnn'][1],
    'gnina_cnn_acceptable': 5.0,
    'gnina_vina_excellent': WORKFLOW_THRESHOLDS['gnina_vina'][0],
    'gnina_vina_good': WORKFLOW_THRESHOLDS['gnina_vina'][1],
    'gnina_vina_acceptable': -5.0,
}


def _thr(metric):
    """Return (excellent_value, gate_value, gate_label, excellent_label)."""
    e, g, gl = WORKFLOW_THRESHOLDS[metric]
    return e, g, gl, EXCELLENT_LABEL[metric]


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

def _load_phase3_ranking(results_dir: Path) -> pd.DataFrame:
    """Load case3 phase3_final_ranking.csv (single-table format) and rename
    its columns into the schema this viz script expects."""
    fp = results_dir / 'phase3_final_ranking.csv'
    if not fp.exists():
        return None
    df = pd.read_csv(fp)
    rename = {
        'kd_um':                            'raw_kras_kd',
        'aff_affinity_pred_value':          'boltz_avg_aff',
        'aff_affinity_probability_binary':  'boltz_avg_prob',
        'conf_iptm':                        'boltz_ligand_iptm',
        'conf_complex_plddt':               'boltz_complex_plddt',
        'cnn_affinity':                     'gnina_best_cnn',
        'vina_affinity':                    'gnina_best_vina',
    }
    for src, dst in rename.items():
        if src in df.columns and dst not in df.columns:
            df[dst] = df[src]
    # Use Boltz iPTM as AF3 iPTM substitute when AF3 wasn't run.
    if 'af3_iptm' not in df.columns and 'boltz_ligand_iptm' in df.columns:
        df['af3_iptm'] = df['boltz_ligand_iptm']
    if 'design_id' not in df.columns:
        rk = df['final_rank'] if 'final_rank' in df.columns else df.index + 1
        df['design_id'] = [f'c{int(r):02d}' for r in rk]
    print(f"Loaded phase3 ranking from {fp} ({len(df)} designs)")
    return df


def load_helmgpt_results(results_dir: Path) -> pd.DataFrame:
    """Load and merge all HELM-GPT pipeline results into a single DataFrame."""
    results_dir = Path(results_dir)

    # 0. Prefer the case3-style consolidated phase3 ranking CSV.
    df = _load_phase3_ranking(results_dir)
    if df is not None:
        return df

    # 1. Load candidate CSV (legacy / multi-file layout)
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
    """Composite quality score (0-1) for ranking designs.

    Prefers the canonical `composite` column written by `postprocess_phase3.py`
    (workflow-spec weights: KD 0.20, perm 0.15, Boltz aff 0.15, Boltz prob 0.10,
    iPTM 0.10, Gnina CNN 0.15, Gnina Vina 0.15). Falls back to a viz-internal
    recompute when that column isn't present (legacy / partial runs).
    """
    if 'composite' in df.columns and df['composite'].notna().any():
        return df['composite'].astype(float)

    # Fallback: weights match the workflow doc Phase-3 Composite Scoring table.
    scores = pd.Series(0.0, index=df.index)

    def _norm(s, lo, hi, higher_better=True):
        n = (s - lo) / (hi - lo) if hi != lo else 0.5
        n = np.clip(n, 0, 1)
        return n if higher_better else 1 - n

    spec = [
        ('raw_kras_kd',     0.20, False),
        ('raw_permeability',0.15, True),
        ('boltz_avg_aff',   0.15, True),
        ('boltz_avg_prob',  0.10, True),
        ('af3_iptm',        0.10, True),
        ('gnina_best_cnn',  0.15, True),
        ('gnina_best_vina', 0.15, False),
    ]
    for col, w, higher in spec:
        if col not in df.columns:
            continue
        vals = df[col].fillna(df[col].min() if higher else df[col].max())
        scores += w * _norm(vals, vals.min(), vals.max(), higher_better=higher)

    return scores


# ============================================================
# Core violin + strip plot helper
# ============================================================

def plot_violin_strip(values, title, ylabel, thresholds, higher_is_better=True,
                      palette_idx=0, output_path=None, figsize=FIGSIZE,
                      threshold_labels=('Excellent (tighter)', 'Workflow gate')):
    """Violin + strip + box distribution plot with rfpeptides-style threshold rendering.

    `thresholds = (excellent, gate)`. The `gate` line is the workflow's PASS
    cutoff (solid, prominent); `excellent` is a tighter context line (dashed,
    faint). `threshold_labels` populates the legend; the value is appended.
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

    # Workflow gate (solid prominent) + excellent context (dashed faint)
    ax.axhline(y=thresholds[1], color=CAT_PALETTE[1], linestyle='-', alpha=0.85,
               linewidth=1.4, label=f"{threshold_labels[1]} ({thresholds[1]:g})")
    ax.axhline(y=thresholds[0], color=CAT_PALETTE[2], linestyle='--', alpha=0.55,
               linewidth=1.0, label=f"{threshold_labels[0]} ({thresholds[0]:g})")
    ax.legend(loc='lower left', fontsize=7, frameon=True, framealpha=0.9)

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
                           palette_idx=0,
                           threshold_labels=('Excellent', 'Workflow gate')):
    """Internal: violin + strip on a given axis (for merged figure), with rfpeptides line style."""
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

def plot_kd_distribution(df, output_path=None):
    """Plot 1: KRAS KD distribution."""
    values = df['raw_kras_kd'].dropna().values
    e, g, gl, el = _thr('kd')
    return plot_violin_strip(
        values, 'KRAS Binding Affinity (KD)',
        'KD (\u03bcM, lower is better)',
        (e, g),
        higher_is_better=False, palette_idx=0, output_path=output_path,
        threshold_labels=(el, gl))


def plot_permeability_distribution(df, output_path=None):
    """Plot 2: Permeability distribution."""
    values = df['raw_permeability'].dropna().values
    e, g, gl, el = _thr('perm')
    return plot_violin_strip(
        values, 'Membrane Permeability',
        'log Perm (cm/s, higher is better)',
        (e, g),
        higher_is_better=True, palette_idx=1, output_path=output_path,
        threshold_labels=(el, gl))


def plot_quality_scatter(df, output_path=None):
    """Plot 3: Scatter plot of KD vs Permeability colored by composite score."""
    fig, ax = simple_ax(figsize=(6, 5))
    scores = calculate_composite_score(df)

    scatter = ax.scatter(df['raw_kras_kd'], df['raw_permeability'], c=scores,
                        cmap='viridis', s=80, alpha=0.8, edgecolors='white', linewidth=0.5)

    kd_gate = WORKFLOW_THRESHOLDS['kd'][1]
    perm_gate = WORKFLOW_THRESHOLDS['perm'][1]

    # Shaded PASS region (KD<gate AND perm>gate)
    rect_good = Rectangle((0, perm_gate), kd_gate, 0 - perm_gate,
                          linewidth=0, facecolor=CAT_PALETTE[2], alpha=0.12)
    ax.add_patch(rect_good)

    ax.axvline(x=kd_gate, color=CAT_PALETTE[2], linestyle='-', alpha=0.85,
               linewidth=1.4, label=f"Workflow gate KD<{kd_gate:g} \u03bcM")
    ax.axhline(y=perm_gate, color=CAT_PALETTE[1], linestyle='-', alpha=0.85,
               linewidth=1.4, label=f"Workflow gate perm>{perm_gate:g}")
    ax.legend(loc='upper right', fontsize=7, frameon=True, framealpha=0.9)

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
    """Plot 4: AF3 iPTM distribution (or Boltz-2 iPTM proxy when AF3 unavailable)."""
    col = 'af3_iptm' if 'af3_iptm' in df.columns else (
        'boltz_ligand_iptm' if 'boltz_ligand_iptm' in df.columns else None)
    if col is None:
        return None
    values = df[col].dropna().values
    if len(values) == 0:
        return None
    e, g, gl, el = _thr('af3_iptm' if col == 'af3_iptm' else 'boltz_iptm')
    title = 'AlphaFold3 Interface iPTM' if col == 'af3_iptm' else 'Boltz-2 Interface iPTM (AF3 substitute)'
    fig = plot_violin_strip(
        values, title, 'iPTM (higher is better)',
        (e, g),
        higher_is_better=True, palette_idx=2, output_path=output_path,
        threshold_labels=(el, gl))
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
    e, g, gl, el = _thr('gnina_cnn')
    return plot_violin_strip(
        values, 'Gnina CNN Affinity', 'pKd (higher is better)',
        (e, g),
        higher_is_better=True, palette_idx=3, output_path=output_path,
        threshold_labels=(el, gl))


def plot_gnina_vina_distribution(df, output_path=None):
    """Plot 6: Gnina Vina score distribution."""
    if 'gnina_best_vina' not in df.columns:
        return None
    values = df['gnina_best_vina'].dropna().values
    if len(values) == 0:
        return None
    e, g, gl, el = _thr('gnina_vina')
    return plot_violin_strip(
        values, 'Gnina Vina Score', 'kcal/mol (more negative is better)',
        (e, g),
        higher_is_better=False, palette_idx=4, output_path=output_path,
        threshold_labels=(el, gl))


def plot_boltz_affinity_distribution(df, output_path=None):
    """Plot 7: Boltz-2 ensemble affinity distribution."""
    if 'boltz_avg_aff' not in df.columns:
        return None
    values = df['boltz_avg_aff'].dropna().values
    if len(values) == 0:
        return None
    e, g, gl, el = _thr('boltz_aff')
    return plot_violin_strip(
        values, 'Boltz-2 Ensemble Affinity', 'Avg Affinity (higher is better)',
        (e, g),
        higher_is_better=True, palette_idx=0, output_path=output_path,
        threshold_labels=(el, gl))


def plot_boltz_probability_distribution(df, output_path=None):
    """Plot 8: Boltz-2 binding probability distribution."""
    if 'boltz_avg_prob' not in df.columns:
        return None
    values = df['boltz_avg_prob'].dropna().values
    if len(values) == 0:
        return None
    e, g, gl, el = _thr('boltz_prob')
    fig = plot_violin_strip(
        values, 'Boltz-2 Binding Probability', 'Avg Probability (higher is better)',
        (e, g),
        higher_is_better=True, palette_idx=1, output_path=output_path,
        threshold_labels=(el, gl))
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


def plot_radar_chart(df, output_path=None, top_n=5):
    """Spider/radar chart: top-N candidates across all available composite metrics.

    Each axis is min-max normalized within the full candidate set so every
    metric uses the full 0-1 radial range (otherwise tightly clustered metrics
    like KD~7-9 μM collapse to a single sliver). Lower-is-better metrics (KD,
    Vina) are inverted so "outer = better" everywhere. A faint median-of-set
    reference polygon is drawn for context.
    """
    # (column, label, higher_is_better) — Boltz aff/prob excluded by request;
    # they're noisy ensemble scores that overlap with Gnina + iPTM info.
    metric_defs = [
        ('raw_kras_kd',      'KD',          False),
        ('raw_permeability', 'Perm',        True),
        ('af3_iptm',         'iPTM',        True),  # AF3 iPTM, or Boltz iPTM proxy
        ('gnina_best_cnn',   'Gnina CNN',   True),
        ('gnina_best_vina',  'Gnina Vina',  False),
    ]
    available = [(c, l, h) for c, l, h in metric_defs if c in df.columns]
    if len(available) < 3:
        print("Radar chart: fewer than 3 metrics available, skipping")
        return None

    # Min-max normalize across the FULL dataframe so each axis has range.
    df_n = pd.DataFrame(index=df.index)
    for col, label, higher in available:
        s = df[col].astype(float)
        lo, hi = s.min(), s.max()
        if pd.isna(lo) or pd.isna(hi) or hi == lo:
            df_n[label] = 0.5
        else:
            n = (s - lo) / (hi - lo)
            df_n[label] = n if higher else 1.0 - n

    # Composite -> top-N (only candidates with all metrics non-NaN qualify)
    df_work = df.copy()
    df_work['_score'] = calculate_composite_score(df_work)
    mask = pd.Series(True, index=df_work.index)
    for col, _, _ in available:
        mask &= df_work[col].notna()
    top_idx = df_work[mask].sort_values('_score', ascending=False).head(top_n).index
    if len(top_idx) == 0:
        print("Radar chart: no candidates with all metrics, skipping")
        return None

    labels = [l for _, l, _ in available]
    n_metrics = len(labels)
    angles = np.linspace(0, 2 * np.pi, n_metrics, endpoint=False).tolist()
    angles += angles[:1]

    fig = plt.figure(figsize=(7.5, 6.5))
    ax = fig.add_subplot(111, polar=True)

    # Spider-web grid (polygons + spokes)
    grid_levels = [0.2, 0.4, 0.6, 0.8, 1.0]
    for level in grid_levels:
        ax.plot(angles, [level] * n_metrics + [level],
                color='gray', linewidth=0.8, alpha=0.35)
    for a in angles[:-1]:
        ax.plot([a, a], [0, 1], color='gray', linewidth=0.8, alpha=0.35)
    ax.yaxis.grid(False); ax.xaxis.grid(False)

    # Median-of-set reference polygon (dashed gray)
    median_vals = df_n.median().reindex(labels).tolist()
    ax.plot(angles, median_vals + median_vals[:1], '--',
            color='gray', linewidth=1.0, alpha=0.55, label='Set median')
    ax.fill(angles, median_vals + median_vals[:1], color='gray', alpha=0.05)

    # Top-N polygons in colorblind palette
    radar_colors = sns.color_palette('colorblind', n_colors=len(top_idx))
    for i, idx in enumerate(top_idx):
        values = df_n.loc[idx, labels].tolist()
        values += values[:1]
        design_id = df_work.loc[idx].get('design_id', f'#{i}')
        ax.plot(angles, values, 'o-', linewidth=1.6, color=radar_colors[i],
                label=str(design_id), markersize=4.5)
        ax.fill(angles, values, alpha=0.10, color=radar_colors[i])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, 1)
    ax.set_yticks(grid_levels)
    ax.set_yticklabels(['0.2', '0.4', '0.6', '0.8', '1.0'], fontsize=7, color='gray')
    ax.set_title(f'Top {len(top_idx)} Candidates — Multi-Metric Profile\n'
                 '(per-axis min-max within set; outer = better)',
                 fontsize=12, fontweight='bold', pad=18)
    ax.spines['polar'].set_visible(False)
    ax.legend(loc='center left', bbox_to_anchor=(1.18, 0.5), fontsize=8,
              frameon=True, framealpha=0.9)

    plt.tight_layout()
    if output_path:
        save_for_pub(fig, output_path)
        print(f"Saved: {output_path}.png, {output_path}.pdf")
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

    # Radar chart
    _save(plot_radar_chart(df, f"{output_prefix}_radar_chart"), "radar_chart")

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
