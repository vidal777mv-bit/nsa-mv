"""Load a local DEM file into the standard analog grid (STANDARDS.md section 3).

The DEM is reprojected (bilinear) from its native CRS onto an azimuthal equidistant projection centred on
the site, with the body radius. The output is a square grid of side L metres whose centre pixel is the site.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject

BODY_RADIUS_M: dict[str, float] = {
    "earth": 6371008.8,  # mean radius, IUGG
    "moon": 1737400.0,
    "mars": 3396190.0,  # IAU 2015
}

_EDGE_TOL_M = 1e-9


def aeqd_proj_string(lat: float, lon: float, radius_m: float) -> str:
    """Azimuthal equidistant projection centred on (lat, lon).

    Formula: +proj=aeqd +lat_0=lat +lon_0=lon +x_0=0 +y_0=0 +R=radius +units=m +no_defs
    """
    return (
        f"+proj=aeqd +lat_0={lat:.10f} +lon_0={lon:.10f} +x_0=0 +y_0=0 "
        f"+R={radius_m:.1f} +units=m +no_defs"
    )


def _native_res_m(src: rasterio.DatasetReader, lat: float, radius_m: float) -> float:
    """Native pixel size in metres (the larger side, so the L >= 2 * native check is conservative).

    Formula, projected CRS: max(|res_x|, |res_y|) * linear unit factor.
    Formula, geographic CRS: max(|res_y| * pi/180 * R, |res_x| * pi/180 * R * cos(lat)) with res in degrees.
    """
    res_x, res_y = abs(src.res[0]), abs(src.res[1])
    if src.crs.is_geographic:
        deg = math.pi / 180.0
        north = res_y * deg * radius_m
        east = res_x * deg * radius_m * math.cos(math.radians(lat))
        return float(max(north, east))
    factor = float(src.crs.linear_units_factor[1])
    return float(max(res_x, res_y) * factor)


def load_local_grid(
    path: str | Path, lat: float, lon: float, body: str, L: float, R: float
) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    """Reproject a local DEM onto the standard grid centred on the site.

    Formula: n = 2 * ceil(R / L) + 1; pixel (i, j) centre = ((j - n//2) L, (n//2 - i) L) metres in the AEQD
    projection; z = bilinear resample of the source; mask = (distance to centre <= R) and finite(z);
    coverage = mask.sum() / (number of pixel centres within R).

    Returns (z, mask, meta) with meta = {native_res_m, coverage, L, R, crs_src, crs_dst}.
    Raises ValueError for an unknown body or invalid geometry, and rasterio's error for an unreadable file
    (the pipeline decides how to log and skip).
    """
    if body not in BODY_RADIUS_M:
        raise ValueError(f"unknown body {body!r}; expected one of {sorted(BODY_RADIUS_M)}")
    if not (L > 0 and R > 0):
        raise ValueError("L and R must be positive")
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"latitude {lat} outside [-90, 90]")
    lon = ((lon + 180.0) % 360.0) - 180.0  # east-positive in [-180, 180)

    radius_m = BODY_RADIUS_M[body]
    n = 2 * math.ceil(R / L) + 1
    half = n // 2
    dst_transform = Affine(L, 0.0, -(n * L) / 2.0, 0.0, -L, (n * L) / 2.0)
    crs_dst_str = aeqd_proj_string(lat, lon, radius_m)
    dst_crs = CRS.from_string(crs_dst_str)

    rows, cols = np.mgrid[0:n, 0:n]
    x = (cols - half) * L
    y = (half - rows) * L
    dist = np.hypot(x, y)
    inside = dist <= R + _EDGE_TOL_M

    with rasterio.open(path) as src:
        if src.crs is None:
            raise ValueError(f"{path}: raster has no CRS")
        src_arr = src.read(1).astype(np.float64)
        src_nodata = src.nodata
        native_res = _native_res_m(src, lat, radius_m)
        dst = np.full((n, n), np.nan, dtype=np.float64)
        reproject(
            source=src_arr,
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src_nodata,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )
        crs_src = src.crs.to_string()

    z = dst
    mask = inside & np.isfinite(z)
    disk_pixels = int(np.count_nonzero(inside))
    coverage = float(mask.sum()) / disk_pixels
    meta: dict[str, object] = {
        "native_res_m": native_res,
        "coverage": coverage,
        "L": float(L),
        "R": float(R),
        "crs_src": crs_src,
        "crs_dst": crs_dst_str,
    }
    return z, mask, meta
