import sqlite3
import pandas as pd
import numpy as np
import time
from pathlib import Path
import sys

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR / "gitgalaxy_master.db"
# Change this to 'galactic_census' if that is your main file table!
FILE_TABLE = "file_data" 

def run_dna_rollup():
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        sys.exit(1)

    print("\n" + "="*80)
    print(" 🧬 INITIATING FUNCTION-TO-FILE DNA ROLL-UP")
    print("="*80)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # -------------------------------------------------------------------------
    # 1. EXTRACT ATOMIC FUNCTION DATA
    # -------------------------------------------------------------------------
    print("📡 Extracting 5.2M functions into memory for aggregation...")
    query = """
        SELECT file_id, func_archetype, func_z_score 
        FROM function_data 
        WHERE func_archetype IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    
    if df.empty:
        print("❌ No classified functions found. Run master_db_updater.py --update function_cluster first.")
        return
        
    print(f"✅ Loaded {len(df):,} atomic functions.")

    # -------------------------------------------------------------------------
    # 2. FEATURE ENGINEERING: THE AGGREGATIONS
    # -------------------------------------------------------------------------
    print("⚙️  Calculating Micro-Species Stoichiometry & Z-Score Radars...")
    
    # Extract just the Cluster ID integer (0-11) for easy pivoting
    df['cluster_id'] = df['func_archetype'].str.extract(r'Cluster (\d+):').astype(float)
    
    # Create the base aggregations (Max, Mean, Median, Count)
    rollup = df.groupby('file_id').agg(
        func_count=('file_id', 'count'),
        func_z_max=('func_z_score', 'max'),
        func_z_mean=('func_z_score', 'mean'),
        func_z_median=('func_z_score', 'median')
    ).reset_index()

    # Calculate the Anomaly Ratios
    # Warning = Z > 5.0 | Severe = Z > 15.0
    warning_counts = df[df['func_z_score'] > 5.0].groupby('file_id').size().reset_index(name='warning_count')
    severe_counts = df[df['func_z_score'] > 15.0].groupby('file_id').size().reset_index(name='severe_count')

    rollup = rollup.merge(warning_counts, on='file_id', how='left').fillna(0)
    rollup = rollup.merge(severe_counts, on='file_id', how='left').fillna(0)

    rollup['pct_z_above_5'] = (rollup['warning_count'] / rollup['func_count']) * 100.0
    rollup['pct_z_above_15'] = (rollup['severe_count'] / rollup['func_count']) * 100.0
    
    # Drop the raw counts, we only want the ratios in the DB
    rollup = rollup.drop(columns=['warning_count', 'severe_count'])

    # Calculate the 12 Stoichiometric Composition Ratios
    # This creates a matrix of file_id vs cluster_id with counts
    composition = pd.crosstab(df['file_id'], df['cluster_id'])
    
    # Convert counts to percentages
    composition = composition.div(composition.sum(axis=1), axis=0) * 100.0
    
    # Rename columns to micro_0_pct, micro_1_pct, etc.
    composition.columns = [f'micro_{int(col)}_pct' for col in composition.columns]
    composition = composition.reset_index()

    # Merge everything together!
    final_rollup = rollup.merge(composition, on='file_id', how='left').fillna(0.0)

    print(f"✅ Generated 17 new DNA macro-features for {len(final_rollup):,} files.")

    # -------------------------------------------------------------------------
    # 3. DATABASE INJECTION
    # -------------------------------------------------------------------------
    print(f"🏗️  Syncing schema in '{FILE_TABLE}'...")
    cursor.execute(f"PRAGMA table_info({FILE_TABLE})")
    existing_columns = [row[1] for row in cursor.fetchall()]

    # Define the 17 new columns we are injecting
    new_cols = [
        'func_z_max', 'func_z_mean', 'func_z_median', 
        'pct_z_above_5', 'pct_z_above_15'
    ] + [f'micro_{i}_pct' for i in range(12)]

    for col in new_cols:
        if col not in existing_columns:
            cursor.execute(f"ALTER TABLE {FILE_TABLE} ADD COLUMN {col} REAL DEFAULT 0.0")
    conn.commit()

    print("💾 Injecting DNA into Master Database (This may take a minute)...")
    
    # Format for fast SQLite executemany
    update_data = final_rollup[new_cols + ['file_id']].to_records(index=False).tolist()
    set_clause = ", ".join([f"{col} = ?" for col in new_cols])
    sql = f"UPDATE {FILE_TABLE} SET {set_clause} WHERE id = ?"
    
    t0 = time.time()
    cursor.execute("BEGIN TRANSACTION")
    cursor.executemany(sql, update_data)
    conn.commit()
    t1 = time.time()

    conn.close()
    
    print("\n" + "="*80)
    print(f" 🎉 ROLL-UP COMPLETE! (Update took {t1-t0:.1f}s)")
    print(f"   Your file table now contains the exact stoichiometric makeup")
    print(f"   and anomaly radars for {len(final_rollup):,} files.")
    print("="*80 + "\n")

if __name__ == "__main__":
    run_dna_rollup()