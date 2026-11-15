"""Earth search pool, coarse design (coordinator redesign, 2026-11-14).

Subcommands (run in this order; every step is resumable; a step stops and reports if nothing completes in 5 min)
  items                 STAC search of esa-worldcover 2021 (land tiles only) -> _worldcover_coarse/items.json
  coarse [--sample N]   one read per 3x3 degree tile: map COG at 300 x 300 (about 1.1 km, nearest, GDAL overviews),
                        bare = class in {60, 70, 100} -> _worldcover_coarse/<item>.npy (cached; finished tiles skipped)
  spacing               candidate centres on a regular lat/lon grid of step s, WorldCover share within 4 km of each
                        centre (haversine on pixel centres); counts per s -> _worldcover_coarse/spacing.json
  candidates            keeps share >= 0.8 at the chosen s; a seeded (20261114) uniform subset of exactly 2000 if more
                        -> candidates.json
  clip [--sample N]     NASADEM half width 4.5 km (deflate GeoTIFF) -> pool/pool_NNNNN.tif (8 threads, 60 s per window)
  index                 pool/index.json: [{id, lat, lon, worldcover_share, near_known_analog, path, valid_fraction}],
                        only windows whose clip exists and valid_fraction >= 0.9
  regions               worldcover_share (same coarse arrays, same 4 km disk) for the 20 validation regions in
                        config/regions.json; statuses are not changed

Outputs: data/raw/earth/pool/ (raw, git-ignored), data/raw/fetch_log.jsonl (one event per tile or window).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analog.io import fetch  # noqa: E402
from analog.io.fetch import FetchError  # noqa: E402

os.environ.setdefault("GDAL_HTTP_TIMEOUT", "60")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")

CONFIG = ROOT / "config"
RAW = ROOT / "data" / "raw"
POOL = RAW / "earth" / "pool"
COARSE = POOL / "_worldcover_coarse"
ITEMS = COARSE / "items.json"
SPACING = COARSE / "spacing.json"
CANDIDATES = POOL / "candidates.json"
INDEX = POOL / "index.json"
MANIFEST = RAW / "manifest.json"
LOG = RAW / "fetch_log.jsonl"

SEED = 20261114  # STANDARDS section 2
LAT_MIN, LAT_MAX = -56.0, 60.0  # NASADEM band and search band (STANDARDS 10.2)
TARGET_N = 2000
MIN_SHARE = 0.8
RADIUS_KM = 4.0  # screening disk
N_COARSE = 300  # per 3-degree tile: 0.01 degree = about 1.1 km per pixel
PIX_DEG = 3.0 / N_COARSE
WIN_PX = 5  # pixel half window around a centre (covers the 4 km disk)
MARGIN_DEG = 0.07  # centres at least 7 px from a tile edge, so the window stays inside the tile
SPACINGS = [0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2]
TILE_TIMEOUT_S = 60
WINDOW_TIMEOUT_S = 60
STALL_S = 300
WORKERS_COARSE = 16
WORKERS_CLIP = 8
CLIP_HALF_KM = 4.5
MIN_VALID = 0.9
EXCLUDE_KM = 25.0
BARE_CLASSES = (60, 70, 100)


def log(event: dict[str, Any]) -> None:
    """Append one JSON line to data/raw/fetch_log.jsonl."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"time": fetch.utc_now(), **event}, ensure_ascii=False) + "\n")


def rel(path: Path) -> str:
    """Repo-relative POSIX path."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


def run_with_timeout(fn, arg, timeout: float):
    """Run fn(arg) in a helper thread and wait at most ``timeout`` seconds.

    Rule: a timed-out call is reported as a failure; its thread is abandoned (never joined).
    """
    ex = ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(fn, arg)
    try:
        return fut.result(timeout=timeout)
    finally:
        ex.shutdown(wait=False)


def load_items() -> list[dict[str, Any]]:
    """Tile list written by the 'items' step."""
    if not ITEMS.exists():
        raise SystemExit("run 'items' first")
    return json.loads(ITEMS.read_text(encoding="utf-8"))


def known_analogs() -> list[dict[str, Any]]:
    """Entries with role known_analog in config/regions.json."""
    regions = json.loads((CONFIG / "regions.json").read_text(encoding="utf-8"))["regions"]
    return [r for r in regions if r["role"] == "known_analog"]


def cmd_items(_: argparse.Namespace) -> int:
    """STAC search for WorldCover 2021 v200 tiles intersecting the band (only land tiles exist)."""
    import pystac_client

    COARSE.mkdir(parents=True, exist_ok=True)
    cat = pystac_client.Client.open(fetch.PC_STAC_URL)
    found = cat.search(collections=["esa-worldcover"], bbox=[-180.0, LAT_MIN, 180.0, LAT_MAX], max_items=10000)
    items = []
    for it in found.items():
        if "2021" not in it.id or "v200" not in it.id:
            continue
        items.append({"id": it.id, "bbox": [float(v) for v in it.bbox], "href": it.assets["map"].href})
    items.sort(key=lambda d: d["id"])
    tmp = ITEMS.with_suffix(".json.part")
    tmp.write_text(json.dumps(items, indent=1), encoding="utf-8")
    os.replace(tmp, ITEMS)
    print(json.dumps({"tiles": len(items), "example": items[0]["id"] if items else None}, indent=2))
    return 0


def read_tile_bare(href: str) -> np.ndarray:
    """Read one WorldCover map tile at N_COARSE x N_COARSE (nearest; GDAL picks an overview) and return bare mask."""
    import planetary_computer
    import rasterio
    from rasterio.enums import Resampling

    signed = planetary_computer.sign(href)
    with rasterio.open(f"/vsicurl/{signed}") as ds:
        arr = ds.read(1, out_shape=(N_COARSE, N_COARSE), resampling=Resampling.nearest)
    return np.isin(arr, BARE_CLASSES)


def tile_task(item: dict[str, Any]) -> dict[str, Any]:
    """Read one tile with a 60 s limit, retry once, cache as .npy. Returns the outcome record."""
    out = COARSE / f"{item['id']}.npy"
    reason = ""
    for attempt in (1, 2):
        t0 = time.time()
        try:
            bare = run_with_timeout(read_tile_bare, item["href"], TILE_TIMEOUT_S)
        except Exception as exc:  # timeout, HTTP or GDAL error: logged, never patched
            reason = f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:160]}"
            continue
        part = COARSE / f"{item['id']}.part.npy"
        np.save(part, bare)
        os.replace(part, out)
        return {"id": item["id"], "ok": True, "seconds": round(time.time() - t0, 2), "attempts": attempt,
                "bare_share": float(bare.mean())}
    return {"id": item["id"], "ok": False, "reason": reason}


def cmd_coarse(args: argparse.Namespace) -> int:
    """Read every tile (or an evenly spread sample of N tiles) into the coarse cache."""
    COARSE.mkdir(parents=True, exist_ok=True)
    items = load_items()
    if args.sample:
        idx = sorted({int(k * len(items) / args.sample) for k in range(args.sample)})
        items = [items[i] for i in idx]
    todo = [it for it in items if not (COARSE / f"{it['id']}.npy").exists()]
    print(f"tiles selected={len(items)} to_read={len(todo)} workers={WORKERS_COARSE}", flush=True)
    t0 = time.time()
    ex = ThreadPoolExecutor(max_workers=WORKERS_COARSE)
    pending = {ex.submit(tile_task, it) for it in todo}
    n = ok = fail = 0
    secs: list[float] = []
    stalled = False
    try:
        while pending:
            done, pending = wait(pending, timeout=STALL_S, return_when=FIRST_COMPLETED)
            if not done:
                stalled = True
                print("STALL: no tile completed in 300 s; stopping (finished tiles are cached)", flush=True)
                break
            for fut in done:
                r = fut.result()
                n += 1
                if r["ok"]:
                    ok += 1
                    secs.append(r["seconds"])
                    log({"event": "coarse_tile", **r})
                else:
                    fail += 1
                    log({"event": "coarse_tile_error", **r})
                if n % 50 == 0 or n == len(todo):
                    print(f"coarse progress {n}/{len(todo)} ok={ok} fail={fail} elapsed_s={time.time() - t0:.0f}",
                          flush=True)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    summary = {"selected": len(items), "read_now": ok, "failed_now": fail, "stalled": stalled,
               "wall_s": round(time.time() - t0, 1),
               "median_s_per_tile": round(float(np.median(secs)), 2) if secs else None,
               "mean_s_per_tile": round(float(np.mean(secs)), 2) if secs else None}
    log({"event": "coarse_run", **summary})
    print(json.dumps(summary, indent=2), flush=True)
    return 1 if stalled else 0


def nominal_bbox(tile_id: str) -> list[float]:
    """Nominal 3x3 degree extent [minx, miny, maxx, maxy] from the WorldCover name (e.g. ..._N00E006_Map).

    Rule: the cached array is the full nominal tile (300 px = 3 deg). STAC item bboxes are the extent of
    valid data (e.g. [6.16, 0, 9, 3]) and must not be used for the pixel grid.
    """
    import re

    m = re.search(r"_([NS])(\d{2})([EW])(\d{3})$", tile_id)
    if not m:
        raise ValueError(f"no tile name in {tile_id!r}")
    lat0 = int(m.group(2)) * (1 if m.group(1) == "N" else -1)
    lon0 = int(m.group(4)) * (1 if m.group(3) == "E" else -1)
    return [float(lon0), float(lat0), float(lon0 + 3), float(lat0 + 3)]


def tile_arrays() -> list[tuple[list[float], np.ndarray, str]]:
    """(nominal bbox, bare mask, id) for every tile already in the coarse cache."""
    tiles = []
    for it in load_items():
        p = COARSE / f"{it['id']}.npy"
        if p.exists():
            tiles.append((nominal_bbox(it["id"]), np.load(p), it["id"]))
    return tiles


def grid_candidates(tiles, step: float) -> tuple[list[tuple[float, float, float, str]], int]:
    """Centres of a regular grid of step s inside each tile, starting at the tile's SW corner plus the margin.

    Each tile has its own grid (same phase everywhere; a global grid aliases with the tile edges).

    Share = bare pixels / pixels within 4 km of the centre (haversine on pixel centres). Returns the kept
    (lat, lon, share, tile id) list and the number of centres tested.
    """
    kept: list[tuple[float, float, float, str]] = []
    tested = 0
    off = np.arange(-WIN_PX, WIN_PX + 1)
    for bbox, bare, tid in tiles:
        minx, miny, maxx, maxy = bbox
        nk = int(math.floor((maxy - MARGIN_DEG - (miny + MARGIN_DEG)) / step + 1e-9)) + 1
        nm = int(math.floor((maxx - MARGIN_DEG - (minx + MARGIN_DEG)) / step + 1e-9)) + 1
        if nk < 1 or nm < 1:
            continue
        KK, MM = np.meshgrid(np.arange(nk), np.arange(nm), indexing="ij")
        lat = miny + MARGIN_DEG + KK.ravel() * step
        lon = minx + MARGIN_DEG + MM.ravel() * step
        keep = (lat >= LAT_MIN) & (lat <= LAT_MAX) & (lon < 180.0)
        lat, lon = lat[keep], lon[keep]
        if lat.size == 0:
            continue
        tested += int(lat.size)
        i0 = np.round((maxy - lat) / PIX_DEG - 0.5).astype(int)
        j0 = np.round((lon - minx) / PIX_DEG - 0.5).astype(int)
        II = i0[:, None, None] + off[None, :, None]
        JJ = j0[:, None, None] + off[None, None, :]
        plat = maxy - (II + 0.5) * PIX_DEG
        plon = minx + (JJ + 0.5) * PIX_DEG
        d = fetch.haversine_km_np(lat[:, None, None], lon[:, None, None], plat, plon)
        mask = d <= RADIUS_KM
        n_in = mask.sum(axis=(1, 2))
        hit = (bare[II, JJ] & mask).sum(axis=(1, 2))
        share = hit / n_in
        for k in np.nonzero(share >= MIN_SHARE)[0]:
            kept.append((float(lat[k]), float(lon[k]), float(share[k]), tid))
    return kept, tested


def cmd_spacing(_: argparse.Namespace) -> int:
    """Count kept centres for each step in SPACINGS; choose the largest step with count >= 2000."""
    tiles = tile_arrays()
    print(f"tiles with cached arrays: {len(tiles)}", flush=True)
    table = []
    for s in SPACINGS:
        t0 = time.time()
        kept, tested = grid_candidates(tiles, s)
        row = {"step_deg": s, "centres_tested": tested, "kept": len(kept), "seconds": round(time.time() - t0, 1)}
        table.append(row)
        print(json.dumps(row), flush=True)
    ok_steps = [r["step_deg"] for r in table if r["kept"] >= TARGET_N]
    chosen = max(ok_steps) if ok_steps else None
    out = {"table": table, "target": TARGET_N, "chosen_step_deg": chosen, "tiles_used": len(tiles)}
    COARSE.mkdir(parents=True, exist_ok=True)
    SPACING.write_text(json.dumps(out, indent=1), encoding="utf-8")
    log({"event": "pool_spacing", "chosen_step_deg": chosen, "tiles": len(tiles)})
    print(f"chosen_step_deg={chosen}", flush=True)
    return 0 if chosen is not None else 1


def cmd_candidates(_: argparse.Namespace) -> int:
    """Kept centres at the chosen step; exactly 2000 by a seeded uniform subset if there are more."""
    if not SPACING.exists():
        raise SystemExit("run 'spacing' first")
    spec = json.loads(SPACING.read_text(encoding="utf-8"))
    step = spec["chosen_step_deg"]
    if step is None:
        raise SystemExit("no step gives >= 2000 windows")
    kept, tested = grid_candidates(tile_arrays(), step)
    total = len(kept)
    if total > TARGET_N:
        rng = random.Random(SEED)
        kept = rng.sample(kept, TARGET_N)
    kept.sort(key=lambda r: (r[0], r[1]))
    payload = {"step_deg": step, "seed": SEED, "kept_before_subsample": total, "centres_tested": tested,
               "candidates": [{"lat": round(a, 6), "lon": round(b, 6), "worldcover_share": round(c, 6), "tile": t}
                              for a, b, c, t in kept]}
    POOL.mkdir(parents=True, exist_ok=True)
    tmp = CANDIDATES.with_suffix(".json.part")
    tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    os.replace(tmp, CANDIDATES)
    print(json.dumps({"step_deg": step, "kept_before_subsample": total, "candidates": len(kept)}, indent=2))
    return 0


def pool_id(i: int) -> str:
    """pool_00001 ... (snake_case, deterministic)."""
    return f"pool_{i + 1:05d}"


def clip_one(i: int, rec: dict[str, Any]) -> dict[str, Any]:
    """NASADEM 4.5 km half width clip for candidate i. Returns the event record."""
    wid = pool_id(i)
    out = fetch.build_raw_path(RAW, "earth", "pool", f"{wid}.tif")
    t0 = time.time()
    try:
        meta = fetch.stac_clip("nasadem", "elevation", rec["lat"], rec["lon"], CLIP_HALF_KM, out)
    except FetchError as exc:
        return {"event": "pool_clip_error", "id": wid, "lat": rec["lat"], "lon": rec["lon"], "reason": str(exc)[:300]}
    return {"event": "pool_clip", "id": wid, "lat": rec["lat"], "lon": rec["lon"], "path": rel(out),
            "bytes": meta["bytes"], "sha256": meta["sha256"], "valid_fraction": meta["valid_fraction"],
            "seconds": round(time.time() - t0, 2)}


def cmd_clip(args: argparse.Namespace) -> int:
    """Clip NASADEM windows for the candidates (resumable); --sample N takes N evenly spread candidates."""
    if not CANDIDATES.exists():
        raise SystemExit("run 'candidates' first")
    cand = json.loads(CANDIDATES.read_text(encoding="utf-8"))["candidates"]
    idx = list(range(len(cand)))
    if args.sample:
        idx = sorted({int(k * len(cand) / args.sample) for k in range(args.sample)})
    todo = [i for i in idx if not fetch.build_raw_path(RAW, "earth", "pool", f"{pool_id(i)}.tif").exists()]
    print(f"candidates={len(cand)} selected={len(idx)} to_clip={len(todo)} workers={WORKERS_CLIP}", flush=True)
    t0 = time.time()
    ex = ThreadPoolExecutor(max_workers=WORKERS_CLIP)
    pending = {ex.submit(run_with_timeout, lambda a: clip_one(*a), (i, cand[i]), WINDOW_TIMEOUT_S): i for i in todo}
    n = ok = fail = 0
    secs: list[float] = []
    stalled = False
    try:
        while pending:
            done, pending = wait(pending, timeout=STALL_S, return_when=FIRST_COMPLETED)
            if not done:
                stalled = True
                print("STALL: no window completed in 300 s; stopping", flush=True)
                break
            for fut in done:
                n += 1
                try:
                    ev = fut.result()
                except Exception as exc:  # timeout (60 s) or unexpected error: a failure record
                    ev = {"event": "pool_clip_error", "reason": f"{type(exc).__name__}: {str(exc)[:200]}"}
                if ev["event"] == "pool_clip":
                    ok += 1
                    secs.append(ev["seconds"])
                else:
                    fail += 1
                log(ev)
                if n % 50 == 0 or n == len(todo):
                    print(f"clip progress {n}/{len(todo)} ok={ok} fail={fail} elapsed_s={time.time() - t0:.0f}",
                          flush=True)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    wall = time.time() - t0
    mb = [fetch.build_raw_path(RAW, "earth", "pool", f"{pool_id(i)}.tif").stat().st_size / 1e6
          for i in idx if fetch.build_raw_path(RAW, "earth", "pool", f"{pool_id(i)}.tif").exists()]
    summary = {"selected": len(idx), "clipped_now": ok, "failed_now": fail, "stalled": stalled,
               "wall_s": round(wall, 1), "wall_s_per_window": round(wall / max(1, n), 3),
               "median_s_per_window": round(float(np.median(secs)), 2) if secs else None,
               "mean_MB_per_window": round(float(np.mean(mb)), 3) if mb else None,
               "files_selected": len(mb)}
    log({"event": "pool_clip_run", **summary, "sample": args.sample})
    print(json.dumps(summary, indent=2), flush=True)
    return 1 if (stalled or fail) else 0


def cmd_index(_: argparse.Namespace) -> int:
    """index.json: one entry per candidate with a clip file and valid_fraction >= 0.9 (read from the file)."""
    import rasterio

    cand = json.loads(CANDIDATES.read_text(encoding="utf-8"))["candidates"]
    analogs = known_analogs()
    entries, low, missing = [], [], []
    for i, rec in enumerate(cand):
        path = fetch.build_raw_path(RAW, "earth", "pool", f"{pool_id(i)}.tif")
        if not path.exists():
            missing.append(pool_id(i))
            continue
        with rasterio.open(path) as ds:
            z = ds.read(1)
        valid = float(np.isfinite(z).mean())
        if valid < MIN_VALID:
            low.append(pool_id(i))
            continue
        dmin = min(fetch.haversine_km(rec["lat"], rec["lon"], a["lat"], a["lon"]) for a in analogs)
        entries.append({"id": pool_id(i), "lat": rec["lat"], "lon": rec["lon"],
                        "worldcover_share": rec["worldcover_share"], "near_known_analog": bool(dmin < EXCLUDE_KM),
                        "path": rel(path), "valid_fraction": valid})
    tmp = INDEX.with_suffix(".json.part")
    tmp.write_text(json.dumps(entries, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, INDEX)
    entry = {"path": rel(INDEX), "source_id": "nasadem_pool_index", "url": "local", "bytes": INDEX.stat().st_size,
             "sha256": fetch.sha256_file(INDEX), "created": fetch.utc_now(), "windows": len(entries)}
    items = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else []
    items = [e for e in items if e.get("path") != entry["path"]] + [entry]
    tmp_m = MANIFEST.with_suffix(".json.part")
    tmp_m.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_m, MANIFEST)
    summary = {"index_windows": len(entries), "valid_below_0.9": len(low), "missing_files": len(missing),
               "near_known_analog": sum(e["near_known_analog"] for e in entries)}
    log({"event": "pool_index", **summary})
    print(json.dumps(summary, indent=2))
    return 0


def disk_share_global(lat: float, lon: float, tiles_by_sw: dict[tuple[int, int], np.ndarray]) -> tuple[float, int]:
    """WorldCover bare share within 4 km of (lat, lon) using every cached tile (pixels absent from the cache count as not bare).

    Pixel grid: 0.01 degree cells aligned to multiples of 0.01 (the tile grid). Pixel centres within 4 km
    (haversine) are the disk. Returns (share, disk pixel count).
    """
    dlat = RADIUS_KM / 111.32
    dlon = RADIUS_KM / (111.32 * max(math.cos(math.radians(lat)), 1e-6))
    i0, i1 = math.floor((lat - dlat) / PIX_DEG) - 1, math.floor((lat + dlat) / PIX_DEG) + 1
    j0, j1 = math.floor((lon - dlon) / PIX_DEG) - 1, math.floor((lon + dlon) / PIX_DEG) + 1
    II, JJ = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1), indexing="ij")
    clat = (II + 0.5) * PIX_DEG
    clon = (JJ + 0.5) * PIX_DEG
    inside = fetch.haversine_km_np(lat, lon, clat, clon) <= RADIUS_KM
    clat, clon = clat[inside], clon[inside]
    n = int(clat.size)
    bare = 0
    for la, lo in zip(clat, clon):
        sw_lat = int(math.floor(la / 3.0)) * 3
        sw_lon = int(math.floor(lo / 3.0)) * 3
        arr = tiles_by_sw.get((sw_lat, sw_lon))
        if arr is None:
            continue
        row = int(round((sw_lat + 3.0 - la) / PIX_DEG - 0.5))
        col = int(round((lo - sw_lon) / PIX_DEG - 0.5))
        bare += int(arr[row, col])
    return bare / n, n


def cmd_regions(_: argparse.Namespace) -> int:
    """Write worldcover_share into the 20 validation regions (dev and reserved) from the coarse cache."""
    tiles_by_sw: dict[tuple[int, int], np.ndarray] = {}
    for bbox, bare, _tid in tile_arrays():
        tiles_by_sw[(int(round(bbox[1])), int(round(bbox[0])))] = bare
    path = CONFIG / "regions.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    out_rows = []
    for r in cfg["regions"]:
        if r["role"] not in ("dev", "reserved"):
            continue
        share, n = disk_share_global(r["lat"], r["lon"], tiles_by_sw)
        r["worldcover_share"] = round(share, 4)
        r["worldcover_share_method"] = "coarse 300x300 per 3 deg tile (about 1.1 km), 4 km disk, classes 60/70/100"
        out_rows.append({"id": r["id"], "role": r["role"], "class": r["class"], "share": round(share, 4),
                         "disk_px": n, "status": r["status"]})
    tmp = path.with_suffix(".json.part")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    log({"event": "pool_region_shares", "rows": out_rows})
    for row in out_rows:
        print(json.dumps(row))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("items").set_defaults(func=cmd_items)
    c = sub.add_parser("coarse")
    c.add_argument("--sample", type=int, default=0)
    c.set_defaults(func=cmd_coarse)
    sub.add_parser("spacing").set_defaults(func=cmd_spacing)
    sub.add_parser("candidates").set_defaults(func=cmd_candidates)
    cl = sub.add_parser("clip")
    cl.add_argument("--sample", type=int, default=0)
    cl.set_defaults(func=cmd_clip)
    sub.add_parser("index").set_defaults(func=cmd_index)
    sub.add_parser("regions").set_defaults(func=cmd_regions)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
