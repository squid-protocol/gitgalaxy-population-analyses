#!/bin/bash
# D13: a second haiku-b lane on cores 0-2, started when Haiku round 1's lane finishes. Runs `--next --agent haiku-b`
# until none is left. Two haiku-b lanes can race for the same next run only at the same instant; the loser fails before
# any agent starts (the run directory is created atomically), so on a failure this lane waits and retries.
cd "$(dirname "$0")" || exit 9
while pgrep -f "^bash lane_agent.sh haiku 12$" >/dev/null; do sleep 30; done
echo "== $(date -u +%FT%TZ) Haiku round 1 lane finished; second haiku-b lane starting on cores 0-2"
sleep 7   # stagger against the other lane's selection
fails=0
while true; do
  out=$(AH_CPUSET=0-2 python3 run.py --next --agent haiku-b 2>&1)
  if echo "$out" | grep -q '"run_id"'; then
    fails=0
    echo "$out" | grep -E '"(run_id|active_s|sessions|nudges|cap_hit|final_check|note)"'
  elif echo "$out" | grep -q "all runs started"; then
    break
  else
    fails=$((fails+1)); echo "selection failed ($fails): $(echo "$out" | tail -1)"
    [ $fails -ge 3 ] && break
    sleep 13
  fi
done
echo "== $(date -u +%FT%TZ) done: haiku-b lane 2"
