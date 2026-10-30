# Same task, two agents: the structure of AI-written COBOL

Draft, 30 October 2026. Measurements only: no source text from the systems is reproduced, only paragraph names
and counts. All ten systems are MIT-licensed and come from Mathieu Acher's study *Coding Agents Develop COBOL
Systems: Evidence from a Multi-Case Empirical Study* (2026), study hub
[acherm/agentic-cobol-study](https://github.com/acherm/agentic-cobol-study). This analysis is independent of
that study and makes no claim about whether the systems are correct, which the study itself evaluates.

## Summary

In Acher's study, Claude Code and Codex each built the same kinds of non-trivial program from scratch in COBOL.
We took the five task families where both systems are published under a licence (a chess engine, a compressor,
a DOOM-like ray-casting game, a pygame-style graphics framework and a SAT solver) and measured their structure
with the GitGalaxy engine: how each program is divided into paragraphs, how those paragraphs call each other,
and how much of the system is COBOL at all.

Four differences hold in every pair, or in every pair where they can apply:

1. **Claude Code never writes code before a program's first paragraph; Codex does in four of five systems.** In
   the chess engine 52% of Codex's COBOL is in these unnamed main lines, and in the pygame framework 40%.
2. **Codex builds shared helper paragraphs that many others call.** Its most-called paragraphs are small
   utilities (`trim-helper` and `format-signed-number`, with 8 callers each); the share of calls landing on
   the top 5% of paragraphs is higher for Codex in all five pairs.
3. **Claude Code's repositories are more COBOL** in all five pairs, though in three the gap is 3 to 4 points of
   test and build scripts. In one it is large: Codex wrote a 1,626-line C rendering bridge for its DOOM-like game.
4. **Codex writes free-format COBOL in all five systems; Claude Code in one.** Codex's three systems built with
   `gpt-5.4` also name every paragraph in lowercase; its two built with `gpt-5.2` use uppercase.

Size, branching and the rate of state changes do not separate the agents. Five pairs cannot establish a rule:
even a five-of-five difference has a two-sided sign-test p of 0.0625. Several differences also follow the model
version rather than the agent (see *Agent or model?*). Read these as consistent patterns in this sample.

Getting the measurements right took two engine fixes, described under *Checking the scans first*. An earlier
version of this comparison reported that Claude Code writes branchier paragraphs in four of four pairs. That
result was an artefact of the engine not seeing main-line code, and it disappeared once the engine did.

## The systems

| family | agent (model) | study difficulty | COBOL lines | other code | free format |
|---|---|---|---:|---|---|
| chess engine | Claude Code (`claude-opus-4-6`) | High | 2,920 | none | no |
| | Codex (`gpt-5.2`) | High | 3,359 | Python 534, shell 35 | yes |
| compressor | Claude Code (`claude-opus-4-6`) | Low | 1,819 | Python 403, shell 268 | no |
| | Codex (`gpt-5.4`) | High | 1,816 | Python 654, shell 157 | yes |
| DOOM-like game | Claude Code (`claude-opus-4-7`) | Medium | 1,616 | shell 50 | no |
| | Codex (`gpt-5.4`) | Medium | 1,910 | C 1,626 | yes |
| pygame-style framework | Claude Code (`claude-opus-4-6`) | High | 764 | C 283 | yes |
| | Codex (`gpt-5.2`) | Medium | 398 | C 340 | yes |
| SAT solver | Claude Code (`claude-opus-4-6`) | Low | 1,347 | shell 558 | no |
| | Codex (`gpt-5.4`) | Medium | 1,706 | shell 808 | yes |

Models and difficulty ratings are the study's. The study notes that paired runs "shared goals or replay
specifications to varying degrees"; the Claude Code SAT solver is a replication of its Codex sibling from replay
prompts. Line counts are coding lines as GitGalaxy counts them. Three task families from the study are left out
because at least one of their two systems has no licence (the COBOL compiler, payroll, and Game of 15).

## Checking the scans first

Each system was scanned with GitGalaxy and each scan was checked before any comparison:

- **Coverage.** Every COBOL source and copybook file in all ten repositories is mapped by the engine.
- **Paragraph inventories match an independent count in all ten systems.** Six were checked with GitGalaxy's
  answer-key reader (`tests/tools/cobol_answer_key.py`, which imports no engine code), units and call edges
  exact. The other four keep their paragraphs in procedure copybooks that reader does not expand, so their
  paragraph names were checked against a separate header count instead: 45, 55, 69 and 110 names, identical.
- **The main line was invisible (GitGalaxy #7170, fixed).** Code between a program's PROCEDURE DIVISION header and
  its first paragraph had no row in the engine's function table: no size, no complexity. That is 45% of the
  Codex chess engine's procedure code and none of Claude Code's, so every per-paragraph comparison was measuring
  different fractions of the two sides. The fix makes each main line a function named after its program. After
  it, no code line is outside a unit in the six systems the answer key can read (the Codex chess engine went
  from 875 such lines to none). Before the fix, the comparison reported *branchier Claude Code paragraphs in four
  of four pairs* (the four then measurable); with main lines counted that splits two and two in those pairs
  (three and two once the compressor joins), and median paragraph length reverses.
- **A memory blowup (GitGalaxy #7169, fixed).** The Claude Code compressor declares `PIC X(1073741824)`, a 1 GiB
  buffer, eight times. The engine expanded each picture position by position and needed 12.9 GB to scan a
  316 KB repository. With the fix it scans in 4.5 seconds at 175 MB, and its inventory matches the answer key
  exactly (47 of 47 paragraphs, 54 of 54 call edges).

## Findings

### 1. Main lines: Codex writes them, Claude Code never does

| family | Claude Code: share of COBOL in main lines | Codex | Codex model |
|---|---:|---:|---|
| chess engine | 0% | **52%** (14 programs) | `gpt-5.2` |
| pygame-style framework | 0% | **40%** | `gpt-5.2` |
| compressor | 0% | 5% | `gpt-5.4` |
| DOOM-like game | 0% | 1% | `gpt-5.4` |
| SAT solver | 0% | 0% | `gpt-5.4` |

Every Claude Code program opens its PROCEDURE DIVISION with a named paragraph. Codex often writes the program's
work directly after the division header. In its chess engine one evaluation program has 327 lines and no
paragraph at all. Both are legal COBOL. The difference matters for anyone measuring or modernising the code,
because a tool that counts only paragraphs (as GitGalaxy did until #7170) does not see this code. The two large
shares are both `gpt-5.2` systems.

### 2. Codex factors shared helpers

| family | top-5% share of calls, Claude Code | Codex | most-called paragraphs (number of callers) |
|---|---:|---:|---|
| chess engine | 0.15 | **0.23** | Claude Code: EXTRACT-TOKEN (5), ADD-MOVE (5). Codex: ADD-MOVE (8), ADD-PROMOS (4) |
| compressor | 0.11 | **0.18** | Claude Code: TOKEN-NEXT (3), FREE-PAYLOADS (3). Codex: trim-helper (8), trim-arg-value (5), write-little-endian (4) |
| DOOM-like game | 0.10 | **0.12** | Claude Code: READ-ONE-BYTE (3). Codex: test-probe-cell (4), render-scene (3) |
| pygame-style framework | 0.14 | **0.19** | Claude Code: RESET-GAME (2), RAND-GAP (2). Codex: UPDATE-TITLE (3), RESET-GAME (2) |
| SAT solver | 0.15 | **0.17** | Claude Code: SKIP-WS (5), READ-WORD (3). Codex: format-signed-number (8), assign-solver-literal (5), parse-integer-token (4) |

The share of all PERFORM edges that land on the most-called 5% of a system's paragraphs is higher for Codex in
all five pairs. In the compressor, chess and SAT pairs it is visible in the names: Codex writes small utilities
for trimming, formatting, parsing and byte order and calls them from many places. Claude Code's most-called
paragraphs have fewer callers and are more often steps of one task. The gaps are small in the DOOM-like and SAT
pairs.

### 3. How much of the system is COBOL

| family | COBOL share, Claude Code | Codex | what the rest is |
|---|---:|---:|---|
| chess engine | 100% | 86% | Codex: a Python harness (534 lines) |
| compressor | 73% | 69% | both: Python and shell test and build scripts |
| DOOM-like game | 97% | **54%** | Codex: a C bridge to SDL for rendering (1,626 lines) |
| pygame-style framework | 73% | 54% | both: a C shim to SDL, as the task asks |
| SAT solver | 71% | 68% | both: shell scripts |

Claude Code's share is higher in all five pairs, but this measure counts every language in the repository,
including tests and build scripts. Only the DOOM-like pair shows program logic moved out of COBOL: Codex renders
through a 1,626-line C bridge. Claude Code's DOOM-like repository holds no C at its pinned commit, although its
README mentions a C sidecar for the screen.

### 4. Format and naming

Codex wrote all five systems in free-format COBOL (`-free` or `>>SOURCE FORMAT FREE`); Claude Code wrote one of
five that way, the pygame framework. Codex's `gpt-5.4` systems (compressor, DOOM-like, SAT) name every paragraph
in lowercase (`trim-helper`, `render-scene`); its `gpt-5.2` systems and every Claude Code system use uppercase
(`ADD-MOVE`, `READ-WORD`). GnuCOBOL accepts both.

### What does not separate them

| measure | higher for Claude Code | higher for Codex | tie |
|---|---:|---:|---:|
| median paragraph length | 2 | 3 | 0 |
| median paragraph complexity | 4 | 0 | 1 |
| share of paragraphs with complexity 10 or more | 3 | 2 | 0 |
| state changes per 100 lines | 3 | 2 | 0 |
| I/O per 100 lines | 3 | 1 | 1 |
| mean calls out per paragraph | 2 | 3 | 0 |

None of these is consistent across the pairs. Median complexity leans to Claude Code (four pairs and a tie),
but the differences are one or two branches.

## Agent or model?

The study used two Claude models and two Codex models, and several differences follow the model version:

- Both large main-line shares (52%, 40%) are `gpt-5.2`; the three `gpt-5.4` systems have 0 to 5%.
- Lowercase paragraph names appear in all three `gpt-5.4` systems and in neither `gpt-5.2` system.
- Claude Code's single `claude-opus-4-7` system (DOOM-like) does not stand out from its four
  `claude-opus-4-6` systems on these measures.

With one or two systems per model, this sample cannot separate an agent's habits from a model version's. A
comparison meant to characterise "Codex" or "Claude Code" needs several systems per model version.

## What this does not show

- **Quality or correctness.** These are structural measurements. A shared helper is not better or worse than a
  repeated step, and a main line is not a defect. The study evaluates whether each system works.
- **A general rule.** Five pairs, one run per agent per task, with specifications shared "to varying degrees" and
  difficulty ratings that differ within some pairs (compressor: Low for Claude Code, High for Codex).
- **The other study systems.** Three families are excluded for licensing; a full comparison needs them.

## Reproduce

```bash
# a GitGalaxy checkout with the #7170 fix (PR #7172) and the #7169 fix (PR #7183)
ENGINE=/path/to/gitgalaxy WORK=/path/to/work ./fetch_scan.sh
python measure.py --repos $WORK/repos --scans $WORK/scans --out data/
```

`data/profile.json` holds every per-system number above. The scan checks use GitGalaxy's
`tests/tools/cobol_answer_key.py draft`, `add-extents` and `score` per repository, with the checkout's
`gitgalaxy` on `PYTHONPATH`.

"DOOM" is used descriptively; this project is not affiliated with id Software, ZeniMax Media or Microsoft, nor
with Anthropic's or OpenAI's evaluation of their agents. The systems were written by Claude Code and Codex in
Mathieu Acher's study; credit for building and validating them is the study's.
