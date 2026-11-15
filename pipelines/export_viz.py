"""P7 export_viz: terrain folders, cards, rankings and index files for the site (STANDARDS 10.5 and 10.6).

Terrain (site/data/terrain/<id>/), common grid L = 30 m, R = 4000 m, n = 269 (same AEQD rules as section 3):
- height.bin: Float32 little-endian, row-major north-up, n*n values, metres relative to the disk mean, NaN outside.
- layers_<body>.bin: Uint8 n*n, bit0 slope > landing limit, bit1 slope > driving limit, bit2 ridge, bit3 valley, of
  <body> (the limits of that body). Slope and TPI are measured on the 100 m grid and nearest-neighbour upsampled to
  30 m, so the layers show exactly what was measured. A target has its own body's layer file; an Earth analog has one
  file per target body that ranks it (an analog has no mission body of its own). Layers are not written when the
  body's limits are missing (meta.json says why).
- hillshade.png: 8-bit grey, sun azimuth 315 deg, altitude 45 deg, the same for every terrain, computed on
  VE x height.
- meta.json: id, body, name, lat, lon, n, L, R, z_min, z_max (display heights), source_id, layers, provenance.

Vertical exaggeration: ONE value for the whole site, in viz.json (rule in viz.vertical_exaggeration): the roughest
terrain (largest P99 - P1 relief of its 30 m disk) is shown with a relief of 20% of the disk diameter 2R, VE rounded
down to 0.1. Heights are written unexaggerated; VE is applied only to the hillshade and must be applied by the viewer.

Cards (data/derived/cards/<target>__<analog>.json, copied to site/data/cards/): contract of STANDARDS 10.5.
z_diff = (analog - target) / sigma; similar if |z_diff| <= 1. rotation_deg: viz.rotation_alignment, the analog shown
rotated counter-clockwise by rotation_deg on a north-up map matches the target (features do not depend on it).

Site index: site/data/targets.json, site/data/rankings/<target>.json, site/data/viz.json.
Mars-first additions (STANDARDS 10.9): each targets.json entry carries landing_class, mission, year, outcome_note and
center_note, copied from config/sites.json (null when a field is absent there), and unlocked, computed here: true when
the target was measured on a DEM with native resolution <= 50 m (never read from sites.json). Also written:
site/data/bodies.json (config/bodies.json bodies), site/data/missions.json (config/missions.json limits and entries with
their sources) and site/data/validation.json: the v1.2 result (failed, all numbers, kept) and the v1.3 holdout result
(or {"status": "pending"}), plus the v1.3 dev noise thresholds of the tie rule.
Per STANDARDS 10.8 the L >= 2 x native rule does NOT apply to the 30 m visual grid (display only; the measurement stays on
the 100 m grid). A terrain whose 30 m disk coverage is below 0.9, or that cannot be read, is skipped and logged.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    Paths,
    RunLog,
    ids_arg,
    features_in_distance,
    limit_for,
    load_json,
    make_paths,
    missions_limits,
    parse_args,
    provenance_block,
    ranking_file,
    read_config,
    select_ids,
    sites_list,
    noise_file_name,
    analog_place,
    load_places,
    validation_file_name,
    window_record_path,
    write_json,
)
from analog import grid as gridmod  # noqa: E402
from analog import viz  # noqa: E402
from analog.core import measure as meas  # noqa: E402

VIZ_L = 30.0
VIZ_R = 4000.0


@dataclass
class Terrain:
    """One exported terrain (target or analog) with everything the writers need."""

    id: str
    kind: str
    body: str
    name: str
    lat: float
    lon: float
    source_id: str
    raw_rel: str
    layer_bodies: set[str] = field(default_factory=set)
    height: np.ndarray | None = None
    mask: np.ndarray | None = None
    native_res_m: float | None = None
    coverage: float | None = None
    relief: float | None = None
    status: str = "pending"
    reason: str | None = None


def load_terrains(paths: Paths, targets: list[dict[str, Any]], rankings: dict[str, dict[str, Any]], log: RunLog) -> dict[str, Terrain]:
    """Terrain specs for the targets in scope and the analogs ranked for them (measure record must be ok)."""
    terrains: dict[str, Terrain] = {}

    def spec(wid: str, kind: str, layer_body: str) -> Terrain | None:
        rp = window_record_path(paths, wid)
        if not rp.exists():
            log.event("warn", "no measure record, terrain skipped", id=wid)
            return None
        rec = load_json(rp)
        if rec.get("status") != "ok":
            log.event("warn", "window not valid, terrain skipped", id=wid, status=rec.get("status"), reason=rec.get("reason"))
            return None
        if wid not in terrains:
            terrains[wid] = Terrain(id=wid, kind=kind, body=rec["body"], name=rec.get("name") or wid, lat=rec["lat"],
                                    lon=rec["lon"], source_id=rec["source_id"], raw_rel=rec["source_path"])
        terrains[wid].layer_bodies.add(layer_body)
        return terrains[wid]

    for t in targets:
        spec(t["id"], "target", t["body"])
    for tid, rk in rankings.items():
        if tid not in {t["id"] for t in targets}:
            continue
        for row in rk.get("ranking", []):
            spec(row["analog_id"], "analog", targets_body(targets, tid))
    return terrains


def targets_body(targets: list[dict[str, Any]], tid: str) -> str:
    """Body of a target id."""
    return next(t["body"] for t in targets if t["id"] == tid)


def build_height(paths: Paths, t: Terrain, cfg: dict[str, Any], log: RunLog) -> None:
    """Load the 30 m grid, check validity (STANDARDS 3) and compute the display heights and relief."""
    raw = paths.root / t.raw_rel
    try:
        z, mask, meta = gridmod.load_local_grid(raw, t.lat, t.lon, t.body, VIZ_L, VIZ_R)
    except Exception as exc:
        t.status, t.reason = "error", f"{type(exc).__name__}: {exc}"
        log.event("error", "30 m grid failed", id=t.id, reason=t.reason)
        return
    t.native_res_m, t.coverage = float(meta["native_res_m"]), float(meta["coverage"])
    if t.coverage < float(cfg["grid"]["min_coverage"]):
        t.status, t.reason = "skipped", f"coverage {t.coverage:.4f} < {cfg['grid']['min_coverage']}"
        log.event("warn", "terrain skipped (coverage)", id=t.id, reason=t.reason)
        return
    t.mask = mask
    t.height = viz.relative_height(z, mask)
    t.relief = viz.relief_m(t.height)
    t.status = "ok"


def layers_for(paths: Paths, t: Terrain, cfg: dict[str, Any], limits: dict[str, Any] | None,
               log: RunLog) -> dict[str, np.ndarray | str]:
    """Layer files per body: {body: bytes} or {body: reason}. Uses the 100 m grid (measurement) and upsamples."""
    out: dict[str, np.ndarray | str] = {}
    L100 = float(cfg["grid"]["L_m"])
    R = float(cfg["grid"]["R_m"])
    tpi = cfg["tpi"]
    for body in sorted(t.layer_bodies):
        landing, _, why_l = limit_for(limits, body, "landing")
        driving, _, why_d = limit_for(limits, body, "driving")
        if landing is None or driving is None:
            out[body] = f"not written: {why_l or why_d}"
            log.event("warn", "layers not written (limits missing)", id=t.id, body=body, reason=out[body])
            continue
        z100, mask100, _ = gridmod.load_local_grid(paths.root / t.raw_rel, t.lat, t.lon, t.body, L100, R)
        bits100 = viz.bits_100m(z100, mask100, L100, int(tpi["radius_px"]), float(tpi["threshold_deg"]), landing, driving)
        bits30 = viz.nearest_upsample(bits100, L100, VIZ_L, viz.grid_size(VIZ_R, VIZ_L))
        bits30 = np.where(t.mask, bits30, 0).astype(np.uint8)
        out[body] = bits30
    return out


def write_terrain(site: Path, t: Terrain, ve: float, layers: dict[str, Any], paths: Paths, cfg: dict[str, Any]) -> dict[str, Any]:
    """Write one terrain folder and return its meta dict."""
    folder = site / "terrain" / t.id
    folder.mkdir(parents=True, exist_ok=True)
    n = t.height.shape[0]
    h32 = np.where(t.mask, t.height, np.nan).astype("<f4")
    (folder / "height.bin").write_bytes(h32.tobytes(order="C"))
    shade = viz.hillshade(t.height, t.mask, VIZ_L, viz.HILLSHADE_AZIMUTH_DEG, viz.HILLSHADE_ALTITUDE_DEG, ve)
    (folder / "hillshade.png").write_bytes(viz.encode_png_gray(viz.to_uint8(shade, fill=0)))
    layer_status: dict[str, Any] = {}
    for body, value in layers.items():
        if isinstance(value, str):
            layer_status[body] = value
            continue
        fname = f"layers_{body}.bin"
        (folder / fname).write_bytes(value.astype(np.uint8).tobytes(order="C"))
        layer_status[body] = fname
    raw_inputs = [(t.source_id, paths.root / t.raw_rel)]
    finite = t.height[np.isfinite(t.height)]
    meta = {
        "id": t.id,
        "kind": t.kind,
        "body": t.body,
        "name": t.name,
        "lat": t.lat,
        "lon": t.lon,
        "n": n,
        "L": VIZ_L,
        "R": VIZ_R,
        "native_res_m": t.native_res_m,
        "z_min": float(finite.min()),
        "z_max": float(finite.max()),
        "relief_p99_p1_m": t.relief,
        "vertical_exaggeration": ve,
        "source_id": t.source_id,
        "layers": layer_status,
        "files": {"height": "height.bin", "hillshade": "hillshade.png", **{k: v for k, v in layer_status.items() if not isinstance(v, str)}},
        "provenance": provenance_block(paths, "cards", raw_inputs),
    }
    write_json(folder / "meta.json", meta)
    return meta


def mission_pct(paths: Paths, wid: str, body: str, kind: str) -> dict[str, Any] | None:
    """Mission file values for a window and body (pct and the limit used). None when the file is missing."""
    mp = paths.stage("mission") / f"{wid}.json"
    if not mp.exists():
        return None
    rec = load_json(mp)
    if rec.get("status") != "ok":
        return None
    entry = rec["by_body"][body][kind]
    return {"pct": entry["pct"], "limit_deg": entry["limit_deg"], "source": entry["source"],
            "reason": entry["reason"] or entry["limit_reason"]}


def build_card(paths: Paths, cfg: dict[str, Any], target: Terrain, analog: Terrain, row: dict[str, Any],
               rotation: float | None, rot_rms: float | None, ve: float, place: dict[str, Any] | None) -> dict[str, Any]:
    """Card of one target-analog pair (STANDARDS 10.5 and 10.12).

    in_distance = features with weight > 0 (they make D); context_features = the others (shown, not scored).
    similar / different use in_distance only; context_similar / context_different use the context features.
    vertical_exaggeration: the pair's value (viz.pair_exaggeration), applied to both terrains of the pair.
    """
    tm = load_json(paths.stage("measure") / f"{target.id}.json")
    am = load_json(window_record_path(paths, analog.id))
    sigmas = {k: cfg["features"][k]["sigma"] for k in meas.FEATURE_IDS}
    in_dist = features_in_distance(cfg)
    context = [k for k in meas.FEATURE_IDS if k not in in_dist]
    features: dict[str, Any] = {}
    similar, different, c_similar, c_different = [], [], [], []
    for k in meas.FEATURE_IDS:
        tv, av = tm["features"].get(k), am["features"].get(k)
        z = None if tv is None or av is None else (float(av) - float(tv)) / float(sigmas[k])
        features[k] = {"target": tv, "analog": av, "z_diff": z}
        if z is None:
            continue
        if k in in_dist:
            (similar if abs(z) <= 1.0 else different).append(k)
        else:
            (c_similar if abs(z) <= 1.0 else c_different).append(k)
    mission_block: dict[str, Any] = {}
    for kind in ("landing", "driving"):
        mt = mission_pct(paths, target.id, target.body, kind)
        ma = mission_pct(paths, analog.id, target.body, kind)
        mission_block[kind] = {
            "target": None if mt is None else mt["pct"],
            "analog": None if ma is None else ma["pct"],
            "limit_deg": None if mt is None else mt["limit_deg"],
            "source": None if mt is None else mt["source"],
            "reason": None if mt is not None and mt["pct"] is not None else (mt or {}).get("reason", "mission file missing"),
        }
    return {
        "target_id": target.id,
        "analog_id": analog.id,
        "rank": row["rank"],
        "D": row["D"],
        "tie_group": row["tie_group"],
        "features": features,
        "vertical_exaggeration": ve,
        "in_distance": in_dist,
        "context_features": context,
        "similar": similar,
        "different": different,
        "context_similar": c_similar,
        "context_different": c_different,
        "analog_place": place,
        "mission_pct": mission_block,
        "mission_baseline_m": cfg["grid"]["L_m"],
        "rotation_deg": rotation,
        "rotation_rms": rot_rms,
        "files": {"target": f"terrain/{target.id}/", "analog": f"terrain/{analog.id}/"},
        "provenance": provenance_block(paths, "cards", [(target.source_id, paths.root / target.raw_rel),
                                                       (analog.source_id, paths.root / analog.raw_rel)]),
    }


SITE_FIELDS = ("landing_class", "mission", "year", "outcome_note", "center_note")  # STANDARDS 10.9, from sites.json
UNLOCK_MAX_NATIVE_M = 50.0  # STANDARDS 10.9: unlocked = a DEM of native resolution <= 50 m exists and the target was measured


def site_fields(site_rec: dict[str, Any] | None) -> dict[str, Any]:
    """The 10.9 text fields of a target as written in config/sites.json; null for any field that is absent there."""
    rec = site_rec or {}
    return {k: rec.get(k) for k in SITE_FIELDS}


def is_unlocked(t: Terrain) -> bool:
    """unlocked (STANDARDS 10.9): the target was measured (its terrain is ok) on a DEM with native resolution <= 50 m.
    Computed from the measurement, never copied from config/sites.json."""
    return bool(t.status == "ok" and t.native_res_m is not None and t.native_res_m <= UNLOCK_MAX_NATIVE_M)


V12_DIAGNOSIS = (
    "The V1 sensor-noise p95 (1.20) is driven by three flat plains (tenere_plain D 1.34, ustyurt_plateau 1.14, "
    "nullarbor_plain 0.65). Single-feature AUC on the same dev pairs (|diff| / sigma, computed 2026-11-14): coherence "
    "0.50 (no class information), hurst 0.82 (the strongest single feature), slope_p95 0.68, hi 0.60. The measure "
    "captures operability (how the surface behaves: slope, roughness texture) more than landform origin, which is why "
    "the landform classes are only partly recovered. This text is an interpretation; the numbers are in the v1.2 block.")
VALIDATION_VERSIONS = ("1.2", "1.3")  # site/data/validation.json shows both: v1.2 (failed, kept) and v1.3


def validation_block(paths: Paths, version: str) -> tuple[dict[str, Any], Path | None]:
    """Summary of data/derived/validation/v<version>.json with every number and status passed | failed. When the file
    does not exist: {"status": "pending"} for the current design (v1.3) and {"status": "not run"} otherwise.
    Returns (doc, source file or None)."""
    vpath = paths.stage("validation") / validation_file_name(version)
    if not vpath.exists():
        return {"status": "pending" if version == "1.3" else "not run"}, None
    v = load_json(vpath)
    doc = {k: val for k, val in v.items() if k != "provenance"}
    doc["status"] = "passed" if (v.get("summary") or {}).get("all_pass") else "failed"
    doc["file"] = paths.rel(vpath)
    if version == "1.2":
        doc["diagnosis"] = V12_DIAGNOSIS
    return doc, vpath


def noise_block(paths: Paths, version: str) -> dict[str, Any]:
    """Dev sensor-noise thresholds of the tie rule (noise_v<version>.json), or {"status": "not run"}."""
    npath = paths.stage("validation") / noise_file_name(version)
    if not npath.exists():
        return {"status": "not run"}
    n = load_json(npath)
    return {"status": "written", "file": paths.rel(npath), "flat_slope_p95_deg": n.get("flat_slope_p95_deg"),
            "rule": n.get("rule"), "n_expected": n.get("n_expected"), "n_used": n.get("n_used"),
            "classes": n.get("classes")}


def write_reference_files(paths: Paths, site: Path, log: RunLog) -> None:
    """site/data/bodies.json, missions.json and validation.json (STANDARDS 10.9). A missing config file gives null and a
    logged reason, never an invented value."""
    for name, src_name, key in (("bodies.json", "bodies.json", "bodies"),
                                ("missions.json", "missions.json", None)):
        src = paths.config_dir / src_name
        if not src.exists():
            log.event("warn", f"config/{src_name} not found: {name} written with null", file=name)
            doc: dict[str, Any] = {"source": paths.rel(src), "reason": f"config/{src_name} not found"}
            doc.update({"bodies": None} if key else {"limits": None, "entries": None, "not_found": None})
            inputs: list[tuple[str, Path]] = []
        else:
            data = load_json(src)
            doc = {"source": paths.rel(src), "reason": None}
            if key:
                doc[key] = data.get(key)
            else:
                doc.update({"limits": data.get("limits"), "entries": data.get("entries"),
                            "not_found": data.get("not_found")})
            inputs = [(f"config_{src_name.split('.')[0]}", src)]
        doc["provenance"] = provenance_block(paths, "cards", inputs)
        write_json(site / name, doc)

    vdoc: dict[str, Any] = {}
    inputs: list[tuple[str, Path]] = []
    for version in VALIDATION_VERSIONS:
        block, vpath = validation_block(paths, version)
        vdoc[f"v{version}"] = block
        if vpath is not None:
            inputs.append((f"validation_v{version}", vpath))
    vdoc["v1.3_noise"] = noise_block(paths, "1.3")
    vdoc["provenance"] = provenance_block(paths, "cards", inputs)
    write_json(site / "validation.json", vdoc)
    log.event("info", "reference files written", v12=vdoc["v1.2"]["status"], v13=vdoc["v1.3"]["status"])


def refined_info(row: dict[str, Any]) -> dict[str, Any] | None:
    """The refined-search fields of a ranking row (STANDARDS 10.13), or None for a frozen-search row."""
    keys = ("pool_id", "rank_before", "D_before", "D_clip_offset0", "refined_offset_km")
    return {k: row[k] for k in keys if k in row} or None


def run(paths: Paths, ids: list[str] | None) -> int:
    """Export terrains, cards and index files. Returns 0 (1 when no terrain could be exported)."""
    cfg = read_config(paths)
    log = RunLog(paths.stage("cards"), "export_viz")
    limits, why = missions_limits(paths)
    if limits is None:
        log.event("warn", "missions limits missing: layers not written", reason=why)
    places_index = load_places(paths, log)
    site = paths.site_data
    write_reference_files(paths, site, log)
    all_sites = sites_list(paths)
    sites_by_id = {s["id"]: s for s in all_sites}
    targets = [t for t in select_ids(all_sites, ids) if t.get("role") == "target"]
    if paths.sample and ids is None:
        targets = targets[:2]

    rankings: dict[str, dict[str, Any]] = {}
    for t in targets:
        rp = ranking_file(paths, t['id'])
        if rp.exists():
            rankings[t["id"]] = load_json(rp)
        else:
            log.event("warn", "no ranking for target (cards skipped)", id=t["id"])

    terrains = load_terrains(paths, targets, rankings, log)
    for t in terrains.values():
        build_height(paths, t, cfg, log)
    ok = [t for t in terrains.values() if t.status == "ok"]
    if not ok:
        log.event("error", "no terrain could be exported")
        return 1
    ve = viz.vertical_exaggeration([t.relief for t in ok], VIZ_R)
    log.event("info", "vertical exaggeration", ve=ve, roughest=max(ok, key=lambda t: t.relief).id,
              roughest_relief_m=max(t.relief for t in ok))

    metas: dict[str, dict[str, Any]] = {}
    for t in ok:
        layers = layers_for(paths, t, cfg, limits, log)
        metas[t.id] = write_terrain(site, t, ve, layers, paths, cfg)
        log.event("info", "terrain written", id=t.id, relief_m=t.relief)

    exported_targets = [t for t in targets if t["id"] in metas and metas[t["id"]]["kind"] == "target"]
    site_targets = [{"id": t["id"], "body": t["body"], "name": t["name"], "lat": t["lat"], "lon": t["lon"],
                     "thumbnail": f"terrain/{t['id']}/hillshade.png", "status": "ok",
                     **site_fields(sites_by_id.get(t["id"])), "unlocked": is_unlocked(terrains[t["id"]])}
                    for t in exported_targets]
    write_json(site / "targets.json", {"targets": site_targets, "provenance": provenance_block(paths, "cards", [])})

    terrain_by_id = {t.id: t for t in ok}
    cards_dir = paths.stage("cards")
    ctx_path = paths.derived / "context" / "earth_context.json"
    ctx_windows = load_json(ctx_path)["windows"] if ctx_path.exists() else {}
    if not ctx_windows:
        log.event("warn", "Earth context cache missing: context and novelty null", path=paths.rel(ctx_path))
    places: dict[str, dict[str, Any] | None] = {}
    for rk in rankings.values():
        for row in rk["ranking"]:
            if row["analog_id"] not in places:
                places[row["analog_id"]] = analog_place(places_index, row["lat"], row["lon"])
    for tgt in exported_targets:
        tid = tgt["id"]
        rk = rankings.get(tid)
        if rk is None:
            continue
        target_t = terrain_by_id[tid]
        rank_rows = []
        for row in rk["ranking"]:
            aid = row["analog_id"]
            card_rel = None
            if aid in terrain_by_id and tid in rankings:
                analog_t = terrain_by_id[aid]
                rot = viz.rotation_alignment(target_t.height, target_t.mask, analog_t.height, analog_t.mask, VIZ_L, VIZ_R)
                ve_pair = viz.pair_exaggeration(target_t.relief, analog_t.relief, VIZ_R)
                card = build_card(paths, cfg, target_t, analog_t, row, rot["rotation_deg"], rot["rms"], ve_pair,
                                  places.get(aid))
                ctx_entry = ctx_windows.get(aid, {})
                card.update(context=ctx_entry.get("context"), novelty=ctx_entry.get("novelty"),
                            known_region_id=ctx_entry.get("known_region_id"), refined=refined_info(row))
                name = f"{tid}__{aid}.json"
                write_json(cards_dir / name, card)
                write_json(site / "cards" / name, card)
                card_rel = f"cards/{name}"
                log.event("info", "card written", target=tid, analog=aid, rotation_deg=rot["rotation_deg"])
            else:
                log.event("warn", "card skipped (analog terrain not exported)", target=tid, analog=aid)
            ctx_entry = ctx_windows.get(aid, {})
            rank_rows.append({"rank": row["rank"], "analog_id": aid, "D": row["D"], "tie_group": row["tie_group"],
                              "lat": row["lat"], "lon": row["lon"], "card": card_rel,
                              "analog_place": places.get(aid), "context": ctx_entry.get("context"),
                              "novelty": ctx_entry.get("novelty"), "known_region_id": ctx_entry.get("known_region_id"),
                              "refined": refined_info(row)})
        write_json(site / "rankings" / f"{tid}.json", {"target_id": tid, "ranking": rank_rows,
                                                      "provenance": provenance_block(paths, "cards", [])})

    viz_doc = {
        "vertical_exaggeration": ve,
        "vertical_exaggeration_rule": (
            "one value for the site: VE = 0.2 * 2R / max(P99 - P1 relief of the 30 m disk over the exported terrains), "
            "rounded down to 0.1 (viz.vertical_exaggeration)"),
        "roughest_terrain": max(ok, key=lambda t: t.relief).id,
        "grid": {"L_m": VIZ_L, "R_m": VIZ_R, "n": viz.grid_size(VIZ_R, VIZ_L)},
        "hillshade": {"azimuth_deg": viz.HILLSHADE_AZIMUTH_DEG, "altitude_deg": viz.HILLSHADE_ALTITUDE_DEG,
                      "computed_on": "VE x height on the 30 m grid"},
        "layer_bits": {"0": "slope > landing limit", "1": "slope > driving limit", "2": "ridge (TPI > +t)",
                       "3": "valley (TPI < -t)"},
        "layers_measured_on": {"L_m": cfg["grid"]["L_m"], "nearest-neighbour upsampled to 30 m": True},
        "rotation": {"step_deg": viz.ROTATION_STEP_DEG, "inner_r_frac": viz.ROTATION_INNER_FRAC,
                     "meaning": "analog rotated counter-clockwise by rotation_deg matches the target"},
        "terrains": {t.id: {"status": "ok", "relief_m": t.relief} for t in ok}
                    | {t.id: {"status": t.status, "reason": t.reason} for t in terrains.values() if t.status != "ok"},
        "provenance": provenance_block(paths, "cards", [(t.source_id, paths.root / t.raw_rel) for t in ok]),
    }
    write_json(site / "viz.json", viz_doc)
    log.event("info", "done", terrains_ok=len(ok), terrains_skipped=len(terrains) - len(ok), ve=ve)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args("Export terrains, cards and site index files (P7).")
    paths = make_paths(args.root, args.sample)
    return run(paths, ids_arg(args))


if __name__ == "__main__":
    raise SystemExit(main())
