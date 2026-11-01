"""Literal keyword differential, Claude Code vs Codex, 10 pooled pairs. Per pair: every reserved word / COBOL verb of the
pair's language counted in CODE only (comments and string literals blanked first), in that language's source files
only (generated/build output skipped). Rate per 1,000 keyword tokens. Reports per pair the keywords one side uses
(>= 2 times) and the other never does, and for COBOL (5 pairs) and across the 5 mainstream pairs the keywords that
lean the same way in most pairs. Measurements and keyword names only. Writes keyword_diff.json.
"""

import collections
import json
import math
import re
from pathlib import Path

import pooled

ROOTS = [Path("/home/joe/gitgalaxy/chess-study/repos"), Path("/home/joe/gitgalaxy/cobol-agents/repos")]
SKIP_DIRS = {"target", "build", "out", "node_modules", ".git", "__pycache__", "dist", "generated", "gen"}
EXT = {"c": {".c", ".h"}, "cpp": {".cpp", ".cc", ".cxx", ".hpp", ".hh", ".h"}, "java": {".java"}, "python": {".py"},
       "rust": {".rs"}, "cobol": {".cob", ".cbl", ".cpy", ".cobol"}}
KW = {
    "c": "auto break case char const continue default do double else enum extern float for goto if inline int long register "
         "restrict return short signed sizeof static struct switch typedef union unsigned void volatile while _Bool bool "
         "_Static_assert static_assert true false NULL",
    "cpp": "alignas alignof auto bool break case catch char class const consteval constexpr constinit const_cast continue "
           "decltype default delete do double dynamic_cast else enum explicit export extern false float for friend goto if "
           "inline int long mutable namespace new noexcept nullptr operator private protected public register "
           "reinterpret_cast return short signed sizeof static static_assert static_cast struct switch template this "
           "throw true try typedef typeid typename union unsigned using virtual void volatile while override final "
           "std::array std::vector std::unordered_map std::map std::optional std::string_view std::unique_ptr std::shared_ptr",
    "java": "abstract assert boolean break byte case catch char class const continue default do double else enum extends "
            "final finally float for goto if implements import instanceof int interface long native new package private "
            "protected public return short static strictfp super switch synchronized this throw throws transient try void "
            "volatile while var record sealed permits yield true false null",
    "python": "False None True and as assert async await break class continue def del elif else except finally for from "
              "global if import in is lambda nonlocal not or pass raise return try while with yield match case "
              "@dataclass @property @staticmethod @classmethod",
    "rust": "as async await break const continue crate dyn else enum extern false fn for if impl in let loop match mod move "
            "mut pub ref return self Self static struct super trait true type unsafe use where while "
            "#[derive #[inline #[test unwrap expect clone Box Rc RefCell Vec Option Result",
    "cobol": "ACCEPT ADD ALTER CALL CANCEL CLOSE COMPUTE CONTINUE DELETE DISPLAY DIVIDE ENTRY EVALUATE EXIT GOBACK GO "
             "IF INITIALIZE INSPECT MERGE MOVE MULTIPLY OPEN PERFORM READ RELEASE RETURN REWRITE SEARCH SET SORT START "
             "STOP STRING SUBTRACT UNSTRING WRITE WHEN OTHER VARYING UNTIL TIMES THRU THROUGH END-IF END-PERFORM "
             "END-EVALUATE END-COMPUTE END-READ END-CALL END-STRING NEXT SENTENCE FUNCTION REDEFINES OCCURS DEPENDING "
             "INDEXED COMP COMP-3 COMP-5 BINARY PACKED-DECIMAL VALUE PIC PICTURE LOCAL-STORAGE LINKAGE USING RETURNING "
             "BY REFERENCE CONTENT 88 FILLER COPY REPLACE TRUE FALSE NOT AND OR ZERO ZEROS ZEROES SPACE SPACES "
             "HIGH-VALUES LOW-VALUES ALL TALLYING REPLACING CONVERTING POINTER ADDRESS SECTION",
}
LANG = {"chess / C": "c", "chess / C++": "cpp", "chess / Java": "java", "chess / Python": "python", "chess / Rust": "rust"}
STR = re.compile(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'')
BLOCK = re.compile(r"/\*.*?\*/", re.S)
PYDOC = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')


def code_only(text: str, lang: str) -> str:
    if lang == "cobol":
        lines = []
        for ln in text.splitlines():
            if len(ln) > 6 and ln[6:7] in "*/" and not ln.lstrip().startswith(("*>",)) and ln[:6].strip(" 0123456789") == "":
                continue  # fixed-format comment line
            ln = ln.split("*>", 1)[0]
            lines.append(ln)
        return STR.sub(" ", "\n".join(lines))
    if lang == "python":
        text = PYDOC.sub(" ", text)
        text = STR.sub(" ", text)
        return "\n".join(ln.split("#", 1)[0] if not ln.lstrip().startswith("#[") else ln for ln in text.splitlines())
    text = BLOCK.sub(" ", text)
    text = STR.sub(" ", text)
    return "\n".join(re.sub(r"//.*", "", ln) for ln in text.splitlines())


def find_repo(name: str) -> Path:
    return next(r / name for r in ROOTS if (r / name).is_dir())


def counts(repo: str, lang: str) -> collections.Counter:
    kws = KW[lang].split()
    pats = {}
    for k in kws:
        if lang == "cobol":
            pats[k] = re.compile(r"(?<![\w-])" + re.escape(k) + r"(?![\w-])", re.I)
        elif k[0] in "#@" or "::" in k:
            pats[k] = re.compile(re.escape(k) + r"(?!\w)")
        else:
            pats[k] = re.compile(r"(?<![\w.])" + re.escape(k) + r"(?!\w)")
    c = collections.Counter()
    exts = EXT[lang]
    for p in find_repo(repo).rglob("*"):
        if not p.is_file() or p.suffix.lower() not in exts or SKIP_DIRS & {x.lower() for x in p.parts}:
            continue
        raw = p.read_text(encoding="utf-8", errors="ignore")
        if lang == "c" and ("Generated by cobc" in raw[:2000] or "libcob" in raw[:3000]):
            continue
        if lang == "cpp" and p.suffix == ".h" and not any(s in raw for s in ("class ", "namespace ", "template", "std::")):
            pass
        text = code_only(raw, lang)
        for k, rx in pats.items():
            n = len(rx.findall(text))
            if n:
                c[k] += n
    return c


def main() -> None:
    res, lean = {}, {"cobol": collections.defaultdict(list), "mainstream": collections.defaultdict(list)}
    for fam, (cc, cx) in pooled.PAIRS.items():
        lang = LANG.get(fam, "cobol")
        a, b = counts(cc, lang), counts(cx, lang)
        ta, tb = sum(a.values()) or 1, sum(b.values()) or 1
        rate = {k: (1000 * a[k] / ta, 1000 * b[k] / tb) for k in set(a) | set(b)}
        only_cc = sorted([k for k in a if a[k] >= 2 and b[k] == 0], key=lambda k: -a[k])
        only_cx = sorted([k for k in b if b[k] >= 2 and a[k] == 0], key=lambda k: -b[k])
        top = sorted(rate, key=lambda k: -abs(math.log2((rate[k][0] + 0.5) / (rate[k][1] + 0.5))))[:12]
        res[fam] = {"language": lang, "tokens": [ta, tb], "only_cc": {k: a[k] for k in only_cc}, "only_codex": {k: b[k] for k in only_cx},
                    "largest_rate_gaps": {k: [round(rate[k][0], 1), round(rate[k][1], 1)] for k in top}}
        group = "cobol" if lang == "cobol" else "mainstream"
        for k, (x, y) in rate.items():
            lean[group][k].append((fam, round(x, 2), round(y, 2)))
    summary = {}
    for g, d in lean.items():
        n = 5
        rows = []
        for k, v in d.items():
            cc_hi = sum(x > y for _, x, y in v)
            cx_hi = sum(y > x for _, x, y in v)
            if max(cc_hi, cx_hi) >= 4 and len(v) >= 4:
                rows.append({"keyword": k, "cc_higher": cc_hi, "codex_higher": cx_hi, "pairs_present": len(v),
                             "p": round(pooled.sign_p(cc_hi, cc_hi + cx_hi), 3), "per_pair": v})
        summary[g] = sorted(rows, key=lambda r: (r["p"], -max(r["cc_higher"], r["codex_higher"])))
    (Path("/home/joe/gitgalaxy/chess-study") / "keyword_diff.json").write_text(json.dumps({"pairs": res, "consistent": summary}, indent=1) + "\n")
    for fam, r in res.items():
        print(f"\n== {fam}  tokens CC {r['tokens'][0]}  Codex {r['tokens'][1]}")
        print("   only Claude Code:", ", ".join(f"{k}({v})" for k, v in list(r["only_cc"].items())[:14]) or "-")
        print("   only Codex      :", ", ".join(f"{k}({v})" for k, v in list(r["only_codex"].items())[:14]) or "-")
    for g, rows in summary.items():
        print(f"\n## consistent leans across {g} pairs (>= 4 of 5 the same way)")
        for r in rows:
            print(f"   {r['keyword']:18} CC>{r['cc_higher']} CX>{r['codex_higher']} of {r['pairs_present']}  p={r['p']}  "
                  + " ".join(f"{x}/{y}" for _, x, y in r["per_pair"]))


if __name__ == "__main__":
    main()
