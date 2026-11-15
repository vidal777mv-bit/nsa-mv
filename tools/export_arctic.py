"""Export the Arctic probe (EXPERIMENT, STANDARDS 10.14) to site/data/arctic.json for the UI.

Reads data/derived/arctic_probe/ only (results.json and measures.json). Writes one small JSON:
- mars_closed_cell_ids: the Mars gap cells whose nearest Arctic window is within the tie threshold (87 of 211);
- moon_closed_target_ids: the Moon gap targets closed (the gap set of the ledger, 2 of 3);
- windows: only the Arctic windows that close something (a Mars gap cell or a Moon gap target): {id, lat, lon, place};
- counts: the totals the note and the ledger quote.

Closures are ties within sensor noise (D <= the rugged p95), and the count is a lower bound (n = 400 of 2,065 candidates).
Nothing here is typed by hand: every value comes from data/derived/arctic_probe.

Usage: .venv/Scripts/python.exe tools/export_arctic.py [--root <project root>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "analog.arctic_site/1"
RESULTS_SCHEMA = "analog.arctic_probe.results/1"
GENERATED_WITH = ("Code written with AI assistance (Claude, Anthropic) under the team's direction; data computed by this "
                  "code from the listed sources.")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _place_name(place: dict[str, Any] | None) -> str | None:
    """The place name of a window (Natural Earth admin-1 region), or None over sea ice or without a match."""
    return (place or {}).get("name")


def build_doc(results: dict[str, Any], measures: dict[str, Any], results_sha: str) -> dict[str, Any]:
    """The site document, built from the probe results and its window list (pure: no file access)."""
    if results.get("schema") != RESULTS_SCHEMA:
        raise ValueError(f"arctic results schema is {results.get('schema')!r}, expected {RESULTS_SCHEMA!r}")
    mars = results["mars"]
    cells = results["mars_cells"]
    moon = results["moon_artemis_iii"]
    closed_cells = sorted(c["id"] for c in cells if c["closed"])
    if len(closed_cells) != mars["closed"]:
        raise ValueError(f"{len(closed_cells)} closed cells in the table, results say {mars['closed']}")
    gap_moon = [t for t in moon if t["gap_in_pool"]]
    closed_moon = [t for t in gap_moon if t["closed"]]

    # the windows that close something: Mars cells (cells_closed > 0) and the Moon gap targets they close
    win: dict[str, dict[str, Any]] = {}
    for w in mars["closing_windows"]:
        if w["cells_closed"] > 0:
            win[w["arctic_id"]] = {"id": w["arctic_id"], "lat": w["lat"], "lon": w["lon"],
                                   "place": _place_name(w.get("place"))}
    for t in closed_moon:
        win.setdefault(t["arctic_id"], {"id": t["arctic_id"], "lat": t["arctic_lat"], "lon": t["arctic_lon"],
                                        "place": _place_name(t.get("arctic_place"))})
    if sum(w["cells_closed"] for w in mars["closing_windows"]) != mars["closed"]:
        raise ValueError("the closing windows do not account for every closed cell")

    window_rows = sorted(win.values(), key=lambda w: w["id"])
    lats = [w["lat"] for w in measures.get("windows", []) if w.get("status") == "ok"]
    band = (math.floor(min(lats)), math.ceil(max(lats)))
    tie = results["tie_thresholds_p95"]["rugged"]
    n_meas, n_cand = results["n_arctic_windows_measured"], results["candidates_kept_by_pool_rule"]
    return {
        "provenance": {
            "schema": SCHEMA,
            "created": results["created"],
            "config_version": results.get("config_version"),
            "code_version": "uncommitted",
            "inputs": [{"source_id": "arctic_probe_results", "path": "data/derived/arctic_probe/results.json",
                        "sha256": results_sha}],
            "generated_with": GENERATED_WITH,
        },
        "note": (f"Experiment: Copernicus GLO-30 Arctic windows {band[0]}-{band[1]}N; closures are ties within sensor "
                 f"noise (D <= p95 {tie:.3f}); a lower bound (n={n_meas} of {n_cand} candidates)."),
        "mars_closed_cell_ids": closed_cells,
        "moon_closed_target_ids": [t["id"] for t in closed_moon],
        "windows": window_rows,
        "counts": {
            "mars_gap_cells": mars["n_gap_cells"],
            "mars_gap_cells_closed": len(closed_cells),
            "moon_gap_targets": len(gap_moon),
            "moon_gap_targets_closed": len(closed_moon),
            "windows_measured": n_meas,
            "windows_candidates": n_cand,
            "windows_closing": len(window_rows),
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export the Arctic probe to site/data/arctic.json (reads arctic_probe only).")
    ap.add_argument("--root", default=str(ROOT), help="project root (default: this repository)")
    args = ap.parse_args(argv)
    root = Path(args.root)
    src = root / "data" / "derived" / "arctic_probe"
    results_path, measures_path = src / "results.json", src / "measures.json"
    if not results_path.exists() or not measures_path.exists():
        print(f"arctic probe outputs not found in {src}")
        return 2
    results = json.loads(results_path.read_text(encoding="utf-8"))
    measures = json.loads(measures_path.read_text(encoding="utf-8"))
    doc = build_doc(results, measures, _sha256(results_path))
    out = root / "site" / "data" / "arctic.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(doc['windows'])} windows, {len(doc['mars_closed_cell_ids'])} Mars cells, "
          f"{len(doc['moon_closed_target_ids'])} Moon targets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
