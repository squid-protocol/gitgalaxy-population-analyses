"""Function vectors in the reference frame.

``raw_features`` reproduces the engine's function-archetype feature construction
(``SignalProcessor`` in gitgalaxy ``metrics/signal_processor.py``) column for column:
log1p of size, complexity and arity; vocabulary density; decisions per line; and, for
each signal, ``log1p(min(hits / loc * 100, cap))``. ``standardize`` applies the
reference robust scaler, and ``embed`` the active lens's weights. ``engine_archetypes``
applies the engine's weights and nearest-centroid rule, so its labels match the
labels the engine wrote into the scan; the test suite checks that parity on real scans.
"""

from __future__ import annotations

import numpy as np

from .reference import DENSITY_PREFIX, Reference


def raw_features(ref: Reference, loc, complexity, args, keyword_density, signals) -> np.ndarray:
    loc = np.asarray(loc, dtype=np.float64)
    complexity = np.asarray(complexity, dtype=np.float64)
    denom = np.where(loc > 0, loc, 1.0)
    cols = []
    sig_index = {c: j for j, c in enumerate(ref.signal_columns)}
    for name in ref.feature_names:
        if name == "log_loc":
            cols.append(np.log1p(loc))
        elif name == "log_complexity":
            cols.append(np.log1p(complexity))
        elif name == "log_args":
            cols.append(np.log1p(np.asarray(args, dtype=np.float64)))
        elif name == "keyword_density":
            cols.append(np.asarray(keyword_density, dtype=np.float64))
        elif name == "func_internal_density":
            cols.append(complexity / denom)
        elif name.startswith(DENSITY_PREFIX):
            col = name[len(DENSITY_PREFIX):]
            dens = signals[:, sig_index[col]] / denom * 100.0
            cap = ref.caps.get(col)
            if cap is not None:
                dens = np.minimum(dens, cap)
            cols.append(np.log1p(dens))
        else:  # pragma: no cover - load_reference rejects unknown feature names
            raise ValueError(f"unknown feature {name}")
    return np.column_stack(cols) if cols else np.zeros((len(loc), 0))


def standardize(ref: Reference, raw: np.ndarray) -> np.ndarray:
    """Population-IQR units: 0 is the population median for that feature."""
    return (raw - ref.medians) / ref.iqrs


def embed(ref: Reference, standardized: np.ndarray) -> np.ndarray:
    """The lens's weighted space, where Euclidean distance is structural distance."""
    return standardized * ref.weights


def engine_archetypes(ref: Reference, standardized: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Nearest engine centroid per function: (archetype index, distance)."""
    x = standardized * ref.engine_weights
    if len(x) == 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0)
    d2 = (x * x).sum(1)[:, None] - 2 * x @ ref.centroids.T + (ref.centroids * ref.centroids).sum(1)[None, :]
    idx = np.argmin(d2, axis=1)
    return idx, np.sqrt(np.maximum(d2[np.arange(len(x)), idx], 0.0))


def structural_key(loc, complexity, args, signals) -> np.ndarray:
    """A hash of the exact raw measurement tuple: equal keys mean the engine measured
    two functions identically (same size, decisions, arity and every signal count)."""
    m = np.column_stack([np.asarray(loc), np.asarray(complexity), np.asarray(args), signals]).astype(np.int64)
    # FNV-1a over the columns: a stable 64-bit digest per row, comparable across scans.
    h = np.full(len(m), np.uint64(1469598103934665603))
    prime = np.uint64(1099511628211)
    with np.errstate(over="ignore"):
        for j in range(m.shape[1]):
            h = (h ^ m[:, j].astype(np.uint64)) * prime
    return h
