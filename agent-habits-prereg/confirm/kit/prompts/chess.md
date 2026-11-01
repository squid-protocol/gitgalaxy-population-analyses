Write a chess engine in {LANG_NAME} that speaks the UCI protocol.

Work in the current directory, which is an empty git repository.

What the engine must do:
- Generate exactly the legal moves of any position, including castling, en passant, promotion, check, checkmate and stalemate.
- Speak UCI on standard input and output: answer `uci` with `id name ...`, `id author ...` and `uciok`; answer `isready` with `readyok`; accept `ucinewgame`, `position startpos [moves ...]` and `position fen <fen> [moves ...]`; answer `go` (with `depth N`, `movetime MS`, or `wtime`/`btime`/`winc`/`binc`) with `bestmove <move>` in long algebraic notation such as `e2e4` or `e7e8q`; obey `stop` and `quit`.
- Count moves: `go perft N` prints one line `<move>: <count>` per legal root move, then a line `Nodes searched: <total>`.
- Play well within the time it is given: it must find forced mates (mate in 2 and mate in 3, within 2 seconds per position), and win a short match against a weak opponent that grabs material whenever it can (four games, colours alternating, 0.5 seconds per move, at least 3 points).

How it is built and run:
- `./build.sh` builds everything from a clean checkout and exits 0 on success.
- `./engine` starts the engine.

Rules:
- {LANG_RULE}
- No third-party chess libraries or engines, and do not download code.

When you believe it is complete, run `/check/check chess`. It builds the project and tests move generation, the UCI interface, mate puzzles (at least 80 % solved) and the match. It uses a practice set of puzzles; the final check uses different positions. The task is done when the final check prints PASS.
