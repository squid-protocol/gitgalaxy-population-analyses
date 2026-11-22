"""Two-layer structural comparison: Call-Graph Seed-and-Extend + 32-Keyword-Family Lattice."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

import numpy as np
from scipy.spatial.distance import cdist

from . import blind as BL
from . import compare as C
from . import features as F
from .fingerprint import build
from .reference import Reference, load_reference
from .scan_io import ScanData


@dataclass(frozen=True)
class TwoLayerResult:
    """Output of Layer 1 (Seed-and-Extend) and Layer 2 (Keyword & Archetype Lattice)."""

    repo_a: str
    repo_b: str
    n_a: int
    n_b: int
    fgw_cost: float
    t1_n: int
    se_n: int
    se_coverage: float
    kw_jsd: float
    arch_jsd: float
    matched_kw_cos: float
    matched_kw_dom_agree: float
    matched_arch_agree: float
    post_delta_res: float

    def to_dict(self) -> dict:
        return asdict(self)


def keyword_lattice_profile(
    signals: np.ndarray,
    rows: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute per-function unit-norm keyword-family vectors, dominant indices, and repo distribution."""
    sigs = np.asarray(signals, dtype=np.float64)
    if rows is not None:
        sigs = sigs[rows]
    if len(sigs) == 0:
        n_sig = sigs.shape[1] if sigs.ndim == 2 else 0
        return np.zeros((0, n_sig)), np.zeros(0, dtype=np.int64), np.zeros(n_sig)
    sums = np.maximum(sigs.sum(axis=1, keepdims=True), 1.0)
    kw_comp = sigs / sums
    kw_norm = kw_comp / np.maximum(np.linalg.norm(kw_comp, axis=1, keepdims=True), 1e-9)
    kw_dom = np.argmax(sigs, axis=1)
    repo_dist = kw_comp.mean(axis=0)
    tot = float(repo_dist.sum())
    if tot > 0:
        repo_dist = repo_dist / tot
    return kw_norm, kw_dom, repo_dist


def keyword_lattice_distance(dist_a: np.ndarray, dist_b: np.ndarray) -> float:
    """Jensen-Shannon distance (0..1, base 2) between two 32-keyword-family distributions."""
    return C._js_distance(np.asarray(dist_a, dtype=np.float64), np.asarray(dist_b, dtype=np.float64))


def _prep_repo(sc: ScanData, ref: Reference, bp: BL.BlindParams, min_loc: int) -> dict:
    ft = build(sc, ref, min_loc=min_loc, keyword_mode="composition").functions
    bv = BL.blind_view(ft)
    n_arch = len(ref.archetype_names)
    xd = BL.descriptors(bv, n_arch, bp.use_graph, bp.use_measures, None, bp.geometry_only)
    hm = BL.hop_matrix(bv, bp.hop_cap)
    comp_all = F.raw_features(
        ref, sc.loc, sc.complexity, sc.args, sc.keyword_density, sc.signals,
        keyword_mode="composition",
    )
    comp = comp_all[bv.rows]
    cnorm = comp / np.maximum(np.linalg.norm(comp, axis=1, keepdims=True), 1e-9)
    nbrs: dict[int, set[int]] = defaultdict(set)
    for u, v in bv.edges.tolist():
        if u != v:
            nbrs[u].add(v)
            nbrs[v].add(u)
    arch = np.asarray(ft.archetype[bv.rows], dtype=np.int64)
    arch_cnt = np.bincount(arch, minlength=n_arch).astype(np.float64)
    arch_dist = arch_cnt / max(1.0, float(arch_cnt.sum()))
    kw_norm, kw_dom, kw_dist = keyword_lattice_profile(sc.signals, bv.rows)
    return {
        "name": sc.name,
        "n": len(bv.rows),
        "xd": xd,
        "hm": hm,
        "comp": comp,
        "cnorm": cnorm,
        "nbrs": nbrs,
        "arch": arch,
        "arch_dist": arch_dist,
        "kw_norm": kw_norm,
        "kw_dom": kw_dom,
        "kw_dist": kw_dist,
    }


def seed_and_extend_with_lattice(
    sc_a: ScanData,
    sc_b: ScanData,
    ref: Reference | None = None,
    *,
    min_loc: int = 3,
    alpha: float = 0.5,
    eps: float = 0.05,
    outer: int = 40,
    hops: int = 3,
    seed_frac: float = 0.15,
) -> TwoLayerResult:
    """Run Layer 1 (FGW Seed-and-Extend) followed by Layer 2 (32-keyword & 14-archetype lattice)."""
    if ref is None:
        ref = load_reference("portable")
    bp = BL.BlindParams()
    A = _prep_repo(sc_a, ref, bp, min_loc)
    B = _prep_repo(sc_b, ref, bp, min_loc)

    kw_jsd = keyword_lattice_distance(A["kw_dist"], B["kw_dist"])
    arch_jsd = C._js_distance(A["arch_dist"], B["arch_dist"])

    if A["n"] == 0 or B["n"] == 0:
        return TwoLayerResult(
            repo_a=A["name"], repo_b=B["name"], n_a=A["n"], n_b=B["n"],
            fgw_cost=1.0, t1_n=0, se_n=0, se_coverage=0.0,
            kw_jsd=kw_jsd, arch_jsd=arch_jsd,
            matched_kw_cos=0.0, matched_kw_dom_agree=0.0,
            matched_arch_agree=0.0, post_delta_res=0.0,
        )

    cost = cdist(A["xd"], B["xd"], metric="euclidean")
    cost /= float(np.median(cost)) + 1e-12
    T = BL.fused_gw(cost, A["hm"], B["hm"], alpha=alpha, eps=eps, outer=outer)
    fgw_cost = float(np.sum(T * cost))

    best_r = np.argmax(T, axis=1)
    best_q = np.argmax(T, axis=0)
    seeds = [(qi, int(best_r[qi]), float(T[qi, best_r[qi]]))
             for qi in range(A["n"]) if best_q[best_r[qi]] == qi]
    seeds.sort(key=lambda x: -x[2])

    if not seeds:
        return TwoLayerResult(
            repo_a=A["name"], repo_b=B["name"], n_a=A["n"], n_b=B["n"],
            fgw_cost=fgw_cost, t1_n=0, se_n=0, se_coverage=0.0,
            kw_jsd=kw_jsd, arch_jsd=arch_jsd,
            matched_kw_cos=0.0, matched_kw_dom_agree=0.0,
            matched_arch_agree=0.0, post_delta_res=0.0,
        )

    k_seed = max(3, min(len(seeds), int(round(seed_frac * len(seeds)))))
    top_seeds = seeds[:k_seed]
    delta = np.median(
        A["comp"][[s[0] for s in top_seeds]] - B["comp"][[s[1] for s in top_seeds]],
        axis=0,
    )
    matched = {qi: ri for qi, ri, _ in top_seeds}
    used_b = {ri for _, ri, _ in top_seeds}
    b_shifted = B["comp"] + delta
    b_snorm = b_shifted / np.maximum(np.linalg.norm(b_shifted, axis=1, keepdims=True), 1e-9)

    for _ in range(hops):
        cand = []
        for qi in range(A["n"]):
            if qi in matched:
                continue
            qn = [u for u in A["nbrs"][qi] if u in matched]
            if not qn:
                continue
            rc_cnt: dict[int, int] = defaultdict(int)
            for u in qn:
                for rc in B["nbrs"][matched[u]]:
                    if rc not in used_b:
                        rc_cnt[rc] += 1
            for rc, cnt in rc_cnt.items():
                cand.append((float(np.dot(A["cnorm"][qi], b_snorm[rc])) + 0.1 * cnt, qi, rc))
        cand.sort(key=lambda x: -x[0])
        for _, qi, rc in cand:
            if qi in matched or rc in used_b:
                continue
            matched[qi] = rc
            used_b.add(rc)

    pairs = list(matched.items())
    matched_arch_agree = sum(1 for qi, ri in pairs if A["arch"][qi] == B["arch"][ri]) / len(pairs)
    matched_kw_dom_agree = sum(1 for qi, ri in pairs if A["kw_dom"][qi] == B["kw_dom"][ri]) / len(pairs)
    matched_kw_cos = float(np.median([float(np.dot(A["kw_norm"][qi], B["kw_norm"][ri])) for qi, ri in pairs]))
    post_delta_res = float(np.median([np.linalg.norm(A["comp"][qi] - b_shifted[ri]) for qi, ri in pairs]))

    return TwoLayerResult(
        repo_a=A["name"],
        repo_b=B["name"],
        n_a=A["n"],
        n_b=B["n"],
        fgw_cost=fgw_cost,
        t1_n=len(top_seeds),
        se_n=len(pairs),
        se_coverage=len(pairs) / max(1, min(A["n"], B["n"])),
        kw_jsd=kw_jsd,
        arch_jsd=arch_jsd,
        matched_kw_cos=matched_kw_cos,
        matched_kw_dom_agree=matched_kw_dom_agree,
        matched_arch_agree=matched_arch_agree,
        post_delta_res=post_delta_res,
    )
