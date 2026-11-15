# Mars data inventory (agent M)

Scope of this pass: item 1 (USGS Astrogeology DTMs), item 2 (Mars Trek and the human Exploration Zones list), item 5 (candidate sites). Items 3 (ESA HRSC, MC-30 mosaics) and 4 (HiRISE coverage) were handed to agent M2, which writes its own files. Facts already gathered for M2 are in section 6. Outputs: this file and `config/mars_coverage.json`. Nothing else was edited.

Rule used throughout: a usable Mars DEM has native resolution <= 50 m and covers >= 90% of the 4 km-radius disk around the centre. Coverage in this pass is **bbox-based** (footprint bbox, no nodata check) unless stated.

## 1. USGS Astrogeology STAC (`https://stac.astrogeology.usgs.gov/api/search`)

- Collections checked: 18 in `/api/collections`. Mars DTM collections: `mro_ctx_controlled_usgs_dtms`, `mro_hirise_socet_dtms` (and a `_test` copy, not analysed). No HRSC collection is listed.
- **CTX DTMs (`mro_ctx_controlled_usgs_dtms`)**: 44,628 products (numberMatched). Description: DTMs from CTX stereo at about 6 m/px, output 20 m/px, absolutely controlled to MOLA. STAC `gsd`: 40,117 items at 20 m; 4,511 items at other values up to 35.96 m. **All 44,628 are <= 50 m.**
  - 4,511 items have no asset whose key contains "dem" (the DEM asset key was not checked further). They are listed with `url: null`.
  - Licence: STAC property `CC0-1.0` (read on 2 sample items only).
  - Access: paginated GET (`limit=100`, `next` link). The `fields` filter is ignored by the server, so each page returns full items (about 0.5 MB). Full pull: 448 requests, 429 MB of metadata, 392 s. This is within the per-request rule but the aggregate is large; flagged.
- **Windowed read test (CTX T01_000893_1847_XN_04N191W__N09_065929_1853_XN_05N191W)**, rasterio over `/vsicurl/`, GeoTIFF on S3 (`astrogeo-ard`): open 0.74 s, 200 x 200 window read 0.84 s, total 1.59 s. 20 m/px, CRS equirectangular sphere (IAU 49900), nodata -32767, valid fraction 1.00. **Windowed reads work for CTX.** Other CTX products untested.
- **Footprint share**: the CTX bbox union covers **20.2%** of the sphere (area-weighted grid, 0.1 deg; upper bound, since bboxes are larger than the valid DEM and overlap). Monte Carlo over 5,000 seeded random centres (seed 20261114): **16.98%** (849/5000; Wilson 95%: 15.96% to 18.05%) have >= 90% of their 4 km disk inside a CTX bbox; 18.9% reach >= 50%.

## 2. NASA Mars Trek and the human Exploration Zones

- **Mars Trek WMTS**: the pattern `https://trek.nasa.gov/tiles/Mars/EQ/<layer>/1.0.0/WMTSCapabilities.xml` works for `Mars_MGS_MOLA_ClrShade_merge_global_463m` (HTTP 200, 7 KB). No Mars DEM layer identifier was found on the Trek portal (`/mars/`), the API documentation page (`/tiles/apidoc/trekAPI.html`, generic, no Mars products) or the `api.nasa.gov/mars-wmts/catalog` endpoint (404). Guessed layer names returned 404 and are not evidence. **Result: no Trek DEM layer enumerated; Trek contributes no product.**
- **NASA Exploration Zones page** (`nasa.gov/journeytomars/mars-exploration-zones/`): names no zone and gives no coordinates. It links a "Map of Proposed Exploration Zones", a signed map and "Status of Exploration Zone Imaging Requests" (PDF, not located).
- **2016 NASA slides** (Bussey and Hoffman, IEEE Aerospace 2016, NTRS 20160002370): 47 EZs proposed by 45 individuals or teams at the First EZ Workshop (Houston, Oct 2015). Map at `exploration-zone-map-v10.pdf` on nasa.gov: **HTTP 404** when tested. Slides give a 100 km radius per EZ and latitude limits of +/- 50 deg.
- **Official list with names: Bussey and Hoffman 2016 (NTRS 20160001040), Appendix D, pp. 19-20.** 47 rows: name, abstract number and **latitude only**. The "Longitude" column holds small integers (1 to 44, equal for repeated sites, e.g. Gale = 3), not longitudes. **Longitudes are therefore not in the official list and are left null; no coordinates were invented.** Duplicates: Ausonia Cavus (abstract 1045) appears twice; Gale Crater appears three times (abstracts 1020, 1040, 1022, different authors).
- The 2015 HLS2 overview slides (NASA, 27 Oct 2015, `hls2-overview-v3tagged.pdf`): read in full; they name the study and the EZ concept but give no sites and no coordinates.

## 3. Candidate sites (item 5)

55 entries in `config/mars_coverage.json` -> `candidate_sites`:

| group | n | with lon/lat | fine DEM (bbox) |
|---|---|---|---|
| Mars 2020 finalists (NE Syrtis, Columbia Hills, Jezero Caltech centre) | 3 | 3 | 3 of 3 |
| Mars 2020 Midway | 1 | 0 (no coordinates found) | null |
| MSL finalists (Mawrth Vallis; Holden/Eberswalde pairs A and B, unassigned) | 3 | 3 | 3 of 3 |
| ExoMars (Oxia Planum favoured ellipse) | 1 | 1 | 1 of 1 |
| Human EZs 2015 (Appendix D) | 47 | 0 (latitude only) | null |

- The 7 entries with coordinates all have CTX footprints covering >= 90% of the 4 km disk (bbox-based). Matching DTM ids are in `dem_product_id`. For Oxia, the DTM is N06_064538, which matches the earlier inventory result.
- **Jezero**: Caltech gives 18.4386 N, 77.5031 E. `config/sites.json` uses 18.4447, 77.4508 (not confirmed by NASA). The two centres are about 3 km apart. Flagged, not changed.
- **Holden and Eberswalde**: the DLR page gives two coordinate pairs without saying which is which. Both pairs are kept unassigned.
- **Mars 2020 final four**: Jezero, NE Syrtis, Columbia Hills and Midway were found in a Caltech paper and an EPSC 2018 abstract (secondary; not NASA primary). Mawrth Vallis was on the earlier eight-site list.
- **Human EZs**: centres need longitudes from the 2016 map (not accessible here) or from the Appendix D source workshop abstracts. Until then `has_fine_dem` cannot be checked.
- **Mars Sample Return**: no candidate landing list was searched in this pass.

## 4. Doubts and deviations

- All coverage is bbox-based. A bbox can include nodata (edges, masked areas). Confirm each candidate with a windowed read before use.
- The 4,511 CTX items without a DEM asset: the asset key was not checked. They may have a different DEM key, or none.
- The CTX licence was read on 2 sample items, not every item.
- `config/mars_coverage.json` is 20.6 MB (44,628 products). It is valid JSON but large for git; consider splitting or compressing. Products for HiRISE and HRSC are not included (agent M2).
- The Appendix D Longitude column reading (sequence numbers, not longitudes) is my interpretation of the extracted text; the PDF was not viewed as an image.
- No Bash command was refused by the permission system. One stray background python process of mine (the first, superseded CTX pull) was stopped by PID; it had been left running after its shell was stopped.

## 5. Recommendations

- (a) "to discover" layer: derive it from the CTX footprint set (bbox union covers about 20% of the sphere; about 17% of centres reach 90% coverage by bbox). The layer needs HiRISE and HRSC added (M2) and a windowed nodata check per candidate.
- (b) additional sites to unlock next, once a DEM is confirmed by windowed read: Columbia Hills (Mars 2020 finalist, near the Spirit centre); NE Syrtis (Mars 2020 finalist); Mawrth Vallis (MSL finalist and ExoMars candidate, DTM P19_008469, bbox-based 100%); Holden/Eberswalde pair A (DTM P19_008483); Holden/Eberswalde pair B (DTM P17_007481). Each needs its centre confirmed by a primary NASA or ESA source first.

## 6. Notes for M2 (items 3 and 4)

- **HiRISE (USGS STAC `mro_hirise_socet_dtms`)**: 1,262 DTMs. STAC gsd 0.774 to 2.848 m (median 1.034). Footprint bbox median 6.7 km wide x 13.5 km high (min 1.3 x 1.6 km, max 24.6 x 77.6 km). 168 of 1,262 (13.3%) have both bbox sides >= 8 km. Seeded sample of 20 footprints (seed 20261114; bbox-based, best interior centre on a 9 x 9 grid): **14 of 20 (70%)** can reach >= 0.90 of an 8 km disk. The full-set count was not run.
- **HiRISE asset**: the DTM key is `dtm` (not `dem`). The first pull used the wrong key, so `dem_href` is None there; the corrected pull is `scratchpad/hirise_items2.json` (1,262 items with `dem_href`).
- **HiRISE windowed read FAILED to fetch**: `.../controlled/dtm/DTEPD_088070_2535_088413_2535_A01.tif` (the STAC `dtm` href) returned HTTP 404 through rasterio. Three other item hrefs returned 404 or a connection error (curl 000). Re-test before use; the bucket may use a different key.
- **HRSC**: DLR regional page `hrscteam.dlr.de/public/data/regionaldtms.php` lists 5 MC-30 quadrangles (MC11E, MC13E, MC20E, MC11W, MC20W), 4 sub-tiles each (20 tiles). DTM names da5 (areoid) and dt5 (sphere); GeoTIFF; no grid spacing and no licence stated; PDS/PSA release "in preparation". The DLR MSL page says the HRSC DTMs have 50 m grid spacing. The ESA PSA HRSC DTM directory (`archives.esac.esa.int/psa/ftp/pds3_extra_datasets/MARS-EXPRESS/HRSC/MEX-M-HRSC-5-REFDR-DTM-V1.0/`) returned **HTTP 401** to this client (not worked around). ODE REST queries for HRSC DTMs returned a query error (URL not fixed).
- **HRSC DLR MSL page** (`europlanet.dlr.de/Mars/mars_MSL.html`): gives Mawrth Vallis, Holden/Eberswalde pairs and Gale with DTMs; used in section 3.
