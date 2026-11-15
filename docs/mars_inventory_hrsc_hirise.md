# Mars inventory part 2: HRSC and HiRISE elevation models (2026-11-13)

HRSC, two families (ESA/DLR/FU Berlin)
1. DTMRDR single-orbit DTMs (PDS volume mexhrs_2001, dataset MEX-M-HRSC-5-REFDR-DTM-V1.0): 1370 DT4 products (sphere), each with a DA4 aeroid twin.
2. Native per product from label MAP_SCALE: 50 m in 3 of 19 valid sampled products; 75 m (8), 100 m (6), 125 m (1), 225 m (1). So some pass native <= 50 m, most do not.
3. Footprints are long strips; all 19 valid sampled products cover the 8 km disk fully (coverage 1.0). Share of Mars at <= 50 m: about 17% by summed footprint area (sample estimate, overlaps not removed); Wilson 95% on the product rate 6-38%.
4. FU Berlin Level 3 MC-quadrangle DTM mosaics (16-bit int16, maps.planet.fu-berlin.de/level3): 65 tiles in 10 MC folders; 26 tiles at 50 m, 35 at 12.5 m (MC-19), 4 unreadable (MC-18; one HTTP 403). 50 m exactly meets L = 100 m >= 2 x native.
5. MC tiles: tile-box union = 41.7% of Mars; median valid-pixel share 0.70 (decimated read); 12 of 26 50 m tiles >= 0.90 valid. Rough valid area about 0.3 of Mars.
6. Access: PDS DT4 read by GDAL PDS driver, open 1.17 s, 200x200 window 1.10 s. FU Berlin tile_-002+000 (50 m): open 2.21 s, window 4.04 s. ESA PSA (archives.esac.esa.int) returned HTTP 401 to guest access; not used. hrscview.fu-berlin.de unreachable.
7. Licence: PDS product = public domain per NASA catalog record (found by search; PDS licence page not read). FU Berlin: unconfirmed on server; FU Berlin FAQ cites CC BY-SA 3.0 IGO for images where stated; credit ESA/DLR/FU-Berlin.
8. Not elevation: FU Berlin hrsc3-mos.tif (50 m, uint8) is an image mosaic; excluded.

HiRISE DTMs (~1 m)
9. DTMINDEX.TAB (uahirise/PDS INDEX): 39 DTM rows (290 ortho rows), native 1.00-2.02 m. The index is stale: the April 2026 release (7 DTMs) is not in it. True total unknown, above 39.
10. Seeded sample (seed 20261114, 20 of 39), polygon of the 4 index corners vs 8 km circle: none >= 0.90; median 0.685 (range 0.561-0.807). Bbox-only overstates (8 of 20 >= 0.90) and is not used. DTM widths 5.2-12.6 km.
11. Conclusion: a single HiRISE DTM cannot serve the 8 km / 100 m measure; a multi-DTM mosaic would need its own footprint check. Not recommended.

Recommendation for the "to discover" layer
12. Key it on 50 m DEM coverage per 8 km circle, not on region outlines: FU Berlin 50 m MC tiles (valid mask per circle) and 50 m DT4 products (label footprints). Ground covered only by 75-225 m HRSC DTMs or 200 m HRSC-MOLA is "out of reach" under the 100 m rule. Leave HiRISE out.

Doubts
- HiRISE and HRSC product counts are not complete: HiRISE index stale; PSA count unavailable (401).
- HRSC sample: 19 valid products, 3 at 50 m; the share is wide.
- MC int16 units and offset not verified (values about 9800-13500); check before use.
- Valid fractions are decimated (about 400 m) approximations.
- HiRISE coordinate convention (planetocentric/graphic) not stated in the index; HiRISE licence not verified.
- Earlier count of 2740 DT4 rows was a double count; 1370 is correct.
