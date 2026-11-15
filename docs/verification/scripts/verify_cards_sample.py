# -*- coding: utf-8 -*-
"""Verificacion independiente de una muestra de fichas (cards).

Solo lee el proyecto. No importa nada de pipelines/. Recomputa con funciones propias
y compara contra lo que dice la ficha. Escribe solo docs/verification/cards_sample.json
y docs/verification/cards_sample.md.
"""
import json, os, math, random, re, collections
import numpy as np
from scipy import ndimage
import rasterio

ROOT = r"C:\SpaceApps2026_Hackathon"
OUT = os.path.join(ROOT, "docs", "verification")
SEED = 20261114
Z = 1.96
TOL_MISSION_PP = 1.0      # mission_pct: tolerancia en puntos (terreno guardado a 30 m, se reconstruye a 100 m)
TOL_NUM = 1e-6            # valores numericos de ensayo (latitudes, conteos)
# Porcentajes de sol rasante: 4 celdas con e = 0 exacto (dec = 0, H = 90/270) pueden contarse o no segun el ruido
# de punto flotante de quien las calcule: 4 de 10368 muestras = 0.0386 pts. Tolerancia 0.05 pts.
TOL_GRAZ_PP = 0.05
R_EARTH_KM = 6371.0088
KOPPEN_TIF = os.path.join(ROOT, "data", "raw", "reference", "koppen", "Beck_KG_V1_present_0p0083.tif")
KOPPEN_LEG = os.path.join(ROOT, "data", "raw", "reference", "koppen", "legend.txt")

FIELDS = [
    "novelty", "known_region_id", "koppen_class",
    "rehearsal.landing", "rehearsal.driving", "rehearsal.low_sun", "rehearsal.low_sun_lat", "rehearsal.cold",
    "limit_deg", "mission_pct.landing", "analog_place", "nearest_town",
]
STRATA = [
    ("novelty_new", 6), ("novelty_known", 6),
    ("landing_yes", 5), ("landing_partial", 5), ("landing_no", 5),
    ("low_sun_no", 5), ("low_sun_yes", 5),
]


def P(*a):
    return os.path.join(ROOT, *a)


def jload(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def wilson(k, n):
    if n == 0:
        return None, None, None
    p = k / n
    z2 = Z * Z
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    margin = Z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return p, centre - margin, centre + margin


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH_KM * math.asin(math.sqrt(a))


def load_legend():
    leg = {}
    pat = re.compile(r"^\s*(\d+):\s+(\S+)\s+")
    with open(KOPPEN_LEG, encoding="utf-8") as fh:
        for line in fh:
            m = pat.match(line)
            if m:
                leg[int(m.group(1))] = m.group(2)
    return leg


def koppen_at(lat, lon, legend):
    with rasterio.open(KOPPEN_TIF) as src:
        row, col = src.index(lon, lat)
        val = src.read(1, window=((row, row + 1), (col, col + 1)))[0, 0]
    code = int(val)
    return code, legend.get(code)


def novelty_recompute(lat, lon, regions):
    hits = []
    for r in regions:
        d = haversine_km(lat, lon, r["lat"], r["lon"])
        if d <= r["radius_km"]:
            hits.append((round(d, 3), r["id"]))
    if not hits:
        return "new", None, hits
    hits.sort()
    return "known_region", hits[0][1], hits


def status_points(diff, yes_max, partial_max):
    if diff <= yes_max:
        return "yes"
    if diff <= partial_max:
        return "partial"
    return "no"


def grazing_pct(lat_deg, eps_deg):
    """Closed-form sampling of STANDARDS 10.15 (P-S): 72 year fractions x 144 hour angles."""
    phi = np.radians(lat_deg)
    eps = np.radians(eps_deg)
    f = np.arange(72) / 72.0
    dec = np.arcsin(np.sin(eps) * np.sin(2 * np.pi * f))
    H = 2 * np.pi * np.arange(144) / 144.0
    s = np.sin(phi) * np.sin(dec)[:, None] + np.cos(phi) * np.cos(dec)[:, None] * np.cos(H)[None, :]
    e = np.degrees(np.arcsin(np.clip(s, -1.0, 1.0)))
    # 0 < e exacto: en dec = 0 con H = 90/270 deg la elevacion es 0 matematico (en float +-1e-15).
    # Se trata |e| < 1e-9 como 0 para no contar ruido de punto flotante.
    return 100.0 * float(np.mean((e > 1e-9) & (e < 10)))


def earth_scan(target_grazing, eps_earth):
    lats = np.arange(0, 90.0 + 1e-9, 0.5)
    vals = [grazing_pct(float(l), eps_earth) for l in lats]
    imax = int(np.argmax(vals))
    reach = [float(l) for l, v in zip(lats, vals) if v >= target_grazing]
    lowest = min(reach) if reach else None
    return lowest, float(vals[imax]), float(lats[imax])


def mission_landing_pct(analog_id, limit_deg):
    """Reconstruye mission_pct (100 m grid, STANDARDS 3/4/10.3) desde site/data/terrain/<id>/height.bin (30 m)."""
    tdir = P("site", "data", "terrain", analog_id)
    meta = jload(os.path.join(tdir, "meta.json"))
    n = int(meta["n"])
    L = float(meta["L"])
    R = float(meta["R"])
    z = np.fromfile(os.path.join(tdir, "height.bin"), dtype="<f4")
    if z.size != n * n:
        raise ValueError(f"height.bin tamano {z.size} != n*n {n * n}")
    z = z.reshape(n, n).astype(np.float64)
    c = (n - 1) / 2.0
    L2 = 100.0
    n2 = 2 * math.ceil(R / L2) + 1
    c2 = (n2 - 1) / 2.0
    X = (np.arange(n2) - c2) * L2
    Y = (c2 - np.arange(n2)) * L2
    XX, YY = np.meshgrid(X, Y)
    zz = ndimage.map_coordinates(z, [c - YY / L, c + XX / L], order=1, mode="nearest")
    disk = (XX ** 2 + YY ** 2) <= R * R
    mask = disk & np.isfinite(zz)
    z0 = np.where(np.isfinite(zz), zz, 0.0)
    ok = np.zeros_like(mask)
    ok[1:-1, 1:-1] = (mask[1:-1, 1:-1] & mask[:-2, 1:-1] & mask[2:, 1:-1]
                      & mask[1:-1, :-2] & mask[1:-1, 2:])
    gx = np.zeros_like(z0)
    gy = np.zeros_like(z0)
    gx[1:-1, 1:-1] = (z0[1:-1, 2:] - z0[1:-1, :-2]) / (2 * L2)
    gy[1:-1, 1:-1] = (z0[:-2, 1:-1] - z0[2:, 1:-1]) / (2 * L2)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    below = ok & (slope <= float(limit_deg))
    n_interior = int(np.sum(ok))
    n_disk = int(np.sum(mask))
    return {
        "pct_interior": 100.0 * int(np.sum(below)) / n_interior,
        "pct_all_disk": 100.0 * int(np.sum(below)) / n_disk,
        "n_interior": n_interior,
        "n_disk": n_disk,
        "grid_n": n2,
    }


def chk(field, card_val, rec_val, ok, note=""):
    return {"field": field, "card": card_val, "recomputed": rec_val,
            "status": "OK" if ok else "DIF", "note": note}


def blocked(field, note):
    return {"field": field, "card": None, "recomputed": None, "status": "BLOQUEADO", "note": note}


def main():
    cards_dir = P("site", "data", "cards")
    reh_dir = P("site", "data", "rehearsal")
    files = sorted(os.listdir(cards_dir))
    assert files == sorted(os.listdir(reh_dir)), "cards y rehearsal no tienen los mismos nombres"
    assert len(files) == 160, len(files)

    targets = {t["id"]: t for t in jload(P("site", "data", "targets.json"))["targets"]}
    rules = jload(P("config", "rehearsal_rules.json"))
    light = jload(P("config", "light.json"))["bodies"]
    regions = jload(P("config", "known_analog_regions.json"))["regions"]
    limits = jload(P("config", "missions.json"))["limits"]
    legend = load_legend()
    assert len(legend) == 30, len(legend)

    # Solo para estratificar (metadatos); la revision es solo de la muestra.
    cards = {f: jload(os.path.join(cards_dir, f)) for f in files}
    rehs = {f: jload(os.path.join(reh_dir, f)) for f in files}

    def line(f, lid):
        return {l["id"]: l for l in rehs[f]["lines"]}[lid]

    pred = {
        "novelty_new": lambda f: cards[f]["novelty"] == "new",
        "novelty_known": lambda f: cards[f]["novelty"] == "known_region",
        "landing_yes": lambda f: line(f, "landing")["status"] == "yes",
        "landing_partial": lambda f: line(f, "landing")["status"] == "partial",
        "landing_no": lambda f: line(f, "landing")["status"] == "no",
        "low_sun_no": lambda f: line(f, "low_sun")["status"] == "no",
        "low_sun_yes": lambda f: line(f, "low_sun")["status"] == "yes",
    }

    rng = random.Random(SEED)
    members = {}
    population = {}
    for name, k in STRATA:
        cand = sorted(f for f in files if pred[name](f))
        population[name] = len(cand)
        for f in rng.sample(cand, min(k, len(cand))):
            members.setdefault(f, []).append(name)
    sample = sorted(members)
    assert len(sample) <= 40, len(sample)
    mission_pick = sorted(random.Random(SEED).sample(sample, 5))

    results = []
    for f in sample:
        card = cards[f]
        tid = card["target_id"]
        aid = card["analog_id"]
        tgt = targets[tid]
        body = tgt["body"]
        ctx = card["context"]

        tmeta = jload(P("site", "data", "terrain", aid, "meta.json"))
        twin_lat, twin_lon = float(tmeta["lat"]), float(tmeta["lon"])
        rank = jload(P("site", "data", "rankings", tid + ".json"))["ranking"]
        rk = [r for r in rank if r["analog_id"] == aid]
        assert len(rk) == 1, (f, len(rk))
        rk_lat, rk_lon = float(rk[0]["lat"]), float(rk[0]["lon"])
        coords_ok = abs(rk_lat - twin_lat) < 0.01 and abs(rk_lon - twin_lon) < 0.01

        checks = []

        # 1. novelty y known_region_id
        rec_nov, rec_id, hits = novelty_recompute(twin_lat, twin_lon, regions)
        hit_note = ("circulos que contienen el punto: " + ", ".join(f"{i} ({d} km)" for d, i in hits)
                    if hits else "ningun circulo contiene el punto")
        checks.append(chk("novelty", card["novelty"], rec_nov, card["novelty"] == rec_nov, hit_note))
        checks.append(chk("known_region_id", card["known_region_id"], rec_id,
                          card["known_region_id"] == rec_id, ""))

        # 2. analog_place y nearest_town: no hay lector de .shp en el .venv
        checks.append(blocked("analog_place",
                              "BLOQUEADO: .venv sin lector de shapefile (pyshp, fiona, pyogrio, osgeo ausentes); "
                              "shapely no lee .shp"))
        checks.append(blocked("nearest_town",
                              "BLOQUEADO: idem, ne_10m_populated_places.shp no se puede leer"))

        # 3. koppen_class (raster Beck 1 km en el punto del gemelo)
        code, cls = koppen_at(twin_lat, twin_lon, legend)
        ok_k = (cls == ctx["koppen_class"]) and (code == ctx.get("koppen_code"))
        checks.append(chk("koppen_class", ctx["koppen_class"], f"{cls} (codigo {code})", ok_k,
                          f"ficha codigo {ctx.get('koppen_code')}"))

        # 4. ensayos
        T_eps = light[body]["obliquity_deg"]
        E_eps = light["earth"]["obliquity_deg"]
        for rid in ("landing", "driving"):
            mp = card["mission_pct"][rid]
            t, a = mp["target"], mp["analog"]
            d = abs(a - t)
            rec = status_points(d, rules[rid]["yes_max_points"], rules[rid]["partial_max_points"])
            ln = line(f, rid)
            vals_ok = abs(ln["target_value"] - t) <= TOL_NUM and abs(ln["analog_value"] - a) <= TOL_NUM
            note = (f"|gemelo-objetivo| = {d:.4f} pts; umbrales yes<={rules[rid]['yes_max_points']}, "
                    f"partial<={rules[rid]['partial_max_points']}; valores de la linea "
                    + ("= ficha" if vals_ok else "DIFIEREN de la ficha"))
            checks.append(chk(f"rehearsal.{rid}", ln["status"], rec, ln["status"] == rec and vals_ok, note))

        Tg = grazing_pct(tgt["lat"], T_eps)
        Ag = grazing_pct(twin_lat, E_eps)
        ls = rules["low_sun"]
        if Ag >= Tg - ls["yes_within_points"]:
            rec_ls = "yes"
        elif Ag >= Tg * ls["partial_min_fraction_of_target"]:
            rec_ls = "partial"
        else:
            rec_ls = "no"
        ln = line(f, "low_sun")
        vals_ok = abs(ln["target_value"] - Tg) <= TOL_GRAZ_PP and abs(ln["analog_value"] - Ag) <= TOL_GRAZ_PP
        checks.append(chk("rehearsal.low_sun", ln["status"], rec_ls, ln["status"] == rec_ls and vals_ok,
                          f"recomputado T={Tg:.6f} A={Ag:.6f}; linea T={ln['target_value']} A={ln['analog_value']}"
                          + ("" if vals_ok else f" (valores fuera de +-{TOL_GRAZ_PP} pts)")))

        if ln["status"] == "no":
            lowest, emax, emax_lat = earth_scan(Tg, E_eps)
            f_low = ln.get("lowest_abs_lat_deg")
            f_emax = ln.get("earth_max_grazing_pct")
            f_emax_lat = ln.get("earth_max_abs_lat_deg")
            ok_l = (f_low == lowest) and (f_emax is None or abs(f_emax - emax) <= TOL_GRAZ_PP) \
                and (f_emax_lat is None or f_emax_lat == emax_lat)
            checks.append(chk("rehearsal.low_sun_lat", f"lowest={f_low} emax={f_emax}@{f_emax_lat}",
                              f"lowest={lowest} emax={emax:.6f}@{emax_lat}", ok_l,
                              "solo casos low_sun=no: latitud minima en Tierra que alcanza el objetivo"))

        cold_set = rules["cold"]["cold_koppen_classes"]
        rec_cold = "partial" if ctx["koppen_class"] in cold_set else "no"
        ln = line(f, "cold")
        checks.append(chk("rehearsal.cold", ln["status"], rec_cold, ln["status"] == rec_cold,
                          f"clase ficha {ctx['koppen_class']}"))

        # limite de pendiente contra config/missions.json
        lim_l = limits[body]["landing"]["limit_deg"]
        lim_d = limits[body]["driving"]["limit_deg"]
        cl = card["mission_pct"]["landing"]["limit_deg"]
        cd = card["mission_pct"]["driving"]["limit_deg"]
        checks.append(chk("limit_deg", f"landing {cl} / driving {cd}",
                          f"landing {lim_l} / driving {lim_d} (missions.json limits.{body})",
                          cl == lim_l and cd == lim_d, ""))

        # 5. mission_pct landing del gemelo (solo 5 fichas)
        if f in mission_pick:
            ma = card["mission_pct"]["landing"]["analog"]
            mp = mission_landing_pct(aid, cl)
            checks.append(chk("mission_pct.landing", ma, round(mp["pct_interior"], 6),
                              abs(mp["pct_interior"] - ma) <= TOL_MISSION_PP,
                              f"denominador = pixeles con pendiente definida ({mp['n_interior']}); "
                              f"alternativa denominador = todo el disco ({mp['n_disk']}): "
                              f"{mp['pct_all_disk']:.4f}; grilla {mp['grid_n']} px a 100 m; tolerancia {TOL_MISSION_PP} pts"))

        results.append({
            "file": f,
            "target_id": tid,
            "analog_id": aid,
            "body": body,
            "strata": members[f],
            "mission_check": f in mission_pick,
            "twin": {"lat": twin_lat, "lon": twin_lon, "ranking_lat": rk_lat, "ranking_lon": rk_lon,
                     "coords_match_ranking": coords_ok},
            "checks": checks,
        })

    # Resumen por estrato y campo
    summary = {}
    for s in [n for n, _ in STRATA] + ["TOTAL"]:
        sub = [r for r in results if s == "TOTAL" or s in r["strata"]]
        summary[s] = {"cards": len(sub)}
        for fld in FIELDS:
            items = [c for r in sub for c in r["checks"] if c["field"] == fld]
            n = sum(1 for c in items if c["status"] in ("OK", "DIF"))
            k = sum(1 for c in items if c["status"] == "OK")
            b = sum(1 for c in items if c["status"] == "BLOQUEADO")
            p, lo, hi = wilson(k, n)
            summary[s][fld] = {"n": n, "ok": k, "blocked": b, "p": p, "wilson_lo": lo, "wilson_hi": hi}

    disc = []
    for r in results:
        for c in r["checks"]:
            if c["status"] == "DIF":
                disc.append({"file": r["file"], "field": c["field"], "card": c["card"],
                             "recomputed": c["recomputed"], "note": c["note"]})

    body_counts = collections.Counter(r["body"] for r in results)
    out = {
        "design": {
            "seed": SEED,
            "strata": {n: {"k": k, "population": population[n]} for n, k in STRATA},
            "unique_cards": len(sample),
            "bodies": dict(body_counts),
            "mission_check_cards": mission_pick,
            "tolerances": {"mission_pct_pp": TOL_MISSION_PP, "grazing_pct_pp": TOL_GRAZ_PP,
                           "numeric": TOL_NUM, "wilson_z": Z},
            "novelty_value_note": "el valor real del campo es 'known_region' (no 'known'); se usa ese",
            "blocked": "analog_place y nearest_town: no hay lector de shapefile en .venv (pyshp, fiona, pyogrio, osgeo ausentes)",
        },
        "summary": summary,
        "discrepancies": disc,
        "results": results,
    }
    with open(os.path.join(OUT, "cards_sample.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    write_md(out)

    print("unique cards", len(sample), "bodies", dict(body_counts))
    print("population", population)
    print("mission cards", mission_pick)
    print("discrepancies", len(disc))
    for d in disc:
        print("DIF", d["file"], d["field"], d["card"], d["recomputed"])


def fmt_rate(s):
    if s["n"] == 0:
        return "—", "—", "—"
    p = s["p"]
    return (f"{s['ok']}/{s['n']}", f"{100 * p:.1f}%",
            f"{100 * s['wilson_lo']:.1f}–{100 * s['wilson_hi']:.1f}")


def write_md(out):
    L = []
    d = out["design"]
    L.append("# Verificacion independiente: muestra de fichas (cards)")
    L.append("")
    L.append(f"Semilla {d['seed']}. Fichas unicas en la muestra: {d['unique_cards']} "
             f"(Marte {d['bodies'].get('mars', 0)}, Luna {d['bodies'].get('moon', 0)}).")
    L.append("")
    L.append("Estratos (poblacion de 160; n por estrato):")
    for n, v in d["strata"].items():
        L.append(f"- {n}: {v['k']} de {v['population']}")
    L.append("")
    L.append("Tolerancias: mission_pct +-1.0 pts (terreno guardado a 30 m, reconstruido a 100 m); "
             "porcentajes de sol rasante +-0.05 pts (ruido de punto flotante en e = 0 exacto, 4 de 10368 muestras); "
             "latitudes y conteos exactos. Estado de ensayo: comparacion exacta. Intervalo: Wilson 95%.")
    L.append("")
    L.append("BLOQUEADO: analog_place y nearest_town no se verifican. El .venv no tiene lector de shapefile "
             "(pyshp, fiona, pyogrio, osgeo). Shapely no lee .shp.")
    L.append("")
    for s, block in out["summary"].items():
        L.append(f"## Estrato: {s} (fichas: {block['cards']})")
        L.append("")
        L.append("| campo | aciertos | tasa | Wilson 95% | bloqueado |")
        L.append("|---|---|---|---|---|")
        for fld in FIELDS:
            v = block[fld]
            k_n, tasa, wil = fmt_rate(v)
            L.append(f"| {fld} | {k_n} | {tasa} | {wil} | {v['blocked']} |")
        L.append("")
    L.append("## Discrepancias")
    L.append("")
    if not out["discrepancies"]:
        L.append("Ninguna.")
    for x in out["discrepancies"]:
        L.append(f"- {x['file']} | {x['field']} | ficha: {x['card']} | recomputado: {x['recomputed']} | {x['note']}")
    L.append("")
    L.append("Causa no resuelta (mission_pct): la reconstruccion desde height.bin (30 m, remuestreada a 100 m) da "
             "59.5-60.1 y 63.1-63.8 con cualquier ancla de rejilla o metodo de remuestreo; los valores de la ficha "
             "quedan fuera de ese rango. Hipotesis: la pipeline calculo la rejilla de 100 m directo desde el DEM "
             "nativo (la ficha lista ese clip en provenance). No verificable sin ese clip.")
    L.append("")
    L.append("## Fichas de la muestra")
    L.append("")
    for r in out["results"]:
        L.append(f"- {r['file']} ({r['body']}) estratos: {', '.join(r['strata'])}"
                 + (" [mission_pct]" if r["mission_check"] else ""))
    L.append("")
    with open(os.path.join(OUT, "cards_sample.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


if __name__ == "__main__":
    main()
