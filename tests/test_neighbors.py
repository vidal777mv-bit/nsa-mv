"""Tests for analog.core.neighbors (STANDARDS 10.14 P-N): exact knn and ties against brute force, plus the required
200-query exactness sample on the real frozen data (skipped when the derived inputs are not present)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "pipelines"))

from analog.core import neighbors as nb  # noqa: E402
import neighbors as PN  # noqa: E402

SEED = 20261114
SIGMA = np.array([3.0, 0.06, 0.2])
WEIGHTS = np.ones(3)
FEATS = ["slope_p95_deg", "hi", "hurst"]   # same order as SIGMA
THR = {"rugged": 0.5, "flat": 0.5}


def _pool(n: int = 300, seed: int = SEED) -> np.ndarray:
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 3)) * np.array([4.0, 0.1, 0.3]) + np.array([10.0, 0.4, 0.6])
    return X


def test_standardise_divides_by_sigma_and_keeps_nan():
    X = np.array([[3.0, 0.06, 0.2], [np.nan, 0.0, 0.4]])
    Z = nb.standardise(X, SIGMA)
    assert np.allclose(Z[0], [1.0, 1.0, 1.0])
    assert np.isnan(Z[1, 0]) and Z[1, 2] == pytest.approx(2.0)


def test_standardise_rejects_bad_sigma():
    with pytest.raises(ValueError):
        nb.standardise(np.zeros((2, 3)), [1.0, 0.0, 1.0])
    with pytest.raises(ValueError):
        nb.standardise(np.zeros((2, 3)), [1.0, np.nan, 1.0])


def test_valid_rows_and_build_tree_refuse_nan():
    Z = nb.standardise(np.array([[1.0, 1.0, 1.0], [np.nan, 1.0, 1.0]]), SIGMA)
    assert nb.valid_rows(Z).tolist() == [True, False]
    with pytest.raises(ValueError):
        nb.build_tree(Z)
    with pytest.raises(ValueError):
        nb.build_tree(np.empty((0, 3)))


def test_knn_matches_brute_force_on_seeded_queries():
    X = _pool()
    Z = nb.standardise(X, SIGMA)
    tree = nb.build_tree(Z)
    rng = np.random.default_rng(SEED)
    for _ in range(40):
        xq = X[rng.integers(0, len(X))] + rng.normal(size=3) * np.array([1.0, 0.01, 0.05])
        idx, D = nb.knn(tree, nb.standardise(xq, SIGMA), 10)
        bidx, bD = nb.brute_knn(X, xq, SIGMA, WEIGHTS, 10)
        assert idx.tolist() == bidx.tolist()
        assert np.max(np.abs(D - bD)) <= 1e-12


def test_knn_tie_order_is_by_index():
    """Duplicated rows are exact ties: the tree must return them in ascending index order."""
    base = np.array([[10.0, 0.4, 0.6]])
    X = np.vstack([np.repeat(base, 5, axis=0), _pool(50)])
    tree = nb.build_tree(nb.standardise(X, SIGMA))
    idx, D = nb.knn(tree, nb.standardise(base[0], SIGMA), 5)
    assert idx.tolist() == [0, 1, 2, 3, 4]
    assert np.allclose(D, 0.0)
    bidx, _ = nb.brute_knn(X, base[0], SIGMA, WEIGHTS, 5)
    assert idx.tolist() == bidx.tolist()


def test_knn_batch_shape_and_k_larger_than_pool():
    X = _pool(6)
    tree = nb.build_tree(nb.standardise(X, SIGMA))
    idx, D = nb.knn(tree, nb.standardise(X[:4], SIGMA), 10)
    assert idx.shape == (4, 6) and D.shape == (4, 6)
    assert np.all(np.diff(D, axis=1) >= 0)
    assert idx[0, 0] == 0 and D[0, 0] == pytest.approx(0.0, abs=1e-15)


def test_knn_and_ties_refuse_nan_query_and_bad_threshold():
    tree = nb.build_tree(nb.standardise(_pool(20), SIGMA))
    with pytest.raises(ValueError):
        nb.knn(tree, np.array([np.nan, 0.0, 0.0]), 3)
    with pytest.raises(ValueError):
        nb.ties(tree, np.zeros(3), -1.0)
    with pytest.raises(ValueError):
        nb.knn(tree, np.zeros(2), 3)


def test_ties_are_the_rows_within_threshold_sorted_by_d_then_index():
    X = _pool(200)
    tree = nb.build_tree(nb.standardise(X, SIGMA))
    xq = X[7] + np.array([0.3, 0.005, 0.02])
    thr = 0.4
    tidx, tD = nb.ties(tree, nb.standardise(xq, SIGMA), thr)
    bidx, bD = nb.brute_knn(X, xq, SIGMA, WEIGHTS, len(X))
    keep = bD <= thr
    assert tidx.tolist() == bidx[keep].tolist()
    assert np.max(np.abs(tD - bD[keep])) <= 1e-12
    assert np.all(tD <= thr)


def test_ties_empty_when_nearest_is_beyond_threshold():
    """Empty tie set = the Earth gap (nearest D > threshold)."""
    X = _pool(100)
    tree = nb.build_tree(nb.standardise(X, SIGMA))
    far = X.mean(axis=0) + np.array([200.0, 0.0, 0.0])
    tidx, _ = nb.ties(tree, nb.standardise(far, SIGMA), 0.5)
    _, D = nb.knn(tree, nb.standardise(far, SIGMA), 1)
    assert tidx.size == 0
    assert D[0] > 0.5


def test_brute_knn_formula_matches_the_standards_definition():
    X = np.array([[13.0, 0.46, 0.8], [10.0, 0.4, 0.6]])
    q = np.array([10.0, 0.4, 0.6])
    _, D = nb.brute_knn(X, q, SIGMA, WEIGHTS, 2)
    expect = np.sqrt(((13.0 - 10.0) / 3.0) ** 2 / 3 + ((0.46 - 0.4) / 0.06) ** 2 / 3 + ((0.8 - 0.6) / 0.2) ** 2 / 3)
    assert D[1] == pytest.approx(expect, rel=1e-12)
    assert D[0] == pytest.approx(0.0, abs=1e-15)


def _engine(X: np.ndarray, nasadem: np.ndarray) -> PN.Engine:
    n = len(X)
    return PN.engine_from_arrays(
        cfg={}, feats=FEATS, sigma=SIGMA, weights=WEIGHTS, flat_below=3.0, thr=THR,
        pool_ids=[f"pool_{i:05d}" for i in range(n)], pool_lat=np.zeros(n), pool_lon=np.zeros(n),
        pool_X=X, pool_near=np.zeros(n, dtype=bool), pool_nasadem=nasadem)


def _q(x, tree: str = "all") -> dict:
    return {"id": "q", "features": dict(zip(FEATS, map(float, x))), "tree": tree}


def test_nasadem_band_equals_all_pool_when_every_window_is_nasadem():
    X = _pool(300)
    eng = _engine(X, np.ones(300, dtype=bool))
    rng = np.random.default_rng(SEED)
    for _ in range(60):
        x = X[rng.integers(0, 300)] + rng.normal(size=3) * np.array([1.0, 0.01, 0.05])
        for tree in ("all", "tgt"):
            got = PN.query_one(_q(x, tree), eng)
            assert got["d_nearest_nasadem"] == got["d_nearest"]
            assert got["gap_nasadem"] == got["gap"]
    got = PN.query_one(_q([np.nan, 0.4, 0.6]), eng)
    assert got["d_nearest_nasadem"] is None and got["gap_nasadem"] is None


def test_copdem_window_closes_the_all_pool_gap_but_not_the_nasadem_gap():
    x = np.array([10.0, 0.4, 0.6])                   # rugged query (slope >= 3 deg): threshold 0.5
    far = _pool(100) + np.array([200.0, 0.0, 0.0])   # NASADEM windows far from the query
    X = np.vstack([far, x[None, :]])                 # last row: a copdem window at the query point
    eng = _engine(X, np.r_[np.ones(100, dtype=bool), False])
    for tree in ("all", "tgt"):
        got = PN.query_one(_q(x, tree), eng)
        assert got["d_nearest"] == 0.0 and got["gap"] is False
        assert got["d_nearest_nasadem"] > THR["rugged"] and got["gap_nasadem"] is True


def test_sensor_rule_and_empty_nasadem_band():
    assert PN.is_nasadem({"sensor": "nasadem"}) and PN.is_nasadem({})
    assert not PN.is_nasadem({"sensor": "copdem"})
    eng = _engine(_pool(50), np.zeros(50, dtype=bool))
    assert eng.tree_nas_all is None and eng.tree_nas_tgt is None
    got = PN.query_one(_q([10.0, 0.4, 0.6]), eng)
    assert got["d_nearest_nasadem"] is None and got["gap_nasadem"] is True


def _real_inputs_present() -> bool:
    d = HERE / "data" / "derived"
    return (d / "measure" / "pool__pool_00001.json").exists() and (d / "validation" / "noise_v1.3.json").exists() \
        and (HERE / "site" / "data" / "atlas" / "mars_cells.json").exists()


@pytest.mark.skipif(not _real_inputs_present(), reason="real derived inputs not present")
def test_exactness_sample_200_queries_on_real_data():
    """Required test (STANDARDS 10.14): seeded 200 queries (16 targets, 84 Mars cells, 100 pool windows);
    indices (tie order included), D to 1e-12 and tie sets identical to brute force."""
    import neighbors as PN
    from _common import make_paths

    paths = make_paths(None, False)
    eng = PN.build_engine(paths)
    targets, cells = PN.load_queries(paths)
    res = PN.exactness_sample(eng, targets, cells)
    assert res["n_queries"] == 200
    assert res["index_mismatch"] == 0, res["index_mismatch_ids"]
    assert res["max_abs_D_diff"] <= 1e-12
    assert res["tie_set_mismatch"] == 0, res["tie_set_mismatch_ids"]
