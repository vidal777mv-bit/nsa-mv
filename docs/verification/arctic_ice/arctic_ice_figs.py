"""Arctic ice check, step 3: hillshade contact sheets (PNG written with zlib only, no image library installed).

- closing_contact.png: the 39 closing windows (Copernicus GLO-30 clips), each 200 x 200 hillshade,
  label = arctic_id and class/share70; border colour = class (ROCK brown, MIXED ochre, ICE blue).
- pool_contact.png: 12 pool windows (NASADEM clips) drawn with seed 20261114, same rendering, as reference.
Hillshade: light azimuth 315, altitude 45 (config/measure.json visual block), computed on the native grid with
cell size from the raster transform (geographic CRS converted to metres at the window latitude).
"""
from __future__ import annotations

import json
import math
import struct
import sys
import zlib
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path("C:/SpaceApps2026_Hackathon")
RAW = ROOT / "data/raw/earth/arctic_probe"
POOL = ROOT / "data/raw/earth/pool"
OUT = ROOT / "docs/verification/arctic_ice"
SCRP = Path(__file__).resolve().parent / "_scratch"
THUMB = 200
AZ, ALT = 315.0, 45.0
COL = {"ROCK": (150, 90, 40), "MIXED": (210, 170, 40), "ICE": (60, 120, 210)}

GLYPHS = {
    "0": [" ### ", "#   #", "#  ##", "# # #", "##  #", "#   #", " ### "],
    "1": ["  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    "2": [" ### ", "#   #", "    #", "   # ", "  #  ", " #   ", "#####"],
    "3": ["#####", "   # ", "  #  ", "   # ", "    #", "#   #", " ### "],
    "4": ["   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "],
    "5": ["#####", "#    ", "#### ", "    #", "    #", "#   #", " ### "],
    "6": ["  ## ", " #   ", "#    ", "#### ", "#   #", "#   #", " ### "],
    "7": ["#####", "    #", "   # ", "  #  ", " #   ", " #   ", " #   "],
    "8": [" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "],
    "9": [" ### ", "#   #", "#   #", " ####", "    #", "   # ", " ##  "],
    "A": [" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    "C": [" ### ", "#   #", "#    ", "#    ", "#    ", "#   #", " ### "],
    "D": ["#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "],
    "E": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"],
    "I": [" ### ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    "K": ["#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"],
    "M": ["#   #", "## ##", "# # #", "# # #", "#   #", "#   #", "#   #"],
    "O": [" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "R": ["#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"],
    "X": ["#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"],
    "P": ["#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "],
    "L": ["#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"],
    "_": ["     ", "     ", "     ", "     ", "     ", "     ", "#####"],
    ".": ["     ", "     ", "     ", "     ", "     ", "  ## ", "  ## "],
    " ": ["     "] * 7,
}


def draw_text(img: np.ndarray, x: int, y: int, text: str, scale: int = 2) -> None:
    cx = x
    for ch in text:
        g = GLYPHS[ch]
        for r, row in enumerate(g):
            for c, px in enumerate(row):
                if px == "#":
                    img[y + r * scale:y + (r + 1) * scale, cx + c * scale:cx + (c + 1) * scale] = 255
        cx += (5 + 1) * scale


def write_png(path: Path, rgb: np.ndarray) -> None:
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[r].tobytes() for r in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    path.write_bytes(png)


def hillshade_thumb(tif: Path, lat: float) -> tuple[np.ndarray, dict]:
    with rasterio.open(tif) as ds:
        z = ds.read(1).astype(float)
        nodata = ds.nodata
        geographic = ds.crs is not None and ds.crs.is_geographic
        rx, ry = abs(ds.res[0]), abs(ds.res[1])
        info = {"shape": list(z.shape), "crs": str(ds.crs), "nodata": nodata}
    if geographic:
        dy_m = ry * 111320.0
        dx_m = rx * 111320.0 * math.cos(math.radians(lat))
    else:
        dx_m, dy_m = rx, ry
    bad = ~np.isfinite(z) | (z < -1000)
    if nodata is not None:
        bad |= z == nodata
    good = z[~bad]
    fill = float(np.median(good)) if good.size else 0.0
    z[bad] = fill
    info["invalid_frac"] = round(float(bad.mean()), 4)
    info["relief_m_p5_p95"] = [round(float(np.percentile(good, 5)), 1), round(float(np.percentile(good, 95)), 1)] if good.size else None
    gr, gc = np.gradient(z, dy_m, dx_m)
    dz_dn = -gr  # rows increase southwards
    dz_de = gc
    nx, ny, nz = -dz_de, -dz_dn, np.ones_like(z)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    az = math.radians(AZ)
    alt = math.radians(ALT)
    lx, ly, lz = math.sin(az) * math.cos(alt), math.cos(az) * math.cos(alt), math.sin(alt)
    shade = np.clip((nx * lx + ny * ly + nz * lz) / norm, 0, 1)
    h, w = shade.shape
    ri = np.linspace(0, h - 1, THUMB).round().astype(int)
    ci = np.linspace(0, w - 1, THUMB).round().astype(int)
    small = shade[np.ix_(ri, ci)]
    return (small * 255).astype(np.uint8), info


def contact(items: list[dict], ncols: int, path: Path, tiles: list[Path]) -> dict:
    band = 48
    cell_w = THUMB + 8
    cell_h = THUMB + band + 8
    nrows = math.ceil(len(items) / ncols)
    W = ncols * cell_w + 8
    H = nrows * cell_h + 8
    gray = np.full((H, W), 24, dtype=np.uint8)
    infos = {}
    for k, (it, tif) in enumerate(zip(items, tiles)):
        r, c = divmod(k, ncols)
        x0 = 8 + c * cell_w
        y0 = 8 + r * cell_h
        shade, info = hillshade_thumb(tif, it["lat"])
        infos[it["label_id"]] = info
        gray[y0 + 4:y0 + 4 + THUMB, x0 + 4:x0 + 4 + THUMB] = shade
        draw_text(gray, x0 + 6, y0 + THUMB + 12, it["label_id"], 2)
        draw_text(gray, x0 + 6, y0 + THUMB + 30, f"{it['class']} {it['s70']:.2f}", 2)
    rgb = np.stack([gray, gray, gray], axis=2)
    for k, it in enumerate(items):
        r, c = divmod(k, ncols)
        x0 = 8 + c * cell_w
        y0 = 8 + r * cell_h
        col = COL[it["class"]]
        h_, w_ = THUMB + band, THUMB + 8
        rgb[y0:y0 + 4, x0:x0 + w_] = col
        rgb[y0 + h_ + 4 - 4:y0 + h_ + 4, x0:x0 + w_] = col
        rgb[y0:y0 + h_ + 4, x0:x0 + 4] = col
        rgb[y0:y0 + h_ + 4, x0 + w_ - 4:x0 + w_] = col
    write_png(path, rgb)
    return infos


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cls = json.loads((SCRP / "classes.json").read_text(encoding="utf-8"))
    closure = json.loads((OUT / "arctic_ice.json").read_text(encoding="utf-8"))
    W = cls["windows"]
    cl_items = []
    for row in closure["closing_39_table"]:
        cl_items.append({"label_id": row["arctic_id"].upper(), "lat": row["lat"], "class": row["class"],
                         "s70": row["s70"]})
    # sort-order of the table is by share70; keep it
    cl_tifs = [RAW / f"{row['arctic_id']}.tif" for row in closure["closing_39_table"]]
    for it, tif in zip(cl_items, cl_tifs):
        assert tif.exists(), tif
    info_cl = contact(cl_items, 8, OUT / "closing_contact.png", cl_tifs)

    pool_ids = cls["pool_ref_ids"]
    pool_idx = {p["id"]: p for p in json.loads((POOL / "index.json").read_text(encoding="utf-8"))}
    pl_items, pl_tifs = [], []
    for pid in pool_ids:
        pw = cls["pool_ref"][pid]
        s70 = pw["c70"]
        pl_items.append({"label_id": pid.upper(), "lat": pw["lat"], "class": klass(s70), "s70": s70})
        pl_tifs.append(ROOT / pool_idx[pid]["path"])
    for tif in pl_tifs:
        assert tif.exists(), tif
    info_pl = contact(pl_items, 6, OUT / "pool_contact.png", pl_tifs)

    print(json.dumps({"closing_items": len(cl_items), "pool_items": len(pl_items),
                      "closing_first": info_cl[cl_items[0]["label_id"]],
                      "pool_first": info_pl[pl_items[0]["label_id"]]}, indent=1))
    (SCRP / "figs_info.json").write_text(json.dumps({"closing": info_cl, "pool": info_pl}, indent=1), encoding="utf-8")
    return 0


def klass(s70: float) -> str:
    if s70 < 0.2:
        return "ROCK"
    if s70 < 0.5:
        return "MIXED"
    return "ICE"


if __name__ == "__main__":
    sys.exit(main())
