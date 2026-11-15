"""Oracles for analog.core.light (STANDARDS 10.15, P-S light and P-S1 local horizon). Run: pytest -q tests/test_light.py

Discretisation note: the sample grid has 72 x 144 points, so a share of samples is quantised in steps of
100 / 10368 % per sample pair along the grid axes. The equator and pole oracles are therefore checked to within one
sample step of the grid share on the sun_time_pct axis (100/144 % at the equator, 100/72 % at the pole), because the
sunrise instants fall exactly on sample points where e == 0 and sun_time_pct counts only e > 0.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from analog.core import light as L

R_MOON = 1737400.0  # m, STANDARDS section 2
PIXEL = 10.0  # m, synthetic DEM grid


def test_shape_and_range_of_samples():
    elev = L.sun_samples(40.0, 23.44)
    assert elev.shape == (L.N_YEAR, L.N_HOUR) == (72, 144)
    assert np.all(elev <= 90.0) and np.all(elev >= -90.0)


def test_equator_zero_obliquity_is_half_sunlit_and_noon_90():
    elev = L.sun_samples(0.0, 0.0)
    assert L.noon_sun_max_deg(0.0, 0.0) == pytest.approx(90.0)
    assert L.sun_time_pct(elev) == pytest.approx(50.0, abs=100.0 / 144.0)


@pytest.mark.parametrize("phi", [-60.0, -20.0, 0.0, 33.3, 45.0, 85.0])
def test_zero_obliquity_any_latitude_is_half_sunlit(phi):
    elev = L.sun_samples(phi, 0.0)
    assert L.sun_time_pct(elev) == pytest.approx(50.0, abs=100.0 / 144.0)


def test_pole_with_obliquity_is_half_sunlit_and_noon_max_is_obliquity():
    elev = L.sun_samples(90.0, 23.44)
    assert L.sun_time_pct(elev) == pytest.approx(50.0, abs=100.0 / 72.0)
    assert L.noon_sun_max_deg(90.0, 23.44) == pytest.approx(23.44, abs=1e-12)
    assert elev[:, 0].max() == pytest.approx(23.44, abs=1e-9)


@pytest.mark.parametrize(
    "phi, eps",
    [(10.0, 23.44), (40.0, 23.44), (-30.0, 25.19), (-86.764, 1.54), (0.0, 23.44), (-85.4381, 1.54), (60.0, 1.54)],
)
def test_closed_forms_equal_sampled_noon_extremes_within_one_step(phi, eps):
    noon = L.sun_samples(phi, eps)[:, 0]
    step = float(np.max(np.abs(np.diff(noon))))
    assert abs(noon.max() - L.noon_sun_max_deg(phi, eps)) <= step + 1e-9
    assert abs(noon.min() - L.noon_sun_min_deg(phi, eps)) <= step + 1e-9


def test_flat_plane_horizon_is_curvature_dip():
    n = 1501
    centre = (n // 2, n // 2)
    dem = np.full((n, n), 100.0)
    hz = L.horizon_profile(dem, PIXEL, centre, R_MOON)
    assert hz.shape == (36,)
    # z = z0 everywhere: max over d of atan(-(2 + d^2 / 2R) / d), optimum at d = 2 sqrt(R), value -atan(2 / sqrt(R))
    expected = -math.degrees(math.atan(2.0 / math.sqrt(R_MOON)))
    assert expected < 0.0
    assert np.allclose(hz, expected, rtol=0.0, atol=1e-6)


def test_wall_of_known_height_at_known_distance():
    n = 601  # R_array = 3000 m, centre index 300
    centre = (n // 2, n // 2)
    dem = np.zeros((n, n))
    # band of rows 190..200 at 50 m: the nearest wall pixel on the north ray is row 200, distance (300 - 200) * 10 = 1000 m
    dem[190:201, :] = 50.0
    hz = L.horizon_profile(dem, PIXEL, centre, R_MOON)
    d_wall = 1000.0
    expected_north = math.degrees(math.atan((50.0 - 2.0 - d_wall**2 / (2.0 * R_MOON)) / d_wall))
    assert hz[0] == pytest.approx(expected_north, abs=1e-6)
    # east ray (azimuth 90, index 9) does not cross the band: flat-plane curvature dip, same as the flat-plane oracle
    assert hz[9] == pytest.approx(-math.degrees(math.atan(2.0 / math.sqrt(R_MOON))), abs=1e-6)


def test_horizon_undefined_centre_raises():
    dem = np.full((51, 51), np.nan)
    with pytest.raises(ValueError):
        L.horizon_profile(dem, PIXEL, (25, 25), R_MOON)


def test_relief_with_zero_horizon_equals_sun_time():
    elev, az = L.sun_geometry(-30.0, 23.44)
    zero = np.zeros(L.N_AZ)
    assert L.sun_time_relief_pct(elev, az, zero) == pytest.approx(L.sun_time_pct(elev), abs=1e-12)


def test_relief_is_nan_when_horizon_undefined():
    elev, az = L.sun_geometry(-30.0, 23.44)
    hz = np.zeros(L.N_AZ)
    hz[5] = np.nan
    assert math.isnan(L.sun_time_relief_pct(elev, az, hz))


def test_grazing_equator_zero_obliquity_matches_closed_count():
    elev = L.sun_samples(0.0, 0.0)  # sin e = cos H; grazing when 0 < cos H < sin 10 deg
    hour = 2.0 * np.pi * np.arange(L.N_HOUR) / L.N_HOUR
    # with eps = 0 every year row is identical, so the share over all samples equals the share over one row
    c = np.cos(hour)
    c = np.where(np.abs(c) < 1e-12, 0.0, c)  # exact zeros (H = 90, 270 deg) are zero in exact arithmetic
    expected = 100.0 * np.count_nonzero((c > 0) & (c < math.sin(math.radians(10.0)))) / L.N_HOUR
    assert L.grazing_pct(elev) == pytest.approx(expected, abs=1e-9)
