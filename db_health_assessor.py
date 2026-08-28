import sqlite3
import textwrap
from pathlib import Path

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR / "data" / "gitgalaxy_master.db"

# Thresholds for raising warnings in the CLI
WARNING_NULL_PCT = 20.0       # Warn if a column is more than 20% NULL
WARNING_EMPTY_PCT = 20.0      # Warn if a text column is >20% empty strings / 'Unknown'
WARNING_ZERO_PCT = 99.0       # Warn if a numeric column is almost entirely 0 (Dead feature)

class GalaxyDBHealthAssessor:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found at {self.db_path}")
        
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

    def get_tables(self):
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        return [row[0] for row in self.cursor.fetchall()]

    def get_schema(self, table_name):
        self.cursor.execute(f"PRAGMA table_info({table_name})")
        # Returns list of tuples: (cid, name, type, notnull, dflt_value, pk)
        return [{"name": row[1], "type": row[2].upper()} for row in self.cursor.fetchall()]

    def assess_table(self, table_name):
        schema = self.get_schema(table_name)
        
        self.cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        total_rows = self.cursor.fetchone()[0]
        
        if total_rows == 0:
            return {"total_rows": 0, "issues": [f"🚨 TABLE IS EMPTY: {table_name}"]}

    # --- CONTEXT-AWARE RULES FOR GITGALAXY ---
        
        ACTIVE_LOGIC_ONLY_COLS = ['global_drift', 'local_drift', 'ai_threat_confidence']
        
        # Architectural domains, security threats, and risk vectors are naturally sparse at the micro-level.
        # llm_/ml_/dl_ are domain-detection signatures (AI/ML tooling): real, working features that are
        # simply rare outside an AI-heavy corpus -- e.g. this 718-repo population is mostly non-AI code, so
        # they read >99% zero without being dead. See squid-protocol/gitgalaxy-population-analyses#1.
        SPARSE_PREFIXES = ('sec_', 'threat_', 'mitigated_', 'amplified_', 'risk_', 'raw_sec_', 'arch_',
                           'llm_', 'ml_', 'dl_')

        # lit_* (literature sensors: code blocks, diagrams, headers, links) only ever fire on markdown/doc
        # files, which have coding_loc = 0 and are therefore structurally excluded from active_logic_total
        # -- the population this check measures against. The tool would be asking "what % of non-doc source
        # files use markdown syntax" (~0% by construction), not "is this feature dead". Confirmed working:
        # 43,752 / 49,252 markdown files carry real lit_headers hits. Exempted here rather than silenced.
        LANGUAGE_SCOPED_PREFIXES = ('lit_',)
        
        # Explicitly whitelist placeholders, file-level metrics, and highly specialized defensive/state hits
        SPARSE_EXACT = {
            'confirmed_kill_chain', 'threat_class', 'ai_threat_confidence',
            'civil_war', 'func_z_score', 'struct_tabs', 'struct_spaces',
            'state_slop_duplicates', 'state_slop_orphans', 'state_graveyard',
            'state_danger', 'state_planned_debt', 'state_fragile_debt', 'state_halt_hits',
            'def_spec_exposure', 'def_auth', 'def_telemetry', 'def_sync_locks', 
            'def_test_skip', 'def_doc', 'def_ownership',
            'lazy_evaluation'  # functional-programming signature; real signal, rare outside FP-heavy code
        }
        EXPECTED_EMPTY_TEXT = {'purpose', 'import_list', 'commit_date'}

        # --- THE FIX: ADAPT LOGIC FILTER FOR BOTH FILES AND FUNCTIONS ---
        has_coding_loc = any(c["name"] == "coding_loc" for c in schema)
        has_loc = any(c["name"] == "loc" for c in schema)
        
        if has_coding_loc:
            logic_filter = " AND (coding_loc > 0 OR language = 'plaintext')"
            active_logic_condition = "coding_loc > 0 OR language = 'plaintext'"
        elif has_loc:
            logic_filter = " AND loc >= 3"
            active_logic_condition = "loc >= 3"
        else:
            logic_filter = ""
            active_logic_condition = "1=1"

        # Build a dynamic SQL query to calculate NULLs, Empties, and Zeros in a single pass
        select_clauses = []
        for col in schema:
            name = col["name"]
            c_type = col["type"]

            # 1. Check for True NULLs (Context Aware: ML columns only exist on active logic)
            if name.startswith('arch_cluster_') or name in ACTIVE_LOGIC_ONLY_COLS:
                select_clauses.append(f"SUM(CASE WHEN {name} IS NULL{logic_filter} THEN 1 ELSE 0 END) AS {name}_null")
            else:
                select_clauses.append(f"SUM(CASE WHEN {name} IS NULL THEN 1 ELSE 0 END) AS {name}_null")

            # 2. Check for "Empty" Text (Blanks, 'Unknown', 'N/A')
            if 'TEXT' in c_type:
                select_clauses.append(f"SUM(CASE WHEN {name} = '' OR {name} = 'Unknown' OR {name} = 'N/A' THEN 1 ELSE 0 END) AS {name}_empty")

            # 3. Check for Zero-flooded numeric columns
            elif 'INT' in c_type or 'REAL' in c_type:
                # Context Aware: Only measure zeros against files that actually have logic
                select_clauses.append(f"SUM(CASE WHEN ({name} = 0 OR {name} = 0.0){logic_filter} THEN 1 ELSE 0 END) AS {name}_zero")

        # Also get the total number of active logic elements so our percentages are mathematically accurate
        select_clauses.append(f"SUM(CASE WHEN {active_logic_condition} THEN 1 ELSE 0 END) AS active_logic_total")

        query = f"SELECT {', '.join(select_clauses)} FROM {table_name}"
        self.cursor.execute(query)
        results = self.cursor.fetchone()

        col_names = [description[0] for description in self.cursor.description]
        stats = dict(zip(col_names, results))

        active_logic_total = stats.get("active_logic_total", total_rows)
        # Prevent division by zero if a table is entirely inert
        active_logic_total = max(active_logic_total, 1)

        issues = []
        for col in schema:
            name = col["name"]
            c_type = col["type"]

            nulls = stats.get(f"{name}_null", 0)
            # Use the active logic total for ML columns, total_rows for everything else
            denom = active_logic_total if (name.startswith('arch_cluster_') or name in ACTIVE_LOGIC_ONLY_COLS) else total_rows
            null_pct = (nulls / denom) * 100

            if null_pct > WARNING_NULL_PCT:
                issues.append(f"⚠️ HIGH NULL RATE: '{name}' is {null_pct:.1f}% NULL ({nulls:,} rows).")

            if 'TEXT' in c_type:
                empties = stats.get(f"{name}_empty", 0)
                empty_pct = (empties / total_rows) * 100
                
                # Context Aware: Raise the warning threshold for metadata we expect to be heavily absent
                threshold = 95.0 if name in EXPECTED_EMPTY_TEXT else WARNING_EMPTY_PCT

                if empty_pct > threshold:
                    issues.append(f"⚠️ MISSING TEXT DATA: '{name}' is {empty_pct:.1f}% empty or 'Unknown' ({empties:,} rows).")

            elif 'INT' in c_type or 'REAL' in c_type:
                zeros = stats.get(f"{name}_zero", 0)
                zero_pct = (zeros / active_logic_total) * 100

                # Context Aware: Skip the "Dead Feature" check for sparse security features, sparse
                # domain-detection signatures, and language-scoped columns the active-logic filter
                # structurally excludes from its own denominator.
                is_sparse_expected = (
                    name.startswith(SPARSE_PREFIXES)
                    or name.startswith(LANGUAGE_SCOPED_PREFIXES)
                    or name in SPARSE_EXACT
                )

                if zero_pct >= WARNING_ZERO_PCT and not name.endswith('id') and not name.startswith('is_') and not is_sparse_expected:
                    issues.append(f"💀 DEAD FEATURE: '{name}' is {zero_pct:.1f}% zeros. (Safe to drop or requires upstream fix).")
        return {"total_rows": total_rows, "issues": issues}

    def run_health_check(self):
        print(f"\n🩺 INITIATING DATABASE HEALTH ASSESSMENT: {self.db_path.name}")
        print("=" * 80)
        
        tables = self.get_tables()
        if not tables:
            print("❌ No tables found in the database.")
            return

        total_issues = 0
        for table in tables:
            # Skip utility tables like processed_jsons or sqlite_sequence
            if table in ['processed_jsons', 'sqlite_sequence']:
                continue
                
            print(f"\n📁 ANALYZING TABLE: {table.upper()}")
            report = self.assess_table(table)
            
            print(f"   Rows Evaluated: {report['total_rows']:,}")
            
            if not report['issues']:
                print("   ✅ Status: Healthy. No significant anomalies detected.")
            else:
                total_issues += len(report['issues'])
                print("   🚨 NOTABLE ISSUES:")
                for issue in report['issues']:
                    # Use textwrap to keep long issue strings clean in the terminal
                    wrapped_issue = textwrap.fill(issue, width=75, initial_indent="      - ", subsequent_indent="        ")
                    print(wrapped_issue)

        print("\n" + "=" * 80)
        if total_issues == 0:
            print("🎉 ASSESSMENT COMPLETE: Database is in pristine condition.")
        else:
            print(f"⚠️ ASSESSMENT COMPLETE: {total_issues} anomalies require attention before ML ingestion.")
        print("=" * 80 + "\n")

if __name__ == "__main__":
    import sys
    try:
        # If a path is passed in the CLI, use it. Otherwise, fall back to the default.
        target_db = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
        assessor = GalaxyDBHealthAssessor(target_db)
        assessor.run_health_check()
    except Exception as e:
        print(f"\n❌ Assessment Failed: {e}")