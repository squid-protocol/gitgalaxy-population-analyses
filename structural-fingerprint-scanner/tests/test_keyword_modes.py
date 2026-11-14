import numpy as np
import pytest

from structural_fingerprint import features as F
from structural_fingerprint.reference import GEOMETRY_FEATURES, load_reference


def test_keyword_modes_behavior():
    ref = load_reference("structure")
    n_sig = len(ref.signal_columns)
    sig_start = len(GEOMETRY_FEATURES)

    # Row 0: tiny 2-LOC function with 1 hit in signal 0
    # Row 1: 20-LOC function with 10 hits in signal 0, 10 hits in signal 1
    # Row 2: 20-LOC function with 20 hits in signal 0, 20 hits in signal 1 (2x verbosity of row 1)
    loc = np.array([2.0, 20.0, 20.0])
    complexity = np.array([1.0, 5.0, 5.0])
    args = np.array([0.0, 2.0, 2.0])
    kd = np.array([0.5, 0.2, 0.4])
    signals = np.zeros((3, n_sig), dtype=np.float64)
    signals[0, 0] = 1.0
    signals[1, 0] = 10.0
    signals[1, 1] = 10.0
    signals[2, 0] = 20.0
    signals[2, 1] = 20.0

    dens = F.raw_features(ref, loc, complexity, args, kd, signals, keyword_mode="density")
    sm = F.raw_features(ref, loc, complexity, args, kd, signals, keyword_mode="smoothed_density", smoothing_k=5.0)
    pres = F.raw_features(ref, loc, complexity, args, kd, signals, keyword_mode="presence")
    cnt = F.raw_features(ref, loc, complexity, args, kd, signals, keyword_mode="counts")
    comp = F.raw_features(ref, loc, complexity, args, kd, signals, keyword_mode="composition")

    # Smoothed density prevents tiny 2-LOC functions from exploding like unsmoothed density
    assert sm[0, sig_start] < dens[0, sig_start]

    # Presence is strictly binary on signal columns
    assert np.all((pres[:, sig_start:] == 0.0) | (pres[:, sig_start:] == 1.0))
    assert pres[0, sig_start] == 1.0
    assert pres[1, sig_start] == 1.0

    # Counts use log1p(hits)
    assert np.isclose(cnt[0, sig_start], np.log1p(1.0))
    assert np.isclose(cnt[1, sig_start], np.log1p(10.0))

    # Composition is invariant to 2x uniform scaling of keyword hits
    assert np.allclose(comp[1, sig_start:], comp[2, sig_start:])
    assert np.isclose(comp[1, sig_start], 0.5)
    assert np.isclose(comp[1, sig_start + 1], 0.5)


def test_unknown_keyword_mode_raises():
    ref = load_reference("structure")
    with pytest.raises(ValueError, match="unknown keyword_mode"):
        F.raw_features(
            ref,
            np.array([10.0]),
            np.array([1.0]),
            np.array([0.0]),
            np.array([0.1]),
            np.zeros((1, len(ref.signal_columns))),
            keyword_mode="invalid",
        )
