# Verificacion: capa Permanent base (Luna), `pipelines/moon_base.py`

Fecha: 2026-11-15. Alcance: 10 sitios lunares de `site/data/targets.json`; iluminacion, PSR y visibilidad de la Tierra.

## Productos oficiales usados

Todos vienen de la pagina PGDA "Lunar Polar Illumination" (https://pgda.gsfc.nasa.gov/products/69), basados en LOLA y en Mazarico et al. (2011).

| Producto | Archivo (descargado en `data/raw/moon/base/`) | Resolucion | Periodo |
| --- | --- | --- | --- |
| Iluminacion promedio (AVGVISIB) | `AVGVISIB_75S_120M_201608.TIF` (83 MB), https://pgda.gsfc.nasa.gov/data/MoonIllumination/AVGVISIB_75S_120M_201608.TIF | 120 m, 75S-90S | Promedio sobre un ciclo de nutacion de 18.6 anos (pasos de 1 h); datos LOLA 2009-07-13 a 2013-07-18 (tags GeoTIFF) |
| PSR (LPSR) | `LPSR_75S_120M_201608.TIF` (1 MB), https://pgda.gsfc.nasa.gov/data/MoonIllumination/LPSR_75S_120M_201608.TIF | 120 m | Igual |
| Visibilidad de la Tierra (AVGVISIB_EARTH) | `AVGVISIB_75S_120M_201608_EARTH.TIF` (43 MB), https://pgda.gsfc.nasa.gov/data/MoonIllumination/AVGVISIB_75S_120M_201608_EARTH.TIF | 120 m | Igual |

Cita (la pide PGDA; la pagina no declara licencia): Mazarico, E., et al. (2011), "Illumination conditions of the lunar polar regions using LOLA topography", Icarus 211, 1066-1081, doi:10.1016/j.icarus.2010.10.030.

Decisiones de lectura:
- Las versiones COG (`*_COG.TIF`) de la pagina devuelven HTTP 200 con una pagina de error de 3.8 KB; no se usaron. Se bajaron los TIF normales.
- Escalas (GDAL): iluminacion y Tierra `raw x 4e-5` = fraccion (25000 = 100%); PSR `raw x 2.5e-5 + 0.5`, valores 0 y 1. PGDA indica que las escalas se aplican automaticamente en los GeoTIFF; rasterio no las aplica solo, asi que el pipeline las aplica.
- Etiquetas PDS: `pds-geosciences.wustl.edu` responde con "THIS SITE CURRENTLY UNAVAILABLE"; no se pudo leer el label. El significado de LPSR (1 = PSR) queda como inferencia de los factores de escala, y se comprobo asi: todos los pixeles marcados como PSR tienen iluminacion exactamente 0% (ver abajo).

## Chequeos internos (sin modelo propio)

- PSR coherente con iluminacion: en los 1 822 329 pixeles PSR dentro del circulo 75S-90S, la iluminacion es 0.0% (media y maximo). Fuera de PSR la media es 33.4%.
- Area PSR en el circulo 75S-90S: 26 242 km2 (3.99% del circulo). No comparado con cifra publicada.
- Escala: iluminacion maxima del producto 89.58%; Tierra maxima 100%.
- Pruebas sinteticas (`tests/test_moon_base.py`, 6 pasan): escala y nodata; media y maximo del disco contra fuerza bruta; media constante exacta; distancia PSR exacta (6000 m para un desplazamiento 3600 E / 4800 S); area PSR en el disco; sitio fuera de producto.

## Verificacion contra cifras publicadas

Resultado: NO se logro una verificacion numerica por sitio. Lo que se intento:

1. Barker, M.K., et al. (2020), "Improved LOLA elevation maps for south pole landing sites", Planetary and Space Science, doi:10.1016/j.pss.2020.105119. Es el mejor candidato porque su Site 11 (rim de de Gerlache) es el mismo ROI PGDA Site11 de nuestro `de_gerlache_rim_2`. Pero sus cifras son distintas en metodo: iluminacion a 1 m de altura, ventana 2024-2026, LDEM de 5 m, y los resultados por RoI estan en la tabla 2, que no sale en el texto del PDF. En el texto solo hay rangos de percentiles por RoI (por ejemplo, "1st percentile of average illumination ranges from 67% (RoI 7) to 71% (RoI 6)") y que el Site 1 tiene "the most area with average illumination >70%". No hay un promedio por sitio que comparar con `de_gerlache_rim_2` (38.0% medio, 79.7% maximo en el disco). Diferencia: no calculable.
2. Mazarico et al. (2011), tabla 3 (ranking de sitios por iluminacion promedio). El articulo en Icarus no se pudo abrir (el DOI redirige a una pagina de Elsevier sin contenido). Sin tabla no hay cifra para Site 11 ni Site 23.
3. Resumen AGU 2010 del equipo Kaguya (citado en busqueda): "86% for the Kaguya low-resolution and 90% for the LOLA" para el polo sur. Comparacion debil: es una cifra de polo, de un resumen (no el articulo), y probablemente sobre un periodo y una altura distintos. Nuestro maximo de iluminacion en todo el circulo polar es 89.58% (dato del producto), contra 90% LOLA: diferencia -0.4 puntos. Promedio en el disco de 4 km sobre el polo: 21.5% (la media del polo no es comparable con el maximo publicado).
4. Bussey et al. (2010), Icarus 208, 558-564, doi:10.1016/j.icarus.2010.03.028: se encontro una cita de "86% de iluminacion del ano en 88.74S 124.5E" en una busqueda previa, pero el resumen en ADS no se pudo abrir (HTTP 405) y no hay fuente que confirme esas coordenadas ni el 86% en ese punto. NO se usa como verificacion. Solo como nota: el producto LOLA en ese punto da 60.1% (pixel) y 78.0% de maximo en 4 km; la diferencia no se puede interpretar sin confirmar la cifra.

Conclusion: la verificacion por sitio queda bloqueada por falta de acceso al texto completo de Mazarico 2011 (tabla 3) y por la tabla 2 de Barker 2020 fuera del texto extraido. Para cerrarla hace falta el PDF de Mazarico 2011 o la tabla 2 de Barker 2020 en formato legible.

## Diferencias de metodo que conviene recordar

- El producto promedia 18.6 anos; las cifras de Barker son de 2 anos a 1 m de altura. Comparar cifras de sitio exige alinear periodo y altura.
- PSR: la distancia al pixel PSR mas cercano tiene una precision de +/-85 m (el pixel de 120 m).
- Visibilidad de la Tierra: PGDA define "visible si cualquier parte del disco no esta obstruida" y advierte que puede ser ligeramente optimista para enlaces DSN.
- Los centros de algunos sitios son proxies (ver `center_note` en `targets.json`); cada nota de sitio lo repite.
- IM-1 (80.13 S) cae dentro de la cobertura 75S-90S y se calculo como polar. Apollo 17 (20.2 N) no esta en el producto y queda como "not polar, constant day/night cycle".
