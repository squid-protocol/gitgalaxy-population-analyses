"""Derive the ``portable`` lens from the keyword-rosetta control corpus.

keyword-rosetta plants one program, with identical intent, in 46 languages and records
what the engine measures in each (``docs/bias_data.json``). A signal that reads the
same in every language measures the program; one that swings with the language
measures the language. For each signal the scanner uses, this script computes its
*cross-language consistency*: the share of languages whose count lies within
``--band`` of the cross-language median. The portable lens multiplies the engine's
weight for that signal by the consistency, clipped to ``[--floor, 1]``.

Signals rosetta does not plant get ``--unmeasured`` (default 0.5): their cross-language
behaviour is unknown, and most of them name language constructs (pointers, macros,
generics, decorators). Signals rosetta lists as firing only on mandatory language
idiom (``unplanted_inputs``) get the floor.

    python tools/derive_portable_weights.py --rosetta /path/to/keyword-rosetta
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "src" / "structural_fingerprint" / "data"

# Geometry features are not rosetta metrics; each is tied to the rosetta measurement that
# carries the same quantity, or fixed when rosetta classes the quantity as ungated.
GEOMETRY = {
    "log_loc": ("fixed", 0.5),  # coding_loc is ungated: verbosity differs by language
    "keyword_density": ("fixed", 0.0),  # keyword_hits is ungated vocabulary, i.e. the language itself
    "log_complexity": ("metric", "branch"),
    "func_internal_density": ("metric", "branch"),
    "log_args": ("metric", "args"),
}
# Engine signal names whose rosetta metric is recorded under another name.
ROSETTA_ALIASES = {"api": "raw_arch_api", "encapsulation": "def_encapsulation"}


def consistency(values: dict[str, float | None], band: float) -> tuple[float, int]:
    xs = sorted(float(v) for v in values.values() if v is not None)
    if not xs:
        return 0.0, 0
    mid = xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2
    if mid == 0:
        inside = sum(1 for x in xs if x == 0)
    else:
        inside = sum(1 for x in xs if abs(x - mid) <= band * abs(mid))
    return inside / len(xs), len(xs)


def derive(rosetta: Path, band: float, floor: float, unmeasured: float) -> dict:
    bias = json.loads((rosetta / "docs" / "bias_data.json").read_text())
    model = json.loads((DATA / "reference_function_model.json").read_text())
    metrics, na = bias["metrics"], bias.get("na", {})
    unprofiled = {lang for lang, s in bias.get("strata", {}).items() if s == "unprofiled"}
    unplanted = set(bias.get("unplanted_inputs", []))

    def measured(metric: str) -> dict[str, float | None]:
        vals = metrics.get(metric, {})
        skip = set(na.get(metric, {})) | unprofiled
        return {lang: v for lang, v in vals.items() if lang not in skip}

    factors, detail = {}, {}
    for feat, (kind, arg) in GEOMETRY.items():
        if kind == "fixed":
            factors[feat] = arg
            detail[feat] = {"rule": "fixed", "factor": arg}
        else:
            c, n = consistency(measured(arg), band)
            factors[feat] = round(max(floor, min(1.0, c)), 3)
            detail[feat] = {"rule": "consistency", "rosetta_metric": arg, "consistency": round(c, 3), "languages": n}
    for col, metric in model["signal_sources"].items():
        if metric in unplanted:
            factors[col] = floor
            detail[col] = {"rule": "unplanted_idiom", "rosetta_metric": metric, "factor": floor}
        elif (rm := ROSETTA_ALIASES.get(metric, metric)) in metrics:
            c, n = consistency(measured(rm), band)
            factors[col] = round(max(floor, min(1.0, c)), 3)
            detail[col] = {"rule": "consistency", "rosetta_metric": rm, "consistency": round(c, 3), "languages": n}
        else:
            factors[col] = unmeasured
            detail[col] = {"rule": "unmeasured", "rosetta_metric": metric, "factor": unmeasured}

    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(rosetta), *args], capture_output=True, text=True,
                              check=False).stdout.strip()

    return {
        "schema": "structural-fingerprint/portable-weights/1",
        "provenance": {
            "source": "keyword-rosetta docs/bias_data.json",
            "rosetta_commit": git("rev-parse", "HEAD"),
            "rosetta_commit_date": git("log", "-1", "--format=%cI"),
            "languages": len(bias.get("languages", [])),
            "band": band,
            "floor": floor,
            "unmeasured": unmeasured,
            "derived_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        },
        "default_factor": unmeasured,
        "factors": factors,
        "detail": detail,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rosetta", type=Path, required=True, help="path to a keyword-rosetta checkout")
    ap.add_argument("--band", type=float, default=0.25, help="relative band around the median (default 0.25)")
    ap.add_argument("--floor", type=float, default=0.25, help="smallest factor a signal can get (default 0.25)")
    ap.add_argument("--unmeasured", type=float, default=0.5, help="factor for signals rosetta does not plant")
    ap.add_argument("--out", type=Path, default=DATA / "portable_weights.json")
    a = ap.parse_args(argv)
    out = derive(a.rosetta.resolve(), a.band, a.floor, a.unmeasured)
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    rules: dict[str, int] = {}
    for d in out["detail"].values():
        rules[d["rule"]] = rules.get(d["rule"], 0) + 1
    print(f"wrote {a.out}: {rules}, rosetta {out['provenance']['rosetta_commit'][:9]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
