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

    def __post_init__(self) -> None:
        if self.fallback not in self.subsystems:
            self.subsystems.append(self.fallback)
        known = set(self.subsystems)
        bad = {s for _, s in self.basename_prefix + self.path_keyword} - known
        if bad:
            raise ValueError(f"taxonomy rules name unknown subsystems: {sorted(bad)}")
        self.index = {s: i for i, s in enumerate(self.subsystems)}

    @classmethod
    def load(cls, path: Path) -> Taxonomy:
        d = json.loads(Path(path).read_text())
        return cls(name=d.get("name", Path(path).stem), subsystems=list(d["subsystems"]),
                   basename_prefix=[tuple(x) for x in d.get("basename_prefix", [])],
                   path_keyword=[tuple(x) for x in d.get("path_keyword", [])],
                   fallback=d.get("fallback", "other"))

    @classmethod
    def from_directories(cls, reference: FunctionTable, top: int = 14) -> Taxonomy:
        """Subsystems = the reference's most populated top-level directories."""
        heads = Counter(_dir_head(p) for p, lang in zip(reference.path, reference.language, strict=True)
                        if lang not in NON_CODE)
        subs = [h for h, _ in heads.most_common(top) if h]
        return cls(name="top-level directories", subsystems=subs, directory_depth=1)

    def classify(self, path: str) -> int:
        if self.directory_depth:
            return self.index.get(_dir_head(path), self.index[self.fallback])
        base = path.rsplit("/", 1)[-1].lower()
        for prefix, sub in self.basename_prefix:
            if base.startswith(prefix):
                return self.index[sub]
        low = path.lower()
        for kw, sub in self.path_keyword:
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
            labels[i] = tax.classify(str(table.path[i]))
            src["path" if labels[i] != tax.index[tax.fallback] else "fallback"] += 1
    return labels, dict(src)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a.ravel(), b.ravel()
    d = np.linalg.norm(a) * np.linalg.norm(b)
    return float(a @ b / d) if d else float("nan")


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


def _survival(ref_labels: np.ndarray, ref: FunctionTable, ref_to_port: TwinResult, port_to_ref: TwinResult,
              s: int, min_loc: int) -> np.ndarray:
    """Per subsystem, the share of the reference's eligible functions linked to a twin in
    either direction. Both directions count because a port that carries a function more
    than once (two copies, or a generated build beside its sources) fails the
    reference-side distinctiveness test while its own copies still find the reference."""
    eligible = (ref.loc >= min_loc) & (ref_labels >= 0)
    has = np.zeros(len(ref), dtype=bool)
    has[ref_to_port.q_index] = True
    has[port_to_ref.t_index] = True
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
    ref_labels = np.where(_code_mask(ref), [tax.classify(str(x)) for x in ref.path], -1).astype(np.int64)
    ref_map = SubwayMap(reference, tax.subsystems, np.bincount(ref_labels[ref_labels >= 0], minlength=s),
                        _calls(ref_labels, ref.edges, s), {"path": int((ref_labels >= 0).sum())},
                        survival=np.where(np.bincount(ref_labels[ref_labels >= 0], minlength=s) > 0, 1.0, np.nan))
    ref_map.wiring_similarity, ref_map.edges_kept = 1.0, 1.0
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
        maps.append(m)
    return maps, tax, layout(ref_map)


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
    for n, x, y in pts:
        tip = html.escape(f"{n}: {xlabel} {x:.2f}, {ylabel} {y:.2f}")
        out.append(f'<circle class="dot" cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="5" data-tip="{tip}"/>'
                   f'<text class="dl" x="{sx(x) + 7:.1f}" y="{sy(y) + 3:.1f}">{html.escape(n)}</text>')
    out.append("</svg>")
    return "".join(out)


def render_section(maps: list[SubwayMap], pos: np.ndarray, tax: Taxonomy, reference: str,
                   profile_to_reference: dict[str, float] | None = None) -> str:
    from .html import _legend, sqrt_share_scale

    order = [maps[0]] + sorted(maps[1:], key=lambda m: -(m.wiring_similarity if np.isfinite(m.wiring_similarity) else -1))
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
    rows = "".join(
        f"<tr><th scope=row>{html.escape(m.repo)}</th><td class=num>{int(m.sizes.sum()):,}</td>"
        f"<td class=num>{m.wiring_similarity:.2f}</td>"
        f"<td class=num>{'' if not np.isfinite(m.edges_kept) else f'{100 * m.edges_kept:.0f}%'}</td>"
        f"<td>{html.escape(', '.join(f'{k} {v:,}' for k, v in sorted(m.sources.items(), key=lambda kv: -kv[1])))}</td></tr>"
        for m in order)
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
            "<em>calls kept</em> is the share of the reference's calls still made between the corresponding functions.</p>"
            f"{_legend(scale)}<div class=subways>{''.join(panels)}</div>{scatter}"
            "<div class=tablewrap><table><thead><tr><th>Repository</th><th class=num>Functions on map</th>"
            "<th class=num>Wiring</th><th class=num>Calls kept</th><th>Placed by</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div></section>")


def write_outputs(out: Path, maps: list[SubwayMap], tax: Taxonomy, reference: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "subway.json").write_text(json.dumps({"reference": reference, "taxonomy": tax.name,
                                                 "subsystems": tax.subsystems,
                                                 "maps": [m.to_dict() for m in maps]}, indent=1) + "\n")
    with open(out / "subway.csv", "w") as f:
        f.write("repo,functions,wiring_similarity,edges_kept," + ",".join(f"survival_{s}" for s in tax.subsystems) + "\n")
        for m in maps:
            surv = ["" if m.survival is None or not np.isfinite(v) else f"{v:.4f}"
                    for v in (m.survival if m.survival is not None else [np.nan] * len(tax.subsystems))]
            ek = "" if not np.isfinite(m.edges_kept) else f"{m.edges_kept:.4f}"
            f.write(f"{m.repo},{int(m.sizes.sum())},{m.wiring_similarity:.4f},{ek}," + ",".join(surv) + "\n")
