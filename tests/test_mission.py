"""Closed-form tests for analog.core.mission (STANDARDS.md section 10.3). Run alone:
.venv/Scripts/python.exe -m pytest tests/test_mission.py
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from analog.core import mission

L = 100.0


def test_plane_10_deg_is_fully_within_limit_15(synth):
    """Plane z = x tan(10 deg): every defined slope is 10 deg, so the share within 15 deg is 100%."""
    z = synth.plane(10.0)
    slope = mission.slope_map_deg(z, synth.disk, L)
    defined = slope[np.isfinite(slope)]
    assert defined.size > 0
    assert np.allclose(defined, 10.0, atol=1e-9)
    res = mission.mission_share(slope, 15.0)
    assert res["pct"] == pytest.approx(100.0, abs=1e-9)
    assert res["n_below"] == res["n_defined"] == defined.size


def test_plane_10_deg_is_fully_outside_limit_5(synth):
    """Same plane with limit 5 deg: no defined slope is within the limit, so the share is 0%."""
    slope = mission.slope_map_deg(synth.plane(10.0), synth.disk, L)
    res = mission.mission_share(slope, 5.0)
    assert res["pct"] == pytest.approx(0.0, abs=1e-12)
    assert res["n_below"] == 0


def test_half_plane_step_has_known_share(synth):
    """Step surface z = tan(20 deg) max(x, 0) on the full 81 x 81 square, every pixel valid.

    Closed form of the central differences (L = 100 m, interior rows 1..79, columns 1..79):
    columns 1..39 (x < 0) have gx = 0 -> slope 0; column 40 (x = 0) has gx = tan(20)/2 -> slope 10.3 deg;
    columns 41..79 have gx = tan(20) -> slope 20 deg. Defined pixels: 79 x 79 = 6241.
    Limit 15: 40 columns (0 and 10.3 deg) are within -> 100 * 40 / 79 %.
    Limit 5: only the 39 flat columns are within -> 100 * 39 / 79 %. Limit 25: all -> 100 %.
    """
    n = 81
    half = n // 2
    cols = np.arange(n)
    x = (cols - half) * L
    row = np.tan(math.radians(20.0)) * np.maximum(x, 0.0)
    z = np.broadcast_to(row[None, :], (n, n)).copy()
    mask = np.ones((n, n), dtype=bool)
    slope = mission.slope_map_deg(z, mask, L)
    assert np.isfinite(slope).sum() == 79 * 79
    assert mission.mission_share(slope, 15.0)["pct"] == pytest.approx(100.0 * 40 / 79, abs=1e-9)
    assert mission.mission_share(slope, 5.0)["pct"] == pytest.approx(100.0 * 39 / 79, abs=1e-9)
    assert mission.mission_share(slope, 25.0)["pct"] == pytest.approx(100.0, abs=1e-9)


def test_share_on_hand_made_slopes():
    """Pure share on a hand-made array: 2 of 4 defined values <= 15, one NaN not counted."""
    s = np.array([0.0, 10.0, 20.0, 30.0, np.nan])
    res = mission.mission_share(s, 15.0)
    assert res["pct"] == pytest.approx(50.0)
    assert res["n_defined"] == 4
    assert res["n_below"] == 2


def test_missing_limit_gives_null_not_zero():
    """A missing limit returns pct None with a reason, never 0 (STANDARDS section 2)."""
    res = mission.mission_share(np.array([1.0, 2.0]), None)
    assert res["pct"] is None
    assert res["reason"] == "no limit"


def test_no_defined_slope_gives_null():
    """All-NaN slope array: pct None, reason says no defined slope."""
    res = mission.mission_share(np.full(5, np.nan), 10.0)
    assert res["pct"] is None
    assert res["reason"] == "no defined slope"
