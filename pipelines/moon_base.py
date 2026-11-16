"""Permanent-base layer for the Moon targets: illumination, permanently shadowed regions (PSR) and Earth visibility,
from the official NASA PGDA south-pole products (LOLA; Mazarico et al. 2011; PGDA product 69).

Reads (never recomputes what is persisted):
- site/data/targets.json (moon targets: id, body, lat, lon, center_note)
- data/raw/moon/base/AVGVISIB_75S_120M_201608.TIF        average solar illumination (raw x 4e-5 = fraction of time, 0..1)
- data/raw/moon/base/LPSR_75S_120M_201608.TIF            permanently shadowed regions (raw x 2.5e-5 + 0.5 = 1 for PSR, 0 otherwise)
- data/raw/moon/base/AVGVISIB_75S_120M_201608_EARTH.TIF  average Earth visibility (raw x 4e-5 = fraction of time, 0..1)

The GeoTIFF scale and offset are read from the file (PGDA page: "Scaling/offsets should be applied automatically for the
GeoTIFFs"). rasterio does not apply them by itself, so they are applied here.

Method per site (STANDARDS 10.x style, one rule for every site):
- the site disk is 4 km radius (8 km across), centred on the targets.json centre, the same disk as the measurement stage;
- illum_mean_pct / illum_max_pct: mean and maximum of the illumination fraction x 100 over the disk pixel centres;
- earth_vis_pct: mean of the Earth-visibility fraction x 100 over the disk;
- psr_nearest_km: distance from the centre to the nearest PSR pixel centre anywhere in the product (0 when inside the disk);
- psr_area_km2: PSR pixel count inside the disk x pixel area;
- a site outside the 75S-90S product (or whose disk is not fully inside its valid circle) is "not polar, constant
  day/night cycle": no values are forced.

Writes:
- data/derived/moon_base/moon_base.json (full precision, with provenance and QA counts)
Then tools/export_moon_base.py writes site/data/moon_base.json (rounded, the browser copy).

Usage: .venv/Scripts/python.exe pipelines/moon_base.py [--root <project root>]
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rasterio  # noqa: E402
from pyproj import Transformer  # noqa: E402
from rasterio.transform import Affine  # noqa: E402

from _common import (  # noqa: E402
    RunLog,
    load_json,
    make_paths,
    parse_args,
    provenance_block,
    write_json,
)

STAGE = "moon_base"
MOON_LONLAT = "+proj=longlat +R=1737400 +no_defs"
DISK_RADIUS_M = 4000.0  # 8 km disk (same radius as the measurement stage, config/measure.json R_m)
# valid circle of the 75S-90S product: the raster half-width (457440 m); a disk is usable when it lies inside it
PRODUCT_HALF_WIDTH_M = 457440.0
NOT_POLAR = "not polar, constant day/night cycle"

PRODUCTS = {
    "illum": {
        "file": "AVGVISIB_75S_120M_201608.TIF",
        "url": "https://pgda.gsfc.nasa.gov/data/MoonIllumination/AVGVISIB_75S_120M_201608.TIF",
        "id": "pgda_illum_75s_120m",
    },
    "psr": {
        "file": "LPSR_75S_120M_201608.TIF",
        "url": "https://pgda.gsfc.nasa.gov/data/MoonIllumination/LPSR_75S_120M_201608.TIF",
        "id": "pgda_psr_75s_120m",
    },
    "earth": {
        "file": "AVGVISIB_75S_120M_201608_EARTH.TIF",
        "url": "https://pgda.gsfc.nasa.gov/data/MoonIllumination/AVGVISIB_75S_120M_201608_EARTH.TIF",
        "id": "pgda_earth_vis_75s_120m",
    },
}

CREDIT = ("Mazarico, E., et al. (2011), Illumination conditions of the lunar polar regions using LOLA topography, "
          "Icarus 211, 1066-1081, doi:10.1016/j.icarus.2010.10.030; NASA GSFC PGDA (product 69 page: "
          "https://pgda.gsfc.nasa.gov/products/69). The page states no licence; cite Mazarico et al. (2011).")

SOURCE_NOTES = {
    "illum": "Average solar illumination: fraction of the 18.6-year nutation cycle (hourly steps) with the Sun "
             "visible at the surface. The product is a model of LOLA topography, not a direct measurement.",
    "psr": "Permanently shadowed regions: binary map (1 = PSR, 0 = not). Value meaning read from the GeoTIFF "
           "offset (raw 20000 -> 1.0); the PDS label could not be read (pds-geosciences.wustl.edu was down).",
    "earth": "Average Earth visibility: fraction of the cycle with any part of the Earth disc unobscured. PGDA warns "
             "this may be slightly optimistic for DSN-only radio links.",
}


# ----------------------------------------------------------------------------------------------- pure logic
def scale_values(raw: np.ndarray, scale: float, offset: float, nodata: float | None) -> np.ndarray:
    """Physical values of a raw GeoTIFF band: raw * scale + offset, with nodata as NaN (float32)."""
    out = raw.astype(np.float32) * np.float32(scale) + np.float32(offset)
    if nodata is not None:
        out = np.where(raw == nodata, np.float32(np.nan), out)
    return out.astype(np.float32)


def disk_window(shape: tuple[int, int], transform: Affine, x: float, y: float, radius_m: float) -> tuple[int, int, int, int]:
    """Row/col window (r0, r1, c0, c1) that holds every pixel centre of the disk, clipped to the raster."""
    H, W = shape
    cc = (x - transform.c) / transform.a - 0.5  # centre, in pixel-index units (column)
    rc = (y - transform.f) / transform.e - 0.5  # centre, in pixel-index units (row); transform.e < 0
    half_c = radius_m / abs(transform.a) + 1.0
    half_r = radius_m / abs(transform.e) + 1.0
    c0 = max(0, int(math.floor(cc - half_c)))
    c1 = min(W, int(math.ceil(cc + half_c)) + 1)
    r0 = max(0, int(math.floor(rc - half_r)))
    r1 = min(H, int(math.ceil(rc + half_r)) + 1)
    return r0, r1, c0, c1


def disk_mask(shape: tuple[int, int], transform: Affine, x: float, y: float, radius_m: float):
    """(window, mask) where mask marks the pixel centres within radius_m of (x, y), inside the window."""
    r0, r1, c0, c1 = disk_window(shape, transform, x, y, radius_m)
    cols = np.arange(c0, c1)
    rows = np.arange(r0, r1)
    X = transform.c + (cols + 0.5) * transform.a
    Y = transform.f + (rows + 0.5) * transform.e
    dx = X[None, :] - x
    dy = Y[:, None] - y
    return (r0, r1, c0, c1), (dx * dx + dy * dy) <= radius_m * radius_m


def disk_stats(values: np.ndarray, transform: Affine, x: float, y: float, radius_m: float) -> dict[str, Any]:
    """Mean and maximum of the finite values over the disk, plus pixel counts (n_disk, n_valid)."""
    (r0, r1, c0, c1), m = disk_mask(values.shape, transform, x, y, radius_m)
    sub = values[r0:r1, c0:c1][m].astype(np.float64)
    ok = np.isfinite(sub)
    n_valid = int(ok.sum())
    if n_valid == 0:
        return {"mean": None, "max": None, "n_disk": int(m.sum()), "n_valid": 0}
    return {
        "mean": float(sub[ok].mean()),
        "max": float(sub[ok].max()),
        "n_disk": int(m.sum()),
        "n_valid": n_valid,
    }


def psr_stats(psr: np.ndarray, transform: Affine, x: float, y: float, radius_m: float) -> dict[str, Any]:
    """Nearest PSR pixel centre to (x, y) in metres (anywhere in the raster) and PSR area inside the disk in km2."""
    rr, cc = np.nonzero(psr)
    if rr.size == 0:
        raise ValueError("no PSR pixels in the product")
    X = transform.c + (cc + 0.5) * transform.a
    Y = transform.f + (rr + 0.5) * transform.e
    d = np.hypot(X - x, Y - y)
    (r0, r1, c0, c1), m = disk_mask(psr.shape, transform, x, y, radius_m)
    pixel_km2 = abs(transform.a * transform.e) / 1e6
    return {
        "nearest_m": float(d.min()),
        "area_km2": float(psr[r0:r1, c0:c1][m].sum()) * pixel_km2,
    }


def inside_product(x: float, y: float, radius_m: float) -> bool:
    """True when the whole disk lies inside the valid 75S-90S circle (see PRODUCT_HALF_WIDTH_M)."""
    return math.hypot(x, y) + radius_m <= PRODUCT_HALF_WIDTH_M


def site_record(x: float | None, y: float | None, center_note: str, rasters: dict[str, Any] | None) -> dict[str, Any]:
    """One site of the output. rasters = {'illum': (values, transform), 'psr': (...), 'earth': (...)} or None when the
    site is outside the product (then every value is null and the note is NOT_POLAR)."""
    if rasters is None or x is None or y is None or not inside_product(x, y, DISK_RADIUS_M):
        return {
            "illum_mean_pct": None, "illum_max_pct": None, "psr_nearest_km": None, "psr_area_km2": None,
            "earth_vis_pct": None, "notes": NOT_POLAR, "qa": None,
        }
    ill, t_ill = rasters["illum"]
    psr, t_psr = rasters["psr"]
    earth, t_earth = rasters["earth"]
    s_ill = disk_stats(ill, t_ill, x, y, DISK_RADIUS_M)
    s_earth = disk_stats(earth, t_earth, x, y, DISK_RADIUS_M)
    s_psr = psr_stats(psr, t_psr, x, y, DISK_RADIUS_M)
    pct = lambda v: None if v is None else 100.0 * v  # noqa: E731
    notes = (f"Disk 4 km radius (8 km across) on the centre; disk pixels valid {s_ill['n_valid']} of {s_ill['n_disk']}. "
             f"PSR distance quantised to the 120 m pixel centres (about +/-85 m). Centre: {center_note}")
    return {
        "illum_mean_pct": pct(s_ill["mean"]),
        "illum_max_pct": pct(s_ill["max"]),
        "psr_nearest_km": s_psr["nearest_m"] / 1000.0,
        "psr_area_km2": s_psr["area_km2"],
        "earth_vis_pct": pct(s_earth["mean"]),
        "notes": notes,
        "qa": {"n_disk": s_ill["n_disk"], "n_valid_illum": s_ill["n_valid"], "n_valid_earth": s_earth["n_valid"]},
    }


def sources_block(raw_dir: Path) -> list[dict[str, Any]]:
    """The sources list written to the output (one entry per product used)."""
    out = []
    for key in ("illum", "psr", "earth"):
        p = PRODUCTS[key]
        out.append({
            "id": p["id"],
            "url": p["url"],
            "product": f"{SOURCE_NOTES[key]} File {p['file']} (PGDA product 69, south pole 75S-90S).",
            "resolution_m": 120,
            "period": ("averaged over hourly steps across one 18.6-year lunar nutation cycle; LOLA data "
                       "2009-07-13 to 2013-07-18 (GeoTIFF tags START_TIME/STOP_TIME)"),
            "credit": CREDIT,
        })
    return out


# ----------------------------------------------------------------------------------------------- main
def read_product(raw_dir: Path, key: str) -> tuple[np.ndarray, Affine, Any]:
    """Read one product: physical values (float32, NaN for nodata), its transform and its CRS."""
    path = raw_dir / PRODUCTS[key]["file"]
    if not path.exists():
        raise FileNotFoundError(f"missing raw product: {path}")
    with rasterio.open(path) as src:
        raw = src.read(1)
        scale = src.scales[0]
        offset = src.offsets[0]
        values = scale_values(raw, scale, offset, src.nodata)
        if key == "psr":
            values = values >= np.float32(0.5)  # binary map: 1.0 = PSR, 0.0 = not PSR (NaN compares False)
        return values, src.transform, src.crs


def main() -> int:
    args = parse_args("Permanent base layer for the Moon targets (PGDA illumination, PSR, Earth visibility)")
    paths = make_paths(args.root, False)
    log = RunLog(paths.derived / STAGE, STAGE)
    raw_dir = paths.raw_dir / "moon" / "base"

    rasters: dict[str, Any] = {}
    crs = None
    for key in ("illum", "psr", "earth"):
        values, transform, this_crs = read_product(raw_dir, key)
        rasters[key] = (values, transform)
        if crs is None:
            crs = this_crs
        elif this_crs != crs or values.shape != rasters["illum"][0].shape:
            raise ValueError(f"product {key} does not share the grid of the illumination map")
        log.event("info", "product read", product=key, file=PRODUCTS[key]["file"], shape=list(values.shape))

    tr = Transformer.from_crs(MOON_LONLAT, crs, always_xy=True)
    targets = [t for t in load_json(paths.root / "site" / "data" / "targets.json")["targets"] if t.get("body") == "moon"]

    sites: dict[str, Any] = {}
    for t in targets:
        x, y = tr.transform(float(t["lon"]), float(t["lat"]))
        polar = inside_product(x, y, DISK_RADIUS_M)
        rec = site_record(x, y, str(t.get("center_note", "")), rasters if polar else None)
        rec["centre_xy_m"] = [round(x, 3), round(y, 3)] if polar else None
        sites[str(t["id"])] = rec
        log.event("info", "site computed", site=t["id"], polar=bool(polar))

    inputs = [("targets", paths.root / "site" / "data" / "targets.json")]
    for key in ("illum", "psr", "earth"):
        inputs.append((PRODUCTS[key]["id"], raw_dir / PRODUCTS[key]["file"]))
    block = provenance_block(paths, STAGE, inputs)

    out = {
        "generated_by": ("pipelines/moon_base.py (Claude, Anthropic, under the team's direction); values computed "
                         "from the PGDA products listed in sources"),
        "provenance": block,
        "method": {
            "disk_radius_m": DISK_RADIUS_M,
            "product_valid_half_width_m": PRODUCT_HALF_WIDTH_M,
            "not_polar_note": NOT_POLAR,
            "illum_units": "percent of the cycle with the Sun visible (fraction x 100)",
            "earth_vis_units": "percent of the cycle with Earth visible (fraction x 100)",
        },
        "sources": sources_block(raw_dir),
        "sites": sites,
    }
    full = paths.derived / STAGE / "moon_base.json"
    write_json(full, out)
    log.event("info", "wrote moon_base", path=paths.rel(full), sites=len(sites))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
