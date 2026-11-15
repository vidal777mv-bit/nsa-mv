"""Offline tests for src/analog/io/fetch.py (one per rule; no network).

Run: .venv/Scripts/python.exe -m pytest tests/test_fetch.py -q
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analog.io import fetch  # noqa: E402
from analog.io.fetch import FetchError  # noqa: E402

TIFF_BYTES = b"II*\x00" + b"\x00" * 200
HTML_BYTES = b"<!DOCTYPE html><html><body>404 Not Found</body></html>"


def test_html_is_detected_even_with_tif_name_and_status_200():
    # Rule: an HTML page is never data, whatever the file name or status says.
    assert fetch.classify_head(HTML_BYTES, "application/octet-stream") == "html"
    reason = fetch.check_payload(HTML_BYTES, "image/tiff", "tiff")
    assert reason is not None and "HTML" in reason


def test_classify_magic_bytes():
    assert fetch.classify_head(TIFF_BYTES) == "tiff"
    assert fetch.classify_head(b"PK\x03\x04rest") == "zip"
    assert fetch.classify_head(b"\x1f\x8b\x08rest") == "gzip"
    assert fetch.classify_head(b'{"id":"nasadem"}') == "json"


def test_expected_kind_mismatch_is_rejected():
    assert fetch.check_payload(b"PK\x03\x04", None, "tiff") == "expected tiff data, got zip"
    assert fetch.check_payload(TIFF_BYTES, None, "tiff") is None


def test_sha256_file_matches_hashlib(tmp_path):
    p = tmp_path / "x.bin"
    data = b"terrain" * 10000
    p.write_bytes(data)
    assert fetch.sha256_file(p) == hashlib.sha256(data).hexdigest()


def test_build_raw_path_layout_and_rejections(tmp_path):
    p = fetch.build_raw_path(tmp_path, "moon", "haworth", "lola_5m_haworth_surf.tif")
    assert p == (tmp_path / "moon" / "haworth" / "lola_5m_haworth_surf.tif").resolve()
    with pytest.raises(ValueError):
        fetch.build_raw_path(tmp_path, "venus", "x", "a.tif")
    with pytest.raises(ValueError):
        fetch.build_raw_path(tmp_path, "moon", "Bad-Id", "a.tif")
    with pytest.raises(ValueError):
        fetch.build_raw_path(tmp_path, "moon", "ok", "../evil.tif")


def test_window_bounds_is_square_and_centred():
    minx, miny, maxx, maxy = fetch.window_bounds(100.0, -50.0, 4000.0)
    assert (maxx - minx) == pytest.approx(8000.0)
    assert (maxy - miny) == pytest.approx(8000.0)
    assert ((minx + maxx) / 2, (miny + maxy) / 2) == pytest.approx((100.0, -50.0))


def test_km_to_deg_equator_and_sixty_north():
    dlat, dlon = fetch.km_to_deg(0.0, 10.0)
    assert dlat == pytest.approx(10.0 / 111.32)
    assert dlon == pytest.approx(dlat)
    _, dlon60 = fetch.km_to_deg(60.0, 10.0)
    assert dlon60 == pytest.approx(2 * dlat, rel=1e-6)  # cos(60 deg) = 0.5


def test_append_manifest_keeps_existing_entries(tmp_path):
    m = tmp_path / "manifest.json"
    fetch.append_manifest(m, {"path": "a", "source_id": "s1"})
    fetch.append_manifest(m, {"path": "b", "source_id": "s2"})
    items = json.loads(m.read_text(encoding="utf-8"))
    assert [e["path"] for e in items] == ["a", "b"]


class _Handler(BaseHTTPRequestHandler):
    routes: dict[str, bytes] = {}

    def do_GET(self):  # noqa: N802 - http.server API
        body = self.routes.get(self.path)
        if body is None:
            self.send_response(404)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(HTML_BYTES)))
            self.end_headers()
            self.wfile.write(HTML_BYTES)
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/tiff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence test server
        pass


@pytest.fixture
def server():
    _Handler.routes = {"/good.tif": TIFF_BYTES + b"x" * 100, "/fake.tif": HTML_BYTES * 3}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def test_download_good_tiff_records_bytes_and_sha256(server, tmp_path):
    dest = tmp_path / "moon" / "haworth" / "good.tif"
    out = fetch.download(server + "/good.tif", dest, expect="tiff", retries=1)
    assert out["bytes"] == len(TIFF_BYTES) + 100
    assert out["sha256"] == hashlib.sha256(dest.read_bytes()).hexdigest()
    assert out["http_code"] == 200
    assert not dest.with_name("good.tif.part").exists()


def test_download_html_served_as_tif_is_refused(server, tmp_path):
    dest = tmp_path / "fake.tif"
    with pytest.raises(FetchError, match="HTML"):
        fetch.download(server + "/fake.tif", dest, expect="tiff", retries=1)
    assert not dest.exists()


def test_download_404_is_refused_without_retry(server, tmp_path):
    with pytest.raises(FetchError, match="HTTP 404"):
        fetch.download(server + "/missing.tif", tmp_path / "m.tif", expect="tiff", retries=3)


def test_download_over_size_budget_is_refused(server, tmp_path):
    with pytest.raises(FetchError, match="budget"):
        fetch.download(server + "/good.tif", tmp_path / "big.tif", expect="tiff", retries=1, max_bytes=50)
    assert not (tmp_path / "big.tif").exists()


def test_worldcover_tile_name_uses_three_degree_south_west_corner():
    # Rule: tile SW corner = floor(lat/3)*3, floor(lon/3)*3; N/S 2 digits, E/W 3 digits.
    assert fetch.worldcover_tile_name(21.0, 18.5) == "ESA_WorldCover_10m_2021_v200_N21E018_Map.tif"
    assert fetch.worldcover_tile_name(-0.5, -0.5) == "ESA_WorldCover_10m_2021_v200_S03W003_Map.tif"
    assert fetch.worldcover_tile_name(57.2, -179.9) == "ESA_WorldCover_10m_2021_v200_N57W180_Map.tif"


def test_disk_pixel_mask_area_matches_pi_r_squared():
    # Rule: pixel centre inside the disk when x^2 + y^2 <= R^2. 80 px of 100 m, R = 4000 m -> ~pi * 40^2 pixels.
    inside = fetch.disk_pixel_mask(80, 80, 100.0, 100.0, 4000.0)
    assert abs(int(inside.sum()) - math.pi * 40**2) / (math.pi * 40**2) < 0.01


def test_disk_share_counts_only_inside_pixels():
    import numpy as np

    values = np.zeros((10, 10), dtype="uint8")
    values[:, :5] = 60  # left half in the set
    inside = fetch.disk_pixel_mask(10, 10, 1.0, 1.0, 4.9)  # disk covers most of the array
    share = fetch.disk_share(values, (60, 70, 100), inside)
    manual = (values[inside] == 60).mean()
    assert share == pytest.approx(manual)
    assert fetch.disk_share(values, (60,), np.zeros((10, 10), dtype=bool)) is None


def test_disk_valid_fraction_counts_finite_pixels_inside_disk_only():
    # Rule: share of disk pixels with a finite value. Left half NaN: the disk is symmetric about x = 0 and no
    # pixel centre lies on x = 0, so the finite share is exactly 1/2. All NaN -> 0. Disk empty -> None.
    import numpy as np

    z = np.ones((80, 80))
    z[:, :40] = np.nan
    assert fetch.disk_valid_fraction(z, 100.0, 100.0, 4000.0) == pytest.approx(0.5)
    assert fetch.disk_valid_fraction(np.full((80, 80), np.nan), 100.0, 100.0, 4000.0) == 0.0
    assert fetch.disk_valid_fraction(z, 100.0, 100.0, 1.0) is None


def test_haversine_one_degree_on_equator():
    assert fetch.haversine_km(0.0, 0.0, 0.0, 1.0) == pytest.approx(111.195, abs=0.01)
    assert fetch.haversine_km(10.0, 20.0, 10.0, 20.0) == pytest.approx(0.0, abs=1e-9)


def test_grid_points_count_and_antimeridian_rule():
    pts = fetch.grid_points(10.0, -56.0, 60.0)
    lats = sorted({p[0] for p in pts})
    assert lats[0] == -56.0 and lats[-1] == 54.0  # 60 is not on the grid (-56 + 10 k)
    assert len(pts) == 12 * 36
    assert all(-180.0 <= lo < 180.0 for _, lo in pts)


def test_spacing_for_target_reproduces_target_count():
    p, target = 0.04, 2000
    d = fetch.spacing_for_target(p, target, -56.0, 60.0)
    expected = p * (360.0 / d) * ((60.0 + 56.0) / d)
    assert expected == pytest.approx(target, rel=1e-9)


def test_haversine_np_matches_scalar():
    import numpy as np

    rng = np.random.default_rng(20261114)
    lat1, lon1 = rng.uniform(-56, 60, 50), rng.uniform(-180, 180, 50)
    lat2, lon2 = rng.uniform(-56, 60, 50), rng.uniform(-180, 180, 50)
    vec = fetch.haversine_km_np(lat1, lon1, lat2, lon2)
    scalar = np.array([fetch.haversine_km(a, b, c, d) for a, b, c, d in zip(lat1, lon1, lat2, lon2)])
    assert np.allclose(vec, scalar, rtol=1e-12, atol=1e-9)
