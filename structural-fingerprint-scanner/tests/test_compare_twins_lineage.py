import re

import numpy as np
import pytest

from structural_fingerprint import fingerprint as FP
from structural_fingerprint.compare import COMPONENTS, IncomparableError, compare_cohort, component_distances, explain
from structural_fingerprint.lineage import descent_matrix, evaluate_lineage, upgma, wilson_lower
from structural_fingerprint.reference import load_reference
from structural_fingerprint.scan_io import load_scan
from structural_fingerprint.twins import TwinParams, _fdr_threshold, find_twins


@pytest.fixture(scope="module")
def fps(cohort):
    ref = load_reference()
    return {k: FP.build(load_scan(cohort[k], ref.signal_columns), ref, min_loc=3) for k in ("base", "fork", "other")}


def test_identical_fingerprints_have_zero_distance(fps):
    d = component_distances(fps["base"], fps["base"])
    assert set(d) == set(COMPONENTS)
    assert all(v == pytest.approx(0.0, abs=1e-12) for v in d.values())


def test_fork_is_closer_than_unrelated(fps):
    c = compare_cohort([fps["base"], fps["fork"], fps["other"]])
    assert c.composite is not None
    assert c.composite[0, 1] < c.composite[0, 2]
    assert c.nearest(1)["base"][0][0] == "fork"
    assert np.allclose(c.composite, c.composite.T)


def test_pair_has_no_composite(fps):
    c = compare_cohort([fps["base"], fps["fork"]])
    assert c.composite is None
    with pytest.raises(ValueError):
        c.nearest()


def test_incomparable_lenses(cohort, fps):
    ref = load_reference("portable")
    other_lens = FP.build(load_scan(cohort["base"], ref.signal_columns), ref, min_loc=3)
    with pytest.raises(IncomparableError):
        compare_cohort([fps["base"], other_lens])


def test_explain_reports_every_component(fps):
    e = explain(fps["base"], fps["other"], top=5)
    assert e["pair"] == ["base", "other"]
    assert len(e["signals"]) == 5 and len(e["archetypes"]) == 5
    assert {g["feature"] for g in e["geometry"]} == set(FP.GEOMETRY_SKETCH)


def test_twins_recover_the_shared_functions(cohort, fps):
    r = find_twins(fps["fork"].functions, fps["base"].functions, TwinParams())
    s = r.stats
    shared = cohort["n_shared"]
    # 320 of the fork's 440 functions came from base; a sixth of those were edited.
    assert s["twins"] >= 0.85 * shared
    assert s["twins"] <= shared + 0.02 * s["eligible"]
    assert s["exact_clones"] > 0
    assert r.threshold > 0 and r.est_fdr <= 0.01
    # Half the copies were renamed: the name-blind search must still find them.
    assert s["renamed_twins"] >= 0.4 * shared
    assert s["name_agreement"] == pytest.approx(1.0)


def test_twins_with_unrelated_code_are_rare(fps):
    r = find_twins(fps["other"].functions, fps["base"].functions, TwinParams())
    assert r.stats["survival"] <= 0.01


def test_twins_are_deterministic(fps):
    a = find_twins(fps["fork"].functions, fps["base"].functions)
    b = find_twins(fps["fork"].functions, fps["base"].functions)
    np.testing.assert_array_equal(a.q_index, b.q_index)
    assert a.threshold == b.threshold


def test_fdr_threshold_needs_power():
    # Ten perfect hits and no decoys cannot certify 1%: the +1 correction refuses.
    t, _ = _fdr_threshold(np.zeros(10), np.array([5.0]), 0.01)
    assert t == 0.0
    t, est = _fdr_threshold(np.linspace(0, 1, 500), np.array([2.0]), 0.01)
    assert t == pytest.approx(1.0) and est <= 0.01


def test_wilson_lower():
    lb = wilson_lower(np.array([0, 6, 2800]), np.array([50, 48, 5000]))
    assert lb[0] == 0.0
    assert lb[1] < 6 / 48 and lb[2] > lb[1]
    assert wilson_lower(np.array([1]), np.array([0]))[0] == 0.0


def test_descent_matrix_and_tree(fps):
    tables = [fps[k].functions for k in ("base", "fork", "other")]
    dm = descent_matrix(tables, workers=2)
    assert dm.shared[0, 1] > 0.5 and dm.shared[0, 2] < 0.05
    assert np.allclose(dm.shared, dm.shared.T)
    nwk, order = upgma(dm.distance, dm.names)
    assert nwk.endswith(";") and nwk.count("(") == nwk.count(")")
    assert sorted(re.findall(r"[a-z]+(?=:)", nwk)) == ["base", "fork", "other"]
    assert sorted(order) == [0, 1, 2]


def test_upgma_small_and_quoting():
    assert upgma(np.zeros((1, 1)), ["only"])[0] == "only;"
    nwk, _ = upgma(np.array([[0, 2.0], [2.0, 0]]), ["a b", "c"])
    assert nwk == "('a b':1.000000,c:1.000000);"


def test_evaluate_lineage_relations():
    names = ["root", "a", "a1", "b", "x"]
    declared = {"a": ["root"], "a1": ["a"], "b": ["root"]}
    d = np.array([
        [0, 1, 2, 3, 9],
        [1, 0, 0.5, 3, 9],
        [2, 0.5, 0, 3, 9],
        [3, 3, 3, 0, 1],
        [9, 9, 9, 1, 0],
    ], dtype=float)
    ev = evaluate_lineage(names, d, declared)
    by = {r["name"]: r for r in ev["rows"]}
    # a's child a1 is nearer than its parent, but descendants are not counted against it
    assert by["a"]["rank"] == 1
    rel = {r["name"]: r["relation"] for r in ev["nearest_rows"]}
    assert rel["a"] == "descendant" and rel["a1"] == "ancestor" and rel["b"] == "other branch"
    assert ev["nearest_is_family"] == pytest.approx(3 / 4)
    ev2 = evaluate_lineage(names, d, declared, max_distance=0.9)
    assert "b" in ev2["undetectable"] and "x" not in {r["name"] for r in ev2["nearest_rows"]}


def test_pooled_threshold_and_explicit_threshold(fps):
    from structural_fingerprint.twins import accept, pooled_threshold, search

    a = search(fps["fork"].functions, fps["base"].functions)
    b = search(fps["other"].functions, fps["base"].functions)
    t, _ = pooled_threshold([a, b], 0.01)
    assert t > 0
    assert pooled_threshold([], 0.01) == (0.0, 0.0)
    # A threshold of 0 keeps only exact clones (and exact distance-0 reciprocal hits).
    strict = accept(a, 0.0)
    assert strict.threshold == 0.0 and strict.stats["twins"] <= accept(a).stats["twins"]
    assert find_twins(fps["fork"].functions, fps["base"].functions, threshold=t).threshold == t
