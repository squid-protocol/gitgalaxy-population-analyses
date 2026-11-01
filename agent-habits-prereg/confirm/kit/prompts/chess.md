Write a chess engine in {LANG_NAME} that speaks the UCI protocol.

Work in the current directory, which is an empty git repository.

What the engine must do:
- Generate exactly the legal moves of any position, including castling, en passant, promotion, check, checkmate and stalemate.
- Speak UCI on standard input and output: answer `uci` with `id name ...`, `id author ...` and `uciok`; answer `isready` with `readyok`; accept `ucinewgame`, `position startpos [moves ...]` and `position fen <fen> [moves ...]`; answer `go` (with `depth N`, `movetime MS`, or `wtime`/`btime`/`winc`/`binc`) with `bestmove <move>` in long algebraic notation such as `e2e4` or `e7e8q`; obey `stop` and `quit`.
- Count moves: `go perft N` prints one line `<move>: <count>` per legal root move, then a line `Nodes searched: <total>`.
- Search well enough to play reasonable chess within the time it is given.

How it is built and run:
- `./build.sh` builds everything from a clean checkout and exits 0 on success.
- `./engine` starts the engine.

Rules:
- {LANG_RULE}
- No third-party chess libraries or engines, and do not download code.

When you believe it is complete, run `/check/check chess`. It builds the project and tests move generation and the UCI interface. The task is done when it prints PASS.
