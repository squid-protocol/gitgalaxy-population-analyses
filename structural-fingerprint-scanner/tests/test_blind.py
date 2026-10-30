import numpy as np
import pytest

from structural_fingerprint import blind as B
from structural_fingerprint.fingerprint import FunctionTable
from structural_fingerprint.subway import Taxonomy

SUBS = ["alpha", "beta", "gamma", "delta"]
TAX = Taxonomy("t", list(SUBS), basename_prefix=[("a_", "alpha"), ("b_", "beta"), ("g_", "gamma"), ("d_", "delta")])
N_ARCH = 3


def _graph(rng, sizes, p_in=0.12, p_out=0.01, chain=True):
    """Directed modular graph; block k calls block k+1 more than anything else."""
    lab = np.repeat(np.arange(len(sizes)), sizes)
    n = len(lab)
    e = []
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            same, nxt = lab[i] == lab[j], lab[j] == lab[i] + 1
            p = p_in if same else (0.04 if (chain and nxt) else p_out)
            if rng.random() < p:
                e.append((i, j))
    return lab, np.array(e, dtype=np.int64)


def _table(repo, lab, edges, rng, feat_shift=0.0, names=None, paths=None):
    n = len(lab)
    prefixes = ["a_", "b_", "g_", "d_"]
    vec = rng.normal(size=(n, 8)) * 0.6
    vec[:, 0] += lab * 0.8 + feat_shift  # size tracks the subsystem a little
    return FunctionTable(
        repo=repo,
        name=np.array(names if names is not None else [f"{prefixes[k]}fn{i}" for i, k in enumerate(lab)]),
        path=np.array(paths if paths is not None else [f"src/{prefixes[k]}file.c" for k in lab]),
        language=np.array(["c"] * n), loc=np.full(n, 20, dtype=np.int32),
        archetype=(lab % N_ARCH).astype(np.int16), key=np.arange(n, dtype=np.uint64),
        vectors=vec.astype(np.float32), edges=edges.astype(np.int32))


@pytest.fixture(scope="module")
def pair():
    rng = np.random.default_rng(3)
    lab, e = _graph(rng, [40, 30, 30, 20])
    ref = _table("ref", lab, e, rng)
    # The port: the same architecture regrown (new random graph, new measurements, a
    # language-level offset), its functions shuffled and renamed so nothing lines up by index.
    lab2, e2 = _graph(np.random.default_rng(4), [40, 30, 30, 20])
    perm = np.random.default_rng(5).permutation(len(lab2))
    inv = np.empty_like(perm)
    inv[perm] = np.arange(len(perm))
    port = _table("port", lab2[perm], inv[e2], np.random.default_rng(6), feat_shift=2.0)
    return ref, port, lab2[perm]


def _place(ref, port, params):
    _, rv = B.reference_context(ref, TAX)
    return B.place(B.blind_view(port), rv.view, rv.labels, len(TAX.subsystems), N_ARCH, params, len(port))


@pytest.mark.parametrize("method", ["fgw", "features"])
def test_recovers_architecture_above_null(pair, method):
    ref, port, truth = pair
    pl = _place(ref, port, B.BlindParams(method=method))
    acc = B.accuracy(pl.labels, truth)
    null = B.null_accuracy(pl.labels, truth, np.random.default_rng(0), 300)
    assert acc > null.mean() + 6 * null.std()
    if method == "fgw":
        assert acc > 0.7


def test_graph_alone_carries_placement(pair):
    """With no per-function measurements, the call-graph alignment still finds the blocks."""
    ref, port, truth = pair
    pl = _place(ref, port, B.BlindParams(use_measures=False))
    null = B.null_accuracy(pl.labels, truth, np.random.default_rng(0), 300)
    assert B.accuracy(pl.labels, truth) > null.mean() + 4 * null.std()


@pytest.mark.parametrize("method", ["fgw", "features"])
def test_blind_to_names_paths_and_row_order(pair, method):
    """Leakage guard: names and paths are never read, and the placement is
    permutation-equivariant, so the file-grouped row order cannot leak a path either."""
    ref, port, _ = pair
    p = B.BlindParams(method=method)
    base = _place(ref, port, p).labels
    garbled = FunctionTable(port.repo, np.array([f"x{i}" for i in range(len(port))]),
                            np.array(["zz/q.c"] * len(port)), port.language, port.loc, port.archetype, port.key,
                            port.vectors, port.edges)
    np.testing.assert_array_equal(_place(ref, garbled, p).labels, base)
    perm = np.random.default_rng(11).permutation(len(port))
    inv = np.empty_like(perm)
    inv[perm] = np.arange(len(perm))
    shuffled = FunctionTable(port.repo, port.name[perm], port.path[perm], port.language[perm], port.loc[perm],
                             port.archetype[perm], port.key[perm], port.vectors[perm], inv[port.edges])
    np.testing.assert_array_equal(_place(ref, shuffled, p).labels, base[perm])


def test_rewired_keeps_degrees(pair):
    _, port, _ = pair
    v = B.blind_view(port)
    g = B.rewired(v, np.random.default_rng(1))
    for c in (0, 1):
        np.testing.assert_array_equal(np.bincount(v.edges[:, c], minlength=v.n), np.bincount(g.edges[:, c], minlength=v.n))
    assert len({tuple(x) for x in g.edges.tolist()}) == len(g.edges)
    assert (g.edges[:, 0] != g.edges[:, 1]).all()
    assert len({tuple(x) for x in g.edges.tolist()} & {tuple(x) for x in v.edges.tolist()}) < 0.5 * len(v.edges)


def test_answer_key_sources(pair):
    ref, port, _ = pair
    ref_labels, _ = B.reference_context(ref, TAX)
    names = list(port.name)
    names[0] = str(ref.name[5])  # one name the reference has
    names[1] = "unmatched"
    paths = list(port.path)
    paths[1] = "src/b_thing.c"
    paths[2] = "misc/readme.c"
    names[2] = "nomatch"
    p2 = FunctionTable(port.repo, np.array(names), np.array(paths), port.language, port.loc, port.archetype,
                       port.key, port.vectors, port.edges)
    key, src = B.answer_key(p2, TAX, ref, ref_labels)
    assert src[0] == "name" and key[0] == ref_labels[5]
    assert src[1] == "path" and TAX.subsystems[key[1]] == "beta"
    assert src[2] == "fallback" and TAX.subsystems[key[2]] == TAX.fallback


def test_wiring_and_nulls():
    ref = np.array([[5.0, 1, 0], [0, 4, 2], [1, 0, 3]])
    assert B.wiring(ref, ref) == pytest.approx((1.0, 1.0))
    full, off = B.wiring(np.diag(np.diag(ref)), ref)
    assert full < 1 and np.isnan(off)  # a diagonal-only map has no cross-subsystem calls to compare
    labels = np.array([0, 0, 1, 1, 2, 2])
    edges = np.array([[0, 1], [1, 2], [2, 3], [3, 4], [4, 0]])
    nw = B.null_wiring(labels, edges, ref, np.random.default_rng(0), 50)
    assert nw["shuffle"].shape == (50, 2) and nw["rename"].shape == (50, 2)
    rng = np.random.default_rng(0)
    pred, key = rng.integers(0, 4, 4000), rng.integers(0, 4, 4000)
    assert B.null_accuracy(pred, key, rng, 200).mean() == pytest.approx(0.25, abs=0.02)


def test_evaluate_port_end_to_end(pair):
    ref, port, _ = pair
    # Names the reference does not have, so the answer key comes from the paths alone.
    port = FunctionTable(port.repo, np.array([f"q{i}" for i in range(len(port))]), port.path, port.language,
                         port.loc, port.archetype, port.key, port.vectors, port.edges)
    ref_labels, rv = B.reference_context(ref, TAX)
    r = B.evaluate_port(port, port, ref, ref_labels, rv, TAX, B.BlindParams(), None, N_ARCH, draws=200,
                        rewire_draws=1, ablations=B.ablations(B.BlindParams()))
    assert r["scored"] == len(port) and set(r["key_sources"]) == {"path"}
    assert r["accuracy"] > r["accuracy_null"]["p95"]
    assert set(r["ablations"]) >= {"graph_only", "measures_only", "knn"}
    assert 0 <= r["rewired"]["off"] <= 1
    assert r["balanced_accuracy"] > r["balanced_accuracy_null"]["p95"]


def test_lift_decision_spreads_votes(pair):
    """The lift rule divides each vote by the subsystem's reference share, so the largest
    subsystem no longer collects every diffuse vote."""
    ref, port, truth = pair
    arg = _place(ref, port, B.BlindParams(decision="argmax")).labels
    lift = _place(ref, port, B.BlindParams(decision="lift")).labels
    assert np.bincount(lift, minlength=4).max() <= np.bincount(arg, minlength=4).max()
    assert B.balanced_accuracy(lift, truth) > 0.5
    with pytest.raises(ValueError):
        _place(ref, port, B.BlindParams(decision="nope"))


def test_finite_json():
    assert B._finite({"a": float("nan"), "b": [np.float64(1.5), np.int64(2)]}) == {"a": None, "b": [1.5, 2]}
