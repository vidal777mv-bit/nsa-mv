"""Overall tilt and downhill direction of every terrain disk -> site/data/tilt.json.

Reading follows site/js/data.js (loadTerrain) and site/js/terrain.js:
- height.bin: n*n float32, little-endian, row-major, row 0 = north.
- Pixel (i, j): x = (j - c) L metres (east), y = (c - i) L metres (north), c = (n - 1) / 2.
- Valid = finite height inside the disk hypot(x, y) <= R (NaN outside the disk).

Model: least-squares plane z = a x + b y + c over valid pixels.
tilt_deg = degrees(atan(hypot(a, b))).
downhill azimuth = direction of (-a, -b), clockwise from north (0 = N, 90 = E).

Usage: python tools/export_tilt.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TERRAIN_DIR = ROOT / "site" / "data" / "terrain"
OUT_PATH = ROOT / "site" / "data" / "tilt.json"

ROSE = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
METHOD = ("least-squares plane over valid disk pixels; x east, y north; "
          "downhill azimuth clockwise from north")


def rose_point(azimuth_deg: float) -> str:
    return ROSE[int(round(azimuth_deg / 45.0)) % 8]


def load_height(path: Path, n: int) -> np.ndarray:
    raw = path.read_bytes()
    if len(raw) != n * n * 4:
        raise ValueError(f"{path}: wrong size ({len(raw)} bytes, expected {n * n * 4})")
    return np.frombuffer(raw, dtype="<f4").reshape(n, n).astype(np.float64)


def disk_coordinates(n: int, L: float) -> tuple[np.ndarray, np.ndarray]:
    c = (n - 1) / 2.0
    rows, cols = np.mgrid[0:n, 0:n]
    x = (cols - c) * L   # east
    y = (c - rows) * L   # north (row 0 = north)
    return x, y


def fit_plane(height: np.ndarray, L: float, R: float) -> tuple[float, float, float, int]:
    """Least-squares z = a x + b y + c over valid disk pixels. Returns (a, b, rms_residual, n_pixels)."""
    n = height.shape[0]
    x, y = disk_coordinates(n, L)
    valid = (np.hypot(x, y) <= R) & np.isfinite(height)
    xv, yv, zv = x[valid], y[valid], height[valid]
    if zv.size < 3:
        raise ValueError("fewer than 3 valid pixels")
    A = np.column_stack([xv, yv, np.ones_like(xv)])
    coef, *_ = np.linalg.lstsq(A, zv, rcond=None)
    a, b = float(coef[0]), float(coef[1])
    rms = float(np.sqrt(np.mean((zv - A @ coef) ** 2)))
    return a, b, rms, int(zv.size)


def tilt_fields(a: float, b: float, rms: float, n_pixels: int) -> dict:
    """Converts plane slopes into the tilt.json fields. Flat ground has no downhill direction (null)."""
    grad = math.hypot(a, b)
    tilt_r = round(math.degrees(math.atan(grad)), 2)
    if grad < 1e-12:
        az, point = None, None
    else:
        # downhill = (-a, -b) in (east, north); azimuth clockwise from north = atan2(east, north)
        az = round(math.degrees(math.atan2(-a, -b)) % 360.0, 1) % 360.0
        point = rose_point(az)
    return {
        "tilt_deg": tilt_r,
        "downhill_azimuth_deg": az,
        "downhill": point,
        "rms_residual_m": round(rms, 3),
        "n_pixels": n_pixels,
    }


def terrain_tilt(terrain_dir: Path) -> dict:
    meta = json.loads((terrain_dir / "meta.json").read_text(encoding="utf-8"))
    n = int(meta["n"])
    height = load_height(terrain_dir / "height.bin", n)
    return tilt_fields(*fit_plane(height, float(meta["L"]), float(meta["R"])))


def main() -> int:
    terrains = {}
    skipped = []
    for d in sorted(p for p in TERRAIN_DIR.iterdir() if p.is_dir()):
        if not ((d / "height.bin").exists() and (d / "meta.json").exists()):
            skipped.append(d.name)
            continue
        terrains[d.name] = terrain_tilt(d)
    out = {
        "generated_by": "tools/export_tilt.py",
        "method": METHOD,
        "terrains": terrains,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(terrains)} terrains -> {OUT_PATH}")
    if skipped:
        print(f"skipped (missing height.bin or meta.json): {skipped}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
