"""src/analog/core/rehearsal.py: one synthetic test per rule of STANDARDS 10.15 (P-P). Run alone:
.venv/Scripts/python.exe -m pytest tests/test_rehearsal.py

Cards here are synthetic dicts; the rules and the body facts are read from config/rehearsal_rules.json and
config/bodies.json (the values under test). The light stage is not written in this file: low_sun is driven by light
dicts passed in directly, and the lowest-latitude hook is tested with a fake module.
"""

from __future__ import annotations

import importlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analog.core import rehearsal as RH  # noqa: E402

RULES = json.loads((ROOT / "config" / "rehearsal_rules.json").read_text(encoding="utf-8"))
BODIES = json.loads((ROOT / "config" / "bodies.json").read_text(encoding="utf-8"))["bodies"]
EARTH_EPS = float(json.loads((ROOT / "config" / "light.json").read_text(encoding="utf-8"))["bodies"]["earth"]["obliquity_deg"])
MARS_URL = BODIES["mars"]["source_url"]
MOON_URL = BODIES["moon"]["source_url"]


def card(t_land: float = 50.0, a_land: float = 50.0, t_drive: float = 60.0, a_drive: float = 60.0,
         koppen: str | None = "BWh", src_land: str | None = "https://example.org/landing",
         limit_land: float = 15.0) -> dict[str, Any]:
    """A synthetic pair card with the fields the evaluator reads (mission_pct and context)."""
    return {
        "target_id": "t", "analog_id": "t__pool__pool_00001",
        "mission_pct": {
            "landing": {"target": t_land, "analog": a_land, "limit_deg": limit_land, "source": src_land, "reason": None},
            "driving": {"target": t_drive, "analog": a_drive, "limit_deg": 30.0,
                        "source": "https://example.org/driving", "reason": None},
        },
        "context": {"koppen_class": koppen},
    }


def light(t_grazing: float | None, a_grazing: float | None) -> dict[str, Any]:
    """Light values as the pipeline passes them: {target, analog, reason}."""
    return {"target": {"grazing_pct": t_grazing}, "analog": {"grazing_pct": a_grazing}, "reason": None}


def line(lines: list[dict[str, Any]], lid: str) -> dict[str, Any]:
    """The line with this id."""
    return next(x for x in lines if x["id"] == lid)


def evaluate(c: dict[str, Any], body: str = "mars", lt: dict | None = None,
             eps: float | None = EARTH_EPS) -> list[dict[str, Any]]:
    """evaluate_pair with the real rules, body facts and Earth obliquity; light defaults to 'not available'."""
    lt = lt if lt is not None else {"target": None, "analog": None, "reason": RH.LIGHT_MISSING}
    return RH.evaluate_pair(c, body, BODIES, RULES, lt, eps)


# ---- landing and driving: thresholds 10 and 25 points (STANDARDS 10.15)

@pytest.mark.parametrize("analog, status", [
    (60.0, "yes"),       # +10.00 points: boundary inclusive -> yes
    (60.01, "partial"),  # just over 10
    (75.0, "partial"),   # +25.00 points: boundary inclusive -> partial
    (75.01, "no"),       # just over 25
    (40.0, "yes"),       # -10.00 points: the difference is absolute
    (25.0, "partial"),   # -25.00 points: boundary inclusive -> partial
    (24.99, "no"),       # just under -25
])
def test_landing_thresholds(analog: float, status: str):
    """Landing: yes if |analog - target| <= 10, partial if <= 25, else no. Target 50 points."""
    ln = line(evaluate(card(t_land=50.0, a_land=analog)), "landing")
    assert ln["status"] == status
    assert ln["group"] == "rehearse" and ln["evidence"] == "reference comparison"
    assert ln["target_value"] == 50.0 and ln["analog_value"] == analog
    assert ln["source"] == "https://example.org/landing"


@pytest.mark.parametrize("analog, status", [
    (100.0, "yes"),     # target 90: +10 -> yes
    (70.0, "partial"),  # -20 -> partial
    (30.0, "no"),       # -60 -> no
])
def test_driving_thresholds_use_the_driving_entry(analog: float, status: str):
    """Driving: same thresholds on mission_pct.driving; the landing entry does not affect it."""
    lines = evaluate(card(t_drive=90.0, a_drive=analog, t_land=50.0, a_land=50.0))
    drv = line(lines, "driving")
    assert drv["status"] == status
    assert drv["group"] == "rehearse" and drv["source"] == "https://example.org/driving"
    assert line(lines, "landing")["status"] == "yes"


def test_landing_without_source_is_null_not_a_guess():
    """No limit without a source: a card limit with no source gives status null and a reason."""
    ln = line(evaluate(card(src_land=None)), "landing")
    assert ln["status"] is None and ln["reason"]
    assert "source" in ln["reason"]


def test_landing_missing_analog_value_is_null_with_reason():
    """Missing input -> null + reason; the card's own reason is carried into it."""
    c = card()
    c["mission_pct"]["landing"]["analog"] = None
    c["mission_pct"]["landing"]["reason"] = "analog terrain not exported"
    ln = line(evaluate(c), "landing")
    assert ln["status"] is None
    assert "analog terrain not exported" in ln["reason"]


# ---- cold: Koppen cold set, best possible status partial

@pytest.mark.parametrize("koppen", ["BWk", "BSk", "ET", "EF", "Dfc", "Dfd", "Dwc", "Dwd", "Dsc", "Dsd"])
def test_cold_set_members_are_partial_never_yes(koppen: str):
    """Every class of the cold set gives partial: a cold Earth climate never reaches the body's range."""
    ln = line(evaluate(card(koppen=koppen)), "cold")
    assert ln["status"] == "partial"
    assert ln["analog_value"] == koppen
    assert ln["target_value"] == "184-242"  # Mars range from bodies.json, always shown


@pytest.mark.parametrize("koppen", ["BWh", "BSh", "Cfb", "Af"])
def test_non_cold_class_is_no(koppen: str):
    """A class outside the cold set gives no."""
    assert line(evaluate(card(koppen=koppen)), "cold")["status"] == "no"


def test_cold_missing_class_is_null_with_reason():
    """No Koppen class in the card -> null + reason."""
    ln = line(evaluate(card(koppen=None)), "cold")
    assert ln["status"] is None and "koppen_class" in ln["reason"]


def test_cold_range_comes_from_the_target_body():
    """The shown range is the target body's (Moon 95-390 K), not Mars'."""
    ln = line(evaluate(card(koppen="BWk"), body="moon"), "cold")
    assert ln["target_value"] == "95-390"
    assert ln["status"] == "partial"


# ---- low_sun: yes if analog >= target - 10, partial if analog >= target / 2, else no

@pytest.mark.parametrize("a, status", [
    (40.0, "yes"),      # target 50: 40 >= 50 - 10 -> yes (boundary)
    (39.99, "partial"),  # just under
    (25.0, "partial"),   # 25 >= 50 / 2 -> partial (boundary)
    (24.99, "no"),       # just under the half
])
def test_low_sun_thresholds(a: float, status: str):
    """low_sun with target grazing 50 %: yes >= 40, partial >= 25, else no."""
    lines = evaluate(card(), lt=light(50.0, a))
    ln = line(lines, "low_sun")
    assert ln["status"] == status
    assert ln["group"] == "rehearse" and ln["unit"] == "percent"
    assert ln["target_value"] == 50.0 and ln["analog_value"] == a


class _FakeLight:
    """Synthetic light module: grazing_pct equals the latitude itself (a straight line for the scan)."""

    @staticmethod
    def sun_samples(phi_deg: float, eps_deg: float) -> np.ndarray:
        return np.array([float(phi_deg)])

    @staticmethod
    def grazing_pct(elev: np.ndarray) -> float:
        return float(elev[0])


def test_low_sun_no_latitude_reaches_a_value_above_the_earth_maximum():
    """Target above the Earth maximum of grazing_pct: status no, no latitude reaches it, the rule says so and gives the
    Earth maximum and the latitude where it occurs (both from the light module's own sampling)."""
    scan = RH.earth_grazing_scan(EARTH_EPS)
    assert scan is not None, "analog.core.light must be importable for this test"
    earth_max_lat, earth_max_pct = max(scan, key=lambda x: (x[1], -x[0]))
    ln = line(evaluate(card(), lt=light(earth_max_pct + 1.0, 0.0)), "low_sun")
    assert ln["status"] == "no"
    assert ln["lowest_abs_lat_deg"] is None
    assert "no latitude on Earth reaches the target" in ln["rule"]
    assert ln["earth_max_grazing_pct"] == pytest.approx(earth_max_pct)
    assert ln["earth_max_abs_lat_deg"] == pytest.approx(earth_max_lat)
    assert ln["reason"] is None


def test_low_sun_lowest_latitude_is_the_first_scan_point_that_reaches_the_target():
    """A reachable target: the lowest |lat| is the first scan point with grazing_pct >= target, and every lower point is
    below it."""
    scan = RH.earth_grazing_scan(EARTH_EPS)
    target = 0.9 * max(g for _, g in scan)  # reachable, and far above a twin at 0 %
    ln = line(evaluate(card(), lt=light(target, 0.0)), "low_sun")
    assert ln["status"] == "no" and ln["lowest_abs_lat_deg"] is not None
    below = [g for lat, g in scan if lat < ln["lowest_abs_lat_deg"]]
    at = dict(scan)[ln["lowest_abs_lat_deg"]]
    assert at >= target and all(g < target for g in below)
    assert "lowest |lat| on Earth reaching the target" in ln["rule"]


def test_low_sun_scan_uses_the_fake_light_module(monkeypatch):
    """Synthetic module with grazing = latitude: target 25 is first reached at 25 deg; the maximum is 90 at 90 deg."""
    monkeypatch.setattr(RH, "light_module", lambda: _FakeLight)
    ln = line(evaluate(card(), lt=light(25.0, 10.0), eps=23.44), "low_sun")
    assert ln["status"] == "no"
    assert ln["lowest_abs_lat_deg"] == pytest.approx(25.0)
    assert ln["earth_max_grazing_pct"] == pytest.approx(90.0)
    assert ln["earth_max_abs_lat_deg"] == pytest.approx(90.0)


def test_low_sun_no_without_light_module_gives_reason(monkeypatch):
    """No light stage module: the no line has no latitude and the reason 'light stage not available'."""
    monkeypatch.setattr(RH, "light_module", lambda: None)
    ln = line(evaluate(card(), lt=light(50.0, 10.0)), "low_sun")
    assert ln["status"] == "no"
    assert ln["lowest_abs_lat_deg"] is None and ln["earth_max_grazing_pct"] is None
    assert ln["reason"] == "light stage not available"


def test_low_sun_no_without_earth_obliquity_gives_reason():
    """No Earth obliquity passed: the no line says so; nothing is assumed."""
    ln = line(evaluate(card(), lt=light(50.0, 10.0), eps=None), "low_sun")
    assert ln["status"] == "no" and ln["lowest_abs_lat_deg"] is None
    assert ln["reason"] == RH.EARTH_EPS_MISSING


def test_light_window_key_maps_the_measure_id_to_the_pool_index_id():
    """light.json keys its earth_windows by the pool index id: 'pool__pool_00226' -> 'pool_00226'."""
    assert RH.light_window_key("pool__pool_00226") == "pool_00226"
    assert RH.light_window_key("gale__pool__pool_00226") is None
    assert RH.light_window_key(None) is None


def test_low_sun_is_never_guessed_without_light_values():
    """light None -> status null with the reason; no latitude, no value."""
    ln = line(evaluate(card(), lt=None), "low_sun")
    assert ln["status"] is None and ln["target_value"] is None and ln["analog_value"] is None
    assert ln["reason"] == RH.LIGHT_MISSING


def test_low_sun_missing_grazing_value_is_null():
    """Light entries present but grazing_pct missing -> null with reason."""
    ln = line(evaluate(card(), lt=light(None, 20.0)), "low_sun")
    assert ln["status"] is None and "grazing_pct" in ln["reason"]


# ---- cannot: always no, ratios from bodies.json (target / Earth)

def test_gravity_ratio_is_target_over_earth():
    """Mars gravity 3.73 over Earth 9.820 (bodies.json)."""
    ln = line(evaluate(card()), "gravity")
    assert ln["status"] == "no" and ln["group"] == "cannot" and ln["evidence"] == "published"
    assert ln["ratio"] == pytest.approx(3.73 / 9.820, rel=1e-12)
    assert ln["target_value"] == pytest.approx(3.73) and ln["analog_value"] == pytest.approx(9.820)
    assert ln["source"] == MARS_URL


def test_pressure_ratio_uses_the_pascal_values():
    """Mars 636 Pa over Earth 101400 Pa; the Moon's 3e-10 Pa gives a ratio near 3e-15."""
    ln = line(evaluate(card()), "pressure")
    assert ln["ratio"] == pytest.approx(636.0 / 101400.0, rel=1e-12)
    moon = line(evaluate(card(), body="moon"), "pressure")
    assert moon["ratio"] == pytest.approx(3e-10 / 101400.0, rel=1e-9)
    assert moon["source"] == MOON_URL


def test_day_length_ratio_moon_is_29_53():
    """Moon day length 708.72 h (29.53 x 24) over Earth 24 h -> 29.53."""
    ln = line(evaluate(card(), body="moon"), "day_length")
    assert ln["status"] == "no"
    assert ln["ratio"] == pytest.approx(708.72 / 24.0, rel=1e-12)
    assert ln["ratio"] == pytest.approx(29.53, abs=1e-9)


def test_temperature_line_carries_both_ranges_and_no_ratio():
    """Temperature is a range, not a ratio: target 184-242 K and Earth 283-293 K, ratio null."""
    ln = line(evaluate(card()), "temperature")
    assert ln["status"] == "no" and ln["ratio"] is None
    assert ln["target_value"] == "184-242" and ln["analog_value"] == "283-293"


def test_unknown_target_body_gives_null_cannot_lines():
    """A target body not in bodies.json: the cannot lines are null with a reason, never a guess."""
    lines = RH.evaluate_pair(card(), "venus", BODIES, RULES, {"target": None, "analog": None, "reason": "x"})
    for lid in ("gravity", "pressure", "temperature", "day_length"):
        ln = line(lines, lid)
        assert ln["status"] is None and "venus" in ln["reason"]


# ---- structure and mapping

def test_evaluate_pair_returns_eight_lines_in_order():
    """Four rehearse lines then four cannot lines, every contract key present on each."""
    lines = evaluate(card())
    assert [x["id"] for x in lines] == list(RH.LINE_ORDER)
    keys = {"id", "group", "label", "status", "target_value", "analog_value", "unit", "rule", "evidence", "source", "reason"}
    for x in lines:
        assert keys <= set(x)
        assert x["status"] in ("yes", "partial", "no", None)
        if x["status"] is None:
            assert x["reason"], f"{x['id']}: a null status needs a reason"


def test_earth_window_id_drops_the_target_prefix():
    """The card analog id '<target>__pool__pool_00226' maps to the window id 'pool__pool_00226'."""
    assert RH.earth_window_id("jezero", "jezero__pool__pool_00226") == "pool__pool_00226"
    assert RH.earth_window_id("jezero", "gale__pool__pool_00226") is None
    assert RH.earth_window_id("jezero", "") is None
    # unrefined (Arctic) candidate: the plain pool id is the window itself
    assert RH.earth_window_id("jezero", "pool__pool_02579") == "pool__pool_02579"


def test_no_line_has_a_nan_value():
    """Numbers that are not finite never reach the lines (they are null)."""
    lines = evaluate(card(t_land=math.nan, a_land=50.0))
    ln = line(lines, "landing")
    assert ln["status"] is None
    assert ln["target_value"] is None


def test_pair_cards_follow_the_current_ranking_including_unrefined_arctic(tmp_path, monkeypatch):
    """pipelines/rehearsal.pair_cards: a pair is a card whose analog_id is in the target's current ranking; an Arctic
    candidate that could not be refined keeps its plain pool id and is still a pair; old per-window cards are not."""
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / "pipelines"))
    import rehearsal as PR
    cards = tmp_path / PR.CARDS_REL
    cards.mkdir(parents=True)
    for aid in ("t1__pool__pool_00001", "pool__pool_02005", "pool__pool_00009"):
        (cards / f"t1__{aid}.json").write_text(json.dumps({"target_id": "t1", "analog_id": aid}), encoding="utf-8")
    rk = tmp_path / "rank.json"
    rk.write_text(json.dumps({"ranking": [{"analog_id": "t1__pool__pool_00001"}, {"analog_id": "pool__pool_02005"}]}),
                  encoding="utf-8")
    monkeypatch.setattr(PR, "ranking_file", lambda paths, tid: rk)
    got = sorted(p.name for p in PR.pair_cards(SimpleNamespace(root=tmp_path), "t1"))
    assert got == ["t1__pool__pool_02005.json", "t1__t1__pool__pool_00001.json"]
