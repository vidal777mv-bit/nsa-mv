"""Tests for pipelines/pool_rules.py: one synthetic case per rule, plus idempotence and NASADEM field preservation.

All synthetic. The NASADEM index has 2,000 rows (as the real pool), so the Arctic ids are pool_02001.. as in production.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "pipelines"))

import pool_rules as pr  # noqa: E402

RULES = pr.load_rules()
ICE_MAX = RULES["ice_share_max"]
BARE_MIN = RULES["bare_share_min"]
N_NASADEM = 2000


def _nasadem_index(n=N_NASADEM):
    return [{"id": f"pool_{i:05d}", "lat": -30.0 + (i % 50) * 0.5, "lon": 10.0 + (i % 40) * 0.5,
             "worldcover_share": 0.95, "near_known_analog": False,
             "path": f"data/raw/earth/pool/pool_{i:05d}.tif", "valid_fraction": 1.0}
            for i in range(1, n + 1)]


def _arctic_cand(n, lat=70.0, lon=-40.0):
    return {"id": f"arc_{n:05d}", "lat": lat, "lon": lon, "worldcover_share": 1.0}


def _shares_for(index, cand, bare=1.0, ice=0.0):
    out = {}
    for r in index:
        out[r["id"]] = {"lat": r["lat"], "lon": r["lon"], "bare_share_full": bare, "ice_share": ice}
    for c in cand:
        out[pr.arctic_pool_id(c["id"], len(index))] = {"lat": c["lat"], "lon": c["lon"],
                                                       "bare_share_full": bare, "ice_share": ice}
    return out


def _clip(cid, vf=1.0):
    return {cid: {"id": cid, "ok": True, "valid_fraction": vf}}


FAR_ANALOG = [{"lat": -60.0, "lon": 0.0}]  # a known analog far from every synthetic window


def _apply(index, shares, cand, clip_log, tmp_root, analogs=FAR_ANALOG):
    arctic_dir = tmp_root / "data/raw/earth/arctic_probe"
    arctic_dir.mkdir(parents=True, exist_ok=True)
    for c in cand:
        (arctic_dir / f"{c['id']}.tif").write_bytes(b"x")
    return pr.apply_rows(index, shares, cand, clip_log, list(analogs), RULES, arctic_dir, tmp_root)


def test_load_rules_reads_config_values():
    cfg = json.loads(pr.CONFIG.read_text(encoding="utf-8"))
    assert RULES["ice_share_max"] == cfg["ice_share_max"] == 0.2
    assert RULES["bare_share_min"] == cfg["bare_share_min"] == 0.8
    assert RULES["bare_classes"] == (60, 70, 100)
    assert RULES["ice_class"] == 70
    assert RULES["known_analog_exclusion_km"] == 25.0


def test_rule_ice_share_at_threshold_excludes_and_below_is_kept(tmp_path):
    idx = _nasadem_index()
    cand = [_arctic_cand(1), _arctic_cand(2)]
    shares = _shares_for(idx, cand)
    shares["pool_00001"]["ice_share"] = ICE_MAX             # exactly at the threshold: excluded (>=)
    shares["pool_02001"]["ice_share"] = ICE_MAX - 1e-4      # just below: kept
    clip = {**_clip("arc_00001"), **_clip("arc_00002")}
    rows, excl = _apply(idx, shares, cand, clip, tmp_path)
    by = {r["id"]: r for r in rows}
    assert by["pool_00001"]["excluded"]["rule"] == "ice_share"
    assert by["pool_00001"]["excluded"]["threshold"] == ICE_MAX
    assert by["pool_02001"]["excluded"] is None
    assert [e["id"] for e in excl] == ["pool_00001"]


def test_rule_bare_share_below_threshold_excludes_and_at_threshold_is_kept(tmp_path):
    idx = _nasadem_index()
    cand = [_arctic_cand(1), _arctic_cand(2)]
    shares = _shares_for(idx, cand)
    shares["pool_00002"]["bare_share_full"] = BARE_MIN - 0.01   # below: excluded
    shares["pool_02002"]["bare_share_full"] = BARE_MIN          # equal: kept (strict <)
    clip = {**_clip("arc_00001"), **_clip("arc_00002")}
    rows, _ = _apply(idx, shares, cand, clip, tmp_path)
    by = {r["id"]: r for r in rows}
    assert by["pool_00002"]["excluded"]["rule"] == "bare_share_full"
    assert by["pool_02002"]["excluded"] is None


def test_arctic_ids_are_2000_plus_n(tmp_path):
    assert pr.arctic_pool_id("arc_00001", 2000) == "pool_02001"
    assert pr.arctic_pool_id("arc_00065", 2000) == "pool_02065"
    idx = _nasadem_index()
    cand = [_arctic_cand(7), _arctic_cand(1)]
    shares = _shares_for(idx, cand)
    rows, _ = _apply(idx, shares, cand, {**_clip("arc_00007"), **_clip("arc_00001")}, tmp_path)
    ids = [r["id"] for r in rows]
    assert ids[:2] == ["pool_00001", "pool_00002"]
    assert ids[N_NASADEM:] == ["pool_02001", "pool_02007"]
    arc7 = next(r for r in rows if r["id"] == "pool_02007")
    assert arc7["probe_id"] == "arc_00007"
    assert arc7["path"] == "data/raw/earth/arctic_probe/arc_00007.tif"
    assert arc7["source_id"] == "cop_dem_glo30" and arc7["sensor"] == "copdem"
    assert arc7["worldcover_share"] == 1.0


def test_apply_is_idempotent(tmp_path):
    idx = _nasadem_index()
    cand = [_arctic_cand(1), _arctic_cand(2, lat=82.0, lon=-60.0)]
    shares = _shares_for(idx, cand, bare=0.9, ice=0.05)
    shares["pool_00003"]["ice_share"] = 0.5
    clip = {**_clip("arc_00001"), **_clip("arc_00002", vf=0.95)}
    analogs = [{"lat": 70.0, "lon": -40.0}]
    rows1, excl1 = _apply(idx, shares, cand, clip, tmp_path, analogs=analogs)
    dump1 = json.dumps(rows1, indent=1, ensure_ascii=False)
    # the second run starts from the first run's output (NASADEM rows now carry the new fields as well)
    rows2, excl2 = _apply(rows1, shares, cand, clip, tmp_path, analogs=analogs)
    assert json.dumps(rows2, indent=1, ensure_ascii=False) == dump1
    assert excl2 == excl1


def test_nasadem_rows_keep_all_original_fields(tmp_path):
    idx = _nasadem_index()
    idx[0]["extra_field"] = "kept"
    cand = [_arctic_cand(1)]
    shares = _shares_for(idx, cand, bare=0.85, ice=0.1)
    rows, _ = _apply(idx, shares, cand, _clip("arc_00001"), tmp_path)
    nas = {r["id"]: r for r in rows if "probe_id" not in r}
    assert len(nas) == N_NASADEM
    for orig in idx:
        new = nas[orig["id"]]
        for k, v in orig.items():
            assert new[k] == v, (orig["id"], k)
        assert new["bare_share_full"] == 0.85 and new["ice_share"] == 0.1
        assert "excluded" in new
    assert nas["pool_00001"]["extra_field"] == "kept"


def test_near_known_analog_within_25_km(tmp_path):
    # at lat 70 one degree of longitude is about 38 km; 0.2 deg is about 7.6 km (near), 0.3 deg about 11.4 km (near),
    # 10 deg away is far
    analog = [{"lat": 70.0, "lon": 0.0}]
    assert pr.near_known(70.0, 0.2, analog, 25.0) is True
    assert pr.near_known(70.0, 10.0, analog, 25.0) is False
    idx = _nasadem_index()
    cand = [_arctic_cand(1, lat=70.0, lon=0.2), _arctic_cand(2, lat=70.0, lon=0.3)]
    shares = _shares_for(idx, cand)
    rows, _ = _apply(idx, shares, cand, {**_clip("arc_00001"), **_clip("arc_00002")}, tmp_path, analogs=analog)
    by = {r["id"]: r for r in rows}
    assert by["pool_02001"]["near_known_analog"] is True
    assert by["pool_02002"]["near_known_analog"] is True
    far = [_arctic_cand(1, lat=70.0, lon=10.0)]
    rows_far, _ = _apply(idx, _shares_for(idx, far), far, _clip("arc_00001"), tmp_path, analogs=analog)
    assert next(r for r in rows_far if r["id"] == "pool_02001")["near_known_analog"] is False


def test_missing_clip_is_no_clip(tmp_path):
    idx = _nasadem_index()
    cand = [_arctic_cand(1), _arctic_cand(2)]
    shares = _shares_for(idx, cand)
    # arc_00001: clip_log entry but no .tif on disk; arc_00002: .tif present but no clip_log entry
    arctic_dir = tmp_path / "data/raw/earth/arctic_probe"
    arctic_dir.mkdir(parents=True)
    (arctic_dir / "arc_00002.tif").write_bytes(b"x")
    rows, excl = pr.apply_rows(idx, shares, cand, _clip("arc_00001"), FAR_ANALOG, RULES, arctic_dir, tmp_path)
    by = {r["id"]: r for r in rows}
    assert by["pool_02001"]["excluded"]["rule"] == "no_clip"
    assert by["pool_02002"]["excluded"]["rule"] == "no_clip"
    assert by["pool_02002"]["valid_fraction"] is None
    assert {e["id"] for e in excl if e["rule"] == "no_clip"} == {"pool_02001", "pool_02002"}


def test_backup_is_written_once_per_day(tmp_path):
    idx_path = tmp_path / "index.json"
    idx_path.write_text("[1]", encoding="utf-8")
    today = dt.date.today()
    assert pr.backup_once_today(idx_path, today) == "written"
    assert (tmp_path / "index.json.backup").read_text(encoding="utf-8") == "[1]"
    idx_path.write_text("[2]", encoding="utf-8")
    assert pr.backup_once_today(idx_path, today) == "kept (backup of today exists)"
    assert (tmp_path / "index.json.backup").read_text(encoding="utf-8") == "[1]"
    # an older rolling backup is replaced (one file only)
    old = dt.datetime.combine(today - dt.timedelta(days=2), dt.time(12)).timestamp()
    os.utime(tmp_path / "index.json.backup", (old, old))
    assert pr.backup_once_today(idx_path, today) == "written"
    assert (tmp_path / "index.json.backup").read_text(encoding="utf-8") == "[2]"


def test_disk_cells_cover_the_4_km_disk():
    # at the equator a 0.01 degree pixel is about 1.112 km per side: disk area / pixel area = pixel count (about 41)
    sw_lat, sw_lon, row, col = pr.disk_cells(0.0, 0.0)
    expected = np.pi * pr.DISK_RADIUS_KM ** 2 / (0.01 * 111.195) ** 2
    assert abs(row.size - expected) / expected < 0.1
    assert row.min() >= 0 and row.max() < pr.TILE_PX and col.min() >= 0 and col.max() < pr.TILE_PX


def test_window_shares_bare_ice_and_absent_pixels():
    cells = pr.disk_cells(10.5, 20.5)
    keys = set(zip(cells[0].tolist(), cells[1].tolist()))
    items = {k: {"id": f"TILE_{k[0]}_{k[1]}"} for k in keys}
    # every pixel class 70 (snow and ice): bare 1.0 and ice 1.0
    all_ice = {k: np.full((pr.TILE_PX, pr.TILE_PX), 70, dtype=np.uint8) for k in keys}
    r = pr.window_shares(cells, all_ice, items, RULES)
    assert r["bare_share_full"] == 1.0 and r["ice_share"] == 1.0 and r["absent_px"] == 0
    # class 10 (tree cover, not bare): bare 0, ice 0
    tree = {k: np.full((pr.TILE_PX, pr.TILE_PX), 10, dtype=np.uint8) for k in keys}
    r = pr.window_shares(cells, tree, items, RULES)
    assert r["bare_share_full"] == 0.0 and r["ice_share"] == 0.0
    # no tile loaded (ocean): counted as absent, the denominator stays the full disk
    r = pr.window_shares(cells, {}, items, RULES)
    assert r["absent_px"] == r["n_disk_px"] and r["bare_share_full"] == 0.0 and r["ice_share"] == 0.0
