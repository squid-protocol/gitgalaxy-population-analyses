"""Trees and lineage evidence for a cohort.

Two different questions, two different trees:

* The **profile tree** clusters repositories by fingerprint distance: how alike their
  designs are (archetype mix, signal densities, geometry, call-graph shape). It works
  across languages, and two independent implementations of the same design land close.
* The **descent tree** clusters by *shared structure*: the share of functions with a
  calibrated structural twin in the other repository. Twins survive renaming but not
  rewriting, so this tree follows inherited code. Like genomes, codebases also share
  code sideways (a library or module both adopted), and shared structure counts that
  too; the twin lists say which functions carry the signal.

Shared structure is scored by the Wilson 95% lower bound of the twin proportion, so a
handful of chance twins in a 50-function repository cannot outrank thousands of twins
in a large one.

Both are UPGMA (average-linkage) trees, written as Newick with branch lengths.
"""

from __future__ import annotations

import csv
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import leaves_list, linkage, to_tree
from scipy.spatial.distance import squareform

from .fingerprint import FunctionTable
from .twins import TwinParams, TwinResult, find_twins

log = logging.getLogger(__name__)


def upgma(distance: np.ndarray, names: list[str]) -> tuple[str, list[int]]:
    """(Newick string, leaf order) for a symmetric distance matrix."""
    n = len(names)
    if n == 1:
        return f"{_quote(names[0])};", [0]
    if n == 2:
        h = float(distance[0, 1]) / 2
        return f"({_quote(names[0])}:{h:.6f},{_quote(names[1])}:{h:.6f});", [0, 1]
    d = np.asarray(distance, dtype=np.float64)
    d = (d + d.T) / 2
    np.fill_diagonal(d, 0.0)
    z = linkage(squareform(np.maximum(d, 0.0), checks=False), method="average")
    root = to_tree(z)

    def walk(node, parent_h: float) -> str:
        h = node.dist / 2
        bl = max(parent_h - h, 0.0)
        if node.is_leaf():
            return f"{_quote(names[node.id])}:{bl:.6f}"
        return f"({walk(node.left, h)},{walk(node.right, h)}):{bl:.6f}"

    top = root.dist / 2
    newick = f"({walk(root.left, top)},{walk(root.right, top)});"
    return newick, [int(i) for i in leaves_list(z)]


def _quote(name: str) -> str:
    if any(c in name for c in " ():;,'[]"):
        return "'" + name.replace("'", "''") + "'"
    return name


def wilson_lower(k: np.ndarray, n: np.ndarray, z: float = 1.96) -> np.ndarray:
    """Wilson score lower bound of the proportion k/n (0 where n is 0)."""
    k = np.asarray(k, dtype=np.float64)
    n = np.asarray(n, dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        p = np.where(n > 0, k / n, 0.0)
        denom = 1 + z * z / n
        centre = p + z * z / (2 * n)
        margin = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
        lb = (centre - margin) / denom
    return np.where(n > 0, np.clip(lb, 0.0, 1.0), 0.0)


@dataclass
class DescentMatrix:
    names: list[str]
    eligible: np.ndarray  # [i]: functions of i eligible for twin search
    survival: np.ndarray  # [i, j]: share of i's eligible functions with a twin in j
    survival_loc: np.ndarray
    twins: np.ndarray
    exact: np.ndarray
    name_agreement: np.ndarray  # nan where undefined
    results: dict[tuple[int, int], TwinResult]

    @property
    def survival_lower(self) -> np.ndarray:
        """Wilson 95% lower bound of each directional survival."""
        lb = wilson_lower(self.twins, self.eligible[:, None] * np.ones_like(self.survival))
        np.fill_diagonal(lb, 1.0)
        return lb

    @property
    def shared(self) -> np.ndarray:
        """Symmetric shared structure: the larger of the two directional survival lower
        bounds, so a small ancestor contained in a large descendant scores high."""
        lb = self.survival_lower
        s = np.maximum(lb, lb.T)
        np.fill_diagonal(s, 1.0)
        return s

    @property
    def distance(self) -> np.ndarray:
        return 1.0 - self.shared


def descent_matrix(tables: list[FunctionTable], params: TwinParams | None = None,
                   workers: int = 1, keep_results: bool = False) -> DescentMatrix:
    n = len(tables)
    p = params or TwinParams()
    surv, surv_loc = np.eye(n), np.eye(n)
    eligible = np.zeros(n, dtype=np.int64)
    twins, exact = np.zeros((n, n), dtype=np.int64), np.zeros((n, n), dtype=np.int64)
    agree = np.full((n, n), np.nan)
    results: dict[tuple[int, int], TwinResult] = {}
    pairs = [(i, j) for i in range(n) for j in range(n) if i != j]

    def run(ij: tuple[int, int]) -> tuple[tuple[int, int], TwinResult]:
        i, j = ij
        return ij, find_twins(tables[i], tables[j], p)

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for (i, j), r in ex.map(run, pairs):
            s = r.stats
            surv[i, j], surv_loc[i, j] = s["survival"], s["survival_loc"]
            eligible[i] = s["eligible"]
            twins[i, j], exact[i, j] = s["twins"], s["exact_clones"]
            if s["name_agreement"] is not None:
                agree[i, j] = s["name_agreement"]
            if keep_results:
                results[(i, j)] = r
            done += 1
            if done % 100 == 0 or done == len(pairs):
                log.info("twin search: %d/%d directed pairs", done, len(pairs))
    return DescentMatrix([t.repo for t in tables], eligible, surv, surv_loc, twins, exact, agree, results)


def read_declared_lineage(path: Path) -> dict[str, list[str]]:
    """CSV with columns ``name,parent`` (one row per declared parent; several allowed)."""
    out: dict[str, list[str]] = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            name, parent = (row.get("name") or "").strip(), (row.get("parent") or "").strip()
            if name and parent:
                out.setdefault(name, []).append(parent)
    return out


def _family(declared: dict[str, list[str]]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """(ancestors, descendants) per name, transitively, from declared parent edges."""
    parents = {c: set(ps) for c, ps in declared.items()}

    def climb(n: str, seen: set[str]) -> set[str]:
        for p in parents.get(n, ()):
            if p not in seen:
                seen.add(p)
                climb(p, seen)
        return seen

    ancestors = {n: climb(n, set()) for n in set(parents) | {p for ps in parents.values() for p in ps}}
    descendants: dict[str, set[str]] = {n: set() for n in ancestors}
    for n, anc in ancestors.items():
        for a in anc:
            descendants.setdefault(a, set()).add(n)
    return ancestors, descendants


def evaluate_lineage(names: list[str], distance: np.ndarray, declared: dict[str, list[str]],
                     max_distance: float | None = None) -> dict:
    """Check a distance matrix against declared lineage.

    ``parent rank``: for each repository with a declared parent in the cohort, the rank
    of its nearest declared parent among the others, *not counting its own declared
    descendants* (a fork's children legitimately share more with it than its parent
    does). ``nearest is family``: for every repository with a declared relative in the
    cohort, whether its nearest neighbour is a declared ancestor, descendant, sibling
    (shares a declared parent) or cousin (shares a declared ancestor other than the
    cohort's root), rather than on another branch.

    ``max_distance``: a nearest neighbour farther than this is no evidence at all; such
    repositories are listed as ``undetectable`` and left out of both rates (for the
    descent tree: no detectable shared structure with anything in the cohort).
    """
    idx = {n: i for i, n in enumerate(names)}
    ancestors, descendants = _family(declared)
    undetectable = set()
    if max_distance is not None:
        for n, i in idx.items():
            others = np.delete(distance[i], i)
            if len(others) and others.min() > max_distance:
                undetectable.add(n)
    rows = []
    for child, parents in declared.items():
        if child not in idx or child in undetectable:
            continue
        ps = [p for p in parents if p in idx and p != child]
        if not ps:
            continue
        i = idx[child]
        skip = descendants.get(child, set())
        order = [j for j in np.argsort(distance[i], kind="stable") if j != i and names[j] not in skip]
        rank = min(order.index(idx[p]) for p in ps) + 1
        rows.append({"name": child, "declared_parents": ps, "rank": rank, "nearest": names[order[0]]})
    ranks = np.array([r["rank"] for r in rows])

    roots = {a for anc in ancestors.values() for a in anc if not ancestors.get(a)}
    fam_rows = []
    for n in names:
        anc, desc = ancestors.get(n, set()), descendants.get(n, set())
        if not (anc or desc) or n in undetectable:
            continue
        i = idx[n]
        j = next(j for j in np.argsort(distance[i], kind="stable") if j != i)
        m = names[j]
        shared_anc = (anc & ancestors.get(m, set())) - roots
        if m in anc:
            rel = "ancestor"
        elif m in desc:
            rel = "descendant"
        elif set(declared.get(n, [])) & set(declared.get(m, [])):
            rel = "sibling"
        elif shared_anc:
            rel = "cousin"
        else:
            rel = "other branch"
        fam_rows.append({"name": n, "nearest": m, "relation": rel})
    fam_hit = [r["relation"] != "other branch" for r in fam_rows]
    return {
        "evaluated": len(rows),
        "hit_at_1": float((ranks == 1).mean()) if len(ranks) else None,
        "hit_at_3": float((ranks <= 3).mean()) if len(ranks) else None,
        "mean_rank": float(ranks.mean()) if len(ranks) else None,
        "nearest_is_family": float(np.mean(fam_hit)) if fam_hit else None,
        "family_evaluated": len(fam_rows),
        "rows": sorted(rows, key=lambda r: (r["rank"], r["name"])),
        "undetectable": sorted(undetectable),
        "nearest_rows": sorted(fam_rows, key=lambda r: (r["relation"] == "other branch", r["name"])),
    }
