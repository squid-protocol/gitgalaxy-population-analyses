#!/usr/bin/env python3
"""The done-condition checker for the agent-habits confirmation runs (identical for both agents).

    check chess | check sat        (run from the project directory)

Builds with ./build.sh, then tests the program. Prints PASS or FAIL and a short reason per test; exit 0 on PASS.
Standard library only.
"""

import itertools
import os
import random
import select
import subprocess
import sys
import tempfile
import time

BUILD_TIMEOUT = 900

# Published perft node counts (chessprogramming.org "Perft Results").
PERFT = [
    ("startpos", None, 3, 8902),
    ("startpos", None, 4, 197281),
    ("kiwipete", "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", 3, 97862),
    ("position 3", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", 4, 43238),
    ("position 4", "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", 3, 9467),
    ("position 5", "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", 3, 62379),
]
START_MOVES = {f + r1 + f + r2 for f in "abcdefgh" for r1, r2 in (("2", "3"), ("2", "4"))} | {
    "b1a3", "b1c3", "g1f3", "g1h3"}


def build() -> str | None:
    if not os.path.isfile("build.sh"):
        return "no ./build.sh"
    try:
        p = subprocess.run(["bash", "build.sh"], capture_output=True, text=True, timeout=BUILD_TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"./build.sh took longer than {BUILD_TIMEOUT}s"
    if p.returncode != 0:
        tail = (p.stdout + p.stderr).strip().splitlines()[-15:]
        return "./build.sh failed:\n" + "\n".join(tail)
    return None


class Engine:
    def __init__(self):
        self.p = subprocess.Popen(["./engine"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, bufsize=0)
        self.fd = self.p.stdout.fileno()
        self.buf = b""
        self.eof = False

    def send(self, line: str) -> None:
        try:
            self.p.stdin.write((line + "\n").encode())
            self.p.stdin.flush()
        except (BrokenPipeError, OSError):
            self.eof = True

    def _line(self, end: float) -> str | None:
        # Raw reads + our own buffer: select() on a buffered reader misses lines already pulled into its buffer.
        while b"\n" not in self.buf:
            if self.eof:
                return None
            r, _, _ = select.select([self.fd], [], [], max(0.0, end - time.time()))
            if not r:
                return None
            chunk = os.read(self.fd, 65536)
            if not chunk:
                self.eof = True
                if not self.buf:
                    return None
                self.buf += b"\n"
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return line.decode("utf-8", "replace").strip()

    def until(self, pred, timeout: float) -> tuple[bool, list[str]]:
        lines, end = [], time.time() + timeout
        while time.time() < end:
            line = self._line(end)
            if line is None:
                break
            lines.append(line)
            if pred(line):
                return True, lines
        return False, lines

    def close(self) -> None:
        try:
            self.send("quit")
            self.p.wait(timeout=3)
        except Exception:
            self.p.kill()


def check_chess() -> list[tuple[bool, str]]:
    if not os.path.isfile("engine"):
        return [(False, "no ./engine")]
    out = []
    e = Engine()
    try:
        e.send("uci")
        ok, _ = e.until(lambda s: s == "uciok", 10)
        out.append((ok, "uci -> uciok"))
        e.send("isready")
        ok, _ = e.until(lambda s: s == "readyok", 10)
        out.append((ok, "isready -> readyok"))
        for name, fen, depth, want in PERFT:
            e.send("ucinewgame")
            e.send("position startpos" if fen is None else f"position fen {fen}")
            e.send(f"go perft {depth}")
            ok, lines = e.until(lambda s: s.lower().startswith("nodes searched"), 180)
            got = None
            if ok:
                try:
                    got = int(lines[-1].split(":", 1)[1].strip())
                except (IndexError, ValueError):
                    got = None
            out.append((got == want, f"perft {name} depth {depth}: want {want}, got {got if got is not None else 'no Nodes searched line'}"))
        e.send("ucinewgame")
        e.send("position startpos")
        e.send("go movetime 1000")
        ok, lines = e.until(lambda s: s.startswith("bestmove"), 15)
        mv = lines[-1].split()[1] if ok and len(lines[-1].split()) > 1 else None
        out.append((mv in START_MOVES, f"go movetime 1000 from the start position: bestmove {mv}"))
    finally:
        e.close()
    return out


def planted(n: int, m: int, rng: random.Random) -> list[list[int]]:
    truth = [rng.random() < 0.5 for _ in range(n + 1)]
    clauses = []
    while len(clauses) < m:
        vs = rng.sample(range(1, n + 1), 3)
        c = [v if rng.random() < 0.5 else -v for v in vs]
        if any((lit > 0) == truth[abs(lit)] for lit in c):
            clauses.append(c)
    return clauses


def pigeonhole(p: int, h: int) -> tuple[int, list[list[int]]]:
    var = lambda i, j: i * h + j + 1  # noqa: E731
    cl = [[var(i, j) for j in range(h)] for i in range(p)]
    for j in range(h):
        for a, b in itertools.combinations(range(p), 2):
            cl.append([-var(a, j), -var(b, j)])
    return p * h, cl


def brute_sat(n: int, clauses: list[list[int]]) -> bool:
    for bits in range(1 << n):
        if all(any(((bits >> (abs(l) - 1)) & 1) == (l > 0) for l in c) for c in clauses):
            return True
    return False


def sat_cases() -> list[tuple[str, int, list[list[int]], bool]]:
    rng = random.Random(20261101)
    cases = []
    for n in (40, 80, 120):
        cases.append((f"planted 3-SAT n={n}", n, planted(n, int(4.2 * n), rng), True))
    for p, h in ((5, 4), (7, 6)):
        n, cl = pigeonhole(p, h)
        cases.append((f"pigeonhole {p}->{h}", n, cl, False))
    for k in range(6):
        n = 14
        cl = [[v if rng.random() < 0.5 else -v for v in rng.sample(range(1, n + 1), 3)] for _ in range(int(4.8 * n))]
        cases.append((f"random 3-SAT n={n} #{k}", n, cl, brute_sat(n, cl)))
    cases.append(("empty formula n=3", 3, [], True))
    cases.append(("unit conflict", 1, [[1], [-1]], False))
    return cases


def check_sat() -> list[tuple[bool, str]]:
    if not os.path.isfile("solver"):
        return [(False, "no ./solver")]
    out = []
    with tempfile.TemporaryDirectory() as td:
        for name, n, cl, want in sat_cases():
            path = os.path.join(td, "f.cnf")
            with open(path, "w") as f:
                f.write(f"c {name}\np cnf {n} {len(cl)}\n" + "".join(" ".join(map(str, c)) + " 0\n" for c in cl))
            try:
                p = subprocess.run(["./solver", path], capture_output=True, text=True, timeout=60)
            except subprocess.TimeoutExpired:
                out.append((False, f"{name}: no answer within 60s"))
                continue
            lines = [ln.strip() for ln in p.stdout.splitlines()]
            status = next((ln for ln in lines if ln.startswith("s ")), None)
            if want:
                lits = [int(t) for ln in lines if ln.startswith("v") for t in ln[1:].split()]
                model = {abs(x): x > 0 for x in lits if x}
                full = all(v in model for v in range(1, n + 1))
                good = full and all(any(model.get(abs(l)) == (l > 0) for l in c) for c in cl)
                ok = status == "s SATISFIABLE" and p.returncode == 10 and good and (not lits or lits[-1] == 0)
                why = "" if ok else f" (status {status!r}, exit {p.returncode}, assignment {'valid' if good else 'missing or wrong'})"
            else:
                ok = status == "s UNSATISFIABLE" and p.returncode == 20
                why = "" if ok else f" (status {status!r}, exit {p.returncode})"
            out.append((ok, f"{name}: {'SAT' if want else 'UNSAT'}{why}"))
    return out


def main() -> int:
    task = sys.argv[1] if len(sys.argv) > 1 else ""
    if task not in ("chess", "sat"):
        print("usage: check chess|sat")
        return 2
    err = build()
    if err:
        print("FAIL\n" + err)
        return 1
    results = check_chess() if task == "chess" else check_sat()
    passed = all(ok for ok, _ in results)
    print("PASS" if passed else "FAIL")
    for ok, msg in results:
        print(("  ok   " if ok else "  FAIL ") + msg)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
