import json, os, collections

ROOT = r"C:\SpaceApps2026_Hackathon"
OUT = os.path.join(ROOT, "docs", "verification", "arctic_top10")
TERR = os.path.join(ROOT, "site", "data", "terrain")

rows = json.load(open(os.path.join(OUT, "_list_stage.json"), encoding="utf-8"))

# Visual classification (hillshade contact sheets), keyed by pool number.
# LISO: smooth surface with low texture (relief p99-p1 below ~60 m, or visibly flat).
LISO = {
    "02787": "superficie lisa, casi sin textura (relieve p99-p1 22 m)",
    "03166": "superficie lisa, casi sin textura (relieve 35 m)",
    "03134": "superficie lisa, sin textura salvo lineas tenues (relieve 52 m)",
    "02045": "superficie lisa, textura tenue (relieve 56 m)",
    "02292": "superficie lisa, textura tenue (relieve 59 m)",
    "02899": "superficie lisa, textura tenue (relieve 60 m); Greenland",
    "03196": "mayormente lisa con un escalon/cresta (relieve 350 m); ice 0.199, justo bajo el limite 0.20; top 1 Mons Mouton",
}
OTRO = {
    "03541": "suave con lineas de flujo, relieve alto (451 m)",
    "02550": "suave con bandas, relieve 204 m",
    "03937": "suave con crestas bajas, relieve 603 m",
    "03310": "suave con lineas tenues, relieve 373 m",
}


def classify(pid):
    if pid in LISO:
        return "LISO-SOSPECHOSO", LISO[pid]
    if pid in OTRO:
        return "OTRO", OTRO[pid]
    return "ROCA", "relieve rocoso, valles y crestas visibles"


def relief(pid):
    m = json.load(open(os.path.join(TERR, "pool__pool_" + pid, "meta.json"), encoding="utf-8"))
    return round(m["relief_p99_p1_m"], 1)


out_rows = []
for r in rows:
    pid = r["pool_key"][len("pool_"):]
    cls, note = classify(pid)
    out_rows.append({
        "site": r["site"],
        "rank": r["rank"],
        "analog_id": r["analog_id"],
        "D": round(r["D"], 4),
        "analog_place": r["analog_place"],
        "lat": r["lat"],
        "lon": r["lon"],
        "ice_share": round(r["ice_share"], 4) if r["ice_share"] is not None else None,
        "bare_share_full": round(r["bare_share_full"], 4) if r["bare_share_full"] is not None else None,
        "relief_p99_p1_m": relief(pid),
        "greenland": r["greenland_name"],
        "top1": r["rank"] == 1,
        "clase": cls,
        "nota": note,
    })

n_rows = len(out_rows)
uniq = sorted({r["analog_id"] for r in out_rows})
cls_rows = collections.Counter(r["clase"] for r in out_rows)
cls_uniq = collections.Counter(classify(u[len("pool__pool_"):])[0] for u in uniq)
sosp = [r for r in out_rows if r["clase"] == "LISO-SOSPECHOSO"]
gl = [r for r in out_rows if r["greenland"]]
gl_cls = collections.Counter(r["clase"] for r in gl)
top1 = [r for r in out_rows if r["top1"]]
top1_arctic_sites = sorted({r["site"] for r in top1})
top1_sosp = [r for r in top1 if r["clase"] != "ROCA"]

summary = {
    "scope": "gemelos arcticos (pool__pool_NNNNN, NNNNN > 2000) en rank <= 10 de site/data/rankings/*.json",
    "n_filas_top10": n_rows,
    "n_gemelos_unicos": len(uniq),
    "por_clase_filas": dict(cls_rows),
    "por_clase_unicos": dict(cls_uniq),
    "greenland_filas": len(gl),
    "greenland_por_clase": dict(gl_cls),
    "top1_filas": [{"site": r["site"], "id": r["analog_id"], "clase": r["clase"]} for r in top1],
    "top1_sospechosos": [{"site": r["site"], "id": r["analog_id"], "lugar": r["analog_place"], "ice_share": r["ice_share"]} for r in top1_sosp],
    "liso_sospechoso": [{"site": r["site"], "rank": r["rank"], "id": r["analog_id"], "lugar": r["analog_place"], "ice_share": r["ice_share"], "relief_p99_p1_m": r["relief_p99_p1_m"]} for r in sosp],
    "metodo": "clasificacion visual de hojas de contacto (moon.png, mars.png); relieve de meta.json como apoyo. Miniaturas 180x180 de site/data/terrain/<analog_id>/hillshade.png (todas existian; ninguna se calculo). Sombreado del sitio como referencia.",
    "nota_ice_rule": "shares.json: ice_share_max 0.2; la regla es menor a 0.2. Ninguna fila supera 0.2; mayor es 0.199 (mons_mouton_plateau rank 1).",
}

json.dump({"resumen": summary, "filas": out_rows}, open(os.path.join(OUT, "arctic_top10.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# Markdown
L = []
L.append("# Revision visual de gemelos articos en top 10\n")
L.append("Alcance: gemelos `pool__pool_NNNNN` con NNNNN > 2000 en rank <= 10 de los 16 sitios. Hojas: `moon.png`, `mars.png`.\n")
L.append("## Conteos\n")
L.append(f"- Filas en top 10: **{n_rows}** (gemelos unicos: {len(uniq)})")
L.append(f"- ROCA: {cls_rows.get('ROCA',0)} filas ({cls_uniq.get('ROCA',0)} unicos)")
L.append(f"- OTRO: {cls_rows.get('OTRO',0)} filas ({cls_uniq.get('OTRO',0)} unicos)")
L.append(f"- LISO-SOSPECHOSO: {cls_rows.get('LISO-SOSPECHOSO',0)} filas ({cls_uniq.get('LISO-SOSPECHOSO',0)} unicos)")
L.append(f"- Greenland: {len(gl)} filas (ROCA {gl_cls.get('ROCA',0)}, OTRO {gl_cls.get('OTRO',0)}, LISO {gl_cls.get('LISO-SOSPECHOSO',0)})")
L.append("")
L.append("## Top 1\n")
for r in top1:
    L.append(f"- {r['site']}: {r['analog_id']} ({r['analog_place']}), ice {r['ice_share']:.3f} -> **{r['clase']}**")
L.append("")
L.append("## LISO-SOSPECHOSO\n")
L.append("| sitio | rank | id | lugar | ice_share | relieve p99-p1 (m) |")
L.append("|---|---|---|---|---|---|")
for r in sosp:
    L.append(f"| {r['site']} | {r['rank']} | {r['analog_id']} | {r['analog_place']} | {r['ice_share']:.3f} | {r['relief_p99_p1_m']} |")
L.append("")
L.append("## Filas completas\n")
L.append("| sitio | rank | id | D | lugar | lat | lon | ice | bare | relieve | clase |")
L.append("|---|---|---|---|---|---|---|---|---|---|---|")
for r in out_rows:
    L.append(f"| {r['site']} | {r['rank']} | {r['analog_id']} | {r['D']} | {r['analog_place']} | {r['lat']} | {r['lon']} | {r['ice_share']} | {r['bare_share_full']} | {r['relief_p99_p1_m']} | {r['clase']} |")
L.append("")
L.append("## Nota de metodo\n")
L.append("- Clasificacion visual a ojo de las miniaturas, con el relieve p99-p1 de meta.json como apoyo. Es una revision de sombreado, no una verificacion de hielo.")
L.append("- En el sombreado del sitio aparece referencia (un recuadro por sitio, sin borde).")
L.append("- Borde rojo en las miniaturas = lugar con 'Greenland' en el nombre.")
L.append("- Todas las miniaturas usan el hillshade del propio gemelo (site/data/terrain/pool__pool_NNNNN/hillshade.png). El prefijo del sitio no existe en esos directorios.")
L.append("")
open(os.path.join(OUT, "arctic_top10.md"), "w", encoding="utf-8").write("\n".join(L))

print(json.dumps(summary, ensure_ascii=False, indent=1))
