"""Site figures from the facts ledger (STANDARDS 10.14, P-G): site/data/facts.json.

The interface never computes or types a public figure: it reads this file. Every entry names the ledger view it comes
from, its value, a display string (the rounding used everywhere) and a one-line definition in plain English.
Reads data/derived/facts/facts.duckdb READ-ONLY. Exits 1 if a view is missing or empty, or if the place counts of the
ledger differ from site/data/discoveries.json (the two must agree).

Usage: .venv/Scripts/python.exe tools/export_site_facts.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data" / "derived" / "facts" / "facts.duckdb"
OUT = ROOT / "site" / "data" / "facts.json"
DISCOVERIES = ROOT / "site" / "data" / "discoveries.json"


def _int(v: float) -> str:
    return f"{int(round(v)):,}"


def _pct(v: float) -> str:
    return f"{v:.1f}%"


# key: (ledger view, unit, display format, definition)
FIGURES = {
    "sites_measured": ("n_targets", "sites", _int, "Mars and Moon landing sites whose ground we measured from NASA elevation models."),
    "sites_mars": ("n_targets_mars", "sites", _int, "Mars sites measured (NASA MRO CTX elevation models, 20 m)."),
    "sites_moon": ("n_targets_moon", "sites", _int, "Moon sites measured (NASA LRO LOLA 5 m / 20 m and LROC NAC elevation models)."),
    "earth_places_searched": ("n_pool_windows", "places", _int, "Bare-ground places on Earth (8 km discs) searched for twins: NASA NASADEM from 56 S to 60 N, Copernicus GLO-30 from 60 N to 84 N. Places with 20% or more ice are left out."),
    "earth_places_nasadem": ("n_pool_windows_nasadem", "places", _int, "Bare-ground Earth places searched from NASA NASADEM elevation, 56 S to 60 N."),
    "earth_places_arctic": ("n_pool_windows_arctic", "places", _int, "Bare-ground Earth places searched from Copernicus GLO-30 elevation, 60 N to 84 N (the Arctic)."),
    "earth_places_excluded": ("n_pool_excluded", "places", _int, "Earth places left out of the search: ice covers 20% or more of the disc, or bare ground covers less than 80% of it."),
    "window_diameter_km": ("window_diameter_km", "km", lambda v: f"{v:g} km", "Every place, on every world, is a disc of this diameter, measured the same way."),
    "mars_places_measured": ("mars_cells_measured", "places", _int, "Places across Mars measured from NASA MRO CTX elevation models and compared with Earth."),
    "mars_gap_places": ("mars_gap_cells", "places", _int, "Mars places with no Earth place within the measurement noise of their relief class."),
    "mars_gap_pct": ("mars_gap_pct", "percent", _pct, "Share of the measured Mars places that Earth cannot rehearse (no twin within measurement noise)."),
    "mars_gap_pct_ci_low": ("mars_gap_wilson_lo", "percent", _pct, "Lower end of the 95% Wilson interval of the Mars gap share."),
    "mars_gap_pct_ci_high": ("mars_gap_wilson_hi", "percent", _pct, "Upper end of the 95% Wilson interval of the Mars gap share."),
    "mars_rehearsable_pct": ("mars_rehearsable_pct", "percent", _pct, "Share of the measured Mars places that have at least one Earth twin within measurement noise."),
    "moon_sites": ("moon_targets_total", "sites", _int, "Moon sites checked for an Earth twin."),
    "moon_gap_sites": ("moon_gap_targets", "sites", _int, "Moon sites with no Earth place within measurement noise (the Earth search covers 56 S to 84 N; places with 20% or more ice are left out)."),
    "moon_gap_sites_nasadem": ("moon_gap_targets_nasadem", "sites", _int, "Moon sites with no NASADEM Earth place within measurement noise (NASADEM covers 56 S to 60 N only)."),
    "mars_gap_places_nasadem": ("mars_gap_cells_nasadem", "places", _int, "Mars places with no NASADEM Earth place (56 S to 60 N) within the measurement noise of their relief class."),
    "mars_gap_pct_nasadem": ("mars_gap_pct_nasadem", "percent", _pct, "Share of the measured Mars places with no NASADEM Earth twin (56 S to 60 N) within measurement noise."),
    "mars_rehearsable_pct_nasadem": ("mars_rehearsable_pct_nasadem", "percent", _pct, "Share of the measured Mars places with at least one NASADEM Earth twin (56 S to 60 N) within measurement noise."),
    "twin_places": ("n_discovery_places", "places", _int, "Distinct Earth places that are a top-three twin of a site or of a Mars place (a place counts once)."),
    "new_twin_places": ("n_new_places", "places", _int, "Twin places outside the well-known analog regions (drawn as circles, an approximation)."),
    "known_twin_places": ("n_known_places", "places", _int, "Twin places inside one of the well-known analog regions."),
    "known_regions": ("n_known_regions", "regions", _int, "Well-known Earth analog regions used to tell new from known."),
    "earth_low_sun_max_pct": ("earth_grazing_max_pct", "percent", _pct, "Most grazing sunlight any place on Earth gets; far below the lunar south pole, so low sun cannot be rehearsed on Earth."),
    "validation_auc": ("auc_v13", "AUC", lambda v: f"{v:.2f}", "Blind test on 15 new Earth regions: how well the measure tells same-kind terrain from different (0.5 = chance, 1 = perfect). Pre-registered pass mark: 0.70."),
}


def main(ledger: Path = LEDGER, out_path: Path = OUT, discoveries: Path = DISCOVERIES) -> int:
    if not ledger.exists():
        print(f"refused: ledger missing ({ledger}); run tools/build_ledger.py first")
        return 1
    con = duckdb.connect(str(ledger), read_only=True)
    out: dict[str, dict] = {}
    for key, (view, unit, fmt, definition) in FIGURES.items():
        try:
            row = con.execute(f"SELECT value FROM {view}").fetchone()
        except duckdb.Error as e:
            print(f"refused: view {view} not in the ledger ({e})")
            return 1
        if row is None or row[0] is None:
            print(f"refused: view {view} is empty")
            return 1
        v = float(row[0])
        out[key] = {"value": v, "display": fmt(v), "unit": unit, "ledger_view": view, "definition": definition}

    moon_gap = con.execute(
        "SELECT g.subject_id, n.value_text FROM facts g LEFT JOIN facts n ON n.subject_id = g.subject_id "
        "AND n.subject_type = 'target' AND n.property = 'name' "
        "WHERE g.subject_type = 'target' AND g.property = 'earth_gap' AND g.value_num = 1 AND g.body = 'moon' "
        "ORDER BY g.subject_id").fetchall()
    out["moon_gap_sites"]["ids"] = [r[0] for r in moon_gap]

    disc = json.loads(discoveries.read_text(encoding="utf-8"))
    pc = disc.get("place_counts") or {}
    for key, k in (("twin_places", "unique_places"), ("new_twin_places", "new"), ("known_twin_places", "known_region")):
        if int(out[key]["value"]) != int(pc.get(k, -1)):
            print(f"refused: ledger {key}={out[key]['value']} differs from discoveries.json place_counts.{k}={pc.get(k)}")
            return 1
    if len(out["moon_gap_sites"]["ids"]) != int(out["moon_gap_sites"]["value"]):
        print("refused: moon gap ids do not match the moon gap count")
        return 1

    doc = {
        "generated_by": "tools/export_site_facts.py",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ledger": "data/derived/facts/facts.duckdb",
        "rule": "Public figures are read from this file only. 'display' is the rounding to show; 'value' is exact.",
        "figures": out,
    }
    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out_path} ({len(out)} figures)")
    return export_explain()


def export_explain(src: Path = ROOT / "config" / "explain.json", measure: Path = ROOT / "config" / "measure.json",
                   out_path: Path = ROOT / "site" / "data" / "explain.json") -> int:
    """Copy the hand-written explanations to the site, adding in_distance from the frozen measure config.
    Refuses if the explained features are not exactly the configured ones."""
    ex = json.loads(src.read_text(encoding="utf-8"))
    feats = json.loads(measure.read_text(encoding="utf-8"))["features"]
    if set(ex["features"]) != set(feats):
        print(f"refused: explain.json features {sorted(ex['features'])} != measure.json features {sorted(feats)}")
        return 1
    for fid, f in ex["features"].items():
        f["in_distance"] = bool(feats[fid].get("in_distance"))
    ex["generated_by"] = "tools/export_site_facts.py (from config/explain.json + config/measure.json)"
    out_path.write_text(json.dumps(ex, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out_path} ({len(ex['features'])} features)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
