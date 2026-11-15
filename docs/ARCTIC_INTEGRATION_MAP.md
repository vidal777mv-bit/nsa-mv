# Mapa de integración: ventanas árticas en el pool de búsqueda de la Tierra

Fecha: 2026-11-14 (lectura de archivos a las 11:39). Solo lectura: no se corrió ningún pipeline ni prueba, no hay git, no se instaló nada. Lo único escrito es este documento. Lo que no se pudo determinar leyendo está marcado como "no determinado".

Congelados (no se tocan): medida (`_common.measure_raw`), `config/measure.json` (sigma), `data/derived/validation/noise_v1.3.json` (umbrales de empate).

---

## 0. Correcciones al punto de partida

- **2,065 son candidatos, no medidas.** `data/raw/earth/arctic_probe/candidates.json`: `kept_before_subsample` = 2065, banda 60-84 N. Medidas: **400** (`data/derived/arctic_probe/measures.json`, 400 de 400 `ok`, generado 08:49).
- **Hay un proceso escribiendo clips ahora.** Los `arc_*.tif` pasaron de 408 a 760 y luego a 769 entre 11:3x y 11:39. `clip_log.json` sigue con 400 entradas (08:49). Proceso no identificado. Las cifras de este mapa son una foto de 11:39.
- **El probe no aplica la exclusión de 25 km.** `arc_00141` está a 20.4 km de `devon_island` (`config/regions.json`, role `known_analog`). Las filas del probe no traen `near_known_analog` (`pipelines/arctic_probe.py:296-298`). Hoy ninguna ventana marcada cierra una celda (verificado: `arc_00141` y `arc_00037` no aparecen en `closing_windows`).
- **Hay dos listas de "conocidos" distintas.** Exclusión de búsqueda (25 km): `config/regions.json` role `known_analog`, 15 entradas. Novedad (círculos): `config/known_analog_regions.json`, 22 entradas. Difieren en 5 y 12 entradas (por ejemplo `svalbard` está solo en la de novedad; `devon_island` solo en la de exclusión). `arc_00037` cae dentro del círculo de Svalbard (novedad "known_region") y no está excluida de la búsqueda.

---

## 1. Cadena (en orden de dependencia)

Cada fila: qué lee, qué escribe y si depende del pool (lista de ventanas con `kind == "pool"` o `data/raw/earth/pool/index.json`).

### A. Construcción del pool (NASADEM, una vez)

| # | Script | Lee | Escribe | ¿Pool? |
|---|---|---|---|---|
| 1 | `pipelines/build_pool_index.py` (`items`, `coarse`, `spacing`, `candidates`, `clip`, `index`, `regions`) | STAC `esa-worldcover` (`items`); `config/regions.json` (role `known_analog` para la exclusión de 25 km); STAC `nasadem` (`clip`) | `data/raw/earth/pool/_worldcover_coarse/*`, `candidates.json`, `pool/pool_NNNNN.tif`, `pool/index.json`, entrada en `data/raw/manifest.json`, `data/raw/fetch_log.jsonl`; `regions` reescribe `config/regions.json` (`worldcover_share`) | Es la fuente |

### B. Medida y sigma

| # | Script | Lee | Escribe | ¿Pool? |
|---|---|---|---|---|
| 2 | `pipelines/build_measure.py --kind pool` | `pool/index.json` (vía `_common.pool_index`), `config/measure.json`, el GeoTIFF de cada ventana | `data/derived/measure/pool__pool_NNNNN.json` (`kind` pool, `role` pool, `sensor` nasadem, `source_id`) | Sí (`pool_jobs`) |
| 3 | `pipelines/calibrate_sigma.py` | `measure/*.json` con `kind == pool` y `status == ok` | `config/measure.json` (sigma, una vez) y `docs/CHANGELOG.md` | Sí. **Congelado: no volver a correr** |
| 4 | `pipelines/validate.py --noise` (o `--holdout`, una sola vez) | Solo registros `kind` region / holdout | `data/derived/validation/noise_v1.3.json` (o el holdout) | No (independiente del pool) |

### C. Búsqueda y refinado

| # | Script | Lee | Escribe | ¿Pool? |
|---|---|---|---|---|
| 5 | `pipelines/search.py` | `measure` pool ok (exige `near_known_analog` en todas, si no REFUSES); `noise_v1.3.json`; `measure` de cada target | `data/derived/ranking/<target>.json` (top 10, tie groups) | Sí |
| 6 | `pipelines/refine_search.py` | Top 10 de `ranking`; `measure` del target; un clip NASADEM de 8.5 km por candidato (`stac_clip`) | `data/derived/refine/<target>.json`, `refine/measure/<t>__pool__pool_N.json`, `refine/clips/*.tif` | Sí (candidatos NASADEM fijos) |
| 7 | `pipelines/mission_pct.py` | Targets y analogs de `ranking_file` (refinado si existe); `source_path` de cada registro | `data/derived/mission/<id>.json` | Indirecto (lista de analogs) |
| 8 | `pipelines/earth_context.py` | `ranking_file` (o todo el pool con `--all-pool`); registros; raster Köppen (`data/raw/reference/koppen`); Natural Earth (poblados, admin-1); `config/known_analog_regions.json` | `data/derived/context/earth_context.json` (hoy 2,000 pool + 160 refinados) | Sí |
| 9 | `pipelines/mars_atlas.py` | `data/raw/mars/pool/index.json`; medidas Mars; **todas** las `measure` pool ok (gemelos top 3); `earth_context.build` | `data/derived/measure/mars_NNNNN.json`, `data/derived/atlas/mars_run.json`, `site/data/atlas/mars_cells.json` | Sí (todo el pool) |
| 10 | `pipelines/light.py` | `pool/index.json` (no `measure`); `site/data/targets.json`; `config/light.json` | `data/derived/light/light.json` (claves `pool_NNNNN`) y copia en el sitio | Sí (índice) |
| 11 | `pipelines/coverage_grids.py` | `pool/index.json` (clase 2); `pool/_worldcover_coarse` (clase 1); medidas Mars y Moon | `site/data/coverage/{mars,moon,earth}.json` | Sí (índice y caché coarse) |

### D. Sitio (terreno, tarjetas, rankings)

| # | Script | Lee | Escribe | ¿Pool? |
|---|---|---|---|---|
| 12 | `pipelines/export_viz.py` (P7) | `ranking_file`; `mission/*.json`; `earth_context.json`; medidas por `window_record_path`; rasters de origen; `config/sites.json`, `bodies.json`, `missions.json`; validación | `data/derived/cards/*.json`; `site/data/terrain/<id>/` (height, hillshade, layers, meta); `site/data/cards/`, `rankings/`, `targets.json`, `viz.json` (VE), `bodies.json`, `missions.json`, `validation.json` | Sí (analogs) |
| 13 | `pipelines/discoveries.py` | Top 3 de targets Mars/Moon; `site/data/atlas/mars_cells.json`; `earth_context.json`; `known_analog_regions.json` | `site/data/discoveries.json` | Sí (analogs) |
| 14 | `pipelines/neighbors.py` (P-N, Earth gap) | `measure` pool ok (todas); `site/data/targets.json` y `site/data/atlas/mars_cells.json` (**requiere pasos 9 y 12 antes**); `earth_context`; cards/rankings del sitio; `known_analog_regions.json` | `data/derived/neighbors/{targets,mars_cells,earth_windows}.parquet`, `run.json` | Sí (origen del gap) |
| 15 | `pipelines/rehearsal.py` | `data/derived/cards/*.json` (pares); `light.json`; `config/rehearsal_rules.json`; `bodies.json`; `site/data/targets.json` | `data/derived/rehearsal/*.json`, `site/data/rehearsal/*.json` | Indirecto (ids `pool__pool_` vía `RH.light_window_key`) |
| 16 | `pipelines/export_ties.py` | `ranking_file` y `site/data/rankings/` (deben coincidir fila a fila; si no, se detiene) | `site/data/ties.json` | Indirecto |
| 17 | `pipelines/export_query.py` (P-Q) | `data/derived/neighbors/*.parquet` | `site/data/query/<tabla>/` | Sí (`earth_windows`; docstring dice "all 2000", línea 6) |
| 18 | `pipelines/export_sources.py` | `config/sources.json`; `site/data/terrain/*/meta.json` (cada `source_id` debe existir en `sources.json`) | `site/data/sources.json` | Indirecto (`cop_dem_glo30` ya existe: `config/sources.json:34`) |

### E. Libro de hechos y textos

| # | Script | Lee | Escribe | ¿Pool? |
|---|---|---|---|---|
| 19 | `tools/build_ledger.py` | **Todas** las `measure` (`data/derived/measure`, `status` None); `refine/measure`; `earth_context`; `site/data/atlas`, `coverage`, `discoveries`; `light.json`; `rehearsal/`; `neighbors/*.parquet`; `arctic_probe/results.json` y `measures.json` | `data/derived/facts/facts.duckdb` (tabla + vistas), `facts.parquet` | Sí |
| 20 | `tools/export_site_facts.py` | `facts.duckdb` (vistas, solo lectura); `site/data/discoveries.json` (cruce de conteos); `config/explain.json`; `config/measure.json` | `site/data/facts.json`, `site/data/explain.json` | Sí (textos de definición) |
| 21 | `tools/render_facts.py` | `README.template.md`, `docs/*.template.md`, `facts.duckdb` | `README.md`, `docs/*.md` generados | Vía agregados (`n_pool_windows`) |
| 22 | `tools/check_ledger.py`, `tools/check_site_data.py` | Ledger, plantillas, `site/data` | Nada (verifican) | Verifican |

### Rama experimental (no está en el pool)

| # | Script | Lee | Escribe | ¿Pool? |
|---|---|---|---|---|
| E1 | `pipelines/arctic_probe.py` (`items`, `coarse`, `candidates`, `clip`, `measure`, `results`, `control`) | `config/measure.json`; `noise_v1.3.json`; `neighbors/{mars_cells,targets,earth_windows}.parquet` (resultados); `pool/index.json` y medidas pool (solo control, 45-60 N) | `data/raw/earth/arctic_probe/*` (clips, `_worldcover_coarse`, `candidates.json`, `clip_log.json`), `data/derived/arctic_probe/{measures,results,sensor_control}.json` | Consume el pool como base |
| E2 | `tools/export_arctic.py` | `data/derived/arctic_probe/` | `site/data/arctic.json` | No |

Nota: `build_mars_pool.py` y `data/raw/mars/pool/` son el pool de Marte; no se mezclan con el de la Tierra.

### Orden de re-ejecución si se integra

Medir nuevas (2) → ranking (5) → refinado (6, si se decide) → mission (7) → context (8) → mars_atlas (9) → light (10) → coverage (11) → export_viz (12) → discoveries (13) → neighbors (14) → export_query (17) → rehearsal (15) → ties (16) → sources (18) → build_ledger (19) → export_site_facts (20) → render_facts (21) → checks (22).

**No re-correr:** `calibrate_sigma` (3) y `validate` (4). Ninguno lee el pool de forma que cambie su resultado, pero calibrate sí incluiría las árticas si se usa `--force`.

---

## 2. Dónde entra el pool (archivo:línea)

**Definición física (NASADEM, 56 S-60 N):**
- `pipelines/build_pool_index.py:56` `LAT_MIN, LAT_MAX = -56.0, 60.0`. Se usa en `:120` (bbox STAC de WorldCover) y `:257` (filtro de centros).
- `:57` `TARGET_N = 2000`; `:309-311` submuestreo a exactamente 2000 con `random.Random(SEED)`.
- `:335` `fetch.stac_clip("nasadem", "elevation", ...)`.
- `:415-417` entrada del índice: `id` (pool_NNNNN), `lat`, `lon`, `worldcover_share`, `near_known_analog`, `path`, `valid_fraction`. **No tiene campo de sensor ni de source_id.**
- `:418-420` `index.json` se **reescribe completo**. Cualquier re-run de `index` borra entradas añadidas a mano.
- `:421` entrada de manifiesto con `source_id: "nasadem_pool_index"`.
- `:108-111` `known_analogs()` lee `regions.json` role `known_analog`.

**Lectura del índice y filtros:**
- `pipelines/_common.py:254-266` `pool_index()` (ruta `data/raw/earth/pool/index.json`).
- `pipelines/_common.py:380-390` `window_records(kind, status)`: filtro por `kind` y `status` (default `ok`).
- `pipelines/_common.py:40` `WORLDCOVER_MIN_SHARE = 0.8`; `pipelines/build_measure.py:175-179` filtro de share.
- `pipelines/_common.py:422-427` `place_id()` (regla `pool__pool_`).
- `pipelines/_common.py:415-419` `ranking_file()` y `:430-434` `window_record_path()`.

**Rol y kind "pool":**
- `pipelines/build_measure.py:170` `id = pool__<id>`, `kind = "pool"`, `role = "pool"`.
- `pipelines/build_measure.py:171` `source_id = e.get("source_id", "nasadem")`.
- `pipelines/build_measure.py:172` `sensor = "nasadem"` (fijo, no lee el índice).
- `pipelines/build_measure.py:61` `DEFAULT_KINDS` incluye `pool`.
- Lectores de `kind == "pool"`: `search.py:116`; `neighbors.py:115` y `:410`; `mars_atlas.py:118`; `earth_context.py:214`; `calibrate_sigma.py:49`; `tools/build_ledger.py:301`.
- `tools/build_ledger.py:305` y `:677` (`n_pool_windows` cuenta `role == 'pool'`).

**Lectores del índice (sin filtro de kind):**
- `pipelines/light.py:226` y `:7` (docstring "the 2000 Earth windows").
- `pipelines/coverage_grids.py:167-170`.
- `pipelines/regional_sample.py:71`, `:125-126` (muestra de 40 con `rng.choice(len(windows))`).
- `pipelines/arctic_probe.py:475` (control, 45-60 N).

**Sensor NASADEM fijo:**
- `_common.py:233-236` `SENSOR_GLOBS`; `build_measure.py:58` `SENSORS`.
- `build_measure.py:138-141` (holdout y regiones; no es el pool).
- `build_pool_index.py:335` y `refine_search.py:72` (STAC `nasadem`).
- `refine_search.py:143` y `:162` `source_id: "nasadem"` fijo.
- `tools/build_ledger.py:256` (solo regiones); `:330` `source_id="nasadem"` para `elevation_m` de **todas** las ventanas.

**Banda en texto:** `config/explain.json:64`, `config/sources.json:17`, `STANDARDS.md:165`, `pipelines/coverage_grids.py:175`, `tools/export_site_facts.py:39` y `:48`, `site/js/ask.js:30`, `site/js/dossier.js:244`, `site/v2/app2.js:20`, `docs/project_page.template.md:90`, `docs/slides.template.md:78`.

---

## 3. Punto de inserción mínimo (propuesta)

**Vía A (recomendada): las árticas son filas más del índice del pool.** Tienen su propio sensor, se miden con el mismo `build_measure` y los lectores existentes (`kind == "pool"`) las toman sin cambiar su código.

Cambios de código (tres piezas, todas pequeñas):
1. **Índice.** Un paso nuevo que añada entradas a `data/raw/earth/pool/index.json` (sin usar `build_pool_index.py index`, que lo reescribe, `:418-420`). Campos por entrada:
   - `id`: `pool_02001` a `pool_04065` (continúa la numeración). Esto es obligatorio: `light.py` construye `pool__<key>`; `neighbors.py` filtra por `POOL_PREFIX` (`pool__pool_`); los regex de `site/js/data.js:29` y `site/js/dossier.js:77` esperan `pool_\d+`. Un id `arc_NNNNN` quedaría fuera de todos.
   - `lat`, `lon`, `worldcover_share` (de `candidates.json`), `valid_fraction` (de `clip_log.json`).
   - `near_known_analog`: 25 km contra `regions.json` role `known_analog`. Obligatorio: `search.py:117-121` rechaza la búsqueda entera si falta.
   - `path`: relativo a `data/raw/earth/arctic_probe/arc_NNNNN.tif`.
   - `source_id: "cop_dem_glo30"`, `sensor: "copdem"`, y `probe_id: "arc_NNNNN"` para trazabilidad.
2. **`build_measure.py:172`**: `"sensor": e.get("sensor", "nasadem")`. Una línea. `source_id` ya se lee en `:171`.
3. **Medir solo lo nuevo:** `build_measure.py --kind pool`. La reanudación por `measure_key` (`:237`) salta las 2,000 existentes.

Qué no cambia: `_common.measure_raw`, `config/measure.json`, `noise_v1.3.json`, las reglas de `search` y del empate, `validate`, y `calibrate` (no se corre).

**Guardas recomendadas (una línea cada una):**
- `calibrate_sigma.py:49`: filtrar `sensor == "nasadem"`. La guarda actual (`:86-90`) solo bloquea sin `--force`.
- `tools/build_ledger.py:301-305`: decidir el `role`. Si se queda `pool`, `n_pool_windows` (`:677`) y `earth_places_searched` pasan de 2,000 a 4,065, y el texto de `export_site_facts.py:39` ("NASADEM, 56 S to 60 N") queda falso. Si se usa `pool_arctic`, hay que tocar `:301` y `:677` y añadir una vista.
- `tools/build_ledger.py:330`: `source_id` por ventana, no `"nasadem"` fijo.
- `pipelines/refine_search.py:66-77` y `:143`, `:162`: para candidatos `cop_dem_glo30`, o bien se usa el clip Copernicus que ya existe (cambia `candidate_clip`), o bien se excluyen con motivo registrado. NASADEM por STAC no sirve por encima de 60 N (extensión en `config/sources.json:17`: -56 a 61; si STAC no devuelve ítems, `fetch.py` levanta `FetchError`). Hay que decidirlo antes de re-correr el refinado.
- `pipelines/coverage_grids.py:172`: la clase 1 de la Tierra lee solo `pool/_worldcover_coarse`. Las celdas por encima de 60 N no tendrían clase 1 sin añadir la caché `arctic_probe/_worldcover_coarse`.

**Vía B (alternativa): kind separado `pool_arctic`.** Protege sigma sin guardas, pero exige cambiar cinco lectores (`search.py:116`, `neighbors.py:115` y `:410`, `mars_atlas.py:118`, `earth_context.py:214`, `build_ledger.py:301`) a un conjunto de kinds.

**Predicción derivable (para la muestra de validación):** closed = (min(D_pool, D_arctic) ≤ thr). En las 211 celdas gap, D_pool > thr por definición, así que la integración solo cambia la marca de gap en las celdas que `arctic_probe` ya marcó como cerradas. Con n=400 son 87. Las listas de twins top 3 de Marte y los top 10 de los 16 targets sí pueden cambiar en cualquier celda. Este argumento no está probado: la muestra de validación debe ser las 211 celdas gap, los 7 Artemis III y las 16 listas de targets, en copia.

---

## 4. Supuestos que se rompen (archivo:línea)

**Código:**
- `build_pool_index.py:56-57`, `:120`, `:257`, `:309-311`: banda, 2000 fijos y submuestreo. Un re-run de `candidates` cambiaría la muestra.
- `build_pool_index.py:418-420`: `index` reescribe el archivo y borraría las árticas.
- `build_measure.py:171-172`: sensor y source por defecto `nasadem`.
- `refine_search.py:72`, `:143`, `:162`: NASADEM fijo.
- `earth_context.py:161`: el texto de origen de elevación dice "NASADEM window mean" para todas las ventanas. Aparece en `context.sources` de cada ventana.
- `search.py:117-121`: REFUSES si una ventana pool no tiene `near_known_analog`.
- `calibrate_sigma.py:49`, `:86-90`: incluiría las árticas con `--force`.
- `export_viz.py:414`: la VE del sitio es un solo valor sobre **todos** los terrenos exportados (hoy 0.8, `cards/run_log.jsonl`). Un terreno ártico más escarpado la bajaría y reescribiría todos los hillshade.
- `neighbors.py:17-19`: el docstring dice que ninguna ventana está marcada; con las árticas `arc_00141` quedaría marcada.
- `coverage_grids.py:11-13`, `:147`, `:167-172`, `:175`: clase 2 solo del índice; clase 1 solo del caché de pool; texto "2000 accepted, NASADEM 56S-60N" fijo.
- `light.py:7`: docstring "the 2000 Earth windows".
- `regional_sample.py:125-126`: `rng.choice(len(windows))` cambia la muestra de 40 si el índice crece. No está en la cadena principal, pero si se re-corre, su salida cambia.
- `arctic_probe.py:296-298`: filas sin `near_known_analog`. `:230` muta `bpi.LAT_MIN/LAT_MAX` solo en memoria.
- `tools/build_ledger.py:613-634` (`arctic_rows`): compara las listas de gap del probe con las del ledger y levanta `ValueError` si difieren. Tras integrar, el ledger tendrá menos celdas gap, así que el build se detiene. Hay que retirar o reescribir esta función, porque además duplicaría los hechos de cierre.
- `build_ledger.py:525`: mapeo `pool__` de las claves de `light.json`. Funciona solo si las claves son `pool_NNNNN`.
- `tools/export_site_facts.py:39` ("NASADEM, 56 S to 60 N") y `:48` ("covers 56 S to 60 N, no poles"). `:86` cruza con `discoveries.place_counts` y debe seguir cuadrando.
- `mars_atlas.py:118-119`: `top_twins` sobre todo el pool. Las 1,838 celdas cambian su top 3 aunque no cambie su marca de gap.

**Textos del sitio (copy):**
- `site/js/ask.js:30` `GAP_CAVEAT`: "2,000-window bare-ground Earth pool (56S–60N; polar regions not included)".
- `site/js/dossier.js:244`: "polar regions are not included".
- `site/v2/app2.js:20`: "NASADEM pool excludes the poles".
- `site/index.html:170`: "The search pool is mostly Sahara, Arabia and Central Asia" (revisar).
- `site/js/data.js:26-30` y `site/js/dossier.js:77`: regex de ids (ver Vía A).

**Config y documentos:**
- `config/explain.json:64`: "covers bare ground from 56 S to 60 N ... no polar ice caps". Se copia a `site/data/explain.json` por `export_site_facts`.
- `config/sources.json:17` (NASADEM, 56S-60N). `:45` (Copernicus, "Used for latitudes > 60N") ya es consistente.
- `STANDARDS.md:165` (regla de muestra "dentro de cobertura NASADEM 56S-60N") y `:156` (sigma "~2000"). Requiere enmienda de la especificación; es decisión de Mario.
- `docs/project_page.template.md:90` ("The Earth pool covers 56 S to 60 N only"). `:29` ya describe el experimento.
- `docs/slides.template.md:78` (notas: "covers 56 S to 60 N, so polar Earth is not included").
- `docs/data_notes.md:19` (texto escrito a mano: "2,000 NASADEM windows").
- `docs/target_inventory.md:74` (plan ártico de 600 tiles; obsoleto).
- `docs/verification/map_states.md:10` (verificación "2000 = 2000 filas"; rehacer).
- `README.template.md:53` (pool dominado por Sahara; revisar). `:9`, `:33` son agregados y se actualizan solos.

**Pruebas que pueden cambiar:** `tests/test_neighbors.py:145` (200 consultas: 100 de pool, sigue cumpliéndose). `tests/test_pipelines.py:252`, `:259`, `:260`, `:499` usan datos reales y esperan `== 2` (refusal); no dependen del tamaño del pool. `tests/test_render_facts.py:49-52` usa "2000" como fixture.

---

## 5. Costo

| Paso | Tiempo registrado | Fuente |
|---|---|---|
| Coarse WorldCover (2,054 tiles, pool) | 171 s, 16 hilos | `data/raw/fetch_log.jsonl` (`coarse_run`) |
| Clip NASADEM pool (2,000 ventanas) | 978 s, 8 hilos, mediana 3.83 s/ventana | `fetch_log.jsonl` (`pool_clip_run`) |
| Índice pool | ~25 s (02:41:37 a 02:42:02) | `fetch_log.jsonl` (`pool_index`) |
| build_measure pool (2,000) | Conflicto: CHANGELOG línea 46 dice ~3 min; el log dice fin a 02:51:50, es decir ~10 min tras el índice (inferencia) | `docs/CHANGELOG.md`, `data/derived/measure/run_log.jsonl` |
| Clips árticos ya bajados (400) | Mediana 2.15 s/ventana; suma 16.9 min en serie | `data/raw/earth/arctic_probe/clip_log.json` |
| Clips árticos restantes (~1,665) | Estimación ≈ 6-8 min con 8 hilos (el proceso ya está corriendo) | estimación a partir de lo anterior |
| Caché coarse árticas (664 tiles) | Hecha; sin tiempo registrado | `arctic_probe/_worldcover_coarse` |
| Medida árticas (400) | No determinado (no hay tiempo en el log) | `arctic_probe.py` solo imprime |
| Refinado (124 clips NASADEM de 8.5 km) | No determinado. Riesgo: STAC NASADEM dio 502 antes | `docs/verification/provenance.md:110` |
| neighbors | 5.58 s (1,854 consultas) | `data/derived/neighbors/run.json` |
| export_viz, mars_atlas, earth_context, light, build_ledger | No determinado (sin tiempo en log). export_viz produjo 176 terrenos | `data/derived/cards/run_log.jsonl` |
| Disco | ~0.5 MB por clip: ~1 GB para 2,065 (estimación; README: 213 MB para ~440 archivos) | `data/derived/arctic_probe/README.md` |

El costo grande no es el cómputo. Son la descarga de las árticas que faltan (S3 público de Copernicus, ~0.5 MB por ventana) y el refinado, que depende de STAC NASADEM, que no sirve por encima de 60 N.

---

## 6. Pruebas (solo listar; no ejecutadas)

Según la regla del proyecto, correr solo los tests de lo que se toque y sus consumidores directos.

| Pieza tocada | Tests |
|---|---|
| `build_pool_index.py` (índice, nuevo paso de append) | Ninguno importa `build_pool_index`. Solo `tests/test_fetch.py` (funciones de `fetch`). Hace falta un test nuevo para el append |
| `_common.py` (`pool_index`) | `tests/test_pipelines.py::test_pool_index_accepts_list_and_windows_forms` |
| `build_measure.py` (sensor de pool) | `tests/test_pipelines.py::test_build_measure_ok_skip_and_null_rules`, `::test_build_measure_resume_kind_and_force`; `tests/test_measure.py` |
| `calibrate_sigma.py` (guarda) | `tests/test_pipelines.py::test_calibrate_sample_writes_sample_config_only`, `::test_calibrate_refuses_small_real_pool` |
| `search.py` | `tests/test_pipelines.py::test_search_excludes_near_known_analog_flag_and_ranks` |
| `refine_search.py` | `tests/test_refine_search.py` |
| `mission_pct.py` | `tests/test_mission.py`; `tests/test_pipelines.py::test_mission_pct_matches_direct_recompute` |
| `earth_context.py` | `tests/test_earth_context.py` |
| `mars_atlas.py` | `tests/test_mars_atlas.py` |
| `light.py` | `tests/test_light.py` |
| `coverage_grids.py` | `tests/test_coverage_grids.py` |
| `export_viz.py` (VE, cards, terreno) | `tests/test_pipelines.py::test_export_viz_contract`, `::test_card_scoring_split_pair_exaggeration_and_place`; `tests/test_viz.py` |
| `discoveries.py` | `tests/test_discoveries.py` |
| `neighbors.py` | `tests/test_neighbors.py` (incluye `test_exactness_sample_200_queries_on_real_data`, que usa datos reales) |
| `rehearsal.py` | `tests/test_rehearsal.py` |
| `export_query.py` | `tests/test_export_query.py` |
| `export_ties.py` | `tests/test_export_ties.py` |
| `export_sources.py` | `tests/test_export_sources.py` |
| `build_ledger.py` | `tests/test_check_ledger.py`, `tests/test_render_facts.py` (importa `build_ledger`) |
| `export_site_facts.py` | `tests/test_export_site_facts.py` |
| `render_facts.py` | `tests/test_render_facts.py` |
| `check_site_data.py` | `tests/test_check_site_data.py` |
| `arctic_probe.py` | `tests/test_arctic_probe.py` |
| `export_arctic.py` | Ninguno (no existe `test_export_arctic.py`) |
| `validate.py` (no se toca) | `tests/test_pipelines.py::test_validate_noise_sample_writes_thresholds`; `tests/test_stats.py` |
