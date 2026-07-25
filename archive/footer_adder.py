#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# The indestructible markdown footer with proper line breaks and emojis
NEW_FOOTER = """

<br><br>

---

### 🌌 Powered by the blAST Engine

This documentation is part of the [GitGalaxy Ecosystem](https://github.com/squid-protocol/gitgalaxy), an AST-free, LLM-free heuristic knowledge graph engine.

* 🪐 **[Explore the GitHub Repository](https://github.com/squid-protocol/gitgalaxy)** for code, tools, and updates.
* 🔭 **[Visualize your own repository at GitGalaxy.io](https://gitgalaxy.io/)** using our interactive 3D WebGPU dashboard.

"""

# Updated signature: NO emoji, matching exactly what is currently broken in the files
SIGNATURE = "### Powered by the blAST Engine"

def fix_footers(target_dir: str):
    target_path = Path(target_dir).resolve()
    
    if not target_path.exists() or not target_path.is_dir():
        print(f"❌ Error: Directory '{target_path}' does not exist.")
        return

    print(f"🚀 Launching Surgical Repair in: {target_path}")
    
    fixed_count = 0
    skipped_count = 0

    for md_file in target_path.glob("*.md"):
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Find where the busted footer starts
            idx = content.rfind(SIGNATURE)

            if idx != -1:
                # We found the signature. Let's backtrack to find the '---' line just above it
                dash_idx = content.rfind("---", 0, idx)
                
                # If we found the dashes right above our signature, cut from there
                if dash_idx != -1 and (idx - dash_idx) < 100:
                    clean_content = content[:dash_idx].strip()
                else:
                    # Otherwise, just cut from the signature itself
                    clean_content = content[:idx].strip()
                
                # Append the new, highly-formatted footer
                new_content = clean_content + NEW_FOOTER
                
                with open(md_file, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                    
                print(f"🔧 [REPAIRED] Fixed formatting on: {md_file.name}")
                fixed_count += 1
            else:
                print(f"⏭️  [SKIPPED] No footer found to fix in: {md_file.name}")
                skipped_count += 1
                
        except Exception as e:
            print(f"❌ [ERROR] Failed to process {md_file.name}: {e}")

    print("\n" + "="*50)
    print(" REPAIR COMPLETE")
    print("="*50)
    print(f" Files Fixed: {fixed_count}")
    print(f" Files Skipped: {skipped_count}")
    print("="*50 + "\n")

if __name__ == "__main__":
    # Absolute path to your wiki directory
    DEFAULT_PATH = "/srv/storage_16tb/projects/gitgalaxy/v6/docs/wiki"
    
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH
    fix_footers(target)