"""Tests for pipelines/export_query.py (STANDARDS 10.14 P-Q): round-trip, order arrays, binary-search range queries."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "pipelines"))

import export_query as EQ  # noqa: E402

SEED = 20261114


def _synthetic(n: int = 60, seed: int = SEED) -> tuple[list, dict]:
    rng = np.random.default_rng(seed)
    f = rng.normal(size=n).astype("<f4").astype(float)
    f[::9] = np.nan  # missing values
    flags = [bool(x) if i % 7 else None for i, x in enumerate(rng.integers(0, 2, size=n))]
    words = ["alpha", "beta", "gamma", None]
    names = [words[int(i)] for i in rng.integers(0, 4, size=n)]
    cols = [("value", "f32", "u", "value"), ("flag", "bool", None, "flag"), ("name", "text", None, "name")]
    data = {"value": [None if np.isnan(x) else float(x) for x in f], "flag": flags, "name": names}
    return cols, data


def test_round_trip_write_then_read_equals_source(tmp_path):
    cols, data = _synthetic()
    EQ.write_table(tmp_path, "t", cols, data, 60, ["synthetic"], {"schema": "test"})
    back = EQ.read_table(tmp_path / "t")
    assert back["manifest"]["rows"] == 60
    src_f = np.array([np.nan if v is None else v for v in data["value"]], dtype="<f4")
    assert np.array_equal(back["columns"]["value"], src_f, equal_nan=True)
    assert back["columns"]["name"] == data["name"]
    src_b = np.array([np.nan if v is None else (1.0 if v else 0.0) for v in data["flag"]], dtype="<f4")
    assert np.array_equal(back["columns"]["flag"], src_b, equal_nan=True)


def test_order_arrays_are_sorted_and_hold_exactly_the_present_rows(tmp_path):
    cols, data = _synthetic()
    EQ.write_table(tmp_path, "t", cols, data, 60, ["synthetic"], {"schema": "test"})
    folder = tmp_path / "t"
    vals = np.fromfile(folder / "value.f32", dtype="<f4")
    order = EQ.order_of(folder, "value")
    assert np.all(np.diff(vals[order]) >= 0)
    present = np.flatnonzero(~np.isnan(vals))
    assert sorted(order.tolist()) == present.tolist()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    col = next(c for c in manifest["columns"] if c["name"] == "value")
    assert col["n_present"] == present.size and col["order"] == "value.order.u32"


def test_order_ties_are_stable_by_row(tmp_path):
    cols = [("v", "f32", None, "v")]
    EQ.write_table(tmp_path, "t", cols, {"v": [2.0, 1.0, 2.0, 1.0, 2.0]}, 5, ["s"], {})
    order = EQ.order_of(tmp_path / "t", "v")
    assert order.tolist() == [1, 3, 0, 2, 4]


def test_range_query_by_binary_search_equals_direct_filter(tmp_path):
    cols, data = _synthetic(200, seed=SEED + 1)
    EQ.write_table(tmp_path, "t", cols, data, 200, ["synthetic"], {})
    folder = tmp_path / "t"
    vals = np.fromfile(folder / "value.f32", dtype="<f4")
    rng = np.random.default_rng(SEED)
    for _ in range(50):
        lo, hi = sorted(rng.normal(size=2).tolist())
        got = EQ.range_rows(folder, "value", lo, hi)
        lo32, hi32 = np.float32(lo), np.float32(hi)
        want = np.flatnonzero((vals >= lo32) & (vals <= hi32))
        assert got.tolist() == want.tolist()


def test_text_missing_and_dict_are_sorted(tmp_path):
    cols = [("name", "text", None, "name")]
    EQ.write_table(tmp_path, "t", cols, {"name": ["b", None, "a", "b"]}, 4, ["s"], {})
    folder = tmp_path / "t"
    codes = np.fromfile(folder / "name.codes.u16", dtype="<u2")
    assert codes.tolist() == [1, 65535, 0, 1]
    assert json.loads((folder / "name.dict.json").read_text(encoding="utf-8")) == ["a", "b"]


def test_write_refuses_length_mismatch(tmp_path):
    with pytest.raises(ValueError):
        EQ.write_table(tmp_path, "t", [("v", "f32", None, "v")], {"v": [1.0, 2.0]}, 3, ["s"], {})


def _exported_root():
    root = HERE / "site" / "data" / "query"
    return root if (root / "twins" / "manifest.json").exists() else None


@pytest.mark.skipif(_exported_root() is None, reason="site/data/query not exported yet")
def test_exported_site_tables_read_back_and_fit_the_budget():
    root = _exported_root()
    total = 0
    for name in ("targets", "mars_cells", "earth_windows", "twins"):
        folder = root / name
        total += sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
        back = EQ.read_table(folder)
        assert back["manifest"]["rows"] == len(next(iter(back["columns"].values())))
    assert total < 2_000_000
    tw = root / "twins"
    D = np.fromfile(tw / "D.f32", dtype="<f4")
    rows = EQ.range_rows(tw, "D", 0.0, 0.1)
    assert rows.tolist() == np.flatnonzero(D <= np.float32(0.1)).tolist()


def _tables_from(tmp_path, cols, data, n):
    EQ.write_table(tmp_path, "t", cols, data, n, ["synthetic"], {})
    return {"t": EQ.read_table(tmp_path / "t")}


def test_evaluate_operators_and_null_never_matches(tmp_path):
    cols = [("x", "f32", None, "x"), ("flag", "bool", None, "flag"), ("name", "text", None, "name")]
    data = {"x": [1.0, None, 5.0, 10.0], "flag": [True, False, None, True],
            "name": ["new", "known_region", None, "new"]}
    tables = _tables_from(tmp_path, cols, data, 4)

    def rows(conds):
        return EQ.evaluate(tables, {"table": "t", "all": conds}).tolist()

    assert rows([{"col": "x", "op": "ge", "value": 5}]) == [2, 3]
    assert rows([{"col": "x", "op": "lt", "value": 5}]) == [0]
    assert rows([{"col": "x", "op": "ne", "value": 5}]) == [0, 3]
    assert rows([{"col": "x", "op": "in", "value": [1, 10]}]) == [0, 3]
    assert rows([{"col": "flag", "op": "eq", "value": 1}]) == [0, 3]
    assert rows([{"col": "name", "op": "eq", "value": "new"}]) == [0, 3]
    assert rows([{"col": "name", "op": "ne", "value": "new"}]) == [1]
    assert rows([{"col": "name", "op": "in", "value": ["known_region", "x"]}]) == [1]
    assert rows([{"col": "name", "op": "eq", "value": "new"}, {"col": "x", "op": "ge", "value": 5}]) == [3]


def test_evaluate_refuses_unknown_column_op_and_table(tmp_path):
    tables = _tables_from(tmp_path, [("x", "f32", None, "x")], {"x": [1.0]}, 1)
    with pytest.raises(ValueError):
        EQ.evaluate(tables, {"table": "t", "all": [{"col": "y", "op": "eq", "value": 1}]})
    with pytest.raises(ValueError):
        EQ.evaluate(tables, {"table": "t", "all": [{"col": "x", "op": "like", "value": 1}]})
    with pytest.raises(ValueError):
        EQ.evaluate(tables, {"table": "nope", "all": []})


def test_preset_questions_have_unique_ids_and_valid_specs():
    ids = [q["id"] for q in EQ.QUESTIONS]
    assert len(ids) == len(set(ids)) == 5
    for q in EQ.QUESTIONS:
        assert q["filter"]["table"] in ("targets", "mars_cells", "earth_windows", "twins")
        assert all(c["op"] in EQ.OPS for c in q["filter"]["all"])


def _neighbors_fixture(root: Path):
    """Synthetic neighbours parquet (3 queries per table, 4 Earth windows) with every column build_tables reads."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    nb_dir = root / "neighbors"
    nb_dir.mkdir(parents=True)
    twins = {"twin_row": [[0, 1]] * 3, "twin_id": [["a", "b"]] * 3, "twin_D": [[0.1, 0.2]] * 3}

    def table(cols, n, extra):
        data = {name: (["x"] * n if ctype == "text" else [True] * n if ctype == "bool" else [1.0] * n)
                for name, ctype, _, _ in cols}
        data.update(extra)
        return data

    tgt = table(EQ.TARGET_COLS, 3, {**twins, "threshold": [0.5] * 3, "body": ["earth"] * 3,
                                    "d_nearest_nasadem": [2.0, 0.1, None], "gap_nasadem": [True, False, None]})
    mars = table(EQ.MARS_COLS, 3, {**twins, "threshold": [0.5] * 3, "body": ["mars"] * 3,
                                   "d_nearest_nasadem": [2.0, 0.1, None], "gap_nasadem": [True, False, None]})
    earth = table(EQ.EARTH_COLS, 4, {"sensor": ["nasadem", "copdem", "nasadem", "copdem"]})
    for name, data in (("targets", tgt), ("mars_cells", mars), ("earth_windows", earth)):
        pq.write_table(pa.table(data), nb_dir / f"{name}.parquet")
    return SimpleNamespace(derived=root)


def test_nasadem_columns_reach_the_export_tables(tmp_path):
    names = {n: [c[0] for c in cols] for n, cols in
             (("targets", EQ.TARGET_COLS), ("mars_cells", EQ.MARS_COLS), ("earth_windows", EQ.EARTH_COLS))}
    assert {"d_nearest_nasadem", "gap_nasadem"} <= set(names["targets"])
    assert {"d_nearest_nasadem", "gap_nasadem"} <= set(names["mars_cells"])
    assert "sensor" in names["earth_windows"]
    built = EQ.build_tables(_neighbors_fixture(tmp_path))
    assert built["targets"]["data"]["gap_nasadem"] == [True, False, None]
    assert built["mars_cells"]["data"]["d_nearest_nasadem"] == [2.0, 0.1, None]
    assert built["earth_windows"]["data"]["sensor"] == ["nasadem", "copdem", "nasadem", "copdem"]
    out = tmp_path / "out"
    EQ.write_table(out, "targets", EQ.TARGET_COLS, built["targets"]["data"], 3, ["synthetic"], {})
    back = EQ.read_table(out / "targets")["columns"]
    assert np.allclose(back["d_nearest_nasadem"][:2], [2.0, 0.1])
    assert np.isnan(back["d_nearest_nasadem"][2]) and back["gap_nasadem"][0] == 1.0
    assert np.isnan(back["gap_nasadem"][2])


@pytest.mark.skipif(_exported_root() is None, reason="site/data/query not exported yet")
def test_questions_json_counts_match_the_parquet_source():
    """Independent check: the stored row counts equal the counts computed from the neighbours parquet."""
    import pyarrow.parquet as pq

    root = _exported_root()
    stored = json.loads((root / "questions.json").read_text(encoding="utf-8"))["questions"]
    by_id = {q["id"]: q for q in stored}
    assert set(by_id) == {q["id"] for q in EQ.QUESTIONS}
    nb = HERE / "data" / "derived" / "neighbors"
    mc = pq.read_table(nb / "mars_cells.parquet").to_pydict()
    assert by_id["mars_no_twin"]["rows"] == sum(1 for g in mc["gap"] if g)
    ew = pq.read_table(nb / "earth_windows.parquet").to_pydict()
    assert by_id["new_cold_desert_twins"]["rows"] == sum(
        1 for n, k in zip(ew["novelty"], ew["koppen_code"]) if n == "new" and k == 5)
    tg = pq.read_table(nb / "targets.parquet").to_pydict()
    assert by_id["artemis_no_twin"]["rows"] == sum(
        1 for m, g in zip(tg["mission"], tg["gap"]) if m == "Artemis III (candidate region)" and g)
    assert all(q["rows"] <= q["table_rows"] for q in stored)
