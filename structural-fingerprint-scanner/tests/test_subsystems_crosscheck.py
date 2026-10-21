import csv
import json

import numpy as np
import pytest

from structural_fingerprint import crosscheck as CC
from structural_fingerprint import fingerprint as FP
from structural_fingerprint import subsystems as SS
from structural_fingerprint import subway as SW
from structural_fingerprint.cli import main
from structural_fingerprint.reference import load_reference
from structural_fingerprint.scan_io import load_scan


@pytest.fixture(scope="module")
def built(cohort):
    ref = load_reference()
    tables = {k: FP.build(load_scan(cohort[k], ref.signal_columns), ref, min_loc=3).functions
              for k in ("base", "fork", "other")}
    maps, _, _ = SW.build_maps(list(tables.values()), "base")
    return ref, tables, maps


def test_subsystem_cells(built):
    ref, tables, maps = built
    p = SS.profile(tables, maps, ref, min_functions=10)
    assert set(p.repos) == {"fork", "other"}
    fork = [c.composite for (r, _), c in p.cells.items() if r == "fork" and np.isfinite(c.composite)]
    other = [c.composite for (r, _), c in p.cells.items() if r == "other" and np.isfinite(c.composite)]
    assert fork and other and np.median(fork) < np.median(other)
    for c in p.cells.values():
        if np.isfinite(c.composite):
            assert c.n >= 10 and c.n_ref >= 10 and set(c.distances) == set(SS.COMPONENTS)
            assert 0 < len(c.drift) <= 3
        else:
            assert c.n < 10 or c.n_ref < 10
    assert p.matrix().shape == (2, len(p.subsystems))
    assert p.languages["fork"] == "c" and p.languages["other"] == "rust"


def test_language_table_and_candidates(built):
    ref, tables, maps = built
    p = SS.profile(tables, maps, ref, min_functions=10, faithful=0.3)
    langs = {r["language"] for r in p.by_language()}
    assert langs == {"c"}  # only the fork kept the wiring
    assert all(c.repo != "fork" for c in p.candidates())  # same language as the reference: never a candidate
    html = SS.render_section(p)
    assert "Subsystems across repositories" in html and "By language" in html


def _verdicts(tmp_path, tables):
    base = tables["base"]
    rows = []
    for i, (path, name) in enumerate(zip(base.path, base.name, strict=True)):
        k = int(str(name).split("_")[1])
        rows.append({"variant": "fork", "subsystem": "core", "file": str(path), "func": str(name),
                     "cls": "exact" if k < 320 else "gone"})
        rows.append({"variant": "other", "subsystem": "core", "file": str(path), "func": str(name), "cls": "gone"})
    rows.append({"variant": "fork", "subsystem": "core", "file": "nowhere.c", "func": "ghost", "cls": "exact"})
    p = tmp_path / "verdicts.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return p


def test_crosscheck_scores_twins_against_verdicts(built, tmp_path):
    _, tables, maps = built
    cc = CC.crosscheck(tables["base"], maps, CC.read_verdicts(_verdicts(tmp_path, tables)))
    fork, other = cc.per_port["fork"], cc.per_port["other"]
    assert fork.precision > 0.95 and fork.recall > 0.8
    assert other.tp == 0 and other.true_rate == 0.0 and other.predicted_rate < 0.02
    assert cc.unmatched_rows == 1
    assert cc.pooled.n == fork.n + other.n
    assert sum(fork.twins_by_class.values()) == fork.tp + fork.fp
    d = cc.to_dict()
    assert d["pooled"]["twins_by_class"]["exact"] == fork.twins_by_class["exact"] + other.twins_by_class["exact"]


def test_crosscheck_rejects_wrong_columns(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("port,function,verdict\nx,y,z\n")
    with pytest.raises(ValueError):
        CC.read_verdicts(p)


def test_cli_writes_subsystems_and_crosscheck(cohort, built, tmp_path):
    _, tables, _ = built
    v = _verdicts(tmp_path, tables)
    out = tmp_path / "subway"
    assert main(["subway", str(cohort["root"]), "--reference", "base", "-o", str(out), "--crosscheck", str(v)]) == 0
    assert (out / "subsystems.csv").read_text().startswith("repo,language,subsystem,")
    d = json.loads((out / "crosscheck.json").read_text())
    assert d["per_port"]["fork"]["precision"] > 0.95
    page = (out / "subway.html").read_text()
    assert "Subsystems across repositories" in page and "Cross-check against source text" in page
    rep = tmp_path / "report"
    assert main(["compare", str(cohort["root"]), "-o", str(rep), "--subway-reference", "base", "--crosscheck", str(v),
                 "--workers", "1"]) == 0
    assert (rep / "crosscheck.csv").is_file() and "Cross-check against source text" in (rep / "report.html").read_text()
