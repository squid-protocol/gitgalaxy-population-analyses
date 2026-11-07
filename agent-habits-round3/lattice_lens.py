"""Round 3, secondary claim R3-S5 (addendum, registered before any round 3 run): the LATTICE lens.

Each program is summarised by the mix of its functions over the frozen fingerprint lattice: the share of functions in
each family (14, plus unassigned) x rung band (k <= 3, 4-5, >= 6) = 45 fixed categories. A function's family is that of
its nearest frozen shape by Jaccard over the lattice signals (ties to the more common shape); k = lattice signals
present. Identification is exactly R3-H1's rule with a different distance: for each program with a same-model candidate
in its cell (task + language), take the nearest other program in the cell by L1 distance between mixes; a hit = same
model. Chance = mean share of same-model candidates; significance by permuting model labels within cells.

    python lattice_lens.py RUNS_CSV SCANS_DIR [--draws 10000] > r3_s5.json

RUNS_CSV columns: run,task,language,model. SCANS_DIR/<run>/ holds that run's GitGalaxy output (*_galaxy_master.db).
Frozen input: lattice_shapes.json (sha256 a27d2c93f817ac25..., temporal-crucible docs/fingerprint_trees_exploratory.json).
Exclusion (as registered): fewer than 3 functions of >= 3 lines -> no fingerprint, excluded and counted.
"""
import csv
import hashlib
import json
import pathlib
import sqlite3
import sys

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

HERE = pathlib.Path(__file__).parent
SHA = "a27d2c93f817ac25"


def lattice():
    raw = (HERE / "lattice_shapes.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest().startswith(SHA), "lattice_shapes.json changed"
    D = json.loads(raw)
    sets = [frozenset(s["signals"]) for s in D["shapes"]]
    nn = np.array([s["n"] for s in D["shapes"]], float)
    n = len(sets)
    J = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            u = len(sets[i] | sets[j])
            J[i, j] = J[j, i] = 1 - (len(sets[i] & sets[j]) / u if u else 1)
    fam = fcluster(linkage(squareform(J, checks=False), method="average"), 14, criterion="maxclust")
    U = sorted(set().union(*sets))
    S = np.array([[c in s for c in U] for s in sets], np.int32)
    order = np.argsort(-nn, kind="stable")
    return U, S, fam, order


def mix(db, language, U, S, fam, order):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    have = {c[1] for c in con.execute("PRAGMA table_info(function_data)")}
    rows = con.execute(f"SELECT {', '.join(('(COALESCE(f.' + c + ',0) > 0)') if c in have else '0' for c in U)} "
                       "FROM function_data f JOIN file_data fd ON f.file_id = fd.id WHERE f.loc >= 3 AND fd.language = ?",
                       (language,)).fetchall()
    con.close()
    if len(rows) < 3:
        return None
    X = np.array(rows, np.int32)
    inter = X @ S.T
    union = X.sum(1)[:, None] + S.sum(1)[None, :] - inter
    jac = np.where(union > 0, inter / np.maximum(union, 1), 1.0)
    f = np.where(jac.max(1) > 0, fam[order[np.argmax(jac[:, order], axis=1)]], 0)
    k = X.sum(1)
    b = np.where(k <= 3, 0, np.where(k <= 5, 1, 2))
    v = np.zeros(15 * 3)
    np.add.at(v, f * 3 + b, 1)
    return v / len(rows)


def main():
    runs_csv, scans = sys.argv[1], pathlib.Path(sys.argv[2])
    draws = int(sys.argv[sys.argv.index("--draws") + 1]) if "--draws" in sys.argv else 10000
    U, S, fam, order = lattice()
    prog, excluded = {}, []
    for r in csv.DictReader(open(runs_csv)):
        dbs = sorted((scans / r["run"]).glob("*_galaxy_master.db"))
        v = mix(dbs[0], r["language"], U, S, fam, order) if dbs else None
        if v is None:
            excluded.append(r["run"])
            continue
        prog[r["run"]] = (f"{r['task']}|{r['language']}", r["model"], v)
    ids = sorted(prog)

    def hits(model):
        h = t = 0
        for i in ids:
            cand = [j for j in ids if j != i and prog[j][0] == prog[i][0]]
            if any(model[j] == model[i] for j in cand):
                t += 1
                best = min(cand, key=lambda j: (np.abs(prog[j][2] - prog[i][2]).sum(), j))
                h += model[best] == model[i]
        return h, t
    model = {i: prog[i][1] for i in ids}
    h, t = hits(model)
    chance = [np.mean([model[j] == model[i] for j in ids if j != i and prog[j][0] == prog[i][0]])
              for i in ids if any(model[j] == model[i] for j in ids if j != i and prog[j][0] == prog[i][0])]
    rng = np.random.default_rng(7)
    cells = {}
    for i in ids:
        cells.setdefault(prog[i][0], []).append(i)
    ge = 0
    for _ in range(draws):
        m2 = {}
        for c, members in cells.items():
            for i, m in zip(members, rng.permutation([model[i] for i in members])):
                m2[i] = m
        ge += hits(m2)[0] >= h
    print(json.dumps({"claim": "R3-S5", "hits": h, "queries": t, "accuracy": h / max(t, 1),
                      "chance": float(np.mean(chance)) if chance else None, "p_one_sided": (1 + ge) / (1 + draws),
                      "draws": draws, "excluded": excluded}, indent=1))


if __name__ == "__main__":
    main()
