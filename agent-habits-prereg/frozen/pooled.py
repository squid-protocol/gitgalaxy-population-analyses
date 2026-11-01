"""Pool the agent pairs of the chess study (5 same-language chess pairs + the chess COBOL pair) with the 4 other
agentic-COBOL pairs: 10 pairs, same task and language within each, Claude Code vs Codex. Per measure: in how many
pairs each agent reads higher, and the two-sided sign-test p (ties dropped). Reads scans through sfs-cohort/
(chess: engine main 433228fe1; COBOL study: engine #7170 branch). Writes pooled.json.
"""

import json
import math
from pathlib import Path

import landscape as L

L.SCANS = L.BASE / "sfs-cohort"
PAIRS = {
    "chess / C": ("agentic-chessengine-c-cc", "agentic-chessengine-c-codex"),
    "chess / C++": ("agentic-chessengine-cpp-cc", "agentic-chessengine-cpp-codex"),
    "chess / Java": ("agentic-chessengine-java-cc", "agentic-chessengine-java-codex"),
    "chess / Python": ("agentic-chessengine-python-cc", "agentic-chessengine-python-codex"),
    "chess / Rust": ("agentic-chessengine-rust-cc", "agentic-chessengine-rust-codex"),
    "chess / COBOL": ("agentic-chessengine-cobol-cc", "agentic-chessengine-cobol-codex"),
    "compressor / COBOL": ("agentic-cobol-compress-cc", "agentic-cobol-compress"),
    "DOOM-like / COBOL": ("agentic-cobol-doom-cc", "agentic-cobol-doom-codex"),
    "pygame-style / COBOL": ("agentic-cobol-pygame-cc", "agentic-cobol-pygame"),
    "SAT solver / COBOL": ("agentic-cobol-sat-cc", "agentic-cobol-sat-codex"),
}
COLS = ["code_loc", "functions", "functions_per_kloc", "loc_median", "complexity_median", "complexity_ge10_pct",
        "args_mean", "fan_out_mean", "top5pct_hub_share", "test_function_share", "doc_per_code_line"]


def sign_p(k: int, n: int) -> float:
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def main() -> None:
    rows, out = [], {}
    for fam, (cc, cx) in PAIRS.items():
        a, b = L.profile(cc), L.profile(cx)
        rows.append({"pair": fam, "claude_code": a, "codex": b})
    measures = COLS + [f"risk_{r}" for r in L.RISKS]
    for m in measures:
        cc_hi = cx_hi = tie = 0
        per = []
        for r in rows:
            g = (lambda p: p["risk"][m[5:]]) if m.startswith("risk_") else (lambda p: p.get(m))
            x, y = g(r["claude_code"]), g(r["codex"])
            if x is None or y is None:
                continue
            per.append((r["pair"], x, y))
            if x > y:
                cc_hi += 1
            elif y > x:
                cx_hi += 1
            else:
                tie += 1
        out[m] = {"claude_code_higher": cc_hi, "codex_higher": cx_hi, "tie": tie,
                  "sign_p": round(sign_p(cc_hi, cc_hi + cx_hi), 4), "per_pair": per}
    (L.BASE / "pooled.json").write_text(json.dumps({"pairs": list(PAIRS), "measures": out}, indent=1) + "\n")
    print(f"{'measure':26}{'CC>':>5}{'CX>':>5}{'tie':>5}{'p':>8}")
    for m, v in sorted(out.items(), key=lambda kv: kv[1]["sign_p"]):
        print(f"{m:26}{v['claude_code_higher']:5}{v['codex_higher']:5}{v['tie']:5}{v['sign_p']:8.3f}")


if __name__ == "__main__":
    main()
