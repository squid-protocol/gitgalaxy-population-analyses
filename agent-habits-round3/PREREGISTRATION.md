# Pre-registration, round 3: can structure alone identify the model that wrote a program?

Registered 2026-11-02, before any round 3 run exists. Author: Joe Esquibel (GitGalaxy LLC), with Claude.
Builds on the agent-habits study ([squid-protocol/agent-habits](https://github.com/squid-protocol/agent-habits);
its registration: [`agent-habits-prereg/`](../agent-habits-prereg/PREREGISTRATION.md), deviations D1-D16).

## 1. Where the hypothesis comes from (exploratory; never re-used for the test)

In the agent-habits confirmation runs (60 programs: Claude Code + Sonnet 5.5 ×2 rounds, Claude Code + Haiku 5.5
×2 rounds, Codex CLI + gpt-6-luna; chess engine and SAT solver × C, Java, Python, Rust, COBOL), **the nearest
neighbour of a program by sfs profile distance, among the other programs of the same task and language, was
written by the same model in 43 of 52 programs (83 %; chance 27 %; label-permutation p < 0.001)**, structure lens,
D16 handling (`agent-habits/results/data/identify_model.txt`). That analysis was not registered; it was run after
the registered tests. Round 3 tests it on data that did not exist when it was found.

## 2. Hypotheses

| id | claim | test | α |
|---|---|---|---|
| **R3-H1** | **Replication.** On fresh runs of the same two tasks and five languages, the same-cell nearest neighbour is the same model more often than chance. | one-sided label-permutation test (model labels shuffled within each cell, 10,000 draws); statistic = number of hits | 0.05 |
| **R3-H2** | **Generalisation to a new task.** The same holds on a task no study run has used: a Huffman file compressor (§4), same five languages. | same test, new-task cells only | 0.05 |
| R3-S1 | The point accuracy is at least 0.60 in R3-A and in R3-B (descriptive bar; reported with a Wilson 95 % CI). | — | — |
| R3-S2 | Each model's own queries beat chance (per-model permutation, one-sided). | uncorrected | 0.05 each |
| R3-S3 | The portable lens (language-neutral) agrees: accuracy above chance. | as H1 | 0.05 |
| R3-S4 | **Cross-task identification.** A program's nearest neighbour **among programs of the same language but the other task(s)** is the same model more often than chance (does the fingerprint survive a change of task?). | as H1, candidates = same language, different task | 0.05 |

H1 and H2 are the primary family (Holm across the two). S1-S4 are secondary, reported uncorrected and labelled.
Reading, fixed now: H1 and H2 confirmed → a model's structural fingerprint is identifiable across fresh runs and a
new task; H1 only → identifiable on known tasks, not shown to generalise; neither → the 83 % was specific to that
sample. Every outcome is reported.

## 3. Method (frozen)

* **Identification:** `identify_model.py` exactly as in the agent-habits repository
  (sha256 `4dab9a51c3389c97806aba09f55a35ce6e3413b1296e66f96c704c386a320ffe`): for each program with at least one
  same-model candidate in its cell, take the nearest other program in the cell by sfs `profile_distance`; a hit is
  same model. Chance = mean share of same-model candidates. For R3-S4 the candidate set is changed to "same
  language, other task" by a parameter only, recorded in the result.
* **Fingerprints:** sfs (structural-fingerprint-scanner, the version in gitgalaxy-population-analyses at the commit
  of this registration), `compare --no-twins`, structure lens (portable lens for S3);
  `run_sfs.sh` sha256 `610cb41fcc759cc953606211e79124c255d0c630ceeb512e6ed9ddd6170445db`.
* **Engine:** GitGalaxy main **after gitgalaxy#7501 merges** (the dense-code fix), pinned in
  `agent-habits-round3/engine.sha` before the first round 3 scan. If #7501 has not merged when the runs finish, the
  engine is main at that time and agent-habits D16's handling applies (lift the saturation bound for a blocked run;
  else a formatter-wrapped measurement copy), validated against tree-sitter and ctags.
* **Exclusions (fixed now):** a program with fewer than 3 functions of at least 3 lines (sfs's floor) has no usable
  fingerprint: excluded and counted, never replaced. A run that fails the task's check is kept (identification uses
  the code, not the verdict); a sensitivity version without failed runs is reported.
* **Validity first:** before any identification result is computed, the round 3 scans get the GitGalaxy vs
  tree-sitter vs ctags appraisal (coverage per arm, exclusions). This time the appraisal precedes the analysis.

## 4. Data to be generated

* **Agents and models:** Claude Code (Sonnet 5.5), Claude Code (Haiku 5.5), Codex CLI (gpt-6-luna, reasoning
  medium); versions recorded per run. Same container image family and harness as agent-habits (one fixed prompt per
  task, 60 active minutes, a hidden checker with a practice set, at most two nudges).
* **R3-A (replication):** chess and SAT × C, Java, Python, Rust, COBOL = 10 cells, the agent-habits prompts and
  checker unchanged, **new** held-out puzzles and formulas (a new seed), **2 runs per model per cell**: 60 runs.
* **R3-B (new task):** a Huffman file compressor (`./huff c IN OUT`, `./huff d IN OUT`, byte-exact round trip,
  compressed size within 1.1× of an ideal Huffman code plus header on a hidden file set) × the same 5 languages,
  **2 runs per model per cell**: 30 runs. Its prompt and checker are written and frozen (hash recorded here as a
  dated addendum) before its first run; the prompt follows the agent-habits rules (states task, interface, language
  rule and the check; nothing about comments, structure or style).
* **Order:** a fixed shuffled order per arm (new seed), recorded before the first run.
* **Codex budget contingency (fixed now):** the Codex Free allowance may not cover 30 runs. If it runs out, the
  remaining Codex cells get **1 run per cell**; those Codex programs stay in every candidate set as distractors,
  and Codex queries without a same-model candidate are dropped (the script already skips them). The report states
  how many Codex runs were made.

## 5. Deviations

Any departure is added here, dated, with a reason, before its results are reported.
