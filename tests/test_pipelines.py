"""Small synthetic end-to-end run of the pipelines on temp files (STANDARDS 10.7, sample mode, tmp root).

Run alone: .venv/Scripts/python.exe -m pytest tests/test_pipelines.py
The project's config and data are never touched: every run uses a temp project root with its own config, raw
rasters and pool index. Sample mode keeps outputs under <tmp>/data/derived/sample/.
"""

from __future__ import annotations

import json
import math
import shutil
import struct
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

HERE = Path(__file__).resolve().parents[1]
PIPES = HERE / "pipelines"
if str(PIPES) not in sys.path:
    sys.path.insert(0, str(PIPES))

import _common as C  # noqa: E402
import build_measure as BM  # noqa: E402
import calibrate_sigma as CS  # noqa: E402
import export_viz as EV  # noqa: E402
import mission_pct as MP  # noqa: E402
import search as SE  # noqa: E402
import validate as VA  # noqa: E402
from analog.core import measure as meas  # noqa: E402

N_POOL = 12
LAT0, LON0 = 10.0, 20.0
PX = 0.0001  # about 11 m at this latitude: L = 30 and 100 m are >= 2 x native
HALF = 0.045  # degrees: covers the 4 km disk with a margin


def _surface(shape: tuple[int, int], seed: int, amp_scale: float) -> np.ndarray:
    """Smooth synthetic terrain: six random sinusoids with seeded frequencies, phases and amplitudes (metres)."""
    rng = np.random.default_rng(seed)
    rows, cols = np.mgrid[0 : shape[0], 0 : shape[1]].astype(float)
    z = np.zeros(shape)
    for _ in range(6):
        wr, wc = rng.uniform(0.002, 0.03, size=2)
        ph = rng.uniform(0, 2 * math.pi)
        a = rng.uniform(5.0, 40.0) * amp_scale
        z += a * np.sin(wr * rows + wc * cols + ph)
    return z + 1000.0


def _write_raster(path: Path, lat: float, lon: float, px: float, half: float, z: np.ndarray, crs: str = "EPSG:4326") -> None:
    """Geographic float32 GeoTIFF centred on (lat, lon), north-up. Mars rasters need the Mars sphere as CRS."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = z.shape[0]
    transform = from_origin(lon - half, lat + half, px, px)
    with rasterio.open(path, "w", driver="GTiff", height=n, width=z.shape[1], count=1, dtype="float32",
                       crs=crs, transform=transform) as dst:
        dst.write(z.astype("float32"), 1)


def _grid_n(half: float, px: float) -> int:
    return int(round(2 * half / px))


@pytest.fixture(scope="module")
def mini(tmp_path_factory) -> Path:
    """Temp project: 1 valid target, 1 target too coarse (skip), 1 dev region with 2 sensors, 12 pool windows
    (1 with worldcover 0.5), pool window 0 flagged near_known_analog (excluded from the ranking), missions with limits."""
    root = tmp_path_factory.mktemp("mini_project")
    cfg = json.loads((HERE / "config" / "measure.json").read_text(encoding="utf-8"))
    for k in cfg["features"].values():
        k["sigma"] = None
    (root / "config").mkdir(parents=True)
    (root / "config" / "measure.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    n = _grid_n(HALF, PX)
    # Mars target: 0.0002 deg is about 11.9 m on the Mars sphere; 0.09 deg is about 5.3 km, which covers the 4 km disk
    n_mars = _grid_n(0.09, 0.0002)
    tgt = {"id": "syn_target", "body": "mars", "name": "Synthetic target", "lat": LAT0, "lon": LON0,
           "dem_source_id": "syn_dem", "role": "target"}
    coarse = {"id": "syn_coarse", "body": "mars", "name": "Too coarse", "lat": LAT0, "lon": LON0 + 1,
              "dem_source_id": "syn_coarse_dem", "role": "target"}
    (root / "config" / "sites.json").write_text(json.dumps({"sites": [tgt, coarse]}), encoding="utf-8")

    mars_crs = "+proj=longlat +R=3396190 +no_defs"  # the target body is Mars: its raster lives on the Mars sphere
    _write_raster(root / "data/raw/earth/syn_target/syn_dem.tif", LAT0, LON0, 0.0002, 0.09,
                  _surface((n_mars, n_mars), 1, 1.0), mars_crs)
    _write_raster(root / "data/raw/earth/syn_coarse/coarse.tif", LAT0, LON0 + 1, 0.02, 0.2,
                  _surface((20, 20), 2, 1.0), mars_crs)
    manifest = [
        {"source_id": "syn_dem", "path": "data/raw/earth/syn_target/syn_dem.tif"},
        {"source_id": "syn_coarse_dem", "path": "data/raw/earth/syn_coarse/coarse.tif"},
    ]
    (root / "data/raw/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    # dev region: nasadem and copdem = nasadem + 0.5 m offset noise (a small, nonzero sensor difference)
    base = _surface((n, n), 3, 1.0)
    _write_raster(root / "data/raw/earth/syn_region/nasadem.tif", LAT0 - 1, LON0 - 1, PX, HALF, base)
    _write_raster(root / "data/raw/earth/syn_region/copdem.tif", LAT0 - 1, LON0 - 1, PX, HALF,
                  base + 0.5 * np.sin(np.arange(n * n).reshape(n, n) * 0.37))

    regions = [
        {"id": "syn_region", "body": "earth", "name": "Synthetic dev", "lat": LAT0 - 1, "lon": LON0 - 1,
         "dem_source_id": "nasadem", "role": "dev", "class": "plain"},
    ]
    (root / "config" / "regions.json").write_text(json.dumps({"regions": regions}), encoding="utf-8")

    windows = []
    for i in range(N_POOL):
        lat, lon = 10.0 + 0.5 * i, 40.0
        rel = f"data/raw/earth/pool/w{i:02d}.tif"
        _write_raster(root / rel, lat, lon, PX, HALF, _surface((n, n), 100 + i, 0.5 + 0.2 * i))
        windows.append({"id": f"w{i:02d}", "lat": lat, "lon": lon, "path": rel, "source_id": "nasadem",
                        "worldcover_share": 0.5 if i == N_POOL - 1 else 0.9,
                        "valid_fraction": 1.0, "near_known_analog": i == 0})
    (root / "data/raw/earth/pool").mkdir(parents=True, exist_ok=True)
    # window 0 is flagged near_known_analog (25 km exclusion is computed by the pool step): search must drop it
    (root / "data/raw/earth/pool/index.json").write_text(json.dumps({"windows": windows}), encoding="utf-8")

    missions = {"limits": {"moon": {"landing": {"limit_deg": 15.0, "source": "test"},
                                    "driving": {"limit_deg": 25.0, "source": "test"}},
                           "mars": {"landing": {"limit_deg": 15.0, "source": "test"},
                                    "driving": {"limit_deg": 25.0, "source": "test"}}}}
    (root / "config" / "missions.json").write_text(json.dumps(missions), encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    return root


def _paths(root: Path) -> C.Paths:
    return C.make_paths(root, sample=True)


def _no_nan_json(path: Path) -> dict:
    """Load JSON and fail if NaN or Infinity tokens are present (STANDARDS 2: null, never NaN)."""
    def bad(token):
        raise AssertionError(f"non-finite token {token} in {path.name}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=bad)


def test_tie_groups_anchor_rule():
    """Anchor rule: a new group when D - D_anchor >= p95; members of one group differ by less than p95."""
    ds = [1.0, 1.1, 1.25, 1.39, 1.45, 2.0]  # 1.45 - 1.0 = 0.45 >= 0.4 (off the float boundary)
    groups = SE.tie_groups(ds, 0.4)
    assert groups == [0, 0, 0, 0, 1, 2]
    for g in set(groups):
        members = [d for d, gg in zip(ds, groups) if gg == g]
        assert max(members) - min(members) < 0.4


def test_pool_index_accepts_list_and_windows_forms(tmp_path: Path):
    """STANDARDS 10.8: the pool index may be a top-level list or {"windows": [...]}; both give the same entries."""
    entries = [{"id": "a", "lat": 1.0, "lon": 2.0, "path": "x.tif", "worldcover_share": 0.9,
                "near_known_analog": False, "valid_fraction": 1.0}]
    for form, payload in (("windows", {"windows": entries}), ("list", entries)):
        root = tmp_path / form
        (root / "data/raw/earth/pool").mkdir(parents=True)
        (root / "data/raw/earth/pool/index.json").write_text(json.dumps(payload), encoding="utf-8")
        got, reason = C.pool_index(C.make_paths(root, sample=False))
        assert reason is None and got == entries
    none, reason = C.pool_index(C.make_paths(tmp_path / "absent", sample=False))
    assert none is None and "not found" in reason


def test_export_30m_grid_is_exempt_from_2x_native_rule(tmp_path: Path):
    """STANDARDS 10.8: a 20-30 m native DEM is exported at 30 m (display grid exempt from L >= 2 x native).
    Here the native pixel is about 27.8 m, so 30 < 2 x native: the old rule would have skipped it."""
    px = 0.00025
    half = 0.1  # about 11 km around the site: the 4 km disk is fully covered
    n = _grid_n(half, px)
    _write_raster(tmp_path / "data/raw/earth/vis/native28.tif", LAT0, LON0, px, half, _surface((n, n), 9, 1.0))
    paths = C.make_paths(tmp_path, sample=True)
    cfg = json.loads((HERE / "config" / "measure.json").read_text(encoding="utf-8"))
    t = EV.Terrain(id="vis", kind="target", body="earth", name="vis", lat=LAT0, lon=LON0, source_id="nasadem",
                   raw_rel="data/raw/earth/vis/native28.tif")
    log = C.RunLog(tmp_path / "log", "test")
    EV.build_height(paths, t, cfg, log)
    assert t.status == "ok", t.reason
    assert t.native_res_m > 15.0 and 30.0 < 2.0 * t.native_res_m
    assert t.height.shape == (269, 269) and np.isfinite(t.height[134, 134])


def test_build_measure_ok_skip_and_null_rules(mini: Path):
    """Targets, dev region sensors and pool windows are measured; a too-coarse raster is skipped with its reason;
    a pool window with worldcover 0.5 is skipped; the JSON has no NaN; features are null unless ok."""
    paths = _paths(mini)
    BM.run(paths, None)
    stage = paths.stage("measure")
    ok_t = _no_nan_json(stage / "syn_target.json")
    assert ok_t["status"] == "ok" and ok_t["native_res_m"] < 15.0
    assert ok_t["coverage"] >= 0.9 and ok_t["features"] is not None
    assert set(ok_t["features"]) == set(meas.FEATURE_IDS)
    assert ok_t["provenance"]["schema"] == "analog.measure/1"
    coarse = _no_nan_json(stage / "syn_coarse.json")
    assert coarse["status"] == "skipped" and "L=100" in coarse["reason"] and coarse["features"] is None
    assert _no_nan_json(stage / "syn_region__nasadem.json")["status"] == "ok"
    assert _no_nan_json(stage / "syn_region__copdem.json")["status"] == "ok"
    skipped_pool = _no_nan_json(stage / f"pool__w{N_POOL - 1:02d}.json")
    assert skipped_pool["status"] == "skipped" and "worldcover" in skipped_pool["reason"]
    assert _no_nan_json(stage / "pool__w00.json")["status"] == "ok"
    w0 = _no_nan_json(stage / "pool__w00.json")
    assert w0["near_known_analog"] is True and w0["valid_fraction"] == 1.0  # 10.8 pool fields carried through
    log = (stage / "run_log.jsonl").read_text(encoding="utf-8")
    assert "syn_coarse" in log and "worldcover" in log


def test_build_measure_resume_kind_and_force(mini: Path):
    """Resumable: an existing record with the same measure_key is reused; a stale key is re-measured; --kind limits
    the jobs (no target or region measured); force re-measures everything in scope."""
    paths = _paths(mini)
    BM.run(paths, None, kinds=["pool"])
    stage = paths.stage("measure")
    p00 = stage / "pool__w00.json"
    rec = _no_nan_json(p00)
    assert rec["measure_key"] == BM.measure_key(C.read_config(paths))
    rec["marker"] = "kept"
    C.write_json(p00, rec)
    assert BM.run(paths, None, kinds=["pool"]) == 0  # all resumed, nothing measured
    assert _no_nan_json(p00).get("marker") == "kept"
    rec["measure_key"] = "stale"
    C.write_json(p00, rec)
    assert BM.run(paths, ["pool__w00"]) == 1  # stale key: re-measured
    fresh = _no_nan_json(p00)
    assert fresh["measure_key"] == BM.measure_key(C.read_config(paths)) and "marker" not in fresh
    assert BM.run(paths, None, kinds=["pool"], force=True) == N_POOL
    with pytest.raises(ValueError):
        BM.run(paths, None, kinds=["bogus"])


def test_calibrate_sample_writes_sample_config_only(mini: Path):
    """Sample calibration: sigma = 1.4826 MAD over the ok pool windows, written to the sample config copy only."""
    paths = _paths(mini)
    assert CS.run(paths, force=False) == 0
    sample_cfg = _no_nan_json(paths.sample_config)
    real_cfg = json.loads((mini / "config" / "measure.json").read_text(encoding="utf-8"))
    assert all(real_cfg["features"][k]["sigma"] is None for k in meas.FEATURE_IDS)
    table, ok = CS.calibrate(paths, CS.MIN_N_SAMPLE)
    assert ok
    for k in meas.FEATURE_IDS:
        assert sample_cfg["features"][k]["sigma"] == pytest.approx(table[k]["sigma"])
        assert sample_cfg["features"][k]["sigma"] > 0


def test_calibrate_refuses_small_real_pool(mini: Path):
    """Real mode needs at least 500 pool values per feature: refusal (exit 2) and no write."""
    real = C.make_paths(mini, sample=False)
    before = (mini / "config" / "measure.json").read_text(encoding="utf-8")
    assert CS.run(real, force=False) == 2
    assert (mini / "config" / "measure.json").read_text(encoding="utf-8") == before


def test_validate_refuses_null_sigma(mini: Path):
    """validate.py refuses (exit 2, nothing written) when any sigma is null, in both modes."""
    real = C.make_paths(mini, sample=False)
    assert VA.run_noise(real) == 2
    assert VA.run_holdout(real) == 2
    assert not (real.stage("validation") / C.noise_file_name("1.3")).exists()


def test_validate_noise_sample_writes_thresholds(mini: Path):
    """--noise with the sample sigma: one dev region gives one D in its relief class; the other class has no value."""
    paths = _paths(mini)
    assert VA.run_noise(paths) == 0
    out = _no_nan_json(paths.stage("validation") / "noise_v1.3.json")
    assert out["n_expected"] == 1 and out["n_used"] == 1
    filled = [c for c in ("rugged", "flat") if out["classes"][c]["n"] == 1]
    assert len(filled) == 1
    other = "flat" if filled[0] == "rugged" else "rugged"
    assert out["classes"][other]["n"] == 0 and out["classes"][other]["p95"] is None
    assert out["classes"][filled[0]]["p95"] == pytest.approx(out["regions"][0]["D"])
    assert out["flat_slope_p95_deg"] == 3.0


def test_search_excludes_near_known_analog_flag_and_ranks(mini: Path):
    """Ranking of syn_target: window 0 (pool flag near_known_analog) excluded, top 10 ascending D, tie groups per the
    noise p95 of the target's relief class (the noise file is written first, as the pipeline order requires)."""
    paths = _paths(mini)
    assert VA.run_noise(paths) == 0
    assert SE.run(paths, None) == 1
    rk = _no_nan_json(paths.stage("ranking") / "syn_target.json")
    assert rk["n_excluded_near_known_analog"] == 1
    assert "pool__w00" not in [r["analog_id"] for r in rk["ranking"]]
    ds = [r["D"] for r in rk["ranking"]]
    assert len(ds) == 10 and ds == sorted(ds)
    p95 = rk["tie_rule"]["noise_p95"]
    assert rk["tie_rule"]["relief_class"] in ("rugged", "flat") and p95 is not None
    groups = [r["tie_group"] for r in rk["ranking"]]
    assert groups == sorted(groups)
    for g in set(groups):
        members = [d for d, gg in zip(ds, groups) if gg == g]
        assert max(members) - min(members) < p95 or len(members) == 1


def test_mission_pct_matches_direct_recompute(mini: Path):
    """Mission share of the target equals an independent recompute (core functions on the same 100 m grid)."""
    from analog import grid as gridmod
    from analog.core import mission

    paths = _paths(mini)
    assert MP.run(paths, ["syn_target"]) == 0
    mp = _no_nan_json(paths.stage("mission") / "syn_target.json")
    z, mask, _ = gridmod.load_local_grid(mini / "data/raw/earth/syn_target/syn_dem.tif", LAT0, LON0, "mars", 100.0, 4000.0)
    slope = mission.slope_map_deg(z, mask, 100.0)
    expect = mission.mission_share(slope, 15.0)["pct"]
    assert mp["by_body"]["mars"]["landing"]["pct"] == pytest.approx(expect, abs=1e-9)
    assert mp["by_body"]["mars"]["landing"]["limit_deg"] == 15.0
    assert mp["n_defined"] == int(np.isfinite(slope).sum())


def test_mission_control_missing_gives_exit_3(mini: Path):
    """Jezero and Gale are the control: when they are not in scope or not valid, the run exits 3 (STOP)."""
    paths = _paths(mini)
    assert MP.run(paths, None) == 3


def test_mission_missing_limits_gives_null(mini: Path, tmp_path: Path):
    """No config/missions.json: pct null with the reason, never 0 or a stand-in limit."""
    root = tmp_path / "nolimits"
    shutil.copytree(mini, root)  # keeps the measure records of the shared project
    (root / "config" / "missions.json").unlink()
    paths = C.make_paths(root, sample=True)
    MP.run(paths, ["syn_target"])
    mp = _no_nan_json(paths.stage("mission") / "syn_target.json")
    assert mp["by_body"]["mars"]["landing"]["pct"] is None
    assert mp["by_body"]["mars"]["landing"]["limit_reason"] == "config/missions.json not found"


def test_export_viz_contract(mini: Path):
    """Terrain folders (height.bin float32 LE n*n, PNG 269 px, meta), viz.json with one VE, targets.json, cards with the
    STANDARDS 10.5 keys, rankings with card paths. The coarse target is not exported."""
    paths = _paths(mini)
    assert EV.run(paths, None) == 0
    site = paths.site_data
    folder = site / "terrain" / "syn_target"
    raw = (folder / "height.bin").read_bytes()
    assert len(raw) == 269 * 269 * 4
    h = np.frombuffer(raw, dtype="<f4").reshape(269, 269)
    assert np.isnan(h[0, 0]) and np.isfinite(h[134, 134])
    finite = h[np.isfinite(h)]
    assert abs(float(finite.astype(np.float64).mean())) < 1e-3
    png = (folder / "hillshade.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", png[16:24]) == (269, 269)
    meta = _no_nan_json(folder / "meta.json")
    assert meta["n"] == 269 and meta["L"] == 30.0 and meta["R"] == 4000.0
    assert meta["layers"]["mars"] == "layers_mars.bin"
    assert (folder / "layers_mars.bin").stat().st_size == 269 * 269
    viz_doc = _no_nan_json(site / "viz.json")
    assert viz_doc["vertical_exaggeration"] > 0
    assert viz_doc["terrains"]["syn_target"]["status"] == "ok"
    targets = _no_nan_json(site / "targets.json")["targets"]
    assert [t["id"] for t in targets] == ["syn_target"]
    ranking = _no_nan_json(site / "rankings" / "syn_target.json")["ranking"]
    assert len(ranking) == 10 and all(r["card"] for r in ranking)
    card = _no_nan_json(site / "cards" / f"syn_target__{ranking[0]['analog_id']}.json")
    for key in ["target_id", "analog_id", "rank", "D", "tie_group", "features", "similar", "different",
                "mission_pct", "rotation_deg", "files", "provenance"]:
        assert key in card
    assert set(card["features"]) == set(meas.FEATURE_IDS)
    assert set(card["mission_pct"]) == {"landing", "driving"}
    assert card["rotation_deg"] is not None and card["rotation_deg"] % 10 == 0
    assert card["files"]["target"] == "terrain/syn_target/"


def test_export_mars_first_fields(mini: Path, tmp_path: Path):
    """STANDARDS 10.9: targets.json carries landing_class, mission, year, outcome_note, center_note from config/sites.json
    (null when absent) and unlocked computed from the measurement (never from sites.json). bodies.json, missions.json
    and validation.json are written; with no validation files the v1.2 block is 'not run' and v1.3 is 'pending'."""
    root = tmp_path / "mars_first"
    shutil.copytree(mini, root)
    sites = json.loads((root / "config" / "sites.json").read_text(encoding="utf-8"))
    sites["sites"][0].update({"landing_class": "landing_demonstrated", "mission": "Synthetic", "year": 2030,
                              "outcome_note": "Synthetic note.", "center_note": "Synthetic centre.",
                              "unlocked": False})  # ignored: unlocked is computed (native <= 50 m)
    (root / "config" / "sites.json").write_text(json.dumps(sites), encoding="utf-8")
    (root / "config" / "bodies.json").write_text(json.dumps({"bodies": {"mars": {"gravity_m_s2": 3.71}}}), encoding="utf-8")
    shutil.rmtree(root / "data" / "derived" / "sample" / "validation", ignore_errors=True)
    paths = C.make_paths(root, sample=True)
    assert EV.run(paths, None) == 0
    site = paths.site_data
    tgt = {t["id"]: t for t in _no_nan_json(site / "targets.json")["targets"]}["syn_target"]
    assert tgt["landing_class"] == "landing_demonstrated" and tgt["mission"] == "Synthetic" and tgt["year"] == 2030
    assert tgt["outcome_note"] == "Synthetic note." and tgt["center_note"] == "Synthetic centre." and tgt["unlocked"] is True
    bodies = _no_nan_json(site / "bodies.json")
    assert bodies["bodies"] == {"mars": {"gravity_m_s2": 3.71}} and bodies["reason"] is None
    missions = _no_nan_json(site / "missions.json")
    assert missions["limits"]["mars"]["landing"]["limit_deg"] == 15.0 and missions["entries"] is None  # mini has no entries
    val = _no_nan_json(site / "validation.json")
    assert val["v1.2"]["status"] == "not run" and val["v1.3"]["status"] == "pending"
    assert val["v1.3_noise"]["status"] == "not run" and "provenance" in val
    # a second run with the field removed from sites.json: the text fields are null, unlocked is still computed
    sites["sites"][0].pop("landing_class")
    (root / "config" / "sites.json").write_text(json.dumps(sites), encoding="utf-8")
    assert EV.run(paths, None) == 0
    tgt = {t["id"]: t for t in _no_nan_json(site / "targets.json")["targets"]}["syn_target"]
    assert tgt["landing_class"] is None and tgt["mission"] == "Synthetic" and tgt["unlocked"] is True


def test_unlocked_is_computed_from_native_resolution():
    """STANDARDS 10.9: unlocked = measured (terrain ok) and native DEM resolution <= 50 m; never from sites.json."""
    base = dict(id="t", kind="target", body="mars", name="t", lat=0.0, lon=0.0, source_id="s", raw_rel="r")
    assert EV.is_unlocked(EV.Terrain(**base, status="ok", native_res_m=20.0)) is True
    assert EV.is_unlocked(EV.Terrain(**base, status="ok", native_res_m=50.0)) is True
    assert EV.is_unlocked(EV.Terrain(**base, status="ok", native_res_m=60.0)) is False
    assert EV.is_unlocked(EV.Terrain(**base, status="skipped", native_res_m=20.0)) is False
    assert EV.is_unlocked(EV.Terrain(**base, status="ok", native_res_m=None)) is False


def _v13_cfg_unit_sigma() -> dict:
    """Real config (v1.3 features, weights, validation.v13) with every sigma set to 1.0, so D is the plain distance."""
    cfg = json.loads((HERE / "config" / "measure.json").read_text(encoding="utf-8"))
    for spec in cfg["features"].values():
        spec["sigma"] = 1.0
    return cfg


def _feat(slope: float, hi: float = 0.5, hurst: float = 0.5, coherence: float = 0.1) -> dict:
    """Feature dict with the six keys (ridge and valley null: they are weight 0 and never enter D)."""
    return {"slope_p95_deg": slope, "hi": hi, "coherence": coherence, "hurst": hurst, "ridge_pct": None,
            "valley_pct": None}


def test_noise_table_tie_rule_uses_the_relief_class():
    """STANDARDS 10.11: the tie threshold is the p95 of D(NASADEM, Copernicus) within the dev region's relief class.
    Rugged = slope_p95 >= 3 deg (3.0 itself is rugged); flat = below. D is set to c by shifting the three features by c."""
    cfg = _v13_cfg_unit_sigma()
    nasa, cop = {}, {}
    rugged_D = {"r1": 0.2, "r2": 0.4, "r3": 0.6, "r4": 1.0, "r5": 0.8}
    flat_D = {"f1": 0.1, "f2": 0.3}
    slope_of = {"r5": 3.0, "f1": 1.0, "f2": 2.9}
    for rid, c in {**rugged_D, **flat_D}.items():
        s = slope_of.get(rid, 10.0)
        nasa[rid] = {"region_id": rid, "features": _feat(s)}
        cop[rid] = {"region_id": rid, "features": _feat(s + c, 0.5 + c, 0.5 + c)}
    nasa["broken"] = {"region_id": "broken", "features": _feat(10.0)}  # no copdem record: left out with a reason
    ids = list(rugged_D) + list(flat_D) + ["broken"]
    doc = VA.noise_table(nasa, cop, ids, cfg)
    assert doc["flat_slope_p95_deg"] == 3.0
    assert doc["classes"]["rugged"]["n"] == 5 and doc["classes"]["flat"]["n"] == 2
    assert doc["classes"]["rugged"]["p95"] == pytest.approx(np.percentile(list(rugged_D.values()), 95))
    assert doc["classes"]["flat"]["p95"] == pytest.approx(np.percentile(list(flat_D.values()), 95))
    assert doc["n_used"] == 7 and doc["n_expected"] == 8
    broken = [r for r in doc["regions"] if r["region_id"] == "broken"][0]
    assert broken["D"] is None and broken["reason"] == "one sensor missing or not ok"


def _dev_and_query(cfg_classes: list[str]) -> tuple[dict, dict, dict]:
    """15 dev regions (3 per class, slope 10*class + 0.1*j) and 15 holdout queries, all with the same class order."""
    dev, query, true_cls = {}, {}, {}
    for ci, cls in enumerate(cfg_classes):
        for j in range(3):
            did = f"d_{ci}_{j}"
            dev[did] = {"region_id": did, "class": cls, "features": _feat(10.0 * ci + 0.1 * j)}
    return dev, query, true_cls


def test_nn_count_and_pass_rule_at_seven_of_fifteen():
    """STANDARDS 10.11: 1-NN of each holdout region against the 15 dev regions; pass needs >= 7 of 15 correct.
    The queries sit at their own class centre (slope 10*class) for the first k of the list and at the next class for
    the rest, so exactly k are correct by construction. k = 7 passes, k = 6 fails; P(X >= 7 | 15, 0.2) = 0.018."""
    cfg = _v13_cfg_unit_sigma()
    classes = list(cfg["validation"]["classes"])
    dev, _, _ = _dev_and_query(classes)
    for k in (7, 6):
        query = {}
        order = [(ci, j) for ci in range(5) for j in range(3)]
        for n, (ci, j) in enumerate(order):
            ok = n < k
            target_ci = ci if ok else (ci + 1) % 5
            query[f"h_{ci}_{j}"] = {"region_id": f"h_{ci}_{j}", "class": classes[ci],
                                    "features": _feat(10.0 * target_ci + 0.2 + 0.01 * n)}
        rows = VA.nn_predictions(query, dev, list(dev), cfg)
        summ = VA.nn_summary(rows, 15, int(cfg["validation"]["v13"]["pass"]["nn_against_dev_min_correct"]))
        assert summ["k_correct"] == k and summ["n_computed"] == 15
        assert summ["pass"] is (k >= 7)
        if k == 7:
            assert summ["binomial_one_sided_p"] == pytest.approx(0.0180, abs=5e-4)
            lo, hi = summ["wilson95"]
            assert lo < 7 / 15 < hi


def test_holdout_pass_criteria_are_the_config_thresholds():
    """AUC >= 0.70; bootstrap CI lower bound strictly > 0.5; permutation p < 0.05; NN pass as counted. Each tested."""
    pass_cfg = _v13_cfg_unit_sigma()["validation"]["v13"]["pass"]
    ok = VA.holdout_pass(0.71, 0.51, 0.04, True, pass_cfg)
    assert ok["all"] is True
    assert VA.holdout_pass(0.69, 0.51, 0.04, True, pass_cfg)["auc"] is False
    assert VA.holdout_pass(0.71, 0.5, 0.04, True, pass_cfg)["auc_ci_lower"] is False  # strictly greater than 0.5
    assert VA.holdout_pass(0.71, 0.51, 0.05, True, pass_cfg)["permutation_p"] is False  # strictly below 0.05
    assert VA.holdout_pass(0.71, 0.51, 0.04, False, pass_cfg)["all"] is False


def test_holdout_refuses_wrong_design_and_runs_once(mini: Path):
    """The holdout mode refuses without the 15 holdout regions (exit 2), and refuses (exit 3) once its file exists."""
    paths = _paths(mini)
    assert VA.run_holdout(paths) == 2
    stage = paths.stage("validation")
    stage.mkdir(parents=True, exist_ok=True)
    marker = stage / "v1.3.json"
    marker.write_text("{}", encoding="utf-8")
    try:
        assert VA.run_holdout(paths) == 3
    finally:
        marker.unlink()


def test_site_raw_path_picks_the_sites_own_file_for_a_shared_source(tmp_path: Path):
    """Four Moon sites share lola_20m_polar_ldem in the manifest: each site gets its own clipped file, never another's."""
    cands = [tmp_path / "data/raw/moon/im1_odysseus/lola.tif", tmp_path / "data/raw/moon/im2_athena/lola.tif"]
    assert C.site_raw_path(cands, "im2_athena") == cands[1]
    assert C.site_raw_path(cands, "cabeus_b_peak") is None  # several files, none its own: no guess
    assert C.site_raw_path(cands[:1], "anything") == cands[0]  # the only candidate
    assert C.site_raw_path([], "anything") is None


def test_holdout_end_to_end_on_synthetic_records(tmp_path: Path):
    """run_holdout on a temp project: 15 dev regions and 15 holdout regions (3 per class) with synthetic measure
    records whose classes are separated, so AUC = 1 and every 1-NN is right: PASS on every criterion. Runs once."""
    root = tmp_path / "holdout_e2e"
    (root / "config").mkdir(parents=True)
    (root / "config" / "measure.json").write_text((HERE / "config" / "measure.json").read_text(encoding="utf-8"),
                                                  encoding="utf-8")
    cfg = json.loads((HERE / "config" / "measure.json").read_text(encoding="utf-8"))
    classes = list(cfg["validation"]["classes"])
    regions, measure = [], {}
    for role, prefix in (("dev", "d"), ("holdout_v13", "h")):
        for ci, cls in enumerate(classes):
            for j in range(3):
                rid = f"{prefix}_{cls}_{j}"
                regions.append({"id": rid, "body": "earth", "name": rid, "lat": 0.0, "lon": 0.0,
                                "dem_source_id": "nasadem", "role": role, "class": cls})
                feat = {"slope_p95_deg": 10.0 * ci + 0.1 * j, "hi": 0.5 + 0.01 * ci, "coherence": 0.1,
                        "hurst": 0.5 + 0.02 * ci + 0.001 * j, "ridge_pct": None, "valley_pct": None}
                kind = "region" if role == "dev" else "holdout"
                measure[f"{rid}__nasadem"] = {"id": f"{rid}__nasadem", "kind": kind, "status": "ok", "sensor": "nasadem",
                                              "region_id": rid, "class": cls, "features": feat}
    (root / "config" / "regions.json").write_text(json.dumps({"regions": regions}), encoding="utf-8")
    mdir = root / "data" / "derived" / "measure"
    mdir.mkdir(parents=True)
    for name, rec in measure.items():
        (mdir / f"{name}.json").write_text(json.dumps(rec), encoding="utf-8")
    paths = C.make_paths(root, sample=False)
    assert VA.run_holdout(paths) == 0
    out = _no_nan_json(paths.stage("validation") / "v1.3.json")
    assert out["AUC"]["auc"] == pytest.approx(1.0)
    assert out["AUC"]["n_same_class_pairs"] == 15 and out["AUC"]["n_pairs_total"] == 105
    assert out["NN"]["summary"]["k_correct"] == 15 and out["NN"]["summary"]["pass"] is True
    assert out["summary"]["all_pass"] is True
    assert out["thresholds"] == cfg["validation"]["v13"]["pass"]
    assert VA.run_holdout(paths) == 3  # runs once


def test_card_scoring_split_pair_exaggeration_and_place(mini: Path):
    """STANDARDS 10.12: in_distance = weight > 0 features; similar/different over them only; context lists over the rest;
    one vertical_exaggeration in [1, 10] per pair; analog_place present (null: no admin-1 file in the temp project)."""
    paths = _paths(mini)
    assert EV.run(paths, None) == 0
    cards = sorted((paths.site_data / "cards").glob("syn_target__*.json"))
    assert cards
    card = _no_nan_json(cards[0])
    cfg = json.loads((HERE / "config" / "measure.json").read_text(encoding="utf-8"))
    in_dist = [k for k in meas.FEATURE_IDS if float(cfg["features"][k]["weight"]) > 0]
    assert card["in_distance"] == in_dist and sorted(card["context_features"]) == sorted(
        k for k in meas.FEATURE_IDS if k not in in_dist)
    assert set(card["similar"]) | set(card["different"]) <= set(in_dist)
    assert set(card["context_similar"]) | set(card["context_different"]) <= set(card["context_features"])
    assert set(card["similar"]) | set(card["different"]) == {k for k in in_dist if card["features"][k]["z_diff"] is not None}
    assert 1.0 <= card["vertical_exaggeration"] <= 10.0
    assert "analog_place" in card and card["analog_place"] is None
    ranking = _no_nan_json(paths.site_data / "rankings" / "syn_target.json")["ranking"]
    assert "analog_place" in ranking[0] and ranking[0]["analog_place"] is None


def test_limit_for_returns_the_source_url_from_missions_json():
    """missions.json stores each limit's link as source_url: limit_for must return it (the mission source on the cards)."""
    limits = {"mars": {"landing": {"limit_deg": 15, "source_url": "https://example.org/mer"}}}
    deg, source, reason = C.limit_for(limits, "mars", "landing")
    assert deg == 15.0 and source == "https://example.org/mer" and reason is None
    assert C.limit_for(limits, "moon", "landing")[0] is None


def _project_copy(mini: Path, tmp_path: Path) -> Path:
    """Private copy of the synthetic project, so index edits never reach the shared module fixture."""
    root = tmp_path / "proj"
    shutil.copytree(mini, root)
    return root


def _set_rows(root: Path, patch: dict[str, dict]) -> None:
    """Update fields of pool index rows in place (keys = window ids)."""
    ipath = root / "data/raw/earth/pool/index.json"
    data = json.loads(ipath.read_text(encoding="utf-8"))
    for w in data["windows"]:
        if w["id"] in patch:
            w.update(patch[w["id"]])
    ipath.write_text(json.dumps(data), encoding="utf-8")


def test_pool_sensor_and_source_come_from_the_index_row(mini: Path, tmp_path: Path):
    """A pool row carries its own sensor and source_id (copdem / cop_dem_glo30); a row without them is nasadem.
    The path is read as given, whatever the sensor: the job points at the explicit file for both."""
    root = _project_copy(mini, tmp_path)
    _set_rows(root, {"w01": {"sensor": "copdem", "source_id": "cop_dem_glo30"}})
    paths = C.make_paths(root, sample=False)
    windows, _ = C.pool_index(paths)
    jobs = {j["id"]: j for j in BM.pool_jobs(paths, windows)}
    assert jobs["pool__w01"]["sensor"] == "copdem" and jobs["pool__w01"]["source_id"] == "cop_dem_glo30"
    assert jobs["pool__w01"]["pre"] is None
    assert jobs["pool__w01"]["path"] == paths.root / "data/raw/earth/pool/w01.tif"
    assert jobs["pool__w00"]["sensor"] == "nasadem" and jobs["pool__w00"]["source_id"] == "nasadem"
    BM.run(paths, ["pool__w01"], kinds=["pool"], force=True)
    rec = _no_nan_json(paths.stage("measure") / "pool__w01.json")
    assert rec["status"] == "ok" and rec["sensor"] == "copdem" and rec["source_id"] == "cop_dem_glo30"
    assert rec["source_path"] == "data/raw/earth/pool/w01.tif"


def test_excluded_row_is_recorded_with_its_rule_and_not_measured(mini: Path, tmp_path: Path):
    """An index row with excluded != null gives status "excluded" with the rule and its value as reason; no features."""
    rule = {"rule": "ice_share", "value": 0.35, "threshold": 0.2}
    root = _project_copy(mini, tmp_path)
    _set_rows(root, {"w02": {"excluded": rule}})
    paths = C.make_paths(root, sample=False)
    windows, _ = C.pool_index(paths)
    job = next(j for j in BM.pool_jobs(paths, windows) if j["id"] == "pool__w02")
    assert job["pre"][0] == "excluded"
    BM.run(paths, ["pool__w02"], kinds=["pool"])
    rec = _no_nan_json(paths.stage("measure") / "pool__w02.json")
    assert rec["status"] == "excluded" and rec["features"] is None and rec["excluded"] == rule
    assert "ice_share" in rec["reason"] and "0.35" in rec["reason"] and "0.2" in rec["reason"]


def test_resume_rewrites_only_rows_whose_exclusion_or_sensor_changed(mini: Path, tmp_path: Path):
    """Unchanged rows are still skipped on a resumed run (0 measured); a row whose excluded value or sensor changed
    is re-written, in both directions, and only that row."""
    root = _project_copy(mini, tmp_path)
    paths = C.make_paths(root, sample=False)
    stage = paths.stage("measure")
    BM.run(paths, None, kinds=["pool"])
    assert BM.run(paths, None, kinds=["pool"]) == 0
    rule = {"rule": "bare_share_full", "value": 0.6, "threshold": 0.8}
    _set_rows(root, {"w02": {"excluded": rule}})
    assert BM.run(paths, None, kinds=["pool"]) == 1
    assert _no_nan_json(stage / "pool__w02.json")["status"] == "excluded"
    _set_rows(root, {"w02": {"excluded": None}})
    assert BM.run(paths, None, kinds=["pool"]) == 1
    assert _no_nan_json(stage / "pool__w02.json")["status"] == "ok"
    _set_rows(root, {"w03": {"sensor": "copdem", "source_id": "cop_dem_glo30"}})
    assert BM.run(paths, None, kinds=["pool"]) == 1
    assert _no_nan_json(stage / "pool__w03.json")["sensor"] == "copdem"
    assert BM.run(paths, None, kinds=["pool"]) == 0


def test_calibrate_ignores_copdem_and_excluded_records(tmp_path: Path):
    """calibrate_sigma uses only pool records with sensor nasadem, status ok and no exclusion: copdem and excluded
    windows cannot move the median or the n."""
    paths = C.make_paths(tmp_path, sample=True)
    stage = paths.stage("measure")
    stage.mkdir(parents=True, exist_ok=True)

    def rec(name: str, value: float, sensor: str, status: str = "ok", excluded=None) -> None:
        feats = {k: value for k in meas.FEATURE_IDS}
        C.write_json(stage / f"pool__{name}.json", {"kind": "pool", "status": status, "sensor": sensor,
                                                   "excluded": excluded, "features": feats})

    for i, v in enumerate([1.0, 2.0, 3.0, 4.0, 5.0]):
        rec(f"n{i}", v, "nasadem")
    rec("c0", 1000.0, "copdem")
    rec("c1", 1000.0, "copdem")
    rec("x0", 1000.0, "nasadem", status="excluded", excluded={"rule": "ice_share", "value": 0.5, "threshold": 0.2})
    rec("x1", 1000.0, "nasadem", excluded={"rule": "ice_share", "value": 0.5, "threshold": 0.2})
    table, ok = CS.calibrate(paths, 1)
    assert ok
    for k in meas.FEATURE_IDS:
        assert table[k]["n"] == 5
        assert table[k]["median"] == pytest.approx(3.0)
