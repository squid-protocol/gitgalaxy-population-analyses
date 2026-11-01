# Agent habits: pre-registration

A pre-registration for a confirmatory study of how two coding agents (Claude Code and Codex) write code, measured
structurally with GitGalaxy. It is committed **before** any confirmation data exists, so this commit's timestamp
is the registration time.

* `PREREGISTRATION.md`: what was looked at (the exploratory set), the hypotheses (5 primary, Holm-corrected;
  6 secondary; 2 on run-to-run variance), the decision rules, the confirmation design (40 fresh repos), exclusions,
  the engine pin, and the sha256 of every frozen analysis script.
* `frozen/`: those scripts, exactly as hashed. Check them with
  `cd frozen && grep -E '^[0-9a-f]{64}  ' ../PREREGISTRATION.md | sha256sum -c`.

The scripts read local scans and checkouts by absolute path; they are here to fix the measurement code, not to run
from this directory. Measurements, counts, keyword and technique names only: no source text from the measured
repositories is published.
