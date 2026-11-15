"""Regional-scale feasibility sample (STANDARDS 10.10, EXPERIMENTAL). Not a production measure stage.

Measures the six features (STANDARDS 4) on the regional grid (L = 400 m, R = 16 km, config/measure_regional.json)
for a seeded sample of windows on two bodies:

- Mars: 40 centres uniform on the sphere between 60S and 60N (uniform in sin(lat)), source HRSC-MOLA blended
  200 m DEM read by remote windows (/vsicurl/). The global file is ~11 GB and load_local_grid reads its input whole,
  so each window is first clipped remotely to a local GeoTIFF (only the rows of the window are transferred), then
  measured with load_local_grid through _common.measure_raw.
- Earth: 40 centres drawn (seeded) from the 2000-window search pool index; NASADEM via fetch.stac_clip with a
  half width of 17 km (34 km window) into data/derived/regional/earth_clips/, then the same measure_raw.

Outputs (all under data/derived/regional/): parts/<body>.json (one per body, written by --body) and sample.json
(written by --assemble, with the provenance block of STANDARDS 7, summaries and the extrapolation). Clips are kept
so that the disk figure is measured, not guessed.

Usage (repository root):
    .venv/Scripts/python.exe pipelines/regional_sample.py --body mars
    .venv/Scripts/python.exe pipelines/regional_sample.py --body earth
    .venv/Scripts/python.exe pipelines/regional_sample.py --assemble
"""

from __future__ import annotations

import argparse
import math
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.windows import Window

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from analog import grid as gridmod  # noqa: E402
from analog.core import measure as meas  # noqa: E402
from analog.core import metrics  # noqa: E402
from analog.io import fetch  # noqa: E402
from analog.io import provenance as prov  # noqa: E402
from analog.io.fetch import sha256_file  # noqa: E402
from _common import RunLog, load_json, measure_raw, write_json, utc_now  # noqa: E402

SEED = 20261114
N_MARS = 40
N_EARTH = 40
MARS_LAT_LIMIT = 60.0
MARS_URL = (
    "https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/"
    "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif"
)
MARS_SOURCE_ID = "hrsc_mola_blend_200m"
EARTH_SOURCE_ID = "nasadem_pc"
EARTH_COLLECTION = "nasadem"
EARTH_ASSET = "elevation"
EARTH_HALF_KM = 17.0
MARGIN_M = 1000.0  # clip beyond R so bilinear sampling at the disk edge has source pixels
WORKERS_EXTRAPOLATION = 8
FEATURES = meas.FEATURE_IDS
CFG_PATH = ROOT / "config" / "measure_regional.json"
POOL_INDEX = ROOT / "data" / "raw" / "earth" / "pool" / "index.json"
OUT = ROOT / "data" / "derived" / "regional"
PARTS = OUT / "parts"
MARS_CLIPS = OUT / "mars_clips"
EARTH_CLIPS = OUT / "earth_clips"
SAMPLE_JSON = OUT / "sample.json"
STAGE = "regional_sample"


def load_cfg() -> dict[str, Any]:
    """config/measure_regional.json (the only config this stage reads)."""
    return load_json(CFG_PATH)


def rel(path: Path) -> str:
    """Repo-relative POSIX path."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


# ---------------------------------------------------------------- centres

def mars_centres(n: int, seed: int, half_m: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """n seeded centres uniform on the sphere, 60S to 60N (uniform in sin(lat)); lon uniform in [-180, 180).

    Rule: a centre whose clipped window would cross the antimeridian is redrawn (stac_clip and load_local_grid do
    not support it); each redraw is logged. Coordinates are rounded to 6 decimals before use, so the clip and the
    measurement use the same centre.
    Returns (centres, rejected, draws).
    """
    rng = np.random.default_rng(seed)
    R_m = gridmod.BODY_RADIUS_M["mars"]
    deg = math.pi / 180.0
    smax = math.sin(math.radians(MARS_LAT_LIMIT))
    out: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    draws = 0
    while len(out) < n:
        s = float(rng.uniform(-smax, smax))
        lon = float(rng.uniform(-180.0, 180.0))
        draws += 1
        lat = round(math.degrees(math.asin(s)), 6)
        lon = round(lon, 6)
        dlon = half_m / (R_m * deg * math.cos(math.radians(lat)))
        if lon - dlon < -180.0 or lon + dlon > 180.0:
            rejected.append({"lat": lat, "lon": lon, "reason": "window crosses the antimeridian"})
            continue
        out.append({"id": f"mars_{len(out) + 1:02d}", "lat": lat, "lon": lon, "draw": draws})
    return out, rejected, draws


def earth_centres(n: int, seed: int) -> list[dict[str, Any]]:
    """n seeded draws without replacement from the pool index (readers accept a list or {"windows": [...]})."""
    data = load_json(POOL_INDEX)
    windows = data["windows"] if isinstance(data, dict) else data
    rng = np.random.default_rng(seed)
    idx = sorted(rng.choice(len(windows), size=n, replace=False).tolist())
    out = []
    for k, i in enumerate(idx):
        w = windows[i]
        out.append({
            "id": f"earth_{k + 1:02d}", "lat": float(w["lat"]), "lon": float(w["lon"]),
            "pool_id": str(w["id"]), "pool_index": int(i), "pool_worldcover_share": w.get("worldcover_share"),
        })
    return out


# ---------------------------------------------------------------- Mars source

def mars_source_info() -> dict[str, Any]:
    """Header facts of the Mars DEM (remote header read only, no data)."""
    fetch.set_gdal_defaults()
    with rasterio.open("/vsicurl/" + MARS_URL) as src:
        res_deg = abs(src.res[1])
        native = res_deg * math.pi / 180.0 * gridmod.BODY_RADIUS_M["mars"]
        return {
            "url": MARS_URL,
            "driver": src.driver,
            "dtype": src.dtypes[0],
            "nodata": src.nodata,
            "crs": src.crs.to_string() if src.crs else None,
            "crs_wkt_name": src.crs.to_wkt()[:80] if src.crs else None,
            "width": src.width,
            "height": src.height,
            "res_deg": res_deg,
            "native_res_m": native,
            "two_x_native_m": 2.0 * native,
            "L_ge_2x_native": bool(400.0 >= 2.0 * native),
            "tiled": bool(src.profile.get("tiled")),
            "block_shape": list(src.block_shapes[0]),
            "overview_factors": list(src.overviews(1)),
            "bytes_per_row_full_width": int(src.width * np.dtype(src.dtypes[0]).itemsize),
            "full_file_gb_if_read_whole": round(src.width * src.height * np.dtype(src.dtypes[0]).itemsize / 1e9, 2),
        }


def mars_window_clip(lat: float, lon: float, half_m: float, out_path: Path) -> dict[str, Any]:
    """Remote windowed read of a square window (half width half_m, metres) of the Mars DEM into a local GeoTIFF.

    Method: pixel window from the affine transform (floor on the minimum, ceil on the maximum); read with
    rasterio over /vsicurl/ (only the rows of the window are requested); nodata -> NaN; float32 GeoTIFF in the same
    geographic CRS, deflate. Raises ValueError when the window leaves the raster.
    """
    fetch.set_gdal_defaults()
    os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
    R_m = gridmod.BODY_RADIUS_M["mars"]
    deg = math.pi / 180.0
    dlat = half_m / (R_m * deg)
    dlon = half_m / (R_m * deg * math.cos(math.radians(lat)))
    west, east, south, north = lon - dlon, lon + dlon, lat - dlat, lat + dlat
    with rasterio.open("/vsicurl/" + MARS_URL) as src:
        t = src.transform
        res_x, res_y = abs(t.a), abs(t.e)
        c0 = math.floor((west - t.c) / res_x)
        c1 = math.ceil((east - t.c) / res_x)
        r0 = math.floor((t.f - north) / res_y)
        r1 = math.ceil((t.f - south) / res_y)
        if c0 < 0 or r0 < 0 or c1 > src.width or r1 > src.height:
            raise ValueError("window leaves the Mars raster")
        win = Window(c0, r0, c1 - c0, r1 - r0)
        nodata = src.nodata
        t_read = time.perf_counter()
        arr = src.read(1, window=win)
        read_s = time.perf_counter() - t_read
        wtr = src.window_transform(win)
        crs = src.crs
    z = arr.astype(np.float32)
    if nodata is not None:
        z[arr == nodata] = np.nan
    z[~np.isfinite(z)] = np.nan
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    part = out_path.with_name(out_path.name + ".part")
    with rasterio.open(
        part, "w", driver="GTiff", height=z.shape[0], width=z.shape[1], count=1, dtype="float32",
        crs=crs, transform=wtr, nodata=np.nan, compress="deflate",
    ) as dst:
        dst.write(z, 1)
    os.replace(part, out_path)
    return {
        "shape": [int(z.shape[0]), int(z.shape[1])],
        "window_pixels": [int(c0), int(r0), int(c1), int(r1)],
        "read_s": read_s,
        "valid_fraction": float(np.isfinite(z).mean()),
        "path": out_path,
        "bytes": out_path.stat().st_size,
    }


# ---------------------------------------------------------------- nulls

def explain_nulls(path: Path, lat: float, lon: float, body: str, cfg: dict[str, Any],
                  feats: dict[str, float | None]) -> dict[str, str]:
    """Reason for each null feature of an ok window (STANDARDS 4 undefined conditions), from the same grid."""
    L = float(cfg["grid"]["L_m"])
    R = float(cfg["grid"]["R_m"])
    z, mask, _ = gridmod.load_local_grid(path, lat, lon, body, L, R)
    valid = mask & np.isfinite(z)
    radius = int(cfg["tpi"]["radius_px"])
    out: dict[str, str] = {}
    for name, value in feats.items():
        if value is not None:
            continue
        if name == "hi":
            vals = z[valid]
            p5, p95 = np.percentile(vals, [5, 95])
            out[name] = f"flat: P95-P5 = {float(p95 - p5):.3g} m < 1e-6 m (STANDARDS 4)"
        elif name == "hurst":
            ptp = float(np.ptp(z[valid]))
            out[name] = ("flat: z constant over the window" if ptp == 0.0
                         else f"zero increments at a lag although z range is {ptp:.3g} m (unexpected)")
        elif name in ("slope_p95_deg", "coherence"):
            n_usable = int(metrics.slope_deg(z, mask, L).size)
            out[name] = f"{n_usable} usable gradient pixels < 50 (STANDARDS 4)"
        elif name in ("ridge_pct", "valley_pct"):
            _, full = metrics.tpi(z, mask, radius)
            out[name] = f"no fully valid TPI disk (valid TPI pixels = {int(full.sum())})"
    return out


# ---------------------------------------------------------------- one window

def measure_window(c: dict[str, Any], body: str, cfg: dict[str, Any], clip_fn, clip_dir: Path,
                   log: RunLog) -> dict[str, Any]:
    """Fetch one window (clip_fn), measure it (measure_raw), time both, explain nulls. Never patches a value."""
    rec: dict[str, Any] = {k: v for k, v in c.items()}
    rec.update(body=body, clip=None, clip_bytes=None, clip_sha256=None, fetch_s=None, measure_s=None,
               seconds=None, status="error", reason=None, features=None, null_reasons={})
    out = clip_dir / f"{c['id']}.tif"
    t0 = time.perf_counter()
    try:
        info = clip_fn(out)
    except Exception as exc:  # the reason is logged and kept; the window is not patched
        rec.update(reason=f"fetch: {type(exc).__name__}: {str(exc)[:300]}", seconds=time.perf_counter() - t0)
        log.event("error", f"{c['id']} fetch failed", reason=rec["reason"])
        return rec
    t1 = time.perf_counter()
    m = measure_raw(out, c["lat"], c["lon"], body, cfg)
    t2 = time.perf_counter()
    rec.update(
        clip=rel(out), clip_bytes=int(out.stat().st_size), clip_sha256=sha256_file(out),
        fetch_s=t1 - t0, measure_s=t2 - t1, seconds=t2 - t0,
        status=m["status"], reason=m["reason"], native_res_m=m["native_res_m"], coverage=m["coverage"],
        n_valid=m["n_valid"], L=m["L"], R=m["R"], crs_src=m["crs_src"], crs_dst=m["crs_dst"],
        features=m["features"],
    )
    if m["status"] == "ok":
        feats = m["features"]
        if any(v is None for v in feats.values()):
            rec["null_reasons"] = explain_nulls(out, c["lat"], c["lon"], body, cfg, feats)
    else:
        log.event("skip" if m["status"] == "skipped" else "error", f"{c['id']} {m['status']}", reason=m["reason"])
    return rec


# ---------------------------------------------------------------- body runs

def run_mars(cfg: dict[str, Any]) -> dict[str, Any]:
    """40 Mars windows: remote clip, then measure. Writes parts/mars.json."""
    log = RunLog(OUT, STAGE)
    half_m = float(cfg["grid"]["R_m"]) + MARGIN_M
    t_start = time.perf_counter()
    source = mars_source_info()
    log.event("info", "mars source header", **{k: source[k] for k in ("native_res_m", "L_ge_2x_native", "tiled")})
    centres, rejected, draws = mars_centres(N_MARS, SEED, half_m)
    for r in rejected:
        log.event("info", "centre redrawn (antimeridian)", **r)
    records = []
    for c in centres:
        clip_info: dict[str, Any] = {}

        def clip_fn(out: Path, c=c, clip_info=clip_info) -> dict[str, Any]:
            info = mars_window_clip(c["lat"], c["lon"], half_m, out)
            clip_info.update(info)
            return info

        rec = measure_window(c, "mars", cfg, clip_fn, MARS_CLIPS, log)
        rows = clip_info["shape"][0]
        rec.update(source_url=MARS_URL, clip_read_s=clip_info.get("read_s"), clip_shape=clip_info.get("shape"),
                   remote_MB_strip_estimate=round(rows * source["bytes_per_row_full_width"] / 1e6, 2))
        records.append(rec)
        print(f"{rec['id']} {rec['status']} {rec['seconds']:.1f}s", flush=True)
    part = {"body": "mars", "source": source, "centres_draws": draws, "rejected_centres": rejected,
            "seed": SEED, "half_m": half_m, "records": records, "run_wall_s": time.perf_counter() - t_start,
            "written": utc_now()}
    write_json(PARTS / "mars.json", part)
    return part


def run_earth(cfg: dict[str, Any]) -> dict[str, Any]:
    """40 Earth windows from the pool index: NASADEM clip via fetch.stac_clip, then measure. Writes parts/earth.json."""
    log = RunLog(OUT, STAGE)
    t_start = time.perf_counter()
    centres = earth_centres(N_EARTH, SEED)
    records = []
    for c in centres:
        clip_info: dict[str, Any] = {}

        def clip_fn(out: Path, c=c, clip_info=clip_info) -> dict[str, Any]:
            info = fetch.stac_clip(EARTH_COLLECTION, EARTH_ASSET, c["lat"], c["lon"], EARTH_HALF_KM, out)
            clip_info.update(info)
            return {"path": out, "bytes": info["bytes"]}

        rec = measure_window(c, "earth", cfg, clip_fn, EARTH_CLIPS, log)
        rec.update(stac_items=clip_info.get("items"), stac_native_res_deg=clip_info.get("native_res_deg"),
                   stac_valid_fraction=clip_info.get("valid_fraction"), stac_shape=clip_info.get("shape"))
        records.append(rec)
        print(f"{rec['id']} {rec['status']} {rec['seconds']:.1f}s", flush=True)
    part = {"body": "earth", "source": {"collection": EARTH_COLLECTION, "asset": EARTH_ASSET,
                                       "half_km": EARTH_HALF_KM, "pool_index": rel(POOL_INDEX)},
            "centres_draws": N_EARTH, "rejected_centres": [], "seed": SEED, "records": records,
            "run_wall_s": time.perf_counter() - t_start, "written": utc_now()}
    write_json(PARTS / "earth.json", part)
    return part


# ---------------------------------------------------------------- assemble

def summarise_body(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts, feature ranges (min, median, max over ok windows), null reasons, and timing per body."""
    ok = [r for r in records if r["status"] == "ok"]
    ranges: dict[str, Any] = {}
    for f in FEATURES:
        vals = [r["features"][f] for r in ok if r["features"] and r["features"][f] is not None]
        ranges[f] = ({"n": len(vals), "min": min(vals), "median": statistics.median(vals), "max": max(vals)}
                     if vals else {"n": 0, "min": None, "median": None, "max": None})
    nulls: dict[str, dict[str, int]] = {}
    for f in FEATURES:
        reasons = Counter(r["null_reasons"].get(f, "unexplained") for r in ok
                          if r["features"] and r["features"][f] is None)
        if reasons:
            nulls[f] = dict(reasons)
    secs = [r["seconds"] for r in records if r.get("seconds") is not None]
    clips = [r["clip_bytes"] for r in records if r.get("clip_bytes")]
    timing = {
        "n_windows": len(records),
        "seconds_mean": statistics.mean(secs) if secs else None,
        "seconds_median": statistics.median(secs) if secs else None,
        "seconds_min": min(secs) if secs else None,
        "seconds_max": max(secs) if secs else None,
        "fetch_s_mean": _mean([r.get("fetch_s") for r in records]),
        "measure_s_mean": _mean([r.get("measure_s") for r in records]),
        "clip_MB_mean": (statistics.mean(clips) / 1e6) if clips else None,
        "clip_MB_max": (max(clips) / 1e6) if clips else None,
        "clip_MB_min": (min(clips) / 1e6) if clips else None,
    }
    return {
        "status_counts": dict(Counter(r["status"] for r in records)),
        "reasons_not_ok": [{"id": r["id"], "status": r["status"], "reason": r["reason"]}
                           for r in records if r["status"] != "ok"],
        "native_res_m": sorted({round(r["native_res_m"], 4) for r in records if r.get("native_res_m")}),
        "coverage_min": _min([r.get("coverage") for r in records]),
        "feature_ranges": ranges,
        "null_counts_by_reason": nulls,
        "timing": timing,
    }


def _mean(vals: list[Any]) -> float | None:
    v = [float(x) for x in vals if x is not None]
    return statistics.mean(v) if v else None


def _min(vals: list[Any]) -> float | None:
    v = [float(x) for x in vals if x is not None]
    return min(v) if v else None


def extrapolate(timing: dict[str, Any], n_target: int, records: list[dict[str, Any]], mars: bool) -> dict[str, Any]:
    """Time and disk for n_target windows at this scale with WORKERS_EXTRAPOLATION parallel workers (ideal scaling).

    Wall time = n * mean seconds per window / workers (and twice that at half parallel efficiency). Disk = n * mean
    clip size (clips kept), and the 81 x 81 float32 grid per window if only the grid were kept. Mars also: remote
    transfer estimate per window (rows x full row bytes, the strips are read whole).
    """
    per = timing["seconds_mean"]
    out: dict[str, Any] = {
        "n_target": n_target,
        "workers": WORKERS_EXTRAPOLATION,
        "wall_hours_ideal": (n_target * per / WORKERS_EXTRAPOLATION / 3600.0) if per else None,
        "wall_hours_if_half_efficiency": (2.0 * n_target * per / WORKERS_EXTRAPOLATION / 3600.0) if per else None,
        "clips_disk_GB": (n_target * timing["clip_MB_mean"] / 1000.0) if timing["clip_MB_mean"] else None,
        "grid_only_disk_GB": n_target * 81 * 81 * 4 / 1e9,
    }
    if mars:
        est = [r["remote_MB_strip_estimate"] for r in records if r.get("remote_MB_strip_estimate")]
        mb = statistics.mean(est) if est else None
        out["remote_MB_per_window_estimate"] = mb
        out["remote_GB_estimate"] = (n_target * mb / 1000.0) if mb else None
    return out


def assemble() -> dict[str, Any]:
    """Build data/derived/regional/sample.json from the two parts, with the STANDARDS 7 provenance block."""
    parts = {b: load_json(PARTS / f"{b}.json") for b in ("mars", "earth")}
    cfg = load_cfg()
    bodies: dict[str, Any] = {}
    targets = {"mars": 3000, "earth": 2000}
    for b in ("mars", "earth"):
        summ = summarise_body(parts[b]["records"])
        summ["extrapolation"] = extrapolate(summ["timing"], targets[b], parts[b]["records"], mars=(b == "mars"))
        summ["centres"] = {"seed": SEED, "n": len(parts[b]["records"]), "draws": parts[b]["centres_draws"],
                           "rejected": parts[b]["rejected_centres"], "run_wall_s": parts[b]["run_wall_s"]}
        summ["source"] = parts[b]["source"]
        bodies[b] = summ
    inputs: list[tuple[str, Path]] = []
    for b, sid in (("mars", MARS_SOURCE_ID), ("earth", EARTH_SOURCE_ID)):
        for r in parts[b]["records"]:
            if r.get("clip"):
                inputs.append((sid, ROOT / r["clip"]))
    inputs.append(("earth_pool_index", POOL_INDEX))
    block = prov.build_provenance(STAGE, CFG_PATH, [{"source_id": s, "path": str(p)} for s, p in inputs])
    for rec, (_, p) in zip(block["inputs"], inputs):
        rec["path"] = rel(p)
    block["config_file"] = rel(CFG_PATH)
    doc = {
        **block,
        "status": "EXPERIMENTAL, STANDARDS 10.10 (not validated; not comparable with the 100 m scale)",
        "design": {
            "seed": SEED, "n_mars": N_MARS, "n_earth": N_EARTH, "mars_lat_band_deg": [-MARS_LAT_LIMIT, MARS_LAT_LIMIT],
            "mars_sampling": "uniform in sin(lat) and lon, on the sphere",
            "earth_sampling": "seeded draw without replacement from data/raw/earth/pool/index.json",
            "earth_window_half_km": EARTH_HALF_KM, "mars_clip_margin_m": MARGIN_M,
            "grid": {"L_m": cfg["grid"]["L_m"], "R_m": cfg["grid"]["R_m"], "n": 2 * math.ceil(cfg["grid"]["R_m"] / cfg["grid"]["L_m"]) + 1},
            "clips_kept": True, "workers_for_extrapolation": WORKERS_EXTRAPOLATION,
            "gdal": {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES (mars)"},
        },
        "bodies": bodies,
        "windows": {b: parts[b]["records"] for b in ("mars", "earth")},
    }
    write_json(SAMPLE_JSON, doc)
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Regional-scale feasibility sample (STANDARDS 10.10, EXPERIMENTAL).")
    ap.add_argument("--body", choices=["mars", "earth"], default=None, help="measure one body's sample")
    ap.add_argument("--assemble", action="store_true", help="write sample.json from the two parts")
    args = ap.parse_args(argv)
    if args.body is None and not args.assemble:
        ap.error("give --body mars|earth and/or --assemble")
    cfg = load_cfg()
    if args.body == "mars":
        run_mars(cfg)
    if args.body == "earth":
        run_earth(cfg)
    if args.assemble:
        doc = assemble()
        print(f"wrote {rel(SAMPLE_JSON)}")
        for b in ("mars", "earth"):
            print(b, doc["bodies"][b]["status_counts"], doc["bodies"][b]["timing"]["seconds_mean"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
