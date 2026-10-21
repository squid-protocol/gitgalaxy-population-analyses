"""Function-level structural twins between two repositories.

A *twin* of a query function is a function in the target repository that the engine
measured almost identically: same size, decisions, arity and signal mix. Twins are
found by name-blind nearest-neighbour search in the lens space and accepted only if

1. **reciprocal**: each is the other's nearest neighbour (reciprocal best hits, the
   rule comparative genomics uses to call orthologs), so a generic shape that many
   functions resemble cannot collect twins;
2. **distinctive**: the nearest neighbour is clearly closer than the second nearest
   (``d1 <= ratio * d2``, Lowe's ratio test); and
3. **closer than chance**: the distance is below a threshold chosen by target-decoy
   competition. The same search is run against a *decoy* target built by shuffling
   each feature among the target functions *of the same engine archetype*: decoys are
   realistic functions of each kind, but no real function survives. Decoy hits at a
   distance estimate how many target hits at that distance are chance, and the
   threshold is the largest distance whose estimated false-twin rate (FDR) stays
   within ``fdr``.

A function whose exact raw measurement tuple occurs exactly once in each repository is
an *exact structural clone*. Clones of at least twice the minimum size are accepted
directly; smaller ones must pass the calibrated threshold like any other match.

Names are never used for matching. They are used afterwards as an independent check:
when both repositories name their functions alike, the share of twins whose names
agree estimates the precision of the name-blind search.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np

from .fingerprint import FunctionTable


@dataclass(frozen=True)
class TwinParams:
    min_loc: int = 6
    ratio: float = 0.8
    fdr: float = 0.01
    block: int = 2048
    seed: int = 0


@dataclass
class TwinResult:
    query: str
    target: str
    params: TwinParams
    eligible: int
    threshold: float
    est_fdr: float
    q_index: np.ndarray  # indices into the query table of accepted twins
    t_index: np.ndarray  # their twins in the target table
    distance: np.ndarray
    exact: np.ndarray  # bool
    decoy_hits: int
    stats: dict = field(default_factory=dict)

    @property
    def accepted(self) -> int:
        return len(self.q_index)


def _norm_name(s: str) -> str:
    return s.strip().lower()


def _top2(q: np.ndarray, t: np.ndarray, block: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Nearest and second-nearest target per query row: (d1, d2, index of nearest)."""
    nq = len(q)
    d1 = np.full(nq, np.inf)
    d2 = np.full(nq, np.inf)
    i1 = np.full(nq, -1, dtype=np.int64)
    if nq == 0 or len(t) == 0:
        return d1, d2, i1
    t = t.astype(np.float32, copy=False)
    tn = (t * t).sum(1)
    for s in range(0, nq, block):
        qb = q[s:s + block].astype(np.float32, copy=False)
        dd = (qb * qb).sum(1)[:, None] + tn[None, :] - 2.0 * (qb @ t.T)
        np.maximum(dd, 0.0, out=dd)
        if dd.shape[1] == 1:
            d1[s:s + len(qb)] = dd[:, 0]
            i1[s:s + len(qb)] = 0
            continue
        part = np.argpartition(dd, 1, axis=1)[:, :2]
        rows = np.arange(len(qb))[:, None]
        pv = dd[rows, part]
        order = np.argsort(pv, axis=1)
        part = np.take_along_axis(part, order, 1)
        pv = np.take_along_axis(pv, order, 1)
        d1[s:s + len(qb)] = pv[:, 0]
        d2[s:s + len(qb)] = pv[:, 1]
        i1[s:s + len(qb)] = part[:, 0]
    return np.sqrt(d1), np.sqrt(d2), i1


def _decoy(t: np.ndarray, strata: np.ndarray, seed_text: str) -> np.ndarray:
    """Shuffle each feature independently within each stratum (engine archetype)."""
    seed = int.from_bytes(hashlib.sha256(seed_text.encode()).digest()[:8], "little")
    rng = np.random.default_rng(seed)
    out = t.copy()
    for s in np.unique(strata):
        rows = np.flatnonzero(strata == s)
        if len(rows) < 2:
            continue
        for j in range(t.shape[1]):
            out[rows, j] = t[rows[rng.permutation(len(rows))], j]
    return out


def _distinct(d1: np.ndarray, d2: np.ndarray, ratio: float) -> np.ndarray:
    return np.where(d1 == 0, d2 > 0, d1 <= ratio * d2)


def _fdr_threshold(target_d: np.ndarray, decoy_d: np.ndarray, fdr: float) -> tuple[float, float]:
    """Largest distance t with (#decoy <= t + 1) / (#target <= t) <= fdr; returns (t, est_fdr).

    The +1 is the standard finite-sample correction for target-decoy competition: with
    no decoy hit yet, the error rate is not zero but unknown, so a pair must produce at
    least 1/fdr twins before any of them is certified at that rate. Small repositories
    therefore report few or no twins rather than chance ones."""
    if len(target_d) == 0:
        return 0.0, 0.0
    ts = np.sort(target_d)
    ds = np.sort(decoy_d)
    n_t = np.arange(1, len(ts) + 1)
    n_d = np.searchsorted(ds, ts, side="right")
    est = (n_d + 1) / n_t
    # q-value style: the FDR at a threshold is the minimum over all looser thresholds
    q = np.minimum.accumulate(est[::-1])[::-1]
    ok = np.flatnonzero(q <= fdr)
    if len(ok) == 0:
        return 0.0, float(q[0]) if len(q) else 0.0
    k = ok[-1]
    return float(ts[k]), float(est[k])


@dataclass
class TwinSearch:
    """Everything the twin search computes before a distance threshold is applied, so a
    threshold can be chosen over several searches at once (``pooled_threshold``)."""

    query: FunctionTable
    target: FunctionTable
    params: TwinParams
    qm: np.ndarray  # eligible query rows
    tm: np.ndarray  # eligible target rows
    d1: np.ndarray  # nearest-target distance per eligible query row
    i1: np.ndarray  # its target position in tm
    t_pass: np.ndarray  # reciprocal and distinctive
    e1: np.ndarray  # nearest-decoy distance
    e_pass: np.ndarray
    exact: np.ndarray  # exact-clone rows that bypass the threshold
    exact_t: np.ndarray  # their target positions in tm


def search(query: FunctionTable, target: FunctionTable, params: TwinParams | None = None) -> TwinSearch:
    p = params or TwinParams()
    qm = np.flatnonzero(query.loc >= p.min_loc)
    tm = np.flatnonzero(target.loc >= p.min_loc)
    scale = np.sqrt(query.vectors.shape[1]) if query.vectors.size else 1.0
    qv, tv = query.vectors[qm], target.vectors[tm]

    d1, d2, i1 = _top2(qv, tv, p.block)
    d1, d2 = d1 / scale, d2 / scale
    _, _, back = _top2(tv, qv, p.block)  # each target function's nearest query function
    reciprocal = (i1 >= 0) & (back[np.maximum(i1, 0)] == np.arange(len(qm)))
    decoy = _decoy(tv, target.archetype[tm], f"{query.repo}\0{target.repo}\0{p.seed}")
    e1, e2, ei = _top2(qv, decoy, p.block)
    e1, e2 = e1 / scale, e2 / scale
    _, _, eback = _top2(decoy, qv, p.block)
    e_recip = (ei >= 0) & (eback[np.maximum(ei, 0)] == np.arange(len(qm)))

    t_pass = reciprocal & _distinct(d1, d2, p.ratio) & np.isfinite(d1)
    e_pass = e_recip & _distinct(e1, e2, p.ratio) & np.isfinite(e1)

    # Exact measurement clones: accepted when the exact tuple occurs once on each side.
    t_keys = target.key[tm]
    q_keys = query.key[qm]
    tu, tc = np.unique(t_keys, return_counts=True)
    qu, qc = np.unique(q_keys, return_counts=True)
    unique_keys = np.intersect1d(tu[tc == 1], qu[qc == 1])
    first_pos = {int(k): int(i) for i, k in enumerate(t_keys)}
    # Small exact matches can collide by chance in large repositories, so only clones of
    # at least twice the minimum size bypass the calibrated threshold.
    exact = np.isin(q_keys, unique_keys) & (query.loc[qm] >= 2 * p.min_loc)
    exact_t = np.array([first_pos[int(k)] for k in q_keys[exact]], dtype=np.int64)
    return TwinSearch(query, target, p, qm, tm, d1, i1, t_pass, e1, e_pass, exact, exact_t)


def pooled_threshold(searches: list[TwinSearch], fdr: float) -> tuple[float, float]:
    """One target-decoy threshold over the candidates of several searches. A series of
    related comparisons (one repository's snapshots against a reference) calibrated
    together has the power that a single small pair lacks, and is measured with one
    yardstick throughout."""
    if not searches:
        return 0.0, 0.0
    t = np.concatenate([s.d1[s.t_pass] for s in searches])
    e = np.concatenate([s.e1[s.e_pass] for s in searches])
    return _fdr_threshold(t, e, fdr)


def accept(s: TwinSearch, threshold: float | None = None) -> TwinResult:
    """Apply a distance threshold (its own target-decoy threshold when ``None``)."""
    p = s.params
    if threshold is None:
        thr, est = _fdr_threshold(s.d1[s.t_pass], s.e1[s.e_pass], p.fdr)
    else:
        thr, est = threshold, float("nan")
    ok = s.t_pass & (s.d1 <= thr)
    tgt_local = s.i1.copy()
    tgt_local[np.flatnonzero(s.exact)] = s.exact_t
    all_idx = np.union1d(np.flatnonzero(ok), np.flatnonzero(s.exact))

    q_index = s.qm[all_idx]
    t_index = s.tm[tgt_local[all_idx]]
    is_exact = s.exact[all_idx]
    dist = np.where(is_exact, 0.0, s.d1[all_idx])

    stats = _stats(s.query, s.target, s.qm, s.tm, q_index, t_index, is_exact)
    stats.update({
        "candidates_distinctive": int(s.t_pass.sum()),
        "decoy_distinctive": int(s.e_pass.sum()),
        "decoy_hits_at_threshold": int((s.e_pass & (s.e1 <= thr)).sum()),
    })
    return TwinResult(query=s.query.repo, target=s.target.repo, params=p, eligible=len(s.qm), threshold=thr,
                      est_fdr=est, q_index=q_index, t_index=t_index, distance=dist, exact=is_exact,
                      decoy_hits=stats["decoy_hits_at_threshold"], stats=stats)


def find_twins(query: FunctionTable, target: FunctionTable, params: TwinParams | None = None,
               threshold: float | None = None) -> TwinResult:
    return accept(search(query, target, params), threshold)


def _stats(query: FunctionTable, target: FunctionTable, qm: np.ndarray, tm: np.ndarray,
           q_index: np.ndarray, t_index: np.ndarray, is_exact: np.ndarray) -> dict:
    eligible_loc = float(query.loc[qm].sum())
    twin_loc = float(query.loc[q_index].sum())
    t_names = {_norm_name(n) for n in target.name[tm]}
    q_names = np.array([_norm_name(n) for n in query.name[q_index]], dtype=object)
    same = np.array([_norm_name(a) == _norm_name(b) for a, b in zip(query.name[q_index], target.name[t_index],
                                                                    strict=True)], dtype=bool)
    named_in_target = np.array([n in t_names for n in q_names], dtype=bool)
    q_all_names = np.array([_norm_name(n) for n in query.name[qm]], dtype=object)
    shared = np.array([n in t_names for n in q_all_names], dtype=bool)
    return {
        "eligible": len(qm),
        "eligible_loc": eligible_loc,
        "twins": len(q_index),
        "exact_clones": int(is_exact.sum()),
        "survival": float(len(q_index) / len(qm)) if len(qm) else 0.0,
        "survival_loc": twin_loc / eligible_loc if eligible_loc else 0.0,
        # Independent check on the name-blind search (names were not used to match):
        "name_agreement": float(same[named_in_target].mean()) if named_in_target.any() else None,
        "twins_with_name_in_target": int(named_in_target.sum()),
        "renamed_twins": int((~same & ~named_in_target).sum()),
        # Of the query functions whose name also exists in the target, how many were
        # found as a same-name twin: a lower bound on recall for preserved functions.
        "shared_names": int(shared.sum()),
        "shared_name_recall": float(same.sum() / shared.sum()) if shared.sum() else None,
    }
