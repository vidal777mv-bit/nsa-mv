"""Visual terrain contract (STANDARDS.md section 10.6): hillshade, layers, 30 m export helpers, rotation alignment.

Pure numpy/scipy plus a hand-written PNG encoder (zlib + struct). No file or network I/O: the pipeline writes the
bytes. Conventions: z is a 2-D float array in metres, north-up (row 0 = north), square pixels of side L metres,
centre pixel = site (STANDARDS section 3). Coordinates: x east, y north, metres; pixel (i, j) has
x = (j - n//2) L and y = (n//2 - i) L.

Layer bits (uint8, STANDARDS 10.6):
    bit 0 (1): slope > landing limit      bit 1 (2): slope > driving limit
    bit 2 (4): ridge (TPI > +t)           bit 3 (8): valley (TPI < -t)
"""

from __future__ import annotations

import math
import struct
import zlib

import numpy as np
from scipy import ndimage

from analog.core import metrics
from analog.core.mission import slope_map_deg

HILLSHADE_AZIMUTH_DEG = 315.0
HILLSHADE_ALTITUDE_DEG = 45.0
BIT_LANDING = 1
BIT_DRIVING = 2
BIT_RIDGE = 4
BIT_VALLEY = 8
ROTATION_STEP_DEG = 10
ROTATION_INNER_FRAC = 0.9
VE_WIDTH_FRACTION = 0.2
VE_FLOOR_STEP = 0.1


def grid_size(R: float, L: float) -> int:
    """Side of the standard grid in pixels.

    Formula: n = 2 * ceil(R / L) + 1 (STANDARDS section 3). For R = 4000 m and L = 30 m: n = 269.
    """
    return 2 * math.ceil(float(R) / float(L)) + 1


def valid_mask(z: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Valid pixels: mask and finite elevation.

    Formula: valid = M and isfinite(z).
    """
    return np.asarray(mask, dtype=bool) & np.isfinite(z)


def relative_height(z: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Heights relative to the disk mean; NaN outside the valid disk.

    Formula: h = z - mean(z over valid pixels), on valid pixels; NaN elsewhere. The mean over the disk of h is 0.
    Raises ValueError when there is no valid pixel.
    """
    valid = valid_mask(z, mask)
    if not valid.any():
        raise ValueError("no valid pixel in the disk")
    mean = float(np.mean(z[valid]))
    out = np.full(z.shape, np.nan, dtype=float)
    out[valid] = z[valid] - mean
    return out


def relief_m(height: np.ndarray) -> float:
    """Display relief of a terrain: P99 - P1 of its valid heights, in metres.

    Formula: P99(h) - P1(h) over finite h. Used only for the vertical exaggeration rule.
    Raises ValueError when no height is finite.
    """
    vals = height[np.isfinite(height)]
    if vals.size == 0:
        raise ValueError("no finite height")
    p1, p99 = np.percentile(vals, [1, 99])
    return float(p99 - p1)


VE_MIN, VE_MAX = 1.0, 10.0  # STANDARDS 10.12 clamp of the per-pair exaggeration


def pair_exaggeration(relief_a_m: float, relief_b_m: float, R: float, width_fraction: float = VE_WIDTH_FRACTION) -> float:
    """Vertical exaggeration of one target-analog pair (STANDARDS 10.12).

    Formula: VE = floor_0.1( width_fraction * 2R / max(relief_a, relief_b) ), clamped to [1, 10]. The same value is
    applied to both terrains of the pair. relief = P99 - P1 of the 30 m height grid (relief_m).
    Raises ValueError for a non-positive relief.
    """
    max_rel = max(float(relief_a_m), float(relief_b_m))
    if not max_rel > 0:
        raise ValueError("pair relief must be positive")
    ve = math.floor(width_fraction * 2.0 * float(R) / max_rel / VE_FLOOR_STEP) * VE_FLOOR_STEP
    return float(min(VE_MAX, max(VE_MIN, round(ve, 10))))


def vertical_exaggeration(reliefs_m: list[float], R: float, width_fraction: float = VE_WIDTH_FRACTION) -> float:
    """One global vertical exaggeration for a whole site (rule documented in site/data/viz.json).

    Rule: the roughest terrain (largest relief over the set) must be displayed with a relief equal to
    ``width_fraction`` of the disk diameter 2R. VE = width_fraction * 2R / max(relief), rounded DOWN to 0.1 so that
    the rule is never exceeded. Example: relief 400 m, R = 4000 m, fraction 0.2 -> VE = 4.0.
    Raises ValueError for an empty set or a non-positive relief.
    """
    if not reliefs_m:
        raise ValueError("no terrain relief given")
    max_rel = float(max(reliefs_m))
    if not max_rel > 0:
        raise ValueError("roughest relief must be positive")
    ve = width_fraction * 2.0 * float(R) / max_rel
    return math.floor(ve / VE_FLOOR_STEP) * VE_FLOOR_STEP


def hillshade(
    z: np.ndarray,
    mask: np.ndarray,
    L: float,
    azimuth_deg: float = HILLSHADE_AZIMUTH_DEG,
    altitude_deg: float = HILLSHADE_ALTITUDE_DEG,
    vertical_exaggeration: float = 1.0,
) -> np.ndarray:
    """Lambertian hillshade in grey levels 0-255 (float), NaN where the gradient is undefined.

    Formula: surface normal n = (-zE, -zN, 1) / sqrt(zE^2 + zN^2 + 1), with zE = dz/dx = gx (columns increase east)
    and zN = dz/dy = -gy (rows increase south), where gy, gx = np.gradient(z_ve, L) and z_ve = VE * z.
    Light vector l = (cos(alt) sin(az), cos(alt) cos(az), sin(alt)), azimuth clockwise from north.
    shade = 255 * clip(n . l, 0, 1).
    Flat ground: shade = 255 sin(altitude) = 255 sin(45 deg) = 180.31 for the defaults (closed form).
    Pixels outside the valid disk, or next to an invalid pixel, are NaN.
    """
    valid = valid_mask(z, mask)
    zf = np.where(valid, np.asarray(z, dtype=float) * float(vertical_exaggeration), np.nan)
    gy, gx = np.gradient(zf, float(L))
    zE = gx
    zN = -gy
    az = math.radians(azimuth_deg)
    alt = math.radians(altitude_deg)
    lx = math.cos(alt) * math.sin(az)
    ly = math.cos(alt) * math.cos(az)
    lz = math.sin(alt)
    norm = np.sqrt(zE * zE + zN * zN + 1.0)
    with np.errstate(invalid="ignore"):
        shade = np.clip((-zE * lx - zN * ly + lz) / norm, 0.0, 1.0) * 255.0
    shade[~np.isfinite(shade)] = np.nan
    return shade


def to_uint8(img: np.ndarray, fill: int = 0) -> np.ndarray:
    """Round a float grey image to uint8; NaN becomes ``fill``.

    Formula: round(clip(v, 0, 255)); NaN -> fill.
    """
    out = np.where(np.isfinite(img), np.rint(np.clip(np.nan_to_num(img), 0, 255)), fill)
    return out.astype(np.uint8)


def encode_png_gray(img: np.ndarray) -> bytes:
    """8-bit greyscale PNG (colour type 0, filter 0, no interlace) written with zlib and struct.

    Formula: PNG = signature + IHDR(width, height, bit depth 8, colour 0) + IDAT(zlib(rows, each prefixed by a
    filter byte 0)) + IEND; every chunk carries its CRC-32. Raises ValueError for a non-2-D or non-uint8 array.
    """
    arr = np.asarray(img)
    if arr.ndim != 2 or arr.dtype != np.uint8:
        raise ValueError("encode_png_gray needs a 2-D uint8 array")
    h, w = arr.shape
    raw = b"".join(b"\x00" + arr[r].tobytes() for r in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def ridge_valley_maps(
    z: np.ndarray, mask: np.ndarray, L: float, radius_px: int, threshold_deg: float
) -> tuple[np.ndarray, np.ndarray]:
    """Boolean ridge and valley maps on the grid of z.

    Formula (metrics.tpi): TPI = z - mean(z over 0 < d <= r_px). t = tan(threshold_deg) * r_px * L.
    ridge = valid TPI and TPI > +t; valley = valid TPI and TPI < -t.
    """
    values, full = metrics.tpi(z, mask, int(radius_px))
    t = math.tan(math.radians(float(threshold_deg))) * int(radius_px) * float(L)
    with np.errstate(invalid="ignore"):
        ridge = full & (values > t)
        valley = full & (values < -t)
    return ridge, valley


def bits_100m(
    z: np.ndarray,
    mask: np.ndarray,
    L: float,
    tpi_radius_px: int,
    tpi_threshold_deg: float,
    landing_limit_deg: float | None,
    driving_limit_deg: float | None,
) -> np.ndarray:
    """Layer bits on the 100 m grid (uint8). Slope and TPI are measured here, before any upsampling.

    Formula per pixel: bit0 = slope > landing limit; bit1 = slope > driving limit; bit2 = ridge; bit3 = valley.
    An undefined slope or TPI sets no bit (the pixel is not measured, so it is not flagged).
    Raises ValueError when a limit is None: the caller decides what to write (no silent stand-in limit).
    """
    if landing_limit_deg is None or driving_limit_deg is None:
        raise ValueError("landing and driving limits are required for the layers")
    slope = slope_map_deg(z, mask, L)
    ridge, valley = ridge_valley_maps(z, mask, L, tpi_radius_px, tpi_threshold_deg)
    with np.errstate(invalid="ignore"):
        landing = slope > float(landing_limit_deg)
        driving = slope > float(driving_limit_deg)
    bits = np.zeros(z.shape, dtype=np.uint8)
    bits |= np.where(landing, BIT_LANDING, 0).astype(np.uint8)
    bits |= np.where(driving, BIT_DRIVING, 0).astype(np.uint8)
    bits |= np.where(ridge, BIT_RIDGE, 0).astype(np.uint8)
    bits |= np.where(valley, BIT_VALLEY, 0).astype(np.uint8)
    return bits


def nearest_upsample(a: np.ndarray, L_src: float, L_dst: float, n_dst: int) -> np.ndarray:
    """Nearest-neighbour resampling of a centred square grid onto a finer or coarser centred grid.

    Formula: destination pixel (i, j) has x = (j - n_dst//2) L_dst and y = (n_dst//2 - i) L_dst. Its source pixel is
    row = n_src//2 - floor(y / L_src + 1/2), col = n_src//2 + floor(x / L_src + 1/2), clipped to the source array.
    Both grids share the site as the centre pixel, so the centre maps to the centre.
    """
    n_src = a.shape[0]
    half_s = n_src // 2
    half_d = n_dst // 2
    idx = np.arange(n_dst)
    x = (idx - half_d) * float(L_dst)
    y = (half_d - idx) * float(L_dst)
    cols = np.clip(half_s + np.floor(x / float(L_src) + 0.5).astype(int), 0, n_src - 1)
    rows = np.clip(half_s - np.floor(y / float(L_src) + 0.5).astype(int), 0, n_src - 1)
    return a[np.ix_(rows, cols)]


def rotate_samples(z: np.ndarray, L: float, theta_deg: float, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Bilinear samples of z at the points Rot(-theta) (x, y), and the fraction of valid neighbours there.

    Formula: q = Rot(-theta) p, Rot(a) = [[cos a, -sin a], [sin a, cos a]] in (east, north) coordinates.
    The image rotated counter-clockwise by theta is rotated(p) = z(Rot(-theta) p). Returns (values, valid_fraction)
    with values taken from z with NaN replaced by 0; valid_fraction is 1 where all four neighbours are valid.
    """
    n = z.shape[0]
    half = n // 2
    t = math.radians(-float(theta_deg))
    qx = math.cos(t) * x - math.sin(t) * y
    qy = math.sin(t) * x + math.cos(t) * y
    ci = qx / float(L) + half
    ri = half - qy / float(L)
    valid = np.isfinite(z).astype(float)
    z0 = np.where(np.isfinite(z), z, 0.0)
    vals = ndimage.map_coordinates(z0, [ri, ci], order=1, mode="constant", cval=0.0)
    vfrac = ndimage.map_coordinates(valid, [ri, ci], order=1, mode="constant", cval=0.0)
    return vals, vfrac


def rotation_alignment(
    z_target: np.ndarray,
    mask_target: np.ndarray,
    z_analog: np.ndarray,
    mask_analog: np.ndarray,
    L: float,
    R: float,
    inner_frac: float = ROTATION_INNER_FRAC,
    step_deg: float = ROTATION_STEP_DEG,
) -> dict[str, object]:
    """Display rotation of the analog that best matches the target (STANDARDS 10.6).

    Convention: rotation_deg = theta means "the analog, displayed rotated counter-clockwise by theta on a north-up
    map, best matches the target". Search over theta = 0, step, ..., 360 - step.
    Formula per theta: on the inner disk (r <= inner_frac R) where both are valid, standardise the target heights
    and the rotated analog heights (z - mean) / std (each over the common set), then
    rms(theta) = sqrt(mean((zt - zr)^2)). rotation_deg = argmin rms (ties: the smallest angle).
    Features are rotation-invariant (tested in tests/test_metrics.py), so this changes only the display.
    Returns {rotation_deg, rms, n_common, rms_by_angle}. rotation_deg None when no angle has >= 100 common pixels.
    Closed-form check: analog(q) = g(Rot(40) q) gives rotation_deg = 40.
    """
    n = z_target.shape[0]
    half = n // 2
    rows, cols = np.mgrid[0:n, 0:n]
    x = (cols - half) * float(L)
    y = (half - rows) * float(L)
    inner = np.hypot(x, y) <= inner_frac * float(R)
    vt = inner & valid_mask(z_target, mask_target)
    if not vt.any():
        raise ValueError("no valid target pixel in the inner disk")
    xt = x[vt]
    yt = y[vt]
    zt_raw = z_target[vt]
    rms_by_angle: dict[float, float | None] = {}
    best: tuple[float, float, int] | None = None
    for theta in np.arange(0.0, 360.0, float(step_deg)):
        samp, vfrac = rotate_samples(z_analog, L, float(theta), xt, yt)
        ok = vfrac >= 0.999
        n_common = int(ok.sum())
        if n_common < 100:
            rms_by_angle[float(theta)] = None
            continue
        a = zt_raw[ok]
        b = samp[ok]
        a = (a - a.mean()) / (a.std() or 1.0)
        b = (b - b.mean()) / (b.std() or 1.0)
        rms = float(math.sqrt(np.mean((a - b) ** 2)))
        rms_by_angle[float(theta)] = rms
        if best is None or rms < best[0]:
            best = (rms, float(theta), n_common)
    if best is None:
        return {"rotation_deg": None, "rms": None, "n_common": 0, "rms_by_angle": rms_by_angle}
    return {"rotation_deg": best[1], "rms": best[0], "n_common": best[2], "rms_by_angle": rms_by_angle}
