"""tools/export_site_facts.py: figures come only from ledger views and must agree with discoveries.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "tools"))

import export_site_facts as EF  # noqa: E402


def _ledger(tmp: Path, drop: str | None = None, places_new: int = 5) -> Path:
    p = tmp / "facts.duckdb"
    con = duckdb.connect(str(p))
    con.execute("CREATE TABLE facts (subject_type VARCHAR, subject_id VARCHAR, body VARCHAR, property VARCHAR, "
                "value_num DOUBLE, value_text VARCHAR)")
    con.execute("INSERT INTO facts VALUES ('target','m1','moon','earth_gap',1,NULL), ('target','m1','moon','name',NULL,'Moon one')")
    values = {view: 1.0 for view, *_ in EF.FIGURES.values()}
    values["n_new_places"] = float(places_new)
    values["n_discovery_places"] = 7.0
    values["n_known_places"] = 2.0
    for view, v in values.items():
        if view != drop:
            con.execute(f"CREATE VIEW {view} AS SELECT {v} AS value")
    con.close()
    return p


def _disc(tmp: Path) -> Path:
    p = tmp / "discoveries.json"
    p.write_text(json.dumps({"place_counts": {"unique_places": 7, "new": 5, "known_region": 2}}), encoding="utf-8")
    return p


def test_explain_must_cover_exactly_the_configured_features(tmp_path: Path):
    measure = tmp_path / "measure.json"
    measure.write_text(json.dumps({"features": {"a": {"in_distance": True}, "b": {"in_distance": False}}}), encoding="utf-8")
    good = tmp_path / "ex.json"
    good.write_text(json.dumps({"features": {"a": {"label": "A"}, "b": {"label": "B"}}}), encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"features": {"a": {"label": "A"}}}), encoding="utf-8")
    out = tmp_path / "explain.json"
    assert EF.export_explain(good, measure, out) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["features"]["a"]["in_distance"] is True
    assert EF.export_explain(bad, measure, tmp_path / "x.json") == 1


def test_clean_ledger_writes_every_figure_with_its_view(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(EF, "export_explain", lambda: 0)
    out = tmp_path / "facts.json"
    assert EF.main(_ledger(tmp_path), out, _disc(tmp_path)) == 0
    figs = json.loads(out.read_text(encoding="utf-8"))["figures"]
    assert set(figs) == set(EF.FIGURES)
    assert figs["new_twin_places"]["display"] == "5" and figs["new_twin_places"]["ledger_view"] == "n_new_places"
    assert figs["moon_gap_sites"]["ids"] == ["m1"]


def test_missing_view_is_refused(tmp_path: Path):
    assert EF.main(_ledger(tmp_path, drop="mars_gap_pct"), tmp_path / "f.json", _disc(tmp_path)) == 1


def test_ledger_and_discoveries_must_agree(tmp_path: Path):
    assert EF.main(_ledger(tmp_path, places_new=4), tmp_path / "f.json", _disc(tmp_path)) == 1


def test_new_sensor_gap_and_exclusion_figures_read_their_views(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(EF, "export_explain", lambda: 0)
    out = tmp_path / "facts.json"
    assert EF.main(_ledger(tmp_path), out, _disc(tmp_path)) == 0
    figs = json.loads(out.read_text(encoding="utf-8"))["figures"]
    for key, view in (("earth_places_nasadem", "n_pool_windows_nasadem"), ("earth_places_arctic", "n_pool_windows_arctic"),
                      ("earth_places_excluded", "n_pool_excluded"), ("mars_gap_places_nasadem", "mars_gap_cells_nasadem"),
                      ("mars_gap_pct_nasadem", "mars_gap_pct_nasadem"), ("mars_rehearsable_pct_nasadem", "mars_rehearsable_pct_nasadem"),
                      ("moon_gap_sites_nasadem", "moon_gap_targets_nasadem")):
        assert figs[key]["ledger_view"] == view and figs[key]["definition"], key


def test_missing_new_view_is_refused(tmp_path: Path):
    assert EF.main(_ledger(tmp_path, drop="n_pool_excluded"), tmp_path / "f.json", _disc(tmp_path)) == 1


def test_pool_definitions_name_both_sensors_and_no_old_text():
    defs = [f[3] for f in EF.FIGURES.values()]
    assert not any("no poles" in d or "NASADEM, 56 S to 60 N" in d for d in defs)
    for key in ("earth_places_searched", "moon_gap_sites"):
        assert "84 N" in EF.FIGURES[key][3], key
