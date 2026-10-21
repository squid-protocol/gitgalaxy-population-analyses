"""Vendor the GitGalaxy function model into the scanner as its reference frame.

The scanner standardizes every function against the population model the engine
itself classifies with (``GENERAL_FUNCTION_INFERENCE_MODEL`` in
``gitgalaxy/standards/analysis_lens.py``): robust-scaler medians and IQRs fitted on
the population corpus, rosetta-governed feature weights, density caps, the
signal-column mapping and the k=14 archetype centroids. Re-run this after the engine
retrains that model; the snapshot records the engine commit it came from.

    python tools/refresh_reference.py --engine /path/to/gitgalaxy-checkout
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "structural_fingerprint" / "data" / "reference_function_model.json"


def _git(engine: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(engine), *args], capture_output=True, text=True, check=False)
    return r.stdout.strip()


def load_model(engine: Path) -> dict:
    path = engine / "gitgalaxy" / "standards" / "analysis_lens.py"
    if not path.is_file():
        raise SystemExit(f"not a gitgalaxy checkout (no {path})")
    spec = importlib.util.spec_from_file_location("_gg_analysis_lens", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.GENERAL_FUNCTION_INFERENCE_MODEL


def build(engine: Path) -> dict:
    m = load_model(engine)
    arch_key = next(k for k in m if k.startswith("ARCHETYPES_K"))
    centroids = m[arch_key]
    names = list(m["cluster_names"])
    if len(centroids) != len(names):
        raise SystemExit(f"{arch_key} has {len(centroids)} centroids but {len(names)} cluster names")
    return {
        "schema": "structural-fingerprint/reference-function-model/1",
        "provenance": {
            "source": "gitgalaxy/standards/analysis_lens.py:GENERAL_FUNCTION_INFERENCE_MODEL",
            "engine_commit": _git(engine, "rev-parse", "HEAD"),
            "engine_commit_date": _git(engine, "log", "-1", "--format=%cI"),
            "extracted_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        },
        "feature_names": list(m["FEATURE_NAMES"]),
        "scaler_medians": [float(x) for x in m["SCALER_MEDIANS"]],
        "scaler_iqrs": [float(x) for x in m["SCALER_IQRS"]],
        "feature_weights": [float(x) for x in m["FEATURE_WEIGHTS"]],
        "cap_values": {k: float(v) for k, v in m.get("CAP_VALUES", {}).items()},
        "signal_sources": dict(m["DNA_SOURCES"]),
        "archetype_names": names,
        "archetype_centroids": [[float(x) for x in c] for c in centroids.values()],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--engine", type=Path, required=True, help="path to a gitgalaxy checkout")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    ref = build(a.engine.resolve())
    a.out.write_text(json.dumps(ref, indent=1) + "\n")
    print(f"wrote {a.out} ({len(ref['feature_names'])} features, {len(ref['archetype_names'])} archetypes, "
          f"engine {ref['provenance']['engine_commit'][:9]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
