import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import sys

# --- DYNAMIC PATH RESOLUTION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
OUTPUT_DIR = SCRIPT_DIR / "cluster_health_reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = SCRIPT_DIR / "gitgalaxy_master.db"

# --- DYNAMIC STANDARDS IMPORT ---
# Add parent directory to path so we can pull the original baseline dispersions
sys.path.append(str(SCRIPT_DIR.parent))
try:
    from gitgalaxy import gitgalaxy_standards_v1 as config
except ImportError:
    try:
        import gitgalaxy_standards_v1 as config
    except ImportError:
        print("❌ Could not import gitgalaxy_standards_v1. Please check your path.")
        sys.exit(1)

def validate_clusters():
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        sys.exit(1)

    print("📡 Connecting to GitGalaxy Master Database...")
    conn = sqlite3.connect(DB_PATH)
    
    # ==============================================================================
    # DYNAMIC K-DETECTION: Ask SQLite how many clusters exist
    # ==============================================================================
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(galactic_census)")
    all_cols = [row[1] for row in cursor.fetchall()]
    
    # Find all columns matching 'arch_cluster_X' and sort them correctly
    cluster_cols = sorted([c for c in all_cols if c.startswith('arch_cluster_')], 
                          key=lambda x: int(x.split('_')[-1]))
    
    num_clusters = len(cluster_cols)
    print(f"🔍 Detected K={num_clusters} physics engine in database schema.")
    
    if num_clusters == 0:
        print("❌ No arch_cluster_X columns found in database.")
        sys.exit(1)

    cols_to_select = ['archetype'] + cluster_cols
    
    query = f"""
        SELECT {', '.join(cols_to_select)} 
        FROM galactic_census 
        WHERE archetype LIKE 'Cluster %'
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("❌ No cluster data found in the database.")
        return

    print(f"🌌 Extracted {len(df):,} structural vectors. Reconstructing drift physics...")

    # 1. Extract Cluster ID dynamically (No dropping K > 16!)
    df['cluster_id'] = df['archetype'].str.extract(r'Cluster (\d+)').astype(int)

    # 2. Extract exact drift from the matching arch_cluster_X column
    cluster_matrix = df[cluster_cols].to_numpy()
    cluster_ids = df['cluster_id'].to_numpy()
    
    # Catch any bounds errors if the database state is desynchronized 
    valid_mask = cluster_ids < num_clusters
    df = df[valid_mask].reset_index(drop=True)
    cluster_matrix = cluster_matrix[valid_mask]
    cluster_ids = cluster_ids[valid_mask]
    
    df['global_drift'] = cluster_matrix[np.arange(len(df)), cluster_ids]

    # 3. Z-Scores for density plotting
    df['z_score'] = df.groupby('archetype')['global_drift'].transform(lambda x: (x - x.mean()) / x.std())

    # 4. Generate Statistical Summary
    stats = df.groupby(['cluster_id', 'archetype'])['global_drift'].agg(
        Population='count',
        New_Mean='mean',
        Std_Dev='std',
    ).reset_index()
    
    stats['95th_Percentile'] = df.groupby(['cluster_id', 'archetype'])['global_drift'].quantile(0.95).values

    # ==============================================================================
    # 5. THE BASELINE SHIFT CALCULATION
    # ==============================================================================
    # Fetch the original dispersions calculated during previous runs (if any exist)
    raw_baselines = config.LANGUAGE_SECURITY_PROFILES.get("ARCHETYPE_DISPERSIONS", {})
    
    import re
    baselines_by_id = {}
    for key, value in raw_baselines.items():
        match = re.search(r'Cluster (\d+)', key)
        if match:
            baselines_by_id[int(match.group(1))] = value
            
    stats['Baseline'] = stats['cluster_id'].map(baselines_by_id).fillna(0.0)
    
    # Calculate % Change ((New - Old) / Old * 100)
    stats['Shift_Pct'] = np.where(
        stats['Baseline'] > 0, 
        ((stats['New_Mean'] - stats['Baseline']) / stats['Baseline']) * 100.0, 
        0.0
    )
    stats = stats.sort_values(by='cluster_id', ascending=True)

    # ==============================================================================
    # CLI REPORT
    # ==============================================================================
    print("\n" + "="*115)
    print(" 🔭 ARCHETYPE BASELINE SHIFT & HEALTH REPORT")
    print("="*115)
    print(f"{'Archetype':<52} | {'Pop.':<9} | {'Baseline':<8} | {'New Mean':<8} | {'Shift %':<8} | {'Health'}")
    print("-" * 115)

    for _, row in stats.iterrows():
        arch = row['archetype'][:49] + "..." if len(row['archetype']) > 52 else row['archetype'][:52]
        pop = row['Population']
        baseline = row['Baseline']
        new_mean = row['New_Mean']
        shift = row['Shift_Pct']
        
        shift_str = f"{shift:+.1f}%"
        
        if baseline == 0.0:
            health = "⚪ UNKNOWN (New Outer-Rim Node)"
        elif shift > 20.0:
            health = "🔴 SPRAWLING (Retrain Advised)"
        elif shift < -15.0:
            health = "🔵 DENSIFYING (Packed Tighter)"
        else:
            health = "🟢 STABLE ORBIT"

        print(f"{arch:<52} | {pop:<9,} | {baseline:<8.2f} | {new_mean:<8.2f} | {shift_str:<8} | {health}")
    print("="*115)

    # ==============================================================================
    # VISUALIZATION EXPORT
    # ==============================================================================
    print(f"\n🎨 Rendering Z-Score Density plots to {OUTPUT_DIR.name}...")
    
    plt.figure(figsize=(18, 10))
    sns.set_theme(style="darkgrid")
    
    df = df.sort_values(by='cluster_id')

    ax = sns.violinplot(
        data=df, 
        y='archetype', 
        x='z_score', 
        hue='archetype',
        palette="magma",
        inner="quartile",
        legend=False,
    )
    
    plt.title(f"Archetype Z-Score Distributions (K={num_clusters} Physics)", fontsize=16, pad=20)
    plt.xlabel("Z-Score of Global Drift (0 = Cluster Mean Drift)", fontsize=12)
    plt.ylabel(f"K-{num_clusters} Archetype", fontsize=12)
    
    plt.axvline(0, color='red', linestyle='--', linewidth=1.5, alpha=0.7, label='Mean')
    plt.axvline(3, color='orange', linestyle=':', linewidth=1.5, alpha=0.7, label='+3 Sigma (Outlier Boundary)')
    plt.legend(loc='lower right')
    
    plt.tight_layout()
    plot_path = OUTPUT_DIR / "archetype_zscore_distribution.png"
    plt.savefig(plot_path, dpi=300)
    print(f"✅ Saved high-res plot to : {plot_path}")
    
    csv_path = OUTPUT_DIR / "archetype_health_metrics.csv"
    stats.to_csv(csv_path, index=False)
    print(f"✅ Saved raw metrics to  : {csv_path}\n")

if __name__ == "__main__":
    validate_clusters()