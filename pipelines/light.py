"""P-S light (STANDARDS 10.15): sun-light numbers for the 16 targets and the 2000 Earth windows, plus P-S1 local horizon
for the Moon targets that have a LOLA 5 m surface DEM.

Reads (never recomputes what is persisted):
- site/data/targets.json (targets: body, lat)
- config/light.json (obliquity per body, with sources)
- data/raw/earth/pool/index.json (the 2000 Earth windows: id, lat)
- data/raw/moon/<target>/lola_5m*_surf.tif (surface elevation). The *_toterr.tif files are the total vertical
  uncertainty of LOLA, not elevation, so they are never used.

Writes:
- data/derived/light/light.json (full precision; sample mode: data/derived/sample/light/light.json)
- site/data/light.json (copy for the browser, 2 decimals, compact)

Sample first (STANDARDS 10.7): --sample runs 2 targets (jezero, haworth by default) and 50 pool windows.

Usage: .venv/Scripts/python.exe pipelines/light.py [--sample] [--ids jezero,haworth]
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    Paths,
    RunLog,
    clean_json,
    ids_arg,
    load_json,
    make_paths,
    parse_args,
    pool_index,
    provenance_block,
    sample_pool,
    select_ids,
    write_json,
)
from analog import grid as gridmod  # noqa: E402
from analog.core import light as lc  # noqa: E402
from analog.io import provenance as prov  # noqa: E402

STAGE = "light"
CONFIG_NAME = "light.json"
SAMPLE_TARGETS = ["jezero", "haworth"]
DEM_L_M = 10.0  # horizon grid pixel: 2 x the native 5 m (STANDARDS 3); used for the horizon only
DEM_R_M = 15000.0  # horizon grid half-width; the usable reach is the nearest valid edge inside it
DEM_PATTERN = "lola_5m*_surf.tif"
DEM_ID_PREFIX = "lola_5m_"
MOON_ONLY_REASON = "P-S1 local horizon is Moon-only (STANDARDS 10.15); not computed for this body"
LABEL_TEMPLATE = "near horizon only (within {reach:.2f} km); far mountains not included"
SITE_DECIMALS = 2


def load_light_config(paths: Paths) -> tuple[dict[str, Any], Path]:
    """config/light.json and its path. Raises if the file is missing (the stage cannot run without it)."""
    path = paths.config_dir / CONFIG_NAME
    return load_json(path), path


def obliquity_deg(cfg: dict[str, Any], body: str) -> float:
    """Obliquity of a body from config/light.json (degrees). KeyError when the body has no entry."""
    return float(cfg["bodies"][body]["obliquity_deg"])


def sun_metrics(lat: float, eps_deg: float) -> dict[str, float]:
    """Closed forms (noon max and min) and sampled shares (sun time and grazing) for one latitude.

    Formula: noon_sun_max = 90 - max(0, |phi| - eps); noon_sun_min = 90 - (|phi| + eps);
    sun_time_pct = 100 * share(e > 0); grazing_pct = 100 * share(0 < e < 10 deg); shares over all 72 x 144 samples.
    """
    elev, _ = lc.sun_geometry(lat, eps_deg)
    return {
        "noon_sun_max_deg": lc.noon_sun_max_deg(lat, eps_deg),
        "noon_sun_min_deg": lc.noon_sun_min_deg(lat, eps_deg),
        "sun_time_pct": lc.sun_time_pct(elev),
        "grazing_pct": lc.grazing_pct(elev),
    }


def moon_dem_path(paths: Paths, tid: str) -> tuple[Path | None, str | None]:
    """The LOLA 5 m surface DEM of a Moon target in data/raw/moon/<tid>/, or (None, reason).

    Only lola_5m*_surf.tif is accepted. The toterr files are uncertainty maps and are never read as elevation.
    """
    folder = paths.raw_dir / "moon" / tid
    if not folder.is_dir():
        return None, "no data/raw/moon/<id> folder for this target"
    hits = sorted(folder.glob(DEM_PATTERN))
    if not hits:
        names = sorted(p.name for p in folder.iterdir() if p.is_file())
        return None, f"no LOLA 5 m surface DEM in data/raw/moon/{tid} (files present: {', '.join(names) or 'none'})"
    return hits[0], None


def local_horizon(paths: Paths, tid: str, lat: float, lon: float, eps_moon: float, log: RunLog) -> tuple[dict[str, Any] | None, str | None, Path | None]:
    """P-S1 for one Moon target: (record, None, dem_path) on success, else (None, reason, None).

    Steps: the DEM is reprojected on the AEQD grid centred on the target (grid.load_local_grid, 10 m, half-width
    15 km); the horizon is the maximum over rays of atan((z(d) - d^2/2R - (z0 + 2)) / d) for 36 azimuths; the reach is
    the distance to the nearest valid edge; sun_time_relief_pct uses the sampled sun of the target latitude.
    """
    path, reason = moon_dem_path(paths, tid)
    if path is None:
        return None, reason, None
    try:
        z, _mask, _meta = gridmod.load_local_grid(path, lat, lon, "moon", DEM_L_M, DEM_R_M)
    except Exception as exc:  # the reason is logged and written; nothing is patched
        return None, f"DEM unreadable: {type(exc).__name__}: {str(exc)[:200]}", None
    n = z.shape[0]
    centre = (n // 2, n // 2)
    if not math.isfinite(float(z[centre])):
        return None, "target centre is outside the LOLA 5 m tile (no elevation at the centre)", None
    try:
        hz = lc.horizon_profile(z, DEM_L_M, centre, gridmod.BODY_RADIUS_M["moon"])
    except ValueError as exc:
        return None, f"horizon not computable: {exc}", None
    if not np.all(np.isfinite(hz)):
        return None, "horizon undefined for at least one azimuth", None
    reach_m = lc.valid_reach_m(z, DEM_L_M, centre)
    elev, az = lc.sun_geometry(lat, eps_moon)
    record = {
        "status": "ok",
        "reason": None,
        "horizon_max_deg": float(np.max(hz)),
        "horizon_median_deg": float(np.median(hz)),
        "horizon_by_azimuth_deg": [float(v) for v in hz],
        "azimuth_step_deg": lc.AZ_STEP_DEG,
        "sun_time_relief_pct": lc.sun_time_relief_pct(elev, az, hz),
        "horizon_reach_km": reach_m / 1000.0,
        "label": LABEL_TEMPLATE.format(reach=reach_m / 1000.0),
        "dem": {"source_id": DEM_ID_PREFIX + tid + "_surf", "path": paths.rel(path)},
    }
    log.event("info", "local horizon computed", id=tid, reach_km=round(reach_m / 1000.0, 3),
              horizon_max_deg=round(record["horizon_max_deg"], 4))
    return record, None, path


def target_record(paths: Paths, t: dict[str, Any], cfg: dict[str, Any], log: RunLog, dems: dict[str, Path]) -> dict[str, Any]:
    """One target: sun numbers from its latitude and its body's obliquity, plus P-S1 for Moon targets."""
    body = str(t["body"])
    lat = float(t["lat"])
    lon = float(t.get("lon", 0.0))
    eps = obliquity_deg(cfg, body)
    rec: dict[str, Any] = {
        "name": t.get("name"),
        "body": body,
        "lat": lat,
        "lon": lon,
        "obliquity_deg": eps,
        **sun_metrics(lat, eps),
    }
    if body != "moon":
        rec["local_horizon"] = None
        rec["local_horizon_reason"] = MOON_ONLY_REASON
        return rec
    horizon, reason, dem_path = local_horizon(paths, str(t["id"]), lat, lon, eps, log)
    rec["local_horizon"] = horizon
    rec["local_horizon_reason"] = reason
    if reason is not None:
        log.event("warn", "P-S1 null for target", id=t["id"], reason=reason)
    if dem_path is not None:
        dems[str(t["id"])] = dem_path
    return rec


def window_record(lat: float, eps_earth: float) -> dict[str, float]:
    """One Earth window: the four sun numbers from its latitude (Earth obliquity)."""
    return {"lat": lat, **sun_metrics(lat, eps_earth)}


def round_tree(obj: Any, nd: int = SITE_DECIMALS) -> Any:
    """Round every float in a nested structure (site copy only; bools and ints are left alone)."""
    if isinstance(obj, dict):
        return {k: round_tree(v, nd) for k, v in obj.items()}
    if isinstance(obj, list):
        return [round_tree(v, nd) for v in obj]
    if isinstance(obj, float):
        return round(obj, nd)
    return obj


def write_compact(path: Path, obj: Any) -> None:
    """Compact JSON, atomic write (temp file then replace). NaN never reaches the file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(clean_json(obj), separators=(",", ":"), ensure_ascii=False, allow_nan=False), encoding="utf-8")
    os.replace(tmp, path)


METHOD_NOTE = (
    "P-S light (STANDARDS 10.15). Circular orbit, Sun as a point; 72 year fractions x 144 hour angles. "
    "Obliquity from config/light.json: Earth 23.44 and Mars 25.19 (NSSDC, to the orbit plane); Moon 1.54 "
    "(lunar equator to the ecliptic, Cassini's second law; NSSDC 6.68 is not used). "
    "noon_sun_max = 90 - max(0, |lat| - eps) and noon_sun_min = 90 - (|lat| + eps) are closed forms. "
    "sun_time_pct = share of samples with elevation > 0; grazing_pct = share with 0 < elevation < 10 deg; "
    "shares are over all 10368 samples, and samples exactly at 0 deg count as not sunlit. "
    "local_horizon (Moon targets with a LOLA 5 m surface DEM only; toterr files are uncertainty, not elevation): "
    "36 azimuths every 10 deg, observer 2 m above the DEM centre, horizon = max over rays of "
    "atan((z(d) - d^2/(2R) - (z0 + 2)) / d) up to the nearest valid edge (reach). "
    "sun_time_relief_pct = share of samples with elevation > the horizon at the nearest azimuth. "
    "Label: near horizon only (within <reach> km); far mountains not included."
)


def main() -> int:
    args = parse_args("P-S light and P-S1 local horizon (STANDARDS 10.15)")
    paths = make_paths(args.root, args.sample)
    log = RunLog(paths.derived / STAGE, STAGE)
    cfg, cfg_path = load_light_config(paths)

    ids = ids_arg(args)
    if args.sample and not ids:
        ids = SAMPLE_TARGETS
    targets = select_ids(list(load_json(paths.root / "site" / "data" / "targets.json")["targets"]), ids)
    log.event("info", "targets in scope", n=len(targets), sample=bool(args.sample))

    windows_all, pool_reason = pool_index(paths)
    earth: dict[str, Any] | None = None
    earth_reason: str | None = pool_reason
    if windows_all is not None:
        windows = sample_pool(windows_all) if args.sample else sorted(windows_all, key=lambda e: str(e["id"]))
        earth = {}
        eps_earth = obliquity_deg(cfg, "earth")
        for w in windows:
            earth[str(w["id"])] = window_record(float(w["lat"]), eps_earth)
        log.event("info", "earth windows measured", n=len(earth), sample=bool(args.sample))
    else:
        log.event("warn", "pool index missing: earth_windows null", reason=pool_reason)

    dems: dict[str, Path] = {}
    target_out = {str(t["id"]): target_record(paths, t, cfg, log, dems) for t in targets}

    inputs: list[tuple[str, Path]] = [
        ("targets", paths.root / "site" / "data" / "targets.json"),
        ("config_light", cfg_path),
    ]
    if windows_all is not None:
        inputs.insert(1, ("earth_pool_index", paths.raw_dir / "earth" / "pool" / "index.json"))
    for tid, dem in sorted(dems.items()):
        inputs.append((DEM_ID_PREFIX + tid + "_surf", dem))
    block = provenance_block(paths, STAGE, inputs)
    # the governing config of this stage is config/light.json (provenance_block reads the measure config by default)
    block["config_file"] = paths.rel(cfg_path)
    block["config_version"] = str(cfg["version"])
    block["config_sha256"] = prov.sha256_file(cfg_path)

    out: dict[str, Any] = {
        "provenance": block,
        "method_note": METHOD_NOTE,
        "scope": {"targets": len(target_out), "earth_windows": len(earth) if earth is not None else 0,
                  "sample": bool(args.sample)},
        "targets": target_out,
        "earth_windows": earth if earth is not None else None,
    }
    if earth is None:
        out["earth_windows_reason"] = earth_reason

    full_path = paths.derived / STAGE / "light.json"
    write_json(full_path, out)
    log.event("info", "wrote full output", path=paths.rel(full_path))

    site_path = paths.site_data / "light.json"
    site_obj = {
        "provenance": block,
        "method_note": METHOD_NOTE,
        "scope": out["scope"],
        "targets": target_out,
        "earth_windows": earth,
    }
    if earth is None:
        site_obj["earth_windows_reason"] = earth_reason
    write_compact(site_path, round_tree(clean_json(site_obj)))
    log.event("info", "wrote site copy", path=paths.rel(site_path), bytes=site_path.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
