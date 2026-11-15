"""Tie export for the site (STANDARDS 10.11, 10.13): which Earth candidates of each target are statistically tied.

Two candidates are tied when their D differs by less than the dev sensor-noise threshold of the target's relief class.
Groups follow the anchor rule of _common.tie_groups. This script only states the ties for the site; it changes no ranking.

Reads: config/sites.json (targets); the ranking the site shows (_common.ranking_file: refine when present, else the search
ranking; each file carries its tie_rule); data/derived/validation/noise_v<version>.json (threshold cross-check);
site/data/rankings/<target>.json (must match the ranking row by row, else the script stops).
Writes: site/data/ties.json only.

Usage: .venv/Scripts/python.exe pipelines/export_ties.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from _common import (  # noqa: E402
    Paths,
    load_json,
    make_paths,
    noise_file_name,
    ranking_file,
    read_config,
    sites_list,
    tie_groups,
    write_json,
)

RULE = (
    "Places in one tie group differ pairwise by less than the sensor-noise threshold of the target's relief class: "
    "the 95th percentile of D between NASADEM and Copernicus GLO-30 over the dev regions of that class "
    "(data/derived/validation/noise_v1.3.json, classes.<class>.p95; STANDARDS 10.11). Groups are formed by the anchor "
    "rule: a new group starts when D minus the first D of the current group reaches the threshold."
)
ABS_TOL = 1e-9
N_CANDIDATES = 10


def sentence(k: int, n: int) -> str:
    """User-facing sentence (template fixed by the brief)."""
    if k > 1 and k == n:
        return (
            f"All {n} Earth places are statistically tied: their differences are smaller than the measurement noise. "
            "None of them is 'the' twin; choose among them by climate, access or what you want to rehearse."
        )
    if k > 1:
        return (
            f"The first {k} of {n} Earth places are statistically tied: their differences are smaller than the "
            "measurement noise. None of them is 'the' twin; choose among them by climate, access or what you want "
            "to rehearse."
        )
    return "Place 1 is closer than the measurement noise allows the others to be."


def build_groups(rows: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    """Groups of one ranking. Stops when the tie_group in the file is not the anchor rule of D at the threshold."""
    ordered = sorted(rows, key=lambda r: int(r["rank"]))
    ds = [float(r["D"]) for r in ordered]
    if any(b < a for a, b in zip(ds, ds[1:])):
        raise ValueError("D is not ascending with rank")
    expected = tie_groups(ds, threshold)
    found = [int(r["tie_group"]) for r in ordered]
    if expected != found:
        raise ValueError(f"tie_group does not follow the anchor rule at threshold {threshold}: file {found}, rule {expected}")
    groups: list[dict[str, Any]] = []
    for g in sorted(set(found)):
        members = [r for r in ordered if int(r["tie_group"]) == g]
        groups.append({
            "tie_group": g,
            "ranks": [int(r["rank"]) for r in members],
            "D_min": float(members[0]["D"]),
            "D_max": float(members[-1]["D"]),
        })
    return groups


def target_entry(rows: list[dict[str, Any]], threshold: float, basis: str) -> dict[str, Any]:
    """Ties of one target: groups, k = candidates tied with the first place, and the sentence."""
    groups = build_groups(rows, threshold)
    n = len(rows)
    k = len(groups[0]["ranks"])
    return {
        "threshold": threshold,
        "threshold_basis": basis,
        "groups": groups,
        "n_tied_with_first": k,
        "n_candidates": n,
        "sentence": sentence(k, n),
    }


def check_site_copy(paths: Paths, tid: str, rows: list[dict[str, Any]]) -> None:
    """The ranking the site shows (site/data/rankings) must equal the ranking file row by row (rank, analog, D, tie)."""
    site_rows = load_json(paths.root / "site" / "data" / "rankings" / f"{tid}.json")["ranking"]
    if len(site_rows) != len(rows):
        raise ValueError(f"{tid}: site has {len(site_rows)} rows, ranking file {len(rows)}")
    key = lambda r: int(r["rank"])  # noqa: E731
    for a, b in zip(sorted(rows, key=key), sorted(site_rows, key=key)):
        same = (
            int(a["rank"]) == int(b["rank"])
            and a["analog_id"] == b["analog_id"]
            and abs(float(a["D"]) - float(b["D"])) <= ABS_TOL
            and int(a["tie_group"]) == int(b["tie_group"])
        )
        if not same:
            raise ValueError(f"{tid}: site ranking differs from the ranking file at rank {a['rank']}")


def main() -> int:
    paths = make_paths(None, sample=False)
    version = str(read_config(paths)["version"])
    noise = load_json(paths.derived / "validation" / noise_file_name(version))
    targets: dict[str, Any] = {}
    for site in sites_list(paths):
        tid = str(site["id"])
        rfile = ranking_file(paths, tid)
        data = load_json(rfile)
        rows = data["ranking"]
        rule = data["tie_rule"]
        cls = str(rule["relief_class"])
        threshold = float(rule["noise_p95"])
        info = noise["classes"][cls]
        if abs(float(info["p95"]) - threshold) > ABS_TOL:
            raise ValueError(f"{tid}: tie_rule noise_p95 {threshold} != noise file classes.{cls}.p95 {info['p95']}")
        if len(rows) != N_CANDIDATES:
            raise ValueError(f"{tid}: {len(rows)} candidates, expected {N_CANDIDATES}")
        check_site_copy(paths, tid, rows)
        basis = (
            f"95th percentile of D between two DEMs of the same place (NASADEM vs Copernicus GLO-30), "
            f"{info['n']} dev regions of relief class '{cls}' (noise_v{version}.json, classes.{cls}.p95)"
        )
        entry = target_entry(rows, threshold, basis)
        entry["relief_class"] = cls
        entry["n_noise_regions"] = int(info["n"])
        entry["threshold_note"] = (
            f"The noise threshold of the '{cls}' class comes from only {info['n']} regions: treat the tie as approximate."
            if int(info["n"]) < 5 else None)
        targets[tid] = entry
        print(f"{tid}: class={cls} threshold={threshold:.4f} k={entry['n_tied_with_first']} of {entry['n_candidates']} "
              f"groups={len(entry['groups'])} source={paths.rel(rfile)}")
    out = {"generated_by": "pipelines/export_ties.py", "rule": RULE, "targets": targets}
    write_json(paths.root / "site" / "data" / "ties.json", out)
    print(f"written: {paths.rel(paths.root / 'site' / 'data' / 'ties.json')} ({len(targets)} targets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
