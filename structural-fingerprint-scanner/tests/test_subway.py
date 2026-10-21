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
    assert (out / "subway.csv").read_text().startswith("repo,functions,wiring_similarity,edges_kept,")
    assert "Subway maps" in (out / "subway.html").read_text()
    rep = tmp_path / "report"
    assert main(["compare", str(cohort["root"]), "-o", str(rep), "--subway-reference", "base", "--workers", "1"]) == 0
    html = (rep / "report.html").read_text()
    assert "Subway maps" in html and "Structure against wiring" in html
    assert (rep / "subway.json").is_file()
