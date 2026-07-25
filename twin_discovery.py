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
    df = pd.read_sql_query("SELECT * FROM galactic_census WHERE coding_loc > 0", conn)
    conn.close()
    
    # --- 1. FILTER THE PURE DNA COLUMNS ---
    raw_hit_cols = [c for c in df.columns if c.startswith('hit_') and not c.endswith('_x1000')]
    exclusion_list = {
        'hit_structural_tab_indentations', 
        'hit_structural_space_indentations', 
        'hit_indentation_faction'
    }
    hit_cols = [c for c in raw_hit_cols if c not in exclusion_list]
    arch_cols = [c for c in df.columns if c.startswith('arch_')]
    
    print("⚡ Compressing vector matrix for high-speed C-backed compute...")
    all_vectors = df[hit_cols].fillna(0).values.astype(np.float32)
    
    print(f"✅ Loaded {len(df):,} files.")
    print(f"🧬 Active Dimensions: {len(hit_cols)} Pure DNA vectors | {len(arch_cols)} Archetype vectors.\n")
    
    return df, hit_cols, arch_cols, all_vectors

def find_twins(df, all_vectors, target_idx, top_n=3):
    """Hyperspeed cosine similarity using argpartition."""
    target_vector = all_vectors[target_idx].reshape(1, -1)
    
    if np.sum(target_vector) == 0:
        return pd.DataFrame()
        
    similarities = cosine_similarity(target_vector, all_vectors)[0]
    
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
            'file_impact': row['structural_mass'],
            'archetype': row['archetype'],
            'score': similarities[idx]
        })
        if len(results) == top_n:
            break
            
    return pd.DataFrame(results)

def audit_single_file(idx, ids, repos, langs, all_vectors):
    """Worker function for the ThreadPool utilizing fast NumPy array lookups."""
    target_id = ids[idx]
    target_vector = all_vectors[idx].reshape(1, -1)
    
    if np.sum(target_vector) == 0:
        return None
        
    similarities = cosine_similarity(target_vector, all_vectors)[0]
    
    top_2_indices = np.argpartition(similarities, -2)[-2:]
    top_2_indices = top_2_indices[np.argsort(similarities[top_2_indices])[::-1]]
    
    best_idx = top_2_indices[0]
    if ids[best_idx] == target_id:
        best_idx = top_2_indices[1]
        
    return {
        'target_repo': repos[idx],
        'target_lang': langs[idx],
        'best_repo': repos[best_idx],
        'best_lang': langs[best_idx],
        'best_score': similarities[best_idx]
    }

def print_target_and_twins(df, all_vectors, target_idx, title):
    """Helper to print a target file and its structural twins."""
    target = df.iloc[target_idx]
    print(f"\n[{title}] -----------------------------------------------------------------")
    print(f"   File: {target['file_path']} ({target['language']})")
    print(f"   Repo: {target['repo_name']} | LOC: {target['total_loc']} | Mass: {target['structural_mass']}")
    print(f"   Archetype: {target['archetype']}")
    print("-" * 80)
    
    dna_twins = find_twins(df, all_vectors, target_idx, top_n=4)
    
    print("   🧬 STRUCTURAL EVOLUTION MATCHES:")
    for rank, (_, twin) in enumerate(dna_twins.iterrows(), 1):
        match_type = "Exact Clone" if twin['score'] >= 0.99 else "Close Relative" if twin['score'] >= 0.95 else "Convergent Design" if twin['score'] >= 0.85 else "Distant"
        print(f"      {rank}. [{twin['score']*100:>6.2f}% | {match_type}] {twin['repo_name']} : {twin['file_path']} ({twin['language']} | {twin['total_loc']} LOC)")


def run_discovery():
    df, hit_cols, arch_cols, all_vectors = load_data()
    
    # =========================================================================
    # PART 1: THE "GOD NODE" SAMPLES
    # Pick the 3 heaviest files from 3 DIFFERENT repositories to find twins for
    # =========================================================================
    print("="*80)
    print(" 🎯 THE 'GOD NODE' DISCOVERY (MATCHING THE HEAVIEST FILES IN THE GALAXY)")
    print("="*80)
    
    # Sort by structural_mass to get the most complex files
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
        print_target_and_twins(df, all_vectors, idx, f"TARGET {i}")

    # =========================================================================
    # PART 1.5: THE MAINFRAME DISCOVERY (COBOL SPECIFIC)
    # =========================================================================
    cobol_files = df[(df['language'].str.lower() == 'cobol') & (df['total_loc'] > 100)].sort_values(by='structural_mass', ascending=False)
    
    if not cobol_files.empty:
        print("\n" + "="*80)
        print(" 🦖 THE MAINFRAME DISCOVERY (HUNTING COBOL TWINS)")
        print("="*80)
        cobol_target_idx = df.index.get_loc(cobol_files.index[0])
        print_target_and_twins(df, all_vectors, cobol_target_idx, "COBOL TARGET")

    # =========================================================================
    # PART 2: CONVERGENT EVOLUTION AUDIT (12-Core Multi-Threading)
    # =========================================================================
    sample_size = 2000 
    sample_indices = random.sample(range(len(df)), sample_size)
    
    print("\n" + "="*80)
    print(f" 🌍 CONVERGENT EVOLUTION AUDIT ({sample_size:,} random files)")
    print("="*80)
    
    cores = os.cpu_count() or 4
    print(f"🚀 Engaging {cores}-Core ThreadPoolExecutor for hyperspeed vector math...")
    
    # Pre-extract numpy arrays to avoid pandas GIL locking inside the threads
    ids_array = df['id'].values
    repos_array = df['repo_name'].values
    langs_array = df['language'].values
    
    # Bins for the report
    stats = {
        "clones": 0,    # >= 99%
        "siblings": 0,  # 95% - 98.9%
        "cousins": 0,   # 85% - 94.9%
        "bespoke": 0,   # < 85%
    }
    
    cross_repo_count = 0
    cross_lang_count = 0
    total_evolved = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=cores) as executor:
        futures = [executor.submit(audit_single_file, idx, ids_array, repos_array, langs_array, all_vectors) for idx in sample_indices]
        
        for future in tqdm(concurrent.futures.as_completed(futures), total=sample_size, desc="Sequencing DNA", unit="file"):
            res = future.result()
            if not res: continue
                
            score = res['best_score']
            
            if score >= 0.99: stats["clones"] += 1
            elif score >= 0.95: stats["siblings"] += 1
            elif score >= 0.85: stats["cousins"] += 1
            else: stats["bespoke"] += 1
            
            if score >= 0.85:
                total_evolved += 1
                if res['target_repo'] != res['best_repo']: cross_repo_count += 1
                if res['target_lang'] != res['best_lang']: cross_lang_count += 1

    # Format the percentages
    p_clones = (stats["clones"] / sample_size) * 100
    p_sibs = (stats["siblings"] / sample_size) * 100
    p_cousins = (stats["cousins"] / sample_size) * 100
    p_bespoke = (stats["bespoke"] / sample_size) * 100
    
    p_cross_repo = (cross_repo_count / max(total_evolved, 1)) * 100
    p_cross_lang = (cross_lang_count / max(total_evolved, 1)) * 100

    print("\n" + "-"*80)
    print(" 📊 GLOBAL ARCHITECTURAL REUSE STATISTICS")
    print("    (How much of our software is truly unique vs. repeated patterns?)")
    print("-" * 80)
    print(f"   • Exact Clones      (>= 99% Match) : {stats['clones']:>5,} files ({p_clones:>5.1f}%) -> Identical blueprints; mostly boilerplate or copy-paste.")
    print(f"   • Close Relatives   (95% - 98.9%)  : {stats['siblings']:>5,} files ({p_sibs:>5.1f}%) -> Minor developer tweaks, but the same underlying engine.")
    print(f"   • Convergent Design (85% - 94.9%)  : {stats['cousins']:>5,} files ({p_cousins:>5.1f}%) -> Different devs solving the same problem the exact same way.")
    print(f"   • Highly Unique     (< 85% Match)  : {stats['bespoke']:>5,} files ({p_bespoke:>5.1f}%) -> Custom, bespoke logic with no standard equivalent.")
    
    print("\n 🌌 ARCHITECTURAL KNOWLEDGE TRANSFER (Cross-Pollination)")
    print("    (For files sharing >= 85% architectural DNA)")
    print("-" * 80)
    print(f"   • Patterns reused across completely different repositories    : {p_cross_repo:.1f}%")
    print(f"   • Patterns translating across different programming languages : {p_cross_lang:.1f}%")
    print("\n" + "="*80)

if __name__ == "__main__":
    run_discovery()