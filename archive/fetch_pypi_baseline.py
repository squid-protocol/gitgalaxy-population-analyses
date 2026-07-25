import os
import json
import shutil
import tarfile
import zipfile
import requests
from pathlib import Path

# The official telemetry feed for PyPI downloads (30 days)
TOP_PYPI_URL = "https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.json"
TARGET_COUNT = 200
BASE_DIR = Path("/srv/storage_16tb/projects/gitgalaxy/data/pypi_top_200")
ARCHIVE_DIR = BASE_DIR / "_archives"

def setup_directories():
    """Ensures the target directories exist."""
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

def get_top_packages():
    """Fetches the top 200 packages from PyPI."""
    print("📡 Fetching the Top 200 PyPI packages telemetry...")
    response = requests.get(TOP_PYPI_URL)
    response.raise_for_status()
    data = response.json()
    
    # Extract just the package names
    packages = [row["project"] for row in data["rows"][:TARGET_COUNT]]
    return packages

def extract_archive(archive_path, extract_to):
    """Safely unpacks the downloaded tarball or wheel."""
    try:
        if str(archive_path).endswith(('.tar.gz', '.tgz', '.tar')):
            with tarfile.open(archive_path, 'r:*') as tar:
                tar.extractall(path=extract_to)
        elif str(archive_path).endswith(('.zip', '.whl')):
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
        return True
    except Exception as e:
        print(f"  ⚠️ Failed to extract {archive_path.name}: {e}")
        return False

def harvest_package(pkg_name, index):
    """Downloads and extracts a single package without executing ANY of its code."""
    print(f"\n[{index}/{TARGET_COUNT}] 📦 Harvesting: {pkg_name}")
    
    pkg_dir = BASE_DIR / pkg_name
    if pkg_dir.exists():
        print(f"  -> Already exists. Skipping.")
        return

    try:
        # 1. Query PyPI API for the package metadata
        api_url = f"https://pypi.org/pypi/{pkg_name}/json"
        resp = requests.get(api_url)
        if resp.status_code != 200:
            print(f"  ❌ PyPI API returned {resp.status_code}. Skipping.")
            return
            
        data = resp.json()
        version = data.get("info", {}).get("version")
        
        if not version or version not in data.get("releases", {}):
            print(f"  ❌ Could not determine latest version for {pkg_name}.")
            return
            
        # 2. Find the Source Distribution (sdist) URL
        sdist_url = None
        filename = None
        for release in data["releases"][version]:
            if release["packagetype"] == "sdist":
                sdist_url = release["url"]
                filename = release["filename"]
                break
                
        if not sdist_url:
            print(f"  ❌ No source distribution (.tar.gz/.zip) available for {pkg_name}.")
            return
            
        # 3. Download the raw file directly
        archive_path = ARCHIVE_DIR / filename
        with requests.get(sdist_url, stream=True) as r:
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
    print("🚀 Initiating PyPI Baseline Harvester (API Bypass Mode)...")
    setup_directories()
    
    try:
        packages = get_top_packages()
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