# Method

This document specifies what structural-fingerprint-scanner computes, in enough detail
to reproduce every number by hand. The code is the reference; section names match
module names.

## 1. Input: a GitGalaxy scan (`scan_io`)

The scanner reads one table row per function from the scan database
(`*_galaxy_master.db`, opened read-only):

- geometry: `loc`, `complexity` (decision points), `args`, `keyword_density`;
- 32 structural signal counts: the engine's hits for branches, linear structure, arity,
  function and class boundaries, guards and bypasses, I/O, API surface, state mutation,
  tests, concurrency, UI, closures, globals, decorators, generics, comprehensions,
  scientific code, reflection, imports, macros, pointers, allocation, debug output,
  casts, panics/aborts, bitwise operations, immutability, cleanup, encapsulation and
  listeners;
- call fan-in and fan-out, the function's name, file path and language;

plus resolved call edges (`fcall_data`), the repository row and the audit's provenance
fields. Synthetic slices (top-level statements the engine buckets as
`__global_context__`) are not functions and are dropped. A signal column an older
engine did not write reads as zero and is listed under `missing_signals` in the
fingerprint, so a comparison across engine versions is visibly not like-for-like.

## 2. The reference frame (`reference`, `features`)

Each function becomes a 37-dimensional vector, built exactly as the engine builds the
vector it classifies function archetypes with:

| feature | value |
|---|---|
| `log_loc` | log(1 + loc) |
| `log_complexity` | log(1 + complexity) |
| `log_args` | log(1 + args) |
| `keyword_density` | as stored |
| `func_internal_density` | complexity / loc |
| `log_density_<signal>` (×32) | log(1 + min(hits / loc × 100, cap)) |

(`loc` of 0 is treated as 1; the only cap is `def_encapsulation`.) Each feature is then
standardized with the **population** robust scaler, `(x − median) / IQR`, using the
medians and IQRs the engine's function model was fitted with on the GitGalaxy
population corpus (8.2M functions). It is not standardized against the repositories
being compared. A coordinate therefore has the same meaning in every report: "this many
population IQRs from the population median".

The scaler, weights, cap, signal mapping and the 14 archetype centroids are vendored in
`data/reference_function_model.json` together with the engine commit they came from
(`tools/refresh_reference.py` re-extracts them). The fingerprint's `spec_hash` covers
all of it plus the lens. Two fingerprints compare only when their hashes match.

**Archetypes** are assigned with the engine's own weights and nearest-centroid rule,
independent of the lens. On scans made by the reference's engine commit, the
recomputed labels equal the labels the engine stored for every function (the
test suite checks this against real scans with `SFS_REAL_SCANS`).

**Lenses** set the weights that define distance:

- `structure` (default): the engine's weights.
- `portable`: the engine's weights multiplied by each feature's *cross-language
  consistency*, measured on keyword-rosetta (one program planted in 46 languages). A
  feature's consistency is the share of languages whose count of the planted program
  lies within ±25% of the cross-language median, clipped to [0.25, 1]. Features
  rosetta does not plant get 0.5. Features rosetta lists as firing only on mandatory
  idiom get 0.25. `keyword_density` (vocabulary) gets 0 and `log_loc` (verbosity) 0.5.
  Derivation and provenance are in `data/portable_weights.json`
  (`tools/derive_portable_weights.py`). Use it when the cohort spans languages.

## 3. The repository fingerprint (`fingerprint`)

Functions shorter than `--min-loc` (default 3, as the engine's archetype trainer) are
left out. The fingerprint has five components:

1. **archetypes**: share of functions, and of function LOC, per archetype.
2. **signals**: per signal, log(1 + total hits / total function LOC × 100).
3. **geometry**: 21-point quantile sketches (0, 5, …, 100%) of the standardized
   `log_loc`, `log_complexity`, `log_args` and `func_internal_density`, and of
   log(1 + fan-in) and log(1 + fan-out); plus the Gini coefficient of complexity.
4. **centroid**: LOC-weighted mean of the function vectors in the lens space, and the
   LOC-weighted RMS spread around it.
5. **callgraph**: over distinct resolved edges between kept functions: edges per
   function, leaf share (no outgoing edge), root share (no incoming edge), hub share
   (incoming edges held by the top 1% of functions) and reciprocal share (edges whose
   reverse also exists).

The per-function vectors, exact-measurement digests (FNV-1a over loc, complexity,
args and all signal counts), names, paths and languages are saved beside the
fingerprint (`.sfp.npz`) for twin search.

## 4. Repository distance (`compare`)

| component | distance |
|---|---|
| archetypes | Jensen–Shannon distance of the count shares (base 2; 0 to 1) |
| signals | root-mean-square difference of the log densities |
| geometry | mean over the six sketches of the mean absolute quantile difference (≈ 1-Wasserstein) |
| centroid | Euclidean distance / √37 |
| callgraph | Euclidean distance / √5 after log(1 + edges per function) |

For a cohort of three or more, the **profile distance** divides each component by its
median over all pairs in the cohort and takes the weighted mean (`--weights`, default
equal). 1.0 is a typical pair for that cohort. The scale is cohort-relative by design;
the component distances are absolute and stay in `pairs.csv`. `sfs explain A B` lists
the signals, archetypes, geometry and call-graph fields that move most.

## 5. Function twins (`twins`)

For a query repository Q and a target T, over functions of at least `--twin-min-loc`
lines (default 6), in the lens space (Euclidean distance / √37):

1. **Reciprocal best hits.** q's nearest t must have q as its own nearest. This is
   the rule comparative genomics uses to call orthologs.
2. **Ratio test.** d₁ ≤ 0.8 · d₂ (nearest vs second nearest in T); a distance of 0
   needs d₂ > 0.
3. **Target–decoy threshold.** The same search runs against a decoy T′ built by
   permuting each feature independently *within each engine archetype* of T: decoys
   are realistic functions of each kind, but every real function is destroyed. With
   hits sorted by distance, the estimated false-twin rate at threshold t is
   (decoys ≤ t + 1) / (targets ≤ t), made monotone as a q-value. The threshold is the
   largest t with estimate ≤ `--fdr` (default 1%). The +1 means a pair must produce at
   least 1/fdr candidates before anything is certified, so very small repositories
   report no twins rather than chance ones. The decoy permutation is seeded from the
   two repository names, so runs are reproducible.
4. **Exact structural clones.** A function whose exact measurement digest occurs once
   in Q and once in T is a clone. Clones of at least twice the minimum size are
   accepted directly; smaller ones must pass steps 1 to 3.

Names are not used for matching. Afterwards they serve as an independent check:
`name_agreement` is the share of twins whose names agree, among twins whose query name
exists in the target at all; `renamed_twins` counts twins whose name does not exist
there.

**Survival** of Q in T is the share of Q's eligible functions with a twin (also
LOC-weighted). **Shared structure** of a pair is the larger of the two directions'
Wilson 95% lower bounds on survival. The lower bound stops a handful of twins in a tiny
repository from outranking thousands in a large one. Taking the larger direction lets
a small ancestor contained in a large descendant score high.

## 6. Trees and the lineage check (`lineage`)

Both trees are UPGMA (average linkage), written as Newick. The **profile tree** uses
the profile distance and answers "how alike are these designs". The **descent tree**
uses 1 − shared structure and answers "how much code did these inherit or exchange".
Shared structure, like shared DNA, also counts code adopted sideways, such as a
library both projects vendored. The twin lists show which functions carry it.

With `--declared-lineage name,parent`, each tree is checked two ways:

- **nearest is family**: the nearest neighbour is a declared ancestor, descendant,
  sibling or cousin (a shared declared ancestor other than the cohort's root), rather
  than on another branch;
- **parent rank**: the declared parent's rank among the other repositories, *not
  counting the repository's own declared descendants*.

For the descent tree, a repository whose largest shared structure is below
`--min-shared` (default 2%) has no detectable descent in the cohort. It is listed as
such and not scored. Rewrites into another language are the usual case.

## 7. Subway maps (`subway`)

A taxonomy (JSON: ordered subsystems, basename-prefix rules, path-keyword rules, a
fallback) assigns the reference's functions to subsystems by file path. Without a
taxonomy, the reference's most populated top-level directories are the subsystems.
Every other repository's code functions (build, data and docs files are left off) are
placed by, in order: their structural twin in the reference (§5, name-blind), a
reference function of the same normalized name (also without a module prefix such as
`P_`), the path rules, the fallback.

- **Stations** are subsystems, sized by function count. **Lines** are the distinct
  resolved calls between two subsystems, as a share of the repository's
  cross-subsystem calls (shares under 0.4% are not drawn).
- The **layout** is a seeded Fruchterman–Reingold embedding of the reference's
  subsystem call graph, then an overlap-removal pass. Every map uses it.
- **Survival** of a station: the share of the reference's eligible functions in that
  subsystem linked to a twin in either direction. Both directions count, because a
  repository that carries a function twice fails the reference-side ratio test while
  its copies still find the reference.
- **Wiring similarity**: cosine of the subsystem call-share matrices (including calls
  within a subsystem).
- **Calls kept**: the share of the reference's function-level calls u → v whose
  counterparts also call each other. A counterpart is the twin, else the functions of
  the same normalized name (at most four candidates; a call counts if any candidate
  pair is connected).

- **Per-repository overrides** in the taxonomy (`"overrides": {repo: {path_keyword: …}}`)
  are tried before the shared path rules, and only for that repository's path step.
  They are for codebases whose folders say plainly what they are (`World/`, `Render/`,
  a Java port's single-letter packages). The fallback station's share is reported
  per repository. A large fallback is code the reference has no subsystem for, and is
  a finding to explain.
- **Graph shape** (mapping-free): on each repository's own call graph, mean degree,
  largest weakly connected component share, average undirected clustering,
  reciprocity, top-1% in-degree share, leaf and root shares, in-degree Gini and degree
  assortativity. **Shape distance** from the reference is the RMS difference after
  standardizing each field across the cohort. The **mapping check** is the Spearman
  correlation between wiring similarity and shape distance. A clearly negative ρ means
  a check that uses no subsystems or layout agrees on who stayed close.
- With `--declared-lineage`, maps are ordered depth-first along the declared lineage
  from the reference.

Survival needs measurements to survive. Wiring and calls kept need only names and
calls. That is why the maps follow translations that the descent tree cannot.

## 8. Twin browser

For each pair whose shared structure is at least `--browser-min-shared` (default 2%),
the report embeds the twins of the direction that defines that share (at most the
6,000 closest per pair, with the cap stated on the page). The page shows each twin's
function, file and size on both sides, its distance, whether it is an exact clone and
whether the names agree. It can filter by text, folder, differing names or exact
clones. Clicking a descent heatmap cell opens that pair, and `report.html#pair=A|B`
links to one directly. `--no-browser` leaves the
section out.

## 9. Limits

- The scanner sees what the engine measures. Two functions with the same measurements
  but different code are indistinguishable. That is why twins need reciprocity,
  distinctiveness and calibration, and why exact clones need size.
- Translations into another language rewrite every measurement, so the descent tree
  cannot follow them. The profile tree under the `portable` lens can, as design
  similarity only.
- The profile distance is cohort-relative. Compare numbers from the same cohort only.
- The reference frame is the engine's population model. Re-extract it after the
  engine retrains, and rebuild fingerprints. The spec hash prevents mixing frames.
