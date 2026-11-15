"""pipelines/mars_atlas.py: the twin ranking and the tie groups of a cell (STANDARDS 10.13). Synthetic features only."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "pipelines"))
sys.path.insert(0, str(HERE / "src"))

import json  # noqa: E402

import mars_atlas as MA  # noqa: E402


def _cfg() -> dict:
    cfg = json.loads((HERE / "config" / "measure.json").read_text(encoding="utf-8"))
    for spec in cfg["features"].values():
        spec["sigma"] = 1.0
    return cfg


def _feat(slope: float, hi: float = 0.5, hurst: float = 0.5) -> dict:
    return {"slope_p95_deg": slope, "hi": hi, "coherence": 0.1, "hurst": hurst, "ridge_pct": None, "valley_pct": None}


def test_top_twins_are_the_three_nearest_by_the_frozen_distance():
    cfg = _cfg()
    pool = [{"id": f"pool__p{i}", "features": _feat(float(i))} for i in range(6)]
    tw = MA.top_twins(_feat(0.0), pool, cfg)
    assert [r["id"] for _, r in tw] == ["pool__p0", "pool__p1", "pool__p2"]
    assert all(d >= 0 for d, _ in tw)


def test_top_twins_skip_candidates_with_null_distance():
    cfg = _cfg()
    partial = {"id": "pool__x", "features": {"slope_p95_deg": 0.0, "hi": None, "coherence": None, "hurst": None,
                                             "ridge_pct": None, "valley_pct": None}}
    ok = {"id": "pool__y", "features": _feat(1.0)}
    tw = MA.top_twins(_feat(0.0), [partial, ok], cfg)
    assert [r["id"] for _, r in tw] == ["pool__y"]
