# NASA Space Apps Challenge 2026: textos para el formulario de entrega

Proyecto: Common Ground (equipo marsvia, San Salvador, El Salvador)
Reto: Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars
Preparado: 2026-11-15, a partir de docs/project_page.md, HOW_IT_WORKS.md, validation/external/RESULTS.md, verification/moon_base.md y README.md.

## Campos oficiales y fuente

Fuente de los campos: "Project Page Form Field Instructions", dentro de la Project Submission Guide
https://www.spaceappschallenge.org/resources/project-submission-guide/ (publicada el 13-nov-2026).

| # | Campo oficial (texto del formulario) | Bloque en este archivo |
|---|---|---|
| 1 | Project Name | 1 |
| 2 | High-Level Project Summary | 2 |
| 3 | Link to Project Demo | 3 |
| 4 | Link to Final Project | 4 |
| 5 | Detailed Project Description | 5 |
| 6 | Use of Super Intelligence (SI) | 6 |
| 7 | NASA Data | 7 |
| 8 | Space Agency Partner Data and Other References | 8 |

Notas sobre los nombres:
- La guía dice "Super Intelligence (SI)", no "Artificial Intelligence". El término oficial es el que aparece en el formulario.
- No hay campo aparte de "References". Las referencias van dentro del campo 8.
- No hay campo "Project details" separado. Lo que pide ese nombre es el campo 5.

Límites de caracteres: no encontré límite en ningún campo. Ni la Project Submission Guide ni la Judging & Awards Guide (https://www.spaceappschallenge.org/resources/judging-awards-guide/) lo indican. El formulario pide login y no lo pude ver. Antes de pegar, comprobar en el formulario si marca un límite. Los conteos de abajo son de referencia.

Requisitos del formulario que la guía sí fija: demo de 30 s o menos, o de 7 diapositivas o menos; todo en inglés; enlaces públicos sin login; campos obligatorios completos.

---

## 1. Project Name

Fuente: "What is the name of your project?"

```text
Common Ground: measured Earth analogs for Mars and Moon sites
```

Conteo: 61 caracteres.

---

## 2. High-Level Project Summary

Fuente: "Provide a high-level summary of your project. What did you develop? How does it address the challenge? Why is it important?"

```text
Common Ground answers one question for mission planners: where on Earth can a crew rehearse for this exact place on Mars or the Moon? We measured 16 landing sites and 1,838 places on Mars with NASA elevation models, and searched 2,730 bare-ground places on Earth, Arctic included, with the same three terrain measures and an exact nearest-neighbour search. Result: Earth can rehearse 95.4% of measured Mars; the other 4.6% has no Earth twin, and that is where robots go first. On the Moon, Earth has ground like 9 of 10 sites, and for the Artemis III regions we add a permanent-base layer from NASA LOLA (sunlight, Earth in view, distance to permanent shadow). Of the 1,786 Earth places that are a twin of some site or Mars place, 1,736 lie outside well-known analog regions. Every number comes from a facts ledger, and validation is reported as it came out: the pre-registered tests narrowly failed (AUC 0.695 vs 0.70) and an external check was insufficient (5 of 6 required pairs). The signal is real but modest: it measures operability, not geological origin.
```

Conteo: 1062 caracteres.

---

## 3. Link to Project Demo

Fuente: "Provide a short demonstration ... either a 7-slide presentation or a 30-second or less video ... publicly accessible link, no password, permission or registration."

```text
YouTube link: to be added by Mario
```

Conteo: 34 caracteres.

Pendiente de Mario: subir el video (30 s o menos, público, sin login) y pegar aquí el enlace. Si el video no está en inglés, debe llevar subtítulos en inglés.

---

## 4. Link to Final Project

Fuente: "Share a publicly accessible link to your final project ... no password, permission or registration."

```text
https://vidal777mv-bit.github.io/nsa-mv/
```

Conteo: 40 caracteres.

---

## 5. Detailed Project Description

Fuente: "Provide additional details about your project. What exactly does it do? How does it work? What benefits does it have? What do you hope to achieve? What tools, coding languages, hardware, or software did you use to develop your project?"

```text
Team: marsvia (NASA Space Apps Challenge 2026, local event San Salvador, El Salvador)
Repository (code, data and documentation): https://github.com/vidal777mv-bit/nsa-mv

WHAT IT DOES
Common Ground is a Mars-first atlas. Pick a site on Mars or the Moon, see what the mission needs (land, drive, live), and find the place on Earth whose terrain measures closest to it, with what a team can rehearse there, what it cannot, and where Earth has no match.

The atlas has 16 sites: 6 on Mars (Jezero, Gale, InSight, Spirit, Zhurong, Oxia Planum) and 10 on the Moon (Apollo 17, IM-1, IM-2 and 7 Artemis III candidate regions). The Mars globe is a game-like map with three states: unlocked (measured), to discover (an elevation model exists, not yet measured) and out of reach (no usable elevation model). On a one-degree Mars grid, 1,621 cells are unlocked and 6,988 are to discover.

HOW IT WORKS
1. Mission limits. Landing and driving slope limits come from NASA documents, listed with their sources: Mars 15 degrees for landing (MER requirement) and 30 degrees for driving (Perseverance tilt limit); Moon 12 degrees (Apollo Lunar Module) and 25 degrees (Lunar Roving Vehicle). None of these sources states a baseline length.

2. Measured terrain. Every window is an 8 km disk on a 100 m grid, computed the same way on Mars, the Moon and Earth. Three features enter the distance: the 95th percentile of slope, the hypsometric integral (bowl or plateau) and the Hurst exponent (how bumpiness grows with distance, 100 to 800 m). Three more are shown but not scored (grain direction, ridges, hollows). The share of each disk within the mission slope limit is a reference comparison, not a probability of success. Examples: Jezero 99.5% and Gale 100.0% within the landing limit, both at a 100 m baseline.

3. Earth twin. The distance between two windows is the root-mean-square difference of the three scored features, each divided by a robust spread (1.4826 times the median absolute deviation) computed over the Earth pool of 2,730 bare-ground windows. An exact k-d tree search finds the nearest neighbours; it was tested against brute force on a seeded sample of queries and matched. Twins closer than the measured sensor noise are shown as statistically tied (threshold 0.42 for rugged terrain). Example: the closest twin of Jezero is a window in Tagant, Mauritania (D = 0.057; slope p95 6.8 degrees at Jezero and 6.6 degrees at the twin).

4. Rehearsal dossier. For each pair, the dossier lists what the Earth site can rehearse (landing and driving terrain, cold, low sun) and what it cannot. Earth cannot reproduce gravity (3.73 m/s2 on Mars, 1.62 on the Moon, 9.82 on Earth), pressure (636 Pa on Mars, 3e-10 Pa on the Moon, 101400 Pa on Earth), temperature range (184 to 242 K on Mars, 95 to 390 K on the Moon) or day length (24.7 h on Mars, 709 h on the Moon). These values are published in NASA Planetary Fact Sheets; we did not measure them. Across the 160 current pairs: landing is yes for 115, partial for 11 and no for 34; driving is yes for all 160, so it does not tell pairs apart; cold is partial at best for 125 and no for 35; low sun is yes for 70 and no for 90. Example, Jezero and its twin in Tagant, Mauritania: landing yes, driving yes, cold no, low sun yes. Low sun also has a limit on Earth: the grazing share never exceeds 18.6% at any latitude, while Haworth, at the lunar south pole, is in that band 50% of the time.

5. Where Earth runs out. The Earth gap is Mars terrain with no Earth twin within sensor noise. Result: 4.6% of the 1,838 measured Mars windows have no Earth twin (Wilson 95% interval 3.7 to 5.6%). Of the 16 sites, 1 has a gap: 1 of the 10 Moon sites and 0 of the 6 Mars sites. Where there is no twin, rehearsal on Earth is not possible and robots go first. That sentence is our interpretation, not a measurement.

6. Arctic ground. NASADEM, the main Earth elevation model, stops at 60 N. We added Copernicus GLO-30 (60 to 84 N) under the same rules and kept rock only: a window with 20% or more snow and ice is left out. The Earth pool is 1,965 NASADEM windows and 765 Arctic windows. With NASADEM alone, 11.7% of the measured Mars windows have no Earth twin; with Arctic rock added, 4.6%.

7. Permanent Moon base layer. For the 10 Moon sites we compute solar illumination, permanent shadow (PSR) and Earth visibility from NASA's LOLA-based polar illumination product (120 m, 75 to 90 S). Internal checks pass: every PSR pixel has 0% illumination, and six synthetic tests pass. A comparison with published per-site figures was not possible, because the source tables were not accessible; we therefore do not claim agreement with published values.

8. Discoveries. 1,786 distinct Earth places are a top-three twin of at least one Mars or Moon site or Mars window. 50 of them fall inside 22 well-known analog regions; 1,736 do not. "New" only means outside those circles, not that nobody has studied the place.

BENEFITS AND INTENDED IMPACT
- For mission planners and field-test teams: a first filter for where to rehearse, with the evidence and the limits shown next to each choice.
- For analog science: the same measurement on three worlds, with every number traceable to a source file. A failed validation is reported with its numbers, so others can test whether a better distance passes.
- For Mars exploration planning: the Earth gap marks terrain that Earth cannot stand in for, a map of where precursor robots add the most.
- For learners: the unlocked / to-discover map shows how much of Mars is measured at all.

VALIDATION, AS IT CAME OUT
Every threshold was written down before each test ran. Terrain classes: 5 (impact crater, volcanic field, dune field, canyon, plain). Test: can the distance separate windows of the same class from windows of different classes (area under the ROC curve, AUC; threshold 0.70), and does the nearest labelled region have the right class?
- v1.2 (6 features, 4 in the distance): AUC 0.693, fail. Nearest-region class correct: 2 of 5, fail.
- v1.3 (3 features, one blind test on 15 new regions): AUC 0.695, fail (short by 0.005). The lower bound of the AUC 95% interval (0.51) and the permutation test (p 0.007) pass. Nearest-region class correct: 6 of 15 (7 needed; chance 3), fail.
We changed the distance for v1.3 and then ran one blind test. Both failed. We stopped iterating instead of tuning the measure until it passed.
- External validation (pre-registered in PREREG.md): 5 valid analog pairs, 6 required; verdict: insufficient. The pairs are Holuhraun (Iceland), Pinacate Gran Desierto (Mexico), Qaidam Basin (China), Meteor Crater (USA) and Kilbourne Hole (USA); all 5 fall within sensor noise. Median percentile 26.84 (test threshold: below 50); one-sided Wilcoxon p = 0.22. Two candidate regions were excluded by the pre-registered rules: McMurdo Dry Valleys (outside the sensor latitude band) and Haughton Crater (its source names no Mars terrain).

LIMITATIONS
- The measure is an operability filter, not a classifier of geological origin. Craters were mistaken for volcanic fields or canyons, while dunes and plains were recognised.
- Mission % is a reference comparison, not a success probability. The mission limits have no stated baseline length, and we measure slope at 100 m. IM-2 sits on 98% landable terrain at that scale and still tipped over: the hazard was smaller than the grid.
- The Earth pool is rock ground only and is dominated by the Sahara, Arabia and Central Asia, where bare ground is.
- Mars coverage is partial: only terrain with a CTX elevation model covering a full 8 km disk can be measured (0.077 of random Mars points). HRSC and HiRISE were not used.
- Earth cannot reproduce reduced gravity, vacuum, thin atmosphere, cold extremes, day length or radiation. The dossier says so for every pair.
- Light is closed-form (latitude and axial tilt only). A near-horizon check exists only for the 5 Moon sites with a LOLA 5 m elevation model.
- Several Mars site centres come from secondary sources; the Jezero centre is not confirmed by NASA or JPL.
- The sensor-noise threshold for flat terrain rests on only 2 regions.

TOOLS, LANGUAGES AND SOFTWARE
Python 3.14 (NumPy, SciPy including the k-d tree, rasterio, pyproj, shapely, pystac-client, pytest). DuckDB and Parquet hold the facts ledger; every number in the text is generated from it and checked by SQL rules. The web atlas is a static site in JavaScript with Three.js 0.160.0 (WebGL). Elevation data are read by window, never as global mosaics. Hardware: [MARIO: confirmar la linea de hardware]. Code is MIT licensed; derived data are CC BY 4.0, subject to the licences of the source data.
```

Conteo: 8.657 caracteres (de referencia; sin límite oficial encontrado).

---

## 6. Use of Super Intelligence (SI)

Fuente: "Did you utilize any Super Intelligence (SI) tools and software in preparing your solution? If yes, how did you use them?" Nota de la guía: esta respuesta es solo para recolección de datos y los jueces no la ven; los jueces sí ven las marcas, descripciones y metadatos de SI dentro del proyecto.

```text
Yes. The idea, the design decisions (thresholds, what counts as a failure, which results to publish), the game-like atlas presentation (unlocked / to discover) and the mission-success framing came from the team, not from an AI tool. Code and analysis were written with AI assistance: Claude (Anthropic) under the team's direction and review, and the web interface was built with Codex (OpenAI) from the team's written brief. Every number in the project is generated from a facts ledger by code and checked by automatic rules; no number was typed by hand. No AI-generated images are used. The demo uses animation made with code and real captures of the atlas and NASA data; it contains no AI-generated images or footage. Data products carry a generated_with field that records the AI tool used, and the repository README has an "AI assistance" section.
```

Conteo: 851 caracteres.

---

## 7. NASA Data

Fuente: "Provide specific details about what NASA data and resources you used. To be eligible for a Global Award, you must use at least one NASA data or resource."

```text
NASA data used. Each source is listed with its access link.

- NASADEM (NASA JPL / USGS, via Microsoft Planetary Computer): Earth elevation, 1 arc-second, for the NASADEM part of the search pool (56 S to 60 N, 1,965 windows) and all validation regions. https://www.earthdata.nasa.gov/data/catalog/lpcloud-nasadem-hgt-001 (doi:10.5067/MEASURES/NASADEM/NASADEM_HGT.001)
- LOLA 5 m south-pole DEMs (NASA GSFC PGDA, product 78): Moon sites Haworth, Malapert massif, Nobile rim 1 and 2, de Gerlache rim. https://pgda.gsfc.nasa.gov/products/78 (Barker et al. 2021, doi:10.1016/j.pss.2020.105119)
- LOLA 20 m polar LDEM, 80-90 S (NASA GSFC PGDA, product 90): Moon sites IM-1, IM-2, Cabeus B, Mons Mouton. https://pgda.gsfc.nasa.gov/products/90
- LOLA-based Lunar Polar Illumination (NASA GSFC PGDA, product 69): illumination, permanent shadow (PSR) and Earth visibility at 120 m, 75 to 90 S, for the Permanent Moon base layer. https://pgda.gsfc.nasa.gov/products/69 (Mazarico et al. 2011, doi:10.1016/j.icarus.2010.10.030)
- LROC NAC DTM, Apollo 17 (NASA / LROC, PDS): Taurus-Littrow. https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/DATA/SDP/NAC_DTM/APOLLO17/
- MRO CTX DTMs (NASA MRO CTX, processed by USGS Astrogeology, CC0): Mars sites InSight, Spirit, Zhurong, Oxia Planum, the Mars search pool and the Mars coverage grid. https://stac.astrogeology.usgs.gov/api/search (collection mro_ctx_controlled_usgs_dtms). Jezero: Mars 2020 Terrain Relative Navigation CTX DTM mosaic, https://astrogeology.usgs.gov/search/map/mars_2020_terrain_relative_navigation_ctx_dtm_mosaic (doi:10.5066/P906QQT8)
- NASA Planetary Fact Sheets (NSSDC): gravity, pressure, temperature range and day length. https://nssdc.gsfc.nasa.gov/planetary/factsheet/
- NASA mission documents for slope limits: Apollo Lunar Module, NASA TN D-6850, https://ntrs.nasa.gov/citations/19720018253; Lunar Roving Vehicle, NASA TR R-401, https://ntrs.nasa.gov/citations/19730008090; MER landing sites, https://marsoweb.nas.nasa.gov/landingsites/mer2003/doc/original.html; Perseverance, https://science.nasa.gov/mission/mars-2020-perseverance/rover-components/
- NASA Artemis III candidate regions (release RELEASE24-136, 28 Oct 2024; the release gives no coordinates, so region centres are proxies taken from the PGDA files): https://www.nasa.gov/news-release/nasa-provides-update-on-artemis-iii-moon-landing-regions/
- Globe textures: LROC colour map (NASA SVS 4720, https://svs.gsfc.nasa.gov/4720); Blue Marble 2002 (NASA Visible Earth 57752, https://visibleearth.nasa.gov/images/57752/blue-marble-land-surface-shallow-water-and-shaded-topography); Viking MDIM 2.1 mosaic (NASA / JPL / USGS, via Wikimedia Commons). No NASA logos are used.
```

Conteo: 2.712 caracteres.

---

## 8. Space Agency Partner Data and Other References

Fuente: "List all of the data, resources, and tools used in your project ... You are also highly encouraged to use data or resources from the 2026 Space Apps Space Agency Partners." Los socios 2026 incluyen a ESA; los datos de ESA van primero.

```text
Space Agency Partner data (ESA):
- Copernicus DEM GLO-30 (ESA / DLR / Airbus, via Microsoft Planetary Computer): Earth elevation for the Arctic part of the search pool (60 N to 84 N, where NASADEM does not exist) and the second sensor for the sensor-noise test. doi:10.5270/ESA-c5d3d65. Notice: (c) DLR e.V. 2010-2014 and (c) Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.
- ESA WorldCover 2021 v200 (CC BY 4.0): bare-ground and ice shares of each window. doi:10.5281/zenodo.7254221

Other data and resources:
- Gale Crater stereo CTX DTMs (figshare article 6584984, CC BY 4.0): the Gale elevation model. doi:10.6084/m9.figshare.6584984
- Koppen-Geiger climate map, 1 km (Beck et al. 2018, Scientific Data, CC BY 4.0): climate class per twin. doi:10.1038/sdata.2018.214
- Natural Earth 1:10m admin-1 and populated places (public domain): place names and nearest town per twin.
- Microsoft Planetary Computer STAC API: used only to search and sign data URLs.
- Software and libraries: listed in section 5 of this description. Full list with licences and DOIs: REFERENCES.md in the repository, https://github.com/vidal777mv-bit/nsa-mv

Scientific references:
- Barker, M.K., et al. (2021). Improved LOLA elevation maps for south pole landing sites. Planetary and Space Science. doi:10.1016/j.pss.2020.105119
- Mazarico, E., et al. (2011). Illumination conditions of the lunar polar regions using LOLA topography. Icarus 211, 1066-1081. doi:10.1016/j.icarus.2010.10.030
- External validation analog sources (Holuhraun, Pinacate Gran Desierto, Qaidam Basin, Meteor Crater, Kilbourne Hole): full citations and links in REFERENCES.md and docs/validation/external/ in the repository. [MARIO: confirmar que REFERENCES.md tiene las URLs completas de estas cinco fuentes]
```

Conteo: 1.832 caracteres.

---

## Checklist: lo que Mario debe tener a mano

Plazo: "Submit for Judging" antes del domingo 15-nov-2026, 23:59 hora local del Local Event (San Salvador, UTC-6). Según el reloj de la consulta (00:19 UTC del 16-nov, o sea 18:19 en El Salvador), quedan unas 5 horas. Hasta el cierre se puede editar y reenviar; cuenta solo el último envío guardado.

- [ ] Video de demo: enlace de YouTube (público, sin login), 30 s o menos. Alternativa: diapositivas de 7 o menos, en inglés. Si el video no está en inglés, subtítulos en inglés. Si aparecen personas, ninguna menor de 18 años.
- [ ] Enlace final: https://vidal777mv-bit.github.io/nsa-mv/ abierto en ventana privada, sin login.
- [ ] Repositorio: https://github.com/vidal777mv-bit/nsa-mv público, con REFERENCES.md.
- [ ] Verificar que el sitio publica la capa Permanent base (campo 5, punto 7 y campo 7, PGDA product 69). Si no está publicada, quitar esos dos textos.
- [ ] Hardware (campo 5, última sección): completar la línea que está entre corchetes.
- [ ] Revisar los campos en el formulario por si marca un límite de caracteres que no vi.
- [ ] Marcar "Terms and Conditions" y "Confirm All Work is Original", luego "Submit for Judging". Solo lo hace Mario.
- [ ] Opcional: solicitar la clasificación FortiGuard del sitio (guía, "Sharing Files"), para evitar bloqueos de filtros web durante la evaluación.

## Decisiones pendientes de Mario

1. Pares de rehabilitación: el texto usa los 160 pares actuales (los que muestra el sitio). project_page.md usa 248 pares, que incluyen 88 archivos viejos de data/derived/rehearsal/ (HOW_IT_WORKS, sección 8b y 13). Si quieres las cifras de 248, cambiar en el campo 5, punto 4.
2. McMurdo Dry Valleys: RESULTS.md lo deja "pendiente de decisión de Mario". El texto dice que quedó excluido por la regla de latitud. Si decides incluirlo, hay que rehacer la validación externa antes de cambiar el texto.
3. Capa Permanent base: project_page.md y HOW_IT_WORKS.md no la describen. El texto la incluye porque el reto la nombra y su verificación está en docs/verification/moon_base.md. Su verificación contra cifras publicadas no se completó, y el texto lo dice.

## Discrepancias encontradas en los documentos fuente

- Gale: project_page.md dice 100.0%; los archivos (README, mission/gale.json) dan 99.98%. El texto usa 99.98%.
- NASADEM: README dice 30.9 m; HOW_IT_WORKS dice 30 m. El texto no pone la resolución en metros, solo "1 arc-second".
- RESULTS.md (validación externa) dice 2,724 ventanas con D; HOW_IT_WORKS dice 2,722 en el árbol de búsqueda. El texto no cita ese número.
