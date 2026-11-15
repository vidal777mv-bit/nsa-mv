"""P4 validate (STANDARDS 10.1, 10.11). Two modes, never mixed.

--noise   Dev sensor-noise thresholds for the tie rule (STANDARDS 10.11): D(NASADEM, Copernicus) of each dev region,
          grouped by relief class of the dev region (NASADEM slope_p95_deg: rugged >= flat_slope_p95_deg, else flat).
          Dev regions only, no holdout, no pass/fail. Writes <derived>/validation/noise_v<version>.json. Re-runnable
          (deterministic; it reads only the dev measure records).

--holdout The single validation of the current config (v1.3 on a fresh holdout, STANDARDS 10.11): AUC of -D over the
          105 pairs of the 15 holdout regions (NASADEM), its bootstrap CI and permutation p, and the 1-NN of each holdout
          region against the 15 dev regions (NASADEM). Thresholds are config validation.v13.pass, read as they are.
          Writes <derived>/validation/v<version>.json. RUNS ONCE: refuses (exit 3) when that file already exists.

Refuses (exit 2, nothing written) when a sigma is null or a required measure record is missing or not ok.
The v1.2 result (validation/v1.2.json: V0, V1, V2 and V2-R with the reserved regions) was written by the earlier
validate.py and is never rewritten. Reserved regions are not used by v1.3.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import binom

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    Paths,
    RunLog,
    make_paths,
    noise_file_name,
    parse_args,
    provenance_block,
    read_config,
    region_raw,
    regions_list,
    sigmas_missing,
    validation_file_name,
    window_records,
    write_json,
)
from analog.core import measure as meas  # noqa: E402
from analog.core import stats  # noqa: E402

EXIT_REFUSED = 2
EXIT_ALREADY_RUN = 3


def relief_class_of(rec: dict[str, Any], flat_below_deg: float) -> str | None:
    """Relief class of a measure record (see core.measure.relief_class)."""
    return meas.relief_class(rec["features"].get("slope_p95_deg"), flat_below_deg)


def noise_table(dev_nasadem: dict[str, dict[str, Any]], dev_copdem: dict[str, dict[str, Any]],
                dev_ids: list[str], cfg: dict[str, Any]) -> dict[str, Any]:
    """D(NASADEM, Copernicus) per dev region, grouped by the relief class of the region's NASADEM record.

    Formula: D of STANDARDS section 4 over the features in distance (weight > 0), sigma from the config. Per class:
    n, median and p95 (numpy linear interpolation). A class with no value has p95 None (search then refuses those
    targets). Dev regions with a null D are listed with the reason and left out.
    """
    v13 = cfg["validation"]["v13"]
    flat_below = float(v13["flat_slope_p95_deg"])
    fcfg = cfg["features"]
    min_shared = cfg["distance"]["min_shared_features"]
    rows: list[dict[str, Any]] = []
    vals: dict[str, list[float]] = {"rugged": [], "flat": []}
    for rid in dev_ids:
        a, b = dev_nasadem.get(rid), dev_copdem.get(rid)
        if a is None or b is None:
            rows.append({"region_id": rid, "class": None, "D": None, "reason": "one sensor missing or not ok"})
            continue
        cls = relief_class_of(a, flat_below)
        d = meas.distance(a["features"], b["features"], fcfg, min_shared)
        rows.append({"region_id": rid, "class": cls, "slope_p95_deg": a["features"].get("slope_p95_deg"), "D": d,
                     "reason": None if d is not None else f"fewer than {min_shared} shared features"})
        if d is not None and cls is not None:
            vals[cls].append(float(d))
    classes: dict[str, Any] = {}
    for cls in ("rugged", "flat"):
        v = vals[cls]
        classes[cls] = {
            "n": len(v),
            "median": float(np.median(v)) if v else None,
            "p95": float(np.percentile(v, 95)) if v else None,
            "regions": [r["region_id"] for r in rows if r.get("class") == cls and r.get("D") is not None],
        }
    return {"flat_slope_p95_deg": flat_below, "rule": v13["tie_rule"], "n_expected": len(dev_ids),
            "n_used": sum(len(v) for v in vals.values()), "classes": classes, "regions": rows}


def discrimination(recs: dict[str, dict[str, Any]], ids: list[str], classes: list[str], cfg: dict[str, Any]) -> dict[str, Any]:
    """AUC of -D for same-class versus different-class pairs over the given regions (NASADEM records).

    Pairs: all unordered pairs (15 regions -> 105 pairs: 15 same-class, 90 different-class). Null D pairs are dropped
    and counted. p from label permutation (permutations), CI from bootstrap over regions (bootstrap), both seeded.
    The pass flag here uses the v1.2 thresholds of validation (auc_min, p_max); the holdout mode applies v13.pass.
    """
    vr = cfg["validation"]
    usable = [rid for rid in ids if rid in recs]
    index = {rid: i for i, rid in enumerate(usable)}
    cls = [recs[rid]["class"] for rid in usable]
    fcfg = cfg["features"]
    min_shared = cfg["distance"]["min_shared_features"]
    pa, pb, score = [], [], []
    for i in range(len(usable)):
        for j in range(i + 1, len(usable)):
            d = meas.distance(recs[usable[i]]["features"], recs[usable[j]]["features"], fcfg, min_shared)
            pa.append(index[usable[i]])
            pb.append(index[usable[j]])
            score.append(float("nan") if d is None else -d)
    pa_a = np.array(pa, dtype=np.int64)
    pb_a = np.array(pb, dtype=np.int64)
    sc = np.array(score, dtype=float)
    perm = stats.permutation_p_by_labels(pa_a, pb_a, sc, cls, B=int(vr["permutations"]), seed=int(vr["seed"]))
    boot = stats.bootstrap_ci_by_regions(pa_a, pb_a, sc, cls, B=int(vr["bootstrap"]), seed=int(vr["seed"]))
    kept = sc[np.isfinite(sc)]
    return {
        "n_regions": len(usable),
        "n_regions_expected": len(ids),
        "n_pairs_total": len(pa),
        "n_pairs_null_D": int(len(pa) - kept.size),
        "n_pairs_self": int(perm.get("n_self_pairs_excluded", 0)),
        "n_pairs_used": int(perm.get("n_pairs", 0)),
        "n_same_class_pairs": int(sum(1 for x in range(len(pa)) if cls[pa[x]] == cls[pb[x]])),
        "auc": perm.get("auc_obs"),
        "bootstrap": {"B": boot.get("B"), "ci_lo": boot.get("ci_lo"), "ci_hi": boot.get("ci_hi"),
                      "n_valid": boot.get("n_valid"), "n_invalid": boot.get("n_invalid")},
        "permutation": {"B": perm.get("B"), "p": perm.get("p"), "n_undefined_perm": perm.get("n_undefined_perm"),
                        "reason": perm.get("reason")},
    }


def nn_predictions(query: dict[str, dict[str, Any]], dev: dict[str, dict[str, Any]], dev_ids: list[str],
                   cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """1-NN class of each query region against the dev regions, by D (NASADEM).

    Each row: the nearest dev region (smallest D, ties by id), its class, and correct = (predicted == true class).
    A query with no finite D to any dev region gets correct None (not counted).
    """
    fcfg = cfg["features"]
    min_shared = cfg["distance"]["min_shared_features"]
    rows: list[dict[str, Any]] = []
    for rid, q in sorted(query.items()):
        cands = []
        for dv in dev_ids:
            if dv not in dev:
                continue
            d = meas.distance(q["features"], dev[dv]["features"], fcfg, min_shared)
            if d is not None:
                cands.append((float(d), dv))
        row: dict[str, Any] = {"region_id": rid, "true_class": q["class"], "n_dev_candidates": len(cands)}
        if not cands:
            row.update(nearest_dev=None, D=None, predicted_class=None, correct=None)
        else:
            d_best, nn = min(cands, key=lambda t: (t[0], t[1]))
            pred = dev[nn]["class"]
            row.update(nearest_dev=nn, D=d_best, predicted_class=pred, correct=bool(pred == q["class"]))
        rows.append(row)
    return rows


def nn_summary(rows: list[dict[str, Any]], n_expected: int, min_correct: int) -> dict[str, Any]:
    """Count of correct 1-NN predictions, Wilson 95% CI and one-sided binomial p against chance 1/5 (STANDARDS 10.11).

    Formula: k correct of n computed; p = P(X >= k | n, 0.2) = binom.sf(k - 1, n, 0.2). Pass needs n == n_expected
    and k >= min_correct.
    """
    computed = [r for r in rows if r.get("correct") is not None]
    k = sum(1 for r in computed if r["correct"])
    n = len(computed)
    return {
        "k_correct": k,
        "n_computed": n,
        "n_expected": n_expected,
        "wilson95": stats.wilson(k, n) if n > 0 else None,
        "binomial_one_sided_p": float(binom.sf(k - 1, n, 0.2)) if n > 0 else None,
        "chance": 0.2,
        "min_correct": min_correct,
        "pass": bool(n == n_expected and k >= min_correct),
    }


def holdout_pass(auc: float | None, ci_lo: float | None, perm_p: float | None, nn_pass: bool,
                 pass_cfg: dict[str, Any]) -> dict[str, bool]:
    """The pass criteria of config validation.v13.pass, each one tested as written."""
    auc_ok = auc is not None and auc >= float(pass_cfg["auc_min"])
    ci_ok = ci_lo is not None and ci_lo > float(pass_cfg["auc_ci_lower_gt"])
    perm_ok = perm_p is not None and perm_p < float(pass_cfg["perm_p_max"])
    return {"auc": bool(auc_ok), "auc_ci_lower": bool(ci_ok), "permutation_p": bool(perm_ok), "nn_against_dev": bool(nn_pass),
            "all": bool(auc_ok and ci_ok and perm_ok and nn_pass)}


def measure_fingerprint(paths: Paths, kinds: tuple[str, ...]) -> dict[str, Any]:
    """Count and a SHA-256 over the sorted record hashes of the measure records this validation read."""
    files = sorted(f for f in paths.stage("measure").glob("*.json") if any(f.stem.startswith(k) for k in kinds))
    hashes = [hashlib.sha256(f.read_bytes()).hexdigest() for f in files]
    return {"n_records": len(files), "sha256_of_record_hashes": hashlib.sha256("".join(hashes).encode()).hexdigest()}


def _dev_records(paths: Paths, dev_ids: list[str]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """(NASADEM, Copernicus) region records with status ok, keyed by region id."""
    recs = window_records(paths.stage("measure"), kind="region", status="ok")
    nasa = {r["region_id"]: r for r in recs if r["sensor"] == "nasadem" and r["region_id"] in dev_ids}
    cop = {r["region_id"]: r for r in recs if r["sensor"] == "copdem" and r["region_id"] in dev_ids}
    return nasa, cop


def run_noise(paths: Paths) -> int:
    """Write the dev noise thresholds (tie rule of STANDARDS 10.11). Returns the exit code."""
    cfg = read_config(paths)
    stage_dir = paths.stage("validation")
    log = RunLog(stage_dir, "validate_noise")
    missing = sigmas_missing(cfg)
    if missing:
        log.event("error", "refused: sigma is null (run calibrate_sigma.py first)", features=missing)
        return EXIT_REFUSED
    regions = regions_list(paths)
    dev_ids = [r["id"] for r in regions if r.get("role") == "dev"]
    nasa, cop = _dev_records(paths, dev_ids)
    absent = [rid for rid in dev_ids if rid not in nasa or rid not in cop]
    if absent:
        log.event("error", "refused: dev regions without both ok sensor records", regions=absent)
        return EXIT_REFUSED
    doc = noise_table(nasa, cop, dev_ids, cfg)
    inputs: list[tuple[str, Path]] = []
    for rid in dev_ids:
        for sensor in ("nasadem", "copdem"):
            raw = region_raw(paths, rid, sensor)
            if raw is not None:
                inputs.append((sensor, raw))
    out = {
        "schema": "analog.validation.noise/1",
        "config_version": cfg["version"],
        "sigma": {k: cfg["features"][k]["sigma"] for k in meas.FEATURE_IDS},
        "features_in_distance": [k for k in meas.FEATURE_IDS if float(cfg["features"][k]["weight"]) > 0.0],
        **doc,
        "provenance": provenance_block(paths, "validation", inputs),
    }
    path = stage_dir / noise_file_name(cfg["version"])
    write_json(path, out)
    summary = {c: {"n": out["classes"][c]["n"], "p95": out["classes"][c]["p95"]} for c in out["classes"]}
    log.event("info", "noise thresholds written", classes=summary, path=paths.rel(path))
    return 0


def run_holdout(paths: Paths) -> int:
    """The single holdout validation of the current config (STANDARDS 10.11). Returns the exit code."""
    cfg = read_config(paths)
    stage_dir = paths.stage("validation")
    log = RunLog(stage_dir, "validate_holdout")
    out_path = stage_dir / validation_file_name(cfg["version"])
    if out_path.exists():
        log.event("error", "refused: the holdout validation already ran for this version (runs once)",
                  path=paths.rel(out_path))
        return EXIT_ALREADY_RUN
    missing = sigmas_missing(cfg)
    if missing:
        log.event("error", "refused: sigma is null (run calibrate_sigma.py first)", features=missing)
        return EXIT_REFUSED

    v13 = cfg["validation"]["v13"]
    classes = list(cfg["validation"]["classes"])
    regions = regions_list(paths)
    dev_ids = [r["id"] for r in regions if r.get("role") == "dev"]
    hold = [r for r in regions if r.get("role") == v13["holdout_role"]]
    expected = len(classes) * int(v13["holdout_per_class"])
    per_class = {c: sum(1 for r in hold if r["class"] == c) for c in classes}
    if len(hold) != expected or any(n != int(v13["holdout_per_class"]) for n in per_class.values()):
        log.event("error", "refused: holdout regions do not match the pre-registered design", found=len(hold),
                  expected=expected, per_class=per_class)
        return EXIT_REFUSED
    hold_ids = [r["id"] for r in hold]
    hold_cls = {r["id"]: r["class"] for r in hold}

    holdout_recs = {r["region_id"]: {**r, "class": hold_cls[r["region_id"]]} for r in
                    window_records(paths.stage("measure"), kind="holdout", status="ok") if r["region_id"] in hold_cls}
    absent = [rid for rid in hold_ids if rid not in holdout_recs]
    dev_nasa, _dev_cop = _dev_records(paths, dev_ids)
    dev_nasa = {rid: {**r, "class": next(x["class"] for x in regions if x["id"] == rid)} for rid, r in dev_nasa.items()}
    if absent or len(dev_nasa) != len(dev_ids):
        log.event("error", "refused: holdout or dev NASADEM records missing or not ok", holdout_absent=absent,
                  dev_present=len(dev_nasa), dev_expected=len(dev_ids))
        return EXIT_REFUSED

    auc_block = discrimination(holdout_recs, hold_ids, classes, cfg)
    nn_rows = nn_predictions(holdout_recs, dev_nasa, dev_ids, cfg)
    nn = nn_summary(nn_rows, len(hold_ids), int(v13["pass"]["nn_against_dev_min_correct"]))
    passes = holdout_pass(auc_block["auc"], auc_block["bootstrap"]["ci_lo"], auc_block["permutation"]["p"],
                          nn["pass"], v13["pass"])
    inputs: list[tuple[str, Path]] = []
    for rid in hold_ids + dev_ids:
        raw = region_raw(paths, rid, "nasadem")
        if raw is not None:
            inputs.append(("nasadem", raw))
    out = {
        "schema": "analog.validation/1",
        "version": cfg["version"],
        "config_version": cfg["version"],
        "design": {"holdout_role": v13["holdout_role"], "holdout_per_class": v13["holdout_per_class"],
                   "holdout_regions": hold_ids, "dev_regions": dev_ids},
        "thresholds": v13["pass"],
        "sigma": {k: cfg["features"][k]["sigma"] for k in meas.FEATURE_IDS},
        "features_in_distance": [k for k in meas.FEATURE_IDS if float(cfg["features"][k]["weight"]) > 0.0],
        "measure_records_read": measure_fingerprint(paths, ("holdout", "region")),
        "AUC": auc_block,
        "NN": {"summary": nn, "rows": nn_rows},
        "pass": passes,
        "summary": {"AUC_pass": passes["auc"] and passes["auc_ci_lower"] and passes["permutation_p"],
                    "NN_pass": passes["nn_against_dev"], "all_pass": passes["all"]},
        "provenance": provenance_block(paths, "validation", inputs),
    }
    write_json(out_path, out)
    log.event("info", "holdout validation written (single run)", summary=out["summary"], path=paths.rel(out_path))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap_extra = [
        (("--noise",), {"action": "store_true", "help": "dev noise thresholds for the tie rule (re-runnable)"}),
        (("--holdout",), {"action": "store_true", "help": "the single holdout validation (runs once)"}),
    ]
    args = parse_args("Validation: --noise (dev tie thresholds) or --holdout (single holdout run).", extra=ap_extra)
    if args.noise == args.holdout:
        print("use exactly one of --noise or --holdout")
        return EXIT_REFUSED
    paths = make_paths(args.root, args.sample)
    return run_noise(paths) if args.noise else run_holdout(paths)


if __name__ == "__main__":
    raise SystemExit(main())
