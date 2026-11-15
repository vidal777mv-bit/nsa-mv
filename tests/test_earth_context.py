"""pipelines/earth_context.py: legend parsing and the novelty rule (STANDARDS 10.13). No raster or network needed."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "pipelines"))
sys.path.insert(0, str(HERE / "src"))

import earth_context as EC  # noqa: E402


def test_novelty_known_inside_circle_new_outside():
    regions = [{"id": "r1", "lat": 0.0, "lon": 0.0, "radius_km": 100.0}]
    assert EC.novelty_of(0.5, 0.5, regions) == ("known_region", "r1")  # about 78 km away
    assert EC.novelty_of(2.0, 0.0, regions) == ("new", None)  # about 222 km away


def test_legend_parses_codes_short_names_and_labels(tmp_path: Path):
    from _common import make_paths

    paths = make_paths(tmp_path, sample=False)
    leg = paths.raw_dir / "reference" / "koppen" / "legend.txt"
    leg.parent.mkdir(parents=True)
    leg.write_text("    4:  BWh  Arid, desert, hot                     [255 0 0]\n"
                   "   29:  ET   Polar, tundra                         [178 178 178]\n", encoding="utf-8")
    table = EC.koppen_legend(paths)
    assert table[4] == ("BWh", "Arid, desert, hot")
    assert table[29] == ("ET", "Polar, tundra")


def test_elevation_source_is_the_source_id_of_the_window_record():
    assert EC.elevation_source({"source_id": "nasadem"}).startswith("nasadem window mean")
    assert EC.elevation_source({"source_id": "cop_dem_glo30"}).startswith("cop_dem_glo30 window mean")
    assert EC.elevation_source({}).startswith("null: measure record has no source_id")


def test_refresh_elevation_rewrites_old_text_from_each_record(tmp_path: Path):
    from _common import RunLog, make_paths, window_record_path, write_json

    paths = make_paths(tmp_path, sample=False)
    write_json(window_record_path(paths, "pool_00001"), {"source_id": "nasadem", "lat": 1.0, "lon": 2.0})
    write_json(window_record_path(paths, "pool_02001"), {"source_id": "cop_dem_glo30", "lat": 70.0, "lon": 2.0})
    old = "NASADEM window mean over the 4 km disk (measure record source)"
    cache = {"windows": {
        "pool_00001": {"context": {"sources": {"elevation": old}}},
        "pool_02001": {"context": {"sources": {"elevation": old}}},
        "pool_09999": {"context": {"sources": {"elevation": old}}},  # no record: kept, logged
    }}
    n = EC.refresh_elevation(paths, cache, RunLog(paths.stage("cards"), "test"))
    assert n == 2
    src = {k: v["context"]["sources"]["elevation"] for k, v in cache["windows"].items()}
    assert src["pool_00001"].startswith("nasadem window mean") and src["pool_02001"].startswith("cop_dem_glo30 window mean")
    assert src["pool_09999"] == old
