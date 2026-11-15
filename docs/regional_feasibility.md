# Regional scale feasibility (STANDARDS 10.10, EXPERIMENTAL)

Sample-only test of the 400 m / 16 km regional scale. Not validated, not comparable with the 100 m scale.
Config: `config/measure_regional.json` (version regional-0.1, sigma null). Pipeline: `pipelines/regional_sample.py`.
Output: `data/derived/regional/sample.json` (provenance block per STANDARDS 7; 81 inputs), `parts/mars.json`,
`parts/earth.json`, clips in `mars_clips/` and `earth_clips/`.

## Data checks
- Mars source: HRSC-MOLA blend 200 m DEM. Not tiled (one row per block, uncompressed strips), overviews 2 to 510,
  int16, nodata -32768, CRS = geographic Mars 2000 sphere (R 3396190, matches IAU 2015). 53347 x 106694 px, about 11.4 GB.
- Native pixel 199.99999 m, so 2 x native = 399.99998 m and L = 400 m passes `L >= 2 x native` (margin 0.00002 m; fragile).
- Earth source: NASADEM via `fetch.stac_clip` (asset `elevation`), native about 30.9 m, passes.
- Finding: `load_local_grid` calls `src.read(1)` on the whole file, which would be about 91 GB as float64 for Mars.
  So Mars needs a remote window clip first (done in the pipeline, not in grid.py). Any production run must do the same.
- Mars windows: 40 centres, 40 draws, 0 redraws (no antimeridian crossing). Earth: 40 seeded pool windows (of 2000).
- Coverage min 1.0 on both bodies. Status: 80 of 80 ok, 0 skipped, 0 errors.

## Per-window timing (sequential, one worker)
- Mars: mean 10.6 s, median 9.1 s, min 6.7 s, max 32.1 s (fetch 10.5 s mean; measure 0.09 s). Run wall 427 s.
  Times rose during the run (windows 22 to 24 were 14 to 32 s), so the remote server is the variable.
- Earth: mean 4.8 s, median 4.9 s, min 3.2 s, max 8.8 s (fetch 4.6 s; measure 0.12 s). Run wall 190 s.
- Clip size: Mars 0.04 MB mean (0.01 to 0.07 MB); Earth 1.24 MB mean (0.74 to 2.25 MB).

## Feature ranges (min / median / max over 40 windows per body)
| feature | Mars | Earth |
|---|---|---|
| slope_p95_deg | 0.41 / 5.37 / 30.96 | 0.17 / 1.87 / 17.63 |
| hi | 0.19 / 0.47 / 0.79 | 0.28 / 0.46 / 0.61 |
| coherence | 0.02 / 0.18 / 0.72 | 0.01 / 0.24 / 0.96 |
| hurst | 0.47 / 0.81 / 0.98 | 0.17 / 0.64 / 0.81 |
| ridge_pct | 0.00 / 4.36 / 44.88 | 0.00 / 0.09 / 19.22 |
| valley_pct | 0.00 / 3.72 / 38.67 | 0.00 / 0.00 / 22.22 |

Nulls: none in any feature of any window, so no null reasons to report.

## Extrapolation (8 workers, ideal scaling; measured mean per window)
- (a) 3000 Mars windows: wall 1.1 h ideal, 2.2 h at half parallel efficiency. Clips 0.12 GB. Remote transfer
  about 109 GB (estimate: about 171 rows x 213 KB per window, strips read whole, about 36 MB per window; not measured).
- (b) 2000 Earth windows: wall 0.33 h ideal, 0.66 h at half efficiency. Clips 2.5 GB (kept). Grid-only (81 x 81
  float32) would be 0.05 GB.

## Test
`tests/test_regional.py`: 1 passed (plane 10 deg at 400 m: slope_p95 = 10, coherence = 1, hurst = 1).

## Risks
- Mars transfer is the main cost: about 109 GB for 3000 windows, and the 8-worker run may be throttled by the server
  (the observed per-window time rose 2 to 3x during the sample). Test the parallel throughput before scaling.
- Fragile `L >= 2 x native` pass on Mars (margin 2e-5 m). Any change of grid or source resolution re-opens it.
- The 400 m scale has no validation of its own; features are not comparable with the 100 m scale (STANDARDS 10.10).
- Earth sigma for the regional scale is not calibrated (sigma null), so no distances can be computed yet.
- The sample has 40 + 40 windows only; ranges above describe the sample, not the globe.
