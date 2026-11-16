# Validacion externa del motor de analogos: PRE-REGISTRO

**Fecha y hora de este documento:** 2026-11-15, 17:35 (hora local, CST). Escrito ANTES de medir ninguna ventana de las regiones nuevas y ANTES de leer cualquier D de este analisis. No se modifica despues; si algo falla, se reporta, no se cambia el criterio.

## 1. Pregunta

Los lugares de la Tierra que la NASA u otra agencia ya usa como analogos de un sitio de Marte o de la Luna, ¿quedan mas cerca de ese sitio segun la medida congelada v1.3 (`config/measure.json`) que un lugar cualquiera del pool de la Tierra?

## 2. Regla de inclusion de pares (aplicada a la fuente, no a los datos)

Un par (region conocida, objetivo) entra SOLO si se cumplen las dos condiciones:

- **(A) Cuerpo explicito.** La fuente dice que la region es analogo de Marte o de la Luna.
- **(B) Sitio o tipo de terreno explicito del cuerpo.** La fuente nombra un sitio de Marte/Luna (de los de `data/derived/neighbors/targets.parquet`) o un tipo de terreno de ese cuerpo (cráter, campo volcanico, lava, paisaje eolico, llanura, etc.). Frases genericas ("analogo para Marte", "para exploracion planetaria", "entrenamiento lunar", "habitat de simulacion", "vida en el subsuelo") NO cuentan.

Objetivo del par:
- Si la fuente nombra un sitio que existe en `targets.parquet`: ese sitio (un solo objetivo).
- Si la fuente nombra un tipo de terreno de Marte pero no un sitio medido: TODAS las celdas de Marte (`mars_cells.parquet`, 1,838). Es la regla de "si la fuente no permite elegir, usa todos y toma la mejor D".
- Si la fuente nombra Marte y la Luna: la union de todas las celdas de Marte y los 10 objetivos lunares.
- Un region aporta como mucho un par (independencia de la prueba de rangos).

### Aplicacion a las 22 regiones de `config/known_analog_regions.json`

| Region | Frase de la fuente (analog_quote, resumida) | (A) | (B) | Resultado |
|---|---|---|---|---|
| holuhraun_iceland | "volcanic terrains in Elysium Planitia" | Marte | sitio Elysium Planitia + terreno volcanico | **ENTRA**: objetivo `insight_elysium` (sitio InSight en Elysium Planitia en targets) |
| pinacate_gran_desierto | "Lava Flows in the Pinacate Volcanic Field as Analogues for Mars" | Marte | lava / campo volcanico | **ENTRA**: todas las celdas de Marte |
| qaidam_basin | "similarity with Mars ... wind-formed landscape" | Marte | paisaje eolico | **ENTRA**: todas las celdas de Marte |
| meteor_crater | "study impact craters on Earth, the Moon, Mars" | Luna y Marte | crateres | **ENTRA**: union Marte + Luna |
| kilbourne_hole | "investigate volcanic areas on the Moon, Mars" | Luna y Marte | areas volcanicas | **ENTRA**: union Marte + Luna |
| mcmurdo_dry_valleys | "best known Earth analog to the Martian high-northern plains" | Marte | llanuras norte de Marte | **NO ENTRA por sensor**: lat -77.5, fuera de la banda de sensor de la medida (NASADEM 56 S-60 N; Copernicus 60-84 N). Decision de banda pendiente de Mario |
| haughton_crater | "Haughton Crater as an analog for Mars ... geology and glaciology" | Marte | NO: la fuente no nombra terreno ni sitio de Marte | NO ENTRA (la frase de la fuente no cumple B; es el caso mas cercano y se reporta) |
| desert_rats_flagstaff | "reviving Apollo-style lunar exploration training" | Luna | NO: entrenamiento, sin sitio ni terreno | NO ENTRA |
| sp_crater | "used the crater to train for moonwalking" | Luna | NO: entrenamiento | NO ENTRA |
| craters_of_the_moon | "research ... in preparation for future Mars missions" | Marte | NO: misiones, sin terreno | NO ENTRA |
| atacama_desert | "suitable analog for ancient Mars" | Marte | NO: "Marte antiguo" no es terreno | NO ENTRA |
| mojave_death_valley | "considered a Mars analog site" | Marte | NO: generico | NO ENTRA |
| lanzarote | "planetary analogue with terrain resembling Mars" | Marte | NO: "terreno parecido" sin tipo | NO ENTRA |
| svalbard | "geologic phenomena ... analogous to landforms on Mars" | Marte | NO: formas genericas | NO ENTRA |
| rio_tinto | "analog to searching for life ... deep beneath the subsurface of Mars" | Marte | NO: subsuelo, no superficie | NO ENTRA |
| ries_crater | "field analogs for planetary exploration" | no (sin Marte/Luna) | NO | NO ENTRA |
| sudbury_basin | "field analogs for planetary exploration" | no (sin Marte/Luna) | NO | NO ENTRA |
| wadi_rum | "colors and textures ... close match to those found on Mars" | Marte | NO: colores y texturas, sin tipo de terreno | NO ENTRA |
| henry_mountains_hanksville | "terrain near Hanksville looks almost Mars-like" | Marte | NO: "casi como Marte", sin tipo | NO ENTRA |
| mars_desert_research_station | "A Mars habitat simulation where scientists work" | Marte | NO: habitat | NO ENTRA |
| mauna_kea | "sites ... excellent analogs for areas on the Moon and/or Mars" | Luna y Marte | NO: "areas" sin tipo | NO ENTRA |
| pilbara | "where the oldest convincing evidence of life guides exploration" | Marte | NO: vida, no terreno | NO ENTRA |

Regiones fuera de la lista: "Black Point lava flow" (ejemplo de Mario) NO esta en `config/known_analog_regions.json` y no se anade en esta validacion. Haughton (ejemplo de Mario) NO entra por la regla B (ver tabla).

**Pares validos previstos: 5** (holuhraun_iceland, pinacate_gran_desierto, qaidam_basin, meteor_crater, kilbourne_hole).

## 3. Medida

- Ventana: disco de radio R = 4,000 m (8 km) en el centro de la region (`lat`, `lon` de `known_analog_regions.json`), malla L = 100 m, bilineal, AEQD. Igual que `pipelines/_common.py` `measure_raw` (STANDARDS seccion 3).
- Fuente de elevacion: NASADEM (Planetary Computer, `fetch.stac_clip`, mitad de ancho 5 km) para latitud <= 60 N; Copernicus GLO-30 del S3 publico (`pipelines/arctic_probe.py` `clip_cop`) para 60 a 84 N.
- Features: `slope_p95_deg`, `hi`, `hurst` (las tres de la distancia, `config/measure.json` v1.3). `coherence`, `ridge_pct`, `valley_pct` no entran en D.
- Distancia: D(a, b) = sqrt( sum_k ((a_k - b_k)/sigma_k)^2 / 3 ), con sigma de `config/measure.json` (congeladas; no se recalculan).
- Ventana invalida (cobertura < 0.9, o L < 2 x resolucion nativa): el par no entra y se reporta; no se parchea.

## 4. Estadistica

- **Pool:** `data/derived/neighbors/earth_windows.parquet`, 2,730 ventanas. Se usan las que tienen D calculable (6 con features nulas no tienen D; quedan 2,724). Las 2 ventanas marcadas `near_known_analog` se MANTIENEN (el pre-registro dice TODO el pool).
- **D del objetivo:** para un sitio, D(region, sitio). Para un conjunto (Marte o Marte+Luna), D = min sobre las celdas del conjunto (celdas con features nulas fuera). El pool se mide igual: para cada ventana del pool, D(ventana, conjunto) = min. Asi la distribucion nula y el dato son la misma funcion.
- **Percentil del par (mitad de rango):** pct = 100 x ( #{pool < D} + 0.5 x #{pool = D} ) / n. Bajo el azar la distribucion es uniforme, mediana 50. Menor = mas cerca del objetivo que un lugar cualquiera del pool.
- **Empate (tie):** umbral de `data/derived/neighbors/run.json` `thresholds` segun la clase de relieve del objetivo (rugged >= 3 deg de slope_p95: 0.41505; flat < 3 deg: 1.10172). Para un conjunto, la clase es la de la celda de mejor D. Empate = SI si D <= umbral (misma regla que `src/analog/core/neighbors.py` `ties`).

## 5. Criterio (fijo)

- **PASA** si (a) la mediana de los percentiles de los pares validos es <= 25 Y (b) la prueba de rangos con signo de Wilcoxon, unilateral (percentil < 50), da p < 0.05.
- **NO PASA** si hay >= 6 pares validos y no se cumple (a) o (b).
- **INSUFICIENTE** si hay menos de 6 pares validos. En ese caso no se declara PASA ni NO PASA; se reportan las cifras como descriptivas.
- Reportar tambien cuantos pares quedan dentro del umbral de empate de su objetivo.

## 6. Verificacion

- Dos pares se recalculan a mano con una forma distinta (lista en pure Python desde los valores persistidos de features, sin numpy ni los modulos del motor) y se comparan con el resultado de `validate_external.py`.
- Pruebas de `tests/test_validate_external.py`: oraculo de identidad (D = 0, percentil 0) y de distribucion conocida (percentil exacto).

## 7. Decisiones que quedan para Mario (no cambian este pre-registro)

1. Banda de sensor para latitudes < 60 S (McMurdo). Si Mario aprueba Copernicus para ese caso, se mide en una ejecucion aparte, documentada como extension.
2. Si Haughton debe entrar (la fuente no nombra terreno de Marte). Se mediria como extension, no como parte de este veredicto.
