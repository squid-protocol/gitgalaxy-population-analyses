#!/bin/bash
# sfs over the 60 confirmation scans (engine 7d2e1f627): structure lens (twins on) and portable lens.
# D16: sat-c-codex-r1 uses its rescan (scans/confirm-d16); the 3 runs still blocked (no program in the scan) are left out.
set -u
C=/home/joe/gitgalaxy/chess-study/confirm
SFS=/home/joe/nyx_projects/gitgalaxy-population-analyses/.claude/worktrees/agentic-cobol/structural-fingerprint-scanner
export PYTHONPATH="$SFS/src"
PY=/home/joe/gitgalaxy/sfs-venv/bin/python
COHORT=$C/sfs/cohort
rm -rf "$COHORT"; mkdir -p "$COHORT"
for d in $C/scans/confirm/*/; do
  r=$(basename "$d")
  case $r in chess-c-codex-r1|chess-rust-codex-r1|chess-rust-codex-r2) continue ;; esac
  if [ "$r" = sat-c-codex-r1 ]; then ln -s "$C/scans/confirm-d16/$r" "$COHORT/$r"; else ln -s "$d" "$COHORT/$r"; fi
done
ls "$COHORT" | wc -l
cd "$SFS" || exit 9
nice $PY -m structural_fingerprint.cli compare "$COHORT" -o "$C/sfs/structure" --workers 3 > "$C/sfs/structure.log" 2>&1
echo "structure rc=$?"
nice $PY -m structural_fingerprint.cli compare "$COHORT" -o "$C/sfs/portable" --lens portable --no-twins > "$C/sfs/portable.log" 2>&1
echo "portable rc=$?"
