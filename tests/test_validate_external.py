"""Tests for pipelines/validate_external.py: closed-form oracles for D, the mid-rank percentile, the sensor bands,
the relief rule and the verdict rule. Synthetic values only; no raw data is read.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "pipelines"))

import validate_external as ve  # noqa: E402

SIG = {"slope_p95_deg": 3.0, "hi": 0.06, "hurst": 0.2}


def test_identical_window_gives_D_zero_and_percentile_zero():
    """Oracle 1: a window identical to the target has D = 0; no pool window is closer, so the percentile is 0."""
    a = {"slope_p95_deg": 6.5, "hi": 0.42, "hurst": 0.71}
    d = ve.dist(a, dict(a), SIG)
    assert d == 0.0
    pool = np.array([0.3, 0.9, 1.7, 2.2])  # every pool window is strictly farther than 0
    assert ve.pct_midrank(pool, d) == 0.0


def test_known_offset_gives_D_equal_to_s_over_sqrt3():
    """Oracle 2: an offset of s sigma on one axis gives D = s / sqrt(3) exactly (D = ||dz|| / sqrt(K), K = 3)."""
    b = {"slope_p95_deg": 5.0, "hi": 0.5, "hurst": 0.8}
    for s in (0.5, 1.0, 2.0):
        a = dict(b)
        a["slope_p95_deg"] = b["slope_p95_deg"] + s * SIG["slope_p95_deg"]
        assert math.isclose(ve.dist(a, b, SIG), s / math.sqrt(3.0), rel_tol=1e-12)


def test_missing_feature_returns_none():
    """A null in-distance feature means no D (the pool drops such rows; the pair is not scored)."""
    a = {"slope_p95_deg": 5.0, "hi": None, "hurst": 0.8}
    b = {"slope_p95_deg": 5.0, "hi": 0.5, "hurst": 0.8}
    assert ve.dist(a, b, SIG) is None


def test_percentile_known_distribution_exact():
    """Oracle 3: pool 1..10. Strictly between values give 50 and the ends give 0 and 100 (mid-rank)."""
    pool = np.arange(1.0, 11.0)
    assert ve.pct_midrank(pool, 5.5) == 50.0
    assert ve.pct_midrank(pool, 0.5) == 0.0
    assert ve.pct_midrank(pool, 11.0) == 100.0


def test_percentile_midrank_with_ties_exact():
    """Oracle 4: pool [1, 2, 2, 3, 4], d = 3: below = 3 (1, 2, 2), equal = 1 -> (3 + 0.5) / 5 = 70 %."""
    pool = np.array([1.0, 2.0, 2.0, 3.0, 4.0])
    assert ve.pct_midrank(pool, 3.0) == 70.0


def test_wilcoxon_all_below_median_exact():
    """Oracle 5: six percentiles all equal to 10 -> every difference is -40, W+ = 0; one-sided exact p = 1/2^6."""
    p = ve.wilcoxon_p_less([10.0] * 6)
    assert math.isclose(p, 1.0 / 64.0, rel_tol=1e-9)


def test_sensor_bands():
    """NASADEM up to 60 N (and from 56 S); Copernicus 60 to 84 N; outside both -> None."""
    assert ve.sensor_for_lat(35.0) == "nasadem"
    assert ve.sensor_for_lat(60.0) == "nasadem"
    assert ve.sensor_for_lat(60.1) == "copdem"
    assert ve.sensor_for_lat(64.85) == "copdem"
    assert ve.sensor_for_lat(-77.5) is None


def test_relief_rule_equal_threshold_is_rugged():
    """STANDARDS 10.11: slope_p95 >= 3 deg is rugged (equal counts as rugged), below 3 deg is flat."""
    assert ve.relief_of(3.0, 3.0) == "rugged"
    assert ve.relief_of(2.99, 3.0) == "flat"


def test_verdict_rule_fewer_than_six_pairs_is_insufficient():
    """PREREG 5: with five valid pairs the verdict is 'insufficient' whatever the numbers say."""
    assert ve.verdict_of(5, 5.0, 0.001) == "insufficient"
    assert ve.verdict_of(6, 20.0, 0.01) == "PASS"
    assert ve.verdict_of(6, 30.0, 0.01) == "FAIL"
    assert ve.verdict_of(6, 20.0, 0.2) == "FAIL"
