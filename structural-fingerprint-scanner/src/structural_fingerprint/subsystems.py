"""Per-subsystem fingerprints: is this repository's renderer designed like the
reference's renderer?

The subway maps decide which subsystem each function belongs to (twin, then name, then
path). Here each (repository, subsystem) cell compares the repository's functions in
that subsystem with the reference's functions in the same subsystem, in the reference
frame, with three distances:

``centroid``      LOC-weighted centres in the lens space, Euclidean / sqrt(features);
``archetypes``    Jensen-Shannon distance of the engine archetype mixes;
``distribution``  mean over features of the 1-Wasserstein distance between the two
                  sets of function coordinates (shape of the whole distribution, not
                  just its centre).

The **composite** divides each by its median over all cells and averages them, so 1.0
is a typical cell in the cohort. A cell needs ``min_functions`` on both sides; smaller
ones are left empty rather than guessed. Each cell also names its **drift**: the
features whose mean moved most, in population-IQR units (the lens weight divided out),
which is what makes a cell explainable.

Across languages this is the engine-calibration view: when a port kept the reference's
algorithm (its call wiring survives: ``calls kept`` at least ``faithful``) yet a
subsystem scores far from the reference, either the port changed that subsystem or the
engine measures that language differently. The language table and the candidate list
say where to look.
"""

from __future__ import annotations

import html
import math
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import wasserstein_distance

from .compare import _js_distance
from .fingerprint import FunctionTable
from .reference import Reference
from .subway import NON_CODE, SubwayMap

COMPONENTS = ("centroid", "archetypes", "distribution")


@dataclass
class Cell:
    repo: str
    subsystem: str
    n: int
    n_ref: int
    distances: dict[str, float] = field(default_factory=dict)
    composite: float = float("nan")
    drift: list[tuple[str, float]] = field(default_factory=list)  # (feature, mean shift in population IQRs)


@dataclass
class SubsystemProfile:
    reference: str
    subsystems: list[str]
    repos: list[str]
    cells: dict[tuple[str, str], Cell]
    languages: dict[str, str]
    calls_kept: dict[str, float]
    scales: dict[str, float]
    min_functions: int
    faithful: float

    def matrix(self) -> np.ndarray:
        m = np.full((len(self.repos), len(self.subsystems)), np.nan)
        for i, r in enumerate(self.repos):
            for j, s in enumerate(self.subsystems):
                c = self.cells.get((r, s))
                if c is not None:
                    m[i, j] = c.composite
        return m

    def by_language(self) -> list[dict]:
        """Median composite per language over faithful repositories, with the features
        that drift most often among their cells."""
        rows = []
        groups: dict[str, list[Cell]] = {}
        ports: dict[str, set[str]] = {}
        for (r, _), c in self.cells.items():
            if not np.isfinite(c.composite) or not (self.calls_kept.get(r, 0.0) >= self.faithful):
                continue
            lang = self.languages.get(r, "?")
            groups.setdefault(lang, []).append(c)
            ports.setdefault(lang, set()).add(r)
        for lang, cells in groups.items():
            drift = Counter()
            for c in cells:
                for f, v in c.drift[:2]:
                    drift[(f, "+" if v > 0 else "−")] += 1
            rows.append({
                "language": lang, "repositories": sorted(ports[lang]), "cells": len(cells),
                "median_distance": float(np.median([c.composite for c in cells])),
                "common_drift": [f"{f} {sign}" for (f, sign), _ in drift.most_common(3)],
            })
        return sorted(rows, key=lambda r: r["median_distance"])

    def candidates(self, quantile: float = 0.75) -> list[Cell]:
        """Cells of faithful repositories in another language than the reference whose
        composite is in the cohort's top quarter."""
        vals = [c.composite for c in self.cells.values() if np.isfinite(c.composite)]
        if not vals:
            return []
        cut = float(np.quantile(vals, quantile))
        ref_lang = self.languages.get(self.reference)
        out = [c for (r, _), c in self.cells.items()
               if np.isfinite(c.composite) and c.composite >= cut and self.calls_kept.get(r, 0.0) >= self.faithful
               and self.languages.get(r) != ref_lang]
        return sorted(out, key=lambda c: -c.composite)


def main_language(t: FunctionTable) -> str:
    langs = Counter(lang for lang in t.language if lang not in NON_CODE)
    return langs.most_common(1)[0][0] if langs else "?"


def _weighted_mean(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    return (x * w[:, None]).sum(0) / w.sum()


def profile(tables: dict[str, FunctionTable], maps: list[SubwayMap], ref: Reference,
            min_functions: int = 10, faithful: float = 0.3, top_drift: int = 3) -> SubsystemProfile:
    reference = maps[0].repo
    subsystems = list(maps[0].subsystems)
    rt = tables[reference]
    r_labels = maps[0].labels
    feats = list(ref.feature_names)
    w = np.where(ref.weights > 0, ref.weights, np.nan)
    cells: dict[tuple[str, str], Cell] = {}
    for m in maps[1:]:
        t = tables[m.repo]
        for k, sub in enumerate(subsystems):
            qi = np.flatnonzero(m.labels == k)
            ri = np.flatnonzero(r_labels == k)
            c = Cell(m.repo, sub, len(qi), len(ri))
            cells[(m.repo, sub)] = c
            if len(qi) < min_functions or len(ri) < min_functions:
                continue
            q, r = t.vectors[qi].astype(float), rt.vectors[ri].astype(float)
            qc = _weighted_mean(q, np.maximum(t.loc[qi], 1).astype(float))
            rc = _weighted_mean(r, np.maximum(rt.loc[ri], 1).astype(float))
            c.distances = {
                "centroid": float(np.linalg.norm(qc - rc) / math.sqrt(len(qc))),
                "archetypes": _js_distance(np.bincount(t.archetype[qi], minlength=len(ref.archetype_names)).astype(float),
                                           np.bincount(rt.archetype[ri], minlength=len(ref.archetype_names)).astype(float)),
                "distribution": float(np.mean([wasserstein_distance(q[:, f], r[:, f]) for f in range(q.shape[1])])),
            }
            shift = (q.mean(0) - r.mean(0)) / w
            order = [f for f in np.argsort(-np.nan_to_num(np.abs(shift), nan=-1)) if np.isfinite(shift[f])][:top_drift]
            c.drift = [(feats[f].removeprefix("log_density_"), float(shift[f])) for f in order]
    scales = {}
    for comp in COMPONENTS:
        vals = [c.distances[comp] for c in cells.values() if c.distances]
        med = float(np.median(vals)) if vals else 1.0
        scales[comp] = med if med > 0 else 1.0
    for c in cells.values():
        if c.distances:
            c.composite = float(np.mean([c.distances[k] / scales[k] for k in COMPONENTS]))
    return SubsystemProfile(
        reference=reference, subsystems=subsystems, repos=[m.repo for m in maps[1:]], cells=cells,
        languages={name: main_language(t) for name, t in tables.items()},
        calls_kept={m.repo: (m.edges_kept if np.isfinite(m.edges_kept) else 0.0) for m in maps},
        scales=scales, min_functions=min_functions, faithful=faithful,
    )


def _drift_text(c: Cell) -> str:
    return ", ".join(f"{f} {v:+.2f}" for f, v in c.drift)


def write_csv(path, p: SubsystemProfile) -> None:
    with open(path, "w") as f:
        f.write("repo,language,subsystem,functions,reference_functions," + ",".join(COMPONENTS)
                + ",composite,drift\n")
        for (r, s), c in p.cells.items():
            d = ",".join("" if k not in c.distances else f"{c.distances[k]:.4f}" for k in COMPONENTS)
            comp = "" if not np.isfinite(c.composite) else f"{c.composite:.4f}"
            f.write(f"{r},{p.languages.get(r, '')},{s},{c.n},{c.n_ref},{d},{comp},\"{_drift_text(c)}\"\n")


def render_section(p: SubsystemProfile, order: list[str] | None = None) -> str:
    from .html import _color, _legend, rank_scale

    repos = [r for r in (order or p.repos) if r in p.repos]
    subs = [s for s in p.subsystems if any(np.isfinite(p.cells[(r, s)].composite) for r in repos)]
    vals = np.array([p.cells[(r, s)].composite for r in repos for s in subs])
    scale = rank_scale(vals, "subsystem distance from the reference's, by rank (closest = red)")
    cell = 18
    lab_w = 12 + 6.4 * max((len(r) + len(p.languages.get(r, "")) + 3 for r in repos), default=10)
    lab_w = int(lab_w)
    w, h = lab_w + len(subs) * cell + 120, len(repos) * cell + 110
    out = [(f'<svg class="heat" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
            'aria-label="Subsystem distance from the reference">')]
    for i, r in enumerate(repos):
        y = i * cell
        out.append(f'<text x="{lab_w - 6}" y="{y + cell * 0.7:.1f}" text-anchor="end">'
                   f"{html.escape(r)} ({html.escape(p.languages.get(r, ''))})</text>")
        for j, s in enumerate(subs):
            c = p.cells[(r, s)]
            x = lab_w + j * cell
            if not np.isfinite(c.composite):
                out.append(f'<rect class="diag" x="{x + 1}" y="{y + 1}" width="{cell - 2}" height="{cell - 2}" rx="2" '
                           f'data-tip="{html.escape(f"{r} · {s}: too few functions ({c.n} vs {c.n_ref})")}"/>')
                continue
            tip = (f"{r} · {s}: distance {c.composite:.2f} · {c.n} functions vs {c.n_ref} · "
                   f"drift: {_drift_text(c)} (population IQRs)")
            out.append(f'<rect fill="{_color(scale.score(c.composite))}" x="{x + 1}" y="{y + 1}" width="{cell - 2}" '
                       f'height="{cell - 2}" rx="2" data-tip="{html.escape(tip)}"/>')
    for j, s in enumerate(subs):
        x = lab_w + j * cell + cell * 0.7
        out.append(f'<text transform="translate({x:.1f},{len(repos) * cell + 6}) rotate(60)">{html.escape(s)}</text>')
    out.append("</svg>")

    lang_rows = "".join(
        f"<tr><th scope=row>{html.escape(r['language'])}</th><td class=num>{len(r['repositories'])}</td>"
        f"<td class=num>{r['cells']}</td><td class=num>{r['median_distance']:.2f}</td>"
        f"<td>{html.escape(', '.join(r['common_drift']))}</td>"
        f"<td>{html.escape(', '.join(r['repositories']))}</td></tr>" for r in p.by_language())
    cand = p.candidates()[:20]
    cand_rows = "".join(
        f"<tr><th scope=row>{html.escape(c.repo)}</th><td>{html.escape(p.languages.get(c.repo, ''))}</td>"
        f"<td>{html.escape(c.subsystem)}</td><td class=num>{c.composite:.2f}</td>"
        f"<td class=num>{100 * p.calls_kept.get(c.repo, 0):.0f}%</td><td>{html.escape(_drift_text(c))}</td></tr>"
        for c in cand)
    cand_html = ("" if not cand else
                 "<h3>Calibration candidates</h3><p class=note>Cells where a port in another language kept the "
                 f"reference's wiring (calls kept ≥ {100 * p.faithful:.0f}%) yet the subsystem sits in the cohort's "
                 "most distant quarter. Either the port changed that subsystem, or the engine measures that language "
                 "differently there; the drift says which features to check.</p>"
                 "<div class=tablewrap><table><thead><tr><th>Repository</th><th>Language</th><th>Subsystem</th>"
                 "<th class=num>Distance</th><th class=num>Calls kept</th><th>Drift (population IQRs)</th></tr></thead>"
                 f"<tbody>{cand_rows}</tbody></table></div>")
    return ("<section><h2>Subsystems across repositories</h2><p class=note>Each cell compares a repository's "
            f"functions in one subsystem with {html.escape(p.reference)}'s functions in the same subsystem "
            "(archetype mix, LOC-weighted centre, and the whole distribution of function coordinates), in the "
            f"reference frame. Cells need {p.min_functions} functions on both sides. Hover a cell for the features "
            "that drifted most.</p>"
            f"{_legend(scale)}<div class=fig>{''.join(out)}</div>"
            f"<h3>By language</h3><p class=note>Repositories that kept the reference's wiring (calls kept ≥ "
            f"{100 * p.faithful:.0f}%), so the algorithm is the same. A language whose subsystems sit far from the "
            "reference although the algorithm did not change is where the engine's measurements are least comparable "
            "across languages.</p><div class=tablewrap><table><thead><tr><th>Language</th>"
            "<th class=num>Repositories</th><th class=num>Cells</th><th class=num>Median distance</th>"
            f"<th>Most common drift</th><th>Repositories</th></tr></thead><tbody>{lang_rows}</tbody></table></div>"
            f"{cand_html}</section>")
