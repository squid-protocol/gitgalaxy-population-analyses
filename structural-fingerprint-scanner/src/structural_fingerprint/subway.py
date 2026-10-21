"""Subway maps: each repository's call graph collapsed to its subsystems, drawn on a
reference repository's fixed layout so that every map in a cohort is comparable.

A *station* is a subsystem, sized by its functions. A *line* between two stations is the
share of the repository's resolved calls that cross between them. Stations are coloured
by **survival**: the share of the reference's functions in that subsystem that still
have a structural twin in this repository, so a map shows not only how a codebase is
wired but which parts of the reference it kept.

Each function gets a subsystem in the most reliable way available:

1. **twin**: its structural twin in the reference (name-blind; survives renaming);
2. **name**: a reference function of the same normalized name (also tried without a
   module prefix such as ``P_``);
3. **path**: the taxonomy's rules on the file path (basename prefixes, then keywords);
4. the taxonomy's fallback.

The reference itself is assigned by path rules only. Without a taxonomy file, the
subsystems are the reference's top-level directories.

Two wiring scores compare each map with the reference's: ``wiring_similarity``, the
cosine of the subsystem call-share matrices, and ``edges_kept``, the share of the
reference's function-level calls still present between the corresponding functions.
"""

from __future__ import annotations

import html
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .fingerprint import FunctionTable
from .twins import TwinParams, TwinResult, find_twins

# Files in these languages are build, data or docs; they are left off the map.
NON_CODE = frozenset({"markdown", "plaintext", "makefile", "shell", "yaml", "json", "batch", "cmake", "powershell",
                      "xml", "html", "css", "csv", "dockerfile", "toml", "ini", "nix", "unknown"})


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


@dataclass
class Taxonomy:
    name: str
    subsystems: list[str]
    basename_prefix: list[tuple[str, str]] = field(default_factory=list)
    path_keyword: list[tuple[str, str]] = field(default_factory=list)
    fallback: str = "other"
    directory_depth: int = 0  # >0: subsystem = this many leading path components
    # Per-repository path rules tried before the shared ones, for codebases whose layout
    # says plainly what a folder is (``World/``, ``Render/``, single-letter Java packages).
    overrides: dict[str, dict[str, list[tuple[str, str]]]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.fallback not in self.subsystems:
            self.subsystems.append(self.fallback)
        known = set(self.subsystems)
        rules = self.basename_prefix + self.path_keyword
        for o in self.overrides.values():
            rules = rules + list(o.get("basename_prefix", [])) + list(o.get("path_keyword", []))
        bad = {s for _, s in rules} - known
        if bad:
            raise ValueError(f"taxonomy rules name unknown subsystems: {sorted(bad)}")
        self.index = {s: i for i, s in enumerate(self.subsystems)}

    @classmethod
    def load(cls, path: Path) -> Taxonomy:
        d = json.loads(Path(path).read_text())
        return cls(name=d.get("name", Path(path).stem), subsystems=list(d["subsystems"]),
                   basename_prefix=[tuple(x) for x in d.get("basename_prefix", [])],
                   path_keyword=[tuple(x) for x in d.get("path_keyword", [])],
                   fallback=d.get("fallback", "other"),
                   overrides={repo: {k: [tuple(x) for x in v] for k, v in o.items()
                                     if k in ("basename_prefix", "path_keyword")}
                              for repo, o in d.get("overrides", {}).items()})

    @classmethod
    def from_directories(cls, reference: FunctionTable, top: int = 14) -> Taxonomy:
        """Subsystems = the reference's most populated top-level directories."""
        heads = Counter(_dir_head(p) for p, lang in zip(reference.path, reference.language, strict=True)
                        if lang not in NON_CODE)
        subs = [h for h, _ in heads.most_common(top) if h]
        return cls(name="top-level directories", subsystems=subs, directory_depth=1)

    def classify(self, path: str, repo: str | None = None) -> int:
        """Subsystem index for a file path; ``repo``'s overrides, if any, are tried first."""
        if self.directory_depth:
            return self.index.get(_dir_head(path), self.index[self.fallback])
        base = path.rsplit("/", 1)[-1].lower()
        low = "/" + path.lower()
        o = self.overrides.get(repo or "", {})
        for prefixes, keywords in ((o.get("basename_prefix", []), o.get("path_keyword", [])),
                                   (self.basename_prefix, self.path_keyword)):
            for prefix, sub in prefixes:
                if base.startswith(prefix):
                    return self.index[sub]
            for kw, sub in keywords:
                if kw in low:
                    return self.index[sub]
        return self.index[self.fallback]


def _dir_head(path: str) -> str:
    parts = [p for p in str(path).split("/") if p]
    return parts[0] if len(parts) > 1 else "(root)"


@dataclass
class SubwayMap:
    repo: str
    subsystems: list[str]
    sizes: np.ndarray  # (S,) functions per subsystem
    calls: np.ndarray  # (S, S) distinct calls, caller subsystem -> callee subsystem
    sources: dict[str, int]  # how functions were assigned
    survival: np.ndarray | None = None  # (S,) share of the reference's functions with a twin here
    wiring_similarity: float = float("nan")
    edges_kept: float = float("nan")
    graph: dict[str, float] = field(default_factory=dict)  # mapping-free shape of the function call graph
    labels: np.ndarray | None = None  # subsystem index per function of the repository's table (-1: not on the map)
    ref_twinned: np.ndarray | None = None  # per reference function: has a twin here (either direction)
    shape_distance: float = float("nan")  # distance of ``graph`` from the reference's, cohort-standardized

    @property
    def share(self) -> np.ndarray:
        t = self.calls.sum()
        return self.calls / t if t else self.calls.astype(float)

    def to_dict(self) -> dict:
        return {
            "repo": self.repo,
            "functions": int(self.sizes.sum()),
            "wiring_similarity": _f(self.wiring_similarity),
            "edges_kept": _f(self.edges_kept),
            "assigned_by": self.sources,
            "graph": {k: _f(v) for k, v in self.graph.items()},
            "shape_distance": _f(self.shape_distance),
            "stations": {s: {"functions": int(n), "survival": None if self.survival is None else _f(self.survival[i])}
                         for i, (s, n) in enumerate(zip(self.subsystems, self.sizes, strict=True))},
            "lines": [{"from": self.subsystems[a], "to": self.subsystems[b], "calls": int(self.calls[a, b])}
                      for a, b in zip(*np.nonzero(self.calls), strict=True)],
        }


def _f(x: float) -> float | None:
    return None if x is None or not np.isfinite(x) else float(x)


def _code_mask(t: FunctionTable) -> np.ndarray:
    return np.array([lang not in NON_CODE for lang in t.language], dtype=bool)


def _calls(labels: np.ndarray, edges: np.ndarray | None, s: int) -> np.ndarray:
    m = np.zeros((s, s), dtype=np.int64)
    if edges is None or not len(edges):
        return m
    a, b = labels[edges[:, 0]], labels[edges[:, 1]]
    ok = (a >= 0) & (b >= 0)
    np.add.at(m, (a[ok], b[ok]), 1)
    return m


def _name_index(t: FunctionTable, labels: np.ndarray) -> dict[str, int]:
    """normalized name -> label, plus the name without a module prefix (``P_Ticker`` -> ``ticker``)."""
    out: dict[str, int] = {}
    for n, lab in zip(t.name, labels, strict=True):
        if lab < 0:
            continue
        out.setdefault(_norm(n), int(lab))
    for n, lab in zip(t.name, labels, strict=True):
        if lab >= 0 and "_" in n:
            out.setdefault(_norm(n.split("_", 1)[1]), int(lab))
    return out


def assign(table: FunctionTable, tax: Taxonomy, ref: FunctionTable | None = None,
           ref_labels: np.ndarray | None = None, twin: TwinResult | None = None) -> tuple[np.ndarray, dict[str, int]]:
    """Subsystem index per function (-1 for non-code), and counts by assignment source."""
    labels = np.full(len(table), -1, dtype=np.int64)
    code = _code_mask(table)
    src = Counter()
    if twin is not None and ref_labels is not None:
        for qi, ti in zip(twin.q_index, twin.t_index, strict=True):
            if code[qi] and ref_labels[ti] >= 0:
                labels[qi] = ref_labels[ti]
                src["twin"] += 1
    names = _name_index(ref, ref_labels) if ref is not None and ref_labels is not None else {}
    for i in np.flatnonzero(code & (labels < 0)):
        n = str(table.name[i])
        hit = names.get(_norm(n))
        if hit is None and "_" in n:
            hit = names.get(_norm(n.split("_", 1)[1]))
        if hit is not None:
            labels[i] = hit
            src["name"] += 1
        else:
            labels[i] = tax.classify(str(table.path[i]), table.repo)
            src["path" if labels[i] != tax.index[tax.fallback] else "fallback"] += 1
    return labels, dict(src)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a.ravel(), b.ravel()
    d = np.linalg.norm(a) * np.linalg.norm(b)
    return float(a @ b / d) if d else float("nan")


GRAPH_FIELDS = ("mean_degree", "lcc_share", "clustering", "reciprocity", "hub_share", "leaf_share", "root_share",
                "in_degree_gini", "assortativity")


def graph_stats(n: int, edges: np.ndarray | None) -> dict[str, float]:
    """Shape of a directed call graph on ``n`` functions, independent of any subsystem
    mapping or layout: mean degree, largest weakly connected component share, average
    clustering (undirected), reciprocity, in-degree concentration (top 1% hub share,
    Gini), leaf and root shares, and degree assortativity."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    out = dict.fromkeys(GRAPH_FIELDS, float("nan"))
    if n == 0:
        return out
    e = np.zeros((0, 2), dtype=np.int64) if edges is None or not len(edges) else np.unique(edges, axis=0)
    e = e[e[:, 0] != e[:, 1]]
    a = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)).tocsr()
    out_deg = np.asarray(a.sum(1)).ravel()
    in_deg = np.asarray(a.sum(0)).ravel()
    u = ((a + a.T) > 0).astype(np.float64).tocsr()
    _, comp = connected_components(u, directed=False)
    deg = np.asarray(u.sum(1)).ravel()
    tri = np.asarray((u @ u).multiply(u).sum(1)).ravel() / 2
    with np.errstate(invalid="ignore", divide="ignore"):
        clust = np.where(deg >= 2, 2 * tri / (deg * (deg - 1)), 0.0)
    top = max(1, int(np.ceil(n * 0.01)))
    ui, uj = u.nonzero()
    out.update({
        "mean_degree": len(e) / n,
        "lcc_share": float(np.bincount(comp).max() / n),
        "clustering": float(clust.mean()),
        "reciprocity": float(a.multiply(a.T).nnz / a.nnz) if a.nnz else 0.0,
        "hub_share": float(np.sort(in_deg)[::-1][:top].sum() / in_deg.sum()) if in_deg.sum() else 0.0,
        "leaf_share": float((out_deg == 0).mean()),
        "root_share": float((in_deg == 0).mean()),
        "in_degree_gini": _gini(in_deg),
        "assortativity": float(np.corrcoef(deg[ui], deg[uj])[0, 1]) if len(ui) > 2 and deg[ui].std() > 0 else 0.0,
    })
    return out


def _gini(x: np.ndarray) -> float:
    x = np.sort(np.asarray(x, dtype=float))
    if len(x) < 2 or x.sum() == 0:
        return 0.0
    k = np.arange(1, len(x) + 1)
    return float(((2 * k - len(x) - 1) * x).sum() / (len(x) * x.sum()))


def _shape_vector(g: dict[str, float]) -> np.ndarray:
    v = np.array([g[f] for f in GRAPH_FIELDS], dtype=float)
    v[0] = math.log1p(v[0]) if np.isfinite(v[0]) else v[0]
    return v


def _set_shape_distances(maps: list[SubwayMap]) -> None:
    """Distance of each map's graph shape from the reference's (maps[0]), each field
    standardized by its spread across the cohort, RMS over fields."""
    m = np.array([_shape_vector(x.graph) for x in maps])
    m = np.where(np.isfinite(m), m, np.nanmean(m, axis=0))
    sd = m.std(0)
    z = (m - m.mean(0)) / np.where(sd > 0, sd, 1.0)
    for x, row in zip(maps, z, strict=True):
        x.shape_distance = float(np.sqrt(np.mean((row - z[0]) ** 2)))


def mapping_check(maps: list[SubwayMap]) -> dict:
    """Is subway wiring similarity an artefact of the subsystem mapping? Compare it with
    the mapping-free graph-shape distance across the cohort (Spearman). A clearly
    negative rho means the two agree on which repositories stayed close to the reference."""
    from scipy.stats import spearmanr

    pts = [(x.wiring_similarity, x.shape_distance) for x in maps[1:]
           if np.isfinite(x.wiring_similarity) and np.isfinite(x.shape_distance)]
    if len(pts) < 4:
        return {"n": len(pts), "spearman_rho": None, "p_value": None}
    r = spearmanr([p[0] for p in pts], [p[1] for p in pts])
    return {"n": len(pts), "spearman_rho": float(r.statistic), "p_value": float(r.pvalue)}


def lineage_order(maps: list[SubwayMap], declared: dict[str, list[str]] | None) -> list[SubwayMap]:
    """Reference first, then its declared descendants depth-first (siblings by wiring),
    then everything else by wiring."""
    def wiring(m: SubwayMap) -> float:
        return m.wiring_similarity if np.isfinite(m.wiring_similarity) else -1.0

    by = {m.repo: m for m in maps}
    rest = sorted(maps[1:], key=lambda m: -wiring(m))
    if not declared:
        return [maps[0], *rest]
    children: dict[str, list[SubwayMap]] = {}
    for m in rest:
        for p in declared.get(m.repo, []):
            if p in by:
                children.setdefault(p, []).append(m)
                break
    out, seen = [], set()

    def visit(m: SubwayMap) -> None:
        if m.repo in seen:
            return
        seen.add(m.repo)
        out.append(m)
        for c in children.get(m.repo, []):
            visit(c)

    visit(maps[0])
    return out + [m for m in rest if m.repo not in seen]


def _edges_kept(ref: FunctionTable, port: FunctionTable, ref_to_port: TwinResult | None,
                max_candidates: int = 4) -> float:
    """Share of the reference's calls (u -> v) whose counterparts in the port also call
    each other. A function's counterpart is its structural twin; failing that, the port
    functions of the same normalized name (also tried without a module prefix). A name
    can occur more than once (a port shipping a generated single-file build beside its
    sources); up to ``max_candidates`` same-named functions are tried, and the call counts
    as kept if any pair of candidates is connected."""
    if ref.edges is None or not len(ref.edges) or port.edges is None:
        return float("nan")
    twin = {}
    if ref_to_port is not None:
        twin = {int(q): int(t) for q, t in zip(ref_to_port.q_index, ref_to_port.t_index, strict=True)}
    by_name: dict[str, list[int]] = {}
    for j, n in enumerate(port.name):
        by_name.setdefault(_norm(str(n)), []).append(j)

    def candidates(i: int) -> list[int]:
        if i in twin:
            return [twin[i]]
        n = str(ref.name[i])
        js = by_name.get(_norm(n)) or (by_name.get(_norm(n.split("_", 1)[1])) if "_" in n else None) or []
        return js if len(js) <= max_candidates else []

    port_edges = set(map(tuple, port.edges.tolist()))
    kept = total = 0
    for u, v in ref.edges.tolist():
        total += 1
        cu, cv = candidates(u), candidates(v)
        if any((a, b) in port_edges for a in cu for b in cv):
            kept += 1
    return kept / total if total else float("nan")


def twinned(n_ref: int, ref_to_port: TwinResult, port_to_ref: TwinResult) -> np.ndarray:
    """Per reference function: linked to a twin in the port in either direction."""
    has = np.zeros(n_ref, dtype=bool)
    has[ref_to_port.q_index] = True
    has[port_to_ref.t_index] = True
    return has


def _survival(ref_labels: np.ndarray, ref: FunctionTable, ref_to_port: TwinResult, port_to_ref: TwinResult,
              s: int, min_loc: int) -> np.ndarray:
    """Per subsystem, the share of the reference's eligible functions linked to a twin in
    either direction. Both directions count because a port that carries a function more
    than once (two copies, or a generated build beside its sources) fails the
    reference-side distinctiveness test while its own copies still find the reference."""
    eligible = (ref.loc >= min_loc) & (ref_labels >= 0)
    has = twinned(len(ref), ref_to_port, port_to_ref)
    out = np.full(s, np.nan)
    for k in range(s):
        m = eligible & (ref_labels == k)
        if m.any():
            out[k] = has[m].mean()
    return out


def build_maps(tables: list[FunctionTable], reference: str, tax: Taxonomy | None = None,
               params: TwinParams | None = None) -> tuple[list[SubwayMap], Taxonomy, np.ndarray]:
    """One map per table, all on the reference's subsystems. Returns (maps, taxonomy, layout)."""
    by = {t.repo: t for t in tables}
    if reference not in by:
        raise ValueError(f"reference {reference!r} is not in the cohort ({', '.join(sorted(by))})")
    p = params or TwinParams()
    ref = by[reference]
    tax = tax or Taxonomy.from_directories(ref)
    s = len(tax.subsystems)
    ref_labels = np.where(_code_mask(ref), [tax.classify(str(x), ref.repo) for x in ref.path], -1).astype(np.int64)
    ref_map = SubwayMap(reference, tax.subsystems, np.bincount(ref_labels[ref_labels >= 0], minlength=s),
                        _calls(ref_labels, ref.edges, s), {"path": int((ref_labels >= 0).sum())},
                        survival=np.where(np.bincount(ref_labels[ref_labels >= 0], minlength=s) > 0, 1.0, np.nan))
    ref_map.wiring_similarity, ref_map.edges_kept = 1.0, 1.0
    ref_map.graph = _code_graph_stats(ref)
    ref_map.labels = ref_labels
    maps = [ref_map]
    for t in tables:
        if t.repo == reference:
            continue
        to_ref = find_twins(t, ref, p)
        from_ref = find_twins(ref, t, p)
        labels, src = assign(t, tax, ref, ref_labels, to_ref)
        m = SubwayMap(t.repo, tax.subsystems, np.bincount(labels[labels >= 0], minlength=s),
                      _calls(labels, t.edges, s), src, survival=_survival(ref_labels, ref, from_ref, to_ref, s, p.min_loc))
        m.wiring_similarity = _cosine(m.share, ref_map.share)
        m.edges_kept = _edges_kept(ref, t, from_ref)
        m.graph = _code_graph_stats(t)
        m.labels = labels
        m.ref_twinned = twinned(len(ref), from_ref, to_ref)
        maps.append(m)
    _set_shape_distances(maps)
    return maps, tax, layout(ref_map)


def _code_graph_stats(t: FunctionTable) -> dict[str, float]:
    code = _code_mask(t)
    remap = -np.ones(len(t), dtype=np.int64)
    remap[code] = np.arange(int(code.sum()))
    e = remap[t.edges] if t.edges is not None and len(t.edges) else np.zeros((0, 2), dtype=np.int64)
    e = e[(e >= 0).all(1)] if len(e) else e
    return graph_stats(int(code.sum()), e)


def layout(ref_map: SubwayMap, seed: int = 7, iterations: int = 600) -> np.ndarray:
    """Seeded Fruchterman-Reingold layout of the reference's subsystem graph, in [0, 1]^2.
    Stations the reference never calls between settle at the rim."""
    s = len(ref_map.subsystems)
    w = (ref_map.calls + ref_map.calls.T).astype(float)
    np.fill_diagonal(w, 0.0)
    if w.max() > 0:
        w /= w.max()
    rng = np.random.default_rng(seed)
    pos = rng.random((s, 2))
    k = 1.6 / math.sqrt(max(s, 1))
    temp = 0.1
    for _ in range(iterations):
        delta = pos[:, None, :] - pos[None, :, :]
        dist = np.sqrt((delta ** 2).sum(-1)) + 1e-9
        rep = (k * k / dist ** 2)[:, :, None] * delta
        att = (w * dist / k)[:, :, None] * delta
        disp = (rep - att).sum(1)
        length = np.sqrt((disp ** 2).sum(1))[:, None] + 1e-9
        pos += disp / length * np.minimum(length, temp)
        temp *= 0.992
    pos -= pos.min(0)
    span = pos.max(0)
    pos /= np.where(span > 0, span, 1.0)
    # Push apart stations that ended up on top of each other, so labels stay readable.
    gap = 0.75 / math.sqrt(max(s, 1))
    for _ in range(300):
        delta = pos[:, None, :] - pos[None, :, :]
        dist = np.sqrt((delta ** 2).sum(-1)) + np.eye(s)
        push = np.clip(gap - dist, 0.0, None) * (1 - np.eye(s))
        if not push.any():
            break
        pos += (push[:, :, None] * delta / dist[:, :, None]).sum(1) * 0.5
        pos = np.clip(pos, 0.0, 1.0)
    return 0.08 + 0.84 * pos


# ---------------------------------------------------------------- rendering

def map_svg(m: SubwayMap, pos: np.ndarray, size: int = 230, labels: bool = False) -> str:
    from .html import _color, sqrt_share_scale

    scale = sqrt_share_scale("")
    xy = pos * size
    share = m.calls + m.calls.T
    np.fill_diagonal(share, 0)
    tot = share[np.triu_indices(len(share), 1)].sum() or 1
    out = [(f'<svg class="subway" width="{size}" height="{size}" viewBox="0 0 {size} {size}" role="img" '
            f'aria-label="{html.escape(m.repo)} subway map">')]
    for a in range(len(share)):
        for b in range(a + 1, len(share)):
            frac = share[a, b] / tot
            if frac < 0.004:
                continue
            tip = html.escape(f"{m.repo}: {m.subsystems[a]} ↔ {m.subsystems[b]}, {100 * frac:.1f}% of cross-subsystem calls")
            out.append(f'<line x1="{xy[a, 0]:.1f}" y1="{xy[a, 1]:.1f}" x2="{xy[b, 0]:.1f}" y2="{xy[b, 1]:.1f}" '
                       f'stroke-width="{0.5 + 11 * frac:.2f}" data-tip="{tip}"/>')
    biggest = max(int(m.sizes.max()), 1)
    for i, sub in enumerate(m.subsystems):
        n = int(m.sizes[i])
        if not n:
            continue
        r = 3 + 15 * math.sqrt(n / biggest)
        sv = None if m.survival is None else m.survival[i]
        fill = _color(scale.score(sv)) if sv is not None and np.isfinite(sv) else "var(--diag)"
        surv = "" if sv is None or not np.isfinite(sv) else f", {100 * sv:.0f}% of the reference's {sub} survives"
        tip = html.escape(f"{m.repo} · {sub}: {n} functions{surv}")
        out.append(f'<circle cx="{xy[i, 0]:.1f}" cy="{xy[i, 1]:.1f}" r="{r:.1f}" fill="{fill}" data-tip="{tip}"/>')
        if labels:
            out.append(f'<text x="{xy[i, 0]:.1f}" y="{xy[i, 1] + r + 11:.1f}" text-anchor="middle">{html.escape(sub)}</text>')
    out.append("</svg>")
    return "".join(out)


def scatter_svg(points: list[tuple[str, float, float]], xlabel: str, ylabel: str, w: int = 640, h: int = 420) -> str:
    """Labelled dot plot (x right, y up) with hover tooltips."""
    pts = [(n, x, y) for n, x, y in points if np.isfinite(x) and np.isfinite(y)]
    if not pts:
        return ""
    pad_l, pad_b, pad_t, pad_r = 52, 40, 12, 90
    xs, ys = [p[1] for p in pts], [p[2] for p in pts]
    x0, x1 = min(0.0, min(xs)), max(xs) * 1.05 or 1
    y0, y1 = min(0.0, min(ys)), max(1.0, max(ys))

    def sx(x):
        return pad_l + (x - x0) / (x1 - x0) * (w - pad_l - pad_r)

    def sy(y):
        return h - pad_b - (y - y0) / (y1 - y0) * (h - pad_b - pad_t)

    out = [f'<svg class="scatter" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(ylabel)}">',
           f'<line class="axis" x1="{pad_l}" y1="{h - pad_b}" x2="{w - pad_r}" y2="{h - pad_b}"/>',
           f'<line class="axis" x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{h - pad_b}"/>']
    for t in np.linspace(y0, y1, 5):
        out.append(f'<text x="{pad_l - 6}" y="{sy(t) + 4:.1f}" text-anchor="end">{t:.2f}</text>')
    for t in np.linspace(x0, x1, 5):
        out.append(f'<text x="{sx(t):.1f}" y="{h - pad_b + 16}" text-anchor="middle">{t:.2f}</text>')
    out.append(f'<text x="{(pad_l + w - pad_r) / 2:.0f}" y="{h - 4}" text-anchor="middle">{html.escape(xlabel)}</text>')
    out.append(f'<text transform="translate(12,{(h - pad_b) / 2:.0f}) rotate(-90)" text-anchor="middle">{html.escape(ylabel)}</text>')
    placed: list[tuple[float, float, float]] = []  # label boxes already drawn: (x, y, width)
    for n, x, y in sorted(pts, key=lambda p: -(p[1] + p[2])):
        tip = html.escape(f"{n}: {xlabel} {x:.2f}, {ylabel} {y:.2f}")
        cx, cy = sx(x), sy(y)
        out.append(f'<circle class="dot" cx="{cx:.1f}" cy="{cy:.1f}" r="5" data-tip="{tip}"/>')
        lw = 6 * len(n)
        # Label only where it does not collide with an earlier label; every dot keeps its tooltip.
        if all(abs(cy - py) > 11 or cx + 7 > px + pw or cx + 7 + lw < px for px, py, pw in placed):
            placed.append((cx + 7, cy, lw))
            out.append(f'<text class="dl" x="{cx + 7:.1f}" y="{cy + 3:.1f}">{html.escape(n)}</text>')
    out.append("</svg>")
    return "".join(out)


def render_section(maps: list[SubwayMap], pos: np.ndarray, tax: Taxonomy, reference: str,
                   profile_to_reference: dict[str, float] | None = None,
                   declared: dict[str, list[str]] | None = None) -> str:
    from .html import _legend, sqrt_share_scale

    order = lineage_order(maps, declared)
    check = mapping_check(maps)
    panels = []
    for m in order:
        is_ref = m.repo == reference
        sub = "reference layout" if is_ref else (
            f"wiring {m.wiring_similarity:.2f} · calls kept {100 * m.edges_kept:.0f}%"
            if np.isfinite(m.edges_kept) else f"wiring {m.wiring_similarity:.2f}")
        panels.append(f'<figure class="panel{" ref" if is_ref else ""}"><figcaption><strong>{html.escape(m.repo)}</strong>'
                      f"<span>{int(m.sizes.sum()):,} functions · {html.escape(sub)}</span></figcaption>"
                      f"{map_svg(m, pos, size=460 if is_ref else 230, labels=is_ref)}</figure>")
    scale = sqrt_share_scale(f"station colour: share of {reference}'s subsystem that survives (square-root scale)")
    fallback = tax.index[tax.fallback]

    def pct(x: float) -> str:
        return "" if x is None or not np.isfinite(x) else f"{100 * x:.0f}%"

    rows = "".join(
        f"<tr><th scope=row>{html.escape(m.repo)}</th><td class=num>{int(m.sizes.sum()):,}</td>"
        f"<td class=num>{m.wiring_similarity:.2f}</td><td class=num>{pct(m.edges_kept)}</td>"
        f"<td class=num>{pct(m.sizes[fallback] / m.sizes.sum() if m.sizes.sum() else float('nan'))}</td>"
        f"<td class=num>{pct(m.graph.get('lcc_share', float('nan')))}</td>"
        f"<td class=num>{m.graph.get('clustering', float('nan')):.3f}</td>"
        f"<td class=num>{m.shape_distance:.2f}</td>"
        f"<td>{html.escape(', '.join(f'{k} {v:,}' for k, v in sorted(m.sources.items(), key=lambda kv: -kv[1])))}</td></tr>"
        for m in order)
    rho = check.get("spearman_rho")
    check_html = ("" if rho is None else
                  "<h3>Mapping-free check</h3><p class=note>The subway maps depend on how functions are assigned "
                  "to subsystems. As a check that needs no mapping or layout, each repository's raw call graph is "
                  "summarised by its shape (mean degree, largest component, clustering, reciprocity, hub "
                  "concentration, leaf and root shares, in-degree Gini, assortativity) and compared with "
                  f"{html.escape(reference)}'s. Across {check['n']} repositories, wiring similarity and this "
                  f"graph-shape distance have Spearman ρ = <strong>{rho:.2f}</strong> (p = {check['p_value']:.2g})"
                  + ("; they agree on which repositories stayed close.</p>" if rho < -0.3 else
                     "; they do not clearly agree, so read the wiring scores with care.</p>")
                  + scatter_svg([(m.repo, m.shape_distance, m.wiring_similarity) for m in order if m.repo != reference],
                                f"graph-shape distance from {reference}", f"wiring similarity to {reference}"))
    scatter = ""
    if profile_to_reference:
        pts = [(m.repo, profile_to_reference.get(m.repo, float("nan")), m.wiring_similarity) for m in order
               if m.repo != reference]
        scatter = (("<h3>Structure against wiring</h3><p class=note>How far each repository's fingerprint has "
                    f"drifted from {html.escape(reference)} (profile distance) against how much of its subsystem "
                    "wiring it kept.</p>")
                   + scatter_svg(pts, f"profile distance from {reference}", f"wiring similarity to {reference}"))
    return (f"<section><h2>Subway maps</h2><p class=note>Each repository's call graph collapsed to the "
            f"{html.escape(tax.name)} ({len(tax.subsystems)} stations) and drawn on {html.escape(reference)}'s layout. "
            "Station size: functions. Line width: share of calls between two subsystems. Functions are placed by "
            f"structural twin in {html.escape(reference)} first, then by name, then by path. "
            "<em>Wiring</em> is the cosine similarity of the subsystem call matrix to the reference's; "
            "<em>calls kept</em> is the share of the reference's calls still made between the corresponding functions. "
            + ("Maps follow the declared lineage from the reference; the rest are ordered by wiring. "
               if declared else "Maps are ordered by wiring. ")
            + f"A large <em>{html.escape(tax.fallback)}</em> station is code the reference has no subsystem for "
            "(new features, scripting, tools): a finding to explain, not noise.</p>"
            f"{_legend(scale)}<div class=subways>{''.join(panels)}</div>{scatter}{check_html}"
            "<div class=tablewrap><table><thead><tr><th>Repository</th><th class=num>Functions on map</th>"
            "<th class=num>Wiring</th><th class=num>Calls kept</th>"
            f"<th class=num>{html.escape(tax.fallback)}</th><th class=num>Largest component</th>"
            "<th class=num>Clustering</th><th class=num>Shape distance</th><th>Placed by</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div></section>")


def write_outputs(out: Path, maps: list[SubwayMap], tax: Taxonomy, reference: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "subway.json").write_text(json.dumps({"reference": reference, "taxonomy": tax.name,
                                                 "subsystems": tax.subsystems, "mapping_check": mapping_check(maps),
                                                 "maps": [m.to_dict() for m in maps]}, indent=1) + "\n")
    with open(out / "subway.csv", "w") as f:
        f.write("repo,functions,wiring_similarity,edges_kept,shape_distance,"
                + ",".join(GRAPH_FIELDS) + "," + ",".join(f"survival_{s}" for s in tax.subsystems) + "\n")
        for m in maps:
            surv = ["" if m.survival is None or not np.isfinite(v) else f"{v:.4f}"
                    for v in (m.survival if m.survival is not None else [np.nan] * len(tax.subsystems))]
            ek = "" if not np.isfinite(m.edges_kept) else f"{m.edges_kept:.4f}"
            g = ["" if not np.isfinite(m.graph.get(k, float("nan"))) else f"{m.graph[k]:.4f}" for k in GRAPH_FIELDS]
            f.write(f"{m.repo},{int(m.sizes.sum())},{m.wiring_similarity:.4f},{ek},{m.shape_distance:.4f},"
                    + ",".join(g) + "," + ",".join(surv) + "\n")
