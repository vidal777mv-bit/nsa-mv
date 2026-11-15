"""Render docs/verification/provenance.md from provenance.json (read-only input, writes only the .md)."""
import json
import pathlib

OUT = pathlib.Path(r"C:\SpaceApps2026_Hackathon\docs\verification")
entries = json.loads((OUT / "provenance.json").read_text(encoding="utf-8"))


def status_of(e):
    res = []
    for u, r in (e.get("url_checks") or {}).items():
        st = r.get("status")
        if st in ("ok", "ok_sin_range"):
            res.append("ok")
        else:
            res.append(f"{st} ({r.get('http_code', '')})".replace(" ()", ""))
    if not res:
        return "n/a"
    return "; ".join(sorted(set(res)))


def shown_short(e):
    s = e.get("mostrado_en_sitio") or []
    if not s:
        return "no"
    parts = []
    for x in s:
        if x.startswith("textura"):
            parts.append("textura globo")
        elif x.startswith("relieve"):
            tg = x.split(": ", 1)[1] if ": " in x else ""
            parts.append(f"relieve: {len(tg.split(', '))} objetivo(s)")
        elif x.startswith("carpetas"):
            n = x.rsplit(": ", 1)[-1]
            parts.append(f"terreno x{n}" if n.isdigit() else "terreno")
        elif x.startswith("texto en site"):
            parts.append("texto")
        elif x.startswith("listada"):
            parts.append("ref")
    return ", ".join(dict.fromkeys(parts)) or "no"


def used_short(e):
    if e.get("uso_tipo", "").startswith("textura"):
        return "textura"
    n = len(e.get("usado_en_scripts") or [])
    if e["usado_sources_json"]:
        return f"si ({n} archivos)" if n else "si (manual)"
    return "no"


def rows(group):
    out = ["| id | cuerpo | misión / instrumento | usado | en sitio | URL (estado) |", "|---|---|---|---|---|---|"]
    for e in group:
        out.append(f"| `{e['id']}` | {e['cuerpo']} | {e['mision_instrumento']} | {used_short(e)} | "
                   f"{shown_short(e)} | {status_of(e)} |")
    return out


src = [e for e in entries if e["in_sources_json"]]
nasa = [e for e in src if e["is_nasa"] is True]
part = [e for e in src if e["is_nasa"] == "parcial"]
other = [e for e in src if e["is_nasa"] is False]
visible = [e for e in entries if not e["in_sources_json"] and e["id"].startswith("SIN_ENTRADA:") and e["id"] != "SIN_ENTRADA:site/data/sample"]

lines = []
lines.append("# Procedencia de datos (verificación)\n")
lines.append(f"Fuentes en `config/sources.json`: **{len(src)}**. NASA: **{len(nasa)}**; mixta (MOLA NASA + HRSC ESA): "
             f"**{len(part)}**; no NASA: **{len(other)}**. Usadas por el análisis (`used`): "
             f"**{sum(1 for e in src if e['usado_sources_json'])}**.\n")
lines.append("Columna *usado*: scripts de `pipelines/`, `src/`, `tools/` que leen la fuente (por id, nombre de archivo, "
             "o por `dem_source_id` de `sites.json`). *en sitio*: relieve/textura/texto/referencia que la muestra "
             "(`site/data/terrain/*/meta.json`, `site/data/targets.json`, `site/assets/globes/`, `site/references.html`).\n")
lines.append("## NASA\n")
lines += rows(nasa + part)
lines.append("\n## No NASA\n")
lines += rows(other)
lines.append("\n## Visible en el sitio sin entrada en `sources.json`\n")
for e in visible:
    lines.append(f"- {e['url']} ({e['mostrado_en_sitio'][0].replace('URL en: ', '')[:110]})")
lines.append("- `site/data/sample/*`: datos sintéticos, no se ven con `DATA_BASE = data/`.")
lines.append("- `three.js` (CDN jsdelivr) y fuentes Google en `site/v2.html`: software o tipografía, no datos.")
lines.append("\n## Conflictos de licencia y avisos\n")
lines.append("- **nasadem**: CONFLICTO sin resolver. EOSDIS dice 'free and open'; Planetary Computer dice 'proprietary'.")
lines.append("- **nasa_svs_lroc_colour_moon** (textura de la Luna): guía de medios NASA, dar crédito; no es dominio público.")
lines.append("- **LOLA (PGDA), LROC, Diviner**: sin texto de licencia publicado; se trata como público con cita.")
lines.append("- **jezero_ctx_trn_dtm_20m**: la ficha del producto no se leyó.")
lines.append("- **Copernicus GLO-30 y MODIS** (Planetary Computer dice 'proprietary'): la licencia COP-DEM-GLO-30-F rige; MODIS sin usar.")
lines.append("\n## Comprobación de URLs (una sonda por URL, sin reintentos)\n")
lines.append("- STAC de Planetary Computer: la raíz responde, pero las colecciones `nasadem`, `cop-dem-glo-30`, "
             "`esa-worldcover`, `modis-11A2-061` dan **502**. Eso bloquea la descarga por STAC mientras siga así.")
lines.append("- `planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/` (página en sources.json): **404**. Sin usar.")
lines.append("- `esa-worldcover.s3.../v200/2021/map/` (en references.html): **404**; es un prefijo de carpeta, el dato se baja por STAC.")
lines.append("- `cdn.jsdelivr.net/.../examples/jsm/`: **404**; es carpeta, no archivo (imports de three.js).")

(OUT / "provenance.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("written", len(lines), "lines")
for e in src:
    print(e["id"], "|", e["is_nasa"], "|", used_short(e), "|", shown_short(e), "|", status_of(e))
