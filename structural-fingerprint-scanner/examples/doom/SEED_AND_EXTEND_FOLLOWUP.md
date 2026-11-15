# DOOM DNA Follow-Up: Seed-and-Extend, Controls, Horizontal Transfers & DOOM-E5

All follow-up scripts, preregistered hypotheses, and interactive visualizations live in [`squid-protocol/doom-dna`](https://github.com/squid-protocol/doom-dna).

## Highlights

- **Unsupervised Seed-and-Extend (`composition` mode + Fused Gromov–Wasserstein + `delta` + 3-hop extension):**
  - Recovers **65–95%** of 1-to-1 functions across C ports (`mood` 95.3%, `puredoom` 89.0%, `doomgeneric` 84.9%, `sdl-doom` 82.3%, `doom-ascii` 80.8%, `doom-wasm` 78.8%, `chocolate-doom` 65.0%) with zero identifiers read.
  - Cross-language `C -> Go` (`gore`, flat directory layout): **426 / 561 (75.9%)** exact 1-to-1 functions (**92.5%** on Tier-1 FGW seeds).
- **66 Cross-Pair Permutations & 9 Permissive Controls:**
  - Every novel/from-scratch/control pair scores **0–1** accidental name hits (`lua`, `quake`, `quake2`, `carddemo-cobol-ctrl`, `c-raycasting`, `c-raycasting2`, `goom3d`, `bubbletea`, `macroquad`).
- **Preregistered Held-Out `DOOM-E5`:**
  - Confirmed `cydoomgeneric` (`100.0%` Tier-1 vs `doomgeneric`, `FGW_cost=0.313`), `DOOM-style-Game` (`0.0%`), `doome` (`0.0%`).
  - Falsified `iron-doom` (`0.0%`, Bevy ECS rewrite of Chocolate Doom) and `doomarkable` (`0.0%`, 41-function external `doomgeneric-rs` wrapper).
- **Horizontal Borrowing Detector (`horizontal_transfers.py`):**
  - Isolates `textscreen` in `odamex`, `eternity`, `woof`, `nugget-doom`, and `doom-wasm`; `src/hexen` in `dsda-doom`; MBF21 pointers between `dsda-doom` and `woof`; `man` docgen in `woof`; and hidden lineage (`doom-ios` <-> `prboom-plus`, `doomgeneric` <-> `sdl-doom`).
- **16-Track Call-Graph DNA Gene Map (`dna-tracks-mockup.html` + `dna_tracks_data.json`):**
  - Discovers 16 organic call-graph communities directly from `linuxdoom`'s call graph (zero filename rules) and projects 49 scanned targets onto them.
