"""The repository fingerprint.

A fingerprint summarises one scan in five components, each measured in the reference
frame so that it is comparable across repositories and languages:

``archetypes``  share of functions (and of function LOC) in each of the engine's 14
                function archetypes.
``signals``     repository-level density of every structural signal (hits per 100
                function LOC, log1p).
``geometry``    quantile sketches of the per-function geometry: size, complexity,
                arity, decision density (population-IQR units) and call fan-in/out.
``centroid``    the LOC-weighted centre of the repository's functions in the lens
                space, and their spread around it.
``callgraph``   shape of the resolved call graph: edges per function, leaf, root and
                hub shares, reciprocity.

The per-function vectors are kept beside the fingerprint (``FunctionTable``) for
function-level twin search.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import __version__
from . import features as F
from .reference import GEOMETRY_FEATURES, Reference
from .scan_io import ScanData

SCHEMA = "structural-fingerprint/repository/1"
QUANTILES = np.linspace(0.0, 1.0, 21)
GEOMETRY_SKETCH = ("log_loc", "log_complexity", "log_args", "func_internal_density", "log_fan_in", "log_fan_out")
CALLGRAPH_FIELDS = ("edges_per_function", "leaf_share", "root_share", "hub_share", "reciprocal_share")


@dataclass
class FunctionTable:
    """Per-function data used by twin search."""

    repo: str
    name: np.ndarray  # str
    path: np.ndarray  # str
    language: np.ndarray  # str
    loc: np.ndarray
    archetype: np.ndarray  # int, index into reference archetype names
    key: np.ndarray  # uint64 exact-measurement digest
    vectors: np.ndarray  # (n, F) float32, lens space

    def __len__(self) -> int:
        return len(self.loc)

    def save(self, path: Path) -> None:
        np.savez_compressed(path, repo=np.array(self.repo), name=self.name, path=self.path,
                            language=self.language, loc=self.loc, archetype=self.archetype, key=self.key,
                            vectors=self.vectors)

    @classmethod
    def load(cls, path: Path) -> FunctionTable:
        with np.load(path, allow_pickle=False) as z:
            return cls(repo=str(z["repo"]), name=z["name"], path=z["path"], language=z["language"],
                       loc=z["loc"], archetype=z["archetype"], key=z["key"], vectors=z["vectors"])


@dataclass
class Fingerprint:
    name: str
    data: dict  # the JSON document
    functions: FunctionTable | None = None

    @property
    def spec_hash(self) -> str:
        return self.data["spec"]["spec_hash"]

    def save(self, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = out_dir / safe_name(self.name)
        p = stem.with_suffix(".sfp.json")
        p.write_text(json.dumps(self.data, indent=1, sort_keys=False) + "\n")
        if self.functions is not None:
            self.functions.save(stem.with_suffix(".sfp.npz"))
        return p

    @classmethod
    def load(cls, path: Path) -> Fingerprint:
        path = Path(path)
        data = json.loads(path.read_text())
        if data.get("schema") != SCHEMA:
            raise ValueError(f"{path}: not a repository fingerprint ({data.get('schema')!r})")
        npz = path.with_name(path.name.removesuffix(".sfp.json") + ".sfp.npz")
        return cls(name=data["name"], data=data, functions=FunctionTable.load(npz) if npz.is_file() else None)


def safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name) or "repo"


def _weighted_mean(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    s = w.sum()
    return (x * w[:, None]).sum(0) / s if s > 0 else np.zeros(x.shape[1])


def _callgraph_shape(n: int, edges: np.ndarray) -> dict[str, float]:
    if n == 0:
        return dict.fromkeys(CALLGRAPH_FIELDS, 0.0)
    if len(edges):
        e = np.unique(edges, axis=0)
    else:
        e = np.zeros((0, 2), dtype=np.int64)
    out_deg = np.bincount(e[:, 0], minlength=n) if len(e) else np.zeros(n)
    in_deg = np.bincount(e[:, 1], minlength=n) if len(e) else np.zeros(n)
    top = max(1, int(np.ceil(n * 0.01)))
    hub = float(np.sort(in_deg)[::-1][:top].sum() / len(e)) if len(e) else 0.0
    if len(e):
        fwd = set(map(tuple, e.tolist()))
        recip = sum(1 for a, b in fwd if (b, a) in fwd) / len(fwd)
    else:
        recip = 0.0
    return {
        "edges_per_function": float(len(e) / n),
        "leaf_share": float((out_deg == 0).mean()),
        "root_share": float((in_deg == 0).mean()),
        "hub_share": hub,
        "reciprocal_share": float(recip),
    }


def _gini(x: np.ndarray) -> float:
    x = np.sort(np.asarray(x, dtype=np.float64))
    if len(x) < 2 or x.sum() == 0:
        return 0.0
    n = len(x)
    return float(((2 * np.arange(1, n + 1) - n - 1) * x).sum() / (n * x.sum()))


def build(scan: ScanData, ref: Reference, min_loc: int = 1) -> Fingerprint:
    """Fingerprint one scan. ``min_loc`` drops functions shorter than that many lines
    from every component (the engine's own archetype trainer used 3)."""
    keep = scan.loc >= min_loc
    loc = scan.loc[keep]
    raw = F.raw_features(ref, loc, scan.complexity[keep], scan.args[keep], scan.keyword_density[keep],
                         scan.signals[keep])
    z = F.standardize(ref, raw)
    vec = F.embed(ref, z)
    arch_idx, _ = F.engine_archetypes(ref, z)
    n = int(keep.sum())
    w = np.maximum(loc, 1.0)

    names = list(ref.archetype_names)
    counts = np.bincount(arch_idx, minlength=len(names)).astype(float)
    loc_mass = np.bincount(arch_idx, weights=w, minlength=len(names))
    archetypes = {
        "count_share": {a: float(c / n) if n else 0.0 for a, c in zip(names, counts, strict=True)},
        "loc_share": {a: float(m / w.sum()) if n else 0.0 for a, m in zip(names, loc_mass, strict=True)},
    }
    stored = [scan.engine_archetype[i] for i in np.flatnonzero(keep)]
    if any(stored):
        agree = sum(1 for i, s in zip(arch_idx, stored, strict=True) if s and names[i] == s)
        labelled = sum(1 for s in stored if s)
        archetypes["engine_label_agreement"] = float(agree / labelled) if labelled else None

    total_loc = float(loc.sum())
    sig_sum = scan.signals[keep].sum(0)
    signals = {c: float(np.log1p(sig_sum[j] / total_loc * 100.0)) if total_loc else 0.0
               for j, c in enumerate(ref.signal_columns)}

    geo_cols = {g: z[:, ref.feature_names.index(g)] for g in GEOMETRY_FEATURES if g != "keyword_density"}
    geo_cols["log_fan_in"] = np.log1p(scan.fan_in[keep])
    geo_cols["log_fan_out"] = np.log1p(scan.fan_out[keep])
    geometry = {
        "quantiles": [float(q) for q in QUANTILES],
        "sketch": {g: (np.quantile(geo_cols[g], QUANTILES).tolist() if n else [0.0] * len(QUANTILES))
                   for g in GEOMETRY_SKETCH},
        "complexity_gini": _gini(scan.complexity[keep]),
        "median_loc": float(np.median(loc)) if n else 0.0,
    }

    center = _weighted_mean(vec, w) if n else np.zeros(ref.n_features)
    spread = float(np.sqrt(_weighted_mean(((vec - center) ** 2).sum(1, keepdims=True), w)[0])) if n else 0.0

    kept_idx = np.flatnonzero(keep)
    remap = -np.ones(scan.n_functions, dtype=np.int64)
    remap[kept_idx] = np.arange(n)
    e = remap[scan.call_edges] if len(scan.call_edges) else np.zeros((0, 2), dtype=np.int64)
    e = e[(e >= 0).all(1)] if len(e) else e

    file_langs: Counter[str] = Counter()
    for lang, cl in zip(scan.file_language, scan.file_coding_loc, strict=True):
        file_langs[lang] += float(cl)
    func_lang = np.asarray(scan.func_language, dtype=object)[keep]
    fl = Counter(func_lang.tolist())

    doc = {
        "schema": SCHEMA,
        "name": scan.name,
        "tool": {"name": "structural-fingerprint-scanner", "version": __version__},
        "spec": {"lens": ref.lens, "spec_hash": ref.spec_hash, "min_loc": min_loc,
                 "reference": ref.provenance, "lens_source": ref.lens_provenance},
        "source": {"scan_db": str(scan.db_path), **scan.metadata,
                   "missing_signals": list(scan.missing_signals)},
        "size": {
            "functions": n,
            "functions_scanned": scan.n_functions,
            "function_loc": total_loc,
            "files": len(scan.file_path),
            "coding_loc": float(scan.file_coding_loc.sum()),
            "languages_by_coding_loc": {k: v for k, v in file_langs.most_common() if v > 0},
            "languages_by_functions": dict(fl.most_common()),
        },
        "archetypes": archetypes,
        "signals": signals,
        "geometry": geometry,
        "centroid": {"vector": center.tolist(), "spread": spread},
        "callgraph": _callgraph_shape(n, e),
    }
    table = FunctionTable(
        repo=scan.name,
        name=np.asarray([scan.func_name[i] for i in kept_idx], dtype=str),
        path=np.asarray([scan.file_path[scan.func_file[i]] for i in kept_idx], dtype=str),
        language=np.asarray(func_lang.tolist(), dtype=str),
        loc=loc.astype(np.int32),
        archetype=arch_idx.astype(np.int16),
        key=F.structural_key(loc, scan.complexity[keep], scan.args[keep], scan.signals[keep]),
        vectors=vec.astype(np.float32),
    )
    return Fingerprint(name=scan.name, data=doc, functions=table)
