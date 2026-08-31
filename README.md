# gitgalaxy-population-analyses

Population-level statistics over [GitGalaxy](https://github.com/squid-protocol/gitgalaxy) scan
data: where a single scan describes one repository, this repo asks what hundreds of scans look
like **together** — how risk exposures distribute across real-world code, whether repositories
cluster into structural archetypes, and how malware-labeled populations separate from benign
ones. Raw inputs come from
[gitgalaxy-raw-output](https://github.com/squid-protocol/gitgalaxy-raw-output) (unedited
per-repo scan bundles); this repo merges them into master SQLite databases (`build_master_db.py`,
`master_db_updater.py`) and runs the analyses offline. Nothing here is on any CI path.

![Archetype z-score distribution](analyses_ridgeplots/archetype_zscore_distribution.png)

## What's here

- **Master database assembly** — `build_master_db.py` / `master_db_updater.py` merge raw-output
  scan DBs into one population database (`data/`); `db_health_assessor.py` sanity-checks it.
- **Risk-exposure distributions** — `detailed_risk_exposure_stats_from_db.py`,
  `plot_ridgelines.py` → the ridgeline plots in `analyses_ridgeplots/` (66 charts: per-metric
  distributions across the population, e.g. `avg_func_args_ridgeplot.png`).
- **Structural archetypes** — `archetype_analysis_suite.py`, `apply_language_specific_clusters.py`,
  `repo_macro_fingerprints.py`, `twin_discovery*.py`: clustering repositories by structural
  signature profile and hunting near-identical "twins" across the population.
- **Threat/malware population studies** — `analyze_threat_prediction_distributions.py`,
  `repo_level_malware_analysis_suite.py`, `graph_malware_zscores_by_cluster.py`,
  `malware_telemetry_report.py`, `extract_zero_day_suspects.py` → `analysis_outputs/`
  (z-score separations of malware-labeled vs. benign repos, classifier confusion heatmap,
  `danger_zone_audit.csv`).
- **Function-level studies** — `function_analysis_suite.py`, `validate_function_metrics.py`,
  `mine_dna_stoichiometry.py`.

![Repo-level malware z-score distribution](analysis_outputs/repo_malware_zscore_distribution.png)

## The GitGalaxy constellation

This repo is one strand of the web of repos that build, prove, and showcase GitGalaxy:

- [gitgalaxy](https://github.com/squid-protocol/gitgalaxy) — the engine that produced every data point here
- [gitgalaxy-raw-output](https://github.com/squid-protocol/gitgalaxy-raw-output) — the unedited scan bundles this repo aggregates
- **gitgalaxy-population-analyses** — *you are here*: the statistical layer on top
- [language-crucible](https://github.com/squid-protocol/language-crucible) — the pinned adversarial corpus behind the engine's golden-master regression gate
- [keyword-rosetta](https://github.com/squid-protocol/keyword-rosetta) — one planted program in 46 languages, measuring cross-language measurement consistency (read its bias findings before treating cross-language comparisons here as unbiased)
- [cobol_to_java_examples](https://github.com/squid-protocol/cobol_to_java_examples) — 10 COBOL repos auto-translated to compiling Spring Boot architectures
- [squid-telemetry](https://github.com/squid-protocol/squid-telemetry) — public distribution/adoption metrics
- Docs: [architecture & methodology site](https://squid-protocol.github.io/gitgalaxy/) · [risk-equation methodology chapter](https://squid-protocol.github.io/gitgalaxy/08-01-methodology) · [Museum of Code](https://squid-protocol.github.io/gitgalaxy/museum-of-code/) · [gitgalaxy.io](https://gitgalaxy.io/)
