# Experiment index

The **map** of the studies in this repo: what was tested, on what data, and how it came out. It is a
*view*, not a source of truth: the authoritative record is [`HYPOTHESES.md`](HYPOTHESES.md) (verdicts,
direction, α) and each study's own pre-registration. If this file and the register disagree, the register
wins; fix this file. Structure and conventions follow the
[temporal crucible's index](https://github.com/squid-protocol/temporal-crucible/blob/main/docs/EXPERIMENTS.md).

Read order for someone new: this file (what has been tried) → [`HYPOTHESES.md`](HYPOTHESES.md) (what
is registered and how it came out) → the study's own doc (how).

## 1. Studies

| study | type | data | status | doc |
|---|---|---|---|---|
| File-archetype clustering (data v2.7.0) | pre-registered plan | master DB v2.7.0, `file_data` | done | `experiments/2.7.0/file-archetype-clustering/EXPERIMENT.md` |
| Repo-archetype clustering (data v2.7.0) | pre-registered plan | master DB v2.7.0, ~368 repos | done | `experiments/2.7.0/repo-archetype-clustering/EXPERIMENT.md` |
| DOOM descent: profile and twin lineage | method validation | 44 programs (the 1993 source and 43 descendants) with stated ancestry | done | `structural-fingerprint-scanner/examples/doom/` |
| DOOM blind placement | method validation | DOOM ports, ancestry hidden | done | `structural-fingerprint-scanner/examples/doom/blind_placement.md` |
| Agentic COBOL pairs (Claude Code vs Codex) | exploratory | 5 MIT pairs, acherm/agentic-cobol-* | paper draft (PR #23) | `agentic-cobol-pairs/` |
| Agent habits (Claude Code vs Codex) | **confirmatory, registered** (AH-) | exploratory: 10 pairs; confirmation: 40 fresh repos, not yet generated | registered 2026-11-01 (PR #24) | `agent-habits-prereg/PREREGISTRATION.md` |

## 2. Naming convention

- **`<SCOPE>-H<n>`** for a primary confirmatory claim, **`<SCOPE>-S<n>`** for a secondary one,
  **`<SCOPE>-V<n>`** for a variance (run-to-run) claim. `<SCOPE>` names the study (`AH-` = agent
  habits).
- **`<SCOPE>-<NAME>`** (a word, not a number) for a named test that is not a numbered hypothesis.
- A replication of an existing claim on new data keeps the base name, prefixed by the new scope, so a
  claim's whole history reads down one grep.
- Every registration lands in **three places, same session**: the study's pre-registration (its commit
  timestamp is the proof), a row in [`HYPOTHESES.md`](HYPOTHESES.md), and a row here. Registration and
  verdict never ship in the same PR (see [`../CONTRIBUTING.md`](../CONTRIBUTING.md)).

New studies start from [`_experiment_template.md`](_experiment_template.md); experiments on how a tool,
brief or setting changes an AI agent's work start from
[`_agent_experiment_template.md`](_agent_experiment_template.md).
