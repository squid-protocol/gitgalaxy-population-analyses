"""Read GitGalaxy scan output.

A GitGalaxy scan writes ``<name>_galaxy_master.db`` (SQLite) next to an audit JSON.
The scanner reads only that database, read-only, and only the columns it needs:
per-function geometry and signal counts, per-file language and path, the repository
row, and resolved call edges. Columns an older engine did not write are reported as
missing and read as zero, so older scans still load; the fingerprint records which
signals were absent so a comparison can say when it is not like-for-like.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

DB_SUFFIX = "_galaxy_master.db"
# Buckets the engine's slicer emits for top-level statements: not functions.
SYNTHETIC_FUNCTIONS = frozenset({"__global_context__", "__module__", "__file_scope__"})


class ScanError(RuntimeError):
    pass


@dataclass
class ScanData:
    """One repository's scan, as arrays aligned on the function axis."""

    name: str
    db_path: Path
    metadata: dict
    # functions (n)
    func_id: np.ndarray
    func_name: list[str]
    func_file: np.ndarray  # index into the file arrays
    loc: np.ndarray
    complexity: np.ndarray
    args: np.ndarray
    keyword_density: np.ndarray
    fan_in: np.ndarray
    fan_out: np.ndarray
    engine_archetype: list[str]
    signals: np.ndarray  # (n, S) raw hit counts, columns = signal_columns
    signal_columns: tuple[str, ...]
    missing_signals: tuple[str, ...]
    # files (m)
    file_path: list[str]
    file_language: list[str]
    file_coding_loc: np.ndarray
    file_archetype: list[str]
    # resolved call edges (e, 2) as function-array indices
    call_edges: np.ndarray = field(default_factory=lambda: np.zeros((0, 2), dtype=np.int64))

    @property
    def n_functions(self) -> int:
        return len(self.func_id)

    @property
    def func_language(self) -> list[str]:
        return [self.file_language[i] for i in self.func_file]

    @property
    def func_path(self) -> list[str]:
        return [self.file_path[i] for i in self.func_file]


def resolve_scans(paths: list[Path]) -> list[Path]:
    """Expand each argument to scan databases: a ``*_galaxy_master.db``, a scan
    directory holding one, or a directory of scan directories."""
    out: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_file():
            out.append(p)
            continue
        if not p.is_dir():
            raise ScanError(f"no such scan: {p}")
        here = sorted(p.glob(f"*{DB_SUFFIX}"))
        if here:
            out.extend(here)
            continue
        below = sorted(p.glob(f"*/*{DB_SUFFIX}"))
        if not below:
            raise ScanError(f"no *{DB_SUFFIX} in {p} or its subdirectories")
        out.extend(below)
    seen, uniq = set(), []
    for p in out:
        r = p.resolve()
        if r not in seen:
            seen.add(r)
            uniq.append(p)
    return uniq


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _audit_metadata(db_path: Path) -> dict:
    stem = db_path.name[: -len(DB_SUFFIX)] if db_path.name.endswith(DB_SUFFIX) else db_path.stem
    audit = db_path.with_name(f"{stem}_galaxy_audit.json")
    if not audit.is_file():
        return {}
    try:
        trail = json.loads(audit.read_text()).get("1. Forensic Trail (Traceability)", {})
    except (OSError, ValueError):
        return {}
    ctx = trail.get("Analysis Context", {})
    src = trail.get("Source Control Footprint (Immutable Anchor)", {})
    validation = trail.get("Archetype Validation", {})
    return {
        "engine_identity": ctx.get("Engine Identity"),
        "scanned_at": ctx.get("Analysis ISO Timestamp"),
        "remote": src.get("Remote Origin URL"),
        "archetype_model": validation.get("Trained"),
        "function_archetype_state": (validation.get("function") or {}).get("State"),
    }


def load_scan(db_path: Path, signal_columns: tuple[str, ...], name: str | None = None) -> ScanData:
    db_path = Path(db_path)
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as e:
        raise ScanError(f"{db_path}: {e}") from e
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("function_data", "file_data"):
            if t not in tables:
                raise ScanError(f"{db_path}: not a GitGalaxy scan database (no {t} table)")
        fcols = _columns(conn, "function_data")
        present = [c for c in signal_columns if c in fcols]
        missing = tuple(c for c in signal_columns if c not in fcols)
        if missing:
            log.warning("%s: %d signal column(s) absent, read as zero: %s", db_path.name, len(missing),
                        ", ".join(missing))

        def opt(col: str, default: str = "0") -> str:
            return f"f.{col}" if col in fcols else default

        sig_sql = ", ".join(f"COALESCE(f.{c}, 0)" for c in present) or "0"
        rows = conn.execute(
            f"""SELECT f.id, f.file_id, COALESCE(f.func_name, ''), COALESCE(f.loc, 0), COALESCE(f.complexity, 0),
                       COALESCE(f.args, 0), COALESCE({opt('keyword_density')}, 0),
                       COALESCE({opt('func_fan_in')}, 0), COALESCE({opt('func_fan_out')}, 0),
                       COALESCE({opt('func_archetype', "''")}, ''), {sig_sql}
                FROM function_data f ORDER BY f.id"""
        ).fetchall()
        rows = [r for r in rows if r[2] not in SYNTHETIC_FUNCTIONS]

        fdcols = _columns(conn, "file_data")
        files = conn.execute(
            f"""SELECT id, COALESCE(file_path, file_name, ''), COALESCE(language, 'unknown'),
                       COALESCE(coding_loc, 0), COALESCE({'file_archetype' if 'file_archetype' in fdcols else "''"}, '')
                FROM file_data ORDER BY id"""
        ).fetchall()
        repo_row = None
        if "repo_data" in tables:
            rcols = _columns(conn, "repo_data")
            want = [c for c in ("repo_name", "commit_hash", "commit_date") if c in rcols]
            if want:
                r = conn.execute(f"SELECT {', '.join(want)} FROM repo_data LIMIT 1").fetchone()
                repo_row = dict(zip(want, r, strict=True)) if r else None
        edges = []
        if "fcall_data" in tables and {"src_func_id", "dst_func_id"} <= _columns(conn, "fcall_data"):
            edges = conn.execute(
                "SELECT src_func_id, dst_func_id FROM fcall_data "
                "WHERE src_func_id IS NOT NULL AND dst_func_id IS NOT NULL"
            ).fetchall()
    except sqlite3.Error as e:
        raise ScanError(f"{db_path}: {e}") from e
    finally:
        conn.close()

    file_index = {fid: i for i, (fid, *_rest) in enumerate(files)}
    rows = [r for r in rows if r[1] in file_index]
    n = len(rows)
    sig = np.zeros((n, len(signal_columns)), dtype=np.float64)
    if n and present:
        got = np.asarray([r[10:] for r in rows], dtype=np.float64)
        for j, c in enumerate(present):
            sig[:, signal_columns.index(c)] = got[:, j]
    func_id = np.asarray([r[0] for r in rows], dtype=np.int64)
    id_to_idx = {int(fid): i for i, fid in enumerate(func_id)}
    call_edges = np.asarray(
        [(id_to_idx[s], id_to_idx[d]) for s, d in edges if s in id_to_idx and d in id_to_idx and s != d],
        dtype=np.int64,
    ).reshape(-1, 2)

    meta = _audit_metadata(db_path)
    if repo_row:
        meta.update({k: v for k, v in repo_row.items() if v is not None})
    if name is None:
        name = (repo_row or {}).get("repo_name") or db_path.name.removesuffix(DB_SUFFIX)

    def col(i: int, dtype=np.float64) -> np.ndarray:
        return np.asarray([r[i] for r in rows], dtype=dtype)

    return ScanData(
        name=str(name),
        db_path=db_path,
        metadata=meta,
        func_id=func_id,
        func_name=[r[2] for r in rows],
        func_file=np.asarray([file_index[r[1]] for r in rows], dtype=np.int64),
        loc=col(3),
        complexity=col(4),
        args=col(5),
        keyword_density=col(6),
        fan_in=col(7),
        fan_out=col(8),
        engine_archetype=[r[9] for r in rows],
        signals=sig,
        signal_columns=tuple(signal_columns),
        missing_signals=missing,
        file_path=[f[1] for f in files],
        file_language=[str(f[2]).lower() for f in files],
        file_coding_loc=np.asarray([f[3] for f in files], dtype=np.float64),
        file_archetype=[f[4] for f in files],
        call_edges=call_edges,
    )
