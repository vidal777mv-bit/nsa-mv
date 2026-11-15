"""P-L ledger (STANDARDS 10.14): the facts table, built ONLY from persisted outputs. No hand-entered value.

Writes data/derived/facts/facts.duckdb (table `facts`, plus named aggregate views used by render_facts.py) and
data/derived/facts/facts.parquet (the same table). Sample mode (--sample N) limits Earth pool and Mars windows to N and
writes under data/derived/facts/sample/.

Columns: fact_id, subject_type (target | mars_cell | earth_window | region | body | mission_limit | validation | pair |
experiment),
subject_id, body, property, value_num, value_text, unit, scale_m, footprint (point | local | regional | global),
kind (measured | derived | published), level (observation | interpretation | scenario), source_id, source_url,
verified (bool), produced_by, config_version, comparison (reference | compliance | null), baseline_m.

Honest tagging used here (lead's rule, 10.14):
- our measures (features, twins, D, elevations, coverage shares) = derived, observation, local, 100 m (the grid);
- mission limits and body facts = published (baseline null where the source states none);
- mission % = derived, comparison reference (limit baseline null);
- centres from secondary sources, or flagged NOT CONFIRMED in config/sites.json = verified false;
- validation results = derived, observation; a 'statistically tied' twin = interpretation.
- light (P-S, data/derived/light/light.json): derived, observation, point footprint; the Moon relief fields are local
  (scale = the horizon reach). Skipped with a logged reason when light.json does not exist.
- rehearsal (P-P, data/derived/rehearsal, subject_type 'pair' = '<target>__<analog_id>', the card name without .json):
  'rehearse' lines are derived / interpretation; 'cannot' lines are published (bodies.json) / observation. Each line
  gives <line>_status, _target, _analog (and _ratio, _reason when present).
Subject type 'validation' also carries the config thresholds and the discoveries counts (aggregates about the whole run).
Earth gap (STANDARDS 10.14, read from data/derived/neighbors, the P-N output): property 'earth_gap' on every Mars cell
(mars_cell) and every site (target), value 1 = gap, 0 = twin within sensor noise, null = not evaluable.
Earth grazing maximum (closed form, from the rehearsal low_sun lines): body 'earth', 'earth_grazing_max_pct' and
'earth_grazing_max_abs_lat'.
Earth pool sensors (docs/ARCTIC_INTEGRATION.md): every pool earth_window carries 'sensor' and its elevation 'source_id'
from its own measure record (nasadem, or copdem above 60 N). Each window listed in data/derived/pool_rules/excluded.json
gets one fact 'excluded_rule'. Earth gap under the NASADEM band only: 'earth_gap_nasadem' (neighbors column gap_nasadem,
written when the P-N output has it; without it no such facts are made, and the build logs that).

Usage: .venv/Scripts/python.exe tools/build_ledger.py [--sample N]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import duckdb  # noqa: E402

from _common import load_json, make_paths, place_id, ranking_file, window_records  # noqa: E402
from build_measure import measure_key  # noqa: E402

CONFIG_VERSION = "1.3"
PRODUCED = "tools/build_ledger.py"
FEATURES = ("slope_p95_deg", "hi", "coherence", "hurst", "ridge_pct", "valley_pct")

ARROW_TYPES = {"fact_id": "string", "subject_type": "string", "subject_id": "string", "body": "string",
               "property": "string", "value_num": "float64", "value_text": "string", "unit": "string",
               "scale_m": "float64", "footprint": "string", "kind": "string", "level": "string",
               "source_id": "string", "source_url": "string", "verified": "bool", "produced_by": "string",
               "config_version": "string", "comparison": "string", "baseline_m": "float64"}
COLUMNS = ("fact_id", "subject_type", "subject_id", "body", "property", "value_num", "value_text", "unit", "scale_m",
           "footprint", "kind", "level", "source_id", "source_url", "verified", "produced_by", "config_version",
           "comparison", "baseline_m")


def fact(subject_type: str, subject_id: str, prop: str, value: Any, *, body: str | None = None, unit: str | None = None,
         scale_m: float | None = None, footprint: str | None = None, kind: str | None = None, level: str | None = None,
         source_id: str | None = None, source_url: str | None = None, verified: bool | None = None,
         produced_by: str = PRODUCED, comparison: str | None = None, baseline_m: float | None = None,
         config_version: str = CONFIG_VERSION) -> dict[str, Any]:
    """One fact row. Numbers go to value_num, text and booleans to value_text ('true'/'false' for booleans)."""
    if isinstance(value, bool):
        vnum, vtext = None, "true" if value else "false"
    elif isinstance(value, (int, float)):
        vnum = None if value is None or (isinstance(value, float) and not math.isfinite(value)) else float(value)
        vtext = None
    elif value is None:
        vnum, vtext = None, None
    else:
        vnum, vtext = None, str(value)
    return {"subject_type": subject_type, "subject_id": str(subject_id), "body": body, "property": prop,
            "value_num": vnum, "value_text": vtext, "unit": unit, "scale_m": scale_m, "footprint": footprint,
            "kind": kind, "level": level, "source_id": source_id, "source_url": source_url, "verified": verified,
            "produced_by": produced_by, "config_version": config_version, "comparison": comparison,
            "baseline_m": baseline_m}


def record_config(rec: dict[str, Any]) -> str:
    """The config version a measure record was produced with: its provenance block, else the inferred value written by
    mars_atlas.py --rekey (refined records were produced with the frozen v1.3 config)."""
    return (rec.get("provenance") or {}).get("config_version") or rec.get("config_version_inferred") or CONFIG_VERSION


def measure_facts(rec: dict[str, Any], subject_type: str, subject_id: str, body: str) -> list[dict[str, Any]]:
    """The six features of an ok measure record (derived, observation, local, 100 m grid), with the record's true
    config version and its measure_key (rule R6 compares the key with the current config)."""
    cv = record_config(rec)
    out = []
    if rec.get("measure_key"):
        out.append(fact(subject_type, subject_id, "measure_key", rec["measure_key"], body=body, footprint="local",
                        kind="derived", level="observation", scale_m=100, produced_by="pipelines/build_measure.py",
                        config_version=cv))
    if rec.get("native_res_m") is not None:
        out.append(fact(subject_type, subject_id, "native_res_m", rec["native_res_m"], body=body, unit="m",
                        scale_m=rec["native_res_m"], footprint="local", kind="measured", level="observation",
                        source_id=rec.get("source_id"), produced_by="pipelines/build_measure.py", config_version=cv))
    for name in FEATURES:
        v = (rec.get("features") or {}).get(name)
        if v is None:
            continue
        out.append(fact(subject_type, subject_id, name, v, body=body, unit="deg" if "slope" in name else "fraction"
                        if name in ("hi", "coherence", "hurst") else "percent", scale_m=100, footprint="local",
                        kind="derived", level="observation", source_id=rec.get("source_id"),
                        produced_by="pipelines/build_measure.py", config_version=cv))
    return out


def centre_facts(site: dict[str, Any]) -> list[dict[str, Any]]:
    """Centre and provenance of a target from config/sites.json. Secondary or NOT CONFIRMED centres: verified false."""
    how = (site.get("center_source") or {}).get("how", "")
    url = (site.get("center_source") or {}).get("url")
    verified = not ("SECONDARY" in how or "NOT CONFIRMED" in how)
    base = dict(subject_type="target", subject_id=site["id"], body=site["body"], footprint="point", kind="published",
                level="observation", source_url=url, verified=verified, produced_by="config/sites.json")
    return [fact(prop=p, value=site[k], **base) for p, k in (("centre_lat", "lat"), ("centre_lon", "lon"))] + [
        fact(prop="centre_provenance", value=how[:300], **base)]


def mission_pct_facts(mission: dict[str, Any], subject_type: str, subject_id: str) -> list[dict[str, Any]]:
    """Mission % of a window on its own body's limits (derived; comparison reference: limit baselines are null)."""
    out = []
    for body, kinds in (mission.get("by_body") or {}).items():
        if body != mission.get("body_of_limits", body):
            continue
        for kind in ("landing", "driving"):
            entry = kinds.get(kind) or {}
            if entry.get("pct") is None:
                continue
            out.append(fact(subject_type, subject_id, f"mission_pct_{kind}", entry["pct"], body=body, unit="percent",
                            scale_m=100, footprint="local", kind="derived", level="observation",
                            source_url=entry.get("source"), produced_by="pipelines/mission_pct.py",
                            comparison="reference", baseline_m=None))
    return out


def load_inputs(paths) -> dict[str, Any]:
    """Every persisted input the ledger reads (nothing is typed in)."""
    data = {}
    data["config"] = load_json(paths.config_dir / "measure.json")
    data["sites"] = load_json(paths.config_dir / "sites.json")["sites"]
    data["regions"] = load_json(paths.config_dir / "regions.json")["regions"]
    data["missions"] = load_json(paths.config_dir / "missions.json")
    data["bodies"] = load_json(paths.config_dir / "bodies.json")["bodies"]
    kpath = paths.config_dir / "known_analog_regions.json"
    data["known"] = load_json(kpath)["regions"] if kpath.exists() else []
    data["measures"] = window_records(paths.stage("measure"), status=None)
    data["refined"] = [load_json(p) for p in sorted((paths.derived / "refine" / "measure").glob("*.json"))]
    data["context"] = load_json(paths.derived / "context" / "earth_context.json")["windows"]
    data["atlas"] = load_json(paths.site_data / "atlas" / "mars_cells.json") if (paths.site_data / "atlas" / "mars_cells.json").exists() else []
    data["atlas_run"] = load_json(paths.derived / "atlas" / "mars_run.json") if (paths.derived / "atlas" / "mars_run.json").exists() else None
    data["coverage"] = {b: load_json(paths.site_data / "coverage" / f"{b}.json") for b in ("mars", "moon", "earth")
                        if (paths.site_data / "coverage" / f"{b}.json").exists()}
    data["validation"] = {v: load_json(paths.derived / "validation" / f"{v}.json") for v in ("v1.2", "v1.3")
                          if (paths.derived / "validation" / f"{v}.json").exists()}
    npath = paths.derived / "validation" / "noise_v1.3.json"
    data["noise"] = load_json(npath) if npath.exists() else None
    dpath = paths.site_data / "discoveries.json"
    data["discoveries"] = load_json(dpath) if dpath.exists() else None
    lpath = paths.root / "data" / "derived" / "light" / "light.json"
    data["light"] = load_json(lpath) if lpath.exists() else None
    rdir = paths.root / "data" / "derived" / "rehearsal"
    data["rehearsal"] = [load_json(p) for p in sorted(rdir.glob("*.json")) if p.name != "run_log.jsonl"]         if rdir.is_dir() else []
    ndir = paths.derived / "neighbors"
    data["neighbors_mars"] = _parquet(ndir / "mars_cells.parquet", "id, gap", "id", optional=("gap_nasadem",))
    data["neighbors_targets"] = _parquet(ndir / "targets.parquet", "id, body, gap", "id", optional=("gap_nasadem",))
    data["neighbors_run"] = load_json(ndir / "run.json") if (ndir / "run.json").exists() else None
    xpath = paths.derived / "pool_rules" / "excluded.json"
    data["excluded"] = load_json(xpath) if xpath.exists() else None
    return data


def _parquet(path: Path, cols: str, order: str, optional: tuple[str, ...] = ()) -> list[dict[str, Any]] | None:
    """Rows of a persisted parquet file (a P-N output) as dicts, or None when the file is absent. Columns named in
    `optional` are read only when the file has them (an older P-N output lacks them)."""
    if not path.exists():
        return None
    con = duckdb.connect()
    try:
        have = {d[0] for d in con.execute(f"SELECT * FROM read_parquet('{path.as_posix()}') LIMIT 0").description}
        names = [c.strip() for c in cols.split(",")] + [c for c in optional if c in have]
        rows = con.execute(f"SELECT {', '.join(names)} FROM read_parquet('{path.as_posix()}') ORDER BY {order}").fetchall()
    finally:
        con.close()
    return [dict(zip(names, r)) for r in rows]


def build_rows(paths, data: dict[str, Any], sample: int | None) -> list[dict[str, Any]]:
    """All fact rows, in a fixed order (fact ids are assigned from the position)."""
    rows: list[dict[str, Any]] = []
    cfg = data["config"]
    by_id = {r["id"]: r for r in data["measures"]}

    # --- configuration thresholds and feature weights (validation subject, published)
    cfg_base = dict(subject_type="validation", subject_id="config_v1.3", footprint="global", kind="published",
                    level="observation", source_id="config/measure.json", verified=True, produced_by="config/measure.json")
    for name in FEATURES:
        spec = cfg["features"][name]
        rows.append(fact(prop=f"sigma_{name}", value=spec["sigma"], unit="sigma", **cfg_base))
        rows.append(fact(prop=f"weight_{name}", value=spec["weight"], **cfg_base))
    rows.append(fact(prop="features_in_distance", value=sum(1 for n in FEATURES if cfg["features"][n]["weight"] > 0),
                     **cfg_base))
    rows.append(fact(prop="measure_key", value=measure_key(cfg), **cfg_base))
    rows.append(fact(prop="features_total", value=len(FEATURES), **cfg_base))
    rows.append(fact(prop="min_shared_features", value=cfg["distance"]["min_shared_features"], **cfg_base))
    rows.append(fact(prop="grid_L_m", value=cfg["grid"]["L_m"], unit="m", **cfg_base))
    rows.append(fact(prop="grid_R_m", value=cfg["grid"]["R_m"], unit="m", **cfg_base))
    v = cfg["validation"]
    rows.append(fact(prop="redundancy_max_abs_spearman", value=v["redundancy_max_abs_spearman"], **cfg_base))
    rows.append(fact(prop="auc_min", value=v["auc_min"], **cfg_base))
    rows.append(fact(prop="p_max", value=v["p_max"], **cfg_base))
    rows.append(fact(prop="nn_min_correct_v13", value=v["v13"]["pass"]["nn_against_dev_min_correct"], **cfg_base))
    rows.append(fact(prop="flat_slope_p95_deg", value=v["v13"]["flat_slope_p95_deg"], unit="deg", **cfg_base))
    rows.append(fact(prop="holdout_regions_per_class", value=v["v13"]["holdout_per_class"], **cfg_base))
    rows.append(fact(prop="n_classes", value=len(v["classes"]), **cfg_base))
    lags = cfg["features"]["hurst"]["lags_px"]
    rows.append(fact(prop="hurst_scale_min_m", value=min(lags) * cfg["grid"]["L_m"], unit="m", **cfg_base))
    rows.append(fact(prop="hurst_scale_max_m", value=max(lags) * cfg["grid"]["L_m"], unit="m", **cfg_base))

    # --- bodies (published)
    for body, facts_b in data["bodies"].items():
        base = dict(subject_type="body", subject_id=body, body=body, footprint="global", kind="published",
                    level="observation", source_url=facts_b.get("source_url"), verified=True,
                    produced_by="config/bodies.json")
        for prop in ("gravity_m_s2", "surface_pressure_pa", "temp_min_k", "temp_max_k", "day_length_h"):
            if facts_b.get(prop) is not None:
                rows.append(fact(prop=prop, value=facts_b[prop], **base))

    # --- mission limits (published, baseline null: the source states none)
    for body, kinds in data["missions"]["limits"].items():
        for kind, entry in kinds.items():
            sid = f"{body}_{kind}"
            rows.append(fact("mission_limit", sid, "limit_deg", entry["limit_deg"], body=body, unit="deg",
                             footprint="global", kind="published", level="observation", source_url=entry.get("source_url"),
                             verified=True, produced_by="config/missions.json", baseline_m=None))

    # --- regions: known analog circles (interpretation: a circle approximation) and dev/holdout measures
    for reg in data["known"]:
        base = dict(subject_type="region", subject_id=reg["id"], body=reg.get("body"), footprint="regional",
                    kind="published", level="interpretation", source_url=reg.get("source_url"), verified=True,
                    produced_by="config/known_analog_regions.json")
        rows.append(fact(prop="radius_km", value=reg["radius_km"], unit="km", scale_m=reg["radius_km"] * 1000, **base))
        rows.append(fact(prop="centre_lat_circle", value=reg["lat"], **base))
        rows.append(fact(prop="centre_lon_circle", value=reg["lon"], **base))
    role_of = {r["id"]: r for r in data["regions"]}
    for m in data["measures"]:
        # features come from the NASADEM record only: the Copernicus record is used for the noise thresholds
        if m.get("kind") in ("region", "holdout") and m.get("status") == "ok" and m.get("sensor") == "nasadem":
            rid = m.get("region_id") or m["id"].split("__")[0]
            rows += measure_facts(m, "region", rid, "earth")
            rows.append(fact("region", rid, "role", role_of.get(rid, {}).get("role", m.get("role")), body="earth",
                             footprint="local", kind="published", level="observation", verified=True,
                             produced_by="config/regions.json", scale_m=100))

    # --- targets: centre, landing class, mission, measures, mission %, twins (effective ranking)
    for s in data["sites"]:
        if s.get("role") != "target":
            continue
        tid = s["id"]
        rows += centre_facts(s)
        for prop in ("landing_class", "mission"):
            if s.get(prop):
                rows.append(fact("target", tid, prop, s[prop], body=s["body"], footprint="point", kind="published",
                                 level="observation", verified=True, produced_by="config/sites.json"))
        m = by_id.get(tid)
        if m and m.get("status") == "ok":
            rows += measure_facts(m, "target", tid, s["body"])
        mp = _load_optional(paths, paths.derived / "mission" / f"{tid}.json")
        if mp:
            mp["body_of_limits"] = s["body"]
            rows += mission_pct_facts(mp, "target", tid)
        rp = ranking_file(paths, tid)
        if rp.exists():
            rk = load_json(rp)
            p95 = (rk.get("tie_rule") or {}).get("noise_p95")
            tops = rk.get("ranking", [])[:3]
            for r, row in enumerate(tops, start=1):
                rows.append(fact("target", tid, f"twin{r}_analog_id", row["analog_id"], body=s["body"],
                                 footprint="local", kind="derived", level="observation", scale_m=100,
                                 produced_by="pipelines/search.py" if "rank_before" not in row else "pipelines/refine_search.py"))
                rows.append(fact("target", tid, f"twin{r}_D", row["D"], body=s["body"], footprint="local", kind="derived",
                                 level="observation", scale_m=100, produced_by="pipelines/search.py"))
                rows.append(fact("earth_window", row["analog_id"], f"top3_twin_of__target_{tid}", f"rank {r}",
                                 footprint="local", kind="derived", level="observation", scale_m=100,
                                 produced_by="pipelines/discoveries.py"))
            if len(tops) >= 2 and p95 is not None:
                gap = tops[1]["D"] - tops[0]["D"]
                rows.append(fact("target", tid, "top1_vs_top2_tie", "statistically_tied" if gap < p95 else "distinct",
                                 footprint="local", kind="derived", level="interpretation", scale_m=100,
                                 produced_by="pipelines/search.py"))

    # --- earth windows: the pool (role pool), refined twins (role refined) and the context cache
    pool = [m for m in data["measures"] if m.get("kind") == "pool" and m.get("status") == "ok"]
    if sample:
        pool = pool[:sample]
    for m in pool:
        rows.append(fact("earth_window", m["id"], "role", "pool", footprint="local", kind="derived",
                         level="observation", scale_m=100, produced_by="pipelines/build_measure.py"))
        if m.get("sensor") is not None:  # nasadem (56 S-60 N) or copdem (60 N-84 N), from the measure record
            rows.append(fact("earth_window", m["id"], "sensor", m["sensor"], footprint="local", kind="derived",
                             level="observation", scale_m=100, produced_by="pipelines/build_measure.py"))
        rows.append(fact("earth_window", m["id"], "place_id", place_id(m["id"]), footprint="local", kind="derived",
                         level="observation", produced_by="pipelines/_common.py place_id"))
        rows += measure_facts(m, "earth_window", m["id"], "earth")
    for m in data["refined"]:
        rid = m["id"]
        rows.append(fact("earth_window", rid, "role", "refined", footprint="local", kind="derived",
                         level="observation", scale_m=100, produced_by="pipelines/refine_search.py"))
        rows.append(fact("earth_window", rid, "place_id", place_id(rid), footprint="local", kind="derived",
                         level="observation", produced_by="pipelines/_common.py place_id"))
        rows += measure_facts(m, "earth_window", rid, "earth")
    src_of = {m["id"]: m.get("source_id") for m in [*data["measures"], *data["refined"]]}  # elevation source per window
    for wid, c in data["context"].items():
        ctx = c.get("context") or {}
        base = dict(subject_type="earth_window", subject_id=wid, body="earth")
        if ctx.get("koppen_class"):
            rows.append(fact(prop="koppen_class", value=ctx["koppen_class"], footprint="local", kind="published",
                             level="observation", scale_m=1000, source_url=None, verified=True,
                             produced_by="pipelines/earth_context.py", source_id="koppen_geiger_1km", **base))
            rows.append(fact(prop="koppen_label", value=ctx["koppen_label"], footprint="local", kind="published",
                             level="observation", scale_m=1000, verified=True, produced_by="pipelines/earth_context.py",
                             source_id="koppen_geiger_1km", **base))
        if ctx.get("elevation_m") is not None:
            rows.append(fact(prop="elevation_m", value=ctx["elevation_m"], unit="m", footprint="local", kind="derived",
                             level="observation", scale_m=4000, produced_by="pipelines/earth_context.py",
                             source_id=src_of.get(wid), **base))
        place = c.get("analog_place")
        if place and place.get("name"):
            rows.append(fact(prop="analog_place_name", value=place["name"], footprint="regional", kind="published",
                             level="observation", verified=True, produced_by="pipelines/earth_context.py",
                             source_id="ne_10m_admin_1_states_provinces", **base))
            rows.append(fact(prop="analog_place_match", value=place.get("match"), footprint="regional", kind="derived",
                             level="observation", verified=True, produced_by="pipelines/earth_context.py",
                             source_id="ne_10m_admin_1_states_provinces", **base))
        town = ctx.get("nearest_town")
        if town:
            rows.append(fact(prop="nearest_town_name", value=town["name"], footprint="point", kind="published",
                             level="observation", verified=True, produced_by="pipelines/earth_context.py",
                             source_id="ne_10m_populated_places", **base))
            rows.append(fact(prop="nearest_town_distance_km", value=town["distance_km"], unit="km", footprint="point",
                             kind="derived", level="observation", produced_by="pipelines/earth_context.py", **base))
        if c.get("novelty") is not None:
            rows.append(fact(prop="novelty", value=c["novelty"], footprint="regional", kind="derived",
                             level="interpretation", produced_by="pipelines/earth_context.py", **base))
            if c.get("known_region_id"):
                rows.append(fact(prop="known_region_id", value=c["known_region_id"], footprint="regional",
                                 kind="published", level="interpretation", source_id="known_analog_regions",
                                 produced_by="pipelines/earth_context.py", verified=True, **base))

    # --- Mars pool (mars_cell subjects): measured status for every window, features and mission % for measured ones
    mars = [m for m in data["measures"] if m.get("kind") == "mars_pool"]
    if sample:
        mars = mars[:sample]
    for m in mars:
        rows.append(fact("mars_cell", m["id"], "measure_status", m.get("status"), body="mars", footprint="local",
                         kind="derived", level="observation", scale_m=100, produced_by="pipelines/mars_atlas.py"))
        if m.get("status") == "ok":
            rows += measure_facts(m, "mars_cell", m["id"], "mars")
    for cell in data["atlas"][: sample or None]:
        cid = cell["id"]
        mp = cell.get("mission_pct") or {}
        for kind in ("landing", "driving"):
            entry = mp.get(kind) or {}
            if entry.get("pct") is not None:
                rows.append(fact("mars_cell", cid, f"mission_pct_{kind}", entry["pct"], body="mars", unit="percent",
                                 scale_m=100, footprint="local", kind="derived", level="observation",
                                 source_url=entry.get("source"), produced_by="pipelines/mars_atlas.py",
                                 comparison="reference", baseline_m=None))
        for r, tw in enumerate(cell["twins"], start=1):
            rows.append(fact("mars_cell", cid, f"twin{r}_analog_id", tw["analog_id"], body="mars", footprint="local",
                             kind="derived", level="observation", scale_m=100, produced_by="pipelines/mars_atlas.py"))
            rows.append(fact("mars_cell", cid, f"twin{r}_D", tw["D"], body="mars", footprint="local", kind="derived",
                             level="observation", scale_m=100, produced_by="pipelines/mars_atlas.py"))
            rows.append(fact("earth_window", tw["analog_id"], f"top3_twin_of__mars_cell_{cid}", f"rank {r}",
                             footprint="local", kind="derived", level="observation", scale_m=100,
                             produced_by="pipelines/discoveries.py"))
        if len(cell["twins"]) >= 2 and cell["twins"][0].get("tie_group") is not None:
            tied = cell["twins"][1]["tie_group"] == cell["twins"][0]["tie_group"]
            rows.append(fact("mars_cell", cid, "top1_vs_top2_tie", "statistically_tied" if tied else "distinct",
                             footprint="local", kind="derived", level="interpretation", scale_m=100,
                             produced_by="pipelines/mars_atlas.py"))

    # --- coverage (body subject, derived; class counts per grid)
    for body, cov in data["coverage"].items():
        counts = cov.get("counts") or {}
        for k in ("0", "1", "2"):
            rows.append(fact("body", body, f"cells_class_{k}", counts.get(k), body=body, unit="cells",
                             scale_m=111000, footprint="global", kind="derived", level="observation",
                             produced_by="pipelines/coverage_grids.py", source_url=None, verified=True))
        notes = cov.get("notes") or {}
        rate = notes.get("single_ctx_full_disk_rate")
        if rate:
            rows.append(fact("body", body, "single_ctx_full_disk_rate", rate["value"], body=body, unit="fraction",
                             scale_m=8000, footprint="global", kind="derived", level="observation",
                             produced_by="pipelines/coverage_grids.py", verified=True))
            rows.append(fact("body", body, "single_ctx_full_disk_rate_wilson_lo", rate["wilson95"][0], body=body,
                             unit="fraction", scale_m=8000, footprint="global", kind="derived", level="observation",
                             produced_by="pipelines/coverage_grids.py", verified=True))
            rows.append(fact("body", body, "single_ctx_full_disk_rate_wilson_hi", rate["wilson95"][1], body=body,
                             unit="fraction", scale_m=8000, footprint="global", kind="derived", level="observation",
                             produced_by="pipelines/coverage_grids.py", verified=True))
            rows.append(fact("body", body, "ctx_attempts", rate["attempts"], body=body, unit="attempts",
                             footprint="global", kind="derived", level="observation",
                             produced_by="pipelines/coverage_grids.py", verified=True))
            rows.append(fact("body", body, "ctx_accepted", rate["accepted"], body=body, unit="windows",
                             footprint="global", kind="derived", level="observation",
                             produced_by="pipelines/coverage_grids.py", verified=True))

    # --- atlas run (body mars)
    if data["atlas_run"]:
        ar = data["atlas_run"]
        base = dict(subject_type="body", subject_id="mars", body="mars", footprint="global", kind="derived",
                    level="observation", produced_by="pipelines/mars_atlas.py", verified=True)
        rows.append(fact(prop="mars_windows_listed", value=ar["windows_listed"], unit="windows", **base))
        rows.append(fact(prop="mars_cells_written", value=ar["cells_written"], unit="cells", **base))
        rows.append(fact(prop="mars_windows_not_measured", value=ar["not_measured"], unit="windows", **base))

    # --- validation (derived, observation, regional)
    for vname, vdoc in data["validation"].items():
        base = dict(subject_type="validation", subject_id=vname, footprint="regional", kind="derived",
                    level="observation", scale_m=100, produced_by="pipelines/validate.py", verified=True,
                    source_id=f"validation_{vname}")
        auc = vdoc["AUC"] if vname == "v1.3" else vdoc["V2"]  # v1.2 keeps its discrimination block as V2
        if vname == "v1.3":
            a = auc
            rows.append(fact(prop="auc", value=a["auc"], **base))
            rows.append(fact(prop="auc_ci_lo", value=a["bootstrap"]["ci_lo"], **base))
            rows.append(fact(prop="auc_ci_hi", value=a["bootstrap"]["ci_hi"], **base))
            rows.append(fact(prop="perm_p", value=a["permutation"]["p"], **base))
            rows.append(fact(prop="n_pairs", value=a["n_pairs_total"], **base))
            rows.append(fact(prop="n_same_class_pairs", value=a["n_same_class_pairs"], **base))
            nn = vdoc["NN"]["summary"]
            rows.append(fact(prop="nn_correct", value=nn["k_correct"], **base))
            rows.append(fact(prop="nn_n", value=nn["n_computed"], **base))
            rows.append(fact(prop="nn_chance_count", value=nn["n_computed"] * nn["chance"], **base))
            rows.append(fact(prop="nn_binomial_p", value=nn["binomial_one_sided_p"], **base))
            rows.append(fact(prop="all_pass", value=vdoc["summary"]["all_pass"], **base))
        else:
            rows.append(fact(prop="auc", value=auc["auc"], **base))
            rows.append(fact(prop="auc_ci_lo", value=auc["bootstrap"]["ci_lo"], **base))
            rows.append(fact(prop="auc_ci_hi", value=auc["bootstrap"]["ci_hi"], **base))
            rows.append(fact(prop="perm_p", value=auc["permutation"]["p"], **base))
            rows.append(fact(prop="n_pairs", value=auc["n_pairs_total"], **base))
            rows.append(fact(prop="nn_correct", value=vdoc["V2R"]["k_correct"], **base))
            rows.append(fact(prop="nn_n", value=vdoc["V2R"]["n_computed"], **base))
            rows.append(fact(prop="nn_chance_count", value=vdoc["V2R"]["n_computed"] * 0.2, **base))
            rows.append(fact(prop="nn_binomial_p", value=vdoc["V2R"]["binomial_one_sided_p"], **base))
            rows.append(fact(prop="v0_max_abs_rho", value=max(abs(p["rho"]) for p in vdoc["V0"]["pairs"]), **base))
            rows.append(fact(prop="features_in_distance", value=len(vdoc["V0"]["features"]), **base))
            rows.append(fact(prop="v1_median", value=vdoc["V1"]["median"], **base))
            rows.append(fact(prop="v1_p95", value=vdoc["V1"]["p95"], **base))
            rows.append(fact(prop="all_pass", value=vdoc["summary"]["all_pass"], **base))
    if data["noise"]:
        n = data["noise"]
        for cls in ("rugged", "flat"):
            rows.append(fact("validation", "noise_v1.3", f"tie_p95_{cls}", n["classes"][cls]["p95"], unit="sigma-free D",
                             footprint="regional", kind="derived", level="observation", scale_m=100,
                             produced_by="pipelines/validate.py", verified=True))
            rows.append(fact("validation", "noise_v1.3", f"tie_n_{cls}", n["classes"][cls]["n"], footprint="regional",
                             kind="derived", level="observation", scale_m=100, produced_by="pipelines/validate.py",
                             verified=True))

    # --- discoveries (validation subject: counts over the run)
    if data["discoveries"]:
        c = data["discoveries"]["counts"]
        base = dict(subject_type="validation", subject_id="discoveries", footprint="global", kind="derived",
                    level="interpretation", produced_by="pipelines/discoveries.py", verified=True)
        rows.append(fact(prop="unique_windows", value=c["unique_windows"], **base))
        rows.append(fact(prop="new_windows", value=c["new"], **base))
        rows.append(fact(prop="known_region_windows", value=c["known_region"], **base))
        rows.append(fact(prop="unclassified_windows", value=c["unclassified"], **base))
        rows.append(fact(prop="known_regions_used", value=data["discoveries"]["known_regions"], **base))
        pc = data["discoveries"].get("place_counts")
        if pc:  # by Earth place (discoveries.place_counts); must equal the n_*_places views (checked after the build)
            rows.append(fact(prop="unique_places", value=pc["unique_places"], **base))
            rows.append(fact(prop="new_places", value=pc["new"], **base))
            rows.append(fact(prop="known_region_places", value=pc["known_region"], **base))
            rows.append(fact(prop="mixed_places", value=pc["mixed"], **base))

    rows += light_rows(data)
    rows += rehearsal_rows(data)
    rows += gap_rows(data)
    rows += earth_grazing_rows(data)
    rows += gap_nasadem_rows(data)
    rows += excluded_rows(data)

    for i, r in enumerate(rows, start=1):
        r["fact_id"] = f"F{i:07d}"
    return rows


LIGHT_UNITS = {"noon_sun_max_deg": "deg", "noon_sun_min_deg": "deg", "sun_time_pct": "percent",
               "grazing_pct": "percent", "horizon_max_deg": "deg", "horizon_median_deg": "deg",
               "sun_time_relief_pct": "percent", "horizon_reach_km": "km"}
LIGHT_SUN = ("noon_sun_max_deg", "noon_sun_min_deg", "sun_time_pct", "grazing_pct")
LIGHT_RELIEF = ("horizon_max_deg", "horizon_median_deg", "sun_time_relief_pct", "horizon_reach_km")


def light_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Light facts (P-S): sun geometry of each target and Earth window (point), and the Moon relief fields (local, scale =
    the horizon reach). Skipped with a logged reason when data/derived/light/light.json does not exist."""
    light = data.get("light")
    if light is None:
        print("light facts skipped: data/derived/light/light.json not found (STANDARDS 10.15 P-S not built yet)")
        return []
    body_of = {s["id"]: s["body"] for s in data["sites"]}
    rows: list[dict[str, Any]] = []
    base = dict(footprint="point", kind="derived", level="observation", produced_by="pipelines/light.py")
    for tid, entry in (light.get("targets") or {}).items():
        body = body_of.get(tid)
        for prop in LIGHT_SUN:
            if entry.get(prop) is not None:
                rows.append(fact("target", tid, prop, entry[prop], body=body, unit=LIGHT_UNITS[prop], **base))
        horizon = entry.get("local_horizon") or {}  # P-S1 relief: Moon targets with a LOLA DEM only
        reach = horizon.get("horizon_reach_km")
        for prop in LIGHT_RELIEF:
            if horizon.get(prop) is not None:
                scale = float(reach) * 1000 if reach is not None else None
                rows.append(fact("target", tid, prop, horizon[prop], body=body, unit=LIGHT_UNITS[prop], scale_m=scale,
                                 **{**base, "footprint": "local"}))
    for key, entry in (light.get("earth_windows") or {}).items():
        wid = f"pool__{key}"  # light.json keys are pool index ids; the ledger uses the measure id (pool__pool_NNNNN)
        for prop in LIGHT_SUN:
            if entry.get(prop) is not None:
                rows.append(fact("earth_window", wid, prop, entry[prop], body="earth", unit=LIGHT_UNITS[prop], **base))
    return rows


def rehearsal_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Rehearsal facts (P-P): one set per pair (subject_type 'pair', id = card name without .json) and per line.
    'rehearse' lines are derived / interpretation; 'cannot' lines are published (bodies.json) / observation."""
    body_of = {s["id"]: s["body"] for s in data["sites"]}
    rows: list[dict[str, Any]] = []
    for doc in data.get("rehearsal") or []:
        tid, aid = doc["target_id"], doc["analog_id"]
        pid = f"{tid}__{aid}"
        for ln in doc["lines"]:
            rehearse = ln["group"] == "rehearse"
            if ln["id"] in ("landing", "driving"):
                footprint, scale = "local", 100.0
            elif ln["id"] == "cold":
                footprint, scale = "point", 1000.0
            elif ln["id"] == "low_sun":
                footprint, scale = "point", None
            else:
                footprint, scale = "global", None
            common = dict(subject_type="pair", subject_id=pid, body=body_of.get(tid), footprint=footprint,
                          scale_m=scale, kind="derived" if rehearse else "published",
                          level="interpretation" if rehearse else "observation", source_url=ln.get("source"),
                          verified=ln["status"] is not None, produced_by="pipelines/rehearsal.py", unit=ln.get("unit"))
            prefix = f"rehearsal_{ln['id']}"
            rows.append(fact(prop=f"{prefix}_status", value=ln["status"], **common))
            rows.append(fact(prop=f"{prefix}_target", value=ln["target_value"], **common))
            rows.append(fact(prop=f"{prefix}_analog", value=ln["analog_value"], **common))
            if ln.get("ratio") is not None:
                rows.append(fact(prop=f"{prefix}_ratio", value=ln["ratio"], **common))
            if ln.get("reason"):
                rows.append(fact(prop=f"{prefix}_reason", value=ln["reason"], **common))
    return rows


def _flag(gap: bool | None) -> int | None:
    """Earth gap as a number: 1 = gap, 0 = a twin within sensor noise, None = not evaluable."""
    return None if gap is None else (1 if gap else 0)


def gap_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Earth gap (P-N output, data/derived/neighbors): one flag per Mars cell and per site. The counts must agree with
    run.json (the P-N run record); a disagreement stops the build. Skipped with a logged reason when the P-N files are absent."""
    mars, tgts, run = data.get("neighbors_mars"), data.get("neighbors_targets"), data.get("neighbors_run")
    if mars is None or tgts is None or run is None:
        print("gap facts skipped: data/derived/neighbors not found (P-N not run)")
        return []
    for name, got, key in (("mars_cells", mars, "mars_cells"), ("targets", tgts, "targets")):
        n_gap = sum(1 for r in got if r["gap"])
        n_eval = sum(1 for r in got if r["gap"] is not None)
        want = run[key]
        if (n_gap, n_eval) != (want["gap"], want["n_evaluable"]):
            raise ValueError(f"neighbors {name}.parquet ({n_gap} gap of {n_eval}) disagrees with run.json ({want})")
    rows: list[dict[str, Any]] = []
    for c in mars:
        rows.append(fact("mars_cell", c["id"], "earth_gap", _flag(c["gap"]), body="mars", unit="flag", footprint="local",
                         kind="derived", level="observation", scale_m=100, source_id="neighbors_mars_cells",
                         produced_by="pipelines/neighbors.py", verified=c["gap"] is not None))
    for t in tgts:
        rows.append(fact("target", t["id"], "earth_gap", _flag(t["gap"]), body=t["body"], unit="flag", footprint="local",
                         kind="derived", level="observation", scale_m=100, source_id="neighbors_targets",
                         produced_by="pipelines/neighbors.py", verified=t["gap"] is not None))
    return rows


def earth_grazing_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Earth's maximum grazing share over |lat| 0..90 (closed form, the rehearsal low_sun lines). Every line carries the
    same value; the ledger stops if they differ."""
    lows = [ln for d in (data.get("rehearsal") or []) for ln in d["lines"]
            if ln["id"] == "low_sun" and ln.get("earth_max_grazing_pct") is not None]
    if not lows:
        print("earth grazing facts skipped: no rehearsal low_sun line carries the Earth maximum")
        return []
    pct = {ln["earth_max_grazing_pct"] for ln in lows}
    lat = {ln["earth_max_abs_lat_deg"] for ln in lows}
    if len(pct) != 1 or len(lat) != 1:
        raise ValueError(f"Earth grazing maximum differs across the low_sun lines: {pct} at {lat}")
    base = dict(subject_type="body", subject_id="earth", body="earth", footprint="global", kind="derived",
                level="observation", source_id="config/light.json", produced_by="pipelines/rehearsal.py", verified=True)
    return [fact(prop="earth_grazing_max_pct", value=pct.pop(), unit="percent", **base),
            fact(prop="earth_grazing_max_abs_lat", value=lat.pop(), unit="deg", **base)]


def gap_nasadem_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Earth gap under the NASADEM band only (docs/ARCTIC_INTEGRATION.md, piece 4: neighbors column gap_nasadem). One flag
    per Mars cell and per site, like earth_gap. A P-N output without the column gives no facts for that table (logged)."""
    mars, tgts = data.get("neighbors_mars"), data.get("neighbors_targets")
    if mars is None or tgts is None:
        print("gap_nasadem facts skipped: data/derived/neighbors not found (P-N not run)")
        return []
    present = {name for name, got in (("mars_cells", mars), ("targets", tgts)) if got and "gap_nasadem" in got[0]}
    if present != {"mars_cells", "targets"}:
        print(f"gap_nasadem facts skipped for {sorted({'mars_cells', 'targets'} - present)}: column gap_nasadem is not in "
              "the neighbors parquet (P-N not re-run after the Arctic integration)")
    rows: list[dict[str, Any]] = []
    if "mars_cells" in present:
        for c in mars:
            rows.append(fact("mars_cell", c["id"], "earth_gap_nasadem", _flag(c["gap_nasadem"]), body="mars", unit="flag",
                             footprint="local", kind="derived", level="observation", scale_m=100,
                             source_id="neighbors_mars_cells", produced_by="pipelines/neighbors.py",
                             verified=c["gap_nasadem"] is not None))
    if "targets" in present:
        for t in tgts:
            rows.append(fact("target", t["id"], "earth_gap_nasadem", _flag(t["gap_nasadem"]), body=t["body"], unit="flag",
                             footprint="local", kind="derived", level="observation", scale_m=100,
                             source_id="neighbors_targets", produced_by="pipelines/neighbors.py",
                             verified=t["gap_nasadem"] is not None))
    return rows


def excluded_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Pool windows the pool rules keep out (data/derived/pool_rules/excluded.json, written by pool_rules.py): one fact
    'excluded_rule' per window, its value the rule that excluded it. Accepts a list of entries, a dict {'windows': [...]}
    or a dict keyed by window id; every entry needs 'id' and 'rule'. Skipped with a logged reason when the file is absent."""
    ex = data.get("excluded")
    if ex is None:
        print("excluded facts skipped: data/derived/pool_rules/excluded.json not found")
        return []
    if isinstance(ex, dict) and "windows" in ex:
        ex = ex["windows"]
    items = [{"id": k, **v} for k, v in ex.items()] if isinstance(ex, dict) else list(ex)
    rows: list[dict[str, Any]] = []
    for e in items:
        if not e.get("rule"):
            raise ValueError(f"excluded window {e.get('id')!r} has no rule in data/derived/pool_rules/excluded.json")
        wid = e["id"] if str(e["id"]).startswith("pool__") else f"pool__{e['id']}"  # the measure id of a pool window
        rows.append(fact("earth_window", wid, "excluded_rule", e["rule"], body="earth", footprint="local", kind="derived",
                         level="observation", scale_m=100, produced_by="pipelines/pool_rules.py"))
    return rows


def _load_optional(paths, p: Path) -> dict[str, Any] | None:
    """A persisted per-window JSON that may be absent (no mission file for that window yet)."""
    return load_json(p) if p.exists() else None


_PLACES = """WITH tw AS (SELECT DISTINCT subject_id FROM facts WHERE subject_type='earth_window' AND starts_with(property, 'top3_twin_of__')),
     pl AS (SELECT p.value_text AS place, n.value_text AS novelty FROM tw
            JOIN facts p ON p.subject_id = tw.subject_id AND p.property = 'place_id'
            LEFT JOIN facts n ON n.subject_id = tw.subject_id AND n.property = 'novelty'),
     g AS (SELECT place, count(DISTINCT novelty) AS k, min(novelty) AS nov FROM pl GROUP BY place)
   SELECT count(*) AS value FROM g WHERE {where}"""

VIEWS = {
    "n_targets": "SELECT count(DISTINCT subject_id) AS value FROM facts WHERE subject_type='target' AND property='centre_lat'",
    "n_targets_mars": "SELECT count(DISTINCT subject_id) AS value FROM facts WHERE subject_type='target' AND property='centre_lat' AND body='mars'",
    "n_targets_moon": "SELECT count(DISTINCT subject_id) AS value FROM facts WHERE subject_type='target' AND property='centre_lat' AND body='moon'",
    "n_moon_candidates": "SELECT count(DISTINCT subject_id) AS value FROM facts WHERE subject_type='target' AND property='landing_class' AND body='moon' AND value_text='candidate'",
    "n_pool_windows": "SELECT count(DISTINCT subject_id) AS value FROM facts WHERE subject_type='earth_window' AND property='role' AND value_text='pool'",
    "n_mars_windows": "SELECT count(DISTINCT subject_id) AS value FROM facts WHERE subject_type='mars_cell' AND property='measure_status'",
    "n_mars_cells": "SELECT count(DISTINCT subject_id) AS value FROM facts WHERE subject_type='mars_cell' AND property='measure_status' AND value_text='ok'",
    "n_discovery_windows": "SELECT count(DISTINCT subject_id) AS value FROM facts WHERE subject_type='earth_window' AND starts_with(property, 'top3_twin_of__')",
    "n_new_twins": "SELECT count(DISTINCT f.subject_id) AS value FROM facts f JOIN facts n ON n.subject_id=f.subject_id AND n.property='novelty' AND n.value_text='new' WHERE f.subject_type='earth_window' AND starts_with(f.property, 'top3_twin_of__')",
    "n_known_twins": "SELECT count(DISTINCT f.subject_id) AS value FROM facts f JOIN facts n ON n.subject_id=f.subject_id AND n.property='novelty' AND n.value_text='known_region' WHERE f.subject_type='earth_window' AND starts_with(f.property, 'top3_twin_of__')",
    # By Earth PLACE (pipelines/_common.place_id): one place that is a twin of several sites or cells counts once; a
    # place whose windows differ in novelty is neither new nor known. These are the public figures.
    "n_discovery_places": _PLACES.format(where="TRUE"),
    "n_new_places": _PLACES.format(where="k = 1 AND nov = 'new'"),
    "n_known_places": _PLACES.format(where="k = 1 AND nov = 'known_region'"),
    "n_mixed_places": _PLACES.format(where="k > 1"),
    "n_twin_windows_without_place": "SELECT count(DISTINCT f.subject_id) AS value FROM facts f LEFT JOIN facts p ON p.subject_id=f.subject_id AND p.property='place_id' WHERE f.subject_type='earth_window' AND starts_with(f.property, 'top3_twin_of__') AND p.subject_id IS NULL",
    "n_known_regions": "SELECT count(DISTINCT subject_id) AS value FROM facts WHERE subject_type='region' AND property='radius_km'",
    "n_features_in_distance": "SELECT value_num AS value FROM facts WHERE subject_type='validation' AND subject_id='config_v1.3' AND property='features_in_distance'",
    "n_features_total": "SELECT value_num AS value FROM facts WHERE subject_type='validation' AND subject_id='config_v1.3' AND property='features_total'",
    "auc_v12": "SELECT value_num AS value FROM facts WHERE subject_type='validation' AND subject_id='v1.2' AND property='auc'",
    "auc_v13": "SELECT value_num AS value FROM facts WHERE subject_type='validation' AND subject_id='v1.3' AND property='auc'",
    "mars_single_ctx_rate": "SELECT value_num AS value FROM facts WHERE subject_type='body' AND subject_id='mars' AND property='single_ctx_full_disk_rate'",
    "n_holdout_regions": "SELECT count(DISTINCT subject_id) AS value FROM facts WHERE subject_type='region' AND property='role' AND value_text='holdout_v13'",
    "n_flat_noise_regions": "SELECT value_num AS value FROM facts WHERE subject_type='validation' AND subject_id='noise_v1.3' AND property='tie_n_flat'",
    "n_features_v12": "SELECT value_num AS value FROM facts WHERE subject_type='validation' AND subject_id='v1.2' AND property='features_in_distance'",
    "window_diameter_km": "SELECT 2 * value_num / 1000 AS value FROM facts WHERE subject_type='validation' AND subject_id='config_v1.3' AND property='grid_R_m'",
    "n_mars_cells_skipped": "SELECT value_num AS value FROM facts WHERE subject_type='body' AND subject_id='mars' AND property='mars_windows_not_measured'",
}


WILSON_Z = 1.959964  # Wilson 95 % (the same interval as the P-N run record)
REHEARSAL_LINES = ("landing", "driving", "cold", "low_sun", "gravity", "pressure", "temperature", "day_length")
REHEARSAL_STATUSES = ("yes", "partial", "no")

_WILSON = """WITH w AS (SELECT CAST((SELECT value FROM mars_gap_cells) AS DOUBLE) / (SELECT value FROM mars_cells_measured) AS p,
                  CAST((SELECT value FROM mars_cells_measured) AS DOUBLE) AS n),
     c AS (SELECT (p + {z2} / (2 * n)) / (1 + {z2} / n) AS centre,
                  {z} * sqrt(p * (1 - p) / n + {z2} / (4 * n * n)) / (1 + {z2} / n) AS half FROM w)
   SELECT 100.0 * (centre {sign} half) AS value FROM c"""

# Named aggregates (STANDARDS 10.14, P-G). Each returns one row and one value. Order matters: views are created in this
# order, so a view can use the ones defined before it.
GAP_VIEWS = {
    "mars_gap_cells": "SELECT count(*) AS value FROM facts WHERE subject_type='mars_cell' AND property='earth_gap' AND value_num = 1",
    "mars_cells_measured": "SELECT count(value_num) AS value FROM facts WHERE subject_type='mars_cell' AND property='earth_gap'",
    "mars_gap_pct": "SELECT 100.0 * (SELECT value FROM mars_gap_cells) / (SELECT value FROM mars_cells_measured) AS value",
    "mars_rehearsable_pct": "SELECT 100.0 - (SELECT value FROM mars_gap_pct) AS value",
    "mars_gap_wilson_lo": _WILSON.format(z=WILSON_Z, z2=WILSON_Z * WILSON_Z, sign="-"),
    "mars_gap_wilson_hi": _WILSON.format(z=WILSON_Z, z2=WILSON_Z * WILSON_Z, sign="+"),
    "gap_targets": "SELECT count(*) AS value FROM facts WHERE subject_type='target' AND property='earth_gap' AND value_num = 1",
    "mars_gap_targets": "SELECT count(*) AS value FROM facts WHERE subject_type='target' AND property='earth_gap' AND value_num = 1 AND body='mars'",
    "moon_gap_targets": "SELECT count(*) AS value FROM facts WHERE subject_type='target' AND property='earth_gap' AND value_num = 1 AND body='moon'",
    "moon_targets_total": "SELECT count(value_num) AS value FROM facts WHERE subject_type='target' AND property='earth_gap' AND body='moon'",
    "moon_horizon_targets": "SELECT count(DISTINCT subject_id) AS value FROM facts WHERE subject_type='target' AND property='horizon_max_deg'",
    "earth_grazing_max_pct": "SELECT value_num AS value FROM facts WHERE subject_type='body' AND subject_id='earth' AND property='earth_grazing_max_pct'",
    "earth_grazing_max_abs_lat": "SELECT value_num AS value FROM facts WHERE subject_type='body' AND subject_id='earth' AND property='earth_grazing_max_abs_lat'",
    "rehearsal_pairs": "SELECT count(DISTINCT subject_id) AS value FROM facts WHERE subject_type='pair' AND property='rehearsal_landing_status'",
}
for _line in REHEARSAL_LINES:
    for _status in REHEARSAL_STATUSES:
        GAP_VIEWS[f"rehearsal_{_line}_{_status}"] = (
            f"SELECT count(*) AS value FROM facts WHERE subject_type='pair' AND property='rehearsal_{_line}_status' "
            f"AND value_text='{_status}'")
VIEWS.update(GAP_VIEWS)

# Pool by sensor, exclusions, and the Earth gap under the NASADEM band only (docs/ARCTIC_INTEGRATION.md, piece 5). Only
# pool windows with status ok carry a 'role' fact, so a count of role pool is a count of ok windows.
_POOL_BY_SENSOR = ("SELECT count(DISTINCT r.subject_id) AS value FROM facts r JOIN facts s ON s.subject_id = r.subject_id "
                   "AND s.subject_type = 'earth_window' AND s.property = 'sensor' AND s.value_text = '{sensor}' "
                   "WHERE r.subject_type = 'earth_window' AND r.property = 'role' AND r.value_text = 'pool'")
NASADEM_VIEWS = {
    "n_pool_windows_nasadem": _POOL_BY_SENSOR.format(sensor="nasadem"),
    "n_pool_windows_arctic": _POOL_BY_SENSOR.format(sensor="copdem"),
    "n_pool_excluded": "SELECT count(DISTINCT subject_id) AS value FROM facts WHERE subject_type='earth_window' AND property='excluded_rule'",
    "mars_gap_cells_nasadem": "SELECT count(*) AS value FROM facts WHERE subject_type='mars_cell' AND property='earth_gap_nasadem' AND value_num = 1",
    "mars_gap_pct_nasadem": ("SELECT 100.0 * (SELECT value FROM mars_gap_cells_nasadem) / "
                             "(SELECT count(value_num) FROM facts WHERE subject_type='mars_cell' AND property='earth_gap_nasadem') AS value"),
    "mars_rehearsable_pct_nasadem": "SELECT 100.0 - (SELECT value FROM mars_gap_pct_nasadem) AS value",
    "moon_gap_targets_nasadem": "SELECT count(*) AS value FROM facts WHERE subject_type='target' AND property='earth_gap_nasadem' AND value_num = 1 AND body='moon'",
}
VIEWS.update(NASADEM_VIEWS)


def write_ledger(out_dir: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Write facts.duckdb (table + views) and facts.parquet. Replaces the previous files of this run."""
    out_dir.mkdir(parents=True, exist_ok=True)
    db = out_dir / "facts.duckdb"
    if db.exists():
        db.unlink()
    con = duckdb.connect(str(db))
    con.execute("""CREATE TABLE facts (fact_id VARCHAR, subject_type VARCHAR, subject_id VARCHAR, body VARCHAR,
                   property VARCHAR, value_num DOUBLE, value_text VARCHAR, unit VARCHAR, scale_m DOUBLE,
                   footprint VARCHAR, kind VARCHAR, level VARCHAR, source_id VARCHAR, source_url VARCHAR,
                   verified BOOLEAN, produced_by VARCHAR, config_version VARCHAR, comparison VARCHAR,
                   baseline_m DOUBLE)""")
    import pyarrow as pa

    table = pa.table({c: pa.array([r[c] for r in rows], type=ARROW_TYPES[c]) for c in COLUMNS})
    con.register("facts_arrow", table)
    con.execute("INSERT INTO facts SELECT * FROM facts_arrow")
    con.unregister("facts_arrow")
    for name, sql in VIEWS.items():
        con.execute(f"CREATE VIEW {name} AS {sql}")
    parquet = out_dir / "facts.parquet"
    con.execute(f"COPY facts TO '{parquet.as_posix()}' (FORMAT PARQUET)")
    summary = {r[0]: r[1] for r in con.execute(
        "SELECT subject_type || '/' || kind || '/' || level AS k, count(*) FROM facts GROUP BY 1 ORDER BY 1").fetchall()}
    con.close()
    return {"db": db, "parquet": parquet, "rows": len(rows), "by_group": summary}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the facts ledger (STANDARDS 10.14, P-L).")
    ap.add_argument("--root", default=None)
    ap.add_argument("--sample", type=int, default=None, help="limit Earth pool and Mars windows to N (sample first)")
    args = ap.parse_args(argv)
    paths = make_paths(args.root, False)
    data = load_inputs(paths)
    rows = build_rows(paths, data, args.sample)
    out = paths.derived / "facts" / ("sample" if args.sample else "")
    res = write_ledger(out, rows)
    print(json.dumps({"rows": res["rows"], "db": str(res["db"]), "groups": res["by_group"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
