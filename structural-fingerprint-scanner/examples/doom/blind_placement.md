# Blind placement: does structure alone put a translation's functions in DOOM's subsystems?

`sfs subway` places each port function in one of linuxdoom's 16 subsystems by structural
twin, then by function name, then by file-path rules. Twins do not match across languages,
so for the translations (doom-scheme, gore, dartdoom, mochadoom, kocoa-doom, managed-doom,
doomf77) the published maps and wiring similarities come almost entirely from names and
paths. This study places every function **without** names, paths or any string, using only
what the engine extracted, and scores the result against the name/path placement.

Engine 6c7c6c1bc scans, reference linuxdoom, taxonomy `subsystems.json`, `min_loc` 3
(as `sfs subway`). Measurements only; no port source is reproduced. Raw results:
[`blind_placement.json`](blind_placement.json) (the main method) and
[`blind_placement_lift.json`](blind_placement_lift.json) (the post-hoc lift rule, see below).
Code: `src/structural_fingerprint/blind.py`, tests `tests/test_blind.py`.

## Verdict

* **Placement: partly yes, for the close translations.** Structure alone recovers the
  name/path placement far above chance for gore (Go; kappa 0.50, balanced accuracy 0.45
  against a null of 0.07), and clearly but more weakly for dartdoom and doom-scheme (kappa
  0.31 and 0.26). For mochadoom, kocoa-doom, managed-doom and doomf77 the signal is
  statistically real but small (kappa 0.03 to 0.17). For the reimplementations it is at
  chance (kappa -0.02 to 0.03), which is what a sound method should report. Across the 14
  ports, blind-placement kappa ranks the ports almost the same way as the published
  off-diagonal wiring (Spearman 0.81, p < 0.001).
* **Wiring: no. Blind wiring is a failure as an independent check.** Computed on the blind
  placement, full wiring is 0.91 to 0.96 for every port, reimplementations and COBOL
  raycasters included. Off-diagonal wiring is 0.50 to 0.64 for rust-doom, room4doom,
  helion and fps-cob, about the same as for the translations (0.51 to 0.78; doomf77 0.14). Rerunning the
  method on a degree-preserving random rewiring of each port's call graph still gives 0.53
  to 0.68 off-diagonal for the translations, so most of the blind off-diagonal wiring is
  produced by the method (who calls whom is predictable from degree and size alone), not
  read from the port. A post-hoc decision rule (lift, below) separates translations from
  reimplementations on full wiring, but it also makes the two COBOL raycasters look like
  DOOM (0.46 and 0.63), and the off-diagonal numbers still do not separate the groups.
* So the published translation wiring numbers stay **names-and-paths results**. Structure
  confirms that the close translations really have DOOM's layout (their functions can be
  put back in place blind, which an unrelated codebase's cannot), but it does not give an
  independent wiring number.

## Method

What the blind placement reads, per function: the lens vector (size, complexity, arity,
vocabulary density, decision density and the 32 signal densities), the engine archetype
(recomputed from those features), and the engine-resolved call edges as pairs of row
indices. It never reads a function name, a file path, a language, a file grouping, or the
row order. `calls_out_to` (callee names) is not used; only `fcall_data` edges are.

1. **Descriptors.** Each lens feature and nine call-graph roles (log in- and out-degree,
   descendants, ancestors, depth below the entry points, height above the leaves,
   PageRank, mean neighbour in/out degree) are replaced by their rank within the
   repository, so a language's overall offsets (Scheme functions are shorter than C's)
   cancel. Archetype is one-hot.
2. **Alignment.** Entropic fused Gromov-Wasserstein between the port and linuxdoom, uniform
   marginals: a soft many-to-many coupling that matches descriptors and keeps functions a
   few calls apart in the port a few calls apart in linuxdoom (undirected hop distance,
   capped at 4). Alpha 0.5, epsilon 0.01, 40 mirror-descent steps.
3. **Vote.** Each port function's coupling mass is summed per linuxdoom subsystem (the
   reference's own path labels define the subsystems), smoothed over the port's call graph
   (label propagation, 0.3, three steps), and the largest subsystem wins (`argmax`).

Hyperparameters were tuned on **chocolate-doom only** (C, the same-language sanity port):
a grid of about 35 settings over alpha, epsilon, hop cap and k for the kNN baseline, then lens
weighting and smoothing. Nothing was tuned on a translation or a negative. The best
chocolate-doom accuracies were within 0.05 of each other over most of the grid.

**Answer key**: `subway.assign`'s placement. Only functions it placed by **name** or **path**
are scored (twin-placed ones are reported separately; fallback ones are unscored). The key
is noisy, especially path-placed functions in ports whose layout is not DOOM's.

**Nulls.**
* *Shuffle*: the blind labels permuted across the scored functions, 2,000 draws. This
  keeps the blind subsystem sizes, so a method that sends everything to playsim gets no
  credit for it. Kappa = (accuracy − null mean) / (1 − null mean).
* *Balanced accuracy*: mean per-subsystem recall over subsystems with ≥ 5 key functions,
  with its own shuffle null (500 draws).
* *Rewired graph*: the whole method rerun on a degree-preserving random rewiring of the
  port's call graph (directed double-edge swaps, 10 per edge; 2 draws). It keeps every
  function's measurements and degrees and destroys who calls whom. Whatever survives it
  comes from measurements and degrees alone.
* For wiring also *rename*: the blind partition kept, its 16 subsystem names permuted.

Runtime: 14 ports with ablations and nulls, about 25 minutes with two workers of two
threads (helion's 8,386 functions dominate).

## 1. Placement accuracy

Main method (argmax), scored functions only.

| port | functions | scored | accuracy | shuffle null (p95) | kappa | balanced acc | its null | rewired-graph acc | name-placed acc | path-placed acc |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| chocolate-doom (C, sanity) | 5129 | 4082 | **0.50** | 0.21 (0.22) | 0.37 | 0.35 | 0.06 | 0.39 | 0.77 | 0.35 |
| gore (Go) | 996 | 723 | **0.60** | 0.20 (0.22) | **0.50** | **0.45** | 0.07 | 0.39 | 0.61 | (8 fns) |
| dartdoom (Dart) | 723 | 707 | **0.48** | 0.24 (0.26) | 0.31 | 0.26 | 0.07 | 0.35 | 0.64 | 0.20 |
| doom-scheme (Scheme) | 798 | 665 | **0.46** | 0.26 (0.28) | 0.26 | 0.24 | 0.08 | 0.37 | 0.54 | 0.23 |
| managed-doom (C#) | 1285 | 1058 | 0.47 | 0.37 (0.38) | 0.17 | 0.15 | 0.10 | 0.43 | 0.74 | 0.32 |
| doomf77 (Fortran) | 146 | 146 | 0.42 | 0.39 (0.42) | 0.06 | 0.17 | 0.12 | 0.45 | 0.55 | 0.41 |
| mochadoom (Java) | 3037 | 2698 | 0.20 | 0.17 (0.17) | 0.05 | 0.11 | 0.07 | 0.18 | 0.37 | 0.13 |
| kocoa-doom (Kotlin) | 2902 | 2638 | 0.19 | 0.16 (0.17) | 0.03 | 0.09 | 0.07 | 0.18 | 0.31 | 0.11 |
| rust-doom (reimpl.) | 582 | 344 | 0.08 | 0.10 (0.11) | −0.02 | 0.15 | 0.19 | 0.09 | 0.22 | 0.08 |
| room4doom (reimpl.) | 4582 | 2378 | 0.27 | 0.24 (0.25) | 0.03 | 0.12 | 0.08 | 0.26 | 0.50 | 0.23 |
| helion (reimpl.) | 8386 | 5211 | 0.30 | 0.32 (0.32) | −0.02 | 0.08 | 0.09 | 0.32 | 0.54 | 0.29 |
| cssdoom (reimpl.) | 217 | 192 | 0.20 | 0.18 (0.20) | 0.03 | 0.18 | 0.17 | 0.19 | (5 fns) | 0.18 |
| agentic-cobol-doom-cc | 45 | 44 | 0.25 | 0.24 (0.27) | 0.02 | 0.32 | 0.31 | 0.20 | (1 fn) | 0.23 |
| fps-cob | 51 | 3 | (3 scored) | | | | | | | |

Shuffle-null p-values: < 0.001 for chocolate-doom, all four close translations,
managed-doom, mochadoom, kocoa-doom and room4doom; 0.05 for doomf77; 0.11 cssdoom, 0.52
agentic-cobol-doom-cc; rust-doom and helion are *below* their null. With thousands of
functions a kappa of 0.03 is "significant"; it is not useful. room4doom (kappa 0.03,
balanced 0.12 vs 0.08) is no worse than mochadoom and kocoa-doom, so for the Java and Kotlin
ports structure alone cannot tell a translation from a reimplementation.

Readings:

* **Confidence is informative.** In the quarter of scored functions with the most
  concentrated vote, accuracy is 0.99 (gore), 0.97 (dartdoom), 0.96 (chocolate-doom),
  0.82 (doom-scheme), 0.74 (managed-doom), against 0.16 to 0.45 for the reimplementations.
  Much of that confident quarter is playsim, so read it with the per-subsystem table.
* **The call graph carries a real part.** On a rewired graph, accuracy falls from 0.60 to
  0.39 (gore), 0.48 to 0.35 (dartdoom), 0.46 to 0.37 (doom-scheme), 0.50 to 0.39
  (chocolate-doom). The rest (still well above the shuffle null) comes from measurements and
  degrees.
* **Name-placed functions agree far more than path-placed ones** (gore 0.61 vs n/a,
  dartdoom 0.64 vs 0.20, doom-scheme 0.54 vs 0.23, chocolate-doom 0.77 vs 0.35). Either the
  path rules are the noisier half of the key, or the functions that kept linuxdoom's names
  are the ones that kept its structure; this study cannot tell which.
* chocolate-doom's twin-placed functions (403) are placed correctly 91% of the time: the
  blind method agrees with the name-blind twin search where both apply.

### Per subsystem (recall / precision, key size), main method

| port | renderer | playsim | game | menu/misc | hud | automap | intermission | finale | sound | system |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| chocolate-doom | 0.88 / 0.62 (249) | 0.80 / 0.65 (1581) | 0.30 / 0.55 (224) | 0.43 / 0.38 (287) | 0.51 / 0.23 (121) | 0.64 / 0.65 (137) | 0.29 / 0.05 (17) | 0.54 / 0.61 (52) | 0.29 / 0.48 (108) | 0.21 / 0.27 (409) |
| gore | 0.73 / 0.75 (73) | 0.96 / 0.67 (244) | 0.45 / 0.72 (29) | 0.40 / 0.47 (63) | 0.29 / 0.63 (134) | 0.58 / 0.86 (33) | 0.65 / 0.88 (34) | 0.14 / 1.00 (22) | 0.73 / 0.85 (15) | 0.16 / 0.15 (38) |
| dartdoom | 0.31 / 0.44 (100) | 0.87 / 0.69 (290) | 0.33 / 1.00 (30) | 0.50 / 0.42 (30) | 0.33 / 0.09 (21) | 0.27 / 0.50 (30) | 0.19 / 0.31 (21) | 0.20 / 0.43 (15) | 0.01 / 0.14 (107) | |
| doom-scheme | 0.35 / 0.57 (88) | 0.87 / 0.53 (252) | 0.14 / 0.50 (37) | 0.00 / 0.00 (21) | 0.29 / 0.27 (41) | 0.19 / 0.58 (37) | | 0.10 / 0.50 (20) | 0.00 / 0.00 (37) | 0.23 / 0.40 (70) |
| mochadoom | 0.11 / 0.44 (541) | 0.85 / 0.22 (525) | 0.01 / 0.17 (114) | 0.03 / 0.10 (205) | 0.11 / 0.08 (85) | 0.05 / 0.11 (83) | 0.19 / 0.24 (27) | 0.00 / 0.00 (30) | 0.02 / 0.31 (270) | 0.03 / 0.04 (151) |
| managed-doom | 0.18 / 0.46 (121) | 0.88 / 0.61 (523) | 0.04 / 0.60 (72) | 0.03 / 0.11 (70) | | | 0.10 / 0.38 (48) | | 0.00 / 0.00 (14) | 0.13 / 0.21 (89) |
| room4doom | 0.04 / 0.30 (775) | 0.79 / 0.33 (736) | 0.04 / 0.42 (132) | 0.00 / 0.00 (38) | 0.02 / 0.01 (51) | 0.05 / 0.05 (19) | 0.12 / 0.50 (33) | | 0.03 / 0.15 (160) | 0.26 / 0.05 (34) |
| helion | 0.04 / 0.19 (1176) | 0.63 / 0.45 (2405) | 0.00 / 0.00 (29) | 0.01 / 0.04 (557) | 0.06 / 0.00 (18) | 0.00 / 0.00 (21) | | | 0.01 / 0.03 (200) | 0.04 / 0.01 (94) |

gore is the one translation where structure finds most of DOOM's subsystems: renderer,
automap, intermission and sound are each placed with precision 0.75 to 0.88. In the others
the method mostly finds playsim and renderer. Sound fails everywhere outside gore and
chocolate-doom (the ports rewrote audio around their platform's API). The method sends far
too much to playsim (45 to 90% of functions against linuxdoom's 32%), because a diffuse
vote defaults to the largest subsystem.

### Ablations (accuracy / balanced accuracy)

| port | main | no GW structure term | graph roles only | measures only | geometry only | kNN |
|---|---:|---:|---:|---:|---:|---:|
| chocolate-doom | 0.50 / 0.35 | 0.47 / 0.36 | 0.40 / 0.18 | 0.43 / 0.26 | 0.45 / 0.26 | 0.42 / 0.17 |
| gore | 0.60 / 0.45 | 0.62 / 0.44 | 0.48 / 0.27 | 0.41 / 0.17 | 0.60 / 0.46 | 0.44 / 0.18 |
| dartdoom | 0.48 / 0.26 | 0.42 / 0.24 | 0.43 / 0.15 | 0.35 / 0.12 | 0.47 / 0.23 | 0.41 / 0.12 |
| doom-scheme | 0.46 / 0.24 | 0.43 / 0.25 | 0.41 / 0.13 | 0.33 / 0.10 | 0.48 / 0.24 | 0.41 / 0.12 |
| managed-doom | 0.47 / 0.15 | 0.45 / 0.17 | 0.40 / 0.12 | 0.42 / 0.14 | 0.49 / 0.16 | 0.48 / 0.14 |
| mochadoom | 0.20 / 0.11 | 0.19 / 0.15 | 0.20 / 0.09 | 0.18 / 0.11 | 0.19 / 0.09 | 0.20 / 0.12 |
| room4doom | 0.27 / 0.12 | 0.23 / 0.13 | 0.30 / 0.08 | 0.19 / 0.10 | 0.26 / 0.09 | 0.29 / 0.09 |
| helion | 0.30 / 0.08 | 0.23 / 0.07 | 0.29 / 0.08 | 0.37 / 0.10 | 0.31 / 0.07 | 0.33 / 0.09 |

* **Geometry only** (size, complexity, arity, vocabulary and decision density; no signal
  densities, no archetype) does as well as the full lens. The signal densities, the only
  inputs with any lexical content (API-call patterns), are not where the placement comes
  from.
* **Graph roles plus measurements beat either alone**, and the optimal-transport coupling
  beats nearest-neighbour voting (kNN) for every close translation. The explicit
  Gromov-Wasserstein structure term adds little on top of graph-role descriptors (0.43 →
  0.46 doom-scheme, 0.42 → 0.48 dartdoom, none for gore).

## 2. Blind wiring

Wiring = cosine of the 16×16 subsystem call-share matrix with linuxdoom's; off-diagonal
drops within-subsystem calls (linuxdoom's matrix is 54% diagonal).

| port | name/path full | name/path off | blind full | blind off | shuffle null full / off | rename null full / off | rewired-graph full / off |
|---|---:|---:|---:|---:|---:|---:|---:|
| chocolate-doom | 0.95 | 0.83 | 0.96 | 0.78 | 0.86 / 0.39 | 0.17 / 0.12 | 0.92 / 0.63 |
| gore | 0.86 | 0.65 | 0.96 | 0.71 | 0.83 / 0.35 | 0.16 / 0.10 | 0.93 / 0.68 |
| dartdoom | 0.93 | 0.59 | 0.95 | 0.73 | 0.85 / 0.28 | 0.16 / 0.11 | 0.92 / 0.53 |
| doom-scheme | 0.95 | 0.75 | 0.93 | 0.63 | 0.89 / 0.31 | 0.13 / 0.11 | 0.92 / 0.56 |
| managed-doom | 0.72 | 0.10 | 0.93 | 0.61 | 0.89 / 0.20 | 0.12 / 0.07 | 0.92 / 0.64 |
| doomf77 | 0.91 | 0.41 | 0.91 | 0.14 | 0.89 / 0.11 | 0.12 / 0.07 | 0.91 / 0.28 |
| mochadoom | 0.78 | 0.38 | 0.92 | 0.51 | 0.91 / 0.29 | 0.13 / 0.09 | 0.92 / 0.59 |
| kocoa-doom | 0.77 | 0.27 | 0.92 | 0.61 | 0.90 / 0.24 | 0.12 / 0.06 | 0.92 / 0.55 |
| rust-doom | 0.16 | 0.10 | 0.91 | 0.50 | 0.91 / 0.27 | 0.12 / 0.07 | 0.91 / 0.59 |
| room4doom | 0.28 | 0.08 | 0.93 | 0.64 | 0.90 / 0.26 | 0.11 / 0.06 | 0.92 / 0.64 |
| helion | 0.55 | 0.07 | 0.92 | 0.61 | 0.89 / 0.23 | 0.12 / 0.08 | 0.92 / 0.58 |
| cssdoom | 0.50 | 0.26 | 0.91 | 0.33 | 0.90 / 0.32 | 0.13 / 0.07 | 0.91 / 0.30 |
| fps-cob | 0.08 | 0.00 | 0.92 | 0.56 | 0.88 / 0.13 | 0.13 / 0.05 | 0.91 / 0.10 |
| agentic-cobol-doom-cc | 0.50 | 0.02 | 0.91 | 0.08 | 0.89 / 0.05 | 0.10 / 0.03 | 0.91 / 0.27 |

This is the failure the brief asked to look for: **the blind method makes everything look
like DOOM.** Full wiring is 0.91 to 0.96 for every port because the blind map is mostly
playsim, and a matrix dominated by the playsim→playsim cell resembles linuxdoom's. The
off-diagonal number beats the shuffle null for nearly every port, reimplementations
included, and is about as high on a randomly rewired graph as on the real one. Both are
properties of the method (it places high-in-degree utilities in the subsystems linuxdoom's
utilities live in, so random calls into them already look like linuxdoom's cross-calls),
not evidence about the port. Across ports, blind and name/path wiring rank-correlate only
weakly (Spearman 0.49 on both full and off-diagonal, p ≈ 0.08, n = 14).

## 3. A post-hoc variant: the lift decision rule

Because the argmax rule over-fills playsim, I also tried assigning each function to the
subsystem whose vote is largest **relative to that subsystem's share of linuxdoom**
(`--decision lift`). On chocolate-doom, the tuning port, lift has the same balanced
accuracy (0.35) and lower raw accuracy (0.33 vs 0.50), so by the pre-registered rule it was
not chosen. I ran it on everything **after** seeing the main results, so treat it as
exploratory.

| port | balanced acc (null) | kappa | blind full | blind off | rewired full / off |
|---|---:|---:|---:|---:|---:|
| chocolate-doom | 0.35 (0.06) | 0.27 | 0.79 | 0.77 | 0.34 / 0.65 |
| gore | **0.58** (0.07) | 0.48 | **0.89** | 0.79 | 0.40 / 0.61 |
| dartdoom | 0.29 (0.07) | 0.21 | 0.74 | 0.81 | 0.35 / 0.60 |
| doom-scheme | 0.33 (0.06) | 0.22 | 0.54 | 0.61 | 0.24 / 0.45 |
| doomf77 | 0.20 (0.07) | 0.08 | 0.21 | 0.32 | 0.34 / 0.52 |
| mochadoom | 0.17 (0.06) | 0.06 | 0.42 | 0.47 | 0.26 / 0.43 |
| kocoa-doom | 0.14 (0.06) | 0.04 | 0.26 | 0.40 | 0.21 / 0.40 |
| managed-doom | 0.13 (0.07) | 0.08 | 0.41 | 0.45 | 0.24 / 0.48 |
| rust-doom | 0.03 (0.05) | 0.01 | 0.09 | 0.20 | 0.13 / 0.28 |
| room4doom | 0.09 (0.07) | 0.02 | 0.29 | 0.53 | 0.23 / 0.44 |
| helion | 0.07 (0.07) | −0.00 | 0.28 | 0.52 | 0.26 / 0.55 |
| cssdoom | 0.05 (0.06) | 0.00 | 0.16 | 0.25 | 0.21 / 0.27 |
| fps-cob | (3 scored) | | 0.46 | 0.45 | 0.23 / 0.25 |
| agentic-cobol-doom-cc | 0.14 (0.08) | 0.09 | 0.63 | 0.37 | 0.39 / 0.28 |

With lift, gore's placement improves (balanced accuracy 0.58; renderer, menu/misc, hud
and playsim precision 0.73 to 0.99), and **full** blind wiring now tracks the name/path
wiring for the 12 non-COBOL ports (Spearman 0.69, p = 0.01) and sits well above the
rewired-graph null for the close translations (gore 0.89 vs 0.40). But it still fails the
negatives: the two COBOL raycasters, with 45 and 51 functions, get 0.46 and 0.63, above
mochadoom and managed-doom. Off-diagonal blind wiring is still mostly manufactured
(rewired 0.40 to 0.65; room4doom and helion 0.52 to 0.53, close to doom-scheme's 0.61).
Lift is the more promising rule for future work, with its own tuning set.

## What did not work

* **kNN on fingerprints** (nearest linuxdoom functions in the descriptor space): accuracy
  0.41 to 0.44 on the close translations, and balanced accuracy only 0.12 to 0.18. A
  function's own measurements say little about which subsystem it is in.
* **Lens weighting** (multiplying the ranked features by the portable lens weights)
  lowered chocolate-doom accuracy (0.47 vs 0.48). It is off by default (`--lens-weights`).
  After rank normalization the lens matters little.
* **Strong label propagation** (0.5, tried with kNN voting on chocolate-doom) homogenizes
  neighbourhoods: off-diagonal wiring drops from 0.54 to 0.22 for a 0.01 accuracy gain.
* **Large structure weight** (alpha 0.9) or large epsilon (0.03) blurs the coupling:
  chocolate-doom accuracy falls to 0.37 to 0.43, and at alpha 0.9 with epsilon 0.03 the
  map loses its cross-subsystem calls altogether.

## Limits and leakage

Guarded against, and tested (`tests/test_blind.py`):

* The placement reads a `BlindView` that holds no names, paths or languages. A test garbles
  every name and path and gets identical labels, and a second test shuffles the rows and
  gets the same labels permuted (rows are grouped by file, so row order would be a path
  proxy).
* `calls_out_to` is never read; no port name is compared with any linuxdoom name.
* Hyperparameters were tuned on chocolate-doom only.

Not ruled out:

* **Call resolution uses names inside the port.** The engine resolves a call by matching
  the callee name against the port's own functions, possibly preferring the same file or
  module. The edge set therefore partly encodes file modularity, and the answer key's path
  half is per file. The method may be rewarded for recovering files rather than DOOM's
  subsystems. This is inherent to using the call graph; it is still structure the engine
  extracted, and no string crosses from port to reference.
* **The code/non-code filter uses the file's language** (as `sfs subway` does). It decides
  which functions are on the map, not where they go.
* **Signal densities include API-call patterns** (`arch_io`, `arch_api`,
  `arch_ui_framework`), which are lexical. The geometry-only ablation, which drops all of
  them, scores the same, so they are not the source of the result.
* **The answer key is noisy**, and its noise is not uniform: path rules on a port whose
  layout is not DOOM's (the reimplementations, the Java packages) are weak, and on
  reimplementations low agreement could be either "structure does not match DOOM" or "the
  key is wrong". The study measures agreement with the published placement, not truth.
* **Uniform marginals** in the transport assume the port's subsystems are about as large
  as linuxdoom's. That is false for ports with large new subsystems (helion's, room4doom's
  tools), and it biases the blind sizes towards linuxdoom's.
* **Small ports** (doomf77 146 functions, the COBOL raycasters 45 to 51, fps-cob only 3
  scored) give wide nulls; their numbers mean little.
* The lift rule (section 3) was chosen after seeing results.

Reproduce:

```
OMP_NUM_THREADS=2 python -m structural_fingerprint.blind WORK/scans/6c7c6c1bc \
  --reference linuxdoom --taxonomy examples/doom/subsystems.json \
  --ports helion,room4doom,chocolate-doom,mochadoom,kocoa-doom,doom-scheme,gore,dartdoom,managed-doom,doomf77,rust-doom,cssdoom,fps-cob,agentic-cobol-doom-cc \
  --ablations --rewire-draws 2 --workers 2 -o examples/doom/blind_placement.json
# exploratory: add --decision lift (without --ablations) -o examples/doom/blind_placement_lift.json
```
