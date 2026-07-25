import os
import shutil
import tarfile
import requests
from pathlib import Path

# The npm registry search API (returns highly popular packages by default)
# We use 'text=node' because standalone qualifiers like 'not:unstable' now return empty lists. 
NPM_SEARCH_URL = "https://registry.npmjs.org/-/v1/search?text=node&size=200"
TARGET_COUNT = 200
BASE_DIR = Path("/srv/storage_16tb/projects/gitgalaxy/data/npm_top_200")
ARCHIVE_DIR = BASE_DIR / "_archives"

def setup_directories():
    """Ensures the target directories exist."""
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

def get_top_packages():
    """Fetches the top 200 packages from the npm registry API."""
    print("📡 Fetching the Top 200 npm packages telemetry...")
    response = requests.get(NPM_SEARCH_URL)
    response.raise_for_status()
    data = response.json()
    
    # Extract just the package names
    packages = [obj["package"]["name"] for obj in data.get("objects", [])[:TARGET_COUNT]]
    return packages

def extract_archive(archive_path, extract_to):
    """Safely unpacks the downloaded tarball."""
    try:
        with tarfile.open(archive_path, 'r:*') as tar:
            tar.extractall(path=extract_to)
        return True
    except Exception as e:
        print(f"  ⚠️ Failed to extract {archive_path.name}: {e}")
        return False

def harvest_package(pkg_name, index):
    """Downloads and extracts a single package without executing ANY of its code."""
    print(f"\n[{index}/{TARGET_COUNT}] 📦 Harvesting: {pkg_name}")
    
    # Safely handle scoped packages (e.g. @types/node -> @types_node)
    safe_pkg_name = pkg_name.replace("/", "_")
    pkg_dir = BASE_DIR / safe_pkg_name
    
    if pkg_dir.exists():
        print(f"  -> Already exists. Skipping.")
        return

    try:
        # 1. Query npm API for the package metadata. 
        # Slashes must be URL-encoded for scoped packages.
        encoded_pkg_name = pkg_name.replace("/", "%2F")
        api_url = f"https://registry.npmjs.org/{encoded_pkg_name}"
        resp = requests.get(api_url)
        
        if resp.status_code != 200:
            print(f"  ❌ npm registry returned {resp.status_code}. Skipping.")
            return
            
        data = resp.json()
        latest_version = data.get("dist-tags", {}).get("latest")
        
        if not latest_version or latest_version not in data.get("versions", {}):
            print(f"  ❌ Could not determine latest version for {pkg_name}.")
            return
            
        # 2. Find the Tarball URL
        version_data = data["versions"][latest_version]
        tarball_url = version_data.get("dist", {}).get("tarball")
                
        if not tarball_url:
            print(f"  ❌ No tarball available for {pkg_name}.")
            return
            
        # 3. Download the raw file directly
        filename = tarball_url.split("/")[-1]
        archive_path = ARCHIVE_DIR / filename
        
        with requests.get(tarball_url, stream=True) as r:
            r.raise_for_status()
            with open(archive_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
        # 4. Extract to the final directory
        pkg_dir.mkdir(parents=True, exist_ok=True)
        if extract_archive(archive_path, pkg_dir):
            print(f"  ✅ Successfully secured {pkg_name}/")
            
        # 5. Clean up the archive immediately to save disk space
        archive_path.unlink()

    except Exception as e:
        print(f"  ❌ Failed to harvest {pkg_name}. Error: {e}")

def main():
    print("🚀 Initiating npm Baseline Harvester (API Bypass Mode)...")
    setup_directories()
    
    try:
        packages = get_top_packages()
        if not packages:
            print("❌ No packages returned from npm API.")
            return
    except Exception as e:
        print(f"❌ Failed to fetch package list: {e}")
        return

    for idx, pkg in enumerate(packages, 1):
        harvest_package(pkg, idx)
        
    print("\n🧹 Sweeping up temporary archive directory...")
    shutil.rmtree(ARCHIVE_DIR, ignore_errors=True)
    print(f"\n🏁 HARVEST COMPLETE. Your baseline is ready at: {BASE_DIR}")

if __name__ == "__main__":
    main()