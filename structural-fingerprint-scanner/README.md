# structural-fingerprint-scanner

Structural fingerprints, lineage and function-level twins for codebases, computed from
[GitGalaxy](https://github.com/squid-protocol/gitgalaxy) scans.

GitGalaxy measures every function it parses: size, decisions, arity, call fan-in and
fan-out, and 32 structural signals (guards, state mutation, I/O, encapsulation,
pointers, macros, and more). This tool places each function in the engine's own
37-dimensional reference frame, fitted on a population of 8.2 million functions, and
builds on it:

- a **fingerprint** of each repository: function-archetype mix, signal densities,
  function-geometry distributions, centre of mass and call-graph shape;
- a **profile distance** between repositories (how alike their designs are), which
  works across languages under the `portable` lens;
- **structural twins**: function pairs measured almost identically, found without
  names by reciprocal best hits and accepted at a calibrated false-twin rate
  (target–decoy, 1% by default). Twins survive renaming, file moves and reformatting;
- **descent**: how much of one codebase's structure survives in another, and a
  descent tree built from it;
- **subway maps**: each repository's call graph collapsed to its subsystems and drawn
  on a reference's fixed layout, with stations coloured by how much of the reference's
  subsystem survives. They follow wiring, which survives translation into another
  language even when every measurement changes. A mapping-free graph-shape check
  confirms the maps aren't an artefact of the subsystem assignment;
- a **twin browser** in the report: pick a pair or click a descent cell and see
  every twin behind the number, by folder, with search and filters;
- reports in Markdown, HTML (heatmaps with trees), CSV, JSON and Newick.

It reads scan output only. It never sees source code and needs nothing beyond NumPy
and SciPy.

## Install

```bash
pip install ./structural-fingerprint-scanner   # Python 3.10+, numpy, scipy
sfs --version
```

## Use

Scan each repository with GitGalaxy first. Each scan directory holds a
`<name>_galaxy_master.db`.

```bash
# Fingerprint scans (writes <name>.sfp.json + <name>.sfp.npz)
sfs fingerprint scans/ -o fingerprints/

# Compare a cohort: distances, twins, both trees, report.html
sfs compare fingerprints/ -o report/ --declared-lineage lineage.csv

# Across languages: down-weight what tracks the language, not the design
sfs compare fingerprints/ -o report-portable/ --lens portable --no-twins

# Which functions of A survive in B, as CSV
sfs twins fingerprints/A.sfp.json fingerprints/B.sfp.json -o twins/

# Subway maps on a reference's layout (subsystems from a taxonomy, or top-level directories)
sfs subway fingerprints/ -o subway/ --reference A --taxonomy subsystems.json [--declared-lineage lineage.csv]
# ...or as a section of the compare report
sfs compare fingerprints/ -o report/ --subway-reference A --taxonomy subsystems.json

# What separates two repositories
sfs explain fingerprints/A.sfp.json fingerprints/B.sfp.json

# The reference frame and lens in use
sfs spec [--lens portable] [--json]
```

`compare` accepts scans, scan directories, fingerprints or fingerprint directories in
any mix. The optional `--declared-lineage` CSV (`name,parent`, one row per parent)
checks both trees against what the projects say about their own ancestry.

### Output of `compare`

| path | content |
|---|---|
| `report.html` | descent and profile heatmaps with trees, the twin browser, archetype mix, lineage check, repository table (and subway maps with `--subway-reference`) |
| `report.md` | the same in Markdown |
| `summary.json` | everything, machine-readable, with the reference and lens provenance |
| `pairs.csv` | one row per pair: every component distance, profile distance, survival both ways, shared structure, twin and clone counts, name agreement |
| `matrices/*.csv` | square matrices behind each figure |
| `trees/profile.nwk`, `trees/descent.nwk` | Newick trees |
| `subway.json`, `subway.csv` | with `--subway-reference`: stations, lines, survival per subsystem, wiring scores |
| `fingerprints/` | the fingerprints used |

## How to read the numbers

- **Profile distance**: 1.0 is a typical pair *in that cohort*, 0.5 twice as close.
  The component distances in `pairs.csv` are absolute.
- **Survival A→B**: share of A's functions (≥6 lines) with a twin in B.
- **Shared structure**: the larger direction's Wilson 95% lower bound on survival.
  Below 2% there is no detectable descent.
- **Name agreement**: names are not used to match, so when two codebases name their
  functions alike, the share of twins whose names agree is an independent estimate of
  the twin search's precision.

[docs/METHOD.md](docs/METHOD.md) specifies every formula, the calibration and the
limits. [examples/doom/](examples/doom/) validates the tool on 44 DOOM ports with
known ancestry.

## Reference frame and reproducibility

The vendored reference model (`src/structural_fingerprint/data/`) records the
GitGalaxy commit it came from. Each fingerprint carries a `spec_hash` over the scaler,
weights, caps, features and lens, and fingerprints with different hashes refuse to
compare. Twin search is deterministic: decoys are seeded from the repository names.

```bash
python tools/refresh_reference.py --engine /path/to/gitgalaxy        # after the engine retrains
python tools/derive_portable_weights.py --rosetta /path/to/keyword-rosetta
```

## Tests

```bash
pip install './structural-fingerprint-scanner[test]'
pytest structural-fingerprint-scanner
# engine parity on real scans (made by the reference's engine commit):
SFS_REAL_SCANS=/path/to/scans pytest structural-fingerprint-scanner
```
