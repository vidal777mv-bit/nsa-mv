"""Oracle and invariance tests for analog.core.metrics (STANDARDS.md section 5)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from analog.core import metrics as m

LAGS = [1, 2, 4, 8]
TPI_RADIUS = 5
TPI_THRESHOLD_DEG = 1.0


def _all_features(z: np.ndarray, mask: np.ndarray, L: float) -> dict[str, float | None]:
    """The six features computed directly from metrics (not via measure.features)."""
    ridge, valley = m.ridge_valley_pct(z, mask, L, TPI_RADIUS, TPI_THRESHOLD_DEG)
    return {
        "slope_p95_deg": m.slope_p95_deg(z, mask, L),
        "hi": m.hi(z, mask),
        "coherence": m.coherence(z, mask, L),
        "hurst": m.hurst(z, mask, LAGS),
        "ridge_pct": ridge,
        "valley_pct": valley,
    }


def _assert_same(a: dict, b: dict, tol: float = 1e-9) -> None:
    assert a.keys() == b.keys()
    for key in a:
        if a[key] is None or b[key] is None:
            assert a[key] is None and b[key] is None, key
        else:
            assert a[key] == pytest.approx(b[key], abs=tol, rel=tol), key


# ---------------------------------------------------------------- closed form

def test_plane_slope_p95_is_10_degrees(synth):
    """Plane z = x tan(10 deg): every gradient magnitude is tan(10 deg), so P95 slope = 10 deg [1e-9]."""
    value = m.slope_p95_deg(synth.plane(10.0), synth.disk, synth.L)
    assert value == pytest.approx(10.0, abs=1e-9)


def test_plane_coherence_is_one(synth):
    """Plane: J = [[g^2, 0], [0, 0]], so (l1 - l2)/(l1 + l2) = 1 [1e-9]."""
    value = m.coherence(synth.plane(10.0), synth.disk, synth.L)
    assert value == pytest.approx(1.0, abs=1e-9)


def test_plane_hurst_is_one(synth):
    """Plane: nu(k) is proportional to k (pooled over x and y), so the log-log slope is 1 [1e-9]."""
    value = m.hurst(synth.plane(10.0), synth.disk, LAGS)
    assert value == pytest.approx(1.0, abs=1e-9)


def test_plane_hi_is_one_half(synth):
    """Plane on a symmetric disk: mean = 0 and P5 = -P95, so hi = 0.5 [0.01]."""
    value = m.hi(synth.plane(10.0), synth.disk)
    assert value == pytest.approx(0.5, abs=0.01)


def test_plane_ridge_and_valley_are_zero(synth):
    """Plane: TPI is 0 everywhere (ring mean equals centre value), so ridge = valley = 0."""
    ridge, valley = m.ridge_valley_pct(synth.plane(10.0), synth.disk, synth.L, TPI_RADIUS, TPI_THRESHOLD_DEG)
    assert ridge == pytest.approx(0.0, abs=1e-9)
    assert valley == pytest.approx(0.0, abs=1e-9)


def test_flat_closed_form(synth):
    """Flat z = c: slope 0, coherence 0 (isotropic), hurst None, hi None, ridge = valley = 0."""
    z = synth.flat(123.4)
    assert m.slope_p95_deg(z, synth.disk, synth.L) == pytest.approx(0.0, abs=1e-12)
    assert m.coherence(z, synth.disk, synth.L) == 0.0
    assert m.hurst(z, synth.disk, LAGS) is None
    assert m.hi(z, synth.disk) is None
    ridge, valley = m.ridge_valley_pct(z, synth.disk, synth.L, TPI_RADIUS, TPI_THRESHOLD_DEG)
    assert ridge == 0.0
    assert valley == 0.0


def test_cone_hi_matches_closed_form(synth):
    """Cone z = h(1 - r/R) over the disk: hi = (1/3 - (1 - sqrt(.95))) / ((1 - sqrt(.05)) - (1 - sqrt(.95)))
    = 0.4101 [0.02]."""
    expected = (1.0 / 3.0 - (1.0 - math.sqrt(0.95))) / ((1.0 - math.sqrt(0.05)) - (1.0 - math.sqrt(0.95)))
    assert expected == pytest.approx(0.4101, abs=5e-5)
    value = m.hi(synth.cone(100.0), synth.disk)
    assert value == pytest.approx(expected, abs=0.02)


def test_cone_coherence_near_zero(synth):
    """Cone gradients are radial, so the gradient field is isotropic: coherence ~ 0 [0.05]."""
    value = m.coherence(synth.cone(100.0), synth.disk, synth.L)
    assert value == pytest.approx(0.0, abs=0.05)


@pytest.mark.parametrize("H", [0.3, 0.7])
def test_fbm_hurst_recovers_lattice_expectation(synth, H):
    """Spectral-synthesis fBm, n = 257, fixed seed 20261114: hurst = the generator's exact lattice expectation
    [0.05] (section 5, v1.0.1). Expected 0.430 (H = 0.3) and 0.712 (H = 0.7); the estimate for this seed is
    0.4246 and 0.6967."""
    z = synth.fbm(H, n=257, seed=synth.seed)
    mask = np.ones_like(z, dtype=bool)
    value = m.hurst(z, mask, LAGS)
    assert value is not None
    assert value == pytest.approx(_lattice_expected_hurst(H, 257), abs=0.05)


def _lattice_expected_hurst(H: float, n: int = 257) -> float:
    """Exact expectation of the pooled-structure-function slope for the discrete spectrum used by fbm().

    Formula: E[nu(k)^2] = sum_f P(f) w_k(f) / sum_f P(f), with P = |f|^-(2H+2) (zero frequency excluded),
    w_k(f) = (|1 - e^{2 pi i k fx}|^2 + |1 - e^{2 pi i k fy}|^2) / 2; slope = least-squares slope of
    log nu(k) against log k over k = 1, 2, 4, 8.
    """
    f = np.fft.fftfreq(n)
    fx, fy = np.meshgrid(f, f)
    radius = np.hypot(fx, fy)
    radius[0, 0] = 1.0
    power = radius ** (-(2.0 * H + 2.0))
    power[0, 0] = 0.0
    lags = np.array(LAGS, dtype=float)
    nu2 = []
    for k in LAGS:
        w = 0.5 * ((2 - 2 * np.cos(2 * np.pi * k * fx)) + (2 - 2 * np.cos(2 * np.pi * k * fy)))
        nu2.append(np.sum(power * w) / np.sum(power))
    return float(np.polyfit(np.log(lags), 0.5 * np.log(np.array(nu2)), 1)[0])


@pytest.mark.parametrize("H", [0.3, 0.7])
def test_fbm_hurst_matches_lattice_expectation(synth, H):
    """Added diagnostic (not a contract oracle): the mean estimate over 8 fixed seeds equals the exact lattice
    expectation for the same surface family within 0.01. Expected 0.430 (H=0.3) and 0.712 (H=0.7) at n = 257;
    the 8-seed means are 0.4305 and 0.7042. A single realisation scatters by about 0.01 (H=0.7), so one seed
    is not used for this comparison."""
    expected = _lattice_expected_hurst(H, 257)
    values = []
    for seed in range(synth.seed, synth.seed + 8):
        z = synth.fbm(H, n=257, seed=seed)
        values.append(m.hurst(z, np.ones_like(z, dtype=bool), LAGS))
    assert all(v is not None for v in values)
    assert float(np.mean(values)) == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------- undefined rules

def test_slope_and_coherence_null_below_50_pixels(synth):
    """Fewer than 50 valid pixels -> slope and coherence are null."""
    x, y = synth.grid_xy()
    tiny = np.hypot(x, y) <= 3 * synth.L  # 29 pixel centres
    z = synth.fbm(0.5, n=synth.n)
    assert m.slope_p95_deg(z, tiny, synth.L) is None
    assert m.coherence(z, tiny, synth.L) is None


def test_ridge_valley_null_without_valid_tpi(synth):
    """A single valid pixel has no complete TPI disk -> ridge and valley are null."""
    mask = np.zeros_like(synth.disk)
    mask[40, 40] = True
    ridge, valley = m.ridge_valley_pct(synth.plane(10.0), mask, synth.L, TPI_RADIUS, TPI_THRESHOLD_DEG)
    assert ridge is None
    assert valley is None


def test_tpi_spike_ridge_closed_form(synth):
    """Single 100 m peak on a zero background, mask = disk.

    Formula: the peak has TPI = 100 - 0 = 100 > t = tan(1 deg) * 5 * 100 = 8.7 m. The 80 ring pixels around
    it have TPI = 0 - 100/80 = -1.25, which is not below -t, and all other pixels have TPI = 0. So
    ridge = 100 / N_full and valley = 0, where N_full is the number of valid-TPI pixels (whole closed disk of
    radius 5 inside the mask), counted here by brute force.
    """
    z = np.zeros((synth.n, synth.n))
    z[40, 40] = 100.0
    mask = synth.disk
    offsets = [(di, dj) for di in range(-5, 6) for dj in range(-5, 6) if di * di + dj * dj <= 25]
    n_full = 0
    for i in range(synth.n):
        for j in range(synth.n):
            if not mask[i, j]:
                continue
            ok = True
            for di, dj in offsets:
                ii, jj = i + di, j + dj
                if not (0 <= ii < synth.n and 0 <= jj < synth.n and mask[ii, jj]):
                    ok = False
                    break
            n_full += ok
    ridge, valley = m.ridge_valley_pct(z, mask, synth.L, TPI_RADIUS, TPI_THRESHOLD_DEG)
    assert ridge == pytest.approx(100.0 / n_full, rel=1e-12)
    assert valley == pytest.approx(0.0, abs=1e-12)


# ---------------------------------------------------------------- invariances

def test_offset_invariance(synth):
    """z + c leaves every feature unchanged [1e-9]."""
    z = synth.fbm(0.5, n=synth.n)
    base = _all_features(z, synth.disk, synth.L)
    shifted = _all_features(z + 1000.0, synth.disk, synth.L)
    _assert_same(base, shifted)


def test_scale_invariance_of_hi_coherence_hurst(synth):
    """k z (k > 0) leaves hi, coherence and hurst unchanged [1e-9]."""
    z = synth.fbm(0.5, n=synth.n)
    base = _all_features(z, synth.disk, synth.L)
    scaled = _all_features(3.7 * z, synth.disk, synth.L)
    for key in ("hi", "coherence", "hurst"):
        assert scaled[key] == pytest.approx(base[key], abs=1e-9), key


@pytest.mark.parametrize("op", ["rot90", "transpose"])
def test_rot90_and_transpose_invariance(synth, op):
    """rot90(z) and transpose(z) leave every feature unchanged [1e-9]; the disk mask is symmetric."""
    z = synth.fbm(0.5, n=synth.n)
    mask = synth.disk
    if op == "rot90":
        z2, m2 = np.rot90(z), np.rot90(mask)
    else:
        z2, m2 = z.T.copy(), mask.T.copy()
    _assert_same(_all_features(z, mask, synth.L), _all_features(z2, m2, synth.L))


def test_negation_swaps_ridge_and_valley(synth):
    """-z swaps ridge_pct and valley_pct; slope, coherence and hurst unchanged [1e-9]."""
    z = synth.fbm(0.5, n=synth.n)
    base = _all_features(z, synth.disk, synth.L)
    assert base["ridge_pct"] > 0.0 and base["valley_pct"] > 0.0  # the swap must be non-trivial
    neg = _all_features(-z, synth.disk, synth.L)
    assert neg["ridge_pct"] == pytest.approx(base["valley_pct"], abs=1e-9)
    assert neg["valley_pct"] == pytest.approx(base["ridge_pct"], abs=1e-9)
    for key in ("slope_p95_deg", "coherence", "hurst"):
        assert neg[key] == pytest.approx(base[key], abs=1e-9), key


def test_single_pixel_spike_moves_hi_less_than_0_01(synth):
    """Setting one valid pixel to 10 (P95 - P5) moves hi by less than 0.01."""
    z = synth.fbm(0.5, n=synth.n)
    mask = synth.disk
    before = m.hi(z, mask)
    vals = z[mask]
    p5, p95 = np.percentile(vals, [5, 95])
    z2 = z.copy()
    z2[45, 45] = 10.0 * (p95 - p5)
    after = m.hi(z2, mask)
    assert abs(after - before) < 0.01
