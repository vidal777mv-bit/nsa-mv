"""Earth context of each twin (STANDARDS 10.13): not scored, shown on the cards, the ranking entries and the discoveries.

Per Earth window (keyed by the analog id used in the rankings):
- context: koppen_class (Beck et al. 2018/2023 Koppen-Geiger 1 km, CC BY 4.0, legend in data/raw/reference/koppen/legend.txt),
  koppen_label, elevation_m (mean of the window's valid heights over its 4 km disk, from its own clip or pool clip),
  nearest_town {name, country, distance_km} from Natural Earth 1:10m populated places (public domain), sources;
- novelty "known_region" | "new" with known_region_id, against config/known_analog_regions.json (circle approximation:
  the centre lies within radius_km of the region centre). null with a reason when that file does not exist yet.

Cache: data/derived/context/earth_context.json (one entry per analog id). Missing inputs give null with a reason; nothing
is invented. The export reads the cache; the Mars atlas and the discoveries use it too.

Usage: .venv/Scripts/python.exe pipelines/earth_context.py      (every Earth twin in the effective rankings)
"""

from __future__ import annotations

import glob
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    Paths,
    RunLog,
    make_paths,
    parse_args,
    provenance_block,
    ranking_file,
    read_config,
    sites_list,
    window_record_path,
    window_records,
    write_json,
    load_json,
)
from analog import grid as gridmod  # noqa: E402
from analog.io import places as PL  # noqa: E402
from analog.io.places import haversine_km  # noqa: E402

KOPPEN_DIR = "reference/koppen"
POP_SHP = "reference/ne_10m_populated_places/ne_10m_populated_places.shp"
KNOWN_FILE = "known_analog_regions.json"
CONTEXT_FILE = "earth_context.json"


def koppen_legend(paths: Paths) -> dict[int, tuple[str, str]]:
    """{code: (short class, label)} from legend.txt (lines like '    4:  BWh  Arid, desert, hot   [255 0 0]')."""
    out: dict[int, tuple[str, str]] = {}
    path = paths.raw_dir / KOPPEN_DIR / "legend.txt"
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        head, _, rest = line.partition(":")
        if not head.strip().isdigit() or not rest.strip():
            continue
        code = int(head.strip())
        parts = rest.split("[", 1)[0].split()
        if not parts:
            continue
        short = parts[0]
        label = " ".join(parts[1:]).strip().replace("  ", " ")
        out[code] = (short, label)
    return out


def koppen_raster(paths: Paths) -> Path | None:
    """The Koppen-Geiger present-day GeoTIFF (Beck_KG_V1_present_*.tif), or None when absent."""
    hits = sorted(glob.glob(str(paths.raw_dir / KOPPEN_DIR / "Beck_KG_V1_present*.tif")))
    return Path(hits[0]) if hits else None


def known_regions(paths: Paths) -> tuple[list[dict[str, Any]] | None, str | None]:
    """config/known_analog_regions.json -> (regions, None), or (None, reason) when the file is not there."""
    path = paths.config_dir / KNOWN_FILE
    if not path.exists():
        return None, "config/known_analog_regions.json not found"
    doc = load_json(path)
    regions = doc["regions"] if isinstance(doc, dict) else doc
    return list(regions), None


def novelty_of(lat: float, lon: float, regions: list[dict[str, Any]]) -> tuple[str, str | None]:
    """'known_region' with its id when the point lies within a known region's circle, else 'new'."""
    for reg in regions:
        if haversine_km(lat, lon, float(reg["lat"]), float(reg["lon"])) <= float(reg["radius_km"]):
            return "known_region", reg["id"]
    return "new", None


def window_elevation(record_path: Path, paths: Paths, cfg: dict[str, Any]) -> float | None:
    """Mean of the valid heights over the window's disk (R from config), from the window's measure record source."""
    rec = load_json(record_path)
    raw = paths.root / rec["source_path"]
    z, mask, _ = gridmod.load_local_grid(raw, rec["lat"], rec["lon"], rec["body"], float(cfg["grid"]["L_m"]),
                                         float(cfg["grid"]["R_m"]))
    sel = z[mask & np.isfinite(z)]
    return None if sel.size == 0 else float(sel.mean())


def elevation_source(rec: dict[str, Any]) -> str:
    """Where the elevation of a window comes from: the source_id of its own measure record (nasadem, cop_dem_glo30, ...)."""
    sid = rec.get("source_id")
    if not sid:
        return "null: measure record has no source_id"
    return f"{sid} window mean over the 4 km disk (source_id of the window's measure record)"


def build(paths: Paths, analog_ids: list[str], log: RunLog) -> dict[str, Any]:
    """Context entries for the given analog ids (keys as used in the rankings)."""
    cfg = read_config(paths)
    legend = koppen_legend(paths)
    kr = koppen_raster(paths)
    regions, known_reason = known_regions(paths)
    shp = paths.raw_dir / POP_SHP
    towns = None
    if shp.exists():
        attrs = PL.read_dbf(shp.with_suffix(".dbf"))
        lats, lons, kept = PL.read_shp_points(shp, attrs)
        towns = (lats, lons, kept)
    else:
        log.event("warn", "Natural Earth populated places not found: nearest_town null", path=paths.rel(shp))
    if kr is None:
        log.event("warn", "Koppen-Geiger raster not found: koppen null", dir=KOPPEN_DIR)
    if regions is None:
        log.event("warn", "known_analog_regions missing: novelty null", reason=known_reason)

    import rasterio

    entries: dict[str, Any] = {}
    ds = rasterio.open(kr) if kr is not None else None
    try:
        for aid in analog_ids:
            rec_path = window_record_path(paths, aid)
            if not rec_path.exists():
                log.event("warn", "no measure record for twin: context skipped", id=aid)
                continue
            rec = load_json(rec_path)
            lat, lon = float(rec["lat"]), float(rec["lon"])
            code = None
            if ds is not None:
                row, col = ds.index(lon, lat)
                val = int(ds.read(1, window=((row, row + 1), (col, col + 1)))[0, 0])
                code = val if val > 0 else None
            koppen_class = legend[code][0] if code in legend else None
            koppen_label = legend[code][1] if code in legend else None
            town = None
            if towns is not None and towns[0].size:
                i, km = PL.nearest_point_km(lat, lon, towns[0], towns[1])
                town = {"name": towns[2][i].get("NAME"), "country": towns[2][i].get("ADM0NAME"),
                        "distance_km": round(km, 2)}
            novelty, known_id = (None, None)
            if regions is not None:
                novelty, known_id = novelty_of(lat, lon, regions)
            entries[aid] = {
                "lat": lat, "lon": lon,
                "novelty": novelty, "known_region_id": known_id,
                "context": {
                    "koppen_class": koppen_class, "koppen_label": koppen_label,
                    "koppen_code": code,
                    "elevation_m": window_elevation(rec_path, paths, cfg),
                    "nearest_town": town,
                    "sources": {
                        "koppen": f"Beck et al. 2018/2023 Koppen-Geiger 1 km, CC BY 4.0 ({kr.name if kr else 'missing'})",
                        "elevation": elevation_source(rec),
                        "town": "Natural Earth 1:10m populated places (public domain)",
                        "novelty": "config/known_analog_regions.json (circle approximation)" if regions is not None
                                   else f"null: {known_reason}",
                    },
                },
            }
    finally:
        if ds is not None:
            ds.close()
    return entries


def refresh_places(paths: Paths, cache: dict[str, Any], log: RunLog) -> int:
    """Fill analog_place (Natural Earth admin-1 name of the window centre, STANDARDS 10.13) for every cached window that lacks
    it; null with a logged reason when the admin-1 file is absent. Returns the number of windows that got a place."""
    from _common import analog_place, load_places

    index = load_places(paths, log)
    filled = 0
    for entry in cache["windows"].values():
        if entry.get("analog_place") is None:
            entry["analog_place"] = analog_place(index, entry["lat"], entry["lon"])
        if entry["analog_place"] is not None:
            filled += 1
    log.event("info", "analog places filled", windows=len(cache["windows"]), with_place=filled)
    return filled


def refresh_novelty(paths: Paths, cache: dict[str, Any], log: RunLog) -> int:
    """Recompute novelty and known_region_id of every cached window from the current known-regions file (no raster read).
    Sets null with the reason when the file is absent. Returns the number of windows whose novelty was set."""
    regions, reason = known_regions(paths)
    set_n = 0
    for entry in cache["windows"].values():
        if regions is None:
            entry["novelty"], entry["known_region_id"] = None, None
            entry["context"]["sources"]["novelty"] = f"null: {reason}"
            continue
        entry["novelty"], entry["known_region_id"] = novelty_of(entry["lat"], entry["lon"], regions)
        entry["context"]["sources"]["novelty"] = "config/known_analog_regions.json (circle approximation)"
        set_n += 1
    log.event("info", "novelty refreshed", windows=len(cache["windows"]), set=set_n,
              known_regions=None if regions is None else len(regions))
    return set_n


def refresh_elevation(paths: Paths, cache: dict[str, Any], log: RunLog) -> int:
    """Rewrite the elevation source text of every cached window from its measure record (old entries said 'NASADEM window
    mean' for every window). A window without a record keeps its text and is logged. Returns the number rewritten."""
    set_n = 0
    for wid, entry in cache["windows"].items():
        rec_path = window_record_path(paths, wid)
        if not rec_path.exists():
            log.event("warn", "no measure record: elevation source not refreshed", id=wid)
            continue
        entry["context"]["sources"]["elevation"] = elevation_source(load_json(rec_path))
        set_n += 1
    log.event("info", "elevation sources refreshed", windows=len(cache["windows"]), set=set_n)
    return set_n


def run(paths: Paths, all_pool: bool = False) -> int:
    """Build the context for every Earth twin in the effective rankings (and, with all_pool, every accepted search-pool
    window); merge into the cache. Returns entries written."""
    log = RunLog(paths.stage("cards"), "earth_context")
    ids: set[str] = set()
    if all_pool:
        ids.update(r["id"] for r in window_records(paths.stage("measure"), kind="pool", status="ok"))
    for t in sites_list(paths):
        if t.get("role") != "target":
            continue
        rp = ranking_file(paths, t["id"])
        if rp.exists():
            ids.update(row["analog_id"] for row in load_json(rp).get("ranking", []))
    cache_path = paths.derived / "context" / CONTEXT_FILE
    cache = load_json(cache_path) if cache_path.exists() else {"windows": {}}
    todo = sorted(i for i in ids if i not in cache["windows"])
    new = build(paths, todo, log)
    cache["windows"].update(new)
    refresh_novelty(paths, cache, log)
    refresh_elevation(paths, cache, log)
    refresh_places(paths, cache, log)
    cache["sources"] = {"koppen": "Beck et al. 2018/2023, CC BY 4.0", "towns": "Natural Earth 1:10m populated places",
                        "novelty": "config/known_analog_regions.json (circle approximation)"}
    cache["provenance"] = provenance_block(paths, "cards", [])
    write_json(cache_path, cache)
    log.event("info", "earth context written", windows=len(cache["windows"]), added=len(new))
    return len(new)


def main(argv: list[str] | None = None) -> int:
    args = parse_args("Earth context of the twins: Koppen class, elevation, nearest town, novelty (STANDARDS 10.13).",
                      extra=[(("--all-pool",), {"action": "store_true",
                                                "help": "also the context of every accepted search-pool window"})])
    paths = make_paths(args.root, args.sample)
    run(paths, all_pool=bool(args.all_pool))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
