"""Tests for tools/export_tilt.py: plane fit with known answers (tilt and downhill direction)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import export_tilt  # noqa: E402

N = 269   # same grid as the real terrain files
L = 30.0
R = 4000.0
SEED = 20261115


def disk_height(a: float, b: float, c: float = 0.0, noise: np.ndarray | None = None) -> np.ndarray:
    """z = a x + b y + c inside the disk, NaN outside (as in height.bin)."""
    x, y = export_tilt.disk_coordinates(N, L)
    z = a * x + b * y + c
    if noise is not None:
        z = z + noise
    z[np.hypot(x, y) > R] = np.nan
    return z


def symmetric_noise(sigma: float) -> np.ndarray:
    """Noise even under point reflection (value at p equals value at -p): orthogonal to x and y,
    so it adds no slope bias on this symmetric grid."""
    rng = np.random.default_rng(SEED)
    e = rng.normal(0.0, sigma, size=(N, N))
    return (e + e[::-1, ::-1]) / 2.0


def angle_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def test_plane_east_slope_2deg_goes_west():
    # z = x tan(2 deg): rises to the east, so it drains west (270)
    h = disk_height(math.tan(math.radians(2.0)), 0.0)
    out = export_tilt.tilt_fields(*export_tilt.fit_plane(h, L, R))
    assert abs(out["tilt_deg"] - 2.00) < 0.005
    assert out["downhill"] == "W"
    assert abs(out["downhill_azimuth_deg"] - 270.0) < 0.05
    assert out["rms_residual_m"] < 1e-6


def test_plane_north_slope_1deg_goes_south():
    # z = y tan(1 deg): rises to the north, so it drains south (180)
    h = disk_height(0.0, math.tan(math.radians(1.0)))
    out = export_tilt.tilt_fields(*export_tilt.fit_plane(h, L, R))
    assert abs(out["tilt_deg"] - 1.00) < 0.005
    assert out["downhill"] == "S"
    assert abs(out["downhill_azimuth_deg"] - 180.0) < 0.05


def test_plane_with_symmetric_noise_within_005_deg():
    # Downhill towards azimuth 60 (ENE): (-a, -b) = s (sin 60, cos 60), s = tan 2 deg
    s = math.tan(math.radians(2.0))
    a, b = -s * math.sin(math.radians(60.0)), -s * math.cos(math.radians(60.0))
    h = disk_height(a, b, c=35.0, noise=symmetric_noise(0.5))
    out = export_tilt.tilt_fields(*export_tilt.fit_plane(h, L, R))
    assert abs(out["tilt_deg"] - 2.0) <= 0.05
    assert angle_diff(out["downhill_azimuth_deg"], 60.0) <= 0.05
    assert out["downhill"] == "NE"  # 60 deg is nearest to NE (45) on the 8-point rose
    assert out["rms_residual_m"] > 0.1  # the noise is really there


def test_flat_terrain_has_zero_tilt_and_no_direction():
    h = disk_height(0.0, 0.0, c=12.0)
    out = export_tilt.tilt_fields(*export_tilt.fit_plane(h, L, R))
    assert out["tilt_deg"] == 0.0
    assert out["downhill"] is None
    assert out["downhill_azimuth_deg"] is None
    assert out["rms_residual_m"] < 1e-9
