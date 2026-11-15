# Common Ground: measured Earth analogs for Mars and Moon sites

**One-line summary.** Pick a site on Mars or the Moon, see what the mission needs, and find the place on Earth whose terrain measures closest to it, with what you can rehearse there, what you cannot, and where Earth has no match.

NASA Space Apps Challenge 2026. Challenges: *Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars* and *Interplanetary Survival Guide: Martian Map*.

Repository and demo: [[PENDING: public repository URL and demo/video URL]]

## High-level summary

Common Ground answers one question for mission planners: where on Earth can a team rehearse for this place? Pick a site on Mars or the Moon. The atlas shows what the mission needs (land, drive, live) and measures the terrain from elevation models. An exact nearest-neighbour search over 2,730 bare-ground Earth windows finds the Earth twin. A dossier lists what a team can rehearse there and what Earth cannot teach: gravity, vacuum, cold, day length and light. Last, it shows where Earth runs out: Mars terrain with no Earth twin, where robots go first. Both validation tests narrowly failed their pre-registered thresholds. We show the numbers as they came out. The signal is real but modest, and it measures operability, not geological origin.

## What it does and how it works

The atlas has one path, in this order.

**1. Pick a site.** 16 sites: 6 on Mars (Jezero, Gale, InSight, Spirit, Zhurong, Oxia Planum) and 10 on the Moon (Apollo 17, IM-1, IM-2 and 7 Artemis III candidate regions). Mars comes first. The Mars globe is a game-like map with three states: *unlocked* (measured), *to discover* (an elevation model exists, not yet measured) and *out of reach* (no elevation model we could use). On the one-degree Mars grid, 1,621 cells are unlocked and 6,988 are to discover.

**2. See what the mission needs.** Land, drive, live. Landing and driving limits come from NASA documents and are listed with their sources: Mars 15 degrees for landing (MER requirement) and 30 degrees for driving (Perseverance tilt limit); Moon 12 degrees (Apollo Lunar Module) and 25 degrees (Lunar Roving Vehicle). None of the sources states a baseline length.

**3. Read the measured evidence.** Every window is an 8 km disk on a 100 m grid, computed the same way on Mars, the Moon and Earth. Three features enter the score: the 95th percentile of slope, the hypsometric integral (bowl or plateau) and the Hurst exponent (how bumpiness grows with distance, over 100 to 800 m). Three more are shown but not scored (grain direction, ridges, hollows). The page also shows the share of the disk whose slope is within the limit that a completed mission demonstrated. This is a reference comparison, not a probability of success. Example: Jezero 99.5% for landing and Gale 100.0%, both at a 100 m baseline. Light comes from a closed-form model of latitude and axial tilt alone: the Sun is in the 0 to 10 degree grazing band 6.25% of the time at Jezero and 6.23% at Apollo 17.

**4. Meet its Earth twin.** The distance between two windows is the root-mean-square difference of the three scored features, each divided by a robust spread (1.4826 times the median absolute deviation) computed over the Earth pool. A k-d tree gives the exact nearest neighbours and was tested against brute force on a seeded sample of queries. Twins closer than the measured sensor noise are shown as statistically tied (threshold 0.42 for rugged terrain, from 13 regions). Example: the closest twin of Jezero is a window in Tagant, Mauritania, with D = 0.057; slope p95 is 6.8 degrees at Jezero and 6.6 degrees at the twin. Each twin also carries context that is not scored: Koppen climate class, elevation and nearest town.

**5. Read the dossier: rehearse here, cannot teach you.** For each pair the dossier lists what the Earth site can rehearse (landing and driving terrain, cold, low sun) and what it cannot. Earth cannot reproduce the target's gravity (3.73 m/s2 on Mars, 1.62 on the Moon, 9.82 on Earth), pressure (636 Pa on Mars, 3e-10 Pa on the Moon, 101400 Pa on Earth), temperature range (184 to 242 K on Mars, 95 to 390 K on the Moon) or day length (24.7 h on Mars, 709 h on the Moon). These values are published (NASA Planetary Fact Sheets), not measured by us. Each pair gets one line per test, with its status. Example, Jezero and its twin in Tagant, Mauritania: landing yes, driving yes, cold no, low sun yes. Across all 248 pairs, landing is yes for 167, partial for 28 and no for 53; cold is partial (its best possible status) for 182 and no for 66; low sun is yes for 85 and no for 163. Driving is yes for all 248 pairs, so it does not tell pairs apart. Low sun also has a limit on Earth: the closed-form grazing share never exceeds 18.6% at any latitude (the maximum is at 72.5 degrees), while Haworth, at the lunar south pole, is in that band 50% of the time.

**6. See where Earth runs out.** The Earth gap is Mars terrain with no Earth twin: no Earth window is within sensor noise. We apply the same test to 1,838 measured Mars windows and to the 16 sites. Result: 4.6% of the 1,838 measured Mars windows have no Earth twin within sensor noise (Wilson 95% interval 3.7 to 5.6%). Of the 16 sites, 1 have a gap: 1 of the 10 Moon sites and 0 of the 6 Mars sites. Where there is no twin, rehearsal on Earth is not possible and robots go first. That sentence is our interpretation, not a measurement.

**The Arctic: the missing part.** NASADEM, the elevation model behind most Earth analog work, stops at 60 N. We added Arctic ground from Copernicus GLO-30 (60 to 84 N) under the same rules and kept rock only: a window with 20% or more snow and ice is left out, in both bands (1,335 windows were left out for ice, too little bare ground or no elevation clip; each one is listed with its reason in data/derived/pool_rules/excluded.json). The Earth pool is now 1,965 NASADEM and 765 Arctic windows. With NASADEM alone, 11.7% of the measured Mars windows have no Earth twin; with Arctic rock added, 4.6%. For the Moon, the sites without an Earth twin go from 3 to 1. Every Arctic closure is a tie within sensor noise: the noise threshold is itself the spread between NASADEM and Copernicus over the same places.

### The Mars pool

To say anything about Mars as a whole, we drew random Mars points and kept those covered by a single CTX elevation model with at least 90% valid pixels over the 8 km disk. 2,000 windows were accepted from 25,914 attempts, a rate of 0.077 (Wilson 95% interval 0.074 to 0.080). Of the 2,000 accepted windows, 1,838 were measured and 162 were not. Each measured window has its top three Earth twins.

### Discoveries

1,786 distinct Earth places are a top-three twin of at least one Mars or Moon site or Mars window (a place that is the twin of several sites is counted once). 50 of them fall inside one of 22 well-known analog regions (drawn as circles, an approximation); 1,736 do not. "New" means only that: outside those circles. It is not a claim that nobody has studied the place.

### Validation, as it came out

Every threshold was written down before each test ran. Terrain classes: 5 (impact crater, volcanic field, dune field, canyon, plain). Test: can the distance tell windows of the same class from windows of different classes (area under the ROC curve, AUC), and does the nearest labelled region have the right class?

| Test | v1.2 (6 features, 4 in the distance) | v1.3 (3 features), blind holdout of 15 regions |
|---|---|---|
| Features independent (Spearman at most 0.80) | pass (max 0.62) | pass |
| AUC at least 0.70 | **0.693: fail** | **0.695: fail** |
| AUC 95% CI above chance (0.5) | 0.44 to 0.91: fail | 0.51 to 0.92: pass |
| Permutation p below 0.05 | 0.006: pass | 0.007: pass |
| Nearest-region class correct | 2 of 5: fail | 6 of 15 (needed 7; chance 3): fail |

What it means. The v1.2 test failed. We changed the distance (v1.3: slope, hypsometric integral, Hurst; grain direction dropped) and pre-registered a fresh blind holdout. The v1.3 test also failed, narrowly: AUC 0.695 against a threshold of 0.70, and 6 of 15 nearest-region hits against 7 needed. The signal is real and replicated on blind data (permutation p 0.007 and 0.006) but modest. The distance captures how operable terrain is (slope, roughness, shape), not how it formed: craters were mistaken for volcanic fields or canyons, while dunes and plains were recognised. We stopped iterating instead of tuning the measure until it passed. The sensor-noise threshold for flat terrain rests on only 2 regions.

## Benefits and intended impact

- **For mission planners and field-test teams:** a first filter for where to rehearse, with the evidence and the limits shown next to each choice.
- **For analog science:** the same measurement on three worlds, with every number traceable to a source file. A failed validation is reported with its numbers, so others can test whether a better distance passes.
- **For Mars exploration planning:** the Earth gap marks terrain that Earth cannot stand in for. That is a map of where precursor robots add the most.
- **For learners:** the unlocked / to-discover map shows how much of Mars is measured at all.

## Tools, languages and data handling

Python 3.14 (NumPy, SciPy including the k-d tree, rasterio, pyproj, shapely, pystac-client, pytest). DuckDB and Parquet hold the facts ledger. The web atlas is a static site in JavaScript with Three.js 0.160.0 (WebGL). Elevation data are read by window, never as global mosaics. Every number in this text is rendered from the facts ledger (tools/render_facts.py) and checked by SQL rules (tools/check_ledger.py). Code is MIT; derived data are CC BY 4.0, subject to the licences of the source data.

## NASA data used

- **NASADEM** (NASA JPL / USGS, via Microsoft Planetary Computer). Earth elevation, 1 arc-second: the 1,965-window NASADEM part of the search pool (56 S to 60 N) and all validation regions. https://www.earthdata.nasa.gov/data/catalog/lpcloud-nasadem-hgt-001 (doi 10.5067/MEASURES/NASADEM/NASADEM_HGT.001)
- **LOLA 5 m south-pole DEMs** (NASA GSFC PGDA, product 78). Moon: Haworth, Malapert massif, Nobile rim 1 and 2, de Gerlache rim. https://pgda.gsfc.nasa.gov/products/78 (Barker et al. 2021, doi 10.1016/j.pss.2020.105119)
- **LOLA 20 m polar LDEM, 80-90 S** (NASA GSFC PGDA, product 90). Moon: IM-1, IM-2, Cabeus B, Mons Mouton. https://pgda.gsfc.nasa.gov/products/90
- **LROC NAC DTM, Apollo 17** (NASA / LROC, PDS). Moon: Taurus-Littrow. https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/DATA/SDP/NAC_DTM/APOLLO17/
- **MRO CTX DTMs** (NASA MRO CTX, processed by USGS Astrogeology, CC0). Mars: InSight, Spirit, Zhurong, Oxia Planum, the Mars pool and the Mars coverage grid, through https://stac.astrogeology.usgs.gov/api/search (collection mro_ctx_controlled_usgs_dtms). Jezero: Mars 2020 Terrain Relative Navigation CTX DTM mosaic, https://astrogeology.usgs.gov/search/map/mars_2020_terrain_relative_navigation_ctx_dtm_mosaic (doi 10.5066/P906QQT8)
- **NASA Planetary Fact Sheets** (NSSDC). Gravity, pressure, temperature range and day length: https://nssdc.gsfc.nasa.gov/planetary/factsheet/
- **NASA mission documents for slope limits.** Apollo LM: NASA TN D-6850, https://ntrs.nasa.gov/citations/19720018253. Lunar Roving Vehicle: NASA TR R-401, https://ntrs.nasa.gov/citations/19730008090. MER landing sites: https://marsoweb.nas.nasa.gov/landingsites/mer2003/doc/original.html. Perseverance: https://science.nasa.gov/mission/mars-2020-perseverance/rover-components/
- **Globe textures.** LROC colour map (NASA SVS 4720, https://svs.gsfc.nasa.gov/4720); Blue Marble 2002 (NASA Visible Earth 57752, https://visibleearth.nasa.gov/images/57752/blue-marble-land-surface-shallow-water-and-shaded-topography); Viking MDIM 2.1 mosaic (NASA / JPL / USGS, via Wikimedia Commons). No NASA logos are used.
- **NASA Artemis III candidate regions** (release RELEASE24-136, 28 Oct 2024; no coordinates given): https://www.nasa.gov/news-release/nasa-provides-update-on-artemis-iii-moon-landing-regions/. Region centres are proxies taken from the PGDA files.

## Other space agency and open data used

- **Copernicus DEM GLO-30** (ESA / DLR / Airbus), second Earth sensor for the sensor-noise test on dev regions, and the elevation of the Arctic part of the search pool (60 N to 84 N, where NASADEM does not exist). doi 10.5270/ESA-c5d3d65. Notice: (c) DLR e.V. 2010-2014 and (c) Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.
- **ESA WorldCover 2021 v200** (CC BY 4.0), to keep only bare-ground Earth windows. doi 10.5281/zenodo.7254221
- **Gale Crater stereo CTX DTMs** (figshare article 6584984, CC BY 4.0), the Gale elevation model. doi 10.6084/m9.figshare.6584984
- **Koppen-Geiger climate map, 1 km** (Beck et al. 2018, Scientific Data, CC BY 4.0), context for each twin. doi 10.1038/sdata.2018.214
- **Natural Earth 1:10m** admin-1 and populated places (public domain), place names and nearest town.
- **Microsoft Planetary Computer STAC API**, used only to search and sign data URLs.
- Full list with licences and DOIs: REFERENCES.md in the repository.

## Limitations

- **The validation failed both pre-registered tests, narrowly.** Numbers are in the table above. The measure is an operability filter, not a classifier of geological origin.
- **Mission % is a reference comparison, not a success probability.** The limits are published without a baseline length, while we measure slope at 100 m. IM-2 sits on 98% landable terrain at that scale and still tipped over: the hazard was smaller than the grid.
- **The Earth pool is rock ground only.** NASADEM covers 1,965 windows from 56 S to 60 N; Copernicus GLO-30 covers 765 windows from 60 N to 84 N. Windows with 20% or more ice are left out, and 1,335 excluded windows are listed with their reason. The NASADEM part is dominated by the Sahara, Arabia and Central Asia because that is where bare ground is.
- **Mars coverage is partial.** Only terrain with a CTX elevation model covering a full 8 km disk can be measured; that is 0.077 of random Mars points. HRSC and HiRISE were not used.
- **Earth cannot reproduce** reduced gravity, vacuum or thin atmosphere, cold extremes, day length or radiation. The dossier says so for every pair.
- **Light is closed-form.** It uses latitude and axial tilt only. A near-horizon check exists only for the 5 Moon sites with a LOLA 5 m elevation model, within the reach of that model; far mountains are not included. Mars sites and the other Moon sites have no horizon result.
- **Site centres:** several Mars centres come from secondary sources (the Jezero centre is not confirmed by NASA or JPL). The centre notes are in the data.
- **Known-analog "new" flags** rest on circle approximations of famous regions.
- **Licences:** NASADEM is released under the NASA open data policy, but the STAC label says "proprietary"; we cite it as NASA open data. PGDA and LROC pages carry no licence text; we cite their references.

## Use of AI

Code and analysis were written with AI assistance (Claude, Anthropic) under the team's direction and review. The web interface was built with a second AI coding assistant (Codex, OpenAI) from the team's written brief. The core idea, the decisions, the game-like "unlocked / to discover" atlas presentation and the mission-success framing came from the team, not from the AI. Scientific choices (thresholds, what counts as a failure, which results to publish) were set by the team before each run and written in STANDARDS.md. Every number in this text is generated from the facts ledger, not typed by hand; a check fails if a number does not resolve to exactly one ledger fact. No AI-generated images are used. Data products carry a `generated_with` field.
