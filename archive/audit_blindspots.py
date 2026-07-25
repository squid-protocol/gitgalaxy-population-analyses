import sqlite3
import pandas as pd
from pathlib import Path

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR / "gitgalaxy_master.db"
OUTPUT_CSV = SCRIPT_DIR / "missed_threats_audit.csv"

THREAT_LABELS = {
    1: "Botnet / DDoS",
    2: "Stealer / Trojan",
    3: "Dropper / Webshell",
    4: "Native Infector"
}

def extract_false_negatives():
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        return

    print("📡 Connecting to Database...")
    conn = sqlite3.connect(DB_PATH)

    # Hunt 4: Pull the False Negatives (Actual Malware that the AI missed)
    query = """
        SELECT 
            f.id AS file_id,
            f.raw_danger,
            f.threat_class AS actual_class,
            p.ai_confidence AS confidence_in_safe,
            f.file_path,
            f.constellation,
            f.language,
            f.archetype,
            r.assigned_macro_species AS repo_macro_species
        FROM 
            ai_predictions p
        JOIN 
            galactic_census f ON p.file_id = f.id
        LEFT JOIN 
            repo_macro_fingerprints r ON f.constellation = r.constellation
        WHERE 
            f.threat_class > 0     -- It IS actually malware
            AND p.threat_class = 0 -- But the AI predicted it was SAFE
        ORDER BY 
            f.raw_danger DESC, p.ai_confidence DESC
    """
    
    print("🔍 Extracting the Ghosts (False Negatives Sorted by Physical Danger Score)...")
    try:
        ghosts_df = pd.read_sql_query(query, conn)
    except sqlite3.OperationalError as e:
        print(f"❌ SQL Error: {e}")
        conn.close()
        return

    conn.close()

    if ghosts_df.empty:
        print("✅ No missed threats found! The AI caught everything.")
        return

    # Export to CSV for deep manual review
    print(f"💾 Saving {len(ghosts_df):,} missed threats to {OUTPUT_CSV.name}...")
    ghosts_df.to_csv(OUTPUT_CSV, index=False)

    # Print a full readout of the top 50 most physically dangerous misses
    print("\n" + "="*115)
    print(" 👻 THE GHOSTS: TOP 50 MISSED THREATS (FALSE NEGATIVES)")
    print("="*115)
    for _, row in ghosts_df.head(50).iterrows():
        conf = row['confidence_in_safe']
        actual_class = int(row['actual_class'])
        class_name = THREAT_LABELS.get(actual_class, "Unknown")
        
        # The AI thought it was safe. We print how confident it was in that wrong assumption.
        print(f"[Danger: {row['raw_danger']:>3.0f} | AI was {conf:>5.2f}% sure it was SAFE] Actual: {class_name:<18} | {row['file_path']}")
        print(f"    Repo: {row['constellation']} | Macro: {row['repo_macro_species']} | Lang: {row['language']}\n")

    print(f"✅ Audit complete! Open {OUTPUT_CSV.name} to view the full list of evasive malware.")

if __name__ == "__main__":
    extract_false_negatives()