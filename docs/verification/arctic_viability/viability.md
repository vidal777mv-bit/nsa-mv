# Viabilidad fisica en gemelos articos: hechos vs contraste

Solo hechos con fuente (ver viability.json, campo `fuentes`). Sin indices ni puntajes. Muestra: 79 gemelos articos (censo arctic_top10) y 67 contrastes no articos (todos los candidatos top 10 con pool_NNNNN <= 2000; menos de 79, asi que no hubo muestreo).

## Tabla resumen

| Hecho | ARTICO | CONTRASTE |
|---|---|---|
| Km al pueblo mas cercano, mediana (rango) | 156.6 (32.2-425.4) | 101.2 (20.0-516.3) |
| Km al aeropuerto mas cercano, mediana (rango) | 816.4 (31.0-2464.4) | 363.1 (29.3-926.2) |
| ice_share >= 0.1 | 10.1% (8/79; IC95 5.2-18.7%) | 0.0% (0/67; IC95 0.0-5.4%) |
| Koppen BSk | 0 | 10.4% (7/67; IC95 5.2-20.0%) |
| Koppen BWh | 0 | 52.2% (35/67; IC95 40.5-63.7%) |
| Koppen BWk | 0 | 37.3% (25/67; IC95 26.7-49.3%) |
| Koppen Dfc | 7.6% (6/79; IC95 3.5-15.6%) | 0 |
| Koppen EF | 8.9% (7/79; IC95 4.4-17.2%) | 0 |
| Koppen ET | 83.5% (66/79; IC95 73.9-90.1%) | 0 |
| En area protegida (admin-1) | 11.4% (9/79; IC95 6.1-20.3%) | 0.0% (0/67; IC95 0.0-5.4%) |
| A menos de 100 km del centro de una region analoga conocida | 0.0% (0/79; IC95 0.0-4.6%) | 4.5% (3/67; IC95 1.5-12.4%) |
| A menos de 100 km de un aeropuerto | 3.8% (3/79; IC95 1.3-10.6%) | 9.0% (6/67; IC95 4.2-18.2%) |

Koppen ET = Polar, tundra; EF = Polar, frost (leyenda Beck et al. 2018). Es clasificacion climatica, no meses.

## Top 1 arcticos (con todos sus hechos)

| Sitio(s) | Gemelo | Lugar admin-1 | Protegida | Aeropuerto km | Pueblo km | ice_share | Koppen | HMP km | Region conocida km |
|---|---|---|---|---|---|---|---|---|---|
| malapert_massif | pool_02378 | Krasnoyarsk | no | 1258.9 (Surgut) | 236.9 (Norilsk) | 0.000 | ET | 3978.2 | 2441.4 (Svalbard (Norway)) |
| gale | pool_02402 | Nationalparken | si | 816.4 (Svalbard Longyear) | 225.2 (Nord) | 0.000 | EF | 1560.1 | 821.0 (Svalbard (Norway)) |
| nobile_rim_1 | pool_02972 | Nationalparken | si | 1082.9 (Reykjavik Air Terminal) | 376.6 (Ittoqqortoormiit) | 0.101 | ET | 1892.0 | 1023.3 (Holuhraun lava flow field (Iceland)) |
| mons_mouton_plateau | pool_03196 | Nunavut | no | 1036.5 (Resolute Bay) | 63.7 (Alert) | 0.199 | ET | 901.1 | 897.8 (Devon Island (Nunavut, Canada)) |
| nobile_rim_2 | pool_03351 | Krasnoyarsk | no | 1337.9 (Surgut) | 199.9 (Boyarka) | 0.000 | ET | 3942.3 | 2451.8 (Svalbard (Norway)) |
| haworth | pool_04055 | Krasnoyarsk | no | 1066.4 (Surgut) | 64.2 (Norilsk) | 0.000 | Dfc | 3979.7 | 2310.6 (Svalbard (Norway)) |

Trabas: si `Protegida` es si, aplica el permiso de la fuente de Groenlandia (estado no verificado, ver abajo). Hielo: ice_share < 0.2 en todos (regla de shares.json).

## Arcticos a menos de 100 km de un aeropuerto y fuera de area protegida

Total: 3 de 79.

| Gemelo | Aeropuerto km | Aeropuerto | Pueblo km | ice_share | Lugar admin-1 | Koppen |
|---|---|---|---|---|---|---|
| pool_03022 | 31.0 | Iqaluit | 32.24 | 0.0 | Nunavut | ET |
| pool_02415 | 78.2 | Iqaluit | 54.04 | 0.0 | Nunavut | ET |
| pool_03634 | 83.2 | Iqaluit | 41.1 | 0.0 | Nunavut | ET |

## Fuentes y limites

- ice_share, bare_share_full: data/derived/pool_rules/shares.json (ESA WorldCover 2021 v200, provenance.inputs)
- koppen: site/data/cards/*.json context.koppen_class; leyenda data/raw/reference/koppen/legend.txt (Beck et al. 2018, Sci Data)
- pueblo: site/data/cards/*.json context.nearest_town (Natural Earth 10m populated places, v5.1.2)
- aeropuerto: docs/verification/arctic_viability/cache/ne_airports/ne_10m_airports.zip (Natural Earth 10m, dominio publico) https://naciscdn.org/naturalearth/10m/cultural/ne_10m_airports.zip
- puerto: docs/verification/arctic_viability/cache/ne_ports/ne_10m_ports.zip https://naciscdn.org/naturalearth/10m/cultural/ne_10m_ports.zip
- area_protegida: data/raw/reference/ne_10m_admin_1 v5.1.1 (Natural Earth, dominio publico)
- region_analoga: config/known_analog_regions.json + config/regions.json role=known_analog
- HMP: https://www.marsinstitute.no/hmp : 'located at 75o 26' N, 89o 52' W, in the northwestern rim area of Haughton Crater'; establecida 2000 (texto verificado)
- Area protegida: las marcas salen SOLO del nombre 'Nationalparken' (poligono Natural Earth con type='Lansdele' y type_en vacio; ningun poligono dice 'National Park' en type/type_en).
- Permiso parque NE Groenlandia: **NO VERIFICADO TEXTUALMENTE**. Los PDF de naalakkersuisut.gl y zackenberg.dk devolvieron binario ilegible en 2 intentos (WebFetch). Solo hay URLs halladas por busqueda.
  - https://eastgreenland.com/rules-regulations/
  - https://zackenberg.dk/fileadmin/g-e-m/Zackenberg/KNNO_Expedition_Permit_No._D-26-03_with_National_Park_access_web.pdf
  - https://naalakkersuisut.gl/-/media/nyheder/2025/09/advisory-against-travel-in-dickson-fjord-west-of-ella-island-and-the-consideration-of-the-national-p.pdf
  - Afirmacion hallada en busqueda, sin verificar en texto: Permiso del Gobierno de Groenlandia requerido para entrar al parque (Executive Order No. 7, 17-jun-1992).

