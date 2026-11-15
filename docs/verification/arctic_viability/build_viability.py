"""Hechos de viabilidad: gemelos articos vs contraste no arctico. Sin puntajes.

Solo lee data/, site/ y config/ del proyecto. Escribe viability.json y viability.md
en docs/verification/arctic_viability/. Lector shapefile copiado de
docs/verification/scripts/verify_places.py (stdlib pura, no importa el proyecto).
"""
import json
import math
import random
import re
import statistics
import struct
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "docs/verification/arctic_viability"
NE_ADM1 = ROOT / "data/raw/reference/ne_10m_admin_1/ne_10m_admin_1_states_provinces"
NE_AIR = OUT / "cache/ne_airports/ne_10m_airports"
NE_PORT = OUT / "cache/ne_ports/ne_10m_ports"
SEED = 20261114
R_EARTH = 6371.0088
Z = 1.96
N_MAX = 79
# Estacion HMP: 75o 26' N, 89o 52' W (marsinstitute.no/hmp, leido 2026-11-14)
HMP_LAT = 75 + 26 / 60
HMP_LON = -(89 + 52 / 60)


# ---------- lector shapefile (copiado de verify_places.py) ----------

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
    pos = 1
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


def read_points(shp, wanted):
    data, stype, recs = read_shp_index(shp.with_suffix(".shp"))
    assert stype == 1, stype
    rows = read_dbf(shp.with_suffix(".dbf"), wanted)
    assert len(rows) == len(recs), (len(rows), len(recs))
    out = []
    for r, row in zip(recs, rows):
        if r["st"] != 1 or row is None:
            continue
        x, y = struct.unpack("<dd", data[r["c"] + 4:r["c"] + 20])
        out.append((y, x, row))
    return out


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


def pct(k, n):
    p, lo, hi = wilson(k, n)
    return {"k": k, "n": n, "pct": round(100 * p, 1), "ic95": [round(100 * lo, 1), round(100 * hi, 1)]}


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def pool_num(s):
    return int(re.search(r"pool_(\d+)$", s).group(1))


def pool_key(s):
    return "pool_%05d" % pool_num(s)


def nearest(lat, lon, pts):
    best = None
    for y, x, row in pts:
        d = haversine(lat, lon, y, x)
        if best is None or d < best[0]:
            best = (d, row)
    return best


def main():
    # ---------- poblaciones ----------
    census = load(ROOT / "docs/verification/arctic_top10/arctic_top10.json")
    shares = load(ROOT / "data/derived/pool_rules/shares.json")["windows"]

    top10 = defaultdict(list)
    top1_sites = defaultdict(list)
    for f in sorted((ROOT / "site/data/rankings").glob("*.json")):
        r = load(f)
        for e in r["ranking"]:
            if e["rank"] > 10:
                continue
            k = pool_key(e["analog_id"])
            top10[k].append({"site": r["target_id"], "rank": e["rank"], "analog_id": e["analog_id"],
                             "lat": e["lat"], "lon": e["lon"], "card": e.get("card"),
                             "ranking_file": f.name, "ranking_context": e.get("context")})
            if e["rank"] == 1:
                top1_sites[k].append(r["target_id"])

    arctic_keys = sorted({pool_key(f["analog_id"]) for f in census["filas"]})
    assert len(arctic_keys) == 79, len(arctic_keys)
    assert set(arctic_keys) == {k for k in top10 if pool_num(k) > 2000}, "censo != rankings"
    contrast_all = sorted(k for k in top10 if pool_num(k) <= 2000)
    rng = random.Random(SEED)
    contrast_keys = sorted(rng.sample(contrast_all, min(N_MAX, len(contrast_all))))

    census_by_key = {}
    for f in census["filas"]:
        census_by_key.setdefault(pool_key(f["analog_id"]), f)

    # ---------- datos de aeropuertos, puertos, admin-1 ----------
    airports = read_points(NE_AIR, {"name", "iata_code", "type", "featurecla"})
    ports = read_points(NE_PORT, {"name"})
    adm_data, adm_type, adm_recs = read_shp_index(NE_ADM1.with_suffix(".shp"))
    assert adm_type == 5, adm_type
    adm_rows = read_dbf(NE_ADM1.with_suffix(".dbf"), {"name", "admin", "type", "type_en"})
    assert len(adm_rows) == len(adm_recs)
    adm_bbox = [polygon_bbox(adm_data, r["c"]) if r["st"] == 5 else None for r in adm_recs]

    # ---------- centros de regiones analogas conocidas ----------
    centers = []
    for x in load(ROOT / "config/known_analog_regions.json")["regions"]:
        centers.append({"id": x["id"], "nombre": x["name"], "lat": x["lat"], "lon": x["lon"],
                        "radio_km": x.get("radius_km"), "fuente": "config/known_analog_regions.json"})
    for x in load(ROOT / "config/regions.json")["regions"]:
        if x.get("role") == "known_analog":
            centers.append({"id": x["id"], "nombre": x["name"], "lat": x["lat"], "lon": x["lon"],
                            "radio_km": None, "fuente": "config/regions.json role=known_analog"})

    # ---------- fila por lugar ----------
    def build_row(key, grupo):
        appear = sorted(top10[key], key=lambda a: (a["rank"], a["site"]))
        first = appear[0]
        if grupo == "ARTICO":
            cf = census_by_key[key]
            lat, lon = cf["lat"], cf["lon"]
        else:
            lat, lon = first["lat"], first["lon"]
        # conflictos de coordenadas entre apariciones
        conf_km = max(haversine(lat, lon, a["lat"], a["lon"]) for a in appear)

        sh = shares[key]
        ice = sh["ice_share"]
        bare = sh["bare_share_full"]
        census_ice_diff = None
        if grupo == "ARTICO":
            census_ice_diff = round(abs(census_by_key[key]["ice_share"] - ice), 6)

        # ficha (card) de la primera aparicion con card
        card_rel = next((a["card"] for a in appear if a.get("card")), None)
        card = load(ROOT / "site/data" / card_rel) if card_rel else None
        if card:
            ctx = card["context"]
            koppen = {"clase": ctx["koppen_class"], "etiqueta": ctx["koppen_label"],
                      "fuente": "site/data/" + card_rel + " context.koppen_class (Beck et al. 2018)"}
            nt = ctx["nearest_town"]
            pueblo = {"nombre": nt["name"], "pais": nt["country"], "km": nt["distance_km"],
                      "fuente": "site/data/" + card_rel + " context.nearest_town (Natural Earth populated places)"}
            card_admin1 = card["analog_place"]["admin1"]
            card_country = card["analog_place"]["country"]
        else:
            koppen = {"clase": None, "etiqueta": None, "fuente": None}
            pueblo = {"nombre": None, "pais": None, "km": None, "fuente": None}
            card_admin1 = card_country = None
        koppen_all = sorted({a["ranking_context"]["koppen_class"] for a in appear
                             if a.get("ranking_context") and "koppen_class" in a["ranking_context"]})

        d, air = nearest(lat, lon, airports)
        air_row = air
        aeropuerto = {"nombre": air_row["name"], "iata": air_row["iata_code"] or None,
                      "tipo": air_row["type"], "km": round(d, 1),
                      "fuente": "Natural Earth 1:10m airports (ne_10m_airports.zip, dominio publico)"}
        dp, port = nearest(lat, lon, ports)
        puerto = {"nombre": port["name"], "km": round(dp, 1),
                  "fuente": "Natural Earth 1:10m ports (ne_10m_ports.zip, dominio publico)"}

        hits = []
        for i, r in enumerate(adm_recs):
            if r["st"] != 5:
                continue
            x0, y0, x1, y1 = adm_bbox[i]
            if not (x0 <= lon <= x1 and y0 <= lat <= y1):
                continue
            if point_in_rings(lon, lat, polygon_rings(adm_data, r["c"])):
                row = adm_rows[i]
                hits.append({"name": row["name"], "admin": row["admin"], "type": row["type"],
                             "type_en": row["type_en"]})
        protegida = any(
            ("national park" in (h["type"] or "").lower() or "national park" in (h["type_en"] or "").lower())
            or h["name"] == "Nationalparken"
            for h in hits)
        area = {"poligonos": hits, "protegida": protegida,
                "regla": "type/type_en contiene 'National Park' o name == 'Nationalparken'",
                "fuente": "Natural Earth 1:10m admin-1 v5.1.1 (data/raw/reference/ne_10m_admin_1)"}

        best_c = None
        inside_radio = []
        for c in centers:
            dc = haversine(lat, lon, c["lat"], c["lon"])
            if best_c is None or dc < best_c[0]:
                best_c = (dc, c)
            if c["radio_km"] and dc <= c["radio_km"]:
                inside_radio.append(c["nombre"])
        region = {"nombre": best_c[1]["nombre"], "km_centro": round(best_c[0], 1),
                  "fuente": best_c[1]["fuente"], "dentro_de_radio_conocido": inside_radio}

        hmp_km = round(haversine(lat, lon, HMP_LAT, HMP_LON), 1)

        return {
            "grupo": grupo,
            "pool": key,
            "analog_id": "pool__" + key,
            "lat": lat,
            "lon": lon,
            "coords_conflicto_max_km": round(conf_km, 3),
            "apariciones_top10": [{"site": a["site"], "rank": a["rank"]} for a in appear],
            "top1_de": sorted(top1_sites.get(key, [])),
            "ice_share": ice,
            "bare_share_full": bare,
            "ice_share_vs_censo_diff": census_ice_diff,
            "koppen": koppen,
            "koppen_en_ranking": koppen_all,
            "pueblo_mas_cercano": pueblo,
            "aeropuerto_mas_cercano": aeropuerto,
            "puerto_mas_cercano": puerto,
            "area_admin1": area,
            "admin1_coincide_con_ficha": (hits[0]["name"] == card_admin1) if (hits and card_admin1) else None,
            "pais_ficha": card_country,
            "region_analoga_conocida_mas_cercana": region,
            "estacion_HMP_km": hmp_km,
        }

    rows = [build_row(k, "ARTICO") for k in arctic_keys] + [build_row(k, "CONTRASTE") for k in contrast_keys]

    # ---------- resumen ----------
    def summarize(group):
        n = len(group)
        towns = [r["pueblo_mas_cercano"]["km"] for r in group if r["pueblo_mas_cercano"]["km"] is not None]
        airs = [r["aeropuerto_mas_cercano"]["km"] for r in group]
        kc = Counter(r["koppen"]["clase"] for r in group)
        return {
            "n": n,
            "km_pueblo": {"mediana": round(statistics.median(towns), 1), "min": round(min(towns), 1),
                          "max": round(max(towns), 1)},
            "km_aeropuerto": {"mediana": round(statistics.median(airs), 1), "min": round(min(airs), 1),
                              "max": round(max(airs), 1)},
            "ice_share_ge_0_1": pct(sum(1 for r in group if r["ice_share"] >= 0.1), n),
            "koppen": {k: pct(v, n) for k, v in sorted(kc.items(), key=lambda kv: str(kv[0]))},
            "area_protegida": pct(sum(1 for r in group if r["area_admin1"]["protegida"]), n),
            "menos_100km_region_analoga_centro": pct(
                sum(1 for r in group if r["region_analoga_conocida_mas_cercana"]["km_centro"] < 100), n),
            "menos_100km_aeropuerto": pct(sum(1 for r in group if r["aeropuerto_mas_cercano"]["km"] < 100), n),
        }

    arc = [r for r in rows if r["grupo"] == "ARTICO"]
    con = [r for r in rows if r["grupo"] == "CONTRASTE"]
    resumen = {"ARTICO": summarize(arc), "CONTRASTE": summarize(con)}

    top1_arc = [r for r in arc if r["top1_de"]]
    arc_sin_protec_100 = sorted(
        [r for r in arc if r["aeropuerto_mas_cercano"]["km"] < 100 and not r["area_admin1"]["protegida"]],
        key=lambda r: r["aeropuerto_mas_cercano"]["km"])

    checks = {
        "arcticos_n": len(arc),
        "contraste_n": len(con),
        "contraste_candidatos_distintos": len(contrast_all),
        "arcticos_coords_conflicto_max_km": max(r["coords_conflicto_max_km"] for r in arc),
        "ice_vs_censo_max_diff": max(r["ice_share_vs_censo_diff"] for r in arc),
        "admin1_vs_ficha_coinciden": Counter(str(r["admin1_coincide_con_ficha"]) for r in rows),
        "sin_ficha": sum(1 for r in rows if r["koppen"]["clase"] is None),
        "koppen_ranking_inconsistente": sum(1 for r in rows if len(r["koppen_en_ranking"]) > 1),
    }

    fuentes = {
        "ice_share, bare_share_full": "data/derived/pool_rules/shares.json (ESA WorldCover 2021 v200, provenance.inputs)",
        "koppen": "site/data/cards/*.json context.koppen_class; leyenda data/raw/reference/koppen/legend.txt (Beck et al. 2018, Sci Data)",
        "pueblo": "site/data/cards/*.json context.nearest_town (Natural Earth 10m populated places, v5.1.2)",
        "aeropuerto": "docs/verification/arctic_viability/cache/ne_airports/ne_10m_airports.zip (Natural Earth 10m, dominio publico) https://naciscdn.org/naturalearth/10m/cultural/ne_10m_airports.zip",
        "puerto": "docs/verification/arctic_viability/cache/ne_ports/ne_10m_ports.zip https://naciscdn.org/naturalearth/10m/cultural/ne_10m_ports.zip",
        "area_protegida": "data/raw/reference/ne_10m_admin_1 v5.1.1 (Natural Earth, dominio publico)",
        "region_analoga": "config/known_analog_regions.json + config/regions.json role=known_analog",
        "HMP": "https://www.marsinstitute.no/hmp : 'located at 75o 26' N, 89o 52' W, in the northwestern rim area of Haughton Crater'; establecida 2000 (texto verificado)",
        "permiso_parque_NE_groenlandia": {
            "estado": "NO VERIFICADO TEXTUALMENTE",
            "motivo": "Los PDF de naalakkersuisut.gl y zackenberg.dk devolvieron binario ilegible en 2 intentos (WebFetch). Solo hay URLs halladas por busqueda.",
            "urls_halladas": [
                "https://eastgreenland.com/rules-regulations/",
                "https://zackenberg.dk/fileadmin/g-e-m/Zackenberg/KNNO_Expedition_Permit_No._D-26-03_with_National_Park_access_web.pdf",
                "https://naalakkersuisut.gl/-/media/nyheder/2025/09/advisory-against-travel-in-dickson-fjord-west-of-ella-island-and-the-consideration-of-the-national-p.pdf"],
            "afirmacion_de_busqueda_no_verificada": "Permiso del Gobierno de Groenlandia requerido para entrar al parque (Executive Order No. 7, 17-jun-1992).",
        },
    }

    result = {
        "meta": {"seed": SEED, "contraste_regla": "pool_NNNNN <= 2000 en top 10 de site/data/rankings; todos si hay menos de 79",
                 "arctico_regla": "79 gemelos unicos de docs/verification/arctic_top10/arctic_top10.json",
                 "sin_puntajes": True},
        "checks": checks,
        "resumen": resumen,
        "top1_arcticos": top1_arc,
        "arcticos_menos_100km_aeropuerto_fuera_protegida": [r["pool"] for r in arc_sin_protec_100],
        "fuentes": fuentes,
        "lugares": rows,
    }
    (OUT / "viability.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    write_md(result)
    print(json.dumps({"checks": checks, "resumen": resumen}, ensure_ascii=False, indent=1, default=str))


def fmt_pct(d):
    return "%s%% (%d/%d; IC95 %s-%s%%)" % (d["pct"], d["k"], d["n"], d["ic95"][0], d["ic95"][1])


def write_md(res):
    s = res["resumen"]
    A, C = s["ARTICO"], s["CONTRASTE"]
    L = []
    L.append("# Viabilidad fisica en gemelos articos: hechos vs contraste")
    L.append("")
    L.append("Solo hechos con fuente (ver viability.json, campo `fuentes`). Sin indices ni puntajes. "
             "Muestra: %d gemelos articos (censo arctic_top10) y %d contrastes no articos (todos los "
             "candidatos top 10 con pool_NNNNN <= 2000; menos de 79, asi que no hubo muestreo)."
             % (A["n"], C["n"]))
    L.append("")
    L.append("## Tabla resumen")
    L.append("")
    L.append("| Hecho | ARTICO | CONTRASTE |")
    L.append("|---|---|---|")
    L.append("| Km al pueblo mas cercano, mediana (rango) | %s (%s-%s) | %s (%s-%s) |" % (
        A["km_pueblo"]["mediana"], A["km_pueblo"]["min"], A["km_pueblo"]["max"],
        C["km_pueblo"]["mediana"], C["km_pueblo"]["min"], C["km_pueblo"]["max"]))
    L.append("| Km al aeropuerto mas cercano, mediana (rango) | %s (%s-%s) | %s (%s-%s) |" % (
        A["km_aeropuerto"]["mediana"], A["km_aeropuerto"]["min"], A["km_aeropuerto"]["max"],
        C["km_aeropuerto"]["mediana"], C["km_aeropuerto"]["min"], C["km_aeropuerto"]["max"]))
    L.append("| ice_share >= 0.1 | %s | %s |" % (fmt_pct(A["ice_share_ge_0_1"]), fmt_pct(C["ice_share_ge_0_1"])))
    kA, kC = A["koppen"], C["koppen"]
    for cls in sorted(set(kA) | set(kC)):
        a = fmt_pct(kA[cls]) if cls in kA else "0"
        c = fmt_pct(kC[cls]) if cls in kC else "0"
        L.append("| Koppen %s | %s | %s |" % (cls, a, c))
    L.append("| En area protegida (admin-1) | %s | %s |" % (fmt_pct(A["area_protegida"]), fmt_pct(C["area_protegida"])))
    L.append("| A menos de 100 km del centro de una region analoga conocida | %s | %s |" % (
        fmt_pct(A["menos_100km_region_analoga_centro"]), fmt_pct(C["menos_100km_region_analoga_centro"])))
    L.append("| A menos de 100 km de un aeropuerto | %s | %s |" % (
        fmt_pct(A["menos_100km_aeropuerto"]), fmt_pct(C["menos_100km_aeropuerto"])))
    L.append("")
    L.append("Koppen ET = Polar, tundra; EF = Polar, frost (leyenda Beck et al. 2018). Es clasificacion climatica, no meses.")
    L.append("")
    L.append("## Top 1 arcticos (con todos sus hechos)")
    L.append("")
    L.append("| Sitio(s) | Gemelo | Lugar admin-1 | Protegida | Aeropuerto km | Pueblo km | ice_share | Koppen | HMP km | Region conocida km |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in res["top1_arcticos"]:
        names = ", ".join(h["name"] for h in r["area_admin1"]["poligonos"]) or "sin poligono"
        L.append("| %s | %s | %s | %s | %.1f (%s) | %.1f (%s) | %.3f | %s | %.1f | %.1f (%s) |" % (
            ", ".join(r["top1_de"]), r["pool"], names,
            "si" if r["area_admin1"]["protegida"] else "no",
            r["aeropuerto_mas_cercano"]["km"], r["aeropuerto_mas_cercano"]["nombre"],
            r["pueblo_mas_cercano"]["km"], r["pueblo_mas_cercano"]["nombre"],
            r["ice_share"], r["koppen"]["clase"], r["estacion_HMP_km"],
            r["region_analoga_conocida_mas_cercana"]["km_centro"],
            r["region_analoga_conocida_mas_cercana"]["nombre"]))
    L.append("")
    L.append("Trabas: si `Protegida` es si, aplica el permiso de la fuente de Groenlandia (estado no verificado, ver abajo). "
             "Hielo: ice_share < 0.2 en todos (regla de shares.json).")
    L.append("")
    L.append("## Arcticos a menos de 100 km de un aeropuerto y fuera de area protegida")
    L.append("")
    lst = res["arcticos_menos_100km_aeropuerto_fuera_protegida"]
    L.append("Total: %d de %d." % (len(lst), A["n"]))
    L.append("")
    if lst:
        L.append("| Gemelo | Aeropuerto km | Aeropuerto | Pueblo km | ice_share | Lugar admin-1 | Koppen |")
        L.append("|---|---|---|---|---|---|---|")
        by = {r["pool"]: r for r in res["lugares"]}
        for p in lst:
            r = by[p]
            names = ", ".join(h["name"] for h in r["area_admin1"]["poligonos"]) or "sin poligono"
            L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                p, r["aeropuerto_mas_cercano"]["km"], r["aeropuerto_mas_cercano"]["nombre"],
                r["pueblo_mas_cercano"]["km"], r["ice_share"], names, r["koppen"]["clase"]))
    L.append("")
    L.append("## Fuentes y limites")
    L.append("")
    f = res["fuentes"]
    for k in ["ice_share, bare_share_full", "koppen", "pueblo", "aeropuerto", "puerto", "area_protegida",
              "region_analoga", "HMP"]:
        L.append("- %s: %s" % (k, f[k]))
    L.append("- Area protegida: las marcas salen SOLO del nombre 'Nationalparken' (poligono Natural Earth con type='Lansdele' y type_en vacio; ningun poligono dice 'National Park' en type/type_en).")
    p = f["permiso_parque_NE_groenlandia"]
    L.append("- Permiso parque NE Groenlandia: **%s**. %s" % (p["estado"], p["motivo"]))
    for u in p["urls_halladas"]:
        L.append("  - %s" % u)
    L.append("  - Afirmacion hallada en busqueda, sin verificar en texto: %s" % p["afirmacion_de_busqueda_no_verificada"])
    L.append("")
    (OUT / "viability.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
