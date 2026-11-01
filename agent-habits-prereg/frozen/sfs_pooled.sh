#!/bin/bash
# sfs compare over a pooled cohort: the 31 chess scans (engine main 433228fe1) + the 8 non-chess agentic-COBOL
# scans (engine #7170 branch, ~/gitgalaxy/cobol-agents/scans-7170). Structure lens (twins on) and portable lens.
set -u
BASE=/home/joe/gitgalaxy/chess-study
SFS=/home/joe/nyx_projects/gitgalaxy-population-analyses/.claude/worktrees/agentic-cobol/structural-fingerprint-scanner
export PYTHONPATH="$SFS/src"
PY=/home/joe/gitgalaxy/sfs-venv/bin/python
COHORT=$BASE/sfs-cohort
rm -rf "$COHORT"; mkdir -p "$COHORT"
for d in "$BASE"/scans/*/; do ln -s "$d" "$COHORT/$(basename "$d")"; done
for d in /home/joe/gitgalaxy/cobol-agents/scans-7170/agentic-cobol-*/; do ln -s "$d" "$COHORT/$(basename "$d")"; done
ls "$COHORT" | wc -l
cd "$SFS" || exit 9
nice $PY -m structural_fingerprint.cli compare "$COHORT" -o "$BASE/sfs-structure" --workers 3 > "$BASE/sfs-structure.log" 2>&1
echo "structure rc=$?"
nice $PY -m structural_fingerprint.cli compare "$COHORT" -o "$BASE/sfs-portable" --lens portable --no-twins \
  > "$BASE/sfs-portable.log" 2>&1
echo "portable rc=$?"
