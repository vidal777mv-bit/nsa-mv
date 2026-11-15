"""Pool ice check: WorldCover class-70 share in the 4 km disk of each NASADEM pool window.

Same method as docs/verification/arctic_ice/arctic_ice_classes.py (copied, not imported):
- tile read: 300 x 300 per 3x3 deg ESA WorldCover 2021 tile, nearest, GDAL overview, class codes kept;
- disk: 0.01 deg pixel centres within 4 km of the window centre;
- shares over ALL disk pixels (pixels without a WorldCover tile count as absent, not as class 70);
- classes: ICE share70 >= 0.5, MIXED 0.2 to 0.5, ROCK < 0.2; Wilson 95% on each class share.

Read-only w.r.t. the project. Writes the final outputs to docs/verification/pool_ice (full mode) and the
sample / tile cache to the scratchpad.

Usage:
  python pool_ice_classes.py sample   -> 100 windows, 25 per latitude band (seed 20261114), scratchpad only
  python pool_ice_classes.py full     -> all 2000 pool windows + outputs in docs/verification/pool_ice
"""
from __future__ import annotations

import datetime as dt
import json
import math
import random
import re
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path("C:/SpaceApps2026_Hackathon")
POOL = ROOT / "data/raw/earth/pool"
INDEX = POOL / "index.json"
ITEMS = POOL / "_worldcover_coarse/items.json"
DISC = ROOT / "site/data/discoveries.json"
RANKING = ROOT / "data/derived/ranking"
OUT = ROOT / "docs/verification/pool_ice"
SCR = Path(__file__).resolve().parent / "_scratch"
TILES = SCR / "tiles"

SEED = 20261114
EARTH_R_KM = 6371008.8 / 1000.0
RADIUS_KM = 4.0
N = 300
PIX = 3.0 / N
PER_BAND = 25
BANDS = ["<0", "0-30", "30-45", "45-60"]
MAX_TILE_ERRORS = 2  # second error stops the run


def band_of(lat: float) -> str:
    if lat < 0:
        return "<0"
    if lat < 30:
        return "0-30"
    if lat < 45:
        return "30-45"
    return "45-60"


def classify(s70: float) -> str:
    if s70 >= 0.5:
        return "ICE"
    if s70 >= 0.2:
        return "MIXED"
    return "ROCK"


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def haversine_np(lat1, lon1, lat2, lon2):
    p1 = np.radians(np.asarray(lat1, dtype=float))
    p2 = np.radians(np.asarray(lat2, dtype=float))
    dp = p2 - p1
    dl = np.radians(np.asarray(lon2, dtype=float) - np.asarray(lon1, dtype=float))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2.0 * EARTH_R_KM * np.arcsin(np.minimum(1.0, np.sqrt(a)))


def sw_of(tile_id: str) -> tuple[int, int]:
    m = re.search(r"_([NS])(\d{2})([EW])(\d{3})$", tile_id)
    if not m:
        raise ValueError(tile_id)
    return (int(m.group(2)) * (1 if m.group(1) == "N" else -1),
            int(m.group(4)) * (1 if m.group(3) == "E" else -1))


def disk_cells(lat: float, lon: float) -> list[tuple[int, int, int, int]]:
    """Pixel centres (0.01 deg global grid) within 4 km of (lat, lon) as (sw_lat, sw_lon, row, col)."""
    dlat = RADIUS_KM / 111.32 + 0.02
    dlon = RADIUS_KM / (111.32 * max(math.cos(math.radians(lat)), 1e-6)) + 0.02
    i0, i1 = math.floor((lat - dlat) / PIX) - 1, math.floor((lat + dlat) / PIX) + 1
    j0, j1 = math.floor((lon - dlon) / PIX) - 1, math.floor((lon + dlon) / PIX) + 1
    II, JJ = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1), indexing="ij")
    clat = (II + 0.5) * PIX
    clon = (JJ + 0.5) * PIX
    inside = haversine_np(lat, lon, clat, clon) <= RADIUS_KM
    clat, clon = clat[inside], clon[inside]
    out = []
    for la, lo in zip(clat, clon):
        sw_lat = int(math.floor(la / 3.0)) * 3
        sw_lon = int(math.floor(lo / 3.0)) * 3
        row = int(round((sw_lat + 3.0 - la) / PIX - 0.5))
        col = int(round((lo - sw_lon) / PIX - 0.5))
        out.append((sw_lat, sw_lon, row, col))
    return out


def load_items() -> dict[tuple[int, int], dict]:
    items = json.loads(ITEMS.read_text(encoding="utf-8"))
    return {sw_of(it["id"]): it for it in items}


def read_tile_classes(item: dict) -> np.ndarray:
    """Same read as arctic_ice_classes.read_tile_classes (nearest, overview, class codes)."""
    import planetary_computer
    import rasterio
    from rasterio.enums import Resampling

    signed = planetary_computer.sign(item["href"])
    with rasterio.open(f"/vsicurl/{signed}") as ds:
        arr = ds.read(1, out_shape=(N, N), resampling=Resampling.nearest)
    return arr.astype(np.uint8)


def get_tiles(keys: set[tuple[int, int]], items: dict) -> tuple[dict, list]:
    TILES.mkdir(parents=True, exist_ok=True)
    todo = [k for k in keys if k in items]  # no WorldCover tile = ocean/absent, not an error
    arrays: dict[tuple[int, int], np.ndarray] = {}
    errors: list[str] = []
    lock = threading.Lock()
    abort = threading.Event()

    def one(k):
        if abort.is_set():
            return k, None, "aborted"
        it = items[k]
        p = TILES / f"{it['id']}.npy"
        if p.exists():
            return k, np.load(p), None
        try:
            a = read_tile_classes(it)
            np.save(p, a)
            return k, a, None
        except Exception as e:  # noqa: BLE001 - recorded, not hidden
            msg = f"{it['id']}: {type(e).__name__}: {str(e)[:200]}"
            with lock:
                errors.append(msg)
                if len(errors) >= MAX_TILE_ERRORS:
                    abort.set()
            return k, None, msg

    with ThreadPoolExecutor(max_workers=12) as ex:
        for k, a, err in ex.map(one, todo):
            if a is not None:
                arrays[k] = a
    return arrays, errors


def share_row(cells, classes):
    counts = {60: 0, 70: 0, 100: 0}
    other = 0
    absent = 0
    for sw_lat, sw_lon, row, col in cells:
        arr = classes.get((sw_lat, sw_lon))
        if arr is None:
            absent += 1
            continue
        v = int(arr[row, col])
        if v in counts:
            counts[v] += 1
        else:
            other += 1
    n = len(cells)
    return {"n_disk_px": n, "absent_px": absent,
            "s60": counts[60] / n, "s70": counts[70] / n, "s100": counts[100] / n,
            "other_share": other / n}


def twins_map() -> dict[str, list[dict]]:
    """place 'pool__pool_NNNNN' -> twin entries from discoveries (top-3 of a Moon/Mars target, or Mars atlas cell)."""
    d = json.loads(DISC.read_text(encoding="utf-8"))
    out: dict[str, list[dict]] = defaultdict(list)
    for x in d["windows"]:
        aid, pid = x["analog_id"], x["place_id"]
        if aid == pid:
            out[pid].append({"kind": "mars_atlas_cell", "target": None, "analog_id": aid,
                             "novelty": x["novelty"]})
        else:
            target = aid.split("__pool__")[0]
            out[pid].append({"kind": "target_top3", "target": target, "analog_id": aid,
                             "novelty": x["novelty"]})
    return out


def effective_ranking_files() -> list[Path]:
    """Same rule as pipelines/_common.ranking_file: data/derived/refine/<tid>.json when it exists, else ranking/."""
    out = []
    for p in sorted(RANKING.glob("*.json")):
        ref = ROOT / "data/derived/refine" / p.name
        out.append(ref if ref.exists() else p)
    return out


def top3_by_target() -> dict[str, set[str]]:
    """target -> set of pool place ids at rank <= 3 in the effective ranking (the rule discoveries.py uses)."""
    out = {}
    for p in effective_ranking_files():
        r = json.loads(p.read_text(encoding="utf-8"))
        # refine files carry analog_id '<target>__pool__pool_N' and pool_id 'pool__pool_N'; search files carry 'pool__pool_N'
        out[r["target_id"]] = {x.get("pool_id", x["analog_id"]) for x in r["ranking"] if x["rank"] <= 3}
    return out


def twin_check(top3: dict[str, set[str]]) -> dict:
    """Cross-check: discoveries target twins vs effective ranking top-3 for each target."""
    d = json.loads(DISC.read_text(encoding="utf-8"))
    disc_targets: dict[str, set[str]] = defaultdict(set)
    for x in d["windows"]:
        if x["analog_id"] != x["place_id"]:
            target = x["analog_id"].split("__pool__")[0]
            disc_targets[target].add(x["place_id"])
    report = {}
    for tid in sorted(top3):
        got = disc_targets.get(tid, set())
        report[tid] = {"ranking_top3": sorted(top3[tid]), "discoveries_top3": sorted(got),
                       "match": top3[tid] == got,
                       "ranking_file": "refine" if (ROOT / "data/derived/refine" / f"{tid}.json").exists() else "ranking"}
    return report


def load_pool_index() -> list[dict]:
    return json.loads(INDEX.read_text(encoding="utf-8"))


def sample_ids(index: list[dict]) -> list[dict]:
    rng = random.Random(SEED)
    chosen = []
    for b in BANDS:
        pool_b = [w for w in index if band_of(w["lat"]) == b]
        chosen += rng.sample(pool_b, PER_BAND)
    return chosen


def measure(windows: list[dict]) -> tuple[list[dict], list[str]]:
    items = load_items()
    cells = {w["id"]: disk_cells(w["lat"], w["lon"]) for w in windows}
    keys = {(sw_lat, sw_lon) for cl in cells.values() for sw_lat, sw_lon, _, _ in cl}
    print(f"windows={len(windows)} tile_keys={len(keys)} tiles_in_items={sum(1 for k in keys if k in items)}",
          flush=True)
    classes, errors = get_tiles(keys, items)
    print(f"tiles loaded={len(classes)} errors={len(errors)}", flush=True)
    if len(errors) >= MAX_TILE_ERRORS:
        for e in errors:
            print("ERROR", e, flush=True)
        raise SystemExit(2)
    rows = []
    for w in windows:
        r = share_row(cells[w["id"]], classes)
        r.update({"id": w["id"], "lat": w["lat"], "lon": w["lon"], "band": band_of(w["lat"]),
                  "index_worldcover_share": w.get("worldcover_share"),
                  "class": classify(r["s70"])})
        rows.append(r)
    return rows, errors


def summarize(rows: list[dict]) -> dict:
    out = {}
    for b in BANDS + ["ALL"]:
        rs = rows if b == "ALL" else [r for r in rows if r["band"] == b]
        n = len(rs)
        c = {k: sum(1 for r in rs if r["class"] == k) for k in ("ICE", "MIXED", "ROCK")}
        out[b] = {"n": n}
        for k in ("ICE", "MIXED", "ROCK"):
            lo, hi = wilson(c[k], n)
            out[b][k] = {"k": c[k], "rate": (c[k] / n if n else 0.0), "wilson95": [round(lo, 4), round(hi, 4)]}
        out[b]["ICE_plus_MIXED"] = c["ICE"] + c["MIXED"]
    return out


def fmt_row(b: str, s: dict) -> str:
    cells = []
    for k in ("ICE", "MIXED", "ROCK"):
        v = s[k]
        cells.append(f"{v['k']} ({100 * v['rate']:.0f}%, {100 * v['wilson95'][0]:.0f}-{100 * v['wilson95'][1]:.0f})")
    return f"| {b} | {s['n']} | " + " | ".join(cells) + " |"


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "sample"
    SCR.mkdir(parents=True, exist_ok=True)
    index = load_pool_index()
    assert len(index) == 2000, len(index)

    if mode == "sample":
        windows = sample_ids(index)
        rows, errors = measure(windows)
        summ = summarize(rows)
        (SCR / "sample.json").write_text(json.dumps({"seed": SEED, "per_band": PER_BAND, "rows": rows,
                                                     "summary": summ, "tile_errors": errors}, indent=1),
                                         encoding="utf-8")
        print("| banda | n | ICE | MIXED | ROCK |")
        print("|---|---|---|---|---|")
        for b in BANDS + ["ALL"]:
            print(fmt_row(b, summ[b]))
        go_full = any(summ[b]["ICE_plus_MIXED"] > 0 for b in BANDS)
        print("DECISION:", "FULL 2000 (some band has ICE+MIXED > 0)" if go_full
              else "NO FULL RUN (all bands ROCK)", flush=True)
        return 0

    if mode == "full":
        windows = index
        rows, errors = measure(windows)
        summ = summarize(rows)
        twins = twins_map()
        top3 = top3_by_target()
        twin_rep = twin_check(top3)
        for r in rows:
            r["twins"] = twins.get("pool__" + r["id"], [])
            r["top3_of_targets"] = sorted(t for t, s in top3.items() if "pool__" + r["id"] in s)
        non_rock = [r for r in rows if r["class"] != "ROCK"]
        rows_out = sorted(rows, key=lambda r: r["id"])
        payload = {
            "created": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rule": "ICE share70 >= 0.5; MIXED 0.2 to 0.5; ROCK < 0.2 (share70 = WorldCover class 70 / all 4 km disk px)",
            "method": "same as docs/verification/arctic_ice/arctic_ice_classes.py (copied): WorldCover 2021 300x300 nearest per 3x3 deg tile, disk 4 km",
            "source": "data/raw/earth/pool/index.json (2000 windows)",
            "tile_errors": errors,
            "summary": summ,
            "non_rock_ids": [r["id"] for r in non_rock],
            "twin_check_ranking_vs_discoveries": twin_rep,
            "windows": rows_out,
        }
        (OUT / "pool_ice.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
        write_md(payload, non_rock)
        print("wrote", OUT / "pool_ice.json", "and pool_ice.md", flush=True)
        return 0

    print("unknown mode", mode)
    return 1


def write_md(p: dict, non_rock: list[dict]) -> None:
    s = p["summary"]
    lines = ["# Pool ice check: are the 2000 pool windows rock or ice?", "",
             "Script: `pool_ice_classes.py` (full). Same method as the Arctic check (WorldCover 2021 class 70, 4 km disk, "
             "full-disk denominator). Rule: ROCK share70 < 0.2; MIXED 0.2 to 0.5; ICE >= 0.5. Wilson 95% per class.", "",
             "## Rates by latitude band (ICE | MIXED | ROCK, count (rate, Wilson 95%))", "",
             "| banda | n | ICE | MIXED | ROCK |", "|---|---|---|---|---|"]
    for b in BANDS + ["ALL"]:
        lines.append(fmt_row(b, s[b]))
    lines += ["", f"Tile errors: {len(p['tile_errors'])}.", "",
              "## Non-ROCK windows (ICE or MIXED)", "",
              "| id | lat | lon | band | s70 | class | twins (discoveries) | top-3 of target (effective ranking) |",
              "|---|---|---|---|---|---|---|---|"]
    for r in sorted(non_rock, key=lambda r: -r["s70"]):
        tw = "; ".join(f"{t['target'] or 'Mars atlas cell'}" for t in r["twins"]) or "none"
        top = ", ".join(r["top3_of_targets"]) or "none"
        lines.append(f"| {r['id']} | {r['lat']} | {r['lon']} | {r['band']} | {r['s70']:.4f} | {r['class']} | {tw} | {top} |")
    lines += ["", "## Twin check: ranking top-3 vs discoveries (per target)", "",
              "| target | match |", "|---|---|"]
    for tid, v in p["twin_check_ranking_vs_discoveries"].items():
        lines.append(f"| {tid} | {'yes' if v['match'] else 'NO'} |")
    (OUT / "pool_ice.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
