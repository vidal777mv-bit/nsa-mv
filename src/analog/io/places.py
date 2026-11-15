"""Offline reverse geocoding of analog window centres (STANDARDS 10.12).

Source: Natural Earth 1:10m admin-1 states/provinces (public domain), an ESRI shapefile (.shp/.shx/.dbf), read here
without GDAL: polygon records only, WGS84 longitude/latitude. Lookup rule:
1. inside: the point lies in a polygon (even-odd over all rings of the record, so holes are respected);
2. nearest: otherwise the nearest polygon boundary within ``max_km`` (great-circle distance to the nearest boundary point);
3. otherwise None. Nothing is invented: a point with no polygon within the limit has no name.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import nearest_points

EARTH_RADIUS_KM = 6371.0088
POLYGON_TYPES = (5, 15, 25)  # Polygon, PolygonZ, PolygonM
NEAREST_KM = 50.0


def _decode(raw: bytes, encoding: str) -> str:
    return raw.split(b"\x00", 1)[0].decode(encoding, errors="replace").strip()


def read_dbf(path: Path, encoding: str = "utf-8") -> list[dict[str, Any]]:
    """Attribute records of a dBASE III file (character and numeric fields; deleted records are dropped)."""
    data = path.read_bytes()
    n_rec = struct.unpack("<I", data[4:8])[0]
    hdr_len = struct.unpack("<H", data[8:10])[0]
    rec_len = struct.unpack("<H", data[10:12])[0]
    fields: list[tuple[str, int]] = []
    off = 32
    while data[off] != 0x0D:
        name = _decode(data[off:off + 11], "ascii")
        fields.append((name, data[off + 16]))
        off += 32
    out: list[dict[str, Any]] = []
    for i in range(n_rec):
        row = data[hdr_len + i * rec_len: hdr_len + (i + 1) * rec_len]
        if row[:1] == b"*":
            continue
        pos = 1
        rec: dict[str, Any] = {}
        for name, length in fields:
            rec[name] = _decode(row[pos:pos + length], encoding)
            pos += length
        out.append(rec)
    return out


@dataclass
class Polygon2D:
    """One polygon record: bounding box, rings (lon, lat arrays) and its attributes."""

    bbox: tuple[float, float, float, float]
    rings: list[np.ndarray]
    attrs: dict[str, Any]
    _polys: list[Polygon] | None = field(default=None, repr=False)

    def polys(self) -> list[Polygon]:
        """Shapely rings (built on first use)."""
        if self._polys is None:
            self._polys = [Polygon(r) for r in self.rings if len(r) >= 4]
        return self._polys


def read_shp_polygons(path: Path, attrs: list[dict[str, Any]]) -> list[Polygon2D]:
    """Polygon records of an ESRI shapefile, paired with the attribute records by position.

    Raises ValueError for a shape type other than polygon (the admin-1 file is polygon only) or a record count that
    does not match the dBASE file.
    """
    data = path.read_bytes()
    shp_type = struct.unpack("<i", data[32:36])[0]
    if shp_type not in POLYGON_TYPES:
        raise ValueError(f"shapefile type {shp_type} is not polygon")
    out: list[Polygon2D] = []
    off = 100
    idx = 0
    while off + 8 <= len(data):
        _, content_words = struct.unpack(">ii", data[off:off + 8])
        body = data[off + 8: off + 8 + 2 * content_words]
        off += 8 + 2 * content_words
        stype = struct.unpack("<i", body[:4])[0]
        if stype == 0:  # null shape: keeps its place in the attribute table
            idx += 1
            continue
        if stype not in POLYGON_TYPES:
            raise ValueError(f"record {idx} has shape type {stype}")
        bbox = struct.unpack("<4d", body[4:36])
        n_parts, n_pts = struct.unpack("<ii", body[36:44])
        parts = np.frombuffer(body, dtype="<i4", count=n_parts, offset=44)
        pts = np.frombuffer(body, dtype="<f8", count=2 * n_pts, offset=44 + 4 * n_parts).reshape(n_pts, 2)
        bounds = list(parts) + [n_pts]
        rings = [pts[bounds[k]:bounds[k + 1]] for k in range(n_parts)]
        out.append(Polygon2D(bbox=bbox, rings=rings, attrs=attrs[idx] if idx < len(attrs) else {}))
        idx += 1
    if len(out) and idx != len(attrs):
        raise ValueError(f"shapefile has {idx} records, dBASE has {len(attrs)}")
    return out


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km (mean Earth radius)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


class PlaceIndex:
    """Admin-1 polygons with the lookup rule of the module docstring. name_field / country_field are the NE columns."""

    def __init__(self, polygons: list[Polygon2D], name_field: str = "name", country_field: str = "admin",
                 source: str = "") -> None:
        self.polygons = polygons
        self.name_field = name_field
        self.country_field = country_field
        self.source = source

    def _record(self, polygon: Polygon2D, how: str, km: float) -> dict[str, Any]:
        admin1 = str(polygon.attrs.get(self.name_field) or "").strip() or None
        country = str(polygon.attrs.get(self.country_field) or "").strip() or None
        name = ", ".join(x for x in (admin1, country) if x) or None
        return {"name": name, "admin1": admin1, "country": country, "source": self.source,
                "match": how, "distance_km": round(km, 3)}

    def lookup(self, lat: float, lon: float, max_km: float = NEAREST_KM) -> dict[str, Any] | None:
        """Place of a point: inside a polygon, else the nearest polygon within max_km, else None."""
        x, y = float(lon), float(lat)
        for pg in self.polygons:
            minx, miny, maxx, maxy = pg.bbox
            if not (minx <= x <= maxx and miny <= y <= maxy):
                continue
            hits = sum(1 for poly in pg.polys() if poly.covers(Point(x, y)))  # even-odd: holes count as outside
            if hits % 2 == 1:
                return self._record(pg, "inside", 0.0)
        # nearest boundary within max_km: candidates are polygons whose bbox lies within a padded box
        dlat = max_km / 111.2
        dlon = max_km / (111.2 * max(math.cos(math.radians(lat)), 0.05))
        best: tuple[float, Polygon2D] | None = None
        for pg in self.polygons:
            minx, miny, maxx, maxy = pg.bbox
            if maxx < x - dlon or minx > x + dlon or maxy < y - dlat or miny > y + dlat:
                continue
            lines = MultiLineString([LineString(r) for r in pg.rings if len(r) >= 2])
            p_on = nearest_points(lines, Point(x, y))[0]
            km = haversine_km(y, x, p_on.y, p_on.x)
            if km <= max_km and (best is None or km < best[0]):
                best = (km, pg)
        if best is None:
            return None
        return self._record(best[1], "nearest", best[0])


def load_admin1(shp_path: Path, source_label: str) -> PlaceIndex:
    """Read the shapefile and its .dbf (same stem, UTF-8) into a PlaceIndex."""
    attrs = read_dbf(shp_path.with_suffix(".dbf"))
    polys = read_shp_polygons(shp_path, attrs)
    return PlaceIndex(polys, source=source_label)


def read_shp_points(path: Path, attrs: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """Point records of an ESRI shapefile (type 1, WGS84): (lat array, lon array, attributes of the kept records).

    Null shapes are skipped with their attributes. Raises ValueError for a non-point shape type or a record count that
    does not match the dBASE file.
    """
    data = path.read_bytes()
    shp_type = struct.unpack("<i", data[32:36])[0]
    if shp_type != 1:
        raise ValueError(f"shapefile type {shp_type} is not point")
    lats: list[float] = []
    lons: list[float] = []
    kept: list[dict[str, Any]] = []
    off = 100
    idx = 0
    while off + 8 <= len(data):
        _, content_words = struct.unpack(">ii", data[off:off + 8])
        body = data[off + 8: off + 8 + 2 * content_words]
        off += 8 + 2 * content_words
        stype = struct.unpack("<i", body[:4])[0]
        if stype == 1:
            x, y = struct.unpack("<dd", body[4:20])
            lons.append(x)
            lats.append(y)
            kept.append(attrs[idx] if idx < len(attrs) else {})
        idx += 1
    if idx != len(attrs):
        raise ValueError(f"shapefile has {idx} records, dBASE has {len(attrs)}")
    return np.array(lats, dtype=float), np.array(lons, dtype=float), kept


def nearest_point_km(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> tuple[int, float]:
    """Index and great-circle distance (km) of the point nearest to (lat, lon). Raises ValueError when there are no points."""
    if lats.size == 0:
        raise ValueError("no points")
    p1 = np.radians(lat)
    p2 = np.radians(lats)
    dp = p2 - p1
    dl = np.radians(lons - lon)
    h = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    d = 2 * EARTH_RADIUS_KM * np.arcsin(np.minimum(1.0, np.sqrt(h)))
    i = int(np.argmin(d))
    return i, float(d[i])


__all__ = ["PlaceIndex", "load_admin1", "read_dbf", "read_shp_polygons", "read_shp_points", "nearest_point_km", "haversine_km", "NEAREST_KM"]
