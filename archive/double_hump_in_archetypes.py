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

def analyze_sub_clusters():
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        sys.exit(1)

    print("📡 Connecting to GitGalaxy Master Database...")
    conn = sqlite3.connect(DB_PATH)
    
    # We want the archetype, the drift, and all the underlying physics/hits
    # to figure out WHAT makes the left tail different.
    query = """
        SELECT * FROM galactic_census 
        WHERE archetype LIKE 'Cluster %' AND logic_loc > 0
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("❌ No data found.")
        return

    # Extract Cluster ID
    df['cluster_id'] = df['archetype'].str.extract(r'Cluster (\d+)').astype(int)
    df = df[df['cluster_id'] < 16].reset_index(drop=True)

    # Reconstruct Drift
    cluster_cols = [f"arch_cluster_{i}" for i in range(16)]
    cluster_matrix = df[cluster_cols].to_numpy()
    cluster_ids = df['cluster_id'].to_numpy()
    df['global_drift'] = cluster_matrix[np.arange(len(df)), cluster_ids]

    # Identify the DNA columns (the raw structural hits)
    dna_cols = [c for c in df.columns if c.startswith('hit_') and not c.endswith('_x1000')]

    print("\n" + "="*100)
    print(" 🧬 HIDDEN TWIN DISCOVERY (25th Percentile Anomaly Analysis)")
    print("="*100)

    # Analyze each cluster for bimodal splits
    for cluster_id in sorted(df['cluster_id'].unique()):
        cdf = df[df['cluster_id'] == cluster_id]
        if len(cdf) < 100: continue

        arch_name = cdf['archetype'].iloc[0][:50]
        
        # Split the cluster: The Anomaly (Bottom 25%) vs The Core (Middle 50%)
        q25 = cdf['global_drift'].quantile(0.25)
        q75 = cdf['global_drift'].quantile(0.75)
        
        anomaly_df = cdf[cdf['global_drift'] <= q25]
        core_df = cdf[(cdf['global_drift'] > q25) & (cdf['global_drift'] <= q75)]

        if len(anomaly_df) == 0 or len(core_df) == 0: continue

        # Find the DNA differences
        anomaly_means = anomaly_df[dna_cols].mean()
        core_means = core_df[dna_cols].mean()
        
        # Calculate percentage difference (avoid div by zero)
        diffs = ((anomaly_means - core_means) / (core_means + 0.01)) * 100
        
        # Get the top 3 features that define the Anomaly vs the Core
        top_diffs = diffs[abs(diffs) > 50].sort_values(ascending=False).dropna()
        
        if len(top_diffs) > 0:
            print(f"\n[{arch_name}]")
            print(f"   Left-Tail Anomaly Pop : {len(anomaly_df):,} files")
            print(f"   Main Core Pop         : {len(core_df):,} files")
            print(f"   🧬 Top Structural Divergences in the Left Tail:")
            
            # Print top 3 positive diffs (Anomaly has MORE of this)
            for col, val in top_diffs.head(3).items():
                clean_col = col.replace('hit_', '').replace('_', ' ').title()
                print(f"      🟢 +{val:>6.1f}% | {clean_col}")
                
            # Print top 3 negative diffs (Anomaly has LESS of this)
            for col, val in top_diffs.tail(3).items():
                clean_col = col.replace('hit_', '').replace('_', ' ').title()
                print(f"      🔴 {val:>6.1f}% | {clean_col}")

    # ==============================================================================
    # VISUALIZATION EXPORT (Detailed Boxen/IQR Plots)
    # ==============================================================================
    print(f"\n🎨 Rendering IQR Boxen plots to {OUTPUT_DIR.name}...")
    
    plt.figure(figsize=(18, 12))
    sns.set_theme(style="darkgrid")
    
    # A Boxen plot (letter-value plot) is perfect for showing percentiles and bimodal humps
    ax = sns.boxenplot(
        data=df, 
        y='archetype', 
        x='global_drift', 
        hue='archetype',
        palette="mako",
        legend=False,
    )
    
    plt.title("Archetype Euclidean Drift (IQR Boxen Breakdown)", fontsize=16, pad=20)
    plt.xlabel("Euclidean Distance to Centroid", fontsize=12)
    plt.ylabel("K-16 Archetype", fontsize=12)
    plt.tight_layout()
    
    plot_path = OUTPUT_DIR / "archetype_iqr_boxen.png"
    plt.savefig(plot_path, dpi=300)
    print(f"✅ Saved high-res plot to : {plot_path}\n")

if __name__ == "__main__":
    analyze_sub_clusters()