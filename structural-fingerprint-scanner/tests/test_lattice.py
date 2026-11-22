"""Tests for the two-layer Seed-and-Extend + 32-keyword-family lattice module."""

from __future__ import annotations

import json

import numpy as np

from structural_fingerprint.cli import main as cli_main
from structural_fingerprint.lattice import (
    keyword_lattice_distance,
    keyword_lattice_profile,
    seed_and_extend_with_lattice,
)
from structural_fingerprint.reference import load_reference
from structural_fingerprint.scan_io import load_scan


def test_keyword_lattice_profile_and_distance():
    sigs_a = np.array([[10, 0, 0], [8, 2, 0]], dtype=np.float64)
    sigs_b = np.array([[0, 0, 10], [0, 2, 8]], dtype=np.float64)
    norm_a, dom_a, dist_a = keyword_lattice_profile(sigs_a)
    norm_b, dom_b, dist_b = keyword_lattice_profile(sigs_b)

    assert np.allclose(np.linalg.norm(norm_a, axis=1), 1.0)
    assert dom_a.tolist() == [0, 0]
    assert dom_b.tolist() == [2, 2]
    assert np.isclose(dist_a.sum(), 1.0)
    assert np.isclose(keyword_lattice_distance(dist_a, dist_a), 0.0, atol=1e-9)
    assert keyword_lattice_distance(dist_a, dist_b) > 0.8


def test_seed_and_extend_with_lattice_separates_fork_from_unrelated(cohort):
    ref = load_reference("portable")
    sc_base = load_scan(cohort["base"], ref.signal_columns)
    sc_fork = load_scan(cohort["fork"], ref.signal_columns)
    sc_other = load_scan(cohort["other"], ref.signal_columns)

    same = seed_and_extend_with_lattice(sc_base, sc_base, ref, outer=15)
    fork = seed_and_extend_with_lattice(sc_base, sc_fork, ref, outer=15)
    other = seed_and_extend_with_lattice(sc_base, sc_other, ref, outer=15)

    assert np.isclose(same.kw_jsd, 0.0, atol=1e-9)
    assert same.matched_kw_cos > 0.99
    assert fork.fgw_cost < other.fgw_cost or fork.kw_jsd < other.kw_jsd
    assert fork.kw_jsd < other.kw_jsd
    assert fork.matched_kw_cos > other.matched_kw_cos


def test_cli_lattice_compare_json(cohort, capsys):
    rc = cli_main([
        "lattice-compare",
        str(cohort["base"]),
        str(cohort["fork"]),
        "--lens", "portable",
        "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["repo_a"] == "base"
    assert payload["repo_b"] == "fork"
    assert 0.0 <= payload["kw_jsd"] <= 1.0
    assert payload["se_n"] >= 3
