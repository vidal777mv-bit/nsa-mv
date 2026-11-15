"""Refined search for the targets' twins (STANDARDS 10.13, v1.4 product layer). Frozen score: v1.3 config unchanged.

For each target, its top-10 Earth twins from the frozen search (data/derived/ranking) are re-measured on a 5 x 5 grid of
2 km steps (offsets -4..4 km in east and north) around the candidate centre. Each candidate gets ONE NASADEM clip,
half-width 8.5 km, clipped with the existing STAC function (analog.io.fetch.stac_clip) and kept under
data/derived/refine/clips/ (never in data/raw). The offset with the lowest D to the target is kept (refined_offset_km).
A candidate whose measure record is not NASADEM (COPDEM above 60N, NASADEM does not exist there) is not refined: it
stays at its pool centre with its pool D and carries refine_skipped; its analog_id is the plain pool id (the measure
record id, no refine/measure file); it is ranked with the refined ones by the same rule.

Outputs (data/derived/refine/):
- clips/<pool id>.tif            the candidate clip (resumable: an existing clip is reused);
- measure/<refined id>.json      one measure-style record per (target, candidate): features at the kept offset, the
                                 clip as source (read by export_viz and mission_pct through _common.window_record_path);
- <target>.json                  the refined ranking: the 10 candidates re-sorted by the refined D, tie groups by the same
                                 anchor rule and the same relief-class threshold as search (the tie rule is unchanged),
                                 with rank_before, D_before (frozen search), D_after, refined_offset_km and its centre.

Usage:
  .venv/Scripts/python.exe pipelines/refine_search.py --ids jezero          (sample: one target)
  .venv/Scripts/python.exe pipelines/refine_search.py                        (all targets with a ranking)
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    Paths,
    RunLog,
    ids_arg,
    load_json,
    make_paths,
    measure_raw,
    noise_file_name,
    parse_args,
    provenance_block,
    read_config,
    refine_dir,
    select_ids,
    sites_list,
    tie_groups,
    utc_now,
    write_json,
)
from analog.core import measure as meas  # noqa: E402
from analog.io import fetch  # noqa: E402
from build_measure import measure_key  # noqa: E402

CLIP_HALF_KM = 8.5  # 10.13: one clip per candidate
STEP_KM = 2.0
OFFSETS_KM = (-4.0, -2.0, 0.0, 2.0, 4.0)  # 5 x 5 grid
KM_PER_DEG_LAT = 111.19493
TOP_K = 10


def shifted_centre(lat: float, lon: float, dx_km: float, dy_km: float) -> tuple[float, float]:
    """Centre moved dx_km east and dy_km north (equirectangular, fine at this scale)."""
    dlat = dy_km / KM_PER_DEG_LAT
    dlon = dx_km / (KM_PER_DEG_LAT * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def candidate_clip(paths: Paths, pool_id: str, lat: float, lon: float, log: RunLog) -> Path | None:
    """The 8.5 km NASADEM clip of one candidate (reused when it exists). None with a logged reason on failure."""
    out = refine_dir(paths) / "clips" / f"{pool_id}.tif"
    if out.exists():
        return out
    try:
        meta = fetch.stac_clip("nasadem", "elevation", lat, lon, CLIP_HALF_KM, out)
    except fetch.FetchError as exc:
        log.event("error", "clip failed (candidate skipped)", id=pool_id, reason=str(exc)[:300])
        return None
    log.event("info", "clip written", id=pool_id, bytes=meta["bytes"], valid_fraction=meta["valid_fraction"])
    return out


NOT_NASADEM_REASON = "no NASADEM above 60N"


def candidate_sensor(paths: Paths, pool_id: str) -> tuple[str, str]:
    """(sensor, source_id) of a pool candidate, read from its measure record (data/derived/measure/<pool id>.json).
    A record without the field is NASADEM, as before the Arctic windows. A missing record is NASADEM too."""
    path = paths.stage("measure") / f"{pool_id}.json"
    rec = load_json(path) if path.exists() else {}
    sensor = rec.get("sensor") or "nasadem"
    return sensor, rec.get("source_id", "nasadem")


def refine_candidate(clip: Path, lat: float, lon: float, target_feats: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """Measure the 25 offsets of one candidate clip. Returns the best offset (lowest D), the D at offset 0 on this clip,
    and every (dx, dy, D) so the search is auditable. D is None when no offset gives a valid window."""
    fcfg = cfg["features"]
    min_shared = cfg["distance"]["min_shared_features"]
    grid: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    d0: float | None = None
    for dy in OFFSETS_KM:
        for dx in OFFSETS_KM:
            slat, slon = shifted_centre(lat, lon, dx, dy)
            res = measure_raw(clip, slat, slon, "earth", cfg)
            d = None
            if res["status"] == "ok":
                d = meas.distance(target_feats, res["features"], fcfg, min_shared)
            grid.append({"dx_km": dx, "dy_km": dy, "D": d, "status": res["status"], "reason": res["reason"]})
            if dx == 0 and dy == 0:
                d0 = d
            if d is not None and (best is None or d < best["D"]):
                best = {"dx_km": dx, "dy_km": dy, "D": d, "lat": slat, "lon": slon, "features": res["features"],
                        "n_valid": res["n_valid"], "coverage": res["coverage"]}
    return {"best": best, "D0_clip": d0, "grid": grid}


def run_target(paths: Paths, tid: str, cfg: dict[str, Any], noise: dict[str, Any], log: RunLog,
               cache: dict[str, dict[str, Any]]) -> int:
    """Refined ranking of one target. Returns the number of twins refined (0 when skipped)."""
    rk_path = paths.stage("ranking") / f"{tid}.json"
    tm_path = paths.stage("measure") / f"{tid}.json"
    if not rk_path.exists() or not tm_path.exists():
        log.event("warn", "target has no frozen ranking or measure record: skipped", id=tid)
        return 0
    rk = load_json(rk_path)
    tm = load_json(tm_path)
    if tm.get("status") != "ok":
        log.event("warn", "target not measured: skipped", id=tid, status=tm.get("status"))
        return 0
    cls = meas.relief_class(tm["features"].get("slope_p95_deg"), float(noise["flat_slope_p95_deg"]))
    p95 = None if cls is None else noise["classes"][cls]["p95"]
    if p95 is None:
        log.event("error", "no dev noise value for the target's relief class: skipped", id=tid, relief_class=cls)
        return 0
    rows = rk["ranking"][:TOP_K]
    entries: list[dict[str, Any]] = []
    for row in rows:
        pid = row["analog_id"]
        sensor, source_id = candidate_sensor(paths, pid)
        if sensor != "nasadem":
            entries.append({
                "analog_id": pid, "pool_id": pid, "rank_before": row["rank"], "D_before": row["D"],
                "D_after": row["D"], "D_clip_offset0": None, "refined_offset_km": None, "grid": [],
                "lat_before": row["lat"], "lon_before": row["lon"], "lat": row["lat"], "lon": row["lon"],
                "sensor": sensor, "source_id": source_id, "refine_skipped": NOT_NASADEM_REASON,
            })
            continue
        if pid not in cache:
            clip = candidate_clip(paths, pid, row["lat"], row["lon"], log)
            cache[pid] = {"clip": clip, "result": {}}
        if cache[pid]["clip"] is None:
            log.event("warn", "candidate without clip: not refined", target=tid, analog=pid)
            continue
        if tid not in cache[pid]["result"]:
            cache[pid]["result"][tid] = refine_candidate(cache[pid]["clip"], row["lat"], row["lon"], tm["features"], cfg)
        res = cache[pid]["result"][tid]
        best = res["best"]
        rid = f"{tid}__{pid}"
        if best is None:
            log.event("warn", "no valid offset for candidate: not refined", target=tid, analog=pid)
            continue
        rec = {
            "id": rid, "kind": "refined", "body": "earth", "name": f"{pid} (refined for {tid})", "lat": best["lat"],
            "lon": best["lon"], "status": "ok", "reason": None, "pool_id": pid, "target_id": tid,
            "source_id": "nasadem", "source_path": cache[pid]["clip"].relative_to(paths.root).as_posix(),
            "L": cfg["grid"]["L_m"], "R": cfg["grid"]["R_m"], "features": best["features"],
            "n_valid": best["n_valid"], "coverage": best["coverage"],
            "near_known_analog": row.get("near_known_analog"), "valid_fraction": None,
            "worldcover_share": None, "measure_key": measure_key(cfg), "config_version": cfg["version"],
        }
        write_json(refine_dir(paths) / "measure" / f"{rid}.json", rec)
        entries.append({
            "analog_id": rid, "pool_id": pid, "rank_before": row["rank"], "D_before": row["D"],
            "D_after": best["D"], "D_clip_offset0": res["D0_clip"], "refined_offset_km": [best["dx_km"], best["dy_km"]],
            "lat_before": row["lat"], "lon_before": row["lon"], "lat": best["lat"], "lon": best["lon"],
            "grid": res["grid"], "sensor": "nasadem", "source_id": "nasadem", "refine_skipped": None,
        })
    entries.sort(key=lambda r: (r["D_after"], r["analog_id"]))
    ds = [r["D_after"] for r in entries]
    groups = tie_groups(ds, float(p95))
    ranking = []
    for rank, (r, g) in enumerate(zip(entries, groups), start=1):
        ranking.append({"rank": rank, "analog_id": r["analog_id"], "D": r["D_after"], "tie_group": g,
                        "lat": r["lat"], "lon": r["lon"], "source_id": r["source_id"], "pool_id": r["pool_id"],
                        "rank_before": r["rank_before"], "D_before": r["D_before"],
                        "refined_offset_km": r["refined_offset_km"], "D_clip_offset0": r["D_clip_offset0"],
                        "sensor": r["sensor"], "refine_skipped": r["refine_skipped"]})
    n_refined = sum(1 for r in ranking if r["refine_skipped"] is None)
    body = {
        "target_id": tid, "body": rk["body"], "stage": "refine_search", "created": utc_now(),
        "method": "5x5 grid of 2 km offsets (-4..4 km) around each top-10 twin, one NASADEM clip (half-width 8.5 km) per candidate; "
                  "candidates not measured on NASADEM (COPDEM above 60N) keep their pool centre and D (refine_skipped); "
                  "lowest D kept; top-10 re-sorted; tie rule unchanged (anchor, p95 of the target's relief class)",
        "tie_rule": {"noise_p95": float(p95), "relief_class": cls, "rule": "new group when D - D_anchor >= noise p95"},
        "n_refined": n_refined, "ranking": ranking,
        "candidates": entries,
        "provenance": provenance_block(paths, "ranking", [(f"measure:{tid}", tm_path), ("ranking", rk_path)]),
    }
    write_json(refine_dir(paths) / f"{tid}.json", body)
    log.event("info", "refined ranking written", id=tid, refined=n_refined, not_refined=len(ranking) - n_refined,
              top1_changed=bool(rows and ranking and ranking[0]["pool_id"] != rows[0]["analog_id"]))
    return len(ranking)


def run(paths: Paths, ids: list[str] | None) -> int:
    """Refined rankings for the targets in scope. Returns the number of targets written (0 when refused)."""
    cfg = read_config(paths)
    log = RunLog(refine_dir(paths), "refine_search")
    noise_path = paths.stage("validation") / noise_file_name(cfg["version"])
    if not noise_path.exists():
        log.event("error", "refused: noise thresholds not found (validate.py --noise first)", path=noise_path.name)
        return 0
    noise = load_json(noise_path)
    targets = [t["id"] for t in select_ids(sites_list(paths), ids) if t.get("role") == "target"]
    cache: dict[str, dict[str, Any]] = {}
    written = 0
    for tid in targets:
        written += 1 if run_target(paths, tid, cfg, noise, log, cache) else 0
    log.event("info", "done", targets_written=written, candidates_clipped=sum(1 for v in cache.values() if v["clip"]))
    return written


def main(argv: list[str] | None = None) -> int:
    args = parse_args("Refined search: 5 x 5 offsets of 2 km around each top-10 twin (STANDARDS 10.13).")
    paths = make_paths(args.root, args.sample)
    n = run(paths, ids_arg(args))
    return 0 if n else 2


if __name__ == "__main__":
    raise SystemExit(main())
