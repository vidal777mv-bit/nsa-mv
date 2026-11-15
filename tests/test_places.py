"""Offline reverse geocoding of analog centres (STANDARDS 10.12): point-in-polygon with holes, nearest within 50 km,
and the Natural Earth 1:10m admin-1 file read without GDAL (skipped when the file is absent).

Run alone: .venv/Scripts/python.exe -m pytest tests/test_places.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from analog.io import places as P

HERE = Path(__file__).resolve().parents[1]
NE_SHP = HERE / "data" / "raw" / "reference" / "ne_10m_admin_1" / "ne_10m_admin_1_states_provinces.shp"


def _ring(x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]], dtype=float)


def _index() -> P.PlaceIndex:
    """One polygon: a 10 x 10 degree square with a 2 x 2 hole in the middle (a lake-like hole)."""
    pg = P.Polygon2D(bbox=(0.0, 0.0, 10.0, 10.0), rings=[_ring(0, 0, 10, 10), _ring(4, 4, 6, 6)],
                     attrs={"name": "Testshire", "admin": "Testland"})
    return P.PlaceIndex([pg], name_field="name", country_field="admin", source="synthetic")


def test_inside_polygon_gives_admin1_and_country():
    rec = _index().lookup(1.0, 1.0)
    assert rec["name"] == "Testshire, Testland" and rec["admin1"] == "Testshire" and rec["country"] == "Testland"
    assert rec["match"] == "inside" and rec["distance_km"] == 0.0 and rec["source"] == "synthetic"


def test_hole_is_outside_and_far_from_any_edge_gives_none():
    """(5, 5) lies in the hole: even-odd gives 2 rings -> outside. Its nearest boundary is about 111 km away: None."""
    assert _index().lookup(5.0, 5.0) is None


def test_nearest_boundary_within_50_km_is_named_and_beyond_is_not():
    idx = _index()
    rec = idx.lookup(5.0, 10.2)  # 0.2 degrees east of the east edge at latitude 5: about 22 km
    assert rec["match"] == "nearest" and rec["name"] == "Testshire, Testland"
    assert rec["distance_km"] == pytest.approx(0.2 * 111.19 * np.cos(np.radians(5.0)), rel=0.01)
    assert idx.lookup(5.0, 11.0) is None  # about 111 km east: no name


def test_haversine_one_degree_of_latitude():
    assert P.haversine_km(0.0, 0.0, 1.0, 0.0) == pytest.approx(111.195, rel=1e-4)


@pytest.mark.skipif(not NE_SHP.exists(), reason="Natural Earth admin-1 file not downloaded (data/raw/reference)")
def test_real_natural_earth_file_known_points():
    """The downloaded file, read as it is: known analog centres map to their admin-1 and country."""
    idx = P.load_admin1(NE_SHP, "Natural Earth test")
    assert len(idx.polygons) == 4596
    gosses = idx.lookup(-23.8208, 132.3078)
    assert gosses["name"] == "Northern Territory, Australia" and gosses["match"] == "inside"
    tenere = idx.lookup(17.7009, 10.7565)
    assert tenere["name"] == "Agadez, Niger"
    assert idx.lookup(30.0, -40.0) is None  # mid-Atlantic: no polygon within 50 km
