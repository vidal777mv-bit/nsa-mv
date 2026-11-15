"""Mission-proven terrain share (STANDARDS.md section 10.3). Pure: numpy only, no file or network I/O.

For a body and a mission kind (landing or driving) the limit ``limit_deg`` is the largest slope that a completed
mission demonstrated (values come from config/missions.json, not from this module). The share is computed on the
100 m standard grid:

    mission_pct = 100 * #{pixels with slope <= limit_deg} / #{pixels with a defined slope}

A pixel has a defined slope when it is a valid disk pixel and its four axial neighbours are valid too (the
interior-only rule of STANDARDS section 4). Pixels without a defined slope are not counted in the denominator; the
pipeline reports the count of disk pixels next to the share so the denominator is visible.
"""

from __future__ import annotations

import math

import numpy as np

from analog.core import metrics


def slope_map_deg(z: np.ndarray, mask: np.ndarray, L: float) -> np.ndarray:
    """Two-dimensional slope in degrees, NaN where the slope is undefined.

    Formula: slope = degrees(arctan(hypot(gx, gy))) with central differences on usable pixels only
    (metrics._gradients: the pixel and its 4 neighbours are valid and the pixel is not on the array border).
    """
    valid = np.asarray(mask, dtype=bool) & np.isfinite(z)
    gx, gy, usable = metrics._gradients(np.asarray(z, dtype=float), valid, float(L))
    out = np.full(z.shape, np.nan, dtype=float)
    out[usable] = np.degrees(np.arctan(np.hypot(gx[usable], gy[usable])))
    return out


def mission_share(slope_deg: np.ndarray, limit_deg: float | None) -> dict[str, float | int | str | None]:
    """Share of defined slopes at or below a mission limit, in percent.

    Formula: pct = 100 * count(s <= limit_deg) / count(isfinite(s)). Non-finite entries are not defined.
    Returns a dict with keys pct, n_below, n_defined and reason:
    - pct None and reason "no limit" when limit_deg is None or not finite (missing value, never a stand-in 0);
    - pct None and reason "no defined slope" when no slope is defined.
    """
    s = np.asarray(slope_deg, dtype=float).ravel()
    defined = np.isfinite(s)
    n_defined = int(defined.sum())
    if limit_deg is None or not math.isfinite(float(limit_deg)):
        return {"pct": None, "n_below": None, "n_defined": n_defined, "reason": "no limit"}
    if n_defined == 0:
        return {"pct": None, "n_below": 0, "n_defined": 0, "reason": "no defined slope"}
    n_below = int(np.count_nonzero(s[defined] <= float(limit_deg)))
    return {
        "pct": 100.0 * n_below / n_defined,
        "n_below": n_below,
        "n_defined": n_defined,
        "reason": None,
    }
