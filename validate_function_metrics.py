import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
import warnings

warnings.filterwarnings('ignore')

SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR / "data" / "gitgalaxy_master.db"

def run_stats():
    print(f"📡 Connecting to {DB_PATH.name}...")
    conn = sqlite3.connect(DB_PATH)
    
    query = """
        SELECT 
            c.file_name, c.coding_loc, c.logic_loc, c.control_flow_ratio,
            COUNT(f.id) as function_count, 
            AVG(f.loc) as avg_func_loc, 
            AVG(f.complexity) as avg_func_complexity
        FROM galactic_census c
        JOIN galactic_functions f ON c.id = f.file_id
        WHERE c.coding_loc > 0 AND c.archetype LIKE 'Cluster %'
        GROUP BY c.id
        ORDER BY RANDOM()
        LIMIT 50000
    """
    
    print("🌌 Extracting 50,000 files for statistical analysis...")
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("❌ Error: No data found.")
        return

    # Calculate metrics
    df['1_raw_size_ratio'] = df['avg_func_loc'] / df['coding_loc'].replace(0, 1)
    df['2_clipped_size_ratio'] = np.clip(df['1_raw_size_ratio'], 0.0, 1.0)
    df['3_density_weighted_ratio'] = df['2_clipped_size_ratio'] * df['control_flow_ratio']
    df['4_log_density_weighted'] = np.log1p(df['3_density_weighted_ratio'])

    metrics = ['3_density_weighted_ratio', '4_log_density_weighted']
    
    print("\n" + "="*80)
    print(" 📊 DISTRIBUTION STATISTICS (THE SHAPE OF THE DATA)")
    print("="*80)
    
    for m in metrics:
        clean_name = "User Idea (Raw)" if m == '3_density_weighted_ratio' else "User Idea (Logged)"
        
        # Pandas calculates "Excess Kurtosis" (0 is a perfect normal distribution)
        skew = df[m].skew()
        kurt = df[m].kurt()
        
        skew_str = "Symmetrical" if abs(skew) < 0.5 else "Right-Skewed (Tail to the right)" if skew > 0 else "Left-Skewed (Tail to the left)"
        kurt_str = "Normal-ish Tails" if abs(kurt) < 1 else "Heavy Outlier Tails" if kurt > 0 else "Flat/Light Tails"
        
        print(f"Metric: {clean_name}")
        print(f"  Mean:     {df[m].mean():.4f}  |  Median: {df[m].median():.4f}")
        print(f"  Std Dev:  {df[m].std():.4f}")
        print(f"  Skewness: {skew:+.4f} ({skew_str})")
        print(f"  Kurtosis: {kurt:+.4f} ({kurt_str})")
        print("\n  [Percentiles]")
        print(f"  Min:      {df[m].min():.4f}")
        print(f"  25th %:   {df[m].quantile(0.25):.4f}")
        print(f"  75th %:   {df[m].quantile(0.75):.4f}")
        print(f"  99th %:   {df[m].quantile(0.99):.4f}")
        print(f"  Max:      {df[m].max():.4f}")
        print("-" * 80)

if __name__ == "__main__":
    run_stats()