import sqlite3
import pandas as pd
import numpy as np
from collections import defaultdict, Counter
from pathlib import Path
import sys
import re

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR / "data" / "gitgalaxy_master.db"

NOISE_MARKERS = [
    'tab_indentations', 'space_indentations', 'indentation_faction',
    'authorship_metadata', 'sec_', 'risk_', 'planned_work', 'tech_debt',
    'commented_out', 'ad_hoc_print', 'structured_documentation',
    'non_standard_unicode_homoglyphs'
]

ARCH_NAMES = {
    "0": "Native Core & Memory Management",
    "1": "Object-Oriented Services & Typed Abstractions",
    "2": "Declarative Definitions & Data Models",
    "3": "C-Headers & Preprocessor Macros",
    "4": "High-Complexity Closures & Orchestration",
    "5": "Universal Dependencies (The God Nodes)",
    "6": "UI Frameworks & View Layers",
    "7": "Async Logic & Concurrency Orchestration",
    "8": "Test Suites & Mock Environments",
    "9": "I/O Boundaries & Scripting Automation"
}

def clean_archetype_name(raw_arch):
    """Forces all historical DB names to map to the current true ARCH_NAMES."""
    if pd.isna(raw_arch) or raw_arch is None:
        return "Unassigned / Ambiguous"
        
    raw_str = str(raw_arch).strip()
    match = re.search(r'(?:Cluster\s*)?(\d+)', raw_str, re.IGNORECASE)
    
    if match and match.group(1) in ARCH_NAMES:
        return f"Cluster {match.group(1)}: {ARCH_NAMES[match.group(1)]}"
            
    return "Unassigned / Ambiguous"

def run_inverse_analysis():
    if not DB_PATH.exists():
        print(f"❌ Error: Database not found at {DB_PATH}")
        sys.exit(1)
        
    print(f"📡 Connecting to Galactic Census at: {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(galactic_census)")
    all_cols = [row[1] for row in cursor.fetchall()]

    intent_cols = [
        c for c in all_cols 
        if c.startswith('hit_') and not any(noise in c.lower() for noise in NOISE_MARKERS)
    ]
    
    print(f"🧬 Isolated {len(intent_cols)} pure logic DNA dimensions.")
    print("📥 Loading files. Please wait...\n")

    query = f"SELECT archetype, {', '.join(intent_cols)} FROM galactic_census WHERE coding_loc > 0"
    df = pd.read_sql_query(query, conn)
    conn.close()

    # Clean the archetype names in the dataframe using the regex function
    df['clean_archetype'] = df['archetype'].apply(clean_archetype_name)

    # Vectorize the hits for speed
    X_vectors = df[intent_cols].fillna(0).values.astype(np.float32)
    X_active = X_vectors > 0
    clean_traits = np.array([c.replace('hit_', '') for c in intent_cols])
    
    # Dictionary structure: { ML_Archetype: [list of signature strings] }
    cluster_compositions = defaultdict(list)

    print("⏳ Mapping ML Archetypes to Stoichiometric Baselines...\n")

    for i, is_active in enumerate(X_active):
        if not is_active.any():
            continue
            
        active_traits = clean_traits[is_active]
        sig_key = " | ".join(sorted(active_traits))
        cluster_compositions[df['clean_archetype'].iloc[i]].append(sig_key)

    print("="*80)
    print(" 🪐 STOICHIOMETRIC COMPOSITION OF ML ARCHETYPES")
    print("="*80)

    # Sort archetypes by cluster number
    sorted_clusters = sorted(cluster_compositions.keys())

    for arch_name in sorted_clusters:
        sig_list = cluster_compositions[arch_name]
        total_files_in_arch = len(sig_list)
        
        # Count the unique ratios in this ML cluster
        ratio_counts = Counter(sig_list)
        unique_ratios = len(ratio_counts)
        
        print(f"\n[{total_files_in_arch:>7,} Files] 🤖 {arch_name}")
        print(f"   ↳ Contains {unique_ratios:,} unique stoichiometric ratio groups.")
        print(f"   🧬 Top 4 DNA Signatures by Volume:")
        
        # Show the top 4 stoichiometric combinations inside this archetype
        for sig, count in ratio_counts.most_common(4):
            pct = (count / total_files_in_arch) * 100
            traits = sig.split(" | ")
            traits_str = ", ".join(traits[:5]) + ("..." if len(traits) > 5 else "")
            
            print(f"      - {pct:>5.1f}% ({count:>6,} files) | DNA: {traits_str}")
            
    print("-" * 80)

if __name__ == "__main__":
    run_inverse_analysis()