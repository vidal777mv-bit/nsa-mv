# Ledger: estado DESPUES (2026-11-15)

Antes: `before.md`. Respaldos: `_ui_backups/pre_ledger/` (facts.json, README.md, project_page.md, explain.json, tilt.json,
facts.duckdb, facts.parquet, ledger_views_before.json).

## 1. Limpieza de data/derived

- Movidos (no borrados): **336 archivos** a `_archive/derived_orphans_2026-11-15/data/derived/` (ruta relativa conservada).
  Manifest con ruta, bytes y motivo de cada uno: `_archive/derived_orphans_2026-11-15/MANIFEST.md`.
  - `data/derived/cards`: 408 -> 160 (248 movidos).
  - `data/derived/rehearsal`: 248 -> 160 (88 movidos).
- Vigentes = los 160 pares de `site/data/rankings` (campo `card`). `site/data/cards` y `site/data/rehearsal` ya tenian 160.
- Nadie lee por nombre fijo: `pipelines/rehearsal.py` filtra por el ranking. El unico lector que tomaba el directorio
  completo era `tools/build_ledger.py`, que ahora cuenta 160.

## 2. Ledger (data/derived/facts/facts.duckdb + facts.parquet)

| Medida | Antes | Despues |
|---|---|---|
| Hechos | 120.290 | 118.301 |
| Vistas nombradas | 71 | 77 |
| Sujetos pair | 248 | 160 |
| Sujetos earth_window | 4.225 | 4.225 |
| Hechos earth_window | 75.765 | 76.067 (+302 tilt) |
| Hechos target | 468 | 545 (+32 tilt, +45 capa lunar) |
| Hechos pair | 6.696 | 4.320 |
| Hechos validation | 65 | 73 (+8 validacion externa) |

Cambio neto: -2.376 filas de rehearsal (88 planes x 27 lineas) y +387 nuevas (tilt 334, capa lunar 45, validacion externa 8).

Hechos nuevos, cada uno con `produced_by` y `source_id` cuando lo hay:
- **Capa lunar** (`pipelines/moon_base.py`, PGDA LOLA, 9 de 10 sitios con valor): `illum_mean_pct`, `illum_max_pct`,
  `earth_vis_pct`, `psr_nearest_km`, `psr_area_km2`. Fuentes `pgda_illum_75s_120m`, `pgda_psr_75s_120m`,
  `pgda_earth_vis_75s_120m`, con URL. `apollo17_taurus_littrow` no tiene valor (fuera del producto 75 S a 90 S), asi que no tiene hecho.
  `verified` = la verificacion del centro del sitio en config/sites.json.
- **Tilt** (`tools/export_tilt.py`): `tilt_deg` y `downhill_azimuth_deg` de 167 terrenos (16 sitios como subject `target`,
  151 ventanas como `earth_window`), escala 8 km.
- **Validacion externa** (`pipelines/validate_external.py`), subject `validation` `external`: `n_pairs_listed` 5,
  `n_valid` 5, `min_pairs` 6, `n_within_tie` 5, `median_percentile` 26,84, `wilcoxon_p_less` 0,21875,
  `verdict` = "insuficiente", `pool_n_with_D` 2.724.

Vistas nuevas: `moon_base_sites` (9), `external_pairs_listed` (5), `external_pairs_valid` (5),
`external_median_percentile` (26,84), `external_wilcoxon_p` (0,21875), `external_verdict` ("insuficiente").

Vistas con valor cambiado (13, todas `rehearsal_*` y `rehearsal_pairs`): ahora cuentan los 160 pares vigentes.
Coinciden con la tabla de HOW_IT_WORKS 8b (landing yes 115 / partial 11 / no 34; cold partial 125 / no 35; low sun yes 70 / no 90;
driving yes 160). Las otras 58 vistas quedan identicas.

Los `fact_id` son posicionales: al quitar 2.376 filas de rehearsal cambian los ids posteriores. Ni facts.json ni las
plantillas usan fact_id. Las filas nuevas van al final para no mover el resto.

## 3. facts.json (site/data/facts.json)

- Antes: 26 cifras. Despues: **29**.
- **Las 26 cifras previas quedan identicas** (value, display, unit, ledger_view, definition). Se compararon una a una.
- Agregadas (solo nuevas): `moon_base_sites` = 9 sitios; `external_pairs_valid` = 5 pares; `external_verdict` = "insuficiente".
- Cambia solo `generated_at`. `rule` y `ledger` iguales. `explain.json` identico.
- Cambio en el exportador: un veredicto de texto se guarda como texto (antes solo se aceptaban numeros).
- sha256 facts.json despues: 39505d04746c7999dbb8e462fdf27ff416b83611aed1e1e4446e05b5fd878db8
- sha256 facts.duckdb despues: 9b8b60e32ff628bc77d0d4c8aa911123764100ad7986f0c01d3e020db6ac4a20

## 4. Textos generados (P-G)

- `README.md`: re-renderizado desde README.template.md. **Identico** al anterior.
- `docs/project_page.md`: re-renderizado desde docs/project_page.template.md. **Cambia una linea** (parrafo 5, "Read the
  dossier"). El texto anterior decia "Across all 248 pairs ... landing yes 167, partial 28, no 53 ... cold partial 182, no 66 ...
  low sun yes 85, no 163". El nuevo dice 160 pares con los numeros de la seccion 2.
  **No publicado.** Por la regla de "si una cifra previa cambia, parar", `docs/project_page.md` se restauro al anterior.
  El resultado renderizado queda en `_ui_backups/pre_ledger/project_page.rendered_candidate.md`.
  **Decision pendiente de Mario**: (a) aceptar el render nuevo (recomendado: el 248 contaba los 88 planes que se acaban de
  retirar) o (b) mantener el texto anterior. Para (a) basta copiar el candidato a `docs/project_page.md`.
- `docs/slides.md`: no re-renderizado (no estaba en el encargo). Su plantilla pasa R5.

## 5. Otra correccion: site/data/tilt.json

- `tilt.json` (15:16) tenia 255 terrenos; `site/data/terrain` tiene 167 carpetas. Las 88 de sobra eran terrenos ya movidos
  a `_archive/site_data_orphans_2026-11-15/` por el otro trabajo. El ledger los habria contado.
- Regenerado con su productor `tools/export_tilt.py`: **167 entradas, valores identicos en las 167**, 88 obsoletas
  retiradas. Respaldo: `_ui_backups/pre_ledger/tilt.json`. Lo leen el ledger y `site/js` (la UI lo busca por id).

## 6. Chequeos

| Chequeo | Antes | Despues |
|---|---|---|
| tools/check_ledger.py (R1 a R6) | 0 filas en las 6 | 0 filas en las 6 (exit 0) |
| tools/check_site_data.py | no corrido antes | RESULT: OK (16 targets, 16 rankings, 160 cards, 167 terrain folders) |
| pytest test_export_site_facts, test_render_facts, test_check_ledger, test_tilt | - | 30 passed |

- check_site_data avisa de `site/data/moon_base.json` como "huerfano (no referenciado)". Es un falso positivo: `site/js/app.js:1196`
  lo lee y el checker no lo conoce. Pendiente: anadirlo a su lista (no se toco).
- No existe test para `tools/build_ledger.py`. Verificado con el ledger real: conteos (45 capa lunar, 334 tilt, 8
  externa), R1 a R6 y la comparacion de vistas. No se anadio archivo de test nuevo.
- Test tocado: `tests/test_export_site_facts.py`. El fixture ahora pone `external_verdict` como texto y se agrego
  `test_verdict_figure_is_kept_as_text`.

## 7. Otros directorios de data/derived con el mismo problema (reportados, no movidos)

| Carpeta | Hallazgo | Por que no se movio |
|---|---|---|
| data/derived/refine/measure | 160 archivos: 72 usados por un ranking vigente, **88 no usados** (ventanas `<target>__pool__pool_N` que ningun ranking usa). | El ledger los lee todos (cuenta como "candidatos refinados", HOW_IT_WORKS 9). Mover cambia el ledger (earth_window 4.225 -> 4.137). Falta decision. |
| data/derived/mission | 379 archivos: 203 `pool__pool_N` (los lee neighbors.py), 16 de sitio, **160 con prefijo `<target>__`**. De estos, 72 usados y **88 no usados**. | Ningun lector toma los prefijados. Es el mismo conjunto de 88 de refine (no verificado archivo por archivo). Decision de Mario. |
| data/derived/sample | 108 JSON de corridas de muestra. | Son salidas de muestra (STANDARDS 10.7), no vigentes ni huerfanas en el mismo sentido. |
| data/derived/measure | 6.127 archivos. | No evaluado: son records de la piscina y de mars cells. |
| refine: 79 analogs de ranking sin archivo refine | Son `pool__pool_N` sin prefijo (ventanas no refinadas). | Ya es el hallazgo "refinados 67 vs 72" de HOW_IT_WORKS 13.2. Sin cambio. |

## 8. Documentacion desactualizada (no editada)

- `docs/HOW_IT_WORKS.md` 8b y 13.1 todavia dicen 248 pares y "archivos viejos por decidir": ya estan resueltos aqui.
  Pendiente actualizarlos (fuera del encargo).
- `build_ledger.py` sigue leyendo todo el directorio `data/derived/rehearsal`. Hoy quedan 160, pero un archivo viejo
  volveria a contar. Recomendacion: filtrar por los pares del ranking, como hace `rehearsal.py`.
