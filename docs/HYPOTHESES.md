# The hypothesis register

The register of record for confirmatory claims in this repo (rules: [`../CONTRIBUTING.md`](../CONTRIBUTING.md)).
Same protocol as the [temporal crucible's register](https://github.com/squid-protocol/temporal-crucible/blob/main/docs/HYPOTHESES.md).

## The protocol

1. **Hypothesis first.** A confirmatory claim is registered here, and in the study's own
   pre-registration, with its direction, its test and its α **before** the analysis that could
   confirm it runs. The registration text is quoted verbatim in the report that evaluates it.
2. **Verdicts are published either way.** A dead hypothesis stays in this register forever with its
   autopsy.
3. **Exploratory is labelled exploratory.** An exploratory observation may *become* a hypothesis,
   registered for **data it has not seen**, never re-tested on the data that suggested it.
4. **Every test carries its guards** (`CONTRIBUTING.md` section 4).

Legend: ✓ supported · ✗ refuted · ⚠ inconclusive · ○ registered, not yet evaluated.

## Register

### AH: agent habits, Claude Code vs Codex (registered 2026-11-01)

Pre-registration: [`agent-habits-prereg/PREREGISTRATION.md`](../agent-habits-prereg/PREREGISTRATION.md),
commit `5700b9e` (2026-11-01T12:41Z), PR #24. Exploratory set: 10 same-task, same-language pairs from
acherm/agentic-* (chess engine in C, C++, Java, Python, Rust, COBOL; four COBOL tasks). Confirmation set:
40 fresh repos (2 tasks × 5 languages × 2 agents × 2 repeats), not yet generated. The ids below are the
note's (H1 there = AH-H1 here).

| id | hypothesis (registered direction) | test / α | registered | verdict | evidence |
|---|---|---|---|---|---|
| AH-H1 | Claude Code writes more comments (doc/code lines) | one-sided sign test over cells, Holm across AH-H1..H5, FWER 0.05 | 2026-11-01 | ○ | — |
| AH-H2 | Claude Code documents more functions (share with a comment block directly above) | same | 2026-11-01 | ○ | — |
| AH-H3 | Codex exits early more (COBOL `EXIT PARAGRAPH/PERFORM`; elsewhere `return`, per 1,000 keyword tokens) | same | 2026-11-01 | ○ | — |
| AH-H4 | Codex adds Python helper code to non-Python projects | one-sided sign test on discordant cells, Holm | 2026-11-01 | ○ | — |
| AH-H5 | Claude Code uses `while` more (non-COBOL cells, per 1,000 keyword tokens) | one-sided sign test, Holm | 2026-11-01 | ○ | — |
| AH-S1 | Non-COBOL: Claude Code has higher mean fan-out | one-sided sign test, uncorrected (secondary) | 2026-11-01 | ○ | — |
| AH-S2 | Non-COBOL: Codex has higher median function complexity | same | 2026-11-01 | ○ | — |
| AH-S3 | COBOL: AH-S1 and AH-S2 do not hold (reversed or tied in at least half the COBOL cells) | count of cells | 2026-11-01 | ○ | — |
| AH-S4 | Claude Code's comments name more of the techniques its code implements | one-sided sign test, uncorrected | 2026-11-01 | ○ | — |
| AH-S5 | Non-COBOL: Claude Code uses more bitwise operations (cell language only) | same | 2026-11-01 | ○ | — |
| AH-S6 | COBOL: Codex uses `CALL` subprograms more; Claude Code uses `EVALUATE` more | same | 2026-11-01 | ○ | — |
| AH-V1 | Comment volume is a stable agent trait (between-agent gap > pooled within-agent SD in most cells) | per-cell ratio > 1 in a majority | 2026-11-01 | ○ | — |
| AH-V2 | Overall structure is NOT a stable agent trait (within-agent / between-agent sfs distance ≥ 0.85, median over cells) | threshold | 2026-11-01 | ○ | — |

## Earlier studies (before this register)

The data-v2.7.0 clustering experiments (`experiments/2.7.0/*/EXPERIMENT.md`) wrote their predictions into
the experiment doc before results; they predate this register and are indexed in
[`EXPERIMENTS.md`](EXPERIMENTS.md) without verdict rows here.
