"""Blind placement: put a port's functions into the reference's subsystems from extracted
structure alone, and measure how much of the subway wiring survives without names.

``subway.assign`` places a port's functions by structural twin, then by function name,
then by file path. Across languages twins rarely match, so a translation's map is drawn
mostly from names and paths, and its wiring similarity is partly a names-and-paths
result. This module asks whether the engine's extracted structure on its own (per-function
measurements, archetypes, and the topology of the resolved call graph) recovers the same
placement.

What the blind placement may read, per function: the lens vector (size, complexity,
arity, vocabulary and decision density, signal densities), the engine archetype, and the
call graph *as edges between row indices*. It never reads a name, a path, a language, a
file grouping, or the row order (rows are grouped by file, so order is a path proxy: the
placement is permutation-equivariant and the tests check that). ``calls_out_to`` in the
scan holds callee names; only the engine-resolved edges are used, and no name of the port
is ever compared with a name of the reference.

Two placements are offered:

``features``  each function takes the majority subsystem of its nearest reference
              functions in a descriptor space (lens vector + graph roles, each column
              rank-normalized within its repository so a language's offsets cancel).
``fgw``       fused Gromov-Wasserstein alignment of the port's call graph to the
              reference's: a soft coupling that keeps functions near each other in
              the port near each other in the reference (hop distances) while matching
              descriptors, solved by entropic mirror descent; votes are then smoothed
              over the port's call graph (label propagation).

A function's subsystem is the one with most of its vote (``decision="argmax"``) or the
one whose vote is largest relative to that subsystem's share of the reference
(``"lift"``), so a diffuse vote does not default to the largest subsystem.

The answer key is the name/path placement of ``subway.assign`` (noisy, but independent of
anything the blind placement reads). Every score comes with nulls: the same labels
shuffled across functions (subsystem sizes kept); for wiring also the blind partition
with its subsystem names shuffled; and the whole method rerun on a degree-preserving
rewiring of the port's call graph, which measures what the method manufactures from
measurements and degrees alone. ``examples/doom/blind_placement.md`` has the DOOM results.

Run: ``python -m structural_fingerprint.blind SCANS --reference linuxdoom --taxonomy
examples/doom/subsystems.json --ports gore,doom-scheme -o blind.json``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import shortest_path
from scipy.special import logsumexp

from .fingerprint import FunctionTable
from .reference import GEOMETRY_FEATURES
from .subway import Taxonomy, _code_mask, _cosine, _name_index, _norm
from .twins import TwinResult

N_GEOMETRY = len(GEOMETRY_FEATURES)  # the lens vector starts with the geometry features

# ------------------------------------------------------------------ answer key


def answer_key(port: FunctionTable, tax: Taxonomy, ref: FunctionTable, ref_labels: np.ndarray,
               twin: TwinResult | None = None) -> tuple[np.ndarray, np.ndarray]:
    """``subway.assign``'s placement, with the source of every label: (labels, sources),
    sources one of ``twin``, ``name``, ``path``, ``fallback`` or ``""`` for non-code."""
    labels = np.full(len(port), -1, dtype=np.int64)
    src = np.full(len(port), "", dtype=object)
    code = _code_mask(port)
    if twin is not None:
        for qi, ti in zip(twin.q_index, twin.t_index, strict=True):
            if code[qi] and ref_labels[ti] >= 0:
                labels[qi], src[qi] = ref_labels[ti], "twin"
    names = _name_index(ref, ref_labels)
    for i in np.flatnonzero(code & (labels < 0)):
        n = str(port.name[i])
        hit = names.get(_norm(n))
        if hit is None and "_" in n:
            hit = names.get(_norm(n.split("_", 1)[1]))
        if hit is not None:
            labels[i], src[i] = hit, "name"
        else:
            labels[i] = tax.classify(str(port.path[i]), port.repo)
            src[i] = "path" if labels[i] != tax.index[tax.fallback] else "fallback"
    return labels, src


# ------------------------------------------------------------------ the blind view


@dataclass
class BlindView:
    """Everything the blind placement is allowed to see of one repository: code functions
    only, re-indexed 0..n-1. ``rows`` maps back to the repository's function table."""

    repo: str
    rows: np.ndarray
    vectors: np.ndarray  # (n, F) lens space
    archetype: np.ndarray  # (n,)
    loc: np.ndarray  # (n,)
    edges: np.ndarray  # (e, 2) distinct caller -> callee, no self loops

    @property
    def n(self) -> int:
        return len(self.rows)


def blind_view(t: FunctionTable) -> BlindView:
    code = _code_mask(t)
    rows = np.flatnonzero(code)
    remap = -np.ones(len(t), dtype=np.int64)
    remap[rows] = np.arange(len(rows))
    e = remap[t.edges] if t.edges is not None and len(t.edges) else np.zeros((0, 2), dtype=np.int64)
    e = e[(e >= 0).all(1)] if len(e) else e.reshape(0, 2)
    e = e[e[:, 0] != e[:, 1]]
    e = np.unique(e, axis=0) if len(e) else e.reshape(0, 2)
    return BlindView(t.repo, rows, np.asarray(t.vectors[rows], dtype=np.float64), np.asarray(t.archetype[rows]),
                     np.asarray(t.loc[rows], dtype=np.float64), e.astype(np.int64))


def permute_view(v: BlindView, perm: np.ndarray) -> BlindView:
    """The same repository with its functions in another order (``perm[new] = old``)."""
    inv = np.empty_like(perm)
    inv[perm] = np.arange(len(perm))
    return BlindView(v.repo, v.rows[perm], v.vectors[perm], v.archetype[perm], v.loc[perm], inv[v.edges])


def rewired(v: BlindView, rng: np.random.Generator, swaps_per_edge: int = 10) -> BlindView:
    """Degree-preserving random rewiring of the call graph (directed double-edge swaps):
    each function keeps its measurements, in-degree and out-degree, but not its neighbours."""
    e = v.edges.copy()
    m = len(e)
    if m < 2:
        return v
    have = set(map(tuple, e.tolist()))
    for _ in range(swaps_per_edge * m):
        i, j = rng.integers(0, m, size=2)
        (a, b), (c, d) = e[i], e[j]
        if a == d or c == b or (a, d) in have or (c, b) in have:
            continue
        have.difference_update({(a, b), (c, d)})
        have.update({(a, d), (c, b)})
        e[i], e[j] = (a, d), (c, b)
    return BlindView(v.repo, v.rows, v.vectors, v.archetype, v.loc, e)


def _adjacency(v: BlindView):
    return coo_matrix((np.ones(len(v.edges)), (v.edges[:, 0], v.edges[:, 1])), shape=(v.n, v.n)).tocsr()


def graph_roles(v: BlindView) -> np.ndarray:
    """Per function, its role in the call graph: log in/out degree, log descendants and
    ancestors (reachability), depth below the entry points and height above the leaves,
    PageRank, and the mean in/out degree of its neighbours."""
    n = v.n
    if n == 0:
        return np.zeros((0, 9))
    a = _adjacency(v)
    a.data[:] = 1.0
    out_deg = np.asarray(a.sum(1)).ravel()
    in_deg = np.asarray(a.sum(0)).ravel()
    reach = shortest_path(a, directed=True, unweighted=True)
    finite = np.isfinite(reach)
    desc = finite.sum(1) - 1
    anc = finite.sum(0) - 1
    roots = np.flatnonzero(in_deg == 0)
    leaves = np.flatnonzero(out_deg == 0)
    depth = np.where(finite[roots].any(0), np.where(finite[roots], reach[roots], np.inf).min(0), 0) if len(roots) \
        else np.zeros(n)
    height = np.where(finite[:, leaves].any(1), np.where(finite[:, leaves], reach[:, leaves], np.inf).min(1), 0) \
        if len(leaves) else np.zeros(n)
    pr = _pagerank(a)
    u = ((a + a.T) > 0).astype(np.float64)
    nd = np.asarray(u.sum(1)).ravel()
    with np.errstate(invalid="ignore", divide="ignore"):
        nb_in = np.where(nd > 0, (u @ np.log1p(in_deg)) / nd, 0.0)
        nb_out = np.where(nd > 0, (u @ np.log1p(out_deg)) / nd, 0.0)
    return np.column_stack([np.log1p(in_deg), np.log1p(out_deg), np.log1p(desc), np.log1p(anc),
                            depth, height, np.log(pr * n), nb_in, nb_out])


def _pagerank(a, damping: float = 0.85, iters: int = 100) -> np.ndarray:
    n = a.shape[0]
    out = np.asarray(a.sum(1)).ravel()
    p = np.full(n, 1.0 / n)
    inv = np.where(out > 0, 1.0 / np.where(out > 0, out, 1), 0.0)
    at = a.T.tocsr()
    for _ in range(iters):
        dangling = p[out == 0].sum()
        p = (1 - damping) / n + damping * (at @ (p * inv) + dangling / n)
    return p / p.sum()


def _rank01(x: np.ndarray) -> np.ndarray:
    """Column-wise mid-rank in [0, 1] within this repository (ties share a rank)."""
    from scipy.stats import rankdata

    if len(x) < 2:
        return np.full_like(x, 0.5, dtype=np.float64)
    return (rankdata(x, axis=0) - 1) / (len(x) - 1)


def descriptors(v: BlindView, n_archetypes: int, use_graph: bool = True, use_measures: bool = True,
                weights: np.ndarray | None = None, geometry_only: bool = False) -> np.ndarray:
    """Per-function descriptor: the lens features and graph roles, each column replaced
    by its within-repository rank in [0, 1] (so a language's overall offsets cancel) and
    the lens features then scaled by the lens weights; plus the archetype, one-hot."""
    parts = []
    if use_measures:
        x = v.vectors[:, :N_GEOMETRY] if geometry_only else v.vectors
        w = np.ones(x.shape[1]) if weights is None else np.asarray(weights, dtype=np.float64)[:x.shape[1]]
        parts.append(_rank01(x) * w)
        if not geometry_only:
            parts.append(np.eye(n_archetypes)[v.archetype] * 0.5)
    if use_graph:
        parts.append(_rank01(graph_roles(v)) * 1.5)
    return np.column_stack(parts) if parts else np.zeros((v.n, 0))


# ------------------------------------------------------------------ placements


@dataclass(frozen=True)
class BlindParams:
    method: str = "fgw"  # "features" or "fgw"
    k: int = 15  # neighbours for "features"
    alpha: float = 0.5  # fgw: weight of the structure term (0 = descriptors only)
    epsilon: float = 0.01  # fgw: entropic regularization
    outer: int = 40  # fgw: mirror-descent steps
    hop_cap: int = 4  # hop distances beyond this (and between components) count as cap + 1
    smooth: float = 0.3  # share of each function's vote taken from its call-graph neighbours (label propagation)
    smooth_steps: int = 3
    decision: str = "argmax"  # "argmax" of the vote, or "lift": the vote over the subsystem's reference share
    use_graph: bool = True
    use_measures: bool = True
    geometry_only: bool = False  # lens features: only size, complexity, arity, vocabulary and decision density


def hop_matrix(v: BlindView, cap: int) -> np.ndarray:
    """Undirected hop distance between functions, capped and scaled to [0, 1]."""
    if v.n == 0:
        return np.zeros((0, 0))
    a = _adjacency(v)
    d = shortest_path(((a + a.T) > 0).astype(np.float64), directed=False, unweighted=True)
    d = np.minimum(np.where(np.isfinite(d), d, cap + 1), cap + 1)
    return (d / (cap + 1)).astype(np.float64)


def _sqdist(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.maximum((x * x).sum(1)[:, None] - 2 * x @ y.T + (y * y).sum(1)[None, :], 0.0)


def _sinkhorn(cost: np.ndarray, p: np.ndarray, q: np.ndarray, eps: float, iters: int = 300,
              tol: float = 1e-7) -> np.ndarray:
    """Entropic OT coupling. Costs are shifted to start at 0; a cost range above ~600 eps
    would underflow, so the kernel falls back to the log domain then."""
    c = cost - cost.min()
    if c.max() / eps > 600:
        k = -c / eps
        f, g = np.zeros(len(p)), np.zeros(len(q))
        for _ in range(iters):
            f = np.log(p) - logsumexp(k + g[None, :], axis=1)
            g = np.log(q) - logsumexp(k + f[:, None], axis=0)
        return np.exp(k + f[:, None] + g[None, :])
    k = np.exp(-c / eps)
    v = np.ones(len(q))
    for _ in range(iters):
        u = p / np.maximum(k @ v, 1e-300)
        v_new = q / np.maximum(k.T @ u, 1e-300)
        done = np.abs(v_new - v).max() <= tol * v.max()
        v = v_new
        if done:
            break
    return u[:, None] * k * v[None, :]


def fused_gw(feature_cost: np.ndarray, d1: np.ndarray, d2: np.ndarray, alpha: float, eps: float,
             outer: int = 40) -> np.ndarray:
    """Entropic fused Gromov-Wasserstein coupling (square loss) between uniform marginals:
    minimizes (1 - alpha) <M, T> + alpha * sum (d1_ik - d2_jl)^2 T_ij T_kl, by mirror
    descent (each step an entropic OT problem on the linearized cost)."""
    n, m = feature_cost.shape
    p, q = np.full(n, 1.0 / n), np.full(m, 1.0 / m)
    d1 = d1.astype(np.float32)
    const = ((d1.astype(np.float64) ** 2) @ p)[:, None] + ((d2 ** 2) @ q)[None, :]
    t = np.outer(p, q)
    for _ in range(outer):
        tens = const - 2 * (d1 @ (t @ d2.T).astype(np.float32)).astype(np.float64)
        t = _sinkhorn((1 - alpha) * feature_cost + alpha * tens, p, q, eps)
    return t


def _propagate(v: BlindView, votes: np.ndarray, beta: float, steps: int) -> np.ndarray:
    """Label propagation: mix each function's normalized vote with its call-graph
    neighbours' (callers and callees alike), ``steps`` times."""
    a = _adjacency(v)
    u = ((a + a.T) > 0).astype(np.float64).tocsr()
    deg = np.asarray(u.sum(1)).ravel()
    tot = votes.sum(1, keepdims=True)
    x0 = votes / np.where(tot > 0, tot, 1.0)
    x = x0
    for _ in range(steps):
        nb = (u @ x) / np.where(deg > 0, deg, 1.0)[:, None]
        x = np.where(deg[:, None] > 0, (1 - beta) * x0 + beta * nb, x0)
    return x


@dataclass
class Placement:
    repo: str
    labels: np.ndarray  # per row of the repository's function table, -1 off the map
    view_labels: np.ndarray  # per blind-view function
    confidence: np.ndarray  # per blind-view function: share of its vote/mass in the winning subsystem
    params: BlindParams = field(default_factory=BlindParams)


def place(port: BlindView, ref: BlindView, ref_view_labels: np.ndarray, s: int, n_archetypes: int,
          params: BlindParams | None = None, n_rows: int | None = None,
          feature_weights: np.ndarray | None = None) -> Placement:
    """Blind subsystem per port function, from the reference's labelled functions."""
    p = params or BlindParams()
    xp = descriptors(port, n_archetypes, p.use_graph, p.use_measures, feature_weights, p.geometry_only)
    xr = descriptors(ref, n_archetypes, p.use_graph, p.use_measures, feature_weights, p.geometry_only)
    onehot = np.eye(s)[ref_view_labels]
    if port.n == 0:
        votes = np.zeros((0, s))
    elif p.method == "features":
        d = _sqdist(xp, xr)
        k = min(p.k, ref.n)
        nn = np.argpartition(d, k - 1, axis=1)[:, :k]
        votes = onehot[nn].sum(1)
    elif p.method == "fgw":
        m = _sqdist(xp, xr)
        m = m / (m.max() or 1.0)
        t = fused_gw(m, hop_matrix(port, p.hop_cap), hop_matrix(ref, p.hop_cap), p.alpha, p.epsilon, p.outer)
        votes = t @ onehot
    else:
        raise ValueError(f"unknown blind method {p.method!r}")
    if p.smooth > 0 and len(port.edges):
        votes = _propagate(port, votes, p.smooth, p.smooth_steps)
    tot = votes.sum(1, keepdims=True)
    share = votes / np.where(tot > 0, tot, 1.0)
    if p.decision == "lift":
        # Each subsystem's vote relative to its share of the reference, so a diffuse
        # vote does not default to the largest subsystem.
        prior = np.bincount(ref_view_labels, minlength=s) / max(len(ref_view_labels), 1)
        score = share / np.where(prior > 0, prior, np.inf)
    elif p.decision == "argmax":
        score = share
    else:
        raise ValueError(f"unknown decision rule {p.decision!r}")
    vl = score.argmax(1) if port.n else np.zeros(0, dtype=np.int64)
    labels = np.full(n_rows if n_rows is not None else int(port.rows.max(initial=-1)) + 1, -1, dtype=np.int64)
    labels[port.rows] = vl
    return Placement(port.repo, labels, vl, share.max(1) if port.n else np.zeros(0), p)


# ------------------------------------------------------------------ scoring


def call_matrix(labels: np.ndarray, edges: np.ndarray, s: int) -> np.ndarray:
    m = np.zeros((s, s))
    if len(edges):
        a, b = labels[edges[:, 0]], labels[edges[:, 1]]
        ok = (a >= 0) & (b >= 0)
        np.add.at(m, (a[ok], b[ok]), 1)
    return m


def wiring(calls: np.ndarray, ref_calls: np.ndarray) -> tuple[float, float]:
    """(full, off-diagonal) cosine of call-share matrices; off-diagonal drops within-subsystem calls."""
    off = ~np.eye(len(calls), dtype=bool)
    return _cosine(calls, ref_calls), _cosine(np.where(off, calls, 0), np.where(off, ref_calls, 0))


def accuracy(pred: np.ndarray, key: np.ndarray) -> float:
    return float((pred == key).mean()) if len(key) else float("nan")


def balanced_accuracy(pred: np.ndarray, key: np.ndarray, min_support: int = 5) -> float:
    """Mean per-subsystem recall over the subsystems with at least ``min_support`` key
    functions, so a placement cannot score by sending everything to the largest one."""
    ks = [k for k, c in zip(*np.unique(key, return_counts=True), strict=True) if c >= min_support]
    return float(np.mean([(pred[key == k] == k).mean() for k in ks])) if ks else float("nan")


def null_balanced_accuracy(pred: np.ndarray, key: np.ndarray, rng: np.random.Generator, draws: int = 2000,
                           min_support: int = 5) -> np.ndarray:
    return np.array([balanced_accuracy(rng.permutation(pred), key, min_support) for _ in range(draws)]) \
        if len(key) else np.zeros(0)


def null_accuracy(pred: np.ndarray, key: np.ndarray, rng: np.random.Generator, draws: int = 2000) -> np.ndarray:
    """Accuracy of the same predicted labels shuffled across the scored functions."""
    return np.array([(rng.permutation(pred) == key).mean() for _ in range(draws)]) if len(key) else np.zeros(0)


def null_wiring(view_labels: np.ndarray, edges: np.ndarray, ref_calls: np.ndarray, rng: np.random.Generator,
                draws: int = 500) -> dict[str, np.ndarray]:
    """Two nulls for blind wiring: ``shuffle`` (labels shuffled across functions, sizes kept)
    and ``rename`` (the blind partition kept, its subsystem names permuted)."""
    s = len(ref_calls)
    out = {"shuffle": [], "rename": []}
    for _ in range(draws):
        out["shuffle"].append(wiring(call_matrix(rng.permutation(view_labels), edges, s), ref_calls))
        out["rename"].append(wiring(call_matrix(rng.permutation(s)[view_labels], edges, s), ref_calls))
    return {k: np.array(v) for k, v in out.items()}


def per_subsystem(pred: np.ndarray, key: np.ndarray, s: int) -> dict[int, dict[str, float]]:
    out = {}
    for k in range(s):
        tp = int(((pred == k) & (key == k)).sum())
        nk, npred = int((key == k).sum()), int((pred == k).sum())
        if nk or npred:
            out[k] = {"key": nk, "placed": npred, "recall": tp / nk if nk else float("nan"),
                      "precision": tp / npred if npred else float("nan")}
    return out


# ------------------------------------------------------------------ the experiment


@dataclass
class ReferenceView:
    """The reference repository as the blind placement sees it."""

    view: BlindView
    labels: np.ndarray  # per view function
    calls: np.ndarray  # (S, S)


def reference_context(ref_lens: FunctionTable, tax: Taxonomy) -> tuple[np.ndarray, ReferenceView]:
    """Path-rule labels of the reference (the taxonomy's definition of its subsystems):
    (labels per table row, the reference's blind view)."""
    labels = np.array([tax.classify(str(x), ref_lens.repo) for x in ref_lens.path], dtype=np.int64)
    labels[~_code_mask(ref_lens)] = -1
    v = blind_view(ref_lens)
    vl = labels[v.rows]
    return labels, ReferenceView(v, vl, call_matrix(vl, v.edges, len(tax.subsystems)))


def _summary(x: np.ndarray, observed: float) -> dict:
    x = np.asarray(x, dtype=float)
    return {"mean": float(x.mean()), "sd": float(x.std()), "p95": float(np.quantile(x, 0.95)),
            "p_value": float(((x >= observed).sum() + 1) / (len(x) + 1))}


def evaluate_port(port_structure: FunctionTable, port_lens: FunctionTable, ref_structure: FunctionTable,
                  ref_labels: np.ndarray, ref: ReferenceView, tax: Taxonomy, params: BlindParams,
                  feature_weights: np.ndarray | None, n_archetypes: int, twin: TwinResult | None = None,
                  draws: int = 2000, rewire_draws: int = 3, ablations: dict[str, BlindParams] | None = None,
                  seed: int = 0) -> dict:
    """Blind placement of one port, scored against the name/path answer key, with nulls.

    ``port_structure`` (structure lens) is used only for the answer key, as ``sfs subway``
    builds it; ``port_lens`` (any lens, same functions) only for the blind placement."""
    if len(port_structure) != len(port_lens) or not (port_structure.name == port_lens.name).all():
        raise ValueError("the two lens tables of a port must list the same functions in the same order")
    rng = np.random.default_rng(seed)
    s = len(tax.subsystems)
    key, src = answer_key(port_structure, tax, ref_structure, ref_labels, twin)
    v = blind_view(port_lens)
    kv, sv = key[v.rows], src[v.rows].astype(str)
    scored = np.isin(sv, ["name", "path"])

    def run(p: BlindParams, view: BlindView = v) -> np.ndarray:
        return place(view, ref.view, ref.labels, s, n_archetypes, p, len(port_lens), feature_weights).view_labels

    main_placement = place(v, ref.view, ref.labels, s, n_archetypes, params, len(port_lens), feature_weights)
    pred, conf = main_placement.view_labels, main_placement.confidence
    confident = scored & (conf >= np.quantile(conf[scored], 0.75)) if scored.any() else scored
    acc = accuracy(pred[scored], kv[scored])
    na = null_accuracy(pred[scored], kv[scored], rng, draws)
    bal = balanced_accuracy(pred[scored], kv[scored])
    nb = null_balanced_accuracy(pred[scored], kv[scored], rng, max(draws // 4, 100))
    w_full, w_off = wiring(call_matrix(pred, v.edges, s), ref.calls)
    k_full, k_off = wiring(call_matrix(kv, v.edges, s), ref.calls)
    nw = null_wiring(pred, v.edges, ref.calls, rng, max(draws // 4, 100))
    srcs, counts = np.unique(sv, return_counts=True)
    out = {
        "repo": v.repo, "functions": v.n, "edges": len(v.edges),
        "key_sources": {str(k): int(c) for k, c in zip(srcs, counts, strict=True)},
        "scored": int(scored.sum()),
        "accuracy": acc, "accuracy_null": _summary(na, acc),
        "kappa": (acc - float(na.mean())) / (1 - float(na.mean())) if len(na) and na.mean() < 1 else float("nan"),
        "balanced_accuracy": bal, "balanced_accuracy_null": _summary(nb, bal) if len(nb) else None,
        "accuracy_top_quartile_confidence": accuracy(pred[confident], kv[confident]),
        "accuracy_by_source": {k: accuracy(pred[sv == k], kv[sv == k]) for k in ("twin", "name", "path")
                               if (sv == k).any()},
        "per_subsystem": {tax.subsystems[k]: d for k, d in per_subsystem(pred[scored], kv[scored], s).items()},
        "wiring_key": {"full": k_full, "off": k_off},
        "wiring_blind": {"full": w_full, "off": w_off},
        "wiring_null_shuffle": {"full": _summary(nw["shuffle"][:, 0], w_full),
                                "off": _summary(nw["shuffle"][:, 1], w_off)},
        "wiring_null_rename": {"full": _summary(nw["rename"][:, 0], w_full),
                               "off": _summary(nw["rename"][:, 1], w_off)},
        "blind_sizes": {tax.subsystems[k]: int(c) for k, c in enumerate(np.bincount(pred, minlength=s)) if c},
    }
    # The method on a degree-preserving rewiring of the port's graph: what it manufactures
    # when the port's calls carry no information about the reference's architecture.
    rw = []
    for _ in range(rewire_draws):
        g = rewired(v, rng)
        pr = run(params, g)
        f, o = wiring(call_matrix(pr, g.edges, s), ref.calls)
        rw.append((accuracy(pr[scored], kv[scored]), f, o, balanced_accuracy(pr[scored], kv[scored])))
    if rw:
        a = np.array(rw)
        out["rewired"] = {"accuracy": float(a[:, 0].mean()), "balanced_accuracy": float(np.nanmean(a[:, 3])),
                          "full": float(a[:, 1].mean()),
                          "off": float(a[:, 2].mean()), "draws": len(a)}
    for name, p in (ablations or {}).items():
        pa = run(p)
        f, o = wiring(call_matrix(pa, v.edges, s), ref.calls)
        out.setdefault("ablations", {})[name] = {"accuracy": accuracy(pa[scored], kv[scored]),
                                                 "balanced_accuracy": balanced_accuracy(pa[scored], kv[scored]),
                                                 "full": f, "off": o}
    return out


def ablations(p: BlindParams) -> dict[str, BlindParams]:
    """Variants of ``p`` that each remove one source of information."""
    from dataclasses import replace

    return {
        "no_structure_term": replace(p, alpha=0.0),  # OT on descriptors only (graph roles still in them)
        "graph_only": replace(p, use_measures=False),  # no per-function measurements at all
        "measures_only": replace(p, alpha=0.0, use_graph=False),  # no call graph at all
        "geometry_only": replace(p, geometry_only=True),  # no signal densities or archetype
        "knn": replace(p, method="features"),  # nearest reference functions, no coupling
    }


def _tables(db, lenses: tuple[str, ...], min_loc: int) -> dict[str, FunctionTable]:
    from .fingerprint import build
    from .reference import load_reference
    from .scan_io import load_scan

    out = {}
    for lens in lenses:
        ref = load_reference(lens)
        out[lens] = build(load_scan(db, ref.signal_columns), ref, min_loc=min_loc).functions
    return out


def _job(args: tuple) -> dict:
    db, ref_db, tax_path, lens, min_loc, params, draws, rewire_draws, with_ablations, lens_weights = args
    from .reference import load_reference
    from .twins import TwinParams, find_twins

    tax = Taxonomy.load(tax_path) if tax_path else None
    rt = _tables(ref_db, ("structure", lens), min_loc)
    pt = _tables(db, ("structure", lens), min_loc)
    tax = tax or Taxonomy.from_directories(rt["structure"])
    ref_labels, ref = reference_context(rt[lens], tax)
    lref = load_reference(lens)
    twin = find_twins(pt["structure"], rt["structure"], TwinParams())
    return evaluate_port(pt["structure"], pt[lens], rt["structure"], ref_labels, ref, tax, params,
                         lref.weights if lens_weights else None,
                         len(lref.archetype_names), twin, draws, rewire_draws,
                         ablations(params) if with_ablations else None)


def _finite(x):
    """JSON-safe copy: NaN and infinities become null."""
    if isinstance(x, dict):
        return {k: _finite(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_finite(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return float(x) if np.isfinite(x) else None
    if isinstance(x, np.integer):
        return int(x)
    return x


def main(argv: list[str] | None = None) -> int:
    """``python -m structural_fingerprint.blind SCANS --reference linuxdoom --taxonomy T --ports a,b -o out.json``"""
    import argparse
    import json
    from concurrent.futures import ProcessPoolExecutor
    from pathlib import Path

    from .scan_io import resolve_scans

    ap = argparse.ArgumentParser(prog="python -m structural_fingerprint.blind", description=__doc__.split("\n")[0])
    ap.add_argument("scans", help="directory of scan directories")
    ap.add_argument("--reference", required=True)
    ap.add_argument("--ports", required=True, help="comma-separated scan names")
    ap.add_argument("--taxonomy")
    ap.add_argument("--lens", default="portable", help="lens of the blind descriptors (default portable)")
    ap.add_argument("--min-loc", type=int, default=3)
    ap.add_argument("--method", default="fgw", choices=("fgw", "features"))
    ap.add_argument("--alpha", type=float, default=BlindParams.alpha)
    ap.add_argument("--epsilon", type=float, default=BlindParams.epsilon)
    ap.add_argument("--smooth", type=float, default=BlindParams.smooth)
    ap.add_argument("--decision", default=BlindParams.decision, choices=("argmax", "lift"))
    ap.add_argument("--draws", type=int, default=2000)
    ap.add_argument("--rewire-draws", type=int, default=3)
    ap.add_argument("--ablations", action="store_true", help="also run the ablations (see ablations())")
    ap.add_argument("--lens-weights", action="store_true",
                    help="scale the ranked lens features by the lens weights (off by default: tuning on "
                         "chocolate-doom placed slightly better without)")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args(argv)
    root = Path(a.scans)
    by = {}
    for name in [a.reference, *a.ports.split(",")]:
        by[name] = resolve_scans([root / name])[0]
    params = BlindParams(method=a.method, alpha=a.alpha, epsilon=a.epsilon, smooth=a.smooth, decision=a.decision)
    jobs = [(by[p], by[a.reference], a.taxonomy, a.lens, a.min_loc, params, a.draws, a.rewire_draws, a.ablations,
             a.lens_weights)
            for p in a.ports.split(",")]
    with ProcessPoolExecutor(max(1, a.workers)) as ex:
        results = list(ex.map(_job, jobs))
    doc = {"reference": a.reference, "lens": a.lens, "params": params.__dict__, "lens_weights": a.lens_weights,
           "ports": results}
    Path(a.out).write_text(json.dumps(_finite(doc), indent=1, allow_nan=False) + "\n")
    for r in results:
        print(f"{r['repo']:24s} acc {r['accuracy']:.3f} (null {r['accuracy_null']['mean']:.3f}) "
              f"wiring full {r['wiring_blind']['full']:.3f} off {r['wiring_blind']['off']:.3f} "
              f"(key {r['wiring_key']['full']:.3f}/{r['wiring_key']['off']:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
