# Verificacion de los 16 sitios destino (2026-11-14)

Censo: config/sites.json = site/data/targets.json. Conteo real: 10 Luna y 6 Marte (el encargo decia 9 y 7).

Resultado: OK 7/16; DISCREPANCIA 1; NO CONFIRMADO 8.
OK con Wilson 95%: p=0.4375, intervalo [0.231, 0.668].

Criterio: aterrizajes <= 5 km; candidatas Artemis: punto dentro de la region o a <= 10 km del centro publicado. NASA no publica coordenadas de candidatas.

| id | cuerpo | veredicto | dist (km) |
|---|---|---|---|
| haworth | moon | NO CONFIRMADO | - |
| malapert_massif | moon | NO CONFIRMADO | - |
| nobile_rim_1 | moon | NO CONFIRMADO | - |
| nobile_rim_2 | moon | NO CONFIRMADO | - |
| de_gerlache_rim_2 | moon | NO CONFIRMADO | - |
| jezero | mars | NO CONFIRMADO | 0.282 |
| gale | mars | NO CONFIRMADO | 0.004 |
| insight_elysium | mars | OK | 0.003 |
| spirit_columbia | mars | OK | 0.000 |
| zhurong | mars | DISCREPANCIA | 28.314 |
| oxia_planum | mars | NO CONFIRMADO | 6.409 |
| apollo17_taurus_littrow | moon | OK | 0.000 |
| im1_odysseus | moon | OK | 0.000 |
| im2_athena | moon | OK | 0.369 |
| cabeus_b_peak | moon | OK | 0.000 |
| mons_mouton_plateau | moon | OK | 0.000 |

Detalle y fuentes por sitio en sites.json.
