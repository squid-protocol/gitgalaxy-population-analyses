#!/bin/bash
# Fetch each system in pins.csv at its pinned commit and scan it with a GitGalaxy checkout.
#
#   ENGINE=/path/to/gitgalaxy WORK=/path/to/work ./fetch_scan.sh
#
# ENGINE must carry GitGalaxy #7170 (main line as a function) and #7169 (PIC run lengths). Each scan runs under
# a 3 GB address-space cap, so an engine without #7169 fails fast instead of exhausting memory. Repos and scans
# stay local: the study publishes measurements and paragraph names only.
set -u
: "${ENGINE:?set ENGINE to a gitgalaxy checkout}" "${WORK:?set WORK to a scratch directory}"
PY=${PY:-python3}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$WORK/repos" "$WORK/scans"
tail -n +2 "$HERE/pins.csv" | while IFS=, read -r repo sha lic; do
  [ "$lic" = "MIT" ] || { echo "skip $repo: licence $lic"; continue; }
  dest="$WORK/repos/$repo"
  if [ ! -d "$dest" ]; then
    mkdir -p "$dest"
    gh api "repos/acherm/$repo/tarball/$sha" | tar -xz -C "$dest" --strip-components=1
  fi
  out="$WORK/scans/$repo"; rm -rf "$out"; mkdir -p "$out"
  ( cd "$out" && ulimit -v 3000000 && PYTHONPATH="$ENGINE" GITGALAXY_LICENSE_KEY=COMMUNITY_FREE_TIER \
      "$PY" -m gitgalaxy.galaxyscope "$dest" --output "$out/" > scan.log 2>&1 )
  echo "scanned $repo rc=$?"
done
