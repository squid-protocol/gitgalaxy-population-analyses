import sqlite3
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from pathlib import Path
import warnings
import json
import time
import argparse

warnings.filterwarnings('ignore')

SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR.parent / "data" / "gitgalaxy_master.db"

def cluster_repositories(min_files=30, force_k=None, accuracy='standard'):
    start_time = time.time()
    if not DB_PATH.exists():
        print(f"❌ Error: Database not found at {DB_PATH}")
        return None, 0.0, 0.0

    # MLOps Rigor Profiles
    profiles = {
        'micro':    {'n_init': 2,  'max_iter': 150},
        'low':      {'n_init': 3,  'max_iter': 300},
        'standard': {'n_init': 8,  'max_iter': 450},
        'medium':   {'n_init': 15, 'max_iter': 600},
        'high':     {'n_init': 30, 'max_iter': 1500}
    }
    prof = profiles.get(accuracy, profiles['standard'])

    print("\n" + "="*80)
    print(" 🎛️  MLOPS RIGOR PROFILES (Compute vs. Confidence)")
    print("="*80)
    for p_name, p_data in profiles.items():
        print(f"   [{p_name.upper():<8}] | n_init: {p_data['n_init']:>2} | max_iter: {p_data['max_iter']:>4}")
    print("-" * 80)
    print(f"⚙️  ACTIVE SETTING: You are running the [{accuracy.upper()}] profile.\n")

    print("="*80)
    print(f" 🌍 INITIATING REPOSITORY-LEVEL META-CLUSTERING [{accuracy.upper()}]")
    print("="*80)

    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT 
            repo_name,
            file_archetype,
            COUNT(id) as file_count
        FROM file_data
        WHERE file_archetype IS NOT NULL
        GROUP BY repo_name, file_archetype
    """
    df_raw = pd.read_sql_query(query, conn)
    conn.close()

    if df_raw.empty:
        print("❌ Error: No file_archetype data found.")
        return None, 0.0, 0.0

    # Pivot into Stoichiometry Ratios using the actual file counts from SQL!
    repo_matrix = df_raw.pivot(index='repo_name', columns='file_archetype', values='file_count').fillna(0.0)
    
    # Ensure the matrix is explicitly float64 before math operations
    repo_matrix = repo_matrix.astype(float)
    
    file_counts = repo_matrix.sum(axis=1)
    valid_repos = file_counts[file_counts >= min_files].index
    repo_matrix = repo_matrix.loc[valid_repos]
    
    print(f"✂️ Filtered out micro-repos (<{min_files} files). Remaining Repositories: {len(repo_matrix):,}")

    repo_ratios = repo_matrix.div(repo_matrix.sum(axis=1), axis=0)
    
    # Fill any NaNs that occurred during division
    repo_ratios = repo_ratios.fillna(0.0)
    
    file_composition_strings = repo_ratios.apply(lambda row: ','.join(f"{v:.4f}" for v in row), axis=1)

    best_sil_score = -1.0
    best_k = 6

    if force_k is not None:
        print(f"🚀 OVERRIDE: Forcing {force_k} clusters...")
        best_k = force_k
        kmeans_test = KMeans(n_clusters=best_k, random_state=42, n_init=prof['n_init'], max_iter=prof['max_iter'])
        labels = kmeans_test.fit_predict(repo_ratios)
        best_sil_score = silhouette_score(repo_ratios, labels)
    else:
        print(f"{'k-Clusters':<12} | {'WCSS (Elbow / Lower is Better)':<35} | {'Silhouette Score'}")
        print("-" * 80)
        results = []
        for test_k in range(4, 15):
            kmeans_test = KMeans(n_clusters=test_k, random_state=42, n_init=prof['n_init'], max_iter=prof['max_iter'])
            labels = kmeans_test.fit_predict(repo_ratios)
            wcss = kmeans_test.inertia_
            sil_score = silhouette_score(repo_ratios, labels)
            results.append((test_k, wcss, sil_score))
            
        sorted_results = sorted(results, key=lambda x: x[0])
        
        # THE FIX: Find the absolute peak silhouette score and its associated K
        best_tuple = max(sorted_results, key=lambda x: x[2])
        best_k = best_tuple[0]
        best_sil_score = best_tuple[2]

        for test_k, wcss, sil_score in sorted_results:
            markers = []
            if test_k == best_k: markers.append("⭐ TRUE PEAK (Winner)")
            print(f" k={test_k:<9} | {wcss:,.4f} {' ' * (30 - len(f'{wcss:,.4f}'))} | {sil_score:.4f} {' + '.join(markers)}")

    print(f"\n🧠 Running Final K-Means to find {best_k} Repo Macro-Species...\n")
    kmeans = KMeans(n_clusters=best_k, random_state=42, n_init=prof['n_init'], max_iter=prof['max_iter'])
    cluster_labels = kmeans.fit_predict(repo_ratios)
    full_distances = kmeans.transform(repo_ratios)
    
    print("="*80)
    print(f" 🪐 REPOSITORY META-ARCHITECTURES (K={best_k})")
    print("="*80)
    
    for cluster_id in range(best_k):
        # Find the repos belonging to this cluster
        in_cluster = (cluster_labels == cluster_id)
        cluster_repos = repo_ratios[in_cluster]
        size = len(cluster_repos)
        if size == 0: continue
        
        print(f"\n🌍 REPO CLUSTER {cluster_id} | Size: {size} Repositories ({(size/len(repo_ratios))*100:.1f}%)")
        
        # Calculate the average file composition of this repo cluster
        centroid = cluster_repos.mean()
        top_archetypes = centroid.sort_values(ascending=False).head(4)
        
        print("   🧬 Dominant File Archetypes (Average Repo Makeup):")
        for arch_id, pct in top_archetypes.items():
            if pct > 0.02: # Only show if it makes up >2% of the repo
                print(f"      - {arch_id:<18}: {pct*100:>5.1f}%")
                
        # List a few examples of repos in this cluster
        sample_repos = cluster_repos.index.tolist()[:8]
        print(f"   📂 Examples: {', '.join(sample_repos)}")
    print("\n" + "="*80)

    # =========================================================================
    # EXPORT CSV FOR MASTER DB UPDATER
    # =========================================================================
    export_df = pd.DataFrame()
    export_df['repo_name'] = repo_ratios.index
    export_df['repo_archetype'] = cluster_labels
    export_df['repo_fingerprint'] = [','.join(f"{d:.4f}" for d in row) for row in full_distances]
    export_df['file_composition'] = file_composition_strings.values
    
    csv_out = SCRIPT_DIR / "kmeans_repo_meta_species.csv"
    export_df.to_csv(csv_out, index=False)

    # =========================================================================
    # EXPORT ML INFERENCE BRAIN
    # =========================================================================
    import re
    
    brain_out = SCRIPT_DIR / "ml_inference_brain_repos.txt"
    brain_dict = {
        "k_clusters": best_k,
        "features": list(repo_ratios.columns), 
        # Round centroids to 5 decimal places for clean precision
        "centroids": {f"Cluster {i}": [round(v, 5) for v in center.tolist()] for i, center in enumerate(kmeans.cluster_centers_)},
        "z_score_params": {}
    }
    
    for cluster_id in range(best_k):
        cluster_distances = full_distances[cluster_labels == cluster_id, cluster_id]
        # Round Z-Score parameters to 5 decimal places
        mean_dist = round(float(np.mean(cluster_distances)), 5) if len(cluster_distances) > 0 else 0.0
        std_dist = round(float(np.std(cluster_distances)), 5) if len(cluster_distances) > 0 else 1.0
        std_dist = max(std_dist, 0.001)
        brain_dict["z_score_params"][f"Cluster {cluster_id}"] = {"mean": mean_dist, "std": std_dist}

    # Dump to JSON, then collapse the expanded numeric arrays onto a single line
    json_str = json.dumps(brain_dict, indent=4)
    json_str = re.sub(r'\[\n\s+([0-9.\-,\s]+)\n\s+\]', lambda m: '[' + re.sub(r'\s+', ' ', m.group(1)).strip() + ']', json_str)

    with open(brain_out, 'w', encoding='utf-8') as f:
        # Match the exact variable name required by the updated v6 pipeline
        f.write("GENERAL_REPO_INFERENCE_MODEL = " + json_str + "\n")
        
    print(f"✅ Repo Brain exported to: {brain_out.name}")
    print(f"✅ Full Matrix exported to: {csv_out.name}")
    print("✅ Run 'python master_db_updater.py --update apply_repo_clusters' to inject!")
    
    elapsed_minutes = (time.time() - start_time) / 60.0
    return best_k, best_sil_score, elapsed_minutes

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--clusters', type=int, default=None, help="Force specific clusters")
    parser.add_argument('--accuracy', type=str, choices=['micro', 'low', 'standard', 'medium', 'high'], default='standard')
    args = parser.parse_args()
    cluster_repositories(force_k=args.clusters, accuracy=args.accuracy)