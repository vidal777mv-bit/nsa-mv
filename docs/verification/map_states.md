# Verificacion independiente: estados del mapa y cifras de portada

Semilla 20261114. Script: `docs/verification/scripts/verify_map_states.py`. Solo lectura de site/, config/, data/.

## A. Cifras de portada

| Cifra | Mostrado | Recontado | OK | Detalle |
|---|---|---|---|---|
| 16 sitios medidos | 16 | 16 | si | targets.json tiene 16 entradas |
| 2,000 lugares de la Tierra | 2000 | 2000 | si | filas data/derived/neighbors/earth_windows.parquet; indice pool index.json = 2000 |
| 1,838 celdas de Marte desbloqueadas | 1838 | 1838 | si | site/data/atlas/mars_cells.json = 1838; mars_cells.parquet = 1838. OJO: son ventanas; coverage/mars.json cuenta 1621 celdas de 1 grado en clase 2 (1844 centros medidos = 1838 + 6 objetivos de Marte, en 1621 celdas) |
| 1,276 gemelos nuevos | 1276 | 1276 | si | regla del archivo (clave = analog_id): 1347 ventanas (archivo 1347); mismatch de conjunto: False; mismatch de novedad: 0. Variante por ventana fisica del pool: 1301 unicas, nuevas=1244, conocidas=57; 39 entradas de objetivos con coordenada refinada distinta del pool |
| 71 conocidos | 71 | 71 | si | dentro de circulo de config/known_analog_regions.json (regla del archivo) |
| Tierra puede ensayar 88.5% de Marte medido (211/1838) | 88.5% / 11.5% (211/1838) | gap=211/1838 = 11.48%; ensaya=88.52%; gap parquet=211; gap export=211; con umbral run.json=211 | si |  |
| Luna: 3 de 7 sitios Artemis sin gemelo | 3 | 3 de 7 Artemis; 3 de 16 objetivos con gap | si |  |
| Tierra contorno 0.9% de la esfera | 0.9 | 0.86 | si | clase 1 = 413 celdas |
| Tierra sin tocar 96.0% | 96.0 | 96.04 | si | clase 0 = 62909 celdas; clase 2 share = 3.10% |

Cuotas de cobertura Marte (area por cos(lat)): desbloqueada 3.67%, por descubrir 15.27%, niebla 81.06%.

## B. Muestra por estratos (Wilson 95%)

| Estrato | n | aciertos | tasa | Wilson 95% |
|---|---|---|---|---|
| mars_cov_2_unlocked | 8 | 8 | 1.0 | [0.6756, 1.0] |
| mars_cov_1_to_discover | 8 | 8 | 1.0 | [0.6756, 1.0] |
| mars_cov_0_out_of_reach | 8 | 8 | 1.0 | [0.6756, 1.0] |
| earth_cov_2_unlocked | 8 | 8 | 1.0 | [0.6756, 1.0] |
| earth_cov_1_to_discover | 8 | 8 | 1.0 | [0.6756, 1.0] |
| earth_cov_0_out_of_reach | 8 | 8 | 1.0 | [0.6756, 1.0] |
| earth_gap_mars_gap1 | 8 | 8 | 1.0 | [0.6756, 1.0] |
| earth_gap_mars_gap0 | 8 | 8 | 1.0 | [0.6756, 1.0] |
| moon_artemis_census | 7 | 7 | 1.0 | [0.6457, 1.0] |

Total muestra (sin censo Luna): n=64, aciertos=64.

## C. Umbral Earth gap (dev NASADEM vs Copernicus)

- rugged: recomputado 0.4150468511, run.json 0.4150468511, diferencia 0.0, pares dev 13
- flat: recomputado 1.1017189574, run.json 1.1017189574, diferencia 0.0, pares dev 2

## D. Discrepancias de la muestra

Ninguna.

## E. Otros hallazgos

- Orientacion del cache WorldCover: {'n_pairs': 2000, 'corr_north_up': 0.4660605269529769, 'corr_south_up': 0.3234183651480914, 'chosen': 'N'}
- Conjuntos de clase 2 (cobertura) iguales a la grilla completa: {'mars': True, 'earth': True}
- Features atlas vs parquet, diferencia maxima: 0.0

