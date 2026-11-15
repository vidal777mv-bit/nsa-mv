# REFERENCES

Every data product, reference, centre source and method used by this project. Checked and dated 2026-11-14 unless
stated. Machine-readable records: `config/sources.json` (`used`, `use`, `license`, `verified`), `config/sites.json`
(`center_source`, 10.9 fields), `config/regions.json`, `config/missions.json`, `config/bodies.json`.
DOI status means doi.org resolution (HTTP 200 or 202 after redirect); 403 means the publisher blocks our client, the DOI itself resolves.

## 1. Earth elevation and land cover

- NASADEM HGT v001 (NASA JPL / USGS, via Planetary Computer, STAC `nasadem`). doi 10.5067/MEASURES/NASADEM/NASADEM_HGT.001 (200). Licence: open without restriction. Earthdata catalog record (https://www.earthdata.nasa.gov/data/catalog/lpcloud-nasadem-hgt-001, read 2026-11-15): 'This dataset is openly shared, without restriction, in accordance with the EOSDIS Data Use and Citation Guidance' (https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance). Citation required. The Planetary Computer STAC label 'proprietary' is superseded by the producer's statement. Resolved 2026-11-15; Mario sign-off pending (docs/verification/licences.md). Used: all Earth 5 km windows, search pool.
- Copernicus DEM GLO-30 (ESA / DLR / Airbus, STAC `cop-dem-glo-30`). doi 10.5270/ESA-c5d3d65 (200). Licence COP-DEM-GLO-30-F (https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf): free, with the Art. 6 notice when distributed. Used: second DEM of the 15 dev regions (V1).
- ESA WorldCover 2021 v200 (ESA consortium, S3 mirror and STAC `esa-worldcover`). doi 10.5281/zenodo.7254221 (200). CC BY 4.0 (https://esa-worldcover.org/en/data-access). Credit: '© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium'. Used: land-cover checks and the coarse pool filter.
- Microsoft Planetary Computer STAC API (https://planetarycomputer.microsoft.com/api/stac/v1). Service terms not read. Used: search and signing only.
- MODIS MOD11A2 v061 (NASA LP DAAC). doi 10.5067/MODIS/MOD11A2.061 (200). Not used (scope cut 2026-11-13).
- Copernicus GLO-30 example tile N75 W090 (public S3). Not used (probe only).

## 2. Planetary elevation (Moon and Mars)

- LOLA 5 m south-pole LDEMs, PGDA product 78 (NASA GSFC PGDA, https://pgda.gsfc.nasa.gov/products/78). Method paper Barker et al. 2021, doi 10.1016/j.pss.2020.105119 (200). Licence: no licence statement on the page; it asks users to cite the reference; treated as NASA public data with citation. Used: full DEMs of haworth, malapert_massif, nobile_rim_1, nobile_rim_2, de_gerlache_rim_2; ROI archive Site11 for the de Gerlache centre.
- LOLA 20 m polar LDEM 80-90 S, PGDA product 90 (https://pgda.gsfc.nasa.gov/products/90). Page cites Barker et al. 2023, Planetary Science Journal (DOI not retrieved). Licence: no licence statement; a 'Data Usage Policy' heading with no text (read 2026-11-14). Used: 6 km windows of im1_odysseus, im2_athena, cabeus_b_peak, mons_mouton_plateau.
- LROC NAC DTM Apollo 17, 5 m (NASA / LROC, ASU; PDS node https://pds.lroc.im-ldi.com/). Licence: public domain for products on the LROC Data Node of the PDS, per the LROC Terms of Use (https://lroc.im-ldi.com/about/terms, read 2026-11-14 and re-read 2026-11-15); credit 'NASA/GSFC/Arizona State University'. Used: 6 km window of apollo17_taurus_littrow.
- USGS CTX DTM, InSight N15_068239 / N03_063385 (STAC `mro_ctx_controlled_usgs_dtms`, S3 bucket astrogeo-ard). Licence: USGS public domain (https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits); STAC collection CC0-1.0 (read 2026-11-14). Credit: USGS / NASA MRO CTX. Used: 6 km window of insight_elysium.
- USGS CTX DTM, Spirit P22_009530 / P06_003333. Licence: USGS public domain (https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits); STAC collection CC0-1.0 (read 2026-11-14). Credit: USGS / NASA MRO CTX. Used: 6 km window of spirit_columbia.
- USGS CTX DTM, Zhurong N14_067844 / N13_067580. Licence: USGS public domain (https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits); STAC collection CC0-1.0 (read 2026-11-14). Credit: USGS / NASA MRO CTX. Used: 6 km window of zhurong.
- USGS CTX DTM, Oxia Planum N06_064538 / N06_064828. Licence: USGS public domain (https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits); STAC collection CC0-1.0 (read 2026-11-14). Credit: USGS / NASA MRO CTX. Used: 6 km window of oxia_planum.
- USGS Mars 2020 TRN CTX DTM mosaic, Jezero, 20 m (planetarymaps.usgs.gov). doi 10.5066/P906QQT8 (200). Licence: USGS public domain (https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits). Used: jezero.
- Gale Crater stereo CTX DTMs and orthoimages (figshare article 6584984). doi 10.6084/m9.figshare.6584984.v1 (202). CC BY 4.0. Credit: Grindrod, P., 'Gale Crater Stereo CTX DTMs + Orthoimages', figshare, doi 10.6084/m9.figshare.6584984.v1. Used: tile PG_Gale_CTX_3_3_AATE_20m.tif (extracted) for gale.
- HRSC-MOLA blended DEM 200 m v2 (USGS). Not downloaded (11.4 GB); reserved for the regional scale, STANDARDS 10.10 (not run).

## 3. Other reference data and globe textures

- Natural Earth 1:10m Cultural, Admin 1 States and Provinces, v5.1.1 (https://www.naturalearthdata.com/downloads/10m-cultural-vectors/; zip from https://naciscdn.org/naturalearth/10m/cultural/). Public domain (https://www.naturalearthdata.com/about/terms-of-use/); attribution not required. Used: reverse geocoding (agent A).
- Moon globe, LROC colour map 2k, NASA SVS CGI Moon Kit 4720 (https://svs.gsfc.nasa.gov/4720). NASA media guidelines (https://www.nasa.gov/nasa-brand-center/images-and-media/): credit NASA; not formally public domain. Used: site/assets/globes/moon.jpg.
- Earth globe, Blue Marble 2002, NASA Visible Earth 57752, via Wikimedia Commons (https://commons.wikimedia.org/wiki/File:Blue_Marble_2002.png). Public domain (Commons licence field). Used: site/assets/globes/earth.jpg.
- Mars globe, Viking MDIM 2.1 colour mosaic (USGS 232 m), via Wikimedia Commons (https://commons.wikimedia.org/wiki/File:Mars_Viking_MDIM21_ClrMosaic_1km.jpg). Public domain (USGS policy). Used: site/assets/globes/mars.jpg. Credit lines: site/assets/globes/SOURCES.md.
- NASA NSSDC Planetary Fact Sheets: https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html, moonfact.html, marsfact.html. Values in config/bodies.json, read 2026-11-14.
- NASA news release RELEASE24-136, 28 Oct 2024, Artemis III candidate landing regions, no coordinates (https://www.nasa.gov/news-release/nasa-provides-update-on-artemis-iii-moon-landing-regions/).
- Koppen-Geiger climate maps, present day, 1 km (0.0083 deg), Beck, H.E. et al. 2018, Scientific Data, doi 10.1038/sdata.2018.214 (200); figshare dataset doi 10.6084/m9.figshare.6396959 (https://figshare.com/articles/dataset/Present_and_future_K_ppen-Geiger_climate_classification_maps_at_1-km_resolution/6396959). Licence CC BY 4.0 (figshare record, read 2026-11-14). Credit: Beck, H.E. et al. (2018), 'Present and future Köppen-Geiger climate classification maps at 1-km resolution', Scientific Data, doi 10.1038/sdata.2018.214, CC BY 4.0. File data/raw/reference/koppen/Beck_KG_V1_present_0p0083.tif (23,094,320 bytes, EPSG:4326, uint8); legend data/raw/reference/koppen/legend.txt (codes 1-30, Af to EF, with the Beck RGB values). Used: Earth context koppen_class per twin, not part of the score.
- Natural Earth 1:10m Cultural, Populated places, version 5.1.2 (https://www.naturalearthdata.com/downloads/10m-cultural-vectors/; zip https://naciscdn.org/naturalearth/10m/cultural/ne_10m_populated_places.zip, 2,811,199 bytes). Public domain (terms read 2026-11-14). Folder data/raw/reference/ne_10m_populated_places/. Used: nearest_town per Earth twin, not part of the score.

## 4. Mission slope limits (config/missions.json; quotes read in the source)

- Apollo Lunar Module landing, moon, 12 deg: Rogers 1972, NASA TN D-6850, https://ntrs.nasa.gov/citations/19720018253. Quote: "an effective slope of 12 deg or less, including the effects of depressions or protuberances". Design value, no baseline stated.
- Lunar Roving Vehicle driving, moon, 25 deg (alternative 23 deg): Costes, Farmer & George 1972, NASA TR R-401, https://ntrs.nasa.gov/citations/19730008090. Quote: "slopes with maximum slope angles along several vehicle lengths of approximately 25 deg"; "Slopes of the order of 20 to 23 deg can be negotiated in favorable circumstances". No baseline stated.
- MER landing sites, Mars, 15 deg: NASA MER landing-site memorandum 2003, https://marsoweb.nas.nasa.gov/landingsites/mer2003/doc/original.html. Quote: "surface slopes should generally be less than 15 deg". No baseline stated; general requirement.
- MSL (Curiosity) landing, Mars, 30 deg at 2-5 m baselines: Golombek et al. 2012, doi 10.1007/s11214-012-9916-y (200); USGS record https://pubs.usgs.gov/publication/70047380. Quote: "slopes of <30 deg at baselines of 2-5 m". Not comparable to 100 m; not used as the limit.
- Mars 2020 Perseverance driving, Mars, 30 deg: NASA Science, https://science.nasa.gov/mission/mars-2020-perseverance/rover-components/. Quote: "avoid terrains that would tilt the rover more than 30 degrees".
- Not found (config/missions.json not_found): Chandrayaan-3, Chang'e-3/4 slope limits, Phoenix slope value, Curiosity driving limit.
- Decision open for the lead: Mars landing limit 15 deg (MER, general) vs 30 deg (MSL, at 2-5 m).

## 5. Centre sources for the 16 targets (config/sites.json)

- haworth, malapert_massif, nobile_rim_1, nobile_rim_2: DEM-raster centre of the PGDA 5 m DEM (https://pgda.gsfc.nasa.gov/products/78). Proxy, not a NASA landing coordinate.
- de_gerlache_rim_2: ROI polygon bounding-box centre, Site11 ROI archive (https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site11/Site11_ROIs.tgz, real gzip). Proxy.
- apollo17_taurus_littrow: NSSDC Lunar Module row, 20.1911 N, 30.7723 E (https://nssdc.gsfc.nasa.gov/planetary/lunar/lunar_sites.html). Primary.
- im1_odysseus: NASA LRO release, 80.13 S, 1.44 E (https://www.nasa.gov/missions/lro/nasas-lro-images-intuitive-machines-odysseus-lander/). Primary.
- im2_athena: LROC 'IM-2 Landing Region', intended site -84.78, 29.13 E (https://www.lroc.asu.edu/images/1401). Primary, intended site (touchdown not given).
- cabeus_b_peak: LROC NAC ROI NAC_ROI_CABEUSPKLO2, centre -83.6, 291.2 E (https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_ROI_CABEUSPKLO2). Proxy, not a NASA coordinate.
- mons_mouton_plateau: LROC NAC ROI NAC_ROI_MOUTNPLTLO1, centre -84.3, 30.6 E (https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_ROI_MOUTNPLTLO1). Proxy.
- jezero: Wikipedia 'Octavia E. Butler Landing' (https://en.wikipedia.org/wiki/Octavia_E._Butler_Landing), rounded 18.44 N, 77.45 E. Secondary source; the 4-decimal value 18.4447, 77.4508 is the lead's and is not confirmed by NASA/JPL.
- gale: Wikipedia 'Bradbury Landing' coordinate template, -4.5895, 137.4417 (https://en.wikipedia.org/wiki/Bradbury_Landing). Secondary source.
- insight_elysium: Golombek et al. 2020, doi 10.1029/2020EA001248 (DOI resolves; publisher 403), 4.502384 N, 135.623447 E, read via search snippet. Secondary source. NASA InSight page gives only the 135.9 E pre-landing target (https://science.nasa.gov/mission/insight/).
- spirit_columbia: NASA science page 'In Depth: Spirit' (https://science.nasa.gov/mission/mer-spirit/), 14.5692 S, 175.4729 E. Primary.
- zhurong: Li et al. 2022, Nature, doi 10.1038/s41586-022-05147-5 (200), and Ding et al. 2022, Nature Geoscience, doi 10.1038/s41561-022-00905-6 (200): 25.066 N, 109.925 E, read via search snippets; the articles were not opened (redirect to login). Secondary source.
- oxia_planum: Wikipedia 'Rosalind Franklin (rover)' mirror (https://wiki.krisyotam.com/content/wikipedia_en_all_nopic_2026-03/ExoMars_rover): favoured ellipse 18.20 N, 335.45 E. Secondary source; no ESA primary coordinate found.
- Earth validation and holdout regions: Wikipedia article coordinates per entry (`center_source.url` in config/regions.json). Earth Impact Database and Global Volcanism Program pages were not readable from this environment.

## 6. Outcome sources (10.9 landing fields)

- InSight landed 26 Nov 2018: https://science.nasa.gov/mission/insight/.
- Perseverance landed in Jezero, 18 Feb 2021: https://science.nasa.gov/mission/mars-2020-perseverance/.
- Curiosity landed 6 Aug 2012, Gale: https://science.nasa.gov/mission/msl-curiosity/.
- Spirit landed 3 Jan 2004, Gusev: https://science.nasa.gov/mission/mer-spirit/.
- Apollo 17, December 1972, Taurus-Littrow (launch 7 Dec, splashdown 19 Dec 1972): https://www.nasa.gov/mission/apollo-17/.
- Odysseus tipped over, Feb 2024: Intuitive Machines CEO Steve Altemus, reported by NBC: https://www.nbclosangeles.com/news/national-international/odysseus-spacecraft-on-its-side-on-moon-company-says/ (NASA LRO release does not mention the tip-over).
- Athena ended on its side in a 20 m crater, Mar 2025: LROC image 1408 (Mark Robinson, 10 Mar 2025): https://lroc.im-ldi.com/images/1408.
- Oxia Planum landing planned 2030: Sefton-Nash et al., EPSC 2026 abstract, ESA-affiliated: https://meetingorganizer.copernicus.org/EPSC2026/EPSC2026-411.html. No esa.int page found.
- Zhurong landed May 2021: Ding et al. 2022 abstract (snippet only): https://www.nature.com/articles/s41561-022-00905-6.
- Artemis III candidates (nine regions, no coordinates): NASA release above (section 3).

## 7. Methods (DOIs checked 2026-11-14 unless stated)

- Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. JASA. doi 10.1080/01621459.1927.10502953 (resolves; publisher 403). Wilson score interval.
- Efron, B. (1979). Bootstrap methods: another look at the jackknife. Annals of Statistics. doi 10.1214/aos/1176344552 (200). Bootstrap over regions.
- Mann, H. B., & Whitney, D. R. (1947). On a test of whether one of two random variables is stochastically larger than the other. Annals of Mathematical Statistics. doi 10.1214/aoms/1177730491 (200). AUC by the U statistic.
- Rosenburg et al. 2011, JGR, doi 10.1029/2010JE003716. Lunar slopes and roughness (LOLA). Verified earlier via Crossref.
- Kreslavsky & Head 2000, JGR Planets, doi 10.1029/2000JE001259. Mars kilometre-scale roughness (MOLA). Verified earlier via Crossref.
- Shepard et al. 2001, JGR Planets, doi 10.1029/2000JE001429. Natural terrain roughness. Verified earlier via Crossref.
- Strahler 1952, GSA Bulletin, doi 10.1130/0016-7606(1952)63[1117:HAAOET]2.0.CO;2. Hypsometry. Verified earlier via Crossref (issue and pages not in Crossref).
- De Reu et al. 2013, Geomorphology, doi 10.1016/j.geomorph.2012.12.015. Topographic position index. Verified earlier via Crossref.
- Bigun, Granlund & Wiklund 1991, IEEE TPAMI, doi 10.1109/34.85668. Orientation estimation (substitute for a 1987 reference that Crossref does not hold). Verified earlier via Crossref.
- Weiss 2001, topographic position and landforms (conference poster). No DOI; details not checked against a source. Cited only as the origin of the TPI idea.
- Barker et al. 2021, Planetary and Space Science 203, 105119, doi 10.1016/j.pss.2020.105119 (200). LOLA south-pole maps. (PGDA product 90 page cites Barker et al. 2023, Planetary Science Journal; that DOI was not retrieved.)
- Golombek et al. 2012 (MSL site), doi 10.1007/s11214-012-9916-y; Golombek et al. 2003 (MER sites), doi 10.1029/2003JE002074; Anderson et al. 2003, doi 10.1029/2003JE002125; Arvidson et al. 2008, doi 10.1029/2007JE003021. Context for the slope limits; verified earlier via Crossref.

## 8. Code libraries (versions in requirements.lock.txt)

- rasterio 1.5.2 (windowed reads, merge, GeoTIFF and JPEG writing): BSD-3-Clause (standard licence; not opened).
- pystac-client 0.9.1 and planetary-computer 1.0.0 (STAC search and URL signing): MIT (standard; not opened).
- pyproj 3.8.0 (projection to the LOLA and CTX raster CRS): MIT (standard; not opened).
- requests 2.34.2 (HTTP): Apache-2.0 (standard; not opened).

## 9. Licence summary and open items

- Public domain or open: USGS products (public domain policy; the CTX DTM collection record states CC0-1.0), LROC NAC DTM Apollo 17 (LROC terms: public domain via the PDS node), Natural Earth (public domain, no attribution required), Commons Earth and Mars textures (public domain), ESA WorldCover (CC BY 4.0), Gale figshare tiles (CC BY 4.0), Köppen-Geiger 1 km (CC BY 4.0), NASA imagery (NASA media guidelines: credit NASA, not public domain in general; see the NASA page).
- NASADEM: open without restriction per the Earthdata catalog record (read 2026-11-15); citation required. The Planetary Computer STAC label 'proprietary' is superseded. Mario sign-off pending.
- Copernicus DEM: free licence with a mandatory notice (Art. 6(a)) and the liability sentence (Art. 6(c)); both must appear with any distribution.
- LOLA/PGDA: no licence text on the product page; cite the reference given on the page.
- Nothing from data/raw is redistributed in the repo (git-ignored).

## 10. Known analog regions (config/known_analog_regions.json, 13 regions)

Each region is a circle approximation (see the radius rule in the file). Analog source: the page opened 2026-11-14 that calls the place a Mars or Moon analog. Extent source: Wikipedia infobox or the analog page, read through the Wikipedia API.

- Atacama Desert: analog NASA Astrobiology research locations, https://astrobiology.nasa.gov/research-locations/ ("a suitable analog for ancient Mars"); extent Wikipedia 'Atacama Desert' (area 104,741 km2).
- Mojave Desert and Death Valley: analog NASA technical report 20150005824 (LPSC 2011), https://ntrs.nasa.gov/citations/20150005824 ("considered a Mars analog site by the Terrestrial Analogs Panel"); extent Wikipedia 'Mojave Desert' infobox 81,000 km2 (text says 54,000 sq mi; infobox used).
- Meteor Crater: analog NASA Earth Observatory, https://science.nasa.gov/earth/earth-observatory/arizonas-meteor-crater-148384/ (training for impact craters on Earth, the Moon and Mars); diameter 1.2 km from the same page.
- Craters of the Moon: analog NPS, https://www.nps.gov/crmo/learn/historyculture/space-exploration-research-and-astronaut-training.htm (NASA research "in preparation for future Mars missions"); extent Wikipedia infobox 753,000 acres.
- Qaidam Basin: analog USGS, https://www.usgs.gov/media/images/chinas-qaidam-basin-landscape-similar-mars (1988, "some similarity with Mars"); extent Wikipedia 120,000 km2.
- Lanzarote: analog ESA, https://www.esa.int/ESA_Multimedia/Images/2016/10/Lanzarote (Pangaea course, "planetary analogue"); extent Wikipedia 845.94 km2.
- Svalbard: analog DLR Europlanet, https://europlanet.dlr.de/Svalbard/index.html ("a terrestrial cold-climate analog for Mars"); extent Wikipedia 62,045 km2.
- Rio Tinto: analog NASA Astrobiology, https://astrobiology.nasa.gov/news/red-river-drills-for-mars/ (2003, Stoker: "an important analog"); length 100 km from Wikipedia 'Rio Tinto'.
- Nordlinger Ries: analog Lambert & Reimold 2023, Frontiers in Astronomy and Space Sciences, doi 10.3389/fspas.2023.1186173, https://www.frontiersin.org/journals/astronomy-and-space-sciences/articles/10.3389/fspas.2023.1186173/text (Ries ranked first as field analog); diameter 24 km from Wikipedia.
- Sudbury Basin: same Lambert & Reimold 2023 paper (Sudbury among field analogs for planetary exploration); original diameter 130 km from Wikipedia.
- Haughton impact crater (Devon Island): analog CBC, https://www.cbc.ca/lite/story/1.1139281 ("Using the Haughton Crater as an analog for Mars"); diameter 23 km from Wikipedia.
- Holuhraun lava flow field (Iceland): analog USGS, https://www.usgs.gov/publications/2014-2015-holuhraun-lava-flow-field-iceland-a-planetary-analog-young-volcanic-terrains (Planetary Science Journal 2025, "a terrestrial analog for volcanic terrains in Elysium Planitia"); extent Wikipedia 'Holuhraun' (more than 85 km2).
- El Pinacate y Gran Desierto de Altar Biosphere Reserve: analog Planetary Science Institute, https://psi.edu/blog/investigations-of-lava-flows-in-the-pinacate-volcanic-field-as-analogues-for-mars (2024, Pinacate lava flows as analogues for Mars); extent Wikipedia biosphere reserve 2,695.05 km2.

Added under the conservative inclusion rule (lead decision 2026-11-14: any opened source calling the place a planetary analog is enough; radius 100 km, rule default_conservative_100km, where no extent could be sourced):

- Henry Mountains and Hanksville area, southern Utah: analog visitutah.com, https://www.visitutah.com/de-de/articles/moonscapes-marscapes-and-more (read 2026-11-14: the terrain near Hanksville "looks almost Mars-like"); radius 100 km (default); centre Wikipedia 'Henry Mountains' infobox, 38 06.53 N, 110 48.82 W.
- Mars Desert Research Station, Utah: analog the same visitutah.com article (calls MDRS "a Mars habitat simulation"); radius 100 km (default); centre from the Wikipedia coordinate used earlier.
- McMurdo Dry Valleys: analog NASA technical report 20100003844, https://ntrs.nasa.gov/citations/20100003844 ("the best known Earth analog to the Martian high-northern plains"); radius 100 km (default).
- Mauna Kea: analog NASA Astrobiology NAI 2010 annual report, https://astrobiology.nasa.gov/nai/annual-reports/2010/uh/analogue-environment-deployments-on-the-big-island/index.html ("excellent analogs for areas on the Moon and/or Mars"); radius 100 km (default).
- Pilbara: analog West et al. 2010, Planetary and Space Science 58(4) 447-458, https://researchers.mq.edu.au/en/publications/the-geology-of-australian-mars-analogue-sites/ (Pilbara named where the oldest evidence of life "guides exploration for early life on Mars"); radius 402.0 km (equal area, 507,896 km2, Wikipedia 'Pilbara', lead review 2026-11-14).
- Kilbourne Hole maar: analog NASA Goddard field team blog, https://science.nasa.gov/blogs/notes-from-the-field/2018/01/11/in-new-mexico-land-of-volcanoes ("a perfect analog site for testing ... volcanic areas on the Moon, Mars"); radius 100 km (default).

Added on the lead's request (Arizona Apollo training and NASA analog field tests; Wikipedia articles read 2026-11-14 via the API; radius 100 km, default_conservative_100km; the Arizona sites are not within 50 km of each other, so they are separate entries):

- S P Crater (Arizona): Wikipedia, https://en.wikipedia.org/wiki/S_P_Crater ("American astronauts have used the crater to train for moonwalking"); centre coordinate template 35.5822 N, 111.6318 W.
- Desert RATS field sites around Flagstaff: Wikipedia, https://en.wikipedia.org/wiki/Desert_Research_and_Technology_Studies (Apollo-style lunar training since 1997; field season "in planned locations surrounding Flagstaff, Arizona"); the article has no coordinate, so the centre is the Flagstaff, Arizona coordinate, Wikipedia https://en.wikipedia.org/wiki/Flagstaff,_Arizona (35.1806 N, 111.62 W).

Radius review after the lead's check of 2026-11-14 (elongated regions):

- Wadi Rum (Jordan): analog NASA Earth Observatory, https://science.nasa.gov/earth/earth-observatory/movie-mars-on-earth-148764/ (28 Aug 2021, colours and textures "a close match to those found on Mars"); radius 15.1 km (equal area 721 km2, Wikipedia 'Wadi Rum' infobox).
- Lanzarote: radius changed from 16.4 km (equal area) to 100 km (default_conservative_100km): the island is elongated and no length was sourced.
- Pilbara: radius changed from 100 km (default) to 402.0 km (equal area 507,896 km2, Wikipedia text).
- Atacama Desert: radius 800 km by the half-length rule (lead, 2026-11-14), centre -24.15, -70.2 (midpoint of the coast from Arica 18 24 S to La Serena 29 55 S). Length source: Wikipedia 'Atacama Desert', "According to the World Wide Fund for Nature, the Atacama Desert ecoregion occupies a continuous strip for nearly 1,600 kilometres (1,000 mi) along the narrow coast of the northern third of Chile, from near Arica (18 24 S) southward to near La Serena (29 55 S)".
- Qaidam Basin, Mojave Desert, Svalbard: elongated, but no length could be sourced (Britannica and the WWF ecoregion page returned 403; the Wikipedia articles give no length). The half-length rule is not applied; the equal-area radii stay (195.4, 160.6, 140.5 km) and are flagged in config/known_analog_regions.json.

Left out, with the reason:

- Colorado Plateau as a whole: no opened source calls the plateau itself an analog (the Meteor Crater page only places the crater on it).
- Cinder Lake crater field and Black Point lava flow: no Wikipedia article under those names (search returned other pages); NASA TR 20100024529 (Black Point) returned an unreadable PDF.
- Tenerife / Teide: analog pages returned 403 or an unreadable PDF (a Tenerife instrument test, no analog sentence readable).
- Namibia: ESA caption (https://www.esa.int/ESA_Multimedia/Images/2024/05/Earth_from_Space_Namibian_landforms, 2024) says an image "may resemble the surface of Mars"; resemblance only, not an analog call. Not included.
- Ladakh: the BSIP paper (Chaddha et al. 2024) returned 404; no other opened source.
- Dhofar (AMADEE-18, https://oewf.org/en/amadee-18): an analog source exists, but no sourced centre coordinate was found, so the region is not listed.
