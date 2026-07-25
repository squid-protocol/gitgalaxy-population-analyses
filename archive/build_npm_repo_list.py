import os
import requests
from pathlib import Path

# The path to your recovered PyPI Timeshift backup
BACKUP_DIR = Path("/run/timeshift/167461/backup/timeshift/snapshots/2026-04-05_21-00-01/localhost/srv/storage_16tb/projects/gitgalaxy/data/pypi_top_200")

# Where we want to save the final list of clone URLs
OUTPUT_FILE = Path("/srv/storage_16tb/projects/gitgalaxy/data/pypi_repo_list.txt")

def clean_github_url(raw_url):
    """Extracts the clean, base GitHub repo URL from messy metadata links."""
    if not raw_url or "github.com" not in raw_url:
        return None
        
    url = raw_url.replace("git+", "").replace("git://", "https://")
    
    # Strip down to just https://github.com/org/repo
    parts = url.split('/')
    try:
        gh_index = parts.index("github.com")
        # Grab exactly the org and the repo name
        base_url = f"https://github.com/{parts[gh_index+1]}/{parts[gh_index+2]}"
        
        # Strip out trailing .git, hashes, or query parameters
        base_url = base_url.split('#')[0].split('?')[0]
        if base_url.endswith('.git'):
            base_url = base_url[:-4]
            
        return base_url
    except (ValueError, IndexError):
        return None

def get_pypi_github_url(pkg_name):
    """Pings the PyPI API and hunts for the source code URL."""
    api_url = f"https://pypi.org/pypi/{pkg_name}/json"
    
    try:
        resp = requests.get(api_url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            info = data.get("info", {})
            
            # Place 1: The 'project_urls' dictionary (Modern standard)
            project_urls = info.get("project_urls") or {}
            
            # Check common keys developers use
            for key in ["Source", "Source Code", "Repository", "Homepage", "Tracker", "Bug Tracker"]:
                url = project_urls.get(key)
                clean = clean_github_url(url)
                if clean: return clean

            # Place 2: The legacy 'home_page' field
            home_page = info.get("home_page")
            clean = clean_github_url(home_page)
            if clean: return clean
            
    except Exception as e:
        print(f"Error fetching {pkg_name}: {e}")
        
    return None

def main():
    if not BACKUP_DIR.exists():
        print(f"❌ Backup directory not found: {BACKUP_DIR}")
        return

    folders = [f.name for f in BACKUP_DIR.iterdir() if f.is_dir() and not f.name.startswith('_')]
    print(f"🔍 Found {len(folders)} packages in the Timeshift backup. Pinging PyPI registry...")

    valid_urls = set() # Use a set to prevent duplicates if links overlap
    
    for idx, folder in enumerate(folders, 1):
        print(f"[{idx}/{len(folders)}] Resolving {folder}...")
        repo_url = get_pypi_github_url(folder)
        
        if repo_url:
            valid_urls.add(repo_url)
        else:
            print(f"  ⚠️ No GitHub URL found in PyPI metadata for {folder}")

    # Write the results
    with open(OUTPUT_FILE, 'w') as f:
        for url in sorted(valid_urls):
            f.write(f"{url}\n")
            
    print(f"\n✅ Successfully resolved {len(valid_urls)}/{len(folders)} GitHub URLs.")
    print(f"📄 Saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()