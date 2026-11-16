"""External validation of the analog engine (pre-registered: docs/validation/external/PREREG.md, 2026-11-15 17:35).

Question: do the Earth places that agencies use as Mars or Moon analogs lie closer to that target, under the frozen v1.3
measure, than a random place of the Earth pool?

Stages. Each reads only files written by the stage before it (STANDARDS section 1):
  fetch    clip one 8 km window per pair. NASADEM (Planetary Computer) for lat <= 60; Copernicus GLO-30 (public S3)
           for 60 to 84 N. Output: data/raw/external/<region>/{nasadem,copdem}.tif and data/raw/external/clip_log.json
  measure  measure each clip with _common.measure_raw (frozen v1.3, config/measure.json, no sigma change).
           Output: data/derived/validation/external_windows.json
  results  (default) D, percentile, tie, median, one-sided Wilcoxon, verdict, and a second-form check.
           Output: data/derived/validation/external.json and docs/validation/external/RESULTS.md

Definitions (PREREG sections 3 to 5):
  D(a, b) = sqrt( sum_k ((a_k - b_k) / sigma_k)^2 / K ), K = 3 features (slope_p95_deg, hi, hurst).
  Target D: a site gives D(window, site); a set (Mars cells, Moon targets) gives the minimum D over its cells.
  Percentile (mid-rank): 100 * (#{pool < D} + 0.5 #{pool == D}) / n, over the pool D between the same target and every
  pool window. Under chance it is uniform (median 50). Lower is closer.
  Tie: D_target <= threshold of the target relief class (run.json thresholds; rugged if slope_p95 >= 3 deg).
  Verdict: PASS if median percentile <= 25 AND one-sided Wilcoxon p (percentile < 50) < 0.05; with fewer than 6 valid
  pairs the verdict is "insufficient" and nothing is forced.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import pyarrow.parquet as pq  # noqa: E402

FEATS = ("slope_p95_deg", "hi", "hurst")
MIN_PAIRS = 6
MEDIAN_MAX = 25.0
P_MAX = 0.05
HALF_KM = 5.0  # clip half-width; the measure uses R = 4 km (fetch_data.EARTH_HALF_WIDTH_KM)
NASADEM_MAX_LAT = 60.0
COP_MAX_LAT = 84.0
COP_MIN_LAT = -84.0
NASADEM_MIN_LAT = -56.0

PAIRS = ROOT / "docs" / "validation" / "external" / "pairs.json"
REGIONS = ROOT / "config" / "known_analog_regions.json"
MEASURE = ROOT / "config" / "measure.json"
RUN = ROOT / "data" / "derived" / "neighbors" / "run.json"
EARTH = ROOT / "data" / "derived" / "neighbors" / "earth_windows.parquet"
MARS = ROOT / "data" / "derived" / "neighbors" / "mars_cells.parquet"
TARGETS = ROOT / "data" / "derived" / "neighbors" / "targets.parquet"
RAW = ROOT / "data" / "raw" / "external"
CLIP_LOG = RAW / "clip_log.json"
WINDOWS = ROOT / "data" / "derived" / "validation" / "external_windows.json"
OUT_JSON = ROOT / "data" / "derived" / "validation" / "external.json"
OUT_MD = ROOT / "docs" / "validation" / "external" / "RESULTS.md"


# ----------------------------------------------------------------------------------------------- pure helpers
def sensor_for_lat(lat: float) -> str | None:
    """Sensor of the 8 km window (PREREG 3): NASADEM 56 S to 60 N, Copernicus GLO-30 60 to 84 N, else None."""
    if NASADEM_MIN_LAT <= lat <= NASADEM_MAX_LAT:
        return "nasadem"
    if NASADEM_MAX_LAT < lat <= COP_MAX_LAT:
        return "copdem"
    return None


def _finite(x: Any) -> float | None:
    if x is None:
        return None
    v = float(x)
    return v if math.isfinite(v) else None


def dist(a: dict[str, Any], b: dict[str, Any], sigma: dict[str, float]) -> float | None:
    """D(a, b) = sqrt( sum_k ((a_k - b_k) / sigma_k)^2 / K ) over the in-distance features. None if one is missing."""
    s = 0.0
    for k in FEATS:
        av, bv = _finite(a.get(k)), _finite(b.get(k))
        if av is None or bv is None:
            return None
        s += ((av - bv) / sigma[k]) ** 2
    return math.sqrt(s / len(FEATS))


def pct_midrank(pool_d: np.ndarray, d: float) -> float:
    """Mid-rank percentile of d in pool_d, 0 to 100. Lower = closer to the target than the pool."""
    n = pool_d.size
    if n == 0:
        raise ValueError("empty pool")
    less = int(np.sum(pool_d < d))
    equal = int(np.sum(pool_d == d))
    return 100.0 * (less + 0.5 * equal) / n


def relief_of(slope_p95_deg: float, flat_deg: float) -> str:
    """'rugged' when slope_p95 >= flat_deg (equal counts as rugged), else 'flat' (STANDARDS 10.11)."""
    return "rugged" if slope_p95_deg >= flat_deg else "flat"


def wilcoxon_p_less(pcts: list[float]) -> float | None:
    """One-sided signed-rank test, H1: median percentile < 50. None when scipy cannot test (e.g. n = 0)."""
    from scipy.stats import wilcoxon

    x = np.asarray(pcts, dtype=float) - 50.0
    if x.size == 0 or np.all(x == 0):
        return None
    return float(wilcoxon(x, alternative="less").pvalue)


def verdict_of(n_valid: int, median_pct: float | None, p: float | None) -> str:
    """PREREG 5: fewer than MIN_PAIRS valid pairs is 'insufficient', never forced into PASS or FAIL."""
    if n_valid < MIN_PAIRS:
        return "insufficient"
    if median_pct is None or p is None:
        return "FAIL"
    return "PASS" if (median_pct <= MEDIAN_MAX and p < P_MAX) else "FAIL"


# ----------------------------------------------------------------------------------------------- io helpers
def load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".part")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False, default=str) + "\n", encoding="utf-8")
    tmp.replace(p)


def parquet_rows(p: Path) -> list[dict[str, Any]]:
    return pq.read_table(p).to_pylist()


def rel(p: Path) -> str:
    return p.resolve().relative_to(ROOT.resolve()).as_posix()


def region_index() -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in load_json(REGIONS)["regions"]}


def pair_list() -> list[dict[str, Any]]:
    return load_json(PAIRS)["pairs"]


def sigma_map() -> dict[str, float]:
    cfg = load_json(MEASURE)
    return {k: float(cfg["features"][k]["sigma"]) for k in FEATS}


# ----------------------------------------------------------------------------------------------- stage: fetch
def cmd_fetch(_: argparse.Namespace) -> int:
    """Clip one window per pair. Existing clips are kept (no re-download)."""
    import arctic_probe as ap  # noqa: E402  (Copernicus S3 clip, same code as the pool)
    from analog.io import fetch  # noqa: E402

    regions = region_index()
    log: list[dict[str, Any]] = load_json(CLIP_LOG) if CLIP_LOG.exists() else []
    done = {r["region_id"]: r for r in log}
    for pair in pair_list():
        rid = pair["region_id"]
        reg = regions[rid]
        sensor = sensor_for_lat(reg["lat"])
        if sensor is None:
            raise SystemExit(f"{rid}: lat {reg['lat']} outside the sensor bands (PREREG 3); not clipped")
        out = RAW / rid / f"{sensor}.tif"
        if out.exists():
            print(f"{rid}: {sensor} clip already on disk, kept")
            continue
        if sensor == "nasadem":
            meta = fetch.stac_clip("nasadem", "elevation", reg["lat"], reg["lon"], HALF_KM, out)
        else:
            meta = ap.clip_cop(reg["lat"], reg["lon"], HALF_KM, out)
        entry = {"region_id": rid, "sensor": sensor, "path": rel(out), "lat": reg["lat"], "lon": reg["lon"],
                 "half_km": HALF_KM, "sha256": fetch.sha256_file(out), "bytes": out.stat().st_size, "meta": meta}
        done[rid] = entry
        print(f"{rid}: {sensor} clip written ({entry['bytes']} bytes)")
    write_json(CLIP_LOG, list(done.values()))
    return 0


# ----------------------------------------------------------------------------------------------- stage: measure
def cmd_measure(_: argparse.Namespace) -> int:
    """Frozen v1.3 measure of each clip through _common.measure_raw (the same chain as the pool)."""
    from _common import make_paths, measure_raw, provenance_block, read_config  # noqa: E402

    paths = make_paths(None, False)
    cfg = read_config(paths)
    clips = {r["region_id"]: r for r in load_json(CLIP_LOG)}
    regions = region_index()
    rows = []
    for pair in pair_list():
        rid = pair["region_id"]
        reg = regions[rid]
        clip = clips.get(rid)
        if clip is None or not (ROOT / clip["path"]).exists():
            rows.append({"region_id": rid, "status": "missing", "reason": "no clip on disk", "features": None})
            continue
        r = measure_raw(ROOT / clip["path"], reg["lat"], reg["lon"], "earth", cfg)
        rows.append({"region_id": rid, "lat": reg["lat"], "lon": reg["lon"], "sensor": clip["sensor"],
                     "clip": clip["path"], "clip_sha256": clip["sha256"], "status": r["status"], "reason": r["reason"],
                     "native_res_m": r["native_res_m"], "coverage": r["coverage"], "n_valid": r["n_valid"],
                     "features": r["features"]})
        print(f"{rid}: {r['status']} {r['reason'] or ''}")
    payload = {
        "doc": "External validation windows, frozen v1.3 measure (PREREG docs/validation/external/PREREG.md).",
        "n_windows": len(rows),
        "n_ok": sum(1 for x in rows if x["status"] == "ok"),
        "windows": rows,
        "provenance": provenance_block(paths, "validate_external_measure", [
            ("known_analog_regions", REGIONS), ("nasadem_copdem_clips", CLIP_LOG)]),
    }
    write_json(WINDOWS, payload)
    return 0


# ----------------------------------------------------------------------------------------------- stage: results
def target_cells(pair: dict[str, Any], mars: list[dict[str, Any]], targets: list[dict[str, Any]]) -> tuple[list[dict], str]:
    """The target cells of a pair (PREREG 2) and a text description."""
    t = pair["target"]
    by_id = {r["id"]: r for r in targets}
    if t["type"] == "site":
        cells = [by_id[i] for i in t["ids"]]
        return cells, "site " + ", ".join(t["ids"])
    cells: list[dict[str, Any]] = []
    names = []
    for s in t["sets"]:
        if s == "mars_cells":
            cells += [r for r in mars if all(_finite(r.get(k)) is not None for k in FEATS)]
            names.append("mars_cells")
        elif s == "moon_targets":
            cells += [r for r in targets if r["body"] == "moon"]
            names.append("moon_targets")
        else:
            raise ValueError(f"unknown set {s}")
    return cells, "set " + "+".join(names)


def cmd_results(_: argparse.Namespace) -> int:
    from _common import make_paths, provenance_block  # noqa: E402

    run = load_json(RUN)
    sig = sigma_map()
    flat_deg = float(run["flat_slope_p95_deg"])
    thr = {"rugged": float(run["thresholds"]["rugged"]), "flat": float(run["thresholds"]["flat"])}
    regions = region_index()
    windows = {w["region_id"]: w for w in load_json(WINDOWS)["windows"]}
    earth = [r for r in parquet_rows(EARTH) if all(_finite(r.get(k)) is not None for k in FEATS)]
    mars = parquet_rows(MARS)
    targets = parquet_rows(TARGETS)
    n_pool_all = len(parquet_rows(EARTH))

    # pool feature matrix (rows with all three features), standardised by sigma
    pool_z = np.array([[float(r[k]) / sig[k] for k in FEATS] for r in earth])

    rows: list[dict[str, Any]] = []
    for pair in pair_list():
        rid = pair["region_id"]
        reg = regions[rid]
        w = windows.get(rid)
        base = {"region_id": rid, "name": reg["name"], "source_url": pair["source_url"],
                "source_quote": pair["source_quote"], "body": pair["body"]}
        if w is None or w["status"] != "ok":
            rows.append({**base, "valid": False, "reason": (w or {}).get("reason") or "not measured"})
            continue
        a = w["features"]
        cells, desc = target_cells(pair, mars, targets)
        ds = [(dist(a, c, sig), c) for c in cells]
        ds = [(d, c) for d, c in ds if d is not None]
        d_best, best = min(ds, key=lambda t: t[0])
        cls = relief_of(float(best["slope_p95_deg"]), flat_deg)
        # pool: D between the same target and every pool window (min over the cells for a set)
        tgt_z = np.array([[float(c[k]) / sig[k] for k in FEATS] for c in cells])
        from scipy.spatial import cKDTree

        tree = cKDTree(tgt_z)
        pool_d = tree.query(pool_z, k=1)[0] / math.sqrt(len(FEATS))
        pct = pct_midrank(pool_d, d_best)
        rows.append({**base, "valid": True, "target": desc, "n_target_cells": len(cells),
                     "target_best_id": best["id"],
                     "target_best_class": cls, "D": d_best, "percentile": pct,
                     "tie_threshold": thr[cls], "tie": bool(d_best <= thr[cls]),
                     "pool_n": int(pool_d.size), "pool_median_D": float(np.median(pool_d)),
                     "analog_features": {k: a[k] for k in FEATS}, "analog_sensor": w["sensor"],
                     "analog_lat": w["lat"], "analog_lon": w["lon"],
                     "best_target_features": {k: best[k] for k in FEATS}})

    valid = [r for r in rows if r["valid"]]
    pcts = [r["percentile"] for r in valid]
    median = float(np.median(pcts)) if pcts else None
    p = wilcoxon_p_less(pcts) if pcts else None
    n_ties = sum(1 for r in valid if r["tie"])
    verdict = verdict_of(len(valid), median, p)

    # second-form check: pure Python D and a sorted-count percentile for the first two valid pairs
    check = []
    for r in valid[:2]:
        w = windows[r["region_id"]]
        pair = next(p_ for p_ in pair_list() if p_["region_id"] == r["region_id"])
        cells, _ = target_cells(pair, mars, targets)
        d_list = []
        for c in cells:
            s2 = 0.0
            for k in FEATS:
                s2 += ((float(w["features"][k]) - float(c[k])) / sig[k]) ** 2
            d_list.append(math.sqrt(s2 / 3.0))
        d2 = min(d_list)
        pool2 = []
        for pr in earth:
            best2 = None
            for c in cells:
                s2 = 0.0
                for k in FEATS:
                    s2 += ((float(pr[k]) - float(c[k])) / sig[k]) ** 2
                dd = math.sqrt(s2 / 3.0)
                best2 = dd if best2 is None or dd < best2 else best2
            pool2.append(best2)
        below = sum(1 for x in pool2 if x < d2)
        equal = sum(1 for x in pool2 if x == d2)
        pct2 = 100.0 * (below + 0.5 * equal) / len(pool2)
        check.append({"region_id": r["region_id"], "D_main": r["D"], "D_second_form": d2,
                      "abs_diff_D": abs(r["D"] - d2), "percentile_main": r["percentile"],
                      "percentile_second_form": pct2, "abs_diff_pct": abs(r["percentile"] - pct2)})

    payload = {
        "doc": "External validation of the analog engine. Pre-registered: docs/validation/external/PREREG.md (2026-11-15 17:35).",
        "config_version": run["config_version"],
        "sigma": sig,
        "thresholds": thr,
        "flat_slope_p95_deg": flat_deg,
        "pool": {"n_rows": n_pool_all, "n_with_D": len(earth)},
        "n_pairs_listed": len(rows),
        "n_valid": len(valid),
        "min_pairs": MIN_PAIRS,
        "median_percentile": median,
        "wilcoxon_p_less": p,
        "n_within_tie": n_ties,
        "verdict": verdict,
        "pairs": rows,
        "excluded_by_rule": load_json(PAIRS).get("excluded_by_rule", {}),
        "second_form_check": check,
        "provenance": provenance_block(make_paths(None, False), "validate_external", [
            ("external_windows", WINDOWS), ("earth_windows", EARTH), ("mars_cells", MARS), ("targets", TARGETS),
            ("prereg_pairs", PAIRS), ("run_json", RUN)]),
    }
    write_json(OUT_JSON, payload)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(render_md(payload), encoding="utf-8")
    print(f"verdict={verdict} n_valid={len(valid)} median={median} p={p} ties={n_ties}")
    return 0


def render_md(p: dict[str, Any]) -> str:
    lines = [
        "# External validation: results",
        "",
        "Pre-registration: `docs/validation/external/PREREG.md` (2026-11-15 17:35). Generated by "
        "`pipelines/validate_external.py`; do not edit by hand.",
        "",
        f"**Verdict: {p['verdict']}**. Valid pairs: {p['n_valid']} of {p["min_pairs"]} required "
        f"({p['n_pairs_listed']} listed).",
        "",
        f"- Median percentile: {p['median_percentile']:.2f}" if p["median_percentile"] is not None else "- Median: n/a",
        f"- One-sided Wilcoxon (percentile < 50), p = {p['wilcoxon_p_less']:.4f}" if p["wilcoxon_p_less"] is not None
        else "- Wilcoxon: n/a",
        f"- Pairs within the tie threshold: {p['n_within_tie']}",
        f"- Tie thresholds (run.json): rugged {p['thresholds']['rugged']:.4f}, flat {p['thresholds']['flat']:.4f}; "
        f"class cut {p['flat_slope_p95_deg']} deg",
        f"- Pool: {p['pool']['n_with_D']} windows with D (of {p['pool']['n_rows']} rows)",
        "",
        "| Region | Source (quote) | Target | D | Percentile | Tie |",
        "|---|---|---|---|---|---|",
    ]
    for r in p["pairs"]:
        if not r["valid"]:
            lines.append(f"| {r['region_id']} | - | - | - | - | not measured: {r['reason']} |")
            continue
        quote = r["source_quote"].replace("|", "/")
        if len(quote) > 110:
            quote = quote[:107] + "..."
        lines.append(f"| {r['region_id']} | {quote} | {r['target']} ({r['body']}), {r['n_target_cells']}  cells, "
                     f"best: {r['target_best_id']} [{r['target_best_class']}] | {r['D']:.4f} | "
                     f"{r['percentile']:.2f} | {'yes' if r['tie'] else 'no'} (threshold {r['tie_threshold']:.4f}) |")
    lines += ["", "## Excluded by rule (PREREG 2)", ""]
    for k, v in p["excluded_by_rule"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Second-method check (pure Python, no cKDTree)", "",
              "| Region | D main | D second method | diff D | Percentile main | Percentile second method | diff pct |",
              "|---|---|---|---|---|---|---|"]
    for c in p["second_form_check"]:
        lines.append(f"| {c['region_id']} | {c['D_main']:.6f} | {c['D_second_form']:.6f} | {c['abs_diff_D']:.1e} | "
                     f"{c['percentile_main']:.4f} | {c['percentile_second_form']:.4f} | {c['abs_diff_pct']:.1e} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("stage", nargs="?", default="results", choices=["fetch", "measure", "results"])
    args = ap.parse_args(argv)
    fn = {"fetch": cmd_fetch, "measure": cmd_measure, "results": cmd_results}[args.stage]
    return fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
