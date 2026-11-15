"""Discoveries (STANDARDS 10.13): Earth windows that are a top-3 twin of a Mars or Moon target or of a Mars atlas cell,
and are NEW (not inside a known analog region). Re-runnable: it reads the current known-regions file and the Earth context
cache, so run it after novelty changes (earth_context.py refreshes novelty; export_viz reads the same cache).

Window identity: the analog id used in the rankings (a refined window of one target-candidate pair has its own id).
Output: site/data/discoveries.json, with the counts, the windows (novelty, context, the cells and targets that point
at them) and the number of known regions used. Novelty null (not classified) is counted apart, never as new.

Usage: .venv/Scripts/python.exe pipelines/discoveries.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    Paths,
    RunLog,
    load_json,
    make_paths,
    parse_args,
    place_id,
    provenance_block,
    ranking_file,
    sites_list,
    write_json,
)
import earth_context as EC  # noqa: E402

TOP = 3


def sources(paths: Paths, log: RunLog) -> list[tuple[str, str, int, str]]:
    """(kind, owner id, rank, analog id) for every top-3 twin of a Moon/Mars target or a Mars atlas cell."""
    out: list[tuple[str, str, int, str]] = []
    for t in sites_list(paths):
        if t.get("role") != "target" or t.get("body") not in ("mars", "moon"):
            continue
        rp = ranking_file(paths, t["id"])
        if not rp.exists():
            log.event("warn", "target has no ranking: not a discovery source", id=t["id"])
            continue
        for row in load_json(rp).get("ranking", [])[:TOP]:
            out.append(("target", t["id"], int(row["rank"]), row["analog_id"]))
    cells_path = paths.site_data / "atlas" / "mars_cells.json"
    if cells_path.exists():
        for cell in load_json(cells_path):
            for rank, tw in enumerate(cell["twins"][:TOP], start=1):
                out.append(("mars_cell", cell["id"], rank, tw["analog_id"]))
    else:
        log.event("warn", "Mars atlas not written: mars cells not counted", path=paths.rel(cells_path))
    return out


def place_counts(windows: list[dict[str, Any]]) -> tuple[dict[str, int], list[str]]:
    """Counts by Earth place (place_id). A place whose windows carry different novelty is 'mixed' (never new or known);
    returns the counts and the mixed place ids."""
    by_place: dict[str, set] = {}
    for w in windows:
        by_place.setdefault(w["place_id"], set()).add(w["novelty"])
    counts = {"new": 0, "known_region": 0, "unclassified": 0, "mixed": 0}
    mixed = []
    for pid, nov in sorted(by_place.items()):
        if len(nov) > 1:
            counts["mixed"] += 1
            mixed.append(pid)
        else:
            v = next(iter(nov))
            counts["unclassified" if v is None else v] += 1
    return {"unique_places": len(by_place), **counts}, mixed


def run(paths: Paths) -> int:
    """Write site/data/discoveries.json. Returns the number of unique windows counted."""
    log = RunLog(paths.derived / "context", "discoveries")
    regions, reason = EC.known_regions(paths)
    cache_path = paths.derived / "context" / EC.CONTEXT_FILE
    if not cache_path.exists():
        log.event("error", "refused: Earth context cache missing (earth_context.py first)", path=paths.rel(cache_path))
        return 0
    cache = load_json(cache_path)["windows"]
    src = sources(paths, log)
    by_window: dict[str, dict[str, Any]] = {}
    for kind, owner, rank, aid in src:
        w = by_window.setdefault(aid, {"analog_id": aid, "uses": []})
        w["uses"].append({"kind": kind, "id": owner, "rank": rank})
    windows = []
    counts = {"new": 0, "known_region": 0, "unclassified": 0}
    for aid, w in sorted(by_window.items()):
        entry = cache.get(aid)
        if entry is None:
            log.event("warn", "twin without context entry: counted as unclassified", analog=aid)
            novelty, known_id, ctx, lat, lon = None, None, None, None, None
        else:
            novelty, known_id = entry.get("novelty"), entry.get("known_region_id")
            ctx, lat, lon = entry.get("context"), entry.get("lat"), entry.get("lon")
        key = "unclassified" if novelty is None else novelty
        counts[key] += 1
        windows.append({"analog_id": aid, "place_id": place_id(aid), "lat": lat, "lon": lon, "novelty": novelty,
                        "known_region_id": known_id, "context": ctx, "uses": w["uses"]})
    pcounts, mixed = place_counts(windows)
    for pid in mixed:
        log.event("warn", "place with windows of different novelty: counted as mixed, not as new", place=pid)
    doc = {
        "rule": "unique Earth windows that are a top-3 twin of a Mars or Moon target or of a Mars atlas cell; "
                "new = not inside a known analog region (circle approximation); unclassified = no novelty (not counted as new)",
        "place_rule": "place_counts count Earth PLACES: a refined window '<target>__pool__pool_N' is the same place as "
                      "'pool__pool_N' (re-centred by a few km). A place whose windows differ in novelty is 'mixed'. "
                      "Use place_counts for public figures; counts (by window) are kept for tracing.",
        "counts": {"unique_windows": len(windows), **counts},
        "place_counts": pcounts,
        "from": {"targets_with_moon_or_mars_body": sum(1 for u in src if u[0] == "target") // TOP,
                 "mars_cells": len({u[1] for u in src if u[0] == "mars_cell"})},
        "known_regions": None if regions is None else len(regions),
        "known_regions_source": "config/known_analog_regions.json" if regions is not None else f"null: {reason}",
        "windows": windows,
        "provenance": provenance_block(paths, "cards", []),
    }
    write_json(paths.site_data / "discoveries.json", doc)
    log.event("info", "discoveries written", unique=len(windows), **counts,
              places=pcounts["unique_places"], places_new=pcounts["new"], places_known=pcounts["known_region"],
              places_mixed=pcounts["mixed"], known_regions=doc["known_regions"])
    return len(windows)


def main(argv: list[str] | None = None) -> int:
    args = parse_args("Discoveries: top-3 Earth twins of Moon/Mars targets and Mars cells, new vs known (STANDARDS 10.13).")
    paths = make_paths(args.root, args.sample)
    return 0 if run(paths) else 2


if __name__ == "__main__":
    raise SystemExit(main())
