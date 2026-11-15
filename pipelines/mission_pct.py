"""P6 mission_pct: mission-proven terrain share on the 100 m grid (STANDARDS 10.3, core/mission.py).

Windows: every target with an ok measure record, and every analog listed in data/derived/ranking/<target>.json (only
windows whose measure record is ok are used; a window that is not valid is not given a share).

For each window the share is computed for both bodies' limits (config/missions.json -> limits): landing and driving,
moon and mars. Earth analogs need this because a card compares an analog with a target of one body. A missing limit
gives pct null with the reason (never a stand-in value). The denominator is the number of pixels with a defined slope
(interior of the disk, see core/mission.py); n_disk_valid is written next to it.

Control (STANDARDS 10.3, extended by the lead): the landing % of Jezero, Gale, InSight, Spirit, Zhurong and Apollo 17
must be >= 50 on their body's landing limit. If the control cannot be computed or fails, the
run exits with code 3 and says so: nothing may be published before that is resolved.

Output: <derived>/mission/<window>.json (baseline 100 m stated in the file).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    Paths,
    RunLog,
    ids_arg,
    limit_for,
    load_json,
    make_paths,
    missions_limits,
    parse_args,
    provenance_block,
    ranking_file,
    read_config,
    select_ids,
    sites_list,
    window_record_path,
    write_json,
)
from analog import grid as gridmod  # noqa: E402
from analog.core import mission  # noqa: E402

BODIES = ("moon", "mars")
KINDS = ("landing", "driving")
# Control windows (lead, 2026-11-14): proven landings. Each must reach CONTROL_MIN_PCT on its landing limit of its body.
CONTROL = {
    "jezero": ("mars", "landing"),
    "gale": ("mars", "landing"),
    "insight_elysium": ("mars", "landing"),
    "spirit_columbia": ("mars", "landing"),
    "zhurong": ("mars", "landing"),
    "apollo17_taurus_littrow": ("moon", "landing"),
}
CONTROL_MIN_PCT = 50.0


def window_share(
    paths: Paths, rec: dict[str, Any], cfg: dict[str, Any], limits: dict[str, Any] | None, limits_reason: str | None
) -> dict[str, Any]:
    """Shares for one window (both bodies, both kinds). rec is the window's measure record (must be ok)."""
    L = float(cfg["grid"]["L_m"])
    R = float(cfg["grid"]["R_m"])
    raw = paths.root / rec["source_path"]
    z, mask, meta = gridmod.load_local_grid(raw, rec["lat"], rec["lon"], rec["body"], L, R)
    slope = mission.slope_map_deg(z, mask, L)
    by_body: dict[str, Any] = {}
    for body in BODIES:
        by_body[body] = {}
        for kind in KINDS:
            limit, source, why = limit_for(limits, body, kind)
            if limits is None:
                why = limits_reason
            res = mission.mission_share(slope, limit)
            by_body[body][kind] = {
                "limit_deg": limit,
                "source": source,
                "pct": res["pct"],
                "n_below": res["n_below"],
                "reason": res["reason"] if res["pct"] is None else None,
                "limit_reason": why,
            }
    return {
        "n_disk_valid": int(mask.sum()),
        "n_defined": int(np.isfinite(slope).sum()),
        "by_body": by_body,
        "baseline_m": L,
        "R_m": R,
        "input": {"source_path": rec["source_path"], "crs_src": meta["crs_src"]},
    }


def analog_ids(paths: Paths, targets: list[str]) -> list[str]:
    """Analog ids listed in the rankings of the given targets (rankings that exist)."""
    out: list[str] = []
    for t in targets:
        rp = ranking_file(paths, t)
        if rp.exists():
            out.extend(row["analog_id"] for row in load_json(rp).get("ranking", []))
    return sorted(set(out))


def run(paths: Paths, ids: list[str] | None) -> int:
    """Compute and write the shares; returns 3 when the control fails, else 0."""
    cfg = read_config(paths)
    stage_dir = paths.stage("mission")
    log = RunLog(stage_dir, "mission_pct")
    limits, why = missions_limits(paths)
    if limits is None:
        log.event("warn", "limits missing: pct written as null", reason=why)

    targets = [t["id"] for t in select_ids(sites_list(paths), ids) if t.get("role") == "target"]
    if paths.sample and ids is None:
        targets = targets[:2]
    windows = sorted(set(targets + analog_ids(paths, targets)))

    results: dict[str, dict[str, Any]] = {}
    for wid in windows:
        rec_path = window_record_path(paths, wid)
        if not rec_path.exists():
            log.event("warn", "no measure record, skipped", id=wid)
            continue
        rec = load_json(rec_path)
        if rec.get("status") != "ok":
            log.event("warn", "window not valid, no share", id=wid, status=rec.get("status"), reason=rec.get("reason"))
            results[wid] = {"status": rec.get("status"), "reason": rec.get("reason")}
            continue
        body_out = window_share(paths, rec, cfg, limits, why)
        body_out.update(id=wid, kind=rec["kind"], lat=rec["lat"], lon=rec["lon"], status="ok", reason=None)
        body_out["provenance"] = provenance_block(paths, "mission", [(rec.get("source_id", "src"), paths.root / rec["source_path"])])
        results[wid] = body_out
        write_json(stage_dir / f"{wid}.json", body_out)
        log.event("info", "share written", id=wid)

    exit_code = 0
    for wid, (body, kind) in CONTROL.items():
        if ids is not None and wid not in ids:
            continue  # control only when the control window is in scope for this run
        if wid not in results or results[wid].get("status") != "ok":
            log.event("error", "CONTROL not computed: window not valid", id=wid, reason=results.get(wid, {}).get("reason", "not in scope"))
            exit_code = 3
            continue
        pct = results[wid]["by_body"][body][kind]["pct"]
        if pct is None:
            log.event("error", "CONTROL not computed: limit missing", id=wid, reason=results[wid]["by_body"][body][kind]["limit_reason"] or results[wid]["by_body"][body][kind]["reason"])
            exit_code = 3
        elif pct < CONTROL_MIN_PCT:
            log.event("error", "CONTROL FAILED (STOP before publishing)", id=wid, pct=pct, minimum=CONTROL_MIN_PCT)
            exit_code = 3
        else:
            log.event("info", "control passed", id=wid, pct=pct, minimum=CONTROL_MIN_PCT)
    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = parse_args("Mission-proven terrain share for targets and ranked analogs (P6).")
    paths = make_paths(args.root, args.sample)
    return run(paths, ids_arg(args))


if __name__ == "__main__":
    raise SystemExit(main())
