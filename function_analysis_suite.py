import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import sys
import warnings

warnings.filterwarnings('ignore')

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
OUTPUT_DIR = SCRIPT_DIR / "analyses_ridgeplots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = SCRIPT_DIR / "data" / "gitgalaxy_master.db"

def run_function_suite():
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        sys.exit(1)

    print("📡 Connecting to GitGalaxy Master Database...")
    conn = sqlite3.connect(DB_PATH)
    
    # NEW QUERY: Focus purely on the atomic functions and their new Micro-Species
    query = """
        SELECT 
            f.id, f.func_name, f.loc, f.complexity, f.args, 
            f.keyword_density, f.func_archetype, f.func_z_score, 
            c.file_path, c.language
        FROM function_data f
        LEFT JOIN file_data c ON f.file_id = c.id
        WHERE f.func_archetype IS NOT NULL
        AND f.loc >= 3
    """
    
    print("🌌 Extracting 75-Dimensional Function Micro-Species (This may take 30-90 seconds)...")
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("❌ No function data found. Have you run the master_db_updater.py yet?")
        return

    # Calculate Internal Logic Density
    df['func_internal_density'] = df['complexity'] / df['loc'].replace(0, 1)

    # Clean up the cluster names for plotting
    df['cluster_display'] = df['func_archetype'].str.split(':').str[0]

    print("\n" + "="*110)
    print(" 🌍 PHASE 0: GLOBAL POPULATION DIAGNOSTIC")
    print("="*110)
    total_funcs = len(df)
    print(f"   - Total Functions Analyzed: {total_funcs:,.0f}")
    print(f"   - Global Max Complexity Found: {df['complexity'].max():,.0f}")
    print(f"   - Average Function LOC: {df['loc'].mean():.1f}")
    print(f"   - Average Z-Score (Dispersion): {df['func_z_score'].mean():.2f}")


    # ==============================================================================
    # 1. MACRO FUNCTION STATISTICS BY MICRO-SPECIES
    # ==============================================================================
    print("\n" + "="*110)
    print(" 📊 PHASE 1: MACRO ARCHITECTURE BY MICRO-SPECIES")
    print("="*110)
    
    stats = df.groupby('func_archetype').agg(
        Total_Funcs=('id', 'count'),
        Avg_LOC=('loc', 'mean'),
        Avg_Complexity=('complexity', 'mean'),
        Min_Z=('func_z_score', 'min'),
        Median_Z=('func_z_score', 'median'),
        Mean_Z=('func_z_score', 'mean'),
        Max_Z=('func_z_score', 'max')
    ).reset_index()

    stats['Pct_of_Ecosystem'] = (stats['Total_Funcs'] / total_funcs) * 100

    print(f"{'Function Archetype':<50} | {'% Ecosys':<8} | {'Z-Min':<7} | {'Z-Med':<7} | {'Z-Mean':<7} | {'Z-Max'}")
    print("-" * 105)
    for _, row in stats.sort_values('Total_Funcs', ascending=False).iterrows():
        clean_name = row['func_archetype'][:47] + "..." if len(row['func_archetype']) > 50 else row['func_archetype']
        print(f"{clean_name:<50} | {row['Pct_of_Ecosystem']:>7.1f}% | {row['Min_Z']:>7.2f} | {row['Median_Z']:>7.2f} | {row['Mean_Z']:>7.2f} | {row['Max_Z']:>7.2f}")

    # ==============================================================================
    # 2. LANGUAGE DOMINANCE PER CLUSTER
    # ==============================================================================
    print("\n" + "="*110)
    print(" 🧬 PHASE 2: LANGUAGE DOMINANCE PER MICRO-SPECIES")
    print("="*110)
    
    for arch in stats.sort_values('Total_Funcs', ascending=False)['func_archetype']:
        arch_df = df[df['func_archetype'] == arch]
        top_langs = arch_df['language'].value_counts(normalize=True).head(3) * 100
        lang_str = ", ".join([f"{lang} ({pct:.1f}%)" for lang, pct in top_langs.items()])
        clean_name = arch.split(":")[0]  # Just print 'Cluster 0', etc. for brevity
        print(f"   {clean_name:<11} -> {lang_str}")


    # ==============================================================================
    # 3. THE "GOD FUNCTION" HUNT
    # ==============================================================================
    print("\n" + "="*110)
    print(" 👾 PHASE 3: THE 'GOD FUNCTION' HUNT (ABSOLUTE HIGHEST COMPLEXITIES)")
    print("="*110)
    
    god_nodes = df.nlargest(5, 'complexity')
    
    for i, (_, row) in enumerate(god_nodes.iterrows(), 1):
        print(f"{i}. {row['func_name']} [{row['language']}]")
        print(f"   ↳ Complexity: {row['complexity']:,.0f} | LOC: {row['loc']:,.0f} | Args: {row['args']:,.0f}")
        print(f"   ↳ Species: {row['func_archetype']}")
        print(f"   ↳ Path: {row['file_path'][:90]}...")
        print()


    # ==============================================================================
    # 4. ANOMALY HUNTING (THE SHAPE-SHIFTERS)
    # ==============================================================================
    print(" 🕵️‍♂️ PHASE 4: ARCHITECTURAL ANOMALIES (HIGHEST Z-SCORES)")
    print("="*110)
    print(" These functions were forced into a cluster but mathematically fight their classification.")
    print(" High probability of malware, massive technical debt, or multi-purpose God Nodes.\n")

    anomalies = df.nlargest(5, 'func_z_score')
    
    for i, (_, row) in enumerate(anomalies.iterrows(), 1):
        print(f"{i}. {row['func_name']} [{row['language']}]")
        print(f"   ↳ Z-Score Dispersion: {row['func_z_score']:,.2f} ⚠️")
        print(f"   ↳ Hiding inside: {row['func_archetype']}")
        print(f"   ↳ Path: {row['file_path'][:90]}...")
        print()

    # ==============================================================================
    # 5. THE PURE EXEMPLARS (LOWEST Z-SCORES)
    # ==============================================================================
    print(" 💎 PHASE 5: THE PURE EXEMPLARS (MATHEMATICAL CENTROIDS)")
    print("="*110)
    print(" These are the single most 'perfect' representations of each architectural cluster.")
    print(" Their DNA matches the centroid almost exactly (Z-Score approaching 0.0).\n")

    for arch in sorted(df['func_archetype'].dropna().unique()):
        arch_df = df[df['func_archetype'] == arch]
        if not arch_df.empty:
            exemplar = arch_df.nsmallest(1, 'func_z_score').iloc[0]
            clean_arch = arch.split(':')[0]
            print(f" {clean_arch}: {exemplar['func_name']} [{exemplar['language']}]")
            print(f"   ↳ Z-Score: {exemplar['func_z_score']:.4f} | LOC: {exemplar['loc']:.0f} | Comp: {exemplar['complexity']:.0f}")
            print(f"   ↳ Path: {exemplar['file_path'][:90]}...")
    print()

    # ==============================================================================
    # 6. Z-SCORE DISTRIBUTION QUANTILES
    # ==============================================================================
    print(" 📏 PHASE 6: Z-SCORE QUANTILE DISTRIBUTION")
    print("="*110)
    print(" This shows the shape of the 'Anomaly Tail' for each cluster.")
    print(f"{'Function Archetype':<45} | {'25th':<6} | {'50th':<6} | {'75th':<6} | {'95th':<6} | {'Max'}")
    print("-" * 110)
    
    for arch in stats.sort_values('Total_Funcs', ascending=False)['func_archetype']:
        arch_df = df[df['func_archetype'] == arch]
        clean_name = arch[:42] + "..." if len(arch) > 45 else arch
        p25 = arch_df['func_z_score'].quantile(0.25)
        p50 = arch_df['func_z_score'].quantile(0.50)
        p75 = arch_df['func_z_score'].quantile(0.75)
        p95 = arch_df['func_z_score'].quantile(0.95)
        m_max = arch_df['func_z_score'].max()
        print(f"{clean_name:<45} | {p25:>6.2f} | {p50:>6.2f} | {p75:>6.2f} | {p95:>6.2f} | {m_max:>6.2f}")
    print("\n")


    # ==============================================================================
    # 7. VISUALIZATION EXPORTS
    # ==============================================================================
    print("🎨 Rendering Visualizations to disk...")

    plot_df = df.copy()
    plot_df['cluster_id'] = plot_df['func_archetype'].str.extract(r'Cluster (\d+)').astype(float)
    plot_df = plot_df.sort_values(by='cluster_id')

    # 1. Complexity Violin Plot
    plt.figure(figsize=(16, 9))
    sns.set_theme(style="darkgrid")
    plot_df['log_comp'] = np.log1p(plot_df['complexity'])
    
    sns.violinplot(data=plot_df, y='func_archetype', x='log_comp', hue='func_archetype', palette="viridis", inner="quartile", legend=False)
    plt.title("Distribution of Function Complexity by Micro-Species", fontsize=16, pad=20)
    plt.xlabel("Log(Cyclomatic Complexity)", fontsize=12)
    plt.ylabel("Micro-Species", fontsize=12)
    plt.tight_layout()
    v_path = OUTPUT_DIR / "func_species_complexity_violin.png"
    plt.savefig(v_path, dpi=300)
    print(f"✅ Saved Density Plot: {v_path.name}")

    # 2. Scatter: LOC vs Complexity colored by Z-Score
    plt.figure(figsize=(14, 10))
    if len(plot_df) > 20000:
        scatter_sample = plot_df.sample(n=20000, random_state=42)
    else:
        scatter_sample = plot_df

    sns.scatterplot(
        data=scatter_sample, 
        x='loc', 
        y='complexity', 
        hue='func_z_score',
        palette="flare", # Red/Orange for high Z-scores
        alpha=0.7,
        s=25,
        edgecolor='none'
    )
    
    plt.xscale('log')
    plt.yscale('log')
    plt.title("Function Dimensions: LOC vs Complexity (Colored by Architectural Anomaly / Z-Score)", fontsize=16, pad=20)
    plt.xlabel("Lines of Code (Log Scale)", fontsize=12)
    plt.ylabel("Cyclomatic Complexity (Log Scale)", fontsize=12)
    
    # Fix legend
    norm = plt.Normalize(scatter_sample['func_z_score'].min(), scatter_sample['func_z_score'].max())
    sm = plt.cm.ScalarMappable(cmap="flare", norm=norm)
    sm.set_array([])
    plt.colorbar(sm, ax=plt.gca(), label="Z-Score Anomaly Rating")
    
    plt.tight_layout()
    s_path = OUTPUT_DIR / "func_species_anomaly_scatter.png"
    plt.savefig(s_path, dpi=300)
    print(f"✅ Saved Anomaly Scatter Plot: {s_path.name}")

    # -------------------------------------------------------------------------
    # 3. Z-SCORE STRIP PLOT (Dot Density & Pure Exemplars)
    # -------------------------------------------------------------------------
    plt.figure(figsize=(16, 10))
    sns.set_theme(style="darkgrid")
    
    # We clip at 15 so massive 125.0 outliers don't crush the X-axis scale
    strip_df = plot_df.copy()
    strip_df['func_z_score_clipped'] = strip_df['func_z_score'].clip(upper=15)
    
    # Sample down if we have millions of rows to prevent a solid block of color
    if len(strip_df) > 50000:
        strip_df = strip_df.sample(n=50000, random_state=42)

    # 1. Plot the transparent dots to build the density visual
    ax = sns.stripplot(
        data=strip_df, 
        x='func_z_score_clipped', 
        y='func_archetype', 
        hue='func_archetype',
        palette="viridis", 
        jitter=0.35,      # Spread them vertically 
        alpha=0.25,       # Transparency builds density
        size=3,           # Small dots
        legend=False
    )
    
    # 2. Plot the 'Pure Exemplars' (The exact centroid) at Z = 0.0
    num_clusters = len(strip_df['func_archetype'].unique())
    plt.scatter(
        x=[0.0] * num_clusters, 
        y=range(num_clusters), 
        color="white", 
        edgecolor="black", 
        marker="*",       # Star marker
        s=400,            # Massive size
        zorder=10,        # Force to the top layer
        label="Pure Exemplar (Centroid)"
    )

    plt.title("Function Z-Score Dispersion (Dot Density & Pure Exemplars)", fontsize=16, pad=20)
    plt.xlabel("Z-Score Anomaly Rating (Distance from Perfect Center)", fontsize=12)
    plt.ylabel("")
    plt.legend(loc="upper right", frameon=True, shadow=True)
    
    plt.tight_layout()
    z_path = OUTPUT_DIR / "func_species_zscore_stripplot.png"
    plt.savefig(z_path, dpi=300)
    print(f"✅ Saved Z-Score Strip Plot: {z_path.name}")

    # 4. KEYWORD DENSITY (RHO) DISTRIBUTION
    plt.figure(figsize=(16, 9))
    sns.set_theme(style="darkgrid")
    sns.violinplot(data=plot_df, y='func_archetype', x='keyword_density', hue='func_archetype', palette="mako", inner="quartile", legend=False)
    plt.title("Keyword Density (Lexical Verbosity) by Micro-Species", fontsize=16, pad=20)
    plt.xlabel("Keyword Density (Rho)", fontsize=12)
    plt.ylabel("")
    plt.tight_layout()
    rho_path = OUTPUT_DIR / "func_species_keyword_density.png"
    plt.savefig(rho_path, dpi=300)
    print(f"✅ Saved Keyword Density Plot: {rho_path.name}")

    # 5. INTERNAL LOGIC DENSITY DISTRIBUTION
    plt.figure(figsize=(16, 9))
    plot_df['log_internal_density'] = np.log1p(plot_df['func_internal_density'])
    sns.violinplot(data=plot_df, y='func_archetype', x='log_internal_density', hue='func_archetype', palette="magma", inner="quartile", legend=False)
    plt.title("Internal Logic Density (Complexity per LOC) by Micro-Species", fontsize=16, pad=20)
    plt.xlabel("Log(Internal Logic Density)", fontsize=12)
    plt.ylabel("")
    plt.tight_layout()
    dense_path = OUTPUT_DIR / "func_species_logic_density.png"
    plt.savefig(dense_path, dpi=300)
    print(f"✅ Saved Logic Density Plot: {dense_path.name}")

    print("\n" + "="*80)
    print(" 🚀 FUNCTION SUITE ANALYSIS COMPLETE")
    print("="*80 + "\n")

if __name__ == "__main__":
    run_function_suite()