#!/bin/bash
# Run the agent-habits confirmation runs one at a time, in the fixed order, until all have started.
# Resumable: run.py --next skips every run whose directory exists. Launch detached:
#   setsid nohup bash batch.sh >> ../batch.log 2>&1 < /dev/null &
cd "$(dirname "$0")" || exit 9
while true; do
  echo "== $(date -u +%FT%TZ) next"
  out=$(python3 run.py --next 2>&1)
  echo "$out" | tail -25
  echo "$out" | grep -q "all runs started" && break
  echo "$out" | grep -q '"run_id"' || { echo "run.py did not report a run; stopping"; break; }
done
echo "== $(date -u +%FT%TZ) batch done"
