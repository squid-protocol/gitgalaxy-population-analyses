import sqlite3
from pathlib import Path
from collections import Counter
import sys

SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR / "data" / "gitgalaxy_master.db"

# Attempt to load your local standards (adjust path if needed)
try:
    from gitgalaxy import gitgalaxy_standards_v1 as config
    LANGUAGE_DEFS = config.LANGUAGE_DEFINITIONS
except ImportError:
    print("⚠️ Could not import gitgalaxy_standards_v1. Run this from the same directory as your gitgalaxy module.")
    sys.exit(1)

def audit_ecosystem():
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        return

    global_ext_tally = Counter()
    total_files = 0

    print(f"📡 Connecting to Database: {DB_PATH.name}...")
    
    # 1. Aggregate all extensions directly from the master database
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        print("📥 Pulling file inventory from galactic_census...")
        cursor.execute("SELECT file_name FROM galactic_census")
        
        for row in cursor.fetchall():
            file_name = row[0]
            if file_name:
                ext = Path(file_name).suffix.lower()
                global_ext_tally[ext] += 1
                total_files += 1
                
        conn.close()
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return

    if not global_ext_tally:
        print("❌ No files found in the database.")
        return

    # 2. Cross-Reference against your Standards
    language_performance = {}
    unmapped_extensions = Counter()

    # Map the found extensions to your defined languages
    for ext, count in global_ext_tally.items():
        matched_lang = None
        for lang_id, definition in LANGUAGE_DEFS.items():
            if ext in definition.get("extensions", []):
                matched_lang = lang_id
                break
        
        if matched_lang:
            if matched_lang not in language_performance:
                language_performance[matched_lang] = 0
            language_performance[matched_lang] += count
        else:
            unmapped_extensions[ext] += count

    # 3. Print the Diagnosis
    print("\n" + "="*60)
    print(f" 🌍 ECOSYSTEM AUDIT ({total_files:,} Files Scanned)")
    print("="*60)
    
    print("\n[ LANGUAGES DEFINED IN STANDARDS: HITS FOUND ]")
    # Show languages that got hits
    for lang, count in sorted(language_performance.items(), key=lambda x: x[1], reverse=True):
        print(f"  ✅ {lang.upper():<15} : {count:,} files")
        
    # Show languages defined in your standards that found ZERO files
    defined_but_empty = [lang for lang in LANGUAGE_DEFS.keys() if lang not in language_performance]
    if defined_but_empty:
        print("\n[ ZERO HITS (Defined in Standards but missing in payloads) ]")
        for lang in defined_but_empty:
            print(f"  👻 {lang.upper():<15} : 0 files")

    print("\n[ TOP 15 UNMAPPED EXTENSIONS (Dark Matter & Debris) ]")
    for ext, count in unmapped_extensions.most_common(15):
        # Clean up empty extensions (usually folders or extensionless files)
        display_ext = ext if ext else "<extensionless>"
        print(f"  🕳️ {display_ext:<15} : {count:,} files")

    print("="*60 + "\n")

if __name__ == "__main__":
    audit_ecosystem()