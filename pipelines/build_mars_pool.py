"""Mars pool: seeded CTX DTM windows for the unlocked atlas (STANDARDS 10.13).

Centres are drawn with seed 20261114, uniform on the sphere (lat = asin(u), u uniform in [-1, 1]; lon uniform in
[-180, 180)). For each centre the USGS STAC collection ``mro_ctx_controlled_usgs_dtms`` (CC0) is searched for DTMs
whose footprint bbox contains the 4.5 km half-width square; up to three candidates (largest bbox first) are read
through a remote window (/vsicurl/, original CRS). The candidate with the highest valid fraction inside the 4 km disk
wins. Accept if valid >= 0.90 and the CRS is the Mars sphere (3396190 m).

Subcommands are flags only:
  python pipelines/build_mars_pool.py --target 30      sample run (stops at 30 accepted)
  python pipelines/build_mars_pool.py --target 2000    full run (resumes: logged centre indices are skipped)
  python pipelines/build_mars_pool.py --summary        counts, Wilson 95% CI, sizes, latitude bands (no network)

Outputs (raw, git-ignored): data/raw/mars/pool/mars_NNNNN.tif, attempts.jsonl (one line per attempt),
index.json (accepted windows).

Notes on deviations found by probing the live STAC items (2026-11-13):
  * The CTX DTM item asset key is ``dtm`` in the items checked (27 of 27 in a Jezero bbox search), not ``dem``.
    The DEM key is chosen in this order: ``dem``, ``geoid_adjusted_dem``, ``dtm``; the key used is logged.
  * ``analog.io.fetch.km_to_deg`` uses Earth's 111.32 km per degree, so it is NOT used here. The Mars degree is
    R * pi / 180 with R = 3396190 m.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

os.environ.setdefault("GDAL_HTTP_TIMEOUT", "60")  # each HTTP request of a remote read is bounded at 60 s
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from analog.io import fetch  # noqa: E402  (helpers imported, not edited)

SEED = 20261114
COLLECTION = "mro_ctx_controlled_usgs_dtms"
STAC_SEARCH = "https://stac.astrogeology.usgs.gov/api/search"
USER_AGENT = fetch.USER_AGENT  # "SpaceApps2026-research"
MARS_R = 3396190.0  # IAU 2015 sphere, metres (STANDARDS section 2)
MARS_SPHERE_PROJ = fetch.BODY_SPHERE_PROJ["mars"]
HALF_WIDTH_M = 4500.0  # window half width (10.13)
DISK_RADIUS_M = 4000.0  # coverage disk radius (10.13)
MIN_VALID = 0.90
SEARCH_LIMIT = 50
MAX_CANDIDATES = 3
WORKERS = 8
STALL_S = 300.0  # stop if no attempt completes for 5 minutes
ASSET_KEYS = ("dem", "geoid_adjusted_dem", "dtm")
STATUSES = ("accepted", "no_dtm", "low_valid", "read_error")
LAT_BANDS = ((-90, -60), (-60, -30), (-30, 0), (0, 30), (30, 60), (60, 90))
MAX_CENTRES = 50000  # the centre sequence is deterministic; this bounds how far a run may go

POOL = ROOT / "data" / "raw" / "mars" / "pool"
ATTEMPTS = POOL / "attempts.jsonl"
INDEX = POOL / "index.json"


# ---------------------------------------------------------------- pure helpers (tested offline)

def centres(n: int, seed: int = SEED) -> list[tuple[float, float]]:
    """Seeded centres uniform on the sphere: lat = degrees(asin(u)), u ~ U[-1, 1]; lon ~ U[-180, 180).

    Formula: u uniform in [-1, 1] gives sin(lat) uniform in [-1, 1], which is the sphere-uniform law.
    Draws are sequential (u, then lon per centre), so the first k centres do not depend on n.
    """
    rng = random.Random(seed)
    out: list[tuple[float, float]] = []
    for _ in range(n):
        u = rng.uniform(-1.0, 1.0)
        lon = rng.uniform(-180.0, 180.0)
        out.append((math.degrees(math.asin(u)), lon))
    return out


def square_extent(lat: float, lon: float, half_m: float = HALF_WIDTH_M, radius_m: float = MARS_R):
    """Lon/lat bbox (w, s, e, n) of the square of half width ``half_m`` around (lat, lon).

    Formula: d = degrees(half_m / R). The square is taken in the equirectangular CTX CRS (standard parallel 0,
    x = R lon, y = R lat), so both half-extents are d in degrees. Latitude is clipped to [-90, 90].
    Lon is not wrapped here; see ``search_pieces``.
    """
    d = math.degrees(half_m / radius_m)
    return (lon - d, max(-90.0, lat - d), lon + d, min(90.0, lat + d))


def bbox_contains(item_bbox, sq) -> bool:
    """True if the item's bbox (w, s, e, n; e < w means it crosses the antimeridian) contains square ``sq``.

    Formula: lat: s_item <= s and n <= n_item. Lon: some shift k in {-360, 0, 360} gives
    w_item + k <= w and e <= e_item + k, with e_item += 360 when e_item < w_item.
    """
    if not item_bbox or len(item_bbox) != 4:
        return False
    iw, is_, ie, in_ = (float(v) for v in item_bbox)
    if ie < iw:
        ie += 360.0
    w, s, e, n = sq
    if not (is_ <= s and n <= in_):
        return False
    return any(iw + k <= w and e <= ie + k for k in (-360.0, 0.0, 360.0))


def bbox_area_km2_proxy(item_bbox) -> float:
    """Area of an item bbox scaled by cos(mid lat) (degrees^2 times cos); used only to rank candidates."""
    iw, is_, ie, in_ = (float(v) for v in item_bbox)
    if ie < iw:
        ie += 360.0
    mid = math.radians(0.5 * (is_ + in_))
    return (ie - iw) * (in_ - is_) * math.cos(mid)


def search_pieces(sq) -> list[tuple[float, float, float, float]]:
    """Split a square that crosses the antimeridian into two STAC bboxes with w <= e (each within [-180, 180])."""
    w, s, e, n = sq
    shift = math.floor((w + 180.0) / 360.0) * 360.0
    w -= shift
    e -= shift
    if e <= 180.0:
        return [(w, s, e, n)]
    return [(w, s, 180.0, n), (-180.0, s, e - 360.0, n)]


def dem_asset(feature: dict[str, Any]):
    """(asset key, href) of the DEM asset of a STAC item, or None. Order: dem, geoid_adjusted_dem, dtm."""
    assets = feature.get("assets") or {}
    for key in ASSET_KEYS:
        a = assets.get(key)
        if isinstance(a, dict) and a.get("href"):
            return key, a["href"]
    return None


def candidate_items(features: list[dict[str, Any]], sq) -> list[dict[str, Any]]:
    """Items with a DEM asset whose bbox contains ``sq``, largest bbox first, ties by id."""
    out = [f for f in features if dem_asset(f) is not None and bbox_contains(f.get("bbox"), sq)]
    out.sort(key=lambda f: (-bbox_area_km2_proxy(f["bbox"]), str(f.get("id"))))
    return out


def disk_valid(z, px_x_m: float, px_y_m: float) -> float | None:
    """Valid (finite) share of the 4 km disk around the window centre; delegates to fetch.disk_valid_fraction."""
    return fetch.disk_valid_fraction(z, px_x_m, px_y_m, DISK_RADIUS_M)


def wilson(k: int, n: int, z: float = 1.959964):
    """Wilson score interval (p, lo, hi) for k successes in n trials; None when n == 0.

    Formula: centre = (p + z^2/2n) / (1 + z^2/n); half = z sqrt(p(1-p)/n + z^2/4n^2) / (1 + z^2/n).
    """
    if n == 0:
        return None
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, centre - half, centre + half


# ---------------------------------------------------------------- I/O

def stac_search(pieces) -> list[dict[str, Any]]:
    """POST the STAC search once per bbox piece (limit 50, first page) and return unique items."""
    import requests

    seen: dict[str, dict[str, Any]] = {}
    for w, s, e, n in pieces:
        body = {"collections": [COLLECTION], "bbox": [w, s, e, n], "limit": SEARCH_LIMIT}
        r = requests.post(STAC_SEARCH, json=body, headers={"User-Agent": USER_AGENT}, timeout=60)
        r.raise_for_status()
        for f in r.json().get("features", []):
            seen.setdefault(str(f.get("id")), f)
    return list(seen.values())


def read_window(href: str, lat: float, lon: float, half_m: float = HALF_WIDTH_M) -> dict[str, Any]:
    """Remote windowed read of the DEM around (lat, lon) in the file's own CRS.

    Returns is_mars, crs (WKT), z (float64, nodata -> NaN, window array), transform, px_x, px_y, crs_obj.
    Only the window is read (rasterio boundless read over /vsicurl/). Nothing is written here.
    """
    import numpy as np
    import rasterio
    from pyproj import Transformer
    from rasterio.windows import from_bounds

    with rasterio.open(f"/vsicurl/{href}") as src:
        crs = src.crs
        wkt = crs.to_wkt() if crs is not None else ""
        is_mars = (
            crs is not None
            and bool(re.search(r"3396190", wkt))
            and crs.linear_units in ("metre", "meter")
        )
        if not is_mars:
            return {"is_mars": False, "crs": wkt[:200]}
        tr = Transformer.from_crs(MARS_SPHERE_PROJ, crs, always_xy=True)
        cx, cy = tr.transform(lon, lat)
        win = from_bounds(cx - half_m, cy - half_m, cx + half_m, cy + half_m, transform=src.transform)
        nodata = src.nodata
        fill = nodata if nodata is not None else float("nan")
        data = src.read(1, window=win, boundless=True, fill_value=fill)
        wtr = src.window_transform(win)
    z = data.astype("float64")
    if nodata is not None:
        z[z == nodata] = np.nan
    return {
        "is_mars": True,
        "crs": wkt,
        "crs_obj": crs,
        "z": z,
        "transform": wtr,
        "px_x": abs(float(wtr.a)),
        "px_y": abs(float(wtr.e)),
    }


def write_window(path: Path, z, transform, crs) -> int:
    """Write the window as a deflate GeoTIFF (float32, NaN nodata) in the original CRS. Returns bytes."""
    import numpy as np
    import rasterio

    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path, "w", driver="GTiff", height=int(z.shape[0]), width=int(z.shape[1]), count=1,
        dtype="float32", crs=crs, transform=transform, nodata=np.nan, compress="deflate",
    ) as dst:
        dst.write(z.astype("float32"), 1)
    return path.stat().st_size


# ---------------------------------------------------------------- one attempt (runs in a worker)

def attempt(idx: int, lat: float, lon: float) -> dict[str, Any]:
    """Search, read up to three candidates, keep the best valid fraction, classify. Never raises.

    The accepted window is written to a temporary file (``_tmp``); the main thread gives it its id and renames it.
    """
    t0 = time.time()
    rec: dict[str, Any] = {
        "centre_index": idx,
        "centre": {"lat": lat, "lon": lon},
        "status": None,
        "product_id": None,
        "valid": None,
        "asset": None,
        "n_candidates": 0,
        "reasons": [],
        "_tmp": None,
    }
    try:
        sq = square_extent(lat, lon)
        try:
            feats = stac_search(search_pieces(sq))
        except Exception as exc:  # network or HTTP error: logged, never retried silently
            rec["status"] = "read_error"
            rec["reasons"].append(f"stac: {type(exc).__name__}: {str(exc)[:160]}")
            return _done(rec, t0)
        cands = candidate_items(feats, sq)
        rec["n_candidates"] = len(cands)
        if not cands:
            rec["status"] = "no_dtm"
            rec["reasons"].append("no_item_bbox_contains_square")
            return _done(rec, t0)

        best = None
        n_err = 0
        n_mars = 0
        for f in cands[:MAX_CANDIDATES]:
            key, href = dem_asset(f)
            try:
                win = read_window(href, lat, lon)
            except Exception as exc:
                n_err += 1
                rec["reasons"].append(f"{f.get('id')}: {type(exc).__name__}: {str(exc)[:120]}")
                continue
            if not win["is_mars"]:
                rec["reasons"].append(f"{f.get('id')}: crs_not_mars")
                continue
            n_mars += 1
            v = disk_valid(win["z"], win["px_x"], win["px_y"])
            v = 0.0 if v is None else float(v)
            if best is None or v > best["valid"]:
                best = {"valid": v, "id": str(f.get("id")), "asset": key, "win": win}

        if best is None:
            rec["status"] = "read_error" if n_err > 0 else "no_dtm"
            return _done(rec, t0)

        rec["product_id"] = best["id"]
        rec["valid"] = best["valid"]
        rec["asset"] = best["asset"]
        if best["valid"] < MIN_VALID:
            rec["status"] = "low_valid"
            return _done(rec, t0)

        tmp = POOL / f"_tmp_{idx:06d}.tif"
        write_window(tmp, best["win"]["z"], best["win"]["transform"], best["win"]["crs_obj"])
        rec["status"] = "accepted"
        rec["_tmp"] = str(tmp)
        return _done(rec, t0)
    except Exception as exc:  # unexpected: logged as read_error with the reason
        rec["status"] = "read_error"
        rec["reasons"].append(f"unexpected: {type(exc).__name__}: {str(exc)[:160]}")
        return _done(rec, t0)


def _done(rec: dict[str, Any], t0: float) -> dict[str, Any]:
    rec["seconds"] = round(time.time() - t0, 3)
    rec["ts"] = fetch.utc_now()
    return rec


# ---------------------------------------------------------------- run loop

def load_log() -> list[dict[str, Any]]:
    if not ATTEMPTS.exists():
        return []
    out = []
    for line in ATTEMPTS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def _id_number(rec: dict[str, Any]) -> int:
    m = re.match(r"mars_(\d+)$", str(rec.get("id", "")))
    return int(m.group(1)) if m else 0


def write_index(log: list[dict[str, Any]]) -> int:
    acc = sorted((r for r in log if r["status"] == "accepted"), key=_id_number)
    rows = [
        {
            "id": r["id"],
            "lat": r["centre"]["lat"],
            "lon": r["centre"]["lon"],
            "product_id": r["product_id"],
            "path": r["path"],
            "valid_fraction": r["valid"],
        }
        for r in acc
    ]
    tmp = INDEX.with_name(INDEX.name + ".part")
    tmp.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    os.replace(tmp, INDEX)
    return len(rows)


def run(target: int, workers: int = WORKERS, max_centres: int = MAX_CENTRES) -> None:
    POOL.mkdir(parents=True, exist_ok=True)
    for stale in POOL.glob("_tmp_*.tif"):
        stale.unlink()
    log = load_log()
    done_idx = {r["centre_index"] for r in log}
    counts = {s: 0 for s in STATUSES}
    for r in log:
        counts[r["status"]] += 1
    n_acc = counts["accepted"]
    next_id = max([_id_number(r) for r in log] + [0]) + 1
    print(f"resume: logged={len(log)} accepted={n_acc} target={target}", flush=True)
    if n_acc >= target:
        print("target already reached", flush=True)
        write_index(log)
        return

    cents = centres(max_centres)
    todo = (i for i in range(max_centres) if i not in done_idx)
    inflight: dict[Any, int] = {}
    n_run = 0
    sec_sum = 0.0
    t_start = time.time()
    last_done = t_start
    stalled = False
    ex = ThreadPoolExecutor(max_workers=workers)

    def refill() -> None:
        while len(inflight) < 2 * workers and n_acc_box[0] < target:
            try:
                i = next(todo)
            except StopIteration:
                return
            lat, lon = cents[i]
            inflight[ex.submit(attempt, i, lat, lon)] = i

    n_acc_box = [n_acc]
    refill()
    while inflight:
        done, _ = wait(list(inflight), timeout=10, return_when=FIRST_COMPLETED)
        if not done:
            if time.time() - last_done > STALL_S:
                stalled = True
                print(f"STALL: no attempt completed in {STALL_S:.0f} s; stopping", flush=True)
                break
            continue
        for fut in done:
            inflight.pop(fut)
            rec = fut.result()
            last_done = time.time()
            tmp = rec.pop("_tmp")
            if rec["status"] == "accepted":
                if n_acc_box[0] >= target:  # beyond target: not logged, so a rerun picks this centre up again
                    if tmp:
                        Path(tmp).unlink(missing_ok=True)
                    continue
                rec["id"] = f"mars_{next_id:05d}"
                next_id += 1
                final = POOL / f"{rec['id']}.tif"
                os.replace(tmp, final)
                rec["path"] = f"data/raw/mars/pool/{rec['id']}.tif"
                rec["bytes"] = final.stat().st_size
                n_acc_box[0] += 1
            counts[rec["status"]] += 1
            with ATTEMPTS.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            log.append(rec)
            n_run += 1
            sec_sum += rec["seconds"]
            if n_run % 100 == 0:
                wall = time.time() - t_start
                print(
                    f"progress attempts={n_run} accepted={n_acc_box[0]} no_dtm={counts['no_dtm']} "
                    f"low_valid={counts['low_valid']} read_error={counts['read_error']} "
                    f"wall={wall:.0f}s wall_per_attempt={wall / n_run:.2f}s "
                    f"worker_mean={sec_sum / n_run:.2f}s",
                    flush=True,
                )
        refill()
    ex.shutdown(wait=not stalled, cancel_futures=True)
    n_index = write_index(log)
    wall = time.time() - t_start
    print(
        f"done attempts_this_run={n_run} accepted_total={n_acc_box[0]} index_rows={n_index} "
        f"wall={wall:.0f}s wall_per_attempt={(wall / n_run if n_run else 0):.2f}s "
        f"worker_mean={(sec_sum / n_run if n_run else 0):.2f}s",
        flush=True,
    )


def summary() -> None:
    log = load_log()
    n = len(log)
    counts = {s: sum(1 for r in log if r["status"] == s) for s in STATUSES}
    acc = [r for r in log if r["status"] == "accepted"]
    ci = wilson(counts["accepted"], n)
    print(f"attempts={n} " + " ".join(f"{s}={counts[s]}" for s in STATUSES))
    if ci:
        print(f"acceptance={ci[0]:.4f} wilson95=[{ci[1]:.4f}, {ci[2]:.4f}]")
    secs = [r["seconds"] for r in log if r.get("seconds") is not None]
    if secs:
        print(f"worker seconds per attempt: mean={sum(secs) / len(secs):.2f} max={max(secs):.2f}")
    size = 0
    for r in acc:
        p = ROOT / r["path"]
        if p.exists():
            size += p.stat().st_size
    if acc:
        print(f"accepted files={len(acc)} total_MB={size / 1e6:.1f} mean_MB={size / 1e6 / len(acc):.3f}")
    bands = []
    for lo, hi in LAT_BANDS:
        k = sum(1 for r in acc if lo <= r["centre"]["lat"] < hi or (hi == 90 and r["centre"]["lat"] == 90))
        bands.append(f"[{lo},{hi}):{k}")
    print("accepted by latitude band: " + " ".join(bands))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", type=int, default=2000, help="stop at this many accepted windows")
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--max-centres", type=int, default=MAX_CENTRES)
    ap.add_argument("--summary", action="store_true", help="print counts from attempts.jsonl and exit")
    args = ap.parse_args()
    if args.summary:
        summary()
        return
    run(args.target, args.workers, args.max_centres)
    summary()


if __name__ == "__main__":
    main()
