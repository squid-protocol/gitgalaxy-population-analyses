#!/usr/bin/env python3
"""
One-shot: backfill a provenance block onto composition brains that were frozen
BEFORE freeze_archetype_brains.py started recording it (#3124).

Why this exists instead of just re-freezing: the corpus that produced the
currently-shipped brains was overwritten and is unreproducible -- re-freezing
from the current corpus yields materially different centroids and archetype
labels (a retrain, out of scope here). This script therefore preserves the
shipped centroids exactly and only *stamps* provenance:

  * feature_contract + feature_contract_sha -- AUTHENTIC, derived from each
    brain's own feature fields with the same algorithm freeze_archetype_brains.py
    uses, so the engine's parity gate (archetype_parity.check_brain) passes.
  * engine_commit / trainer_version -- the engine + trainer this backfill ships
    with (meaningful and true).
  * corpus fields -- honestly marked "unrecorded (pre-provenance freeze)",
    because they genuinely were not captured. This is the exact deficiency #3124
    documents; the next real freeze attaches full corpus provenance natively.

Run from the repo root (any interpreter; no numpy/sklearn needed):
    python backfill_provenance.py
"""
import json
from pathlib import Path

# Canonical helpers live in the freeze script; import them so the sha algorithm
# and trainer version stay single-source. (freeze defines these at import time
# and guards the actual training behind __main__, so importing is cheap/safe.)
from freeze_archetype_brains import _contract_sha, _engine_commit, TRAINER_VERSION

SD = Path(__file__).resolve().parent
UNRECORDED = "unrecorded"  # honest sentinel; the backfill_note field explains why


def _file_contract(b: dict) -> dict:
    return {
        "level": "file",
        "k": b["k"],
        "stoich_weight": b["stoich_weight"],
        "stoich_archetypes": b["stoich_archetypes"],
        "aux_features": b["aux_features"],
        "noncode_languages": b["noncode_languages"],
        "min_coding_loc": b["min_coding_loc"],
    }


def _repo_contract(b: dict) -> dict:
    return {
        "level": "repo",
        "k": b["k"],
        "comp_weight": b["comp_weight"],
        "comp_archetypes": b["comp_archetypes"],
        "scale_features": b["scale_features"],
        "coupling_feature": b["coupling_feature"],
        "feature_order": b["feature_order"],
        "min_files": b["min_files"],
    }


def _backfill(path: Path, contract_fn) -> None:
    b = json.loads(path.read_text())
    if b.get("provenance"):
        print(f"{path.name}: already has provenance -- skipping")
        return
    contract = contract_fn(b)
    b["provenance"] = {
        "corpus": UNRECORDED,
        "corpus_sha256": UNRECORDED,
        "trainer_commit": UNRECORDED,
        "trainer_version": TRAINER_VERSION,
        "engine_commit": _engine_commit(),
        "trained_at": UNRECORDED,
        "record_count": None,
        "language_mix": {},
        "k": b["k"],
        "feature_contract": contract,
        "feature_contract_sha": _contract_sha(contract),
        "backfilled": True,
        "backfill_note": (
            "Provenance backfilled onto a brain frozen before the freeze step recorded it. "
            "The feature_contract_sha and engine_commit are authentic; the training corpus was "
            "not captured and is unreproducible. The next freeze_archetype_brains.py run attaches "
            "full corpus provenance."
        ),
    }
    path.write_text(json.dumps(b, indent=1))
    print(f"{path.name}: provenance backfilled (contract {b['provenance']['feature_contract_sha']})")


if __name__ == "__main__":
    _backfill(SD / "data" / "file_archetype_brain.json", _file_contract)
    _backfill(SD / "data" / "repo_archetype_brain.json", _repo_contract)
