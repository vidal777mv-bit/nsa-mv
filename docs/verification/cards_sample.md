# Verificacion independiente: muestra de fichas (cards)

Semilla 20261114. Fichas unicas en la muestra: 34 (Marte 10, Luna 24).

Estratos (poblacion de 160; n por estrato):
- novelty_new: 6 de 124
- novelty_known: 6 de 36
- landing_yes: 5 de 113
- landing_partial: 5 de 24
- landing_no: 5 de 23
- low_sun_no: 5 de 90
- low_sun_yes: 5 de 70

Tolerancias: mission_pct +-1.0 pts (terreno guardado a 30 m, reconstruido a 100 m); porcentajes de sol rasante +-0.05 pts (ruido de punto flotante en e = 0 exacto, 4 de 10368 muestras); latitudes y conteos exactos. Estado de ensayo: comparacion exacta. Intervalo: Wilson 95%.

BLOQUEADO: analog_place y nearest_town no se verifican. El .venv no tiene lector de shapefile (pyshp, fiona, pyogrio, osgeo). Shapely no lee .shp.

## Estrato: novelty_new (fichas: 6)

| campo | aciertos | tasa | Wilson 95% | bloqueado |
|---|---|---|---|---|
| novelty | 6/6 | 100.0% | 61.0–100.0 | 0 |
| known_region_id | 6/6 | 100.0% | 61.0–100.0 | 0 |
| koppen_class | 6/6 | 100.0% | 61.0–100.0 | 0 |
| rehearsal.landing | 6/6 | 100.0% | 61.0–100.0 | 0 |
| rehearsal.driving | 6/6 | 100.0% | 61.0–100.0 | 0 |
| rehearsal.low_sun | 6/6 | 100.0% | 61.0–100.0 | 0 |
| rehearsal.low_sun_lat | 4/4 | 100.0% | 51.0–100.0 | 0 |
| rehearsal.cold | 6/6 | 100.0% | 61.0–100.0 | 0 |
| limit_deg | 6/6 | 100.0% | 61.0–100.0 | 0 |
| mission_pct.landing | 2/2 | 100.0% | 34.2–100.0 | 0 |
| analog_place | — | — | — | 6 |
| nearest_town | — | — | — | 6 |

## Estrato: novelty_known (fichas: 6)

| campo | aciertos | tasa | Wilson 95% | bloqueado |
|---|---|---|---|---|
| novelty | 6/6 | 100.0% | 61.0–100.0 | 0 |
| known_region_id | 6/6 | 100.0% | 61.0–100.0 | 0 |
| koppen_class | 6/6 | 100.0% | 61.0–100.0 | 0 |
| rehearsal.landing | 6/6 | 100.0% | 61.0–100.0 | 0 |
| rehearsal.driving | 6/6 | 100.0% | 61.0–100.0 | 0 |
| rehearsal.low_sun | 6/6 | 100.0% | 61.0–100.0 | 0 |
| rehearsal.low_sun_lat | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.cold | 6/6 | 100.0% | 61.0–100.0 | 0 |
| limit_deg | 6/6 | 100.0% | 61.0–100.0 | 0 |
| mission_pct.landing | — | — | — | 0 |
| analog_place | — | — | — | 6 |
| nearest_town | — | — | — | 6 |

## Estrato: landing_yes (fichas: 5)

| campo | aciertos | tasa | Wilson 95% | bloqueado |
|---|---|---|---|---|
| novelty | 5/5 | 100.0% | 56.6–100.0 | 0 |
| known_region_id | 5/5 | 100.0% | 56.6–100.0 | 0 |
| koppen_class | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.landing | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.driving | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.low_sun | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.low_sun_lat | 2/2 | 100.0% | 34.2–100.0 | 0 |
| rehearsal.cold | 5/5 | 100.0% | 56.6–100.0 | 0 |
| limit_deg | 5/5 | 100.0% | 56.6–100.0 | 0 |
| mission_pct.landing | 1/1 | 100.0% | 20.7–100.0 | 0 |
| analog_place | — | — | — | 5 |
| nearest_town | — | — | — | 5 |

## Estrato: landing_partial (fichas: 5)

| campo | aciertos | tasa | Wilson 95% | bloqueado |
|---|---|---|---|---|
| novelty | 5/5 | 100.0% | 56.6–100.0 | 0 |
| known_region_id | 5/5 | 100.0% | 56.6–100.0 | 0 |
| koppen_class | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.landing | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.driving | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.low_sun | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.low_sun_lat | 4/4 | 100.0% | 51.0–100.0 | 0 |
| rehearsal.cold | 5/5 | 100.0% | 56.6–100.0 | 0 |
| limit_deg | 5/5 | 100.0% | 56.6–100.0 | 0 |
| mission_pct.landing | — | — | — | 0 |
| analog_place | — | — | — | 5 |
| nearest_town | — | — | — | 5 |

## Estrato: landing_no (fichas: 5)

| campo | aciertos | tasa | Wilson 95% | bloqueado |
|---|---|---|---|---|
| novelty | 5/5 | 100.0% | 56.6–100.0 | 0 |
| known_region_id | 5/5 | 100.0% | 56.6–100.0 | 0 |
| koppen_class | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.landing | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.driving | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.low_sun | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.low_sun_lat | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.cold | 5/5 | 100.0% | 56.6–100.0 | 0 |
| limit_deg | 5/5 | 100.0% | 56.6–100.0 | 0 |
| mission_pct.landing | 0/2 | 0.0% | 0.0–65.8 | 0 |
| analog_place | — | — | — | 5 |
| nearest_town | — | — | — | 5 |

## Estrato: low_sun_no (fichas: 5)

| campo | aciertos | tasa | Wilson 95% | bloqueado |
|---|---|---|---|---|
| novelty | 5/5 | 100.0% | 56.6–100.0 | 0 |
| known_region_id | 5/5 | 100.0% | 56.6–100.0 | 0 |
| koppen_class | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.landing | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.driving | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.low_sun | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.low_sun_lat | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.cold | 5/5 | 100.0% | 56.6–100.0 | 0 |
| limit_deg | 5/5 | 100.0% | 56.6–100.0 | 0 |
| mission_pct.landing | — | — | — | 0 |
| analog_place | — | — | — | 5 |
| nearest_town | — | — | — | 5 |

## Estrato: low_sun_yes (fichas: 5)

| campo | aciertos | tasa | Wilson 95% | bloqueado |
|---|---|---|---|---|
| novelty | 5/5 | 100.0% | 56.6–100.0 | 0 |
| known_region_id | 5/5 | 100.0% | 56.6–100.0 | 0 |
| koppen_class | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.landing | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.driving | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.low_sun | 5/5 | 100.0% | 56.6–100.0 | 0 |
| rehearsal.low_sun_lat | — | — | — | 0 |
| rehearsal.cold | 5/5 | 100.0% | 56.6–100.0 | 0 |
| limit_deg | 5/5 | 100.0% | 56.6–100.0 | 0 |
| mission_pct.landing | — | — | — | 0 |
| analog_place | — | — | — | 5 |
| nearest_town | — | — | — | 5 |

## Estrato: TOTAL (fichas: 34)

| campo | aciertos | tasa | Wilson 95% | bloqueado |
|---|---|---|---|---|
| novelty | 34/34 | 100.0% | 89.8–100.0 | 0 |
| known_region_id | 34/34 | 100.0% | 89.8–100.0 | 0 |
| koppen_class | 34/34 | 100.0% | 89.8–100.0 | 0 |
| rehearsal.landing | 34/34 | 100.0% | 89.8–100.0 | 0 |
| rehearsal.driving | 34/34 | 100.0% | 89.8–100.0 | 0 |
| rehearsal.low_sun | 34/34 | 100.0% | 89.8–100.0 | 0 |
| rehearsal.low_sun_lat | 22/22 | 100.0% | 85.1–100.0 | 0 |
| rehearsal.cold | 34/34 | 100.0% | 89.8–100.0 | 0 |
| limit_deg | 34/34 | 100.0% | 89.8–100.0 | 0 |
| mission_pct.landing | 3/5 | 60.0% | 23.1–88.2 | 0 |
| analog_place | — | — | — | 34 |
| nearest_town | — | — | — | 34 |

## Discrepancias

- de_gerlache_rim_2__de_gerlache_rim_2__pool__pool_00091.json | mission_pct.landing | ficha: 62.382836908977296 | recomputado: 60.050622 | denominador = pixeles con pendiente definida (4741); alternativa denominador = todo el disco (4965): 57.3414; grilla 81 px a 100 m; tolerancia 1.0 pts
- malapert_massif__malapert_massif__pool__pool_00024.json | mission_pct.landing | ficha: 67.79837533847115 | recomputado: 63.741827 | denominador = pixeles con pendiente definida (4741); alternativa denominador = todo el disco (4965): 60.8661; grilla 81 px a 100 m; tolerancia 1.0 pts

Causa no resuelta (mission_pct): la reconstruccion desde height.bin (30 m, remuestreada a 100 m) da 59.5-60.1 y 63.1-63.8 con cualquier ancla de rejilla o metodo de remuestreo; los valores de la ficha quedan fuera de ese rango. Hipotesis: la pipeline calculo la rejilla de 100 m directo desde el DEM nativo (la ficha lista ese clip en provenance). No verificable sin ese clip.

## Fichas de la muestra

- apollo17_taurus_littrow__apollo17_taurus_littrow__pool__pool_00078.json (moon) estratos: novelty_known
- apollo17_taurus_littrow__apollo17_taurus_littrow__pool__pool_01514.json (moon) estratos: landing_partial
- cabeus_b_peak__cabeus_b_peak__pool__pool_00138.json (moon) estratos: novelty_new
- de_gerlache_rim_2__de_gerlache_rim_2__pool__pool_00055.json (moon) estratos: novelty_known
- de_gerlache_rim_2__de_gerlache_rim_2__pool__pool_00091.json (moon) estratos: landing_no [mission_pct]
- de_gerlache_rim_2__de_gerlache_rim_2__pool__pool_00097.json (moon) estratos: landing_no
- de_gerlache_rim_2__de_gerlache_rim_2__pool__pool_01835.json (moon) estratos: low_sun_no
- haworth__haworth__pool__pool_00063.json (moon) estratos: landing_yes
- haworth__haworth__pool__pool_00603.json (moon) estratos: novelty_new [mission_pct]
- haworth__haworth__pool__pool_01222.json (moon) estratos: low_sun_no
- im1_odysseus__im1_odysseus__pool__pool_00072.json (moon) estratos: landing_yes
- insight_elysium__insight_elysium__pool__pool_00524.json (mars) estratos: low_sun_yes
- insight_elysium__insight_elysium__pool__pool_01650.json (mars) estratos: landing_yes
- jezero__jezero__pool__pool_01135.json (mars) estratos: novelty_new
- jezero__jezero__pool__pool_01676.json (mars) estratos: low_sun_yes
- malapert_massif__malapert_massif__pool__pool_00024.json (moon) estratos: landing_no [mission_pct]
- malapert_massif__malapert_massif__pool__pool_00097.json (moon) estratos: novelty_known
- malapert_massif__malapert_massif__pool__pool_01247.json (moon) estratos: novelty_new, landing_no
- mons_mouton_plateau__mons_mouton_plateau__pool__pool_00117.json (moon) estratos: landing_partial
- mons_mouton_plateau__mons_mouton_plateau__pool__pool_00370.json (moon) estratos: novelty_new
- mons_mouton_plateau__mons_mouton_plateau__pool__pool_01222.json (moon) estratos: low_sun_no
- nobile_rim_1__nobile_rim_1__pool__pool_00045.json (moon) estratos: novelty_known
- nobile_rim_1__nobile_rim_1__pool__pool_00091.json (moon) estratos: low_sun_no
- nobile_rim_1__nobile_rim_1__pool__pool_01675.json (moon) estratos: novelty_known
- nobile_rim_1__nobile_rim_1__pool__pool_01835.json (moon) estratos: landing_no
- nobile_rim_2__nobile_rim_2__pool__pool_00040.json (moon) estratos: novelty_known, landing_partial
- nobile_rim_2__nobile_rim_2__pool__pool_00069.json (moon) estratos: landing_partial, low_sun_no
- nobile_rim_2__nobile_rim_2__pool__pool_00078.json (moon) estratos: landing_partial
- oxia_planum__oxia_planum__pool__pool_01843.json (mars) estratos: low_sun_yes
- spirit_columbia__spirit_columbia__pool__pool_00249.json (mars) estratos: low_sun_yes
- spirit_columbia__spirit_columbia__pool__pool_00336.json (mars) estratos: landing_yes [mission_pct]
- zhurong__zhurong__pool__pool_00435.json (mars) estratos: low_sun_yes
- zhurong__zhurong__pool__pool_00748.json (mars) estratos: novelty_new [mission_pct]
- zhurong__zhurong__pool__pool_00955.json (mars) estratos: landing_yes
