import json
import os
import concurrent.futures
from pathlib import Path
from collections import defaultdict, Counter

SHORT_TERMS = {
    "Dangerous Code Execution": "Exec",
    "Security Rule Bypasses": "Bypass",
    "Suspicious Network Connections": "NetIO",
    "Global Environment Tampering": "EnvTamper",
    "Scrambled / Obfuscated Code": "Obfus",
    "Shadow Logic": "Shadow",
    "Sub-Atomic Decryption": "Bitwise",
    "Steganographic Execution": "Stego",
    "Unicode Smuggling": "Unicode",
    "Embedded Credentials & Keys": "Secrets",
    "entropy": "HighEntropy"
}

# Maps the low-level engine schema keys to our Short Terms
SCHEMA_TO_SHORT = {
    "sec_danger": "Exec",
    "sec_safety_neg": "Bypass",
    "sec_io": "NetIO",
    "sec_flux": "EnvTamper",
    "sec_heat_triggers": "Obfus",
    "sec_graveyard": "Shadow",
    "sec_bitwise_hits": "Bitwise",
    "sec_shadow_imports": "Stego",
    "sec_homoglyphs": "Unicode",
    "sec_private_info": "Secrets"
}

# The Kill-Chain Engine: Maps overlapping signals to real-world attack behaviors
THREAT_PROFILES = {
    "Data Exfiltration": lambda v, h: "Secrets" in v and "NetIO" in h,
    "Reverse Shell / RCE": lambda v, h: "Injection Surface" in v and "Exec" in h,
    "Obfuscated Dropper": lambda v, h: any(k in h for k in ["Obfus", "Stego", "Unicode"]) and "NetIO" in h and "Exec" in h,
    "Shadow Execution": lambda v, h: "Shadow" in h and "Exec" in h,
    "State Sabotage": lambda v, h: "Logic Bomb / Sabotage" in v and "EnvTamper" in h
}

def process_audit_file(audit_path):
    """
    Worker function to process a single audit file. 
    Designed to run in an isolated process across multiple CPU cores.
    """
    package_name = audit_path.name.replace("_galaxy_audit.json", "")
    
    try:
        with open(audit_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return None

    # Load the sister telemetry file to evaluate per-file Kill-Chains
    galaxy_path = audit_path.parent / f"{package_name}_galaxy.json"
    stars_lookup = {}
    hit_schema = []
    
    if galaxy_path.exists():
        try:
            with open(galaxy_path, 'r', encoding='utf-8') as gf:
                galaxy_data = json.load(gf)
                stars_lookup = {s.get("path"): s for s in galaxy_data.get("galaxy", {}).get("stars", [])}
                if not stars_lookup: # Handle columnar format fallback
                    paths = galaxy_data.get("galaxy", {}).get("paths", [])
                    hits = galaxy_data.get("galaxy", {}).get("hits_flat", [])
                    hit_schema = galaxy_data.get("meta", {}).get("schemas", {}).get("hit_vector", [])
                    schema_len = len(hit_schema)
                    
                    if paths and hits and schema_len > 0:
                        for i, p in enumerate(paths):
                            start_idx = i * schema_len
                            end_idx = start_idx + schema_len
                            stars_lookup[p] = {
                                "hit_vector": hits[start_idx:end_idx],
                                "telemetry": {"ownership": "Mapped via Columnar", "threat_snippets": {}}
                            }
                
                # If standard format
                if not hit_schema:
                    hit_schema = galaxy_data.get("meta", {}).get("schemas", {}).get("hit_vector", [])
        except Exception:
            pass

    total_files = data.get("2. Global Synthesis Summary", {}).get("summary", {}).get("total_files", 1)
    security_audit = data.get("3. Forensic Security & Vulnerability Audit", {})
    status = security_audit.get("Audit Status", "")

    result = {
        "tier": None,
        "total_files": total_files,
        "infected_files": 0,
        "vectors": [],
        "authors": [],
        "snippets": [],
        "pkg_data": None
    }

    if status in ["CRITICAL_THREATS_DETECTED", "ELEVATED_SURFACE_RISK"]:
        breaches = security_audit.get("Vulnerability Exposures (Threshold Breaches)", {})
        file_threat_map = defaultdict(set)
        local_vectors = set()
        pkg_authors = set()
        pkg_snippets = set()
        is_flashpoint = False
        
        # Track confirmed Kill-Chains for this package (NOW A COUNTER)
        pkg_detected_profiles = Counter()

        # 1. Map High-Level Vulnerabilities to specific files
        for vector_name, details in breaches.items():
            if details.get("Artifacts Flagged", 0) > 0:
                short_name = vector_name.replace(" Risk Exposure", "").replace("Exposure", "").strip()
                local_vectors.add(short_name)
                for crit_file in details.get("Critical Files", []):
                    path = crit_file.get("Path")
                    if path: file_threat_map[path].add(short_name)
        
        secrets = security_audit.get("Exposed Secrets & Credentials (Quarantined Files)", [])
        has_secrets = False
        if secrets:
            has_secrets = True
            local_vectors.add("Secrets")
            for secret in secrets:
                path = secret.get("Path")
                if path: file_threat_map[path].add("Secrets")

        infected_files_count = len(file_threat_map)
        
        # 2. Extract author telemetry and evaluate PER-FILE Kill-Chains
        for file_path, file_vectors in file_threat_map.items():
            star = stars_lookup.get(file_path, {})
            tel = star.get("telemetry", {})
            
            author = tel.get("ownership", "Unknown Architect")
            if author and author != "Unknown Architect" and author != "Mapped via Columnar":
                pkg_authors.add(author)
            
            for vector_snippets in tel.get("threat_snippets", {}).values():
                for snippet in vector_snippets: pkg_snippets.add(snippet)

            # --> PER-FILE KILL-CHAIN EVALUATION <--
            file_hits = set()
            raw_hits = star.get("hit_vector", [])
            for i, val in enumerate(raw_hits):
                if val > 0 and i < len(hit_schema):
                    schema_key = hit_schema[i]
                    if schema_key in SCHEMA_TO_SHORT:
                        file_hits.add(SCHEMA_TO_SHORT[schema_key])

            # Check if this specific file completes a Kill-Chain
            for profile_name, logic_check in THREAT_PROFILES.items():
                if logic_check(file_vectors, file_hits):
                    pkg_detected_profiles[profile_name] += 1

            # Flashpoint check
            risk_vector = star.get("risk_vector", [])
            if len(risk_vector) > 10:
                if risk_vector[9] < 15.0 or risk_vector[10] > 80.0:
                    is_flashpoint = True

        if local_vectors:
            infection_pct = (infected_files_count / max(total_files, 1)) * 100.0

            # Global X-Ray Data for the table readout
            raw_data = security_audit.get("Raw Threat Signature Hits (Total Repository Occurrences)", {})
            active_raw_hits = []
            for hit_name, hit_count in raw_data.items():
                if hit_name == "_description" or not isinstance(hit_count, int) or hit_count <= 0: continue
                clean_name = hit_name.split('(')[0].strip()
                active_raw_hits.append(f"{SHORT_TERMS.get(clean_name, clean_name)}:{hit_count}")

            is_corroborated = len(pkg_detected_profiles) > 0
            
            has_file_level_trifecta = any(
                "Hidden Malware" in v and "Logic Bomb / Sabotage" in v and "Injection Surface" in v 
                for v in file_threat_map.values()
            )

            pkg_data = {
                "package": package_name,
                "vectors": ", ".join(sorted(local_vectors)),
                "infected_files": infected_files_count,
                "total_files": total_files,
                "infection_pct": infection_pct,
                "raw_hits": active_raw_hits,
                "authors": list(pkg_authors), 
                "snippets": list(pkg_snippets),
                "is_corroborated": is_corroborated,
                "detected_profiles": dict(pkg_detected_profiles), # Return dict with file counts
                "trifecta": has_file_level_trifecta,
                "is_flashpoint": is_flashpoint
            }
            
            # ==========================================
            # THE INVERSE DENSITY ROUTER
            # ==========================================
            is_machine_noise = (total_files > 50) and (infection_pct >= 40.0)

            if is_machine_noise:
                # Banish massive Webpack/Compilation bundles to Tier 3 unless they have a confirmed Kill-Chain
                result["tier"] = "critical" if is_corroborated else "noise"
            elif is_corroborated or has_file_level_trifecta or (is_flashpoint and infection_pct >= 10.0):
                result["tier"] = "critical"
            elif has_secrets or infection_pct >= 5.0:
                result["tier"] = "suspicious"
            else:
                result["tier"] = "noise"

            result["infected_files"] = infected_files_count
            result["vectors"] = list(local_vectors)
            result["authors"] = list(pkg_authors)
            result["snippets"] = list(pkg_snippets)
            result["pkg_data"] = pkg_data

    return result

def print_table(title, packages):
    width = 155
    print("\n" + "=" * width)
    print(f" {title} ({len(packages)} Packages)")
    print("=" * width)
    
    if not packages:
        print("  No packages in this tier.")
        return

    packages.sort(key=lambda x: (x["trifecta"], x["infection_pct"]), reverse=True)

    print(f"| {'PACKAGE NAME':<26} | {'% INFECTED':<17} | {'CORROBORATED':<12} | {'FLASHPOINT':<10} | {'TRIFECTA':<8} | {'THREAT VECTORS DETECTED':<60} |")
    print("-" * width)

    for pkg in packages:
        pkg_name = pkg["package"][:23] + "..." if len(pkg["package"]) > 26 else pkg["package"]
        vectors = pkg["vectors"][:57] + "..." if len(pkg["vectors"]) > 60 else pkg["vectors"]
        
        pct_str = f"{pkg['infection_pct']:.1f}% ({pkg['infected_files']}/{pkg['total_files']})"
        corroborated_str = "🎯 YES" if pkg.get('is_corroborated') else "   -"
        trifecta_str = "🔥 YES" if pkg.get('trifecta') else "   -"
        flashpoint_str = "⏱️ HOT" if pkg.get('is_flashpoint') else "   -"
        
        xray_str = ", ".join(pkg.get("raw_hits", [])) or "None (Threshold Match)"
        xray_str = xray_str[:136] + "..." if len(xray_str) > 139 else xray_str

        authors = pkg.get("authors", [])
        author_str = ", ".join(authors)[:136] + "..." if authors else "Unknown / Legacy Code"
        
        snippets = pkg.get("snippets", [])
        if snippets:
            snip_str = snippets[0][:130].replace("\n", " ") + "..."
        else:
            snip_str = "No readable snippets (Obfuscated/Minified Payload)"

        print(f"| {pkg_name:<26} | {pct_str:<17} | {corroborated_str:<12} | {flashpoint_str:<10} | {trifecta_str:<8} | {vectors:<60} |")
        print(f"|    ↳ X-RAY : {xray_str:<139} |")
        print(f"|    ↳ AUTHOR: {author_str:<139} |")
        print(f"|    ↳ SNIP  : {snip_str:<139} |")
        print("-" * width)

def print_executive_summary(total_scanned, total_files_in_ecosystem, total_infected_files, tier_critical, tier_suspicious, tier_noise, vector_counts, combo_pkg_counts, combo_file_counts, author_counts, snippet_counts):
    width = 155
    print("\n" + "=" * width)
    print(" 📊 EXECUTIVE THREAT INTELLIGENCE SUMMARY")
    print("=" * width)
    
    infection_rate = (total_infected_files / max(1, total_files_in_ecosystem)) * 100.0
    print(f"  [ TARGET ACQUISITION & BLAST RADIUS ]")
    print(f"  Total Packages Audited : {total_scanned:,}")
    print(f"  Total Files Scanned    : {total_files_in_ecosystem:,}")
    print(f"  Total Files Infected   : {total_infected_files:,} ({infection_rate:.2f}% of scanned ecosystem)")
    print()
    
    total_flagged = len(tier_critical) + len(tier_suspicious) + len(tier_noise)
    print(f"  [ TRIAGE DISTRIBUTION ({total_flagged} Packages Flagged) ]")
    if total_flagged > 0:
        pct_crit = (len(tier_critical) / total_flagged) * 100
        pct_susp = (len(tier_suspicious) / total_flagged) * 100
        pct_noise = (len(tier_noise) / total_flagged) * 100
        print(f"  🚨 Tier 1 (Critical)   : {len(tier_critical):<5} ({pct_crit:.1f}%) -> [Kill-Chains: RCE, Exfiltration, Droppers, Sabotage]")
        print(f"  ⚠️ Tier 2 (Suspicious) : {len(tier_suspicious):<5} ({pct_susp:.1f}%) -> [Exposed Secrets, API Leaks, Moderate Anomalies]")
        print(f"  📉 Tier 3 (Noise)      : {len(tier_noise):<5} ({pct_noise:.1f}%) -> [Uncorroborated Scattered Signals, Safe Bundles]")
    else:
        print("  No packages flagged.")
    print()
    
    print(f"  [ THREAT VECTOR EXPOSURE RATE ]")
    if vector_counts and total_flagged > 0:
        for v, count in sorted(vector_counts.items(), key=lambda x: x[1], reverse=True):
            pct_vector = (count / total_flagged) * 100
            print(f"  - {v:<30}: {count:<5} packages ({pct_vector:.1f}%)")
    else:
        print("  - No active threat vectors detected.")
    print()

    print(f"  [ TOXIC COCKTAILS (Confirmed Kill-Chains) ]")
    
    # Map the explanations for the UI (Real-World Threat Taxonomy)
    combo_explanations = {
        "Data Exfiltration": "(Stolen API Keys/Secrets + Network Socket)",
        "Reverse Shell / RCE": "(Unsafe I/O Injection + Dynamic Execution)",
        "Obfuscated Dropper": "(Glassworms, Homoglyphs, Steganography)",
        "Shadow Execution": "(Hidden Backdoors in Commented-out Graveyards)",
        "State Sabotage": "(Time-Delayed Logic Bombs + Environment Wipers)"
    }
    
    if combo_pkg_counts:
        for combo, pkg_count in sorted(combo_pkg_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            pct_combo = (pkg_count / max(1, total_flagged)) * 100
            file_count = combo_file_counts.get(combo, 0)
            
            # Attach the explanation to the name
            desc = combo_explanations.get(combo, "")
            display_name = f"{combo} {desc}"
            
            # Widened spacing to <65 to accommodate the detailed attack names perfectly
            print(f"  - {display_name:<65}: {pkg_count:<4} packages ({pct_combo:>4.1f}%) | {file_count} infected files")
    else:
        print("  - No structured attack profiles detected.")
    print()
    
    print(f"  [ HIGH-RISK ARCHITECTS (Ranked by Infected File Count) ]")
    if author_counts:
        for a, count in sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  - {a:<40}: {count} infected files")
    else:
        print("  - No author data available.")
    print()

    print(f"  [ MOST RECURRING THREAT SNIPPETS ]")
    if snippet_counts:
        for snip, count in sorted(snippet_counts.items(), key=lambda x: x[1], reverse=True)[:3]:
            clean_snip = snip.replace("\n", " ").strip()
            clean_snip = clean_snip[:110] + "..." if len(clean_snip) > 110 else clean_snip
            print(f"  - ({count}x) {clean_snip}")
    else:
        print("  - No readable threat snippets extracted.")
        
    print("=" * width + "\n")

def generate_triage_threat_report(scan_dir):
    scan_path = Path(scan_dir)
    if not scan_path.exists():
        print(f"Directory {scan_dir} not found.")
        return

    audit_files = list(scan_path.rglob("*_galaxy_audit.json"))
    if not audit_files:
        print(f"No audit files found in {scan_dir}.")
        return

    total_scanned = len(audit_files)
    total_files_in_ecosystem = 0
    total_infected_files = 0
    
    global_vector_counts = Counter()
    global_combo_pkg_counts = Counter()
    global_combo_file_counts = Counter()
    global_author_counts = Counter()
    global_snippet_counts = Counter()
    
    tier_critical, tier_suspicious, tier_noise = [], [], []

    print(f"🚀 Igniting Multiprocess Scanner across {os.cpu_count() or 4} cores for {total_scanned:,} packages...")

    with concurrent.futures.ProcessPoolExecutor() as executor:
        results = executor.map(process_audit_file, audit_files)
        
        for res in results:
            if not res:
                continue
                
            total_files_in_ecosystem += res["total_files"]
            total_infected_files += res["infected_files"]
            
            for vector in res["vectors"]:
                global_vector_counts[vector] += 1
                
            if res.get("pkg_data"):  
                for profile, file_count in res["pkg_data"].get("detected_profiles", {}).items():
                    global_combo_pkg_counts[profile] += 1
                    global_combo_file_counts[profile] += file_count
                
            for author in res["authors"]:
                global_author_counts[author] += res["infected_files"]
                
            for snippet in res["snippets"]:
                global_snippet_counts[snippet] += 1
                
            tier = res["tier"]
            if tier == "critical":
                tier_critical.append(res["pkg_data"])
            elif tier == "suspicious":
                tier_suspicious.append(res["pkg_data"])
            elif tier == "noise":
                tier_noise.append(res["pkg_data"])

    print("\n" + "*" * 155)
    print(" 📡 GITGALAXY THREAT INTELLIGENCE TRIAGE")
    print("*" * 155)
    print_table("🚨 TIER 1: CRITICAL THREATS (Kill-Chains: RCE, Exfiltration, Obfuscated Droppers, State Sabotage)", tier_critical)
    print_table("⚠️ TIER 2: SUSPICIOUS ANOMALIES (API Leaks, Hardcoded Secrets, Moderate Density)", tier_suspicious)
    print_table("📉 TIER 3: LIKELY NOISE (Uncorroborated Scattered Signals in Massive Architectures)", tier_noise)

    print_executive_summary(
        total_scanned=total_scanned,
        total_files_in_ecosystem=total_files_in_ecosystem,
        total_infected_files=total_infected_files,
        tier_critical=tier_critical,
        tier_suspicious=tier_suspicious,
        tier_noise=tier_noise,
        vector_counts=global_vector_counts,
        combo_pkg_counts=global_combo_pkg_counts,
        combo_file_counts=global_combo_file_counts,
        author_counts=global_author_counts,
        snippet_counts=global_snippet_counts
    )

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GitGalaxy Threat Intelligence Generator")
    parser.add_argument(
        "target_dir", 
        nargs="?", 
        default="/srv/storage_16tb/projects/gitgalaxy/v6/updated_results", 
        help="Directory containing _galaxy_audit.json files"
    )
    
    args = parser.parse_args()
    generate_triage_threat_report(args.target_dir)