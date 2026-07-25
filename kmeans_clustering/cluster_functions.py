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
# HELPER FUNCTIONS FOR FUNCTION GEOMETRY
# =========================================================================
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

# =========================================================================
# MULTIPROCESSING WORKER
# =========================================================================
def _evaluate_single_k(args):
    # Cleanly unpack all 6 arguments passed from the main process
    test_k, X_data, X_sample, sample_idx, n_init_val, max_iter_val = args
    
    # Use the dynamically passed n_init and max_iter values from the accuracy profile
    kmeans_test = KMeans(n_clusters=test_k, random_state=42, n_init=n_init_val, max_iter=max_iter_val)
    labels = kmeans_test.fit_predict(X_data)
    wcss = kmeans_test.inertia_
    sample_labels = labels[sample_idx]
    sil_score = silhouette_score(X_sample, sample_labels)
    return test_k, wcss, sil_score

def run_dna_clustering(target_language=None, force_k=None, accuracy='standard'):
    if not DB_PATH.exists():
        print(f"❌ Error: Master Database not found at {DB_PATH}")
        return None, 0.0, 0.0

    # Define the mathematical rigorousness profiles
    profiles = {
        'micro':    {'limit': 25000,  'sil_sample': 5000,  'n_init': 2,  'max_iter': 150,  'use': 'Sanity Check'},
        'low':      {'limit': 50000,  'sil_sample': 10000, 'n_init': 3,  'max_iter': 300,  'use': 'Fast Prototyping'},
        'standard': {'limit': 125000, 'sil_sample': 20000, 'n_init': 8,  'max_iter': 450,  'use': 'Balanced Baseline'},
        'medium':   {'limit': 250000, 'sil_sample': 30000, 'n_init': 15, 'max_iter': 600,  'use': 'Nightly Builds'},
        'high':     {'limit': 500000, 'sil_sample': 45000, 'n_init': 20, 'max_iter': 1500, 'use': 'Scientific Ground Truth'}
    }
    prof = profiles.get(accuracy, profiles['standard'])

    print(f"📡 Connecting to Galactic Census Database at: {DB_PATH}...")
    
    print("\n" + "="*80)
    print(" 🎛️  MLOPS RIGOR PROFILES (Compute vs. Confidence)")
    print("="*80)
    for p_name, p_data in profiles.items():
        print(f"   [{p_name.upper():<8}] | N: {p_data['limit']:>7,} | n_init: {p_data['n_init']:>2} | max_iter: {p_data['max_iter']:>4} | Use: {p_data['use']}")
    print("-" * 80)
    print(f"⚙️  ACTIVE SETTING: You are running the [{accuracy.upper()}] profile.\n")
    
    # --- DYNAMIC QUERY FOR FUNCTION GEOMETRY ---
    print("🌌 Running Global Function Clustering...\n")
    # Note: We filter out tiny functions (< 3 LOC) to prevent divide-by-zero density explosions
    # and exclude tests to focus on architectural execution logic.
    query = f"""
        SELECT f.*, c.language, c.repo_name 
        FROM function_data f
        JOIN file_data c ON f.file_id = c.id
        WHERE f.loc >= 3 
        AND f.func_name NOT LIKE '%test%'
        AND f.func_name NOT LIKE '%mock%'
        ORDER BY RANDOM() LIMIT {prof['limit']}
    """
    output_csv = SCRIPT_DIR / "kmeans_function_micro_species.csv"
    brain_output_path = SCRIPT_DIR / "ml_inference_brain_functions.txt"
    
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if len(df) == 0:
        print("❌ Error: No files found matching that criteria.")
        return None, 0.0, 0.0

    # =========================================================================
    # 1. ENGINEER FUNCTION GEOMETRIES & LOG TRANSFORMS
    # =========================================================================
    print("⚙️ Engineering function geometries (Internal Density & Log Transforms)...")
    
    # Fill nulls for safe math
    for col in ['complexity', 'loc', 'args', 'keyword_density']:
        if col in df.columns:
            df[col] = df[col].fillna(0.0)

    # Core Geometry Log Transforms
    df['log_loc'] = np.log1p(df['loc'])
    df['log_complexity'] = np.log1p(df['complexity'])
    df['log_args'] = np.log1p(df['args'])
    
    # Internal Logic Density (Decision points per line of code)
    df['func_internal_density'] = df['complexity'] / df['loc'].replace(0, 1)

    # =========================================================================
    # 2. THE PURE DNA MATRIX & DENSITY CONVERSION
    # =========================================================================
    excluded_cols = {
        'id', 'file_id', 'func_name', 'complexity', 'loc', 'args', 
        'usage_status', 'keyword_density', 'func_archetype', 'func_z_score',
        'def_ownership', 'language', 'repo_name',
        'struct_camel_case', 'struct_snake_case', 'struct_pascal_case', 'struct_upper_case',
        'struct_short_vars', 'struct_long_vars', 'struct_tabs', 'struct_spaces', 'def_doc'
    }

    dna_hit_cols = [
        c for c in df.columns 
        if c not in excluded_cols 
        and not c.startswith('log_') 
        and c != 'func_internal_density'
        and not c.startswith('total_')
        and not c.endswith('_total')
        and not c.startswith('summary_')
        and not c.startswith('func_cluster_') 
        and not c.startswith('threat_')       # <--- NEW: Exclude threat vectors
        and not c.startswith('sec_')          # <--- NEW: Exclude sec_graveyard, etc.
    ]
    
    log_density_hit_cols = []
    safe_denom = df['loc'].replace(0, 1)

    for col in dna_hit_cols:
        raw_density_name = f"raw_density_{col}"
        df[raw_density_name] = (df[col].fillna(0) / safe_denom) * 100.0
        
        log_density_name = f"log_density_{col}"
        df[log_density_name] = np.log1p(df[raw_density_name])
        log_density_hit_cols.append(log_density_name)

    # =========================================================================
    # 3. THE MULTI-MODAL FEATURE VECTOR
    # =========================================================================
    telemetry_features = [
        'log_loc', 
        'log_complexity', 
        'log_args', 
        'keyword_density', 
        'func_internal_density'
    ]
    
    cluster_features = telemetry_features + log_density_hit_cols

    df = df.dropna(subset=cluster_features).copy()
    X_raw = df[cluster_features]

    print(f"🧠 Preparing Unsupervised ML on {len(df):,} functions across {len(cluster_features)} dimensions...")
    
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
    print(f" 🧬 K-MEANS ARCHITECTURAL MICRO-SPECIES PROFILING (k={k_values[0]})")
    print("="*80)

    for k in k_values:
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=prof['n_init'], max_iter=prof['max_iter'])
        cluster_labels = kmeans.fit_predict(X_scaled)
        
        cluster_col_name = f'Cluster_k{k}'
        df[cluster_col_name] = cluster_labels
        
        for cluster_id in range(k):
            cluster_data = df[df[cluster_col_name] == cluster_id]
            size = len(cluster_data)
            pct = (size / len(df)) * 100
            
            scaled_centroid = kmeans.cluster_centers_[cluster_id]
            scaled_series = pd.Series(scaled_centroid, index=cluster_features)
            
            # Extract the strongest architectural pulls (+ IQR) and weakest pulls (- IQR)
            top_drivers = scaled_series[scaled_series > 0].sort_values(ascending=False).head(15)
            bottom_drivers = scaled_series[scaled_series < 0].sort_values(ascending=True).head(5)
            
            lang_counts = cluster_data['language'].value_counts()
            top_langs = lang_counts.head(5)
            langs_str = ", ".join([f"{l} ({count/size*100:.1f}%)" for l, count in top_langs.items()])
            if len(lang_counts) > 5:
                other_pct = 100.0 - sum((count/size)*100 for count in top_langs)
                langs_str += f", Other ({other_pct:.1f}%)"

            # ---> NEW: Extract Top Repositories forming this Micro-Species <---
            repo_counts = cluster_data['repo_name'].value_counts()
            top_repos = repo_counts.head(5)
            repos_str = ", ".join([f"{r} ({count/size*100:.1f}%)" for r, count in top_repos.items()])
            if len(repo_counts) > 5:
                other_repo_pct = 100.0 - sum((count/size)*100 for count in top_repos)
                repos_str += f", Other ({other_repo_pct:.1f}%)"

            cluster_points = X_scaled[cluster_labels == cluster_id]
            centroid = kmeans.cluster_centers_[cluster_id]
            distances = np.linalg.norm(cluster_points - centroid, axis=1)
            dispersion = np.mean(distances)

            print(f"\n🧪 FUNCTION CLUSTER {cluster_id} | Size: {size:,} functions ({pct:.1f}%)")
            print(f"   📐 Spatial Dispersion: {dispersion:.2f}")
            print(f"   🧬 Language Make-up: {langs_str}")
            print(f"   🌌 Repo Origins: {repos_str}")
            
            print(f"   🔥 Defining Signatures (Over-represented DNA):")
            for f_name, iqr_score in top_drivers.items():
                clean_name = f_name.replace('log_density_hit_sec_', 'SECURITY: ')\
                                   .replace('log_density_hit_', 'DNA: ')\
                                   .replace('log_density_', 'DNA: ')\
                                   .replace('log_', 'Log ')\
                                   .replace('_', ' ').title()
                print(f"      - {clean_name}: +{iqr_score:.2f} IQR")

            print(f"   🧊 Anti-Signatures (Actively Missing DNA):")
            for f_name, iqr_score in bottom_drivers.items():
                clean_name = f_name.replace('log_density_hit_sec_', 'SECURITY: ')\
                                   .replace('log_density_hit_', 'DNA: ')\
                                   .replace('log_density_', 'DNA: ')\
                                   .replace('log_', 'Log ')\
                                   .replace('_', ' ').title()
                print(f"      - {clean_name}: {iqr_score:.2f} IQR")

    # =========================================================================
    # 4.75 SYSTEM HEALTH DIAGNOSTICS
    # =========================================================================
    print("\n" + "="*80)
    print(" 🩺 CLUSTERING HEALTH DIAGNOSTIC REPORT")
    print("="*80)

    # Check for extreme gravitational pull (IQR > 5 or 10)
    max_iqr_pull = np.max(np.abs(kmeans.cluster_centers_))
    cluster_idx, feature_idx = np.unravel_index(np.argmax(np.abs(kmeans.cluster_centers_)), kmeans.cluster_centers_.shape)
    worst_feature = cluster_features[feature_idx]
    worst_feature_val = kmeans.cluster_centers_[cluster_idx, feature_idx]

    # Check for quarantine micro-clusters (< 0.5% size)
    cluster_sizes_pct = pd.Series(cluster_labels).value_counts(normalize=True) * 100
    smallest_cluster_pct = cluster_sizes_pct.min()

    print(f"   - Maximum Feature Pull: {max_iqr_pull:.2f} IQR (Feature: '{worst_feature}' in Cluster {cluster_idx})")
    print(f"   - Smallest Cluster Size: {smallest_cluster_pct:.2f}% of ecosystem")

    if max_iqr_pull > 10.0 or smallest_cluster_pct < 0.5:
        print("\n   🚨 STATUS: UNHEALTHY (CRITICAL REVISION NEEDED)")
        if max_iqr_pull > 10.0:
            print(f"      * Feature '{worst_feature}' has an extreme tail ({worst_feature_val:+.2f} IQR). It is destroying the distance matrix.")
        if smallest_cluster_pct < 0.5:
            print(f"      * Micro-cluster detected ({smallest_cluster_pct:.2f}%). K-Means is quarantining broken outliers instead of finding true architectural patterns.")
    elif max_iqr_pull > 5.0:
        print("\n   ⚠️ STATUS: WARNING (HEAVY TAILS DETECTED)")
        print(f"      * Feature '{worst_feature}' is pulling very hard ({worst_feature_val:+.2f} IQR). This is acceptable if it defines a rare, known architecture, but monitor closely.")
    else:
        print("\n   ✅ STATUS: HEALTHY")
        print("      * All variables are perfectly balanced. No single metric is artificially dominating the Euclidean distance. Clusters represent true structural architecture.")

    math_end_time = time.time()
    elapsed_minutes = (math_end_time - math_start_time) / 60.0
    
    # =========================================================================
    # 5. EXPORT THE ML INFERENCE BRAIN
    # =========================================================================
    best_k = k_values[0]
    
    # Fully automated generic naming for rapid prototyping
    professional_names = [f"fxn_cluster_{i}" for i in range(best_k)]

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
    cluster_result_cols = [f'Cluster_k{k}' for k in k_values]
    
    export_cols = ['file_id', 'func_name', 'loc', 'complexity'] + cluster_result_cols + cluster_features
    df[export_cols].to_csv(output_csv, index=False)
    
    print(f"✅ Full Matrix exported to: {output_csv}")
    
    return best_k, max_sil, elapsed_minutes

if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    parser = argparse.ArgumentParser(description="Run DNA Clustering on GitGalaxy Database")
    parser.add_argument('--language', type=str, default=None, help="Filter by specific language (e.g., python)")
    parser.add_argument('--clusters', type=int, default=None, help="Force a specific number of clusters")
    parser.add_argument('--accuracy', type=str, choices=['micro', 'low', 'standard', 'medium', 'high'], default='standard', help="Set the rigorousness of the math engine")
    
    args = parser.parse_args()
    
    # ---> THE MLOPS STABILITY OVERRIDE <---
    # If the user forces a specific cluster count, automatically bump the rigor to HIGH
    # to prevent SQL random sampling from shifting the K-Means center of gravity!
    if args.clusters is not None and args.accuracy != 'high':
        print("\n🛡️  FORCED CLUSTER DETECTED: Automatically upgrading to HIGH accuracy for deterministic stability.")
        args.accuracy = 'high'
        
    run_dna_clustering(target_language=args.language, force_k=args.clusters, accuracy=args.accuracy)