"""Arctic ice check, step 2: classes, ROCK-only closure of Mars gap cells, and the final JSON + MD.

Reads: data/derived/arctic_probe/{measures,results}.json, config/measure.json (sigma), data/derived/neighbors/
mars_cells.parquet (query vectors, read-only), scratchpad classes.json (from arctic_ice_classes.py).
Writes: docs/verification/arctic_ice/arctic_ice.json and arctic_ice.md.

Class rule (as asked): ROCK share70 < 0.2; MIXED 0.2 to < 0.5; ICE >= 0.5. share70 = class 70 pixels / all
pixels within 4 km (full disk, same denominator as the pool rule).

Distance (STANDARDS section 4, weights 1, features slope_p95_deg, hi, hurst; coherence and ridge/valley are
excluded from D in config/measure.json): D = sqrt(mean_k ((a_k - b_k) / sigma_k)^2), K = 3.
Closed = nearest D <= the cell's own tie threshold (results.json / mars_cells 'threshold').
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path("C:/SpaceApps2026_Hackathon")
DER = ROOT / "data/derived/arctic_probe"
OUT = ROOT / "docs/verification/arctic_ice"
SCRP = Path(__file__).resolve().parent / "_scratch"
TILES = SCRP / "tiles"
FEATS = ["slope_p95_deg", "hi", "hurst"]
Z = 1.96
PIX = 3.0 / 300
WIN_PX = 5


def wilson(k: int, n: int) -> list[float]:
    p = k / n
    den = 1 + Z * Z / n
    cen = (p + Z * Z / (2 * n)) / den
    mar = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / den
    return [round(cen - mar, 4), round(cen + mar, 4)]


def klass(s70: float) -> str:
    if s70 < 0.2:
        return "ROCK"
    if s70 < 0.5:
        return "MIXED"
    return "ICE"


def pool_rule_replica(w: dict, tile_id: str) -> float | None:
    """Replica of build_pool_index.grid_candidates share: only a +-5 px box (WIN_PX) around the centre's pixel
    is tested against the 4 km disk, so the disk is cut in longitude at high latitude."""
    p = TILES / f"{tile_id}.npy"
    if not p.exists():
        return None
    bare = np.isin(np.load(p), (60, 70, 100))
    sw_lat = int(math.floor(w["lat"] / 3.0)) * 3
    sw_lon = int(math.floor(w["lon"] / 3.0)) * 3
    maxy, minx = sw_lat + 3.0, float(sw_lon)
    i0 = int(round((maxy - w["lat"]) / PIX - 0.5))
    j0 = int(round((w["lon"] - minx) / PIX - 0.5))
    off = np.arange(-WIN_PX, WIN_PX + 1)
    II = i0 + off[:, None]
    JJ = j0 + off[None, :]
    plat = maxy - (II + 0.5) * PIX
    plon = minx + (JJ + 0.5) * PIX
    la1, lo1 = math.radians(w["lat"]), math.radians(w["lon"])
    la2, lo2 = np.radians(plat), np.radians(plon)
    a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    d = 2 * 6371008.8 / 1000.0 * np.arcsin(np.minimum(1.0, np.sqrt(a)))
    inside = (d <= 4.0) & (II >= 0) & (II < 300) & (JJ >= 0) & (JJ < 300)
    n = int(inside.sum())
    if n == 0:
        return None
    hit = int((bare[np.clip(II, 0, 299), np.clip(JJ, 0, 299)] & inside).sum())
    return hit / n


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    meas = json.loads((DER / "measures.json").read_text(encoding="utf-8"))["windows"]
    res = json.loads((DER / "results.json").read_text(encoding="utf-8"))
    cfg = json.loads((ROOT / "config/measure.json").read_text(encoding="utf-8"))
    sigma = np.array([float(cfg["features"][k]["sigma"]) for k in FEATS])
    cls = json.loads((SCRP / "classes.json").read_text(encoding="utf-8"))
    W = cls["windows"]
    closing = cls["closing_ids"]
    sample40 = cls["sample40_ids"]

    # ---- class per window (all 400 classified; the closure needs the full set)
    for w in meas:
        c = W[w["id"]]
        w["s70"] = c["c70"]
        w["s60"] = c["c60"]
        w["s100"] = c["c100"]
        w["bare_full_disk"] = c["bare_share"]
        w["class"] = klass(c["c70"])
        w["n_disk_px"] = c["n_disk_px"]
        w["pool_rule_replica"] = pool_rule_replica(w, w["tile"])
    by_id = {w["id"]: w for w in meas}

    def counts(ids):
        cs = [by_id[i]["class"] for i in ids]
        n = len(cs)
        out = {"n": n}
        for k in ("ROCK", "MIXED", "ICE"):
            kk = sum(1 for c in cs if c == k)
            out[k] = {"n": kk, "share": round(kk / n, 4), "wilson95": wilson(kk, n)}
        return out

    all_ids = [w["id"] for w in meas]
    c39 = counts(closing)
    c40 = counts(sample40)
    call = counts(all_ids)

    # ---- pool-rule replica check (why the stored candidate share differs from the full disk)
    rep_ok = [w for w in meas if w["pool_rule_replica"] is not None]
    match = sum(1 for w in rep_ok if abs(w["pool_rule_replica"] - w["worldcover_share"]) < 1e-5)
    mism = [w for w in meas if abs(w["bare_full_disk"] - w["worldcover_share"]) > 1e-5]
    rep_check = {"windows_checked": len(rep_ok), "replica_matches_stored_candidate_share": match,
                 "windows_full_disk_differs_from_stored": len(mism),
                 "max_abs_diff_full_disk_vs_stored": round(max(abs(w["bare_full_disk"] - w["worldcover_share"]) for w in meas), 4),
                 "mismatch_lat_range": [round(min(w["lat"] for w in mism), 2), round(max(w["lat"] for w in mism), 2)] if mism else None}

    # ---- Mars gap cells and closure
    import pyarrow.parquet as pq
    cells = pq.read_table(ROOT / "data/derived/neighbors/mars_cells.parquet").to_pylist()
    gap = [c for c in cells if c["gap"] is True]
    assert len(gap) == 211, len(gap)
    Xq = np.array([[c[k] for k in FEATS] for c in gap], dtype=float)
    thr = np.array([c["threshold"] for c in gap], dtype=float)
    Zq = Xq / sigma

    def nearest(ids):
        Xa = np.array([[by_id[i]["features"][k] for k in FEATS] for i in ids], dtype=float)
        Za = Xa / sigma
        D = np.sqrt(((Zq[:, None, :] - Za[None, :, :]) ** 2).mean(axis=2))
        j = D.argmin(axis=1)
        return D[np.arange(len(gap)), j], np.array(ids)[j]

    d_all, id_all = nearest(all_ids)
    rock_ids = [i for i in all_ids if by_id[i]["class"] == "ROCK"]
    d_rock, id_rock = nearest(rock_ids)
    closed_all = d_all <= thr
    closed_rock = d_rock <= thr

    stored = {c["id"]: c for c in res["mars_cells"]}
    d_stored = np.array([stored[c["id"]]["d_arctic_nearest"] for c in gap])
    closed_stored = np.array([stored[c["id"]]["closed"] for c in gap])
    sanity = {"closed_all_recomputed": int(closed_all.sum()), "closed_stored": int(closed_stored.sum()),
              "max_abs_diff_nearest_D_vs_stored": float(np.max(np.abs(d_all - d_stored))),
              "closed_flags_identical": bool(np.array_equal(closed_all, closed_stored))}

    n = len(gap)
    k_all = int(closed_all.sum())
    k_rock = int(closed_rock.sum())
    lost = [gap[i]["id"] for i in range(n) if closed_all[i] and not closed_rock[i]]
    closures = {
        "n_gap_cells": n,
        "closed_all_windows": {"k": k_all, "share": round(k_all / n, 4), "wilson95": wilson(k_all, n)},
        "closed_rock_only": {"k": k_rock, "share": round(k_rock / n, 4), "wilson95": wilson(k_rock, n)},
        "closed_lost_when_ice_removed": len(lost),
        "lost_cell_ids": lost,
        "n_rock_windows": len(rock_ids),
        "rock_nearest_windows_for_closed_rock": {str(k): int(v) for k, v in zip(*np.unique(id_rock[closed_rock], return_counts=True))},
        "all_nearest_class_of_closing_windows": {k: sum(1 for i in id_all[closed_all] if by_id[i]["class"] == k)
                                                 for k in ("ROCK", "MIXED", "ICE")},
    }

    # ---- windows table (the 39)
    table = []
    for wid in closing:
        w = by_id[wid]
        table.append({"arctic_id": wid, "lat": w["lat"], "lon": w["lon"], "class": w["class"],
                      "s70": round(w["s70"], 4), "s60": round(w["s60"], 4), "s100": round(w["s100"], 4),
                      "n_disk_px": w["n_disk_px"], "slope_p95_deg": round(w["features"]["slope_p95_deg"], 2)})
    table.sort(key=lambda r: -r["s70"])

    payload = {
        "schema": "analog.arctic_ice_check/1",
        "question": "Do the Arctic windows that close Mars gaps sit on rock/bare ground (ROCK) or on snow/ice (ICE)?",
        "seed": cls["seed"],
        "class_rule": {"ROCK": "share70 < 0.2", "MIXED": "0.2 <= share70 < 0.5", "ICE": "share70 >= 0.5"},
        "share_definition": "WorldCover 2021 class 70 pixels / all pixels within 4 km (full disk, nearest-sampled 300x300 per 3 deg tile, same as the coarse cache)",
        "distance": {"features": FEATS, "sigma": dict(zip(FEATS, sigma.tolist())), "formula": "sqrt(mean_k((a_k-b_k)/sigma_k)^2), K=3"},
        "classes": {"closing_39": c39, "sample_40_of_other_361": c40, "all_400": call},
        "closing_39_table": table,
        "pool_rule_check": rep_check,
        "closure": closures,
        "sanity": sanity,
        "sample40_ids": sample40,
        "tile_errors": cls["tile_errors"],
        "cache_check": cls["cache_check"],
    }
    (OUT / "arctic_ice.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")

    # ---- markdown
    def fmt_c(c):
        return " | ".join(f"{c[k]['n']} ({c[k]['share']*100:.0f}%, {c[k]['wilson95'][0]*100:.0f}-{c[k]['wilson95'][1]*100:.0f})"
                          for k in ("ROCK", "MIXED", "ICE"))

    lines = []
    lines.append("# Arctic ice check: are the closing windows rock or ice?\n")
    lines.append("Script: `arctic_ice_classes.py` (class shares, re-read of the WorldCover tiles with classes kept) and "
                 "`arctic_ice_closure.py` (this file + JSON). Figures: `closing_contact.png`, `pool_contact.png`.\n")
    lines.append("Class rule: ROCK share70 < 0.2; MIXED 0.2 to 0.5; ICE >= 0.5. Share = WorldCover class 70 / all pixels "
                 "within 4 km. Wilson 95% on the share of each class.\n")
    lines.append("## Counts (ROCK | MIXED | ICE)\n")
    lines.append("| Set | n | ROCK | MIXED | ICE |")
    lines.append("|---|---|---|---|---|")
    lines.append(f"| 39 closing windows | {c39['n']} | {fmt_c(c39)} |")
    lines.append(f"| 40 sample of the other 361 (seed 20261114) | {c40['n']} | {fmt_c(c40)} |")
    lines.append(f"| all 400 measured (extra) | {call['n']} | {fmt_c(call)} |")
    lines.append("")
    lines.append("## Mars gap cells closed (211 gap cells, tie threshold per cell)\n")
    lines.append("| Windows used | closed | share | Wilson 95% |")
    lines.append("|---|---|---|---|")
    lines.append(f"| all 400 | {k_all} | {k_all/n*100:.1f}% | {closures['closed_all_windows']['wilson95'][0]*100:.1f}-{closures['closed_all_windows']['wilson95'][1]*100:.1f}% |")
    lines.append(f"| ROCK only ({len(rock_ids)} windows) | {k_rock} | {k_rock/n*100:.1f}% | {closures['closed_rock_only']['wilson95'][0]*100:.1f}-{closures['closed_rock_only']['wilson95'][1]*100:.1f}% |")
    lines.append("")
    lines.append(f"Closures lost when ICE/MIXED windows are removed: {len(lost)}.\n")
    lines.append("## Pool-rule note\n")
    lines.append(f"The stored candidate share (`measures.json` worldcover_share) tests only a +-5 px box around the centre "
                 f"(`WIN_PX` in build_pool_index). At these latitudes the 4 km disk is wider than that box in longitude, "
                 f"so the stored share differs from the full-disk share in {rep_check['windows_full_disk_differs_from_stored']} of 400 windows "
                 f"(max {rep_check['max_abs_diff_full_disk_vs_stored']}). The replica of the box rule reproduces the stored value in "
                 f"{rep_check['replica_matches_stored_candidate_share']} of {rep_check['windows_checked']} windows checked. "
                 f"The class rule here uses the full disk.\n")
    lines.append("## 39 closing windows (sorted by share70)\n")
    lines.append("| arctic_id | lat | lon | class | s70 | s60 | s100 | disk px | slope_p95 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in table:
        lines.append(f"| {r['arctic_id']} | {r['lat']} | {r['lon']} | {r['class']} | {r['s70']} | {r['s60']} | {r['s100']} | {r['n_disk_px']} | {r['slope_p95_deg']} |")
    lines.append("")
    (OUT / "arctic_ice.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"classes39": {k: c39[k]['n'] for k in ('ROCK','MIXED','ICE')},
                      "classes40": {k: c40[k]['n'] for k in ('ROCK','MIXED','ICE')},
                      "classes400": {k: call[k]['n'] for k in ('ROCK','MIXED','ICE')},
                      "closed_all": k_all, "closed_rock": k_rock, "lost": len(lost),
                      "sanity": sanity, "pool_rule": rep_check}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
