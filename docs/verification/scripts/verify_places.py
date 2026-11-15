"""Verificacion independiente de lugar y pais de los gemelos (muestra).

Lector propio de shapefile (struct, stdlib pura): poligonos tipo 5 (admin-1) y
puntos tipo 1 (populated places), con .dbf. No importa nada del proyecto.
Muestra: semilla 20261114, 30 fichas (una por pais, paises elegidos por semilla),
mas las fichas con match distinto de 'inside' (max 10).
"""
import json
import math
import random
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NE_ADM1 = ROOT / "data/raw/reference/ne_10m_admin_1/ne_10m_admin_1_states_provinces"
NE_POP = ROOT / "data/raw/reference/ne_10m_populated_places/ne_10m_populated_places"
CARDS = ROOT / "site/data/cards"
RANKINGS = ROOT / "site/data/rankings"
DISCOVERIES = ROOT / "site/data/discoveries.json"
OUT = ROOT / "docs/verification"

SEED = 20261114
N_COUNTRY = 30
MAX_NON_INSIDE = 10
R_EARTH = 6371.0088
Z = 1.96


# ---------- lector shapefile ----------

def read_shp_index(path):
    data = path.read_bytes()
    assert struct.unpack(">i", data[0:4])[0] == 9994, "no es shapefile"
    flen = struct.unpack(">i", data[24:28])[0] * 2
    stype = struct.unpack("<i", data[32:36])[0]
    recs = []
    off = 100
    while off + 8 <= min(len(data), flen):
        _rnum, clen = struct.unpack(">ii", data[off:off + 8])
        cstart = off + 8
        cend = cstart + clen * 2
        st = struct.unpack("<i", data[cstart:cstart + 4])[0]
        recs.append({"st": st, "c": cstart})
        off = cend
    return data, stype, recs


def polygon_bbox(data, c):
    return struct.unpack("<4d", data[c + 4:c + 36])


def polygon_rings(data, c):
    nparts, npts = struct.unpack("<ii", data[c + 36:c + 44])
    parts = struct.unpack("<%di" % nparts, data[c + 44:c + 44 + 4 * nparts])
    p0 = c + 44 + 4 * nparts
    flat = struct.unpack("<%dd" % (2 * npts), data[p0:p0 + 16 * npts])
    xs, ys = flat[0::2], flat[1::2]
    bounds = list(parts) + [npts]
    return [(xs[bounds[i]:bounds[i + 1]], ys[bounds[i]:bounds[i + 1]]) for i in range(nparts)]


def point_in_rings(lon, lat, rings):
    """Ray casting (regla par-impar sobre todos los anillos: huecos quedan fuera)."""
    inside = False
    for xs, ys in rings:
        n = len(xs)
        j = n - 1
        for i in range(n):
            xi, yi, xj, yj = xs[i], ys[i], xs[j], ys[j]
            if (yi > lat) != (yj > lat):
                x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
                if lon < x_cross:
                    inside = not inside
            j = i
    return inside


def read_dbf(path, wanted):
    raw = path.read_bytes()
    nrec = struct.unpack("<I", raw[4:8])[0]
    hlen = struct.unpack("<H", raw[8:10])[0]
    rlen = struct.unpack("<H", raw[10:12])[0]
    cpg = Path(str(path)[:-4] + ".cpg")
    enc = cpg.read_text().strip() if cpg.exists() else "utf-8"
    enc = "utf-8" if enc.upper().startswith("UTF") else enc
    fields = []
    off = 32
    pos = 1  # byte 0 = marca de borrado
    while raw[off] != 0x0D:
        name = raw[off:off + 11].split(b"\x00")[0].decode("ascii")
        flen = raw[off + 16]
        fields.append((name, pos, flen))
        pos += flen
        off += 32
    rows = []
    for r in range(nrec):
        base = hlen + r * rlen
        row = raw[base:base + rlen]
        if row[0:1] == b"*":
            rows.append(None)
            continue
        d = {}
        for name, p, flen in fields:
            if name in wanted:
                d[name] = row[p:p + flen].split(b"\x00")[0].decode(enc, errors="replace").strip()
        rows.append(d)
    return rows


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(a))


def wilson(k, n):
    p = k / n
    z2 = Z * Z
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    margin = Z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return p, max(0.0, centre - margin), min(1.0, centre + margin)


# ---------- datos del proyecto (solo lectura) ----------

def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def main():
    # coordenadas del gemelo: rankings (analog_id -> lat/lon)
    coords = {}
    for f in sorted(RANKINGS.glob("*.json")):
        r = load_json(f)
        for e in r["ranking"]:
            coords[e["analog_id"]] = {"target_id": r["target_id"], "lat": e["lat"], "lon": e["lon"],
                                      "ranking_file": f.name}
    # coordenadas de discoveries (para comparar)
    disc = load_json(DISCOVERIES)
    disc_coords = {}
    for w in disc["windows"]:
        disc_coords.setdefault(w["analog_id"], []).append((w["lat"], w["lon"]))

    cards = {}
    for f in sorted(CARDS.glob("*.json")):
        c = load_json(f)
        cards[f.name] = c

    # ---------- muestra ----------
    by_country = {}
    for name, c in cards.items():
        by_country.setdefault(c["analog_place"]["country"], []).append(name)
    countries = sorted(by_country)
    rng = random.Random(SEED)
    chosen_countries = sorted(rng.sample(countries, min(N_COUNTRY, len(countries))))
    sample_country = [(c, rng.choice(sorted(by_country[c]))) for c in chosen_countries]
    uncovered = sorted(set(countries) - set(chosen_countries))
    non_inside = sorted(n for n, c in cards.items() if c["analog_place"]["match"] != "inside")
    non_inside_pick = non_inside[:MAX_NON_INSIDE]
    sample = [(c, n, "pais") for c, n in sample_country] + [
        (cards[n]["analog_place"]["country"], n, "no_inside") for n in non_inside_pick]

    # ---------- shapefiles ----------
    adm_data, adm_type, adm_recs = read_shp_index(NE_ADM1.with_suffix(".shp"))
    assert adm_type == 5, adm_type
    adm_rows = read_dbf(NE_ADM1.with_suffix(".dbf"), {"name", "admin"})
    assert len(adm_rows) == len(adm_recs), (len(adm_rows), len(adm_recs))
    adm_bbox = [polygon_bbox(adm_data, r["c"]) if r["st"] == 5 else None for r in adm_recs]

    pop_data, pop_type, pop_recs = read_shp_index(NE_POP.with_suffix(".shp"))
    assert pop_type == 1, pop_type
    pop_rows = read_dbf(NE_POP.with_suffix(".dbf"), {"NAME", "ADM0NAME", "ADM1NAME"})
    assert len(pop_rows) == len(pop_recs), (len(pop_rows), len(pop_recs))
    towns = []
    for r, row in zip(pop_recs, pop_rows):
        if r["st"] != 1 or row is None:
            continue
        x, y = struct.unpack("<dd", pop_data[r["c"] + 4:r["c"] + 20])
        towns.append((y, x, row["NAME"], row["ADM0NAME"], row["ADM1NAME"]))

    results = []
    for stratum, name, kind in [(s[0], s[1], s[2]) for s in sample]:
        card = cards[name]
        ap = card["analog_place"]
        nt = card["context"]["nearest_town"]
        cc = coords[card["analog_id"]]
        lat, lon = cc["lat"], cc["lon"]

        # admin-1: punto en poligono (bbox primero)
        hits = []
        for i, r in enumerate(adm_recs):
            if r["st"] != 5:
                continue
            x0, y0, x1, y1 = adm_bbox[i]
            if not (x0 <= lon <= x1 and y0 <= lat <= y1):
                continue
            if point_in_rings(lon, lat, polygon_rings(adm_data, r["c"])):
                hits.append(i)
        if hits:
            rec_admin1 = adm_rows[hits[0]]["name"]
            rec_country = adm_rows[hits[0]]["admin"]
            rec_match = "inside"
        else:
            rec_admin1 = None
            rec_country = None
            rec_match = "not_inside"

        # pueblo mas cercano: haversine sobre todos los puntos
        best = None
        ties = 0
        for ty, tx, tname, tcountry, _t1 in towns:
            d = haversine(lat, lon, ty, tx)
            if best is None or d < best[0] - 1e-9:
                best = (d, tname, tcountry)
                ties = 1
            elif abs(d - best[0]) <= 1e-9:
                ties += 1
        rec_dist, rec_town, rec_town_country = best

        disc_pts = disc_coords.get(card["analog_id"], [])
        disc_diff = None
        if disc_pts:
            disc_diff = round(max(haversine(lat, lon, a, b) for a, b in disc_pts), 3)

        ok = {
            "admin1": rec_admin1 == ap["admin1"],
            "country": rec_country == ap["country"],
            "match": rec_match == ap["match"],
            "nearest_town_name": rec_town == nt["name"],
            "nearest_town_country": rec_town_country == nt["country"],
            "nearest_town_distance": abs(rec_dist - nt["distance_km"]) <= 1.0,
        }
        results.append({
            "stratum": stratum,
            "why": kind,
            "card": name,
            "target_id": card["target_id"],
            "analog_id": card["analog_id"],
            "lat": lat,
            "lon": lon,
            "coord_source": cc["ranking_file"],
            "discoveries_max_diff_km": disc_diff,
            "ficha": {
                "admin1": ap["admin1"], "country": ap["country"], "match": ap["match"],
                "nearest_town": {"name": nt["name"], "country": nt["country"],
                                 "distance_km": nt["distance_km"]},
            },
            "recomputado": {
                "admin1": rec_admin1, "country": rec_country, "match": rec_match,
                "nearest_town": {"name": rec_town, "country": rec_town_country,
                                 "distance_km": round(rec_dist, 3), "ties_at_min": ties},
            },
            "ok": ok,
        })

    fields = ["admin1", "country", "match", "nearest_town_name", "nearest_town_country",
              "nearest_town_distance"]
    n = len(results)
    stats = {}
    for f in fields:
        k = sum(1 for r in results if r["ok"][f])
        p, lo, hi = wilson(k, n) if n else (0, 0, 0)
        stats[f] = {"k": k, "n": n, "p": round(p, 4), "wilson95_low": round(lo, 4),
                    "wilson95_high": round(hi, 4)}

    out = {
        "seed": SEED,
        "design": {
            "estrato": "pais del gemelo (analog_place.country)",
            "paises_totales": len(countries),
            "paises_cubiertos": len(chosen_countries),
            "paises_no_cubiertos": uncovered,
            "regla": "1 ficha por pais para 30 paises elegidos con random.Random(20261114).sample; "
                     "ficha dentro del pais elegida con rng.choice sobre nombres ordenados",
            "fichas_match_no_inside_en_cards": len(non_inside),
            "n_total": n,
        },
        "stats": stats,
        "results": results,
        "fuentes": {
            "admin1": "data/raw/reference/ne_10m_admin_1 (name, admin), Natural Earth 5.1.1",
            "populated_places": "data/raw/reference/ne_10m_populated_places (NAME, ADM0NAME), 5.1.2",
            "coords": "site/data/rankings/<target>.json (lat/lon por analog_id)",
        },
    }
    (OUT / "places_sample.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- markdown ----------
    L = []
    L.append("# Verificacion independiente: lugar y pais de los gemelos (muestra)")
    L.append("")
    L.append("Lector propio de shapefile (Python puro, struct). Admin-1 Natural Earth 5.1.1 y "
             "populated places Natural Earth 5.1.2. Semilla 20261114.")
    L.append("")
    L.append("## Diseno de muestra")
    L.append("")
    L.append(f"- Estrato: pais del gemelo. {len(countries)} paises en las 160 fichas; "
             f"n={N_COUNTRY} no alcanza para cubrir todos, se cubren {len(chosen_countries)} "
             f"con 1 ficha cada uno (max 3 por pais no obliga). No cubiertos (sorteo): "
             + ", ".join(uncovered) + ".")
    L.append(f"- Fichas con match distinto de 'inside': {len(non_inside)} de 160 (estrato vacio, "
             "0 de 10 posibles).")
    L.append(f"- n total = {n}.")
    L.append("")
    L.append("## Tasas (Wilson 95%)")
    L.append("")
    L.append("| Campo | k/n | p | Wilson 95% |")
    L.append("|---|---|---|---|")
    for f in fields:
        s = stats[f]
        L.append(f"| {f} | {s['k']}/{s['n']} | {s['p']:.3f} | [{s['wilson95_low']:.3f}, {s['wilson95_high']:.3f}] |")
    L.append("")
    L.append("## Discrepancias")
    L.append("")
    disc_rows = [r for r in results if not all(r["ok"].values())]
    if not disc_rows:
        L.append("Ninguna.")
    for r in disc_rows:
        bad = [f for f in r["ok"] if not r["ok"][f]]
        L.append(f"- `{r['card']}` ({r['target_id']}, lat {r['lat']}, lon {r['lon']}): "
                 + "; ".join(
                     f"{f}: ficha={_get(r['ficha'], f)} / recomp={_get(r['recomputado'], f)}"
                     for f in bad))
    L.append("")
    L.append("## Detalle")
    L.append("")
    L.append("| estrato | ficha | admin1 | country | match | pueblo ficha | pueblo recomp | km ficha | km recomp |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        f_ = r["ficha"]
        g_ = r["recomputado"]
        L.append(f"| {r['stratum']} | {r['card']} | {f_['admin1']} / {g_['admin1']} | "
                 f"{f_['country']} / {g_['country']} | {f_['match']} / {g_['match']} | "
                 f"{f_['nearest_town']['name']} ({f_['nearest_town']['country']}) | "
                 f"{g_['nearest_town']['name']} ({g_['nearest_town']['country']}) | "
                 f"{f_['nearest_town']['distance_km']} | {g_['nearest_town']['distance_km']} |")
    (OUT / "places_sample.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    print(json.dumps({"n": n, "stats": stats,
                      "discrepancias": [r["card"] for r in disc_rows]}, ensure_ascii=False, indent=1))


def _get(d, f):
    if f.startswith("nearest_town_"):
        key = f[len("nearest_town_"):]
        key = {"name": "name", "country": "country", "distance": "distance_km"}[key]
        return d["nearest_town"][key]
    return d[f]


if __name__ == "__main__":
    main()
