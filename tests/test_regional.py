"""Regional scale (STANDARDS 10.10, EXPERIMENTAL): the 400 m config reproduces the plane oracle through measure.features."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from analog.core import measure as ms

ROOT = Path(__file__).resolve().parents[1]


def test_plane_10deg_oracle_at_400m_regional_grid():
    """Plane z = x tan(10 deg) on the regional grid (L = 400 m, R = 16 km, n = 81): slope_p95 = 10 deg,
    coherence = 1, hurst = 1 (STANDARDS 5 closed forms), through measure.features with config/measure_regional.json."""
    cfg = json.loads((ROOT / "config" / "measure_regional.json").read_text(encoding="utf-8"))
    L = float(cfg["grid"]["L_m"])
    R = float(cfg["grid"]["R_m"])
    assert (L, R) == (400.0, 16000.0)
    assert all(spec["sigma"] is None for spec in cfg["features"].values())

    n = 2 * math.ceil(R / L) + 1
    assert n == 81
    half = n // 2
    rows, cols = np.mgrid[0:n, 0:n]
    x = (cols - half) * L
    y = (half - rows) * L
    mask = np.hypot(x, y) <= R + 1e-9
    z = x * math.tan(math.radians(10.0))

    vec = ms.features(z, mask, L, cfg)
    assert vec["slope_p95_deg"] == pytest.approx(10.0, abs=1e-9)
    assert vec["coherence"] == pytest.approx(1.0, abs=1e-9)
    assert vec["hurst"] == pytest.approx(1.0, abs=1e-9)
