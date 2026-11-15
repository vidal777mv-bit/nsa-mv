"""Provenance inventory for the 'Data from NASA' page.

Read-only over the project. Writes only docs/verification/provenance.json and provenance.md.
Steps: (1) sources.json x code (pipelines/src/tools) x site; (2) manifest local files;
(3) one HTTP probe per unique URL (urllib, 10 s, GET with Range bytes=0-0; errors annotated).
"""
import concurrent.futures as cf
import json
import pathlib
import re
import socket
import ssl
import urllib.error
import urllib.request
from collections import defaultdict
from urllib.parse import urlparse

ROOT = pathlib.Path(r"C:\SpaceApps2026_Hackathon")
OUT = ROOT / "docs" / "verification"
UA = "provenance-check/1.0"
TIMEOUT = 10
URL_RE = re.compile(r"https?://[^\s\"'<>)\]\\`]+")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


SRC = load(ROOT / "config" / "sources.json")["sources"]
MAN = load(ROOT / "data" / "raw" / "manifest.json")
SITES = load(ROOT / "config" / "sites.json")["sites"]

LOLA = (True, "NASA GSFC PGDA (LOLA, sonda LRO)", "LRO / LOLA",
        "Sin licencia publicada; la pagina pide cita (Barker et al.)")
DIV = (True, "NASA LRO, instrumento Diviner (UCLA), archivo PDS", "LRO / Diviner",
       "PDS: gratuito, sin licencia explicita")
CTX = (True, "NASA MRO, instrumento CTX (DTM controlado por USGS)", "MRO / CTX",
       "Dominio publico USGS")
CTX_FIG = (True, "Imagenes NASA MRO CTX; DTM de autores externos (figshare)", "MRO / CTX",
           "CC BY 4.0 (figshare)")

META = {
    "nasadem": (True, "NASA JPL/USGS: NASADEM = reproceso de SRTM (NASA) y ASTER GDEM",
                "SRTM / ASTER GDEM (reprocesado)",
                "CONFLICTO: EOSDIS 'free and open' vs Planetary Computer 'proprietary'"),
    "cop_dem_glo30": (False, "ESA/DLR/Airbus (Copernicus). No es NASA", "TanDEM-X (Copernicus DEM)",
                      "COP-DEM-GLO-30-F, libre con aviso de atribucion (Art. 6)"),
    "esa_worldcover": (False, "ESA WorldCover (Sentinel). No es NASA", "Sentinel-1/2", "CC BY 4.0"),
    "modis_mod11a2_061": (True, "NASA LP DAAC (MODIS, Terra)", "Terra / MODIS",
                          "EOSDIS open (NASA); PC dice 'proprietary'"),
    "copernicus_glo30_s3_example": (False, "ESA/DLR/Airbus (Copernicus). No es NASA", "TanDEM-X",
                                    "COP-DEM-GLO-30-F"),
    "pgda_lola_product78_page": LOLA,
    "lola_5m_site06_surf": LOLA, "lola_5m_site06_toterr": LOLA,
    "lola_5m_site23_surf": LOLA, "lola_5m_site23_toterr": LOLA,
    "lola_5m_site11_surf": LOLA, "lola_5m_site11_toterr": LOLA,
    "lola_5m_dm2_surf": LOLA, "lola_5m_dm2_toterr": LOLA,
    "lola_5m_haworth_surf": LOLA, "lola_5m_haworth_toterr": LOLA,
    "lola_5m_site04_surf": LOLA, "lola_5m_sl2_surf": LOLA,
    "lola_5m_site06_rois": LOLA, "lola_5m_site23_rois": LOLA, "lola_5m_site11_rois": LOLA,
    "lola_5m_dm2_rois": LOLA, "lola_5m_haworth_rois": LOLA, "lola_5m_sl2_rois": LOLA,
    "lola_80s_80mpp": LOLA, "lola_20m_polar_ldem": LOLA,
    "diviner_prp_south": DIV, "diviner_prp_south_label": DIV, "diviner_pcp_directory": DIV,
    "jezero_ctx_trn_dtm_20m": (True, "USGS a partir de imagenes NASA MRO CTX y topografia MOLA (NASA)",
                               "MRO / CTX + MGS / MOLA", "Dominio publico USGS; ficha del producto no leida"),
    "gale_ctx_dtm_figshare": CTX_FIG,
    "hrsc_mola_blend_200m": ("parcial", "Mezcla: MOLA (NASA MGS) + HRSC (ESA)",
                             "MGS / MOLA + Mars Express / HRSC",
                             "USGS dominio publico; HRSC/ESA pueden tener otros terminos"),
    "gale_ctx_dtm_tile_3_3": (True, "Igual que gale_ctx_dtm_figshare: NASA MRO CTX, extracto local",
                              "MRO / CTX", "CC BY 4.0 (figshare)"),
    "usgs_ctx_dtm_insight_n15_068239": CTX,
    "usgs_ctx_dtm_spirit_p22_009530": CTX,
    "usgs_ctx_dtm_zhurong_n14_067844": CTX,
    "usgs_ctx_dtm_oxia_n06_064538": CTX,
    "lroc_nac_dtm_apollo17": (True, "NASA/LROC (ASU), archivo PDS", "LRO / LROC NAC",
                              "NASA PDS gratuito; sin licencia LROC explicita"),
    "natural_earth_10m_admin_1": (False, "Natural Earth. No es NASA", "Vectores culturales",
                                  "Dominio publico (Natural Earth)"),
    "natural_earth_10m_populated_places": (False, "Natural Earth. No es NASA", "Vectores culturales",
                                           "Dominio publico (Natural Earth)"),
    "nasa_svs_lroc_colour_moon": (True, "NASA SVS (CGI Moon Kit 4720), mapa de color LROC",
                                  "LRO / LROC (color)",
                                  "Guia de medios NASA: dar credito; NO dominio publico"),
    "commons_blue_marble_earth": (True, "NASA Visible Earth 57752 (Blue Marble 2002), via Wikimedia Commons",
                                  "Terra / MODIS (compuesto Blue Marble)",
                                  "Dominio publico (Commons); credito NASA"),
    "commons_viking_mdim21_mars": (True, "NASA/JPL/USGS, mosaico Viking MDIM 2.1 via Commons",
                                   "Viking Orbiter", "Dominio publico (Commons 'pd'; USGS)"),
    "koppen_geiger_1km_present": (False, "Beck et al. 2018 (Scientific Data). No es NASA",
                                  "Clasificacion climatica", "CC BY 4.0"),
    "natural_earth_10m_populated_places": (False, "Natural Earth. No es NASA", "Vectores culturales",
                                           "Dominio publico (Natural Earth)"),
}
assert set(META) == {s["id"] for s in SRC}, set(META) ^ {s["id"] for s in SRC}

EXTRA_TOKENS = {
    "cop_dem_glo30": ["copdem", "cop-dem-glo-30"],
    "natural_earth_10m_admin_1": ["ne_10m_admin_1"],
    "natural_earth_10m_populated_places": ["ne_10m_populated_places"],
    "koppen_geiger_1km_present": ["Beck_KG_V1_present"],
    "hrsc_mola_blend_200m": ["Mars_HRSC_MOLA_BlendDEM"],
    "gale_ctx_dtm_tile_3_3": ["PG_Gale_CTX_3_3"],
}
DISPLAY = {
    "nasadem": ["NASADEM"], "cop_dem_glo30": ["Copernicus GLO-30", "COP-DEM"],
    "esa_worldcover": ["WorldCover"], "koppen_geiger_1km_present": ["Köppen", "Koppen"],
    "natural_earth_10m_admin_1": ["Natural Earth"], "natural_earth_10m_populated_places": ["Natural Earth"],
    "commons_blue_marble_earth": ["Blue Marble"], "commons_viking_mdim21_mars": ["Viking", "MDIM"],
    "nasa_svs_lroc_colour_moon": ["CGI Moon Kit", "lroc_color"], "lroc_nac_dtm_apollo17": ["LROC"],
    "modis_mod11a2_061": ["MODIS"], "diviner_prp_south": ["Diviner"],
    "pgda_lola_product78_page": ["LOLA"],
}
TEXTURE_FILE = {
    "commons_blue_marble_earth": "site/assets/globes/earth.jpg",
    "commons_viking_mdim21_mars": "site/assets/globes/mars.jpg",
    "nasa_svs_lroc_colour_moon": "site/assets/globes/moon.jpg",
}


def tokens(s):
    t = {s["id"]}
    fn = s.get("filename")
    if fn:
        p = pathlib.PurePosixPath(fn)
        t.update({p.name, p.stem})
    if s.get("access") == "stac":
        t.add(s["url_or_collection"])
    u = s.get("url_or_collection") or ""
    if u.startswith("http"):
        t.add(u.rsplit("/", 1)[-1])
    t.update(EXTRA_TOKENS.get(s["id"], []))
    return {x for x in t if x}


def norm(u):
    # keep the trailing slash: the exact URL in sources.json is what gets probed
    return u.rstrip(".,;:)")


# probes from the previous run are reused (one attempt per URL, no retries)
CACHE = {}
if (OUT / "provenance.json").exists():
    for _e in load(OUT / "provenance.json"):
        for _u, _r in (_e.get("url_checks") or {}).items():
            if _r.get("status") and _u not in CACHE:
                CACHE[_u] = _r

# figshare API metadata, copied from the stdout of the first run (same two calls, not repeated)
FIGSHARE_RUN1 = {
    "6584984": {"title": "Gale Crater Stereo CTX DTMs + Orthoimages", "authors": ["Peter Grindrod"],
                "license": "https://creativecommons.org/licenses/by/4.0/"},
    "6396959": {"title": "Present and future Köppen-Geiger climate classification maps at 1-km resolution",
                "authors": ["Hylke E. Beck", "Niklaus E. Zimmermann", "Tim R. McVicar", "Noemi Vergopolan",
                            "Alexis Berg", "Eric F. Wood"],
                "license": "https://creativecommons.org/licenses/by/4.0/"},
}

# known usage that is manual or reachable-only, not a script reading the file
CONSISTENCY_NOTE = {
    "pgda_lola_product78_page": "uso manual: pagina citada para centros y licencia; ningun script la lee",
    "gale_ctx_dtm_figshare": "uso manual: el zip se extrajo a mano (una tile); ningun script lo lee",
    "hrsc_mola_blend_200m": "codigo tiene la ruta (regional_sample.py) pero no se descargo; uso=no",
    "lola_5m_site06_rois": "centre() la alcanza solo si el archivo existe; broken, no descargado",
    "lola_5m_site23_rois": "centre() la alcanza solo si el archivo existe; broken, no descargado",
    "lola_5m_dm2_rois": "centre() la alcanza solo si el archivo existe; broken, no descargado",
    "lola_5m_haworth_rois": "centre() la alcanza solo si el archivo existe; broken, no descargado",
    "lola_5m_sl2_rois": "centre() la alcanza solo si el archivo existe; broken, no descargado",
}


# ---- (1a) code scan: pipelines, src, tools
code_files = []
for d in ("pipelines", "src", "tools"):
    for p in (ROOT / d).rglob("*.py"):
        if "__pycache__" not in p.parts:
            code_files.append(p)
code_text = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8", errors="replace")
             for p in code_files}

dem_readers = sorted(k for k, v in code_text.items() if "dem_source_id" in v)
lola_pattern_readers = sorted(k for k, v in code_text.items() if "lola_5m*_surf" in v)

# ---- (1b) site scan
site_ui = [p for p in (ROOT / "site").rglob("*")
           if p.is_file() and p.suffix in (".js", ".html", ".json") and "README_screens" not in p.parts
           and "v2" not in p.parts]
site_doc = [p for p in (ROOT / "site").glob("*.md")] + [ROOT / "site" / "assets" / "globes" / "SOURCES.md"]
site_text = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8", errors="replace") for p in site_ui}
site_text_doc = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8", errors="replace") for p in site_doc}
refs_html = (ROOT / "site" / "references.html").read_text(encoding="utf-8", errors="replace")

terrain_meta = {}
for p in (ROOT / "site" / "data" / "terrain").glob("*/meta.json"):
    m = load(p)
    terrain_meta.setdefault(m.get("source_id"), []).append(p.parent.name)

# ---- (2) manifest local files
man_stats = defaultdict(lambda: {"entries": 0, "present": 0, "size_ok": 0, "missing_example": []})
for e in MAN:
    st = man_stats[e["source_id"]]
    st["entries"] += 1
    p = ROOT / e["path"]
    if p.exists():
        st["present"] += 1
        if p.stat().st_size == e["bytes"]:
            st["size_ok"] += 1
    elif len(st["missing_example"]) < 2:
        st["missing_example"].append(e["path"])

# ---- URL universe
def source_urls(s):
    out = []
    if s.get("access") == "stac":
        out.append(f"https://planetarycomputer.microsoft.com/api/stac/v1/collections/{s['url_or_collection']}")
    elif (s.get("url_or_collection") or "").startswith("http"):
        out.append(s["url_or_collection"])
    if (s.get("page") or "").startswith("http"):
        out.append(s["page"])
    if s.get("doi"):
        out.append("https://doi.org/" + s["doi"])
    return [norm(u) for u in out]


SRC_URLS = {}
for s in SRC:
    for u in source_urls(s):
        SRC_URLS.setdefault(u, set()).add(s["id"])

# URLs the site shows (UI files), with the files that carry them
site_url_files = defaultdict(set)
for rel, txt in site_text.items():
    for m in URL_RE.findall(txt):
        site_url_files[norm(m)].add(rel)
visible_no_entry = {u: sorted(f) for u, f in site_url_files.items() if u not in SRC_URLS}

FIG_API = ["https://api.figshare.com/v2/articles/6584984", "https://api.figshare.com/v2/articles/6396959"]
ALL_URLS = sorted(set(SRC_URLS) | set(visible_no_entry) | set(FIG_API))
MAN_COUNT = {}
for _e in MAN:
    MAN_COUNT[_e["source_id"]] = MAN_COUNT.get(_e["source_id"], 0) + 1


# ---- (3) one probe per URL
def probe(url):
    full = url in FIG_API
    headers = {"User-Agent": UA}
    if full:
        headers["Accept"] = "application/json"
    else:
        headers["Range"] = "bytes=0-0"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read(300000) if full else r.read(1)
            res = {"status": "ok", "http_code": r.status, "final_url": r.geturl()}
            if full:
                res["json"] = json.loads(body.decode("utf-8"))
            return res
    except urllib.error.HTTPError as e:
        if e.code == 416:
            return {"status": "ok_sin_range", "http_code": 416, "note": "responde; el servidor rechaza Range"}
        return {"status": f"http_{e.code}", "http_code": e.code, "note": "no bloquea (anotado)"}
    except ssl.SSLError as e:
        return {"status": "ssl", "note": f"certificado/SSL: {e.__class__.__name__}"}
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLError):
            return {"status": "ssl", "note": "certificado/SSL"}
        if isinstance(e.reason, socket.timeout):
            return {"status": "timeout", "note": "10 s"}
        return {"status": "error", "note": f"URLError: {str(e.reason)[:120]}"}
    except (socket.timeout, TimeoutError):
        return {"status": "timeout", "note": "10 s"}
    except Exception as e:  # noqa: BLE001 - annotate, never retry
        return {"status": "error", "note": f"{type(e).__name__}: {str(e)[:120]}"}


probes = {u: CACHE[u] for u in ALL_URLS if u in CACHE}
TO_PROBE = [u for u in ALL_URLS if u not in CACHE]
print("cached:", len(probes), "new probes:", len(TO_PROBE))
with cf.ThreadPoolExecutor(max_workers=16) as ex:
    futs = {ex.submit(probe, u): u for u in TO_PROBE}
    for f in cf.as_completed(futs):
        probes[futs[f]] = f.result()

figshare = {}
for u in FIG_API:
    figshare[u] = FIGSHARE_RUN1["6584984" if "6584984" in u else "6396959"]

# ---- assemble per source
def hits_in(text_map, toks, ci=False):
    out = []
    for rel, txt in text_map.items():
        hay = txt.lower() if ci else txt
        for t in toks:
            needle = t.lower() if ci else t
            if needle in hay:
                out.append(rel)
                break
    return sorted(out)


entries = []
for s in SRC:
    sid = s["id"]
    is_nasa, motivo, instr, lic_short = META[sid]
    toks = tokens(s)
    code_hits = hits_in(code_text, toks)
    dem_ids = {x["dem_source_id"] for x in SITES}
    if sid in dem_ids:
        code_hits = sorted(set(code_hits) | set(dem_readers))
    if sid.startswith("lola_5m_") and sid.endswith("_surf") and MAN_COUNT.get(sid):
        code_hits = sorted(set(code_hits) | set(lola_pattern_readers))  # light.py: lola_5m*_surf.tif
    if sid.endswith("_rois") and sid.replace("_rois", "_surf") in dem_ids:
        code_hits = sorted(set(code_hits) | {"pipelines/fetch_data.py"})  # centre(): sibling ROI archive

    shown = []
    disp = DISPLAY.get(sid, [])
    if sid in TEXTURE_FILE:
        shown.append(f"textura de globo: {TEXTURE_FILE[sid]}")
    tg = sorted(x["id"] for x in SITES if x.get("dem_source_id") == sid)
    if tg:
        shown.append("relieve (hillshade) de objetivos en site/data/targets.json: " + ", ".join(tg))
    tm = terrain_meta.get(sid, [])
    if tm:
        shown.append(f"carpetas site/data/terrain/*/meta.json con este source_id: {len(tm)}")
    if disp:
        ui = hits_in(site_text, disp, ci=True)
        if ui:
            shown.append("texto en site: " + ", ".join(ui))
    for u in source_urls(s):
        if u in refs_html or (s.get("doi") and s["doi"] in refs_html):
            shown.append("listada en site/references.html")
            break
    if not shown:
        shown.append("no aparece en la UI (solo en config/manifest)")

    url_list = source_urls(s)
    checks = {u: {k: v for k, v in probes[u].items() if k != "json"} for u in url_list}
    ms = man_stats.get(sid)
    obj = {
        "id": sid,
        "in_sources_json": True,
        "cuerpo": s["body"],
        "is_nasa": is_nasa,
        "motivo_nasa": motivo,
        "mision_instrumento": instr,
        "proveedor": s["provider"],
        "producto": s["product"],
        "url": s.get("url_or_collection"),
        "pagina": s.get("page"),
        "doi": s.get("doi"),
        "licencia_corta": lic_short,
        "licencia_sources_json": s["license"],
        "usado_sources_json": s["used"],
        "uso_sources_json": s["use"],
        "usado_en_scripts": code_hits,
        "uso_tipo": "textura de globo (sitio, no pipeline)" if sid in TEXTURE_FILE else "codigo/manual",
        "consistencia_uso": (None if sid in TEXTURE_FILE else (bool(code_hits) == bool(s["used"]))),
        "nota_consistencia": CONSISTENCY_NOTE.get(sid),
        "mostrado_en_sitio": shown,
        "url_checks": checks,
        "manifest_local": (
            {"entradas": ms["entries"], "presentes": ms["present"], "tamano_ok": ms["size_ok"],
             "faltan_ejemplo": ms["missing_example"]} if ms else None),
    }
    if sid == "gale_ctx_dtm_figshare" or sid == "koppen_geiger_1km_present":
        doi_id = "6584984" if sid == "gale_ctx_dtm_figshare" else "6396959"
        obj["figshare_api"] = figshare.get(f"https://api.figshare.com/v2/articles/{doi_id}")
    entries.append(obj)

# ---- visible without a sources.json entry
for u, files in sorted(visible_no_entry.items()):
    host = urlparse(u).netloc
    nasa_host = any(k in host for k in ("nasa", "lroc", "nssdc", "ntrs", "marsoweb", "lro"))
    entries.append({
        "id": f"SIN_ENTRADA:{host}",
        "in_sources_json": False,
        "cuerpo": None,
        "is_nasa": ("por dominio NASA" if nasa_host else False),
        "motivo_nasa": "URL visible en el sitio sin entrada en config/sources.json",
        "mision_instrumento": None,
        "proveedor": host,
        "producto": None,
        "url": u,
        "pagina": None,
        "doi": None,
        "licencia_corta": "no verificada",
        "licencia_sources_json": None,
        "usado_sources_json": None,
        "uso_sources_json": None,
        "usado_en_scripts": [],
        "consistencia_uso": None,
        "mostrado_en_sitio": ["URL en: " + ", ".join(files)],
        "url_checks": {u: {k: v for k, v in probes[u].items() if k != "json"}},
        "manifest_local": None,
    })

# synthetic data: visible only if DATA_BASE is switched to data/sample/
entries.append({
    "id": "SIN_ENTRADA:site/data/sample",
    "in_sources_json": False, "cuerpo": "mars/moon/earth", "is_nasa": False,
    "motivo_nasa": "Datos sinteticos de demostracion, no son resultado NASA",
    "mision_instrumento": None, "proveedor": "sintetico", "producto": "site/data/sample/*",
    "url": None, "pagina": None, "doi": None, "licencia_corta": "n/a",
    "licencia_sources_json": None, "usado_sources_json": None, "uso_sources_json": None,
    "usado_en_scripts": [], "consistencia_uso": None,
    "mostrado_en_sitio": ["NO por defecto: site/js/config.js DATA_BASE = 'data/'; solo si se cambia a 'data/sample/' (banner SAMPLE)"],
    "url_checks": {}, "manifest_local": None,
})

OUT.mkdir(parents=True, exist_ok=True)
with open(OUT / "provenance.json", "w", encoding="utf-8") as f:
    json.dump(entries, f, ensure_ascii=False, indent=2)

# ---- stdout summary (ASCII only)
n_src = len([e for e in entries if e["in_sources_json"]])
nasa_true = [e["id"] for e in entries if e["in_sources_json"] and e["is_nasa"] is True]
nasa_part = [e["id"] for e in entries if e["in_sources_json"] and e["is_nasa"] == "parcial"]
nasa_false = [e["id"] for e in entries if e["in_sources_json"] and e["is_nasa"] is False]
print("sources:", n_src, "NASA true:", len(nasa_true), "partial:", len(nasa_part), "non-NASA:", len(nasa_false))
print("used (sources.json):", sum(1 for e in entries if e["in_sources_json"] and e["usado_sources_json"]))
print("code-consistent:", sum(1 for e in entries if e["in_sources_json"] and e["consistencia_uso"]))
print("inconsistent:", [e["id"] for e in entries if e["in_sources_json"] and not e["consistencia_uso"]])
bad = {u: p["status"] for u, p in probes.items() if p["status"] not in ("ok", "ok_sin_range")}
print("URLs probed:", len(probes), "not OK:", len(bad))
for u, st in sorted(bad.items()):
    print("  ", st, u)
print("visible without entry:", len(visible_no_entry))
for u, f in sorted(visible_no_entry.items()):
    print("  ", u, "<-", ", ".join(f)[:150])
print("dem_readers:", dem_readers)
print("lola_pattern_readers:", lola_pattern_readers)
print("figshare:", json.dumps(figshare, ensure_ascii=True)[:600])
