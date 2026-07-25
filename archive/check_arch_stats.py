import sqlite3
import pandas as pd
from pathlib import Path
import sys

# --- DYNAMIC PATH RESOLUTION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR / "gitgalaxy_master.db"

def analyze_archetype_clusters():
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        sys.exit(1)

    print("📡 Connecting to GitGalaxy Master Database...")
    conn = sqlite3.connect(DB_PATH)
    
    # Generate the 10 cluster column names
    cluster_cols = [f"arch_cluster_{i}" for i in range(10)]
    query = f"SELECT {', '.join(cluster_cols)} FROM galactic_census"
    
    print("🌌 Extracting archetype distance vectors...")
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("❌ No data found in the database.")
        return

    # Pandas .describe() automatically calculates count, mean, std, min, percentiles, and max.
    # We transpose (.T) it so the features are rows, making it readable in the CLI.
    stats = df.describe().T

    # ==============================================================================
    # CLI REPORT
    # ==============================================================================
    print("\n" + "="*95)
    print(" 📊 ARCHETYPE CLUSTER DISTANCE (EUCLIDEAN) STATISTICS")
    print("="*95)
    print(f"{'Feature':<18} | {'Count':<10} | {'Mean':<8} | {'StdDev':<8} | {'Min':<8} | {'Median':<8} | {'Max':<8}")
    print("-" * 95)

    for index, row in stats.iterrows():
        # Safely format the output
        count = int(row['count'])
        mean = row['mean']
        std = row['std']
        vmin = row['min']
        median = row['50%']
        vmax = row['max']
        
        print(f"{index:<18} | {count:<10,d} | {mean:<8.3f} | {std:<8.3f} | {vmin:<8.3f} | {median:<8.3f} | {vmax:<8.3f}")

    print("="*95 + "\n")
    
    # Quick health check heuristic
    print("🔍 QUICK HEALTH DIAGNOSTIC:")
    if stats['max'].max() == 0.0:
        print(" 🔴 CRITICAL: All maximums are 0.0. The distance vectors failed to ingest.")
    else:
        print(" 🟢 DATA DETECTED: The distance vectors are populated.")
        print("    * Note: These values represent Euclidean Distance (Drift) from the centroid.")
        print("    * Lower Min values mean files perfectly match that archetype.")
        print("    * If Means are roughly between 2.0 and 8.0, the scaling is highly healthy.")

if __name__ == "__main__":
    analyze_archetype_clusters()