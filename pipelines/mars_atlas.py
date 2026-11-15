"""Mars atlas (STANDARDS 10.13): the Mars pool measured with the frozen config, each cell with its top-3 Earth twins.

Frozen score (v1.3 config, sigma from the Earth pool): the six features are measured for every accepted Mars window
(data/raw/mars/pool/mars_NNNNN.tif, CTX DTM, 4.5 km half-width, Mars CRS kept) with the same measure_raw as the
targets. Its D to every Earth pool window (measure records kind pool, status ok) is the frozen distance; the top 3 are the
twins. Tie groups use the same anchor rule and the relief-class threshold of the Mars window (noise_v1.3.json).

Outputs:
- data/derived/measure/mars_NNNNN.json   measure record, kind mars_pool (the coverage grid reads it as class 2);
- site/data/atlas/mars_cells.json        the list of cells, STANDARDS 10.13 format:
                                         [{id, lat, lon, features, twins:[{analog_id, D, tie_group, analog_place,
                                         novelty, known_region_id, context}], mission_pct:{landing, driving}}];
- data/derived/atlas/mars_run.json       run summary with counts, limits and provenance (kept out of the site file).

Mission % on the Mars limits (missions.json limits.mars) on the 100 m grid, as in mission_pct.py.
Resumable: an existing mars_NNNNN measure record is reused. --limit N measures the first N windows (sample first).

Usage:
  .venv/Scripts/python.exe pipelines/mars_atlas.py --sample 50    (sample: first 50 windows)
  .venv/Scripts/python.exe pipelines/mars_atlas.py                (all accepted windows)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    Paths,
    RunLog,
    limit_for,
    load_json,
    load_places,
    make_paths,
    analog_place,
    measure_raw,
    missions_limits,
    noise_file_name,
    provenance_block,
    read_config,
    tie_groups,
    utc_now,
    window_records,
    write_json,
)
from analog.core import measure as meas  # noqa: E402
from analog.core import mission  # noqa: E402
from analog import grid as gridmod  # noqa: E402
import earth_context as EC  # noqa: E402

TWINS = 3


def mars_index(paths: Paths) -> list[dict[str, Any]]:
    """Accepted Mars pool windows (id, lat, lon, path, product_id, valid_fraction)."""
    p = paths.raw_dir / "mars" / "pool" / "index.json"
    doc = load_json(p)
    return list(doc["windows"] if isinstance(doc, dict) else doc)


def measure_window(paths: Paths, w: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """Measure one Mars window and write its record (kind mars_pool). Reused when present."""
    out = paths.stage("measure") / f"{w['id']}.json"
    if out.exists():
        return load_json(out)
    raw = paths.root / w["path"]
    res = measure_raw(raw, float(w["lat"]), float(w["lon"]), "mars", cfg)
    rec = {
        "id": w["id"], "kind": "mars_pool", "body": "mars", "name": None, "lat": float(w["lat"]),
        "lon": float(w["lon"]), "role": "mars_pool", "class": None, "region_id": None, "sensor": None,
        "source_id": "ctx_dtm", "source_path": paths.rel(raw), "product_id": w.get("product_id"),
        "valid_fraction": w.get("valid_fraction"), "near_known_analog": False, "worldcover_share": None,
        "status": res["status"], "reason": res["reason"], "L": res["L"], "R": res["R"],
        "native_res_m": res["native_res_m"], "coverage": res["coverage"], "n_valid": res["n_valid"],
        "crs_src": res["crs_src"], "crs_dst": res["crs_dst"], "features": res["features"],
        "provenance": provenance_block(paths, "measure", [("ctx_dtm", raw)] if raw.exists() else []),
    }
    write_json(out, rec)
    return rec


def rekey(paths: Paths, cfg: dict[str, Any]) -> int:
    """Backfill measure_key on records that lack it (Mars atlas and refined twins were written before the key existed).

    The key is a function of the feature-defining config only (grid, TPI, Hurst lags); the stored features do not change.
    Only records whose provenance names a config with the same feature definitions are rekeyed: the check is the key itself
    computed from the config that produced the record (its provenance config_version must be 1.1 or 1.3 here).
    Returns the number of records rekeyed.
    """
    from build_measure import measure_key

    key = measure_key(cfg)
    n = 0
    for folder in (paths.stage("measure"), paths.derived / "refine" / "measure"):
        for f in sorted(folder.glob("*.json")):
            rec = load_json(f)
            if "measure_key" in rec or rec.get("status") is None:
                continue
            cv = (rec.get("provenance") or {}).get("config_version")
            if cv is None and folder.parts[-2] == "refine":
                # refine_search wrote these with no provenance block: the frozen v1.3 config was in place for that run
                rec["config_version_inferred"] = "1.3"
            elif cv not in ("1.1", "1.3"):
                continue
            rec["measure_key"] = key
            write_json(f, rec)
            n += 1
    return n


def earth_features(paths: Paths) -> tuple[list[str], list[dict[str, Any]]]:
    """(ids, records) of the Earth pool windows with status ok: the twin candidates."""
    recs = window_records(paths.stage("measure"), kind="pool", status="ok")
    return [r["id"] for r in recs], recs


def top_twins(mars_feats: dict[str, Any], pool: list[dict[str, Any]], cfg: dict[str, Any]) -> list[tuple[float, dict]]:
    """The TWINS nearest Earth pool windows by the frozen D (null D excluded). Ties broken by id."""
    fcfg = cfg["features"]
    min_shared = cfg["distance"]["min_shared_features"]
    scored = []
    for r in pool:
        d = meas.distance(mars_feats, r["features"], fcfg, min_shared)
        if d is not None:
            scored.append((float(d), r))
    scored.sort(key=lambda t: (t[0], t[1]["id"]))
    return scored[:TWINS]


def mission_pcts(raw: Path, lat: float, lon: float, cfg: dict[str, Any], limits: dict[str, Any] | None) -> dict[str, Any]:
    """Mars landing and driving shares (percent, 100 m grid) on the Mars limits of missions.json."""
    L, R = float(cfg["grid"]["L_m"]), float(cfg["grid"]["R_m"])
    z, mask, _ = gridmod.load_local_grid(raw, lat, lon, "mars", L, R)
    slope = mission.slope_map_deg(z, mask, L)
    out: dict[str, Any] = {}
    for kind in ("landing", "driving"):
        limit, source, why = limit_for(limits, "mars", kind)
        res = mission.mission_share(slope, limit)
        out[kind] = {"pct": res["pct"], "limit_deg": limit, "source": source, "reason": why or res["reason"]}
    return out


def run(paths: Paths, limit: int | None) -> int:
    """Measure the Mars pool, write the atlas list and the run summary. Returns the number of cells written."""
    cfg = read_config(paths)
    log = RunLog(paths.derived / "atlas", "mars_atlas")
    noise_path = paths.stage("validation") / noise_file_name(cfg["version"])
    if not noise_path.exists():
        log.event("error", "refused: noise thresholds not found (validate.py --noise first)")
        return 0
    noise = load_json(noise_path)
    flat_below = float(noise["flat_slope_p95_deg"])
    limits, why = missions_limits(paths)
    if limits is None:
        log.event("warn", "missions limits missing: mission_pct null", reason=why)
    places = load_places(paths, log)

    windows = mars_index(paths)
    if limit:
        windows = windows[:limit]
    n_measured = n_skipped = 0
    for w in windows:
        rec = measure_window(paths, w, cfg)
        if rec["status"] == "ok":
            n_measured += 1
        else:
            n_skipped += 1
            log.event("warn", "Mars window not measured", id=w["id"], status=rec["status"], reason=rec["reason"])
    log.event("info", "Mars windows measured", windows=len(windows), ok=n_measured, not_ok=n_skipped)

    _ids, pool = earth_features(paths)
    cells: list[dict[str, Any]] = []
    twin_ids: set[str] = set()
    cell_twins: dict[str, list[tuple[float, dict[str, Any]]]] = {}
    for w in windows:
        rec = load_json(paths.stage("measure") / f"{w['id']}.json")
        if rec["status"] != "ok":
            continue
        tw = top_twins(rec["features"], pool, cfg)
        cell_twins[w["id"]] = tw
        twin_ids.update(r["id"] for _, r in tw)

    # Earth context of the twins (cache; novelty from the current known-regions file)
    cache_path = paths.derived / "context" / EC.CONTEXT_FILE
    cache = load_json(cache_path) if cache_path.exists() else {"windows": {}}
    missing = [i for i in sorted(twin_ids) if i not in cache["windows"]]
    cache["windows"].update(EC.build(paths, missing, log))
    EC.refresh_novelty(paths, cache, log)
    cache["provenance"] = provenance_block(paths, "cards", [])
    write_json(cache_path, cache)

    for w in windows:
        if w["id"] not in cell_twins:
            continue
        rec = load_json(paths.stage("measure") / f"{w['id']}.json")
        tw = cell_twins[w["id"]]
        p95 = None
        relief_cls = meas.relief_class(rec["features"].get("slope_p95_deg"), flat_below)
        if relief_cls is not None:
            p95 = noise["classes"][relief_cls]["p95"]
        groups = tie_groups([d for d, _ in tw], float(p95)) if p95 is not None else [None] * len(tw)
        twins = []
        for (d, r), g in zip(tw, groups):
            entry = cache["windows"].get(r["id"], {})
            ctx = entry.get("context")
            twins.append({
                "analog_id": r["id"], "D": d, "tie_group": g,
                "analog_place": analog_place(places, r["lat"], r["lon"]),
                "novelty": entry.get("novelty"), "known_region_id": entry.get("known_region_id"),
                "context": ctx,
            })
        cells.append({
            "id": w["id"], "lat": float(w["lat"]), "lon": float(w["lon"]),
            "features": rec["features"], "twins": twins,
            "mission_pct": mission_pcts(paths.root / rec["source_path"], float(w["lat"]), float(w["lon"]), cfg, limits),
        })

    write_json(paths.site_data / "atlas" / "mars_cells.json", cells)
    summary = {
        "stage": "mars_atlas", "created": utc_now(), "windows_listed": len(windows),
        "cells_written": len(cells), "not_measured": n_skipped,
        "twins_per_cell": TWINS, "twin_candidates": len(pool),
        "tie_rule": {"flat_slope_p95_deg": flat_below, "rule": "anchor rule with the p95 of the Mars window's relief class"},
        "mission_limits_mars": None if limits is None else limits.get("mars"),
        "site_file": "site/data/atlas/mars_cells.json",
        "provenance": provenance_block(paths, "cells", []),
    }
    write_json(paths.derived / "atlas" / "mars_run.json", summary)
    log.event("info", "mars atlas written", cells=len(cells))
    return len(cells)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mars atlas: Mars pool measured, top-3 Earth twins, mission %.")
    ap.add_argument("--root", default=None)
    ap.add_argument("--sample", type=int, default=None, help="measure the first N windows only (sample first)")
    ap.add_argument("--rekey", action="store_true", help="only backfill measure_key on existing records, then stop")
    args = ap.parse_args(argv)
    paths = make_paths(args.root, False)
    if args.rekey:
        n = rekey(paths, read_config(paths))
        print(f"rekeyed {n} records")
        return 0
    return 0 if run(paths, args.sample) else 2


if __name__ == "__main__":
    raise SystemExit(main())
