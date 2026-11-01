"""Which COBOL EXIT forms each side of the 5 COBOL pairs uses (code only, via keyword_diff.code_only)."""
import collections
import re

import keyword_diff as K
import pooled

RX = re.compile(r"(?<![\w-])EXIT(?:\s+(PARAGRAPH|PERFORM(?:\s+CYCLE)?|PROGRAM|SECTION|FUNCTION|METHOD))?(?![\w-])", re.I)
for fam, pair in pooled.PAIRS.items():
    if fam in K.LANG:
        continue
    for agent, repo in zip(("CC", "Codex"), pair):
        c = collections.Counter()
        for p in K.find_repo(repo).rglob("*"):
            if p.is_file() and p.suffix.lower() in K.EXT["cobol"]:
                t = K.code_only(p.read_text(encoding="utf-8", errors="ignore"), "cobol")
                for m in RX.finditer(t):
                    c[(m.group(1) or "bare").upper().split()[0]] += 1
        print(f"{fam:22}{agent:6}", dict(c))
