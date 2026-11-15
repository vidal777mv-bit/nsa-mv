"""Tests for analog.grid.load_local_grid: synthetic GeoTIFFs in a temp directory (STANDARDS.md section 3)."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from analog import grid as gridmod
from analog.core import metrics as m

SLOPE_DEG = 10.0
LAT0 = 40.0
LON0 = -87.0
EARTH_R = gridmod.BODY_RADIUS_M["earth"]


def _write_tif(path: Path, data: np.ndarray, transform, crs: str, nodata: float | None = None) -> None:
    """Write a single-band float64 GeoTIFF."""
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="float64",
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(data, 1)


def _projected_case(tmp_path: Path, nodata_west_half: bool = False) -> tuple[Path, float, float]:
    """UTM 16N raster, 20 m pixels, 14 km square around the site; z = (E - E0) tan(10 deg)."""
    e0, n0 = Transformer.from_crs("EPSG:4326", "EPSG:32616", always_xy=True).transform(LON0, LAT0)
    px = 20.0
    npx = 700
    west, north = e0 - 7000.0, n0 + 7000.0
    transform = from_origin(west, north, px, px)
    cols = west + (np.arange(npx) + 0.5) * px
    xc = np.broadcast_to(cols[None, :], (npx, npx))
    data = (xc - e0) * math.tan(math.radians(SLOPE_DEG))
    nodata = None
    if nodata_west_half:
        data = data.copy()
        data[:, : npx // 2] = -9999.0
        nodata = -9999.0
    path = tmp_path / "utm_plane.tif"
    _write_tif(path, data, transform, "EPSG:32616", nodata=nodata)
    return path, e0, n0


def _geographic_case(tmp_path: Path) -> Path:
    """EPSG:4326 raster, 0.002 deg pixels (about 222 m), +-0.1 deg around the site.
    z = (lon - LON0) * (pi/180) R cos(LAT0) * tan(10 deg), so the plane is 10 deg along east at the site."""
    px = 0.002
    npx = 100
    west, north = LON0 - 0.1, LAT0 + 0.1
    transform = from_origin(west, north, px, px)
    lon_c = west + (np.arange(npx) + 0.5) * px
    m_per_deg_lon = math.pi / 180.0 * EARTH_R * math.cos(math.radians(LAT0))
    row = (lon_c - LON0) * m_per_deg_lon * math.tan(math.radians(SLOPE_DEG))
    data = np.broadcast_to(row[None, :], (npx, npx)).copy()
    path = tmp_path / "geo_plane.tif"
    _write_tif(path, data, transform, "EPSG:4326")
    return path


def test_aeqd_string_uses_body_radius():
    """Projection string carries the body radius from STANDARDS section 2."""
    s = gridmod.aeqd_proj_string(40.0, -87.0, EARTH_R)
    assert "+proj=aeqd" in s and "+lat_0=40.0000000000" in s and "+lon_0=-87.0000000000" in s
    assert "+R=6371008.8" in s
    assert gridmod.BODY_RADIUS_M == {"earth": 6371008.8, "moon": 1737400.0, "mars": 3396190.0}


def test_projected_plane_slope_centre_coverage_and_shape(tmp_path):
    """UTM plane z = (E - E0) tan(10 deg): slope recovered within 0.5 deg, centre z = 0, full coverage."""
    path, _, _ = _projected_case(tmp_path)
    z, mask, meta = gridmod.load_local_grid(path, LAT0, LON0, "earth", 100.0, 4000.0)
    assert z.shape == (81, 81) and mask.shape == (81, 81)
    assert z.dtype == np.float64 and mask.dtype == bool
    assert mask[40, 40]
    slope = m.slope_p95_deg(z, mask, 100.0)
    assert slope == pytest.approx(SLOPE_DEG, abs=0.5)
    assert z[40, 40] == pytest.approx(0.0, abs=1e-3)
    assert meta["coverage"] >= 0.999
    assert meta["native_res_m"] == pytest.approx(20.0, abs=1e-9)
    assert meta["L"] == 100.0 and meta["R"] == 4000.0
    assert meta["crs_src"] == "EPSG:32616"
    assert meta["crs_dst"].startswith("+proj=aeqd")
    assert meta["L"] >= 2 * meta["native_res_m"]  # not flagged: L = 5 x native


def test_nodata_becomes_nan_and_lowers_coverage(tmp_path):
    """Source nodata (-9999) in the west half becomes NaN, outside the mask, and lowers coverage to about 0.5."""
    path, _, _ = _projected_case(tmp_path, nodata_west_half=True)
    z, mask, meta = gridmod.load_local_grid(path, LAT0, LON0, "earth", 100.0, 4000.0)
    assert np.isnan(z[40, 0])
    assert np.isfinite(z[40, 80])
    assert not mask[40, 0]
    assert 0.40 < meta["coverage"] < 0.60
    assert not np.any(z == -9999.0)


def test_geographic_plane_and_reported_resolution(tmp_path):
    """EPSG:4326 plane: slope within 0.5 deg, centre z = 0; native pixel about 222 m, so L < 2 * native is
    reported through meta (the pipeline skips such windows)."""
    path = _geographic_case(tmp_path)
    z, mask, meta = gridmod.load_local_grid(path, LAT0, LON0, "earth", 100.0, 4000.0)
    assert meta["crs_src"] == "EPSG:4326"
    assert meta["native_res_m"] == pytest.approx(0.002 * math.pi / 180.0 * EARTH_R, rel=1e-3)
    assert meta["L"] < 2 * meta["native_res_m"]
    assert meta["coverage"] >= 0.999
    assert z[40, 40] == pytest.approx(0.0, abs=1e-3)
    slope = m.slope_p95_deg(z, mask, 100.0)
    assert slope == pytest.approx(SLOPE_DEG, abs=0.5)


def test_longitude_is_wrapped_to_pm180(tmp_path):
    """lon = 273 deg is the same site as lon = -87 deg; the projection is centred on -87."""
    path, _, _ = _projected_case(tmp_path)
    _, _, meta = gridmod.load_local_grid(path, LAT0, 273.0, "earth", 100.0, 4000.0)
    assert "+lon_0=-87.0000000000" in meta["crs_dst"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"body": "venus", "L": 100.0, "R": 4000.0, "lat": LAT0, "lon": LON0},
        {"body": "earth", "L": 0.0, "R": 4000.0, "lat": LAT0, "lon": LON0},
        {"body": "earth", "L": 100.0, "R": 4000.0, "lat": 95.0, "lon": LON0},
    ],
)
def test_invalid_inputs_raise(tmp_path, kwargs):
    """Unknown body, non-positive L and latitude out of range are rejected before any file is read."""
    path, _, _ = _projected_case(tmp_path)
    with pytest.raises(ValueError):
        gridmod.load_local_grid(path, kwargs["lat"], kwargs["lon"], kwargs["body"], kwargs["L"], kwargs["R"])
