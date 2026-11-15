"""Shared helpers for the measurement pipelines: paths, JSON I/O, config, raw-file lookup, run log.

No science lives here except ``measure_raw``, which is the single place where a raw DEM becomes a standard grid and a
feature vector (STANDARDS sections 3, 4 and the validity rules). Every other pipeline imports it, so a window is always
measured the same way.

Sample mode (STANDARDS 10.7): everything is written under data/derived/sample/ (and the site copy under
data/derived/sample/site/data/), so sample outputs never mix with real ones. Sample sigma values are written to
data/derived/sample/config/measure.json, never to config/measure.json.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from analog import grid as gridmod  # noqa: E402
from analog.core import measure as meas  # noqa: E402
from analog.io.places import PlaceIndex, load_admin1  # noqa: E402
from analog.io import provenance as prov  # noqa: E402

SEED = 20261114
SAMPLE_TARGETS = 2
SAMPLE_REGIONS = 3
SAMPLE_POOL = 50
WORLDCOVER_MIN_SHARE = 0.8
STAGE_NAMES = ("measure", "validation", "ranking", "mission", "cards")


@dataclass(frozen=True)
class Paths:
    """All locations of one run. Real runs use data/derived; sample runs use data/derived/sample."""

    root: Path
    sample: bool

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def measure_config(self) -> Path:
        """config/measure.json (the frozen file; only calibrate_sigma writes its sigma values)."""
        return self.config_dir / "measure.json"

    @property
    def raw_dir(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def derived(self) -> Path:
        base = self.root / "data" / "derived"
        return base / "sample" if self.sample else base

    @property
    def sample_config(self) -> Path:
        return self.derived / "config" / "measure.json"

    @property
    def active_config(self) -> Path:
        """Config used by the stages: the sample copy in sample mode (if calibrated), else config/measure.json."""
        if self.sample and self.sample_config.exists():
            return self.sample_config
        return self.measure_config

    @property
    def site_data(self) -> Path:
        return (self.derived / "site" / "data") if self.sample else (self.root / "site" / "data")

    @property
    def changelog(self) -> Path:
        return self.root / "docs" / "CHANGELOG.md"

    def stage(self, name: str) -> Path:
        if name not in STAGE_NAMES:
            raise ValueError(f"unknown stage {name!r}")
        return self.derived / name

    def rel(self, path: str | Path) -> str:
        """Repo-relative POSIX path for a file under the project root (absolute paths outside it are kept)."""
        p = Path(path).resolve()
        try:
            return p.relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return p.as_posix()


def make_paths(root: str | Path | None, sample: bool) -> Paths:
    """Build the Paths object for a run. root defaults to the project root."""
    return Paths(root=Path(root).resolve() if root else ROOT, sample=bool(sample))


def utc_now() -> str:
    """ISO 8601 UTC time with a Z suffix (STANDARDS section 2)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_json(obj: Any) -> Any:
    """Convert numpy scalars and non-finite floats to JSON-safe values (NaN and inf become null, STANDARDS 2)."""
    if isinstance(obj, dict):
        return {str(k): clean_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean_json(v) for v in obj]
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def load_json(path: str | Path) -> Any:
    """Read a JSON file (UTF-8)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, obj: Any) -> None:
    """Write JSON atomically (temp file, then replace). NaN never reaches the file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".part")
    tmp.write_text(json.dumps(clean_json(obj), indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)


class RunLog:
    """Append-only log of skips, errors and decisions for one stage (stdout too)."""

    def __init__(self, stage_dir: Path, stage: str) -> None:
        self.path = stage_dir / "run_log.jsonl"
        self.stage = stage
        stage_dir.mkdir(parents=True, exist_ok=True)

    def event(self, level: str, msg: str, **fields: Any) -> None:
        rec = {"time": utc_now(), "stage": self.stage, "level": level, "msg": msg, **fields}
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(clean_json(rec), ensure_ascii=False) + "\n")
        print(f"[{level}] {self.stage}: {msg}" + (f" {fields}" if fields else ""))


def read_config(paths: Paths) -> dict[str, Any]:
    """Measure config in use (see Paths.active_config)."""
    return load_json(paths.active_config)


def features_in_distance(cfg: dict[str, Any]) -> list[str]:
    """Features with weight > 0 in config (the ones that enter D; ridge and valley are weight 0 since v1.2)."""
    return [k for k in meas.FEATURE_IDS if float(cfg["features"][k]["weight"]) > 0.0]


def validation_file_name(version: str) -> str:
    """Holdout validation output of one config version, e.g. v1.2.json or v1.3.json (validate.py, read by export)."""
    return f"v{version}.json"


def noise_file_name(version: str) -> str:
    """Dev sensor-noise thresholds of one config version, e.g. noise_v1.3.json (validate.py --noise, read by search)."""
    return f"noise_v{version}.json"


def sigmas_missing(cfg: dict[str, Any]) -> list[str]:
    """Names of features whose sigma is null in the config."""
    return [k for k, spec in cfg["features"].items() if k in meas.FEATURE_IDS and spec.get("sigma") is None]


def sites_list(paths: Paths) -> list[dict[str, Any]]:
    """Planetary targets from config/sites.json (STANDARDS section 8)."""
    return list(load_json(paths.config_dir / "sites.json")["sites"])


def regions_list(paths: Paths) -> list[dict[str, Any]]:
    """Earth windows from config/regions.json (STANDARDS section 8)."""
    return list(load_json(paths.config_dir / "regions.json")["regions"])


def select_ids(items: list[dict[str, Any]], ids: list[str] | None, key: str = "id") -> list[dict[str, Any]]:
    """Keep the items whose key is in ids (order of items kept); all items when ids is None."""
    if not ids:
        return items
    wanted = set(ids)
    return [it for it in items if str(it.get(key)) in wanted]


def manifest_paths(paths: Paths) -> dict[str, list[Path]]:
    """source_id -> every absolute raw path listed for it in data/raw/manifest.json (a source can serve several sites,
    e.g. lola_20m_polar_ldem clipped per site; the caller must pick the path that belongs to the site)."""
    mpath = paths.raw_dir / "manifest.json"
    if not mpath.exists():
        return {}
    out: dict[str, list[Path]] = {}
    for entry in load_json(mpath):
        out.setdefault(str(entry["source_id"]), []).append(paths.root / entry["path"])
    return out


def site_raw_path(candidates: list[Path], site_id: str) -> Path | None:
    """The manifest path of one site: the candidate stored in data/raw/<body>/<site_id>/, else the only candidate.
    None when several candidates exist and none belongs to the site (never guessed)."""
    own = [p for p in candidates if p.parent.name == site_id]
    if own:
        return own[0]
    if len(candidates) == 1:
        return candidates[0]
    return None


def local_source_path(paths: Paths, source_id: str, site_id: str) -> Path | None:
    """Raw file of a local source in config/sources.json (access 'local', field 'filename'), stored under
    data/raw/<body>/<site_id>/<filename>, as the source record says. Used only when the manifest lacks the id; the
    sha256 is then computed from this file by the provenance block. Returns None when the source has no filename."""
    spath = paths.config_dir / "sources.json"
    if not spath.exists():
        return None
    for src in load_json(spath).get("sources", []):
        if src.get("id") == source_id and src.get("filename") and src.get("body"):
            return paths.raw_dir / src["body"] / site_id / src["filename"]
    return None


SENSOR_GLOBS: dict[str, tuple[str, ...]] = {
    "nasadem": ("nasadem*.tif",),
    "copdem": ("copdem*.tif", "cop_dem_glo30*.tif"),
}


def region_raw(paths: Paths, region_id: str, sensor: str) -> Path | None:
    """First GeoTIFF of a sensor ('nasadem' or 'copdem') under data/raw/earth/<region_id>/, or None.

    Accepted names: nasadem*.tif; copdem*.tif or cop_dem_glo30*.tif (the fetch step has used both spellings).
    """
    folder = paths.raw_dir / "earth" / region_id
    if not folder.is_dir():
        return None
    for pattern in SENSOR_GLOBS[sensor]:
        hits = sorted(folder.glob(pattern))
        if hits:
            return hits[0]
    return None


def pool_index(paths: Paths) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Search pool index data/raw/earth/pool/index.json (STANDARDS 10.8).

    Accepted forms: a top-level list, or {"windows": [...]}. Entry fields: id, lat, lon, worldcover_share,
    near_known_analog (bool, 25 km exclusion), path (repo-relative), valid_fraction. Returns (windows, None), or
    (None, reason) when the index does not exist.
    """
    ipath = paths.raw_dir / "earth" / "pool" / "index.json"
    if not ipath.exists():
        return None, "pool index not found (data/raw/earth/pool/index.json)"
    data = load_json(ipath)
    windows = data["windows"] if isinstance(data, dict) else data
    return list(windows), None


def sample_pool(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Seeded sample of SAMPLE_POOL windows (STANDARDS 10.7), returned sorted by id."""
    if len(entries) <= SAMPLE_POOL:
        return sorted(entries, key=lambda e: str(e["id"]))
    rng = np.random.default_rng(SEED)
    idx = sorted(rng.choice(len(entries), size=SAMPLE_POOL, replace=False).tolist())
    chosen = [entries[i] for i in idx]
    return sorted(chosen, key=lambda e: str(e["id"]))


def missions_limits(paths: Paths) -> tuple[dict[str, Any] | None, str | None]:
    """Limits per body from config/missions.json -> limits.

    Expected form: {"limits": {"moon": {"landing": {"limit_deg", "source"}, "driving": {...}}, "mars": {...}}}.
    Returns (limits, None), or (None, reason) when the file or the limits block is missing (no value is invented).
    """
    mpath = paths.config_dir / "missions.json"
    if not mpath.exists():
        return None, "config/missions.json not found"
    data = load_json(mpath)
    limits = data.get("limits")
    if not isinstance(limits, dict):
        return None, "config/missions.json has no 'limits' block"
    return limits, None


def limit_for(limits: dict[str, Any] | None, body: str, kind: str) -> tuple[float | None, str | None, str | None]:
    """(limit_deg, source_url, reason) for a body and kind ('landing' or 'driving'); None values when unknown."""
    if limits is None:
        return None, None, "limits missing"
    entry = (limits.get(body) or {}).get(kind) if isinstance(limits.get(body), dict) else None
    if not entry or entry.get("limit_deg") is None:
        return None, None, f"no {kind} limit for {body}"
    # missions.json stores the link as source_url (the older key "source" is still read if present)
    return float(entry["limit_deg"]), entry.get("source_url") or entry.get("source"), None


def provenance_block(paths: Paths, stage: str, inputs: list[tuple[str, Path]]) -> dict[str, Any]:
    """Provenance block (STANDARDS 7). Inputs are (source_id, existing file). Paths are stored repo-relative.

    Raises FileNotFoundError when an input file is missing (provenance must be exact).
    """
    cfg = paths.active_config
    items = [{"source_id": sid, "path": str(p)} for sid, p in inputs]
    block = prov.build_provenance(stage, cfg, items)
    for rec, (_, p) in zip(block["inputs"], inputs):
        rec["path"] = paths.rel(p)
    block["config_file"] = paths.rel(cfg)
    return block


def measure_raw(
    path: Path,
    lat: float,
    lon: float,
    body: str,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Load one raw DEM on the standard grid and compute the feature vector (STANDARDS sections 3 and 4).

    Validity (STANDARDS 3): L >= 2 * native_res_m and coverage >= min_coverage, else status 'skipped' with the reason
    and no features. A read or projection error gives status 'error' with the reason. Nothing is patched.
    Returns a dict with keys: status, reason, L, R, native_res_m, coverage, n_valid, crs_src, crs_dst, features.
    """
    grid_cfg = cfg["grid"]
    L = float(grid_cfg["L_m"])
    R = float(grid_cfg["R_m"])
    min_cov = float(grid_cfg["min_coverage"])
    min_ratio = float(grid_cfg["min_L_over_native"])
    out: dict[str, Any] = {
        "status": "error", "reason": None, "L": L, "R": R, "native_res_m": None, "coverage": None,
        "n_valid": None, "crs_src": None, "crs_dst": None, "features": None,
    }
    try:
        z, mask, meta = gridmod.load_local_grid(path, lat, lon, body, L, R)
    except Exception as exc:  # the pipeline logs the reason; core never swallows errors
        out["reason"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        return out
    out.update(
        native_res_m=meta["native_res_m"], coverage=meta["coverage"], crs_src=meta["crs_src"],
        crs_dst=meta["crs_dst"], n_valid=int(mask.sum()),
    )
    if L < min_ratio * float(meta["native_res_m"]):
        out.update(status="skipped", reason=f"L={L} m < {min_ratio} x native {meta['native_res_m']:.3f} m")
        return out
    if float(meta["coverage"]) < min_cov:
        out.update(status="skipped", reason=f"coverage {meta['coverage']:.4f} < {min_cov}")
        return out
    out["features"] = meas.features(z, mask, L, cfg)
    out["status"] = "ok"
    return out


def parse_args(description: str, extra: list[tuple[tuple[str, ...], dict[str, Any]]] | None = None) -> argparse.Namespace:
    """Common command line: --root, --sample, --ids (plus the extra arguments of one script)."""
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--root", default=None, help="project root (default: the repository root)")
    ap.add_argument("--sample", action="store_true", help="sample mode (STANDARDS 10.7): 2 targets, 3 regions, 50 pool windows")
    ap.add_argument("--ids", default=None, help="comma-separated ids to process (default: all in scope)")
    for names, kwargs in extra or []:
        ap.add_argument(*names, **kwargs)
    return ap.parse_args()


def ids_arg(args: argparse.Namespace) -> list[str] | None:
    """--ids as a list, or None."""
    if not args.ids:
        return None
    return [s.strip() for s in args.ids.split(",") if s.strip()]


def window_records(stage_dir: Path, kind: str | None = None, status: str | None = "ok") -> list[dict[str, Any]]:
    """Measure records (one JSON per window) in stage_dir, optionally filtered by kind and status."""
    out: list[dict[str, Any]] = []
    for p in sorted(stage_dir.glob("*.json")):
        rec = load_json(p)
        if kind is not None and rec.get("kind") != kind:
            continue
        if status is not None and rec.get("status") != status:
            continue
        out.append(rec)
    return out


def tie_groups(sorted_d: list[float], p95: float) -> list[int]:
    """Anchor rule: group index per analog for a list of D values sorted ascending.

    Formula: group g starts at item i when D_i - D_anchor >= p95 (anchor = first item of the group). Items in one
    group differ pairwise by less than p95.
    """
    out: list[int] = []
    group = -1
    anchor = None
    for d in sorted_d:
        if anchor is None or d - anchor >= p95:
            group += 1
            anchor = d
        out.append(group)
    return out


def refine_dir(paths: "Paths") -> Path:
    """data/derived/refine (or the sample folder in sample mode): the refined-search stage (STANDARDS 10.13)."""
    return paths.derived / "refine"


def ranking_file(paths: "Paths", tid: str) -> Path:
    """The ranking the site shows for a target: the refined one when refine_search has written it, else the frozen search
    output (data/derived/ranking). Each file keeps its own stage; this only chooses which one to read."""
    refined = refine_dir(paths) / f"{tid}.json"
    return refined if refined.exists() else paths.stage("ranking") / f"{tid}.json"


def place_id(window_id: str) -> str:
    """The Earth PLACE a window belongs to (counting rule, 2026-11-14). A refined window '<target>__pool__pool_N' is the
    pool window 'pool__pool_N' re-centred by a few km for one target: the same place. Any other id is its own place.
    Counts of discoveries are by place, so one place that is a twin of several sites or cells is counted once."""
    i = window_id.rfind("pool__pool_")
    return window_id[i:] if i >= 0 else window_id


def window_record_path(paths: "Paths", wid: str) -> Path:
    """Measure record of a window: a refined window (data/derived/refine/measure/<id>.json) when it exists, else the
    measure stage. Refined ids are unique per (target, candidate) pair."""
    refined = refine_dir(paths) / "measure" / f"{wid}.json"
    return refined if refined.exists() else paths.stage("measure") / f"{wid}.json"


NE_ADMIN1_SHP = Path("reference") / "ne_10m_admin_1" / "ne_10m_admin_1_states_provinces.shp"  # under data/raw/


def load_places(paths: Paths, log: RunLog) -> "PlaceIndex | None":
    """Natural Earth 1:10m admin-1 index (STANDARDS 10.12), or None with a logged warning when the file is absent."""
    shp = paths.raw_dir / NE_ADMIN1_SHP
    if not shp.exists():
        log.event("warn", "Natural Earth admin-1 file not found: analog_place will be null", path=paths.rel(shp))
        return None
    vfile = shp.with_suffix(".VERSION.txt")
    version = vfile.read_text(encoding="utf-8").strip() if vfile.exists() else "unknown"
    label = f"Natural Earth 1:10m admin-1 states/provinces v{version} (public domain), {shp.name}"
    index = load_admin1(shp, label)
    log.event("info", "admin-1 index loaded", polygons=len(index.polygons), source=label)
    return index


def analog_place(index: "PlaceIndex | None", lat: float, lon: float) -> dict[str, Any] | None:
    """analog_place of a window centre: {name, admin1, country, source, match, distance_km, nearest_named_feature}.
    null when there is no index or no polygon within 50 km. nearest_named_feature is not available offline here: null."""
    if index is None:
        return None
    rec = index.lookup(lat, lon)
    if rec is None:
        return None
    return {**rec, "nearest_named_feature": None}
