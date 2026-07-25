import os
import sqlite3
from pathlib import Path
import sys

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()

# Directories to search for individual repository .db files
INPUT_DIRS = [
    Path("/srv/storage_16tb/projects/gitgalaxy/v6/updated_results_2")
]

MASTER_DB_PATH = SCRIPT_DIR / "data" / "gitgalaxy_master.db"

# A source db must have these to be considered valid at all.
CORE_TABLES = ['repo_data', 'file_data', 'function_data']

# record_keeper.py added these at different times, so older *_master.db files may
# not have them yet. Each is merged opportunistically per-db: if it's missing or
# its schema has drifted, only ITS OWN contribution is skipped for that repo --
# repo_data/file_data/function_data still merge normally.
OPTIONAL_TABLES = ['folder_data', 'class_data', 'excluded_artifacts']

def find_database_files():
    """Finds all SQLite databases in the input directories."""
    db_files = []
    for directory in INPUT_DIRS:
        if directory.exists():
            # Find all _master.db files, excluding the master database if it's in the same folder
            found = [f for f in directory.rglob("*_master.db") if f.name != MASTER_DB_PATH.name]
            db_files.extend(found)
    return db_files

def clone_table_schema(master_cursor, source_cursor, table):
    """Clones a single table's CREATE TABLE (and its indexes) from source to master, if present."""
    source_cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
    result = source_cursor.fetchone()
    if not (result and result[0]):
        return False

    safe_sql = result[0].replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS")
    master_cursor.execute(safe_sql)

    source_cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
        (table,),
    )
    for (index_sql,) in source_cursor.fetchall():
        master_cursor.execute(index_sql.replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS"))
    return True

def get_columns(cursor, table_name):
    """Dynamically extracts column names from a table, ignoring the primary key 'id'."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    cols = [row[1] for row in cursor.fetchall() if row[1] != 'id']
    return cols

def merge_databases():
    db_files = find_database_files()
    if not db_files:
        print("❌ No database files found in the specified input directories.")
        return

    print(f"🚀 Found {len(db_files)} database files. Initiating Master Merge...")

    master_conn = sqlite3.connect(MASTER_DB_PATH)
    master_cursor = master_conn.cursor()

    # Create an idempotency shield table to track what we've already merged
    master_cursor.execute("CREATE TABLE IF NOT EXISTS merged_scans (db_name TEXT UNIQUE)")
    master_conn.commit()

    # Tracking metrics to guarantee zero data loss
    verification = {
        "source_repos": 0, "master_repos": 0,
        "source_files": 0, "master_files": 0,
        "source_funcs": 0, "master_funcs": 0,
        "source_classes": 0, "master_classes": 0,
        "source_folders": 0, "master_folders": 0,
        "source_excluded": 0, "master_excluded": 0,
    }

    core_schema_cloned = False
    repo_cols = file_cols = func_cols = None
    repo_placeholders = file_placeholders = func_placeholders = None
    func_select_cols = parent_class_pos = None

    optional_schema_cloned = {t: False for t in OPTIONAL_TABLES}
    optional_cols = {}
    skipped_optional = {t: 0 for t in OPTIONAL_TABLES}

    for index, db_path in enumerate(db_files, start=1):
        # Check the Idempotency Shield first
        master_cursor.execute("SELECT 1 FROM merged_scans WHERE db_name = ?", (db_path.name,))
        if master_cursor.fetchone():
            print(f"[{index}/{len(db_files)}] ⏩ Skipping (Already Merged): {db_path.name}")
            continue

        try:
            source_conn = sqlite3.connect(db_path)
            source_cursor = source_conn.cursor()

            # 0. Basic Table Verification
            source_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = {row[0] for row in source_cursor.fetchall()}
            if not set(CORE_TABLES).issubset(existing_tables):
                print(f"[{index}/{len(db_files)}] ⚠️ WARNING: '{db_path.name}' is missing required tables. Skipping.")
                continue

            # 1. Clone core schema on the first pass
            if not core_schema_cloned:
                for t in CORE_TABLES:
                    clone_table_schema(master_cursor, source_cursor, t)

                # Cache the dynamic column names for inserts
                repo_cols = get_columns(source_cursor, "repo_data")
                file_cols = get_columns(source_cursor, "file_data")
                func_cols = get_columns(source_cursor, "function_data")

                repo_placeholders = ",".join(["?"] * len(repo_cols))
                file_placeholders = ",".join(["?"] * len(file_cols))
                func_placeholders = ",".join(["?"] * len(func_cols))

                # function_data is always selected as (file_id, <everything else in
                # table order>) below, so parent_class_id's position in that "rest"
                # tuple is fixed for the whole run once the reference schema is set.
                func_select_cols = [c for c in func_cols if c != 'file_id']
                parent_class_pos = (
                    func_select_cols.index('parent_class_id') if 'parent_class_id' in func_select_cols else None
                )

                core_schema_cloned = True
            else:
                # 1.5 Strict Column Verification (Prevents Schema Corruption)
                if repo_cols != get_columns(source_cursor, "repo_data") or \
                   file_cols != get_columns(source_cursor, "file_data") or \
                   func_cols != get_columns(source_cursor, "function_data"):
                    print(f"[{index}/{len(db_files)}] ⚠️ WARNING: Schema column mismatch in '{db_path.name}'. Skipping.")
                    continue

            # 1.6 Clone/verify the optional tables independently. A missing or
            # drifted optional table only drops ITS OWN contribution for this repo.
            merge_this_optional = {}
            for t in OPTIONAL_TABLES:
                if t not in existing_tables:
                    merge_this_optional[t] = False
                    continue
                if not optional_schema_cloned[t]:
                    clone_table_schema(master_cursor, source_cursor, t)
                    optional_cols[t] = get_columns(source_cursor, t)
                    optional_schema_cloned[t] = True
                    merge_this_optional[t] = True
                elif optional_cols[t] != get_columns(source_cursor, t):
                    print(f"[{index}/{len(db_files)}] ⚠️ WARNING: '{t}' schema mismatch in '{db_path.name}'. Skipping '{t}' for this repo only.")
                    merge_this_optional[t] = False
                    skipped_optional[t] += 1
                else:
                    merge_this_optional[t] = True

            print(f"[{index}/{len(db_files)}] Merging: {db_path.name}")

            # 2. Extract Source Data
            source_cursor.execute(f"SELECT {','.join(repo_cols)} FROM repo_data")
            repo_rows = source_cursor.fetchall()
            verification["source_repos"] += len(repo_rows)

            source_cursor.execute(f"SELECT id, {','.join(file_cols)} FROM file_data")
            file_rows = source_cursor.fetchall()
            verification["source_files"] += len(file_rows)

            source_cursor.execute(f"SELECT file_id, {','.join(func_select_cols)} FROM function_data")
            func_rows = source_cursor.fetchall()
            verification["source_funcs"] += len(func_rows)

            # Classes are keyed by their OLD file_id so they can be re-attached to
            # the NEW file_id below, and their OLD id is kept so functions can remap
            # parent_class_id the same way file_id already gets remapped.
            classes_by_old_file_id = {}
            if merge_this_optional['class_data']:
                class_select_cols = [c for c in optional_cols['class_data'] if c != 'file_id']
                source_cursor.execute(f"SELECT id, file_id, {','.join(class_select_cols)} FROM class_data")
                class_rows = source_cursor.fetchall()
                verification["source_classes"] += len(class_rows)
                for c in class_rows:
                    old_class_id, old_file_id_for_class = c[0], c[1]
                    classes_by_old_file_id.setdefault(old_file_id_for_class, []).append((old_class_id, c[2:]))

            folder_rows = []
            if merge_this_optional['folder_data']:
                folder_cols = optional_cols['folder_data']
                source_cursor.execute(f"SELECT {','.join(folder_cols)} FROM folder_data")
                folder_rows = source_cursor.fetchall()
                verification["source_folders"] += len(folder_rows)

            excluded_rows = []
            if merge_this_optional['excluded_artifacts']:
                excluded_cols = optional_cols['excluded_artifacts']
                source_cursor.execute(f"SELECT {','.join(excluded_cols)} FROM excluded_artifacts")
                excluded_rows = source_cursor.fetchall()
                verification["source_excluded"] += len(excluded_rows)

            # 3. Insert Repo Data
            master_cursor.executemany(f"INSERT OR REPLACE INTO repo_data ({','.join(repo_cols)}) VALUES ({repo_placeholders})", repo_rows)

            # 3.5 Insert Folder / Excluded-Artifacts Data (no foreign keys to remap --
            # folder_data keys off repo_name+commit_hash, excluded_artifacts is standalone)
            if folder_rows:
                folder_cols = optional_cols['folder_data']
                folder_placeholders = ",".join(["?"] * len(folder_cols))
                master_cursor.executemany(
                    f"INSERT INTO folder_data ({','.join(folder_cols)}) VALUES ({folder_placeholders})",
                    folder_rows,
                )
            if excluded_rows:
                excluded_cols = optional_cols['excluded_artifacts']
                excluded_placeholders = ",".join(["?"] * len(excluded_cols))
                master_cursor.executemany(
                    f"INSERT INTO excluded_artifacts ({','.join(excluded_cols)}) VALUES ({excluded_placeholders})",
                    excluded_rows,
                )

            # 4. Insert File Data, Remapping Foreign Keys for Classes and Functions
            # Group functions by their OLD file_id
            funcs_by_old_file_id = {}
            for f in func_rows:
                old_file_id = f[0]
                funcs_by_old_file_id.setdefault(old_file_id, []).append(f[1:])  # everything except the old file_id

            class_insert_sql = None
            if merge_this_optional['class_data']:
                class_cols = optional_cols['class_data']
                class_insert_sql = f"INSERT INTO class_data ({','.join(class_cols)}) VALUES ({','.join(['?'] * len(class_cols))})"

            master_funcs_to_insert = []

            for f_row in file_rows:
                old_file_id = f_row[0]
                file_data = f_row[1:]

                # Insert the file into the master DB
                master_cursor.execute(f"INSERT INTO file_data ({','.join(file_cols)}) VALUES ({file_placeholders})", file_data)

                # Capture the NEW file_id generated by the master DB
                new_master_file_id = master_cursor.lastrowid

                # Insert this file's classes now (if any), remapping file_id, and
                # remember old->new class id so this file's functions can remap
                # parent_class_id right below -- mirrors how record_keeper.py itself
                # links functions to classes only within the same file.
                class_id_map = {}
                if merge_this_optional['class_data']:
                    for old_class_id, class_rest in classes_by_old_file_id.get(old_file_id, []):
                        master_cursor.execute(class_insert_sql, [new_master_file_id] + list(class_rest))
                        class_id_map[old_class_id] = master_cursor.lastrowid

                # Grab all functions that belonged to this old file_id and attach the new IDs
                for func_data in funcs_by_old_file_id.get(old_file_id, []):
                    func_data = list(func_data)
                    if parent_class_pos is not None:
                        old_parent_class_id = func_data[parent_class_pos]
                        func_data[parent_class_pos] = (
                            class_id_map.get(old_parent_class_id) if old_parent_class_id is not None else None
                        )
                    # Reassemble: [new_file_id, parent_class_id (remapped), func_name...]
                    master_funcs_to_insert.append([new_master_file_id] + func_data)

            # 5. Insert Function Data with corrected Foreign Keys
            if master_funcs_to_insert:
                master_cursor.executemany(f"INSERT INTO function_data ({','.join(func_cols)}) VALUES ({func_placeholders})", master_funcs_to_insert)

            # Record that this DB was successfully merged to prevent future rescans
            master_cursor.execute("INSERT INTO merged_scans (db_name) VALUES (?)", (db_path.name,))
            master_conn.commit()

            source_conn.close()

        except Exception as e:
            print(f"❌ Error merging {db_path.name}: {e}")

    # Commit all changes to master
    master_conn.commit()

    # 6. Verify Master Database Counts (Crash-Proof)
    def safe_count(table):
        try:
            master_cursor.execute(f"SELECT COUNT(*) FROM {table}")
            return master_cursor.fetchone()[0]
        except sqlite3.OperationalError:
            return 0

    verification["master_repos"] = safe_count("repo_data")
    verification["master_files"] = safe_count("file_data")
    verification["master_funcs"] = safe_count("function_data")
    verification["master_classes"] = safe_count("class_data")
    verification["master_folders"] = safe_count("folder_data")
    verification["master_excluded"] = safe_count("excluded_artifacts")

    master_conn.close()

    # ==============================================================================
    # THE INTEGRITY REPORT
    # ==============================================================================
    print("\n" + "="*50)
    print("🧬 MASTER DATABASE INTEGRITY REPORT")
    print("="*50)
    print(f"Target DB: {MASTER_DB_PATH.name}")
    print("-"*50)

    def status(src, dst):
        return "✅ PERFECT MATCH" if src == dst else "❌ DATA LOSS DETECTED"

    print(f"Repositories : {verification['source_repos']:<8} -> {verification['master_repos']:<8} | {status(verification['source_repos'], verification['master_repos'])}")
    print(f"Files        : {verification['source_files']:<8} -> {verification['master_files']:<8} | {status(verification['source_files'], verification['master_files'])}")
    print(f"Functions    : {verification['source_funcs']:<8} -> {verification['master_funcs']:<8} | {status(verification['source_funcs'], verification['master_funcs'])}")
    print(f"Classes      : {verification['source_classes']:<8} -> {verification['master_classes']:<8} | {status(verification['source_classes'], verification['master_classes'])}")
    print(f"Folders      : {verification['source_folders']:<8} -> {verification['master_folders']:<8} | {status(verification['source_folders'], verification['master_folders'])}")
    print(f"Excluded     : {verification['source_excluded']:<8} -> {verification['master_excluded']:<8} | {status(verification['source_excluded'], verification['master_excluded'])}")
    print("-"*50)
    for t in OPTIONAL_TABLES:
        if skipped_optional[t]:
            print(f"⚠️  {t}: schema-drift skipped for {skipped_optional[t]} repo(s) this run (see warnings above)")
    print("="*50 + "\n")

if __name__ == "__main__":
    merge_databases()
