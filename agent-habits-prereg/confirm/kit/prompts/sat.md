Write a SAT solver in {LANG_NAME} for propositional formulas in DIMACS CNF format, based on the DPLL algorithm (unit propagation and backtracking search; any further techniques are your choice).

Work in the current directory, which is an empty git repository.

What the solver must do:
- `./solver FILE` reads a DIMACS CNF formula from FILE (comment lines start with `c`; the header is `p cnf <variables> <clauses>`; each clause is a list of non-zero integers ending in `0`).
- If the formula is satisfiable, print `s SATISFIABLE` and then one or more lines starting with `v` that list a value for every variable (a positive number for true, a negative one for false), ending with `0`; exit with code 10.
- If it is unsatisfiable, print `s UNSATISFIABLE` and exit with code 20.

How it is built and run:
- `./build.sh` builds everything from a clean checkout and exits 0 on success.
- `./solver` is the program described above.

Rules:
- {LANG_RULE}
- No third-party SAT or constraint-solving libraries, and do not download code.

When you believe it is complete, run `/check/check sat`. It builds the project and tests the solver on satisfiable and unsatisfiable formulas. The task is done when it prints PASS.
