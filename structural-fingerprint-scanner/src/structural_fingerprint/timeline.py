"""Drift timelines: fingerprint a repository at points in its history and follow how
far it drifts from a reference, and how fast it turns over.

For each repository, snapshots are taken on its first-parent history at a fixed step
(``--every 1y``, ``6m`` …) plus the current head. Each snapshot is exported with
``git archive`` (the working tree is never touched), scanned with the GitGalaxy engine,
fingerprinted in the reference's frame, and cached by commit SHA, so a re-run or a
longer history only scans what is missing. Scans are deleted after fingerprinting
unless ``--keep-scans``.

Twins against the reference use one distance threshold per repository and direction,
chosen by target-decoy competition over the candidates of all its snapshots together:
one yardstick for the whole series, with the power a single small pair lacks.

Per snapshot, against the **reference**: the share of the reference's functions linked
to a structural twin in the snapshot in either direction (*reference survival*; both
directions, so a tree that carries a function more than once still counts it), the snapshot's share with a
twin in the reference, shared structure (Wilson lower bound), the absolute component
distances of §4 of the method, and, with a taxonomy, the subway wiring scores (*calls
kept*, *wiring*). Against the **previous snapshot**: *retention*, the share of the
previous snapshot's functions that still have a twin, which shows bursts of rewriting.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .compare import COMPONENTS, component_distances
from .fingerprint import Fingerprint, FunctionTable, build
from .lineage import wilson_lower
from .reference import load_reference
from .scan_io import DB_SUFFIX, load_scan
from .twins import TwinParams, TwinResult, accept, find_twins, pooled_threshold, search

log = logging.getLogger(__name__)

# Categorical series colours (validated reference palette, light / dark), fixed order.
SERIES = [("#2a78d6", "#3987e5"), ("#eb6834", "#d95926"), ("#1baf7a", "#199e70"), ("#eda100", "#c98500"),
          ("#e87ba4", "#d55181"), ("#008300", "#008300"), ("#6250d6", "#9085e9"), ("#e34948", "#e66767")]


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)} in {repo}: {r.stderr.strip()}")
    return r.stdout.strip()


def _months(every: str) -> int:
    every = every.strip().lower()
    n, unit = int(every[:-1]), every[-1]
    if unit == "y":
        return 12 * n
    if unit == "m":
        return n
    raise ValueError(f"--every takes Ny or Nm (e.g. 1y, 6m), not {every!r}")


def _add_months(d: dt.date, m: int) -> dt.date:
    y, mo = divmod(d.month - 1 + m, 12)
    return dt.date(d.year + y, mo + 1, min(d.day, 28))


def plan_snapshots(repo: Path, every: str = "1y", since: str | None = None, until: str | None = None,
                   branch: str = "HEAD") -> list[tuple[str, str]]:
    """(date, sha) pairs on the first-parent history, one per step, plus the head."""
    first = _git(repo, "log", "--first-parent", "--reverse", "--format=%cs", branch).splitlines()
    if not first:
        raise RuntimeError(f"{repo}: no history on {branch}")
    if _git(repo, "rev-parse", "--is-shallow-repository") == "true":
        raise RuntimeError(f"{repo} is a shallow clone; a timeline needs its history (git fetch --unshallow)")
    start = dt.date.fromisoformat(since or first[0])
    head_sha = _git(repo, "rev-parse", branch)
    head_date = dt.date.fromisoformat(_git(repo, "log", "-1", "--format=%cs", branch))
    end = dt.date.fromisoformat(until) if until else head_date
    step = _months(every)
    out: list[tuple[str, str]] = []
    d = start
    while d <= end:
        sha = _git(repo, "rev-list", "-1", "--first-parent", f"--before={d.isoformat()} 23:59:59", branch)
        if sha and (not out or out[-1][1] != sha):
            out.append((_git(repo, "log", "-1", "--format=%cs", sha), sha))
        d = _add_months(d, step)
    if not until and (not out or out[-1][1] != head_sha):
        out.append((head_date.isoformat(), head_sha))
    return out


@dataclass
class Scanner:
    """Runs the GitGalaxy engine on a directory, as the DOOM harness does."""

    engine: Path
    python: str = sys.executable

    def scan(self, src: Path, out: Path) -> Path:
        out.mkdir(parents=True, exist_ok=True)
        cmd = [self.python, "-m", "gitgalaxy.galaxyscope", str(src), "--output", str(out) + "/"]
        heavy = self.engine / "tests" / "tools" / "box" / "heavy-run.sh"
        if heavy.exists() and shutil.which("flock"):
            cmd = [str(heavy), *cmd]
        env = dict(os.environ, PYTHONPATH=str(self.engine),
                   GITGALAXY_LICENSE_KEY=os.environ.get("GITGALAXY_LICENSE_KEY", "COMMUNITY_FREE_TIER"))
        with open(out / "scan.log", "w") as fh:
            rc = subprocess.run(cmd, cwd=out, env=env, stdout=fh, stderr=subprocess.STDOUT, check=False).returncode
        dbs = sorted(out.glob(f"*{DB_SUFFIX}"))
        if rc or not dbs:
            raise RuntimeError(f"scan of {src} failed (rc {rc}); see {out / 'scan.log'}")
        return dbs[0]


def snapshot_fingerprint(repo: Path, name: str, date: str, sha: str, cache: Path, scanner: Scanner, lens: str,
                         min_loc: int, keep_scans: bool = False) -> Fingerprint:
    tag = f"{name}@{date}"
    # Keyed by commit alone: forks share their parent's history (Crispy Doom's commits before
    # 2014 are Chocolate Doom's), so a snapshot is scanned once for every repository that has it.
    stem = cache / "snapshots" / f"{sha[:12]}"
    if stem.with_suffix(".sfp.json").is_file():
        fp = Fingerprint.load(stem.with_suffix(".sfp.json"))
        if fp.data["spec"]["lens"] == lens and fp.data["spec"]["min_loc"] == min_loc:
            return fp
    work = cache / "_work" / f"{name}-{sha[:12]}"
    shutil.rmtree(work, ignore_errors=True)
    src = work / name  # the scan takes its repository name from this directory
    src.mkdir(parents=True)
    archive = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", sha], capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", str(src)], input=archive.stdout, check=True)
    try:
        db = scanner.scan(src, work / "scan")
        ref = load_reference(lens)
        fp = build(load_scan(db, ref.signal_columns, name=tag), ref, min_loc=min_loc)
        fp.data["source"].update({"commit": sha, "commit_date": date, "repository": str(repo)})
        stem.parent.mkdir(parents=True, exist_ok=True)
        json_path = fp.save(stem.parent)
        # Fingerprint.save names files after the fingerprint; rename to the commit for the cache.
        json_path.rename(stem.with_suffix(".sfp.json"))
        json_path.with_name(json_path.name.removesuffix(".sfp.json") + ".sfp.npz").rename(stem.with_suffix(".sfp.npz"))
    finally:
        if not keep_scans:
            shutil.rmtree(work, ignore_errors=True)
    return fp


def _kept(old: FunctionTable, fwd: TwinResult, back: TwinResult, min_loc: int) -> float:
    """Share of ``old``'s eligible functions linked to a twin in either direction. Both
    directions count: a tree that carries a function more than once (Chocolate Doom adding
    Heretic, Hexen and Strife beside Doom) fails the old-side ratio test, while each copy
    still finds the original."""
    from .subway import twinned

    eligible = old.loc >= min_loc
    return float(twinned(len(old), fwd, back)[eligible].mean()) if eligible.any() else float("nan")


def measure(snap: Fingerprint, ref: Fingerprint, prev: Fingerprint | None, params: TwinParams,
            taxonomy=None, ref_results: tuple[TwinResult, TwinResult] | None = None) -> dict:
    """``ref_results``: the (reference -> snapshot, snapshot -> reference) twins, accepted with
    the repository's pooled threshold; computed per pair when not given."""
    rt, st = ref.functions, snap.functions
    fwd, back = ref_results or (find_twins(rt, st, params), find_twins(st, rt, params))
    ref_survival, r_in_s, s_in_r = _kept(rt, fwd, back, params.min_loc), fwd.stats, back.stats
    lb = max(float(wilson_lower(np.array([r_in_s["twins"]]), np.array([r_in_s["eligible"]]))[0]),
             float(wilson_lower(np.array([s_in_r["twins"]]), np.array([s_in_r["eligible"]]))[0]))
    row = {
        "functions": snap.data["size"]["functions"],
        "coding_loc": snap.data["size"]["coding_loc"],
        "reference_survival": ref_survival,
        "survival_in_reference": s_in_r["survival"],
        "shared_structure": lb,
        **{f"distance_{k}": v for k, v in component_distances(ref, snap).items()},
        "retention": None,
        "calls_kept": None,
        "wiring": None,
    }
    if prev is not None:
        pt = prev.functions
        row["retention"] = _kept(pt, find_twins(pt, st, params), find_twins(st, pt, params), params.min_loc)
    if taxonomy is not None:
        from .subway import build_maps

        maps, _, _ = build_maps([rt, st], rt.repo, taxonomy, params)
        row["calls_kept"] = float(maps[1].edges_kept) if np.isfinite(maps[1].edges_kept) else None
        row["wiring"] = float(maps[1].wiring_similarity) if np.isfinite(maps[1].wiring_similarity) else None
    return row


def run(repos: list[tuple[str, Path]], ref: Fingerprint, out: Path, scanner: Scanner, every: str = "1y",
        since: str | None = None, until: str | None = None, params: TwinParams | None = None, taxonomy=None,
        keep_scans: bool = False, thresholds: dict | None = None) -> list[dict]:
    """Rows per snapshot. Twins against the reference use one threshold per repository and
    direction, pooled over all its snapshots (recorded in ``thresholds`` when a dict is
    passed): a small overlap with the reference otherwise sits at the edge of what one
    pair can certify, and the per-snapshot threshold flips between certified and not."""
    p = params or TwinParams()
    lens, min_loc = ref.data["spec"]["lens"], ref.data["spec"]["min_loc"]
    cache = out / "cache"
    rt = ref.functions
    rows: list[dict] = []
    for name, path in repos:
        plan = plan_snapshots(path, every, since, until)
        log.info("%s: %d snapshots", name, len(plan))
        snaps = []
        for k, (date, sha) in enumerate(plan, 1):
            log.info("%s %s (%s) [%d/%d]", name, date, sha[:9], k, len(plan))
            try:
                fp = snapshot_fingerprint(path, name, date, sha, cache, scanner, lens, min_loc, keep_scans)
            except (RuntimeError, subprocess.CalledProcessError) as e:
                log.warning("%s %s: skipped (%s)", name, date, e)
                continue
            if fp.functions is None or not len(fp.functions):
                log.warning("%s %s: no functions, skipped", name, date)
                continue
            snaps.append((date, sha, fp))
        if not snaps:
            continue
        fwd = [search(rt, fp.functions, p) for _, _, fp in snaps]
        back = [search(fp.functions, rt, p) for _, _, fp in snaps]
        t_fwd, _ = pooled_threshold(fwd, p.fdr)
        t_back, _ = pooled_threshold(back, p.fdr)
        if thresholds is not None:
            thresholds[name] = {"reference_to_snapshot": t_fwd, "snapshot_to_reference": t_back}
        prev = None
        for (date, sha, fp), sf, sb in zip(snaps, fwd, back, strict=True):
            res = (accept(sf, t_fwd), accept(sb, t_back))
            rows.append({"repo": name, "date": date, "commit": sha, **measure(fp, ref, prev, p, taxonomy, res)})
            prev = fp
    return rows


def write_outputs(out: Path, rows: list[dict], ref_name: str, meta: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "timeline.json").write_text(json.dumps({"reference": ref_name, **meta, "snapshots": rows}, indent=1) + "\n")
    cols = ["repo", "date", "commit", "functions", "coding_loc", "reference_survival", "survival_in_reference",
            "shared_structure", *(f"distance_{k}" for k in COMPONENTS), "retention", "calls_kept", "wiring"]
    with open(out / "timeline.csv", "w") as f:
        f.write(",".join(cols) + "\n")
        f.writelines(",".join("" if r.get(c) is None else (f"{r[c]:.6f}" if isinstance(r[c], float) else str(r[c]))
                             for c in cols) + "\n" for r in rows)


# ---------------------------------------------------------------- rendering

def _year(date: str) -> float:
    d = dt.date.fromisoformat(date)
    return d.year + (d.timetuple().tm_yday - 1) / 365.25


def _nice_ceiling(v: float) -> float:
    """Smallest round value (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8 x 10^k) at or above ``v``, for axis ticks."""
    if v <= 0:
        return 1.0
    k = 10 ** np.floor(np.log10(v))
    for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if m * k >= v:
            return float(m * k)
    return float(10 * k)


def shared_history(rows: list[dict]) -> list[tuple[str, str, str]]:
    """(a, b, last shared date) for repositories whose snapshot series start with the same
    commits, e.g. a fork that carries its parent's history."""
    by: dict[str, list[tuple[str, str]]] = {}
    for r in rows:
        by.setdefault(r["repo"], []).append((r["date"], r["commit"]))
    names, out = list(by), []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            last = None
            for (d1, c1), (_, c2) in zip(by[a], by[b], strict=False):
                if c1 != c2:
                    break
                last = d1
            if last:
                out.append((a, b, last))
    return out


def line_chart(series: dict[str, list[tuple[str, float]]], title: str, ylabel: str, fmt, colours: dict[str, int],
               events: list[tuple[str, str]] | None = None, ymin: float | None = 0.0, ymax: float | None = None,
               w: int = 560, h: int = 300) -> str:
    pts = [(_year(d), v) for s in series.values() for d, v in s if v is not None and np.isfinite(v)]
    if not pts:
        return ""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1 = min(xs), max(xs)
    if x1 - x0 < 1:
        x0, x1 = x0 - 0.5, x1 + 0.5
    y0 = min(ys) if ymin is None else ymin
    y1 = _nice_ceiling(max(ys)) if ymax is None else ymax
    if y1 <= y0:
        y1 = y0 + 1
    pl, pr, pt, pb = 48, 96, 10, 34

    def sx(x):
        return pl + (x - x0) / (x1 - x0) * (w - pl - pr)

    def sy(y):
        return h - pb - (y - y0) / (y1 - y0) * (h - pt - pb)

    o = [f'<svg class="tl" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(title)}">']
    for t in np.linspace(y0, y1, 5):
        o.append(f'<line class="grid" x1="{pl}" x2="{w - pr}" y1="{sy(t):.1f}" y2="{sy(t):.1f}"/>'
                 f'<text x="{pl - 6}" y="{sy(t) + 4:.1f}" text-anchor="end">{html.escape(fmt(t))}</text>')
    for yr in range(int(np.ceil(x0)), int(x1) + 1, max(1, int((x1 - x0) // 8) or 1)):
        o.append(f'<text x="{sx(yr):.1f}" y="{h - pb + 16}" text-anchor="middle">{yr}</text>')
    for k, (d, label) in enumerate(sorted(events or [])):
        x = _year(d)
        if x0 <= x <= x1:
            # Alternate label rows so neighbouring events do not overprint.
            o.append(f'<line class="event" x1="{sx(x):.1f}" x2="{sx(x):.1f}" y1="{pt}" y2="{h - pb}"/>'
                     f'<text class="event" x="{sx(x) + 3:.1f}" y="{pt + 10 + 12 * (k % 2)}">{html.escape(label)}</text>')
    ends = []
    for name, s in series.items():
        c = colours[name]
        pts_s = [(_year(d), v, d) for d, v in s if v is not None and np.isfinite(v)]
        if not pts_s:
            continue
        o.append(f'<polyline class="s{c}" points="' + " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y, _ in pts_s) + '"/>')
        for x, y, d in pts_s:
            o.append(f'<circle class="s{c}" cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="4" '
                     f'data-tip="{html.escape(f"{name} · {d}: {fmt(y)}")}"/>')
        x, y, _ = pts_s[-1]
        ends.append([sy(y) + 4, sx(x) + 7, name])
    # End labels: keep at least 12px between neighbours, top to bottom.
    ends.sort()
    for k in range(1, len(ends)):
        ends[k][0] = max(ends[k][0], ends[k - 1][0] + 12)
    for ly, lx, name in ends:
        o.append(f'<text class="end" x="{lx:.1f}" y="{ly:.1f}">{html.escape(name)}</text>')
    o.append("</svg>")
    return f'<figure class="tlf"><figcaption>{html.escape(title)}<span>{html.escape(ylabel)}</span></figcaption>{"".join(o)}</figure>'


def render_section(rows: list[dict], ref_name: str, events: list[tuple[str, str]] | None = None) -> str:
    names = list(dict.fromkeys(r["repo"] for r in rows))
    colours = {n: i % len(SERIES) for i, n in enumerate(names)}

    def series(key: str) -> dict[str, list[tuple[str, float]]]:
        return {n: [(r["date"], r[key]) for r in rows if r["repo"] == n] for n in names}

    def pct(v: float) -> str:
        return f"{100 * v:.0f}%"

    charts = [
        line_chart(series("reference_survival"), f"How much of {ref_name} survives",
                   f"share of {ref_name}'s functions with a structural twin", pct, colours, events, 0, 1),
        line_chart(series("calls_kept"), f"{ref_name}'s calls still made", "calls kept (subway)", pct, colours,
                   events, 0, 1) if any(r["calls_kept"] is not None for r in rows) else "",
        line_chart(series("retention"), "Retention since the previous snapshot",
                   "share of the previous snapshot's functions still with a twin", pct, colours, events, 0, 1),
        line_chart(series("distance_centroid"), f"Design distance from {ref_name}",
                   "centroid distance (reference frame)", lambda v: f"{v:.2f}", colours, events, 0, None),
        line_chart(series("functions"), "Size", "functions", lambda v: f"{v:,.0f}", colours, events, 0, None),
    ]
    legend = "".join(f'<span class="item"><span class="sw s{colours[n]}"></span>{html.escape(n)}</span>' for n in names)
    css = "".join(f".tl .s{i}{{stroke:{lt};fill:{lt}}}.legend .sw.s{i}{{background:{lt}}}" for i, (lt, _) in enumerate(SERIES))
    dark = "".join(f".tl .s{i}{{stroke:{dk};fill:{dk}}}.legend .sw.s{i}{{background:{dk}}}" for i, (_, dk) in enumerate(SERIES))
    style = ("<style>.tl polyline{fill:none!important;stroke-width:2;stroke-linejoin:round}.tl circle{stroke:var(--surface);"
             "stroke-width:1.5}.tl text{fill:var(--text2);font-size:11px}.tl .end{font-size:11px;fill:var(--text)}"
             ".tl .grid{stroke:var(--rule)}.tl .event{stroke:var(--text2);stroke-dasharray:3 3}.tl text.event{stroke:none;"
             "fill:var(--text2)}.tlgrid{display:flex;flex-wrap:wrap;gap:12px 24px}.tlf{margin:0}.tlf figcaption{font-size:13px;"
             "font-weight:600;display:flex;flex-direction:column}.tlf figcaption span{font-weight:400;color:var(--text2);"
             "font-size:12px}.legend .item{display:inline-flex;align-items:center;gap:5px;margin-right:12px}"
             ".legend .sw{width:12px;height:12px;border-radius:50%;display:inline-block}"
             + css + "@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"]) " + dark.replace("}.", "}:root:not([data-theme=\"light\"]) .")
             + "}:root[data-theme=\"dark\"] " + dark.replace("}.", "}:root[data-theme=\"dark\"] .") + "</style>")
    table = "".join(
        f"<tr><th scope=row>{html.escape(r['repo'])}</th><td>{r['date']}</td><td><code>{r['commit'][:9]}</code></td>"
        f"<td class=num>{r['functions']:,}</td><td class=num>{pct(r['reference_survival'])}</td>"
        f"<td class=num>{'' if r['retention'] is None else pct(r['retention'])}</td>"
        f"<td class=num>{'' if r['calls_kept'] is None else pct(r['calls_kept'])}</td>"
        f"<td class=num>{r['distance_centroid']:.2f}</td></tr>" for r in rows)
    shared = "".join(f" {html.escape(a)} and {html.escape(b)} share their history up to {d}, so their lines coincide "
                     "until then." for a, b, d in shared_history(rows))
    return (f"{style}<section><h2>Drift over time</h2><p class=note>Each repository fingerprinted at points in its "
            f"history and compared with {html.escape(ref_name)}. Survival and retention use name-blind structural twins, "
            "with one threshold per repository calibrated over all its snapshots; calls kept uses the subway maps. "
            f"Dashed lines mark events.{shared}</p>"
            f'<div class="legend">{legend}</div><div class="tlgrid">{"".join(c for c in charts if c)}</div>'
            "<div class=tablewrap><table><thead><tr><th>Repository</th><th>Date</th><th>Commit</th>"
            "<th class=num>Functions</th><th class=num>Reference survival</th><th class=num>Retention</th>"
            f"<th class=num>Calls kept</th><th class=num>Design distance</th></tr></thead><tbody>{table}</tbody></table>"
            "</div></section>")


def read_events(path: Path) -> list[tuple[str, str]]:
    import csv

    with open(path, newline="") as f:
        return [(r["date"], r["label"]) for r in csv.DictReader(f) if r.get("date") and r.get("label")]
