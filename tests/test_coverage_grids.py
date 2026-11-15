"""pipelines/coverage_grids.py: cell indexing, class rules and the Mars notes (STANDARDS 10.13)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "pipelines"))

import coverage_grids as CG  # noqa: E402


def test_cell_index_row_zero_is_the_north_row_and_column_zero_starts_at_minus_180():
    assert CG.cell_of(89.5, -179.5) == (0, 0)
    assert CG.cell_of(-89.5, 179.5) == (179, 359)
    assert CG.cell_of(0.2, 10.7) == (89, 190)


def test_bbox_class_one_uses_cell_centres_inside_the_bbox():
    grid = np.zeros((CG.H, CG.W), dtype=np.int8)
    CG.mars_bbox_class(grid, [[10.0, 20.0, 12.4, 22.4]])  # centres 10.5, 11.5 (lon) and 20.5, 21.5 (lat)
    assert int(grid.sum()) == 4
    assert grid[CG.cell_of(21.0, 11.0)] == 1 and grid[CG.cell_of(19.0, 11.0)] == 0


def test_wilson_interval_matches_the_published_formula():
    lo, hi = CG.wilson(2000, 25914)
    assert lo == pytest.approx(0.0740, abs=5e-4) and hi == pytest.approx(0.0805, abs=5e-4)


def test_antimeridian_product_never_paints_a_full_band():
    """A stored width-360 bbox (the 16 CTX products crossing 180 deg) becomes two 2-degree strips at the ends of the map."""
    boxes, wrapped = CG.mars_boxes([[-180.0, 4.3, 180.0, 5.1], [10.0, 20.0, 10.5, 20.5]])
    assert wrapped == 1 and len(boxes) == 3
    grid = np.zeros((CG.H, CG.W), dtype=np.int8)
    CG.mars_bbox_class(grid, [boxes[0], boxes[1]])
    painted_per_row = grid.sum(axis=1)
    assert int(painted_per_row.max()) <= 4  # two 2-degree strips = at most 4 cells in any row
    assert grid[CG.cell_of(4.5, -179.5)] == 1 and grid[CG.cell_of(4.5, 179.5)] == 1
    assert grid[CG.cell_of(4.5, 0.5)] == 0  # the middle of the band is not painted


def test_area_shares_weight_cells_by_cosine_of_latitude():
    grid = np.zeros((CG.H, CG.W), dtype=np.int8)
    shares = CG.area_shares(grid)
    assert abs(shares["0"] - 1.0) < 1e-12 and shares["1"] == 0.0
    grid[CG.cell_of(0.5, 0.5)] = 1  # equator cell
    grid[CG.cell_of(80.5, 0.5)] = 2  # high-latitude cell weighs less
    s = CG.area_shares(grid)
    assert s["1"] > s["2"] > 0


RULES = {"bands": [
    {"id": "nasadem", "lat_min": -56.0, "lat_max": 60.0, "source_id": "nasadem", "sensor": "nasadem"},
    {"id": "arctic", "lat_min": 60.0, "lat_max": 84.0, "source_id": "cop_dem_glo30", "sensor": "copdem"},
]}


def test_arctic_cache_paints_only_cells_centred_north_of_60N(tmp_path: Path):
    """Two synthetic 3 x 3 degree tiles, all bare: N60E003 (Arctic) and N54E003 (below 60N, must not paint)."""
    np.save(tmp_path / "ESA_WorldCover_10m_2021_v200_N60E003.npy", np.ones((300, 300), dtype=bool))
    np.save(tmp_path / "ESA_WorldCover_10m_2021_v200_N54E003.npy", np.ones((300, 300), dtype=bool))
    grid = np.zeros((CG.H, CG.W), dtype=np.int8)
    info = CG.worldcover_class(grid, tmp_path, min_lat=60.0)
    assert info["tiles"] == 2
    assert grid[CG.cell_of(60.5, 3.5)] == 1 and grid[CG.cell_of(62.5, 4.5)] == 1  # Arctic cells painted
    assert grid[CG.cell_of(58.5, 3.5)] == 0 and grid[CG.cell_of(55.5, 4.5)] == 0  # below 60N: not from this cache
    assert int(grid.sum()) == 9  # only the nine cells of N60E003


def test_pool_cache_without_min_lat_paints_every_bare_cell(tmp_path: Path):
    np.save(tmp_path / "ESA_WorldCover_10m_2021_v200_N54E003.npy", np.ones((300, 300), dtype=bool))
    grid = np.zeros((CG.H, CG.W), dtype=np.int8)
    CG.worldcover_class(grid, tmp_path)
    assert int(grid.sum()) == 9 and grid[CG.cell_of(55.5, 4.5)] == 1


def test_class2_is_the_index_rows_not_excluded_and_its_text_is_generated():
    rows = [
        {"id": "pool_00001", "lat": 10.5, "lon": 20.5},  # NASADEM row, no source_id field (frozen index)
        {"id": "pool_00002", "lat": 11.5, "lon": 21.5, "source_id": "nasadem", "excluded": None},
        {"id": "pool_02001", "lat": 70.5, "lon": 30.5, "source_id": "cop_dem_glo30", "excluded": None},
        {"id": "pool_00003", "lat": 12.5, "lon": 22.5, "source_id": "nasadem",
         "excluded": {"rule": "ice_share", "value": 0.5, "threshold": 0.2}},  # not in class 2
    ]
    points, text = CG.earth_class2(rows, RULES)
    assert points == [(10.5, 20.5), (11.5, 21.5), (70.5, 30.5)]
    assert text.startswith("class 2: 3 search-pool window centres")
    assert "2 nasadem 56S to 60N" in text and "1 cop_dem_glo30 60N to 84N" in text
    assert "1 excluded rows" in text
    assert "2000" not in text and "56S-60N" not in text  # nothing typed: the counts come from the rows


def test_earth_build_class2_from_index_and_class1_from_both_caches(tmp_path: Path):
    """Whole earth branch on a synthetic root: a 3-row index (one NASADEM row excluded, one Arctic row), two caches."""
    from _common import RunLog, make_paths, write_json

    paths = make_paths(tmp_path, sample=False)
    write_json(paths.config_dir / "earth_pool_rules.json", RULES)
    write_json(paths.measure_config, {"version": "synthetic-test"})  # provenance reads the frozen config file's bytes
    write_json(paths.raw_dir / "earth" / "pool" / "index.json", [
        {"id": "pool_00001", "lat": 10.5, "lon": 20.5, "source_id": "nasadem", "excluded": None},
        {"id": "pool_00002", "lat": 12.5, "lon": 22.5, "source_id": "nasadem",
         "excluded": {"rule": "ice_share", "value": 0.5, "threshold": 0.2}},
        {"id": "pool_02001", "lat": 70.5, "lon": 30.5, "source_id": "cop_dem_glo30", "excluded": None},
    ])
    pool_cache = paths.raw_dir / "earth" / "pool" / "_worldcover_coarse"
    arctic_cache = paths.raw_dir / "earth" / "arctic_probe" / "_worldcover_coarse"
    for d in (pool_cache, arctic_cache):
        d.mkdir(parents=True)
    np.save(pool_cache / "ESA_WorldCover_10m_2021_v200_N54E003.npy", np.ones((300, 300), dtype=bool))
    np.save(arctic_cache / "ESA_WorldCover_10m_2021_v200_N60E003.npy", np.ones((300, 300), dtype=bool))
    doc = CG.build(paths, "earth", RunLog(paths.stage("cards"), "test"))
    grid = np.array(doc["grid"]).reshape(CG.H, CG.W)
    assert doc["counts"]["2"] == 2  # two non-excluded rows; the excluded NASADEM row is not class 2
    assert grid[CG.cell_of(10.5, 20.5)] == 2 and grid[CG.cell_of(70.5, 30.5)] == 2
    assert grid[CG.cell_of(12.5, 22.5)] == 0  # excluded row: no class 2, and no cache paints this cell
    assert doc["counts"]["1"] == 18  # nine cells of N54E003 (pool cache) + nine of N60E003 (Arctic cache)
    assert grid[CG.cell_of(55.5, 4.5)] == 1 and grid[CG.cell_of(60.5, 3.5)] == 1
    assert "class 2: 2 search-pool window centres" in doc["source"] and "2000" not in doc["source"]
