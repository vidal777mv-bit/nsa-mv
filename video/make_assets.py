"""Assets for the landing scene, from the published terrain only (site/data/terrain).
ground.png: Jezero relief (NASA MRO CTX DTM via USGS), bilinear x4, hillshade az 315 alt 45, Mars ochre tint.
steep.png: coral where the slope over ~100 m (3 cells of 30 m) exceeds the 15 deg Mars landing limit; transparent elsewhere.
tagant.png: same shading for Tagant, Mauritania (NASADEM), sage tint.
Prints the share of the disk within the limit, to compare with the card (99.5% at the 100 m baseline)."""
import json, math, struct, sys, zlib
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1] / "site" / "data" / "terrain"
OUT = Path(__file__).resolve().parent / "assets"

def load(tid):
    m = json.loads((ROOT / tid / "meta.json").read_text(encoding="utf-8"))
    n = m["n"]; z = np.fromfile(ROOT / tid / "height.bin", "<f4").reshape(n, n).astype(float)
    return m, z

def png(path, rgba):
    h, w, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[i].astype(np.uint8).tobytes() for i in range(h))
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))

def upsample(z, k):
    n = z.shape[0]; src = np.linspace(0, n - 1, n * k)
    i0 = np.floor(src).astype(int); i1 = np.minimum(i0 + 1, n - 1); f = src - i0
    a = z[i0][:, :]; b = z[i1][:, :]; r = a * (1 - f)[:, None] + b * f[:, None]
    c = r[:, i0]; d = r[:, i1]; return c * (1 - f)[None, :] + d * f[None, :]

def shade(z, L, tint, exag=2.0):
    zz = np.where(np.isfinite(z), z, np.nanmean(z)) * exag
    gy, gx = np.gradient(zz, L)
    slope = np.arctan(np.hypot(gx, gy)); aspect = np.arctan2(-gx, gy)
    az, alt = math.radians(315), math.radians(45)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    hs = np.clip(0.25 + 0.85 * hs, 0, 1)
    rgb = np.stack([hs * tint[0], hs * tint[1], hs * tint[2]], -1)
    return rgb

def disk_alpha(n, soft=6):
    c = (n - 1) / 2; i, j = np.mgrid[0:n, 0:n]; r = np.hypot(i - c, j - c) / c
    return np.clip((1 - r) * n / (2 * soft), 0, 1)

k = 4
for tid, tint, name in [("jezero", (232, 150, 100), "ground.png"), ("jezero__pool__pool_00226", (170, 196, 150), "tagant.png")]:
    m, z = load(tid)
    zu = upsample(z, k); L = m["L"] / k
    rgb = shade(zu, L, tint)
    a = disk_alpha(zu.shape[0]) * np.isfinite(zu)
    png(OUT / name, np.dstack([rgb, a * 255]))
    if tid == "jezero":
        zf = np.where(np.isfinite(z), z, np.nan)
        step = 3  # 3 x 30 m ~ 100 m baseline
        gx = (np.roll(zf, -1, 1) - np.roll(zf, 1, 1))
        gy = (np.roll(zf, -1, 0) - np.roll(zf, 1, 0))
        # central difference over 2 cells (60 m) and over 2*step cells (180 m) bracket the 100 m baseline
        s60 = np.degrees(np.arctan(np.hypot(gx, gy) / (2 * m["L"])))
        gx3 = (np.roll(zf, -step, 1) - np.roll(zf, step, 1)) / (2 * step * m["L"])
        gy3 = (np.roll(zf, -step, 0) - np.roll(zf, step, 0)) / (2 * step * m["L"])
        s180 = np.degrees(np.arctan(np.hypot(gx3, gy3)))
        n = z.shape[0]; c = (n - 1) / 2; i, j = np.mgrid[0:n, 0:n]
        inner = (np.hypot(i - c, j - c) * m["L"] <= m["R"] - 3 * step * m["L"]) & np.isfinite(s60) & np.isfinite(s180)
        for lab, s in (("60 m", s60), ("180 m", s180)):
            print(f"Jezero share within 15 deg ({lab} baseline): {100 * np.mean(s[inner] <= 15):.2f}%")
        steep = upsample(np.where(np.isfinite(s60), s60, 0), k) > 15
        rgba = np.zeros(steep.shape + (4,)); rgba[steep] = (255, 120, 90, 210)
        png(OUT / "steep.png", rgba)
print("ok", sorted(p.name for p in OUT.glob("*.png")))
