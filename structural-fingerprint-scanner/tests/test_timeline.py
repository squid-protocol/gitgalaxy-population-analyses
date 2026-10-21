import json
import os
import subprocess
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from structural_fingerprint import fingerprint as FP
from structural_fingerprint import timeline as TL
from structural_fingerprint.reference import load_reference
from structural_fingerprint.scan_io import load_scan

from .conftest import random_functions, write_scan


class FakeScanner(TL.Scanner):
    """Stands in for the engine: each snapshot holds funcs.json, turned into a scan DB."""

    def __init__(self):
        super().__init__(engine=Path("."))
        self.calls = 0

    def scan(self, src: Path, out: Path) -> Path:
        self.calls += 1
        funcs = json.loads((src / "funcs.json").read_text())
        return write_scan(out, src.name, funcs)


def _git(repo: Path, *args: str, date: str | None = None) -> None:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    if date:
        env.update(GIT_AUTHOR_DATE=f"{date}T12:00:00", GIT_COMMITTER_DATE=f"{date}T12:00:00")
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


@pytest.fixture(scope="module")
def history(tmp_path_factory):
    """A reference, and a repository that starts as a copy of it and is rewritten over time."""
    root = tmp_path_factory.mktemp("tl")
    rng = np.random.default_rng(3)
    base = random_functions(300, rng, "ref")
    ref_db = write_scan(root / "scans", "ref", base)
    ref = load_reference()
    ref_fp = FP.build(load_scan(ref_db, ref.signal_columns), ref, min_loc=3)
    repo = root / "port"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    new = random_functions(300, np.random.default_rng(11), "new")
    plan = [("2001-01-10", 0), ("2002-06-01", 150), ("2003-03-01", 150), ("2004-03-01", 300)]
    for date, replaced in plan:
        funcs = new[:replaced] + base[replaced:]
        (repo / "funcs.json").write_text(json.dumps(funcs))
        _git(repo, "add", "funcs.json")
        _git(repo, "commit", "-q", "--allow-empty", "-m", date, date=date)
    return {"root": root, "repo": repo, "ref": ref_fp}


def test_plan_snapshots(history):
    plan = TL.plan_snapshots(history["repo"], "1y")
    dates = [d for d, _ in plan]
    assert dates[0] == "2001-01-10" and dates[-1] == "2004-03-01"
    assert len({s for _, s in plan}) == len(plan)  # no commit twice
    assert len(TL.plan_snapshots(history["repo"], "6m")) >= len(plan)
    with pytest.raises(ValueError):
        TL.plan_snapshots(history["repo"], "1w")


def test_shallow_clone_is_refused(history, tmp_path):
    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{history['repo']}", str(shallow)], check=True)
    with pytest.raises(RuntimeError, match="shallow"):
        TL.plan_snapshots(shallow)


def test_run_tracks_drift_and_caches(history, tmp_path):
    scanner = FakeScanner()
    thresholds: dict = {}
    rows = TL.run([("port", history["repo"])], history["ref"], tmp_path, scanner, every="1y", thresholds=thresholds)
    assert set(thresholds["port"]) == {"reference_to_snapshot", "snapshot_to_reference"}
    surv = [r["reference_survival"] for r in rows]
    assert surv[0] > 0.9 and surv[-1] < 0.05
    assert all(a >= b - 0.02 for a, b in pairwise(surv))  # rewriting only removes
    assert rows[0]["retention"] is None and rows[1]["retention"] < 0.9
    assert rows[0]["distance_centroid"] < rows[-1]["distance_centroid"]
    first = scanner.calls
    assert first == len(rows)
    TL.run([("port", history["repo"]), ("same-history", history["repo"])], history["ref"], tmp_path, scanner)
    assert scanner.calls == first  # every snapshot came from the commit-keyed cache, for both names
    TL.write_outputs(tmp_path, rows, "ref", {"every": "1y"})
    assert (tmp_path / "timeline.csv").read_text().startswith("repo,date,commit,functions,")
    page = TL.render_section(rows, "ref", [("2002-01-01", "event")])
    assert page.count("<polyline") >= 4 and "event" in page and "How much of ref survives" in page


def test_failed_scan_is_skipped(history, tmp_path):
    class Broken(FakeScanner):
        def scan(self, src, out):
            raise RuntimeError("engine crashed")

    assert TL.run([("port", history["repo"])], history["ref"], tmp_path, Broken()) == []
