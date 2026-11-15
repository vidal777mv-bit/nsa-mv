"""Offline tests for pipelines/build_mars_pool.py (STANDARDS 10.13). No network, no raw data.

Run alone: .venv/Scripts/python.exe -m pytest tests/test_mars_pool.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
PIPES = HERE / "pipelines"
if str(PIPES) not in sys.path:
    sys.path.insert(0, str(PIPES))

import build_mars_pool as bmp  # noqa: E402


def test_centres_deterministic_and_sphere_uniform():
    a = bmp.centres(10000)
    b = bmp.centres(10000)
    assert a == b, "same seed must give the same sequence"
    assert bmp.centres(50) == a[:50], "a longer run must continue the same sequence"
    lat = np.radians(np.array([c[0] for c in a]))
    lon = np.array([c[1] for c in a])
    assert np.all(np.abs(np.degrees(lat)) <= 90.0)
    assert np.all((lon >= -180.0) & (lon < 180.0))
    # uniform in sin(lat): mean 0 (sd about 0.0058 for 10,000 draws; tolerance 0.02)
    assert abs(float(np.mean(np.sin(lat)))) < 0.02
    # P(|lat| > 60 deg) = 1 - sin(60 deg) = 0.134 for a sphere-uniform centre
    share = float(np.mean(np.abs(np.degrees(lat)) > 60.0))
    assert abs(share - (1.0 - math.sin(math.radians(60.0)))) < 0.02


def test_bbox_contains_logic():
    sq = bmp.square_extent(10.0, 20.0)
    w, s, e, n = sq
    assert abs((e - w) / 2 - math.degrees(4500.0 / bmp.MARS_R)) < 1e-12
    # item larger than the square on every side: contained
    assert bmp.bbox_contains([w - 1, s - 1, e + 1, n + 1], sq)
    # item edge exactly on the square edge: contained (<=)
    assert bmp.bbox_contains([w, s, e, n], sq)
    # item that misses the north edge by a little: not contained
    assert not bmp.bbox_contains([w - 1, s - 1, e + 1, n - 1e-6], sq)
    # item that misses the west edge: not contained
    assert not bmp.bbox_contains([w + 1e-6, s - 1, e + 1, n + 1], sq)
    # antimeridian: item from 170 to -170 (crosses 180) contains a square spanning 175..185
    sq_dl = (175.0, 0.0, 185.0, 0.1)
    assert bmp.bbox_contains([170.0, -1.0, -170.0, 1.0], sq_dl)
    assert not bmp.bbox_contains([170.0, -1.0, -176.0, 1.0], sq_dl)
    # the search pieces of a square crossing 180 stay inside [-180, 180] with w <= e
    pieces = bmp.search_pieces(sq_dl)
    assert len(pieces) == 2
    for pw, ps, pe, pn in pieces:
        assert -180.0 <= pw <= pe <= 180.0


def test_candidates_need_dem_asset_and_largest_first():
    sq = bmp.square_extent(0.0, 0.0)
    feats = [
        {"id": "small", "bbox": [-0.2, -0.2, 0.2, 0.2], "assets": {"dtm": {"href": "x"}}},
        {"id": "no_asset", "bbox": [-5, -5, 5, 5], "assets": {"thumbnail": {"href": "t"}}},
        {"id": "big", "bbox": [-3, -3, 3, 3], "assets": {"dem": {"href": "d"}}},
        {"id": "miss", "bbox": [1, 1, 3, 3], "assets": {"dem": {"href": "d"}}},
    ]
    got = [f["id"] for f in bmp.candidate_items(feats, sq)]
    assert got == ["big", "small"]
    assert bmp.dem_asset(feats[2]) == ("dem", "d")
    assert bmp.dem_asset(feats[0]) == ("dtm", "x")


def test_disk_valid_fraction_synthetic():
    n = 450  # 9 km square at 20 m: 4.5 km half width
    px = 20.0
    z = np.ones((n, n))
    # all finite -> 1.0; all NaN -> 0.0
    assert bmp.disk_valid(z, px, px) == 1.0
    assert bmp.disk_valid(np.full((n, n), np.nan), px, px) == 0.0
    # left half NaN (x < 0): pixel centres are symmetric about the middle, so exactly half the disk is valid
    zh = z.copy()
    zh[:, : n // 2] = np.nan
    assert abs(bmp.disk_valid(zh, px, px) - 0.5) < 1e-3
    # NaN only outside the 4 km disk (the square corners are beyond 4 km): disk stays fully valid
    zc = z.copy()
    zc[:40, :40] = np.nan
    zc[-40:, -40:] = np.nan
    assert bmp.disk_valid(zc, px, px) == 1.0
