# Experiment: Repo-archetype clustering inputs (data v2.7.0)

**Status:** pre-registered plan (written before results); Results + Decision filled after.
**Data:** `data/master_db_v270.db`, `file_data.file_archetype` (the 16-way file taxonomy from the
sibling file-archetype experiment). **Runner:** `run_experiment.py` → `results.json`.

## Hypothesis

A repo is best characterized by its **file-archetype composition** (backbone) plus **scale**.
Composition alone is scale-invariant, so a 30-file micro-library and the 100k-file linux tree look
identical — scale must be a first-class axis. **Language is deliberately excluded** (owner
decision: a stack indicator, not a repo archetype). **Dependency-coupling** (is there a central
hub, how far do changes ripple) is tested as a candidate extra axis.

**Registered predictions:**
1. Composition + scale (R-A) already yields recognizable, nameable repo groups (validated against
   the real repo names — e.g. the OS kernels cluster together; test-heavy libraries cluster).
2. Coupling (R-B) adds a real axis: it separates tightly-coupled frameworks from flat collections
   of independent scripts *within* the same composition/scale band.
3. Scale meaningfully splits micro-libs from monorepos (not just a nuisance dimension).

## Method

`file_data` aggregated per repo (repos with ≥30 files → ~368). Two variants, common small k
(silhouette-swept 4–10 on R-B), KMeans (`n_init=25`):

| Variant | Features |
|---|---|
| **R-A** composition + scale | 16 file-archetype ratios (up-weighted 1.5×) + `log(file_count)`, `log(total_loc)` |
| **R-B** + coupling | R-A + `pagerank_gini` (hub concentration), `mean(dependency_density)`, `mean(blast_radius)` |

**Transform discipline:** composition stays an unscaled distribution [0,1], up-weighted; scale and
coupling are heavy-tailed → **percentile-rank to [0,1]** (never variance-scaled — the
pagerank/RobustScaler explosion lesson from the file experiment).

**Evaluation:** silhouette + cluster balance, but the decisive check is **eyeballing the actual
repos per cluster** (N is small and every repo is named) — do the clusters correspond to
recognizable kinds of projects, and does coupling (R-B vs R-A) move repos in a way that makes
sense?

## Results

368 repos (≥30 files). k≈6–7 (silhouette-swept). Silhouette is low (~0.20 — expected for fuzzy
repo boundaries at small N); the decisive evidence is the **named repos per cluster**.

**v1 (composition over ALL 16 file archetypes) — a real finding.** The two non-code buckets
(Declarative + Data/Markup) numerically dominate file counts, so clustering degenerated into
*scale × how-much-non-code* bands and the code-structure signal washed out (every cluster's top
composition was the non-code buckets). Saved as `results_v1_allcomp.json`.

**v2 (composition over CODE files only + `non_code_fraction` as one feature).** Now the clusters
reflect **code structure**, and they are recognizable:

- **Large hub-coupled monorepos** (gini≈0.49): freebsd, linux, runtime, tensorflow, elasticsearch
- **Large FLAT/modular platforms** (gini≈0.18): kotlin, TypeScript, rust, swift, roslyn, kubernetes
  — *same scale band as the monorepos, split off purely by coupling*
- **Typed libraries** (Generic/Templated 45%): mypy, pydantic, pytest, typer, rich, cryptography
- **Mainframe / COBOL & config** (I/O & Config 76%): abapGit, Cobol-Projects, Apollo-11, gnucobol, cics-genapp
- **Guard/validation-heavy** (Defensive Guards 52%): zod, express, laravel, @node-red_nodes
- **Small flat repos** (gini≈0.09): black, mojo, vapor, type-challenges

**Registered predictions:** (1) composition+scale gives recognizable groups ✔. (2) **coupling adds
a real axis ✔ strongly** — `pagerank_gini` splits tightly-coupled kernels (linux/freebsd, 0.49)
from flat modular toolchains (kotlin/rust/swift, 0.18) *within the same scale band*, the single
most insightful distinction. (3) scale splits micro-libs from monorepos ✔.

## Coupling refinement (v3)

The three v2 coupling features were diagnosed: `mean_blast` corr(scale) = **−0.76** (a scale proxy,
not coupling), `mean_dep_density` corr(pagerank_gini) = **+0.72** (redundant). A head-to-head at
k=7 on the axis that matters (does the OS-kernel *hub* set separate from the *flat* toolchain set):

| coupling | silhouette | hub-vs-flat |
|---|---|---|
| none (comp+scale) | 0.166 | MIXED |
| **pagerank_gini only** | 0.161 | **SEPARATED** |
| + betweenness_gini | 0.179 | MIXED (breaks it) |
| + dep + blast (v2) | 0.193 | separated, but via the scale-leak |

**`pagerank_gini` alone** delivers the separation. `betweenness_gini` is 0.62-redundant and its
noise *re-mixes* hub/flat despite a higher silhouette; the v2 trio only scored higher because
`mean_blast` double-counted scale. Lesson: one honest coupling axis > piling on — and silhouette
is again the wrong judge (it rewarded the scale-confounded version). **No further coupling metrics
are warranted from the master DB**; a genuinely new facet (graph *modularity* / community
structure) would need the per-repo `*_graph.sqlite` artifacts — a separate frontier.

## Decision

**Adopt R-B = code-composition (14 code archetypes, renormalized, up-weighted 1.5×) + `non_code_fraction`
+ scale (`log file_count`, `log total_loc`) + coupling (`pagerank_gini` ONLY), all rank-transformed
except composition; language excluded; k=7.** Final clusters (validated by name):

| archetype | signature | e.g. |
|---|---|---|
| Hub-Coupled Monorepo | huge, gini≈0.50 | freebsd, linux, runtime, tensorflow, elasticsearch |
| Flat Modular Platform | huge, gini≈0.20 | kotlin, TypeScript, rust, swift, roslyn, kubernetes |
| Hub-Coupled App | mid, gini≈0.46 | okhttp, openzeppelin, kivy, keystone |
| Small Flat Repo | small, gini≈0.14 | black, mojo, raspberrypi, type-challenges |
| Typed Library | Generic 46% | mypy, pydantic, pytest, cryptography |
| Mainframe / COBOL & Config | I/O 78% | abapGit, Apollo-11, gnucobol, cics-genapp |
| Guard/Validation-heavy | Guards 69% | zod, @node-red_nodes, express |

k choice: silhouette peaks at k=7 and declines after; higher k only slices the large-repo gradient
into judgment-call sub-bands, while the 3 specialty clusters (Typed Lib, COBOL, Guard) are stable
at any k. Next: `label_repo_archetypes.py` (auto-name + write `repo_archetype`).
