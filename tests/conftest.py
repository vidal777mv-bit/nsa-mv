"""Shared test setup: put src/ on sys.path and provide closed-form synthetic surfaces."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SEED = 20261114
GRID_N = 81  # standard synthetic grid: L = 100, R = 4000 -> n = 81, centre index 40
GRID_L = 100.0
GRID_R = 4000.0


def grid_xy(n: int = GRID_N, L: float = GRID_L) -> tuple[np.ndarray, np.ndarray]:
    """Pixel-centre coordinates (east x, north y) in metres; centre pixel = (0, 0).

    Formula: x = (j - n//2) L, y = (n//2 - i) L (north-up rows).
    """
    half = n // 2
    rows, cols = np.mgrid[0:n, 0:n]
    return (cols - half) * L, (half - rows) * L


def disk_mask(n: int = GRID_N, L: float = GRID_L, R: float = GRID_R) -> np.ndarray:
    """True where the pixel centre lies within R of the centre (distance <= R).

    Formula: hypot(x, y) <= R.
    """
    x, y = grid_xy(n, L)
    return np.hypot(x, y) <= R + 1e-9


def plane(theta_deg: float = 10.0, n: int = GRID_N, L: float = GRID_L) -> np.ndarray:
    """Tilted plane z = x tan(theta)."""
    x, _ = grid_xy(n, L)
    return x * np.tan(np.radians(theta_deg))


def flat(c: float = 123.4, n: int = GRID_N) -> np.ndarray:
    """Constant surface z = c."""
    return np.full((n, n), float(c))


def cone(h: float = 100.0, n: int = GRID_N, L: float = GRID_L, R: float = GRID_R) -> np.ndarray:
    """Cone z = h (1 - r / R), r = distance from the centre pixel."""
    x, y = grid_xy(n, L)
    return h * (1.0 - np.hypot(x, y) / R)


def fbm(H: float, n: int = 257, seed: int = SEED) -> np.ndarray:
    """Fractional Brownian surface by spectral synthesis.

    Formula: F(f) = |f|^-(H+1) * (a + i b), a, b ~ N(0, 1) from default_rng(seed); z = Re(ifft2(F)).
    The 2-D power spectrum is then proportional to |f|^-(2H+2), which gives a Hurst exponent H.
    The zero-frequency term is set to zero; the result is rescaled to a 100 m standard deviation.
    """
    rng = np.random.default_rng(seed)
    f = np.fft.fftfreq(n)
    fx, fy = np.meshgrid(f, f)
    radius = np.hypot(fx, fy)
    radius[0, 0] = 1.0
    amp = radius ** (-(H + 1.0))
    amp[0, 0] = 0.0
    coef = amp * (rng.standard_normal((n, n)) + 1j * rng.standard_normal((n, n)))
    z = np.real(np.fft.ifft2(coef))
    return 100.0 * (z - z.mean()) / z.std()  # metres, standard deviation 100 m (ridge/valley threshold is in metres)


@pytest.fixture
def synth() -> SimpleNamespace:
    """Closed-form surfaces and helpers used by the oracle tests."""
    return SimpleNamespace(
        seed=SEED,
        n=GRID_N,
        L=GRID_L,
        R=GRID_R,
        grid_xy=grid_xy,
        disk=disk_mask(),
        disk_mask=disk_mask,
        plane=plane,
        flat=flat,
        cone=cone,
        fbm=fbm,
    )


@pytest.fixture
def measure_cfg() -> dict:
    """Parsed config/measure.json (read-only; tests copy it before changing sigmas)."""
    return json.loads((ROOT / "config" / "measure.json").read_text(encoding="utf-8"))
