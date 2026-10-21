"""Cross-check structural twins against an independent source-text verdict.

The scanner never reads source. An independent tool that does, such as the DOOM study's
``lineage.py`` in gitgalaxy, classifies every reference function in every port by
comparing normalized function bodies: ``exact`` (same token hash), ``near`` (token
similarity >= 0.9), ``derived`` (>= 0.6), ``name-only`` or ``gone``. This module takes
that verdict as ground truth and scores the scanner's name-blind twins against it,
function by function:

* a reference function **survives** by source text when its class is in ``positive``
  (default ``exact`` and ``near``);
* the scanner **predicts** survival when the function has a structural twin in the port
  in either direction (the same rule as subway survival);
* only reference functions of at least ``min_loc`` lines are scored (the twin search's
  floor), so both tools are judged on the same population.

The input is a CSV with columns ``variant`` (port), ``file`` and ``func`` (the reference
function's path and name, as in the scan) and ``cls`` (the class): ``lineage.py``'s
``survival_functions.csv``.
"""

from __future__ import annotations

import csv
import html
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from .fingerprint import FunctionTable
from .subway import SubwayMap

CLASSES = ("exact", "near", "derived", "name-only", "gone")


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    twins_by_class: Counter = field(default_factory=Counter)

    def add(self, truth: bool, pred: bool, cls: str) -> None:
        if pred:
            self.twins_by_class[cls] += 1
        if truth and pred:
            self.tp += 1
        elif pred:
            self.fp += 1
        elif truth:
            self.fn += 1
        else:
            self.tn += 1

    @property
    def n(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else float("nan")

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else float("nan")

    @property
    def predicted_rate(self) -> float:
        return (self.tp + self.fp) / self.n if self.n else float("nan")

    @property
    def true_rate(self) -> float:
        return (self.tp + self.fn) / self.n if self.n else float("nan")

    def to_dict(self) -> dict:
        return {"functions": self.n, "tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn,
                "precision": _f(self.precision), "recall": _f(self.recall),
                "scanner_survival": _f(self.predicted_rate), "source_survival": _f(self.true_rate),
                "twins_by_class": {c: self.twins_by_class.get(c, 0) for c in CLASSES}}


def _f(x: float) -> float | None:
    return None if not np.isfinite(x) else float(x)


@dataclass
class CrossCheck:
    reference: str
    positive: tuple[str, ...]
    min_loc: int
    per_port: dict[str, Counts]
    per_subsystem: dict[str, Counts]
    pooled: Counts
    unmatched_rows: int
    spearman: dict

    def to_dict(self) -> dict:
        return {"reference": self.reference, "positive": list(self.positive), "min_loc": self.min_loc,
                "pooled": self.pooled.to_dict(), "spearman_survival": self.spearman,
                "unmatched_rows": self.unmatched_rows,
                "per_port": {k: v.to_dict() for k, v in self.per_port.items()},
                "per_subsystem": {k: v.to_dict() for k, v in self.per_subsystem.items()}}


def read_verdicts(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    need = {"variant", "file", "func", "cls"}
    if rows and not need <= set(rows[0]):
        raise ValueError(f"{path}: needs columns {sorted(need)}; has {sorted(rows[0])}")
    return rows


def crosscheck(ref: FunctionTable, maps: list[SubwayMap], verdicts: list[dict],
               positive: tuple[str, ...] = ("exact", "near"), min_loc: int = 6) -> CrossCheck:
    index: dict[tuple[str, str], int] = {}
    for i, (p, n) in enumerate(zip(ref.path, ref.name, strict=True)):
        index.setdefault((str(p), str(n)), i)
    by_port = {m.repo: m for m in maps if m.ref_twinned is not None}
    per_port: dict[str, Counts] = defaultdict(Counts)
    per_sub: dict[str, Counts] = defaultdict(Counts)
    pooled = Counts()
    unmatched = 0
    for row in verdicts:
        m = by_port.get(row["variant"])
        if m is None:
            continue
        i = index.get((row["file"], row["func"]))
        if i is None:
            unmatched += 1
            continue
        if ref.loc[i] < min_loc:
            continue
        truth = row["cls"] in positive
        pred = bool(m.ref_twinned[i])
        for c in (per_port[m.repo], per_sub[row.get("subsystem") or "all"], pooled):
            c.add(truth, pred, row["cls"])
    pts = [(c.true_rate, c.predicted_rate) for c in per_port.values() if c.n]
    if len(pts) >= 4:
        r = spearmanr([p[0] for p in pts], [p[1] for p in pts])
        sp = {"n": len(pts), "rho": float(r.statistic), "p_value": float(r.pvalue)}
    else:
        sp = {"n": len(pts), "rho": None, "p_value": None}
    return CrossCheck(ref.repo, positive, min_loc, dict(per_port), dict(per_sub), pooled, unmatched, sp)


def write_csv(path: Path, cc: CrossCheck) -> None:
    with open(path, "w") as f:
        f.write("port,functions,tp,fp,fn,tn,precision,recall,scanner_survival,source_survival,"
                + ",".join(f"twins_{c}" for c in CLASSES) + "\n")
        for port, c in sorted(cc.per_port.items(), key=lambda kv: -kv[1].true_rate):
            d = c.to_dict()
            vals = ["" if d[k] is None else f"{d[k]:.4f}" for k in ("precision", "recall", "scanner_survival",
                                                                    "source_survival")]
            f.write(f"{port},{c.n},{c.tp},{c.fp},{c.fn},{c.tn}," + ",".join(vals) + ","
                    + ",".join(str(c.twins_by_class.get(k, 0)) for k in CLASSES) + "\n")


def render_section(cc: CrossCheck, source_name: str = "lineage.py") -> str:
    from .subway import scatter_svg

    def pct(x: float) -> str:
        return "n/a" if not np.isfinite(x) else f"{100 * x:.0f}%"

    p = cc.pooled
    tw = sum(p.twins_by_class.values()) or 1
    cls_rows = "".join(f"<tr><th scope=row>{c}</th><td class=num>{p.twins_by_class.get(c, 0):,}</td>"
                       f"<td class=num>{100 * p.twins_by_class.get(c, 0) / tw:.1f}%</td></tr>" for c in CLASSES)
    port_rows = "".join(
        f"<tr><th scope=row>{html.escape(k)}</th><td class=num>{c.n}</td><td class=num>{pct(c.true_rate)}</td>"
        f"<td class=num>{pct(c.predicted_rate)}</td><td class=num>{pct(c.precision)}</td>"
        f"<td class=num>{pct(c.recall)}</td></tr>"
        for k, c in sorted(cc.per_port.items(), key=lambda kv: -kv[1].true_rate))
    sub_rows = "".join(
        f"<tr><th scope=row>{html.escape(k)}</th><td class=num>{c.n}</td><td class=num>{pct(c.precision)}</td>"
        f"<td class=num>{pct(c.recall)}</td></tr>"
        for k, c in sorted(cc.per_subsystem.items(), key=lambda kv: -kv[1].n))
    sp = cc.spearman
    rho = "" if sp.get("rho") is None else (f" Across {sp['n']} ports, the two survival rates have Spearman ρ = "
                                            f"<strong>{sp['rho']:.2f}</strong> (p = {sp['p_value']:.2g}).")
    pos = " or ".join(cc.positive)
    scatter = scatter_svg([(k, c.true_rate, c.predicted_rate) for k, c in cc.per_port.items() if c.n],
                          f"source-text survival ({pos})", "scanner survival (structural twin)")
    return (f"<section><h2>Cross-check against source text</h2><p class=note>An independent source-text verdict "
            f"(<code>{html.escape(source_name)}</code>) classifies every {html.escape(cc.reference)} function in every "
            "port by comparing normalized function bodies. Counting a function as surviving when it is "
            f"<em>{html.escape(pos)}</em> there, the scanner's name-blind twins (functions of at least {cc.min_loc} lines) "
            f"have precision <strong>{pct(p.precision)}</strong> and recall <strong>{pct(p.recall)}</strong> over "
            f"{p.n:,} function × port pairs.{rho}</p>"
            f"{scatter}<div class=tb-grid><div><h3>What the twins are</h3><p class=note>Source-text class of every "
            "function the scanner called a twin.</p><div class=tablewrap><table><thead><tr><th>Class</th>"
            f"<th class=num>Twins</th><th class=num>Share</th></tr></thead><tbody>{cls_rows}</tbody></table></div>"
            "<h3>By subsystem</h3><div class=tablewrap><table><thead><tr><th>Subsystem</th><th class=num>Pairs</th>"
            "<th class=num>Precision</th><th class=num>Recall</th></tr></thead>"
            f"<tbody>{sub_rows}</tbody></table></div></div>"
            "<div><h3>By port</h3><div class=tablewrap><table><thead><tr><th>Port</th><th class=num>Functions</th>"
            "<th class=num>Source-text survival</th><th class=num>Scanner survival</th><th class=num>Precision</th>"
            f"<th class=num>Recall</th></tr></thead><tbody>{port_rows}</tbody></table></div></div></div></section>")
