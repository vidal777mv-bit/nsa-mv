# Correcciones de documentacion, 2026-11-15

Alcance: solo texto de documentos y comentarios/docstrings. No se cambio logica, valores de config, datos, ledger ni los archivos que se regeneran de plantillas (`tools/build_ledger.py`, `tools/export_site_facts.py`, `data/`, `site/data/`, `README.md`, `docs/project_page.md`). No hubo commit, instalacion, ni corrida de pipelines o tests.

## Correcciones

| # | Archivo:linea | Antes | Despues | Evidencia |
|---|---|---|---|---|
| 1 | `config/earth_pool_rules.json:19` (`bands[arctic].built_by`) | `pipelines/pool_add_arctic.py (rows pool_02001.., ...)` | `pipelines/arctic_probe.py (candidates and clips) + pipelines/pool_rules.py apply (writes the Arctic rows pool_02001.., id = 2000 + arctic probe number, probe_id kept; the ice, bare and 25 km flags of every row). (The former name pipelines/pool_add_arctic.py does not exist.)` | El archivo no existe en `pipelines/`. `pipelines/pool_rules.py` (docstring lineas 1-13; `apply_rows`, lineas 283-331) escribe las filas Arctic con id `pool_{n_nasadem + N:05d}`. `pipelines/arctic_probe.py` (`cmd_candidates`, `cmd_clip`) genera candidatos y clips. Solo cambio el string; el JSON parsea. |
| 2 | `pipelines/light.py:1` (docstring) | `... and the 2000 Earth windows, plus ...` | `... and the 4,065 Earth windows, plus ...` | `data/raw/earth/pool/index.json` tiene 4,065 filas (lista). `main()` (lineas 226-231) usa `pool_index()` y todas las filas (`sorted(windows_all)`), no solo las aceptadas. `pool_index` en `pipelines/_common.py:254`. |
| 3 | `pipelines/light.py:7` (docstring, lista de lecturas) | `- data/raw/earth/pool/index.json (the 2000 Earth windows: id, lat)` | `- data/raw/earth/pool/index.json (the 4,065 Earth windows: id, lat; excluded rows are included and flagged in the index)` | Igual que 2. |
| 4 | `STANDARDS.md:157` (nueva vineta bajo 10.1) | (no existia) | "Method note (sigma, 2026-11-15)": sigma calibrada 2026-11-14 02:53:43 UTC sobre las 2,000 ventanas NASADEM originales, antes de la regla de hielo; 34 con hielo >= 20% (2 tambien con suelo desnudo < 80%), 1 solo con suelo desnudo < 80%; sigma congelada a proposito; efecto esperado; cifras informativas 1.4826 x MAD con y sin las 35 ventanas. `config/measure.json` no cambia. | `data/derived/pool_rules/summary.json`, `summary.nasadem`: `excluded_ice_share` 34, `excluded_bare_share_full` 1, `flag_ice_and_bare` 2 (la exclusion evalua hielo primero). `data/derived/measure/run_log.jsonl` y `docs/CHANGELOG.md` (seccion sigma). Reproduccion: `_backup_pre_arctic/data/derived/measure/pool__pool_*.json` (2,000 registros `ok`, `nasadem`) da exactamente los 6 sigma de `config/measure.json`. Ver tabla abajo. |
| 5 | `STANDARDS.md:300-303` (10.14, despues de R5) | Solo R1 a R5 | Se agrega R6 con la definicion de `tools/check_ledger.py` (docstring) y el SQL de `RULES["R6"]`: cada fact de feature (`slope_p95_deg`, `hi`, `coherence`, `hurst`, `ridge_pct`, `valley_pct`) viene de un registro cuyo `measure_key` es igual al de `config_v1.3`. | `tools/check_ledger.py` lineas 9-12 (docstring) y 47-56 (`RULES["R6"]`). |
| 6 | `docs/HOW_IT_WORKS.md:6` (encabezado) | (no existia) | Nota: pasada de documentacion del 2026-11-15; items 1, 2, 4, 5, 8 de la seccion 13 corregidos o anotados; secciones 11b y 11c agregadas. | Esta misma pasada. |
| 7 | `docs/HOW_IT_WORKS.md:123` (seccion 4, antes "Discrepancy") | Discrepancia: cita a `pool_add_arctic.py` | "Corrected 2026-11-15": script real por regla (arctic_probe, pool_rules shares/apply, build_pool_index). | Ver fila 1 y las funciones citadas. Verificado: `shares` calcula bare/ice sobre el disco completo de 4 km; `apply` pone `excluded` (ice >= 0.2, bare < 0.8, sin clip) y la bandera de 25 km en Arctic; `build_pool_index.py` `cmd_index` pone la bandera de 25 km en NASADEM (`EXCLUDE_KM = 25.0`). |
| 8 | `docs/HOW_IT_WORKS.md:148` (seccion 5, despues del caveat) | Solo caveat | Nota de metodo sigma (misma sustancia que fila 4), con las cifras informativas. | Fila 4. |
| 9 | `docs/HOW_IT_WORKS.md:221` (8a) | "the docstring ... still says 2000 Earth windows" | "Corrected 2026-11-15: ... now says 4,065" | Fila 2. |
| 10 | `docs/HOW_IT_WORKS.md:276` (9) | "STANDARDS 10.14 lists R1 to R5 ..." | Agrega: R6 ya definido en STANDARDS 10.14. | Fila 5. |
| 11 | `docs/HOW_IT_WORKS.md:329` (nueva 11b) | (no existia) | "Permanent Moon base layer": cifras de `docs/verification/moon_base.md` con su origen, y la verificacion por sitio contra cifras publicadas NO lograda. | `docs/verification/moon_base.md` (secciones "Chequeos internos", "Verificacion contra cifras publicadas", "Diferencias de metodo"). |
| 12 | `docs/HOW_IT_WORKS.md:338` (nueva 11c) | (no existia) | "External validation": veredicto insuficiente, 5 de 6 pares, mediana 26.84, Wilcoxon p = 0.2188, exclusiones. | `docs/validation/external/RESULTS.md` (cabecera, tablas principal y de segunda forma) y `docs/validation/external/PREREG.md` (fecha 2026-11-15 17:35). |
| 13 | `docs/HOW_IT_WORKS.md:365-373` (seccion 13) | Lista sin estado | Items 4, 5 y 8 marcados corregidos/anotados. Items 1, 2, 3, 6, 7 y 9 marcados "[open, not in this pass]". | Fuera del alcance de esta pasada. |
| 14 | `docs/ARCTIC_INTEGRATION.md:51` | "The 211 Mars gap cells ..." | Mismo texto + "(historical, before the Arctic integration; current: 84 of 1,838 with all bands, 215 with NASADEM only)" | `site/data/facts.json`: `mars_gap_places` 84, `mars_gap_places_nasadem` 215, `mars_places_measured` 1,838. |
| 15 | `docs/ARCTIC_INTEGRATION_MAP.md:154` (final de linea) | Predicciones con 211 y 87 (n = 400) | Marca historica al final de la linea con las cifras actuales. | Igual que fila 14. |
| 16 | `docs/CHANGELOG.md:160` (final de linea) | "Closes 87 of 211 Mars gap cells ..." (probe de 400) | Marca historica al final de la linea. | Igual que fila 14. Texto original intacto. |
| 17 | `docs/CHANGELOG.md:161` | "gap aggregates (211/1838, 11.5 %, ...)" | Marca historica tras "Wilson 10.1-13.0)". | Igual que fila 14. |
| 18 | `docs/REDESIGN_V2.md:41` | "mars_gap_places (211), mars_gap_pct (11.5%)" | Marca historica tras "mars_gap_pct (11.5%)". | Igual que fila 14. El archivo esta en `.gitignore:82`, por eso no aparece en `git diff`. |

Sin cambio, verificado: `*.template.md` (incluidos `README.template.md`, `docs/project_page.template.md`, `docs/slides.template.md`), `STANDARDS.md` (salvo lo indicado), `site/README.md`, `REFERENCES.md`: no contienen 211, 87 ni 400 ventanas. Las plantillas usan placeholders `{{agg:...}}` y no requirieron cambio.

## Sigma: cifras informativas (no escritas en config)

Calculadas con 1.4826 x MAD (`src/analog/core/stats.py`, `robust_sigma`) sobre `_backup_pre_arctic/data/derived/measure/pool__pool_*.json`, con y sin las 35 ventanas excluidas (lista de `data/raw/earth/pool/index.json`, filas NASADEM con `excluded`).

| Feature | `config/measure.json` (sigma congelada) | Reproduccion con 2,000 ventanas (n) | Sin las 35 ventanas (n) | Cambio |
|---|---|---|---|---|
| slope_p95_deg | 3.04096 | 3.04096 (2000) | 2.89275 (1965) | -4.9% |
| hi | 0.0640131 | 0.0640131 (1994) | 0.0635761 (1959) | -0.7% |
| coherence | 0.156923 | 0.156923 (2000) | 0.157907 (1965) | +0.6% |
| hurst | 0.200185 | 0.200185 (2000) | 0.196630 (1965) | -1.8% |
| ridge_pct | 1.82397 | 1.82397 (2000) | 1.72797 (1965) | -5.3% |
| valley_pct | 0.61439 | 0.61439 (2000) | 0.575991 (1965) | -6.3% |

Los 1,965 registros aceptados coinciden con el backup en las 6 features (0 diferencias).

## Hallazgos colaterales (no tocados; para el agente que reconstruye el ledger)

1. **Hash de `config/earth_pool_rules.json` cambio.** Antes `9e460444...`, ahora `d74c9c4d...`. `data/derived/pool_rules/summary.json` y `shares.json` (y la procedencia de `coverage_grids`) guardan el hash anterior. `check_shares_rules` no lo compara (solo `bare_classes`, `ice_class`, `disk_radius_km`), asi que nada falla, pero la procedencia queda desactualizada hasta el siguiente `pool_rules apply`.
2. **Registros de medicion de las 35 ventanas.** La corrida de `build_measure` de 2026-11-15 03:43:39 UTC dejo `data/derived/measure/pool__pool_*.json` de esas 35 con `status: excluded` y `features: null`. `calibrate_sigma.py` filtra `status == ok`, asi que una re-corrida daria sigma de 1,965 ventanas. El respaldo pre-Arctic conserva las features. Esto afecta la reproducibilidad, no `config/measure.json`.
3. **Descripcion del disco de bare share.** `STANDARDS.md` 10.2 dice "the 8 km disk". El codigo (`pipelines/pool_rules.py`, `pipelines/build_pool_index.py` `grid_candidates`) y `config/earth_pool_rules.json` (`bare_share_disk`) usan el disco de radio 4 km (8 km de diametro). No se toco, fuera de la lista.
4. **`git status`** muestra modificados `tools/build_ledger.py` y `tools/export_site_facts.py`, y como sin seguimiento (untracked) `docs/SUBMISSION_FORM.md` y `docs/verification/ledger/`. No son de esta pasada.
5. **Segunda forma en `RESULTS.md`.** La tabla de verificacion de segunda forma tiene solo 2 filas (holuhraun_iceland, pinacate_gran_desierto), no las 5 pares.

## Verificacion hecha

- `config/earth_pool_rules.json` parsea como JSON despues de la edicion.
- `pipelines/light.py` parsea (`ast.parse`).
- `git diff --numstat` de los archivos tocados: STANDARDS 5 lineas anadidas; earth_pool_rules 1 cambio; ARCTIC_INTEGRATION 1; ARCTIC_INTEGRATION_MAP 1; CHANGELOG 2; light.py 2 cambios; HOW_IT_WORKS 35 anadidas / 12 quitadas. Sin cambio de finales de linea.
- Cifras de `site/data/facts.json` leidas y citadas (84, 215, 1,838).
- No se ejecutaron pipelines, tests ni suites.
