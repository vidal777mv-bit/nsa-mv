"""pipelines/refine_search.py: the 5 x 5 grid of 2 km offsets (STANDARDS 10.13). Unit tests only: no STAC access."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "pipelines"))

import _common  # noqa: E402
import refine_search as RS  # noqa: E402


def test_grid_is_five_by_five_at_two_km_from_minus_four_to_four():
    assert RS.OFFSETS_KM == (-4.0, -2.0, 0.0, 2.0, 4.0)
    assert len(RS.OFFSETS_KM) == 5 and RS.STEP_KM == 2.0 and RS.CLIP_HALF_KM == 8.5


def test_shifted_centre_moves_the_stated_distance():
    lat, lon = 30.0, 10.0
    slat, slon = RS.shifted_centre(lat, lon, 4.0, -2.0)
    assert slat == pytest.approx(lat - 2.0 / 111.19493, rel=1e-9)
    # 4 km east at latitude 30 is 4 / (111.19493 * cos 30) degrees of longitude
    assert slon == pytest.approx(lon + 4.0 / (111.19493 * math.cos(math.radians(lat))), rel=1e-9)
    assert RS.shifted_centre(lat, lon, 0.0, 0.0) == pytest.approx((lat, lon))


# --- candidates that are not NASADEM (synthetic: refine_candidate and candidate_clip are replaced, no STAC) ---

NOISE = {"flat_slope_p95_deg": 2.0, "classes": {"flat": {"p95": 0.1}, "rugged": {"p95": 0.2}}}
CFG = {"version": "1.3", "grid": {"L_m": 100.0, "R_m": 4000.0}, "tpi": {}, "features": {"hurst": {"lags_px": [1, 2]}},
       "distance": {"min_shared_features": 1}}


def _setup(tmp_path, pool):
    """Target 'tgt' with a frozen ranking of (pool_id, D, sensor or None). None = measure record without a sensor field."""
    paths = RS.make_paths(tmp_path, False)
    RS.write_json(paths.stage("ranking") / "tgt.json", {"body": "mars", "ranking": [
        {"rank": i, "analog_id": pid, "D": d, "lat": 30.0 + i * 0.1, "lon": 10.0, "near_known_analog": False}
        for i, (pid, d, _) in enumerate(pool, start=1)]})
    RS.write_json(paths.stage("measure") / "tgt.json", {"status": "ok", "features": {"slope_p95_deg": 1.0}})
    for pid, _, sensor in pool:
        rec = {"id": pid, "kind": "pool", "status": "ok"}
        if sensor is not None:
            rec["sensor"] = sensor
            rec["source_id"] = "cop_dem_glo30" if sensor == "copdem" else "nasadem"
        RS.write_json(paths.stage("measure") / f"{pid}.json", rec)
    return paths


def _patch(monkeypatch, refined_d):
    """Replace the STAC clip and the 25-offset measure. refined_d: pool_id -> D at the kept offset."""
    calls: list[str] = []

    def fake_clip(paths, pool_id, lat, lon, log):
        calls.append(pool_id)
        return RS.refine_dir(paths) / "clips" / f"{pool_id}.tif"

    def fake_refine(clip, lat, lon, target_feats, cfg):
        d = refined_d[clip.stem]
        best = {"dx_km": 2.0, "dy_km": -2.0, "D": d, "lat": lat + 0.02, "lon": lon + 0.02,
                "features": {"slope_p95_deg": 1.0}, "n_valid": 10, "coverage": 1.0}
        return {"best": best, "D0_clip": d + 0.1, "grid": []}

    monkeypatch.setattr(RS, "candidate_clip", fake_clip)
    monkeypatch.setattr(RS, "refine_candidate", fake_refine)
    monkeypatch.setattr(RS, "provenance_block", lambda *a, **k: {})
    return calls


def _run(paths):
    log = RS.RunLog(RS.refine_dir(paths), "refine_search")
    RS.run_target(paths, "tgt", CFG, NOISE, log, {})
    return RS.load_json(RS.refine_dir(paths) / "tgt.json")


def test_copdem_candidate_is_not_refined_and_keeps_its_pool_d(tmp_path, monkeypatch):
    paths = _setup(tmp_path, [("pool__pool_00001", 0.50, "copdem"), ("pool__pool_00002", 0.70, "nasadem")])
    calls = _patch(monkeypatch, {"pool__pool_00002": 0.60})
    out = _run(paths)
    assert calls == ["pool__pool_00002"]  # the COPDEM candidate is never clipped
    c = {r["pool_id"]: r for r in out["ranking"]}["pool__pool_00001"]
    assert c["D"] == 0.50 and c["D_before"] == 0.50 and c["rank_before"] == 1
    assert c["lat"] == pytest.approx(30.1) and c["refined_offset_km"] is None
    assert c["sensor"] == "copdem" and c["source_id"] == "cop_dem_glo30"
    assert c["refine_skipped"] == "no NASADEM above 60N"
    assert not (RS.refine_dir(paths) / "measure" / "tgt__pool__pool_00001.json").exists()
    assert out["n_refined"] == 1
    # not refined: plain pool id, which resolves to the measure-stage record (no refine/measure file for it)
    assert c["analog_id"] == "pool__pool_00001"
    assert _common.window_record_path(paths, c["analog_id"]) == paths.stage("measure") / "pool__pool_00001.json"
    assert _common.window_record_path(paths, c["analog_id"]).exists()


def test_mixed_ranking_orders_by_d_and_tie_groups(tmp_path, monkeypatch):
    # sorted D: 0.45 (nasadem, no sensor field), 0.50 (copdem, kept), 0.90 (nasadem). p95 flat = 0.1:
    # 0.50 - 0.45 < 0.1 joins the first group; 0.90 - 0.45 >= 0.1 starts a new one.
    paths = _setup(tmp_path, [("pool__pool_00001", 0.50, "copdem"), ("pool__pool_00002", 0.70, "nasadem"),
                              ("pool__pool_00003", 0.40, None)])
    calls = _patch(monkeypatch, {"pool__pool_00002": 0.90, "pool__pool_00003": 0.45})
    out = _run(paths)
    assert sorted(calls) == ["pool__pool_00002", "pool__pool_00003"]
    r = out["ranking"]
    assert [x["pool_id"] for x in r] == ["pool__pool_00003", "pool__pool_00001", "pool__pool_00002"]
    assert [x["rank"] for x in r] == [1, 2, 3]
    assert [x["tie_group"] for x in r] == [0, 0, 1]
    assert [x["D"] for x in r] == [0.45, 0.50, 0.90]
    assert [x["sensor"] for x in r] == ["nasadem", "copdem", "nasadem"]
    assert [x["refine_skipped"] for x in r] == [None, "no NASADEM above 60N", None]
    assert out["n_refined"] == 2


def test_all_nasadem_candidates_are_refined_as_before(tmp_path, monkeypatch):
    paths = _setup(tmp_path, [("pool__pool_00001", 0.30, "nasadem"), ("pool__pool_00002", 0.60, None)])
    calls = _patch(monkeypatch, {"pool__pool_00001": 0.80, "pool__pool_00002": 0.20})
    out = _run(paths)
    assert calls == ["pool__pool_00001", "pool__pool_00002"]
    assert [x["pool_id"] for x in out["ranking"]] == ["pool__pool_00002", "pool__pool_00001"]
    for x in out["ranking"]:
        assert x["refine_skipped"] is None and x["source_id"] == "nasadem" and x["sensor"] == "nasadem"
        assert x["refined_offset_km"] == [2.0, -2.0]
        assert (RS.refine_dir(paths) / "measure" / f"{x['analog_id']}.json").exists()
    assert out["n_refined"] == 2


def test_candidate_sensor_reads_the_record_and_defaults_to_nasadem(tmp_path):
    paths = _setup(tmp_path, [("pool__pool_00001", 0.5, "copdem"), ("pool__pool_00002", 0.6, None)])
    assert RS.candidate_sensor(paths, "pool__pool_00001") == ("copdem", "cop_dem_glo30")
    assert RS.candidate_sensor(paths, "pool__pool_00002") == ("nasadem", "nasadem")
    assert RS.candidate_sensor(paths, "pool__pool_99999") == ("nasadem", "nasadem")
