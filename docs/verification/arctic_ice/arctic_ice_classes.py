"""Arctic ice check, step 1: WorldCover class shares in the 4 km disk of each window.

Read-only w.r.t. the project. Writes only to docs/verification/arctic_ice (final) and to the scratchpad (tile cache).

- Selection (seed 20261114): all 39 closing windows; 40 drawn from the other 361 measured windows;
  12 pool windows (NASADEM) drawn from data/raw/earth/pool/index.json for the reference sheet.
- The coarse cache (_worldcover_coarse/*.npy) stores only a bool "bare" mask (classes 60/70/100), so class 70
  cannot be read from it. Each tile needed is re-read with the same method (300 x 300 per 3x3 deg tile, nearest,
  GDAL overview) keeping the class codes. The re-read bare mask is checked cell by cell against the cache.
- Shares are over ALL disk pixels (same denominator as the pool rule); pixels without a WorldCover tile count as
  "absent" and are reported separately.
"""
from __future__ import annotations

import json
import math
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path("C:/SpaceApps2026_Hackathon")
DER = ROOT / "data/derived/arctic_probe"
RAW = ROOT / "data/raw/earth/arctic_probe"
POOL = ROOT / "data/raw/earth/pool"
COARSE = RAW / "_worldcover_coarse"
OUT = ROOT / "docs/verification/arctic_ice"
SCR = Path(__file__).resolve().parent / "_scratch"
TILES = SCR / "tiles"

SEED = 20261114
EARTH_R_KM = 6371008.8 / 1000.0
RADIUS_KM = 4.0
N = 300
PIX = 3.0 / N
CLASSES = (60, 70, 100)
N_POOL_REF = 12
N_SAMPLE_OTHER = 40


def haversine_np(lat1, lon1, lat2, lon2):
    p1 = np.radians(np.asarray(lat1, dtype=float))
    p2 = np.radians(np.asarray(lat2, dtype=float))
    dp = p2 - p1
    dl = np.radians(np.asarray(lon2, dtype=float) - np.asarray(lon1, dtype=float))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2.0 * EARTH_R_KM * np.arcsin(np.minimum(1.0, np.sqrt(a)))


def sw_of(tile_id: str) -> tuple[int, int]:
    m = re.search(r"_([NS])(\d{2})([EW])(\d{3})$", tile_id)
    if not m:
        raise ValueError(tile_id)
    return (int(m.group(2)) * (1 if m.group(1) == "N" else -1),
            int(m.group(4)) * (1 if m.group(3) == "E" else -1))


def disk_cells(lat: float, lon: float) -> list[tuple[int, int, int, int]]:
    """Pixel centres (0.01 deg global grid) within 4 km of (lat, lon) as (sw_lat, sw_lon, row, col)."""
    dlat = RADIUS_KM / 111.32 + 0.02
    dlon = RADIUS_KM / (111.32 * max(math.cos(math.radians(lat)), 1e-6)) + 0.02
    i0, i1 = math.floor((lat - dlat) / PIX) - 1, math.floor((lat + dlat) / PIX) + 1
    j0, j1 = math.floor((lon - dlon) / PIX) - 1, math.floor((lon + dlon) / PIX) + 1
    II, JJ = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1), indexing="ij")
    clat = (II + 0.5) * PIX
    clon = (JJ + 0.5) * PIX
    inside = haversine_np(lat, lon, clat, clon) <= RADIUS_KM
    clat, clon = clat[inside], clon[inside]
    out = []
    for la, lo in zip(clat, clon):
        sw_lat = int(math.floor(la / 3.0)) * 3
        sw_lon = int(math.floor(lo / 3.0)) * 3
        row = int(round((sw_lat + 3.0 - la) / PIX - 0.5))
        col = int(round((lo - sw_lon) / PIX - 0.5))
        out.append((sw_lat, sw_lon, row, col))
    return out


def load_items() -> dict[tuple[int, int], dict]:
    items = json.loads((COARSE / "items.json").read_text(encoding="utf-8"))
    return {sw_of(it["id"]): it for it in items}


def read_tile_classes(item: dict) -> np.ndarray:
    """Same read as pipelines/build_pool_index.read_tile_bare, but returns class codes (uint8)."""
    import planetary_computer
    import rasterio
    from rasterio.enums import Resampling

    signed = planetary_computer.sign(item["href"])
    with rasterio.open(f"/vsicurl/{signed}") as ds:
        arr = ds.read(1, out_shape=(N, N), resampling=Resampling.nearest)
    return arr.astype(np.uint8)


def get_tiles(keys: set[tuple[int, int]], items: dict) -> tuple[dict, dict]:
    """Class arrays for every needed tile key (None when no WorldCover tile exists there)."""
    TILES.mkdir(parents=True, exist_ok=True)
    todo = [k for k in keys if k in items]
    arrays: dict[tuple[int, int], np.ndarray] = {}
    errors: dict[str, str] = {}

    def one(k):
        it = items[k]
        p = TILES / f"{it['id']}.npy"
        if p.exists():
            return k, np.load(p), None
        try:
            a = read_tile_classes(it)
            np.save(p, a)
            return k, a, None
        except Exception as e:  # noqa: BLE001 - recorded, not hidden
            return k, None, f"{type(e).__name__}: {str(e)[:200]}"

    with ThreadPoolExecutor(max_workers=12) as ex:
        for k, a, err in ex.map(one, todo):
            if a is not None:
                arrays[k] = a
            else:
                errors[str(k)] = err
    return arrays, errors


def share_row(cells, classes):
    counts = {c: 0 for c in CLASSES}
    other = 0
    absent = 0
    for sw_lat, sw_lon, row, col in cells:
        arr = classes.get((sw_lat, sw_lon))
        if arr is None:
            absent += 1
            continue
        v = int(arr[row, col])
        if v in counts:
            counts[v] += 1
        else:
            other += 1
    n = len(cells)
    return {"n_disk_px": n, "absent_px": absent,
            "c60": counts[60] / n, "c70": counts[70] / n, "c100": counts[100] / n,
            "other": other / n, "absent": absent / n,
            "bare_share": (counts[60] + counts[70] + counts[100]) / n}


def cache_share(cells, cache) -> dict:
    """Bare share from the coarse .npy cache exactly as stored (absent tile counts as not bare)."""
    n = len(cells)
    bare = 0
    cached_px = 0
    for sw_lat, sw_lon, row, col in cells:
        ca = cache.get((sw_lat, sw_lon))
        if ca is None:
            continue
        cached_px += 1
        bare += int(ca[row, col])
    return {"bare_share_cache": bare / n, "cached_px": cached_px}


def load_cache_bool(items) -> dict:
    out = {}
    for k, it in items.items():
        p = COARSE / f"{it['id']}.npy"
        if p.exists():
            out[k] = np.load(p)
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    SCR.mkdir(parents=True, exist_ok=True)

    res = json.loads((DER / "results.json").read_text(encoding="utf-8"))
    meas = json.loads((DER / "measures.json").read_text(encoding="utf-8"))
    windows = meas["windows"]
    by_id = {w["id"]: w for w in windows}
    closing_ids = [c["arctic_id"] for c in res["mars"]["closing_windows"]]
    assert len(closing_ids) == 39 and len(set(closing_ids)) == 39
    others = [w["id"] for w in windows if w["id"] not in set(closing_ids)]
    assert len(others) == 361, len(others)
    sample40 = random.Random(SEED).sample(others, N_SAMPLE_OTHER)

    pool_index = json.loads((POOL / "index.json").read_text(encoding="utf-8"))
    pool_pick = random.Random(SEED).sample(range(len(pool_index)), N_POOL_REF)
    pool_ref = [pool_index[i] for i in sorted(pool_pick)]

    # every window with a measure (all 400) gets classified: the ROCK set needs all of them for the closure
    all_ids = [w["id"] for w in windows]
    items = load_items()

    needed = {}
    for wid in all_ids:
        w = by_id[wid]
        needed[wid] = disk_cells(w["lat"], w["lon"])
    pool_cells = {p["id"]: disk_cells(p["lat"], p["lon"]) for p in pool_ref}

    keys = set()
    for cells in list(needed.values()) + list(pool_cells.values()):
        for sw_lat, sw_lon, _, _ in cells:
            keys.add((sw_lat, sw_lon))
    print(f"windows={len(all_ids)} pool_ref={len(pool_ref)} tile_keys_needed={len(keys)} "
          f"tiles_in_items={sum(1 for k in keys if k in items)}", flush=True)

    classes, errors = get_tiles(keys, items)
    print(f"tiles read/loaded={len(classes)} errors={len(errors)}", flush=True)
    if errors:
        print("first errors:", list(errors.items())[:3], flush=True)

    cache = load_cache_bool(items)
    # check: re-read bare mask == stored cache, on every tile that has both
    mism = 0
    checked = 0
    for k, arr in classes.items():
        ca = cache.get(k)
        if ca is None:
            continue
        checked += 1
        bare_new = np.isin(arr, CLASSES)
        mism += int(np.count_nonzero(bare_new != ca))
    print(f"cache check: tiles compared={checked} mismatching cells={mism}", flush=True)

    rows = {}
    for wid in all_ids:
        w = by_id[wid]
        cells = needed[wid]
        r = share_row(cells, classes)
        r.update(cache_share(cells, cache))
        r["id"] = wid
        r["lat"] = w["lat"]
        r["lon"] = w["lon"]
        r["measures_worldcover_share"] = w["worldcover_share"]
        r["in_closing"] = wid in set(closing_ids)
        r["in_sample40"] = wid in set(sample40)
        rows[wid] = r

    pool_rows = {}
    for p in pool_ref:
        r = share_row(pool_cells[p["id"]], classes)
        r.update(cache_share(pool_cells[p["id"]], cache))
        r["id"] = p["id"]
        r["lat"] = p["lat"]
        r["lon"] = p["lon"]
        pool_rows[p["id"]] = r

    payload = {
        "seed": SEED,
        "closing_ids": closing_ids,
        "sample40_ids": sample40,
        "pool_ref_ids": [p["id"] for p in pool_ref],
        "tile_errors": errors,
        "cache_check": {"tiles_compared": checked, "mismatching_cells": mism},
        "windows": rows,
        "pool_ref": pool_rows,
    }
    (SCR / "classes.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print("wrote", SCR / "classes.json", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
