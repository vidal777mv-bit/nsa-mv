"""Arctic probe (EXPERIMENT, STANDARDS 10.7 sample first): does Arctic bare ground (60N-84N) close any Earth gap?

Question: the Earth search pool covers 56S-60N (NASADEM). Do 60N-84N windows (Copernicus GLO-30) give an Earth twin
inside the tie threshold to Mars atlas cells and Artemis III Moon targets that currently have an "Earth gap"?

This script ONLY writes under data/derived/arctic_probe/ and data/raw/earth/arctic_probe/. It reads (never writes) the
frozen config, the neighbours tables and the pool measures. It reuses the pool's own functions: the WorldCover coarse
reader and the candidate rule (pipelines/build_pool_index.py), the DEM -> 100 m grid -> features chain
(pipelines/_common.measure_raw), the exact KD-tree neighbours (src/analog/core/neighbors.py) and the tie thresholds
persisted by the validation stage (data/derived/validation/noise_v1.3.json).

Subcommands (in order; every step is resumable):
  items                  STAC list of WorldCover 2021 tiles for 60N-84N -> raw/_worldcover_coarse/items.json
  coarse                 one 300 x 300 read per 3x3 deg tile (bare = classes 60/70/100), cached as .npy
  candidates [--n N]     pool rule at the pool step (0.9 deg), share >= 0.8 in the 4 km disk; seeded subset of N
  clip [--first K]       Copernicus GLO-30 (public S3 COG) windowed read, half width 4.5 km, snapped to the source grid
  measure [--first K]    frozen v1.3 measure (pipelines/_common.measure_raw) -> data/derived/arctic_probe/measures.json
  results                nearest Arctic D for every Mars gap cell and every Artemis III Moon target
  control                the sensor control: 40 pool windows (45-60N) re-measured with Copernicus vs their NASADEM record
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

os.environ.setdefault("GDAL_HTTP_TIMEOUT", "60")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")

from analog.core import neighbors as nb  # noqa: E402
from analog.core.stats import wilson  # noqa: E402
from analog.io import fetch  # noqa: E402

RAW = ROOT / "data" / "raw" / "earth" / "arctic_probe"
COARSE = RAW / "_worldcover_coarse"
OUT = ROOT / "data" / "derived" / "arctic_probe"
SEED = 20261114
LAT_MIN, LAT_MAX = 60.0, 84.0  # WorldCover ends at 84N
STEP_DEG = 0.9  # the pool's chosen step (data/raw/earth/pool/_worldcover_coarse/spacing.json)
CLIP_HALF_KM = 4.5
COP_BASE = "https://copernicus-dem-30m.s3.amazonaws.com"
FEATS = ["slope_p95_deg", "hi", "hurst"]
ARTEMIS_TAG = "Artemis III"


# ----------------------------------------------------------------------------------------------- pure logic
def gap_closure(Xq: np.ndarray, thr: np.ndarray, Xa: np.ndarray, sigma: np.ndarray) -> dict[str, np.ndarray]:
    """Which queries have an Arctic window inside their tie threshold.

    Formula: D(q, a) = ||x_q/sigma - x_a/sigma|| / sqrt(K) (STANDARDS 10.14, equal weights); closed_q = min_a D <= thr_q.
    Xq: (m, K) raw query features; thr: (m,) tie thresholds; Xa: (n, K) raw Arctic features (no NaN); sigma: (K,).
    Returns d_arctic (m,), arctic_row (m,) (index into Xa, ties by index) and closed (m,) bool.
    Uses the exact KD-tree of core/neighbors; the brute-force formula is the reference in the tests.
    """
    Xq = np.asarray(Xq, dtype=float)
    Xa = np.asarray(Xa, dtype=float)
    tree = nb.build_tree(nb.standardise(Xa, sigma))
    Zq = nb.standardise(Xq, sigma)
    idx, D = nb.knn(tree, Zq, 1)
    d = D[:, 0]
    return {"d_arctic": d, "arctic_row": idx[:, 0], "closed": d <= np.asarray(thr, dtype=float)}


# ----------------------------------------------------------------------------------------------- helpers
def load_json(p: Path) -> Any:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".part")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    os.replace(tmp, p)


def rel(p: Path) -> str:
    return Path(p).resolve().relative_to(ROOT).as_posix()


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def cop_url(la: int, lo: int) -> str:
    """Copernicus GLO-30 COG url for the 1x1 degree tile whose south-west corner is (la, lo)."""
    ns = "N" if la >= 0 else "S"
    ew = "E" if lo >= 0 else "W"
    name = f"Copernicus_DSM_COG_10_{ns}{abs(la):02d}_00_{ew}{abs(lo):03d}_00_DEM"
    return f"{COP_BASE}/{name}/{name}.tif"


def clip_cop(lat: float, lon: float, half_km: float, out: Path) -> dict[str, Any]:
    """Windowed read of Copernicus GLO-30 around (lat, lon) -> float32 GeoTIFF (EPSG:4326, NaN nodata).

    Window: +-half_km north-south, +-half_km / cos(lat) east-west (fetch.km_to_deg, like the pool clip). The bounds are
    snapped outward to the source pixel grid (tile origins are integer degrees, so snapping to multiples of the pixel
    size reproduces source pixels exactly: no resampling). Only the window is read from each COG (rasterio.merge reads
    windows); tiles that do not exist (404, ocean) are skipped and their area stays NaN. The source pixel is
    1" x 1" up to 50N, then 1" x 1.5" (50-60), 1" x 2" (60-70), 1" x 3" (70-80), 1" x 5" (80-85): the file keeps the
    native, non-square pixel and grid.py reprojects it with its true transform.
    """
    import rasterio
    from rasterio.merge import merge

    dlat, dlon = fetch.km_to_deg(lat, half_km)
    west, east, south, north = lon - dlon, lon + dlon, lat - dlat, lat + dlat
    if west < -180 or east >= 180:
        raise fetch.FetchError("window crosses the antimeridian")
    tiles = [(la, lo) for la in range(math.floor(south), math.floor(north) + 1)
             for lo in range(math.floor(west), math.floor(east) + 1)]
    srcs, names, missing, keyed = [], [], [], []
    try:
        for la, lo in tiles:
            try:
                ds = rasterio.open("/vsicurl/" + cop_url(la, lo))
            except rasterio.errors.RasterioIOError:
                missing.append(f"{la},{lo}")
                continue
            srcs.append(ds)
            keyed.append((la, lo, ds))
            names.append(f"{la},{lo}")
        if not srcs:
            raise fetch.FetchError(f"no Copernicus tile over the window (missing {missing})")
        # resolution of the tile that holds the centre (else the first one): merge resamples (nearest) any other band
        centre = [ds for la, lo, ds in keyed if la == math.floor(lat) and lo == math.floor(lon)]
        ref = centre[0] if centre else srcs[0]
        rx, ry = abs(ref.res[0]), abs(ref.res[1])
        b = (math.floor(west / rx + 1e-9) * rx, math.floor(south / ry + 1e-9) * ry,
             math.ceil(east / rx - 1e-9) * rx, math.ceil(north / ry - 1e-9) * ry)
        arr, tr = merge(srcs, bounds=b, res=(rx, ry), nodata=np.nan, dtype="float32")
    finally:
        for s in srcs:
            s.close()
    z = arr[0]
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.name + ".part")
    with rasterio.open(part, "w", driver="GTiff", height=z.shape[0], width=z.shape[1], count=1, dtype="float32",
                       crs="EPSG:4326", transform=tr, nodata=np.nan, compress="deflate") as dst:
        dst.write(z, 1)
    os.replace(part, out)
    return {"tiles_read": names, "tiles_missing": missing, "res_deg": [rx, ry], "shape": [int(z.shape[0]), int(z.shape[1])],
            "valid_fraction": float(np.isfinite(z).mean()), "bytes": out.stat().st_size, "sha256": fetch.sha256_file(out)}


# ----------------------------------------------------------------------------------------------- stage: tiles
def cmd_items(_: argparse.Namespace) -> int:
    """WorldCover 2021 v200 tiles with south edge in [60, 81] (STAC, same service the pool used)."""
    import pystac_client

    COARSE.mkdir(parents=True, exist_ok=True)
    cat = pystac_client.Client.open(fetch.PC_STAC_URL)
    found = cat.search(collections=["esa-worldcover"], bbox=[-180.0, 60.0, 180.0, 84.0], max_items=10000)
    items = []
    for it in found.items():
        if "2021" not in it.id or "v200" not in it.id:
            continue
        sw = nominal_sw(it.id)
        if sw[0] < 60:
            continue
        items.append({"id": it.id, "bbox": [float(v) for v in it.bbox], "href": it.assets["map"].href})
    items.sort(key=lambda d: d["id"])
    write_json(COARSE / "items.json", items)
    log(f"tiles={len(items)}")
    return 0


def nominal_sw(tile_id: str) -> tuple[int, int]:
    """(south, west) corner of a WorldCover tile from its name (e.g. ..._N60W090)."""
    import re

    m = re.search(r"_([NS])(\d{2})([EW])(\d{3})$", tile_id)
    if not m:
        raise ValueError(tile_id)
    return int(m.group(2)) * (1 if m.group(1) == "N" else -1), int(m.group(4)) * (1 if m.group(3) == "E" else -1)


def cmd_coarse(_: argparse.Namespace) -> int:
    """One coarse read per tile (pool function read_tile_bare), 16 threads, cached .npy."""
    import build_pool_index as bpi

    items = load_json(COARSE / "items.json")
    todo = [it for it in items if not (COARSE / f"{it['id']}.npy").exists()]
    log(f"tiles={len(items)} to_read={len(todo)}")
    t0 = time.time()
    ok = fail = 0

    def one(it: dict[str, Any]) -> tuple[str, bool, str]:
        for attempt in (1, 2):
            try:
                bare = bpi.run_with_timeout(bpi.read_tile_bare, it["href"], 60)
            except Exception as exc:  # logged, never patched
                reason = f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:120]}"
                continue
            part = COARSE / f"{it['id']}.part.npy"
            np.save(part, bare)
            os.replace(part, COARSE / f"{it['id']}.npy")
            return it["id"], True, ""
        return it["id"], False, reason

    with ThreadPoolExecutor(max_workers=16) as ex:
        for tid, good, why in ex.map(one, todo):
            ok += good
            fail += not good
            if not good:
                log(f"FAIL {tid}: {why}")
    log(f"coarse done ok={ok} fail={fail} wall_s={time.time() - t0:.0f}")
    return 1 if fail else 0


# ----------------------------------------------------------------------------------------------- stage: candidates
def cmd_candidates(args: argparse.Namespace) -> int:
    """The pool rule (build_pool_index.grid_candidates) on the Arctic tiles; seeded uniform subset of n."""
    import build_pool_index as bpi

    bpi.LAT_MIN, bpi.LAT_MAX = LAT_MIN, LAT_MAX  # the only parameter that changes: the latitude band
    tiles = []
    for it in load_json(COARSE / "items.json"):
        p = COARSE / f"{it['id']}.npy"
        if p.exists():
            tiles.append((bpi.nominal_bbox(it["id"]), np.load(p), it["id"]))
    kept, tested = bpi.grid_candidates(tiles, STEP_DEG)
    total = len(kept)
    rng = random.Random(SEED)
    # Always the seeded draw (also when n >= total): random.sample uses the same per-draw sequence for any k on this
    # population size, so a larger n keeps the earlier draw as its prefix (ids arc_00001.. and their clips stay valid).
    chosen = rng.sample(kept, min(args.n, total))
    # order = the random draw order, so the first 50 are themselves a uniform random sample of the 400
    cand = [{"id": f"arc_{i + 1:05d}", "lat": round(a, 6), "lon": round(b, 6), "worldcover_share": round(c, 6), "tile": t}
            for i, (a, b, c, t) in enumerate(chosen)]
    payload = {"step_deg": STEP_DEG, "seed": SEED, "band": [LAT_MIN, LAT_MAX], "tiles_used": len(tiles),
               "centres_tested": tested, "kept_before_subsample": total, "n_drawn": len(cand), "candidates": cand}
    write_json(RAW / "candidates.json", payload)
    log(f"tiles={len(tiles)} tested={tested} kept={total} drawn={len(cand)}")
    return 0


# ----------------------------------------------------------------------------------------------- stage: clip
def clip_job(rec: dict[str, Any]) -> dict[str, Any]:
    out = RAW / f"{rec['id']}.tif"
    t0 = time.time()
    if out.exists():
        return {"id": rec["id"], "ok": True, "cached": True}
    try:
        meta = clip_cop(rec["lat"], rec["lon"], CLIP_HALF_KM, out)
    except Exception as exc:
        return {"id": rec["id"], "ok": False, "reason": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return {"id": rec["id"], "ok": True, "seconds": round(time.time() - t0, 2), **meta}


def cmd_clip(args: argparse.Namespace) -> int:
    cand = load_json(RAW / "candidates.json")["candidates"][: args.first or None]
    t0 = time.time()
    log(f"clipping {len(cand)} windows (8 threads)")
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(clip_job, cand))
    ok = [r for r in res if r["ok"]]
    bad = [r for r in res if not r["ok"]]
    clip_log = RAW / "clip_log.json"
    prev = {r["id"]: r for r in (load_json(clip_log) if clip_log.exists() else [])}
    for r in res:
        if not r.get("cached"):
            prev[r["id"]] = r
    write_json(clip_log, sorted(prev.values(), key=lambda r: r["id"]))
    log(f"clip ok={len(ok)} fail={len(bad)} wall_s={time.time() - t0:.0f}")
    for r in bad[:10]:
        log(f"  FAIL {r['id']}: {r['reason']}")
    return 0


# ----------------------------------------------------------------------------------------------- stage: measure
def cmd_measure(args: argparse.Namespace) -> int:
    """Frozen v1.3 measure of each clip through _common.measure_raw (same chain as the pool)."""
    from _common import make_paths, measure_raw, provenance_block, read_config

    paths = make_paths(None, False)
    cfg = read_config(paths)
    cand = load_json(RAW / "candidates.json")["candidates"][: args.first or None]
    clip_log = {r["id"]: r for r in load_json(RAW / "clip_log.json")} if (RAW / "clip_log.json").exists() else {}
    rows = []
    t0 = time.time()
    for rec in cand:
        tif = RAW / f"{rec['id']}.tif"
        row: dict[str, Any] = {"id": rec["id"], "lat": rec["lat"], "lon": rec["lon"],
                               "worldcover_share": rec["worldcover_share"], "tile": rec["tile"],
                               "source_id": "cop_dem_glo30", "path": rel(tif) if tif.exists() else None}
        if not tif.exists():
            row.update(status="missing", reason="no clip on disk", features=None)
            rows.append(row)
            continue
        c = clip_log.get(rec["id"], {})
        row.update(valid_fraction=c.get("valid_fraction"), res_deg=c.get("res_deg"), sha256=c.get("sha256"))
        r = measure_raw(tif, rec["lat"], rec["lon"], "earth", cfg)
        row.update(status=r["status"], reason=r["reason"], native_res_m=r["native_res_m"], coverage=r["coverage"],
                   n_valid=r["n_valid"], features=r["features"])
        rows.append(row)
    n_ok = sum(r["status"] == "ok" for r in rows)
    payload = {"provenance": provenance_block(paths, "arctic_probe_measure", [("cop_dem_glo30", RAW / "candidates.json")]),
               "note": "EXPERIMENT. Copernicus GLO-30 windows measured with the frozen v1.3 config (no sigma change). "
                       "Input hash is of candidates.json; each window carries the sha256 of its clip.",
               "n_windows": len(rows), "n_ok": n_ok, "windows": rows}
    write_json(OUT / "measures.json", payload)
    st: dict[str, int] = {}
    for r in rows:
        st[r["status"]] = st.get(r["status"], 0) + 1
    log(f"measured {len(rows)} windows status={st} wall_s={time.time() - t0:.0f}")
    return 0


# ----------------------------------------------------------------------------------------------- stage: results
def pool_feature_medians() -> dict[str, float]:
    import pyarrow.parquet as pq

    t = pq.read_table(ROOT / "data" / "derived" / "neighbors" / "earth_windows.parquet").to_pylist()
    return {k: float(np.nanmedian([r[k] for r in t if r[k] is not None])) for k in FEATS}


def place_of(lat: float, lon: float) -> dict[str, Any] | None:
    """Offline Natural Earth admin-1 name of a point (the project's own index), or None."""
    from _common import RunLog, analog_place, load_places, make_paths

    paths = make_paths(None, False)
    global _PLACES
    if "_PLACES" not in globals():
        class _Quiet:
            def event(self, *a: Any, **k: Any) -> None:
                return None
        _PLACES = load_places(paths, _Quiet())  # type: ignore[arg-type]
    rec = analog_place(_PLACES, lat, lon)
    return None if rec is None else {k: rec.get(k) for k in ("name", "admin1", "country", "match", "distance_km")}


def cmd_results(_: argparse.Namespace) -> int:
    import pyarrow.parquet as pq
    from _common import make_paths, read_config

    paths = make_paths(None, False)
    cfg = read_config(paths)
    sigma = np.array([float(cfg["features"][k]["sigma"]) for k in FEATS])
    meas = load_json(OUT / "measures.json")
    arc = [w for w in meas["windows"] if w["status"] == "ok" and all(w["features"].get(k) is not None for k in FEATS)]
    Xa = np.array([[w["features"][k] for k in FEATS] for w in arc], dtype=float)
    noise = load_json(ROOT / "data" / "derived" / "validation" / "noise_v1.3.json")
    thr_cls = {c: float(i["p95"]) for c, i in noise["classes"].items()}
    med_cls = {c: float(i["median"]) for c, i in noise["classes"].items()}
    log(f"arctic windows usable={len(arc)} of {meas['n_windows']}")

    # --- feature medians
    a_med = {k: float(np.median(Xa[:, i])) for i, k in enumerate(FEATS)}
    p_med = pool_feature_medians()

    # --- queries
    cells = pq.read_table(ROOT / "data" / "derived" / "neighbors" / "mars_cells.parquet").to_pylist()
    tgts = pq.read_table(ROOT / "data" / "derived" / "neighbors" / "targets.parquet").to_pylist()
    gap_cells = [c for c in cells if c["gap"] is True]
    moon = [t for t in tgts if t["body"] == "moon" and ARTEMIS_TAG in (t.get("mission") or "")]
    assert len(moon) == 7, len(moon)

    def run(queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        Xq = np.array([[q[k] for k in FEATS] for q in queries], dtype=float)
        thr = np.array([q["threshold"] for q in queries], dtype=float)
        g = gap_closure(Xq, thr, Xa, sigma)
        out = []
        for i, q in enumerate(queries):
            w = arc[int(g["arctic_row"][i])]
            cls = q["relief_class"]
            out.append({"id": q["id"], "lat": q["lat"], "lon": q["lon"], "relief_class": cls,
                        "threshold": q["threshold"], "d_pool_nearest": q["d_nearest"],
                        "d_arctic_nearest": float(g["d_arctic"][i]), "arctic_id": w["id"],
                        "arctic_lat": w["lat"], "arctic_lon": w["lon"],
                        "closed": bool(g["closed"][i]),
                        "closed_within_class_median_noise": bool(g["d_arctic"][i] <= med_cls[cls]),
                        "arctic_beats_pool": bool(g["d_arctic"][i] < q["d_nearest"])})
        return out

    mars = run(gap_cells)
    moon_res = run(moon)
    # all 16 targets and all Moon targets for context (non-gap targets: does Arctic add anything?)
    for r in moon_res:
        r["gap_in_pool"] = bool(next(t for t in tgts if t["id"] == r["id"])["gap"])
        if r["closed"]:
            r["arctic_place"] = place_of(r["arctic_lat"], r["arctic_lon"])
    for r in mars:
        if r["closed"]:
            r["arctic_place"] = place_of(r["arctic_lat"], r["arctic_lon"])

    n = len(mars)
    k = sum(r["closed"] for r in mars)
    k_med = sum(r["closed_within_class_median_noise"] for r in mars)
    lo, hi = wilson(k, n)
    lo_m, hi_m = wilson(k_med, n)
    by_class = {}
    for cls in ("rugged", "flat"):
        sub = [r for r in mars if r["relief_class"] == cls]
        kk = sum(r["closed"] for r in sub)
        w = wilson(kk, len(sub)) if sub else None
        by_class[cls] = {"n": len(sub), "closed": kk, "wilson95": list(w) if w else None}
    # brute-force agreement of the tree result (reference formula)
    Zq = np.array([[q[k_] for k_ in FEATS] for q in gap_cells], dtype=float) / sigma
    Za = Xa / sigma
    brute = np.sqrt(((Zq[:, None, :] - Za[None, :, :]) ** 2).sum(-1) / len(FEATS)).min(axis=1)
    max_dd = float(np.max(np.abs(brute - np.array([r["d_arctic_nearest"] for r in mars]))))

    # closure vs number of Arctic windows used (prefixes of the seeded random draw): is the count still rising?
    Xq_all = np.array([[q[k_] for k_ in FEATS] for q in gap_cells], dtype=float)
    thr_all = np.array([q["threshold"] for q in gap_cells], dtype=float)
    curve = []
    for m_ in (50, 100, 200, len(arc)):
        if m_ <= len(arc):
            cl = gap_closure(Xq_all, thr_all, Xa[:m_], sigma)["closed"]
            curve.append({"n_arctic_windows": m_, "mars_gap_cells_closed": int(cl.sum())})

    # distribution of the closing windows
    from collections import Counter

    closers = Counter(r["arctic_id"] for r in mars if r["closed"])
    closing_places = []
    for aid, cnt in closers.most_common():
        w = next(x for x in arc if x["id"] == aid)
        closing_places.append({"arctic_id": aid, "lat": w["lat"], "lon": w["lon"], "cells_closed": cnt,
                               "features": w["features"], "place": place_of(w["lat"], w["lon"])})

    results = {
        "schema": "analog.arctic_probe.results/1",
        "created": fetch.utc_now(),
        "config_version": cfg["version"],
        "experiment": "EXPERIMENT. Adds an Arctic (60N-84N, Copernicus GLO-30) window sample to the 56S-60N NASADEM pool. "
                      "Nothing in the pool, sigma, thresholds, neighbours or ledger was changed.",
        "n_arctic_windows_measured": meas["n_windows"], "n_arctic_windows_usable": len(arc),
        "tie_thresholds_p95": thr_cls, "sensor_noise_median": med_cls,
        "candidates_kept_by_pool_rule": load_json(RAW / "candidates.json")["kept_before_subsample"],
        "sensor_control_file": "data/derived/arctic_probe/sensor_control.json",
        "sensor_noise_note": "NASADEM vs Copernicus D over 15 dev regions (noise_v1.3.json): the tie threshold IS the p95. "
                             "Any closure means D <= p95 of the sensor noise: a tie within sensor noise, not a clean match.",
        "feature_medians": {"arctic": a_med, "pool_2000_nasadem": p_med},
        "mars": {"n_gap_cells": n, "closed": k, "share": k / n, "wilson95": [lo, hi],
                 "closed_within_class_median_noise": k_med, "share_median_noise": k_med / n, "wilson95_median_noise": [lo_m, hi_m],
                 "by_relief_class": by_class, "closure_vs_n_windows": curve, "arctic_beats_pool_count": sum(r["arctic_beats_pool"] for r in mars),
                 "tree_vs_brute_max_abs_diff": max_dd, "closing_windows": closing_places},
        "moon_artemis_iii": moon_res,
        "mars_cells": mars,
    }
    write_json(OUT / "results.json", results)
    log(f"MARS gap cells closed {k}/{n} ({k / n:.3f}, Wilson [{lo:.3f}, {hi:.3f}]); within class-median noise {k_med}/{n}")
    for r in moon_res:
        log(f"MOON {r['id']}: gap_in_pool={r['gap_in_pool']} d_pool={r['d_pool_nearest']:.3f} d_arctic={r['d_arctic_nearest']:.3f} "
            f"thr={r['threshold']:.3f} closed={r['closed']} at ({r['arctic_lat']},{r['arctic_lon']})")
    return 0


# ----------------------------------------------------------------------------------------------- stage: control
def cmd_control(args: argparse.Namespace) -> int:
    """Sensor control on the pipeline itself: up to 40 pool windows between 45N and 60N re-read from Copernicus S3 with the
    same clip code and measured with the frozen config; D(NASADEM record, Copernicus S3 record) per window.
    Checks that the Copernicus reader reproduces the validated sensor-noise scale at high latitude (1.5" pixels)."""
    from _common import make_paths, measure_raw, read_config

    paths = make_paths(None, False)
    cfg = read_config(paths)
    sigma = np.array([float(cfg["features"][k]["sigma"]) for k in FEATS])
    idx = load_json(ROOT / "data" / "raw" / "earth" / "pool" / "index.json")
    pool = [e for e in idx if 45.0 <= e["lat"] <= 59.9 and abs(e["lon"]) < 179.0]
    rng = random.Random(SEED)
    sel = rng.sample(pool, min(args.n, len(pool)))
    rows = []
    cdir = RAW / "control"
    for e in sel:
        out = cdir / f"{e['id']}.tif"
        try:
            if not out.exists():
                clip_cop(e["lat"], e["lon"], CLIP_HALF_KM, out)
            r = measure_raw(out, e["lat"], e["lon"], "earth", cfg)
            nas = load_json(ROOT / "data" / "derived" / "measure" / f"pool__{e['id']}.json")
            if r["status"] != "ok" or nas["status"] != "ok":
                rows.append({"id": e["id"], "lat": e["lat"], "D": None, "reason": r["reason"] or nas["reason"]})
                continue
            a = np.array([nas["features"][k] for k in FEATS], dtype=float)
            b = np.array([r["features"][k] for k in FEATS], dtype=float)
            if np.isnan(a).any() or np.isnan(b).any():
                rows.append({"id": e["id"], "lat": e["lat"], "D": None, "reason": "null feature"})
                continue
            D = float(np.sqrt((((a - b) / sigma) ** 2).sum() / len(FEATS)))
            rows.append({"id": e["id"], "lat": e["lat"], "lon": e["lon"], "slope_p95_deg_nasadem": float(a[0]), "D": D,
                         "z_diff_cop_minus_nasadem": {k: float(v) for k, v in zip(FEATS, (b - a) / sigma)}})
        except Exception as exc:
            rows.append({"id": e["id"], "lat": e["lat"], "D": None, "reason": f"{type(exc).__name__}: {str(exc)[:120]}"})
    d = np.array([r["D"] for r in rows if r["D"] is not None])
    noise = load_json(ROOT / "data" / "derived" / "validation" / "noise_v1.3.json")
    thr = {c: float(i["p95"]) for c, i in noise["classes"].items()}
    rug = [r for r in rows if r["D"] is not None and r["slope_p95_deg_nasadem"] >= 3.0]
    dr = np.array([r["D"] for r in rug])
    out = {"n_selected": len(sel), "n_ok": int(d.size), "median_D": float(np.median(d)), "p95_D": float(np.percentile(d, 95)),
           "n_rugged": len(rug), "rugged_median_D": float(np.median(dr)) if dr.size else None,
           "rugged_p95_D": float(np.percentile(dr, 95)) if dr.size else None,
           "signed_z_diff_cop_minus_nasadem": {
               k: {"median": float(np.median([r["z_diff_cop_minus_nasadem"][k] for r in rows if r["D"] is not None])),
                   "p5": float(np.percentile([r["z_diff_cop_minus_nasadem"][k] for r in rows if r["D"] is not None], 5)),
                   "p95": float(np.percentile([r["z_diff_cop_minus_nasadem"][k] for r in rows if r["D"] is not None], 95))}
               for k in FEATS},
           "dev_noise_p95": thr, "share_rugged_above_dev_p95": float(np.mean(dr > thr["rugged"])) if dr.size else None,
           "rows": rows}
    write_json(OUT / "sensor_control.json", out)
    log(f"control n={d.size} median={out['median_D']:.3f} p95={out['p95_D']:.3f} rugged n={len(rug)} "
        f"median={out['rugged_median_D']} p95={out['rugged_p95_D']} (dev p95 rugged {thr['rugged']:.3f})")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("items").set_defaults(func=cmd_items)
    sub.add_parser("coarse").set_defaults(func=cmd_coarse)
    c = sub.add_parser("candidates")
    c.add_argument("--n", type=int, default=400)
    c.set_defaults(func=cmd_candidates)
    for name, fn in (("clip", cmd_clip), ("measure", cmd_measure)):
        s = sub.add_parser(name)
        s.add_argument("--first", type=int, default=0, help="only the first K candidates (0 = all)")
        s.set_defaults(func=fn)
    sub.add_parser("results").set_defaults(func=cmd_results)
    ct = sub.add_parser("control")
    ct.add_argument("--n", type=int, default=40)
    ct.set_defaults(func=cmd_control)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
