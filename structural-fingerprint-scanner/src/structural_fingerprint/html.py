"""Self-contained HTML report: heatmaps with dendrograms, archetype mix, tables.

No external assets. Every figure is coloured as a 0-100 rating with GitGalaxy's
Universal Risk Spectrum (the five stops gitgalaxy.io uses, one per 20 points), so the
report reads like the website. Every cell has a hover tooltip, and every figure has a
CSV behind it.
"""

from __future__ import annotations

import html
import json

import numpy as np
from scipy.cluster.hierarchy import dendrogram, linkage
from scipy.spatial.distance import squareform

from .compare import Cohort
from .fingerprint import Fingerprint
from .lineage import DescentMatrix

# GitGalaxy's Universal Risk Spectrum (site/config/colors.js UNIVERSAL_COLORS): every 0-100
# rating on gitgalaxy.io is drawn with these five stops, one per 20 points.
UNIVERSAL_COLORS = ["#0055ff", "#00ffff", "#ffff00", "#ff8800", "#ff0000"]
CELL = 18


def _bin(score: float) -> int:
    """The site's mapping: floor(score / 20), clamped to the five stops."""
    if not np.isfinite(score):
        return 0
    return int(min(4, max(0, score // 20)))


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


def _heatmap(names: list[str], m: np.ndarray, order: list[int], score, fmt, label: str) -> str:
    """``score`` maps a cell value to the 0-100 rating that picks its colour."""
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
            out.append(f'<rect class="c{_bin(score(v))}" x="{lab_w + c * CELL + 1}" y="{y + 1}" width="{CELL - 2}" '
                       f'height="{CELL - 2}" rx="2" data-tip="{tip}"/>')
    for c, j in enumerate(order):
        x = lab_w + c * CELL + CELL * 0.7
        out.append(f'<text class="cl" transform="translate({x:.1f},{n * CELL + 6}) rotate(60)">'
                   f'{html.escape(names[j])}</text>')
    out.append("</svg>")
    return "".join(out)


def _legend(unit: str) -> str:
    """Five swatches, one per 20-point band of the 0-100 rating, as on the website."""
    items = "".join(f'<span class="item"><span class="sw c{k}"></span>{20 * k}–{20 * (k + 1)}</span>'
                    for k in range(len(UNIVERSAL_COLORS)))
    return f'<div class="legend">{items}<em class=scale>{html.escape(unit)}</em></div>'


def _figure(title: str, note: str, names, m, score, fmt, unit: str, dist=None) -> str:
    order, dn = _order(dist if dist is not None else m)
    heat = _heatmap(names, m, order, score, fmt, title)
    return (f'<section><h2>{html.escape(title)}</h2><p class="note">{note}</p>{_legend(unit)}'
            f'<div class="fig">{_dendro_svg(dn, len(order))}{heat}</div></section>')


def _archetype_strip(fps: list[Fingerprint], order: list[int]) -> str:
    arch = list(fps[0].data["archetypes"]["count_share"])
    m = np.array([[fp.data["archetypes"]["count_share"][a] for a in arch] for fp in fps])
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
            out.append(f'<rect class="c{_bin(100 * v)}" x="{lab_w + c * CELL + 1}" y="{y + 1}" '
                       f'width="{CELL - 2}" height="{CELL - 2}" rx="2" data-tip="{tip}"/>')
    for c, a in enumerate(arch):
        x = lab_w + c * CELL + CELL * 0.7
        out.append(f'<text class="cl" transform="translate({x:.1f},{n * CELL + 6}) rotate(60)">{html.escape(a)}</text>')
    out.append("</svg>")
    return ("<section><h2>Function archetype mix</h2><p class=\"note\">Share of each repository's functions in each "
            "of the engine's 14 function archetypes (rows in descent-tree order).</p>"
            f"{_legend('% of functions')}<div class=\"fig\">{''.join(out)}</div></section>")


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
.legend{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--text2);margin:6px 0 10px}
.legend em{font-style:normal}.legend .scale{margin-left:4px}.legend .item{display:inline-flex;align-items:center;gap:4px}.legend .sw{width:14px;height:10px;border-radius:2px;display:block}
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


def _palette_css() -> str:
    # The website draws ratings with the same five stops in every theme.
    return "".join(f".c{k}{{fill:{c};background:{c}}}" for k, c in enumerate(UNIVERSAL_COLORS))


def render_html(summary: dict, fps: list[Fingerprint], cohort: Cohort, descent: DescentMatrix | None) -> str:
    names = cohort.names
    spec = summary["spec"]
    css = CSS + _palette_css()
    embedded = json.dumps(summary).replace("</", "<\\/")  # keep "</script>" out of the JSON
    sections = []
    order_desc = list(range(len(names)))
    if descent is not None:
        order_desc, _ = _order(descent.distance)
        sections.append(_figure(
            "Descent: shared structure", "Share of functions with a calibrated structural twin in the other "
            "repository (the larger of the two directions). Twins are found without names; this tracks inherited code.",
            names, descent.shared, lambda v: 100 * v, lambda v: f"{100 * v:.1f}% shared", "% shared",
            dist=descent.distance))
    if cohort.composite is not None:
        hi = float(np.max(cohort.composite))
        sections.append(_figure(
            "Profile: structural distance", "Fingerprint distance (archetype mix, signal densities, function "
            "geometry, centre, call-graph shape). 1.0 is a typical pair in this cohort.",
            names, cohort.composite, lambda v: 100 * (1 - v / hi) if hi > 0 else 0.0,
            lambda v: f"distance {v:.2f} · closeness {100 * (1 - v / hi) if hi > 0 else 0:.0f}",
            f"closeness (100 = closest pair; farthest {hi:.1f} = 0)", dist=cohort.composite))
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
