#!/bin/bash
# D11 + D12: queue the second rounds behind the running lanes.
#   cores 3-5: after the Codex lane, sonnet-b (12) then haiku-b (12)   (D12: haiku-b moved here from cores 0-2)
#   cores 0-2: Haiku round 1 continues on its own lane; nothing queued behind it.
cd "$(dirname "$0")" || exit 9
while pgrep -f "^bash batch_n.sh 0 7$" >/dev/null || pgrep -f "^bash batch_n.sh 0 4$" >/dev/null; do sleep 30; done
AH_CPUSET=3-5 bash lane_agent.sh sonnet-b 12 > ../lane_sonnet_b.log 2>&1
AH_CPUSET=3-5 bash lane_agent.sh haiku-b 12 > ../lane_haiku_b.log 2>&1
echo "== $(date -u +%FT%TZ) second rounds done"
