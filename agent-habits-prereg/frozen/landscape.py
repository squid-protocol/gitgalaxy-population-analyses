"""Landscape of the agentic chess engines (acherm/agentic-chessengine-*, MIT): one structural profile per repo, from
GitGalaxy scans (engine main 433228fe1), and the same-language Claude Code vs Codex pairs side by side.

    python landscape.py            # writes landscape.json and prints the tables

Measurements and function names only; no source text. Cells the scan-quality appraisal (compare/) found
unreliable are carried in FLAGS and printed with the profile.
"""

import json
import sqlite3
import statistics
from pathlib import Path

BASE = Path("/home/joe/gitgalaxy/chess-study")
NON_CODE = {"markdown", "json", "yaml", "xml", "html", "css", "text", "unknown", "makefile", "cmake", "toml", "ini",
            "csv", "plaintext", "restructuredtext", "dockerfile", "gitignore", "license", "svg"}
MIN_LOC = 3
SCANS = BASE / "scans"
RISKS = ["cognitive_load", "safety_score", "tech_debt", "verification", "api_exposure", "concurrency", "state_flux",
         "dead_code", "documentation"]
# Same task, same language, the two agents (Claude Code `-cc`, Codex `-codex`).
PAIRS = {
    "C": ("agentic-chessengine-c-cc", "agentic-chessengine-c-codex"),
    "C++": ("agentic-chessengine-cpp-cc", "agentic-chessengine-cpp-codex"),
    "Java": ("agentic-chessengine-java-cc", "agentic-chessengine-java-codex"),
    "Python": ("agentic-chessengine-python-cc", "agentic-chessengine-python-codex"),
    "Ruby": ("agentic-chessengine-ruby-cc", "agentic-chessengine-ruby-codex"),
    "Rust": ("agentic-chessengine-rust-cc", "agentic-chessengine-rust-codex"),
    "COBOL": ("agentic-chessengine-cobol-cc", "agentic-chessengine-cobol-codex"),
    "Why3": ("agentic-chessengine-why3-cc", "agentic-chessengine-why3-codex"),
}
FLAGS = {
    "agentic-chessengine-ruby-codex": "Ruby `x << CONST` read as a heredoc: position.rb parse_board swallows 26 functions",
    "agentic-chessengine-why3-cc": "OCaml/WhyML not scanned (no profile)",
    "agentic-chessengine-why3-codex": "OCaml/WhyML not scanned (no profile)",
    "agentic-chessengine-lean-codex": "Lean not scanned",
    "agentic-chessengine-mojo-codexfailure": "Mojo not scanned",
    "agentic-chessengine-latex-TeXCCChess": "TeX not scanned",
    "agentic-chessengine-latex-codex-replication": "TeX not scanned",
    "agentic-chessengine-icon-codex": "Icon: no reference tool",
    "agentic-chessengine-brainfuck-codexfailure": "Brainfuck: no reference tool",
    "agentic-chessengine-dsl-newlang-codex": ".gmb DSL: no reference tool",
    "agentic-chessengine-css-codex-guided": "index.html excluded as packed payload",
    "agentic-chessengine-cpp-cc": "C++ call recall 58% vs libclang: fan-out undercounted",
    "agentic-chessengine-cpp-codex": "C++ call recall 58% vs libclang: fan-out undercounted",
}


def profile(repo: str) -> dict:
    db = next((SCANS / repo).glob("*_galaxy_master.db"))
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    langs = {}
    for lang, loc in con.execute("SELECT lower(language), sum(coding_loc) FROM file_data GROUP BY 1"):
        if lang and loc:
            langs[lang] = int(loc)
    code = {k: v for k, v in langs.items() if k not in NON_CODE}
    code_loc = sum(code.values())
    primary = max(code, key=code.get) if code else (max(langs, key=langs.get) if langs else None)
    files = con.execute(
        "SELECT lower(language), coding_loc, doc_loc, " + ", ".join(f"coalesce(risk_{r}, 0)" for r in RISKS)
        + ", coalesce(fam_tests, 0) FROM file_data"
    ).fetchall()
    cf = [f for f in files if f[0] in code and (f[1] or 0) > 0]
    w = sum(f[1] for f in cf)
    risks = {r: round(sum(f[1] * f[3 + i] for f in cf) / w, 1) if w else None for i, r in enumerate(RISKS)}
    doc_ratio = round(sum(f[2] or 0 for f in cf) / w, 3) if w else None
    rows = con.execute(
        "SELECT f.func_name, f.loc, coalesce(f.complexity, 0), coalesce(f.func_fan_in, 0), coalesce(f.func_fan_out, 0),"
        " coalesce(f.args, 0), coalesce(f.def_shape, ''), lower(d.language), d.file_path"
        " FROM function_data f JOIN file_data d ON d.id = f.file_id WHERE f.loc >= ?", (MIN_LOC,)
    ).fetchall()
    rows = [r for r in rows if r[7] in code]
    test_rows = [r for r in rows if "test" in (r[8] or "").lower() or r[0].lower().startswith("test")]
    repo_row = con.execute(
        "SELECT total_files, total_test_files, network_modularity, network_cyclic_density, total_classes FROM repo_data"
    ).fetchone() or (None,) * 5
    con.close()
    p = {"repo": repo, "primary": primary, "languages": code, "code_loc": code_loc, "files": repo_row[0],
         "test_files": repo_row[1], "classes": repo_row[4], "functions": len(rows),
         "test_function_share": round(len(test_rows) / len(rows), 3) if rows else None,
         "doc_per_code_line": doc_ratio, "risk": risks,
         "modularity": repo_row[2], "cyclic_density": repo_row[3], "flag": FLAGS.get(repo)}
    if rows:
        loc = [r[1] for r in rows]
        cx = [r[2] for r in rows]
        fin = sorted((r[3] for r in rows), reverse=True)
        top = max(1, round(0.05 * len(rows)))
        p.update({
            "loc_median": statistics.median(loc), "loc_max": max(loc),
            "complexity_median": statistics.median(cx), "complexity_ge10_pct": round(100 * sum(c >= 10 for c in cx) / len(rows), 1),
            "args_mean": round(statistics.mean(r[5] for r in rows), 2),
            "fan_out_mean": round(statistics.mean(r[4] for r in rows), 2),
            "top5pct_hub_share": round(sum(fin[:top]) / sum(fin), 3) if sum(fin) else None,
            "functions_per_kloc": round(1000 * len(rows) / code_loc, 1) if code_loc else None,
            "hubs": [{"name": r[0], "fan_in": r[3]} for r in sorted(rows, key=lambda r: -r[3])[:3]],
        })
    return p


def main() -> None:
    repos = sorted(d.name for d in (BASE / "scans").iterdir() if d.is_dir())
    profiles = {r: profile(r) for r in repos}
    cols = ["code_loc", "functions", "functions_per_kloc", "loc_median", "complexity_median", "complexity_ge10_pct",
            "fan_out_mean", "top5pct_hub_share", "test_function_share", "doc_per_code_line"]
    pairs, lean = [], {c: {"claude_code": 0, "codex": 0, "tie": 0} for c in cols + [f"risk_{r}" for r in RISKS]}
    for fam, (cc, cx) in PAIRS.items():
        a, b = profiles[cc], profiles[cx]
        trusted = not (a["flag"] or b["flag"]) or fam == "C++"
        pairs.append({"language": fam, "claude_code": cc, "codex": cx, "trusted": trusted})
        if not trusted or not a["functions"] or not b["functions"]:
            continue
        for c in cols:
            x, y = a.get(c), b.get(c)
            if x is not None and y is not None:
                lean[c]["claude_code" if x > y else "codex" if y > x else "tie"] += 1
        for r in RISKS:
            x, y = a["risk"][r], b["risk"][r]
            if x is not None and y is not None:
                lean[f"risk_{r}"]["claude_code" if x > y else "codex" if y > x else "tie"] += 1
    out = {"engine": (BASE / "engine.sha").read_text().strip(), "min_loc": MIN_LOC, "profiles": profiles,
           "pairs": pairs, "higher_in_trusted_pairs": lean}
    (BASE / "landscape.json").write_text(json.dumps(out, indent=1) + "\n")
    hdr = f"{'repo':44}{'primary':11}{'kLOC':>6}{'fns':>6}{'f/kL':>6}{'medL':>5}{'medCx':>6}{'cx10%':>6}{'fout':>6}{'hub':>6}{'test':>6}{'doc':>6}"
    print(hdr)
    for r, p in profiles.items():
        g = p.get
        print(f"{r.replace('agentic-chessengine-', ''):44}{str(p['primary'])[:10]:11}{p['code_loc'] / 1000:6.1f}{p['functions']:6}"
              f"{str(g('functions_per_kloc', '-')):>6}{str(g('loc_median', '-')):>5}{str(g('complexity_median', '-')):>6}"
              f"{str(g('complexity_ge10_pct', '-')):>6}{str(g('fan_out_mean', '-')):>6}{str(g('top5pct_hub_share', '-')):>6}"
              f"{str(g('test_function_share', '-')):>6}{str(g('doc_per_code_line', '-')):>6}" + (f"   ! {p['flag']}" if p["flag"] else ""))
    print("\nrisk surfaces (LOC-weighted %)")
    print(f"{'repo':44}" + "".join(f"{r[:8]:>9}" for r in RISKS))
    for r, p in profiles.items():
        print(f"{r.replace('agentic-chessengine-', ''):44}" + "".join(f"{str(p['risk'][k]):>9}" for k in RISKS))
    print("\nhigher in trusted pairs:", [p["language"] for p in pairs if p["trusted"]])
    for c, v in lean.items():
        print(f"  {c:26} claude_code {v['claude_code']}  codex {v['codex']}  tie {v['tie']}")


if __name__ == "__main__":
    main()
