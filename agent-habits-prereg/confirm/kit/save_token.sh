#!/bin/bash
# Save the Claude Code long-lived token (from `claude setup-token`) for the agent-habits container runs.
# Reads silently until an empty line, tolerates bracketed-paste markers and a key wrapped over several lines,
# and saves the sk-ant-... key found in what was pasted. The key is never printed.
set -u
F="$HOME/gitgalaxy/chess-study/confirm/secrets/claude_token"
mkdir -p "$(dirname "$F")" && chmod 700 "$(dirname "$F")"
echo "Paste the key (it starts with sk-ant; nothing will show), then press Enter TWICE:"
ALL=""
while IFS= read -rs LINE; do
  [ -z "$LINE" ] && break
  ALL="$ALL$LINE"
done
echo
KEY="$(printf %s "$ALL" | python3 -c '
import re, sys
s = sys.stdin.read()
s = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", s)   # bracketed-paste and other escape sequences
s = re.sub(r"\s+", "", s)
m = re.search(r"sk-ant-[A-Za-z0-9_\-]{20,}", s)
print(m.group(0) if m else "")
')"
unset ALL LINE
if [ -z "$KEY" ]; then
  echo "No sk-ant key found in what was pasted: nothing saved."
  exit 1
fi
( umask 077; printf %s "$KEY" > "$F" )
echo "Saved: a key of $(printf %s "$KEY" | wc -c) characters, starting sk-ant."
unset KEY
