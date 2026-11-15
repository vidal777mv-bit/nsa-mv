"""Closed-form tests for analog.viz (STANDARDS.md section 10.6). Run alone:
.venv/Scripts/python.exe -m pytest tests/test_viz.py
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from analog import grid as gridmod
from analog import viz
from analog.core.mission import slope_map_deg

L100 = 100.0
L30 = 30.0
R = 4000.0


def _disk(n: int, L: float, R_: float) -> np.ndarray:
    half = n // 2
    rows, cols = np.mgrid[0:n, 0:n]
    return np.hypot((cols - half) * L, (half - rows) * L) <= R_ + 1e-9


def test_grid_size_contract():
    """n = 2 ceil(R/L) + 1: 269 for the 30 m visual grid, 81 for the 100 m measurement grid."""
    assert viz.grid_size(4000.0, 30.0) == 269
    assert viz.grid_size(4000.0, 100.0) == 81


def test_hillshade_flat_is_sin45_times_255(synth):
    """Flat surface: shade = 255 sin(45 deg) = 180.3122 everywhere."""
    z = synth.flat(50.0)
    shade = viz.hillshade(z, synth.disk, L100)
    finite = np.isfinite(shade)
    assert finite.sum() > 0.8 * synth.disk.sum()  # NaN only at the disk edge (4-neighbour rule) and outside
    assert not np.any(finite & ~synth.disk)
    assert np.allclose(shade[finite], 255.0 * math.sin(math.radians(45.0)), atol=1e-9)


def test_hillshade_tilted_plane_matches_burrough_formula(synth):
    """Plane z = k x (rising to the east), k = tan(10 deg). Burrough form with slope s = 10 deg and downslope
    aspect 270 deg (towards the west): shade = 255 [sin(alt) cos(s) + cos(alt) sin(s) cos(az - aspect)] with
    az = 315 deg, alt = 45 deg, so cos(az - aspect) = cos(45 deg). Linear surface: exact in every pixel."""
    k = math.tan(math.radians(10.0))
    z = synth.plane(10.0)
    shade = viz.hillshade(z, synth.disk, L100)
    s = math.radians(10.0)
    alt = math.radians(45.0)
    expected = 255.0 * (math.sin(alt) * math.cos(s) + math.cos(alt) * math.sin(s) * math.cos(math.radians(45.0)))
    finite = shade[np.isfinite(shade)]
    assert finite.size > 0
    assert np.allclose(finite, expected, atol=1e-9)
    # closed form in k: (0.5 k + sin45) / sqrt(1 + k^2) * 255
    assert expected == pytest.approx(255.0 * (0.5 * k + math.sin(alt)) / math.sqrt(1 + k * k), abs=1e-9)


def test_to_uint8_rounds_and_fills():
    """Rounding to nearest, NaN to the fill value (0), clipping to [0, 255]."""
    img = np.array([[180.31, np.nan], [300.0, -4.0]])
    out = viz.to_uint8(img)
    assert out.dtype == np.uint8
    assert out.tolist() == [[180, 0], [255, 0]]


def test_png_roundtrip_decodes_to_same_pixels():
    """Encode a 3 x 4 patch, then decode the IDAT chunk by hand and compare every pixel."""
    arr = (np.arange(12, dtype=np.uint8) * 20).reshape(3, 4)
    data = viz.encode_png_gray(arr)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    idat = b""
    width = height = None
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        tag = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        crc = struct.unpack(">I", data[pos + 8 + length : pos + 12 + length])[0]
        assert crc == zlib.crc32(tag + body) & 0xFFFFFFFF
        if tag == b"IHDR":
            width, height, depth, ctype = struct.unpack(">IIBB", body[:10])
            assert (depth, ctype) == (8, 0)
        if tag == b"IDAT":
            idat += body
        pos += 12 + length
    raw = zlib.decompress(idat)
    rows = np.frombuffer(raw, dtype=np.uint8).reshape(height, 1 + width)
    assert (width, height) == (4, 3)
    assert np.all(rows[:, 0] == 0)
    assert np.array_equal(rows[:, 1:], arr)


def test_plane_has_only_driving_bit(synth):
    """Plane 10 deg, landing limit 15 (no bit0), driving limit 5 (bit1 everywhere defined). TPI of a plane is 0,
    so no ridge or valley bit. Undefined pixels carry no bit."""
    z = synth.plane(10.0)
    bits = viz.bits_100m(z, synth.disk, L100, 5, 1.0, 15.0, 5.0)
    slope = slope_map_deg(z, synth.disk, L100)
    defined = np.isfinite(slope)
    assert np.all(bits[defined] == viz.BIT_DRIVING)
    assert np.all(bits[~defined] == 0)


def test_v_valley_and_inverted_ridge_bits():
    """z = c |x| (a V valley, c = 1) and z = -|x| (a ridge), 81 x 81 grid, full disk valid.

    Column 40 is x = 0. Slope: 45 deg on columns != 40, and exactly 0 on column 40 (symmetric neighbours), so with
    landing limit 15 bit0 is set everywhere except column 40. TPI at column 40 is -c * mean(100 |dj|) over the
    annulus 0 < di^2 + dj^2 <= 25 (oracle loop below), which is far beyond t = tan(1 deg) * 5 * 100 = 8.75 m:
    valley for z = |x| and ridge for z = -|x|. Columns are independent of rows, so every row of the column agrees.
    """
    n = 81
    half = n // 2
    rows, cols = np.mgrid[0:n, 0:n]
    x = (cols - half) * L100
    mask = np.ones((n, n), dtype=bool)
    offsets = [(di, dj) for di in range(-5, 6) for dj in range(-5, 6) if 0 < di * di + dj * dj <= 25]
    annulus_mean_abs = np.mean([abs(dj) * L100 for di, dj in offsets])
    t = math.tan(math.radians(1.0)) * 5 * L100
    assert annulus_mean_abs > t

    bits_v = viz.bits_100m(np.abs(x), mask, L100, 5, 1.0, 15.0, 45.0 + 1.0)
    assert np.all((bits_v[5:-5, 40] & viz.BIT_VALLEY) > 0)
    assert np.all((bits_v[5:-5, 40] & viz.BIT_RIDGE) == 0)
    others = np.delete(bits_v, 40, axis=1)
    inner = others[5:-5, 5:-5]  # interior: defined slope and full TPI disk
    assert np.all((inner & viz.BIT_LANDING) > 0)
    assert np.all((bits_v[5:-5, 40] & viz.BIT_LANDING) == 0)

    bits_r = viz.bits_100m(-np.abs(x), mask, L100, 5, 1.0, 15.0, 45.0 + 1.0)
    assert np.all((bits_r[5:-5, 40] & viz.BIT_RIDGE) > 0)
    assert np.all((bits_r[5:-5, 40] & viz.BIT_VALLEY) == 0)


def test_missing_limit_raises_instead_of_stand_in(synth):
    """The layers never use a stand-in limit: None raises ValueError (caller writes null and logs)."""
    with pytest.raises(ValueError):
        viz.bits_100m(synth.plane(10.0), synth.disk, L100, 5, 1.0, None, 5.0)


def test_nearest_upsample_maps_centre_and_edges():
    """100 m grid of 81 pixels with value = column index, upsampled to the 30 m grid of 269 pixels.
    Centre (134, 134) -> source (40, 40). Column x = 30 m -> 100 m column 40 (0.3 rounds to 0); x = 60 m ->
    column 41 (0.6 rounds to 1); x = -4020 m (first column) -> column 0."""
    src = np.broadcast_to(np.arange(81)[None, :], (81, 81)).astype(float)
    dst = viz.nearest_upsample(src, L100, L30, 269)
    assert dst.shape == (269, 269)
    assert dst[134, 134] == 40
    assert dst[134, 135] == 40  # x = 30 m
    assert dst[134, 136] == 41  # x = 60 m
    assert dst[134, 0] == 0  # x = -4020 m clipped to the first column
    assert dst[134, 268] == 80


def test_vertical_exaggeration_rule():
    """VE = 0.2 * 2R / max relief, floor to 0.1. Relief 400 m, R 4000 m -> 4.0. Relief 333 m -> 4.8 (4.80 floored)."""
    assert viz.vertical_exaggeration([400.0, 100.0], 4000.0) == pytest.approx(4.0)
    assert viz.vertical_exaggeration([333.0], 4000.0) == pytest.approx(4.8)
    with pytest.raises(ValueError):
        viz.vertical_exaggeration([], 4000.0)


def _gauss(x, y, cx, cy, s):
    return np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2.0 * s * s))


def _g(x, y):
    """Asymmetric synthetic terrain (two bumps and a tilt), defined on the plane."""
    return 300.0 * _gauss(x, y, 900.0, 400.0, 700.0) + 120.0 * _gauss(x, y, -1200.0, -700.0, 500.0) + 0.02 * x


def test_rotation_alignment_recovers_40_deg():
    """analog(q) = g(Rot(40 deg) q), target = g. The analog displayed rotated counter-clockwise by 40 deg matches the
    target, so rotation_deg = 40 (sign convention in viz.rotation_alignment). Other angles are clearly worse."""
    n = 269
    half = n // 2
    rows, cols = np.mgrid[0:n, 0:n]
    x = (cols - half) * L30
    y = (half - rows) * L30
    mask = np.hypot(x, y) <= R + 1e-9
    z_t = _g(x, y)
    a = math.radians(40.0)
    qx = math.cos(a) * x - math.sin(a) * y
    qy = math.sin(a) * x + math.cos(a) * y
    z_a = _g(qx, qy)
    res = viz.rotation_alignment(z_t, mask, z_a, mask, L30, R)
    assert res["rotation_deg"] == pytest.approx(40.0, abs=10.0)
    assert res["rotation_deg"] == 40.0
    assert res["rms_by_angle"][40.0] < 0.05
    assert res["rms_by_angle"][320.0] > 0.2
    assert res["rms_by_angle"][30.0] > res["rms_by_angle"][40.0]


def test_export_grid_30m_has_269_pixels_and_zero_disk_mean(tmp_path: Path):
    """A synthetic geographic GeoTIFF around the site, loaded on the 30 m standard grid (STANDARDS 10.6):
    n = 269, mask = disk within R, relative height has zero mean over the disk and NaN outside."""
    lat0, lon0 = 10.0, -60.0
    px = 0.0002  # about 22 m
    npx = 600  # +-0.06 deg, about 6.6 km each side: covers the 4 km disk
    west, north = lon0 - npx * px / 2, lat0 + npx * px / 2
    transform = from_origin(west, north, px, px)
    lon_c = west + (np.arange(npx) + 0.5) * px
    data = np.broadcast_to(((lon_c - lon0) * 4000.0)[None, :], (npx, npx)).astype(np.float64).copy()
    path = tmp_path / "geo_ramp.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=npx, width=npx, count=1, dtype="float64", crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data, 1)
    z, mask, meta = gridmod.load_local_grid(path, lat0, lon0, "earth", L30, R)
    assert z.shape == (269, 269)
    assert mask.sum() > 0.9 * np.count_nonzero(_disk(269, L30, R))
    h = viz.relative_height(z, mask)
    assert abs(float(np.mean(h[mask]))) < 1e-9
    assert np.all(np.isnan(h[~mask]))
    assert meta["L"] == L30


def test_pair_exaggeration_rule_and_clamp():
    """STANDARDS 10.12: VE = floor_0.1(0.2 * 2R / max(relief of the pair)), clamped to [1, 10], one value per pair."""
    from analog import viz

    assert viz.pair_exaggeration(400.0, 300.0, 4000.0) == pytest.approx(4.0)  # 1600/400 = 4.0 uses the larger relief
    assert viz.pair_exaggeration(500.0, 600.0, 4000.0) == pytest.approx(2.6)  # 1600/600 = 2.67, floor 0.1
    assert viz.pair_exaggeration(1840.0, 100.0, 4000.0) == pytest.approx(1.0)  # 0.87 clamped up to 1
    assert viz.pair_exaggeration(100.0, 100.0, 4000.0) == pytest.approx(10.0)  # 16 clamped down to 10
    assert viz.pair_exaggeration(100.0, 100.0, 4000.0) == viz.pair_exaggeration(100.0, 100.0, 4000.0)
    with pytest.raises(ValueError):
        viz.pair_exaggeration(0.0, 0.0, 4000.0)
