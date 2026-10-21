import sqlite3

import numpy as np
import pytest

from structural_fingerprint import fingerprint as FP
from structural_fingerprint.reference import load_reference
from structural_fingerprint.scan_io import ScanError, load_scan, resolve_scans

from .conftest import random_functions, write_scan


def test_resolve_scans_forms(cohort):
    root = cohort["root"]
    assert resolve_scans([cohort["base"]]) == [cohort["base"]]
    assert resolve_scans([cohort["base"].parent]) == [cohort["base"]]
    assert {p.name for p in resolve_scans([root])} >= {"base_galaxy_master.db", "fork_galaxy_master.db"}
    with pytest.raises(ScanError):
        resolve_scans([root / "missing"])


def test_load_scan(cohort):
    ref = load_reference()
    s = load_scan(cohort["base"], ref.signal_columns)
    assert s.name == "base"
    assert s.n_functions == 400
    assert s.signals.shape == (400, len(ref.signal_columns))
    assert s.missing_signals == ()
    assert len(s.call_edges) > 0
    assert set(s.func_language) == {"c"}


def test_missing_columns_read_as_zero(tmp_path):
    ref = load_reference()
    funcs = random_functions(20, np.random.default_rng(1), "f")
    db = write_scan(tmp_path, "old", funcs, drop_columns=("struct_macros", "def_listeners"))
    s = load_scan(db, ref.signal_columns)
    assert set(s.missing_signals) == {"struct_macros", "def_listeners"}
    assert s.signals[:, ref.signal_columns.index("struct_macros")].sum() == 0
    fp = FP.build(s, ref)
    assert fp.data["source"]["missing_signals"] == ["struct_macros", "def_listeners"]


def test_synthetic_slices_are_not_functions(tmp_path):
    ref = load_reference()
    funcs = random_functions(5, np.random.default_rng(2), "f")
    funcs[0]["name"] = "__global_context__"
    s = load_scan(write_scan(tmp_path, "slices", funcs), ref.signal_columns)
    assert s.n_functions == 4
    assert "__global_context__" not in s.func_name


def test_not_a_scan(tmp_path):
    db = tmp_path / "x_galaxy_master.db"
    sqlite3.connect(db).close()
    with pytest.raises(ScanError):
        load_scan(db, load_reference().signal_columns)


def test_fingerprint_roundtrip(cohort, tmp_path):
    ref = load_reference()
    fp = FP.build(load_scan(cohort["base"], ref.signal_columns), ref, min_loc=3)
    d = fp.data
    assert d["schema"] == FP.SCHEMA
    assert sum(d["archetypes"]["count_share"].values()) == pytest.approx(1.0)
    assert sum(d["archetypes"]["loc_share"].values()) == pytest.approx(1.0)
    assert set(d["geometry"]["sketch"]) == set(FP.GEOMETRY_SKETCH)
    assert all(len(v) == len(FP.QUANTILES) for v in d["geometry"]["sketch"].values())
    assert 0 <= d["callgraph"]["leaf_share"] <= 1
    assert len(d["centroid"]["vector"]) == ref.n_features
    p = fp.save(tmp_path)
    back = FP.Fingerprint.load(p)
    assert back.data == d
    assert back.functions is not None and len(back.functions) == len(fp.functions)
    np.testing.assert_array_equal(back.functions.vectors, fp.functions.vectors)


def test_min_loc_filters(cohort):
    ref = load_reference()
    s = load_scan(cohort["base"], ref.signal_columns)
    a = FP.build(s, ref, min_loc=1)
    b = FP.build(s, ref, min_loc=40)
    assert b.data["size"]["functions"] < a.data["size"]["functions"]
    assert b.data["size"]["functions"] == int((s.loc >= 40).sum())


def test_empty_scan(tmp_path):
    ref = load_reference()
    fp = FP.build(load_scan(write_scan(tmp_path, "empty", []), ref.signal_columns), ref)
    assert fp.data["size"]["functions"] == 0
    assert fp.data["callgraph"]["edges_per_function"] == 0.0
