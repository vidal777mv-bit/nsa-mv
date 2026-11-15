"""tools/check_ledger.py: rules R1-R6 on tiny synthetic ledgers (STANDARDS 10.14). Each violating ledger breaks one rule
once; the clean ledger passes all six. Each test writes its own temp ledger and template."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "tools"))
sys.path.insert(0, str(HERE / "pipelines"))

import build_ledger as BL  # noqa: E402
import check_ledger as CL  # noqa: E402

KEY = "abc123"
TEMPLATE = "AUC {{fact:v1.3:auc:f3}} on {{agg:n_targets}} targets\n"


def _rows() -> list[dict]:
    """A small clean ledger: a target (centre, feature with the current key, mission %), a region with a regional footprint,
    a validation AUC, the config subject with the current key, and an Earth window feature."""
    rows = [
        BL.fact("validation", "config_v1.3", "measure_key", KEY, footprint="global", kind="published",
                level="observation", source_id="config/measure.json", verified=True, produced_by="config/measure.json"),
        BL.fact("target", "t1", "centre_lat", 10.0, body="mars", footprint="point", kind="published",
                level="observation", source_url="https://example.org", verified=True, produced_by="config/sites.json"),
        BL.fact("target", "t1", "slope_p95_deg", 5.0, body="mars", unit="deg", scale_m=100, footprint="local",
                kind="derived", level="observation", source_id="ctx", produced_by="pipelines/build_measure.py"),
        BL.fact("target", "t1", "measure_key", KEY, body="mars", footprint="local", kind="derived",
                level="observation", scale_m=100, produced_by="pipelines/build_measure.py"),
        BL.fact("target", "t1", "mission_pct_landing", 99.5, body="mars", unit="percent", scale_m=100,
                footprint="local", kind="derived", level="observation", source_url="https://example.org/limit",
                produced_by="pipelines/mission_pct.py", comparison="reference", baseline_m=None),
        BL.fact("region", "r1", "radius_km", 50.0, footprint="regional", kind="published", level="interpretation",
                scale_m=50000, source_id="known", produced_by="config/known_analog_regions.json", verified=True),
        BL.fact("validation", "v1.3", "auc", 0.6948, footprint="regional", kind="derived", level="observation",
                scale_m=100, source_id="validation_v1.3", produced_by="pipelines/validate.py", verified=True),
        BL.fact("earth_window", "w1", "hi", 0.5, body="earth", footprint="local", kind="derived", level="observation",
                scale_m=100, source_id="nasadem", produced_by="pipelines/build_measure.py"),
    ]
    for i, r in enumerate(rows, start=1):
        r["fact_id"] = f"F{i:03d}"
    return rows


def _violations(tmp: Path, rows: list[dict], template: str = TEMPLATE) -> dict[str, list]:
    for i, r in enumerate(rows, start=1):
        r["fact_id"] = f"F{i:04d}"
    db = BL.write_ledger(tmp / "facts", rows)["db"]
    (tmp / "README.template.md").write_text(template, encoding="utf-8")
    con = duckdb.connect(str(db), read_only=True)
    try:
        return CL.run_rules(con, tmp)
    finally:
        con.close()


def _only(res: dict[str, list], failing: str) -> None:
    """Exactly the named rule has offending rows; every other rule has none."""
    assert len(res[failing]) >= 1, (failing, res)
    assert all(res[k] == [] for k in res if k != failing), res


def test_clean_ledger_passes_all_rules(tmp_path: Path):
    res = _violations(tmp_path / "clean", _rows())
    assert set(res) == {"R1", "R2", "R3", "R4", "R5", "R6"}
    assert all(rows == [] for rows in res.values()), res


def test_r1_mission_pct_without_reference_comparison_fails(tmp_path: Path):
    rows = _rows()
    for r in rows:
        if r["property"] == "mission_pct_landing":
            r["comparison"] = "compliance"  # the limit baseline is null: must be reference
    res = _violations(tmp_path / "r1", rows)
    _only(res, "R1")
    assert res["R1"][0][3] == "mission_pct_landing"


def test_r2_point_fact_on_a_region_subject_fails(tmp_path: Path):
    rows = _rows()
    rows.append(BL.fact("region", "r1", "town_centre", 1.0, footprint="point", kind="published", level="observation",
                        source_id="ne", produced_by="pipelines/earth_context.py", verified=True))
    _only(_violations(tmp_path / "r2", rows), "R2")


def test_r3_fact_without_source_or_producer_fails(tmp_path: Path):
    rows = _rows()
    rows.append(BL.fact("earth_window", "w2", "hi", 0.4, body="earth", footprint="local", kind="derived",
                        level="observation", scale_m=100, source_id=None, produced_by=None))
    _only(_violations(tmp_path / "r3", rows), "R3")


def test_r4_same_subject_property_scale_with_two_values_fails(tmp_path: Path):
    rows = _rows()
    for value in (0.51, 0.55):  # the same subject, property and scale with two values (the template uses auc, not this)
        rows.append(BL.fact("validation", "v1.3", "auc_ci_lo", value, footprint="regional", kind="derived",
                            level="observation", scale_m=100, source_id="validation_v1.3",
                            produced_by="pipelines/validate.py", verified=True))
    _only(_violations(tmp_path / "r4", rows), "R4")


def test_r5_placeholder_that_does_not_resolve_fails(tmp_path: Path):
    res = _violations(tmp_path / "r5", _rows(), template="AUC {{fact:v1.3:no_such_property:f3}}\n")
    _only(res, "R5")
    assert res["R5"][0][2] == "v1.3:no_such_property:f3"


def test_r6_feature_from_a_record_with_another_key_fails(tmp_path: Path):
    rows = _rows()
    rows.append(BL.fact("earth_window", "w2", "slope_p95_deg", 3.0, body="earth", unit="deg", scale_m=100,
                        footprint="local", kind="derived", level="observation", source_id="nasadem",
                        produced_by="pipelines/build_measure.py"))
    rows.append(BL.fact("earth_window", "w2", "measure_key", "stale-key", body="earth", footprint="local",
                        kind="derived", level="observation", scale_m=100, produced_by="pipelines/build_measure.py"))
    res = _violations(tmp_path / "r6", rows)
    _only(res, "R6")
    assert res["R6"][0][3] == "slope_p95_deg"


def test_main_exits_one_and_prints_the_failing_rule(tmp_path: Path, capsys):
    rows = _rows()
    rows.append(BL.fact("earth_window", "w2", "hi", 0.4, body="earth", footprint="local", kind="derived",
                        level="observation", scale_m=100, source_id=None, produced_by=None))
    for i, r in enumerate(rows, start=1):
        r["fact_id"] = f"F{i:04d}"
    tmp = tmp_path / "exit"
    db = BL.write_ledger(tmp / "facts", rows)["db"]
    (tmp / "README.template.md").write_text(TEMPLATE, encoding="utf-8")
    assert CL.main(["--root", str(tmp), "--db", str(db)]) == 1
    assert "R3 FAIL" in capsys.readouterr().out


def _f(subject_type: str, subject_id: str, prop: str, value, **kw) -> dict:
    return BL.fact(subject_type, subject_id, prop, value, footprint="local", kind="derived", level="observation",
                   scale_m=100, produced_by="test", **kw)


def _nasadem_rows() -> list[dict]:
    """Two pool windows (one NASADEM, one Copernicus), one excluded window, three Mars cells (gap, twin, not evaluable)
    and two sites (a Moon gap, a Mars twin)."""
    rows = [
        _f("earth_window", "pool__pool_00001", "role", "pool"),
        _f("earth_window", "pool__pool_00001", "sensor", "nasadem"),
        _f("earth_window", "pool__pool_02001", "role", "pool"),
        _f("earth_window", "pool__pool_02001", "sensor", "copdem"),
        _f("earth_window", "pool__pool_02002", "excluded_rule", "ice_share>=0.2"),
        _f("mars_cell", "m1", "earth_gap_nasadem", 1, body="mars"),
        _f("mars_cell", "m2", "earth_gap_nasadem", 0, body="mars"),
        _f("mars_cell", "m3", "earth_gap_nasadem", None, body="mars"),
        _f("target", "t_moon", "earth_gap_nasadem", 1, body="moon"),
        _f("target", "t_mars", "earth_gap_nasadem", 0, body="mars"),
    ]
    for i, r in enumerate(rows, start=1):
        r["fact_id"] = f"F{i:04d}"
    return rows


def test_pool_and_nasadem_gap_views_on_minimal_data(tmp_path: Path):
    db = BL.write_ledger(tmp_path / "facts", _nasadem_rows())["db"]
    con = duckdb.connect(str(db), read_only=True)
    try:
        got = {v: con.execute(f"SELECT value FROM {v}").fetchone()[0] for v in (
            "n_pool_windows_nasadem", "n_pool_windows_arctic", "n_pool_excluded", "mars_gap_cells_nasadem",
            "mars_gap_pct_nasadem", "mars_rehearsable_pct_nasadem", "moon_gap_targets_nasadem")}
    finally:
        con.close()
    assert got == {"n_pool_windows_nasadem": 1, "n_pool_windows_arctic": 1, "n_pool_excluded": 1,
                   "mars_gap_cells_nasadem": 1, "mars_gap_pct_nasadem": 50.0, "mars_rehearsable_pct_nasadem": 50.0,
                   "moon_gap_targets_nasadem": 1}


def test_gap_nasadem_facts_only_when_the_column_exists(capsys):
    no_col = {"neighbors_mars": [{"id": "m1", "gap": True}], "neighbors_targets": [{"id": "t1", "body": "moon", "gap": True}]}
    assert BL.gap_nasadem_rows(no_col) == []
    assert "gap_nasadem" in capsys.readouterr().out
    data = {"neighbors_mars": [{"id": "m1", "gap": True, "gap_nasadem": True}, {"id": "m2", "gap": False, "gap_nasadem": None}],
            "neighbors_targets": [{"id": "t1", "body": "moon", "gap": True, "gap_nasadem": False}]}
    got = {(r["subject_type"], r["subject_id"], r["property"]): r["value_num"] for r in BL.gap_nasadem_rows(data)}
    assert got == {("mars_cell", "m1", "earth_gap_nasadem"): 1.0, ("mars_cell", "m2", "earth_gap_nasadem"): None,
                   ("target", "t1", "earth_gap_nasadem"): 0.0}


def test_parquet_reads_optional_column_only_when_present(tmp_path: Path):
    with_col = tmp_path / "with.parquet"
    without = tmp_path / "without.parquet"
    con = duckdb.connect()
    con.execute(f"COPY (SELECT 'm1' AS id, true AS gap, false AS gap_nasadem) TO '{with_col.as_posix()}' (FORMAT PARQUET)")
    con.execute(f"COPY (SELECT 'm1' AS id, true AS gap) TO '{without.as_posix()}' (FORMAT PARQUET)")
    con.close()
    rows = BL._parquet(without, "id, gap", "id", optional=("gap_nasadem",))
    assert rows == [{"id": "m1", "gap": True}]
    rows = BL._parquet(with_col, "id, gap", "id", optional=("gap_nasadem",))
    assert rows == [{"id": "m1", "gap": True, "gap_nasadem": False}]
    assert BL._parquet(tmp_path / "absent.parquet", "id, gap", "id") is None


def test_excluded_windows_get_one_rule_fact_each(capsys):
    entries = [{"id": "pool_02001", "rule": "ice_share>=0.2", "value": 0.35, "threshold": 0.2},
               {"id": "pool__pool_02002", "rule": "bare_share_full<0.8"}]
    expect = [("pool__pool_02001", "excluded_rule", "ice_share>=0.2"),
              ("pool__pool_02002", "excluded_rule", "bare_share_full<0.8")]
    for shape in (entries, {"windows": entries}, {e["id"]: {k: v for k, v in e.items() if k != "id"} for e in entries}):
        rows = BL.excluded_rows({"excluded": shape})
        assert [(r["subject_id"], r["property"], r["value_text"]) for r in rows] == expect
    assert BL.excluded_rows({"excluded": None}) == []
    assert "excluded facts skipped" in capsys.readouterr().out
    with pytest.raises(ValueError):
        BL.excluded_rows({"excluded": [{"id": "pool_02003"}]})


def test_arctic_probe_comparison_is_retired():
    assert not hasattr(BL, "arctic_rows")
