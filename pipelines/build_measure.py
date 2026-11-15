"""P2 build_measure: six terrain features per window on the 100 m standard grid (STANDARDS sections 3, 4, 10.2).

Windows measured:
- targets: config/sites.json (role target), raw file found through data/raw/manifest.json (source_id = dem_source_id);
- dev regions: config/regions.json (role dev) with both sensors: <region>__nasadem and <region>__copdem;
  reserved regions are NEVER measured here (only validate.py measures them, inside its run);
- pool: data/raw/earth/pool/index.json, kept only when worldcover_share >= 0.8 (STANDARDS 10.2). Each row gives its
  sensor and source_id (NASADEM when absent); a row with excluded != null is recorded as status "excluded", not measured.

Output: <derived>/measure/<id>.json, one per window, with status ok | skipped | missing | error, the reason, the grid
metadata and the features (null unless ok). Skips and errors are also written to measure/run_log.jsonl.

Resumable: a window whose record already exists with the same measure_key (hash of the grid, TPI and Hurst-lag
settings, which are the only config values that change a feature; sigma does not) is skipped. --force re-measures.
A progress line is printed every PROGRESS_EVERY jobs. --kind limits the run (default target,region,pool; holdout only when named).

Usage:
  .venv/Scripts/python.exe pipelines/build_measure.py --ids haworth,jezero
  .venv/Scripts/python.exe pipelines/build_measure.py --kind pool
  .venv/Scripts/python.exe pipelines/build_measure.py --sample
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    SAMPLE_REGIONS,
    SAMPLE_TARGETS,
    WORLDCOVER_MIN_SHARE,
    Paths,
    RunLog,
    ids_arg,
    make_paths,
    load_json,
    local_source_path,
    site_raw_path,
    manifest_paths,
    measure_raw,
    parse_args,
    pool_index,
    provenance_block,
    read_config,
    region_raw,
    regions_list,
    sample_pool,
    select_ids,
    sites_list,
    write_json,
)

SENSORS = (("nasadem", "nasadem", "nasadem"), ("cop_dem_glo30", "copdem", "copdem"))  # (source_id, sensor key, id tag)
HOLDOUT_ROLE = "holdout_v13"  # config/regions.json role of the fresh v1.3 holdout (STANDARDS 10.11)
KINDS = ("target", "region", "pool", "holdout")
DEFAULT_KINDS = ("target", "region", "pool")  # holdout is measured only when asked by name (--kind holdout)
PROGRESS_EVERY = 200


def measure_key(cfg: dict[str, Any]) -> str:
    """sha256 of the config values that change a feature: grid, TPI and Hurst lags (sigma and weights do not).

    Used only to decide whether an existing record can be reused on a resumed run (STANDARDS 7 keeps the full
    config hash in the provenance block).
    """
    keep = {"grid": cfg["grid"], "tpi": cfg["tpi"], "hurst_lags_px": cfg["features"]["hurst"]["lags_px"]}
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode("utf-8")).hexdigest()


def reusable(rec: dict[str, Any], job: dict[str, Any], key: str) -> bool:
    """True when an existing record still matches its job: same measure_key, sensor, source_id and excluded value,
    and status "excluded" exactly when the job is excluded. Records written before the excluded field have None."""
    if rec.get("measure_key") != key:
        return False
    if rec.get("sensor") != job.get("sensor") or rec.get("source_id") != job.get("source_id"):
        return False
    if rec.get("excluded") != job.get("excluded"):
        return False
    return (rec.get("status") == "excluded") == (job.get("excluded") is not None)


def _record(job: dict[str, Any], paths: Paths, result: dict[str, Any], inputs: list[tuple[str, Path]],
            key: str) -> dict[str, Any]:
    """Assemble the JSON record of one window (provenance included)."""
    prov_inputs = [(sid, p) for sid, p in inputs if p.exists()]
    return {
        "id": job["id"],
        "kind": job["kind"],
        "measure_key": key,
        "body": job["body"],
        "name": job.get("name"),
        "lat": job["lat"],
        "lon": job["lon"],
        "role": job.get("role"),
        "class": job.get("class"),
        "region_id": job.get("region_id"),
        "sensor": job.get("sensor"),
        "source_id": job.get("source_id"),
        "source_path": paths.rel(job["path"]) if job.get("path") else None,
        "near_known_analog": job.get("near_known_analog"),
        "valid_fraction": job.get("valid_fraction"),
        "worldcover_share": job.get("worldcover_share"),
        "excluded": job.get("excluded"),
        "status": result["status"],
        "reason": result["reason"],
        "L": result["L"],
        "R": result["R"],
        "native_res_m": result["native_res_m"],
        "coverage": result["coverage"],
        "n_valid": result["n_valid"],
        "crs_src": result["crs_src"],
        "crs_dst": result["crs_dst"],
        "features": result["features"],
        "provenance": provenance_block(paths, "measure", prov_inputs),
    }


def target_jobs(paths: Paths, sites: list[dict[str, Any]], manifest: dict[str, list[Path]]) -> list[dict[str, Any]]:
    """One job per planetary target. Missing or non-GeoTIFF raw files become pre-checked skips with a reason."""
    jobs: list[dict[str, Any]] = []
    for s in sites:
        if s.get("role") != "target":
            continue
        job = {"id": s["id"], "kind": "target", "body": s["body"], "name": s["name"], "lat": s["lat"],
               "lon": s["lon"], "role": "target", "source_id": s["dem_source_id"], "path": None, "pre": None}
        raw = site_raw_path(manifest.get(s["dem_source_id"], []), s["id"])  # the path of THIS site (shared sources)
        if raw is None and not manifest.get(s["dem_source_id"]):
            raw = local_source_path(paths, s["dem_source_id"], s["id"])  # manifest lacks it: sources.json filename
        if raw is None:
            job["pre"] = ("missing", "dem_source_id not in data/raw/manifest.json nor a local source filename")
        elif not raw.exists():
            job["pre"] = ("missing", f"raw file not on disk: {paths.rel(raw)}")
        elif raw.suffix.lower() not in (".tif", ".tiff"):
            job["pre"] = ("skipped", f"raw input is {raw.suffix} (archive, tile not extracted): not a GeoTIFF")
        job["path"] = raw
        jobs.append(job)
    return jobs


def holdout_jobs(paths: Paths, regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One NASADEM job per holdout region (role holdout_v13, STANDARDS 10.11). Measured only with --kind holdout."""
    jobs: list[dict[str, Any]] = []
    for r in regions:
        if r.get("role") != HOLDOUT_ROLE:
            continue
        raw = region_raw(paths, r["id"], "nasadem")
        job = {"id": f"{r['id']}__nasadem", "kind": "holdout", "body": r["body"], "name": r["name"],
               "lat": r["lat"], "lon": r["lon"], "role": HOLDOUT_ROLE, "class": r["class"], "region_id": r["id"],
               "sensor": "nasadem", "source_id": "nasadem", "path": raw, "pre": None}
        if raw is None:
            job["pre"] = ("missing", f"no nasadem GeoTIFF in data/raw/earth/{r['id']}/")
        jobs.append(job)
    return jobs


def region_jobs(paths: Paths, regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Two jobs per dev region (NASADEM and Copernicus). Reserved and known-analog regions are not measured here."""
    jobs: list[dict[str, Any]] = []
    for r in regions:
        if r.get("role") != "dev":
            continue
        for sensor_id, sensor, tag in SENSORS:
            raw = region_raw(paths, r["id"], sensor)
            job = {"id": f"{r['id']}__{tag}", "kind": "region", "body": r["body"], "name": r["name"],
                   "lat": r["lat"], "lon": r["lon"], "role": "dev", "class": r["class"], "region_id": r["id"],
                   "sensor": tag, "source_id": sensor_id, "path": raw, "pre": None}
            if raw is None:
                job["pre"] = ("missing", f"no {sensor} GeoTIFF in data/raw/earth/{r['id']}/")
            jobs.append(job)
    return jobs


def excluded_reason(excl: Any) -> str:
    """Reason text for an index row with excluded != null: the rule and its value (not measured)."""
    if isinstance(excl, dict):
        return f"excluded by rule {excl.get('rule')}: value {excl.get('value')} (threshold {excl.get('threshold')})"
    return f"excluded: {excl}"


def pool_jobs(paths: Paths, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One job per pool window. The sensor and source_id come from the index row (NASADEM when absent); the path is
    read as given, whatever the sensor. A row with excluded != null is a pre-checked "excluded" (not measured);
    worldcover_share below 0.8 (or absent) is a pre-checked skip (STANDARDS 10.2)."""
    jobs: list[dict[str, Any]] = []
    for e in entries:
        raw = paths.root / e["path"] if e.get("path") else None
        job = {"id": f"pool__{e['id']}", "kind": "pool", "body": "earth", "name": None, "lat": float(e["lat"]),
               "lon": float(e["lon"]), "role": "pool", "source_id": e.get("source_id", "nasadem"),
               "sensor": e.get("sensor", "nasadem"), "path": raw, "pre": None,
               "near_known_analog": e.get("near_known_analog"), "valid_fraction": e.get("valid_fraction"),
               "worldcover_share": e.get("worldcover_share"), "excluded": e.get("excluded")}
        share = e.get("worldcover_share")
        if job["excluded"] is not None:
            job["pre"] = ("excluded", excluded_reason(job["excluded"]))
        elif share is None:
            job["pre"] = ("skipped", "worldcover_share not in pool index")
        elif float(share) < WORLDCOVER_MIN_SHARE:
            job["pre"] = ("skipped", f"worldcover_share {float(share):.3f} < {WORLDCOVER_MIN_SHARE}")
        elif raw is None or not raw.exists():
            job["pre"] = ("missing", "pool raw file not on disk")
        jobs.append(job)
    return jobs


def run(paths: Paths, ids: list[str] | None, kinds: list[str] | None = None, force: bool = False) -> int:
    """Measure every job in scope and write one JSON per window. Returns the number of windows measured this run.

    kinds: subset of target | region | pool | holdout (None = target, region, pool). force: re-measure windows that already have a record with
    the same measure_key (default: such records are reused, which makes an interrupted run resumable).
    """
    cfg = read_config(paths)
    key = measure_key(cfg)
    stage_dir = paths.stage("measure")
    log = RunLog(stage_dir, "build_measure")
    manifest = manifest_paths(paths)

    sites = sites_list(paths)
    regions = regions_list(paths)
    entries, reason = pool_index(paths)
    if entries is None:
        log.event("warn", "pool skipped", reason=reason)
        entries = []

    targets = [s for s in sites if s.get("role") == "target"]
    dev_regions = [r for r in regions if r.get("role") == "dev"]
    pool = entries
    if paths.sample:
        if ids is None:  # --ids overrides the default sample set (it is still a sample-mode run)
            targets = targets[:SAMPLE_TARGETS]
        available = [r for r in dev_regions
                     if all(region_raw(paths, r["id"], k) is not None for _, k, _ in SENSORS)]
        keep = {r["id"] for r in available[:SAMPLE_REGIONS]}
        dev_regions = [r for r in dev_regions if r["id"] in keep]
        pool = sample_pool(entries) if entries else []
        log.event("info", "sample selection", targets=[t["id"] for t in targets],
                  regions=sorted(keep), regions_with_both_sensors=len(available), pool=len(pool))

    jobs = target_jobs(paths, targets, manifest)
    jobs += region_jobs(paths, dev_regions)
    jobs += pool_jobs(paths, pool)
    jobs += holdout_jobs(paths, regions)
    jobs = select_ids(jobs, ids)
    wanted = tuple(kinds) if kinds else DEFAULT_KINDS
    bad = sorted(set(wanted) - set(KINDS))
    if bad:
        raise ValueError(f"unknown kind(s) {bad}; use {KINDS}")
    jobs = [j for j in jobs if j["kind"] in wanted]

    t0 = time.monotonic()
    counts: dict[str, int] = {}
    measured = 0
    resumed = 0
    n_jobs = len(jobs)
    for i, job in enumerate(jobs, start=1):
        out_path = stage_dir / f"{job['id']}.json"
        if not force and out_path.exists() and reusable(load_json(out_path), job, key):
            resumed += 1
        else:
            inputs: list[tuple[str, Path]] = []
            if job["path"] is not None and job["path"].exists():
                inputs.append((job["source_id"], job["path"]))
            if job["pre"] is not None:
                status, why = job["pre"]
                result = {"status": status, "reason": why, "L": cfg["grid"]["L_m"], "R": cfg["grid"]["R_m"],
                          "native_res_m": None, "coverage": None, "n_valid": None, "crs_src": None,
                          "crs_dst": None, "features": None}
            else:
                result = measure_raw(job["path"], job["lat"], job["lon"], job["body"], cfg)
            write_json(out_path, _record(job, paths, result, inputs, key))
            measured += 1
            counts[result["status"]] = counts.get(result["status"], 0) + 1
            if result["status"] != "ok":
                log.event("warn", result["status"], id=job["id"], reason=result["reason"])
        if i % PROGRESS_EVERY == 0 or i == n_jobs:
            log.event("info", "progress", done=i, total=n_jobs, measured_now=measured, resumed=resumed,
                      by_status=dict(sorted(counts.items())), elapsed_s=round(time.monotonic() - t0, 1))
    log.event("info", "done", windows_total=n_jobs, measured_now=measured, resumed=resumed,
              by_status=dict(sorted(counts.items())), kinds=list(wanted))
    return measured


def main(argv: list[str] | None = None) -> int:
    args = parse_args(
        "Measure targets, dev regions and pool windows (P2).",
        extra=[
            (("--kind",), {"default": None, "help": "comma-separated subset of target,region,pool,holdout (holdout only when named)"}),
            (("--force",), {"action": "store_true", "help": "re-measure windows that already have a record"}),
        ],
    )
    paths = make_paths(args.root, args.sample)
    kinds = [k.strip() for k in args.kind.split(",") if k.strip()] if args.kind else None
    run(paths, ids_arg(args), kinds=kinds, force=bool(args.force))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
