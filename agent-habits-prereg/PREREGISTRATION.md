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

None yet. Any departure from this note is added here, dated, with a reason, before the results are reported.

## 9. Publication

Measurements, counts, keyword and technique names only; no source text (the owner's LLC licence rule). Every
outcome is reported, including refuted and inconclusive hypotheses.
