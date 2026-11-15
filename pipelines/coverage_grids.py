"""Coverage grids, the fog of the atlas (STANDARDS 10.13): site/data/coverage/<body>.json for mars, moon and earth.

Grid: 1 degree cells, 360 x 180, origin [-180, 90] (row 0 is the northern row, lat 89..90; column 0 is lon -180..-179),
row-major ints. The cell is decided by its CENTRE for the point and footprint rules (lon -179.5 + c, lat 89.5 - r).
Classes: 0 out_of_reach, 1 to_discover, 2 unlocked.

- Mars: 2 at a measured Mars window centre (target or Mars pool window, data/derived/measure, status ok); 1 where the
  cell centre lies inside a CTX DTM bbox from config/mars_coverage.json (USGS STAC mro_ctx_controlled_usgs_dtms, CC0);
  0 elsewhere.
- Moon: 2 at a measured Moon site; 1 where the cell centre lies between 90S and 80S (LOLA 20 m polar DEM); 0 elsewhere.
- Earth: 2 at a search-pool window centre: every row of data/raw/earth/pool/index.json whose `excluded` is null (NASADEM
  and the Arctic rows, config/earth_pool_rules.json); 1 where the coarse WorldCover bare share of the 1 degree cell is
  >= 0.8 (cached 300 px tiles per 100 x 100 px cell: data/raw/earth/pool/_worldcover_coarse for all cells, and
  data/raw/earth/arctic_probe/_worldcover_coarse for cells whose centre is north of the Arctic band's lat_min);
  0 elsewhere (ocean, vegetation, crops, and cells without a cached tile). The coarse cache is bare-or-not only, so
  class 70 (snow and ice) counts as bare there; the source text says so.

Usage: .venv/Scripts/python.exe pipelines/coverage_grids.py [--body mars|moon|earth] (default: all three)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    Paths,
    RunLog,
    load_json,
    make_paths,
    parse_args,
    provenance_block,
    window_records,
    write_json,
)

W, H = 360, 180
CLASSES = {"0": "out_of_reach", "1": "to_discover", "2": "unlocked"}
WORLDCOVER_MIN_SHARE = 0.8
MOON_BAND = (-90.0, -80.0)
BODIES = ("mars", "moon", "earth")
EARTH_RULES = "earth_pool_rules.json"  # the bands (source_id, lat_min, lat_max) and the ice rule; one place for all pieces
ARCTIC_CACHE = Path("earth") / "arctic_probe" / "_worldcover_coarse"  # under data/raw/
POOL_CACHE = Path("earth") / "pool" / "_worldcover_coarse"  # under data/raw/


def cell_of(lat: float, lon: float) -> tuple[int, int]:
    """(row, col) of the cell containing a point (row 0 = lat 89..90, col 0 = lon -180..-179)."""
    r = int(np.floor(90.0 - lat))
    c = int(np.floor(lon + 180.0))
    return min(max(r, 0), H - 1), min(max(c, 0), W - 1)


def centres() -> tuple[np.ndarray, np.ndarray]:
    """Cell centre latitudes (per row) and longitudes (per column)."""
    lat_c = 89.5 - np.arange(H)
    lon_c = -179.5 + np.arange(W)
    return lat_c, lon_c


ANTIMERIDIAN_STRIP_DEG = 2.0  # fallback footprint for a product whose corner coordinates are not stored


def mars_boxes(products: list[list[float]]) -> tuple[list[list[float]], int]:
    """Footprint boxes [minlon, minlat, maxlon, maxlat] for the coverage rule, and the number of antimeridian products.

    A product with a stored bbox wider than 180 deg crosses the antimeridian and its stored bbox is [-180, lat1, 180, lat2]:
    it must never paint a full latitude band. Its real corners are not in config/mars_coverage.json, so it is re-derived as
    two 2-degree strips adjacent to -180 and +180 with the stored latitude range (stated in the notes).
    """
    boxes: list[list[float]] = []
    wrapped = 0
    for minx, miny, maxx, maxy in products:
        if maxx - minx > 180.0:
            wrapped += 1
            boxes.append([-180.0, miny, -180.0 + ANTIMERIDIAN_STRIP_DEG, maxy])
            boxes.append([180.0 - ANTIMERIDIAN_STRIP_DEG, miny, 180.0, maxy])
        else:
            boxes.append([minx, miny, maxx, maxy])
    return boxes, wrapped


def area_shares(grid: np.ndarray) -> dict[str, float]:
    """Area-weighted share of the sphere per class: a 1-degree cell weighs cos(centre latitude)."""
    lat_c, _ = centres()
    w = np.cos(np.radians(lat_c))[:, None] * np.ones((1, W))
    total = float(w.sum())
    return {k: float(w[grid == int(k)].sum() / total) for k in CLASSES}


def mars_bbox_class(grid: np.ndarray, products: list[list[float]]) -> None:
    """Class 1 where a cell centre lies inside a CTX bbox [minlon, minlat, maxlon, maxlat] (vectorised per product)."""
    lat_c, lon_c = centres()
    for minx, miny, maxx, maxy in products:
        rows = np.nonzero((lat_c >= miny) & (lat_c <= maxy))[0]
        cols = np.nonzero((lon_c >= minx) & (lon_c <= maxx))[0]
        if rows.size and cols.size:
            sub = grid[np.ix_(rows, cols)]
            np.maximum(sub, 1, out=sub)
            grid[np.ix_(rows, cols)] = sub


def earth_class2(pool_rows: list[dict[str, Any]], rules: dict[str, Any]) -> tuple[list[tuple[float, float]], str]:
    """Earth class 2: the centres of the index rows with `excluded` null, and the source line that counts them per band.

    The counts come from the index and the bands of config/earth_pool_rules.json, never from a typed number. A row without
    source_id is a NASADEM row (the frozen 2,000-window pool was written before the field existed).
    """
    bands = {b["source_id"]: b for b in rules["bands"]}
    kept = [w for w in pool_rows if w.get("excluded") is None]
    points = [(float(w["lat"]), float(w["lon"])) for w in kept]
    counts = {sid: 0 for sid in bands}
    other = 0
    for w in kept:
        sid = w.get("source_id") or "nasadem"
        if sid in counts:
            counts[sid] += 1
        else:
            other += 1
    parts = [f"{counts[sid]} {sid} {_lat_text(b['lat_min'])} to {_lat_text(b['lat_max'])}" for sid, b in bands.items()]
    if other:
        parts.append(f"{other} from other sources")
    excluded = len(pool_rows) - len(kept)
    text = (f"class 2: {len(kept)} search-pool window centres = index rows with excluded null ({'; '.join(parts)}); "
            f"{excluded} excluded rows (ice or not bare ground) are not class 2")
    return points, text


def _lat_text(lat: float) -> str:
    """-56 -> '56S', 60 -> '60N'."""
    return f"{abs(lat):g}{'S' if lat < 0 else 'N'}"


def worldcover_class(grid: np.ndarray, coarse_dir: Path, min_lat: float = -90.0) -> dict[str, Any]:
    """Class 1 where a 1 degree block of a cached tile has bare share >= 0.8, for cells whose centre lies north of min_lat.

    A 3 x 3 degree tile named ..._N00E006 covers lat [0, 3) and lon [6, 9); its 300 x 300 array is north-up with 0.01
    degree pixels, so the 1 degree cell (lat a..a+1, lon b..b+1) is rows (lat0 + 2 - a) * 100 ... +100 and columns
    (b - lon0) * 100 ... +100.
    """
    n_tiles = 0
    n_cells = 0
    for p in sorted(coarse_dir.glob("*.npy")):
        m = re.search(r"_([NS])(\d{2})([EW])(\d{3})$", p.stem)
        if not m:
            continue
        lat0 = int(m.group(2)) * (1 if m.group(1) == "N" else -1)
        lon0 = int(m.group(4)) * (1 if m.group(3) == "E" else -1)
        arr = np.load(p)
        if arr.shape != (300, 300):
            continue
        n_tiles += 1
        for i in range(3):  # 1 degree row inside the tile, from the south
            for j in range(3):
                a = lat0 + i  # south edge of the cell
                b = lon0 + j  # west edge
                if a + 0.5 <= min_lat:  # cell centre not north of min_lat: not this cache's cell
                    continue
                r0 = (lat0 + 2 - a) * 100
                c0 = (b - lon0) * 100
                share = float(arr[r0:r0 + 100, c0:c0 + 100].mean())
                if share >= WORLDCOVER_MIN_SHARE:
                    row, col = cell_of(a + 0.5, b + 0.5)
                    if grid[row, col] < 1:
                        grid[row, col] = 1
                        n_cells += 1
    return {"tiles": n_tiles, "cells_class1_from_share": n_cells}


def build(paths: Paths, body: str, log: RunLog) -> dict[str, Any]:
    """The grid of one body (classes 0/1/2) and its counts."""
    grid = np.zeros((H, W), dtype=np.int8)
    wrapped_count = 0
    sources: list[str] = []
    inputs: list[tuple[str, Path]] = []
    points: list[tuple[float, float]] = []

    measured = [r for r in window_records(paths.stage("measure"), status="ok") if r.get("body") == body]
    if body != "earth":  # Earth class 2 is the search pool only, not every Earth measure record (dev regions excluded)
        points += [(r["lat"], r["lon"]) for r in measured]

    if body == "mars":
        cfg = paths.config_dir / "mars_coverage.json"
        products = [p["bbox"] for p in load_json(cfg)["products"]]
        boxes, wrapped = mars_boxes(products)
        wrapped_count = wrapped
        mars_bbox_class(grid, boxes)
        sources.append(f"config/mars_coverage.json: {len(products)} USGS STAC CTX DTM bboxes (CC0), centre-in-bbox rule; "
                       f"{wrapped} antimeridian products as two 2-degree strips")
        inputs.append(("mars_coverage", cfg))
        sources.append(f"class 2: {len(measured)} measured Mars window centres (targets; Mars pool windows when added)")
    elif body == "moon":
        lat_c, _ = centres()
        band_rows = np.nonzero((lat_c >= MOON_BAND[0]) & (lat_c <= MOON_BAND[1]))[0]
        grid[band_rows, :] = np.maximum(grid[band_rows, :], 1)
        sources.append("LOLA 20 m polar DEM footprint: cells with centre between 90S and 80S (class 1)")
        sources.append(f"class 2: {len(measured)} measured Moon site centres")
    elif body == "earth":
        pool_path = paths.raw_dir / "earth" / "pool" / "index.json"
        rules_path = paths.config_dir / EARTH_RULES
        pool = load_json(pool_path)
        pool = pool["windows"] if isinstance(pool, dict) else pool
        rules = load_json(rules_path)
        arctic_min = float(next(b["lat_min"] for b in rules["bands"] if b["id"] == "arctic"))
        pts, class2_text = earth_class2(pool, rules)
        points += pts
        inputs.append(("nasadem_pool_index", pool_path))
        inputs.append(("earth_pool_rules", rules_path))
        info_pool = worldcover_class(grid, paths.raw_dir / POOL_CACHE)
        info_arctic = worldcover_class(grid, paths.raw_dir / ARCTIC_CACHE, min_lat=arctic_min)
        sources.append(f"ESA WorldCover 2021 coarse bare share >= {WORLDCOVER_MIN_SHARE} per 1 degree cell: pool cache "
                       f"({info_pool['tiles']} tiles) for all cells, Arctic cache ({info_arctic['tiles']} tiles) for cells "
                       f"centred north of {_lat_text(arctic_min)}; cells without a cached tile are 0. The coarse cache is "
                       "bare-or-not only, so class 70 (snow and ice) counts as bare: ice-sheet cells can be class 1")
        sources.append(class2_text)
    else:
        raise ValueError(f"unknown body {body!r}")

    for lat, lon in points:
        row, col = cell_of(lat, lon)
        grid[row, col] = 2
    counts = {k: int(np.sum(grid == int(k))) for k in CLASSES}
    log.event("info", "coverage built", body=body, counts=counts)
    doc = {
        "body": body, "res_deg": 1, "width": W, "height": H, "origin": [-180, 90], "classes": CLASSES,
        "grid": grid.ravel().astype(int).tolist(), "counts": counts, "source": " | ".join(sources),
        "provenance": provenance_block(paths, "coverage", inputs),
    }
    if body == "mars":
        doc["notes"] = mars_notes(paths, counts, grid, wrapped_products=wrapped_count)
    return doc


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% interval for k successes in n trials (STANDARDS section 5, same formula as core/stats)."""
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return float(centre - half), float(centre + half)


def mars_notes(paths: Paths, counts: dict[str, int], grid: np.ndarray, wrapped_products: int) -> dict[str, Any]:
    """The Mars acceptance rate from the attempt log, and what the class-1 rule is (an upper bound)."""
    attempts_path = paths.raw_dir / "mars" / "pool" / "attempts.jsonl"
    rows = [json.loads(line) for line in attempts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    n = len(rows)
    k = sum(1 for r in rows if r.get("status") == "accepted")
    lo, hi = wilson(k, n)
    return {
        "single_ctx_full_disk_rate": {
            "value": k / n, "accepted": k, "attempts": n, "wilson95": [lo, hi],
            "meaning": "share of Mars with a single CTX DTM covering a full 8 km disk (valid >= 0.90 in the 4 km disk)",
            "source": "data/raw/mars/pool/attempts.jsonl (accepted / all attempts; random centres seeded 20261114)",
        },
        "class1_is": "upper bound: the bbox of a CTX DTM covers the cell, not a full 8 km disk with valid >= 0.90",
        "class2_is": f"{counts['2']} 1-degree cells that contain a measured Mars window centre (targets and the Mars pool). "
                     "This counts cells, not measured area.",
        "class1_source": "centre of the cell inside a CTX DTM bbox; products stored as width-360 bboxes are two 2-degree "
                         f"strips adjacent to +/-180 ({wrapped_products} products, stored corners not available)",
        "area_weighted_share": area_shares(grid),
    }


def run(paths: Paths, bodies: list[str]) -> int:
    """Write site/data/coverage/<body>.json for each body. Returns the number written."""
    log = RunLog(paths.stage("cards"), "coverage_grids")
    out_dir = paths.site_data / "coverage"
    written = 0
    for body in bodies:
        doc = build(paths, body, log)
        write_json(out_dir / f"{body}.json", doc)
        written += 1
    return written


def main(argv: list[str] | None = None) -> int:
    args = parse_args("Coverage grids (fog) for mars, moon and earth (STANDARDS 10.13).",
                      extra=[(("--body",), {"default": None, "help": "mars, moon or earth (default all)"})])
    paths = make_paths(args.root, args.sample)
    bodies = [args.body] if args.body else list(BODIES)
    run(paths, bodies)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
