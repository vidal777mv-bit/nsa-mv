"""Terrain features on a regular grid (STANDARDS.md section 4).

Conventions shared by every function here:
- ``z`` is a 2-D float array of elevations in metres, north-up, square pixels of side ``L`` metres.
- ``mask`` is a 2-D bool array; a pixel is *valid* when ``mask`` is True and ``z`` is finite.
- Gradients are central differences ``gy, gx = np.gradient(z, L)``. A gradient is used only where the
  pixel and the four neighbours used by the central difference are valid, and never on the array border.
- A feature that is undefined returns ``None`` (the JSON ``null``); it never returns 0 or -9999 as a stand-in.
"""

from __future__ import annotations

import math

import numpy as np

MIN_GRADIENT_PIXELS = 50
FLAT_RANGE_M = 1e-6
TRACE_EPS = 1e-12


def _valid(z: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Return ``mask & isfinite(z)``.

    Formula: valid[i, j] = M[i, j] and z[i, j] is finite.
    """
    return np.asarray(mask, dtype=bool) & np.isfinite(z)


def _gradients(z: np.ndarray, valid: np.ndarray, L: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Central-difference gradients and the mask of pixels where they are usable.

    Formula: gy, gx = np.gradient(z, L) computed on z with invalid pixels set to NaN. A pixel is usable when it
    and its 4 axial neighbours are valid and it is not on the array border (the central difference does not
    exist there).

    Returns (gx, gy, usable) with gx, gy in metres per metre (slope as a fraction).
    """
    zf = np.where(valid, z, np.nan)
    gy, gx = np.gradient(zf, L)
    usable = valid.copy()
    usable[1:-1, 1:-1] = (
        valid[1:-1, 1:-1] & valid[:-2, 1:-1] & valid[2:, 1:-1] & valid[1:-1, :-2] & valid[1:-1, 2:]
    )
    usable[0, :] = False
    usable[-1, :] = False
    usable[:, 0] = False
    usable[:, -1] = False
    return gx, gy, usable


def slope_deg(z: np.ndarray, mask: np.ndarray, L: float) -> np.ndarray:
    """Per-pixel slope in degrees over usable gradient pixels (flattened array).

    Formula: slope = degrees(arctan(hypot(gx, gy))).
    Returns an empty array when no pixel is usable.
    """
    valid = _valid(z, mask)
    gx, gy, usable = _gradients(z, valid, L)
    return np.degrees(np.arctan(np.hypot(gx[usable], gy[usable])))


def slope_p95_deg(z: np.ndarray, mask: np.ndarray, L: float) -> float | None:
    """95th percentile of the slope distribution, in degrees.

    Formula: P95( degrees( arctan( hypot(gx, gy) ) ) ) over usable pixels.
    Returns None when fewer than 50 usable pixels exist.
    """
    slopes = slope_deg(z, mask, L)
    if slopes.size < MIN_GRADIENT_PIXELS:
        return None
    return float(np.percentile(slopes, 95))


def hi(z: np.ndarray, mask: np.ndarray) -> float | None:
    """Hypsometric integral proxy, clipped to [0, 1].

    Formula: hi = clip( (mean(z) - P5(z)) / (P95(z) - P5(z)), 0, 1 ), over valid pixels.
    Returns None when there is no valid pixel or when P95 - P5 < 1e-6 m (flat terrain).
    """
    vals = z[_valid(z, mask)]
    if vals.size == 0:
        return None
    p5, p95 = np.percentile(vals, [5, 95])
    span = float(p95 - p5)
    if span < FLAT_RANGE_M:
        return None
    value = (float(vals.mean()) - float(p5)) / span
    return float(min(max(value, 0.0), 1.0))


def coherence(z: np.ndarray, mask: np.ndarray, L: float) -> float | None:
    """Orientation coherence of the gradient field, in [0, 1].

    Formula: J = [[<gx^2>, <gx gy>], [<gx gy>, <gy^2>]] with means over usable pixels; eigenvalues
    l1 >= l2 of J; coherence = (l1 - l2) / (l1 + l2). Since J is symmetric positive semi-definite,
    with a = <gx^2>, b = <gx gy>, c = <gy^2>: l1 + l2 = a + c and (l1 - l2) = 2 sqrt(((a - c)/2)^2 + b^2).
    Returns 0.0 when l1 + l2 < 1e-12 (flat terrain is isotropic), None when fewer than 50 usable pixels.
    """
    valid = _valid(z, mask)
    gx, gy, usable = _gradients(z, valid, L)
    if int(usable.sum()) < MIN_GRADIENT_PIXELS:
        return None
    gxu = gx[usable]
    gyu = gy[usable]
    a = float(np.mean(gxu * gxu))
    b = float(np.mean(gxu * gyu))
    c = float(np.mean(gyu * gyu))
    trace = a + c
    if trace < TRACE_EPS:
        return 0.0
    d = math.sqrt(((a - c) / 2.0) ** 2 + b * b)
    return float(min(max(2.0 * d / trace, 0.0), 1.0))


def hurst(z: np.ndarray, mask: np.ndarray, lags_px: list[int] | tuple[int, ...]) -> float | None:
    """Hurst exponent from the pooled structure function.

    Formula: nu(k) = sqrt( mean of (z(x+k) - z(x))^2 over all valid pairs along x AND along y, pooled ),
    for each lag k in ``lags_px``; both ends of a pair must be valid. hurst = least-squares slope of
    log nu(k) against log k.
    Returns None when any nu(k) == 0 (flat terrain) or a lag has no valid pair.
    """
    valid = _valid(z, mask)
    zf = np.where(valid, z, 0.0)
    n_rows, n_cols = zf.shape
    nus: list[float] = []
    for k in lags_px:
        k = int(k)
        sq_sum = 0.0
        count = 0
        if k < n_cols:
            vv = valid[:, :-k] & valid[:, k:]
            d = zf[:, k:] - zf[:, :-k]
            sq_sum += float(np.sum(d[vv] ** 2))
            count += int(vv.sum())
        if k < n_rows:
            vv = valid[:-k, :] & valid[k:, :]
            d = zf[k:, :] - zf[:-k, :]
            sq_sum += float(np.sum(d[vv] ** 2))
            count += int(vv.sum())
        if count == 0:
            return None
        nu = math.sqrt(sq_sum / count)
        if nu == 0.0:
            return None
        nus.append(nu)
    if len(nus) < 2:
        return None
    slope = np.polyfit(np.log(np.asarray(lags_px, dtype=float)), np.log(np.asarray(nus)), 1)[0]
    return float(slope)


def tpi(z: np.ndarray, mask: np.ndarray, radius_px: int) -> tuple[np.ndarray, np.ndarray]:
    """Topographic position index over an annulus, valid only where the full disk is valid.

    Formula: TPI = z - mean(z over the annulus 0 < d <= r_px), d in pixels, r_px = radius_px.
    A pixel is valid for TPI only when every pixel of its closed disk (d <= r_px) is valid, so the
    annulus is always complete.

    Returns (tpi, full) where ``tpi`` is NaN outside ``full`` and ``full`` is the bool mask of valid TPI pixels.
    """
    r = int(radius_px)
    valid = _valid(z, mask)
    n_rows, n_cols = z.shape
    vpad = np.zeros((n_rows + 2 * r, n_cols + 2 * r), dtype=bool)
    vpad[r : r + n_rows, r : r + n_cols] = valid
    zpad = np.zeros((n_rows + 2 * r, n_cols + 2 * r), dtype=float)
    zpad[r : r + n_rows, r : r + n_cols] = np.where(valid, z, 0.0)

    offsets = [
        (di, dj)
        for di in range(-r, r + 1)
        for dj in range(-r, r + 1)
        if 0 < di * di + dj * dj <= r * r
    ]
    full = valid.copy()
    annulus_sum = np.zeros((n_rows, n_cols), dtype=float)
    for di, dj in offsets:
        full &= vpad[r + di : r + di + n_rows, r + dj : r + dj + n_cols]
        annulus_sum += zpad[r + di : r + di + n_rows, r + dj : r + dj + n_cols]
    annulus_mean = annulus_sum / len(offsets)
    tpi_values = np.where(full, np.where(valid, z, 0.0) - annulus_mean, np.nan)
    return tpi_values, full


def ridge_valley_pct(
    z: np.ndarray, mask: np.ndarray, L: float, radius_px: int, threshold_deg: float
) -> tuple[float | None, float | None]:
    """Share of ridge and valley pixels, in percent.

    Formula: t = tan(threshold_deg) * radius_px * L (metres of height over the TPI window);
    ridge_pct = 100 * share of valid-TPI pixels with tpi > +t; valley_pct = 100 * share with tpi < -t.
    Returns (None, None) when there is no valid TPI pixel.
    """
    values, full = tpi(z, mask, radius_px)
    total = int(full.sum())
    if total == 0:
        return None, None
    t = math.tan(math.radians(threshold_deg)) * radius_px * L
    tv = values[full]
    ridge = 100.0 * float(np.count_nonzero(tv > t)) / total
    valley = 100.0 * float(np.count_nonzero(tv < -t)) / total
    return ridge, valley
