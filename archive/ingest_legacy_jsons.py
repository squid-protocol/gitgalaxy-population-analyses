import os
import json
import sqlite3
import re
import math
from pathlib import Path

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR / "gitgalaxy_master.db"

INPUT_DIRS = [
    Path("/srv/storage_16tb/projects/gitgalaxy/threat_hunter/shared_out"),
    Path("/srv/storage_16tb/projects/gitgalaxy/v6/updated_results")
]

# --- HOTPATCH MODIFIERS ---
CONCURRENCY_MODS = [
    (re.compile(r'(?:^|/)(?:workers?|jobs?|queues?|tasks?|threads?|pools?|background)/', re.I), 0.85),
    (re.compile(r'(?:^|/)(?:streams?|sockets?|websockets?|pubsub|observables?|rx)/', re.I), 1.05),
    (re.compile(r'(?:^|/)(?:ui|views?|components?|pages?|screens?)/', re.I), 1.15),
    (re.compile(r'(?:^|/)(?:stores?|states?|reducers?|contexts?)/', re.I), 1.20),
    (re.compile(r'\.(html|htm|css|scss|svg|xml)$', re.I), 0.0)
]

FLUX_MODS = [
    (re.compile(r'(?:^|/)(?:stores?|states?|redux|vuex|pinia|zustand|mobx|contexts?|databases?|caches?)\b', re.I), 0.85),
    (re.compile(r'(?:^|/)(?:mutations?|actions?|forms?|inputs?)/', re.I), 0.95),
    (re.compile(r'(?:^|/)(?:components?|views?|pages?|screens?)/', re.I), 1.10),
    (re.compile(r'(?:^|/)(?:utils?|helpers?|shared|common)/', re.I), 1.15),
    (re.compile(r'(?:^|/)(?:configs?|envs?|globals?|constants?|settings?)/', re.I), 1.25),
    (re.compile(r'(?:^|/)migrations?/|\.sql$|\.gradle$', re.I), 0.0),
    (re.compile(r'(?:^|/)(?:tests?|specs?|testing)/|.*IT\.java$', re.I), 0.0),
    (re.compile(r'(?:^|/)examples?/', re.I), 0.0)
]

def get_path_multiplier(path, mods):
    search_path = path.replace("\\", "/")
    for pattern, val in mods:
        if pattern.search(search_path):
            return val
    return 1.0

def sigmoid(density, threshold, slope):
    try:
        return 1.0 / (1.0 + math.exp(-slope * (density - threshold)))
    except OverflowError:
        return 1.0 if density > threshold else 0.0

def get_logic_loc_bin(lloc):
    if lloc < 20: return "<20"
    if lloc < 50: return "<50"
    if lloc < 200: return "<200"
    if lloc < 500: return "<500"
    if lloc < 2000: return "<2000"
    if lloc < 5000: return "<5000"
    return "+5001"

def slugify(text):
    text = text.lower().replace(" & ", " and ")
    return re.sub(r'[^a-z0-9]+', '_', text).strip('_')

def parse_risk_percentage(val_str):
    val_str = str(val_str).replace('%', '').strip()
    if "Team Tabs" in val_str: return 0.0
    if "Team Spaces" in val_str: return 100.0
    if "Neutral" in val_str: return 50.0
    if "Mixed" in val_str:
        match = re.search(r'/\s*([0-9\.]+)', val_str)
        if match: return float(match.group(1))
        return 50.0
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def main():
    if not DB_PATH.exists():
        print(f"❌ Error: Master Database not found at {DB_PATH}")
        return

    json_files = []
    for directory in INPUT_DIRS:
        if directory.exists():
            json_files.extend(list(directory.rglob("*_galaxy_audit.json")))

    if not json_files:
        print("No Audit JSON files found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get active DB columns to map schemas dynamically
    cursor.execute("PRAGMA table_info(galactic_census)")
    db_columns = {row[1] for row in cursor.fetchall()}
    
    cursor.execute("SELECT json_path FROM processed_jsons")
    processed_files = {row[0] for row in cursor.fetchall()}
    
    new_files = [f for f in json_files if str(f.resolve()) not in processed_files]
    new_files.sort(key=lambda f: f.stat().st_size, reverse=True)
    
    if not new_files:
        print("✅ All JSON files have already been indexed.")
        conn.close()
        return

    print(f"🚀 Igniting Ingestion for {len(new_files)} legacy JSON archives...")
    total_processed = 0

    for file_path in new_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
                
            ctx = payload.get("1. Forensic Trail (Traceability)", {}).get("Analysis Context", {})
            footprint = payload.get("1. Forensic Trail (Traceability)", {}).get("Source Control Footprint (Immutable Anchor)", {})
            
            repo_name = ctx.get("Target Root Name", "Unknown")
            raw_commit_date = footprint.get("Last Code Integration Date", "Unknown")
            commit_date = raw_commit_date.split("T")[0] if "T" in raw_commit_date else "Unknown"
            
            visible_matter = payload.get("6. Visible Matter (Scanned Artifacts)", {})
            total_visible_nodes = max(1, payload.get("2. Global Synthesis Summary", {}).get("summary", {}).get("visible_stars", 1))
            
            batch_rows = []
            
            for c_name, c_data in visible_matter.items():
                stars = c_data.get("Stars / Files", {})
                for f_path, star in stars.items():
                    
                    row_data = {}
                    
                    ident = star.get("1. Identity", {})
                    spatial = star.get("2. Spatial Coordinates", {})
                    galactic = star.get("3. Galactic Profile", {})
                    risks = star.get("4. Risk Exposures", {})
                    sats = star.get("5. Function Analysis (Satellites)", [])
                    hits = star.get("7. Structural DNA (Net Mitigated Signals)", {})
                    imports = star.get("9. Extracted Dependencies", [])
                    network = star.get("8. Dependency Network", {})
                    mits = star.get("6. Contextual Mitigations & Amplifications", {})
                    if isinstance(mits, str): mits = {}

                    row_data['repo_name'] = repo_name
                    row_data['commit_date'] = commit_date
                    row_data['file_name'] = ident.get("Filename", "Unknown")
                    row_data['file_path'] = f_path
                    row_data['language'] = ident.get("Language", "Unknown")
                    row_data['constellation'] = c_name
                    row_data['archetype'] = galactic.get("Global Archetype (Macro-Species)", "Unknown Archetype")
                    row_data['lock_tier'] = ident.get("Lock Tier", 4)
                    row_data['author'] = ident.get("Architect", "Unknown")
                    row_data['purpose'] = ident.get("Museum Entry", "Unknown")
                    
                    row_data['pos_x'] = spatial.get("X", 0.0)
                    row_data['pos_y'] = spatial.get("Y", 0.0)
                    row_data['pos_z'] = spatial.get("Z", 0.0)
                    
                    row_data['total_loc'] = galactic.get("Total LOC", 0)
                    row_data['coding_loc'] = galactic.get("coding LOC", 0)
                    row_data['comment_loc'] = galactic.get("Documentation LOC", 0)
                    row_data['structural_mass'] = galactic.get("Structural Mass", 0.0)
                    row_data['popularity'] = galactic.get("Popularity Rank", 0)
                    row_data['cog_raw'] = galactic.get("Raw Cognitive Density", 0.0)
                    row_data['ownership_entropy'] = galactic.get("Ownership Entropy", 0.0)
                    row_data['silo_risk'] = galactic.get("Author Distribution", 0.0)
                    row_data['raw_churn_freq'] = galactic.get("Raw Churn Frequency", 0.0)
                    row_data['global_drift'] = float(galactic.get("Global Drift", galactic.get("Global Archetype Drift", 0.0)))
                    row_data['local_drift'] = float(galactic.get("Local Drift", galactic.get("Local Archetype Drift", 0.0)))
                    row_data['logic_density'] = float(galactic.get("Logic Density", 0.0))
                    
                    cfr_raw = str(galactic.get("Control Flow Ratio", "0.0%")).replace('%', '')
                    cfr = float(cfr_raw) / 100.0 if cfr_raw.replace('.','',1).isdigit() else 0.0
                    row_data['control_flow_ratio'] = cfr
                    row_data['logic_loc'] = int(round(row_data['coding_loc'] * cfr))
                    row_data['logic_loc_bin'] = get_logic_loc_bin(row_data['logic_loc'])

                    func_count = len(sats)
                    row_data['function_count'] = func_count
                    if func_count > 0:
                        row_data['avg_func_loc'] = sum(s.get("Lines of Code (LOC)", 0) for s in sats) / func_count
                        row_data['avg_func_complexity'] = sum(s.get("Control Flow Branches", 0) for s in sats) / func_count
                        row_data['max_func_complexity'] = max([s.get("Control Flow Branches", 0) for s in sats] + [0])
                        row_data['avg_func_args'] = sum(s.get("Input Parameters", 0) for s in sats) / func_count
                    else:
                        row_data['avg_func_loc'] = 0.0
                        row_data['avg_func_complexity'] = 0.0
                        row_data['max_func_complexity'] = 0.0
                        row_data['avg_func_args'] = 0.0
                        
                    row_data['import_count'] = len(imports)
                    row_data['import_list'] = ",".join(imports)
                    
                    row_data['direct_upstream'] = network.get("Direct Upstream (Fragility)", 0)
                    row_data['direct_downstream'] = network.get("Direct Downstream (Blast Radius)", 0)
                    row_data['total_upstream'] = network.get("Total Upstream (Absolute Fragility)", 0)
                    row_data['total_downstream'] = network.get("Total Downstream (Absolute Blast Radius)", 0)
                    row_data['direct_upstream_ratio'] = row_data['direct_upstream'] / total_visible_nodes
                    row_data['direct_downstream_ratio'] = row_data['direct_downstream'] / total_visible_nodes
                    row_data['total_upstream_ratio'] = row_data['total_upstream'] / total_visible_nodes
                    row_data['total_downstream_ratio'] = row_data['total_downstream'] / total_visible_nodes

                    def parse_mit(v): return int(str(v).split()[0]) if v else 0
                    m_danger = parse_mit(mits.get("Mitigated Danger", 0))
                    m_mem = parse_mit(mits.get("Mitigated Memory Allocs", 0))
                    a_rce = parse_mit(mits.get("Amplified Rce", 0))
                    a_race = parse_mit(mits.get("Amplified Race Conditions", 0))
                    a_leaks = parse_mit(mits.get("Amplified Leaks", 0))

                    row_data['mitigated_danger'] = m_danger
                    row_data['mitigated_memory_allocs'] = m_mem
                    row_data['amplified_rce'] = a_rce
                    row_data['amplified_race_conditions'] = a_race
                    row_data['amplified_leaks'] = a_leaks

                    raw_danger = int(hits.get("Dynamic Code Execution (Eval/Exec)", 0)) + m_danger
                    raw_mem = int(hits.get("Manual Memory Allocation", 0)) + m_mem
                    raw_conc = max(0, int(hits.get("Asynchronous/Concurrent Execution", 0)) - a_race)
                    raw_leaks = max(0, int(hits.get("Embedded Credentials & Keys", 0)) - a_leaks)
                    raw_rce = max(0, int(hits.get("Sec Tainted Injection", 0)) - a_rce)

                    row_data['raw_danger'] = raw_danger
                    row_data['raw_memory_alloc'] = raw_mem
                    row_data['raw_concurrency'] = raw_conc
                    row_data['raw_sec_private_info'] = raw_leaks
                    row_data['raw_sec_tainted_injection'] = raw_rce
                    row_data['is_malware'] = 0

                    # 1. Map the Hits
                    for orig, val in hits.items():
                        col_name = f"hit_{slugify(orig)}"
                        if col_name in db_columns:
                            row_data[col_name] = int(val)
                            
                    # 2. Map the Risks (Except Concurrency and Flux)
                    for orig, val in risks.items():
                        col_name = f"risk_{slugify(orig)}"
                        if col_name in db_columns:
                            row_data[col_name] = parse_risk_percentage(val)

                    # 3. ON-THE-FLY RECALCULATION: Concurrency & State Flux
                    loc = max(row_data['coding_loc'], 1)
                    raw_concurrency = row_data.get('hit_asynchronous_concurrent_execution', 0)
                    sync_locks = row_data.get('hit_thread_synchronization_locks', 0)
                    raw_flux = row_data.get('hit_state_mutations_variable_reassignments', 0)
                    freeze_hits = row_data.get('hit_immutable_data_declarations', 0)

                    # Concurrency Math
                    mp_c = get_path_multiplier(f_path, CONCURRENCY_MODS)
                    net_c = max(0.0, raw_concurrency - (sync_locks * 1.5))
                    if net_c == 0:
                        row_data['risk_concurrency_exposure'] = 0.0
                    else:
                        den_c = net_c / max(loc + 25, 1)
                        row_data['risk_concurrency_exposure'] = min(sigmoid(den_c, 2.5, 0.8) * 100.0 * mp_c, 100.0)

                    # State Flux Math
                    mp_f = get_path_multiplier(f_path, FLUX_MODS)
                    net_f = max(0.0, raw_flux - (freeze_hits * 0.5))
                    if net_f == 0:
                        row_data['risk_state_flux_exposure'] = 0.0
                    else:
                        den_f = net_f / max(loc + 0, 1)
                        row_data['risk_state_flux_exposure'] = min(sigmoid(den_f, 6.0, 0.4) * 100.0 * mp_f, 100.0)

                    # 4. Map the Archetypes (Truncated to what fits in the DB)
                    arch_fingerprint = galactic.get("Global Fingerprint", {})
                    for orig, val in arch_fingerprint.items():
                        col_name = "arch_" + slugify(orig.split(':')[0])
                        if col_name in db_columns:
                            row_data[col_name] = float(val)

                    batch_rows.append(row_data)

            if batch_rows:
                cols = list(batch_rows[0].keys())
                placeholders = ",".join(["?"] * len(cols))
                insert_sql = f"INSERT OR REPLACE INTO galactic_census ({','.join(cols)}) VALUES ({placeholders})"
                
                tuple_rows = [[r.get(c, 0) for c in cols] for r in batch_rows]
                cursor.executemany(insert_sql, tuple_rows)
                
            cursor.execute("INSERT INTO processed_jsons (json_path) VALUES (?)", (str(file_path.resolve()),))
            conn.commit()
            total_processed += 1
            print(f"    [+] Ingested {file_path.name}")

        except Exception as e:
            print(f"    [-] Error processing {file_path.name}: {e}")

    conn.close()
    print(f"\n✅ Successfully ingested {total_processed} legacy archives.")

if __name__ == "__main__":
    main()