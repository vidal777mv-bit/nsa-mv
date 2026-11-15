# Procedencia de datos (verificación)

Fuentes en `config/sources.json`: **44**. NASA: **37**; mixta (MOLA NASA + HRSC ESA): **1**; no NASA: **6**. Usadas por el análisis (`used`): **25**.

Columna *usado*: scripts de `pipelines/`, `src/`, `tools/` que leen la fuente (por id, nombre de archivo, o por `dem_source_id` de `sites.json`). *en sitio*: relieve/textura/texto/referencia que la muestra (`site/data/terrain/*/meta.json`, `site/data/targets.json`, `site/assets/globes/`, `site/references.html`).

## NASA

| id | cuerpo | misión / instrumento | usado | en sitio | URL (estado) |
|---|---|---|---|---|---|
| `nasadem` | earth | SRTM / ASTER GDEM (reprocesado) | si (10 archivos) | terreno x160, texto, ref | http_502 (502); ok |
| `modis_mod11a2_061` | earth | Terra / MODIS | no | texto, ref | http_502 (502); ok |
| `pgda_lola_product78_page` | moon | LRO / LOLA | si (manual) | texto, ref | ok |
| `lola_5m_site06_surf` | moon | LRO / LOLA | si (3 archivos) | relieve: 1 objetivo(s), terreno x1, ref | ok |
| `lola_5m_site06_toterr` | moon | LRO / LOLA | no | ref | ok |
| `lola_5m_site23_surf` | moon | LRO / LOLA | si (3 archivos) | relieve: 1 objetivo(s), terreno x1, ref | ok |
| `lola_5m_site23_toterr` | moon | LRO / LOLA | no | ref | ok |
| `lola_5m_site11_surf` | moon | LRO / LOLA | si (3 archivos) | relieve: 1 objetivo(s), terreno x1, ref | ok |
| `lola_5m_site11_toterr` | moon | LRO / LOLA | no | ref | ok |
| `lola_5m_dm2_surf` | moon | LRO / LOLA | si (3 archivos) | relieve: 1 objetivo(s), terreno x1, ref | ok |
| `lola_5m_dm2_toterr` | moon | LRO / LOLA | no | ref | ok |
| `lola_5m_haworth_surf` | moon | LRO / LOLA | si (3 archivos) | relieve: 1 objetivo(s), terreno x1, ref | ok |
| `lola_5m_haworth_toterr` | moon | LRO / LOLA | no | ref | ok |
| `lola_5m_site04_surf` | moon | LRO / LOLA | no | ref | ok |
| `lola_5m_sl2_surf` | moon | LRO / LOLA | no | ref | ok |
| `lola_5m_site06_rois` | moon | LRO / LOLA | no | ref | ok |
| `lola_5m_site23_rois` | moon | LRO / LOLA | no | ref | ok |
| `lola_5m_site11_rois` | moon | LRO / LOLA | si (1 archivos) | ref | ok |
| `lola_5m_dm2_rois` | moon | LRO / LOLA | no | ref | ok |
| `lola_5m_haworth_rois` | moon | LRO / LOLA | no | ref | ok |
| `lola_5m_sl2_rois` | moon | LRO / LOLA | no | ref | ok |
| `lola_80s_80mpp` | moon | LRO / LOLA | no | ref | ok |
| `diviner_prp_south` | moon | LRO / Diviner | no | texto, ref | ok |
| `diviner_prp_south_label` | moon | LRO / Diviner | no | no | ok |
| `diviner_pcp_directory` | moon | LRO / Diviner | no | ref | ok |
| `jezero_ctx_trn_dtm_20m` | mars | MRO / CTX + MGS / MOLA | si (2 archivos) | relieve: 1 objetivo(s), terreno x1, ref | ok |
| `gale_ctx_dtm_figshare` | mars | MRO / CTX | si (manual) | ref | ok |
| `gale_ctx_dtm_tile_3_3` | mars | MRO / CTX | si (2 archivos) | relieve: 1 objetivo(s), terreno x1, ref | ok |
| `usgs_ctx_dtm_insight_n15_068239` | mars | MRO / CTX | si (2 archivos) | relieve: 1 objetivo(s), terreno x1 | ok |
| `usgs_ctx_dtm_spirit_p22_009530` | mars | MRO / CTX | si (2 archivos) | relieve: 1 objetivo(s), terreno x1 | ok |
| `usgs_ctx_dtm_zhurong_n14_067844` | mars | MRO / CTX | si (2 archivos) | relieve: 1 objetivo(s), terreno x1 | ok |
| `usgs_ctx_dtm_oxia_n06_064538` | mars | MRO / CTX | si (2 archivos) | relieve: 1 objetivo(s), terreno x1 | ok |
| `lroc_nac_dtm_apollo17` | moon | LRO / LROC NAC | si (2 archivos) | relieve: 1 objetivo(s), terreno x1, texto, ref | ok |
| `lola_20m_polar_ldem` | moon | LRO / LOLA | si (3 archivos) | relieve: 4 objetivo(s), terreno x4, ref | ok |
| `nasa_svs_lroc_colour_moon` | moon | LRO / LROC (color) | textura | textura globo, texto, ref | ok |
| `commons_blue_marble_earth` | earth | Terra / MODIS (compuesto Blue Marble) | textura | textura globo, texto, ref | ok |
| `commons_viking_mdim21_mars` | mars | Viking Orbiter | textura | textura globo, texto, ref | ok |
| `hrsc_mola_blend_200m` | mars | MGS / MOLA + Mars Express / HRSC | no | ref | http_404 (404); ok |

## No NASA

| id | cuerpo | misión / instrumento | usado | en sitio | URL (estado) |
|---|---|---|---|---|---|
| `cop_dem_glo30` | earth | TanDEM-X (Copernicus DEM) | si (5 archivos) | texto, ref | http_502 (502); ok |
| `esa_worldcover` | earth | Sentinel-1/2 | si (3 archivos) | texto, ref | http_502 (502); ok |
| `copernicus_glo30_s3_example` | earth | TanDEM-X | no | ref | ok |
| `natural_earth_10m_admin_1` | earth | Vectores culturales | si (2 archivos) | texto, ref | ok |
| `koppen_geiger_1km_present` | earth | Clasificacion climatica | si (1 archivos) | texto, ref | ok |
| `natural_earth_10m_populated_places` | earth | Vectores culturales | si (2 archivos) | texto, ref | ok |

## Visible en el sitio sin entrada en `sources.json`

- http://www.w3.org/2000/svg (site/index.html, site/js/comparison-inspector.js)
- https://api.figshare.com/v2/articles/6584984 (site/references.html)
- https://astrogeology.usgs.gov/ (site/references.html)
- https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js (site/index.html, site/v2.html)
- https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/ (site/index.html, site/v2.html)
- https://creativecommons.org/licenses/by/4.0/ (site/references.html)
- https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf (site/references.html)
- https://en.wikipedia.org/wiki/ (site/references.html)
- https://esa-worldcover.org/en/data-access (site/references.html)
- https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ (site/references.html)
- https://fonts.googleapis.com (site/v2.html)
- https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..900&family=Newsreader:opsz,wght@6..72,400;6..72,500&display=swap (site/v2.html)
- https://fonts.gstatic.com (site/v2.html)
- https://lpdaac.usgs.gov/products/nasadem_hgtv001/ (site/references.html)
- https://lroc.im-ldi.com/about/terms (site/references.html)
- https://marsoweb.nas.nasa.gov/landingsites/mer2003/doc/original.html (site/data/cards/gale__gale__pool__pool_00001.json, site/data/cards/gale__gale__pool__pool_00103.json, site/dat)
- https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html (site/data/bodies.json, site/data/sample/bodies.json, site/js/config.js, site/references.html)
- https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html (site/data/bodies.json, site/data/rehearsal/gale__gale__pool__pool_00001.json, site/data/rehearsal/gale__gale__)
- https://nssdc.gsfc.nasa.gov/planetary/factsheet/moonfact.html (site/data/bodies.json, site/data/rehearsal/apollo17_taurus_littrow__apollo17_taurus_littrow__pool__pool_00004.)
- https://ntrs.nasa.gov/api/citations/19720018253/downloads/19720018253.pdf (site/data/missions.json, site/references.html)
- https://ntrs.nasa.gov/api/citations/19730008090/downloads/19730008090.pdf (site/data/missions.json, site/references.html)
- https://ntrs.nasa.gov/citations/19720018253 (site/data/cards/apollo17_taurus_littrow__apollo17_taurus_littrow__pool__pool_00004.json, site/data/cards/apoll)
- https://ntrs.nasa.gov/citations/19730008090 (site/data/cards/apollo17_taurus_littrow__apollo17_taurus_littrow__pool__pool_00004.json, site/data/cards/apoll)
- https://planetarycomputer.microsoft.com/api/stac/v1 (site/references.html)
- https://pubs.usgs.gov/publication/70025013 (site/data/missions.json, site/references.html)
- https://pubs.usgs.gov/publication/70047380 (site/data/missions.json, site/js/config.js, site/references.html)
- https://science.nasa.gov/mission/mars-2020-perseverance/rover-components/ (site/data/cards/gale__gale__pool__pool_00001.json, site/data/cards/gale__gale__pool__pool_00103.json, site/dat)
- https://stac.astrogeology.usgs.gov/api/collections/mro_ctx_controlled_usgs_dtms (site/references.html)
- https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance (site/references.html)
- https://www.nasa.gov/image-article/welcome-octavia-e-butler-landing/ (site/references.html)
- https://www.nasa.gov/news-release/nasa-provides-update-on-artemis-iii-moon-landing-regions/ (site/references.html)
- https://www.naturalearthdata.com/about/terms-of-use/ (site/references.html)
- https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits (site/references.html)
- https://www.wikidata.org/wiki/Q41308 (site/references.html)
- `site/data/sample/*`: datos sintéticos, no se ven con `DATA_BASE = data/`.
- `three.js` (CDN jsdelivr) y fuentes Google en `site/v2.html`: software o tipografía, no datos.

## Conflictos de licencia y avisos

- **nasadem**: CONFLICTO sin resolver. EOSDIS dice 'free and open'; Planetary Computer dice 'proprietary'.
- **nasa_svs_lroc_colour_moon** (textura de la Luna): guía de medios NASA, dar crédito; no es dominio público.
- **LOLA (PGDA), LROC, Diviner**: sin texto de licencia publicado; se trata como público con cita.
- **jezero_ctx_trn_dtm_20m**: la ficha del producto no se leyó.
- **Copernicus GLO-30 y MODIS** (Planetary Computer dice 'proprietary'): la licencia COP-DEM-GLO-30-F rige; MODIS sin usar.

## Comprobación de URLs (una sonda por URL, sin reintentos)

- STAC de Planetary Computer: la raíz responde, pero las colecciones `nasadem`, `cop-dem-glo-30`, `esa-worldcover`, `modis-11A2-061` dan **502**. Eso bloquea la descarga por STAC mientras siga así.
- `planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/` (página en sources.json): **404**. Sin usar.
- `esa-worldcover.s3.../v200/2021/map/` (en references.html): **404**; es un prefijo de carpeta, el dato se baja por STAC.
- `cdn.jsdelivr.net/.../examples/jsm/`: **404**; es carpeta, no archivo (imports de three.js).
