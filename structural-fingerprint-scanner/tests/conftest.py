"""Synthetic GitGalaxy scan databases for the test suite."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from structural_fingerprint.reference import load_reference

SIGNALS = load_reference().signal_columns


def random_functions(n: int, rng: np.random.Generator, prefix: str) -> list[dict]:
    out = []
    for i in range(n):
        loc = int(rng.integers(6, 90))
        rates = rng.gamma(0.6, 1.5, size=len(SIGNALS)) * (rng.random(len(SIGNALS)) < 0.45)
        sig = {c: int(rng.poisson(r * loc / 10)) for c, r in zip(SIGNALS, rates, strict=True)}
        out.append({"name": f"{prefix}_{i}", "loc": loc, "complexity": int(rng.integers(1, max(2, loc // 3))),
                    "args": int(rng.integers(0, 6)), "keyword_density": float(rng.uniform(0.3, 2.0)),
                    "path": f"src/{prefix}_{i % 12}.c", "signals": sig})
    return out


def write_scan(root: Path, name: str, functions: list[dict], language: str = "c",
               drop_columns: tuple[str, ...] = (), edges: list[tuple[int, int]] | None = None) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    db = d / f"{name}_galaxy_master.db"
    conn = sqlite3.connect(db)
    cols = [c for c in SIGNALS if c not in drop_columns]
    conn.execute("CREATE TABLE file_data (id INTEGER PRIMARY KEY, repo_name TEXT, file_name TEXT, file_path TEXT, "
                 "language TEXT, coding_loc INTEGER, file_archetype TEXT)")
    conn.execute("CREATE TABLE function_data (id INTEGER PRIMARY KEY, file_id INTEGER, func_name TEXT, complexity INTEGER, "
                 "loc INTEGER, args INTEGER, keyword_density REAL, func_archetype TEXT, func_fan_in INTEGER, "
                 "func_fan_out INTEGER, " + ", ".join(f"{c} INTEGER" for c in cols) + ")")
    conn.execute("CREATE TABLE repo_data (id INTEGER PRIMARY KEY, repo_name TEXT, commit_hash TEXT)")
    conn.execute("CREATE TABLE fcall_data (id INTEGER PRIMARY KEY, src_func_id INTEGER, dst_func_id INTEGER)")
    conn.execute("INSERT INTO repo_data (repo_name, commit_hash) VALUES (?, ?)", (name, "0" * 40))
    paths = sorted({f["path"] for f in functions})
    loc_by_path = {p: sum(f["loc"] for f in functions if f["path"] == p) for p in paths}
    for i, p in enumerate(paths, 1):
        conn.execute("INSERT INTO file_data VALUES (?,?,?,?,?,?,?)", (i, name, p.rsplit("/", 1)[-1], p, language,
                                                                       loc_by_path[p], ""))
    pid = {p: i for i, p in enumerate(paths, 1)}
    for k, f in enumerate(functions, 1):
        vals = [k, pid[f["path"]], f["name"], f["complexity"], f["loc"], f["args"], f["keyword_density"], "",
                f.get("fan_in", 0), f.get("fan_out", 0), *(f["signals"][c] for c in cols)]
        conn.execute(f"INSERT INTO function_data VALUES ({','.join('?' * len(vals))})", vals)
    for s, t in edges or []:
        conn.execute("INSERT INTO fcall_data (src_func_id, dst_func_id) VALUES (?, ?)", (s, t))
    conn.commit()
    conn.close()
    return db


@pytest.fixture(scope="session")
def cohort(tmp_path_factory) -> dict:
    """base; fork = 80% of base (half renamed, a sixth lightly edited) + new code; unrelated."""
    root = tmp_path_factory.mktemp("scans")
    rng = np.random.default_rng(7)
    base = random_functions(400, rng, "base")
    fork = []
    for i, f in enumerate(base[:320]):
        g = {**f, "signals": dict(f["signals"]), "path": f["path"].replace("src/", "lib/")}
        if i % 2:
            g["name"] = f"renamed_{i}"
        if i % 6 == 0:  # a small edit: one more decision, one more branch hit
            g["complexity"] += 1
            g["signals"]["struct_branch"] += 1
        fork.append(g)
    fork += random_functions(120, rng, "forknew")
    other = random_functions(400, np.random.default_rng(99), "other")
    edges = [(i, i + 1) for i in range(1, 300, 3)]
    return {
        "root": root,
        "base": write_scan(root, "base", base, edges=edges),
        "fork": write_scan(root, "fork", fork, edges=edges),
        "other": write_scan(root, "other", other, language="rust"),
        "n_shared": 320,
    }
