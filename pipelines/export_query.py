"""P-Q query export (STANDARDS 10.14): columnar binary tables for the browser, under site/data/query/<table>/.

Reads only data/derived/neighbors/*.parquet (P-N). Tables:
- targets, mars_cells   one row per query (features, relief class, tie threshold, d_nearest, tie_set_size, gap,
                        d_nearest_nasadem and gap_nasadem (NASADEM band only), mission data)
- earth_windows         one row per Earth pool window (all pool windows: NASADEM 2000 and the Arctic windows, column
                        sensor): features, novelty, context, place, nearest town,
                        landing share under the moon and Mars limits (where a persisted mission record exists)
- twins                 one row per (query, rank): query_id, rank, earth_row (row in earth_windows), D, novelty,
                        in_tie_set, nearest_town_km, landing_pct (under the query body's landing limit)

Layout per table (identical for all tables; the browser reads it the same way):
  manifest.json            rows, columns (name, type, unit, fact_property, missing, files), encoding, provenance
  <col>.f32                Float32 little-endian, one value per row, NaN = missing          (type f32 / bool)
  <col>.order.u32          UInt32 row indices of the non-missing rows, sorted ascending by value (stable)  (f32 only)
  <col>.codes.u16          UInt16 codes into <col>.dict.json, 65535 = missing               (type text)
  <col>.dict.json          sorted list of the distinct strings of a text column

A bool column is stored as f32 (1.0 / 0.0, NaN missing). A range query by binary search: searchsorted on the
sorted values (values[order]) gives the row set (see ``range_rows``).

Preset questions (site/data/query/questions.json): each is a filter spec over one table,
  {"table": <name>, "all": [{"col": <column>, "op": eq|ne|lt|le|gt|ge|in, "value": <number | string | list>}, ...]}
combined with AND. A null value never matches. ``evaluate`` runs the spec on the tables as written to disk, and the
row count stored with each question is that count.

Usage:
  .venv/Scripts/python.exe pipelines/export_query.py       (writes site/data/query/, prints the sizes and counts)
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import Paths, make_paths, provenance_block, utc_now  # noqa: E402

SCHEMA = "analog.query/1"
QUESTIONS_SCHEMA = "analog.query.questions/1"
TEXT_MISSING = 65535
MAX_TOTAL_BYTES = 2_000_000
NEIGHBORS = "neighbors"
ARTEMIS = "Artemis III (candidate region)"

# (name, type, unit, fact_property) per table, in column order. type: f32 | bool | text.
TARGET_COLS = [
    ("id", "text", None, "subject_id"),
    ("name", "text", None, "name"),
    ("body", "text", None, "body"),
    ("mission", "text", None, "mission"),
    ("landing_class", "text", None, "landing_class"),
    ("relief_class", "text", None, "relief_class"),
    ("lat", "f32", "deg", "lat"),
    ("lon", "f32", "deg", "lon"),
    ("slope_p95_deg", "f32", "deg", "slope_p95_deg"),
    ("hi", "f32", "ratio", "hi"),
    ("coherence", "f32", "ratio", "coherence"),
    ("hurst", "f32", "ratio", "hurst"),
    ("ridge_pct", "f32", "%", "ridge_pct"),
    ("valley_pct", "f32", "%", "valley_pct"),
    ("threshold", "f32", "sigma units", "tie_threshold"),
    ("d_nearest", "f32", "sigma units", "d_nearest"),
    ("tie_set_size", "f32", "count", "tie_set_size"),
    ("gap", "bool", None, "earth_gap"),
    ("d_nearest_nasadem", "f32", "sigma units", "d_nearest_nasadem"),
    ("gap_nasadem", "bool", None, "earth_gap_nasadem"),
]
MARS_COLS = [
    ("id", "text", None, "subject_id"),
    ("body", "text", None, "body"),
    ("relief_class", "text", None, "relief_class"),
    ("lat", "f32", "deg", "lat"),
    ("lon", "f32", "deg", "lon"),
    ("slope_p95_deg", "f32", "deg", "slope_p95_deg"),
    ("hi", "f32", "ratio", "hi"),
    ("coherence", "f32", "ratio", "coherence"),
    ("hurst", "f32", "ratio", "hurst"),
    ("ridge_pct", "f32", "%", "ridge_pct"),
    ("valley_pct", "f32", "%", "valley_pct"),
    ("threshold", "f32", "sigma units", "tie_threshold"),
    ("d_nearest", "f32", "sigma units", "d_nearest"),
    ("tie_set_size", "f32", "count", "tie_set_size"),
    ("gap", "bool", None, "earth_gap"),
    ("d_nearest_nasadem", "f32", "sigma units", "d_nearest_nasadem"),
    ("gap_nasadem", "bool", None, "earth_gap_nasadem"),
    ("landing_pct", "f32", "%", "mission_landing_pct"),
    ("driving_pct", "f32", "%", "mission_driving_pct"),
]
EARTH_COLS = [
    ("id", "text", None, "subject_id"),
    ("lat", "f32", "deg", "lat"),
    ("lon", "f32", "deg", "lon"),
    ("slope_p95_deg", "f32", "deg", "slope_p95_deg"),
    ("hi", "f32", "ratio", "hi"),
    ("coherence", "f32", "ratio", "coherence"),
    ("hurst", "f32", "ratio", "hurst"),
    ("ridge_pct", "f32", "%", "ridge_pct"),
    ("valley_pct", "f32", "%", "valley_pct"),
    ("sensor", "text", None, "sensor"),
    ("tree_member_target", "bool", None, "in_target_tree"),
    ("tree_member_mars", "bool", None, "in_mars_tree"),
    ("near_known_analog", "bool", None, "near_known_analog"),
    ("novelty", "text", None, "novelty"),
    ("known_region_id", "text", None, "known_region_id"),
    ("koppen_code", "f32", "code", "koppen_code"),
    ("koppen_class", "text", None, "koppen_class"),
    ("koppen_label", "text", None, "koppen_label"),
    ("elevation_m", "f32", "m", "elevation_m"),
    ("town_name", "text", None, "nearest_town_name"),
    ("town_country", "text", None, "nearest_town_country"),
    ("nearest_town_km", "f32", "km", "nearest_town_distance_km"),
    ("place_name", "text", None, "place_name"),
    ("place_admin1", "text", None, "place_admin1"),
    ("place_country", "text", None, "place_country"),
    ("context_source", "text", None, "context_source"),
    ("landing_pct_moon", "f32", "%", "mission_landing_pct_moon"),
    ("landing_pct_mars", "f32", "%", "mission_landing_pct_mars"),
]
TWIN_COLS = [
    ("query_id", "text", None, "subject_id"),
    ("query_kind", "text", None, "query_kind"),
    ("rank", "f32", "rank", "twin_rank"),
    ("earth_row", "f32", "row", "earth_row"),
    ("D", "f32", "sigma units", "D"),
    ("novelty", "text", None, "novelty"),
    ("in_tie_set", "bool", None, "in_tie_set"),
    ("nearest_town_km", "f32", "km", "nearest_town_distance_km"),
    ("landing_pct", "f32", "%", "mission_landing_pct"),
]

# Preset questions (plain-English titles; the filter is the exact JSON the page applies).
QUESTIONS = [
    {"id": "mars_no_twin", "title": "Mars terrain with no Earth twin",
     "note": "Mars cells whose nearest Earth window is farther than the tie threshold (the Earth gap).",
     "filter": {"table": "mars_cells", "all": [{"col": "gap", "op": "eq", "value": 1}]}},
    {"id": "new_cold_desert_twins", "title": "New Earth twins in cold deserts (Köppen BWk)",
     "note": "Earth windows not inside a known analog region, Köppen code 5 (BWk, arid cold). BSk (cold steppe) not included.",
     "filter": {"table": "earth_windows", "all": [{"col": "novelty", "op": "eq", "value": "new"},
                                                   {"col": "koppen_code", "op": "in", "value": [5]}]}},
    {"id": "jezero_rehearsal_50km", "title": "Jezero rehearsal sites within 50 km of a town",
     "note": "Top-10 Earth twins of Jezero whose nearest town (Natural Earth populated places) is within 50 km.",
     "filter": {"table": "twins", "all": [{"col": "query_id", "op": "eq", "value": "jezero"},
                                           {"col": "nearest_town_km", "op": "le", "value": 50}]}},
    {"id": "landable_like_twins", "title": "Earth twins at least 90% under the target's landing limit",
     "note": "Top-10 Earth twins of the targets whose landing share under their own body's limit is >= 90%. Only the "
             "windows with a persisted mission record have a value; the rest never match.",
     "filter": {"table": "twins", "all": [{"col": "query_kind", "op": "eq", "value": "target"},
                                           {"col": "landing_pct", "op": "ge", "value": 90}]}},
    {"id": "artemis_no_twin", "title": "Artemis III candidate regions with no Earth twin",
     "note": "Targets whose mission is the Artemis III candidate region, with an Earth gap.",
     "filter": {"table": "targets", "all": [{"col": "mission", "op": "eq", "value": ARTEMIS},
                                              {"col": "gap", "op": "eq", "value": 1}]}},
]


def _to_f32(values: list[Any]) -> np.ndarray:
    """Float32 array; None becomes NaN."""
    return np.array([np.nan if v is None else float(v) for v in values], dtype="<f4")


def _bool_f32(values: list[Any]) -> np.ndarray:
    """Bool as f32: 1.0 / 0.0, NaN for None."""
    return np.array([np.nan if v is None else (1.0 if v else 0.0) for v in values], dtype="<f4")


def write_numeric(out: Path, name: str, values: np.ndarray, order: bool) -> dict[str, Any]:
    """<name>.f32 and optionally <name>.order.u32 (non-missing rows sorted by value, stable)."""
    vals = np.asarray(values, dtype="<f4")
    vals.tofile(out / f"{name}.f32")
    files = [f"{name}.f32"]
    present = np.flatnonzero(~np.isnan(vals))
    if order:
        ordr = present[np.argsort(vals[present], kind="stable")].astype("<u4")
        ordr.tofile(out / f"{name}.order.u32")
        files.append(f"{name}.order.u32")
    return {"files": files, "n_present": int(present.size)}


def write_text(out: Path, name: str, values: list[Any]) -> dict[str, Any]:
    """<name>.codes.u16 and <name>.dict.json (sorted distinct strings). 65535 = missing."""
    uniq = sorted({str(v) for v in values if v is not None})
    if len(uniq) >= TEXT_MISSING:
        raise ValueError(f"text column {name} has too many distinct values ({len(uniq)})")
    pos = {v: i for i, v in enumerate(uniq)}
    codes = np.array([TEXT_MISSING if v is None else pos[str(v)] for v in values], dtype="<u2")
    codes.tofile(out / f"{name}.codes.u16")
    (out / f"{name}.dict.json").write_text(json.dumps(uniq, ensure_ascii=False), encoding="utf-8")
    return {"files": [f"{name}.codes.u16", f"{name}.dict.json"],
            "n_present": int(np.count_nonzero(codes != TEXT_MISSING)), "dict_size": len(uniq)}


def write_table(root: Path, table: str, cols: list[tuple[str, str, str | None, str]],
                data: dict[str, list[Any]], n_rows: int, sources: list[str], prov: dict[str, Any]) -> dict[str, Any]:
    """Write one table folder and its manifest. data maps column name -> python list of length n_rows."""
    out = root / table
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    columns = []
    for name, ctype, unit, prop in cols:
        vals = data[name]
        if len(vals) != n_rows:
            raise ValueError(f"{table}.{name}: {len(vals)} values for {n_rows} rows")
        if ctype == "f32":
            info = write_numeric(out, name, _to_f32(vals), order=True)
            entry = {"name": name, "type": "f32", "unit": unit, "fact_property": prop, "missing": "NaN",
                     "order": f"{name}.order.u32", "n_present": info["n_present"], "files": info["files"]}
        elif ctype == "bool":
            info = write_numeric(out, name, _bool_f32(vals), order=False)
            entry = {"name": name, "type": "bool", "unit": None, "fact_property": prop, "missing": "NaN",
                     "order": None, "n_present": info["n_present"], "files": info["files"]}
        elif ctype == "text":
            info = write_text(out, name, vals)
            entry = {"name": name, "type": "text", "unit": None, "fact_property": prop, "missing": 65535,
                     "order": None, "n_present": info["n_present"], "dict_size": info["dict_size"],
                     "files": info["files"]}
        else:
            raise ValueError(f"unknown column type {ctype}")
        columns.append(entry)
    manifest = {"schema": SCHEMA, "table": table, "rows": n_rows, "created": utc_now(), "source": sources,
                "encoding": {"f32": "Float32 little-endian; NaN = missing", "bool": "f32 1.0/0.0; NaN = missing",
                             "order": "UInt32 little-endian row indices of non-missing rows, ascending by value",
                             "text": "UInt16 codes into the .dict.json (sorted); 65535 = missing"},
                "columns": columns, "provenance": prov}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                                       encoding="utf-8")
    size = sum(f.stat().st_size for f in out.iterdir() if f.is_file())
    return {"table": table, "rows": n_rows, "columns": len(columns), "bytes": size}


def _load(paths: Paths, name: str) -> dict[str, list[Any]]:
    import pyarrow.parquet as pq
    return pq.read_table(paths.derived / NEIGHBORS / f"{name}.parquet").to_pydict()


def build_tables(paths: Paths) -> dict[str, dict[str, Any]]:
    """Columns of the four tables, from the neighbours outputs only. Returns table -> {data, n}."""
    tg = _load(paths, "targets")
    mc = _load(paths, "mars_cells")
    ew = _load(paths, "earth_windows")
    n_t, n_m, n_e = len(tg["id"]), len(mc["id"]), len(ew["id"])

    twin_q: dict[str, list[Any]] = {k: [] for k, _, _, _ in TWIN_COLS}
    for src, kind in ((tg, "target"), (mc, "mars_cell")):
        for i, qid in enumerate(src["id"]):
            thr = src["threshold"][i]
            body = src["body"][i]
            rows = src["twin_row"][i] or []
            ds = src["twin_D"][i] or []
            for r, (row, d) in enumerate(zip(rows, ds), start=1):
                row = int(row)
                twin_q["query_id"].append(qid)
                twin_q["query_kind"].append(kind)
                twin_q["rank"].append(r)
                twin_q["earth_row"].append(row)
                twin_q["D"].append(float(d))
                twin_q["novelty"].append(ew["novelty"][row])
                twin_q["in_tie_set"].append(None if thr is None else bool(d <= thr))
                twin_q["nearest_town_km"].append(ew["nearest_town_km"][row])
                key = f"landing_pct_{body}" if body in ("moon", "mars") else None
                twin_q["landing_pct"].append(ew[key][row] if key else None)
    n_twins = len(twin_q["query_id"])

    tgt_data = {c: tg[c] for c, _, _, _ in TARGET_COLS}
    mars_data = {c: mc[c] for c, _, _, _ in MARS_COLS}
    earth_data = {c: ew[c] for c, _, _, _ in EARTH_COLS}
    return {
        "targets": {"data": tgt_data, "n": n_t, "cols": TARGET_COLS},
        "mars_cells": {"data": mars_data, "n": n_m, "cols": MARS_COLS},
        "earth_windows": {"data": earth_data, "n": n_e, "cols": EARTH_COLS},
        "twins": {"data": twin_q, "n": n_twins, "cols": TWIN_COLS},
    }


def export(paths: Paths, out_root: Path) -> dict[str, Any]:
    """Write the four tables and questions.json under out_root. Raises when the total exceeds the 2 MB budget."""
    built = build_tables(paths)
    out_root.mkdir(parents=True, exist_ok=True)
    prov = provenance_block(paths, "query", [
        ("neighbors:targets", paths.derived / NEIGHBORS / "targets.parquet"),
        ("neighbors:mars_cells", paths.derived / NEIGHBORS / "mars_cells.parquet"),
        ("neighbors:earth_windows", paths.derived / NEIGHBORS / "earth_windows.parquet"),
        ("neighbors:run", paths.derived / NEIGHBORS / "run.json"),
    ])
    sources = ["data/derived/neighbors/targets.parquet", "data/derived/neighbors/mars_cells.parquet",
               "data/derived/neighbors/earth_windows.parquet"]
    sizes = [write_table(out_root, name, b["cols"], b["data"], b["n"], sources, prov)
             for name, b in built.items()]
    tables = {name: read_table(out_root / name) for name in built}
    questions = []
    for q in QUESTIONS:
        rows = evaluate(tables, q["filter"])
        questions.append({**q, "rows": int(rows.size), "table_rows": tables[q["filter"]["table"]]["manifest"]["rows"]})
    (out_root / "questions.json").write_text(
        json.dumps({"schema": QUESTIONS_SCHEMA, "created": utc_now(), "questions": questions},
                   indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    total = sum(s["bytes"] for s in sizes) + (out_root / "questions.json").stat().st_size
    if total >= MAX_TOTAL_BYTES:
        raise ValueError(f"query export is {total} bytes, over the {MAX_TOTAL_BYTES} budget")
    return {"tables": sizes, "questions": [{"id": q["id"], "rows": q["rows"]} for q in questions],
            "total_bytes": total, "budget_bytes": MAX_TOTAL_BYTES}


# ---- reader and filter evaluation (the same layout the browser reads) -----------------------------------------

def read_table(folder: Path) -> dict[str, Any]:
    """Read a table folder back: {'manifest': ..., 'columns': {name: values}} (f32 arrays, text as list or None)."""
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    cols: dict[str, Any] = {}
    for c in manifest["columns"]:
        name = c["name"]
        if c["type"] in ("f32", "bool"):
            cols[name] = np.fromfile(folder / f"{name}.f32", dtype="<f4")
        elif c["type"] == "text":
            codes = np.fromfile(folder / f"{name}.codes.u16", dtype="<u2")
            d = json.loads((folder / f"{name}.dict.json").read_text(encoding="utf-8"))
            cols[name] = [None if code == TEXT_MISSING else d[int(code)] for code in codes]
    return {"manifest": manifest, "columns": cols, "folder": folder}


def order_of(folder: Path, name: str) -> np.ndarray:
    """The order array of a numeric column (row indices ascending by value)."""
    return np.fromfile(folder / f"{name}.order.u32", dtype="<u4")


def range_rows(folder: Path, name: str, lo: float, hi: float) -> np.ndarray:
    """Rows with lo <= value <= hi, found by binary search on the order array (ascending row indices returned)."""
    vals = np.fromfile(folder / f"{name}.f32", dtype="<f4")
    order = order_of(folder, name)
    sorted_vals = vals[order]
    i = int(np.searchsorted(sorted_vals, np.float32(lo), side="left"))
    j = int(np.searchsorted(sorted_vals, np.float32(hi), side="right"))
    return np.sort(order[i:j].astype(np.int64))


OPS = ("eq", "ne", "lt", "le", "gt", "ge", "in")


def evaluate(tables: dict[str, dict[str, Any]], spec: dict[str, Any]) -> np.ndarray:
    """Rows of spec['table'] matching every condition in spec['all'] (AND). Null never matches.

    Raises ValueError on an unknown table, column or operator, or a value of the wrong kind for the column type.
    """
    name = spec["table"]
    if name not in tables:
        raise ValueError(f"unknown table {name!r}")
    t = tables[name]
    types = {c["name"]: c["type"] for c in t["manifest"]["columns"]}
    n = t["manifest"]["rows"]
    mask = np.ones(n, dtype=bool)
    for cond in spec["all"]:
        col, op, val = cond["col"], cond["op"], cond["value"]
        if col not in types:
            raise ValueError(f"{name}: unknown column {col!r}")
        if op not in OPS:
            raise ValueError(f"unknown op {op!r}")
        arr = t["columns"][col]
        if types[col] == "text":
            if op not in ("eq", "ne", "in"):
                raise ValueError(f"{col}: op {op} is not valid for text")
            present = np.array([v is not None for v in arr], dtype=bool)
            if op == "eq":
                hit = np.array([v == val for v in arr], dtype=bool)
            elif op == "ne":
                hit = np.array([v != val for v in arr], dtype=bool)
            else:
                members = set(val)
                hit = np.array([v in members for v in arr], dtype=bool)
            cur = hit & present
        else:
            if op == "in":
                cur = np.isin(arr, np.asarray(val, dtype="<f4")) & ~np.isnan(arr)
            elif op == "eq":
                cur = arr == np.float32(val)
            elif op == "ne":
                cur = (arr != np.float32(val)) & ~np.isnan(arr)
            elif op == "lt":
                cur = arr < np.float32(val)
            elif op == "le":
                cur = arr <= np.float32(val)
            elif op == "gt":
                cur = arr > np.float32(val)
            else:
                cur = arr >= np.float32(val)
            cur = cur & ~np.isnan(arr)
        mask &= cur
    return np.flatnonzero(mask).astype(np.int64)


def main(argv: list[str] | None = None) -> int:
    paths = make_paths(None, False)
    out_root = paths.root / "site" / "data" / "query"
    res = export(paths, out_root)
    for t in res["tables"]:
        print(f"{t['table']:14s} rows={t['rows']:5d} cols={t['columns']:3d} bytes={t['bytes']}")
    for q in res["questions"]:
        print(f"question {q['id']:24s} rows={q['rows']}")
    print(f"total bytes={res['total_bytes']} (budget {res['budget_bytes']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
