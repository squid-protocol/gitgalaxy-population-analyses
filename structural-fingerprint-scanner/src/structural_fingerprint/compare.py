"""Distances between repository fingerprints.

Each fingerprint component has its own distance, in units that mean something on
their own:

``archetypes``  Jensen-Shannon distance between archetype mixes (0 = identical mix,
                1 = disjoint), base 2.
``signals``     root-mean-square difference of the log1p signal densities, i.e. the
                typical per-signal log ratio of how often each structure occurs.
``geometry``    mean 1-Wasserstein distance between the per-function geometry
                distributions, estimated from the quantile sketches, in population
                IQR units (fan-in/out in log1p units).
``centroid``    distance between the LOC-weighted function centres, per feature, in
                the lens space (population IQR units, weighted).
``callgraph``   Euclidean distance between call-graph shape vectors (log1p of edges
                per function, then four shares), per field.

For a cohort of three or more, the composite *structural distance* rescales each
component by its median across the cohort's pairs, so that no component dominates by
its units, and averages them with the given weights. A composite of 1.0 is a typical
pair for that cohort; 0.5 is twice as close as typical.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .fingerprint import CALLGRAPH_FIELDS, GEOMETRY_SKETCH, Fingerprint

COMPONENTS = ("archetypes", "signals", "geometry", "centroid", "callgraph")
DEFAULT_WEIGHTS = dict.fromkeys(COMPONENTS, 1.0)


class IncomparableError(ValueError):
    pass


def check_comparable(fps: list[Fingerprint]) -> None:
    hashes = {fp.spec_hash for fp in fps}
    if len(hashes) > 1:
        detail = ", ".join(f"{fp.name}={fp.spec_hash}" for fp in fps)
        raise IncomparableError(f"fingerprints were built in different reference frames ({detail}); "
                                "rebuild them with the same scanner version and lens")
    lens_min = {fp.data["spec"]["min_loc"] for fp in fps}
    if len(lens_min) > 1:
        raise IncomparableError(f"fingerprints use different --min-loc values: {sorted(lens_min)}")


def _vec(d: dict) -> np.ndarray:
    return np.asarray(list(d.values()), dtype=np.float64)


def _js_distance(p: np.ndarray, q: np.ndarray) -> float:
    p = p / p.sum() if p.sum() > 0 else np.full_like(p, 1 / len(p))
    q = q / q.sum() if q.sum() > 0 else np.full_like(q, 1 / len(q))
    m = 0.5 * (p + q)

    def kl(a: np.ndarray, b: np.ndarray) -> float:
        nz = a > 0
        return float((a[nz] * np.log2(a[nz] / b[nz])).sum())

    return math.sqrt(max(0.0, 0.5 * kl(p, m) + 0.5 * kl(q, m)))


def _callgraph_vec(cg: dict) -> np.ndarray:
    v = np.asarray([cg[f] for f in CALLGRAPH_FIELDS], dtype=np.float64)
    v[0] = math.log1p(v[0])
    return v


def component_distances(a: Fingerprint, b: Fingerprint) -> dict[str, float]:
    da, db = a.data, b.data
    sig_a, sig_b = _vec(da["signals"]), _vec(db["signals"])
    geo = [float(np.mean(np.abs(np.asarray(da["geometry"]["sketch"][g]) - np.asarray(db["geometry"]["sketch"][g]))))
           for g in GEOMETRY_SKETCH]
    ca, cb = np.asarray(da["centroid"]["vector"]), np.asarray(db["centroid"]["vector"])
    ga, gb = _callgraph_vec(da["callgraph"]), _callgraph_vec(db["callgraph"])
    return {
        "archetypes": _js_distance(_vec(da["archetypes"]["count_share"]), _vec(db["archetypes"]["count_share"])),
        "signals": float(np.sqrt(np.mean((sig_a - sig_b) ** 2))),
        "geometry": float(np.mean(geo)),
        "centroid": float(np.linalg.norm(ca - cb) / math.sqrt(len(ca))),
        "callgraph": float(np.linalg.norm(ga - gb) / math.sqrt(len(ga))),
    }


@dataclass
class Cohort:
    names: list[str]
    components: dict[str, np.ndarray]  # each (n, n)
    scales: dict[str, float]
    weights: dict[str, float]
    composite: np.ndarray | None  # (n, n), None for fewer than three repositories

    def pair(self, i: int, j: int) -> dict:
        out = {c: float(self.components[c][i, j]) for c in COMPONENTS}
        if self.composite is not None:
            out["composite"] = float(self.composite[i, j])
        return out

    def nearest(self, k: int = 3) -> dict[str, list[tuple[str, float]]]:
        if self.composite is None:
            raise ValueError("nearest relatives need a cohort of three or more")
        out = {}
        for i, n in enumerate(self.names):
            order = [j for j in np.argsort(self.composite[i]) if j != i][:k]
            out[n] = [(self.names[j], float(self.composite[i, j])) for j in order]
        return out


def compare_cohort(fps: list[Fingerprint], weights: dict[str, float] | None = None) -> Cohort:
    check_comparable(fps)
    w = dict(DEFAULT_WEIGHTS, **(weights or {}))
    unknown = set(w) - set(COMPONENTS)
    if unknown:
        raise ValueError(f"unknown component weight(s): {sorted(unknown)}")
    n = len(fps)
    comps = {c: np.zeros((n, n)) for c in COMPONENTS}
    for i in range(n):
        for j in range(i + 1, n):
            for c, v in component_distances(fps[i], fps[j]).items():
                comps[c][i, j] = comps[c][j, i] = v
    scales: dict[str, float] = {}
    composite = None
    if n >= 3:
        iu = np.triu_indices(n, 1)
        total = sum(w.values())
        composite = np.zeros((n, n))
        for c in COMPONENTS:
            med = float(np.median(comps[c][iu]))
            scales[c] = med if med > 0 else 1.0
            composite += w[c] * comps[c] / scales[c]
        composite /= total if total > 0 else 1.0
    return Cohort(names=[fp.name for fp in fps], components=comps, scales=scales, weights=w, composite=composite)


def explain(a: Fingerprint, b: Fingerprint, top: int = 8) -> dict:
    """What separates two fingerprints, component by component, largest first."""
    da, db = a.data, b.data
    sig = sorted(((s, db["signals"][s] - da["signals"][s]) for s in da["signals"]), key=lambda kv: -abs(kv[1]))
    arch_a, arch_b = da["archetypes"]["count_share"], db["archetypes"]["count_share"]
    arch = sorted(((k, arch_b[k] - arch_a[k]) for k in arch_a), key=lambda kv: -abs(kv[1]))
    mid = len(da["geometry"]["quantiles"]) // 2
    p90 = round(0.9 * (len(da["geometry"]["quantiles"]) - 1))
    geo = []
    for g in GEOMETRY_SKETCH:
        qa, qb = da["geometry"]["sketch"][g], db["geometry"]["sketch"][g]
        geo.append({"feature": g, "median": [qa[mid], qb[mid]], "p90": [qa[p90], qb[p90]],
                    "median_shift": qb[mid] - qa[mid]})
    geo.sort(key=lambda r: -abs(r["median_shift"]))
    cg = [{"field": f, a.name: da["callgraph"][f], b.name: db["callgraph"][f],
           "shift": db["callgraph"][f] - da["callgraph"][f]} for f in CALLGRAPH_FIELDS]
    return {
        "pair": [a.name, b.name],
        "distances": component_distances(a, b),
        "signals": [{"signal": s, "per_100_loc": [math.expm1(da["signals"][s]), math.expm1(db["signals"][s])],
                     "log1p_shift": d} for s, d in sig[:top]],
        "archetypes": [{"archetype": k, "share_shift": d, a.name: arch_a[k], b.name: arch_b[k]} for k, d in arch[:top]],
        "geometry": geo,
        "callgraph": cg,
    }
