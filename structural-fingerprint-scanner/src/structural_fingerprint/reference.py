"""The reference frame every fingerprint is measured in.

A function becomes a point in the engine's own 37-dimensional function space: five
geometry features (size, complexity, arity, vocabulary density, decision density) and
32 per-LOC signal densities, each log-transformed, robust-scaled against the
population model the engine was trained on, and weighted by the engine's
rosetta-governed feature weights. Because the scaler comes from the population model
and not from the repositories being compared, a coordinate means the same thing in
every report: "this many population IQRs above the population median".

A *lens* reweights that space for a purpose. ``structure`` is the engine's space as
shipped. ``portable`` additionally down-weights the signals that the keyword-rosetta
control corpus (one program planted in 46 languages) shows to track the language
rather than the design, for comparisons across languages.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from importlib import resources

import numpy as np

GEOMETRY_FEATURES = ("log_loc", "log_complexity", "log_args", "keyword_density", "func_internal_density")
DENSITY_PREFIX = "log_density_"
LENSES = ("structure", "portable")


def _load_json(name: str) -> dict:
    return json.loads(resources.files("structural_fingerprint.data").joinpath(name).read_text())


@dataclass(frozen=True)
class Reference:
    """The vendored engine function model plus the active lens."""

    feature_names: tuple[str, ...]
    medians: np.ndarray
    iqrs: np.ndarray
    weights: np.ndarray  # the lens's weights: these define distances
    engine_weights: np.ndarray  # the engine's weights: these define archetypes
    caps: dict[str, float]
    signal_columns: tuple[str, ...]  # scan-DB columns, in feature order
    archetype_names: tuple[str, ...]
    centroids: np.ndarray  # (k, F), in the engine's weighted space
    lens: str
    provenance: dict = field(default_factory=dict)
    lens_provenance: dict = field(default_factory=dict)

    @property
    def n_features(self) -> int:
        return len(self.feature_names)

    @property
    def spec_hash(self) -> str:
        """Identifies the exact geometry: two fingerprints are comparable only if these match."""
        h = hashlib.sha256()
        h.update(json.dumps([self.feature_names, self.signal_columns, self.lens], sort_keys=True).encode())
        for arr in (self.medians, self.iqrs, self.weights):
            h.update(np.asarray(arr, dtype=np.float64).round(12).tobytes())
        h.update(json.dumps(self.caps, sort_keys=True).encode())
        return h.hexdigest()[:16]

    def describe(self) -> dict:
        return {
            "lens": self.lens,
            "spec_hash": self.spec_hash,
            "reference": self.provenance,
            "lens_source": self.lens_provenance,
            "features": [
                {"name": n, "median": float(m), "iqr": float(i), "weight": float(w)}
                for n, m, i, w in zip(self.feature_names, self.medians, self.iqrs, self.weights, strict=True)
            ],
            "caps": self.caps,
            "archetypes": list(self.archetype_names),
        }


def load_reference(lens: str = "structure") -> Reference:
    if lens not in LENSES:
        raise ValueError(f"unknown lens {lens!r}; choose from {', '.join(LENSES)}")
    m = _load_json("reference_function_model.json")
    names = tuple(m["feature_names"])
    sources = m["signal_sources"]
    signal_columns = tuple(n[len(DENSITY_PREFIX):] for n in names if n.startswith(DENSITY_PREFIX))
    missing = [c for c in signal_columns if c not in sources]
    if missing:
        raise ValueError(f"reference model lists densities with no signal source: {missing}")
    if tuple(n for n in names if not n.startswith(DENSITY_PREFIX)) != GEOMETRY_FEATURES:
        raise ValueError("reference model geometry features changed; update GEOMETRY_FEATURES and features.py")

    base_w = np.asarray(m["feature_weights"], dtype=np.float64)
    weights = base_w.copy()
    lens_prov: dict = {}
    if lens == "portable":
        pw = _load_json("portable_weights.json")
        lens_prov = pw["provenance"]
        factors = pw["factors"]
        for i, n in enumerate(names):
            key = n.removeprefix(DENSITY_PREFIX)
            weights[i] = base_w[i] * float(factors.get(key, pw["default_factor"]))

    iqrs = np.asarray(m["scaler_iqrs"], dtype=np.float64)
    iqrs = np.where(iqrs > 0, iqrs, 1.0)  # the engine treats a zero IQR as 1
    centroids = np.asarray(m["archetype_centroids"], dtype=np.float64)
    if centroids.shape != (len(m["archetype_names"]), len(names)):
        raise ValueError(f"centroid matrix {centroids.shape} does not match the feature list")
    return Reference(
        feature_names=names,
        medians=np.asarray(m["scaler_medians"], dtype=np.float64),
        iqrs=iqrs,
        weights=weights,
        engine_weights=base_w,
        caps={k: float(v) for k, v in m.get("cap_values", {}).items()},
        signal_columns=signal_columns,
        archetype_names=tuple(m["archetype_names"]),
        centroids=centroids,
        lens=lens,
        provenance=m["provenance"],
        lens_provenance=lens_prov,
    )
