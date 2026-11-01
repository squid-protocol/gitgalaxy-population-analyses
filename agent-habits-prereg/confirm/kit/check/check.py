#!/usr/bin/env python3
"""The done-condition checker for the agent-habits confirmation runs (identical for both agents).

    check chess | check sat        (run from the project directory)

Builds with ./build.sh, then tests the program. Prints PASS or FAIL and a short reason per test; exit 0 on PASS.
Standard library only.
"""

import itertools
import json
import os
import random
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path

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

# D7 additions. Assets are generated once by gen_assets.py (fixed seeds, verified) and shipped beside this file.
ASSETS = Path(__file__).resolve().parent / "assets"
PUZZLE_SHARE_NUM, PUZZLE_SHARE_DEN = 4, 5      # solve at least 80 % of the mate puzzles
MATCH_GAMES, MATCH_NEED, MATCH_MAX_PLIES, MATCH_SEED = 4, 3.0, 300, 20261101
PIECE_VALUE = {1: 1, 2: 3, 3: 3, 4: 5, 5: 9, 6: 0}
SAT_HARD_TIMEOUT = 60
SAT_HARD_SHARE_NUM, SAT_HARD_SHARE_DEN = 4, 5  # solve at least 80 % of the hard formulas, never a wrong answer


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
        out.append(puzzle_test(e))
    finally:
        e.close()
    out.append(match_test())
    return out


def bestmove(e: "Engine", setup: str, go: str, timeout: float) -> str | None:
    e.send(setup)
    e.send(go)
    ok, lines = e.until(lambda s: s.startswith("bestmove"), timeout)
    if not ok:
        return None
    t = lines[-1].split()
    return t[1] if len(t) > 1 else None


def puzzle_test(e: "Engine") -> tuple[bool, str]:
    """D7: unique forced mates (mate in 2 or 3); the engine must find the mating first move in 2 s."""
    ps = json.loads((ASSETS / "puzzles.json").read_text())
    solved = 0
    missed = []
    for p in ps:
        e.send("ucinewgame")
        mv = bestmove(e, f"position fen {p['fen']}", "go movetime 2000", 10)
        if mv == p["move"]:
            solved += 1
        else:
            missed.append(f"mate in {p['mate_in']}: {p['fen']} (played {mv})")
    need = -(-PUZZLE_SHARE_NUM * len(ps) // PUZZLE_SHARE_DEN)
    msg = f"mate puzzles: solved {solved} of {len(ps)} (need {need}) in 2 s each"
    if missed and solved < need:
        msg += "\n         missed, first 3: " + "; ".join(missed[:3])
    return solved >= need, msg


def greedy_move(board, rng: random.Random):
    """The weak opponent: take the most valuable piece it can (mate if it can), else a random move."""
    import chess
    best, best_score = [], None
    for m in board.legal_moves:
        score = 0
        victim = board.piece_at(m.to_square)
        if victim:
            score += PIECE_VALUE[victim.piece_type]
        elif board.is_en_passant(m):
            score += 1
        if m.promotion:
            score += PIECE_VALUE[m.promotion] - 1
        board.push(m)
        if board.is_checkmate():
            score += 1000
        board.pop()
        if best_score is None or score > best_score:
            best, best_score = [m], score
        elif score == best_score:
            best.append(m)
    return rng.choice(best)


def match_test() -> tuple[bool, str]:
    """D7: 4 games against the greedy opponent, colours alternating, 0.5 s per engine move; need 3 points."""
    import chess
    points, results = 0.0, []
    for g in range(MATCH_GAMES):
        rng = random.Random(MATCH_SEED + g)
        engine_white = g % 2 == 0
        board = chess.Board()
        moves: list[str] = []
        e = Engine()
        result = None
        try:
            e.send("uci")
            e.until(lambda s: s == "uciok", 10)
            e.send("ucinewgame")
            me = chess.WHITE if engine_white else chess.BLACK
            while result is None:
                # Only the automatic draw rules (fivefold repetition, 75 moves) end a game; at the ply cap a side
                # 5+ points of material ahead is adjudicated the winner (standard tournament adjudication).
                if board.is_game_over():
                    o = board.outcome()
                    result = 0.5 if o.winner is None else (1.0 if o.winner == me else 0.0)
                    break
                if board.ply() >= MATCH_MAX_PLIES:
                    diff = sum(PIECE_VALUE[p.piece_type] * (1 if p.color == me else -1) for p in board.piece_map().values())
                    result = 1.0 if diff >= 5 else 0.0 if diff <= -5 else 0.5
                    break
                if board.turn == (chess.WHITE if engine_white else chess.BLACK):
                    setup = "position startpos" + (" moves " + " ".join(moves) if moves else "")
                    mv = bestmove(e, setup, "go movetime 500", 10)
                    try:
                        m = chess.Move.from_uci(mv) if mv else None
                    except ValueError:
                        m = None
                    if m is None or m not in board.legal_moves:
                        result = 0.0
                        results.append(f"game {g + 1}: illegal or missing move {mv!r} at ply {board.ply()}")
                        break
                else:
                    m = greedy_move(board, rng)
                board.push(m)
                moves.append(m.uci())
        finally:
            e.close()
        points += result
        results.append(f"game {g + 1} ({'white' if engine_white else 'black'}): {result} after {board.ply()} plies")
    msg = f"match vs greedy opponent: {points} of {MATCH_GAMES} (need {MATCH_NEED})\n         " + "; ".join(results)
    return points >= MATCH_NEED, msg


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
    out.append(hard_sat_test())
    return out


def read_cnf(path: Path) -> tuple[int, list[list[int]]]:
    n, cl, cur = 0, [], []
    for ln in path.read_text().splitlines():
        ln = ln.strip()
        if not ln or ln[0] == "c":
            continue
        if ln[0] == "p":
            n = int(ln.split()[2])
            continue
        for t in map(int, ln.split()):
            if t == 0:
                cl.append(cur)
                cur = []
            else:
                cur.append(t)
    return n, cl


def hard_sat_test() -> tuple[bool, str]:
    """D7: random 3-SAT at ratio 4.26 (n = 150-250) and large planted formulas, 60 s each.
    Never a wrong answer; at least 80 % answered."""
    man = json.loads((ASSETS / "sat" / "manifest.json").read_text())
    solved, wrong, timeouts = 0, [], []
    tmp = Path(tempfile.mkdtemp())
    for c in man:
        src = ASSETS / "sat" / c["file"]
        path = tmp / f"{random.SystemRandom().getrandbits(64):016x}.cnf"  # an anonymous name: the file name tells nothing
        path.write_text(src.read_text().split("\n", 1)[1])               # and the descriptive comment line is dropped
        t0 = time.time()
        try:
            p = subprocess.run(["./solver", str(path)], capture_output=True, text=True, timeout=SAT_HARD_TIMEOUT)
        except subprocess.TimeoutExpired:
            timeouts.append(c["file"])
            continue
        lines = [ln.strip() for ln in p.stdout.splitlines()]
        status = next((ln for ln in lines if ln.startswith("s ")), None)
        if c["status"] == "SAT":
            n, cl = read_cnf(path)
            lits = [int(t) for ln in lines if ln.startswith("v") for t in ln[1:].split()]
            model = {abs(x): x > 0 for x in lits if x}
            good = all(v in model for v in range(1, n + 1)) and all(any(model.get(abs(l)) == (l > 0) for l in k) for k in cl)
            ok = status == "s SATISFIABLE" and p.returncode == 10 and good
        else:
            ok = status == "s UNSATISFIABLE" and p.returncode == 20
        if ok:
            solved += 1
        elif status is None and p.returncode not in (10, 20):
            timeouts.append(f"{c['file']} (no answer, exit {p.returncode})")
        else:
            wrong.append(f"{c['file']} (want {c['status']}, got {status!r}, exit {p.returncode}, {time.time() - t0:.1f}s)")
    need = -(-SAT_HARD_SHARE_NUM * len(man) // SAT_HARD_SHARE_DEN)
    msg = f"hard formulas: {solved} of {len(man)} answered correctly within {SAT_HARD_TIMEOUT}s (need {need}, no wrong answers)"
    if wrong:
        msg += "\n         WRONG: " + "; ".join(wrong[:4])
    if timeouts and solved < need:
        msg += "\n         unanswered: " + "; ".join(timeouts[:4])
    return solved >= need and not wrong, msg


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
