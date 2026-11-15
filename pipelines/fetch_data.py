"""Fetch and clip the raw inputs (thin pipeline; logic lives in src/analog/io/fetch.py).

Subcommands
  verify                      re-check each source in config/sources.json and write its 'verified' block
  fetch-site SITE [--with-toterr] [--with-roi]
                              download a planetary site's 5 m DEM (and uncertainty / ROI archive)
  stac-test                   10 km STAC windows from nasadem and cop-dem-glo-30 over the first dev Earth region
  centre SITE                 print the DEM-raster centre (and ROI-polygon centre if the ROI file is real)
  earth-clip [--regions A,B] [--sample N]
                              5 km NASADEM windows for every dev and reserved region, plus Copernicus GLO-30
                              for dev regions: data/raw/earth/<region_id>/{nasadem,copdem}.tif

Outputs: data/raw/<body>/<id>/<file>, data/raw/manifest.json (appended), data/raw/fetch_log.jsonl.
Config files are read and (for verify only) rewritten in config/.
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import tarfile
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analog.io import fetch  # noqa: E402
from analog.io.fetch import FetchError  # noqa: E402

CONFIG = ROOT / "config"
RAW = ROOT / "data" / "raw"
MANIFEST = RAW / "manifest.json"
LOG = RAW / "fetch_log.jsonl"
STAC_TEST_KM = 10.0


def load(name: str) -> dict[str, Any]:
    """Read a JSON config file from config/."""
    return json.loads((CONFIG / name).read_text(encoding="utf-8"))


def save(name: str, obj: dict[str, Any]) -> None:
    """Write a JSON config file atomically (only used by 'verify')."""
    tmp = CONFIG / (name + ".part")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, CONFIG / name)


def log(event: dict[str, Any]) -> None:
    """Append one JSON line to data/raw/fetch_log.jsonl and echo it."""
    event = {"time": fetch.utc_now(), **event}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    print(json.dumps(event, ensure_ascii=False))


def rel(path: Path) -> str:
    """Repo-relative POSIX path for manifest entries."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


def probe(url: str) -> tuple[int, str | None, int | None, bytes]:
    """Range GET of the first 4 KB. Returns (http_code, content_type, total_bytes, head).

    Only the first chunk is read and the connection is closed: no full download.
    """
    r = requests.get(
        url, headers={"User-Agent": fetch.USER_AGENT, "Range": "bytes=0-4095"},
        stream=True, timeout=120, allow_redirects=True,
    )
    try:
        head = next(r.iter_content(4096), b"")
        ctype = r.headers.get("Content-Type")
        cr = r.headers.get("Content-Range")
        total = int(cr.split("/")[-1]) if cr and cr.split("/")[-1].isdigit() else None
        if total is None and r.headers.get("Content-Length", "").isdigit():
            total = int(r.headers["Content-Length"])
        return r.status_code, ctype, total, head
    finally:
        r.close()


def verify_source(src: dict[str, Any]) -> dict[str, Any]:
    """Check one source and return its 'verified' block (STANDARDS section 8).

    Rule: STAC sources are verified by their collection JSON. Other sources by a
    range GET; the payload must match 'expect' (html = a page, None = any non-HTML).
    """
    now = fetch.utc_now()
    if src["access"] == "stac":
        url = f"{fetch.PC_STAC_URL}/collections/{src['url_or_collection']}"
        r = requests.get(url, headers={"User-Agent": fetch.USER_AGENT}, timeout=120)
        good = False
        if r.status_code == 200:
            try:
                good = r.json().get("id") == src["url_or_collection"]
            except ValueError:
                good = False
        return {"status": "ok" if good else "broken", "http_code": r.status_code,
                "bytes": len(r.content), "checked_utc": now}
    code, ctype, total, head = probe(src["url_or_collection"])
    kind = fetch.classify_head(head, ctype)
    expect = src.get("expect")
    if expect == "html":
        good = code == 200 and kind == "html"
    elif expect is None:
        good = code in (200, 206) and kind != "html"
    else:
        good = code in (200, 206) and fetch.check_payload(head, ctype, expect) is None
    return {"status": "ok" if good else "broken", "http_code": code, "bytes": total, "checked_utc": now}


def cmd_verify(args: argparse.Namespace) -> int:
    """Re-verify sources and rewrite their config/sources.json 'verified' blocks.

    Without --ids every source is checked; with --ids only the listed ids are
    checked and rewritten, the others are left as they are.
    """
    cfg = load("sources.json")
    wanted = set(args.ids.split(",")) if getattr(args, "ids", None) else None
    if wanted is not None:
        missing = wanted - {s["id"] for s in cfg["sources"]}
        if missing:
            print(f"ERROR unknown source ids: {sorted(missing)}")
            return 1
    for src in cfg["sources"]:
        if wanted is not None and src["id"] not in wanted:
            continue
        try:
            src["verified"] = verify_source(src)
        except requests.RequestException as exc:
            src["verified"] = {"status": "broken", "http_code": None, "bytes": None, "checked_utc": fetch.utc_now()}
            print(f"ERROR {src['id']}: {type(exc).__name__}: {exc}")
        v = src["verified"]
        print(f"{v['status']:7s} {v['http_code']} bytes={v['bytes']} {src['id']}")
    save("sources.json", cfg)
    return 0


def find_site(sites: list[dict[str, Any]], site_id: str) -> dict[str, Any]:
    """Return the entry with this id or raise FetchError."""
    for s in sites:
        if s["id"] == site_id:
            return s
    raise FetchError(f"site {site_id!r} not in config/sites.json or regions.json")


def fetch_file(source_id: str, body: str, folder: str) -> Path | None:
    """Download one source into data/raw/<body>/<folder>/<filename>; append to the manifest.

    Rule: an existing file already listed in the manifest is kept (not re-downloaded).
    A failure is logged with its reason and returns None (no silent fallback).
    """
    src = next((s for s in load("sources.json")["sources"] if s["id"] == source_id), None)
    if src is None:
        log({"event": "error", "source_id": source_id, "reason": "unknown source id"})
        return None
    if not src.get("filename"):
        log({"event": "error", "source_id": source_id, "reason": "no filename configured (checked only)"})
        return None
    if src.get("clip") == "window":
        log({"event": "error", "source_id": source_id,
             "reason": "windowed source: use 'window-clip', never a whole-file download"})
        return None
    dest = fetch.build_raw_path(RAW, body, folder, src["filename"])
    if dest.exists() and MANIFEST.exists() and any(e["path"] == rel(dest) for e in json.loads(MANIFEST.read_text(encoding="utf-8"))):
        log({"event": "skip_exists", "source_id": source_id, "path": rel(dest)})
        return dest
    expect = src.get("expect") if src.get("expect") in ("tiff", "zip", "gzip") else None
    try:
        rec = fetch.download(src["url_or_collection"], dest, expect=expect)
    except FetchError as exc:
        log({"event": "error", "source_id": source_id, "url": src["url_or_collection"], "reason": str(exc)})
        return None
    entry = {"path": rel(dest), "source_id": source_id, "url": src["url_or_collection"],
             "bytes": rec["bytes"], "sha256": rec["sha256"], "created": rec["created"]}
    fetch.append_manifest(MANIFEST, entry)
    log({"event": "downloaded", **entry})
    return dest


def cmd_fetch_site(args: argparse.Namespace) -> int:
    """Download a Moon/Mars site's DEM, and optionally its uncertainty and ROI archive."""
    site = find_site(load("sites.json")["sites"], args.site)
    dem_id = site["dem_source_id"]
    ids = [dem_id]
    if dem_id.endswith("_surf"):
        base = dem_id[: -len("_surf")]
        if args.with_toterr:
            ids.append(base + "_toterr")
        if args.with_roi:
            ids.append(base + "_rois")
    ok = True
    for sid in ids:
        ok = fetch_file(sid, site["body"], site["id"]) is not None and ok
    return 0 if ok else 1


def cmd_stac_test(_: argparse.Namespace) -> int:
    """Clip 10 km windows from nasadem and cop-dem-glo-30 over the first dev Earth region."""
    region = next(r for r in load("regions.json")["regions"] if r["role"] == "dev")
    jobs = [("nasadem", "nasadem", "elevation"), ("cop_dem_glo30", "cop-dem-glo-30", "data")]
    rc = 0
    for source_id, collection, asset in jobs:
        out = fetch.build_raw_path(RAW, "earth", region["id"], f"{source_id}_{int(STAC_TEST_KM)}km.tif")
        try:
            meta = fetch.stac_clip(collection, asset, region["lat"], region["lon"], STAC_TEST_KM, out)
        except FetchError as exc:
            log({"event": "error", "source_id": source_id, "region": region["id"], "reason": str(exc)})
            rc = 1
            continue
        entry = {"path": rel(out), "source_id": source_id, "url": f"{fetch.PC_STAC_URL}/collections/{collection}",
                 "bytes": meta["bytes"], "sha256": meta["sha256"], "created": meta["created"],
                 "items": meta["items"], "bounds_deg": meta["bounds_deg"],
                 "valid_fraction": meta["valid_fraction"], "native_res_deg": meta["native_res_deg"]}
        fetch.append_manifest(MANIFEST, entry)
        log({"event": "stac_clip", **entry})
    return rc


EARTH_HALF_WIDTH_KM = 5.0  # validation windows: 10 km across, the 8 km disk plus margin


def earth_jobs(region: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """(source_id, STAC collection, asset key, file name) per Earth validation region.

    Rule (PLAN v2 section 4 / task brief): dev regions get NASADEM and Copernicus
    GLO-30 (sensor noise, V1); reserved regions get NASADEM only.
    """
    jobs = [("nasadem", "nasadem", "elevation", "nasadem.tif")]
    if region["role"] == "dev":
        jobs.append(("cop_dem_glo30", "cop-dem-glo-30", "data", "copdem.tif"))
    return jobs


def cmd_earth_clip(args: argparse.Namespace) -> int:
    """Clip NASADEM (and Copernicus GLO-30 for dev regions) windows for validation regions.

    Output: data/raw/earth/<region_id>/{nasadem,copdem}.tif, half width 5 km. An existing
    file that is already in the manifest is kept (resumable).
    """
    regions = [r for r in load("regions.json")["regions"] if r["role"] in ("dev", "reserved", "holdout_v13")]
    if args.regions:
        wanted = set(args.regions.split(","))
        regions = [r for r in regions if r["id"] in wanted]
        missing = wanted - {r["id"] for r in regions}
        if missing:
            log({"event": "error", "reason": f"not dev/reserved/holdout_v13 regions: {sorted(missing)}"})
            return 1
    if args.sample:
        regions = [r for r in regions if r["role"] == "dev"][: args.sample]
    rc = 0
    for region in regions:
        for source_id, collection, asset, fname in earth_jobs(region):
            out = fetch.build_raw_path(RAW, "earth", region["id"], fname)
            entries = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else []
            if out.exists() and any(e["path"] == rel(out) for e in entries):
                log({"event": "skip_exists", "region": region["id"], "path": rel(out)})
                continue
            try:
                meta = fetch.stac_clip(collection, asset, region["lat"], region["lon"], EARTH_HALF_WIDTH_KM, out)
            except FetchError as exc:
                log({"event": "error", "region": region["id"], "source_id": source_id, "reason": str(exc)})
                rc = 1
                continue
            entry = {"path": rel(out), "source_id": source_id,
                     "url": f"{fetch.PC_STAC_URL}/collections/{collection}", "bytes": meta["bytes"],
                     "sha256": meta["sha256"], "created": meta["created"], "items": meta["items"],
                     "bounds_deg": meta["bounds_deg"], "valid_fraction": meta["valid_fraction"],
                     "native_res_deg": meta["native_res_deg"], "half_width_km": EARTH_HALF_WIDTH_KM,
                     "region": region["id"]}
            fetch.append_manifest(MANIFEST, entry)
            log({"event": "earth_clip", **entry})
    return rc


WINDOW_HALF_WIDTH_KM = 6.0  # planetary windows: 12 km across, the 4 km disk plus margin
DISK_RADIUS_M = 4000.0  # coverage rule is checked in this disk (STANDARDS 10.9 / task brief)
DISK_MIN_VALID = 0.90


def cmd_window_clip(args: argparse.Namespace) -> int:
    """Clip a remote window (half width 6 km, original CRS) of a planetary site's DEM.

    Source entries with "clip": "window" are read with HTTP range requests only
    (GDAL /vsicurl/); the whole file is never downloaded. Output:
    data/raw/<body>/<site>/<filename>. Rule: the valid fraction inside the 4 km disk
    must be >= 0.90; below that the file is removed and the reason is logged.
    An existing file already in the manifest is kept (resumable).
    """
    site = find_site(load("sites.json")["sites"], args.site)
    src = next((s for s in load("sources.json")["sources"] if s["id"] == site["dem_source_id"]), None)
    if src is None:
        log({"event": "error", "site": site["id"], "reason": f"unknown dem_source_id {site['dem_source_id']!r}"})
        return 1
    if src.get("clip") != "window" or not src.get("filename"):
        log({"event": "error", "site": site["id"], "source_id": src["id"],
             "reason": "source is not configured for a window clip (clip='window' and filename needed)"})
        return 1
    out = fetch.build_raw_path(RAW, site["body"], site["id"], src["filename"])
    entries = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else []
    if out.exists() and any(e["path"] == rel(out) for e in entries):
        log({"event": "skip_exists", "site": site["id"], "path": rel(out)})
        return 0
    try:
        meta = fetch.cog_window_clip(src["url_or_collection"], site["body"], site["lat"], site["lon"],
                                     WINDOW_HALF_WIDTH_KM, out)
    except FetchError as exc:
        log({"event": "error", "site": site["id"], "source_id": src["id"], "reason": str(exc)})
        return 1
    except Exception as exc:  # remote read failures from rasterio / pyproj: report, never patch
        log({"event": "error", "site": site["id"], "source_id": src["id"],
             "reason": f"remote window read failed: {type(exc).__name__}: {exc}"})
        return 1
    import rasterio

    with rasterio.open(out) as ds:
        z = ds.read(1).astype("float64")
    px_x, px_y = meta["px_m"]
    disk_frac = fetch.disk_valid_fraction(z, px_x, px_y, DISK_RADIUS_M)
    entry = {"path": rel(out), "source_id": src["id"], "url": src["url_or_collection"],
             "bytes": meta["bytes"], "sha256": meta["sha256"], "created": meta["created"],
             "window_half_width_km": WINDOW_HALF_WIDTH_KM, "centre_projected": meta["centre_projected"],
             "crs": meta["crs"], "px_m": meta["px_m"], "shape": meta["shape"],
             "valid_fraction_window": meta["valid_fraction"], "valid_fraction_disk_4km": disk_frac,
             "site": site["id"]}
    if disk_frac is None or disk_frac < DISK_MIN_VALID:
        out.unlink(missing_ok=True)
        log({"event": "window_rejected", **entry, "reason": f"disk valid {disk_frac} < {DISK_MIN_VALID}"})
        return 1
    fetch.append_manifest(MANIFEST, entry)
    log({"event": "window_clip", **entry})
    return 0


def shp_vertices(shp: Path) -> list[tuple[float, float]]:
    """Read x,y vertices of every record of a polygon/polyline/point shapefile (.shp).

    Format (ESRI shapefile spec): header 100 bytes, shape type int32 LE at 32;
    each record: 8-byte header (BE), then type int32 LE; polygon/polyline have
    box (4 doubles), numParts, numPoints, parts, points.
    """
    data = shp.read_bytes()
    if struct.unpack(">i", data[0:4])[0] != 9994:  # file code is big-endian
        raise FetchError(f"{shp.name} is not a shapefile")
    pts: list[tuple[float, float]] = []
    off = 100
    while off + 8 <= len(data):
        content_len = struct.unpack(">i", data[off + 4: off + 8])[0] * 2
        c = off + 8
        stype = struct.unpack("<i", data[c: c + 4])[0]
        if stype in (3, 5, 13, 15, 23, 25):  # polyline/polygon (+Z/M variants)
            # content: type(4) box(32) numParts(4) numPoints(4) parts(4*numParts) points(16*numPoints)
            nparts = struct.unpack("<i", data[c + 36: c + 40])[0]
            npts = struct.unpack("<i", data[c + 40: c + 44])[0]
            p0 = c + 44 + 4 * nparts
            for i in range(npts):
                x, y = struct.unpack("<dd", data[p0 + 16 * i: p0 + 16 * i + 16])
                pts.append((x, y))
        elif stype == 1:  # point
            x, y = struct.unpack("<dd", data[c + 4: c + 20])
            pts.append((x, y))
        off = c + content_len
    return pts


def roi_centre(tgz: Path, body: str) -> dict[str, Any] | None:
    """Centre (lat, lon) of the bounding box of all ROI vertices in a real .tgz archive.

    Rule: the archive must be gzip (checked by content). It is extracted into a new,
    empty directory next to it (untrusted data: the tar 'data' filter is used). The
    .prj decides the CRS: PROJCS is projected (read with pyproj), GEOGCS is taken as
    lon/lat degrees. Returns None with a logged reason when unusable.
    """
    from pyproj import CRS, Transformer

    head = tgz.read_bytes()[:4096]
    if fetch.classify_head(head, None) != "gzip":
        log({"event": "roi_skip", "path": rel(tgz), "reason": f"not a gzip archive ({fetch.classify_head(head, None)})"})
        return None
    out_dir = tgz.parent / "roi_extract"
    if out_dir.exists():
        log({"event": "roi_skip", "path": rel(tgz), "reason": f"{rel(out_dir)} already exists; delete it to re-extract"})
        return None
    out_dir.mkdir(parents=True)
    with tarfile.open(tgz, "r:gz") as tar:
        tar.extractall(out_dir, filter="data")
    shps = sorted(out_dir.rglob("*.shp"))
    if not shps:
        log({"event": "roi_skip", "path": rel(tgz), "reason": "no .shp inside archive"})
        return None
    pts = []
    try:
        for shp in shps:
            pts += shp_vertices(shp)
    except (FetchError, struct.error) as exc:
        log({"event": "roi_skip", "path": rel(tgz), "reason": f"shapefile read failed: {exc}"})
        return None
    if not pts:
        log({"event": "roi_skip", "path": rel(tgz), "reason": "no vertices read"})
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    prj = shps[0].with_suffix(".prj")
    wkt = prj.read_text(encoding="utf-8", errors="ignore") if prj.exists() else ""
    if "PROJCS" in wkt:
        tr = Transformer.from_crs(CRS.from_wkt(wkt), fetch.BODY_SPHERE_PROJ[body], always_xy=True)
        lon, lat = tr.transform(cx, cy)
    elif "GEOGCS" in wkt:
        lon, lat = cx, cy
    else:
        log({"event": "roi_skip", "path": rel(tgz), "reason": "no usable .prj"})
        return None
    lon = ((lon + 180.0) % 360.0) - 180.0
    return {"lat": round(lat, 4), "lon": round(lon, 4), "n_vertices": len(pts),
            "shapefiles": [p.name for p in shps], "crs": "PROJCS" if "PROJCS" in wkt else "GEOGCS"}


def cmd_centre(args: argparse.Namespace) -> int:
    """Print the DEM-raster centre and, when real, the ROI-polygon centre for a site."""
    import rasterio
    from pyproj import Transformer

    site = find_site(load("sites.json")["sites"], args.site)
    src = next(s for s in load("sources.json")["sources"] if s["id"] == site["dem_source_id"])
    dem = fetch.build_raw_path(RAW, site["body"], site["id"], src["filename"])
    if not dem.exists():
        log({"event": "error", "site": site["id"], "reason": f"DEM not downloaded: {rel(dem)}"})
        return 1
    with rasterio.open(dem) as ds:
        h, w = ds.height, ds.width
        x, y = ds.xy(h / 2.0, w / 2.0)
        tr = Transformer.from_crs(ds.crs, fetch.BODY_SPHERE_PROJ[site["body"]], always_xy=True)
        lon, lat = tr.transform(x, y)
        crs_text = ds.crs.to_string() if ds.crs else None
    lon = ((lon + 180.0) % 360.0) - 180.0
    result: dict[str, Any] = {"site": site["id"], "dem_centre": {"lat": round(lat, 4), "lon": round(lon, 4)},
                              "dem_crs": crs_text, "dem_shape": [h, w]}
    roi_src = src["id"].replace("_surf", "_rois")
    roi = next((s for s in load("sources.json")["sources"] if s["id"] == roi_src), None)
    if roi and roi.get("filename"):
        tgz = fetch.build_raw_path(RAW, site["body"], site["id"], roi["filename"])
        if tgz.exists():
            result["roi_centre"] = roi_centre(tgz, site["body"])
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", help="re-verify config/sources.json")
    v.add_argument("--ids", help="comma-separated source ids only (default: all)")
    v.set_defaults(func=cmd_verify)
    w = sub.add_parser("window-clip", help="6 km remote window of a planetary site's DEM (no full download)")
    w.add_argument("site")
    w.set_defaults(func=cmd_window_clip)
    f = sub.add_parser("fetch-site", help="download a planetary site's DEM")
    f.add_argument("site")
    f.add_argument("--with-toterr", action="store_true")
    f.add_argument("--with-roi", action="store_true")
    f.set_defaults(func=cmd_fetch_site)
    sub.add_parser("stac-test", help="10 km STAC test windows over the first dev region").set_defaults(func=cmd_stac_test)
    c = sub.add_parser("centre", help="print a downloaded site's centre")
    c.add_argument("site")
    c.set_defaults(func=cmd_centre)
    e = sub.add_parser("earth-clip", help="5 km NASADEM / Copernicus windows for validation regions")
    e.add_argument("--regions", help="comma-separated region ids (default: all dev and reserved)")
    e.add_argument("--sample", type=int, help="only the first N dev regions")
    e.set_defaults(func=cmd_earth_clip)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
