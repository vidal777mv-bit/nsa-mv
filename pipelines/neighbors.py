"""P-N neighbours (STANDARDS 10.14): exact Earth twins of the 16 targets and of every Mars atlas cell.

Reads only persisted outputs: config/measure.json (v1.3), data/derived/validation/noise_v1.3.json (tie thresholds),
data/derived/measure (Earth pool and target records), site/data/atlas/mars_cells.json (Mars cells),
data/derived/context/earth_context.json and the site cards/rankings/atlas (Earth context, places), and
config/known_analog_regions.json (novelty rule, recomputed and checked against the persisted novelty).

Earth pool (Arctic integration 2026-11-14, docs/ARCTIC_INTEGRATION.md): every ok pool record of data/derived/measure.
That is the NASADEM windows (pool_00001..02000, sensor "nasadem"; a record with no sensor field counts as NASADEM) and
the Arctic windows (sensor "copdem", above 60N where NASADEM does not exist). The NASADEM band is the subset with
sensor == nasadem; every gap below is computed twice, over all the pool and over that band.

Outputs (data/derived/neighbors/):
- targets.parquet, mars_cells.parquet   one row per query: features, relief class, tie threshold, nearest D, tie set
                                        size, Earth gap flag (all pool), d_nearest_nasadem and gap_nasadem (NASADEM
                                        band only, same rule and threshold), top-10 twins (twin_row, twin_id, twin_D);
- earth_windows.parquet                 one row per Earth pool window (row index = twin_row): sensor, features, novelty,
                                        context and place where a persisted record exists (null otherwise);
- run.json                              counts, gap shares with Wilson 95% intervals, exactness sample, timing,
                                        checks against the unrefined rankings and the persisted novelty, provenance.

Distance (STANDARDS 4 with v1.3 weights = 1 over slope_p95_deg, hi, hurst): D = ||z_a - z_b|| / sqrt(K). Trees are
built over the Earth pool rows with no NaN in these features. The target tree excludes near_known_analog windows
(search.py rule, 25 km); the Mars tree does not (mars_atlas.py rule). Currently no pool window is flagged, so both
trees hold the same rows; the flag is still applied.

Gap (Earth gap, STANDARDS 10.14): d_nearest (= D to the nearest twin) > tie threshold of the query's relief class (noise p95 of the class,
rugged = slope_p95_deg >= 3 deg). Equivalent to an empty tie set (ties = windows with D <= threshold).
NASADEM-band gap: the same rule over the NASADEM band only (d_nearest_nasadem, gap_nasadem). With all the pool
NASADEM the two are identical. An empty band (no valid NASADEM window) gives d_nearest_nasadem null and gap_nasadem 1.

Usage:
  .venv/Scripts/python.exe pipelines/neighbors.py            (writes data/derived/neighbors/*)
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    Paths,
    RunLog,
    SEED,
    features_in_distance,
    load_json,
    make_paths,
    noise_file_name,
    provenance_block,
    read_config,
    sites_list,
    utc_now,
    window_records,
    write_json,
)
from analog.core import measure as meas  # noqa: E402
from analog.core import neighbors as nb  # noqa: E402
from analog.core.stats import wilson  # noqa: E402
from analog.io.places import haversine_km  # noqa: E402

N_TWINS = 10
SAMPLE_MARS = 84     # exactness sample: 16 targets + 84 Mars cells + 100 pool windows = 200 queries (STANDARDS 10.14)
SAMPLE_POOL = 100
POOL_PREFIX = "pool__pool_"


@dataclass
class Engine:
    """Everything the query pass needs, built once from persisted outputs."""

    cfg: dict[str, Any]
    feats: list[str]
    sigma: np.ndarray
    weights: np.ndarray
    flat_below: float
    thr: dict[str, float]
    pool_ids: list[str]
    pool_lat: np.ndarray
    pool_lon: np.ndarray
    pool_X: np.ndarray          # raw in-distance values (nan = missing)
    pool_near: np.ndarray       # near_known_analog flag
    valid_all: np.ndarray       # rows in the Mars tree
    valid_tgt: np.ndarray       # rows in the target tree
    tree_all: Any
    tree_tgt: Any
    map_all: np.ndarray         # tree row -> pool row
    map_tgt: np.ndarray
    pool_nasadem: np.ndarray    # NASADEM band flag per pool row (sensor nasadem, or no sensor field)
    tree_nas_all: Any           # NASADEM band trees (None when the band has no valid row)
    tree_nas_tgt: Any
    map_nas_all: np.ndarray     # band tree row -> pool row
    map_nas_tgt: np.ndarray
    pool_mission: dict[str, Any] = field(default_factory=dict)  # persisted mission records (bare pool ids)


def feat_vector(features: dict[str, Any], feats: list[str]) -> np.ndarray:
    """In-distance values as floats (nan for null)."""
    return np.array([np.nan if features.get(k) is None else float(features[k]) for k in feats], dtype=float)


def build_engine(paths: Paths) -> Engine:
    """Load config, thresholds and the Earth pool, and build both trees. Raises on any missing input (no guessing)."""
    cfg = read_config(paths)
    feats = features_in_distance(cfg)
    spec = [cfg["features"][k] for k in feats]
    weights = np.array([float(s["weight"]) for s in spec], dtype=float)
    if not np.all(weights == weights[0]):
        raise ValueError(f"P-N assumes equal weights over the in-distance features, got {weights.tolist()}")
    if any(s.get("sigma") is None for s in spec):
        raise ValueError("sigma not calibrated for an in-distance feature")
    sigma = np.array([float(s["sigma"]) for s in spec], dtype=float)

    noise = load_json(paths.derived / "validation" / noise_file_name(cfg["version"]))
    flat_below = float(noise["flat_slope_p95_deg"])
    thr = {}
    for cls, info in noise["classes"].items():
        if info["p95"] is None:
            raise ValueError(f"no dev noise p95 for relief class {cls!r}")
        thr[cls] = float(info["p95"])

    recs = sorted(window_records(paths.stage("measure"), kind="pool", status="ok"), key=lambda r: str(r["id"]))
    pool_ids = [str(r["id"]) for r in recs]
    pool_X = np.vstack([feat_vector(r["features"], feats) for r in recs])
    pool_near = np.array([r.get("near_known_analog") is True for r in recs])
    pool_lat = np.array([float(r["lat"]) for r in recs])
    pool_lon = np.array([float(r["lon"]) for r in recs])
    pool_nasadem = np.array([is_nasadem(r) for r in recs], dtype=bool)
    return engine_from_arrays(cfg, feats, sigma, weights, flat_below, thr, pool_ids, pool_lat, pool_lon,
                              pool_X, pool_near, pool_nasadem)


def is_nasadem(rec: dict[str, Any]) -> bool:
    """NASADEM band of a measure record: sensor == "nasadem", or no sensor field (the pre-Arctic pool)."""
    s = rec.get("sensor")
    return s is None or s == "nasadem"


def _band_tree(Z: np.ndarray, mask: np.ndarray) -> Any:
    """Tree over the rows of Z selected by mask, or None when the band has no row."""
    return nb.build_tree(Z[mask]) if mask.any() else None


def engine_from_arrays(cfg: dict[str, Any], feats: list[str], sigma: np.ndarray, weights: np.ndarray,
                       flat_below: float, thr: dict[str, float], pool_ids: list[str], pool_lat: np.ndarray,
                       pool_lon: np.ndarray, pool_X: np.ndarray, pool_near: np.ndarray,
                       pool_nasadem: np.ndarray) -> Engine:
    """Trees over the pool arrays: all valid rows, and the NASADEM band of each. No I/O (the tests use it too)."""
    Z = nb.standardise(pool_X, sigma)
    valid_all = nb.valid_rows(Z)
    valid_tgt = valid_all & ~pool_near
    nas = np.asarray(pool_nasadem, dtype=bool)
    valid_nas_all = valid_all & nas
    valid_nas_tgt = valid_tgt & nas
    return Engine(
        cfg=cfg, feats=feats, sigma=sigma, weights=weights, flat_below=flat_below, thr=thr,
        pool_ids=pool_ids, pool_lat=pool_lat, pool_lon=pool_lon, pool_X=pool_X, pool_near=pool_near,
        valid_all=valid_all, valid_tgt=valid_tgt,
        tree_all=nb.build_tree(Z[valid_all]), tree_tgt=nb.build_tree(Z[valid_tgt]),
        map_all=np.flatnonzero(valid_all), map_tgt=np.flatnonzero(valid_tgt),
        pool_nasadem=nas,
        tree_nas_all=_band_tree(Z, valid_nas_all), tree_nas_tgt=_band_tree(Z, valid_nas_tgt),
        map_nas_all=np.flatnonzero(valid_nas_all), map_nas_tgt=np.flatnonzero(valid_nas_tgt),
    )


def load_queries(paths: Paths) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(targets, mars cells). Targets: the role 'target' sites with an ok measure record (none skipped silently)."""
    targets = []
    site_targets = {t["id"]: t for t in load_json(paths.site_data / "targets.json")["targets"]}
    for s in sites_list(paths):
        if s.get("role") != "target":
            continue
        rec = load_json(paths.stage("measure") / f"{s['id']}.json")
        if rec.get("status") != "ok":
            raise ValueError(f"target {s['id']} is not measured (status {rec.get('status')})")
        targets.append({"id": s["id"], "kind": "target", "body": rec["body"], "name": s.get("name"),
                        "lat": float(rec["lat"]), "lon": float(rec["lon"]), "features": rec["features"],
                        "tree": "tgt", "mission": site_targets[s["id"]].get("mission"),
                        "landing_class": site_targets[s["id"]].get("landing_class")})
    cells_raw = load_json(paths.site_data / "atlas" / "mars_cells.json")
    cells = []
    for c in cells_raw:
        cells.append({"id": str(c["id"]), "kind": "mars_cell", "body": "mars", "name": None,
                      "lat": float(c["lat"]), "lon": float(c["lon"]), "features": c["features"], "tree": "all",
                      "mission_pct": c.get("mission_pct")})
    return targets, cells


def query_one(q: dict[str, Any], eng: Engine) -> dict[str, Any]:
    """Top-10 twins, nearest D, tie set and gap of one query (tree search, exact D)."""
    x = feat_vector(q["features"], eng.feats)
    cls = meas.relief_class(q["features"].get("slope_p95_deg"), eng.flat_below)
    thr = eng.thr[cls] if cls is not None else None
    out: dict[str, Any] = {"relief_class": cls, "threshold": thr, "d_nearest": None, "tie_set_size": None,
                           "gap": None, "d_nearest_nasadem": None, "gap_nasadem": None,
                           "twin_row": [], "twin_id": [], "twin_D": [], "reason": None}
    if np.isnan(x).any():
        out["reason"] = "null in-distance feature: no distance"
        return out
    tree, mp = (eng.tree_tgt, eng.map_tgt) if q["tree"] == "tgt" else (eng.tree_all, eng.map_all)
    zq = nb.standardise(x, eng.sigma)
    idx, D = nb.knn(tree, zq, N_TWINS)
    rows = mp[idx]
    out["twin_row"] = [int(r) for r in rows]
    out["twin_id"] = [eng.pool_ids[r] for r in rows]
    out["twin_D"] = [float(d) for d in D]
    out["d_nearest"] = float(D[0])
    tree_n = eng.tree_nas_tgt if q["tree"] == "tgt" else eng.tree_nas_all
    d_n = None if tree_n is None else float(nb.knn(tree_n, zq, 1)[1][0])
    out["d_nearest_nasadem"] = d_n
    if thr is not None:
        tie_idx, _ = nb.ties(tree, zq, thr)
        out["tie_set_size"] = int(tie_idx.size)
        out["gap"] = bool(D[0] > thr)
        out["gap_nasadem"] = bool(d_n is None or d_n > thr)
    return out


def brute_one(q: dict[str, Any], eng: Engine) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Reference for one query: (pool rows, D, tie pool rows) by full formula. Same eligible set as the tree."""
    x = feat_vector(q["features"], eng.feats)
    mask = eng.valid_tgt if q["tree"] == "tgt" else eng.valid_all
    rows_map = eng.map_tgt if q["tree"] == "tgt" else eng.map_all
    idx, D = nb.brute_knn(eng.pool_X[mask], x, eng.sigma, eng.weights, N_TWINS)
    cls = meas.relief_class(q["features"].get("slope_p95_deg"), eng.flat_below)
    thr = eng.thr[cls] if cls is not None else None
    if thr is None:
        ties_rows = np.empty(0, dtype=np.int64)
    else:
        allD = np.sqrt(np.sum(eng.weights * ((eng.pool_X[mask] - x) / eng.sigma) ** 2, axis=1) / np.sum(eng.weights))
        tie_local = np.flatnonzero(allD <= thr)
        ties_rows = rows_map[tie_local[np.lexsort((tie_local, allD[tie_local]))]]
    return rows_map[idx], D, ties_rows


def exactness_sample(eng: Engine, targets: list[dict[str, Any]], cells: list[dict[str, Any]]) -> dict[str, Any]:
    """Seeded sample (SEED): all 16 targets + 84 Mars cells + 100 Earth pool windows = 200 queries.

    Checks the tree against the brute-force formula: twin indices identical (tie order included), |D diff| <= 1e-12,
    and the tie set identical to the brute-force set with D <= threshold.
    """
    rng = np.random.default_rng(SEED)
    cell_pick = sorted(int(i) for i in rng.choice(len(cells), size=SAMPLE_MARS, replace=False))
    valid_pool = np.flatnonzero(eng.valid_all)
    pool_pick = sorted(int(i) for i in rng.choice(valid_pool, size=SAMPLE_POOL, replace=False))
    queries: list[dict[str, Any]] = list(targets) + [cells[i] for i in cell_pick]
    for i in pool_pick:
        queries.append({"id": eng.pool_ids[i], "kind": "pool", "body": "earth", "lat": None, "lon": None,
                        "features": dict(zip(eng.feats, eng.pool_X[i].tolist())), "tree": "all"})
    max_dd = 0.0
    idx_bad: list[str] = []
    tie_bad: list[str] = []
    n_ties_checked = 0
    for q in queries:
        if np.isnan(feat_vector(q["features"], eng.feats)).any():
            continue
        got = query_one(q, eng)
        b_rows, b_D, b_ties = brute_one(q, eng)
        if [int(r) for r in b_rows] != got["twin_row"]:
            idx_bad.append(q["id"])
        max_dd = max(max_dd, float(np.max(np.abs(np.asarray(got["twin_D"]) - b_D))))
        if got["tie_set_size"] is not None:
            n_ties_checked += 1
            tree_ties = nb.ties(eng.tree_tgt if q["tree"] == "tgt" else eng.tree_all,
                                nb.standardise(feat_vector(q["features"], eng.feats), eng.sigma),
                                eng.thr[meas.relief_class(q["features"].get("slope_p95_deg"), eng.flat_below)])[0]
            tree_rows = (eng.map_tgt if q["tree"] == "tgt" else eng.map_all)[tree_ties]
            if [int(r) for r in tree_rows] != [int(r) for r in b_ties]:
                tie_bad.append(q["id"])
    return {
        "n_queries": len(queries), "n_targets": len(targets), "n_mars_cells": len(cell_pick),
        "n_pool_windows": len(pool_pick), "seed": SEED, "k": N_TWINS,
        "index_mismatch": len(idx_bad), "index_mismatch_ids": idx_bad[:10],
        "max_abs_D_diff": max_dd, "tolerance": 1e-12,
        "tie_set_checked": n_ties_checked, "tie_set_mismatch": len(tie_bad), "tie_set_mismatch_ids": tie_bad[:10],
        "pass": (not idx_bad) and (not tie_bad) and max_dd <= 1e-12,
    }


def gap_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Gap count and share with a Wilson 95% interval over the evaluable rows (D defined and class defined)."""
    ev = [r for r in rows if r["gap"] is not None]
    k = sum(1 for r in ev if r["gap"])
    n = len(ev)
    ci = wilson(k, n) if n else None
    by_cls: dict[str, dict[str, Any]] = {}
    for cls in ("rugged", "flat"):
        sub = [r for r in ev if r["relief_class"] == cls]
        kk = sum(1 for r in sub if r["gap"])
        cc = wilson(kk, len(sub)) if sub else None
        by_cls[cls] = {"n": len(sub), "gap": kk, "wilson95": list(cc) if cc else None}
    return {"n_queries": len(rows), "n_evaluable": n, "gap": k, "gap_share": (k / n) if n else None,
            "wilson95": list(ci) if ci else None, "by_relief_class": by_cls}


def earth_context_map(paths: Paths, log: RunLog) -> tuple[dict[str, dict[str, Any]], dict]:
    """Persisted Earth context per pool id: (id -> {source, context, place, novelty, known_region_id}, checks).

    Priority cache > atlas > cards > rankings. Sources that disagree on Köppen code, elevation or town are counted.
    """
    found: dict[str, list[dict[str, Any]]] = {}

    def add(wid: str, source: str, ent: dict[str, Any]) -> None:
        found.setdefault(wid, []).append({"source": source, **ent})

    cache = load_json(paths.derived / "context" / "earth_context.json")["windows"]
    for key, e in cache.items():
        # Only the unshifted pool window (bare id). "<target>__pool__..." keys are refined windows (refine_search
        # offsets), a different place with its own context; they never describe the pool window.
        if not key.startswith(POOL_PREFIX):
            continue
        wid = key
        add(wid, "cache", {"context": e.get("context"), "place": e.get("analog_place"), "novelty": e.get("novelty"),
                           "known_region_id": e.get("known_region_id"), "lat": e.get("lat"), "lon": e.get("lon")})
    atlas = load_json(paths.site_data / "atlas" / "mars_cells.json")
    for c in atlas:
        for t in c["twins"]:
            wid = t["analog_id"]
            add(wid, "atlas", {"context": t.get("context"), "place": t.get("analog_place"),
                               "novelty": t.get("novelty"), "known_region_id": t.get("known_region_id")})
    for p in sorted((paths.site_data / "cards").glob("*.json")):
        d = load_json(p)
        aid = str(d["analog_id"])
        wid = aid if aid.startswith(POOL_PREFIX) else None
        if wid:
            add(wid, "cards", {"context": d.get("context"), "place": d.get("analog_place"),
                               "novelty": d.get("novelty"), "known_region_id": d.get("known_region_id")})
    for p in sorted((paths.site_data / "rankings").glob("*.json")):
        for r in load_json(p).get("ranking", []):
            aid = str(r["analog_id"])
            wid = aid if aid.startswith(POOL_PREFIX) else None
            if wid:
                add(wid, "rankings", {"context": r.get("context"), "place": r.get("analog_place"),
                                      "novelty": r.get("novelty"), "known_region_id": r.get("known_region_id")})

    conflicts = {"koppen_code": 0, "elevation_m": 0, "nearest_town": 0, "place_name": 0}
    out: dict[str, dict[str, Any]] = {}
    for wid, entries in found.items():
        first = entries[0]
        for e in entries[1:]:
            a, b = first.get("context") or {}, e.get("context") or {}
            if a and b:
                if a.get("koppen_code") != b.get("koppen_code"):
                    conflicts["koppen_code"] += 1
                ea, eb = a.get("elevation_m"), b.get("elevation_m")
                if ea is not None and eb is not None and abs(float(ea) - float(eb)) > 1e-6:
                    conflicts["elevation_m"] += 1
                if (a.get("nearest_town") or {}).get("name") != (b.get("nearest_town") or {}).get("name"):
                    conflicts["nearest_town"] += 1
            pa, pb = first.get("place") or {}, e.get("place") or {}
            if pa and pb and pa.get("name") != pb.get("name"):
                conflicts["place_name"] += 1
        # the context and the place may come from different entries (cache has no place; atlas has both)
        ctx_entry = next((e for e in entries if e.get("context")), None)
        place_entry = next((e for e in entries if e.get("place")), None)
        out[wid] = {"source": ctx_entry["source"] if ctx_entry else (place_entry["source"] if place_entry else None),
                    "context": ctx_entry["context"] if ctx_entry else None,
                    "place": place_entry["place"] if place_entry else None,
                    "persisted_novelty": [e["novelty"] for e in entries if e.get("novelty")],
                    "persisted_known_region_id": [e["known_region_id"] for e in entries if e.get("novelty")],
                    "persisted_latlon": [(e.get("lat"), e.get("lon")) for e in entries if e.get("lat") is not None]}
    log.event("info", "persisted Earth context gathered", windows=len(out), conflicts=conflicts)
    return out, {"windows_with_context_entry": len(out), "conflicts": conflicts}


def novelty_of(lat: float, lon: float, regions: list[dict[str, Any]]) -> tuple[str, str | None]:
    """Same rule as pipelines/earth_context.novelty_of (circle approximation, config/known_analog_regions.json)."""
    for reg in regions:
        if haversine_km(lat, lon, float(reg["lat"]), float(reg["lon"])) <= float(reg["radius_km"]):
            return "known_region", reg["id"]
    return "new", None


def rankings_check(paths: Paths, eng: Engine, targets: list[dict[str, Any]], results: dict[str, dict[str, Any]],
                   ) -> dict[str, Any]:
    """Compare the unrefined top-10 with data/derived/ranking (search.py) and the unrefined D of refine (D_before)."""
    rows = []
    n_order_bad = 0
    max_dd_rank = 0.0
    max_dd_refine = 0.0
    refine_missing = []
    for t in targets:
        tid = t["id"]
        res = results[tid]
        rk_path = paths.derived / "ranking" / f"{tid}.json"
        rk = load_json(rk_path)["ranking"] if rk_path.exists() else None
        ref_path = paths.derived / "refine" / f"{tid}.json"
        ref = load_json(ref_path)["candidates"] if ref_path.exists() else None
        if rk is None:
            refine_missing.append(tid)
            continue
        ids_rk = [str(r["analog_id"]) for r in rk]
        D_rk = [float(r["D"]) for r in rk]
        ids_mine = res["twin_id"]
        if ids_rk != ids_mine:
            n_order_bad += 1
        dd = [abs(a - b) for a, b in zip(D_rk, res["twin_D"])]
        max_dd_rank = max(max_dd_rank, max(dd) if dd else 0.0)
        if ref is not None:
            before = {str(c["pool_id"]): float(c["D_before"]) for c in ref if c.get("pool_id")}
            for pid, dv in zip(ids_mine, res["twin_D"]):
                if pid in before:
                    max_dd_refine = max(max_dd_refine, abs(before[pid] - dv))
        rows.append({"target": tid, "ranking_ids_equal": ids_rk == ids_mine, "max_abs_D_diff_ranking": max(dd) if dd else None,
                     "n_ranking": len(rk)})
    return {"n_targets_checked": len(rows), "n_targets_with_order_difference": n_order_bad,
            "max_abs_D_diff_vs_ranking_json": max_dd_rank, "max_abs_D_diff_vs_refine_D_before": max_dd_refine,
            "targets_without_ranking": refine_missing, "per_target": rows}


def run(paths: Paths) -> int:
    t0 = time.perf_counter()
    out_dir = paths.derived / "neighbors"
    out_dir.mkdir(parents=True, exist_ok=True)
    log = RunLog(out_dir, "neighbors")
    eng = build_engine(paths)
    targets, cells = load_queries(paths)
    log.event("info", "trees built", pool_rows=len(eng.pool_ids), tree_all=int(eng.valid_all.sum()),
              tree_tgt=int(eng.valid_tgt.sum()), null_excluded=[eng.pool_ids[i] for i in np.flatnonzero(~eng.valid_all)],
              near_known_excluded=int(eng.pool_near.sum()))

    # Timing and full agreement with brute force (the 200-sample test is the required check; this covers all queries)
    queries = targets + cells
    t1 = time.perf_counter()
    results = {q["id"]: query_one(q, eng) for q in queries}
    t_tree = time.perf_counter() - t1
    t2 = time.perf_counter()
    all_agree = True
    brute_bad: list[str] = []
    for q in queries:
        b_rows, _, _ = brute_one(q, eng)
        if [int(r) for r in b_rows] != results[q["id"]]["twin_row"]:
            all_agree = False
            brute_bad.append(q["id"])
    t_brute = time.perf_counter() - t2
    log.event("info", "queries done", n=len(queries), tree_s=round(t_tree, 3), brute_s=round(t_brute, 3),
              all_agree=all_agree)

    sample = exactness_sample(eng, targets, cells)
    log.event("info", "exactness sample", **{k: v for k, v in sample.items() if k.endswith("ids")})

    # Earth windows table (row index = twin_row)
    regions = load_json(paths.config_dir / "known_analog_regions.json")["regions"]
    ctx, ctx_checks = earth_context_map(paths, log)
    pool_recs = {str(r["id"]): r for r in window_records(paths.stage("measure"), kind="pool", status="ok")}
    eng.pool_mission = load_mission_records(paths)  # noqa: B010 (set once, before the earth table is built)
    novelty_mismatch: list[str] = []
    latlon_mismatch: list[str] = []
    n_novelty_checked = 0
    earth_rows = []
    for i, wid in enumerate(eng.pool_ids):
        rec = pool_recs[wid]
        nov, kid = novelty_of(eng.pool_lat[i], eng.pool_lon[i], regions)
        c = ctx.get(wid, {})
        for pn, pk in zip(c.get("persisted_novelty", []), c.get("persisted_known_region_id", [])):
            n_novelty_checked += 1
            if pn != nov or pk != kid:
                novelty_mismatch.append(wid)
                break
        for la, lo in c.get("persisted_latlon", []):
            if abs(float(la) - eng.pool_lat[i]) > 1e-9 or abs(float(lo) - eng.pool_lon[i]) > 1e-9:
                latlon_mismatch.append(wid)
                break
        cx = c.get("context") or {}
        town = cx.get("nearest_town") or {}
        pl = c.get("place") or {}
        f = rec["features"]
        earth_rows.append({
            "id": wid, "lat": float(eng.pool_lat[i]), "lon": float(eng.pool_lon[i]),
            "slope_p95_deg": _f(f.get("slope_p95_deg")), "hi": _f(f.get("hi")), "coherence": _f(f.get("coherence")),
            "hurst": _f(f.get("hurst")), "ridge_pct": _f(f.get("ridge_pct")), "valley_pct": _f(f.get("valley_pct")),
            "tree_member_target": bool(eng.valid_tgt[i]), "tree_member_mars": bool(eng.valid_all[i]),
            "near_known_analog": bool(eng.pool_near[i]), "sensor": "nasadem" if is_nasadem(rec) else str(rec["sensor"]),
            "novelty": nov, "known_region_id": kid,
            "koppen_code": _f(cx.get("koppen_code")), "koppen_class": cx.get("koppen_class"),
            "koppen_label": cx.get("koppen_label"), "elevation_m": _f(cx.get("elevation_m")),
            "town_name": town.get("name"), "town_country": town.get("country"),
            "nearest_town_km": _f(town.get("distance_km")),
            "landing_pct_moon": _f(_landing(eng.pool_mission.get(wid), "moon")),
            "landing_pct_mars": _f(_landing(eng.pool_mission.get(wid), "mars")),
            "place_name": pl.get("name"), "place_admin1": pl.get("admin1"), "place_country": pl.get("country"),
            "context_source": c.get("source"),
        })
    n_ctx = sum(1 for r in earth_rows if r["koppen_class"] is not None)
    n_place = sum(1 for r in earth_rows if r["place_name"] is not None)
    n_town = sum(1 for r in earth_rows if r["town_name"] is not None)

    # Query tables
    tgt_rows = [_query_row(q, results[q["id"]]) for q in targets]
    cell_rows = [_query_row(q, results[q["id"]]) for q in cells]
    for r, q in zip(cell_rows, cells):
        r["landing_pct"] = _f((q.get("mission_pct") or {}).get("landing", {}).get("pct"))
        r["driving_pct"] = _f((q.get("mission_pct") or {}).get("driving", {}).get("pct"))
    for r, q in zip(tgt_rows, targets):
        r["name"] = q.get("name")
        r["mission"] = q.get("mission")
        r["landing_class"] = q.get("landing_class")

    import pyarrow.parquet as pq
    pq.write_table(_table(earth_rows), out_dir / "earth_windows.parquet")
    pq.write_table(_table(tgt_rows), out_dir / "targets.parquet")
    pq.write_table(_table(cell_rows), out_dir / "mars_cells.parquet")

    gaps_t = gap_stats(tgt_rows)
    gaps_m = gap_stats(cell_rows)
    gaps_t_nas = gap_stats(_nasadem_view(tgt_rows))
    gaps_m_nas = gap_stats(_nasadem_view(cell_rows))
    inputs = [("config", paths.measure_config), ("noise", paths.derived / "validation" /
              noise_file_name(eng.cfg["version"])), ("atlas", paths.site_data / "atlas" / "mars_cells.json"),
              ("earth_context", paths.derived / "context" / "earth_context.json"),
              ("known_regions", paths.config_dir / "known_analog_regions.json"),
              ] + [(f"measure:{t['id']}", paths.stage("measure") / f"{t['id']}.json") for t in targets]
    summary = {
        "schema": "analog.neighbors/1",
        "created": utc_now(),
        "config_version": eng.cfg["version"],
        "distance": "D = ||z_a - z_b|| / sqrt(K); z = x / sigma; K = 3 in-distance features, equal weights",
        "in_distance_features": eng.feats,
        "sigma": dict(zip(eng.feats, eng.sigma.tolist())),
        "k": N_TWINS,
        "thresholds": eng.thr,
        "flat_slope_p95_deg": eng.flat_below,
        "pool": {"n_ok": len(eng.pool_ids), "n_tree_all": int(eng.valid_all.sum()),
                 "n_tree_targets": int(eng.valid_tgt.sum()),
                 "excluded_null_in_distance": [eng.pool_ids[i] for i in np.flatnonzero(~eng.valid_all)],
                 "n_near_known_flagged": int(eng.pool_near.sum()),
                 "n_nasadem_band": int(eng.pool_nasadem.sum()),
                 "n_nasadem_band_tree_all": int(len(eng.map_nas_all)),
                 "n_nasadem_band_tree_targets": int(len(eng.map_nas_tgt))},
        "targets": gaps_t,
        "mars_cells": gaps_m,
        "targets_nasadem": gaps_t_nas,
        "mars_cells_nasadem": gaps_m_nas,
        "exactness_sample": sample,
        "all_queries_match_brute_force": all_agree,
        "all_queries_brute_mismatch_ids": brute_bad[:10],
        "timing_s": {"tree_all_queries": round(t_tree, 4), "brute_force_all_queries": round(t_brute, 4),
                     "n_queries": len(queries)},
        "rankings_check": rankings_check(paths, eng, targets, results),
        "earth_context": {**ctx_checks, "windows_with_context": n_ctx, "windows_with_place": n_place,
                          "windows_with_town": n_town, "n_windows": len(eng.pool_ids)},
        "novelty_check": {"computed_rule": "config/known_analog_regions.json circle, haversine <= radius_km",
                          "persisted_entries_checked": n_novelty_checked, "mismatch": len(novelty_mismatch),
                          "mismatch_ids": novelty_mismatch[:10]},
        "latlon_check": {"mismatch": len(latlon_mismatch), "mismatch_ids": latlon_mismatch[:10]},
        "tables": {"earth_windows": len(earth_rows), "targets": len(tgt_rows), "mars_cells": len(cell_rows),
                   "twins_per_query": N_TWINS},
        "run_seconds": round(time.perf_counter() - t0, 2),
        "provenance": provenance_block(paths, "neighbors", inputs),
    }
    write_json(out_dir / "run.json", summary)
    log.event("info", "done", targets=gaps_t["gap"], mars_gap=gaps_m["gap"], exactness_pass=sample["pass"])
    return 0 if (sample["pass"] and all_agree and not novelty_mismatch) else 1


def _landing(mission_rec: dict[str, Any] | None, body: str) -> float | None:
    """Landing share under the body's limit from a persisted mission record (data/derived/mission), or None."""
    if mission_rec is None:
        return None
    return (((mission_rec.get("by_body") or {}).get(body) or {}).get("landing") or {}).get("pct")


def load_mission_records(paths: Paths) -> dict[str, dict[str, Any]]:
    """Persisted mission records of the unshifted Earth pool windows (bare id), keyed by window id."""
    out: dict[str, dict[str, Any]] = {}
    for p in sorted((paths.derived / "mission").glob("pool__pool_*.json")):
        out[p.stem] = load_json(p)
    return out


def _f(v: Any) -> float | None:
    """float or None (NaN and missing become None)."""
    if v is None:
        return None
    x = float(v)
    return None if np.isnan(x) else x


def _nasadem_view(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows as gap_stats reads them, with the NASADEM-band gap in place of the all-pool gap."""
    return [{"gap": r["gap_nasadem"], "relief_class": r["relief_class"]} for r in rows]


def _query_row(q: dict[str, Any], r: dict[str, Any]) -> dict[str, Any]:
    f = q["features"]
    return {
        "id": q["id"], "kind": q["kind"], "body": q["body"], "lat": q["lat"], "lon": q["lon"],
        "relief_class": r["relief_class"], "slope_p95_deg": _f(f.get("slope_p95_deg")), "hi": _f(f.get("hi")),
        "coherence": _f(f.get("coherence")), "hurst": _f(f.get("hurst")), "ridge_pct": _f(f.get("ridge_pct")),
        "valley_pct": _f(f.get("valley_pct")), "threshold": r["threshold"], "d_nearest": r["d_nearest"],
        "tie_set_size": r["tie_set_size"], "gap": r["gap"], "d_nearest_nasadem": r["d_nearest_nasadem"],
        "gap_nasadem": r["gap_nasadem"], "reason": r["reason"],
        "twin_row": r["twin_row"], "twin_id": r["twin_id"], "twin_D": r["twin_D"],
    }


def _table(rows: list[dict[str, Any]]):
    import pyarrow as pa
    cols: dict[str, list[Any]] = {}
    for r in rows:
        for k, v in r.items():
            cols.setdefault(k, []).append(v)
    arrays = {}
    for k, vals in cols.items():
        if k in ("twin_row",):
            arrays[k] = pa.array(vals, type=pa.list_(pa.int32()))
        elif k in ("twin_id",):
            arrays[k] = pa.array(vals, type=pa.list_(pa.string()))
        elif k in ("twin_D",):
            arrays[k] = pa.array(vals, type=pa.list_(pa.float64()))
        else:
            arrays[k] = pa.array(vals)
    return pa.table(arrays)


def main(argv: list[str] | None = None) -> int:
    paths = make_paths(None, False)
    return run(paths)


if __name__ == "__main__":
    raise SystemExit(main())
