#!/bin/bash
# Run N_CLAUDE Claude runs and N_CODEX Codex runs, one at a time, alternating (each agent in its frozen order),
# then stop. After each Codex run, log the free plan's used_percent; skip further Codex runs past CODEX_STOP_PCT.
#   setsid nohup bash batch_n.sh 5 4 > ../batch_n.log 2>&1 < /dev/null &
N_CLAUDE=${1:?claude runs}; N_CODEX=${2:?codex runs}; CODEX_STOP_PCT=${3:-60}
cd "$(dirname "$0")" || exit 9
RUNS=../runs
codex_pct() {  # the newest used_percent any run's Codex session recorded
  find "$RUNS" -path '*codex*' -name '*.jsonl' -newermt '-2 hours' -print0 2>/dev/null | xargs -0 -r grep -ohE '"used_percent":[0-9.]+' \
    | tail -1 | cut -d: -f2
}
c=0; x=0; codex_ok=1
while [ $c -lt "$N_CLAUDE" ] || { [ $x -lt "$N_CODEX" ] && [ $codex_ok = 1 ]; }; do
  for agent in claude codex; do
    if [ $agent = claude ] && [ $c -ge "$N_CLAUDE" ]; then continue; fi
    if [ $agent = codex ] && { [ $x -ge "$N_CODEX" ] || [ $codex_ok = 0 ]; }; then continue; fi
    echo "== $(date -u +%FT%TZ) next $agent"
    out=$(python3 run.py --next --agent $agent 2>&1)
    echo "$out" | grep -E '"(run_id|active_s|sessions|nudges|limit_interruptions|cap_hit|final_check|note)"'
    echo "$out" | grep -q '"run_id"' || { echo "no run for $agent: $(echo "$out" | tail -2)"; [ $agent = codex ] && codex_ok=0 || c=$N_CLAUDE; continue; }
    if [ $agent = claude ]; then c=$((c+1)); else
      x=$((x+1)); p=$(codex_pct); echo "codex free plan used_percent: ${p:-unknown}"
      if [ -n "$p" ] && awk "BEGIN{exit !($p >= $CODEX_STOP_PCT)}"; then echo "codex usage >= ${CODEX_STOP_PCT}%: no more Codex runs"; codex_ok=0; fi
    fi
  done
done
echo "== $(date -u +%FT%TZ) done: $c claude, $x codex"
