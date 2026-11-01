"""Language-restricted differential signal scan. The sfs aggregates pool every language in a repo, and Codex ships
Python helpers in 5 of its 10 paired repos, so here each signal family is a density per 100 function LOC over the
functions of the PAIR'S language only (function_data signal columns, loc >= 3), Claude Code vs Codex, 10 pairs.
Also reports which other languages each side's functions are in. Writes signal_diff_lang.json.
"""

import json
import math
import sqlite3
import statistics

import landscape as L
import pooled

L.SCANS = L.BASE / "sfs-cohort"
LANG = {"chess / C": "c", "chess / C++": "cpp", "chess / Java": "java", "chess / Python": "python", "chess / Rust": "rust"}
SIGS = ["struct_branch", "struct_linear", "struct_args", "struct_closures", "struct_generics", "struct_comprehensions",
        "struct_decorators", "struct_class_start", "struct_macros", "def_safety", "state_safety_neg", "def_cleanup",
        "def_freeze_hits", "def_encapsulation", "def_test", "arch_io", "arch_api", "arch_globals", "arch_import",
        "arch_scientific", "arch_concurrency", "state_flux", "state_pointers", "state_memory_alloc", "state_print_hits",
        "state_cast_hits", "state_bailout_hits", "state_heat_triggers", "bitwise_ops"]


def dens(repo: str, lang: str) -> dict:
    db = next((L.SCANS / repo).glob("*_galaxy_master.db"))
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    r = con.execute("SELECT sum(f.loc), " + ", ".join(f"sum(coalesce(f.{s}, 0))" for s in SIGS)
                    + " FROM function_data f JOIN file_data d ON d.id = f.file_id WHERE lower(d.language) = ? AND f.loc >= 3",
                    (lang,)).fetchone()
    con.close()
    loc = r[0] or 1
    return {s: 100.0 * (v or 0) / loc for s, v in zip(SIGS, r[1:])}


def main() -> None:
    pairs = {fam: (dens(cc, LANG.get(fam, "cobol")), dens(cx, LANG.get(fam, "cobol"))) for fam, (cc, cx) in pooled.PAIRS.items()}
    out = []
    for s in SIGS:
        row = {"signal": s, "per_pair": {f: [round(a[s], 3), round(b[s], 3)] for f, (a, b) in pairs.items()}}
        for scope, keep in (("all", lambda f: True), ("chess_non_cobol", lambda f: f in LANG), ("cobol", lambda f: f not in LANG)):
            hc = hx = t = oc = ox = 0
            logs = []
            for f, (a, b) in pairs.items():
                if not keep(f):
                    continue
                x, y = a[s], b[s]
                if abs(x - y) < 1e-9:
                    t += 1
                elif x > y:
                    hc += 1
                else:
                    hx += 1
                oc += x > 0 and y == 0
                ox += y > 0 and x == 0
                if x or y:
                    logs.append(math.log2((x + 0.1) / (y + 0.1)))
            row[scope] = {"cc": hc, "codex": hx, "tie": t, "only_cc": oc, "only_codex": ox,
                          "p": round(pooled.sign_p(hc, hc + hx), 4), "log2": round(statistics.median(logs), 2) if logs else None}
        out.append(row)
    (L.BASE / "signal_diff_lang.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"{'signal':22}{'all CC/CX/tie':>15}{'p':>7}{'log2':>6}{'onlyCC/CX':>10}  {'mainstream':>11} {'cobol':>8}")
    for r in sorted(out, key=lambda r: (r["all"]["p"], -abs(r["all"]["log2"] or 0))):
        a, m, c = r["all"], r["chess_non_cobol"], r["cobol"]
        print(f"{r['signal']:22}{a['cc']:>6}/{a['codex']}/{a['tie']:<6}{a['p']:7.3f}{str(a['log2']):>6}{a['only_cc']:>6}/{a['only_codex']:<3}"
              f"  {m['cc']}/{m['codex']}/{m['tie']:<6}  {c['cc']}/{c['codex']}/{c['tie']}")


if __name__ == "__main__":
    main()
