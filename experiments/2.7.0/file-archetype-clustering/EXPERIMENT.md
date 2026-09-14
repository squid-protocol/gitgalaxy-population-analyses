# Experiment: File-archetype clustering inputs (data v2.7.0)

**Status:** pre-registered plan below (written before results); Results + Decision filled after the run.
**Data:** `data/master_db_v270.db` (gitgalaxy-raw-output v2.7.0), `file_data` with the
function-archetype stoichiometry (`func_cluster_ratios`) produced by
`master_db_updater.py --update rollup_function_clusters`.
**Runner:** `run_experiment.py` → `results.json`.

## Motivation

Auditing the existing `cluster_files.py` feature vector (see the constellation memory / PR #5
context) found it is ~199 dims but **lopsided**:

- The 14-dim **function-archetype stoichiometry** — the whole point of building the function
  taxonomy — is <8% of the vector.
- **171 file "hit density" features** dominate, of which ~18 are rosetta-inert families
  (llm/lit/ml/crypto/regex/time) and ~31 are <1% non-zero on this corpus (dead padding).
- A **transform bug**: already-normalized graph/quality metrics (`pagerank_score`,
  `betweenness_score`, `normalized_blast_radius`, `ownership_entropy`, `popularity`,
  `producer_ratio`, `structural_mass`, `cog_raw`) are divided by LOC and log-transformed as if
  they were hit counts. `pagerank / LOC` is meaningless (same class of bug as clustering a
  foreign key in the function work).
- **Redundancy:** the aggregate function metrics (avg/max complexity, gini, args…) restate what
  the stoichiometry already encodes.

## Hypothesis

A file's archetype is best characterized **compositionally** — *what kinds of functions it
contains* (the stoichiometry) plus a few genuinely file-level properties that are **not**
re-aggregations of its functions (scale, state organization, and dependency-graph role). The
171-dim hit-density bag is mostly redundant + noisy and should be dropped or heavily demoted.

**Predictions (registered):**
1. **B beats A and C** on interpretability and separation.
2. Raw architectural hits (C) add little over stoichiometry → C ≈ B.
3. The **dependency-graph role** (`pagerank`/`blast_radius`) is the most valuable non-function
   signal (hub-vs-leaf), invisible in the function mix.
4. No-function CODE files (constants/config/`__init__` — "`x = ...`") self-organize into a
   clean **declarative / non-code** cluster when included with all-zero stoichiometry.

## Method

Deterministic id-hash sample of `file_data` (`coding_loc ≥ 8`, code languages only — pure data
formats excluded; no-function code files INCLUDED). Three variants, common k (silhouette-swept on
B), KMeans (`random_state=42`, `n_init=10`):

| Variant | Features |
|---|---|
| **A** stoichiometry-pure | 14 function-archetype ratios + `log_coding_loc` |
| **B** compositional+ | A + curated file-level structure: `log_function_count`, `log_class_count`, `log_import_count`, `encapsulation_ratio`, `doc_ratio`, `control_flow_ratio`, and the graph role `log_pagerank` + `log_blast_radius`; **stoichiometry up-weighted 2.5×** |
| **C** governed-hits | B + rosetta-surviving arch hit densities (`io/api/concurrency/ui`) at weight 0.5 |

**Transform discipline (the fix):** stoichiometry stays a proper composition — raw fractions in
[0,1], **not** RobustScaled (scaling a mostly-zero simplex dim blows up rare values), weighted
instead. Auxiliary features are RobustScaled then weighted. Graph metrics are `log1p`'d, **never
divided by LOC**.

**Evaluation:** silhouette, min-cluster % (quarantine check), max feature pull (health), and —
the real judge — **interpretability**: can each cluster be named (Test suites / API-route modules
/ Data models / Core-algorithm files / Thin utilities / Config-declarative), and are clusters
structural rather than language-driven (rosetta-informed)?

## Results

Sample: 120,000 files (32% no-function/declarative). Common k = 15 (silhouette-swept on B).

**v1 (RobustScaler on aux) — a real finding, not just a bug.** The dependency-graph metrics
(`pagerank`, `blast_radius`) are so heavy-tailed (near-zero median, rare huge values) that even
`log1p` + RobustScaler **explodes** them — the scaled `log_pagerank` centroid pull hit **~3495
IQR**, collapsing B/C into one **97% mega-cluster + quarantine micro-clusters** (silhouette 0.88,
but that's the quarantine failure mode, not separation). Only A was healthy. → Graph metrics
cannot be used with variance scaling; they need a **distribution-agnostic** transform.
Saved as `results_v1_robustscaler.json`.

**v2 (percentile-rank → uniform [0,1] on aux).** All three healthy (max pull 2.3, min-cluster
~2.2%):

| Variant | dims | silhouette | min-cluster % | verdict |
|---|---|---|---|---|
| A stoichiometry-pure | 15 | **0.487** | 2.32 | clean but coarse |
| B compositional+ | 23 | 0.335 | 2.21 | **richest / most nameable** |
| C governed-hits | 27 | 0.327 | 2.20 | ≈ B (hits add nothing) |

Both A and B recover ~14 clean single-archetype file clusters (each 70–92% one function
archetype — *Forwarder files, Guard files, Generics files, I/O files, Compute-core files, Test
files, C-struct files, …*) **plus** a 32% **declarative/non-code** cluster (98% no-function —
the headers/config/constants "`x = ...`" files, exactly as predicted).

**The decisive difference is the ~14% mixed-composition cluster:**
- **A** defines it *negatively* — "no dominant function type" (Compute 18% / Forwarders 13% /
  Type-Conv 12%): a weak residual grab-bag.
- **B** defines it *positively* — the same files, characterized by `log_function_count +0.81`,
  `log_coding_loc +0.77`, high control-flow and graph centrality: a nameable **"Large core
  module"** archetype.

**Registered predictions:** (1) B most useful ✔ (positively-defined large-module cluster + scale
/ graph nuance, though A wins raw silhouette — silhouette favors the coarser, lower-dim space
here, not usefulness). (2) C ≈ B, raw hits redundant ✔ (0.327 vs 0.335). (3) graph role valuable
✔ **but only after the rank transform** — naive scaling was pathological (v1). (4) no-function
files form a clean declarative cluster ✔.

## Decision

**Adopt Variant B** as the file-archetype taxonomy: 14-dim function-archetype stoichiometry
(up-weighted 2.5×, kept as an unscaled composition) + curated file-level features
(size, function/class/import counts, encapsulation, doc ratio, control-flow, and the
**percentile-rank-transformed** graph role) at k≈15; include no-function code files (they form
the declarative cluster); **drop the 171-dim hit-density bag** (C shows it adds nothing) and the
redundant aggregate function metrics. Fold this into `cluster_files.py` (transform fix + brain
with FEATURE_NAMES/WEIGHTS, mirroring the function clusterer). Open question left for the owner:
A's higher silhouette / "a file *is* its function composition" purity vs B's richer scale+graph
taxonomy — recommendation is B.
