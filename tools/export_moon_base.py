"""Export the Moon permanent-base layer to site/data/moon_base.json for the UI.

Reads data/derived/moon_base/moon_base.json only (written by pipelines/moon_base.py). Writes:
{"generated_by", "sources": [{id, url, product, resolution_m, period, credit}], "sites": {<target_id>: {illum_mean_pct,
illum_max_pct, psr_nearest_km, psr_area_km2, earth_vis_pct, notes}}}

Values are rounded for the browser (percent and km to 2 decimals; PSR area to 4 decimals). Nothing is typed by hand.

Usage: .venv/Scripts/python.exe tools/export_moon_base.py [--root <project root>]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PCT_KEYS = ("illum_mean_pct", "illum_max_pct", "earth_vis_pct")
KM_KEYS = ("psr_nearest_km",)
AREA_KEYS = ("psr_area_km2",)
SITE_KEYS = ("illum_mean_pct", "illum_max_pct", "psr_nearest_km", "psr_area_km2", "earth_vis_pct", "notes")


def _round(value: Any, ndigits: int) -> Any:
    """Round a finite number; keep None (not polar) and text as they are."""
    if value is None or isinstance(value, str):
        return value
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(f"non-finite value in the derived file: {value!r}")
    return round(v, ndigits)


def build_site(src: dict[str, Any], site_id: str) -> dict[str, Any]:
    """One site of the browser copy: the six published keys only, rounded."""
    missing = [k for k in SITE_KEYS if k not in src]
    if missing:
        raise KeyError(f"site {site_id} lacks keys {missing}")
    out: dict[str, Any] = {}
    for k in PCT_KEYS:
        out[k] = _round(src[k], 2)
    for k in KM_KEYS:
        out[k] = _round(src[k], 3)
    for k in AREA_KEYS:
        out[k] = _round(src[k], 4)
    out["notes"] = str(src["notes"])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export the Moon permanent-base layer for the UI")
    ap.add_argument("--root", default=None, help="project root (default: the repository root)")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve() if args.root else ROOT

    src_path = root / "data" / "derived" / "moon_base" / "moon_base.json"
    if not src_path.exists():
        print(f"missing {src_path}; run pipelines/moon_base.py first", file=sys.stderr)
        return 1
    data = json.loads(src_path.read_text(encoding="utf-8"))

    sources = [
        {
            "id": s["id"],
            "url": s["url"],
            "product": s["product"],
            "resolution_m": s["resolution_m"],
            "period": s["period"],
            "credit": s["credit"],
        }
        for s in data["sources"]
    ]
    sites = {sid: build_site(rec, sid) for sid, rec in sorted(data["sites"].items())}
    out = {"generated_by": data["generated_by"], "sources": sources, "sites": sites}

    dst = root / "site" / "data" / "moon_base.json"
    tmp = dst.with_name(dst.name + ".part")
    tmp.write_text(json.dumps(out, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(dst)
    print(f"wrote {dst} ({len(sites)} sites, {len(sources)} sources)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
