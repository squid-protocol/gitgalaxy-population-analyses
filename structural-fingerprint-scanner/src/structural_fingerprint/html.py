"""Self-contained HTML report: heatmaps with dendrograms, archetype mix, tables.

No external assets. Every figure is coloured as a 0-100 rating along GitGalaxy's
Universal Risk Spectrum, the gradient gitgalaxy.io uses, so the report reads like the
website. Each figure maps its values onto 0-100 to use the whole spectrum (square root
for shares, cohort rank for distances), and its legend gives the real value at each stop. Every cell has a hover tooltip, and every figure has a
CSV behind it.
"""

from __future__ import annotations

import html
import json
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy.cluster.hierarchy import dendrogram, linkage
from scipy.spatial.distance import squareform

from .compare import Cohort
from .fingerprint import Fingerprint
from .lineage import DescentMatrix

# GitGalaxy's Universal Risk Spectrum (site/config/colors.js): the five stops gitgalaxy.io
# rates 0-100 with, placed at 0/25/50/75/100% exactly as UNIVERSAL_GRADIENT places them.
# Cells interpolate continuously along that gradient; each figure supplies a Scale that
# maps its values onto 0-100 in the way that spreads its data across the whole spectrum.
UNIVERSAL_COLORS = ["#0055ff", "#00ffff", "#ffff00", "#ff8800", "#ff0000"]
UNIVERSAL_GRADIENT = "linear-gradient(90deg, #0055ff 0%, #00ffff 25%, #ffff00 50%, #ff8800 75%, #ff0000 100%)"
_STOPS = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in UNIVERSAL_COLORS], dtype=float)
CELL = 18


def _color(score: float) -> str:
    """Hex colour at ``score`` (0-100) along the Universal gradient."""
    t = 0.0 if not np.isfinite(score) else float(np.clip(score, 0.0, 100.0)) / 25.0
    i = min(int(t), len(_STOPS) - 2)
    rgb = _STOPS[i] + (_STOPS[i + 1] - _STOPS[i]) * (t - i)
    return "#" + "".join(f"{round(x):02x}" for x in rgb)


@dataclass
class Scale:
    """Maps a figure's values onto the 0-100 rating and labels the gradient's stops."""

    score: Callable[[float], float]
    ticks: list[str]  # labels at 0, 25, 50, 75 and 100 on the gradient
    note: str


def sqrt_share_scale(note: str) -> Scale:
    """For shares in [0, 1]: the square root spreads the small shares, where most pairs and
    most archetypes sit, across the lower stops instead of one band. Stops fall at 0, 6.25,
    25, 56.25 and 100%."""
    return Scale(lambda v: 100.0 * float(np.sqrt(np.clip(v, 0.0, 1.0))),
                 [f"{100 * (q / 100) ** 2:.0f}%" for q in (0, 25, 50, 75, 100)], note)


def rank_scale(values: np.ndarray, note: str, low_is_hot: bool = True) -> Scale:
    """By rank within the figure's own values, so colour spreads evenly over what is there;
    the ticks show the actual value at each stop."""
    xs = np.sort(values[np.isfinite(values)])
    n = len(xs)

    def score(v: float) -> float:
        if n < 2:
            return 50.0
        frac = (np.searchsorted(xs, v, side="right") - 1) / (n - 1)
        return 100.0 * ((1.0 - frac) if low_is_hot else frac)

    qs = [(1 - q / 100) if low_is_hot else q / 100 for q in (0, 25, 50, 75, 100)]
    ticks = [f"{np.quantile(xs, q):.2f}" if n else "" for q in qs]
    return Scale(score, ticks, note)


def _order(dist: np.ndarray) -> tuple[list[int], dict]:
    n = len(dist)
    if n < 3:
        return list(range(n)), {}
    d = np.maximum((dist + dist.T) / 2, 0)
    np.fill_diagonal(d, 0)
    z = linkage(squareform(d, checks=False), method="average")
    dn = dendrogram(z, no_plot=True)
    return [int(i) for i in dn["leaves"]], {"icoord": dn["icoord"], "dcoord": dn["dcoord"]}


def _dendro_svg(dn: dict, n: int, width: int = 120) -> str:
    if not dn:
        return ""
    maxd = max((max(d) for d in dn["dcoord"]), default=1.0) or 1.0
    paths = []
    for xs, ys in zip(dn["icoord"], dn["dcoord"], strict=True):
        pts = [((1 - y / maxd) * (width - 4) + 2, x / 10 * CELL) for x, y in zip(xs, ys, strict=True)]
        paths.append("M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in pts))
    return (f'<svg class="dendro" width="{width}" height="{n * CELL}" viewBox="0 0 {width} {n * CELL}" '
            f'aria-hidden="true"><path d="{" ".join(paths)}"/></svg>')


def _heatmap(names: list[str], m: np.ndarray, order: list[int], scale: Scale, fmt, label: str) -> str:
    n = len(order)
    lab_w = 150
    w, h = lab_w + n * CELL + 90, n * CELL + lab_w  # right margin: rotated column labels run past the grid
    out = [f'<svg class="heat" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{label}">']
    for r, i in enumerate(order):
        y = r * CELL
        out.append(f'<text class="rl" x="{lab_w - 6}" y="{y + CELL * 0.7:.1f}" text-anchor="end">'
                   f'{html.escape(names[i])}</text>')
        for c, j in enumerate(order):
            v = float(m[i, j])
            if i == j:
                out.append(f'<rect class="diag" x="{lab_w + c * CELL + 1}" y="{y + 1}" width="{CELL - 2}" '
                           f'height="{CELL - 2}" rx="2"/>')
                continue
            tip = html.escape(f"{names[i]} · {names[j]}: {fmt(v)}")
            out.append(f'<rect fill="{_color(scale.score(v))}" x="{lab_w + c * CELL + 1}" y="{y + 1}" width="{CELL - 2}" '
                       f'height="{CELL - 2}" rx="2" data-tip="{tip}"/>')
    for c, j in enumerate(order):
        x = lab_w + c * CELL + CELL * 0.7
        out.append(f'<text class="cl" transform="translate({x:.1f},{n * CELL + 6}) rotate(60)">'
                   f'{html.escape(names[j])}</text>')
    out.append("</svg>")
    return "".join(out)


def _legend(scale: Scale) -> str:
    """The website's gradient bar with the figure's own values at the five stops."""
    ticks = "".join(f'<span style="left:{25 * k}%">{html.escape(t)}</span>' for k, t in enumerate(scale.ticks))
    return (f'<div class="legend"><div class="grad"><div class="bar" style="background:{UNIVERSAL_GRADIENT}"></div>'
            f'<div class="ticks">{ticks}</div></div><em class=scale>{html.escape(scale.note)}</em></div>')


def _figure(title: str, note: str, names, m, scale: Scale, fmt, dist=None) -> str:
    order, dn = _order(dist if dist is not None else m)
    heat = _heatmap(names, m, order, scale, fmt, title)
    return (f'<section><h2>{html.escape(title)}</h2><p class="note">{note}</p>{_legend(scale)}'
            f'<div class="fig">{_dendro_svg(dn, len(order))}{heat}</div></section>')


def _archetype_strip(fps: list[Fingerprint], order: list[int]) -> str:
    arch = list(fps[0].data["archetypes"]["count_share"])
    m = np.array([[fp.data["archetypes"]["count_share"][a] for a in arch] for fp in fps])
    arch_scale = sqrt_share_scale("% of functions, square-root scale")
    lab_w, n, k = 150, len(order), len(arch)
    w, h = lab_w + k * CELL + 160, n * CELL + 170
    out = [(f'<svg class="heat" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
            'aria-label="Function archetype mix per repository">')]
    for r, i in enumerate(order):
        y = r * CELL
        out.append(f'<text class="rl" x="{lab_w - 6}" y="{y + CELL * 0.7:.1f}" text-anchor="end">'
                   f'{html.escape(fps[i].name)}</text>')
        for c, a in enumerate(arch):
            v = float(m[i, c])
            tip = html.escape(f"{fps[i].name} · {a}: {100 * v:.1f}% of functions")
            out.append(f'<rect fill="{_color(arch_scale.score(v))}" x="{lab_w + c * CELL + 1}" y="{y + 1}" '
                       f'width="{CELL - 2}" height="{CELL - 2}" rx="2" data-tip="{tip}"/>')
    for c, a in enumerate(arch):
        x = lab_w + c * CELL + CELL * 0.7
        out.append(f'<text class="cl" transform="translate({x:.1f},{n * CELL + 6}) rotate(60)">{html.escape(a)}</text>')
    out.append("</svg>")
    return ("<section><h2>Function archetype mix</h2><p class=\"note\">Share of each repository's functions in each "
            "of the engine's 14 function archetypes (rows in descent-tree order).</p>"
            f"{_legend(arch_scale)}<div class=\"fig\">{''.join(out)}</div></section>")


def _table(summary: dict) -> str:
    rows = []
    for r in summary["repositories"]:
        prof = ", ".join(f"{html.escape(n)} ({d:.2f})" for n, d in r.get("nearest_by_profile", [])[:2])
        desc = ", ".join(f"{html.escape(n)} ({100 * s:.0f}%)" for n, s in r.get("nearest_by_descent", [])[:2])
        arch = ", ".join(f"{html.escape(a)} {100 * s:.0f}%" for a, s in r["top_archetypes"][:2])
        rows.append(f"<tr><th scope=row>{html.escape(r['name'])}</th><td class=num>{r['functions']:,}</td>"
                    f"<td class=num>{r['coding_loc']:,.0f}</td><td>{html.escape(', '.join(r['languages']))}</td>"
                    f"<td>{arch}</td><td>{prof or 'n/a'}</td><td>{desc or 'n/a'}</td></tr>")
    return ("<section><h2>Repositories</h2><div class=tablewrap><table><thead><tr><th>Repository</th>"
            "<th class=num>Functions</th><th class=num>Coding LOC</th><th>Languages</th><th>Leading archetypes</th>"
            "<th>Nearest by profile</th><th>Nearest by descent</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div></section>")


def _lineage(summary: dict) -> str:
    ev = summary.get("lineage_evaluation") or {}
    parts = []
    for basis, e in ev.items():
        if not e or not e.get("evaluated"):
            continue
        rows = "".join(f"<tr><th scope=row>{html.escape(r['name'])}</th><td>{html.escape(', '.join(r['declared_parents']))}"
                       f"</td><td class=num>{r['rank']}</td><td>{html.escape(r['nearest'])}</td></tr>" for r in e["rows"])
        fam = e.get("nearest_is_family")
        parts.append(f"<h3>{html.escape(basis)}</h3><p>Nearest neighbour is declared family (ancestor, descendant, sibling or cousin) "
                     f"for <strong>{100 * (fam or 0):.0f}%</strong> of {e.get('family_evaluated', 0)} repositories. "
                     f"Of {e['evaluated']} with a declared parent in the cohort, the parent is the nearest "
                     f"non-descendant for <strong>{100 * e['hit_at_1']:.0f}%</strong> and within the nearest three for "
                     f"<strong>{100 * e['hit_at_3']:.0f}%</strong> (mean rank {e['mean_rank']:.2f}).</p>"
                     + (f"<p class=note>No detectable shared structure with any repository in the cohort: "
                        f"{html.escape(', '.join(e['undetectable']))}.</p>" if e.get("undetectable") else "")
                     + f"<div class=tablewrap><table><thead><tr><th>Repository</th><th>Declared parent(s)</th>"
                     f"<th class=num>Rank</th><th>Nearest</th></tr></thead><tbody>{rows}</tbody></table></div>")
    return f"<section><h2>Declared lineage check</h2>{''.join(parts)}</section>" if parts else ""


CSS = """
:root{color-scheme:light;--surface:#fcfcfb;--text:#0b0b0b;--text2:#52514e;--rule:#e4e3df;--diag:#e9e8e4;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--surface:#1a1a19;--text:#f0efec;
--text2:#c3c2b7;--rule:#383835;--diag:#2a2a28}}
:root[data-theme="dark"]{color-scheme:dark;--surface:#1a1a19;--text:#f0efec;--text2:#c3c2b7;--rule:#383835;--diag:#2a2a28}
*{box-sizing:border-box}body{margin:0;background:var(--surface);color:var(--text);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1200px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:36px 0 6px}h3{font-size:16px;margin:20px 0 4px}
.meta,.note{color:var(--text2);margin:0 0 10px;max-width:80ch}.fig{display:flex;overflow-x:auto;padding-bottom:6px}
.dendro path{fill:none;stroke:var(--text2);stroke-width:1.2}
.heat text{fill:var(--text2);font-size:11px}.diag{fill:var(--diag)}
.legend{display:flex;align-items:flex-start;gap:14px;font-size:12px;color:var(--text2);margin:6px 0 18px}.legend .grad{width:260px}.legend .bar{height:10px;border-radius:3px}.legend .ticks{position:relative;height:14px}.legend .ticks span{position:absolute;transform:translateX(-50%);top:2px;white-space:nowrap}.legend .ticks span:first-child{transform:none}.legend .ticks span:last-child{transform:translateX(-100%)}
.legend em{font-style:normal}.legend .scale{margin-top:-1px}
table{border-collapse:collapse;font-size:13px;width:100%}th,td{padding:5px 8px;border-bottom:1px solid var(--rule);text-align:left;
vertical-align:top}thead th{color:var(--text2);font-weight:600}.num{text-align:right;font-variant-numeric:tabular-nums}
.tablewrap{overflow-x:auto}code{font-size:13px}
#tip{position:fixed;pointer-events:none;background:var(--text);color:var(--surface);padding:4px 8px;border-radius:4px;
font-size:12px;display:none;z-index:9;max-width:320px}
"""

JS = """
const tip=document.getElementById('tip');
document.addEventListener('mousemove',e=>{const t=e.target.closest('[data-tip]');
if(!t){tip.style.display='none';return}tip.textContent=t.dataset.tip;tip.style.display='block';
tip.style.left=Math.min(e.clientX+12,innerWidth-330)+'px';tip.style.top=(e.clientY+14)+'px'});
"""


def render_html(summary: dict, fps: list[Fingerprint], cohort: Cohort, descent: DescentMatrix | None) -> str:
    names = cohort.names
    spec = summary["spec"]
    css = CSS
    embedded = json.dumps(summary).replace("</", "<\\/")  # keep "</script>" out of the JSON
    sections = []
    order_desc = list(range(len(names)))
    if descent is not None:
        order_desc, _ = _order(descent.distance)
        sections.append(_figure(
            "Descent: shared structure", "Share of functions with a calibrated structural twin in the other "
            "repository (the larger of the two directions). Twins are found without names; this tracks inherited code.",
            names, descent.shared, sqrt_share_scale("% shared, square-root scale"),
            lambda v: f"{100 * v:.1f}% shared", dist=descent.distance))
    if cohort.composite is not None:
        sections.append(_figure(
            "Profile: structural distance", "Fingerprint distance (archetype mix, signal densities, function "
            "geometry, centre, call-graph shape). 1.0 is a typical pair in this cohort.",
            names, cohort.composite,
            rank_scale(cohort.composite[np.triu_indices(len(names), 1)], "profile distance, by rank in this cohort"),
            lambda v: f"distance {v:.2f}", dist=cohort.composite))
    sections.append(_archetype_strip(fps, order_desc))
    sections.append(_lineage(summary))
    sections.append(_table(summary))
    ref = spec["reference"]
    prov = (f"Lens <code>{html.escape(spec['lens'])}</code> · spec <code>{spec['spec_hash']}</code> · reference model "
            f"GitGalaxy <code>{html.escape(ref.get('engine_commit', '')[:9])}</code> · "
            f"structural-fingerprint-scanner {summary['tool']['version']}")
    return ("<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content=\"width=device-width,"
            "initial-scale=1\"><title>Structural fingerprint report</title>"
            f"<style>{css}</style></head><body><main><h1>Structural fingerprint report</h1>"
            f"<p class=meta>{len(names)} repositories · {prov}</p>"
            + "".join(sections)
            + "<p class=note>Matrices behind every figure are in <code>matrices/</code>; "
            "<code>summary.json</code> has everything machine-readable.</p>"
            f"</main><div id=tip role=tooltip></div><script>{JS}</script>"
            f"<script type=application/json id=summary>{embedded}</script></body></html>")
