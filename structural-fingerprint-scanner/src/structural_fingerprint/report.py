"""Write a cohort comparison to disk: Markdown, JSON, CSV, Newick and HTML."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np

from . import __version__
from .compare import COMPONENTS, Cohort
from .fingerprint import Fingerprint
from .lineage import DescentMatrix, upgma


def _write_matrix(path: Path, names: list[str], m: np.ndarray, fmt: str = "{:.6f}") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["", *names])
        for n, row in zip(names, m, strict=True):
            w.writerow([n, *("" if (isinstance(v, float) and math.isnan(v)) else fmt.format(v) for v in row)])


def _top(d: dict[str, float], k: int) -> list[tuple[str, float]]:
    return sorted(d.items(), key=lambda kv: -kv[1])[:k]


def _fmt_pct(x: float | None) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.1f}%"


def build_summary(fps: list[Fingerprint], cohort: Cohort, descent: DescentMatrix | None,
                  lineage_eval: dict | None) -> dict:
    names = cohort.names
    profile_nwk = upgma(cohort.composite, names)[0] if cohort.composite is not None else None
    descent_nwk = upgma(descent.distance, names)[0] if descent is not None else None
    repos = []
    for i, fp in enumerate(fps):
        d = fp.data
        entry = {
            "name": fp.name,
            "functions": d["size"]["functions"],
            "coding_loc": d["size"]["coding_loc"],
            "languages": list(d["size"]["languages_by_coding_loc"])[:3],
            "top_archetypes": _top(d["archetypes"]["count_share"], 3),
            "callgraph": d["callgraph"],
            "missing_signals": d["source"].get("missing_signals", []),
        }
        if cohort.composite is not None:
            order = [j for j in np.argsort(cohort.composite[i]) if j != i][:3]
            entry["nearest_by_profile"] = [(names[j], float(cohort.composite[i, j])) for j in order]
        if descent is not None:
            sh = descent.shared[i].copy()
            sh[i] = -1
            order = [j for j in np.argsort(-sh) if j != i][:3]
            entry["nearest_by_descent"] = [(names[j], float(sh[j])) for j in order]
        repos.append(entry)
    ref = fps[0].data["spec"]
    return {
        "tool": {"name": "structural-fingerprint-scanner", "version": __version__},
        "spec": ref,
        "cohort": names,
        "component_scales": cohort.scales,
        "component_weights": cohort.weights,
        "repositories": repos,
        "trees": {"profile": profile_nwk, "descent": descent_nwk},
        "lineage_evaluation": lineage_eval,
        "twin_params": None,
    }


def write_cohort(out: Path, fps: list[Fingerprint], cohort: Cohort, descent: DescentMatrix | None,
                 lineage_eval: dict | None, twin_params: dict | None, extra_sections: list[str] | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    names = cohort.names
    summary = build_summary(fps, cohort, descent, lineage_eval)
    summary["twin_params"] = twin_params

    for c in COMPONENTS:
        _write_matrix(out / "matrices" / f"component_{c}.csv", names, cohort.components[c])
    if cohort.composite is not None:
        _write_matrix(out / "matrices" / "profile_distance.csv", names, cohort.composite)
    if descent is not None:
        _write_matrix(out / "matrices" / "shared_structure.csv", names, descent.shared)
        _write_matrix(out / "matrices" / "survival.csv", names, descent.survival)
        _write_matrix(out / "matrices" / "survival_lower95.csv", names, descent.survival_lower)
        _write_matrix(out / "matrices" / "survival_loc.csv", names, descent.survival_loc)
        _write_matrix(out / "matrices" / "twins.csv", names, descent.twins.astype(float), "{:.0f}")
        _write_matrix(out / "matrices" / "exact_clones.csv", names, descent.exact.astype(float), "{:.0f}")
        _write_matrix(out / "matrices" / "name_agreement.csv", names, descent.name_agreement)

    with open(out / "pairs.csv", "w", newline="") as f:
        w = csv.writer(f)
        head = ["a", "b", *COMPONENTS]
        if cohort.composite is not None:
            head.append("profile_distance")
        if descent is not None:
            head += ["survival_a_in_b", "survival_b_in_a", "shared_structure", "twins_a_to_b", "exact_clones_a_to_b",
                     "name_agreement_a_to_b"]
        w.writerow(head)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                row = [names[i], names[j], *(f"{cohort.components[c][i, j]:.6f}" for c in COMPONENTS)]
                if cohort.composite is not None:
                    row.append(f"{cohort.composite[i, j]:.6f}")
                if descent is not None:
                    na = descent.name_agreement[i, j]
                    row += [f"{descent.survival[i, j]:.6f}", f"{descent.survival[j, i]:.6f}",
                            f"{descent.shared[i, j]:.6f}", int(descent.twins[i, j]), int(descent.exact[i, j]),
                            "" if math.isnan(na) else f"{na:.6f}"]
                w.writerow(row)

    trees = out / "trees"
    trees.mkdir(exist_ok=True)
    for k, nwk in summary["trees"].items():
        if nwk:
            (trees / f"{k}.nwk").write_text(nwk + "\n")
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    (out / "report.md").write_text(markdown(summary, cohort, descent))
    from .html import render_html  # local import keeps the CLI start-up light

    (out / "report.html").write_text(render_html(summary, fps, cohort, descent, extra_sections))
    return summary


def markdown(summary: dict, cohort: Cohort, descent: DescentMatrix | None) -> str:
    spec = summary["spec"]
    ref = spec["reference"]
    L = [
        "# Structural fingerprint report",
        "",
        (f"{len(summary['cohort'])} repositories · lens `{spec['lens']}` · spec `{spec['spec_hash']}` · "
         f"reference model from GitGalaxy `{ref.get('engine_commit', '')[:9]}` · "
         f"structural-fingerprint-scanner {summary['tool']['version']}"),
        "",
        "## Repositories",
        "",
        "| Repository | Functions | Coding LOC | Main languages | Leading archetypes | Nearest by profile | Nearest by descent |",
        "|---|---:|---:|---|---|---|---|",
    ]
    for r in summary["repositories"]:
        arch = ", ".join(f"{a} {100 * s:.0f}%" for a, s in r["top_archetypes"][:2])
        prof = ", ".join(f"{n} ({d:.2f})" for n, d in r.get("nearest_by_profile", [])[:2]) or "n/a"
        desc = ", ".join(f"{n} ({100 * s:.0f}%)" for n, s in r.get("nearest_by_descent", [])[:2]) or "n/a"
        L.append(f"| {r['name']} | {r['functions']:,} | {r['coding_loc']:,.0f} | {', '.join(r['languages'])} | "
                 f"{arch} | {prof} | {desc} |")
    L += ["", ("Profile distance: 1.0 is a typical pair in this cohort, lower is closer. Descent: share of functions "
               "with a calibrated structural twin (Wilson 95% lower bound, larger of the two directions)."), ""]

    ev = summary.get("lineage_evaluation")
    if ev:
        L += ["## Declared lineage check", ""]
        for basis, e in ev.items():
            if not e or not e.get("evaluated"):
                continue
            L.append(f"**{basis}**: nearest neighbour is declared family (ancestor, descendant, sibling or cousin) for "
                     f"{_fmt_pct(e['nearest_is_family'])} of {e['family_evaluated']} repositories. "
                     f"Of {e['evaluated']} with a declared parent in the cohort, the parent is the nearest "
                     f"non-descendant for {_fmt_pct(e['hit_at_1'])}, within the nearest three for "
                     f"{_fmt_pct(e['hit_at_3'])} (mean rank {e['mean_rank']:.2f}).")
            if e.get("undetectable"):
                L.append("")
                L.append(f"No detectable shared structure with any repository in the cohort: {', '.join(e['undetectable'])}.")
            L.append("")
            L.append("| Repository | Declared parent(s) | Rank | Nearest |")
            L.append("|---|---|---:|---|")
            for row in e["rows"]:
                L.append(f"| {row['name']} | {', '.join(row['declared_parents'])} | {row['rank']} | {row['nearest']} |")
            L.append("")

    if cohort.composite is not None:
        L += ["## Component scales", "",
              "Each component's distance is divided by its cohort median before averaging:", "",
              "| Component | Cohort median | Weight |", "|---|---:|---:|"]
        for c in COMPONENTS:
            L.append(f"| {c} | {cohort.scales.get(c, float('nan')):.4f} | {cohort.weights[c]:g} |")
        L.append("")
    if summary.get("twin_params"):
        tp = summary["twin_params"]
        L += ["## Twin search", "",
              (f"Reciprocal best hits in the lens space, ratio test {tp['ratio']}, functions of at least "
               f"{tp['min_loc']} lines, distance threshold per pair at an estimated false-twin rate of "
               f"{100 * tp['fdr']:.1f}% (archetype-stratified decoys, +1 corrected)."), ""]
    L += ["## Files", "",
          "- `summary.json`: everything above, machine-readable",
          "- `pairs.csv`: one row per pair, every distance",
          "- `matrices/`: square matrices (components, profile distance, survival, shared structure, twins)",
          "- `trees/`: Newick trees (`profile.nwk`, `descent.nwk`)",
          "- `fingerprints/`: one fingerprint per repository (`.sfp.json` + `.sfp.npz`)",
          "- `report.html`: this report with heatmaps and trees", ""]
    return "\n".join(L)
