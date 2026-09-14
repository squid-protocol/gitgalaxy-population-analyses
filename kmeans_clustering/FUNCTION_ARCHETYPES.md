# Function Archetypes (k=14, rosetta-governed)

The canonical unsupervised taxonomy of *function* structure across the
gitgalaxy-raw-output population (v2.7.0 master DB, 8.2M functions; model trained on a
deterministic 500k-function sample). Produced by `cluster_functions.py`; the labeled model
ships as `ml_inference_brain_functions_labeled.txt`.

## How it's built

1. **Sample** — deterministic id-hash sample of functions with `loc >= 3`, excluding
   test/mock names (`cluster_functions.py`). Deterministic order ⇒ reproducible, and larger
   accuracy profiles are strict supersets of smaller ones.
2. **Features (38-D)** — 5 geometry features (`log_loc`, `log_complexity`, `log_args`,
   `keyword_density`, `func_internal_density`) + 33 per-LOC "DNA" densities
   (`log1p(hits/loc*100)`) of the architectural/structural/state/defensive signal columns.
3. **Rosetta governance** (see keyword-rosetta `docs/bias_data.json`) — one identical program
   in 46 languages tells us which metrics measure *architecture* vs *language*:
   - **Dropped** as inert (0 in all 46 languages) + a <1% population-prevalence prune:
     `llm_*`, `ml_traditional`, `dl_frameworks`, `vectorized_math`, `state_slop_duplicates`,
     `arch_crypto/regex/time`, `lit_*`, `prompt_injection`, `agentic_rce`, and the rest of the
     near-dead markers. (71 raw DNA cols → 33.)
   - **Down-weighted 0.5×** (rosetta shows they track language, not architecture / fire on
     mandatory idiom): `arch_api`, `arch_ipc`, `state_memory_alloc`, `arch_concurrency`,
     `state_print_hits`, `def_freeze_hits`, `def_spec_exposure`, `def_sync_locks`, `token_mass`,
     plus debt markers; `keyword_density` 0.5×, `log_complexity` 0.75×.
   - **Log-capped** `def_encapsulation` at p99 (winsorize the extreme accessor tail).
4. **Encapsulation lens (0.3×)** — the *alternate/canonical* cut. At full weight, encapsulation
   was so dominant it defined ~22% of functions across three clusters and masked secondary
   themes. Down-weighting it to 0.3× surfaces type-conversion and I/O archetypes and yields a
   HEALTHY diagnostic (max feature pull 3.16 IQR vs 5.22; smallest cluster 4.0%). The full-weight
   "fidelity" cut is kept on record as `*_k14_baseline.*`.
5. **Cluster** — RobustScaler (median/IQR) → apply `FEATURE_WEIGHTS` → KMeans k=14. k chosen from
   a flat silhouette plateau (0.11–0.13) favoring parsimony + interpretability over the noisy
   argmax.

## The 14 archetypes

| # | Archetype | ~Share | Defining signature (IQR above median) | Notes |
|---|-----------|--------|----------------------------------------|-------|
| 0 | **Interface Declarations** | 5.8% | func-start, args, linear, exposes API | small signature/entry fns |
| 1 | **Type Conversions** | 4.0% | **casts +2.9**, unsafe ops, pointers | surfaced by the encap lens |
| 2 | **State Mutators** | 5.5% | state-flux, args, pointers (all mild) | least-specialized / general |
| 3 | **Callbacks & Closures** | 4.8% | **closures +2.9**, some concurrency/UI | JS/TS/Go idiom |
| 4 | **Parameter Forwarders** | 13.8% | many args + pointers, **low** size/complexity | thin API glue — most common |
| 5 | **Compute Cores** | 12.2% | **internal density +1.2**, size, branching | algorithmic/tight-loop code |
| 6 | **C Struct Operations** | 7.0% | **struct "class start" +2.3**, pointers | 97% C — structs as data types |
| 7 | **Many-Argument Workhorses** | 10.5% | **args +2.3**, large, mutation, defensive | kitchen-sink procedural |
| 8 | **I/O & Config Routines** | 7.1% | I/O boundaries + immutable/const | surfaced by the encap lens |
| 9 | **Encapsulated Accessors** | 5.8% | encapsulation +1.5, pointers | getters/setters (C-heavy residual) |
| 10 | **Annotated Framework Methods** | 4.3% | **decorators +3.2**, exposes API | JVM annotation style |
| 11 | **Generic / Templated Code** | 6.7% | **generics +3.2**, API, concurrency | Rust/TS/Java generics |
| 12 | **Defensive Guards** | 8.3% | **def_safety +2.8**, bailouts, dense | validation / error handling |
| 13 | **Tests & Verification** | 4.2% | **def_test +2.9** + decorators | assertion-heavy (non-test-named) |

Nine of these (0,3,4,5,6,7,10,11,12,13 — forwarders, compute cores, C-structs, workhorses,
closures, annotations, generics, guards, tests) reproduce in **both** the full-weight and 0.3×
encapsulation cuts, so they are robust structural categories, not artifacts of a weighting choice.
Language concentration that survives (C-structs 97% C, JVM annotations/tests, JS/Go closures) is
real engineering idiom — rosetta governance removed the *measurement* bias, so what remains is a
genuine cross-language finding, not an artifact.

## How it's applied

- **Offline (this repo):** `master_db_updater.py` loads `ml_inference_brain_functions_labeled.txt`,
  rebuilds the 38-D vector in `FEATURE_NAMES` order, applies `FEATURE_WEIGHTS`, scales, and assigns
  each function its nearest-centroid archetype (`function_data.func_archetype`) plus per-cluster
  distances (`func_cluster_*`).
- **At scan time (engine):** the same model is intended to load into gitgalaxy's
  `analysis_lens.GENERAL_FUNCTION_INFERENCE_MODEL`; `signal_processor.py` must build the identical
  38-feature vector (same prune/order/weights/cap) so its centroids align. Changing this
  regenerates every function's `func_archetype`, so it requires a golden-master regeneration and a
  rosetta re-baseline.
