"""Read-only check of site/data/ against STANDARDS 10.5, 10.6, 10.9 and 10.12 (sample/ is never read).

Checks:
- targets.json: every target has its fields (10.9), a thumbnail that exists, and a rankings/<id>.json file;
- rankings: every entry has rank, D, tie_group, analog_place and a card path that exists (or null when the analog
  terrain was not exported, which is then reported as a note);
- cards (10.5, 10.12): required fields; in_distance and context_features partition the six features; similar and
  different use in_distance only; context_similar and context_different use the context features; vertical_exaggeration
  in [1, 10]; analog_place null or {name, admin1, country, source}; mission_pct with landing and driving;
- terrain folders (10.6, 10.8): height.bin = 269 * 269 * 4 bytes, layers_<body>.bin = 269 * 269 bytes for each body in
  meta.json, hillshade.png and meta.json present; the analog's layer file for the target's body exists;
- bodies.json, missions.json, validation.json and viz.json parse, and validation.json has the v1.2, v1.3 and v1.3_noise
  blocks.
- root files the interface reads (ROOT_FILE_KEYS: facts, ties, explain, sources, tilt): each parses and has its main keys.
- rehearsal/ (STANDARDS 10.15, P-P): when the folder exists, every pair card in cards/ has a rehearsal file with the same
  name, no rehearsal file lacks its card, each file has {provenance, target_id, analog_id, lines} with the eight lines in
  order, a status of yes | partial | no | null (null needs a reason), group 'cannot' lines are status no. When the folder
  does not exist yet it is a note, as for the atlas.
- light.json (P-S, site/data/light.json): when present it parses and has the targets and earth_windows blocks; when
  absent it is a note (the light stage is not built yet).
- arctic.json (STANDARDS 10.14 experiment, tools/export_arctic.py): when present it has the keys provenance, note,
  mars_closed_cell_ids, moon_closed_target_ids, windows and counts; the id lists and the windows agree with the counts
  (closed cells, closed Moon targets, windows that close something); each window has id, lat, lon, place. When absent
  it is a note.

Orphans: files under site/data/ (except sample/) that no checked document references. They are LISTED with their sizes,
never deleted. They are reported as notes; --strict makes them count as problems.

Exit codes: 0 no problems; 1 at least one problem (or an orphan with --strict); 2 site/data missing.

Usage: .venv/Scripts/python.exe tools/check_site_data.py [--root <project root>] [--strict]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from analog.core import measure as meas  # noqa: E402

N_TERRAIN = 269  # 2 * ceil(4000 / 30) + 1 (STANDARDS 10.6)
HEIGHT_BYTES = N_TERRAIN * N_TERRAIN * 4
LAYER_BYTES = N_TERRAIN * N_TERRAIN
TARGET_KEYS = ("id", "body", "name", "lat", "lon", "thumbnail", "status", "landing_class", "mission", "year",
               "outcome_note", "center_note", "unlocked")
CARD_KEYS = ("target_id", "analog_id", "rank", "D", "tie_group", "features", "similar", "different",
             "context_similar", "context_different", "in_distance", "context_features", "vertical_exaggeration",
             "analog_place", "mission_pct", "rotation_deg", "files", "provenance", "context", "novelty",
             "known_region_id", "refined")
COVERAGE_BODIES = ("mars", "moon", "earth")
COVERAGE_CELLS = 360 * 180
COVERAGE_CLASSES = {"0": "out_of_reach", "1": "to_discover", "2": "unlocked"}
ATLAS_KEYS = ("id", "lat", "lon", "features", "twins", "mission_pct")
TWIN_KEYS = ("analog_id", "D", "tie_group", "analog_place", "novelty", "known_region_id", "context")
RANK_KEYS = ("rank", "analog_id", "D", "tie_group", "lat", "lon", "card", "analog_place", "context", "novelty",
             "known_region_id", "refined")
PLACE_KEYS = ("name", "admin1", "country", "source")
VALIDATION_BLOCKS = ("v1.2", "v1.3", "v1.3_noise")
REHEARSAL_KEYS = ("provenance", "target_id", "analog_id", "lines")
REHEARSAL_LINE_IDS = ("landing", "driving", "cold", "low_sun", "gravity", "pressure", "temperature", "day_length")
REHEARSAL_LINE_KEYS = ("id", "group", "label", "status", "target_value", "analog_value", "unit", "rule", "evidence",
                       "source", "reason")
REHEARSAL_STATUSES = ("yes", "partial", "no", None)
REHEARSAL_EVIDENCE = ("derived observation", "reference comparison", "published")
LIGHT_BLOCKS = ("targets", "earth_windows")
ARCTIC_KEYS = ("provenance", "note", "mars_closed_cell_ids", "moon_closed_target_ids", "windows", "counts")
ARCTIC_COUNT_KEYS = ("mars_gap_cells", "mars_gap_cells_closed", "moon_gap_targets", "moon_gap_targets_closed",
                     "windows_measured", "windows_candidates", "windows_closing")
ARCTIC_WINDOW_KEYS = ("id", "lat", "lon", "place")
# Root files the interface loads (app.js: facts, tilt; app2.js: explain, facts, sources, ties, tilt via init). Each must
# parse and carry its main keys; a missing one is a problem because the interface requests it unconditionally.
ROOT_FILE_KEYS = {
    "facts.json": ("generated_by", "ledger", "figures"),
    "ties.json": ("generated_by", "rule", "targets"),
    "explain.json": ("doc", "similarity", "features", "layers", "mission_pct", "scope"),
    "sources.json": ("generated_by", "sources", "by_url"),
    "tilt.json": ("generated_by", "method", "terrains"),
}


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    referenced: set[str] = field(default_factory=set)
    counts: dict[str, int] = field(default_factory=lambda: {"targets": 0, "rankings": 0, "cards": 0, "terrains": 0})
    folders: set[str] = field(default_factory=set)

    def problem(self, msg: str) -> None:
        self.problems.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)


def _load(path: Path, rep: Report, label: str) -> Any:
    """JSON of a file, or None with a problem recorded (never raises on a bad file)."""
    if not path.exists():
        rep.problem(f"{label}: missing ({path.name})")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        rep.problem(f"{label}: does not parse ({exc})")
        return None


def _rel(data: Path, path: Path) -> str:
    return path.relative_to(data).as_posix()


def check_terrain(data: Path, folder_rel: str, rep: Report) -> dict[str, Any] | None:
    """One terrain folder (10.6). Returns its meta.json when readable."""
    folder = data / folder_rel.rstrip("/")
    if not folder.is_dir():
        rep.problem(f"terrain folder missing: {folder_rel}")
        return None
    rep.folders.add(folder_rel.rstrip("/"))
    rep.counts["terrains"] = len(rep.folders)
    height = folder / "height.bin"
    if not height.exists() or height.stat().st_size != HEIGHT_BYTES:
        rep.problem(f"{folder_rel}height.bin: missing or not {HEIGHT_BYTES} bytes")
    else:
        rep.referenced.add(_rel(data, height))
    hill = folder / "hillshade.png"
    if not hill.exists():
        rep.problem(f"{folder_rel}hillshade.png: missing")
    else:
        rep.referenced.add(_rel(data, hill))
    meta = _load(folder / "meta.json", rep, f"{folder_rel}meta.json")
    if meta is None:
        return None
    rep.referenced.add(_rel(data, folder / "meta.json"))
    if meta.get("n") != N_TERRAIN:
        rep.problem(f"{folder_rel}meta.json: n is {meta.get('n')}, expected {N_TERRAIN}")
    layers = meta.get("layers") or {}
    for body, fname in layers.items():
        lp = folder / fname
        if not lp.exists() or lp.stat().st_size != LAYER_BYTES:
            rep.problem(f"{folder_rel}{fname}: missing or not {LAYER_BYTES} bytes")
        else:
            rep.referenced.add(_rel(data, lp))
    return meta


def check_card(data: Path, card_rel: str, rank_row: dict[str, Any], target_body: str,
               rep: Report) -> None:
    """One card (10.5 and 10.12) and the two terrain folders it names."""
    cpath = data / card_rel
    card = _load(cpath, rep, card_rel)
    if card is None:
        return
    rep.referenced.add(card_rel)
    rep.counts["cards"] += 1
    missing = [k for k in CARD_KEYS if k not in card]
    if missing:
        rep.problem(f"{card_rel}: missing fields {missing}")
        return
    feats = set(meas.FEATURE_IDS)
    ind, ctx = set(card["in_distance"]), set(card["context_features"])
    if ind | ctx != feats or ind & ctx:
        rep.problem(f"{card_rel}: in_distance and context_features do not partition the six features")
    if not set(card["similar"]) | set(card["different"]) <= ind:
        rep.problem(f"{card_rel}: similar/different contain a feature outside in_distance")
    if not set(card["context_similar"]) | set(card["context_different"]) <= ctx:
        rep.problem(f"{card_rel}: context_similar/context_different contain a feature outside context_features")
    ve = card["vertical_exaggeration"]
    if not isinstance(ve, (int, float)) or not 1.0 <= float(ve) <= 10.0:
        rep.problem(f"{card_rel}: vertical_exaggeration {ve} outside [1, 10]")
    place = card["analog_place"]
    if place is not None and not all(k in place for k in PLACE_KEYS):
        rep.problem(f"{card_rel}: analog_place lacks {PLACE_KEYS}")
    if not {"landing", "driving"} <= set(card["mission_pct"]):
        rep.problem(f"{card_rel}: mission_pct lacks landing or driving")
    for kind in ("landing", "driving"):
        entry = card["mission_pct"].get(kind) or {}
        for name in ("target", "analog", "source"):
            if entry.get(name) is None:
                rep.problem(f"{card_rel}: mission_pct.{kind}.{name} is null")
    if card["target_id"] != rank_row.get("target_id", card["target_id"]):
        rep.problem(f"{card_rel}: target_id mismatch")
    files = card["files"]
    tmeta = check_terrain(data, files["target"], rep)
    ameta = check_terrain(data, files["analog"], rep)
    if ameta is not None and target_body not in (ameta.get("layers") or {}):
        rep.problem(f"{card_rel}: analog terrain has no layers_{target_body}.bin (its target's body)")
    if tmeta is not None and target_body not in (tmeta.get("layers") or {}):
        rep.problem(f"{card_rel}: target terrain has no layers_{target_body}.bin")


def check_site(data: Path, strict: bool = False) -> Report:
    """Run every check on a site/data folder and return the report (read-only)."""
    rep = Report()
    if not data.is_dir():
        rep.problem(f"site/data not found: {data}")
        return rep

    targets_doc = _load(data / "targets.json", rep, "targets.json")
    rep.referenced.add("targets.json")
    targets = (targets_doc or {}).get("targets", []) if isinstance(targets_doc, dict) else []
    for t in targets:
        rep.counts["targets"] += 1
        tid = t.get("id")
        missing = [k for k in TARGET_KEYS if k not in t]
        if missing:
            rep.problem(f"targets.json {tid}: missing fields {missing}")
        thumb = t.get("thumbnail")
        if thumb:
            if (data / thumb).exists():
                rep.referenced.add(thumb)
            else:
                rep.problem(f"targets.json {tid}: thumbnail {thumb} missing")
        rk_rel = f"rankings/{tid}.json"
        rk = _load(data / rk_rel, rep, rk_rel)
        if rk is None:
            continue
        rep.referenced.add(rk_rel)
        rep.counts["rankings"] += 1
        for row in rk.get("ranking", []):
            rmissing = [k for k in RANK_KEYS if k not in row]
            if rmissing:
                rep.problem(f"{rk_rel} {row.get('analog_id')}: missing fields {rmissing}")
                continue
            if row["card"] is None:
                rep.note(f"{rk_rel} {row['analog_id']}: no card (analog terrain not exported)")
                continue
            check_card(data, row["card"], {"target_id": tid}, t.get("body"), rep)

    for name in ("bodies.json", "missions.json", "validation.json", "viz.json"):
        doc = _load(data / name, rep, name)
        if doc is not None:
            rep.referenced.add(name)
            if name == "validation.json":
                absent = [b for b in VALIDATION_BLOCKS if b not in doc]
                if absent:
                    rep.problem(f"validation.json: missing blocks {absent}")
            if name == "viz.json" and not isinstance(doc.get("vertical_exaggeration"), (int, float)):
                rep.problem("viz.json: vertical_exaggeration missing")

    check_root_files(data, rep)
    check_coverage(data, rep)
    check_atlas(data, rep)
    check_discoveries(data, rep)
    check_query(data, rep)
    check_light(data, rep)
    check_rehearsal(data, rep)
    check_arctic(data, rep)

    for path in sorted(data.rglob("*")):
        if not path.is_file():
            continue
        rel = _rel(data, path)
        if rel.split("/", 1)[0] == "sample":
            continue
        if rel not in rep.referenced:
            size = path.stat().st_size
            rep.notes.append(f"orphan (not referenced): {rel} ({size} bytes)")
    return rep


def check_root_files(data: Path, rep: Report) -> None:
    """Root JSON files the interface reads (ROOT_FILE_KEYS): when present, each parses and has its main keys; an absent
    one is a note (the interface then shows that it is not there), as for light.json and arctic.json."""
    for name, keys in ROOT_FILE_KEYS.items():
        if not (data / name).exists():
            rep.note(f"{name} not in site/data (the interface loads it)")
            continue
        doc = _load(data / name, rep, name)
        if doc is None:
            continue
        rep.referenced.add(name)
        if not isinstance(doc, dict):
            rep.problem(f"{name}: not an object")
            continue
        absent = [k for k in keys if k not in doc]
        if absent:
            rep.problem(f"{name}: missing keys {absent}")


def check_coverage(data: Path, rep: Report) -> None:
    """site/data/coverage/<body>.json (STANDARDS 10.13): 360 x 180 row-major ints in {0,1,2}, counts consistent."""
    for body in COVERAGE_BODIES:
        rel = f"coverage/{body}.json"
        doc = _load(data / rel, rep, rel)
        if doc is None:
            continue
        rep.referenced.add(rel)
        if doc.get("body") != body or doc.get("res_deg") != 1 or doc.get("width") != 360 or doc.get("height") != 180:
            rep.problem(f"{rel}: body/res_deg/width/height not 1 degree, 360 x 180")
        if doc.get("origin") != [-180, 90] or doc.get("classes") != COVERAGE_CLASSES:
            rep.problem(f"{rel}: origin or classes differ from STANDARDS 10.13")
        grid = doc.get("grid") or []
        if len(grid) != COVERAGE_CELLS or any(v not in (0, 1, 2) for v in grid):
            rep.problem(f"{rel}: grid is not {COVERAGE_CELLS} values in 0/1/2")
        else:
            counted = {k: sum(1 for v in grid if v == int(k)) for k in COVERAGE_CLASSES}
            if doc.get("counts") != counted:
                rep.problem(f"{rel}: counts do not match the grid")
        if body == "mars" and not isinstance(doc.get("notes"), dict):
            rep.problem(f"{rel}: notes (acceptance rate and class-1 meaning) missing")


def check_atlas(data: Path, rep: Report) -> None:
    """site/data/atlas/mars_cells.json: a list of cells in the STANDARDS 10.13 format, three twins each."""
    rel = "atlas/mars_cells.json"
    if not (data / rel).exists():
        rep.note("atlas/mars_cells.json not written yet")
        return
    cells = _load(data / rel, rep, rel)
    if not isinstance(cells, list):
        rep.problem(f"{rel}: not a list of cells")
        return
    rep.referenced.add(rel)
    for c in cells:
        missing = [k for k in ATLAS_KEYS if k not in c]
        if missing:
            rep.problem(f"{rel} {c.get('id')}: missing fields {missing}")
            continue
        if len(c["twins"]) != 3:
            rep.problem(f"{rel} {c['id']}: {len(c['twins'])} twins, expected 3")
        for tw in c["twins"]:
            tmiss = [k for k in TWIN_KEYS if k not in tw]
            if tmiss:
                rep.problem(f"{rel} {c['id']}: twin missing {tmiss}")
        if not {"landing", "driving"} <= set(c["mission_pct"]):
            rep.problem(f"{rel} {c['id']}: mission_pct lacks landing or driving")


def check_discoveries(data: Path, rep: Report) -> None:
    """site/data/discoveries.json: counts add up to the windows listed."""
    rel = "discoveries.json"
    if not (data / rel).exists():
        rep.note("discoveries.json not written yet")
        return
    doc = _load(data / rel, rep, rel)
    if doc is None:
        return
    rep.referenced.add(rel)
    c = doc.get("counts", {})
    if c.get("unique_windows") != len(doc.get("windows", [])):
        rep.problem(f"{rel}: unique_windows does not equal the windows listed")
    if c.get("unique_windows") != c.get("new", 0) + c.get("known_region", 0) + c.get("unclassified", 0):
        rep.problem(f"{rel}: new + known_region + unclassified does not add to unique_windows")


def check_light(data: Path, rep: Report) -> None:
    """site/data/light.json (P-S): parses and has the targets and earth_windows blocks; a note while it is absent."""
    rel = "light.json"
    if not (data / rel).exists():
        rep.note("light.json not written yet (light stage, STANDARDS 10.15 P-S)")
        return
    doc = _load(data / rel, rep, rel)
    if doc is None:
        return
    rep.referenced.add(rel)
    absent = [b for b in LIGHT_BLOCKS if b not in doc]
    if absent:
        rep.problem(f"{rel}: missing blocks {absent}")


def check_arctic(data: Path, rep: Report) -> None:
    """site/data/arctic.json (experiment, STANDARDS 10.14): keys, and the id lists, windows and counts agree."""
    rel = "arctic.json"
    if not (data / rel).exists():
        rep.note("arctic.json not written yet (Arctic probe, tools/export_arctic.py)")
        return
    doc = _load(data / rel, rep, rel)
    if doc is None:
        return
    rep.referenced.add(rel)
    missing = [k for k in ARCTIC_KEYS if k not in doc]
    if missing:
        rep.problem(f"{rel}: missing keys {missing}")
        return
    counts = doc["counts"] if isinstance(doc["counts"], dict) else {}
    absent = [k for k in ARCTIC_COUNT_KEYS if k not in counts]
    if absent:
        rep.problem(f"{rel}: counts lack {absent}")
        return
    cells, moon, wins = doc["mars_closed_cell_ids"], doc["moon_closed_target_ids"], doc["windows"]
    if len(set(cells)) != len(cells) or not all(str(c).startswith("mars_") for c in cells):
        rep.problem(f"{rel}: mars_closed_cell_ids are not unique mars_ ids")
    if len(cells) != counts["mars_gap_cells_closed"]:
        rep.problem(f"{rel}: {len(cells)} closed cells listed, counts say {counts['mars_gap_cells_closed']}")
    if counts["mars_gap_cells_closed"] > counts["mars_gap_cells"]:
        rep.problem(f"{rel}: more closed cells than gap cells")
    if len(moon) != counts["moon_gap_targets_closed"] or counts["moon_gap_targets_closed"] > counts["moon_gap_targets"]:
        rep.problem(f"{rel}: moon_closed_target_ids ({len(moon)}) do not match counts.moon_gap_targets_closed")
    bad = [w.get("id") for w in wins if not isinstance(w, dict) or not all(k in w for k in ARCTIC_WINDOW_KEYS)]
    if bad:
        rep.problem(f"{rel}: windows lack {ARCTIC_WINDOW_KEYS}: {bad[:5]}")
    ids = [w.get("id") for w in wins if isinstance(w, dict)]
    if len(set(ids)) != len(ids):
        rep.problem(f"{rel}: duplicate window ids")
    if len(wins) != counts["windows_closing"]:
        rep.problem(f"{rel}: {len(wins)} windows listed, counts say {counts['windows_closing']}")
    if not isinstance(doc["note"], str) or "lower bound" not in doc["note"]:
        rep.problem(f"{rel}: note must state that the count is a lower bound")


def _rehearsal_problems(rel: str, doc: Any, card: dict[str, Any] | None, rep: Report) -> None:
    """One rehearsal document against its card (STANDARDS 10.15): keys, the eight lines in order, statuses, reasons."""
    if not isinstance(doc, dict):
        rep.problem(f"{rel}: not an object")
        return
    missing = [k for k in REHEARSAL_KEYS if k not in doc]
    if missing:
        rep.problem(f"{rel}: missing fields {missing}")
        return
    if card is not None and (doc["target_id"] != card.get("target_id") or doc["analog_id"] != card.get("analog_id")):
        rep.problem(f"{rel}: target_id/analog_id differ from the card")
    ids = [ln.get("id") for ln in doc["lines"]]
    if ids != list(REHEARSAL_LINE_IDS):
        rep.problem(f"{rel}: lines are {ids}, expected {list(REHEARSAL_LINE_IDS)}")
    for ln in doc["lines"]:
        lmiss = [k for k in REHEARSAL_LINE_KEYS if k not in ln]
        if lmiss:
            rep.problem(f"{rel} {ln.get('id')}: missing fields {lmiss}")
            continue
        if ln["status"] not in REHEARSAL_STATUSES:
            rep.problem(f"{rel} {ln['id']}: status {ln['status']!r} not in yes|partial|no|null")
        if ln["status"] is None and not ln["reason"]:
            rep.problem(f"{rel} {ln['id']}: status null without a reason")
        if ln["group"] == "cannot" and ln["status"] not in ("no", None):
            rep.problem(f"{rel} {ln['id']}: a cannot line must be status no")
        if ln["evidence"] not in REHEARSAL_EVIDENCE:
            rep.problem(f"{rel} {ln['id']}: evidence {ln['evidence']!r} is not a known tag")


def check_rehearsal(data: Path, rep: Report) -> None:
    """site/data/rehearsal/<card name>.json for every pair card in site/data/cards (STANDARDS 10.15, P-P)."""
    rdir = data / "rehearsal"
    cdir = data / "cards"
    cards = sorted(cdir.glob("*.json")) if cdir.is_dir() else []
    if not rdir.is_dir():
        if cards:
            rep.note(f"rehearsal/ not written yet ({len(cards)} cards without a rehearsal plan)")
        return
    card_names = {c.name for c in cards}
    for cpath in cards:
        rel = f"rehearsal/{cpath.name}"
        if not (rdir / cpath.name).exists():
            rep.problem(f"{rel}: missing (the card {cpath.name} has no rehearsal plan)")
            continue
        card = _load(cpath, rep, f"cards/{cpath.name}")
        doc = _load(rdir / cpath.name, rep, rel)
        rep.referenced.add(rel)
        if doc is not None:
            _rehearsal_problems(rel, doc, card if isinstance(card, dict) else None, rep)
    for path in sorted(rdir.glob("*.json")):
        if path.name not in card_names:
            rep.problem(f"rehearsal/{path.name}: orphan (no card with this name)")


def _expected_bytes(name: str, rows: int, n_present: int | None) -> int | None:
    """Byte size fixed by the query encoding (STANDARDS 10.14, P-Q): .f32 and .codes.u16 hold one value per row, the
    .order.u32 index holds one entry per non-missing row. None for a file kind this checker does not know."""
    if name.endswith(".f32"):
        return rows * 4
    if name.endswith(".codes.u16"):
        return rows * 2
    if name.endswith(".order.u32"):
        return (n_present if n_present is not None else rows) * 4
    return None


def check_query(data: Path, rep: Report) -> None:
    """site/data/query/<table>/ (P-Q): every file a manifest names must exist with the size its encoding implies, every
    dictionary must hold dict_size entries, and every file in a table folder must be named by its manifest (else it is an
    orphan). Top-level query JSON files (e.g. questions.json) are referenced when they parse."""
    qroot = data / "query"
    if not qroot.is_dir():
        return
    for jpath in sorted(qroot.glob("*.json")):
        rel = _rel(data, jpath)
        if _load(jpath, rep, rel) is not None:
            rep.referenced.add(rel)
    for tdir in sorted(d for d in qroot.iterdir() if d.is_dir()):
        mpath = tdir / "manifest.json"
        mrel = _rel(data, mpath)
        manifest = _load(mpath, rep, mrel)
        if manifest is None:
            continue
        rep.referenced.add(mrel)
        rows = int(manifest.get("rows", -1))
        if rows < 0:
            rep.problem(f"{mrel}: rows missing")
            continue
        for col in manifest.get("columns", []):
            n_present = col.get("n_present")
            for fname in col.get("files", []):
                fpath = tdir / fname
                frel = _rel(data, fpath)
                if not fpath.exists():
                    rep.problem(f"{frel}: named by {mrel} but missing")
                    continue
                rep.referenced.add(frel)
                want = _expected_bytes(fname, rows, n_present)
                if want is None:
                    if fname.endswith(".dict.json"):
                        d = _load(fpath, rep, frel)
                        if isinstance(d, list) and col.get("dict_size") is not None and len(d) != int(col["dict_size"]):
                            rep.problem(f"{frel}: {len(d)} dictionary entries, manifest says {col['dict_size']}")
                    else:
                        rep.problem(f"{frel}: unknown query file kind")
                    continue
                if fpath.stat().st_size != want:
                    rep.problem(f"{frel}: {fpath.stat().st_size} bytes, expected {want} ({rows} rows)")


def _print(rep: Report, data: Path, strict: bool) -> int:
    print(f"site/data: {data}")
    print(f"checked: {rep.counts['targets']} targets, {rep.counts['rankings']} rankings, "
          f"{rep.counts['cards']} cards, {rep.counts['terrains']} terrain folders")
    for p in rep.problems:
        print(f"PROBLEM {p}")
    orphans = [n for n in rep.notes if n.startswith("orphan")]
    for n in rep.notes:
        if not n.startswith("orphan"):
            print(f"NOTE {n}")
    print(f"orphans listed (not deleted): {len(orphans)}, {sum(int(n.rsplit('(', 1)[1].split(' ')[0]) for n in orphans)} bytes")
    for n in orphans:
        print(f"  {n}")
    bad = bool(rep.problems) or (strict and bool(orphans))
    print("RESULT: " + ("FAIL" if bad else "OK"))
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Read-only check of site/data against STANDARDS 10.5/10.6/10.9/10.12.")
    ap.add_argument("--root", default=str(ROOT), help="project root (default: this repository)")
    ap.add_argument("--strict", action="store_true", help="count orphan files as problems")
    args = ap.parse_args(argv)
    data = Path(args.root) / "site" / "data"
    if not data.is_dir():
        print(f"site/data not found: {data}")
        return 2
    rep = check_site(data, strict=args.strict)
    return _print(rep, data, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
