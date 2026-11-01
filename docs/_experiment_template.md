<!--
Template for a population-analyses study write-up (from the temporal crucible's docs/_experiment_template.md).
Copy to <study>/README.md (or experiments/<data-version>/<study>/EXPERIMENT.md), fill in, delete this comment.
A confirmatory doc MUST cite its pre-registration and report every registered verdict either way; an
exploratory doc claims no p-values and says so up top. Add the study's row to docs/EXPERIMENTS.md and (for
confirmatory) its rows to docs/HYPOTHESES.md. See CONTRIBUTING.md: registration and verdict never ship together.
-->

# <Study title>

**Type:** confirmatory | exploratory
**Registered:** <date>, pre-registration <path> at commit <sha> · PR #<n>   *(confirmatory only)*
**Question:** <one sentence>   **Measures:** <what GitGalaxy / sfs measures>   **Comparison:** <pairs / groups / controls>
**Data:** <repos, pinned commits and licences: pins.csv>   **Engine:** <commit: engine.sha>   **Tools:** `<scripts>`

## Registered claims (verbatim)

> <the direction + test + α, quoted exactly as registered, before any statistic ran>

## Scan-quality appraisal (before any analysis)

<per repo / language: definitions vs tree-sitter and ctags, calls vs a reference, language assignment,
exclusions, errors, timeouts, memory; the cells a known defect touches and how they are handled>

## Guards (all required; say which apply and how)

- [ ] Licensed inputs only; measurements only, no source text
- [ ] Temporal ablation (`GITGALAXY_DISABLE_GIT_HISTORY=1`) on every scan
- [ ] One engine commit for both sides of every comparison
- [ ] Measures restricted to the language under study (or the language mix shown beside them)
- [ ] Each signal's rule read for that language, and a matching source line checked, before naming a finding
- [ ] Headline numbers cross-checked by a second route
- [ ] Every number next to its comparison (chance / shuffled control / other side)
- [ ] Tests counted; multiple-comparison correction on any table wider than one claim
- [ ] Repeat runs, where the inputs are generated, before calling a difference a trait
- [ ] Size-matched controls / length-matched pairs where the grain is the function
- [ ] Denominators and ranges taken from the data

## Result

| id | verdict | statistic | evidence |
|---|---|---|---|
| <ID> | ✓ / ✗ / ⚠ | <p, effect, n> | <cell> |

For any null claimed as a *replicated null* (not merely underpowered): report the equivalence (TOST) CI and the
δ it must fall within.

## Reading

<what it means; what it changes; what it does NOT establish>

## Follow-ups registered (for unseen data only)

<any exploratory observation graduating to a registration: names the data it will be tested on, never the data
that suggested it>
