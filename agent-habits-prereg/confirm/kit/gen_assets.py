#!/usr/bin/env python3
"""Generate the D7 checker assets once, from fixed seeds (needs python-chess and pycosat; not in the run image).

    python gen_assets.py OUTDIR        # writes OUTDIR/puzzles.json, OUTDIR/sat/*.cnf, OUTDIR/sat/manifest.json

Puzzles: sparse attack positions, white to move, kept only if exactly ONE first move forces mate in N
(N = 2 or 3) and no mate in N-1 exists (brute-force search over all replies).
SAT: random 3-SAT at clause/variable ratio 4.26 (status from picosat via pycosat) and large planted formulas (ratio 3.5: large, not hard)
(satisfiable by construction; picosat confirms).
"""

import json
import random
import sys
from pathlib import Path

import chess
import pycosat

SEED = 20261101


def forced_mate(b: chess.Board, n: int) -> bool:
    """Side to move can force mate in at most n of its moves."""
    for m in list(b.legal_moves):
        b.push(m)
        try:
            if b.is_checkmate():
                return True
            if n > 1 and not b.is_game_over():
                if all(_after_reply(b, r, n - 1) for r in list(b.legal_moves)):
                    return True
        finally:
            b.pop()
    return False


def _after_reply(b: chess.Board, r: chess.Move, n: int) -> bool:
    b.push(r)
    try:
        return forced_mate(b, n)
    finally:
        b.pop()


def mating_first_moves(b: chess.Board, n: int) -> list[str]:
    out = []
    for m in list(b.legal_moves):
        b.push(m)
        try:
            if b.is_checkmate():
                ok = True
            elif n > 1 and not b.is_game_over():
                ok = all(_after_reply(b, r, n - 1) for r in list(b.legal_moves))
            else:
                ok = False
        finally:
            b.pop()
        if ok:
            out.append(m.uci())
    return out


ATTACK_SETS = [
    "Q", "R", "RR", "QR", "RB", "QN", "QB", "RN",
]


def random_position(rng: random.Random) -> chess.Board | None:
    b = chess.Board(None)
    squares = rng.sample(range(64), 10)
    b.set_piece_at(squares[0], chess.Piece(chess.KING, chess.WHITE))
    b.set_piece_at(squares[1], chess.Piece(chess.KING, chess.BLACK))
    i = 2
    for sym in rng.choice(ATTACK_SETS):
        b.set_piece_at(squares[i], chess.Piece.from_symbol(sym))
        i += 1
    for _ in range(rng.randint(0, 3)):  # black defenders: pawns not on ranks 1/8, sometimes a minor piece
        sq = squares[i]
        i += 1
        if chess.square_rank(sq) in (0, 7):
            continue
        b.set_piece_at(sq, chess.Piece(chess.PAWN, chess.BLACK))
    if rng.random() < 0.3:
        b.set_piece_at(squares[i], chess.Piece.from_symbol(rng.choice("nb")))
    b.turn = chess.WHITE
    b.clear_stack()
    if not b.is_valid() or b.is_check() or b.is_game_over():
        return None
    return b


def puzzles(want2: int, want3: int, rng: random.Random) -> list[dict]:
    got = {2: [], 3: []}
    seen = set()
    tries = 0
    while (len(got[2]) < want2 or len(got[3]) < want3) and tries < 200000:
        tries += 1
        b = random_position(rng)
        if b is None or b.board_fen() in seen:
            continue
        seen.add(b.board_fen())
        if mating_first_moves(b, 1):
            continue
        m2 = mating_first_moves(b, 2)
        if m2:
            if len(m2) == 1 and len(got[2]) < want2:
                got[2].append({"fen": b.fen(), "mate_in": 2, "move": m2[0]})
            continue
        if len(got[3]) < want3 and len(b.piece_map()) <= 6:
            m3 = mating_first_moves(b, 3)
            if len(m3) == 1:
                got[3].append({"fen": b.fen(), "mate_in": 3, "move": m3[0]})
    print(f"puzzles: {len(got[2])} mate-in-2, {len(got[3])} mate-in-3 from {tries} candidates", file=sys.stderr)
    return got[2] + got[3]


def rand3sat(n: int, ratio: float, rng: random.Random) -> list[list[int]]:
    return [[v if rng.random() < 0.5 else -v for v in rng.sample(range(1, n + 1), 3)] for _ in range(int(ratio * n))]


def planted(n: int, m: int, rng: random.Random) -> list[list[int]]:
    truth = [rng.random() < 0.5 for _ in range(n + 1)]
    cl = []
    while len(cl) < m:
        c = [v if rng.random() < 0.5 else -v for v in rng.sample(range(1, n + 1), 3)]
        if any((l > 0) == truth[abs(l)] for l in c):
            cl.append(c)
    return cl


def sat_set(out: Path, rng: random.Random) -> None:
    (out / "sat").mkdir(parents=True, exist_ok=True)
    manifest = []
    specs = [("random", n, k) for n, cnt in ((150, 4), (200, 4), (250, 2)) for k in range(cnt)]
    specs += [("planted", n, k) for n, cnt in ((2000, 2), (5000, 1)) for k in range(cnt)]
    for kind, n, k in specs:
        cl = rand3sat(n, 4.26, rng) if kind == "random" else planted(n, int(3.5 * n), rng)
        res = pycosat.solve(cl)
        status = "UNSAT" if res == "UNSAT" else "SAT"
        if kind == "planted":
            assert status == "SAT"
        name = f"{kind}-n{n}-{k}.cnf"
        (out / "sat" / name).write_text(f"c {kind} 3-SAT n={n}\np cnf {n} {len(cl)}\n"
                                        + "".join(" ".join(map(str, c)) + " 0\n" for c in cl))
        manifest.append({"file": name, "n": n, "clauses": len(cl), "status": status})
        print(f"{name}: {status}", file=sys.stderr)
    (out / "sat" / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")


def main() -> None:
    out = Path(sys.argv[1])
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else SEED  # SEED: the held-out set; SEED + 1000: the practice set
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    (out / "puzzles.json").write_text(json.dumps(puzzles(14, 8, rng), indent=1) + "\n")
    sat_set(out, random.Random(seed + 1))


if __name__ == "__main__":
    main()
