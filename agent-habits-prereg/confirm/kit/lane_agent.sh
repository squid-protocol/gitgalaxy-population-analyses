#!/bin/bash
# One pinned lane for any agent (D8/D9): N runs of AGENT, one at a time, in that agent's order.
#   AH_CPUSET=0-2 setsid nohup bash lane_agent.sh haiku 12 > ../lane_haiku.log 2>&1 < /dev/null &
AGENT=${1:?agent}; N=${2:?runs}
cd "$(dirname "$0")" || exit 9
for i in $(seq 1 "$N"); do
  echo "== $(date -u +%FT%TZ) next $AGENT ($i of $N)"
  out=$(python3 run.py --next --agent "$AGENT" 2>&1)
  echo "$out" | grep -E '"(run_id|active_s|sessions|nudges|limit_interruptions|cap_hit|final_check|note)"'
  echo "$out" | grep -q '"run_id"' || { echo "no run for $AGENT: $(echo "$out" | tail -2)"; break; }
done
echo "== $(date -u +%FT%TZ) done: $AGENT"
