# Read a similarity score against chance

A methods note from the 44-port DOOM study. Measurements only; no port's source is reproduced. "DOOM" is used
descriptively; this project is not affiliated with id Software, ZeniMax Media or Microsoft.

## The number that looked like a finding

doomf77 is a Fortran translation of DOOM. It keeps almost none of the original's function names (1%), yet its call
wiring scored **0.91** against linuxdoom's, on a 0–1 scale. That reads as a striking result: the architecture
survives a translation into a 1970s language with every name changed. We quoted it.

Then we shuffled doomf77's own functions across the subsystems at random and scored it again. It still scored
**0.80**. Almost all of the 0.91 was there before any function was placed where it belongs.

## Why the score had a floor

`sfs subway` collapses a call graph to subsystems (renderer, playsim, sound, ...: 16 of them for DOOM) and counts
the calls from each subsystem to each other one. *Wiring similarity* is the cosine between that 16 × 16 matrix and
the reference's.

Most calls in a well-organised program stay inside their own subsystem: in linuxdoom, 54% of calls are on the
matrix's diagonal. A cosine against a matrix that heavy on the diagonal rewards any program that keeps its calls
local, whatever it does. A made-up program whose calls *only* stay inside their subsystem, spread evenly, scores
**0.47** against linuxdoom without sharing anything else with it. That is the score's floor, and it is a property
of the reference, computable before looking at any port (`wiring_floor` in `subway.json`).

## Two corrections

**Score what is specific.** `cross_wiring` is the same cosine over the calls *between* subsystems only: the
diagonal, which every program fills, is dropped. Cross-module calls (playsim calling the renderer, the game loop
calling sound) are where a design shows.

**Compare each port with itself, shuffled.** `cross_wiring_null` keeps the port's call graph and its subsystem
sizes and shuffles which function sits in which subsystem, 200 times (seeded). Its mean is what that call graph
scores with the placement carrying no information. The gap between the real score and the null is what the
placement explains. A gap near zero means the score came from the graph's shape and the subsystem sizes, not from
the port keeping the reference's architecture.

## What changed

| port | what it is | wiring | cross wiring | cross null | gap |
|---|---|---:|---:|---:|---:|
| chocolate-doom | C fork | 0.95 | 0.83 | 0.32 | **+0.51** |
| doom-scheme | Scheme translation | 0.95 | 0.75 | 0.24 | **+0.51** |
| gore | Go translation | 0.86 | 0.65 | 0.15 | **+0.50** |
| dartdoom | Dart translation | 0.93 | 0.59 | 0.40 | +0.19 |
| doomf77 | Fortran translation | 0.91 | 0.41 | 0.36 | +0.05 |
| mochadoom | Java translation | 0.78 | 0.38 | 0.37 | +0.01 |
| kocoa-doom | Kotlin translation | 0.77 | 0.27 | 0.35 | −0.08 |
| managed-doom | C# translation | 0.72 | 0.10 | 0.25 | −0.15 |
| rust-doom | from-scratch reimplementation | 0.16 | 0.10 | 0.04 | +0.06 |
| room4doom | from-scratch reimplementation | 0.28 | 0.08 | 0.08 | 0.00 |
| helion | from-scratch reimplementation | 0.55 | 0.07 | 0.16 | −0.08 |
| Quake II | unrelated C engine (GPL-2) | 0.24 | 0.11 | 0.09 | +0.02 |
| WinQuake | unrelated C engine (GPL-2) | 0.12 | 0.05 | 0.07 | −0.03 |
| Lua | unrelated C program (MIT) | 0.08 | 0.00 | 0.00 | 0.00 |

The last three rows are negative controls: programs with no DOOM code, scanned with the same engine and placed on
linuxdoom's subsystems the same way (mostly by file path or the fallback, since they share few names).

By raw wiring, every translation looked like it kept DOOM's architecture (0.72 to 0.95). Against chance, two do as
strongly as a C fork (Scheme and Go), one partly (Dart), and four show nothing (Fortran, Java, Kotlin, C#). The
reimplementations and the unrelated programs sit at chance, as they should.

## What the null does not fix

The null tells you whether a placement carries information. It does not tell you where the placement came from.
Here a translation's functions are placed by name, then by file path, because structural twins do not match across
languages. A gap of zero for mochadoom can mean the Java port lost the wiring or that name-and-path placement failed
on a port that renamed and reorganised the most; this table cannot tell those apart.

A placement made from structure alone, with names and paths withheld (`examples/doom/blind_placement.md`), agrees
with the name/path placement well above chance for gore, dartdoom and doom-scheme (Cohen's κ 0.50, 0.31, 0.26) and
barely for the Java, Kotlin and C# ports (κ 0.03 to 0.17). It does not settle their case either. And the wiring
computed from that blind placement fails its own null: it makes reimplementations and COBOL raycasters look like
DOOM, because aligning a call graph to the reference imposes the reference's shape. The same four checks apply to a
new method as to an old score.

## The general lesson

Any code-similarity score should come with four things:

1. **Its floor.** Work out what a trivial or generic input scores. A cosine over a few dimensions that one pattern
   dominates is high for nearly everything.
2. **A null from the same object.** Shuffle the thing the score claims to measure (here, the placement) and keep
   everything else. Report the gap, not the score.
3. **Negative controls from outside the population.** Comparing DOOM ports only with other DOOM ports cannot show a
   baseline. Unrelated programs of the same era and language can.
4. **The assignment's provenance.** If the score depends on a mapping (names, paths, a taxonomy), say how each item
   was mapped, as `assigned_by` does, so a reader can see what the score leans on.

## Reproduce

```bash
sfs subway SCANS -o subway --reference linuxdoom --taxonomy examples/doom/subsystems.json
# subway.csv: wiring_similarity, cross_wiring, wiring_null, cross_wiring_null; subway.json: wiring_floor
```

The DOOM scans are produced by gitgalaxy's `tests/tools/doom_speedrun/doom_speedrun.py run` at the pinned SHAs of
its manifest (engine 6c7c6c1bc for the numbers above).
