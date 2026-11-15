"""Pool rules for the Earth search pool (contract: docs/ARCTIC_INTEGRATION.md, piece 1).

Every rule is read from config/earth_pool_rules.json. Nothing here hard-codes a threshold. The only constants are
the WorldCover read method (300 x 300 per 3x3 degree tile, nearest, 4 km disk), copied from the verification scripts
docs/verification/pool_ice and docs/verification/arctic_ice (copied, not imported).

  shares  WorldCover 2021 bare share (bare_classes) and ice share (ice_class) over the FULL 4 km disk of every window:
          2,000 NASADEM pool windows + the Arctic candidates -> data/derived/pool_rules/shares.json.
          Tiles are cached in data/raw/earth/_worldcover_classes/ (resumable).
  apply   data/raw/earth/pool/index.json: Arctic rows (id pool_{n_nasadem + N:05d} for arc_N, probe_id kept);
          bare_share_full, ice_share and excluded on every row (NASADEM rows keep all their original fields).
          Writes data/derived/pool_rules/excluded.json and summary.json. Idempotent. One rolling backup per day
          (index.json.backup).

Usage (from the project root):
  .venv\\Scripts\\python.exe pipelines\\pool_rules.py shares
  .venv\\Scripts\\python.exe pipelines\\pool_rules.py apply
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from analog.io import fetch  # noqa: E402  (haversine_km / haversine_km_np, R = 6371.0088 km, as build_pool_index)
import build_pool_index as bpi  # noqa: E402  (known_analogs(): config/regions.json role known_analog; MIN_VALID)

CONFIG = ROOT / "config" / "earth_pool_rules.json"
POOL = ROOT / "data" / "raw" / "earth" / "pool"
INDEX = POOL / "index.json"
ARCTIC = ROOT / "data" / "raw" / "earth" / "arctic_probe"
ARCTIC_CANDIDATES = ARCTIC / "candidates.json"
CLIP_LOG = ARCTIC / "clip_log.json"
ITEMS = [POOL / "_worldcover_coarse" / "items.json", ARCTIC / "_worldcover_coarse" / "items.json"]
TILE_CACHE = ROOT / "data" / "raw" / "earth" / "_worldcover_classes"
OUT = ROOT / "data" / "derived" / "pool_rules"
SHARES = OUT / "shares.json"
EXCLUDED = OUT / "excluded.json"
SUMMARY = OUT / "summary.json"

DISK_RADIUS_KM = 4.0  # full disk of the bare-share rule (config bare_share_disk: "full 4 km radius disk")
TILE_DEG = 3.0  # WorldCover tiles are 3 x 3 degrees
TILE_PX = 300  # per tile, 0.01 degree pixels (same read as the verification scripts)
MAX_TILE_ERRORS = 2  # second failed tile stops the run; the cache keeps the work already done
WORKERS = 12

_PROBE_RE = re.compile(r"^arc_(\d{5})$")


class TileError(RuntimeError):
    pass


# ---------------------------------------------------------------- rules (config only)

def load_rules(path: Path = CONFIG) -> dict[str, Any]:
    raw = path.read_bytes()
    cfg = json.loads(raw.decode("utf-8"))
    return {
        "version": cfg["version"],
        "config_sha256": hashlib.sha256(raw).hexdigest(),
        "bands": {b["id"]: b for b in cfg["bands"]},
        "bare_classes": tuple(int(c) for c in cfg["bare_classes"]),
        "bare_share_min": float(cfg["bare_share_min"]),
        "ice_class": int(cfg["ice_class"]),
        "ice_share_max": float(cfg["ice_share_max"]),
        "known_analog_exclusion_km": float(cfg["known_analog_exclusion_km"]),
        "worldcover_source_id": cfg["worldcover_source_id"],
    }


def rules_public(rules: dict[str, Any]) -> dict[str, Any]:
    return {
        "config_version": rules["version"],
        "config_sha256": rules["config_sha256"],
        "bare_classes": list(rules["bare_classes"]),
        "bare_share_min": rules["bare_share_min"],
        "ice_class": rules["ice_class"],
        "ice_share_max": rules["ice_share_max"],
        "known_analog_exclusion_km": rules["known_analog_exclusion_km"],
        "disk_radius_km": DISK_RADIUS_KM,
    }


# ---------------------------------------------------------------- geometry and WorldCover reads

def sw_of(tile_id: str) -> tuple[int, int]:
    m = re.search(r"_([NS])(\d{2})([EW])(\d{3})$", tile_id)
    if not m:
        raise ValueError(f"not a WorldCover tile id: {tile_id}")
    return (int(m.group(2)) * (1 if m.group(1) == "N" else -1),
            int(m.group(4)) * (1 if m.group(3) == "E" else -1))


def disk_cells(lat: float, lon: float, radius_km: float = DISK_RADIUS_KM):
    """Pixel centres (0.01 degree grid) inside the disk: arrays (sw_lat, sw_lon, row, col) per pixel."""
    pix = TILE_DEG / TILE_PX
    dlat = radius_km / 111.32 + 0.02
    dlon = radius_km / (111.32 * max(math.cos(math.radians(lat)), 1e-6)) + 0.02
    i0 = math.floor((lat - dlat) / pix) - 1
    i1 = math.floor((lat + dlat) / pix) + 1
    j0 = math.floor((lon - dlon) / pix) - 1
    j1 = math.floor((lon + dlon) / pix) + 1
    ii, jj = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1), indexing="ij")
    clat = (ii + 0.5) * pix
    clon = (jj + 0.5) * pix
    inside = fetch.haversine_km_np(lat, lon, clat, clon) <= radius_km
    clat, clon = clat[inside], clon[inside]
    sw_lat = np.floor(clat / TILE_DEG).astype(np.int64) * int(TILE_DEG)
    sw_lon = np.floor(clon / TILE_DEG).astype(np.int64) * int(TILE_DEG)
    row = np.round((sw_lat + TILE_DEG - clat) / pix - 0.5).astype(np.int64)
    col = np.round((clon - sw_lon) / pix - 0.5).astype(np.int64)
    return sw_lat, sw_lon, row, col


def window_shares(cells, classes: dict, items: dict, rules: dict[str, Any]) -> dict[str, Any]:
    """Shares over ALL disk pixels. A pixel without a WorldCover tile counts as absent (neither bare nor ice)."""
    sw_lat, sw_lon, row, col = cells
    n = int(row.size)
    uniq = np.unique(np.stack([sw_lat, sw_lon], axis=1), axis=0)
    bare = ice = absent = 0
    tiles: list[str] = []
    for la, lo in uniq:
        key = (int(la), int(lo))
        m = (sw_lat == la) & (sw_lon == lo)
        arr = classes.get(key)
        if arr is None:
            absent += int(m.sum())
            continue
        vals = arr[row[m], col[m]]
        bare += int(np.isin(vals, rules["bare_classes"]).sum())
        ice += int((vals == rules["ice_class"]).sum())
        tiles.append(items[key]["id"])
    return {"n_disk_px": n, "absent_px": absent, "bare_share_full": bare / n, "ice_share": ice / n,
            "tiles": sorted(tiles)}


def load_items() -> dict[tuple[int, int], dict]:
    items: dict[tuple[int, int], dict] = {}
    for p in ITEMS:
        for it in json.loads(p.read_text(encoding="utf-8")):
            items.setdefault(sw_of(it["id"]), it)  # a tile listed twice is the same tile
    return items


def read_tile_classes(item: dict) -> np.ndarray:
    """Same read as docs/verification/pool_ice and arctic_ice: nearest, GDAL overview, class codes kept."""
    import planetary_computer
    import rasterio
    from rasterio.enums import Resampling

    signed = planetary_computer.sign(item["href"])
    with rasterio.open(f"/vsicurl/{signed}") as ds:
        arr = ds.read(1, out_shape=(TILE_PX, TILE_PX), resampling=Resampling.nearest)
    return arr.astype(np.uint8)


def load_tile(item: dict) -> np.ndarray:
    p = TILE_CACHE / f"{item['id']}.npy"
    if p.exists():
        return np.load(p)
    last = ""
    for _ in range(2):  # one retry per tile
        try:
            arr = read_tile_classes(item)
            TILE_CACHE.mkdir(parents=True, exist_ok=True)
            part = p.with_name(p.stem + ".part.npy")
            np.save(part, arr)
            os.replace(part, p)
            return arr
        except Exception as e:  # noqa: BLE001 - recorded and reported, never hidden
            last = f"{item['id']}: {type(e).__name__}: {str(e)[:200]}"
    raise TileError(last)


def get_tiles(keys: set[tuple[int, int]], items: dict) -> dict[tuple[int, int], np.ndarray]:
    """Class arrays for every needed tile. Keys without a WorldCover item are ocean/absent, not errors."""
    todo = sorted(k for k in keys if k in items)
    arrays: dict[tuple[int, int], np.ndarray] = {}
    errors: list[str] = []
    lock = threading.Lock()
    abort = threading.Event()

    def one(k):
        if abort.is_set():
            return k, None
        try:
            return k, load_tile(items[k])
        except TileError as e:
            with lock:
                errors.append(str(e))
                if len(errors) >= MAX_TILE_ERRORS:
                    abort.set()
            return k, None

    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for k, arr in ex.map(one, todo):
            if arr is not None:
                arrays[k] = arr
            done += 1
            if done % 250 == 0:
                print(f"  tiles {done}/{len(todo)}", flush=True)
    if errors:
        for e in errors:
            print("ERROR", e, flush=True)
        raise SystemExit(2)
    return arrays


# ---------------------------------------------------------------- windows

def nasadem_rows(index_rows: list[dict]) -> list[dict]:
    """The NASADEM rows are the ones without probe_id; they must be exactly pool_00001..pool_NNNNN."""
    rows = [r for r in index_rows if not r.get("probe_id")]
    expect = {f"pool_{i:05d}" for i in range(1, len(rows) + 1)}
    if {r["id"] for r in rows} != expect:
        raise ValueError("NASADEM rows are not pool_00001..pool_NNNNN without gaps")
    return rows


def arctic_pool_id(probe_id: str, offset: int) -> str:
    m = _PROBE_RE.match(probe_id)
    if not m:
        raise ValueError(f"bad probe id: {probe_id}")
    return f"pool_{offset + int(m.group(1)):05d}"


def pool_windows(index_rows: list[dict], cand: list[dict], rules: dict[str, Any]) -> list[dict]:
    nas = nasadem_rows(index_rows)
    band = rules["bands"]["arctic"]
    out = [{"id": r["id"], "probe_id": None, "lat": float(r["lat"]), "lon": float(r["lon"])} for r in nas]
    for c in cand:
        if not band["lat_min"] <= c["lat"] <= band["lat_max"]:
            raise ValueError(f"{c['id']} outside the Arctic band: {c['lat']}")
        out.append({"id": arctic_pool_id(c["id"], len(nas)), "probe_id": c["id"],
                    "lat": float(c["lat"]), "lon": float(c["lon"])})
    return out


def near_known(lat: float, lon: float, analogs: list[dict], km: float) -> bool:
    """Same test as build_pool_index.cmd_index: nearest known_analog strictly closer than km."""
    if not analogs:  # an empty list would mark every window as "far" in silence
        raise ValueError("no known_analog in config/regions.json; cannot test the 25 km exclusion")
    dmin = min(fetch.haversine_km(lat, lon, a["lat"], a["lon"]) for a in analogs)
    return bool(dmin < km)


def exclusion(has_clip: bool, ice: float, bare: float, rules: dict[str, Any]) -> dict[str, Any] | None:
    if not has_clip:
        return {"rule": "no_clip", "value": None, "threshold": None}
    if ice >= rules["ice_share_max"]:
        return {"rule": "ice_share", "value": ice, "threshold": rules["ice_share_max"]}
    if bare < rules["bare_share_min"]:
        return {"rule": "bare_share_full", "value": bare, "threshold": rules["bare_share_min"]}
    return None


def _same_point(row: dict, share: dict, wid: str) -> None:
    if abs(row["lat"] - share["lat"]) > 1e-9 or abs(row["lon"] - share["lon"]) > 1e-9:
        raise ValueError(f"shares.json is out of date for {wid}: rerun `shares`")


def apply_rows(index_rows: list[dict], share_windows: dict[str, dict], cand: list[dict],
               clip_log: dict[str, dict], analogs: list[dict], rules: dict[str, Any],
               arctic_dir: Path, root: Path) -> tuple[list[dict], list[dict]]:
    """Pure: returns (new index rows, excluded entries). NASADEM rows keep their fields; Arctic rows are rebuilt."""
    nas = nasadem_rows(index_rows)
    offset = len(nas)
    band = rules["bands"]["arctic"]
    rows: list[dict] = []
    excluded: list[dict] = []
    for r in nas:
        s = share_windows[r["id"]]
        _same_point(r, s, r["id"])
        new = dict(r)
        new["bare_share_full"] = s["bare_share_full"]
        new["ice_share"] = s["ice_share"]
        new["excluded"] = exclusion(True, s["ice_share"], s["bare_share_full"], rules)
        rows.append(new)
    for c in sorted(cand, key=lambda x: x["id"]):
        pid = arctic_pool_id(c["id"], offset)
        s = share_windows[pid]
        _same_point(c, s, pid)
        tif = arctic_dir / f"{c['id']}.tif"
        clip = clip_log.get(c["id"])
        vf = clip.get("valid_fraction") if clip else None
        has_clip = tif.exists() and bool(clip and clip.get("ok")) and vf is not None
        row = {
            "id": pid,
            "probe_id": c["id"],
            "lat": c["lat"],
            "lon": c["lon"],
            "worldcover_share": c["worldcover_share"],
            "bare_share_full": s["bare_share_full"],
            "ice_share": s["ice_share"],
            "near_known_analog": near_known(c["lat"], c["lon"], analogs, rules["known_analog_exclusion_km"]),
            "path": tif.relative_to(root).as_posix(),
            "valid_fraction": vf,
            "source_id": band["source_id"],
            "sensor": band["sensor"],
            "excluded": exclusion(has_clip, s["ice_share"], s["bare_share_full"], rules),
        }
        rows.append(row)
    for row in rows:
        if row["excluded"]:
            excluded.append({"id": row["id"], "probe_id": row.get("probe_id"), "lat": row["lat"],
                             "lon": row["lon"], "rule": row["excluded"]["rule"],
                             "value": row["excluded"]["value"], "threshold": row["excluded"]["threshold"]})
    return rows, excluded


def summarize(rows: list[dict], rules: dict[str, Any]) -> dict[str, Any]:
    ice_max, bare_min = rules["ice_share_max"], rules["bare_share_min"]
    out: dict[str, Any] = {}
    for band in ("nasadem", "arctic"):
        rs = [r for r in rows if (r.get("probe_id") is not None) == (band == "arctic")]
        rule_counts = Counter(r["excluded"]["rule"] if r["excluded"] else "accepted" for r in rs)
        out[band] = {
            "total": len(rs),
            "excluded_ice_share": rule_counts["ice_share"],
            "excluded_bare_share_full": rule_counts["bare_share_full"],
            "excluded_no_clip": rule_counts["no_clip"],
            "accepted": rule_counts["accepted"],
            "flag_ice_any": sum(1 for r in rs if r["ice_share"] >= ice_max),
            "flag_bare_any": sum(1 for r in rs if r["bare_share_full"] < bare_min),
            "flag_ice_and_bare": sum(1 for r in rs if r["ice_share"] >= ice_max and r["bare_share_full"] < bare_min),
            "near_known_analog": sum(1 for r in rs if r.get("near_known_analog")),
        }
    arc = [r for r in rows if r.get("probe_id")]
    out["arctic_valid_fraction_below_min_valid_info"] = sum(
        1 for r in arc if r["valid_fraction"] is not None and r["valid_fraction"] < bpi.MIN_VALID)
    out["all"] = {k: out["nasadem"][k] + out["arctic"][k] for k in out["nasadem"]}
    return out


# ---------------------------------------------------------------- files

def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def backup_once_today(index_path: Path, today: dt.date | None = None) -> str:
    """One rolling backup. Skipped only when index.json.backup was already written today."""
    bak = index_path.with_name(index_path.name + ".backup")
    today = today or dt.date.today()
    if bak.exists() and dt.date.fromtimestamp(bak.stat().st_mtime) == today:
        return "kept (backup of today exists)"
    shutil.copyfile(index_path, bak)
    return "written"


def window_shares_doc(windows: list[dict], classes: dict, items: dict, rules: dict[str, Any]) -> tuple[dict, int]:
    out: dict[str, Any] = {}
    absent_total = 0
    for w in windows:
        r = window_shares(disk_cells(w["lat"], w["lon"]), classes, items, rules)
        absent_total += r["absent_px"]
        out[w["id"]] = {"probe_id": w["probe_id"], "lat": w["lat"], "lon": w["lon"],
                        "bare_share_full": r["bare_share_full"], "ice_share": r["ice_share"],
                        "n_disk_px": r["n_disk_px"], "absent_px": r["absent_px"], "tiles": r["tiles"]}
    return out, absent_total


# ---------------------------------------------------------------- subcommands

def cmd_shares() -> int:
    rules = load_rules()
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    cand = json.loads(ARCTIC_CANDIDATES.read_text(encoding="utf-8"))["candidates"]
    windows = pool_windows(index, cand, rules)
    items = load_items()
    keys: set[tuple[int, int]] = set()
    for w in windows:
        sw_lat, sw_lon, _, _ = disk_cells(w["lat"], w["lon"])
        keys.update(zip(sw_lat.tolist(), sw_lon.tolist()))
    print(f"windows={len(windows)} tile_keys={len(keys)} tile_keys_with_item={sum(k in items for k in keys)}",
          flush=True)
    classes = get_tiles(keys, items)
    print(f"tiles loaded={len(classes)}", flush=True)
    shares, absent_total = window_shares_doc(windows, classes, items, rules)
    payload = {
        "provenance": {
            "schema": "analog.pool_rules.shares/1",
            "created": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_id": rules["worldcover_source_id"],
            "worldcover": "ESA WorldCover 2021 v200 map, 300 x 300 per 3x3 degree tile, nearest, GDAL overviews",
            "denominator": "all pixel centres inside the disk; pixels without a WorldCover tile are absent "
                           "(neither bare nor ice)",
            "inputs": {"index": INDEX.relative_to(ROOT).as_posix(),
                       "arctic_candidates": ARCTIC_CANDIDATES.relative_to(ROOT).as_posix()},
            "tile_cache": TILE_CACHE.relative_to(ROOT).as_posix(),
            "rules": rules_public(rules),
            "counts": {"windows": len(windows), "tile_keys": len(keys), "absent_px_total": absent_total},
            "code": "pipelines/pool_rules.py shares",
        },
        "windows": shares,
    }
    write_json(SHARES, payload)
    print(f"wrote {SHARES.relative_to(ROOT).as_posix()} windows={len(shares)} absent_px_total={absent_total}",
          flush=True)
    return 0


def check_shares_rules(doc: dict, rules: dict[str, Any]) -> None:
    """Shares depend on the WorldCover method and the classes only (not on the thresholds)."""
    prov = doc["provenance"]["rules"]
    for key in ("bare_classes", "ice_class", "disk_radius_km"):
        if prov[key] != rules_public(rules)[key]:
            raise SystemExit(f"shares.json was computed with {key}={prov[key]}; rerun `shares`")


def cmd_apply() -> int:
    rules = load_rules()
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    shares_doc = json.loads(SHARES.read_text(encoding="utf-8"))
    check_shares_rules(shares_doc, rules)
    cand = json.loads(ARCTIC_CANDIDATES.read_text(encoding="utf-8"))["candidates"]
    clip_log = {e["id"]: e for e in json.loads(CLIP_LOG.read_text(encoding="utf-8"))}
    analogs = bpi.known_analogs()
    rows, excluded = apply_rows(index, shares_doc["windows"], cand, clip_log, analogs, rules, ARCTIC, ROOT)
    summary = summarize(rows, rules)
    backup = backup_once_today(INDEX)
    write_json(INDEX, rows)
    write_json(EXCLUDED, excluded)
    write_json(SUMMARY, {"rules": rules_public(rules), "rows": len(rows), "summary": summary,
                         "index_backup": backup, "created": dt.datetime.now(dt.timezone.utc).strftime(
                             "%Y-%m-%dT%H:%M:%SZ")})
    print(f"index rows={len(rows)} backup={backup}", flush=True)
    for band in ("nasadem", "arctic", "all"):
        s = summary[band]
        print(f"{band}: total={s['total']} ice={s['excluded_ice_share']} bare={s['excluded_bare_share_full']} "
              f"no_clip={s['excluded_no_clip']} accepted={s['accepted']}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pool rules: WorldCover shares and index flags (see module docstring).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("shares", help="shares over the full 4 km disk -> data/derived/pool_rules/shares.json")
    sub.add_parser("apply", help="Arctic rows + bare/ice/excluded flags in pool/index.json")
    args = ap.parse_args(argv)
    return cmd_shares() if args.cmd == "shares" else cmd_apply()


if __name__ == "__main__":
    sys.exit(main())
