"""Oracles for pipelines/moon_base.py: one synthetic raster with a known value per rule.

Run: .venv/Scripts/python.exe -m pytest -q tests/test_moon_base.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from rasterio.transform import Affine

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "pipelines"))

import moon_base as MB  # noqa: E402

PIX = 120.0  # m, the PGDA 75S product resolution
# grid of 60 x 60 pixels, pixel centre (i, j) at x = -3600 + (j + 0.5) * 120 (cols), y = 3600 - (i + 0.5) * 120 (rows)
T = Affine(PIX, 0.0, -3600.0, 0.0, -PIX, 3600.0)
SHAPE = (60, 60)


def centre_of_pixel(row: int, col: int) -> tuple[float, float]:
    """World coordinates of a pixel centre (the disk centre used in the tests)."""
    return T.c + (col + 0.5) * T.a, T.f + (row + 0.5) * T.e


def test_scale_values_applies_gdal_scale_offset_and_nodata():
    raw = np.array([[10000, -32768], [20000, 0]], dtype=np.int16)
    out = MB.scale_values(raw, 4e-5, 0.0, -32768.0)
    assert out[0, 0] == pytest.approx(0.4, abs=1e-7)  # 10000 x 4e-5 = 40 %
    assert np.isnan(out[0, 1])  # nodata becomes NaN
    assert out[1, 0] == pytest.approx(0.8, abs=1e-7)
    psr_raw = np.array([[20000, -20000]], dtype=np.int16)
    psr = MB.scale_values(psr_raw, 2.5e-5, 0.5, None)
    assert psr[0, 0] == pytest.approx(1.0, abs=1e-6)  # PSR
    assert psr[0, 1] == pytest.approx(0.0, abs=1e-6)  # not PSR


def test_disk_mean_and_max_equal_brute_force_oracle():
    """Inside the 4 km-style disk (R = 900 m here) the values are a known pattern; outside they must be ignored."""
    rng = np.random.default_rng(20261114)
    values = rng.uniform(0.0, 1.0, SHAPE).astype(np.float32)
    x, y = centre_of_pixel(30, 30)
    R = 900.0
    # brute-force oracle: loop over every pixel centre
    inside = []
    for i in range(SHAPE[0]):
        for j in range(SHAPE[1]):
            cx, cy = centre_of_pixel(i, j)
            if math.hypot(cx - x, cy - y) <= R:
                inside.append(float(values[i, j]))
    got = MB.disk_stats(values, T, x, y, R)
    assert got["n_disk"] == len(inside)
    assert got["n_valid"] == len(inside)
    assert got["mean"] == pytest.approx(sum(inside) / len(inside), abs=1e-9)
    assert got["max"] == pytest.approx(max(inside), abs=1e-9)


def test_disk_of_constant_field_gives_exact_mean_and_max():
    """Known value: 25 % inside the disk, 90 % outside. The mean must be exactly 0.25 and the max 0.25."""
    values = np.full(SHAPE, 0.9, dtype=np.float32)
    x, y = centre_of_pixel(30, 30)
    R = 600.0
    for i in range(SHAPE[0]):
        for j in range(SHAPE[1]):
            cx, cy = centre_of_pixel(i, j)
            if math.hypot(cx - x, cy - y) <= R:
                values[i, j] = 0.25
    got = MB.disk_stats(values, T, x, y, R)
    assert got["mean"] == pytest.approx(0.25, abs=1e-12)
    assert got["max"] == pytest.approx(0.25, abs=1e-12)


def test_psr_nearest_distance_is_exact_for_a_known_offset():
    """One PSR pixel at (3600 m east, 4800 m south) of the centre: the distance is 6000 m exactly."""
    psr = np.zeros(SHAPE, dtype=bool)
    x, y = centre_of_pixel(10, 10)
    psr[10 + 40, 10 + 30] = True  # rows grow southward: +40 rows = -4800 m; +30 cols = +3600 m
    got = MB.psr_stats(psr, T, x, y, 4000.0)
    assert got["nearest_m"] == pytest.approx(6000.0, abs=1e-6)


def test_psr_area_inside_disk_counts_only_pixels_in_the_disk():
    """A 3 x 3 PSR block at the centre is inside the disk (area 9 pixels); a PSR far away is not counted."""
    psr = np.zeros(SHAPE, dtype=bool)
    psr[29:32, 29:32] = True  # block centred on pixel (30, 30)
    psr[5, 5] = True  # far outside a 600 m disk
    x, y = centre_of_pixel(30, 30)
    got = MB.psr_stats(psr, T, x, y, 600.0)
    assert got["area_km2"] == pytest.approx(9 * PIX * PIX / 1e6, rel=1e-12)  # 0.1296 km2
    assert got["nearest_m"] == pytest.approx(0.0, abs=1e-9)  # the centre pixel itself is PSR


def test_site_outside_the_product_is_not_polar_and_forces_no_values():
    rec = MB.site_record(None, None, "centre note", None)
    assert rec["notes"] == "not polar, constant day/night cycle"
    assert rec["illum_mean_pct"] is None and rec["psr_area_km2"] is None and rec["earth_vis_pct"] is None
    # a disk that touches the edge of the valid circle is not usable either
    assert MB.inside_product(MB.PRODUCT_HALF_WIDTH_M - MB.DISK_RADIUS_M + 1.0, 0.0, MB.DISK_RADIUS_M) is False
    assert MB.inside_product(0.0, 0.0, MB.DISK_RADIUS_M) is True
