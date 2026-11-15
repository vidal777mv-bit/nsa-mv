"""P5 search: for each target, the nearest pool windows in feature space (STANDARDS 10.2, PLAN section 3).

For every target with an ok measure record: D to every ok pool window whose pool-index flag near_known_analog is
False (STANDARDS 10.8: the 25 km exclusion is computed by the pool index, not here). The top_k (10) by D are kept.
Ties (STANDARDS 10.11): the threshold is the dev sensor-noise p95 of the target's own relief class (rugged or flat,
from noise_v<version>.json written by validate.py --noise). Analogs whose D differs by less than it share a tie_group.

tie_group rule (anchor): sort by D; a new group starts when D - D_anchor >= p95, where D_anchor is the D of the first
analog of the current group. Any two analogs in one group therefore differ by less than p95.

Refuses (exit code 2, nothing written) when data/derived/validation/noise_v<config version>.json is missing (p95 needed) or when an ok
pool window has no near_known_analog flag (exclusion cannot be verified). The search runs even when a validation
test failed. A target whose relief class has no noise value is skipped with the reason.

Output: <derived>/ranking/<target>.json.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    tie_groups,
    noise_file_name,
    Paths,
    RunLog,
    ids_arg,
    load_json,
    make_paths,
    parse_args,
    provenance_block,
    read_config,
    select_ids,
    sites_list,
    window_records,
    write_json,
)
from analog.core import measure as meas  # noqa: E402

# tie_groups lives in _common (shared with refine_search); re-exported here for the tests




def rank_target(
    target: dict[str, Any],
    pool: list[dict[str, Any]],
    cfg: dict[str, Any],
    p95: float,
    top_k: int,
) -> dict[str, Any]:
    """Ranking of pool windows for one target. Returns the ranking body (without provenance).

    Exclusion: windows with near_known_analog True are dropped (counted). Null distances are dropped (counted).
    """
    fcfg = cfg["features"]
    min_shared = cfg["distance"]["min_shared_features"]
    scored: list[tuple[float, str, dict[str, Any]]] = []
    n_excluded = 0
    n_null = 0
    for w in pool:
        if w.get("near_known_analog") is True:
            n_excluded += 1
            continue
        d = meas.distance(target["features"], w["features"], fcfg, min_shared)
        if d is None:
            n_null += 1
            continue
        scored.append((d, str(w["id"]), w))
    scored.sort(key=lambda t: (t[0], t[1]))
    top = scored[:top_k]
    groups = tie_groups([t[0] for t in top], p95)
    rows = []
    for rank, ((d, _, w), g) in enumerate(zip(top, groups), start=1):
        rows.append({
            "rank": rank,
            "analog_id": w["id"],
            "D": d,
            "tie_group": g,
            "lat": w["lat"],
            "lon": w["lon"],
            "source_id": w.get("source_id"),
        })
    return {
        "target_id": target["id"],
        "body": target["body"],
        "n_pool_ok": len(pool),
        "n_excluded_near_known_analog": n_excluded,
        "n_null_distance": n_null,
        "n_candidates": len(scored),
        "exclusion_source": "pool index field near_known_analog (25 km, computed in the pool step)",
        "top_k": top_k,
        "tie_rule": {"noise_p95": p95, "rule": "new group when D - D_anchor >= noise p95"},
        "ranking": rows,
    }


REFUSED = -1  # returned by run() when the search refuses (main exits 2)


def run(paths: Paths, ids: list[str] | None) -> int:
    """Rank the pool for each target in scope. Returns the number of rankings written, or REFUSED."""
    cfg = read_config(paths)
    stage_dir = paths.stage("ranking")
    log = RunLog(stage_dir, "search")
    noise_path = paths.stage("validation") / noise_file_name(cfg["version"])
    if not noise_path.exists():
        log.event("error", "refused: noise thresholds not found (validate.py --noise first)", path=noise_path.name)
        return REFUSED
    noise = load_json(noise_path)
    flat_below = float(noise["flat_slope_p95_deg"])
    pool = window_records(paths.stage("measure"), kind="pool", status="ok")
    missing_flag = [w["id"] for w in pool if w.get("near_known_analog") is None]
    if missing_flag:
        log.event("error", "refused: pool windows without near_known_analog flag", n=len(missing_flag),
                  first=missing_flag[:5])
        return REFUSED
    s = cfg["search"]
    targets = [t for t in select_ids(sites_list(paths), ids) if t.get("role") == "target"]
    if paths.sample and ids is None:
        targets = targets[:2]

    written = 0
    for t in targets:
        rec_path = paths.stage("measure") / f"{t['id']}.json"
        if not rec_path.exists():
            log.event("warn", "no measure record for target, ranking skipped", id=t["id"])
            continue
        tr = load_json(rec_path)
        if tr.get("status") != "ok":
            log.event("warn", "target not measured, ranking skipped", id=t["id"], status=tr.get("status"),
                      reason=tr.get("reason"))
            continue
        cls = meas.relief_class(tr["features"].get("slope_p95_deg"), flat_below)
        if cls is None:
            log.event("warn", "target slope null, ranking skipped", id=t["id"])
            continue
        cls_noise = noise["classes"][cls]
        if cls_noise["p95"] is None:
            log.event("error", "no dev noise value for the target's relief class, ranking skipped", id=t["id"],
                      relief_class=cls, n=cls_noise["n"])
            continue
        p95 = float(cls_noise["p95"])
        body = rank_target(tr, pool, cfg, p95, int(s["top_k_per_target"]))
        body["tie_rule"] = {"noise_p95": p95, "relief_class": cls, "relief_slope_p95_deg": tr["features"]["slope_p95_deg"],
                            "flat_slope_p95_deg": flat_below, "noise_n_dev_regions": cls_noise["n"],
                            "rule": "new group when D - D_anchor >= noise p95 of the target's relief class"}
        body["noise_summary"] = {c: {"n": noise["classes"][c]["n"], "p95": noise["classes"][c]["p95"]}
                                 for c in noise["classes"]}
        inputs = [(f"measure:{t['id']}", paths.stage("measure") / f"{t['id']}.json"), ("noise", noise_path)]
        body["provenance"] = provenance_block(paths, "ranking", inputs)
        write_json(stage_dir / f"{t['id']}.json", body)
        written += 1
        log.event("info", "ranking written", id=t["id"], candidates=body["n_candidates"],
                  excluded_near_known=body["n_excluded_near_known_analog"],
                  top1=body["ranking"][0]["analog_id"] if body["ranking"] else None)
    log.event("info", "done", rankings_written=written)
    return written


def main(argv: list[str] | None = None) -> int:
    args = parse_args("Search the pool for analogs of each target (P5).")
    paths = make_paths(args.root, args.sample)
    n = run(paths, ids_arg(args))
    return 2 if n == REFUSED else 0


if __name__ == "__main__":
    raise SystemExit(main())
