"""tools/check_site_data.py on a small synthetic site/data tree (read-only checker, STANDARDS 10.5/10.6/10.9/10.12).

Run alone: .venv/Scripts/python.exe -m pytest tests/test_check_site_data.py
Each test writes its own temp tree; the repository's site/data is never read here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "tools"))

import check_site_data as CS  # noqa: E402

N = 269


def _write(path: Path, data: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")


def _terrain(data: Path, tid: str, body: str = "mars") -> None:
    folder = data / "terrain" / tid
    _write(folder / "height.bin", bytes(N * N * 4))
    _write(folder / "hillshade.png", b"\x89PNG\r\n\x1a\n")
    _write(folder / f"layers_{body}.bin", bytes(N * N))
    meta = {"id": tid, "n": N, "layers": {body: f"layers_{body}.bin"}}
    _write(folder / "meta.json", json.dumps(meta))


def _card(tid: str, aid: str) -> dict:
    feats = {k: {"target": 1.0, "analog": 1.0, "z_diff": 0.0}
             for k in ("slope_p95_deg", "hi", "coherence", "hurst", "ridge_pct", "valley_pct")}
    return {"target_id": tid, "analog_id": aid, "rank": 1, "D": 0.5, "tie_group": 0, "features": feats,
            "similar": ["slope_p95_deg"], "different": [], "context_similar": ["coherence"], "context_different": [],
            "in_distance": ["slope_p95_deg", "hi", "hurst"], "context_features": ["coherence", "ridge_pct", "valley_pct"],
            "vertical_exaggeration": 4.0, "context": {"koppen_class": "BWh"}, "novelty": "new",
            "known_region_id": None, "refined": None,
            "analog_place": {"name": "Testshire, Testland", "admin1": "Testshire", "country": "Testland", "source": "t"},
            "mission_pct": {"landing": {"target": 90.0, "analog": 80.0, "limit_deg": 15.0, "source": "https://example.org/l"}, "driving": {"target": 100.0, "analog": 99.0, "limit_deg": 30.0, "source": "https://example.org/d"}}, "rotation_deg": 0.0,
            "files": {"target": f"terrain/{tid}/", "analog": f"terrain/{aid}/"}, "provenance": {}}


def _coverage_doc(body: str) -> dict:
    grid = [0] * (360 * 180)
    grid[0] = 2
    grid[1] = 1
    counts = {"0": grid.count(0), "1": grid.count(1), "2": grid.count(2)}
    doc = {"body": body, "res_deg": 1, "width": 360, "height": 180, "origin": [-180, 90],
           "classes": {"0": "out_of_reach", "1": "to_discover", "2": "unlocked"}, "grid": grid, "counts": counts,
           "source": "test"}
    if body == "mars":
        doc["notes"] = {"single_ctx_full_disk_rate": {}}
    return doc


@pytest.fixture()
def site(tmp_path: Path) -> Path:
    """A valid tree: target t (mars) with one analog a ranked for it."""
    root = tmp_path / "proj"
    data = root / "site" / "data"
    targets = {"targets": [{"id": "t", "body": "mars", "name": "T", "lat": 0.0, "lon": 0.0,
                            "thumbnail": "terrain/t/hillshade.png", "status": "ok", "landing_class": None,
                            "mission": None, "year": None, "outcome_note": None, "center_note": None,
                            "unlocked": True}]}
    _write(data / "targets.json", json.dumps(targets))
    rank = {"target_id": "t", "ranking": [{"rank": 1, "analog_id": "a", "D": 0.5, "tie_group": 0, "lat": 0.0,
                                           "lon": 0.0, "card": "cards/t__a.json",
                                           "analog_place": _card("t", "a")["analog_place"],
                                           "context": {"koppen_class": "BWh"}, "novelty": "new",
                                           "known_region_id": None, "refined": None}]}
    _write(data / "rankings" / "t.json", json.dumps(rank))
    _write(data / "cards" / "t__a.json", json.dumps(_card("t", "a")))
    _terrain(data, "t")
    _terrain(data, "a")
    _write(data / "bodies.json", json.dumps({"bodies": {"mars": {}}}))
    _write(data / "missions.json", json.dumps({"limits": {}}))
    _write(data / "validation.json", json.dumps({"v1.2": {}, "v1.3": {}, "v1.3_noise": {}}))
    _write(data / "viz.json", json.dumps({"vertical_exaggeration": 0.8}))
    for body in ("mars", "moon", "earth"):
        _write(data / "coverage" / f"{body}.json", json.dumps(_coverage_doc(body)))
    return root


def _run(root: Path, strict: bool = False) -> tuple[int, CS.Report]:
    rep = CS.check_site(root / "site" / "data", strict=strict)
    return CS._print(rep, root / "site" / "data", strict), rep


def test_valid_tree_passes(site: Path):
    code, rep = _run(site)
    assert code == 0 and rep.problems == []
    assert rep.counts == {"targets": 1, "rankings": 1, "cards": 1, "terrains": 2}


def test_wrong_height_size_is_a_problem(site: Path):
    (site / "site/data/terrain/a/height.bin").write_bytes(bytes(10))
    code, rep = _run(site)
    assert code == 1 and any("height.bin" in p for p in rep.problems)


def test_missing_card_is_a_problem(site: Path):
    (site / "site/data/cards/t__a.json").unlink()
    code, rep = _run(site)
    assert code == 1 and any("t__a.json" in p for p in rep.problems)


def test_in_distance_must_partition_the_features(site: Path):
    card_path = site / "site/data/cards/t__a.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card["context_features"] = ["coherence", "ridge_pct", "valley_pct", "hi"]  # hi in both lists
    card_path.write_text(json.dumps(card), encoding="utf-8")
    code, rep = _run(site)
    assert code == 1 and any("partition" in p for p in rep.problems)


def test_similar_outside_in_distance_is_a_problem(site: Path):
    card_path = site / "site/data/cards/t__a.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card["similar"] = ["coherence"]  # a context feature must not be in similar
    card_path.write_text(json.dumps(card), encoding="utf-8")
    code, rep = _run(site)
    assert code == 1 and any("outside in_distance" in p for p in rep.problems)


def test_vertical_exaggeration_range(site: Path):
    card_path = site / "site/data/cards/t__a.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card["vertical_exaggeration"] = 12.0
    card_path.write_text(json.dumps(card), encoding="utf-8")
    code, rep = _run(site)
    assert code == 1 and any("vertical_exaggeration" in p for p in rep.problems)


def test_missing_terrain_folder_and_missing_thumbnail(site: Path):
    import shutil

    shutil.rmtree(site / "site/data/terrain/a")
    code, rep = _run(site)
    assert code == 1 and any("terrain folder missing: terrain/a/" in p for p in rep.problems)


def test_missing_validation_block_is_a_problem(site: Path):
    _write(site / "site/data/validation.json", json.dumps({"v1.2": {}}))
    code, rep = _run(site)
    assert code == 1 and any("v1.3" in p for p in rep.problems)


def test_orphans_are_listed_not_deleted_and_strict_fails(site: Path):
    stray = site / "site/data/terrain/old_gone/height.bin"
    _write(stray, b"x" * 7)
    code, rep = _run(site)
    assert code == 0  # orphans are notes unless --strict
    assert any("orphan (not referenced): terrain/old_gone/height.bin (7 bytes)" in n for n in rep.notes)
    assert stray.exists()  # never deleted
    code_strict, _ = _run(site, strict=True)
    assert code_strict == 1


def test_sample_folder_is_never_read(site: Path):
    _write(site / "site/data/sample/cards/broken.json", "{not json")
    code, rep = _run(site)
    assert code == 0 and not any("broken" in n for n in rep.notes)


def test_main_returns_2_without_site_data(tmp_path: Path):
    assert CS.main(["--root", str(tmp_path)]) == 2


def test_coverage_grids_checked_and_counted(site: Path):
    """coverage/<body>.json: 360 x 180 values in 0/1/2 with counts that match; mars needs the notes block."""
    data = site / "site" / "data"
    for body in ("mars", "moon", "earth"):
        _write(data / "coverage" / f"{body}.json", json.dumps(_coverage_doc(body)))
    code, rep = _run(site)
    assert code == 0 and rep.problems == []
    doc = _coverage_doc("mars")
    doc["counts"]["2"] = 5  # wrong count
    _write(data / "coverage" / "mars.json", json.dumps(doc))
    code, rep = _run(site)
    assert code == 1 and any("counts do not match" in p for p in rep.problems)


def test_atlas_cells_need_three_twins_and_the_fields(site: Path):
    """atlas/mars_cells.json is a list of cells; each has the 10.13 fields and exactly three twins."""
    data = site / "site" / "data"
    twin = {"analog_id": "pool__p1", "D": 0.1, "tie_group": 0, "analog_place": None, "novelty": "new",
            "known_region_id": None, "context": None}
    cell = {"id": "mars_00001", "lat": 1.0, "lon": 2.0, "features": {}, "twins": [twin, twin, twin],
            "mission_pct": {"landing": None, "driving": None}}
    _write(data / "atlas" / "mars_cells.json", json.dumps([cell]))
    code, rep = _run(site)
    assert code == 0 and rep.problems == []
    cell["twins"] = [twin, twin]
    _write(data / "atlas" / "mars_cells.json", json.dumps([cell]))
    code, rep = _run(site)
    assert code == 1 and any("2 twins" in p for p in rep.problems)


def test_discoveries_counts_must_add_up(site: Path):
    """discoveries.json: unique_windows = windows listed = new + known_region + unclassified."""
    data = site / "site" / "data"
    doc = {"counts": {"unique_windows": 2, "new": 1, "known_region": 1, "unclassified": 0},
           "windows": [{"analog_id": "a"}, {"analog_id": "b"}]}
    _write(data / "discoveries.json", json.dumps(doc))
    code, rep = _run(site)
    assert code == 0 and rep.problems == []
    doc["counts"]["new"] = 2
    _write(data / "discoveries.json", json.dumps(doc))
    code, rep = _run(site)
    assert code == 1 and any("add to unique_windows" in p for p in rep.problems)


def test_null_mission_values_or_source_in_a_ranked_card_fail(site: Path):
    """A ranked card must carry target, analog and source for both landing and driving (no null values)."""
    card_path = site / "site/data/cards/t__a.json"
    base = json.loads(card_path.read_text(encoding="utf-8"))
    for kind, field in (("landing", "analog"), ("driving", "source"), ("landing", "target")):
        card = json.loads(json.dumps(base))
        card["mission_pct"][kind][field] = None
        card_path.write_text(json.dumps(card), encoding="utf-8")
        code, rep = _run(site)
        assert code == 1 and any(f"mission_pct.{kind}.{field} is null" in p for p in rep.problems), (kind, field)
    card_path.write_text(json.dumps(base), encoding="utf-8")
    code, rep = _run(site)
    assert code == 0 and rep.problems == []


def _query_table(data: Path, rows: int = 3, n_present: int = 2) -> None:
    """A valid P-Q table: one f32 column with an order index (2 present of 3), one text column with codes and a dictionary."""
    t = data / "query" / "tbl"
    _write(t / "x.f32", bytes(rows * 4))
    _write(t / "x.order.u32", bytes(n_present * 4))
    _write(t / "k.codes.u16", bytes(rows * 2))
    _write(t / "k.dict.json", json.dumps(["a", "b"]))
    manifest = {"schema": "analog.query/1", "table": "tbl", "rows": rows, "columns": [
        {"name": "x", "type": "f32", "missing": "NaN", "order": "x.order.u32", "n_present": n_present,
         "files": ["x.f32", "x.order.u32"]},
        {"name": "k", "type": "text", "missing": 65535, "order": None, "n_present": rows, "dict_size": 2,
         "files": ["k.codes.u16", "k.dict.json"]}]}
    _write(t / "manifest.json", json.dumps(manifest))


def test_valid_query_tables_pass_and_are_referenced(site: Path):
    data = site / "site" / "data"
    _query_table(data)
    code, rep = _run(site)
    assert code == 0 and rep.problems == []
    assert "query/tbl/x.f32" in rep.referenced and "query/tbl/k.dict.json" in rep.referenced


def test_query_file_with_the_wrong_size_is_a_problem(site: Path):
    data = site / "site" / "data"
    _query_table(data)
    _write(data / "query" / "tbl" / "x.f32", bytes(8))  # 2 values instead of 3
    code, rep = _run(site)
    assert code == 1 and any("query/tbl/x.f32" in p and "expected 12" in p for p in rep.problems)


def test_order_index_size_follows_n_present(site: Path):
    data = site / "site" / "data"
    _query_table(data)
    _write(data / "query" / "tbl" / "x.order.u32", bytes(12))  # 3 entries, n_present is 2
    code, rep = _run(site)
    assert code == 1 and any("x.order.u32" in p for p in rep.problems)


def test_missing_named_file_and_dictionary_count(site: Path):
    data = site / "site" / "data"
    _query_table(data)
    (data / "query" / "tbl" / "k.codes.u16").unlink()
    _write(data / "query" / "tbl" / "k.dict.json", json.dumps(["a", "b", "c"]))
    code, rep = _run(site)
    assert code == 1
    assert any("k.codes.u16" in p and "missing" in p for p in rep.problems)
    assert any("dictionary entries" in p for p in rep.problems)


def test_unnamed_query_file_is_an_orphan(site: Path):
    data = site / "site" / "data"
    _query_table(data)
    _write(data / "query" / "tbl" / "stray.f32", bytes(12))
    code, rep = _run(site)
    assert code == 0  # orphans are notes unless --strict
    assert any("orphan (not referenced): query/tbl/stray.f32" in n for n in rep.notes)
