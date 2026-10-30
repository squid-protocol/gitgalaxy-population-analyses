import json
from pathlib import Path

import numpy as np
import pytest

from structural_fingerprint import fingerprint as FP
from structural_fingerprint import subway as SW
from structural_fingerprint.cli import main
from structural_fingerprint.reference import load_reference
from structural_fingerprint.scan_io import load_scan

DOOM_TAXONOMY = Path(__file__).resolve().parents[1] / "examples" / "doom" / "subsystems.json"


@pytest.fixture(scope="module")
def tables(cohort):
    ref = load_reference()
    return {k: FP.build(load_scan(cohort[k], ref.signal_columns), ref, min_loc=3).functions
            for k in ("base", "fork", "other")}


def test_doom_taxonomy_rules():
    tax = SW.Taxonomy.load(DOOM_TAXONOMY)
    name = {v: k for k, v in tax.index.items()}
    assert name[tax.classify("linuxdoom-1.10/r_draw.c")] == "renderer"
    assert name[tax.classify("src/doom/p_mobj.c")] == "playsim"
    assert name[tax.classify("src/d_net.c")] == "net"  # the more specific prefix wins over d_
    assert name[tax.classify("engine/AutomapWidget.java")] == "automap"
    assert name[tax.classify("misc/readme_tool.c")] == "other"


def test_taxonomy_rejects_unknown_subsystem():
    with pytest.raises(ValueError):
        SW.Taxonomy("t", ["a"], basename_prefix=[("x_", "b")])


def test_directory_taxonomy():
    t = FP.FunctionTable(repo="r", name=np.array(["f", "g", "h"]), path=np.array(["lib/a.c", "lib/b.c", "app/c.c"]),
                         language=np.array(["c", "c", "c"]), loc=np.array([5, 5, 5]),
                         archetype=np.zeros(3, dtype=np.int16), key=np.arange(3, dtype=np.uint64),
                         vectors=np.zeros((3, 4), dtype=np.float32))
    tax = SW.Taxonomy.from_directories(t)
    assert tax.subsystems[:2] == ["lib", "app"]
    assert tax.subsystems[tax.classify("app/x.c")] == "app"
    assert tax.subsystems[tax.classify("vendor/y.c")] == "other"


def test_function_table_keeps_edges(tables, tmp_path):
    t = tables["base"]
    assert t.edges is not None and len(t.edges) > 0 and t.edges.max() < len(t)
    t.save(tmp_path / "x.sfp.npz")
    back = FP.FunctionTable.load(tmp_path / "x.sfp.npz")
    np.testing.assert_array_equal(back.edges, t.edges)


def test_maps_on_reference_layout(tables):
    maps, tax, pos = SW.build_maps(list(tables.values()), "base")
    by = {m.repo: m for m in maps}
    assert maps[0].repo == "base" and by["base"].wiring_similarity == 1.0
    assert pos.shape == (len(tax.subsystems), 2) and pos.min() >= 0 and pos.max() <= 1
    # The fork copies base's functions and calls; the unrelated repository does not.
    assert by["fork"].edges_kept > 0.6 > by["other"].edges_kept
    assert np.nanmax(by["fork"].survival) > 0.5
    assert np.nanmax(by["other"].survival) < 0.05
    assert by["fork"].sources.get("twin", 0) > 0
    assert sum(by["fork"].sources.values()) == int(by["fork"].sizes.sum())


def test_wiring_floor_and_cross_wiring():
    ref = np.array([[6, 2, 0], [0, 4, 2], [1, 0, 3]])
    assert SW.wiring_floor(np.eye(3)) == pytest.approx(1.0)
    assert 0 < SW.wiring_floor(ref) < 1
    # Same cross-subsystem calls, different local traffic: cross wiring ignores the diagonal.
    local = np.array([[1, 2, 0], [0, 9, 2], [1, 0, 0]])
    assert SW._cosine(SW._off_diagonal(local), SW._off_diagonal(ref)) == pytest.approx(1.0)
    assert SW._cosine(local, ref) < 1.0


def test_null_wiring_is_seeded_and_below_a_copy(tables):
    maps, _, _ = SW.build_maps(list(tables.values()), "base")
    by = {m.repo: m for m in maps}
    fork, base = by["fork"], by["base"]
    t = tables["fork"]
    again = SW.null_wiring(fork.labels, t.edges, base.calls)
    assert again == pytest.approx((fork.wiring_null, fork.cross_wiring_null), nan_ok=True)
    # A copy's placement is never worse than shuffling its own functions (equal here: one live subsystem).
    assert fork.wiring_similarity >= fork.wiring_null - 1e-9
    assert np.isnan(SW.null_wiring(np.full(3, -1), None, base.calls)[0])


def test_layout_is_deterministic(tables):
    _, _, a = SW.build_maps(list(tables.values()), "base")
    _, _, b = SW.build_maps(list(tables.values()), "base")
    np.testing.assert_array_equal(a, b)


def test_unknown_reference(tables):
    with pytest.raises(ValueError):
        SW.build_maps(list(tables.values()), "nope")


def test_cli_subway_and_compare_section(cohort, tmp_path):
    out = tmp_path / "subway"
    assert main(["subway", str(cohort["root"]), "--reference", "base", "-o", str(out)]) == 0
    d = json.loads((out / "subway.json").read_text())
    assert d["reference"] == "base" and {m["repo"] for m in d["maps"]} == {"base", "fork", "other"}
    assert (out / "subway.csv").read_text().startswith(
        "repo,functions,wiring_similarity,edges_kept,shape_distance,cross_wiring,wiring_null,cross_wiring_null,")
    assert 0 < d["wiring_floor"] <= 1 and "cross_wiring" in d["maps"][1]
    assert "Subway maps" in (out / "subway.html").read_text()
    rep = tmp_path / "report"
    assert main(["compare", str(cohort["root"]), "-o", str(rep), "--subway-reference", "base", "--workers", "1"]) == 0
    html = (rep / "report.html").read_text()
    assert "Subway maps" in html and "Structure against wiring" in html
    assert (rep / "subway.json").is_file()


def test_overrides_apply_to_their_repository_only(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"name": "t", "subsystems": ["render", "play", "other"],
                             "path_keyword": [["draw", "render"]],
                             "overrides": {"java-port": {"path_keyword": [["/src/p/", "play"]]}}}))
    tax = SW.Taxonomy.load(p)
    assert tax.subsystems[tax.classify("src/p/Actions.java", "java-port")] == "play"
    assert tax.subsystems[tax.classify("src/p/Actions.java", "other-port")] == "other"
    assert tax.subsystems[tax.classify("src/p/draw.java", "other-port")] == "render"
    p.write_text(json.dumps({"name": "t", "subsystems": ["a"], "overrides": {"x": {"path_keyword": [["k", "zz"]]}}}))
    with pytest.raises(ValueError):
        SW.Taxonomy.load(p)


def test_graph_stats_on_a_known_graph():
    # triangle 0-1-2 plus a tail 2->3, and an isolated node 4
    g = SW.graph_stats(5, np.array([[0, 1], [1, 2], [2, 0], [2, 3], [1, 0]]))
    assert g["mean_degree"] == pytest.approx(5 / 5)
    assert g["lcc_share"] == pytest.approx(4 / 5)
    assert g["reciprocity"] == pytest.approx(2 / 5)
    # clustering: nodes 0 and 1 have 1 triangle over 1 pair; node 2 has 1 of 3 pairs; 3 and 4 have none
    assert g["clustering"] == pytest.approx((1 + 1 + 1 / 3) / 5)
    assert g["leaf_share"] == pytest.approx(2 / 5) and g["root_share"] == pytest.approx(1 / 5)
    assert all(np.isnan(v) for v in SW.graph_stats(0, None).values())


def test_lineage_order_and_mapping_check(tables):
    maps, _, _ = SW.build_maps(list(tables.values()), "base")
    order = SW.lineage_order(maps, {"fork": ["base"]})
    assert [m.repo for m in order][:2] == ["base", "fork"]
    assert maps[0].shape_distance == 0.0 and all(np.isfinite(m.shape_distance) for m in maps)
    assert set(maps[1].graph) == set(SW.GRAPH_FIELDS)
    check = SW.mapping_check(maps)
    # "other" has no calls, so its wiring is undefined and it is left out; too few points to test
    assert check["n"] == 1 and check["spearman_rho"] is None


def test_twin_browser_in_report(cohort, tmp_path):
    from structural_fingerprint import browser as BR
    from structural_fingerprint.lineage import descent_matrix

    rep = tmp_path / "report"
    assert main(["compare", str(cohort["root"]), "-o", str(rep), "--workers", "1"]) == 0
    page = (rep / "report.html").read_text()
    assert "id=twin-browser" in page and 'data-pair="' in page
    blob = page.split("<script type=application/json id=twins>")[1].split("</script>")[0]
    data = json.loads(blob.replace("<\\/", "</"))
    pair = next(p for p in data["pairs"] if {p["q"], p["t"]} == {"base", "fork"})
    assert pair["twins"] >= 0.85 * cohort["n_shared"] and len(pair["rows"]) == pair["shown"]
    qn, qp, _qloc, tn, tp, _tloc, dist, flags = pair["rows"][0]
    assert isinstance(qn, str) and isinstance(tn, str) and dist >= 0 and flags in (0, 1, 2, 3)
    assert 0 <= qp < len(pair["paths"]) and 0 <= tp < len(pair["paths"])
    assert not any({p["q"], p["t"]} == {"base", "other"} for p in data["pairs"])  # nothing shared, not listed
    # The cap keeps the closest twins.
    ref = load_reference()
    tbl = {k: FP.build(load_scan(cohort[k], ref.signal_columns), ref, min_loc=3).functions for k in ("base", "fork")}
    dm = descent_matrix(list(tbl.values()), keep_results=True)
    capped = BR.payload(tbl, dm, max_rows=10)["pairs"][0]
    assert capped["shown"] == 10 and [r[6] for r in capped["rows"]] == sorted(r[6] for r in capped["rows"])
    assert main(["compare", str(cohort["root"]), "-o", str(tmp_path / "nb"), "--no-browser", "--workers", "1"]) == 0
    assert "id=twin-browser" not in (tmp_path / "nb" / "report.html").read_text()
