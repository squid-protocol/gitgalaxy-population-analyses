"""Every number in README.md: a structural profile of the paired agentic-COBOL systems, from GitGalaxy scans.

    python measure.py --repos WORK/repos --scans WORK/scans --out data/

Per system: language mix, source format, paragraph naming case, and over COBOL functions (paragraphs, sections
and -- since GitGalaxy #7170 -- each program's main line, `def_shape` 'main_line') the size, branching, rates
of state mutation and I/O per 100 lines, call-graph shape, and the most-called paragraphs. Then, per measure,
in how many pairs each agent's system reads higher. Measurements and paragraph names only; no source text.
"""

import argparse
import collections
import json
import re
import sqlite3
import statistics
from pathlib import Path

PAIRS = {  # family -> (Claude Code repo, Codex repo); every repo is acherm/<name>, MIT
    "chess engine": ("agentic-chessengine-cobol-cc", "agentic-chessengine-cobol-codex"),
    "compressor": ("agentic-cobol-compress-cc", "agentic-cobol-compress"),
    "DOOM-like game": ("agentic-cobol-doom-cc", "agentic-cobol-doom-codex"),
    "pygame-style framework": ("agentic-cobol-pygame-cc", "agentic-cobol-pygame"),
    "SAT solver": ("agentic-cobol-sat-cc", "agentic-cobol-sat-codex"),
}
NON_CODE = {"markdown", "json", "yaml", "xml", "html", "css", "text", "unknown", "makefile", "cmake", "toml", "ini", "csv"}
COBOL_EXT = {".cob", ".cbl", ".cpy"}
FREE = re.compile(r">>\s*SOURCE\s+(FORMAT\s+)?(IS\s+)?FREE|\s-free\b", re.I)
MIN_LOC = 3  # as the structural fingerprint scanner's default: one- and two-line units are left out
MEASURES = ["cobol_share", "main_line_share", "functions", "loc_median", "complexity_median", "complexity_ge10_pct",
            "state_mutation_per100", "io_per100", "fan_out_mean", "top5pct_hub_share"]


def scan_db(scans: Path, repo: str) -> Path:
    dbs = list((scans / repo).glob("*_galaxy_master.db"))
    if not dbs:
        raise SystemExit(f"no scan for {repo} under {scans}")
    return dbs[0]


def per100(total: float, loc: int) -> float | None:
    return round(100.0 * total / loc, 2) if loc else None


def profile(repos: Path, scans: Path, repo: str) -> dict:
    con = sqlite3.connect(f"file:{scan_db(scans, repo)}?mode=ro", uri=True)
    langs = {lang: int(loc) for lang, loc in con.execute(
        "SELECT lower(language), sum(coding_loc) FROM file_data GROUP BY 1") if lang and lang not in NON_CODE and loc}
    rows = con.execute(
        "SELECT f.func_name, f.loc, f.complexity, coalesce(f.def_shape, ''), coalesce(f.func_fan_in, 0),"
        " coalesce(f.func_fan_out, 0), coalesce(f.state_flux, 0), coalesce(f.arch_io, 0)"
        " FROM function_data f JOIN file_data d ON d.id = f.file_id"
        " WHERE lower(d.language) = 'cobol' AND f.loc >= ?", (MIN_LOC,)
    ).fetchall()
    con.close()
    if not rows:
        return {"repo": repo, "languages": langs, "functions": 0}
    paras = [r for r in rows if r[3] != "main_line"]
    mains = [r for r in rows if r[3] == "main_line"]
    loc = [r[1] for r in rows]
    cx = [r[2] or 0 for r in rows]
    fin = sorted((r[4] for r in rows), reverse=True)
    top = max(1, round(0.05 * len(rows)))
    lines = sum(loc)
    root = repos / repo
    sources = [p for p in root.rglob("*") if p.is_file() and ".gitgalaxy" not in p.parts]
    build = [p for p in sources if p.name.lower() in {"makefile", "build.sh"} or p.suffix.lower() in {".sh", ".mk"}]
    free = any(FREE.search(p.read_text(errors="replace")) for p in build + [p for p in sources if p.suffix.lower() in COBOL_EXT])
    return {
        "repo": repo,
        "languages": langs,
        "cobol_share": round(langs.get("cobol", 0) / sum(langs.values()), 3) if langs else None,
        "free_format": free,
        "functions": len(rows),
        "paragraphs": len(paras),
        "main_lines": len(mains),
        "main_line_share": round(sum(r[1] for r in mains) / lines, 3),
        "lowercase_paragraph_names_pct": round(100.0 * sum(1 for r in paras if r[0] != r[0].upper()) / len(paras), 1) if paras else None,
        "loc_median": statistics.median(loc),
        "complexity_median": statistics.median(cx),
        "complexity_ge10_pct": round(100.0 * sum(c >= 10 for c in cx) / len(rows), 1),
        "state_mutation_per100": per100(sum(r[6] for r in rows), lines),
        "io_per100": per100(sum(r[7] for r in rows), lines),
        "fan_out_mean": round(sum(r[5] for r in rows) / len(rows), 2),
        "top5pct_hub_share": round(sum(fin[:top]) / sum(fin), 3) if sum(fin) else None,
        "hubs": [{"name": r[0], "fan_in": r[4], "loc": r[1]} for r in sorted(paras, key=lambda r: -r[4])[:3]],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repos", type=Path, required=True, help="directory holding one checkout per repo")
    ap.add_argument("--scans", type=Path, required=True, help="directory holding one GitGalaxy scan per repo")
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "data")
    a = ap.parse_args()
    families, lean = [], {m: collections.Counter() for m in MEASURES}
    for fam, (cc, cx) in PAIRS.items():
        p_cc, p_cx = profile(a.repos, a.scans, cc), profile(a.repos, a.scans, cx)
        families.append({"family": fam, "claude_code": p_cc, "codex": p_cx})
        for m in MEASURES:
            x, y = p_cc.get(m), p_cx.get(m)
            if x is not None and y is not None:
                lean[m]["claude_code" if x > y else "codex" if y > x else "tie"] += 1
    a.out.mkdir(parents=True, exist_ok=True)
    result = {"min_loc": MIN_LOC, "families": families, "higher_in_pairs": {m: dict(c) for m, c in lean.items()}}
    (a.out / "profile.json").write_text(json.dumps(result, indent=1) + "\n")
    for f in families:
        for agent in ("claude_code", "codex"):
            p = f[agent]
            print(f"{f['family']:24}{agent:12} COBOL {100 * p['cobol_share']:3.0f}%  main {100 * p['main_line_share']:3.0f}%  "
                  f"paras {p['paragraphs']:3}  free {str(p['free_format']):5}  lower {p['lowercase_paragraph_names_pct']:5.1f}%  "
                  f"med {p['loc_median']:4}  cx {p['complexity_median']:3}  hub {p['top5pct_hub_share']}")
    for m, c in result["higher_in_pairs"].items():
        print(f"  {m:24} " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())))


if __name__ == "__main__":
    main()
