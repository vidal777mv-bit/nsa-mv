"""P-P rehearsal plan (STANDARDS section 10.15): one JSON per target-twin pair, same file name as its card.

Reads (never writes): data/derived/cards/<target>__<analog_id>.json (pair cards: analog_id starts with '<target>__'),
config/bodies.json, config/rehearsal_rules.json, site/data/targets.json (body of each target) and, when it exists,
data/derived/light/light.json (P-S: targets{id}, earth_windows{id}). The Earth window id of a card is the analog id
without the '<target>__' prefix (e.g. 'pool__pool_00226'), which is also the id used in the measure records and the
query tables; a card whose refined.pool_id disagrees is given no light values (never guessed).

Writes: data/derived/rehearsal/<card name>.json and site/data/rehearsal/<card name>.json, each
{provenance, target_id, analog_id, lines: [...]} (lines as in src/analog/core/rehearsal.py).

Without light.json the light lines (low_sun) come out with status null and reason 'light stage not available'; the
rest are unaffected. Run after the light stage to fill them.

Sample mode (STANDARDS 10.7): --sample uses the first target of each body (2 targets) and writes under
data/derived/sample/ only. Full run: no flag (all 16 targets, 160 pairs).

Usage: .venv/Scripts/python.exe pipelines/rehearsal.py [--sample] [--ids t1,t2] [--root <dir>]
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    Paths,
    RunLog,
    ids_arg,
    load_json,
    make_paths,
    parse_args,
    provenance_block,
    ranking_file,
    write_json,
)
from analog.core import rehearsal as RH  # noqa: E402

LIGHT_REL = "data/derived/light/light.json"
LIGHT_CONFIG_REL = "config/light.json"
CARDS_REL = "data/derived/cards"
RULES_REL = "config/rehearsal_rules.json"
BODIES_REL = "config/bodies.json"
TARGETS_REL = "site/data/targets.json"
STAGE = "rehearsal"  # data/derived/rehearsal (Paths.stage() only knows its own stage list, so the folder is built here)


def sample_targets(targets: list[dict[str, Any]]) -> list[str]:
    """First target of each body in targets.json order (STANDARDS 10.7: a sample of 2 targets, one Mars, one Moon)."""
    seen: dict[str, str] = {}
    for t in targets:
        seen.setdefault(str(t["body"]), str(t["id"]))
    return list(seen.values())


def ranked_analogs(paths: Paths, target_id: str) -> set[str] | None:
    """analog_ids of the target's CURRENT ranking (refined when it exists), or None when no ranking file exists."""
    rp = ranking_file(paths, target_id)
    if not rp.exists():
        return None
    return {str(r["analog_id"]) for r in load_json(rp).get("ranking", [])}


def pair_cards(paths: Paths, target_id: str) -> list[Path]:
    """Pair cards of one target = cards whose analog_id is in the target's current ranking (2026-11-14). A refined pair
    has the id '<target>__pool__pool_N'; a candidate that could not be refined (Arctic, no NASADEM above 60N) keeps
    its plain pool id 'pool__pool_N'. Older per-window cards whose id is not in the ranking are not pairs.
    Without a ranking file it falls back to the old rule (analog_id starts with '<target>__')."""
    ranked = ranked_analogs(paths, target_id)
    out: list[Path] = []
    for p in sorted((paths.root / CARDS_REL).glob("*.json")):
        try:
            doc = load_json(p)
        except ValueError:
            continue
        if not isinstance(doc, dict) or doc.get("target_id") != target_id:
            continue
        aid = str(doc.get("analog_id", ""))
        if (aid in ranked) if ranked is not None else aid.startswith(f"{target_id}__"):
            out.append(p)
    return out


def light_entries(light_doc: dict[str, Any] | None, target_id: str, wkey: str | None) -> dict[str, Any]:
    """{'target': entry|None, 'analog': entry|None, 'reason': str|None} from light.json (no value is invented).
    ``wkey`` is the earth_windows key (the pool index id, see RH.light_window_key)."""
    if light_doc is None:
        return {"target": None, "analog": None, "reason": f"{RH.LIGHT_MISSING}: {LIGHT_REL} not found"}
    targets = light_doc.get("targets") or {}
    windows = light_doc.get("earth_windows") or {}
    t_entry = targets.get(target_id)
    a_entry = windows.get(wkey) if wkey else None
    reasons = []
    if t_entry is None:
        reasons.append(f"target {target_id} not in light.json targets")
    if a_entry is None:
        reasons.append(f"window key {wkey} not in light.json earth_windows")
    return {"target": t_entry, "analog": a_entry, "reason": "; ".join(reasons) or None}


def build_pair(paths: Paths, card_path: Path, target_body: str, bodies: dict[str, Any], rules: dict[str, Any],
               light_doc: dict[str, Any] | None, earth_eps: float | None) -> dict[str, Any]:
    """The rehearsal document of one pair (pure evaluation; only the provenance reads files)."""
    card = load_json(card_path)
    tid, aid = card["target_id"], card["analog_id"]
    wid = RH.earth_window_id(tid, aid)
    wkey = RH.light_window_key(wid)
    light = light_entries(light_doc, tid, wkey)
    refined = card.get("refined") or {}
    if refined.get("pool_id") and refined.get("pool_id") != wid:
        light["analog"] = None
        light["reason"] = f"card refined.pool_id {refined.get('pool_id')} differs from window id {wid}"
    lines = RH.evaluate_pair(card, target_body, bodies, rules, light, earth_eps)
    inputs = [("card", card_path), ("bodies", paths.root / BODIES_REL), ("rules", paths.root / RULES_REL),
              ("targets", paths.root / TARGETS_REL)]
    lp = paths.root / LIGHT_REL
    if lp.exists():
        inputs.append(("light", lp))
    lcp = paths.root / LIGHT_CONFIG_REL
    if lcp.exists():
        inputs.append(("light_config", lcp))
    return {
        "provenance": provenance_block(paths, STAGE, inputs),
        "target_id": tid,
        "analog_id": aid,
        "lines": lines,
    }


def run(paths: Paths, ids: list[str] | None = None) -> dict[str, Any]:
    """Build every pair of the selected targets; returns the summary (counts per line id and status)."""
    out_dir = paths.derived / STAGE
    log = RunLog(out_dir, STAGE)
    targets = load_json(paths.root / TARGETS_REL)["targets"]
    if ids:
        selected = [t for t in targets if str(t["id"]) in set(ids)]
    elif paths.sample:
        wanted = set(sample_targets(targets))
        selected = [t for t in targets if str(t["id"]) in wanted]
    else:
        selected = list(targets)
    bodies = load_json(paths.root / BODIES_REL)["bodies"]
    rules = load_json(paths.root / RULES_REL)
    lp = paths.root / LIGHT_REL
    light_doc = load_json(lp) if lp.exists() else None
    if light_doc is None:
        log.event("warn", "light stage output not found: low_sun lines will be null", path=LIGHT_REL)
    lcfg = paths.root / LIGHT_CONFIG_REL
    earth_eps = float(load_json(lcfg)["bodies"]["earth"]["obliquity_deg"]) if lcfg.exists() else None
    if earth_eps is None:
        log.event("warn", "config/light.json not found: low_sun Earth scan null", path=LIGHT_CONFIG_REL)

    counts: Counter = Counter()
    n_pairs = 0
    site_dir = paths.site_data / "rehearsal"
    for t in selected:
        tid = str(t["id"])
        cards = pair_cards(paths, tid)
        log.event("info", "target", id=tid, body=t["body"], pairs=len(cards))
        for cp in cards:
            doc = build_pair(paths, cp, str(t["body"]), bodies, rules, light_doc, earth_eps)
            name = cp.name
            write_json(out_dir / name, doc)
            write_json(site_dir / name, doc)
            n_pairs += 1
            for line in doc["lines"]:
                counts[(line["id"], line["status"] or "null")] += 1
    summary = {"pairs": n_pairs, "targets": [str(t["id"]) for t in selected], "light_present": light_doc is not None,
               "counts": {f"{k[0]}:{k[1]}": v for k, v in sorted(counts.items())}}
    log.event("info", "rehearsal written", pairs=n_pairs, targets=len(selected), light_present=light_doc is not None)
    return summary


def main(argv: list[str] | None = None) -> int:
    args = parse_args("P-P rehearsal plan per target-twin pair (STANDARDS 10.15).")
    paths = make_paths(args.root, args.sample)
    summary = run(paths, ids=ids_arg(args))
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
