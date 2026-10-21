import math
import os
from pathlib import Path

import numpy as np
import pytest

from structural_fingerprint import features as F
from structural_fingerprint.reference import GEOMETRY_FEATURES, load_reference
from structural_fingerprint.scan_io import load_scan, resolve_scans


def test_reference_shape_and_provenance():
    ref = load_reference()
    assert ref.n_features == len(GEOMETRY_FEATURES) + len(ref.signal_columns)
    assert ref.centroids.shape == (len(ref.archetype_names), ref.n_features)
    assert len(ref.provenance["engine_commit"]) == 40
    assert np.all(ref.iqrs > 0)


def test_spec_hash_identifies_lens():
    s, p = load_reference("structure"), load_reference("portable")
    assert s.spec_hash == load_reference("structure").spec_hash
    assert s.spec_hash != p.spec_hash
    assert np.all(p.weights <= s.weights + 1e-12)
    assert p.weights[s.feature_names.index("keyword_density")] == 0.0
    np.testing.assert_array_equal(p.engine_weights, s.engine_weights)


def test_unknown_lens():
    with pytest.raises(ValueError):
        load_reference("nope")


def test_raw_features_match_engine_formula():
    ref = load_reference()
    sig = np.zeros((1, len(ref.signal_columns)))
    sig[0, ref.signal_columns.index("struct_branch")] = 4
    sig[0, ref.signal_columns.index("def_encapsulation")] = 100  # far above its cap
    raw = F.raw_features(ref, [20], [5], [2], [1.25], sig)[0]
    get = dict(zip(ref.feature_names, raw, strict=True))
    assert get["log_loc"] == pytest.approx(math.log1p(20))
    assert get["log_complexity"] == pytest.approx(math.log1p(5))
    assert get["log_args"] == pytest.approx(math.log1p(2))
    assert get["keyword_density"] == pytest.approx(1.25)
    assert get["func_internal_density"] == pytest.approx(5 / 20)
    assert get["log_density_struct_branch"] == pytest.approx(math.log1p(4 / 20 * 100))
    cap = ref.caps["def_encapsulation"]
    assert get["log_density_def_encapsulation"] == pytest.approx(math.log1p(cap))


def test_zero_loc_uses_denominator_one():
    ref = load_reference()
    raw = F.raw_features(ref, [0], [3], [0], [0], np.zeros((1, len(ref.signal_columns))))[0]
    assert raw[ref.feature_names.index("func_internal_density")] == pytest.approx(3.0)


def test_centroid_classifies_as_itself():
    ref = load_reference()
    z = ref.centroids / np.where(ref.engine_weights > 0, ref.engine_weights, 1.0)
    idx, dist = F.engine_archetypes(ref, z)
    assert list(idx) == list(range(len(ref.archetype_names)))
    assert np.allclose(dist, 0, atol=1e-6)  # expanded-square distance: float residue only


def test_structural_key_is_exact():
    sig = np.array([[1, 2, 3], [1, 2, 3], [1, 2, 4]])
    k = F.structural_key([10, 10, 10], [2, 2, 2], [1, 1, 1], sig)
    assert k[0] == k[1] != k[2]


REAL = os.environ.get("SFS_REAL_SCANS")


@pytest.mark.skipif(not REAL, reason="set SFS_REAL_SCANS to a directory of GitGalaxy scans for the parity check")
def test_engine_archetype_parity_on_real_scans():
    """Recomputed archetypes must equal the labels the engine wrote. Requires scans made by
    the engine commit the reference model was extracted from."""
    ref = load_reference()
    for db in resolve_scans([Path(REAL)])[:8]:
        s = load_scan(db, ref.signal_columns)
        z = F.standardize(ref, F.raw_features(ref, s.loc, s.complexity, s.args, s.keyword_density, s.signals))
        idx, _ = F.engine_archetypes(ref, z)
        mine = [ref.archetype_names[i] for i in idx]
        labelled = [(a, b) for a, b in zip(mine, s.engine_archetype, strict=True) if b]
        assert labelled, db
        agree = sum(a == b for a, b in labelled) / len(labelled)
        assert agree == 1.0, f"{db.name}: {agree:.4f}"
