# Pre-registration: Claude Code vs Codex, structural habits

Registered 2026-11-01T12:39Z, before any confirmation data exists. Author: Joe Esquibel (GitGalaxy LLC), with Claude.
Everything below was fixed by looking at the **exploratory set** only. The confirmation set must not be scanned,
read or opened until this note (and the script hashes in section 7) are frozen and timestamped.

## 1. What has been looked at (the exploratory set)

* 10 same-task, same-language pairs, each a Claude Code repo and a Codex repo (acherm/agentic-*, MIT):
  chess engine in C, C++, Java, Python, Rust and COBOL; compressor, DOOM-like game, pygame-style framework and SAT
  solver in COBOL. Pins: `pins.csv` (chess) and `~/gitgalaxy/cobol-agents/pins.csv` (COBOL study).
* Context only (not in any test): rust-cc-redo (a second Claude Code chess run), the Ruby pair (engine bug, below),
  and the chess repos in other languages.
* Engines: chess scans at GitGalaxy main `433228fe1`; COBOL-study scans at the #7170 branch.
* Analyses run: `landscape.py`, `pooled.py`, `signal_diff_lang.py`, `keyword_diff.py`, `exit_kinds.py`,
  `sfs_read.py` (sfs structure + portable lens), `comments/` (comment extraction and classification),
  `compare/` (scan quality against tree-sitter, ctags and call-graph references).
* About 150 keywords, 29 signal families and 20 profile measures were inspected. The hypotheses below were picked
  from them, so the exploratory numbers are **hypothesis-generating only** and are not evidence for them.

## 2. Hypotheses

Direction is stated for every hypothesis; every test is one-sided in that direction.
"Cell" = one task × language combination (section 4). Per cell, each agent's value is the mean over its repeats.

### Primary (the confirmatory family; Holm-corrected across H1-H5)

| ID | Prediction | Measure (exactly as the frozen scripts compute it) | Exploratory result |
|---|---|---|---|
| H1 | Claude Code writes more comments | `doc_per_code_line` (`landscape.py`: doc_loc / coding_loc over the cell language's files) | CC higher 10/10 |
| H2 | Claude Code documents more of its functions | share of functions/paragraphs with a comment block directly above (`comments/analyze.py`) | 33 % vs 2 % pooled |
| H3 | Codex leaves early more often | COBOL cells: `EXIT PARAGRAPH` + `EXIT PERFORM` per 1,000 keyword tokens (`exit_kinds.py` / `keyword_diff.py`); other cells: `return` per 1,000 keyword tokens (`keyword_diff.py`) | COBOL 5/5; mainstream 4/5 |
| H4 | Codex adds Python helper code to non-Python projects | repo has >= 1 Python function with loc >= 3 in a cell whose language is not Python (sfs `languages_by_functions`) | Codex 5 of 9, CC 1 of 9 |
| H5 | Claude Code uses `while` loops more (non-COBOL cells) | `while` per 1,000 keyword tokens (`keyword_diff.py`) | CC higher 5/5 |

### Secondary (reported, uncorrected, each stands alone)

| ID | Prediction | Measure | Exploratory |
|---|---|---|---|
| S1 | Non-COBOL: CC has higher mean fan-out | `fan_out_mean` (`landscape.py`) | 5/5 |
| S2 | Non-COBOL: Codex has higher median function complexity | `complexity_median` | 5/5 |
| S3 | COBOL: S1 and S2 do **not** hold (direction reversed or tied in at least half the COBOL cells) | as S1, S2 | fan-out Codex 3 of 4 non-chess; complexity CC 4 of 5 |
| S4 | CC comments name more of the techniques its code implements | named / implemented (`comments/techcheck.py`) | 94 % vs 30 % |
| S5 | Non-COBOL: CC uses more bitwise operations | `bitwise_ops` per 100 function LOC, cell language only (`signal_diff_lang.py`) | 5/5 |
| S6 | COBOL: Codex uses `CALL` subprograms more; CC uses `EVALUATE` more | per 1,000 keyword tokens | exploratory leans only |

### Variance (the run-to-run question)

| ID | Prediction | Measure |
|---|---|---|
| V1 | Comment volume is a stable agent trait: the between-agent gap in `doc_per_code_line` is larger than the within-agent spread | per cell: (mean CC - mean Codex) / pooled within-agent SD > 1 in a majority of cells |
| V2 | Overall structure is **not** a stable agent trait: within-agent repeat distance is about the same as between-agent distance | sfs structure lens `profile_distance`, median over cells of (mean within-agent repeat distance) / (mean between-agent distance) >= 0.85 |

V2 is stated in the direction the single exploratory redo suggested (rust-cc-redo: 0.668 to rust-cc, 0.687 to
rust-codex, ratio 0.97). If V2 is refuted, an agent's structural fingerprint is real and the paper says so.

## 3. Decision rules

* **Primary:** for each H, a one-sided sign test over cells (ties dropped). Holm correction at family-wise
  alpha = 0.05 across H1-H5. H4 is a per-repo yes/no, so it is tested as a one-sided McNemar-style sign test
  over cells (cells where exactly one agent ships Python helpers).
* **Confirmed / refuted / inconclusive:** confirmed if Holm-adjusted p < 0.05; refuted if the direction is reversed
  in a majority of cells; inconclusive otherwise. Every hypothesis is reported, whatever the outcome.
* **Secondary:** raw one-sided sign-test p, no correction, labelled as such.
* **Variance:** V1 and V2 by the thresholds in their rows, with the per-cell values shown.
* The exploratory set is rescanned with the confirmation engine and reported alongside, but **is never pooled into the
  confirmatory tests**.

## 4. The confirmation set

Generated fresh after this note is frozen. Nobody looks at the code before the scans and the frozen scripts have run.

* **Agents:** Claude Code and Codex. The exact CLI versions and models are recorded at generation time, and the
  same versions are used for every run.
* **Tasks (2):** (a) a UCI chess engine, using the task prompt of the exploratory set where it can be recovered
  verbatim, otherwise a prompt written once, stored in `confirm/prompts/` and used unchanged for both agents;
  (b) a DPLL SAT solver that reads DIMACS (same prompt rules).
* **Languages (5):** C, Java, Python, Rust, COBOL (GnuCOBOL). That makes 10 cells.
* **Repeats:** 2 independent runs per agent per cell, each in a fresh environment with no shared history:
  2 agents × 10 cells × 2 = **40 repos**. V1/V2 use the repeats; H1-H5 and S1-S6 use the cell means.
* **Power check:** with 10 cells, H passes uncorrected at 9/10 (one-sided p = 0.011) and survives Holm for the top
  hypothesis at 9/10. 8/10 (p = 0.055) does not pass. If budget allows only 6 cells, only 6/6 passes; the note
  is not changed for that, the result is just reported as inconclusive.
* **Run hygiene:** same wall-clock budget and same "done" condition for both agents (the task's own test command
  passes, or the time cap is hit). Runs that fail to produce a buildable program are kept and flagged, not dropped;
  the H tests run with and without them (with = primary).
* **No tuning:** prompts are not changed per agent; no run is redone because its result looks odd.

## 5. Exclusions (fixed now)

* Files: the same rules as the frozen scripts (generated output such as cobc-emitted C, `target/`, `build/`,
  vendored code). Tests are kept.
* A cell is excluded only if the engine's scan of either side fails (non-zero exit, timeout) or a known engine defect
  touches the measured language. Any engine defect found during confirmation is logged, fixed in a separate PR, and
  the cell is reported both ways (before and after the fix).
* Known exploratory-set defects: Ruby `x << CONST` read as a heredoc (Ruby is not a confirmation language); C++
  call recall 58 % against libclang (C++ is not a confirmation language).

## 6. Engine

Confirmation scans use GitGalaxy main **after #7241 (#7206) merges**, at a single commit recorded in
`confirm/engine.sha` before the first confirmation scan. The exploratory set is rescanned with the same commit.
No engine change made after that commit is used for the confirmatory tests.

## 7. Frozen analysis code (sha256 at registration)

Any change to these files after registration is a deviation and is reported in section 8.

```
3a0a53e73659ea6c5618f39ed52759aa531d47262a8c32056fae9006cece87d5  landscape.py
b4291d54209cb0535a8f60b5dcf6bcbd63fed70a3320ed69ca0a6c738be30f36  pooled.py
e37b1e7a39f809cc36ab76a038ba075c5a172ee4a2a74e7fd8791ff0f35acaae  signal_diff_lang.py
c118188e8ceb1cf6ce623bcf775ba32e8f906c7f941893c97f0c0ba26e31fd21  keyword_diff.py
b92e2e513f33d44d33f3878822270e305b77842e4e83f62cdcf012338dd6545d  exit_kinds.py
19fcd959ab9491e185a7bac0326834e55187b3526ad0736ca5411b8a3609602b  sfs_read.py
0f9455b946ecba70937efea9bd6caff1f333ca4545887ded305a2dd59675b9d6  sfs_pooled.sh
b131fac8804cdfd993706a55ab6ca7be75d4331dbad4ee5d5125b8543f15fc0c  comments/analyze.py
f01386a40893c452434f9b5e3a1c892a9965a6fe868027256fa6ebb615fb2590  comments/classify.py
95d5cfa8652bb7ff96aa6fa9666172657072b904f60f7131db4ec32087a7a90b  comments/extract.py
a781536a3f7de592b71b42ea68bb9736734b1de9da73c0da3cb1515c5290d3a2  comments/handcheck.py
ded301345350007df203d9592f5b82dcbb137f3ceee7a353e78de59cfd89129c  comments/summary.py
4a612584e67d477cfb092865ddf8777fe9432993e83b03d886ccad0ab444d630  comments/techcheck.py
```

The scripts hard-code the exploratory repo names. For the confirmation set they get only a new pair/cell table
and paths, in a separate file (`confirm/cells.py`) written before the first scan; the measurement code is unchanged.
Classifier rules (`comments/classify.py`) stay frozen: no re-tuning on confirmation comments. A fresh 100-block
hand-check of the confirmation comments is reported, to show the classifier's accuracy on new data.

## 8. Deviations

Any departure from this note is added here, dated, with a reason, before the results are reported.

### D1 (2026-11-01, before any confirmation run): 24 runs instead of 40

**Why:** cost and time. A public search for licensed same-task pairs (metadata only, no source opened;
`confirm/candidates.md`) found one usable pair, so generation stays the plan, at a lower cost.

* **Primary and secondary tests (H1-H5, S1-S6):** all 10 cells, **one run per agent per cell** (20 runs). Power
  is unchanged: the tests run over the same 10 cells (9/10 still needed). In the two repeat cells below, these
  tests use each agent's **first** run only, so every cell has one run per agent.
* **Variance tests (V1, V2):** **two repeat cells only**, chess/Rust and SAT/Python, with **2 runs per agent**
  in each (1 extra per agent per cell: 4 runs). Total 20 + 4 = **24 generated repos** (24 agent sessions).
  - Within-agent spread in a repeat cell is the difference between that agent's two runs.
  - V1 passes if the between-agent gap exceeds the pooled within-agent SD in **both** repeat cells.
  - V2 passes if the mean, over the two repeat cells, of (within-agent / between-agent sfs distance) is ≥ 0.85.
  - With two cells, V1 and V2 are labelled **underpowered** whatever the outcome.

### D2 (2026-11-01, before any confirmation run): the agents and models

The exploratory set's authors state Claude Code with **Opus 4.6** and Codex with **GPT-5.2-5.4 / gpt-5-codex**:
flagship models of early 2026, none available now. The confirmation uses:

| side | agent | model | setting | account |
|---|---|---|---|---|
| Claude Code | Claude Code 2.1.316 | `claude-sonnet-5-5` (Sonnet 5.5) | default effort | the owner's Team seat |
| Codex | Codex CLI 0.166.0 (`@openai/codex`) | `gpt-6-luna` (the CLI's default for this account) | reasoning effort medium | ChatGPT Free |

Both are a **newer generation and a lighter tier** than the exploratory set's. How a result is read (fixed now):
* a hypothesis **confirmed** here holds across a change of model generation and tier on both sides (a stronger
  claim than the exploratory one);
* a hypothesis **not confirmed** here is reported as "not confirmed under a model change": it cannot separate a
  habit that disappeared from an effect of the new models, and is never reported as a clean refutation of the
  exploratory observation.
The exact versions are recorded per run (`confirm/runs.csv`) and no version changes during the study; if either
CLI auto-updates, the run is redone on the pinned version before any measurement.

### D3 (2026-11-01): usage limits

The Codex Free allowance is unpublished, and Claude Code has a 5-hour limit. A run interrupted by a limit is
**resumed in the same session** after the reset (`codex exec resume <id>`, `claude --resume <id>`) with the
single message "continue"; it is never restarted from scratch. Each interruption is logged in `confirm/runs.csv`.
The wall-clock cap counts active time only.

### D4 (2026-11-01): found pairs as a supplementary check

The usable found pair (Crown Defender TD, JavaScript, MIT, `confirm/candidates.csv`) is scanned and reported
beside the confirmation as a **supplementary, uncorrected check** of H1-H5 where they apply. It is not part of any
primary test. The selection rule is fixed: every candidate marked usable in `confirm/candidates.csv` as of
2026-11-01. The marginal receipts-CLI pair is included only if its Codex side has at least 300 code lines.

### D5 (2026-11-01, before any confirmation run): autonomous runs, and the frozen run kit

**Autonomous, not steered.** The exploratory set's runs were interactive: the authors state, for example,
"47 substantive prompts, 15.5 active hours" for one COBOL chess engine. No verbatim prompt was published. The
confirmation runs are autonomous: one fixed prompt per task (`confirm/kit/prompts/`, written once, identical for both
agents; it states the task, the interface, the language rule and how completion is checked, and says nothing about
comments, tests, structure or helper scripts), then no human input. What is confirmed is therefore each agent's
habits **without human steering**; a hypothesis not confirmed is reported with that difference named, beside D2's.

**Done condition and budget.** The harness, not the agent, decides done: after each session it runs the checker
(`confirm/kit/check/check.py`: builds with `./build.sh`, then chess: UCI handshake, perft on six published positions,
a timed `go`; SAT: planted-satisfiable, pigeonhole and brute-forced random formulas, every model verified). On FAIL
it resumes the same session with the checker's first 40 lines, at most **2 times**. Cap: **60 active minutes** per
run over all sessions (limit waits excluded, D3). A run that ends without PASS is kept and flagged (section 4).

**Environment.** Every session runs in a fresh container of one image (`agent-habits-run:1`, id
`sha256:8f66cca4bca0480d590dbd758c0fa5b80e06e34c11585f636a79b562ec931150`): Debian 12, GnuCOBOL 3.1.2, JDK 17,
Python 3.11, gcc 12, Rust 1.82.0, Codex CLI 0.166.0, Claude Code 2.1.316, 3 CPUs, 6 GB, network on (model APIs);
each run's agent home starts empty except for its login, so no memory, settings or skills from the host reach it.

**Order.** The 24 runs execute in a fixed shuffled order (`run.py --order`, seed 20261101); in a repeat cell, r1 is
the run that happens first.

**Frozen kit (sha256):**

```
23af9554e6a00bdc2a8e2e53cb2fa493dfd536e557f729f42b26533644edc5f7  prompts/chess.md
6113f82425a820a859a7144c60854b59a3a969212128e2e2fb88e110bd5510f7  prompts/sat.md
5e8711a7ad38c9ab6b8210b6ea39ecf0705a04181dce690e75c89ea1032d07d7  cells.py
2727e697eda093c4bfadb0bb24fb8d7fd5d80f4997feb0c01bca4a5dc2f9a193  run.py
28ed58675d728d6e3756f24fef3911e7788e9b3a2064c9b5a678379f73987efb  check/check.py
89bbf9ff9934ed8f6aa194f1665174bc71187a240b3d3524ece0ddf272b8fd3c  check/check
437c4757e157bdff6e978df0dbef8ad26b760b9d8506300d54571b5af78ba548  docker/Dockerfile
fd13c70000fec3f2116dfbcbb6121210b4a29328bf0e46210a59dd594a67d824  docker/claude-2.1.316  (Anthropic's binary; not committed)
```

The kit is committed in `confirm/kit/` (all but the Claude binary). It was smoke-tested on a toy task, one session
per agent, outside the study (no study cell was run).

## 9. Publication

Measurements, counts, keyword and technique names only; no source text (the owner's LLC licence rule). Every
outcome is reported, including refuted and inconclusive hypotheses.

### D6 (2026-11-01, after runs 1-2 started): pacing, and a selection option

**Pacing.** The owner stopped the batch after two runs (`sat-rust-codex-r1` finished, `chess-rust-claude-r1` in
progress): the remaining runs are started one at a time, by hand, at a pace the Codex Free allowance and the Claude
5-hour window allow. Neither run was redone or inspected for its measures.

**`run.py --next --agent AGENT`** picks the next pending run of one agent in the frozen order, so Claude runs can
continue while the Codex allowance recovers. It changes no prompt, checker, cap, nudge rule or order; within an agent
the order (and so which run is r1) is unchanged. The agent each run's slot belonged to is fixed by the order, so
runs completed per agent can drift in calendar time; the run dates are reported per run.

`run.py` sha256 after this change: `ce451276ab1b93b81fa1a8570310d5cf81c4edb288d42a66a783985c3207f15c`
(was `2727e697...` in D5; runs 1-2 used the D5 version).

### D7 (2026-11-01, after the two pilot runs, before any of their measures was looked at): harder tasks

**Why:** the first two runs passed the D5 checker in one session each (49 s and 103 s of agent time; 154 and 944
lines), far smaller than the exploratory set's programs (2-10k lines). Structure-based tests (S1-S3, V2) would be
starved of functions. Only pass/fail, active time and line counts of the two runs were seen.

**Decision (owner, 2026-11-01):**
* The two runs (`sat-rust-codex-r1`, `chess-rust-claude-r1`) are a **pilot**: moved to `confirm/pilot/`, excluded
  from every test, never measured for the study. Every cell is run afresh under the new kit, same plan and order.
* The done condition is raised so that a one-shot minimal program does not pass: chess adds tactical puzzles and a
  short match against a weak opponent; SAT adds hard random and large formulas under a time limit. The prompts say
  so (and still say nothing about comments, tests, structure or helper scripts). Cap and nudge rule unchanged.
* The new kit (prompts, checker, instances, image) is frozen by hash in a D7 addendum **before** the first run under
  it, and smoke-tested on toy tasks only.

#### D7 addendum (2026-11-01, before the first run under it): the frozen harder kit

**Chess done condition** (adds to the D5 checks): 22 unique forced mates (14 mate-in-2, 8 mate-in-3; each verified
by brute force to have exactly one mating first move and no faster mate), 2 s each, at least 80 % (18) solved; and a
4-game match against a greedy material-grabbing opponent (colours alternating, 0.5 s per engine move, illegal move =
loss), at least 3 points. Games end only on the automatic rules (checkmate, stalemate, insufficient material,
fivefold repetition, 75-move rule); at 300 plies a side 5+ points of material ahead is adjudicated the winner,
otherwise a draw. The referee is python-chess 1.11.2 in `/opt/checkvenv` (checker only).

**SAT done condition** (adds to the D5 checks): 13 hard formulas, 60 s each: random 3-SAT at ratio 4.26 with
n = 150 (4), 200 (4), 250 (2) (status from picosat: 5 SAT, 5 UNSAT) and planted 3-SAT at ratio 3.5 with
n = 2,000 (2) and 5,000 (1); no wrong answer allowed, at least 80 % (11) answered. Each formula is handed to the
solver under a random file name, without its comment line.

**Practice vs held-out.** An agent's session mounts `check_public/` (same checker code, a practice set generated
with seed 20262101: no puzzle in common with the held-out set). Only the harness's final check mounts the held-out
set (seed 20261101). The held-out files are not committed until the study ends (agents have network access); their
hash is fixed here.

**Validation** (scratch references, not shipped): a picosat-backed solver passes 13/13 hard formulas (6 s); a plain
recursive DPLL in Python answers 0/13. An engine with exact mate search and a 2-ply search passes (22/22 puzzles,
3.0/4 match); a correct move generator that plays its first legal move fails (1/22, 0.5/4). Both agents ran a
20-second toy task on image v2 (outside the study).

**Frozen (sha256):**

```
a633a5675fcce5b70caca199ac54c9c7de476657aee11106595e92b25533d549  prompts/chess.md
7800c32ac5490fe3c1d68f2ea645266b7dfbaf87ab93b2d5b2bfcd52e31c8635  prompts/sat.md
5e8711a7ad38c9ab6b8210b6ea39ecf0705a04181dce690e75c89ea1032d07d7  cells.py
018b8f342feab7f2a74bc3ba6810c77b523e56e5a7cdb604281d4788293e536e  run.py
cffa114d66f34803809e3629fa674ef0f79fc61e8e2eafeda66fb604167d1d31  check/check.py (= check_public/check.py)
150386ce78c1d768a13a06456eeb193f89f25d1ef3461e2dee00bce2e106397c  check/check (= check_public/check)
858decbacefc9b1333c4852e271b6ebf87885a92662da9dd89dd5d7300c890d8  docker/Dockerfile
df1c49beec75f82a117079171ebb2817886697378fc8107fdbbdabeec2404125  gen_assets.py
482bc1ce419af5e56d5a5c4f6a908eb17310c0250ff448c3a6e92bbb68149024  held-out assets (sha256 of the sorted per-file sha256 list)
c6cdb5807895fd66e2a553150e0ff3b9d24101fa112a7f910cea294bf8cd7724  practice assets (same method; committed)
image agent-habits-run:2 = sha256:5f635efda4054dc78a22f5b14c83159d375580cf871ea015c794d2068f174719
```

Cap (60 active minutes), nudge rule (2), cells, order (seed 20261101) and agents/models (D2) are unchanged.

### D8 (2026-11-01, after run 1 and while run 2 is in progress): two parallel lanes

To save wall-clock time the runs execute in **two lanes at once, one per agent**: Claude Code runs on CPU cores 0-2,
Codex runs on cores 3-5 (`AH_CPUSET`, `docker run --cpuset-cpus`), each lane one run at a time in its agent's frozen
order (`batch_n.sh`). Pinning keeps the timing-sensitive checks (2 s puzzles, 0.5 s match moves, 60 s formulas) from
competing for cores between lanes; the cores are identical, and other load on the host falls on both lanes alike.
Runs 1 (`sat-rust-codex-r1`) and 2 (`chess-rust-claude-r1`) ran unpinned, one at a time. The owner set this batch
at 5 runs per agent; after each Codex run the free plan's `used_percent` is logged and Codex runs pause at 60 %.
No prompt, checker, asset, cap, nudge rule or order changed.

`run.py` sha256 after this change: `b67763385c38c6b9c292f8cb06dca0b6541c0e29878e85f0e168c73b0084750e`
(only the `AH_CPUSET` option was added).

### D9 (2026-11-01, before any Haiku run): an exploratory third arm, Claude Code on Haiku 5.5

The owner added a third arm: **Claude Code 2.1.316 with `claude-haiku-5-5`** (default effort), the same 10 cells and
2 repeat cells (12 runs), same prompts, checker, held-out set, cap, nudge rule and image, on CPU cores 0-2 beside the
Codex lane (D8).

* **Exploratory only.** H1-H5, S1-S6 and V1-V2 are and stay Claude Code (Sonnet 5.5) vs Codex; no Haiku run enters
  any registered test. Haiku results are reported descriptively, labelled exploratory, with no p-values.
* **The question it opens** (for a later registration on unseen data, never tested on these runs): do the registered
  directions also hold for Haiku vs Codex (a habit of Claude Code / Anthropic's training generally) or only for Sonnet
  vs Codex (a habit of one model)? And Haiku vs Sonnet within Claude Code (the model's share of the habit).
* **Order.** `cells.AGENTS` (and so `plan()` and the registered order, seed 20261101) is unchanged; Haiku is in
  `cells.EXTRA_AGENTS` with its own shuffled order (seed 20261102), appended after the registered order. Checked:
  the registered 24-run order is identical before and after the change. r1/r2 of a Haiku repeat cell follow that
  order.
* Smoke-tested on a toy task (outside the study): model `claude-haiku-5-5`, no error.

sha256 after this change: run.py `30e85d4aeb4b9c761fd13e86f77a2adcae9cb1048596f1d39cda52462791d94f`, cells.py `e762ff38e34f570ea3925921666eb943a340f6df31b5d120bee7b7db6f932b33` (D8: run.py `b6776338...`).

### D10 (2026-11-01, before any Haiku run was measured): the Haiku arm becomes confirmatory; a rule for more arms

D9 set the Haiku arm as exploratory. No measure of any confirmation run (any arm) had been computed or looked at
when this was written: only pass/fail, active time and line counts of the Sonnet and Codex runs, and nothing of the
Haiku runs (the first was in progress). So the Haiku comparisons are registered as confirmatory here, replacing D9's
"exploratory only". Arms: **S** = Claude Code on Sonnet 5.5, **X** = Codex on gpt-6-luna, **K** = Claude Code on
Haiku 5.5 (D9).

**Family A, S vs X** (H1-H5, S1-S6, V1-V2): unchanged.

**Family B, K vs X: the habits belong to Claude Code, not one model.** Same measures, same directions, same tests
as H1-H5 (one-sided sign test over the 10 cells, ties dropped; Holm across B1-B5 at family-wise α = 0.05; the first
run per agent in the repeat cells):

| id | prediction (K vs X) | measure |
|---|---|---|
| AH-B1 | K writes more comments | as H1 |
| AH-B2 | K documents more of its functions | as H2 |
| AH-B3 | X exits early more | as H3 |
| AH-B4 | X adds Python helper code to non-Python projects | as H4 |
| AH-B5 | K uses `while` more (non-COBOL cells) | as H5 |

**Family C, K vs S: does the model change the habit inside Claude Code?** No direction is justified, so two-sided
sign tests on the five H1-H5 measures (AH-C1..C5), Holm across C1-C5 at α = 0.05. Reading, fixed now: A and B
confirmed with C null = a habit of Claude Code / its vendor; A confirmed, B not = a habit of the Sonnet model. A null
in C is reported as "no difference detected", not as equivalence.

**Variance.** K's repeat cells (chess/Rust, SAT/Python) give its within-agent spread; reported beside S's and X's for
V1/V2, descriptively.

**Reading across families.** Holm controls each family; across families the report states that three families (A,
B, C) were tested and gives every raw p beside its adjusted one.

**Rule for future arms** (another model, agent or vendor on the same tasks): before any of its runs is measured, the
new arm registers its families against each existing arm on the same measures (directional where a prior result
gives a direction, two-sided otherwise), Holm within each family; its runs use the same kit, held-out set, cap,
nudge rule and image, on a pinned lane; its order gets its own seed. A deviation records the arm before its first
run.

### D11 (2026-11-01, before any run of the new rounds and before any measure of any run): second rounds of S and K

The owner added a second, independent full round of each Claude arm: **S'** (`sonnet-b`: Claude Code 2.1.316,
`claude-sonnet-5-5`) and **K'** (`haiku-b`: `claude-haiku-5-5`), each the same 10 cells + 2 repeat cells (12 runs),
same kit, held-out set, cap, nudge rule and image; own seeded orders (seeds 20261103 for `haiku-b`, 20261104 for
`sonnet-b`), appended after the existing orders (checked: the first 36 positions are unchanged). Lanes (D8): K' on
cores 0-2 after K; S' on cores 3-5 after the Codex lane.

**Families D (S vs S') and E (K vs K'): the within-model noise floor (negative controls).** Two-sided sign tests on
the five H1-H5 measures over the 10 cells (first run per arm in repeat cells), Holm across D1-D5 and across E1-E5
at α = 0.05 each. **Predicted: no difference.** Reading, fixed now: Family A (S vs X) confirmed with D null = the
agent gap exceeds run-to-run noise; a measure significant in D is reported as unstable within the model, and its
A result is read with that caveat.

**Variance, upgraded.** With S and S' (and K and K') the within-model spread is available in all 10 cells, not only
the two repeat cells: V1 is additionally reported over all 10 cells as (|mean S - X| > |S - S'|) per cell, counted
over cells; V2 likewise with sfs distance (S-S' distance vs S-X distance per cell). These all-cell versions are
reported beside the registered two-cell V1/V2, which stay the registered tests.

**Replication (reported, not a family):** S' vs X on the H1-H5 measures, described as a replication of Family A with
independent Sonnet runs (X runs are shared, so it is not independent evidence).

cells.py sha256 after this change: `6b486e1ccac6a6438e6a19359f61d10e96df976095da675399de008153c4058e` (run.py unchanged since D9).
