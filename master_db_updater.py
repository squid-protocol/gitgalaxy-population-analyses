import sqlite3
import pandas as pd
import numpy as np
import time
import ast
import argparse
from pathlib import Path
import sys

# Threat Model Requirements
try:
    import xgboost as xgb
except ImportError:
    print("⚠️  Warning: xgboost not installed. Threat engine will fail if called.")

# Health Assessor Requirement
try:
    from db_health_assessor import GalaxyDBHealthAssessor
except ImportError:
    print("❌ Error: Could not import GalaxyDBHealthAssessor. Ensure db_health_assessor.py is in the same directory.")
    sys.exit(1)

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR / "data" / "gitgalaxy_master.db"

# ML Artifact Paths
BRAIN_PATH_FUNCTIONS = SCRIPT_DIR / "kmeans_clustering" / "ml_inference_brain_functions.txt"
MODEL_PATH_THREAT = SCRIPT_DIR / "xgboost_threat_model" / "gitgalaxy_malware_xgb_multiclass.json"

# --- HELPER FUNCTIONS ---
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

def load_brain(filepath):
    """Dynamically parses the ML Brain dictionary from a text file."""
    if not filepath.exists():
        print(f"❌ Error: ML Inference Brain not found at {filepath}")
        sys.exit(1)
        
    print(f"🧠 Loading ML Inference Brain from: {filepath.name}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    try:
        dict_string = content.split("=", 1)[1].strip()
        return ast.literal_eval(dict_string)
    except Exception as e:
        print(f"❌ Error parsing the Brain file: {e}")
        sys.exit(1)


# =========================================================================
# MODULE 1: THE THREAT ENGINE (XGBoost)
# =========================================================================
def run_threat_engine():
    """Generates AI Threat Predictions and writes to the sidecar table."""
    print("\n" + "="*80)
    print(" 🛡️ INITIATING THREAT MODEL INFERENCE (XGBoost)")
    print("="*80)
    
    if not MODEL_PATH_THREAT.exists():
        print(f"❌ Error: Threat model not found at {MODEL_PATH_THREAT}")
        sys.exit(1)

    print(f"🧠 Loading XGBoost Brain: {MODEL_PATH_THREAT.name}...")
    model = xgb.XGBClassifier()
    model.load_model(MODEL_PATH_THREAT)
    expected_features = model.feature_names_in_

    conn = sqlite3.connect(DB_PATH)
    
    print("🏗️  Building safe 'ai_predictions' sidecar table...")
    conn.execute("DROP TABLE IF EXISTS ai_predictions")
    conn.execute("""
        CREATE TABLE ai_predictions (
            file_id INTEGER PRIMARY KEY,
            ai_confidence REAL,
            threat_class INTEGER
        )
    """)
    conn.commit()

    chunk_size = 50000
    print(f"🚀 Igniting Global Threat Scan (Chunk Size: {chunk_size:,} files)...")
    start_time = time.time()
    
    total_processed = 0
    total_threats_found = 0

    query = """
        SELECT c.*, 
               COUNT(f.id) as real_function_count,
               AVG(f.loc) as real_avg_func_loc,
               AVG(f.complexity) as real_avg_func_complexity,
               GROUP_CONCAT(f.complexity) as func_complexity_vector
        FROM galactic_census c
        LEFT JOIN galactic_functions f ON c.id = f.file_id
        GROUP BY c.id
    """
    
    for chunk_df in pd.read_sql_query(query, conn, chunksize=chunk_size):
        chunk_start = time.time()
        file_ids = chunk_df['id'].tolist()
        
        # --- FEATURE ENGINEERING (Must match training exactly) ---
        null_cols = ['logic_loc', 'real_avg_func_loc', 'real_avg_func_complexity', 'real_function_count', 'direct_upstream', 'total_downstream']
        for c in null_cols:
            if c in chunk_df.columns:
                chunk_df[c] = chunk_df[c].fillna(0.0)

        chunk_df['parsed_vector'] = chunk_df['func_complexity_vector'].apply(parse_concat_vector)
        chunk_df['complexity_gini'] = chunk_df.apply(lambda row: calculate_gini(row['parsed_vector']) if row['real_function_count'] > 1 else 0.0, axis=1)
        chunk_df['func_internal_density'] = chunk_df['real_avg_func_complexity'] / chunk_df['real_avg_func_loc'].replace(0, 1)
        chunk_df['func_density'] = chunk_df['real_function_count'] / (chunk_df['logic_loc'].replace(0, 1) / 100.0)

        chunk_df['log_direct_upstream'] = np.log1p(chunk_df['direct_upstream'])
        chunk_df['log_total_downstream'] = np.log1p(chunk_df['total_downstream'])

        raw_count_cols = [c for c in chunk_df.columns if c.startswith(('core_', 'risk_', 'design_', 'threat_')) and c != 'threat_class']
        safe_denom = chunk_df['logic_loc'].replace(0, np.nan).fillna(chunk_df['coding_loc']).replace(0, 1)    
        
        for col in raw_count_cols:
            chunk_df[f"density_{col}"] = (chunk_df[col] / safe_denom) * 100.0
            
        # Surgical Pruning
        cols_to_drop = [
            'id', 'repo_name', 'commit_date', 'file_name', 'file_path', 'constellation', 'archetype', 
            'logic_loc_bin', 'import_list', 'author', 'is_malware', 'threat_class', 'confirmed_kill_chain',
            'raw_churn_freq', 'popularity', 'ai_threat_confidence', 'language', 'purpose', 'pos_x', 'pos_y', 'pos_z', 
            'parsed_vector', 'func_complexity_vector', 'total_loc', 'coding_loc', 'comment_loc', 'logic_loc', 'structural_mass',
            'cog_raw', 'ownership_entropy', 'silo_risk', 'function_count', 'avg_func_loc', 'avg_func_complexity', 'max_func_complexity', 'avg_func_args',
            'direct_upstream', 'direct_downstream', 'total_upstream', 'total_downstream', 'direct_upstream_ratio', 'direct_downstream_ratio', 
            'total_upstream_ratio', 'total_downstream_ratio', 'global_drift', 'local_drift', 'logic_density',
            'real_avg_func_loc', 'real_avg_func_complexity', 'real_function_count'
        ]
        
        stale_clusters = [c for c in chunk_df.columns if c.startswith('arch_cluster_')] 
        cols_to_drop.extend(stale_clusters)
        cols_to_drop.extend(raw_count_cols)
        
        X_chunk = chunk_df.drop(columns=[c for c in cols_to_drop if c in chunk_df.columns])
        
        if 'repo_z_score' in X_chunk.columns:
            X_chunk['repo_z_score'] = pd.to_numeric(X_chunk['repo_z_score'], errors='coerce')
        
        if 'repo_macro_species' in X_chunk.columns:
            X_chunk = pd.get_dummies(X_chunk, columns=['repo_macro_species'], dummy_na=False)
            
        object_cols = X_chunk.select_dtypes(include=['object']).columns
        if len(object_cols) > 0:
            X_chunk = X_chunk.drop(columns=object_cols)
            
        X_chunk = X_chunk.fillna(0).replace([np.inf, -np.inf], 0)
        X_chunk = X_chunk.reindex(columns=expected_features, fill_value=0)
        X_chunk = X_chunk.apply(pd.to_numeric, errors='coerce').fillna(0.0)
                
        # --- PREDICTION ---
        probabilities = model.predict_proba(X_chunk)        
        
        insert_data = []
        for i in range(len(file_ids)):
            probs_row = probabilities[i]
            predicted_class = int(np.argmax(probs_row))
            conf = round(float(probs_row[predicted_class]) * 100.0, 2)
            
            insert_data.append((file_ids[i], conf, predicted_class))
            if predicted_class > 0 and conf >= 85.0:
                total_threats_found += 1
                
        conn.executemany("""
            INSERT INTO ai_predictions (file_id, ai_confidence, threat_class) 
            VALUES (?, ?, ?)
        """, insert_data)
        conn.commit()
        
        total_processed += len(chunk_df)
        print(f"   -> Scanned {total_processed:,} files... (Chunk Time: {time.time() - chunk_start:.2f}s)")

    conn.close()
    print("\n" + "="*80)
    print(f" 🌌 THREAT INFERENCE COMPLETE | Found {total_threats_found:,} Threats in {time.time() - start_time:.2f}s")
    print("="*80)


# =========================================================================
# MODULE 2: THE FUNCTION CLUSTER ENGINE (K-Means)
# =========================================================================
def run_function_cluster_engine():
    """Applies the Unsupervised K-Means archetypes to the function_data table."""
    brain = load_brain(BRAIN_PATH_FUNCTIONS)
    
    arch_key = next((k for k in brain.keys() if k.startswith('ARCHETYPES_K')), None)
    if not arch_key:
        print("❌ Could not find ARCHETYPES_Kxx in the loaded Brain.")
        sys.exit(1)
        
    archetypes_dict = brain[arch_key]
    arch_names = list(archetypes_dict.keys())
    num_clusters = len(archetypes_dict)
    
    print("\n" + "="*80)
    print(f" 🧬 INITIATING FUNCTION-LEVEL CLUSTERING (K={num_clusters})")
    print("="*80)

    print("🛫 RUNNING PRE-FLIGHT DIAGNOSTICS...")
    assessor = GalaxyDBHealthAssessor(DB_PATH)
    assessor.run_health_check()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"\n🏗️  Syncing schema in 'function_data' for {num_clusters} clusters...")
    cursor.execute("PRAGMA table_info(function_data)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    new_cols = ['func_archetype', 'func_z_score'] + [f"func_cluster_{i}" for i in range(num_clusters)]
    for col in new_cols:
        if col not in existing_columns:
            cursor.execute(f"ALTER TABLE function_data ADD COLUMN {col} REAL")
            
    for col in existing_columns:
        if col.startswith("func_cluster_"):
            try:
                idx = int(col.split("_")[-1])
                if idx >= num_clusters:
                    cursor.execute(f"ALTER TABLE function_data DROP COLUMN {col}")
            except Exception:
                pass
    conn.commit()

    chunk_size = 100000
    print(f"🚀 Igniting Cluster DB Update (Chunk Size: {chunk_size:,} functions)...")
    start_time = time.time()
    
    query = """
        SELECT * FROM function_data 
        WHERE loc >= 3 
        AND func_name NOT LIKE '%test%'
        AND func_name NOT LIKE '%mock%'
    """
    
    total_processed = 0
    medians = np.array(brain['SCALER_MEDIANS'])
    iqrs = np.array(brain['SCALER_IQRS'])
    safe_iqrs = np.where(iqrs == 0, 1.0, iqrs)
    centroids = np.array(list(archetypes_dict.values()))

    excluded_cols = {
        'id', 'file_id', 'func_name', 'complexity', 'loc', 'args', 
        'usage_status', 'keyword_density', 'func_archetype', 'func_z_score',
        'def_ownership', 'language', 'repo_name',
        'struct_camel_case', 'struct_snake_case', 'struct_pascal_case', 'struct_upper_case',
        'struct_short_vars', 'struct_long_vars', 'struct_tabs', 'struct_spaces', 'def_doc'
    }

    for chunk_df in pd.read_sql_query(query, conn, chunksize=chunk_size):
        chunk_start = time.time()
        
        for col in ['complexity', 'loc', 'args', 'keyword_density']:
            if col in chunk_df.columns:
                chunk_df[col] = chunk_df[col].fillna(0.0)

        chunk_df['log_loc'] = np.log1p(chunk_df['loc'])
        chunk_df['log_complexity'] = np.log1p(chunk_df['complexity'])
        chunk_df['log_args'] = np.log1p(chunk_df['args'])
        chunk_df['func_internal_density'] = chunk_df['complexity'] / chunk_df['loc'].replace(0, 1)

        dna_hit_cols = [
            c for c in chunk_df.columns 
            if c not in excluded_cols 
            and not c.startswith('log_') 
            and c != 'func_internal_density'
            and not c.startswith('total_')
            and not c.endswith('_total')
            and not c.startswith('summary_')
            and not c.startswith('func_cluster_')
            and not c.startswith('threat_')       # <--- NEW: Mirror the 62-dimension filter
            and not c.startswith('sec_')          # <--- NEW: Mirror the 62-dimension filter
        ]
        
        log_density_hit_cols = []
        safe_denom = chunk_df['loc'].replace(0, 1)
        
        for col in dna_hit_cols:
            raw_density = (chunk_df[col].fillna(0) / safe_denom) * 100.0
            log_name = f"log_density_{col}"
            chunk_df[log_name] = np.log1p(raw_density)
            log_density_hit_cols.append(log_name)

        telemetry_features = ['log_loc', 'log_complexity', 'log_args', 'keyword_density', 'func_internal_density']
        cluster_features = telemetry_features + log_density_hit_cols

        X_raw = chunk_df[cluster_features].fillna(0.0).to_numpy()
        
        # --- INFERENCE MATH ---
        X_scaled = (X_raw - medians) / safe_iqrs
        distances = np.linalg.norm(X_scaled[:, np.newaxis, :] - centroids, axis=2)
        min_indices = np.argmin(distances, axis=1)
        
        chunk_df['func_z_score'] = distances[np.arange(len(chunk_df)), min_indices]
        chunk_df['func_archetype'] = [arch_names[i] for i in min_indices]
        
        for i in range(num_clusters):
            chunk_df[f'func_cluster_{i}'] = distances[:, i]

        # --- DB BATCH UPDATE ---
        update_cols = ['func_archetype', 'func_z_score'] + [f'func_cluster_{i}' for i in range(num_clusters)]
        update_data = chunk_df[update_cols + ['id']].to_records(index=False).tolist()

        set_clause = ", ".join([f"{col} = ?" for col in update_cols])
        sql = f"UPDATE function_data SET {set_clause} WHERE id = ?"
        
        cursor.execute("BEGIN TRANSACTION")
        cursor.executemany(sql, update_data)
        conn.commit()
        
        total_processed += len(chunk_df)
        print(f"   -> Upgraded {total_processed:,} functions... (Chunk Time: {time.time() - chunk_start:.2f}s)")

    conn.close()
    
    print("\n" + "="*80)
    print(f" ✅ FUNCTION CLUSTERING COMPLETE | Processed {total_processed:,} functions in {time.time() - start_time:.2f}s")
    print("="*80)

    print("\n🛬 RUNNING POST-FLIGHT DIAGNOSTICS...")
    assessor = GalaxyDBHealthAssessor(DB_PATH)
    assessor.run_health_check()

# =========================================================================
# MODULE 2.5: FUNCTION CLUSTER ROLL-UP
# =========================================================================
def rollup_function_clusters():
    """Calculates the % of each function cluster per file and updates file_data."""
    print("\n" + "="*80)
    print(" 🧬 RECALCULATING FUNCTION CLUSTER RATIOS (Function -> File Rollup)")
    print("="*80)
    
    brain = load_brain(BRAIN_PATH_FUNCTIONS)
    arch_key = next((k for k in brain.keys() if k.startswith('ARCHETYPES_K')), None)
    if not arch_key:
        print("❌ Error: Could not find ARCHETYPES_Kxx in the loaded Brain.")
        sys.exit(1)
        
    arch_names = list(brain[arch_key].keys())
    num_clusters = len(arch_names)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Dynamically inject the single Vector column into file_data
    cursor.execute("PRAGMA table_info(file_data)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    
    if "func_cluster_ratios" not in existing_columns:
        print("🏗️  Adding dynamic 'func_cluster_ratios' vector column to file_data...")
        cursor.execute("ALTER TABLE file_data ADD COLUMN func_cluster_ratios TEXT DEFAULT ''")
    conn.commit()
    
    print("📊 Calculating Function Archetype distributions per file...")
    
    query = """
        SELECT file_id, func_archetype, COUNT(id) as count
        FROM function_data
        GROUP BY file_id, func_archetype
    """
    df = pd.read_sql_query(query, conn)
    
    if df.empty:
        print("❌ No functions found to roll up.")
        return
        
    name_to_idx = {name: i for i, name in enumerate(arch_names)}
    df['cluster_idx'] = df['func_archetype'].map(name_to_idx)
    df = df.dropna(subset=['cluster_idx']) 
    df['cluster_idx'] = df['cluster_idx'].astype(int)
    
    pivot = df.pivot(index='file_id', columns='cluster_idx', values='count').fillna(0)
    
    row_sums = pivot.sum(axis=1)
    pct_df = pivot.div(row_sums, axis=0) * 100.0
    
    print("💾 Injecting Stoichiometric Vector Strings into file_data...")
    
    update_data = []
    for file_id, row in pct_df.iterrows():
        # Collapse the exact K ratios into a single comma-separated string
        vals_str = ",".join([str(round(row.get(i, 0.0), 2)) for i in range(num_clusters)])
        update_data.append((vals_str, file_id))
        
    cursor.execute("BEGIN TRANSACTION")
    cursor.executemany("UPDATE file_data SET func_cluster_ratios = ? WHERE id = ?", update_data)
    conn.commit()
    conn.close()
    
    print(f"🎉 SUCCESS: {len(update_data):,} files updated with dynamic structural DNA vectors!")
    print("="*80 + "\n")

# =========================================================================
# MODULE 2.75: RETROACTIVE GINI PATCH
# =========================================================================
def retroactive_gini_fix():
    """Calculates missing Gini coefficients using existing function data."""
    print("\n" + "="*80)
    print(" 🩹 RETROACTIVELY CALCULATING GINI COEFFICIENTS")
    print("="*80)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("📊 Fetching function complexities from database...")
    # Get all function complexities grouped by file_id
    query = """
        SELECT file_id, GROUP_CONCAT(complexity) as comp_vector
        FROM function_data
        GROUP BY file_id
    """
    df = pd.read_sql_query(query, conn)
    
    if df.empty:
        print("❌ No functions found.")
        return
        
    print("🧮 Calculating Gini math in RAM...")
    update_data = []
    
    for _, row in df.iterrows():
        file_id = row['file_id']
        comp_str = row['comp_vector']
        if not comp_str:
            continue
            
        # Convert the SQL string "5,1,10" into a list of floats [5.0, 1.0, 10.0]
        complexities = [float(x) for x in str(comp_str).split(',')]
        
        # Gini requires more than 1 function to have inequality
        if len(complexities) > 1 and sum(complexities) > 0:
            gini_val = calculate_gini(complexities)
            update_data.append((round(gini_val, 3), file_id))
    
    print(f"💾 Injecting {len(update_data):,} repaired Gini coefficients into file_data...")
    
    cursor.execute("BEGIN TRANSACTION")
    cursor.executemany("UPDATE file_data SET func_complexity_gini = ? WHERE id = ?", update_data)
    conn.commit()
    conn.close()
    
    print("🎉 SUCCESS: The Gini flatline has been cured!")
    print("="*80 + "\n")

def apply_file_clusters():
    print("\n" + "="*80)
    
    print(" 💉 PHASE 3: FILE CLUSTER INJECTION")
    print("="*80)
    
    csv_path = SCRIPT_DIR / "kmeans_clustering" / "kmeans_file_clusters.csv"
    
    if not csv_path.exists():
        print(f"❌ Error: Could not find {csv_path}. Did you run cluster_files.py?")
        return
        
    print("📡 Connecting to Master Database...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("🧬 Reading File Clusters CSV...")
    df = pd.read_csv(csv_path)
    
    if 'file_archetype' not in df.columns or 'file_fingerprint' not in df.columns:
        print("❌ Error: CSV is missing 'file_archetype' or 'file_fingerprint'. Re-run cluster_files.py.")
        return
        
    print("💾 Injecting File Clusters into Master Database (This will take a few seconds)...")
    
    # ---> THE FIX: Map the correct FILE columns, not the REPO columns! <---
    update_data = [
        (f"file_cluster_{int(row['file_archetype'])}", str(row['file_fingerprint']), row['id']) 
        for _, row in df.iterrows()
    ]
    
    # Fast bulk injection into file_data
    cursor.execute("BEGIN TRANSACTION")
    cursor.executemany("UPDATE file_data SET file_archetype = ?, file_fingerprint = ? WHERE id = ?", update_data)
    conn.commit()
    conn.close()
    
    print(f"🎉 SUCCESS: {len(update_data):,} files permanently stamped with their Vector Fingerprint!")
    print("="*80 + "\n")

# =========================================================================
# MODULE 3.5: FILE CLUSTER ROLL-UP (File -> Repo)
# =========================================================================
def rollup_file_clusters():
    """Calculates the % of each file cluster per repo and updates repo_data."""
    print("\n" + "="*80)
    print(" 🌌 RECALCULATING FILE CLUSTER RATIOS (File -> Repo Rollup)")
    print("="*80)
    
    brain_path_files = SCRIPT_DIR / "kmeans_clustering" / "ml_inference_brain_files.txt"
    brain = load_brain(brain_path_files)
    
    arch_key = next((k for k in brain.keys() if k.startswith('ARCHETYPES_K')), None)
    if not arch_key:
        print("❌ Error: Could not find ARCHETYPES_Kxx in the loaded File Brain.")
        sys.exit(1)
        
    arch_names = list(brain[arch_key].keys())
    num_clusters = len(arch_names)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("📊 Calculating File Archetype distributions per repository...")
    
    query = """
        SELECT repo_name, file_archetype, COUNT(id) as count
        FROM file_data
        WHERE file_archetype IS NOT NULL AND file_archetype != ''
        GROUP BY repo_name, file_archetype
    """
    df = pd.read_sql_query(query, conn)
    
    if df.empty:
        print("❌ No files found to roll up. Did you run apply_file_clusters?")
        return
        
    # Map 'file_cluster_X' to its index
    name_to_idx = {name: i for i, name in enumerate(arch_names)}
    df['cluster_idx'] = df['file_archetype'].map(name_to_idx)
    df = df.dropna(subset=['cluster_idx']) 
    df['cluster_idx'] = df['cluster_idx'].astype(int)
    
    pivot = df.pivot(index='repo_name', columns='cluster_idx', values='count').fillna(0)
    
    # Ensure all columns from 0 to num_clusters - 1 exist even if a cluster is missing in this DB slice
    for i in range(num_clusters):
        if i not in pivot.columns:
            pivot[i] = 0.0
            
    row_sums = pivot.sum(axis=1)
    pct_df = pivot.div(row_sums, axis=0) * 100.0
    
    print("💾 Injecting File Composition Strings into repo_data...")
    
    update_data = []
    for repo_name, row in pct_df.iterrows():
        # Collapse the exact K ratios into a single comma-separated string
        vals_str = ",".join([str(round(row.get(i, 0.0), 2)) for i in range(num_clusters)])
        update_data.append((vals_str, repo_name))
        
    cursor.execute("BEGIN TRANSACTION")
    cursor.executemany("UPDATE repo_data SET file_composition = ? WHERE repo_name = ?", update_data)
    conn.commit()
    conn.close()
    
    print(f"🎉 SUCCESS: {len(update_data):,} repositories updated with dynamic file composition vectors!")
    print("="*80 + "\n")

def apply_repo_clusters():
    print("\n" + "="*80)
    print(" 💉 PHASE 4: REPO-LEVEL META-ARCHITECTURE INJECTION")
    print("="*80)
    
    csv_path = SCRIPT_DIR / "kmeans_clustering" / "kmeans_repo_meta_species.csv"
    
    if not csv_path.exists():
        print(f"❌ Error: Could not find {csv_path}. Did you run cluster_repos.py?")
        return
        
    print("📡 Connecting to Master Database...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ensure the columns exist just in case
    cursor.execute("PRAGMA table_info(repo_data)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    if 'repo_archetype' not in existing_columns:
        cursor.execute("ALTER TABLE repo_data ADD COLUMN repo_archetype TEXT")
        cursor.execute("ALTER TABLE repo_data ADD COLUMN repo_fingerprint TEXT")
        cursor.execute("ALTER TABLE repo_data ADD COLUMN file_composition TEXT")
        
    print("🧬 Reading Repo Meta-Species CSV...")
    df = pd.read_csv(csv_path)
    
    print("💾 Injecting Vector Fingerprints into 'repo_data' (This will take a second)...")
    
    update_data = [
        (
            f"Meta-Species {int(row['repo_archetype'])}", 
            str(row['repo_fingerprint']), 
            str(row['file_composition']),
            row['repo_name']
        ) 
        for _, row in df.iterrows()
    ]
    
    cursor.execute("BEGIN TRANSACTION")
    cursor.executemany("UPDATE repo_data SET repo_archetype = ?, repo_fingerprint = ?, file_composition = ? WHERE repo_name = ?", update_data)
    conn.commit()
    conn.close()
    
    print(f"🎉 SUCCESS: {len(update_data):,} repositories permanently stamped with their Meta-Fingerprint!")
    print("="*80 + "\n")
    
# =========================================================================
# THE GATEKEEPER
# =========================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GitGalaxy Master Database Machine Learning Synchronizer")
    parser.add_argument('--update', type=str, required=True, 
                        choices=['threat', 'function_clusters', 'rollup_function_clusters', 'retroactive_gini', 'apply_file_clusters', 'rollup_file_clusters', 'apply_repo_clusters'], 
                        help="Specify which ML pipeline to run to prevent accidental overwrites.")
    
    args = parser.parse_args()
    
    if args.update == 'threat':
        run_threat_engine()
    elif args.update == 'function_clusters':
        run_function_cluster_engine()
    elif args.update == 'rollup_function_clusters':
        rollup_function_clusters()
    elif args.update == 'retroactive_gini':
        retroactive_gini_fix()
    elif args.update == 'apply_file_clusters':
        apply_file_clusters()
    elif args.update == 'rollup_file_clusters':
        rollup_file_clusters()
    elif args.update == 'apply_repo_clusters':
        apply_repo_clusters()