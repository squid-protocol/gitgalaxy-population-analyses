import json

from structural_fingerprint.cli import main


def test_spec(capsys):
    assert main(["spec", "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["lens"] == "structure" and len(d["features"]) == 37


def test_fingerprint_then_compare_from_fingerprints(cohort, tmp_path, capsys):
    fp_dir = tmp_path / "fps"
    assert main(["fingerprint", str(cohort["root"]), "-o", str(fp_dir)]) == 0
    assert (fp_dir / "base.sfp.json").is_file() and (fp_dir / "base.sfp.npz").is_file()
    lineage = tmp_path / "lineage.csv"
    lineage.write_text("name,parent\nfork,base\n")
    out = tmp_path / "report"
    assert main(["compare", str(fp_dir), "-o", str(out), "--declared-lineage", str(lineage), "--workers", "1"]) == 0
    for f in ("report.html", "report.md", "summary.json", "pairs.csv", "trees/descent.nwk", "trees/profile.nwk",
              "matrices/shared_structure.csv", "matrices/survival_lower95.csv", "matrices/profile_distance.csv"):
        assert (out / f).is_file(), f
    s = json.loads((out / "summary.json").read_text())
    assert s["lineage_evaluation"]["descent"]["hit_at_1"] == 1.0
    html = (out / "report.html").read_text()
    assert html.startswith("<!doctype html>") and "Descent: shared structure" in html
    assert "<\\/" not in html.split('id=summary>')[0]


def test_compare_scans_without_twins(cohort, tmp_path):
    out = tmp_path / "r"
    assert main(["compare", str(cohort["base"]), str(cohort["fork"]), str(cohort["other"]), "-o", str(out),
                 "--no-twins", "--lens", "portable"]) == 0
    s = json.loads((out / "summary.json").read_text())
    assert s["spec"]["lens"] == "portable" and s["trees"]["descent"] is None


def test_twins_and_explain(cohort, tmp_path, capsys):
    assert main(["twins", str(cohort["fork"]), str(cohort["base"]), "-o", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    summary = json.loads(out[out.index("{"):])
    assert summary["twins"] > 200
    rows = (tmp_path / "twins_fork__base.csv").read_text().splitlines()
    assert rows[0].startswith("query_function,") and len(rows) == summary["twins"] + 1
    assert main(["explain", str(cohort["base"]), str(cohort["other"])]) == 0
    assert "Component distances" in capsys.readouterr().out


def test_bad_weights(cohort, tmp_path):
    import pytest

    with pytest.raises(SystemExit):
        main(["compare", str(cohort["root"]), "-o", str(tmp_path), "--weights", "bogus=1"])
