"""Sun light at a site (STANDARDS.md section 10.15): closed forms, sampled Sun geometry, local horizon (P-S1).

Pure module: numpy only, no file or network I/O, no imports from io/ or grid.py.

Sampling (P-S): a circular orbit with the Sun as a point. Year fraction f_i = i/72 (i = 0..71) and hour angle
H_j = 2 pi j / 144 (j = 0..143): 72 x 144 = 10 368 samples. Angles are degrees unless the name says otherwise;
percentages are 0-100 shares of ALL samples.

Local horizon (P-S1): 36 azimuths every 10 deg (0 = north, clockwise through east); observer 2 m above the centre
of a DEM on a sphere of radius R; the horizon angle along a ray is the maximum over the ray of
atan((z(d) - d^2 / (2R) - (z0 + 2)) / d), with z(d) bilinear on the DEM, up to the nearest valid edge.
"""

from __future__ import annotations

import math

import numpy as np

N_YEAR = 72  # year fractions f_i = i / 72
N_HOUR = 144  # hour angles H_j = 2 pi j / 144
N_AZ = 36  # horizon azimuths, one every 10 deg
AZ_STEP_DEG = 360.0 / N_AZ
GRAZING_MAX_DEG = 10.0  # grazing = 0 < elevation < 10 deg
EYE_HEIGHT_M = 2.0  # observer height above the DEM centre (P-S1)


def noon_sun_max_deg(phi_deg: float, eps_deg: float) -> float:
    """Highest Sun elevation at local noon over a year (closed form).

    Formula: noon_sun_max = 90 - max(0, |phi| - eps). The Sun's declination reaches the value of eps closest to phi.
    """
    return 90.0 - max(0.0, abs(float(phi_deg)) - float(eps_deg))


def noon_sun_min_deg(phi_deg: float, eps_deg: float) -> float:
    """Lowest Sun elevation at local noon over a year (closed form; may be negative).

    Formula: noon_sun_min = 90 - (|phi| + eps).
    """
    return 90.0 - (abs(float(phi_deg)) + float(eps_deg))


def sun_geometry(phi_deg: float, eps_deg: float) -> tuple[np.ndarray, np.ndarray]:
    """Sampled Sun elevation and azimuth, both of shape (72, 144): rows = year fraction, columns = hour angle.

    Formula: f_i = i / 72; sin(dec_i) = sin(eps) sin(2 pi f_i); H_j = 2 pi j / 144;
    sin(e) = sin(phi) sin(dec) + cos(phi) cos(dec) cos(H);
    north = cos(phi) sin(dec) - sin(phi) cos(dec) cos(H); east = -cos(dec) sin(H);
    azimuth = atan2(east, north) mod 360 (degrees clockwise from north).
    """
    phi = math.radians(float(phi_deg))
    eps = math.radians(float(eps_deg))
    f = np.arange(N_YEAR) / N_YEAR
    dec = np.arcsin(np.sin(eps) * np.sin(2.0 * np.pi * f))[:, None]
    hour = (2.0 * np.pi * np.arange(N_HOUR) / N_HOUR)[None, :]
    sin_e = np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.cos(hour)
    # exact horizon samples are zero in exact arithmetic but carry rounding noise (cos 90 deg = 6e-17); snap them so
    # the strict e > 0 count is decided by the geometry, not by the noise
    sin_e = np.where(np.abs(sin_e) < 1e-12, 0.0, sin_e)
    elev = np.degrees(np.arcsin(np.clip(sin_e, -1.0, 1.0)))
    north = np.cos(phi) * np.sin(dec) - np.sin(phi) * np.cos(dec) * np.cos(hour)
    east = -np.cos(dec) * np.sin(hour)
    az = np.degrees(np.arctan2(east, north)) % 360.0
    return elev, az


def sun_samples(phi_deg: float, eps_deg: float) -> np.ndarray:
    """Sampled Sun elevation in degrees, shape (72, 144). See sun_geometry for the formula."""
    elev, _ = sun_geometry(phi_deg, eps_deg)
    return elev


def sun_time_pct(elev: np.ndarray) -> float:
    """Share of samples with the Sun above the geometric horizon, in percent.

    Formula: sun_time_pct = 100 * #{e > 0} / #{all samples}. Samples exactly at 0 deg count as not sunlit.
    """
    e = np.asarray(elev, dtype=float)
    return 100.0 * float(np.count_nonzero(e > 0.0)) / e.size


def grazing_pct(elev: np.ndarray) -> float:
    """Share of samples with the Sun low over the flat horizon (grazing light), in percent.

    Formula: grazing_pct = 100 * #{0 < e < 10 deg} / #{all samples}.
    """
    e = np.asarray(elev, dtype=float)
    return 100.0 * float(np.count_nonzero((e > 0.0) & (e < GRAZING_MAX_DEG))) / e.size


def sun_time_relief_pct(elev: np.ndarray, az: np.ndarray, horizon_by_az: np.ndarray) -> float:
    """Share of samples with the Sun above the local horizon, in percent (P-S1). NaN if the horizon is undefined.

    Formula: the horizon of a sample is the value at its nearest azimuth, k = round(az / 10 deg) mod 36;
    sun_time_relief_pct = 100 * #{e > horizon_by_az[k]} / #{all samples}. Elevations and azimuths are the sampled
    arrays of sun_geometry (same shape).
    """
    e = np.asarray(elev, dtype=float)
    a = np.asarray(az, dtype=float)
    hz = np.asarray(horizon_by_az, dtype=float)
    if hz.shape != (N_AZ,) or not np.all(np.isfinite(hz)):
        return float("nan")
    k = np.rint(a / AZ_STEP_DEG).astype(int) % N_AZ
    return 100.0 * float(np.count_nonzero(e > hz[k])) / e.size


def _bilinear(z: np.ndarray, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """Bilinear value of z at fractional (row, col) positions; NaN wherever a neighbour is NaN.

    Formula: standard bilinear interpolation on the four surrounding pixel centres.
    """
    r0 = np.floor(rows).astype(int)
    c0 = np.floor(cols).astype(int)
    fr = rows - r0
    fc = cols - c0
    return (
        (1 - fr) * (1 - fc) * z[r0, c0]
        + (1 - fr) * fc * z[r0, c0 + 1]
        + fr * (1 - fc) * z[r0 + 1, c0]
        + fr * fc * z[r0 + 1, c0 + 1]
    )


def valid_reach_m(dem: np.ndarray, pixel_m: float, centre: tuple[int, int]) -> float:
    """Distance from the centre to the nearest edge of valid data, in metres.

    Formula: reach = min(distance from the centre to the array edge, distance from the centre to the nearest NaN
    pixel). Rays are never followed beyond this distance.
    """
    z = np.asarray(dem, dtype=float)
    n_rows, n_cols = z.shape
    row_c, col_c = int(centre[0]), int(centre[1])
    edge = min(row_c, col_c, n_rows - 1 - row_c, n_cols - 1 - col_c) * float(pixel_m)
    bad = ~np.isfinite(z)
    if not bad.any():
        return float(edge)
    rows, cols = np.nonzero(bad)
    nearest = float(np.hypot(rows - row_c, cols - col_c).min()) * float(pixel_m)
    return float(min(edge, nearest))


def horizon_profile(
    dem: np.ndarray,
    pixel_m: float,
    centre: tuple[int, int],
    radius_body_m: float,
    eye_height_m: float = EYE_HEIGHT_M,
) -> np.ndarray:
    """Local horizon angle in degrees for 36 azimuths (0 = north, clockwise), shape (36,).

    Formula: for azimuth a and distance d = k * pixel_m (k >= 1, d <= reach - 2 pixel_m):
    horizon(a) = max_d degrees(atan((z(d) - d^2 / (2 R) - (z0 + eye_height)) / d)), z0 = DEM value at the centre,
    z(d) bilinear. Samples with an undefined value are ignored; an azimuth with no defined sample is NaN.
    Raises ValueError when the centre has no elevation or the usable ray length is too short (no silent fallback).
    """
    z = np.asarray(dem, dtype=float)
    row_c, col_c = int(centre[0]), int(centre[1])
    z0 = float(z[row_c, col_c])
    if not math.isfinite(z0):
        raise ValueError("observer centre has no elevation in the DEM")
    pixel = float(pixel_m)
    reach = valid_reach_m(z, pixel, (row_c, col_c))
    d_max = reach - 2.0 * pixel
    if d_max <= pixel:
        raise ValueError(f"usable ray length too short: {reach:.1f} m")
    d = np.arange(pixel, d_max + 1e-9, pixel)
    az = np.radians(np.arange(N_AZ) * AZ_STEP_DEG)
    rows = row_c - np.outer(np.cos(az), d) / pixel
    cols = col_c + np.outer(np.sin(az), d) / pixel
    zd = _bilinear(z, rows, cols)
    angle = np.degrees(np.arctan((zd - d[None, :] ** 2 / (2.0 * float(radius_body_m)) - (z0 + float(eye_height_m))) / d[None, :]))
    masked = np.where(np.isfinite(angle), angle, -np.inf)
    best = masked.max(axis=1)
    best[np.isneginf(best)] = np.nan
    return best
