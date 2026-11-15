# Verificacion independiente: punto de aterrizaje de Zhurong

## Valor del sitio
- `site/data/targets.json` (id `zhurong`): lat 25.066 N, lon 109.925 E.

## Fuente primaria (revisada por pares)
- Wu, B., Dong, J., Wang, Y., et al. (2022). "Landing Site Selection and Characterization of Tianwen-1 (Zhurong Rover) on Mars". *Journal of Geophysical Research: Planets*, 127, e2021JE007137. DOI 10.1029/2021JE007137. Acceso abierto (Wiley), leido en PDF.
  - Seccion 1 (p. 2): region principal de aterrizaje "approximately 180 × 70 km in size centered at 110.318°E, 24.748°N" (poligono rojo, Figura 1). Region de respaldo centrada en 131.626°E, 26.467°N. Las elipses de aterrizaje (56 × 22 km) se dibujaron dentro de la region principal.
  - Seccion 3.1 (p. 9): "On 15 May 2021, the Tianwen-1 lander carrying the Zhurong rover successfully landed near the center of ellipse No. 16 in the main landing region." "The actual location of the lander was 109.925°E, 25.066°N at an elevation of −4,099.4 m in the MOLA DEM, approximately 3.1 km south of the center of ellipse No. 16."
  - Pie de figura 6 (p. 10): posicion del aterrizador (109.925°E, 25.066°N) sobre imagen HiRIC HX1-Or_GRAS_HiRIC-CCD1-F_SCI_N_20210602133202; paracaidas y tapa trasera 109.923°E, 25.060°N; escudo termico 109.901°E, 25.050°N.

## Resultado
- **Coordenada oficial del aterrizador: 25.066 N, 109.925 E** (Wu et al. 2022, sec. 3.1 y Fig. 6). Coincide exactamente con `targets.json`. Distancia: 0 km.
- **24.748 N, 110.318 E NO es el punto de aterrizaje ni el centro de la elipse de aterrizaje.** Es el centro de la region principal de aterrizaje preseleccionada (~180 × 70 km), que es mayor que la elipse. La elipse usada fue la No. 16 (56 × 22 km), cuyo centro no aparece con coordenadas en el texto; el aterrizador quedo a 3.1 km al sur de ese centro.
- **Hipotesis de la verificacion anterior: parcialmente correcta.** Es un punto previo al aterrizaje (centro de la zona de seleccion), no el punto de aterrizaje. Pero no es "la elipse previa": es el centro de la region mayor dentro de la cual se eligieron las elipses.
- **Distancia entre 24.748/110.318 y 25.066/109.925:**
  - Con radio terrestre (6371.0088 km, haversine usado en el proyecto): **53.12 km**.
  - Con radio de Marte (3389.5 km): **28.26 km**. Este es el valor de "28 km" de la verificacion anterior.
  - Conclusion: el "28 km" correspondia al radio de Marte; el calculo con radio terrestre da 53 km. Cualquier distancia en Marte o Luna que use 6371.0088 km esta mal escalada (factor ~1.88).

## Otras fuentes consultadas (no primarias o con discrepancia)
- Wikipedia (Zhurong rover), infobox: 25.102 N, 109.914 E, citando HiRISE ESP_069665_2055. Ese es el **centro de la imagen HiRISE** de 6 jun 2021 (confirmado en la pagina HiRISE: "Latitude (centered) 25.102, Longitude (East) 109.914"), no el aterrizador. Distancia al punto oficial: 4.15 km (radio terrestre) / 2.21 km (radio de Marte).
- Wikipedia (Tianwen-1): 25°03′58″N 109°55′30″E = 25.066 N, 109.925 E (concuerda).
- SpaceNews: menciona 110.318 E, 24.748 N como centro del area objetivo previa a la llegada.
- Nature Astronomy 2021 (s41550-021-01519-5, "Geomorphic contexts and science focus of the Zhurong landing site"): el sitio respondio con redireccion a login (403 / idp.nature.com). No verificado en texto completo.
- Liu et al.: no se encontro en las busquedas un articulo de Liu et al. con esa localizacion. No verificado.
- Limitacion: la pagina HiRISE ESP_069665_2055 se leyo y dio solo el centro de imagen, sin coordenada del aterrizador. La version HTML de Wiley (agupubs) dio 403; el texto de Wu et al. se leyo del PDF descargado por el enlace del repositorio PolyU.

## Conclusion para el proyecto
- `targets.json` (25.066 N, 109.925 E) es correcto y respaldado por fuente primaria revisada por pares.
- No hay que cambiar el sitio. Lo que sí conviene revisar: (a) el calculo de distancias para Marte en el proyecto usa radio terrestre; (b) si en algun texto se cita 24.748/110.318 como "aterrizaje", corregir a "centro de la region principal de aterrizaje previo".
