import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
from sklearn.decomposition import PCA
from sklearn.preprocessing import RobustScaler, StandardScaler
from sklearn.linear_model import LinearRegression, Lasso
from sklearn.metrics import r2_score
from scipy.stats import ttest_ind
from pathlib import Path
import sys
import argparse
import warnings

warnings.filterwarnings('ignore')

# --- HELPER FUNCTIONS FOR FUNCTION GEOMETRY ---
def calculate_gini(array):
    if not array: return 0.0
    array = np.array(array, dtype=np.float64)
    if np.sum(array) == 0: return 0.0
    array = np.sort(array)
    index = np.arange(1, array.shape[0] + 1)
    n = array.shape[0]
    return ((np.sum((2 * index - n  - 1) * array)) / (n * np.sum(array)))

def parse_concat_vector(val):
    if not val or pd.isna(val): return []
    try: return [float(x) for x in str(val).split(',')]
    except Exception: return []

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
OUTPUT_DIR = SCRIPT_DIR / "analyses_ridgeplots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = SCRIPT_DIR / "data" / "gitgalaxy_master.db"

THREAT_LABELS = {1: "1: Botnet", 2: "2: Stealer", 3: "3: Dropper", 4: "4: Infector"}
THREAT_PALETTE = {1: "#0072B2", 2: "#E69F00", 3: "#D55E00", 4: "#CC79A7"}

def run_master_suite(target_phase=None):
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        sys.exit(1)

    print("📡 Connecting to GitGalaxy Master Database...")
    conn = sqlite3.connect(DB_PATH)
    
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(galactic_census)")
    all_cols = [row[1] for row in cursor.fetchall()]
    
    cluster_cols = sorted([c for c in all_cols if c.startswith('arch_cluster_')], key=lambda x: int(x.split('_')[-1]))
    num_clusters = len(cluster_cols)
    core_cols = [c for c in all_cols if c.startswith('core_')]
    risk_cols = [c for c in all_cols if c.startswith('risk_')]
    design_cols = [c for c in all_cols if c.startswith('design_')]
    
    telemetry_cols = [
        'control_flow_ratio', 'direct_upstream', 'direct_downstream',
        'total_upstream', 'total_downstream', 'max_func_complexity', 'avg_func_args', 'raw_churn_freq'
    ]
    
    print(f"🔍 Detected K={num_clusters} physics engine, {len(core_cols)} core, {len(design_cols)} design, and {len(risk_cols)} risk dimensions.")

    query = """
        SELECT 
            c.*,
            COUNT(f.id) as real_function_count,
            AVG(f.loc) as real_avg_func_loc,
            AVG(f.complexity) as real_avg_func_complexity,
            GROUP_CONCAT(f.complexity) as func_complexity_vector
        FROM galactic_census c
        LEFT JOIN galactic_functions f ON c.id = f.file_id
        WHERE c.coding_loc > 0 AND c.archetype LIKE 'Cluster %'
        GROUP BY c.id
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Calculate advanced function geometries in memory
    df['parsed_vector'] = df['func_complexity_vector'].apply(parse_concat_vector)
    df['complexity_gini'] = df.apply(lambda row: calculate_gini(row['parsed_vector']) if row['real_function_count'] > 1 else 0.0, axis=1)
    df['func_internal_density'] = df['real_avg_func_complexity'] / df['real_avg_func_loc'].replace(0, 1)

    if df.empty:
        print("❌ No valid data found in the database.")
        return
        
    print(f"🌌 Extracted {len(df):,} structural vectors for analysis.")

    # ==============================================================================
    # 0. GLOBAL PREPROCESSING (Always runs to build the physics foundations)
    # ==============================================================================
    df['log_logic_loc'] = np.log1p(df['logic_loc'].fillna(0))
    df['log_churn'] = np.log1p(df['raw_churn_freq'].fillna(0))
    df['log_max_func_complexity'] = np.log1p(df['max_func_complexity'].fillna(0))
    df['log_avg_func_args'] = np.log1p(df['avg_func_args'].fillna(0))
    df['log_direct_upstream'] = np.log1p(df['direct_upstream'].fillna(0))
    df['log_direct_downstream'] = np.log1p(df['direct_downstream'].fillna(0))
    df['log_total_upstream'] = np.log1p(df['total_upstream'].fillna(0))
    df['log_total_downstream'] = np.log1p(df['total_downstream'].fillna(0))

    df['cluster_id'] = df['archetype'].str.extract(r'Cluster (\d+)').astype(int)
    df['cluster_display'] = 'Cluster ' + df['cluster_id'].astype(str)
    
    cluster_matrix = df[cluster_cols].to_numpy()
    cluster_ids = df['cluster_id'].to_numpy()
    df['global_drift'] = cluster_matrix[np.arange(len(df)), cluster_ids]
    df['z_score'] = df.groupby('archetype')['global_drift'].transform(lambda x: (x - x.mean()) / x.std())


    # ==============================================================================
    # 1. EUCLIDEAN DISTANCE (ASSIGNED CLUSTER HEALTH)
    # ==============================================================================
    if target_phase in [None, 1]:
        print("\n" + "="*105)
        print(" 📊 PHASE 1: ASSIGNED ARCHETYPE DRIFT (EUCLIDEAN) STATISTICS")
        print("="*105)

        stats = df.groupby('archetype')['global_drift'].describe()
        
        print(f"{'Archetype':<45} | {'Count':<9} | {'Mean':<7} | {'StdDev':<7} | {'Min':<7} | {'Median':<7} | {'Max':<7}")
        print("-" * 105)

        for index, row in stats.iterrows():
            clean_name = index[:42] + "..." if len(index) > 45 else index
            print(f"{clean_name:<45} | {int(row['count']):<9,d} | {row['mean']:<7.3f} | {row['std']:<7.3f} | {row['min']:<7.3f} | {row['50%']:<7.3f} | {row['max']:<7.3f}")


    # ==============================================================================
    # 2. ARCHETYPE PROFILING (LANGUAGES & EXEMPLARS)
    # ==============================================================================
    if target_phase in [None, 2]:
        print("\n" + "="*120)
        print(" 🧬 PHASE 2: ARCHETYPE PROFILING (LANGUAGES & FULL EXEMPLARS)")
        print("="*120)

        for cluster_id in sorted(df['cluster_id'].unique()):
            subset = df[df['cluster_id'] == cluster_id]
            arch_name = subset['archetype'].iloc[0]

            lang_counts = subset['language'].value_counts(normalize=True) * 100
            top_langs = ", ".join([f"{l} ({p:.1f}%)" for l, p in lang_counts.head(4).items()])

            exemplars = subset.nsmallest(2, 'z_score')
            drifters = subset.nlargest(2, 'z_score')

            print(f"\n🧪 {arch_name} | Total Files: {len(subset):,}")
            print(f"   🗣️ Top Languages: {top_langs}")
            print(f"   💎 Purest Exemplars (Lowest Z-Score):")
            for _, r in exemplars.iterrows():
                print(f"      - {r['file_name']} (Z: {r['z_score']:+.2f}) [{r['language']}] -> {r['file_path']}")
            print(f"   👽 Extreme Drifters (Highest Z-Score):")
            for _, r in drifters.iterrows():
                print(f"      - {r['file_name']} (Z: {r['z_score']:+.2f}) [{r['language']}] -> {r['file_path']}")


    # ==============================================================================
    # 3. ARCHETYPE VALIDATION & DRIFT HEALTH (OUTLIER DECAY CURVE)
    # ==============================================================================
    if target_phase in [None, 3]:
        print("\n" + "="*120)
        print(" 🔭 PHASE 3: ARCHETYPE Z-SCORE HEALTH (OUTLIER DECAY CURVE)")
        print("="*120)
        
        print(f"{'Archetype':<50} | {'Total Files':<11} | {'Z > 0.25':<8} | {'Z > 0.50':<8} | {'Z > 1.0':<8} | {'Z > 2.0':<8} | {'Z > 3.0':<8}")
        print("-" * 120)
        for arch in sorted(df['archetype'].unique()):
            arch_df = df[df['archetype'] == arch]
            total = len(arch_df)
            
            z_025 = len(arch_df[arch_df['z_score'] > 0.25]) / total * 100
            z_050 = len(arch_df[arch_df['z_score'] > 0.50]) / total * 100
            z_100 = len(arch_df[arch_df['z_score'] > 1.0]) / total * 100
            z_200 = len(arch_df[arch_df['z_score'] > 2.0]) / total * 100
            z_300 = len(arch_df[arch_df['z_score'] > 3.0]) / total * 100
            
            clean_name = arch[:47] + "..." if len(arch) > 50 else arch
            print(f"{clean_name:<50} | {total:<11,d} | {z_025:>5.1f}%  | {z_050:>5.1f}%  | {z_100:>5.1f}%  | {z_200:>5.1f}%  | {z_300:>5.1f}%")

        plt.figure(figsize=(18, 10))
        sns.set_theme(style="darkgrid")
        plot_df = df.sort_values(by='cluster_id')
        sns.violinplot(data=plot_df, y='archetype', x='z_score', hue='archetype', palette="magma", inner="quartile", legend=False)
        plt.title(f"Archetype Z-Score Distributions (K={num_clusters} Physics)", fontsize=16, pad=20)
        plt.axvline(0, color='red', linestyle='--', alpha=0.7)
        plt.axvline(3, color='orange', linestyle=':', alpha=0.7)
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / "archetype_zscore_distribution.png", dpi=300)


    # ==============================================================================
    # 4. THREAT VS. BASELINE DRIFT (MALWARE DISTRIBUTION) + STATISTICAL TEST
    # ==============================================================================
    if target_phase in [None, 4]:
        print("\n" + "="*120)
        print(" 🦠 PHASE 4: THREAT VS. BASELINE DRIFT (POPULATION DIFFERENCE TEST)")
        print("="*120)

        safe_df = df[df['threat_class'] == 0]
        malware_df = df[df['threat_class'] > 0]
        
        if not malware_df.empty:
            print(f"{'Archetype':<25} | {'Safe Files':<12} | {'Malware Count':<15} | {'Safe Mean':<12} | {'Threat Mean':<13} | {'p-value (Welch)'}")
            print("-" * 120)
            
            for cluster_disp in sorted(df['cluster_display'].unique()):
                s_df = safe_df[safe_df['cluster_display'] == cluster_disp]
                m_df = malware_df[malware_df['cluster_display'] == cluster_disp]
                
                s_count = len(s_df)
                m_count = len(m_df)
                
                s_drift = s_df['global_drift'].dropna()
                m_drift = m_df['global_drift'].dropna()
                
                s_mean = s_drift.mean() if s_count > 0 else 0.0
                m_mean = m_drift.mean() if m_count > 0 else 0.0
                
                p_val_str = "N/A"
                sig_marker = ""
                if s_count >= 2 and m_count >= 2:
                    t_stat, p_val = ttest_ind(s_drift, m_drift, equal_var=False)
                    if p_val < 0.001:
                        p_val_str = "< 0.001"
                        sig_marker = "*** (Highly Sig)"
                    elif p_val < 0.01:
                        p_val_str = f"{p_val:.3f}"
                        sig_marker = "** (Sig)"
                    elif p_val < 0.05:
                        p_val_str = f"{p_val:.3f}"
                        sig_marker = "* (Sig)"
                    else:
                        p_val_str = f"{p_val:.3f}"
                        sig_marker = "ns (Not Sig)"
                
                vol_marker = "⚠️" if m_count > 50 else ""
                print(f"{cluster_disp:<25} | {s_count:<12,d} | {m_count:<15,d} | {s_mean:<12.3f} | {m_mean:<13.3f} | {p_val_str} {sig_marker} {vol_marker}")

            safe_sample = safe_df.sample(frac=1, random_state=42).groupby('cluster_display').head(2000)
            plt.figure(figsize=(14, 8))
            cluster_order = sorted(df['cluster_display'].unique())
            sns.stripplot(data=safe_sample, y='cluster_display', x='z_score', order=cluster_order, color="gray", size=3, alpha=0.15, jitter=0.3, zorder=1)
            sns.stripplot(data=malware_df, y='cluster_display', x='z_score', order=cluster_order, hue='threat_class', palette=THREAT_PALETTE, size=5, alpha=0.85, jitter=0.2, zorder=2)
            plt.axvline(0, color='black', linestyle='--')
            plt.axvline(3, color='red', linestyle=':')
            plt.title("Malware Drift vs. Healthy Code Baseline (With Population Significance)", fontsize=16, fontweight='bold', pad=20)
            plt.tight_layout()
            plt.savefig(OUTPUT_DIR / "multi_class_zscore_distribution.png", dpi=300)
        else:
            print("⏭️ No known malware found in database. Skipping Threat Radar.")


    # ==============================================================================
    # 5. 3D PCA GALAXY MAPPING
    # ==============================================================================
    if target_phase in [None, 5]:
        print("\n" + "="*80)
        print(" 🌌 PHASE 5: 3D PCA GALAXY COMPRESSION")
        print("="*80)

        safe_denom = df['logic_loc'].replace(0, np.nan).fillna(df['coding_loc']).replace(0, 1)    
        
        log_density_core_cols = []
        for col in core_cols:
            raw_density = (df[col].fillna(0) / safe_denom) * 100.0
            new_col = f"log_density_{col}"
            df[new_col] = np.log1p(raw_density.fillna(0.0))
            log_density_core_cols.append(new_col)

        telemetry_features = [
            'control_flow_ratio', 'log_logic_loc', 'log_direct_upstream', 'log_direct_downstream', 
            'log_total_upstream', 'log_total_downstream', 'log_max_func_complexity', 'log_avg_func_args', 'log_churn'
        ]

        pca_features = log_density_core_cols + telemetry_features

        plot_df = df.dropna(subset=pca_features).copy()
        X_scaled = RobustScaler().fit_transform(plot_df[pca_features])
        pca = PCA(n_components=3)
        pca_features_out = pca.fit_transform(X_scaled)
        
        variance = pca.explained_variance_ratio_ * 100
        print(f"   📊 Variance Explained: PCA 1 ({variance[0]:.1f}%), PCA 2 ({variance[1]:.1f}%), PCA 3 ({variance[2]:.1f}%)")
        print(f"   📉 Total 3D Compression Variance: {sum(variance):.1f}%")

        plot_df['PCA_X'] = pca_features_out[:, 0]
        plot_df['PCA_Y'] = pca_features_out[:, 1]
        plot_df['PCA_Z'] = pca_features_out[:, 2]

        MAX_POINTS_PER_CLUSTER = 2000
        sampled_dfs = []
        for cluster_id in sorted(plot_df['cluster_id'].unique()):
            sampled_dfs.append(plot_df[plot_df['cluster_id'] == cluster_id].sort_values('global_drift').head(MAX_POINTS_PER_CLUSTER))

        final_3d_df = pd.concat(sampled_dfs, ignore_index=True)
        fig = px.scatter_3d(final_3d_df, x='PCA_X', y='PCA_Y', z='PCA_Z', color='archetype', hover_name='file_name', color_discrete_sequence=px.colors.qualitative.Alphabet)
        fig.update_traces(marker=dict(size=3, opacity=0.7, line=dict(width=0)))
        fig.update_layout(scene=dict(bgcolor='rgb(20, 24, 34)'), paper_bgcolor='rgb(20, 24, 34)', margin=dict(l=0, r=0, b=0, t=50))
        fig.write_html(str(OUTPUT_DIR / "galaxy_pca_3d_map.html"))
        print(f"✅ Saved 3D Interactive Map to {OUTPUT_DIR.name}")


    # ==============================================================================
    # 6. EXPANDED SEARCH SPACE REGRESSION (LASSO FEATURE SELECTION)
    # ==============================================================================
    if target_phase in [None, 6]:
        print("\n" + "="*110)
        print(" 🎯 PHASE 6: EXPANDED NORMALIZATION REGRESSION (LASSO L1 PENALTY)")
        print("="*110)

        # 1. Use existing Risk Scores and New Geometries Directly
        expanded_predictors = risk_cols + ['complexity_gini', 'func_internal_density']

        d_logic = df['logic_loc'].replace(0, np.nan).fillna(1)
        raw_telemetry = ['direct_upstream', 'direct_downstream', 'total_upstream', 'total_downstream']
        
        # 2. Only normalize Raw Dependency Telemetry (No Double Dipping!)
        for col in raw_telemetry:
            log_name = f"log_{col}"
            df[log_name] = np.log1p(df[col].fillna(0))
            expanded_predictors.append(log_name)

            dens_name = f"{col}_per_logic_loc"
            df[dens_name] = df[col].fillna(0) / d_logic
            expanded_predictors.append(dens_name)

        # 3. Add Raw Churn
        df['log_churn'] = np.log1p(df['raw_churn_freq'].fillna(0))
        expanded_predictors.append('log_churn')

        # 4. The Non-Linearity Upgrade (Polynomial Expansion)
        # By squaring the features, we allow the LASSO algorithm to detect if 
        # the relationship between a metric and architectural drift is exponential.
        nonlinear_candidates = risk_cols + ['complexity_gini', 'func_internal_density', 'log_churn']
        for col in nonlinear_candidates:
            sq_name = f"{col}_sq"
            df[sq_name] = df[col] ** 2
            expanded_predictors.append(sq_name)

        df[expanded_predictors] = df[expanded_predictors].replace([np.inf, -np.inf], 0.0).fillna(0.0)

        print(f"{'Archetype':<25} | {'R² Score':<10} | {'Primary Drift Drivers (Lasso Selected)'}")
        print("-" * 110)

        for cluster_id in sorted(df['cluster_id'].unique()):
            subset = df[df['cluster_id'] == cluster_id].copy()
            arch_name = subset['cluster_display'].iloc[0]
            
            if len(subset) < 50: continue
                
            X_raw = subset[expanded_predictors]
            y_actual = subset['global_drift'].fillna(0.0)
            
            if np.std(y_actual) == 0: continue
                
            valid_cols = [col for col in expanded_predictors if np.std(X_raw[col]) > 0]
            if not valid_cols: continue
                
            X_scaled_reg = StandardScaler().fit_transform(X_raw[valid_cols])
            
            # L1 Penalty handles multicollinearity across the 4 normalization dimensions
            model = Lasso(alpha=0.02, max_iter=5000, random_state=42).fit(X_scaled_reg, y_actual)
            y_pred = model.predict(X_scaled_reg)
            r2 = r2_score(y_actual, y_pred)
            
            coefficients = list(zip(valid_cols, model.coef_))
            active_coeffs = [(n, c) for n, c in coefficients if abs(c) > 0.01]
            # Sort by absolute magnitude (strongest impact first)
            active_coeffs.sort(key=lambda item: abs(item[1]), reverse=True)
            
            def get_base_name(n):
                name = n.replace('risk_', '').replace('log_base_', '')
                if name.endswith('_sq'): return name[:-3]
                if name.endswith('_cb'): return name[:-3]
                return name

            def clean_name(n):
                name = n.replace('risk_', '').replace('log_base_', '')
                if name.endswith('_sq'):
                    return f"({name[:-3]})^2"
                if name.endswith('_cb'):
                    return f"({name[:-3]})^3"
                return name
                
            if not active_coeffs:
                top_equation = "No distinct linear drivers survived L1 regularization."
            else:
                # Deduplication Filter: Only allow the strongest version of a feature
                unique_coeffs = []
                seen_bases = set()
                
                for name, coef in active_coeffs:
                    base = get_base_name(name)
                    if base not in seen_bases:
                        seen_bases.add(base)
                        unique_coeffs.append((name, coef))
                        if len(unique_coeffs) == 4:
                            break
                            
                top_equation = " + ".join([f"({coef:.2f} * {clean_name(name)})" for name, coef in unique_coeffs])
            
            print(f"{arch_name:<25} | {r2:<10.3f} | {top_equation}")
            
            sns.set_theme(style="darkgrid")
            plt.figure(figsize=(10, 8))
            if len(subset) > 5000:
                plot_idx = np.random.choice(len(y_actual), 5000, replace=False)
                sns.scatterplot(x=y_actual.iloc[plot_idx], y=y_pred[plot_idx], alpha=0.4, color='#3498db', edgecolor='none', s=30)
            else:
                sns.scatterplot(x=y_actual, y=y_pred, alpha=0.4, color='#3498db', edgecolor='none', s=30)
                
            plt.plot([y_actual.min(), y_actual.max()], [y_actual.min(), y_actual.max()], color='#e74c3c', linestyle='--')
            plt.title(f"Predicting Architectural Drift via Lasso Feature Selection\n{arch_name}", fontsize=14, weight='bold', pad=20)
            plt.tight_layout()
            plt.savefig(OUTPUT_DIR / f"cluster_{cluster_id}_predictive_scatter.png", dpi=150, bbox_inches='tight')
            plt.close()

    if target_phase is None:
        print("\n" + "="*80)
        print(" 🚀 MASTER SUITE ANALYSIS COMPLETE")
        print("="*80 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GitGalaxy Archetype Analysis Suite")
    parser.add_argument('--phase', type=int, choices=[1, 2, 3, 4, 5, 6], default=None,
                        help="Specify a single phase to run (1-6). If omitted, runs all phases.")
    args = parser.parse_args()
    
    run_master_suite(target_phase=args.phase)