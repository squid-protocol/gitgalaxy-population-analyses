import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import time
import argparse

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

# --- DYNAMIC PATH RESOLUTION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR / "gitgalaxy_master.db"

# =========================================================================
# 🧠 PASTE YOUR NEW ML_INFERENCE_BRAIN HERE
# Open ml_inference_brain_paste.txt, copy everything, and replace the dict below!
# =========================================================================
ML_INFERENCE_BRAIN = {
    'SCALER_MEDIANS': [3.074, 3.781, 2.494, 2.162, 0.0, 0.0, 0.0, 0.0, 1.713, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2.097, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.136, 1.386, 1.099, 0.0, 0.0, 0.0, 0.693, 0.0, 0.0, 1.929, 0.0],
    'SCALER_IQRS': [3.831, 2.382, 3.614, 3.258, 1.751, 1.88, 1.0, 1.0, 3.36, 3.181, 1.0, 1.0, 1.0, 1.0, 1.0, 3.35, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.494, 1.0, 1.695, 1.0, 0.419, 3.466, 1.946, 1.099, 1.0, 1.0, 1.163, 1.0, 0.483, 3.536, 0.125],
    'ARCHETYPES_K9': {
        'Cluster 0: Native Memory & Systems Pointers': [-0.029, -0.168, -0.052, -0.011, 0.544, 0.502, 0.287, 0.069, -0.093, 1.125, 0.056, 0.188, 0.99, 0.028, 0.649, 0.06, 0.034, 3.112, 0.208, 0.007, 1.52, 0.17, 0.018, 0.585, 0.099, 0.769, 0.195, 0.378, 0.104, 0.728, 0.703, 0.466, 0.448, 3.435, 0.426, 0.049, 0.107, 0.856, 0.119, 1.093],
        'Cluster 1: High-Dependency Config & Object Nodes': [-0.633, -0.732, -0.42, -0.399, 0.327, 0.089, 0.042, 0.014, -0.172, 0.153, 0.03, 0.04, 0.078, 0.019, 0.142, -0.262, 0.014, 0.093, 0.04, 0.001, 0.092, 0.025, 0.003, 0.083, 0.008, 0.184, 0.019, 0.184, 0.025, -0.104, -0.269, -0.325, 0.346, 0.111, 0.075, -0.397, 0.052, 0.005, -0.216, 0.008],
        'Cluster 2: Asynchronous & Concurrent Orchestrators': [0.05, 0.503, 0.266, 0.362, 0.622, 1.253, 1.243, 0.042, 0.327, 0.541, 4.272, 0.122, 0.151, 0.412, 0.461, 0.335, 0.126, 0.273, 0.27, 0.0, 0.529, 0.478, 0.1, 0.265, 0.176, 0.405, 0.246, 1.102, 0.264, 0.188, 0.326, 0.364, 0.814, 0.534, 0.013, 0.215, 0.128, 0.696, 0.425, 0.72],
        'Cluster 3: Low-Level Bitwise Systems Core': [-0.053, 0.138, 0.107, 0.084, 1.037, 0.601, 0.296, 0.027, 0.311, 0.932, 0.066, 0.128, 0.736, 0.086, 0.812, -0.005, 0.025, 4.043, 0.16, 0.011, 0.689, 0.108, 0.007, 0.881, 0.076, 0.688, 0.11, 0.94, 0.064, 0.372, 0.47, 0.205, 0.595, 0.434, 0.314, 0.143, 0.079, 0.737, 0.182, 0.78],
        'Cluster 4: Complex Encapsulated OOP Logic': [0.16, -0.033, 0.153, 0.21, 0.647, 0.831, 0.401, 0.05, 0.089, 0.543, 0.092, 0.262, 0.289, 0.383, 0.324, 0.013, 0.048, 0.178, 0.207, 0.003, 0.597, 0.6, 0.016, 0.413, 0.037, 0.475, 0.144, 0.953, 0.067, 0.854, 0.589, 0.13, 0.408, 0.27, 0.031, 0.385, 0.139, 0.715, 0.179, 1.712],
        'Cluster 5: Async Closures & Memory Allocation': [0.086, 0.365, 0.457, 0.425, 0.409, 1.19, 1.054, 0.054, 0.036, 0.599, 3.886, 3.07, 0.551, 0.755, 0.211, 0.239, 0.343, 0.114, 0.904, 0.0, 0.442, 0.492, 0.223, 0.413, 0.106, 1.176, 0.479, 0.582, 0.474, 0.339, 0.485, 0.354, 0.68, 0.217, 0.045, 0.335, 0.226, 0.772, 0.28, 1.063],
        'Cluster 6: Immutable State & Closure Logic': [-0.01, 0.288, 0.45, 0.353, 0.433, 0.756, 0.736, 0.038, 0.106, 0.403, 0.093, 3.156, 0.294, 0.691, 0.174, 0.187, 0.142, 0.048, 0.339, 0.0, 0.382, 0.207, 0.019, 0.301, 0.029, 0.978, 0.163, 0.517, 0.227, 0.267, 0.288, 0.183, 0.558, 0.158, 0.04, 0.262, 0.128, 0.559, 0.32, 0.76],
        'Cluster 7: Exception Handling & Defensive Wrappers': [-0.043, 0.26, 0.038, 0.014, 0.619, 0.622, 3.185, 0.045, 0.273, 0.567, 0.074, 0.4, 0.105, 0.181, 0.98, 0.234, 0.046, 0.046, 0.087, 0.0, 0.445, 0.397, 0.026, 0.146, 0.059, 0.306, 0.198, 0.921, 0.099, 0.313, 0.176, 0.189, 0.709, 0.16, 0.017, -0.041, 0.074, 0.506, 0.095, 0.569],
        'Cluster 8: Downstream Execution Triggers': [-0.325, -0.034, -0.206, -0.202, 0.404, 0.449, 0.429, 0.009, 0.225, 0.277, 0.208, 0.42, 0.113, 0.232, 0.655, 0.136, 0.021, 0.209, 0.114, 0.004, 0.432, 0.217, 0.006, 0.286, 0.022, 0.428, 0.147, 0.559, 0.051, 0.116, 0.086, 0.154, 4.73, 0.398, 0.244, -0.21, 0.106, 0.283, -0.121, 0.44],
    }
}

# =========================================================================
# DIAGNOSTIC VALIDATORS
# =========================================================================

def _run_pre_flight_check(cursor, num_clusters):
    """Scans the database BEFORE the update to report the currently broken columns."""
    print("\n" + "="*50)
    print(" 🛫 PRE-FLIGHT HEALTH CHECK")
    print("="*50)
    
    # Get all active columns in the database
    cursor.execute("PRAGMA table_info(galactic_census)")
    db_cols = [row[1] for row in cursor.fetchall()]

    # We only care about active logic files (where coding_loc > 0 or it's plaintext)
    # Inert files like JSON/Minified naturally have NULLs, which is fine.
    active_logic_condition = "coding_loc > 0 OR language = 'plaintext'"

    check_cols = ['archetype', 'global_drift'] + [f'arch_cluster_{i}' for i in range(num_clusters) if f'arch_cluster_{i}' in db_cols]
    
    for col in check_cols:
        cursor.execute(f"SELECT COUNT(*) FROM galactic_census WHERE {col} IS NULL AND ({active_logic_condition})")
        null_count = cursor.fetchone()[0]
        if null_count > 0:
            print(f" ⚠️  WARNING: {col:<15} has {null_count:,} NULL values.")
        else:
            print(f" ✅  CLEAN:   {col:<15} is fully populated.")
            
    print("="*50 + "\n")

def _run_post_flight_check(cursor, num_clusters, valid_archetypes):
    """Strictly validates the database AFTER the update to ensure absolute mathematical parity."""
    print("\n" + "="*50)
    print(" 🛬 POST-FLIGHT VALIDATION")
    print("="*50)
    
    active_logic_condition = "coding_loc > 0 OR language = 'plaintext'"
    check_cols = ['archetype', 'global_drift'] + [f'arch_cluster_{i}' for i in range(num_clusters)]
    
    has_errors = False

    # 1. Strict Null Check (Did we fix the gaps?)
    for col in check_cols:
        cursor.execute(f"SELECT COUNT(*) FROM galactic_census WHERE {col} IS NULL AND ({active_logic_condition})")
        null_count = cursor.fetchone()[0]
        if null_count > 0:
            print(f" ❌ ERROR: {col:<15} STILL HAS {null_count:,} NULL values!")
            has_errors = True
        else:
            print(f" ✅ FIXED: {col:<15} has 0 NULLs.")

    # 2. Archetype Dictionary Verification (Are there rogue labels?)
    cursor.execute(f"SELECT DISTINCT archetype FROM galactic_census WHERE {active_logic_condition}")
    db_archetypes = {row[0] for row in cursor.fetchall()}
    
    # We must also account for the 'Unknown Archetype' fallback in case a file failed math entirely
    acceptable_archetypes = set(valid_archetypes)
    acceptable_archetypes.add("Unknown Archetype")

    invalid_archetypes = db_archetypes - acceptable_archetypes
    missing_archetypes = set(valid_archetypes) - db_archetypes

    if invalid_archetypes:
        print(f"\n ❌ ERROR: Found rogue archetypes in DB not mapped in your config:")
        for rogue in invalid_archetypes:
            print(f"    - '{rogue}'")
        has_errors = True
    else:
        print(f"\n ✅ DICTIONARY LOCK: All active logic files belong to an approved K{num_clusters} Archetype.")

    if missing_archetypes:
        print(f"\n ℹ️  NOTE: The following archetypes are valid, but zero files matched them:")
        for missing in missing_archetypes:
            print(f"    - '{missing}'")

    print("="*50)
    
    if has_errors:
        raise ValueError("Post-Flight Validation Failed. The database contains structural anomalies.")
    else:
        print(" 🚀 VALIDATION SUCCESSFUL: The database is mathematically sound!")
        print("="*50 + "\n")

# =========================================================================
# MAIN UPGRADE ENGINE
# =========================================================================

def upgrade_database_physics(limit=None):
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        sys.exit(1)

    brain = ML_INFERENCE_BRAIN
    
    if not brain or 'SCALER_MEDIANS' not in brain:
        print("❌ Error: The ML_INFERENCE_BRAIN dictionary is empty or invalid.")
        print("Please paste the contents of ml_inference_brain_paste.txt at the top of the script.")
        sys.exit(1)
    
    arch_key = next((k for k in brain.keys() if k.startswith('ARCHETYPES_K')), None)
    if not arch_key:
        print("❌ Could not find ARCHETYPES_Kxx in ML_INFERENCE_BRAIN.")
        sys.exit(1)
        
    archetypes_dict = brain[arch_key]
    arch_names = list(archetypes_dict.keys())
    num_clusters = len(archetypes_dict)
    
    print(f"🧠 Loaded {arch_key} with {num_clusters} clusters directly from script.")

    print("📡 Connecting to GitGalaxy Master Database...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ---> RUN DIAGNOSTICS <---
    _run_pre_flight_check(cursor, num_clusters)

    print(f"🏗️  Syncing database schema for {num_clusters} architecture clusters...")
    
    # 1. Scan existing database schema
    cursor.execute("PRAGMA table_info(galactic_census)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    # 2. Inject missing columns dynamically
    for i in range(num_clusters):
        col_name = f"arch_cluster_{i}"
        if col_name not in existing_columns:
            print(f"   ➕ Adding new dimension: {col_name}...")
            cursor.execute(f"ALTER TABLE galactic_census ADD COLUMN {col_name} REAL")

    # 3. Surgically drop obsolete cluster columns (Requires SQLite 3.35.0+)
    for col in existing_columns:
        if col.startswith("arch_cluster_"):
            try:
                cluster_idx = int(col.split("_")[-1])
                if cluster_idx >= num_clusters:
                    print(f"   🧹 Sweeping obsolete dimension: {col}...")
                    cursor.execute(f"ALTER TABLE galactic_census DROP COLUMN {col}")
            except (ValueError, sqlite3.OperationalError) as e:
                print(f"   ⚠️ Could not drop {col} (SQLite version may be too old): {e}")

    conn.commit()

    base_select = """
        SELECT 
            c.*,
            COUNT(f.id) as real_function_count,
            AVG(f.loc) as real_avg_func_loc,
            AVG(f.complexity) as real_avg_func_complexity,
            GROUP_CONCAT(f.complexity) as func_complexity_vector
        FROM galactic_census c
        LEFT JOIN galactic_functions f ON c.id = f.file_id
        WHERE c.coding_loc > 0 OR c.language = 'plaintext'
    """
    
    if limit:
        print(f"🧪 CLI TEST MODE: Limiting extraction to {limit:,} rows...")
        query = base_select + f" GROUP BY c.id LIMIT {limit}"
    else:
        print("🌌 Extracting raw telemetry for ALL active logic files...")
        query = base_select + " GROUP BY c.id"
        
    df = pd.read_sql_query(query, conn)
    
    if df.empty:
        print("❌ No data found.")
        conn.close()
        return

    print("⚙️  Calculating dimensional densities and logarithmic transforms...")
    
    # 1. Null Safety for new joined columns
    null_cols = ['logic_loc', 'raw_churn_freq', 'avg_func_args', 'direct_upstream', 'direct_downstream', 'total_upstream', 'total_downstream', 'control_flow_ratio', 'real_avg_func_loc', 'real_avg_func_complexity', 'real_function_count']
    for c in null_cols:
        if c in df.columns:
            df[c] = df[c].fillna(0.0)

    # 2. Calculate the New Function Geometries
    df['parsed_vector'] = df['func_complexity_vector'].apply(parse_concat_vector)
    df['complexity_gini'] = df.apply(lambda row: calculate_gini(row['parsed_vector']) if row['real_function_count'] > 1 else 0.0, axis=1)
    df['func_density'] = df['real_function_count'] / (df['logic_loc'].replace(0, 1) / 100.0)
    df['func_internal_density'] = df['real_avg_func_complexity'] / df['real_avg_func_loc'].replace(0, 1)
    
    # 3. Log Transforms
    df['log_logic_loc'] = np.log1p(df['logic_loc'])
    df['log_churn'] = np.log1p(df['raw_churn_freq'])
    df['log_avg_func_args'] = np.log1p(df['avg_func_args'])
    df['log_direct_upstream'] = np.log1p(df['direct_upstream'])
    df['log_direct_downstream'] = np.log1p(df['direct_downstream'])
    df['log_total_upstream'] = np.log1p(df['total_upstream'])
    df['log_total_downstream'] = np.log1p(df['total_downstream'])
    df['log_func_density'] = np.log1p(df['func_density'])

    # 4. Core DNA Densities
    core_cols = [c for c in df.columns if c.startswith('core_') and not c.endswith('_x1000')]
    safe_denom = df['logic_loc'].replace(0, np.nan).fillna(df['coding_loc']).replace(0, 1)    
    
    log_density_hit_cols = []
    for col in core_cols:
        raw_density = (df[col] / safe_denom) * 100.0
        df[f"log_density_{col}"] = np.log1p(raw_density.fillna(0.0))
        log_density_hit_cols.append(f"log_density_{col}")

    # 5. The Fully Synced 40-Dimension Telemetry Vector
    telemetry_features = [
        'control_flow_ratio', 
        'log_logic_loc', 
        'log_direct_upstream',
        'log_direct_downstream',
        'log_total_upstream',
        'log_total_downstream',
        'log_avg_func_args', 
        'log_churn',
        'complexity_gini',         
        'log_func_density',            
        'func_internal_density'
    ]
    
    cluster_features = log_density_hit_cols + telemetry_features
    
    # Drop rows that somehow missed the feature engineering
    df = df.dropna(subset=cluster_features)
    X_raw = df[cluster_features].fillna(0.0).to_numpy()

    print("📏 Applying ML Scalers...")
    medians = np.array(brain['SCALER_MEDIANS'])
    iqrs = np.array(brain['SCALER_IQRS'])
    
    safe_iqrs = np.where(iqrs == 0, 1.0, iqrs)
    X_scaled = (X_raw - medians) / safe_iqrs

    centroids = np.array(list(archetypes_dict.values()))
    
    print("🔪 Chunking distance calculations to prevent RAM explosion...")
    distances = np.zeros((len(X_scaled), num_clusters))
    chunk_size = 50000
    
    for i in range(0, len(X_scaled), chunk_size):
        end = min(i + chunk_size, len(X_scaled))
        chunk = X_scaled[i:end]
        distances[i:end] = np.linalg.norm(chunk[:, np.newaxis, :] - centroids, axis=2)
    
    for i in range(num_clusters):
        df[f'arch_cluster_{i}'] = distances[:, i]
        
    min_indices = np.argmin(distances, axis=1)
    df['global_drift'] = distances[np.arange(len(df)), min_indices]
    df['archetype'] = [arch_names[i] for i in min_indices]

    print("💾 Batch updating SQLite Database. This may take a minute...")
    update_cols = ['archetype', 'global_drift'] + [f'arch_cluster_{i}' for i in range(num_clusters)]
    update_data = df[update_cols + ['id']].to_records(index=False).tolist()

    set_clause = ", ".join([f"{col} = ?" for col in update_cols])
    sql = f"UPDATE galactic_census SET {set_clause} WHERE id = ?"
    
    t0 = time.time()
    cursor.execute("BEGIN TRANSACTION")
    cursor.executemany(sql, update_data)
    conn.commit()
    t1 = time.time()
    
    # ---> RUN FINAL DIAGNOSTICS <---
    _run_post_flight_check(cursor, num_clusters, arch_names)
    
    conn.close()
    print(f"✅ DB UPGRADE COMPLETE! (Update took {t1-t0:.1f}s)")
    print(f"   Updated {len(df):,} files to K={num_clusters} physics.")
    print("="*60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retroactively upgrade SQLite Database with new K-Means Physics.")
    parser.add_argument('--limit', type=int, default=None, help="Limit the number of rows processed for testing")
    args = parser.parse_args()
    upgrade_database_physics(limit=args.limit)