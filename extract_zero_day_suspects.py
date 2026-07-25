import sqlite3
import pandas as pd
from pathlib import Path

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR / "data" / "gitgalaxy_master.db"
OUTPUT_CSV = SCRIPT_DIR / "analysis_outputs" / "danger_zone_audit.csv"

THREAT_LABELS = {
    1: "Botnet / DDoS",
    2: "Stealer / Trojan",
    3: "Dropper / Webshell",
    4: "Native Infector"
}

def extract_suspects():
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        return

    print("📡 Connecting to Database...")
    conn = sqlite3.connect(DB_PATH)

    # Hunt 3: Pull the AI threats, but sort them by actual PHYSICAL DANGER
    query = """
        SELECT 
            f.id AS file_id,
            f.raw_danger,
            p.ai_confidence AS confidence,
            p.threat_class AS predicted_class,
            f.file_path,
            f.constellation,
            f.language,
            f.archetype,
            r.assigned_macro_species AS repo_macro_species,
            f.raw_sec_private_info
        FROM 
            ai_predictions p
        JOIN 
            galactic_census f ON p.file_id = f.id
        LEFT JOIN 
            repo_macro_fingerprints r ON f.constellation = r.constellation
        WHERE 
            f.threat_class = 0 
            AND p.threat_class > 0
        ORDER BY 
            f.raw_danger DESC, p.ai_confidence DESC
    """
    
    print("🔍 Extracting the Danger Zone (Sorted by Physical Danger Score)...")
    try:
        suspects_df = pd.read_sql_query(query, conn)
    except sqlite3.OperationalError as e:
        print(f"❌ SQL Error: {e}")
        conn.close()
        return

    conn.close()

    if suspects_df.empty:
        print("✅ No suspects found matching that criteria.")
        return

    # Export to CSV for manual review
    print(f"💾 Saving {len(suspects_df):,} files to {OUTPUT_CSV.name}...")
    suspects_df.to_csv(OUTPUT_CSV, index=False)

    # Print a full readout of the top 50 most physically dangerous files
    print("\n" + "="*110)
    print(" ☢️ THE DANGER ZONE: TOP 50 MOST PHYSICALLY LETHAL SUSPECTS")
    print("="*110)
    for _, row in suspects_df.head(50).iterrows():
        conf = row['confidence']  # Already 0-100 from apply script
        pred_class = int(row['predicted_class'])
        class_name = THREAT_LABELS.get(pred_class, "Unknown")
        
        print(f"[Danger: {row['raw_danger']:>3.0f} | AI: {conf:>6.2f}% as {class_name:<18}] {row['file_path']}")
        print(f"    Repo: {row['constellation']} | Macro: {row['repo_macro_species']} | Lang: {row['language']}\n")

    print(f"✅ Audit complete! Open {OUTPUT_CSV.name} to view the full hit-list.")

if __name__ == "__main__":
    extract_suspects()