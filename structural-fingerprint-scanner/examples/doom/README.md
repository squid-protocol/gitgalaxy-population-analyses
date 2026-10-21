# Validation: 44 DOOM ports

DOOM is a natural benchmark for lineage tools. id Software released the engine's source
in 1997, and three decades of ports descend from it, many with documented ancestry. The
corpus is the 44 clearly licensed ports pinned in GitGalaxy's DOOM-rosetta manifest
(`tests/doom_rosetta/manifest.csv` in the gitgalaxy repository). They span C, C++, C#,
Java, Kotlin, Go, Rust, Dart, Crystal, F#, Scheme, Fortran, JavaScript, PostgreSQL,
COBOL and assembly. Every number below is a measurement from scan output. No port's
source is reproduced here. "DOOM" is used descriptively; this project is not affiliated
with id Software, ZeniMax Media or Microsoft.

`declared_lineage.csv` records each port's stated ancestry. Where the direct parent is
not in the corpus (Boom, MBF, ZDoom), the nearest ancestor that is in it is used.

## Reproduce

```bash
# 1. scan the pinned ports with GitGalaxy (engine 9f213ab83 for the numbers below)
python tests/tools/doom_speedrun/doom_speedrun.py fetch --work WORK
python tests/tools/doom_speedrun/doom_speedrun.py scan  --work WORK
# 2. compare
sfs compare WORK/scans/<engine-sha> -o report --declared-lineage examples/doom/declared_lineage.csv
sfs compare WORK/scans/<engine-sha> -o report-portable --lens portable --no-twins
```

The full comparison (44 fingerprints, 1,892 directed twin searches, both trees) takes
about 5.5 minutes and 1.5 GB on a 6-core laptop.

## Results (engine 9f213ab83, lens `structure`)

### The engine's labels are reproduced exactly

Recomputing every function's archetype from the scan's raw measurements gives the
label the engine stored for 100% of functions on every port tested. The scanner's
coordinates are the engine's own.

### Twins are precise without names

Names are not used to match. Across all 88,036 twins in pairs where names are
comparable, **87.7%** of twins join functions of the same name. In high-survival pairs
agreement is 94–99.8%:

| query → target | survival | name agreement |
|---|---:|---:|
| linuxdoom → sdl-doom | 57.3% | 98.7% |
| linuxdoom → doomgeneric | 56.9% | 98.7% |
| linuxdoom → doom-ascii | 54.3% | 99.1% |
| linuxdoom → doom-wasm | 52.5% | 98.0% |
| linuxdoom → chocolate-doom | 34.3% | 94.0% |
| linuxdoom → crispy-doom | 19.2% | 90.8% |
| linuxdoom → fastdoom | 15.1% | 89.1% |

Agreement weakens where survival is in the low single digits (dsda-doom 50%,
nugget-doom 20%). Twin calls near the threshold in heavily rewritten pairs are the
least reliable, and the per-pair `name_agreement` column shows where.

These survival figures track an independent comparison made earlier from source text,
which counted linuxdoom function bodies that remain identical after normalization:
35.1% in Chocolate Doom (scanner: 34.3%) and 21.1% in Crispy Doom (scanner: 19.2%). The
scanner never sees source.

### Descent recovers declared families

Of the 23 ports with detectable shared structure, **74%** have a declared ancestor,
descendant, sibling or cousin as their nearest neighbour in the descent tree:
crispy↔chocolate, dsda→prboom-plus, nugget↔woof, fastdoom/mood/mochadoom/puredoom→linuxdoom,
and so on. The 19 ports with no detectable shared structure (below 2%) are the rewrites
into other languages and the independent engines. That is the expected result: a
translation rewrites every measurement.

The six "misses" are informative:

- **eternity → doom-wasm, odamex → doom-wasm.** Every twin in eternity→doom-wasm (193)
  is a function of Chocolate Doom's `textscreen` UI library (`TXT_ButtonDrawer`,
  `TXT_CheckBoxKeyPress`, …), which Eternity adopted. This is code shared sideways
  rather than by descent, found without using names.
- **doomgeneric ↔ sdl-doom** share 89.6% of structure, against 60.7% with the Chocolate
  fork doom-wasm. The manifest's "Chocolate Doom codebase" for doomgeneric was itself
  inferred from copyright headers. Structurally, doomgeneric is a minimal linuxdoom port
  carrying some Chocolate files.
- **srb2 → dsda-doom, doomretro → nugget-doom**: low shared structure (≤6%) between
  heavily rewritten descendants of the same root. Read the twin lists before drawing
  conclusions.

The **profile tree** puts a declared relative nearest for 58%. That is lower by design:
it measures how alike designs are, not inheritance. It groups the vanilla-faithful C
ports, the large C++ engines (gzdoom, doom3-bfg, doomsday, eternity, odamex,
edge-classic) and the small single-file raycasters.

### Across languages (`--lens portable`)

Profiles pair kocoa-doom with mochadoom (Kotlin port of a Java port), room4doom with
rust-doom (both Rust) and fps-cob with the Claude-written COBOL raycaster. Even with
language-tracking signals down-weighted, profile distance still groups largely by
language family and kind of program. It does not recover cross-language ancestry.

### Two AI agents, one COBOL raycaster

The corpus holds two COBOL raycasters from the same study, one written by Claude Code
and one by Codex, plus an independent one (fps-cob). `sfs explain`:

| | Claude Code | Codex | fps-cob |
|---|---|---|---|
| functions (≥3 lines) | 49 | 152 | 51 |
| coding LOC by language | COBOL 1,616 | COBOL 1,910 + C 1,626 | COBOL 2,738 |
| median function size (lines) | 23 | 10 | 37 |
| leading archetype | I/O & Config Routines 73.5% | I/O & Config Routines 50.0% | I/O & Config Routines 82.4% |
| state mutation per 100 function LOC | 52.5 | 20.6 | 40.6 |
| pointer use per 100 function LOC | 0 | 9.6 | 0 |
| call graph: hub share | 0.06 | 0.15 | 0.10 |

Codex split the program into many small functions and moved part of it into C, with
pointers and immutability markers. Claude Code kept to COBOL, with fewer, larger
paragraphs, more state mutation and more I/O.
