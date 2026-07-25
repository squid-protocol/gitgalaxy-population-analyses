import sqlite3
import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from pathlib import Path
import sys
import random
import concurrent.futures
import os

try:
    from tqdm import tqdm
except ImportError:
    print("❌ Error: tqdm is required. Run: pip install tqdm")
    sys.exit(1)

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR / "data" / "gitgalaxy_master.db"

def load_data():
    if not DB_PATH.exists():
        print(f"❌ Error: Master Database not found at {DB_PATH}")
        sys.exit(1)
        
    print(f"📡 Connecting to Galactic Census at: {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    
    print("📥 Loading 1.25 Million files into memory. Please wait...")
    # Load executable logic files
    df = pd.read_sql_query("SELECT * FROM galactic_census WHERE coding_loc > 0", conn)
    conn.close()
    
    # --- ISOLATE THE 16-DIMENSIONAL ARCHETYPE FINGERPRINT ---
    arch_cols = [c for c in df.columns if c.startswith('arch_')]
    
    if not arch_cols:
        print("❌ Error: No 'arch_' columns found in the database. Ensure build_master_db.py extracted them.")
        sys.exit(1)
    
    print("⚡ Loading the 16-Dimensional Archetype Fingerprints into the physics engine...")
    # Extract the distances to the 16 cluster centroids
    X_fingerprints = df[arch_cols].fillna(0).values.astype(np.float32)
    
    print(f"✅ Loaded {len(df):,} files.")
    print(f"🌌 Matching based purely on gravitational pull to the {len(arch_cols)} ML Archetypes.\n")
    
    return df, arch_cols, X_fingerprints

def find_archetype_twins(df, X_fingerprints, target_idx, top_n=3):
    """Hyperspeed cosine similarity matching on the 16-D Archetype Fingerprint."""
    target_vector = X_fingerprints[target_idx].reshape(1, -1)
    
    if np.sum(target_vector) == 0:
        return pd.DataFrame()
        
    # Cosine similarity on distance vectors finds files with the exact same *balance* of traits
    similarities = cosine_similarity(target_vector, X_fingerprints)[0]
    
    k = top_n + 1
    top_k_indices = np.argpartition(similarities, -k)[-k:]
    top_k_indices = top_k_indices[np.argsort(similarities[top_k_indices])[::-1]]
    
    results = []
    target_id = df['id'].iloc[target_idx]
    
    for idx in top_k_indices:
        if df['id'].iloc[idx] == target_id:
            continue
            
        row = df.iloc[idx]
        results.append({
            'id': row['id'],
            'repo_name': row['repo_name'],
            'file_path': row['file_path'],
            'language': row['language'],
            'total_loc': row['total_loc'],
            'structural_mass': row['structural_mass'],
            'archetype': row['archetype'],
            'score': similarities[idx]
        })
        if len(results) == top_n:
            break
            
    return pd.DataFrame(results)

def audit_single_file(idx, ids, repos, langs, primary_archetypes, X_fingerprints):
    """Worker function for the ThreadPool utilizing fast NumPy array lookups."""
    target_id = ids[idx]
    target_arch = primary_archetypes[idx]
    target_vector = X_fingerprints[idx].reshape(1, -1)
    
    if np.sum(target_vector) == 0:
        return None
        
    similarities = cosine_similarity(target_vector, X_fingerprints)[0]
    
    top_2_indices = np.argpartition(similarities, -2)[-2:]
    top_2_indices = top_2_indices[np.argsort(similarities[top_2_indices])[::-1]]
    
    best_idx = top_2_indices[0]
    if ids[best_idx] == target_id:
        best_idx = top_2_indices[1]
        
    return {
        'target_repo': repos[idx],
        'target_lang': langs[idx],
        'target_arch': target_arch,
        'best_repo': repos[best_idx],
        'best_lang': langs[best_idx],
        'best_arch': primary_archetypes[best_idx],
        'best_score': similarities[best_idx]
    }

def print_target_and_twins(df, X_fingerprints, target_idx, title):
    """Helper to print a target file and its archetype twins."""
    target = df.iloc[target_idx]
    print(f"\n[{title}] -----------------------------------------------------------------")
    print(f"   File: {target['file_path']} ({target['language']})")
    print(f"   Repo: {target['repo_name']} | LOC: {target['total_loc']} | Mass: {target['structural_mass']}")
    print(f"   Primary Archetype: {target['archetype']}")
    print("-" * 80)
    
    arch_twins = find_archetype_twins(df, X_fingerprints, target_idx, top_n=4)
    
    print("   🧠 ARCHITECTURAL SOULMATES (Matched via 16-D Euclidean Distance Fingerprint):")
    for rank, (_, twin) in enumerate(arch_twins.iterrows(), 1):
        match_type = "Identical Gravity" if twin['score'] >= 0.999 else "Heavy Overlap" if twin['score'] >= 0.98 else "Similar Pull" if twin['score'] >= 0.90 else "Distant"
        print(f"      {rank}. [{twin['score']*100:>6.3f}% | {match_type}] {twin['repo_name']} : {twin['file_path']} ({twin['language']} | {twin['total_loc']} LOC)")
        print(f"           ↳ {twin['archetype']}")

def run_discovery():
    df, arch_cols, X_fingerprints = load_data()
    
    # =========================================================================
    # PART 1: THE "GOD NODE" SAMPLES
    # =========================================================================
    print("="*80)
    print(" 🎯 THE 'GOD NODE' DISCOVERY (MATCHING BEHAVIORAL ARCHETYPES)")
    print("="*80)
    
    heaviest_files = df.sort_values(by='structural_mass', ascending=False).head(500)
    
    hero_indices = []
    seen_repos = set()
    
    for original_idx, row in heaviest_files.iterrows():
        if row['repo_name'] not in seen_repos and row['total_loc'] > 100:
            positional_idx = df.index.get_loc(original_idx)
            hero_indices.append(positional_idx)
            seen_repos.add(row['repo_name'])
        if len(hero_indices) == 3:
            break
            
    for i, idx in enumerate(hero_indices, 1):
        print_target_and_twins(df, X_fingerprints, idx, f"TARGET {i}")

    # =========================================================================
    # PART 1.5: THE MAINFRAME DISCOVERY (COBOL SPECIFIC)
    # =========================================================================
    cobol_files = df[(df['language'].str.lower() == 'cobol') & (df['total_loc'] > 100)].sort_values(by='structural_mass', ascending=False)
    
    if not cobol_files.empty:
        print("\n" + "="*80)
        print(" 🦖 THE MAINFRAME DISCOVERY (HUNTING COBOL ARCHETYPES)")
        print("="*80)
        cobol_target_idx = df.index.get_loc(cobol_files.index[0])
        print_target_and_twins(df, X_fingerprints, cobol_target_idx, "COBOL TARGET")

    # =========================================================================
    # PART 2: ARCHETYPE EVOLUTION AUDIT (12-Core Multi-Threading)
    # =========================================================================
    sample_size = 2000 
    sample_indices = random.sample(range(len(df)), sample_size)
    
    print("\n" + "="*80)
    print(f" 🌍 ARCHETYPE EVOLUTION AUDIT ({sample_size:,} random files)")
    print("="*80)
    
    cores = os.cpu_count() or 4
    print(f"🚀 Engaging {cores}-Core ThreadPoolExecutor for 16-D Fingerprint matching...")
    
    ids_array = df['id'].values
    repos_array = df['repo_name'].values
    langs_array = df['language'].values
    archs_array = df['archetype'].values
    
    stats = {
        "identical": 0, # >= 99.9%
        "heavy": 0,     # 98% - 99.8%
        "similar": 0,   # 90% - 97.9%
        "distant": 0,   # < 90%
    }
    
    cross_repo_count = 0
    cross_lang_count = 0
    matched_primary_arch_count = 0
    total_evolved = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=cores) as executor:
        futures = [executor.submit(audit_single_file, idx, ids_array, repos_array, langs_array, archs_array, X_fingerprints) for idx in sample_indices]
        
        for future in tqdm(concurrent.futures.as_completed(futures), total=sample_size, desc="Matching Archetypes", unit="file"):
            res = future.result()
            if not res: continue
                
            score = res['best_score']
            
            if score >= 0.999: stats["identical"] += 1
            elif score >= 0.98: stats["heavy"] += 1
            elif score >= 0.90: stats["similar"] += 1
            else: stats["distant"] += 1
            
            if score >= 0.90:
                total_evolved += 1
                if res['target_repo'] != res['best_repo']: cross_repo_count += 1
                if res['target_lang'] != res['best_lang']: cross_lang_count += 1
                if res['target_arch'] == res['best_arch']: matched_primary_arch_count += 1

    p_identical = (stats["identical"] / sample_size) * 100
    p_heavy = (stats["heavy"] / sample_size) * 100
    p_similar = (stats["similar"] / sample_size) * 100
    p_distant = (stats["distant"] / sample_size) * 100
    
    p_cross_repo = (cross_repo_count / max(total_evolved, 1)) * 100
    p_cross_lang = (cross_lang_count / max(total_evolved, 1)) * 100
    p_arch_match = (matched_primary_arch_count / max(total_evolved, 1)) * 100

    print("\n" + "-"*80)
    print(" 📊 ARCHETYPE POPULATION STATISTICS (Fingerprint Similarity Thresholds)")
    print("-" * 80)
    print(f"   • Identical Gravity (>= 99.9%) : {stats['identical']:>5,} files ({p_identical:>5.1f}%) -> Exact same pull to all 16 clusters.")
    print(f"   • Heavy Overlap     (98-99.8%) : {stats['heavy']:>5,} files ({p_heavy:>5.1f}%) -> Near-identical behavioral footprint.")
    print(f"   • Similar Pull      (90-97.9%) : {stats['similar']:>5,} files ({p_similar:>5.1f}%) -> Shared domain, slight variance in secondary traits.")
    print(f"   • Distant           (< 90%)    : {stats['distant']:>5,} files ({p_distant:>5.1f}%) -> Highly unique cluster distances.")
    
    print("\n 🌌 ARCHITECTURAL VALIDATION (For files with >= 90% Fingerprint similarity)")
    print("-" * 80)
    print(f"   • How often did a Fingerprint match result in the EXACT SAME Primary Archetype string? : {p_arch_match:.1f}%")
    print(f"   • Matches crossing Repository boundaries : {p_cross_repo:.1f}%")
    print(f"   • Matches crossing Language boundaries   : {p_cross_lang:.1f}%")
    print("\n" + "="*80)

if __name__ == "__main__":
    run_discovery()