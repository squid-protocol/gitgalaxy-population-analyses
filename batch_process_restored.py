import os
import subprocess
from pathlib import Path
import sys
import re
import time
import gzip
import shutil
import argparse
from datetime import datetime

# ==============================================================================
# TEE LOGGER: Duplicates all stdout to both the Terminal and a Log File
# ==============================================================================
class TeeLogger(object):
    def __init__(self, log_filepath):
        self.terminal = sys.stdout
        self.log_file = open(log_filepath, "w", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
        self.flush()

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

    def close(self):
        self.log_file.close()

def get_target_folders(data_dir):
    """
    Intelligently resolves target folders using Git tracking, naming conventions, 
    and root-file heuristics to natively support tarball/zip 'Naked Repos'.
    """
    targets = []
    
    if not data_dir.exists():
        print(f"❌ Error: Directory {data_dir} not found.")
        sys.exit(1)
        
    for item in sorted(data_dir.iterdir()):
        if not item.is_dir() or item.name.startswith('.') or item.name == '_archives':
            continue
            
        # 1. Direct Git Repo
        if (item / ".git").is_dir():
            print(f"🎯 Direct Repo Detected : {item.name}")
            targets.append(item)
            continue
            
        # 2. Container Heuristics (Named corpus/lists, or lacks root files)
        is_container_by_name = any(x in item.name.lower() for x in ['_corpus', 'top_200', '_systems'])
        has_root_files = any(child.is_file() for child in item.iterdir())
        
        if is_container_by_name or not has_root_files:
            container_repos = []
            for sub_item in sorted(item.iterdir()):
                # Accept the sub-item as a repo even if it lacks a .git folder
                if sub_item.is_dir() and not sub_item.name.startswith('.'):
                    container_repos.append(sub_item)
            
            if container_repos:
                print(f"📦 Container Detected   : {item.name} (Found {len(container_repos)} repos inside)")
                targets.extend(container_repos)
        else:
            # 3. Direct Naked Repo (No .git, but has files like README.md, setup.py, etc.)
            print(f"🎯 Naked Repo Detected  : {item.name} (No .git folder)")
            targets.append(item)
                    
    return targets

def resolve_output_names(target_folders):
    """Map each target folder to a UNIQUE flat output-dir name.

    A repo keeps its bare basename when that name is unique across the whole scan
    set. When two targets share a basename -- a top-level `redis` (the C server)
    and `pypi_top_200/redis` (the redis-py client), or two unrelated projects both
    named `core` -- writing both to `output/<basename>` collides: with the
    resume/skip logic one silently overwrites or shadows the other (this dropped
    the real redis behind a tutorial stub in the v2.7.0 batch). Colliding names are
    disambiguated by their parent directory (`<parent>__<name>`), with a full-path
    slug fallback, so every repo lands in its own folder and none is ever dropped.
    """
    from collections import Counter

    counts = Counter(f.name for f in target_folders)
    names, used = {}, set()
    for f in target_folders:
        name = f.name if counts[f.name] == 1 else f"{f.parent.name}__{f.name}"
        if name in used:  # residual collision -> fuller relative-path slug
            name = "__".join(p for p in f.parts[-3:])
        base, n = name, 2
        while name in used:  # final uniqueness guarantee
            name, n = f"{base}__{n}", n + 1
        used.add(name)
        names[f] = name
    return names


def compress_artifacts(repo_output_dir):
    """
    Compresses large scan artifacts (_audit.json, _master.db, _graph.sqlite, _sarif.json, _sbom.json)
    with gzip to comply with GitHub's 100MB per-file limit and reduce overall archive size.
    """
    compressible_extensions = [
        "_galaxy_audit.json",
        "_galaxy_master.db",
        "_galaxy_graph.sqlite",
        "_galaxy_sarif.json",
        "_galaxy_sbom.json",
    ]
    for file_path in repo_output_dir.iterdir():
        if file_path.is_file() and not file_path.name.endswith(".gz"):
            if any(file_path.name.endswith(ext) for ext in compressible_extensions):
                gz_path = file_path.with_name(file_path.name + ".gz")
                try:
                    with open(file_path, "rb") as f_in:
                        with gzip.open(gz_path, "wb", compresslevel=6) as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    file_path.unlink()
                    print(f"   📦 Compressed {file_path.name} -> {gz_path.name}")
                except Exception as e:
                    print(f"   ⚠️ Failed to compress {file_path.name}: {e}")

def run_batch_scan(target_path=None, output_path=None, halt_on_error=False, compress=True):
    project_root = Path("/srv/storage_16tb/projects/gitgalaxy/v6")
    data_dir = Path(target_path) if target_path else Path("/srv/storage_16tb/projects/gitgalaxy/data") 
    output_dir = Path(output_path) if output_path else Path("/srv/storage_16tb/projects/gitgalaxy-raw-output/v2.4.6")

    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Initialize the Master Log File
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    master_log_path = output_dir / f"batch_scan_master_{timestamp}.log"
    
    # Redirect stdout to our TeeLogger
    tee = TeeLogger(master_log_path)
    sys.stdout = tee
    
    print(f"Output directory established at: {output_dir}")
    print(f"📜 Master Log File active at: {master_log_path}")

    target_folders = get_target_folders(data_dir)
    output_names = resolve_output_names(target_folders)  # collision-safe per-repo dirs
    total_folders = len(target_folders)

    print(f"\n🎯 Found {total_folders} total repositories/packages to scan.")
    
    if total_folders == 0:
        print("✅ No target folders found. Exiting.")
        sys.stdout = tee.terminal # Restore normal stdout
        tee.close()
        return
        
    print(f"🚀 Starting BATCH SCAN for all {total_folders} targets...\n")

    # ==========================================================================
    # ANOMALY INTERCEPTOR PATTERNS & STATE
    # ==========================================================================
    telemetry_pattern = re.compile(r"Processed\s+([\d,]+)\s+lines of code at\s+([\d,]+)\s+LOC/s")
    
    # regexes to catch specific log signatures emitted by GalaxyScope
    p_redos = re.compile(r"TIMEOUT GUILLOTINE: '([^']+)' exceeded")
    p_starvation = re.compile(r"TIMEOUT: (.+)") # Catches the worker starvation list
    p_slow = re.compile(r"SLOW PARSE DETECTED: '([^']+)' took ([\d\.]+) seconds")
    p_xray = re.compile(r"X-RAY TRIGGERED: Weaponized binary detected at '([^']+)'")
    p_typosquat = re.compile(r"TYPOSQUATTING DETECTED: (.+)")
    
    anomaly_report = {
        "failed_repos": [],
        "redos_timeouts": [],
        "slow_files": [],
        "xray_hits": [],
        "typosquat_hits": []
    }
    
    scan_results = []
    global_start_time = time.perf_counter()
    total_loc = 0
    halt_batch = False  # <--- The kill switch

    for index, folder in enumerate(target_folders, start=1):
        
        # Output folder per repo: collision-safe name (bare basename when unique,
        # <parent>__<name> when it would collide with another target -- see
        # resolve_output_names).
        repo_output_dir = output_dir / output_names[folder]
        repo_output_dir.mkdir(parents=True, exist_ok=True)
        
        # --- RESUME / SKIP LOGIC ---
        # Look for the GPU payload in the per-repo folder as final pipeline artifact indicator
        expected_output = repo_output_dir / f"{folder.name}_galaxy_gpu.json"
        if expected_output.exists():
            # Ensure any leftover uncompressed files get zipped
            if compress:
                compress_artifacts(repo_output_dir)
            print(f"\n⏭️  [{index}/{total_folders}] SKIPPING: '{folder.name}' (Already scanned at {repo_output_dir.name})")
            continue
            
        print("\n" + "="*60)
        print(f"[{index}/{total_folders}] 🚀 IGNITING GALAXYOSCOPE FOR: {folder.name}")
        print(f"               Target Path: {folder.absolute()}")
        print(f"               Output Path: {repo_output_dir.absolute()}")
        print("="*60)
        
        repo_loc = 0
        repo_rate = 0
        
        try:
            custom_env = os.environ.copy()
            custom_env["GITGALAXY_DATA_DIR"] = str(repo_output_dir)
            custom_env["GITGALAXY_LICENSE_KEY"] = "COMMUNITY_FREE_TIER"
            
            process = subprocess.Popen(
                [sys.executable, "-m", "gitgalaxy.galaxyscope", str(folder.absolute()), "--output", str(repo_output_dir)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1, 
                cwd=str(project_root), 
                env=custom_env 
            )

            # Stream output live, logging it and scanning it for errors
            for line in process.stdout:
                sys.stdout.write(line)
                
                # Check for standard telemetry
                match = telemetry_pattern.search(line)
                if match:
                    repo_loc = int(match.group(1).replace(',', ''))
                    repo_rate = int(match.group(2).replace(',', ''))
                    continue
                
                # Check for anomalies
                if "TIMEOUT GUILLOTINE" in line:
                    m = p_redos.search(line)
                    if m: anomaly_report["redos_timeouts"].append((folder.name, m.group(1)))
                elif "TIMEOUT:" in line and "Worker Thread Starvation" not in line:
                    m = p_starvation.search(line)
                    if m: anomaly_report["redos_timeouts"].append((folder.name, m.group(1).strip()))
                elif "SLOW PARSE DETECTED" in line:
                    m = p_slow.search(line)
                    if m: anomaly_report["slow_files"].append((folder.name, m.group(1), m.group(2)))
                elif "X-RAY TRIGGERED" in line:
                    m = p_xray.search(line)
                    if m: anomaly_report["xray_hits"].append((folder.name, m.group(1)))
                elif "TYPOSQUATTING DETECTED" in line:
                    m = p_typosquat.search(line)
                    if m: anomaly_report["typosquat_hits"].append((folder.name, m.group(1)))

            process.wait()
            
            if process.returncode == 0:
                print(f"\n✅ SUCCESS: {folder.name} completed.\n")
                if compress:
                    compress_artifacts(repo_output_dir)
                if repo_loc > 0 and repo_rate > 0:
                    engine_time = repo_loc / repo_rate
                    scan_results.append({
                        'name': folder.name,
                        'loc': repo_loc,
                        'rate': repo_rate,
                        'time': engine_time
                    })
                    total_loc += repo_loc
            else:
                print(f"\n❌ FAILURE: Error scanning {folder.name}. Engine crashed or aborted.\n")
                anomaly_report["failed_repos"].append(folder.name)
                if halt_on_error:
                    halt_batch = True
            
        except FileNotFoundError:
            print("\n❌ CRITICAL: Python executable not found. Are you in your galaxy_venv?\n")
            anomaly_report["failed_repos"].append(folder.name)
            if halt_on_error:
                halt_batch = True
        except Exception as e:
            print(f"\n❌ UNEXPECTED ERROR on {folder.name}: {e}\n")
            anomaly_report["failed_repos"].append(folder.name)
            if halt_on_error:
                halt_batch = True

        if halt_batch:
            print(f"\n🛑 BATCH HALTED: Critical exception detected in '{folder.name}'. Stopping further scans.")
            break

    global_end_time = time.perf_counter()
    total_wall_clock_seconds = global_end_time - global_start_time

    # ==============================================================================
    # FINAL CLI REPORT & ANOMALY SUMMARY
    # ==============================================================================
    print("\n" + "="*80)
    if halt_batch:
        print("🛑 MISSION ABORTED: GALAXYOSCOPE BATCH TELEMETRY REPORT (INCOMPLETE)")
    else:
        print("MISSION COMPLETE: GALAXYOSCOPE BATCH TELEMETRY REPORT")
    print("="*80)
    
    if scan_results:
        scan_results.sort(key=lambda x: x['rate'], reverse=True)
        print(f"{'Rank':<5} | {'Repository':<30} | {'LOC Scanned':<12} | {'Rate (LOC/s)':<12} | {'Engine Time'}")
        print("-" * 80)
        for i, res in enumerate(scan_results, 1):
            name = res['name'] if len(res['name']) <= 28 else res['name'][:25] + "..." 
            print(f"{i:<5} | {name:<30} | {res['loc']:<12,} | {res['rate']:<12,} | {res['time']:.2f}s")
        print("-" * 80)
        
        global_avg_rate = total_loc / total_wall_clock_seconds if total_wall_clock_seconds > 0 else 0
        print(f"Total Repositories Scanned : {len(scan_results)}")
        print(f"Total LOC Scanned          : {total_loc:,}")
        print(f"Total Clock Time Taken     : {total_wall_clock_seconds:.2f} seconds")
        print(f"Global Average Scan Rate   : {global_avg_rate:,.0f} LOC/s")
    else:
        print("No telemetry data was collected. Check engine output for errors.")

    # --- THE ANOMALY AUDIT REPORT ---
    print("\n" + "="*80)
    print(" 🚨 BATCH ANOMALY & ERROR REPORT")
    print("="*80)
    
    if anomaly_report["failed_repos"]:
        print(f"❌ Failed Repositories ({len(anomaly_report['failed_repos'])}):")
        for repo in anomaly_report["failed_repos"]:
            print(f"   - {repo}")
    else:
        print("❌ Failed Repositories: 0")
        
    if anomaly_report["redos_timeouts"]:
        print(f"\n⏳ ReDoS / Saturation Timeouts ({len(anomaly_report['redos_timeouts'])} files):")
        for repo, file in anomaly_report["redos_timeouts"]:
            print(f"   - [{repo}] : {file}")
            
    if anomaly_report["slow_files"]:
        print(f"\n🐌 Slow Files > 10s ({len(anomaly_report['slow_files'])} files):")
        for repo, file, time_sec in anomaly_report["slow_files"]:
            print(f"   - [{repo}] : {file} ({time_sec}s)")
            
    if anomaly_report["xray_hits"]:
        print(f"\n☢️ X-Ray Weaponized Binaries ({len(anomaly_report['xray_hits'])} hits):")
        for repo, file in anomaly_report["xray_hits"]:
            print(f"   - [{repo}] : {file}")
            
    if anomaly_report["typosquat_hits"]:
        print(f"\n⚠️ Typosquatting Attempts ({len(anomaly_report['typosquat_hits'])} hits):")
        for repo, details in anomaly_report["typosquat_hits"]:
            print(f"   - [{repo}] : {details}")

    if not any(anomaly_report.values()):
        print("\n✅ Clean sweep! No timeouts, failures, or critical anomalies detected.")

    print("="*80)
    print(f"💾 Report saved to: {master_log_path}\n")

    # Restore normal stdout before exiting
    sys.stdout = tee.terminal
    tee.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GitGalaxy Batch Scanner")
    parser.add_argument("target", nargs="?", default="/srv/storage_16tb/projects/gitgalaxy/data", help="Folder containing repos to scan")
    parser.add_argument("--output", default="/srv/storage_16tb/projects/gitgalaxy-raw-output/v2.4.6", help="Output destination folder")
    parser.add_argument("--halt-on-error", action="store_true", help="Halt batch scan immediately if a repo scan fails")
    parser.add_argument("--no-compress", action="store_true", help="Disable automatic gzip compression of large artifacts")
    args = parser.parse_args()
    
    run_batch_scan(
        target_path=args.target,
        output_path=args.output,
        halt_on_error=args.halt_on_error,
        compress=not args.no_compress
    )