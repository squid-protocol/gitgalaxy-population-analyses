import sqlite3
import math
import re
import time

# 1. Configuration
db_file = 'gitgalaxy_master.db'

# 2. Path Modifiers (Mirrored from gitgalaxy_standards_v1.py)
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
    """Calculates the domain context multiplier for a given file path."""
    search_path = path.replace("\\", "/")
    for pattern, val in mods:
        if pattern.search(search_path):
            return val
    return 1.0

def sigmoid(density, threshold, slope):
    """Calculates the S-curve exposure percentage safely."""
    try:
        return 1.0 / (1.0 + math.exp(-slope * (density - threshold)))
    except OverflowError:
        return 1.0 if density > threshold else 0.0

def main():
    print(f"[*] Connecting to {db_file}...")
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    print("[*] Fetching raw DNA telemetry from galactic_census...")
    start_time = time.time()
    
    # We fetch ALL files so the entire census remains mathematically consistent
    cursor.execute('''
        SELECT 
            id, 
            file_path, 
            coding_loc, 
            hit_asynchronous_concurrent_execution, 
            hit_thread_synchronization_locks,
            hit_state_mutations_variable_reassignments,
            hit_immutable_data_declarations
        FROM galactic_census
    ''')
    rows = cursor.fetchall()
    
    print(f"[+] Loaded {len(rows):,} files in {time.time() - start_time:.2f} seconds.")
    print("[*] Recalculating physics equations...")

    updates = []
    
    for row in rows:
        db_id, path, loc, raw_concurrency, sync_locks, raw_flux, freeze_hits = row
        loc = max(loc, 1) # Prevent division by zero
        
        # -------------------------------------------------------------
        # EQUATION 1: CONCURRENCY EXPOSURE
        # -------------------------------------------------------------
        mp_c = get_path_multiplier(path, CONCURRENCY_MODS)
        net_c = max(0.0, raw_concurrency - (sync_locks * 1.5))
        
        if net_c == 0:
            score_c = 0.0
        else:
            den_c = net_c / max(loc + 25, 1) # New padding: 25
            # New Tuning: Threshold 2.5, Slope 0.8
            score_c = sigmoid(den_c, 2.5, 0.8) * 100.0 * mp_c
            score_c = min(score_c, 100.0) # Clamp to 100 max

        # -------------------------------------------------------------
        # EQUATION 2: STATE FLUX EXPOSURE
        # -------------------------------------------------------------
        mp_f = get_path_multiplier(path, FLUX_MODS)
        net_f = max(0.0, raw_flux - (freeze_hits * 0.5))
        
        if net_f == 0:
            score_f = 0.0
        else:
            den_f = net_f / max(loc + 0, 1) # New padding: 0
            # New Tuning: Threshold 6.0, Slope 0.4
            score_f = sigmoid(den_f, 6.0, 0.4) * 100.0 * mp_f
            score_f = min(score_f, 100.0) # Clamp to 100 max

        updates.append((score_c, score_f, db_id))

    print("[*] Hot-patching the database in memory-safe chunks...")
    
    # Write to the DB in chunks of 100,000 to keep RAM utilization flat
    batch_size = 100000
    total_updates = len(updates)
    
    for i in range(0, total_updates, batch_size):
        batch = updates[i:i + batch_size]
        cursor.executemany('''
            UPDATE galactic_census 
            SET risk_concurrency_exposure = ?, 
                risk_state_flux_exposure = ? 
            WHERE id = ?
        ''', batch)
        conn.commit()
        print(f"    -> Committed {min(i + batch_size, total_updates):,}/{total_updates:,} rows...")

    conn.close()
    print(f"\n[+] Hot-patch complete! Total execution time: {time.time() - start_time:.2f} seconds.")

if __name__ == "__main__":
    main()