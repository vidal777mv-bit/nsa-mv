"""Download and clip remote rasters into data/raw (STANDARDS sections 1, 8, 9).

Only per-site windows are written, never global mosaics. Every write goes to
``data/raw/<body>/<id>/<file>`` and is appended to ``data/raw/manifest.json``.

Functions here are I/O code. Pure helpers (path building, payload
classification, window geometry) are separated so they can be tested offline.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

USER_AGENT = "SpaceApps2026-research"
# ESA WorldCover 2021 v200 map tiles (3x3 deg, EPSG:4326, 10 m), public ESA S3 mirror (no signing).
WORLDCOVER_BASE = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
WORLDCOVER_BARE_SPARSE_CLASSES = (60, 70, 100)  # STANDARDS 10.2: bare-sparse, snow-ice, moss-lichen
METRES_PER_DEG = 111320.0  # same spherical scale as km_to_deg (111.32 km per degree)
BODIES = ("earth", "moon", "mars")
MAX_FILE_BYTES = 500 * 1024 * 1024  # budget: no file > 500 MB (STANDARDS 9)
PC_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
# Body spheres for lon/lat -> projected coordinates (STANDARDS section 2).
BODY_SPHERE_PROJ = {
    "moon": "+proj=longlat +R=1737400 +no_defs",
    "mars": "+proj=longlat +R=3396190 +no_defs",
}
_ID_RE = re.compile(r"^[a-z0-9_]+$")
_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
_TIFF_MAGIC = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")


class FetchError(RuntimeError):
    """A download or clip failed. The message is the logged reason."""


def utc_now() -> str:
    """Return the current time as ISO 8601 UTC, e.g. ``2026-11-14T15:00:00Z``."""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def repo_root() -> Path:
    """Project root: src/analog/io/fetch.py -> three levels up from ``src``."""
    return Path(__file__).resolve().parents[3]


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """SHA-256 of a file's bytes, read in chunks.

    Formula: sha256 = H(bytes of file), hex digest.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def classify_head(head: bytes, content_type: str | None = None) -> str:
    """Classify the first bytes of a response as tiff, zip, gzip, json, html or unknown.

    HTML is detected by its signature or by a text/html content type. A 404 page
    served with status 200 is therefore caught here, not by its file name.
    """
    if head.startswith(_TIFF_MAGIC):
        return "tiff"
    if head.startswith(b"PK\x03\x04"):
        return "zip"
    if head.startswith(b"\x1f\x8b"):
        return "gzip"
    stripped = head.lstrip().lower()
    if stripped.startswith((b"<!doctype html", b"<html", b"<?xml", b"<")):
        return "html"
    if content_type and "text/html" in content_type.lower():
        return "html"
    if stripped.startswith(b"{"):
        return "json"
    return "unknown"


def check_payload(head: bytes, content_type: str | None, expect: str | None) -> str | None:
    """Return None if the payload is acceptable, else the reason it is not.

    Rule: an HTML page is never data. If ``expect`` is given, the detected kind
    must equal it.
    """
    kind = classify_head(head, content_type)
    if kind == "html":
        return "HTML page returned instead of data (404 or landing page)"
    if expect is not None and kind != expect:
        return f"expected {expect} data, got {kind}"
    return None


def build_raw_path(root: Path, body: str, item_id: str, filename: str) -> Path:
    """Return ``root/<body>/<item_id>/<filename>`` after validating every part.

    Rules: body in earth|moon|mars; id is snake_case ascii; filename has no
    separators; the result must stay under ``root``.
    """
    if body not in BODIES:
        raise ValueError(f"unknown body {body!r}")
    if not _ID_RE.match(item_id):
        raise ValueError(f"id must be snake_case ascii, got {item_id!r}")
    if not _NAME_RE.match(filename) or filename in (".", ".."):
        raise ValueError(f"unsafe file name {filename!r}")
    base = Path(root).resolve()
    path = (base / body / item_id / filename).resolve()
    if base not in path.parents:
        raise ValueError("path escapes data/raw")
    return path


def window_bounds(cx: float, cy: float, half_width_m: float) -> tuple[float, float, float, float]:
    """Square window (minx, miny, maxx, maxy) centred on (cx, cy).

    Formula: minx = cx - R, maxx = cx + R, same for y, with R = half width (m).
    """
    if half_width_m <= 0:
        raise ValueError("half width must be > 0")
    return (cx - half_width_m, cy - half_width_m, cx + half_width_m, cy + half_width_m)


def km_to_deg(lat: float, half_width_km: float) -> tuple[float, float]:
    """Degrees of latitude and longitude spanning a half width in km (WGS84 sphere).

    Formula: dlat = km / 111.32; dlon = km / (111.32 * cos(lat)). Latitude is
    clamped to 89.9 deg to keep dlon finite near the poles.
    """
    import math

    if half_width_km <= 0:
        raise ValueError("half width must be > 0")
    dlat = half_width_km / 111.32
    coslat = math.cos(math.radians(min(abs(lat), 89.9)))
    return dlat, half_width_km / (111.32 * coslat)


def append_manifest(manifest: Path, entry: dict[str, Any]) -> None:
    """Append one entry to the JSON-list manifest, writing atomically.

    Entry keys: path, source_id, url, bytes, sha256, created (STANDARDS data/raw
    manifest in PLAN section 5 / task brief).
    """
    manifest = Path(manifest)
    items: list[dict[str, Any]] = []
    if manifest.exists():
        items = json.loads(manifest.read_text(encoding="utf-8"))
    items.append(entry)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    tmp = manifest.with_suffix(".json.part")
    tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, manifest)


def download(
    url: str,
    dest: Path,
    expect: str | None = None,
    retries: int = 3,
    backoff_s: float = 5.0,
    max_bytes: int = MAX_FILE_BYTES,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    """Stream ``url`` to ``dest`` and return its size, sha256 and HTTP status.

    Rules: stream in chunks; refuse payloads over ``max_bytes`` (checked against
    Content-Length and while streaming); refuse HTML and wrong kinds; retry on
    connection errors, 429 and 5xx with linear backoff; write to ``*.part`` then
    rename. Raises FetchError with the reason on failure.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": USER_AGENT}
    last_reason = "no attempt made"
    for attempt in range(1, retries + 1):
        try:
            with requests.get(url, headers=headers, stream=True, timeout=timeout_s, allow_redirects=True) as r:
                if r.status_code in (429,) or r.status_code >= 500:
                    last_reason = f"HTTP {r.status_code}"
                    raise _Retry()
                if r.status_code != 200:
                    raise FetchError(f"HTTP {r.status_code} for {url}")
                declared = r.headers.get("Content-Length")
                if declared and int(declared) > max_bytes:
                    raise FetchError(f"declared size {declared} B exceeds {max_bytes} B budget")
                ctype = r.headers.get("Content-Type")
                part = dest.with_name(dest.name + ".part")
                h = hashlib.sha256()
                total = 0
                head = b""
                with open(part, "wb") as fh:
                    for block in r.iter_content(chunk_size=1 << 20):
                        if not block:
                            continue
                        if len(head) < 4096:
                            head += block[: 4096 - len(head)]
                        total += len(block)
                        if total > max_bytes:
                            fh.close()
                            part.unlink(missing_ok=True)
                            raise FetchError(f"payload exceeds {max_bytes} B budget")
                        h.update(block)
                        fh.write(block)
                reason = check_payload(head, ctype, expect)
                if reason:
                    part.unlink(missing_ok=True)
                    raise FetchError(f"{reason} ({url})")
                os.replace(part, dest)
                return {
                    "url": url,
                    "path": str(dest),
                    "bytes": total,
                    "sha256": h.hexdigest(),
                    "http_code": r.status_code,
                    "content_type": ctype,
                    "created": utc_now(),
                }
        except FetchError:
            raise
        except (requests.RequestException, _Retry) as exc:
            last_reason = f"{type(exc).__name__}: {exc}" if not isinstance(exc, _Retry) else last_reason
            if attempt < retries:
                time.sleep(backoff_s * attempt)
    raise FetchError(f"failed after {retries} attempts: {last_reason} ({url})")


class _Retry(Exception):
    """Internal signal: retry this attempt."""


def stac_clip(
    collection: str,
    asset_key: str,
    lat: float,
    lon: float,
    half_width_km: float,
    out_path: Path,
) -> dict[str, Any]:
    """Clip a square window (half width km) around (lat, lon) from a Planetary Computer STAC collection.

    Steps: search items whose bbox meets the window (pystac-client), sign hrefs
    (planetary_computer.sign_inplace), read the windows remotely with rasterio
    (GDAL /vsicurl/), mosaic the tile pieces (rasterio.merge), and write a
    float32 GeoTIFF in EPSG:4326 with NaN as nodata. Only EPSG:4326 collections
    are accepted. Returns metadata; raises FetchError on failure.
    """
    import numpy as np
    import planetary_computer
    import pystac_client
    import rasterio
    from rasterio.crs import CRS
    from rasterio.merge import merge

    if not -180 <= lon < 180 or not -90 <= lat <= 90:
        raise FetchError(f"lat/lon out of range: {lat}, {lon}")
    dlat, dlon = km_to_deg(lat, half_width_km)
    west, east = lon - dlon, lon + dlon
    south, north = lat - dlat, lat + dlat
    if west < -180 or east >= 180:
        raise FetchError("window crosses the antimeridian; not supported by stac_clip")
    try:
        cat = pystac_client.Client.open(PC_STAC_URL, modifier=planetary_computer.sign_inplace)
        items = list(cat.search(collections=[collection], bbox=[west, south, east, north], max_items=50).items())
    except Exception as exc:  # network / API failure: report, never guess
        raise FetchError(f"STAC search failed for {collection}: {exc}") from exc
    if not items:
        raise FetchError(f"no items in {collection} over the window")
    srcs = []
    try:
        for item in items:
            href = item.assets[asset_key].href
            srcs.append(rasterio.open(href if href.startswith("/vsi") else f"/vsicurl/{href}"))
        bad = [s.crs for s in srcs if s.crs is None or CRS.from_user_input(s.crs) != CRS.from_epsg(4326)]
        if bad:
            raise FetchError(f"{collection} is not EPSG:4326 (found {bad[0]}); stac_clip supports 4326 only")
        nodata = srcs[0].nodata
        native_res = srcs[0].res[0]
        arr, transform = merge(
            srcs, bounds=(west, south, east, north), res=srcs[0].res, nodata=nodata, dtype="float32"
        )
    except FetchError:
        raise
    except Exception as exc:
        raise FetchError(f"remote read failed for {collection}: {exc}") from exc
    finally:
        for s in srcs:
            s.close()
    z = arr[0].astype("float64")
    if nodata is not None:
        z[z == nodata] = np.nan
    z[~np.isfinite(z)] = np.nan
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    part = out_path.with_name(out_path.name + ".part")
    with rasterio.open(
        part, "w", driver="GTiff", height=z.shape[0], width=z.shape[1], count=1,
        dtype="float32", crs="EPSG:4326", transform=transform, nodata=np.nan,
        compress="deflate",
    ) as dst:
        dst.write(z.astype("float32"), 1)
    os.replace(part, out_path)
    return {
        "collection": collection,
        "asset": asset_key,
        "items": [it.id for it in items],
        "native_res_deg": native_res,
        "shape": [int(z.shape[0]), int(z.shape[1])],
        "valid_fraction": float(np.isfinite(z).mean()),
        "bounds_deg": [west, south, east, north],
        "path": str(out_path),
        "bytes": out_path.stat().st_size,
        "sha256": sha256_file(out_path),
        "created": utc_now(),
    }


def cog_window_clip(
    url: str,
    body: str,
    lat: float,
    lon: float,
    half_width_km: float,
    out_path: Path,
) -> dict[str, Any]:
    """Clip a square window (half width km) from a remote projected COG (e.g. LOLA, CTX).

    The site (lat, lon) is projected from the body sphere into the raster CRS
    with pyproj; the window is centre +/- R metres in that CRS (the raster CRS
    must use metre units). Read with rasterio via /vsicurl/ (windowed, boundless
    fill with NaN). Writes a float32 GeoTIFF with the same CRS.
    """
    import numpy as np
    import rasterio
    from pyproj import Transformer
    from rasterio.windows import from_bounds

    if body not in BODY_SPHERE_PROJ:
        raise FetchError(f"cog_window_clip needs a planetary body, got {body!r}")
    R = half_width_km * 1000.0
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(f"/vsicurl/{url}") as src:
            if src.crs is None or src.crs.linear_units not in ("metre", "meter"):
                raise FetchError(f"raster CRS must use metres, got {src.crs}")
            tr = Transformer.from_crs(BODY_SPHERE_PROJ[body], src.crs, always_xy=True)
            cx, cy = tr.transform(lon, lat)
            minx, miny, maxx, maxy = window_bounds(cx, cy, R)
            win = from_bounds(minx, miny, maxx, maxy, transform=src.transform)
            nodata = src.nodata
            data = src.read(1, window=win, boundless=True, fill_value=nodata if nodata is not None else 0)
            wtr = src.window_transform(win)
            crs = src.crs
    z = data.astype("float64")
    if nodata is not None:
        z[z == nodata] = np.nan
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    part = out_path.with_name(out_path.name + ".part")
    with rasterio.open(
        part, "w", driver="GTiff", height=z.shape[0], width=z.shape[1], count=1,
        dtype="float32", crs=crs, transform=wtr, nodata=np.nan, compress="deflate",
    ) as dst:
        dst.write(z.astype("float32"), 1)
    os.replace(part, out_path)
    return {
        "url": url,
        "centre_projected": [cx, cy],
        "window_m": [minx, miny, maxx, maxy],
        "crs": crs.to_string(),
        "px_m": [abs(wtr.a), abs(wtr.e)],
        "shape": [int(z.shape[0]), int(z.shape[1])],
        "valid_fraction": float(np.isfinite(z).mean()),
        "path": str(out_path),
        "bytes": out_path.stat().st_size,
        "sha256": sha256_file(out_path),
        "created": utc_now(),
    }


def worldcover_tile_name(lat: float, lon: float) -> str:
    """File name of the ESA WorldCover 3x3 degree tile that contains (lat, lon).

    Formula: the tile's south-west corner is (floor(lat/3)*3, floor(lon/3)*3); the
    name carries N/S with 2 digits and E/W with 3 digits, e.g. (21.0, 18.5) ->
    ``ESA_WorldCover_10m_2021_v200_N21E018_Map.tif``.
    """
    if not -90 <= lat <= 90 or not -180 <= lon < 180:
        raise ValueError(f"lat/lon out of range: {lat}, {lon}")
    la = int(math.floor(lat / 3.0)) * 3
    lo = int(math.floor(lon / 3.0)) * 3
    ns = "N" if la >= 0 else "S"
    ew = "E" if lo >= 0 else "W"
    return f"ESA_WorldCover_10m_2021_v200_{ns}{abs(la):02d}{ew}{abs(lo):03d}_Map.tif"


def disk_pixel_mask(n_rows: int, n_cols: int, px_x_m: float, px_y_m: float, radius_m: float):
    """Boolean mask of pixels whose centre lies within ``radius_m`` of the window centre.

    The window centre is the middle of the array (between pixels when the size is
    even). Pixel centres are at ``(k + 0.5 - n/2) * px`` metres from the centre.
    Formula: inside = x^2 + y^2 <= R^2.
    """
    import numpy as np

    if n_rows < 1 or n_cols < 1 or px_x_m <= 0 or px_y_m <= 0 or radius_m <= 0:
        raise ValueError("grid sizes, pixel sizes and radius must be > 0")
    y = (np.arange(n_rows) + 0.5 - n_rows / 2.0) * px_y_m
    x = (np.arange(n_cols) + 0.5 - n_cols / 2.0) * px_x_m
    yy, xx = np.meshgrid(y, x, indexing="ij")
    return (xx * xx + yy * yy) <= radius_m * radius_m


def disk_share(values, in_set: tuple[int, ...], inside) -> float | None:
    """Share of the disk pixels whose value belongs to ``in_set``; None if the disk is empty.

    Formula: share = #{p : inside[p] and values[p] in in_set} / #{p : inside[p]}.
    Pixels outside the disk are ignored; nodata pixels inside it count as not in the set.
    """
    import numpy as np

    values = np.asarray(values)
    inside = np.asarray(inside, dtype=bool)
    n = int(inside.sum())
    if n == 0:
        return None
    hit = np.isin(values[inside], np.asarray(in_set))
    return float(hit.sum()) / n


def disk_valid_fraction(z, px_x_m: float, px_y_m: float, radius_m: float) -> float | None:
    """Share of the disk pixels (centre at the array middle) whose value is finite; None if empty.

    Formula: frac = #{p : inside[p] and isfinite(z[p])} / #{p : inside[p]}, inside as in disk_pixel_mask.
    Used to check the 90% coverage rule in the disk, not in the whole window.
    """
    import numpy as np

    z = np.asarray(z, dtype="float64")
    inside = disk_pixel_mask(z.shape[0], z.shape[1], px_x_m, px_y_m, radius_m)
    n = int(inside.sum())
    if n == 0:
        return None
    return float(np.isfinite(z[inside]).sum()) / n


def open_worldcover_tile(name: str, cache: dict[str, Any]) -> Any | None:
    """Open one WorldCover tile over HTTP once and keep it in ``cache``.

    Rule: HTTP 404 means the tile does not exist (no land in that 3x3 degree cell),
    returned as None. Any other status is an error (never treated as ocean).
    """
    import rasterio

    if name in cache:
        return cache[name]
    url = f"{WORLDCOVER_BASE}/{name}"
    r = requests.head(url, headers={"User-Agent": USER_AGENT}, timeout=120, allow_redirects=True)
    if r.status_code == 404:
        cache[name] = None
        return None
    if r.status_code != 200:
        raise FetchError(f"WorldCover tile {name}: HTTP {r.status_code}")
    # GDAL option is read from the environment (set in set_gdal_defaults); no rasterio.Env here,
    # because Env changes process-wide state and stalled concurrent tile opens.
    set_gdal_defaults()
    cache[name] = rasterio.open(f"/vsicurl/{url}")
    return cache[name]


def set_gdal_defaults() -> None:
    """Set GDAL options for remote reads once per process (no directory listing on open)."""
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")


def worldcover_disk_share(
    lat: float,
    lon: float,
    cache: dict[str, Any],
    radius_m: float = 4000.0,
    n_px: int = 80,
    in_set: tuple[int, ...] = WORLDCOVER_BARE_SPARSE_CLASSES,
) -> dict[str, Any]:
    """WorldCover share of ``in_set`` (default classes 60, 70, 100) inside a disk of ``radius_m`` around (lat, lon).

    Method: a square window of 2R (metres) is read at n_px x n_px with
    rasterio.merge (GDAL picks the coarse internal overview, about 74 m for the
    10 m product, resampled to the n_px grid, i.e. about 100 m for 80 px over 8 km).
    The share is computed over the disk pixels (``disk_share``). Ocean or any
    no-tile cell gives share 0 (land only). Windows crossing the antimeridian are
    refused with a reason (share None).
    """
    from rasterio.enums import Resampling
    from rasterio.merge import merge

    if radius_m <= 0 or n_px < 2:
        raise ValueError("radius and n_px must be positive")
    cos_lat = math.cos(math.radians(lat))
    if cos_lat <= 1e-6:
        raise FetchError("WorldCover disk not defined at the poles")
    dlat = radius_m / METRES_PER_DEG
    dlon = radius_m / (METRES_PER_DEG * cos_lat)
    west, east, south, north = lon - dlon, lon + dlon, lat - dlat, lat + dlat
    if west < -180 or east >= 180:
        return {"share": None, "reason": "window crosses the antimeridian", "lat": lat, "lon": lon}
    names = sorted({worldcover_tile_name(la, lo) for la in (south, north) for lo in (west, east)})
    srcs = [ds for ds in (open_worldcover_tile(n, cache) for n in names) if ds is not None]
    if not srcs:
        return {"share": 0.0, "reason": "no WorldCover tile over the window (ocean)", "tiles": names,
                "lat": lat, "lon": lon}
    res = ((east - west) / n_px, (north - south) / n_px)
    arr, tr = merge(srcs, bounds=(west, south, east, north), res=res, nodata=0, dtype="uint8",
                    resampling=Resampling.nearest)
    values = arr[0]
    px_x_m = tr.a * METRES_PER_DEG * cos_lat
    px_y_m = -tr.e * METRES_PER_DEG
    inside = disk_pixel_mask(values.shape[0], values.shape[1], px_x_m, px_y_m, radius_m)
    share = disk_share(values, tuple(in_set), inside)
    return {"share": share, "n_disk_px": int(inside.sum()), "shape": [int(values.shape[0]), int(values.shape[1])],
            "px_m": [round(px_x_m, 2), round(px_y_m, 2)], "tiles": names, "lat": lat, "lon": lon}


EARTH_RADIUS_KM = 6371008.8 / 1000.0  # STANDARDS section 2 (IUGG mean radius)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km on the mean Earth sphere.

    Formula: a = sin^2(dlat/2) + cos(lat1) cos(lat2) sin^2(dlon/2);
    d = 2 R asin(sqrt(a)), R = 6371.0088 km.
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2.0 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def grid_points(step_deg: float, lat_min: float, lat_max: float) -> list[tuple[float, float]]:
    """Regular lat/lon grid: lat = lat_min + i*step (<= lat_max), lon = -180 + j*step (< 180).

    Rule: the grid is the same for every run (no randomness). Values are rounded to
    6 decimals so repeated runs produce identical window centres.
    """
    if step_deg <= 0 or lat_max <= lat_min:
        raise ValueError("step must be > 0 and lat_max > lat_min")
    lats = []
    i = 0
    while lat_min + i * step_deg <= lat_max + 1e-9:
        lats.append(round(lat_min + i * step_deg, 6))
        i += 1
    n_lon = int(round(360.0 / step_deg))
    lons = [round(-180.0 + j * step_deg, 6) for j in range(n_lon)]
    return [(la, lo) for la in lats for lo in lons if lo < 180.0]


def spacing_for_target(p_pass: float, target: int, lat_min: float, lat_max: float) -> float:
    """Grid step (deg) that yields about ``target`` passing windows.

    Formula: expected passes N(d) = p * (360 / d) * ((lat_max - lat_min) / d), with p the
    pass fraction of uniformly drawn (lat, lon) points; solved for d:
    d = sqrt(p * 360 * (lat_max - lat_min) / target).
    """
    if not 0 < p_pass <= 1 or target <= 0:
        raise ValueError("pass fraction must be in (0, 1] and target > 0")
    return math.sqrt(p_pass * 360.0 * (lat_max - lat_min) / target)


def haversine_km_np(lat1, lon1, lat2, lon2):
    """Vectorised haversine distance in km (same formula as ``haversine_km``).

    Formula: a = sin^2(dlat/2) + cos(lat1) cos(lat2) sin^2(dlon/2); d = 2 R asin(sqrt(a)).
    Inputs are numpy arrays (or scalars) of degrees; broadcasting applies.
    """
    import numpy as np

    p1 = np.radians(np.asarray(lat1, dtype=float))
    p2 = np.radians(np.asarray(lat2, dtype=float))
    dp = p2 - p1
    dl = np.radians(np.asarray(lon2, dtype=float) - np.asarray(lon1, dtype=float))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.minimum(1.0, np.sqrt(a)))
