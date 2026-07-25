import os
# MUST BE SET BEFORE IMPORTING NUMPY/SKLEARN TO PREVENT C-LEVEL CRASHES
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import sqlite3
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import RobustScaler
import time
from sklearn.metrics import silhouette_score
from pathlib import Path
import warnings
import argparse
import concurrent.futures
import multiprocessing

warnings.filterwarnings('ignore')

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR.parent / "data" / "gitgalaxy_master.db"

# =========================================================================
# MULTIPROCESSING WORKER
# =========================================================================
def _evaluate_single_k(args):
    test_k, X_data, X_sample, sample_idx, n_init_val, max_iter_val = args
    
    kmeans_test = KMeans(n_clusters=test_k, random_state=42, n_init=n_init_val, max_iter=max_iter_val)
    labels = kmeans_test.fit_predict(X_data)
    wcss = kmeans_test.inertia_
    sample_labels = labels[sample_idx]
    sil_score = silhouette_score(X_sample, sample_labels)
    return test_k, wcss, sil_score

def run_dna_clustering(target_language=None, force_k=None, accuracy='medium'):
    if not DB_PATH.exists():
        print(f"❌ Error: Master Database not found at {DB_PATH}")
        return None, 0.0, 0.0

    profiles = {
        'micro':    {'limit': 25000,  'sil_sample': 5000,  'n_init': 2,  'max_iter': 150},
        'low':      {'limit': 50000,  'sil_sample': 10000, 'n_init': 3,  'max_iter': 300},
        'standard': {'limit': 125000, 'sil_sample': 20000, 'n_init': 8,  'max_iter': 450},
        'medium':   {'limit': 250000, 'sil_sample': 30000, 'n_init': 15, 'max_iter': 600},
        'high':     {'limit': 500000, 'sil_sample': 45000, 'n_init': 20, 'max_iter': 900}
    }
    prof = profiles[accuracy]

    print(f"📡 Connecting to Galactic Census Database at: {DB_PATH}...")
    
    print("\n" + "="*80)
    print(" 🎛️  MLOPS RIGOR PROFILES (Compute vs. Confidence)")
    print("="*80)
    for p_name, p_data in profiles.items():
        print(f"   [{p_name.upper():<8}] | N: {p_data['limit']:>7,} | n_init: {p_data['n_init']:>2} | max_iter: {p_data['max_iter']:>4}")
    print("-" * 80)
    print(f"⚙️  ACTIVE SETTING: You are running the [{accuracy.upper()}] profile.\n")
    
    # --- DYNAMIC QUERY FOR FILE CLUSTERING ---
    print("🌌 Running Global File-Level Clustering...\n")
    
    # We only cluster files with enough logic to form an architectural pattern
    query = f"""
        SELECT * FROM file_data 
        WHERE coding_loc >= 10 
        AND language != 'plaintext'
        AND language != 'json'
        AND language != 'markdown'
        ORDER BY RANDOM() LIMIT {prof['limit']}
    """
    output_csv = SCRIPT_DIR / "kmeans_file_clusters.csv"
    brain_output_path = SCRIPT_DIR / "ml_inference_brain_files.txt"
    
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if len(df) == 0:
        print("❌ Error: No files found matching that criteria.")
        return None, 0.0, 0.0

    # =========================================================================
    # 1. ENGINEER FILE GEOMETRIES
    # =========================================================================
    print("⚙️ Engineering file geometries and function stoichiometry...")
    
    df['coding_loc'] = df['coding_loc'].fillna(0.0)
    df['log_coding_loc'] = np.log1p(df['coding_loc'])
    
    # Ensure the newly rolled-up function columns exist and are zero-filled
    rollup_cols = ['func_z_max', 'func_z_mean', 'func_z_median', 'pct_z_above_5', 'pct_z_above_15']
    for c in rollup_cols:
        if c in df.columns:
            df[c] = df[c].fillna(0.0)

    # ---> NEW: Unpack the dynamic Vector String into temporary K-Means columns <---
    composition_features = []
    if 'func_cluster_ratios' in df.columns:
        # Helper to safely parse the string into a list of floats
        def parse_ratios(val):
            if not val or pd.isna(val): return []
            try: return [float(x) for x in str(val).split(',')]
            except Exception: return []
            
        df['parsed_ratios'] = df['func_cluster_ratios'].apply(parse_ratios)
        max_k_found = df['parsed_ratios'].apply(len).max()
        
        if max_k_found > 0:
            for i in range(max_k_found):
                col_name = f'micro_{i}_pct'
                log_col_name = f'log_micro_{i}_pct'
                
                # Extract raw percentage
                df[col_name] = df['parsed_ratios'].apply(lambda x: x[i] if i < len(x) else 0.0)
                
                # Immediately apply Log transform (np.log1p handles 0.0 safely)
                df[log_col_name] = np.log1p(df[col_name])
                
                # Only append the LOG version to our features to prevent colinearity!
                composition_features.append(log_col_name)
                
                # Add the raw column to rollup_cols so Phase 2 ignores it completely!
                rollup_cols.append(col_name)

    # =========================================================================
    # 2. THE PURE DNA MATRIX & DENSITY CONVERSION
    # =========================================================================
    # Exclude metadata, stylistic choices, and obsolete cluster columns
    excluded_cols = {
        'id', 'file_id', 'file_name', 'file_path', 'repo_name', 'commit_date',
        'author', 'purpose', 'import_list', 'constellation', 'archetype', 'global_drift',
        'total_loc', 'coding_loc', 'comment_loc', 'logic_loc', 'language',
        'struct_camel_case', 'struct_snake_case', 'struct_pascal_case', 'struct_upper_case',
        'struct_short_vars', 'struct_long_vars', 'struct_tabs', 'struct_spaces', 'def_doc', 'def_ownership',
        'silo_risk', 'raw_churn_freq', 'risk_spec_match',
        'planned_debt', 'fragile_debt', 'graveyard', 'spec_exposure' # <--- EXCLUDE HUMAN INTENT
    }

    # -------------------------------------------------------------------------
    # PROTECTED METRICS (Do NOT divide these by LOC)
    # -------------------------------------------------------------------------
    pre_calculated_metrics = [
        'control_flow_ratio', 'avg_func_loc', 'avg_func_complexity', 
        'max_func_complexity', 'avg_func_args', 'func_complexity_gini', 
        'func_internal_density', 'dependency_density', 'encapsulation_ratio'
    ]

    log_precalc_cols = []
    for col in pre_calculated_metrics:
        if col in df.columns:
            log_name = f"log_{col}"
            # Log transform them to handle outliers, but NO division!
            df[log_name] = np.log1p(df[col].fillna(0.0))
            log_precalc_cols.append(log_name)

    # Find the standard hit columns AND raw counts (like function_count, class_count, popularity)
    raw_hit_cols = [
        c for c in df.select_dtypes(include=[np.number]).columns 
        if c not in excluded_cols 
        and not c.startswith('log_')
        and not c.startswith('total_')
        and not c.endswith('_total')
        and not c.startswith('summary_')
        and not c.startswith('arch_cluster_')
        and not c.startswith('func_cluster_')
        and not c.startswith('threat_')       # <--- NEW: Exclude threat vectors
        and not c.startswith('sec_')          # <--- NEW: Exclude sec_graveyard, etc.
        and c not in rollup_cols 
        and c not in pre_calculated_metrics # Protect the VIP metrics from division
    ]
    
    log_density_hit_cols = []
    safe_denom = df['coding_loc'].replace(0, 1)

    for col in raw_hit_cols:
        raw_density_name = f"raw_density_{col}"
        df[raw_density_name] = (df[col].fillna(0) / safe_denom) * 100.0
        
        log_density_name = f"log_density_{col}"
        df[log_density_name] = np.log1p(df[raw_density_name])
        log_density_hit_cols.append(log_density_name)

    # =========================================================================
    # 3. THE MULTI-MODAL MACRO FEATURE VECTOR
    # =========================================================================
    telemetry_features = [
        'log_coding_loc', 
        'func_z_max', 
        'func_z_mean', 
        'pct_z_above_5', 
        'pct_z_above_15'
    ] + log_precalc_cols 
    
    # composition_features is now dynamically populated in Phase 1
    cluster_features = telemetry_features + composition_features + log_density_hit_cols

    df = df.dropna(subset=cluster_features).copy()
    X_raw = df[cluster_features]

    print(f"🧠 Preparing Unsupervised ML on {len(df):,} files across {len(cluster_features)} dimensions...")
    math_start_time = time.time()

    # =========================================================================
    # 4. ROBUST SCALING
    # =========================================================================
    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(X_raw)

    # =========================================================================
    # 4.5 MATHEMATICAL DIAGNOSTICS (Elbow & Silhouette)
    # =========================================================================
    print("\n" + "="*80)
    print(" 📐 RUNNING MATHEMATICAL DIAGNOSTICS (Finding Optimal 'k')")
    print("="*80)
    
    sample_size = min(40000, len(X_scaled))
    np.random.seed(42)
    sample_indices = np.random.choice(len(X_scaled), sample_size, replace=False)
    X_sample = X_scaled[sample_indices]

    best_k = 7
    max_sil = 0.0  

    if force_k is not None:
        print(f"🚀 OVERRIDE: Forcing K-Means to explicitly build {force_k} clusters...")
        best_k = force_k
    else:
        test_k_values = list(range(10, 25))
        
        print(f"{'k-Clusters':<12} | {'WCSS (Elbow / Lower is Better)':<35} | {'Silhouette Score (Peak is Better)'}")
        print("-" * 80)

        tasks = [(k, X_scaled, X_sample, sample_indices, prof['n_init'], prof['max_iter']) for k in test_k_values]
        
        max_workers = max(1, multiprocessing.cpu_count() - 2)
        print(f"🚀 Firing up {max_workers} CPU cores for parallel K-evaluation...\n")

        results = []
        ctx = multiprocessing.get_context('spawn')
        
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx) as executor:
            for result in executor.map(_evaluate_single_k, tasks):
                results.append(result)
                
        sorted_results = sorted(results, key=lambda x: x[0])
        max_sil = max(r[2] for r in sorted_results)
        
        # Select the absolute highest mathematical peak
        best_k = max(sorted_results, key=lambda x: x[2])[0]
                        
        for test_k, wcss, sil_score in sorted_results:
            markers = []
            if sil_score == max_sil:
                markers.append("🏔️ PEAK")
            if test_k == best_k:
                markers.append("⭐ HEURISTIC WINNER")
                
            marker_str = " + ".join(markers) if markers else ""
            print(f" k={test_k:<9} | {wcss:,.0f} {' ' * (32 - len(f'{wcss:,.0f}'))} | {sil_score:.4f} {marker_str}")

    k_values = [best_k]
    
    print("\n" + "="*80)
    print(f" 🧬 K-MEANS FILE-LEVEL PROFILING (k={k_values[0]})")
    print("="*80)

    for k in k_values:
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=prof['n_init'], max_iter=prof['max_iter'])
        cluster_labels = kmeans.fit_predict(X_scaled)
        
        distances = kmeans.transform(X_scaled)
        
        df['file_fingerprint'] = [','.join(f"{d:.4f}" for d in row) for row in distances]
        df['file_archetype'] = cluster_labels
        
        for cluster_id in range(k):
            cluster_data = df[df['file_archetype'] == cluster_id]
            size = len(cluster_data)
            pct = (size / len(df)) * 100
            
            scaled_centroid = kmeans.cluster_centers_[cluster_id]
            scaled_series = pd.Series(scaled_centroid, index=cluster_features)
            
            top_drivers = scaled_series[scaled_series > 0].sort_values(ascending=False).head(20)
            
            lang_counts = cluster_data['language'].value_counts()
            top_langs = lang_counts.head(5)
            langs_str = ", ".join([f"{l} ({count/size*100:.1f}%)" for l, count in top_langs.items()])

            cluster_points = X_scaled[cluster_labels == cluster_id]
            centroid = kmeans.cluster_centers_[cluster_id]
            dispersion = np.mean(np.linalg.norm(cluster_points - centroid, axis=1))

            print(f"\n🧪 FILE CLUSTER {cluster_id} | Size: {size:,} files ({pct:.1f}%)")
            print(f"   📐 Spatial Dispersion: {dispersion:.2f}")
            print(f"   🧬 Language Make-up: {langs_str}")
            print(f"   🔥 Defining Signatures (Over-represented DNA):")
            for f_name, iqr_score in top_drivers.items():
                clean_name = f_name.replace('log_density_hit_sec_', 'SECURITY: ')\
                                   .replace('log_density_hit_', 'DNA: ')\
                                   .replace('log_micro_', 'Log Stoichiometry (Func Cluster ')\
                                   .replace('micro_', 'Stoichiometry (Func Cluster ')\
                                   .replace('_pct', '% )')\
                                   .replace('log_', 'Log ')\
                                   .replace('_', ' ').title()
                print(f"      - {clean_name}: +{iqr_score:.2f} IQR")

    # =========================================================================
    # 5. EXPORT THE ML INFERENCE BRAIN
    # =========================================================================
    best_k = k_values[0]
    
    # Fully automated generic naming for rapid prototyping
    professional_names = [f"file_cluster_{i}" for i in range(best_k)]

    medians = [round(x, 3) for x in scaler.center_.tolist()]
    iqrs = [round(x, 3) for x in scaler.scale_.tolist()]

    py_string = "ML_INFERENCE_BRAIN = {\n"
    py_string += f"    'SCALER_MEDIANS': {medians},\n"
    py_string += f"    'SCALER_IQRS': {iqrs},\n"
    py_string += f"    'ARCHETYPES_K{k_values[0]}': {{\n"

    for i, name in enumerate(professional_names):
        if i < len(kmeans.cluster_centers_):
            centroid = [round(x, 3) for x in kmeans.cluster_centers_[i].tolist()]
            py_string += f"        '{name}': {centroid},\n"

    py_string += "    }\n"
    py_string += "}\n"

    with open(brain_output_path, 'w', encoding='utf-8') as f:
        f.write(py_string)
        
    print(f"\n🧠 ML Inference Brain exported to: {brain_output_path}")
    
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    export_cols = ['id', 'file_name', 'coding_loc', 'file_archetype', 'file_fingerprint'] + cluster_features
    df[export_cols].to_csv(output_csv, index=False)
    
    print(f"✅ Full Matrix exported to: {output_csv}")
    
    math_end_time = time.time()
    elapsed_minutes = (math_end_time - math_start_time) / 60.0
    return best_k, max_sil, elapsed_minutes

if __name__ == "__main__":
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser()
    parser.add_argument('--accuracy', type=str, choices=['micro', 'low', 'standard', 'medium', 'high'], default='standard')
    parser.add_argument('--cluster', type=int, default=None, help="Force a specific number of clusters (e.g., --cluster 24)")
    args = parser.parse_args()
    
    # ---> THE MLOPS STABILITY OVERRIDE <---
    # If the user forces a specific cluster count, automatically bump the rigor to HIGH
    # to prevent SQL random sampling from shifting the K-Means center of gravity!
    if args.cluster is not None and args.accuracy != 'high':
        print("\n🛡️  FORCED CLUSTER DETECTED: Automatically upgrading to HIGH accuracy for deterministic stability.")
        args.accuracy = 'high'
    
    run_dna_clustering(force_k=args.cluster, accuracy=args.accuracy)