"""Tests for pipelines/arctic_probe.py: the gap-closing logic (synthetic) and the Copernicus tile naming."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "pipelines"))

import arctic_probe as ap  # noqa: E402

SIGMA = np.array([3.0, 0.06, 0.2])


def test_gap_closure_synthetic_known_answer():
    """Three queries with a known answer: one inside the threshold, one exactly on it, one outside.

    Arctic windows are placed at known standardised offsets: D = ||dz|| / sqrt(3), so an offset of s sigma along one axis
    gives D = s / sqrt(3). Threshold 0.4150: s = 0.5 -> D 0.2887 (closed); on the boundary -> closed (<=); s = 1.0 ->
    D 0.5774 (gap stays).
    """
    thr = 0.4150468510682017
    s_edge = thr * np.sqrt(3.0)
    q = np.array([[10.0, 0.40, 0.60], [20.0, 0.50, 0.80], [30.0, 0.60, 0.90]])
    # Arctic windows: one per query at the offset along the slope axis, plus two far decoys
    a = np.array([
        [10.0 + 0.5 * SIGMA[0], 0.40, 0.60],
        [20.0 + s_edge * SIGMA[0], 0.50, 0.80],
        [30.0 + 1.0 * SIGMA[0], 0.60, 0.90],
        [100.0, 0.10, 0.10],
        [-50.0, 0.90, 0.99],
    ])
    out = ap.gap_closure(q, np.full(3, thr), a, SIGMA)
    assert np.allclose(out["d_arctic"], [0.5 / np.sqrt(3.0), thr, 1.0 / np.sqrt(3.0)], atol=1e-12)
    assert out["closed"].tolist() == [True, True, False]
    assert out["arctic_row"].tolist() == [0, 1, 2]


def test_gap_closure_matches_brute_force_and_uses_per_query_threshold():
    rng = np.random.default_rng(20261114)
    Xa = rng.normal(size=(120, 3)) * np.array([5.0, 0.1, 0.3]) + np.array([10.0, 0.5, 0.7])
    Xq = rng.normal(size=(40, 3)) * np.array([5.0, 0.1, 0.3]) + np.array([10.0, 0.5, 0.7])
    thr = np.where(np.arange(40) % 2 == 0, 0.4150468510682017, 1.1017189574465522)
    out = ap.gap_closure(Xq, thr, Xa, SIGMA)
    D = np.sqrt((((Xq[:, None, :] - Xa[None, :, :]) / SIGMA) ** 2).sum(-1) / 3.0)
    assert np.allclose(out["d_arctic"], D.min(axis=1), atol=1e-12)
    assert out["arctic_row"].tolist() == D.argmin(axis=1).tolist()
    assert out["closed"].tolist() == (D.min(axis=1) <= thr).tolist()


def test_gap_closure_empty_arctic_is_an_error_not_a_closure():
    import pytest

    with pytest.raises(ValueError):
        ap.gap_closure(np.zeros((1, 3)), np.array([0.4]), np.empty((0, 3)), SIGMA)


def test_cop_url_naming():
    u = ap.cop_url(75, -90)
    assert u.endswith("Copernicus_DSM_COG_10_N75_00_W090_00_DEM/Copernicus_DSM_COG_10_N75_00_W090_00_DEM.tif")
    assert "_N78_00_E016_" in ap.cop_url(78, 16)
