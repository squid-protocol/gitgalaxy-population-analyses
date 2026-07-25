import sqlite3
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from pathlib import Path
import warnings

warnings.filterwarnings('ignore')

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR / "data" / "gitgalaxy_master.db"
K_MACRO_SPECIES = 11
MIN_FILES = 30

def build_repo_fingerprint_table():
    if not DB_PATH.exists():
        print(f"❌ Error: Database not found at {DB_PATH}")
        return

    print("📡 Connecting to Database to pull Constellation telemetry...")
    conn = sqlite3.connect(DB_PATH)
    
    query = """
        SELECT constellation, archetype 
        FROM galactic_census 
        WHERE archetype IS NOT NULL 
        AND archetype LIKE 'Cluster %'
    """
    df = pd.read_sql_query(query, conn)

    print("🧮 Calculating Archetype ratios...")
    repo_matrix = pd.crosstab(df['constellation'], df['archetype'])
    
    # Filter out micro-repos
    file_counts = repo_matrix.sum(axis=1)
    valid_repos = file_counts[file_counts >= MIN_FILES].index
    repo_matrix = repo_matrix.loc[valid_repos]
    
    # Convert to ratios
    arch_cols = repo_matrix.columns
    repo_ratios = repo_matrix.div(repo_matrix.sum(axis=1), axis=0)

    print(f"🧠 Running K-Means (k={K_MACRO_SPECIES}) to establish Macro-Species...")
    kmeans = KMeans(n_clusters=K_MACRO_SPECIES, random_state=42, n_init='auto')
    
    # .transform() gives us the distance from every repo to EVERY centroid
    # This is the "Z-Score Fingerprint" you want for XGBoost
    distance_matrix = kmeans.fit_transform(repo_ratios)
    labels = kmeans.labels_

    print("🧬 Compiling the Fingerprint Matrix...")
    fingerprint_df = pd.DataFrame(index=repo_ratios.index)
    fingerprint_df['assigned_macro_species'] = labels
    
    # Add the distance to all 11 clusters
    for i in range(K_MACRO_SPECIES):
        fingerprint_df[f'dist_to_{i}'] = distance_matrix[:, i]

    # Calculate the Z-Score specifically for its ASSIGNED cluster
    # We grab the distance to its assigned cluster, then normalize it against peers
    assigned_distances = np.choose(labels, distance_matrix.T)
    fingerprint_df['primary_drift'] = assigned_distances
    
    fingerprint_df['primary_z_score'] = fingerprint_df.groupby('assigned_macro_species')['primary_drift'].transform(
        lambda x: (x - x.mean()) / x.std()
    ).fillna(0.0)

    # Drop the raw drift, keep the z-score
    fingerprint_df = fingerprint_df.drop(columns=['primary_drift'])

    # Write the table to the database
    print("💾 Writing `repo_macro_fingerprints` table to SQLite...")
    fingerprint_df.to_sql('repo_macro_fingerprints', conn, if_exists='replace', index_label='constellation')
    
    # Build an index for fast joining later
    cursor = conn.cursor()
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_fingerprint_constellation ON repo_macro_fingerprints(constellation);")
    conn.commit()
    conn.close()

    print(f"✅ Successfully integrated {len(fingerprint_df):,} repo fingerprints into the database!")

if __name__ == "__main__":
    build_repo_fingerprint_table()