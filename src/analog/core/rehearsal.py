"""Rehearsal plan of one target-twin pair (STANDARDS section 10.15, P-P). Pure: no file or network I/O.

Input: one pair card (data/derived/cards), the body facts (config/bodies.json), the rules (config/rehearsal_rules.json),
the light values of the target and of the twin (data/derived/light/light.json, P-S) and the Earth obliquity
(config/light.json), passed in by the pipeline.

Each line is {id, group, label, status, target_value, analog_value, unit, rule, evidence, source, reason, ratio,
lowest_abs_lat_deg, earth_max_grazing_pct, earth_max_abs_lat_deg}:
- group 'rehearse': what the Earth twin can rehearse (landing, driving, cold, low_sun);
- group 'cannot': what the twin cannot teach (gravity, pressure, temperature, day_length), always status 'no'.
- status: 'yes' | 'partial' | 'no' | None. None means an input is missing; then ``reason`` says which one. Nothing is
  guessed: a missing value never becomes 0 or a default.
- ``rule`` states how the status was judged. For a low_sun line with status 'no' it also says whether any Earth
  latitude reaches the target grazing_pct: the lowest |latitude| that does, or that no latitude does, with the Earth
  maximum and where it occurs.
- ``ratio`` is target / Earth for the cannot lines that have a ratio (gravity, pressure, day_length), else None.
- ``lowest_abs_lat_deg``: low_sun lines with status 'no' only; the lowest |latitude| on Earth whose grazing_pct reaches
  the target value, None when none does.
- ``earth_max_grazing_pct`` / ``earth_max_abs_lat_deg``: low_sun lines; the Earth maximum of grazing_pct over |lat| 0..90
  and the lowest |lat| where it occurs.

The Earth grazing values come from src/analog/core/light.py itself (sun_samples and grazing_pct, the same 72 x 144
sampling as the light stage), scanned over |lat| 0..90 every EARTH_SCAN_STEP_DEG degrees. No sun model is written here.
"""

from __future__ import annotations

import importlib
import math
from typing import Any

GROUP_REHEARSE = "rehearse"
GROUP_CANNOT = "cannot"
REHEARSE_IDS = ("landing", "driving", "cold", "low_sun")
CANNOT_IDS = ("gravity", "pressure", "temperature", "day_length")
LINE_ORDER = REHEARSE_IDS + CANNOT_IDS
LIGHT_MISSING = "light stage not available"
EARTH_EPS_MISSING = "Earth obliquity missing (config/light.json)"
EARTH_SCAN_STEP_DEG = 0.5


def earth_window_id(target_id: str, analog_id: str) -> str | None:
    """Earth window id of a card analog id, in the measure/query convention: '<target>__pool__pool_00226' ->
    'pool__pool_00226'. None when the analog id does not carry the target prefix (never guessed)."""
    prefix = f"{target_id}__"
    if not analog_id:
        return None
    if analog_id.startswith(prefix):
        rest = analog_id[len(prefix):]
        return rest or None
    # A candidate that could not be refined (Arctic: no NASADEM above 60N) keeps its plain pool id: it IS the window.
    if analog_id.startswith("pool__pool_"):
        return analog_id
    return None


def light_window_key(window_id: str | None) -> str | None:
    """Key of an Earth window in data/derived/light/light.json (earth_windows), which uses the search-pool index id:
    'pool__pool_00226' -> 'pool_00226'. None when the id is not in the pool convention."""
    if not window_id or not window_id.startswith("pool__"):
        return None
    key = window_id[len("pool__"):]
    return key or None


def _num(value: Any) -> float | None:
    """A finite number, or None. Booleans and strings are not numbers here."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    return v if math.isfinite(v) else None


def _line(line_id: str, group: str, label: str, status: str | None, target_value: Any, analog_value: Any,
          unit: str | None, rule: str | None, evidence: str, source: str | None, reason: str | None,
          ratio: float | None = None, lowest_abs_lat_deg: float | None = None,
          earth_max_grazing_pct: float | None = None, earth_max_abs_lat_deg: float | None = None) -> dict[str, Any]:
    """One line with every key of the contract (the optional keys are null when they do not apply)."""
    return {"id": line_id, "group": group, "label": label, "status": status, "target_value": target_value,
            "analog_value": analog_value, "unit": unit, "rule": rule, "evidence": evidence, "source": source,
            "reason": reason, "ratio": ratio, "lowest_abs_lat_deg": lowest_abs_lat_deg,
            "earth_max_grazing_pct": earth_max_grazing_pct, "earth_max_abs_lat_deg": earth_max_abs_lat_deg}


def _null(line_id: str, group: str, label: str, unit: str | None, evidence: str, reason: str) -> dict[str, Any]:
    """A line whose input is missing: status null with the reason."""
    return _line(line_id, group, label, None, None, None, unit, None, evidence, None, reason)


def _mission_line(kind: str, card: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    """landing / driving: |analog - target| in percentage points against the thresholds in the rules (10 and 25)."""
    spec = rules[kind]
    label, evidence, unit = spec["label"], spec["evidence"], spec["unit"]
    entry = ((card.get("mission_pct") or {}).get(kind)) or {}
    t, a = _num(entry.get("target")), _num(entry.get("analog"))
    limit, source = _num(entry.get("limit_deg")), entry.get("source")
    if t is None or a is None:
        why = entry.get("reason") or "no value"
        return _null(kind, GROUP_REHEARSE, label, unit, evidence,
                     f"card mission_pct.{kind} target or analog missing ({why})")
    if limit is None:
        return _null(kind, GROUP_REHEARSE, label, unit, evidence, f"card mission_pct.{kind}.limit_deg missing")
    if not source:
        return _null(kind, GROUP_REHEARSE, label, unit, evidence,
                     f"card mission_pct.{kind}.source missing (no limit without a source)")
    diff = abs(a - t)
    yes_max, partial_max = float(spec["yes_max_points"]), float(spec["partial_max_points"])
    status = "yes" if diff <= yes_max else "partial" if diff <= partial_max else "no"
    rule = (f"|analog - target| = {diff:.2f} points; yes if <= {yes_max:g}, partial if <= {partial_max:g}; "
            f"limit {limit:g} deg (card)")
    return _line(kind, GROUP_REHEARSE, label, status, t, a, unit, rule, evidence, source, None)


def _cold_line(card: dict[str, Any], target_body: str | None, bodies: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    """cold: the twin's Koppen class is in the cold set -> partial (best possible), else no. The target body's
    temperature range from bodies.json is always shown with it."""
    spec = rules["cold"]
    label, evidence, unit = spec["label"], spec["evidence"], spec["unit"]
    body = bodies.get(target_body) if target_body else None
    tmin, tmax = (_num(body.get("temp_min_k")), _num(body.get("temp_max_k"))) if body else (None, None)
    if tmin is None or tmax is None:
        return _null("cold", GROUP_REHEARSE, label, unit, evidence,
                     f"temperature range of body {target_body!r} missing in config/bodies.json")
    cls = (card.get("context") or {}).get("koppen_class")
    if not cls:
        return _null("cold", GROUP_REHEARSE, label, unit, evidence, "card context.koppen_class missing")
    in_set = cls in spec["cold_koppen_classes"]
    status = spec["best_status"] if in_set else "no"
    rule = (f"twin class {cls} {'in' if in_set else 'not in'} the cold set; best possible status is "
            f"{spec['best_status']}; target range {tmin:g}-{tmax:g} K from bodies.json")
    return _line("cold", GROUP_REHEARSE, label, status, f"{tmin:g}-{tmax:g}", cls, unit, rule, evidence,
                 spec["source"], None)


def light_module() -> Any | None:
    """The light stage module analog.core.light, or None when it is not present."""
    try:
        return importlib.import_module("analog.core.light")
    except ModuleNotFoundError:
        return None


def earth_grazing_scan(eps_deg: float, step_deg: float = EARTH_SCAN_STEP_DEG) -> list[tuple[float, float]] | None:
    """(|lat|, grazing_pct) for |lat| = 0, step, ..., 90 on Earth with obliquity eps_deg, from light.py's own sampling
    (sun_samples -> grazing_pct). None when the light module is not present.

    Formula: grazing_pct(sun_samples(lat, eps)) = 100 * share of the 72 x 144 samples with 0 < elevation < 10 deg.
    """
    light = light_module()
    if light is None:
        return None
    n = round(90.0 / step_deg)
    return [(i * step_deg, float(light.grazing_pct(light.sun_samples(i * step_deg, eps_deg)))) for i in range(n + 1)]


def earth_reach(target_pct: float, eps_deg: float | None) -> dict[str, Any]:
    """Earth grazing facts for one target value: the lowest |lat| whose grazing_pct >= target (None when no latitude
    reaches it), the Earth maximum and the lowest |lat| where it occurs. ``reason`` is set when the scan cannot run."""
    out: dict[str, Any] = {"lowest": None, "max_pct": None, "max_lat": None, "reason": None}
    if eps_deg is None:
        out["reason"] = EARTH_EPS_MISSING
        return out
    scan = earth_grazing_scan(float(eps_deg))
    if scan is None:
        out["reason"] = LIGHT_MISSING
        return out
    reached = [lat for lat, g in scan if g >= target_pct]
    max_lat, max_pct = max(((lat, g) for lat, g in scan), key=lambda x: (x[1], -x[0]))
    out.update(lowest=reached[0] if reached else None, max_pct=max_pct, max_lat=max_lat)
    return out


def _low_sun_line(light: dict[str, Any] | None, rules: dict[str, Any], earth_eps_deg: float | None) -> dict[str, Any]:
    """low_sun: analog grazing_pct against the target's: yes if analog >= target - 10 points, partial if analog >= target
    / 2, else no. For a no line the rule also says whether any Earth latitude reaches the target value."""
    spec = rules["low_sun"]
    label, evidence, unit = spec["label"], spec["evidence"], spec["unit"]
    light = light or {}
    t_entry, a_entry = light.get("target"), light.get("analog")
    if not isinstance(t_entry, dict) or not isinstance(a_entry, dict):
        return _null("low_sun", GROUP_REHEARSE, label, unit, evidence, light.get("reason") or LIGHT_MISSING)
    t, a = _num(t_entry.get("grazing_pct")), _num(a_entry.get("grazing_pct"))
    if t is None or a is None:
        return _null("low_sun", GROUP_REHEARSE, label, unit, evidence, "grazing_pct missing in light values")
    yes_within = float(spec["yes_within_points"])
    frac = float(spec["partial_min_fraction_of_target"])
    if a >= t - yes_within:
        status = "yes"
    elif a >= t * frac:
        status = "partial"
    else:
        status = "no"
    rule = (f"yes if analog >= target - {yes_within:g} ({t - yes_within:.2f}); partial if analog >= "
            f"{frac:g} x target ({t * frac:.2f}); grazing band {spec['grazing_band_deg'][0]}-"
            f"{spec['grazing_band_deg'][1]} deg")
    reach = earth_reach(t, earth_eps_deg)
    lowest = None
    reason = None
    if reach["reason"] is not None:
        if status == "no":
            reason = reach["reason"]
    elif status == "no":
        if reach["lowest"] is None:
            rule += (f"; no latitude on Earth reaches the target {t:.2f} %: Earth maximum {reach['max_pct']:.2f} % "
                     f"at |lat| {reach['max_lat']:.1f} deg (scan 0-90 deg, step {EARTH_SCAN_STEP_DEG:g} deg, "
                     f"obliquity {float(earth_eps_deg):g} deg)")
        else:
            lowest = reach["lowest"]
            rule += (f"; lowest |lat| on Earth reaching the target {t:.2f} %: {lowest:.1f} deg (scan step "
                     f"{EARTH_SCAN_STEP_DEG:g} deg)")
    return _line("low_sun", GROUP_REHEARSE, label, status, t, a, unit, rule, evidence, spec["source"], reason,
                 lowest_abs_lat_deg=lowest,
                 earth_max_grazing_pct=reach["max_pct"], earth_max_abs_lat_deg=reach["max_lat"])


def _cannot_line(kind: str, bodies: dict[str, Any], target_body: str | None, rules: dict[str, Any]) -> dict[str, Any]:
    """cannot: always no. Value and ratio come from bodies.json (target body vs Earth)."""
    spec = rules["cannot"][kind]
    label, evidence, unit = spec["label"], spec["evidence"], spec["unit"]
    twin = rules["twin_body"]
    tb = bodies.get(target_body) if target_body else None
    eb = bodies.get(twin)
    if tb is None or eb is None:
        return _null(kind, GROUP_CANNOT, label, unit, evidence,
                     f"body facts of {target_body!r} or {twin!r} missing in config/bodies.json")
    source = tb.get("source_url")
    if not source:
        return _null(kind, GROUP_CANNOT, label, unit, evidence,
                     f"source_url of body {target_body!r} missing in config/bodies.json")
    if kind == "temperature":
        keys = spec["body_keys"]
        tv = [_num(tb.get(k)) for k in keys]
        av = [_num(eb.get(k)) for k in keys]
        if any(v is None for v in tv + av):
            return _null(kind, GROUP_CANNOT, label, unit, evidence, "temperature range missing in config/bodies.json")
        rule = (f"target range {tv[0]:g}-{tv[1]:g} K vs Earth printed range {av[0]:g}-{av[1]:g} K "
                f"(config/bodies.json); cannot group: status no by definition")
        return _line(kind, GROUP_CANNOT, label, "no", f"{tv[0]:g}-{tv[1]:g}", f"{av[0]:g}-{av[1]:g}", unit, rule,
                     evidence, source, None)
    key = spec["body_key"]
    t, a = _num(tb.get(key)), _num(eb.get(key))
    if t is None or a is None or a == 0:
        return _null(kind, GROUP_CANNOT, label, unit, evidence, f"{key} missing or zero in config/bodies.json")
    ratio = t / a
    rule = f"ratio target / Earth = {t:.6g} / {a:.6g} = {ratio:.6g} (config/bodies.json)"
    return _line(kind, GROUP_CANNOT, label, "no", t, a, unit, rule, evidence, source, None,
                 ratio=ratio if spec.get("ratio") else None)


def evaluate_pair(card: dict[str, Any], target_body: str | None, bodies: dict[str, Any], rules: dict[str, Any],
                  light: dict[str, Any] | None, earth_eps_deg: float | None = None) -> list[dict[str, Any]]:
    """All lines of the rehearsal plan of one pair, in the order of LINE_ORDER.

    Formulas: landing / driving: yes if |a - t| <= 10, partial if <= 25, else no (points). cold: partial if the twin
    class is in the cold set, else no. low_sun: yes if a >= t - 10, partial if a >= t / 2, else no; for no, the lowest
    Earth |lat| with grazing_pct >= t on a 0.5 deg scan of |lat| 0..90, or none. cannot: status no, ratio = target /
    Earth from bodies.json.
    ``light`` is {"target": {grazing_pct, ...} | None, "analog": {...} | None, "reason": str} or None when the light
    stage output is absent. ``earth_eps_deg`` is the Earth obliquity (config/light.json). Missing inputs give status
    None and a reason.
    """
    lines = [
        _mission_line("landing", card, rules),
        _mission_line("driving", card, rules),
        _cold_line(card, target_body, bodies, rules),
        _low_sun_line(light, rules, earth_eps_deg),
    ]
    lines += [_cannot_line(k, bodies, target_body, rules) for k in CANNOT_IDS]
    return lines
