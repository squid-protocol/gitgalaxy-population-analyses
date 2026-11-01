<!--
Template for an AGENT experiment (scope AG-): does a tool, brief or setting change how well or how cheaply an AI agent
fixes issues in a codebase? Filled in by churn's experiment designer (Opus) as design.md; registered as
docs/agents/<id>-<slug>.md in a draft PR before any arm runs; the result goes in docs/agents/<id>-<slug>-result.md in a
SEPARATE PR. Every rule below exists because the #4479 self-scan A/B broke it (docs/agent_selfscan_ab_explore.md).
Delete this comment when filling in.

In this repo (copied verbatim from temporal-crucible docs/_agent_experiment_template.md at 21bc1a7): register as
<study>/PREREGISTRATION.md plus rows in docs/HYPOTHESES.md, in its own PR before any arm runs; the result goes in a
separate PR. "tc#" means this study's tracking issue; "docs/agents/" means the study's directory. The same rules hold
when the agents' output is the data being measured (e.g. agent-habits: arms = agents, tasks = cells): ONE difference
between arms, replicates >= 2 per arm per task, blinding where a human or model scores, and a power floor below
which a claim is "not evaluable", never a null.
-->

# Experiment <E-id>: <question in one line>

**Type:** confirmatory (agent utility, scope `AG-`)
**Registered:** <date> — tc#<n> · registration PR #<n>   **Tracking:** gitgalaxy#<n>
**What the answer would change:** <the brief, rule, policy or product claim, and in which direction for each outcome>
**Mode:** replay | live   **Budget:** $<n> (arms × tasks × replicates × per-run cap, plus design, scoring, write-ups)

## Arms

| label | condition (the instruction its worker gets) |
|---|---|
| <label> | <...> |

Arms differ in ONE thing. Everything else is identical: model, base commit, task brief, budget cap, gates.
Costs are counted as they would fall in real use (e.g. a DB built once per main commit is pre-built, its build time
reported separately, never charged per task).

## Tasks (listed before any run; never ones an earlier experiment used)

| # | issue | stratum | base (replay: the fix's first parent) | reference (replay: the merged fix) |
|---|---|---|---|---|

- **Replay is the default.** A merged fix is the ground truth: the arm starts at its parent and gets the issue text
  only. The brief must not leak the fix (no PR numbers, commit messages, or file names the issue does not name).
- Strata are declared here, with the stratum where an effect is expected (e.g. *vague*: the issue names no file or
  function; *impact*: the fix spans ≥ 3 files or needs "who calls this").
- **Replicates ≥ 2 per arm per task.** One run per arm is an anecdote. The equivalence band for cost is set from the
  replicates' spread before unblinding, and stated in the result.

## Rubric (scored per run, blind, after the full gates ran on that run)

| item | what is scored | how (mechanical where possible) |
|---|---|---|
| R1 correct | the reference fix's tests pass on the run's code | apply the reference tests; 0/1 or fraction |
| R2 no regression | full `pr_gates` + golden check green | gate output; 0/1 |
| R3 localisation | the run changed the function(s) the reference changed | function-grain diff overlap |
| R4 sibling recall | share of the pre-enumerated sibling gaps the run found | list = reference follow-ups ∪ all runs' findings, adjudicated blind |
| R5 economy | changed lines vs the reference | ratio; penalise > 2× |

Add or drop items only with a reason. "No worse" is defined by the rubric, never by a reviewer's impression.
Better quality at higher cost is a result to report, not a loss.

## Blinding

Runs carry random ids; the label map stays with churn (`.labels.json`) until every score is recorded. The scorer is
a separate session that never sees the map, the runs' prompts or their conditions. Notes and commits never name the
condition.

## Registered claims (verbatim; ids AG-H<n>)

> **AG-H<n>:** <direction> on <rubric item or cost>, <test> (paired by task; e.g. McNemar on discordant pairs,
> Wilcoxon signed-rank on per-task means, TOST for cost equivalence), α = 0.05 / <number of claims> (Bonferroni).

Power floor: <e.g. ≥ 20 discordant run pairs>; below it the claim is reported **not evaluable**, never as a null.

## Stop rule and cleanup

- Stop when every planned run finished, or when the budget would be exceeded (score what ran; say so).
- Replay arms open no PRs; their worktrees and branches are removed by churn. Live arms open draft PRs labelled
  `experiment` and titled `[exp <id> <run id>]`, never `shepherd:merge`; churn keeps the best (rubric total, ties to
  the cheaper) and closes the rest. The tracking issue closes with a link to the result PR.

## Result (in the result PR only)

| id | verdict | statistic | evidence |
|---|---|---|---|
| AG-H<n> | ✓ / ✗ / ⚠ / not evaluable | <p, effect, n, CI> | <cells> |

Per-run table (from `results.json`): run id, condition, task, replicate, R1..R5, cost, minutes. What it means, what it
changes (per the line at the top), and what it does NOT establish.
