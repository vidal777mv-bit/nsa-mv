"""P3 calibrate_sigma: sigma_k = 1.4826 * MAD_k over the Earth search pool (STANDARDS 10.1, core/stats.robust_sigma).

Input: <derived>/measure/pool__*.json with status ok, sensor nasadem and no exclusion (built by build_measure.py).
Only this script writes sigma values into config/measure.json, once, before validation. A non-null sigma is never
overwritten unless --force is given (and then the old values are logged). Every calibration is appended to
docs/CHANGELOG.md with the n, median and sigma of each feature.

Sample mode writes the sample sigma to data/derived/sample/config/measure.json and never touches config/measure.json
or docs/CHANGELOG.md.

Refused (nothing written, exit code 2): fewer than MIN_N non-null values for a feature (real runs), a sigma that is
zero or not finite (a degenerate feature cannot be normalised).
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    Paths,
    RunLog,
    make_paths,
    parse_args,
    utc_now,
    window_records,
    write_json,
    load_json,
)
from analog.core import measure as meas  # noqa: E402
from analog.core import stats  # noqa: E402

MIN_N_REAL = 500
MIN_N_SAMPLE = 10


def calibrate(paths: Paths, min_n: int) -> tuple[dict[str, Any], bool]:
    """Compute sigma per feature from the ok pool windows. Returns (table, ok).

    table[name] = {n, median, mad, sigma, reason}; sigma None and a reason when the feature cannot be calibrated.
    Formula: sigma = 1.4826 * median(|x - median(x)|) over the non-null values (stats.robust_sigma).
    """
    # Guard: NASADEM windows only, never excluded rows (copdem windows, e.g. Arctic, must not mix into sigma)
    pool = [r for r in window_records(paths.stage("measure"), kind="pool", status="ok")
            if r.get("sensor") == "nasadem" and r.get("excluded") is None]
    table: dict[str, Any] = {}
    ok = True
    for name in meas.FEATURE_IDS:
        vals = np.array([r["features"][name] for r in pool if r["features"].get(name) is not None], dtype=float)
        n = int(vals.size)
        if n < min_n:
            table[name] = {"n": n, "median": None, "mad": None, "sigma": None,
                           "reason": f"n={n} < {min_n} pool values"}
            ok = False
            continue
        med = float(np.median(vals))
        mad = float(np.median(np.abs(vals - med)))
        sigma = stats.robust_sigma(vals)
        if sigma is None or not np.isfinite(sigma) or sigma <= 0.0:
            table[name] = {"n": n, "median": med, "mad": mad, "sigma": None,
                           "reason": "sigma is zero or not finite (degenerate feature)"}
            ok = False
            continue
        table[name] = {"n": n, "median": med, "mad": mad, "sigma": float(sigma), "reason": None}
    return table, ok


def run(paths: Paths, force: bool) -> int:
    """Calibrate, then write (real: config + changelog; sample: sample config copy). Returns the exit code."""
    base_path = paths.measure_config
    cfg = load_json(base_path)
    stage_dir = paths.stage("measure")
    log = RunLog(paths.derived / "config" if paths.sample else stage_dir, "calibrate_sigma")
    min_n = MIN_N_SAMPLE if paths.sample else MIN_N_REAL
    table, ok = calibrate(paths, min_n)
    for name, row in table.items():
        log.event("info" if row["sigma"] is not None else "error", "feature", feature=name, **row)
    if not ok:
        log.event("error", "sigma not written: at least one feature cannot be calibrated")
        return 2

    already = {k: cfg["features"][k]["sigma"] for k in meas.FEATURE_IDS if cfg["features"][k].get("sigma") is not None}
    if already and not force and not paths.sample:
        log.event("error", "sigma already calibrated; refusing to overwrite (use --force only with a logged reason)",
                  existing=already)
        return 3

    out = copy.deepcopy(cfg)
    for name in meas.FEATURE_IDS:
        out["features"][name]["sigma"] = table[name]["sigma"]

    if paths.sample:
        target = paths.sample_config
        write_json(target, out)
        log.event("info", "sample sigma written (config/measure.json untouched)", path=paths.rel(target))
        return 0

    write_json(base_path, out)
    lines = [
        f"## Sigma calibration — {utc_now()}",
        "",
        "- Script: pipelines/calibrate_sigma.py, pool = data/derived/measure/pool__*.json (status ok). "
        "Config sha256 is in the next validation provenance.",
    ]
    if already:
        lines.append(f"- Overwritten with --force; previous values: {already}")
    for name in meas.FEATURE_IDS:
        row = table[name]
        lines.append(
            f"- {name}: n={row['n']}, median={row['median']:.6g}, MAD={row['mad']:.6g}, sigma=1.4826*MAD={row['sigma']:.6g}"
        )
    entry = "\n".join(lines) + "\n"
    with open(paths.changelog, "a", encoding="utf-8") as fh:
        fh.write("\n" + entry)
    log.event("info", "sigma written to config/measure.json and logged in docs/CHANGELOG.md",
              sigma={k: table[k]["sigma"] for k in meas.FEATURE_IDS})
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(
        "Calibrate sigma = 1.4826 MAD over the search pool and write it into config/measure.json (P3).",
        extra=[(("--force",), {"action": "store_true", "help": "overwrite existing sigma (logged)"})],
    )
    paths = make_paths(args.root, args.sample)
    return run(paths, force=bool(args.force))


if __name__ == "__main__":
    raise SystemExit(main())
