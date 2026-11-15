# -*- coding: utf-8 -*-
"""Genera docs/verification/map_states.md a partir de map_states.json (solo lectura del json)."""
import json
from pathlib import Path

OUT = Path("C:/SpaceApps2026_Hackathon/docs/verification")
r = json.loads((OUT / "map_states.json").read_text(encoding="utf-8"))

L = []
L.append("# Verificacion independiente: estados del mapa y cifras de portada")
L.append("")
L.append(f"Semilla {r['seed']}. Script: `docs/verification/scripts/verify_map_states.py`. Solo lectura de site/, config/, data/.")
L.append("")
L.append("## A. Cifras de portada")
L.append("")
L.append("| Cifra | Mostrado | Recontado | OK | Detalle |")
L.append("|---|---|---|---|---|")
for p in r["portada"]:
    det = p.get("detalle", "").replace("|", "/")
    L.append(f"| {p['cifra']} | {p['mostrado']} | {p['recontado']} | {'si' if p['ok'] else 'NO'} | {det} |")
L.append("")
L.append(f"Cuotas de cobertura Marte (area por cos(lat)): desbloqueada {r['mars_coverage_shares_pct']['unlocked']}%, "
         f"por descubrir {r['mars_coverage_shares_pct']['to_discover']}%, niebla {r['mars_coverage_shares_pct']['fog']}%.")
L.append("")
L.append("## B. Muestra por estratos (Wilson 95%)")
L.append("")
L.append("| Estrato | n | aciertos | tasa | Wilson 95% |")
L.append("|---|---|---|---|---|")
for s in r["strata"]:
    w = s["wilson95"]
    L.append(f"| {s['estrato']} | {s['n']} | {s['aciertos']} | {s['tasa']} | [{w[0]}, {w[1]}] |")
L.append("")
L.append(f"Total muestra (sin censo Luna): n={r['strata_sample_total']['n']}, aciertos={r['strata_sample_total']['aciertos']}.")
L.append("")
L.append("## C. Umbral Earth gap (dev NASADEM vs Copernicus)")
L.append("")
for c, v in r["umbral"]["check"].items():
    L.append(f"- {c}: recomputado {v['recomputed']:.10f}, run.json {v['run_json']:.10f}, diferencia {v['abs_diff']}, pares dev {v['n_dev_pairs']}")
L.append("")
L.append("## D. Discrepancias de la muestra")
L.append("")
if not r["discrepancies_sample"]:
    L.append("Ninguna.")
else:
    for d in r["discrepancies_sample"]:
        L.append(f"- {d}")
L.append("")
L.append("## E. Otros hallazgos")
L.append("")
L.append(f"- Orientacion del cache WorldCover: {r['orientation_worldcover_cache']}")
L.append(f"- Conjuntos de clase 2 (cobertura) iguales a la grilla completa: {r['grid_class2_set_equality']}")
L.append(f"- Features atlas vs parquet, diferencia maxima: {r['feature_consistency_atlas_vs_parquet_max_abs_diff']}")
L.append("")
(OUT / "map_states.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("ok")
