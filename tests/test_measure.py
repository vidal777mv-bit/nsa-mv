"""Tests for analog.core.measure: feature vector and distance (STANDARDS.md section 4 and 5)."""

from __future__ import annotations

import copy
import math

import numpy as np
import pytest

from analog.core import measure as ms

SEED = 20261114


def _cfg_with_sigmas(cfg: dict, sigma: float = 1.0) -> dict:
    """Copy of measure.json with every feature sigma set to an explicit value (tests only)."""
    out = copy.deepcopy(cfg)
    for spec in out["features"].values():
        spec["sigma"] = sigma
    return out


def test_features_returns_six_keys_on_plane(synth, measure_cfg):
    """features() returns the six feature ids; plane values are the closed forms of section 5."""
    cfg = _cfg_with_sigmas(measure_cfg)
    vec = ms.features(synth.plane(10.0), synth.disk, synth.L, cfg)
    assert set(vec) == set(ms.FEATURE_IDS)
    assert vec["slope_p95_deg"] == pytest.approx(10.0, abs=1e-9)
    assert vec["coherence"] == pytest.approx(1.0, abs=1e-9)
    assert vec["hurst"] == pytest.approx(1.0, abs=1e-9)
    assert vec["hi"] == pytest.approx(0.5, abs=0.01)
    assert vec["ridge_pct"] == pytest.approx(0.0, abs=1e-9)
    assert vec["valley_pct"] == pytest.approx(0.0, abs=1e-9)


def test_features_flat_has_null_hurst_and_hi(synth, measure_cfg):
    """Flat surface: hurst and hi are null, the others follow the closed form."""
    cfg = _cfg_with_sigmas(measure_cfg)
    vec = ms.features(synth.flat(50.0), synth.disk, synth.L, cfg)
    assert vec["hurst"] is None
    assert vec["hi"] is None
    assert vec["slope_p95_deg"] == pytest.approx(0.0, abs=1e-12)
    assert vec["coherence"] == 0.0
    assert vec["ridge_pct"] == 0.0
    assert vec["valley_pct"] == 0.0


def test_features_requires_config_keys(synth, measure_cfg):
    """No silent defaults: a config without the TPI section raises KeyError."""
    cfg = _cfg_with_sigmas(measure_cfg)
    del cfg["tpi"]
    with pytest.raises(KeyError):
        ms.features(synth.plane(10.0), synth.disk, synth.L, cfg)


def _vec(rng: np.random.Generator) -> dict[str, float]:
    """Random feature vector with all six features non-null."""
    return {
        "slope_p95_deg": float(rng.uniform(0, 30)),
        "hi": float(rng.uniform(0, 1)),
        "coherence": float(rng.uniform(0, 1)),
        "hurst": float(rng.uniform(0.1, 1.2)),
        "ridge_pct": float(rng.uniform(0, 50)),
        "valley_pct": float(rng.uniform(0, 50)),
    }


def _random_features_cfg(rng: np.random.Generator) -> dict[str, dict[str, float]]:
    names = ms.FEATURE_IDS
    return {
        name: {"weight": float(rng.uniform(0.2, 3.0)), "sigma": float(rng.uniform(0.5, 10.0))} for name in names
    }


def test_distance_closed_form_hand_example():
    """Hand value: weights (1, 2, 1, 1), sigmas (1, 1, 2, 1), diffs (3, 0, 4, 1):
    num = 1*9 + 2*0 + 1*(4/2)^2 + 1*1 = 9 + 4 + 1 = 14; den = 5; D = sqrt(14/5)."""
    fcfg = {
        "slope_p95_deg": {"weight": 1.0, "sigma": 1.0},
        "hi": {"weight": 2.0, "sigma": 1.0},
        "coherence": {"weight": 1.0, "sigma": 2.0},
        "hurst": {"weight": 1.0, "sigma": 1.0},
    }
    a = {"slope_p95_deg": 3.0, "hi": 0.0, "coherence": 4.0, "hurst": 1.0}
    b = {"slope_p95_deg": 0.0, "hi": 0.0, "coherence": 0.0, "hurst": 0.0}
    assert ms.distance(a, b, fcfg) == pytest.approx(math.sqrt(14.0 / 5.0), abs=1e-12)


def test_distance_self_is_zero():
    """D(a, a) = 0."""
    rng = np.random.default_rng(SEED)
    fcfg = _random_features_cfg(rng)
    a = _vec(rng)
    assert ms.distance(a, a, fcfg) == pytest.approx(0.0, abs=1e-12)


def test_distance_symmetric():
    """D(a, b) = D(b, a) [1e-12]."""
    rng = np.random.default_rng(SEED)
    fcfg = _random_features_cfg(rng)
    for _ in range(50):
        a, b = _vec(rng), _vec(rng)
        assert ms.distance(a, b, fcfg) == pytest.approx(ms.distance(b, a, fcfg), abs=1e-12)


def test_distance_triangle_inequality_1000_random_triples():
    """Triangle inequality on 1000 seeded random triples (all features shared, so the weighted norm applies)."""
    rng = np.random.default_rng(SEED)
    fcfg = _random_features_cfg(rng)
    for _ in range(1000):
        a, b, c = _vec(rng), _vec(rng), _vec(rng)
        dab = ms.distance(a, b, fcfg)
        dbc = ms.distance(b, c, fcfg)
        dac = ms.distance(a, c, fcfg)
        assert dac <= dab + dbc + 1e-9


def test_distance_scales_inversely_with_sigma():
    """Scaling every sigma by s divides D by s [1e-9]."""
    rng = np.random.default_rng(SEED)
    fcfg = _random_features_cfg(rng)
    a, b = _vec(rng), _vec(rng)
    base = ms.distance(a, b, fcfg)
    for s in (0.5, 2.0, 7.3):
        scaled = {k: {"weight": v["weight"], "sigma": v["sigma"] * s} for k, v in fcfg.items()}
        assert ms.distance(a, b, scaled) == pytest.approx(base / s, abs=1e-9)


def test_distance_raises_when_sigma_not_calibrated():
    """sigma None in the config -> ValueError('sigma not calibrated')."""
    rng = np.random.default_rng(SEED)
    fcfg = _random_features_cfg(rng)
    fcfg["hi"]["sigma"] = None
    a, b = _vec(rng), _vec(rng)
    with pytest.raises(ValueError, match="sigma not calibrated"):
        ms.distance(a, b, fcfg)


def test_distance_null_when_fewer_than_four_shared():
    """Only 3 shared non-null features -> D is null; 4 shared -> a number."""
    fcfg = {k: {"weight": 1.0, "sigma": 1.0} for k in ms.FEATURE_IDS}
    full = {k: 1.0 for k in ms.FEATURE_IDS}
    three = {"slope_p95_deg": 2.0, "hi": 2.0, "coherence": 2.0, "hurst": None, "ridge_pct": None, "valley_pct": None}
    four = {"slope_p95_deg": 2.0, "hi": 2.0, "coherence": 2.0, "hurst": 2.0, "ridge_pct": None, "valley_pct": None}
    assert ms.distance(full, three, fcfg) is None
    assert ms.distance(full, four, fcfg) == pytest.approx(1.0, abs=1e-12)


def test_distance_null_feature_is_excluded_not_zeroed():
    """A null feature drops out of the sum and the weight total; it is not treated as 0."""
    fcfg = {k: {"weight": 1.0, "sigma": 1.0} for k in ms.FEATURE_IDS}
    a = {k: 0.0 for k in ms.FEATURE_IDS}
    b = {k: 2.0 for k in ms.FEATURE_IDS}
    b_null = dict(b, hurst=None)
    # all six shared: D = 2; five shared: sum = 5 * 4, den = 5 -> D = 2 again (equal differences)
    assert ms.distance(a, b, fcfg) == pytest.approx(2.0, abs=1e-12)
    assert ms.distance(a, b_null, fcfg) == pytest.approx(2.0, abs=1e-12)


def test_distance_ignores_weight_zero_features_in_D_and_in_shared_count():
    """Config v1.2: ridge_pct and valley_pct have weight 0 (redundancy rule). They never change D and never count
    toward min_shared_features: 3 shared weighted features + both weight-0 features shared -> None (not 5 shared)."""
    fcfg = {k: {"weight": 1.0, "sigma": 1.0} for k in ms.FEATURE_IDS}
    fcfg["ridge_pct"] = {"weight": 0.0, "sigma": 1.0}
    fcfg["valley_pct"] = {"weight": 0.0, "sigma": 1.0}
    a = {k: 0.0 for k in ms.FEATURE_IDS}
    b = {"slope_p95_deg": 2.0, "hi": 2.0, "coherence": 2.0, "hurst": None, "ridge_pct": 1e6, "valley_pct": -1e6}
    assert ms.distance(a, b, fcfg) is None  # shared weighted features = 3 < 4
    b4 = dict(b, hurst=2.0)  # 4 weighted features shared; the huge ridge/valley differences must not enter D
    assert ms.distance(a, b4, fcfg) == pytest.approx(2.0, abs=1e-12)
    b_ridge_only = dict(b4, ridge_pct=5e5)
    assert ms.distance(a, b_ridge_only, fcfg) == pytest.approx(2.0, abs=1e-12)


def test_relief_class_boundary_at_three_degrees():
    """STANDARDS 10.11: rugged when slope_p95_deg >= 3.0 (equal is rugged), flat below; null slope has no class."""
    assert ms.relief_class(3.0, 3.0) == "rugged"
    assert ms.relief_class(2.9999, 3.0) == "flat"
    assert ms.relief_class(12.5, 3.0) == "rugged"
    assert ms.relief_class(None, 3.0) is None
