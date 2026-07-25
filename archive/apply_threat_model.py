import sqlite3
import pandas as pd
import numpy as np
import xgboost as xgb
import time
from pathlib import Path
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
DB_PATH = SCRIPT_DIR / "gitgalaxy_master.db"
MODEL_PATH = SCRIPT_DIR / "gitgalaxy_malware_xgb_multiclass.json"
CHUNK_SIZE = 50000  # Process 50k files at a time to save RAM

def run_global_inference():
    print(f"🧠 Loading XGBoost Brain: {MODEL_PATH.name}...")
    try:
        model = xgb.XGBClassifier()
        model.load_model(MODEL_PATH)
        expected_features = model.feature_names_in_
    except Exception as e:
        print(f"❌ Failed to load model: {e}")
        return

    print(f"📡 Connecting to Master Database: {DB_PATH.name}...")
    conn = sqlite3.connect(DB_PATH)
    
    # 1. Create the safe "Sidecar" table
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

    print(f"🚀 Igniting Global Scan (Chunk Size: {CHUNK_SIZE:,} files)...")
    start_time = time.time()
    
    total_processed = 0
    total_threats_found = 0

    # 2. Query the database in chunks to protect RAM
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
    
    for chunk_df in pd.read_sql_query(query, conn, chunksize=CHUNK_SIZE):
        chunk_start = time.time()
        
        # Save IDs for the SQL insert later
        file_ids = chunk_df['id'].tolist()
        
        # =====================================================================
        # FEATURE ENGINEERING (MUST PERFECTLY MATCH TRAINING SCRIPT)
        # =====================================================================
        # 1. Null Safety
        null_cols = ['logic_loc', 'real_avg_func_loc', 'real_avg_func_complexity', 'real_function_count', 'direct_upstream', 'total_downstream']
        for c in null_cols:
            if c in chunk_df.columns:
                chunk_df[c] = chunk_df[c].fillna(0.0)

        # 2. Function Geometry
        chunk_df['parsed_vector'] = chunk_df['func_complexity_vector'].apply(parse_concat_vector)
        chunk_df['complexity_gini'] = chunk_df.apply(lambda row: calculate_gini(row['parsed_vector']) if row['real_function_count'] > 1 else 0.0, axis=1)
        chunk_df['func_internal_density'] = chunk_df['real_avg_func_complexity'] / chunk_df['real_avg_func_loc'].replace(0, 1)
        chunk_df['func_density'] = chunk_df['real_function_count'] / (chunk_df['logic_loc'].replace(0, 1) / 100.0)

        # 3. Log Topological Exposure (The Blast Radius)
        chunk_df['log_direct_upstream'] = np.log1p(chunk_df['direct_upstream'])
        chunk_df['log_total_downstream'] = np.log1p(chunk_df['total_downstream'])

        # 4. Core DNA Densities
        raw_count_cols = [c for c in chunk_df.columns if c.startswith('core_') or c.startswith('risk_') or c.startswith('design_') or c.startswith('threat_')]
        raw_count_cols = [c for c in raw_count_cols if c != 'threat_class'] 
        
        safe_denom = chunk_df['logic_loc'].replace(0, np.nan).fillna(chunk_df['coding_loc']).replace(0, 1)    
        for col in raw_count_cols:
            chunk_df[f"density_{col}"] = (chunk_df[col] / safe_denom) * 100.0
            
        # 5. Surgical Pruning
        cols_to_drop = [
            'id', 'repo_name', 'commit_date', 'file_name', 'file_path', 
            'constellation', 'archetype', 'logic_loc_bin', 'import_list', 
            'author', 'is_malware', 'threat_class', 'confirmed_kill_chain',
            'raw_churn_freq', 'popularity', 'ai_threat_confidence', 'language',
            'purpose', 'pos_x', 'pos_y', 'pos_z', 'parsed_vector', 'func_complexity_vector',
            'total_loc', 'coding_loc', 'comment_loc', 'logic_loc', 'structural_mass',
            'cog_raw', 'ownership_entropy', 'silo_risk', 'function_count', 
            'avg_func_loc', 'avg_func_complexity', 'max_func_complexity', 'avg_func_args',
            'direct_upstream', 'direct_downstream', 'total_upstream', 'total_downstream',
            'direct_upstream_ratio', 'direct_downstream_ratio', 'total_upstream_ratio',
            'total_downstream_ratio', 'global_drift', 'local_drift', 'logic_density',
            'real_avg_func_loc', 'real_avg_func_complexity', 'real_function_count'
        ]
        
        # THE FIX: using chunk_df instead of df
        stale_clusters = [c for c in chunk_df.columns if c.startswith('arch_cluster_')] 
        cols_to_drop.extend(stale_clusters)
        
        cols_to_drop.extend(raw_count_cols)
        
        X_chunk = chunk_df.drop(columns=[c for c in cols_to_drop if c in chunk_df.columns])
        
        if 'repo_z_score' in X_chunk.columns:
            X_chunk['repo_z_score'] = pd.to_numeric(X_chunk['repo_z_score'], errors='coerce')
        
        # One-Hot Encode Macro-Species
        cols_to_encode = []
        if 'repo_macro_species' in X_chunk.columns: cols_to_encode.append('repo_macro_species')
        if cols_to_encode:
            X_chunk = pd.get_dummies(X_chunk, columns=cols_to_encode, dummy_na=False)
            
        # Drop unexpected strings
        object_cols = X_chunk.select_dtypes(include=['object']).columns
        if len(object_cols) > 0:
            X_chunk = X_chunk.drop(columns=object_cols)
            
        X_chunk = X_chunk.fillna(0).replace([np.inf, -np.inf], 0)
        
        # CRITICAL FIX: Reindex to exactly match the Model's expected columns
        X_chunk = X_chunk.reindex(columns=expected_features, fill_value=0)
        
        # =====================================================================
        # PREDICTION & STORAGE
        # =====================================================================
        X_chunk = X_chunk.apply(pd.to_numeric, errors='coerce').fillna(0.0)
                
        probabilities = model.predict_proba(X_chunk)        
        
        insert_data = []
        for i in range(len(file_ids)):
            probs_row = probabilities[i]
            predicted_class = int(np.argmax(probs_row))
            conf = round(float(probs_row[predicted_class]) * 100.0, 2)
            
            insert_data.append((file_ids[i], conf, predicted_class))
            
            # Count it as a threat if it predicts classes 1-4 with high confidence
            if predicted_class > 0 and conf >= 85.0:
                total_threats_found += 1
                
        conn.executemany("""
            INSERT INTO ai_predictions (file_id, ai_confidence, threat_class) 
            VALUES (?, ?, ?)
        """, insert_data)
        conn.commit()
        
        total_processed += len(chunk_df)
        chunk_time = time.time() - chunk_start
        print(f"   -> Scanned {total_processed:,} files... (Chunk Time: {chunk_time:.2f}s)")

    total_time = time.time() - start_time
    conn.close()

    print("\n" + "="*60)
    print(" 🌌 GLOBAL INFERENCE COMPLETE")
    print("="*60)
    print(f" Total Files Scanned : {total_processed:,}")
    print(f" Total Time          : {total_time:.2f} seconds")
    print(f" AI Threats Detected : {total_threats_found:,} (at >= 85.0% confidence)")
    print("="*60)

if __name__ == "__main__":
    run_global_inference()