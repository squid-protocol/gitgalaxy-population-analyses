# Contributing

How studies are run in this repo. The method is the temporal crucible's, copied from
[temporal-crucible](https://github.com/squid-protocol/temporal-crucible) `CONTRIBUTING.md`,
`docs/HYPOTHESES.md` and `docs/EXPERIMENTS.md` at `21bc1a7` so both research repos hold the same
standard. Its rules are kept verbatim where they apply, and adapted only where this repo differs
(population scans rather than commit histories). Section 4 adds the guards specific to population
studies; each one exists because a study here was caught out by it.

## 1. The PR flow

1. **Branch, don't push to `main` directly.**
2. **Open the PR as a draft.** Org norm (learned the hard way on `gitgalaxy`): non-draft PRs on
   `squid-protocol` repos can auto-merge within seconds of opening, before pull-request-only checks
   have started. Open as draft, then mark it ready when it is.
3. Keep the PR focused. If a change touches both a tool's behaviour and a registered hypothesis's
   evaluation, say so explicitly in the PR description: reviewers need to know whether they are
   reviewing code or a confirmatory result.
4. **Registration and verdict never ship in the same PR.** A PR that adds both a new registration
   AND that same hypothesis's verdict in one shot is, by definition, not pre-registered: split it,
   or say plainly in the PR that it is post-hoc/exploratory and label it as such in the output.

## 2. Hypothesis-first (the rule this repo runs on)

[`docs/HYPOTHESES.md`](docs/HYPOTHESES.md) is the **register of record**. If your change produces or
touches a confirmatory claim (a hypothesis test with a p-value and a verdict, not a
descriptive/exploratory table):

1. **Register first.** The hypothesis, its direction, its test and its α go into
   `docs/HYPOTHESES.md` (and the study's own pre-registration, e.g.
   [`agent-habits-prereg/PREREGISTRATION.md`](agent-habits-prereg/PREREGISTRATION.md)) *before* the
   analysis that could confirm it runs. The registration text is quoted verbatim in the report that
   evaluates it. The registering commit's timestamp is the proof, so it is pushed before any
   confirmation data is generated, scanned or opened.
2. **Verdicts are published either way.** A null or contradicted result is not a reason to drop the
   table from the doc: it is the finding. A dead hypothesis stays in the register forever with its
   autopsy. Update the register's `verdict` column regardless of which way it went.
3. **Exploratory stays labelled exploratory**, in the doc and in any generated report. Descriptive
   tables (prevalence shares, gap rankings, "higher in N of M pairs") claim no p-values and are
   marked in place. An exploratory observation can graduate into a registered hypothesis, but only
   for data it has not seen yet (the next repos, the next runs, the next label class), **never
   re-tested on the sample that suggested it**.
4. **Every test keeps its guards** (section 4, plus the temporal crucible's where they apply:
   size-matched controls, length-matched pairs at function grain, temporal ablation, rename
   tracking, multiple-comparison correction on any table wider than one registered claim). Don't
   quietly drop a guard to make a table simpler.
5. **Freeze the analysis code with the registration.** Record the sha256 of every script the
   confirmatory tests will run (and commit the scripts, or their exact copies, beside the note).
   A later change to a frozen script is a deviation, logged in the note's Deviations section with a
   date and a reason before results are reported.

Start a new study from [`docs/_experiment_template.md`](docs/_experiment_template.md); an experiment
about how a tool, brief or setting changes an AI agent's work starts from
[`docs/_agent_experiment_template.md`](docs/_agent_experiment_template.md). Index it in
[`docs/EXPERIMENTS.md`](docs/EXPERIMENTS.md).

## 3. Running scans

* **Long batches run detached, never through a 600-second-capped shell.** Population scans and sfs
  comparisons over dozens of repos outlast any interactive or agent shell timeout. Launch them with
  `setsid nohup ... > log 2>&1 < /dev/null &`, make them resumable (skip a repo whose scan output is
  complete), and re-run the identical command if interrupted.
* **The temporal ablation is not optional** for any scan whose numbers feed a test: run galaxyscope
  with `GITGALAXY_DISABLE_GIT_HISTORY=1`, so churn/stability columns are neutral constants and a
  repo's history cannot leak into a structural comparison. If you ever compare against an unablated
  scan, say so loudly in the PR and keep it away from any confirmatory hypothesis.
* **Record what produced every number:** engine commit (`engine.sha`), each repo's pinned commit and
  licence (`pins.csv`), tool versions, and the exact command. A study that cannot be rebuilt from its
  README is not finished.

## 4. Guards for population studies

Each guard below exists because a study here was caught out by it.

1. **Licensed inputs only, measurements only.** The owner is an LLC, so corpus use is commercial:
   fetch only repos whose licence permits it (check with `gh api repos/O/R/license`; skip "no
   licence"), and publish measurements, counts, names and line numbers, never source text. Quote at
   most identifier-level fragments.
2. **Appraise scan quality before any analysis.** Before a single comparison, check what the engine
   actually extracted on the study's repos: definitions against tree-sitter and ctags, call edges
   against a compiler-grade reference where one exists, files assigned the wrong language, files
   excluded or banished, scan errors, timeouts and memory. Mark every cell a known defect touches and
   keep it out of the tests (the chess study's Ruby `<<` heredoc bug swallowed 26 functions in one
   file; OCaml, Lean, Mojo and TeX were not scanned at all).
3. **One engine per comparison.** Two sides of a comparison are scanned with the same engine commit.
   When a study pools scans made with different engines, say which and why, and rescan before a
   confirmatory test.
4. **Restrict each measure to the language under study.** A repo is usually polyglot (helper
   scripts, build files, generated output). Repo-level aggregates (including sfs signal densities)
   pool every language, so a side's Python helper scripts can masquerade as "more generics and
   comprehensions" in a C project. Compute per-language, or show the language mix next to the number.
5. **Check what a signal matches in that language before naming a finding.** A signal family is a
   per-language rule (`gitgalaxy/standards/language_standards/languages/<lang>.py`); "generics" means
   `_Generic` in C, type hints in Python, and nothing in COBOL. Read the rule, then look at a matching
   line in the source.
6. **Cross-check a headline number by a second route.** A measure that carries the story is checked
   against an independent count (e.g. GitGalaxy's doc/code ratio against a raw comment-line count)
   before it is reported.
7. **Every number has its comparison next to it.** A similarity next to a chance or shuffled control;
   a direction count next to its sign-test p; a rate next to the other side's rate. A number without
   its control is not shown.
8. **Count the tests.** When many measures were inspected (keywords, signals, profile columns), say
   how many, and treat any single lean as a hypothesis: some 5-0 splits are expected by chance among
   150 keywords. A pattern earns weight when it appears in independent channels (e.g. `EXIT` in COBOL
   and `if`/`return` elsewhere for the same early-exit style).
9. **Repeat runs before claiming a trait.** For anything generated (agent output, randomized tools),
   measure the within-source spread before calling a between-source difference a fingerprint: one
   extra run of one agent sat as far from its first run as from the other agent.
10. **Denominators and ranges come from the data.** Count from the data and grep the text for every
    stated total ("44 programs" included the reference; there were 43 descendants). Never state a
    range from memory.
11. **Keep a metric artifact apart from a finding.** An odd dip or spike is checked against how the
    metric behaves on that input (duplicated code, one-direction scores, zero-filled columns) before
    it becomes narrative.

## 5. Writing it up

* A result doc cites its pre-registration and reports **every** registered verdict either way, using
  the template's table.
* Plain-language summary first (what we did, what we learned), then the register rows, then the
  guards that applied and how, then what the result does NOT establish.
* For public articles, the GitGalaxy `popsci-interactive-article` skill holds the voice and the
  honesty checks; the guards above still decide what may be claimed.
