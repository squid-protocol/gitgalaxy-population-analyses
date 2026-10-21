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
python tests/tools/doom_speedrun/lineage.py --work WORK --sha <engine-sha>   # source-text verdicts (gitgalaxy)
sfs compare WORK/scans/<engine-sha> -o report --declared-lineage examples/doom/declared_lineage.csv \
    --subway-reference linuxdoom --taxonomy examples/doom/subsystems.json \
    --crosscheck WORK/results/<engine-sha>/lineage/survival_functions.csv
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

### Subway maps

`sfs subway WORK/scans/<engine-sha> -o subway --reference linuxdoom --taxonomy examples/doom/subsystems.json`
(14 s) draws every port's call graph over linuxdoom's 16 subsystems. Calls kept (the
share of linuxdoom's 1,594 calls still made between the corresponding functions) and
wiring similarity follow lineage where structure no longer does:

| port | language | calls kept | wiring | shared structure with linuxdoom |
|---|---|---:|---:|---:|
| mood | C + COBOL | 99.9% | 0.99 | 36% |
| puredoom | C (single header) | 93% | 0.97 | 26% |
| sdl-doom, doom-ascii, doomgeneric | C | 84–85% | 0.98–0.99 | 51–54% |
| doom3-bfg | C++ | 83% | 0.32 | 0% |
| gore | Go | 77% | 0.86 | 0% |
| chocolate-doom | C | 72% | 0.95 | 31% |
| doom-scheme | Scheme | 49% | 0.95 | 0% |
| dartdoom | Dart | 41% | 0.93 | 0.1% |
| mochadoom | Java | 35% | 0.81 | 4% |
| managed-doom | C# | 21% | 0.73 | 0% |

(Shared structure is the Wilson lower bound used by the descent tree.)

**Is this an artefact of the subsystem mapping?** No. A mapping-free summary of each
port's raw call graph (degree, components, clustering, reciprocity, hub concentration…)
ranks the ports the same way: Spearman ρ = −0.77 between wiring similarity and
graph-shape distance from linuxdoom (n = 42, p = 2×10⁻⁹). Per-port taxonomy overrides
for the ports whose folders say what they are lower Mocha Doom's and Kocoa Doom's
unmapped share from 35% and 33% to 10%, and raise their wiring similarity from 0.59 and
0.52 to 0.81 and 0.75. The Java and Kotlin translations kept linuxdoom's wiring far
better than file names alone could show. The remaining large "other" stations are new
code: gzdoom's scripting VM, doom3-bfg's own engine, doomsday's libraries and
room4doom's editor tools.

Two readings stand out. Translations (Go, Scheme, Dart, Java, C#) rewrite every
measurement, so descent cannot see them, but they keep the call wiring: gore keeps 77%
of linuxdoom's calls. And doom3-bfg, a separate engine, ships DOOM Classic converted to
C++ (`doomclassic/doom/`). The conversion shifts the measurements enough to defeat twin
matching, but 83% of the calls survive. Station colours show which subsystems survive
structurally: in Chocolate and Crispy Doom, playsim and renderer stay warm while
platform and system code cool.

### Subsystems across languages

Comparing each port's subsystems with linuxdoom's same subsystems, over the ports that
kept linuxdoom's wiring (calls kept ≥ 30%, so the algorithm is the same), gives this
median subsystem distance (1.0 = a typical cell):

| language | ports | median distance | drift that recurs most |
|---|---:|---:|---|
| C | 16 | 0.79 | def_encapsulation +, def_freeze_hits +, log_args + |
| C++ | 3 | 0.85 | arch_api −, def_freeze_hits +, log_args + |
| Scheme | 1 | 1.12 | struct_func_start −, struct_args −, arch_api − |
| Java | 1 | 1.14 | struct_decorators +, log_loc −, state_pointers − |
| Dart | 1 | 1.47 | def_encapsulation +, struct_linear −, log_args + |
| Go | 1 | 1.62 | def_encapsulation +, struct_linear −, state_cast_hits + |

Go and Dart drift mostly on encapsulation (gore +3.8 population IQRs) and linear
structure (−1.9) although their wiring is linuxdoom's. That is a lead for engine
calibration: whether Go receivers and Dart accessors are being counted as encapsulation
where C has none. The report lists every such cell under "Calibration candidates". C
ports themselves drift towards more arguments per function (+1.1 IQR in Chocolate and
Crispy), which fits the study's finding that ports decompose the original.

### Cross-check against source text

`lineage.py` (gitgalaxy `tests/tools/doom_speedrun/`) reads the source and classifies
each of linuxdoom's functions in each of 30 ports by normalized body: exact, near
(token similarity ≥ 0.9), derived (≥ 0.6), name-only or gone. Scored against it, with
"exact or near" as surviving, over 19,380 function × port pairs:

| `--fdr` | precision | recall | twins of unrelated functions | port-level Spearman ρ |
|---|---:|---:|---:|---:|
| 0.01 (default) | 92% | 61% | 3.4% | 0.78 |
| 0.05 | 76% | 71% | 12.7% | 0.91 |
| 0.10 | 69% | 73% | 17.1% | 0.92 |

At the default, 57% of the twins are exact source copies, 35% near and 5% derived. By
subsystem, precision is 96% in playsim, 91% in the renderer and 98% in the zone
allocator, and weakest in netcode and platform code, where functions are small and
generic. Recall is lowest in three ports, each for a known reason: doom3-bfg (its DOOM
Classic was converted to C++, which changes the measurements), doom-ios (its headers are
labelled Objective-C, gitgalaxy#5876), and prboom-plus, where the pair shares too little
code to certify a threshold at 1% (recall 9% at 1%, 48% at 5%).

### Drift over time

`sfs timeline` fingerprinted four ports once a year through their full git history
(81 snapshots, each scanned once and cached by commit; re-scoring the cached series
takes under two minutes) against
linuxdoom, with the subsystem taxonomy and two events taken from the histories
(`timeline_events.csv`: Chocolate's `src/heretic` first appears on 2008-09-04; Crispy
Doom's first own commit is 2014-03-04):

```bash
sfs timeline --repo chocolate-doom=history/chocolate-doom --repo crispy-doom=history/crispy-doom \
    --repo prboom-plus=history/prboom-plus --repo woof=history/woof \
    --reference report/fingerprints/linuxdoom.sfp.json --engine <gitgalaxy checkout> \
    --python <engine venv>/bin/python --every 1y --taxonomy examples/doom/subsystems.json \
    --events examples/doom/timeline_events.csv -o timeline
```

| port | first snapshot | linuxdoom survival then → now | calls kept then → now | size then → now |
|---|---|---:|---:|---:|
| chocolate-doom | 2005-07 | 85% → 57% | 95% → 76% | 710 → 5,149 functions |
| crispy-doom | 2005-07 (shared) | 85% → 43% | 95% → 73% | 710 → 5,894 |
| prboom-plus | 2001-02 | 17% → 13% | 62% → 60% | 1,153 → 2,439 |
| woof | 2008-06 | 19% → 12% | 71% → 50% | 969 → 3,893 |

- **Chocolate and Crispy share their history up to the fork** and coincide until 2013.
  From 61% each in 2013, Chocolate lost 4 points of linuxdoom survival by 2026 and
  Crispy 18, about four times as much, while keeping nearly the same wiring (73%
  against 76% of calls): Crispy changes function bodies, not the call structure.
- **Chocolate's biggest drop is its first year** (85% → 68%), long before Heretic,
  Hexen and Strife arrive, as the port replaced linuxdoom's platform layer.
- **Woof modernises fast after 2020.** It quadruples in size (1,000 → 3,900 functions),
  its calls kept falls from 71% to 50%, and its design distance from linuxdoom nearly
  doubles.
- **prboom-plus barely moves** after its 2007–08 restructuring.

Twins against the reference use **one threshold per repository**, calibrated over all
its snapshots together. With per-snapshot thresholds, a port that shares about a
hundred candidate twins with linuxdoom sits right at the edge of what the +1 correction
can certify at 1%, and its survival flipped between 16% and 3% from one year to the
next. The pooled thresholds came out at 0.046–0.056 for all four ports, close to what
large pairs certify on their own. Survival counts a twin found in either direction:
Chocolate carries Doom, Heretic, Hexen and Strife side by side after 2008, and the
reference-side search alone showed a false collapse to 2%.

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
