"""Feature vector and distance between two terrain windows (STANDARDS.md section 4).

``features`` takes the full measure config (``config/measure.json`` as a dict); ``distance`` takes the
``features`` section of that config (feature id -> {"weight", "sigma"}).
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np

from analog.core import metrics

FEATURE_IDS: tuple[str, ...] = ("slope_p95_deg", "hi", "coherence", "hurst", "ridge_pct", "valley_pct")


def features(
    z: np.ndarray, mask: np.ndarray, L: float, cfg: Mapping[str, object]
) -> dict[str, float | None]:
    """Compute the six features of one window.

    Formula: see metrics.py for each term. Parameters come from cfg:
    tpi.radius_px, tpi.threshold_deg (ridge/valley) and features.hurst.lags_px.
    Each value is a float, or None when that feature is undefined (STANDARDS table, section 4).
    Raises KeyError when cfg lacks a required key (no silent defaults).
    """
    tpi_cfg = cfg["tpi"]
    lags = cfg["features"]["hurst"]["lags_px"]  # type: ignore[index]
    ridge, valley = metrics.ridge_valley_pct(
        z,
        mask,
        L,
        int(tpi_cfg["radius_px"]),  # type: ignore[index]
        float(tpi_cfg["threshold_deg"]),  # type: ignore[index]
    )
    return {
        "slope_p95_deg": metrics.slope_p95_deg(z, mask, L),
        "hi": metrics.hi(z, mask),
        "coherence": metrics.coherence(z, mask, L),
        "hurst": metrics.hurst(z, mask, lags),
        "ridge_pct": ridge,
        "valley_pct": valley,
    }


def relief_class(slope_p95_deg: object, flat_below_deg: float) -> str | None:
    """Relief class of a window for the v1.3 tie rule (STANDARDS 10.11).

    'rugged' when slope_p95_deg >= flat_below_deg, else 'flat' (a value equal to the threshold is rugged).
    None when the slope is null (no class, no threshold).
    """
    v = _as_float(slope_p95_deg)
    if v is None:
        return None
    return "rugged" if v >= float(flat_below_deg) else "flat"


def _as_float(value: object) -> float | None:
    """Return a finite float, or None for missing, null or NaN values."""
    if value is None:
        return None
    x = float(value)  # type: ignore[arg-type]
    return None if math.isnan(x) else x


def distance(
    a: Mapping[str, object],
    b: Mapping[str, object],
    features_cfg: Mapping[str, Mapping[str, object]],
    min_shared: int = 4,
) -> float | None:
    """Normalised weighted distance between two feature vectors.

    Formula: D(a, b) = sqrt( sum_k w_k ((a_k - b_k) / sigma_k)^2 / sum_k w_k ), summed over features k
    with w_k > 0 where both a_k and b_k are non-null (and listed in features_cfg). Features with weight 0 (excluded
    by the redundancy rule, config v1.2) are computed elsewhere but never enter D nor the shared-feature count.
    Returns None when fewer than ``min_shared`` (default 4) features with weight > 0 are shared.
    Raises ValueError("sigma not calibrated") when any feature in features_cfg has sigma None.
    """
    for name, spec in features_cfg.items():
        if spec.get("sigma") is None:
            raise ValueError(f"sigma not calibrated for feature {name!r}")

    num = 0.0
    den = 0.0
    shared = 0
    for name, spec in features_cfg.items():
        w = float(spec["weight"])  # type: ignore[arg-type]
        if w <= 0.0:
            continue
        av = _as_float(a.get(name))
        bv = _as_float(b.get(name))
        if av is None or bv is None:
            continue
        sigma = float(spec["sigma"])  # type: ignore[arg-type]
        num += w * ((av - bv) / sigma) ** 2
        den += w
        shared += 1

    if shared < min_shared or den <= 0.0:
        return None
    return float(math.sqrt(num / den))
