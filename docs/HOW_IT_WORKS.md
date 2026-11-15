# How the engine works

Common Ground: measured Earth analogs for Mars and Moon sites.
Read-only review of the files on disk, 2026-11-15, about 15:35 local time. No pipeline was re-run and no test was executed. Two read-only checks were run: `tools/check_ledger.py` and `tools/check_site_data.py`.

Every figure names its source file in parentheses. `[not found]` means no file holds the figure.

## 0. The chain at a glance

```
1 Sources -> 2 Windows -> 3 Measure (+3b mission %) -> 4 Earth pool -> 5 Sigma
  -> 6 Nearest neighbours (+6b refined search) -> 7 Earth gap (+7b context)
  -> 8 Light and rehearsal -> 9 Facts ledger -> 10 Site exports
```

One direction only. Each step reads only the persisted output of the steps before it (STANDARDS section 1 and 10.14). Nothing reads the ledger back, and no stage rewrites another stage's output.

Frozen by design: the six features and the sigma values in `config/measure.json` (v1.3), the tie thresholds in `data/derived/validation/noise_v1.3.json`, and the validation results in `data/derived/validation/`.

Two things changed the pool after the first design. The Earth pool grew from 2,000 NASADEM windows to 2,730 places by adding Arctic windows (Copernicus, 60 N to 84 N), and it is now filtered by ice and bare-ground rules. Both are in section 4.

---

## 1. Sources

**In:** 54 source records (`config/sources.json`). Products the chain uses:

| Product | Agency / provider | Resolution | Used for |
|---|---|---|---|
| NASADEM HGT v001 (`nasadem`) | NASA / JPL / USGS, via Microsoft Planetary Computer | 30 m | Earth pool 56 S to 60 N, refined search, validation regions (`config/sources.json`) |
| Copernicus DEM GLO-30 (`cop_dem_glo30`) | ESA / DLR / Airbus, via Microsoft Planetary Computer | 30 m | Earth pool 60 N to 84 N (Arctic), sensor check (`config/sources.json`) |
| ESA WorldCover 2021 v200 (`esa_worldcover`) | ESA WorldCover consortium, via Planetary Computer | 10 m | Bare-ground and ice shares of each window (`config/sources.json`) |
| USGS controlled CTX DTMs (`usgs_ctx_dtm_*`, `jezero_ctx_trn_dtm_20m`, `gale_ctx_dtm_*`) | USGS Astrogeology / NASA MRO CTX; Gale from figshare | 20.00 to 20.73 m (per file) | Mars windows and Mars targets (`config/sources.json`) |
| LOLA 5 m site DEMs (`lola_5m_*_surf`) | NASA GSFC PGDA | 5 m | Moon target DEMs (`config/sources.json`) |
| LOLA 20 m polar LDEM 80 to 90 S (`lola_20m_polar_ldem`) | NASA GSFC PGDA | 20 m | Moon coverage class 1 only (`config/sources.json`, `pipelines/coverage_grids.py`) |
| LROC NAC DTM Apollo 17 (`lroc_nac_dtm_apollo17`) | NASA / LROC (ASU) | 5 m | Apollo 17 target (`config/sources.json`) |
| HRSC-MOLA blend (`hrsc_mola_blend_200m`) | USGS / ESA / NASA | 200 m | Regional experiment only, outside the chain (`config/sources.json`, `data/derived/regional/`) |
| Koppen-Geiger 1 km (`koppen_geiger_1km_present`) | Beck et al. (CC BY 4.0) | 1 km | Climate class per twin: context, and the cold line of the rehearsal (`config/sources.json`) |
| Natural Earth 1:10m admin-1 and populated places | Natural Earth (public domain) | vector | Place names and nearest town per twin (`config/sources.json`) |
| NSSDC Planetary Fact Sheets (`nasa_nssdc_*_factsheet`) | NASA NSSDC | n/a | Gravity, pressure, temperature range, day length (`config/bodies.json`) |

Listed in `config/sources.json` but not read by any pipeline, `tools` or `src` script (text search, 2026-11-15): `modis_mod11a2_061`, `copernicus_glo30_s3_example`.

Raw inputs sit in `data/raw/` (git-ignored). Each derived JSON records the SHA-256 of its inputs in its provenance block (STANDARDS section 7). `[not found]`: total size of `data/raw/`.

**Scripts:** `pipelines/fetch_data.py` (planetary sites, validation regions; logic in `src/analog/io/fetch.py`), `pipelines/build_pool_index.py` (WorldCover tiles, NASADEM Earth windows), `pipelines/build_mars_pool.py` (CTX DTM windows for Mars), `pipelines/arctic_probe.py` (Copernicus Arctic clips; first written as an experiment).

---

## 2. Windows

**In:** raw DEM files from step 1.

**Does:** every place is a disc of radius R = 4,000 m (8 km across), resampled to a 100 m grid of 81 by 81 pixels, in an azimuthal equidistant projection centred on the site (STANDARDS section 3; `config/measure.json` grid: L_m 100, R_m 4000). A window is valid only if L >= 2 x native resolution and coverage >= 0.9. Otherwise it is skipped and logged, never patched (`config/measure.json` grid, STANDARDS section 3).

**Out:** one record per window in `data/derived/measure/*.json`.

**Counts** (`data/derived/measure/`, 6,126 records; `kind` and `status` read from each record):

| Kind | Windows | ok | Not ok |
|---|---|---|---|
| Earth pool (NASADEM and Arctic) | 4,065 | 2,730 | 1,335 excluded (step 4) |
| Mars pool (CTX DTM windows) | 2,000 | 1,838 | 162 skipped, all for coverage < 0.9 |
| Targets (6 Mars, 10 Moon) | 16 | 16 | 0 |
| Dev regions (15 regions x 2 sensors) | 30 | 30 | 0 |
| Holdout regions (v1.3) | 15 | 15 | 0 |

Mars windows: 4.5 km half-width squares read from the USGS CTX DTM stack (STANDARDS 10.13). Attempts in `data/raw/mars/pool/attempts.jsonl`: 25,914 in total. Outcomes: 22,583 no DTM, 1,251 low valid fraction, 80 read errors, 2,000 accepted (2,000 / 25,914 = 7.7%). The accepted list is `data/raw/mars/pool/index.json` (2,000 rows).

**Script:** `pipelines/build_measure.py` (pool, targets, regions, holdout); `pipelines/mars_atlas.py` (Mars windows); `pipelines/_common.py` `measure_raw`, the one place where a raw DEM becomes a grid and a feature vector.

---

## 3. Measure (six features)

**In:** the 100 m grid of each window (step 2).

**Does:** six terrain features per window (STANDARDS section 4; definitions in `config/measure.json`):

- `slope_p95_deg`: 95th percentile of slope (degrees).
- `hi`: robust hypsometric integral, clip((mean - P5) / (P95 - P5), 0, 1).
- `hurst`: roughness scaling, least-squares slope of log nu(k) against log k, lags 1, 2, 4, 8 px (100 to 800 m).
- `coherence`: grain-direction anisotropy from the gradient structure tensor.
- `ridge_pct`, `valley_pct`: share of pixels with TPI above +t or below -t; TPI radius 5 px (500 m), t = tan(1 deg) x 500 m.

**In the distance (v1.3):** `slope_p95_deg`, `hi`, `hurst`, weight 1 each. `coherence`, `ridge_pct` and `valley_pct` have weight 0 and are shown as context only (`config/measure.json`). Reason for the exclusion: `ridge_pct` and `valley_pct` correlate with `slope_p95_deg` at 0.955 and 0.945 (`config/measure.json`, `docs/CHANGELOG.md`); `coherence` alone had AUC 0.50 on dev classes (`config/measure.json`).

**Out:** the same 6,126 records of step 2.

**Mission-proven terrain % (step 3b):** `pipelines/mission_pct.py` gives the share of valid disk pixels whose slope is at or below each mission limit, landing and driving (STANDARDS 10.3). Limits from `config/missions.json`:

- Moon landing 12 deg (Apollo Lunar Module, NASA TN D-6850). Moon driving 25 deg (Lunar Roving Vehicle, NASA TR R-401).
- Mars landing 15 deg (MER requirement). Mars driving 30 deg (Perseverance tilt planning). **Caveat:** neither Mars limit has a stated 100 m baseline; `config/missions.json` marks both as "DECISION FOR THE LEAD", and `data/derived/atlas/mars_run.json` repeats it. Mars mission % is a comparison, not a compliance test.

Control: Jezero landing 99.54% and Gale landing 99.98% on Mars (`data/derived/mission/jezero.json`, `data/derived/mission/gale.json`). Both are above the 50% gate. Apollo 17 (Moon) landing 91.02% (`data/derived/mission/run_log.jsonl`). Output: 379 files in `data/derived/mission/`.

**Script:** `pipelines/build_measure.py`, `src/analog/core/metrics.py`, `src/analog/core/mission.py`, `pipelines/mission_pct.py`.

---

## 4. Earth pool

**In:**
- NASADEM, 56 S to 60 N: 2,000 windows, fixed seed (`config/earth_pool_rules.json` band `nasadem`; `pipelines/build_pool_index.py`).
- Copernicus GLO-30, 60 N to 84 N: 2,065 Arctic candidates (`config/earth_pool_rules.json` band `arctic`; `data/derived/pool_rules/summary.json`, `arctic.total` 2,065).

**Does:** keeps a window only if:
- bare ground (WorldCover classes 60, 70, 100) covers at least 80% of the full 4 km disk, and
- ice (class 70) covers less than 20% of that disk (`config/earth_pool_rules.json`).

Windows within 25 km of a known analog are kept for the sigma pool but are excluded from the rankings (STANDARDS 10.2; `config/regions.json` role `known_analog`).

**Out:**
- 4,065 windows in total, of which 2,730 are accepted (NASADEM 1,965, Arctic 765).
- 1,335 excluded: 1,293 for ice >= 20%, 36 for bare ground < 80%, 6 with no clip (`data/derived/pool_rules/excluded.json`, `data/derived/pool_rules/summary.json`).
- Near a known analog: 2 flagged, both Arctic; 0 NASADEM (`data/derived/pool_rules/summary.json`).
- Index: `data/raw/earth/pool/index.json` (4,065 rows, `excluded` field per row). Shares: `data/derived/pool_rules/shares.json`.

**Scripts:** `pipelines/build_pool_index.py` (NASADEM windows), `pipelines/arctic_probe.py` (Arctic clips), `pipelines/pool_rules.py` (`shares`, then `apply`: writes the Arctic rows and the exclusion flags; idempotent).

**Discrepancy:** `config/earth_pool_rules.json` names `pipelines/pool_add_arctic.py` as the builder of the Arctic rows. That file does not exist. The code that does it is `pipelines/pool_rules.py` (its docstring and `tools/build_ledger.py` `produced_by`).

---

## 5. Sigma calibration

**In:** the features of the Earth pool (step 3, NASADEM windows).

**Does:** sigma_k = 1.4826 x MAD_k over the Earth pool (STANDARDS 10.1). Label-free, computed once, never overwritten without `--force`.

**Out** (`config/measure.json`):

| Feature | sigma |
|---|---|
| `slope_p95_deg` | 3.0410 deg |
| `hi` | 0.06401 |
| `coherence` | 0.15692 |
| `hurst` | 0.20019 |
| `ridge_pct` | 1.82397 |
| `valley_pct` | 0.61439 |

Run: 2026-11-14 02:53:43 UTC, on 2,000 NASADEM windows (`hi` on 1,994, because 6 flat windows are null). Source: `docs/CHANGELOG.md` (sigma section) and `data/derived/measure/run_log.jsonl`.

**Caveat:** sigma was calibrated before the ice and bare-ground rule and before the Arctic rows. Those 2,000 windows include 34 ice-dominated windows and 1 bare-excluded window (`data/derived/pool_rules/summary.json`, `summary.nasadem`). The design freezes sigma, so it was not recomputed (`docs/ARCTIC_INTEGRATION.md`).

**Script:** `pipelines/calibrate_sigma.py`, `src/analog/core/stats.py` (`robust_sigma`).

---

## 6. Nearest neighbours

**In:** the three in-distance features of every window, standardised by sigma (step 5).

**Does:** z_k = x_k / sigma_k, then D(a, b) = ||z_a - z_b||_2 / sqrt(K), K = 3 (`data/derived/neighbors/run.json`, `distance`). Exact k = 10 nearest twins with `scipy.spatial.cKDTree` (`query(k)`). Ties come from `query_ball_point` with the relief-class threshold (`src/analog/core/neighbors.py`).

**Tie thresholds, in D units** (`data/derived/neighbors/run.json`, `thresholds`; source `data/derived/validation/noise_v1.3.json`):
- Rugged (slope_p95 >= 3 deg): 0.4150.
- Flat (slope_p95 < 3 deg): 1.1017.

**Queries:** 1,854 = 16 targets + 1,838 Mars cells. Pool used for targets: 2,722 windows = 2,730 minus 6 with null D minus 2 near a known analog (`run.json`, `pool.n_tree_targets`).

**Exactness** (`run.json`, `exactness_sample`): 200 seeded queries (16 targets, 84 Mars cells, 100 pool windows) match brute force. Index mismatches 0. Max |D difference| 8.9e-16, tolerance 1e-12. Tie-set mismatches 0. All 1,854 queries match brute force (`all_queries_match_brute_force` true). The 16 target rankings match the ranking JSON files row by row (`rankings_check`). Timing: tree 0.63 s, brute force 1.14 s for all queries (`timing_s`).

**Out:**
- `data/derived/neighbors/earth_windows.parquet` (2,730 rows), `targets.parquet` (16), `mars_cells.parquet` (1,838), and `run.json`.
- Rankings: `data/derived/ranking/*.json`, 16 files x 10 twins = 160 pairs (`data/derived/ranking/run_log.jsonl`, "rankings_written 16").

**Scripts:** `pipelines/neighbors.py`, `pipelines/search.py` (rankings).

### 6b. Refined search (targets only)

`pipelines/refine_search.py` re-measures each target's top-10 twins on a 5 x 5 grid of 2 km steps (offsets -4 to +4 km), using one NASADEM clip of half-width 8.5 km per candidate. It keeps the lowest-D offset (STANDARDS 10.13).

- Candidates: 160 (`data/derived/refine/*.json`).
- Marked `refine_skipped`: 88, because NASADEM does not exist above 60 N.
- Refined: 72.
- **Not reconciled:** `data/derived/refine/run_log.jsonl` reports `candidates_clipped: 67`. The count of 72 refined in the candidate files does not match it. `[not found]`: the cause of the difference.

---

## 7. Earth gap

**In:** Mars cells and targets with their nearest twin distance, D_nearest (step 6).

**Does:** gap = D_nearest > tie threshold of the subject's relief class. A gap means no Earth place is indistinguishable from the Mars or Moon place within sensor noise (STANDARDS 10.14, `src/analog/core/neighbors.py`).

**Out** (`run.json`, `data/derived/neighbors/*.parquet`, and `data/derived/ledger` via `tools/build_ledger.py`):

| Subject | All Earth bands | NASADEM only (56 S to 60 N) |
|---|---|---|
| Mars cells | 84 of 1,838 = 4.57% (Wilson 95%: 3.71 to 5.62) | 215 of 1,838 = 11.70% (Wilson 95%: 10.31 to 13.25) |
| Targets | 1 of 16 (`de_gerlache_rim_2`, D 0.4223 vs 0.4150) | 3 of 16 (`nobile_rim_1`, `de_gerlache_rim_2`, `mons_mouton_plateau`) |

- All 84 Mars gap cells are rugged (84 of 1,461 rugged; 0 of 377 flat) (`run.json`, `mars_cells.by_relief_class`).
- The Arctic windows close two of the three NASADEM-only gap targets: `nobile_rim_1` (nearest twin `pool__pool_02972`) and `mons_mouton_plateau` (nearest twin `pool__pool_03196`) (`data/derived/neighbors/targets.parquet`).
- Mars rehearsable share (at least one twin within noise): 95.43% with all bands; 88.30% with NASADEM only (`site/data/facts.json`).
- Most grazing sunlight any Earth place gets: 18.64% (`site/data/facts.json`, `earth_low_sun_max_pct`; ledger view `earth_grazing_max_pct`).

**Scripts:** `pipelines/neighbors.py` (gap), `pipelines/export_query.py` (`site/data/query`).

### 7b. Earth context per twin (not scored)

`pipelines/earth_context.py` adds, per twin: Koppen class, window mean elevation, nearest town (Natural Earth populated places), and place name (admin-1 and country). Output: `data/derived/context/earth_context.json`, 2,760 entries. Coverage per `data/derived/neighbors/run.json` (`earth_context`): 2,600 of 2,730 windows have an entry, and 2,565 have complete context. The reason the 2,760 entries do not match 2,730 is `[not found]`.

---

## 8. Light and rehearsal plan

### 8a. Light (no relief)

**In:** `config/light.json`. Obliquity: Earth 23.44 deg and Mars 25.19 deg (NSSDC, to orbit plane); Moon 1.54 deg to the ecliptic (Cassini's second law). The NSSDC value of 6.68 deg is not used, because it is the tilt to the lunar orbit around Earth (`config/light.json` `note`).

**Does:** circular orbit, Sun as a point, 72 year fractions x 144 hour angles (`light.json` `method_note`). sin(e) = sin(phi) sin(dec) + cos(phi) cos(dec) cos(H). Closed forms give noon maximum and minimum elevation. Sampling gives `sun_time_pct` (share with e > 0) and `grazing_pct` (share with 0 < e < 10 deg). Local horizon for Moon targets with a LOLA DEM, 36 azimuths (`local_horizon`).

**Out:** `data/derived/light/light.json`, with 16 targets and 4,065 Earth windows (`light.json`, `targets` and `earth_windows`). Copy in `site/data/light.json`. Local horizon available for 5 Moon targets (`tools/build_ledger.py` view `moon_horizon_targets`).

**Script:** `pipelines/light.py`, `src/analog/core/light.py`. Note: the docstring of `pipelines/light.py` still says "the 2000 Earth windows"; the file holds 4,065.

### 8b. Rehearsal plan (one file per target-twin pair)

**In:** the pair cards in `data/derived/cards/`, `data/derived/light/light.json`, `config/rehearsal_rules.json`, `config/bodies.json`.

**Does:** eight lines per pair: landing, driving, cold, low_sun, gravity, pressure, temperature, day_length.
- Landing and driving: difference in percentage points between target and twin. Yes if <= 10, partial if <= 25, else no. Limits from the card (`config/rehearsal_rules.json`).
- Cold: twin in one of 10 cold Koppen classes gives partial at best. Temperature range is always shown.
- Low sun: yes if analog >= target - 10 points, partial if analog >= target / 2, else no.
- Gravity, pressure, temperature and day length: always "cannot", status no, from `config/bodies.json`.

**Out, current run** (`site/data/rehearsal/`, 160 files, equal to `data/derived/rehearsal/` for the current ranking; `data/derived/rehearsal/run_log.jsonl` "pairs 160"):

| Line | Status counts over 160 pairs |
|---|---|
| landing | yes 115, partial 11, no 34 |
| driving | yes 160 |
| cold | partial 125, no 35 |
| low_sun | yes 70, no 90 |
| gravity, pressure, temperature, day_length | no 160 each (cannot group) |

**Stale files, needs a decision:** `data/derived/rehearsal/` holds 248 pair files. The 88 extra files are not in the current ranking and come from earlier runs. `tools/build_ledger.py` reads the whole folder, so the ledger counts 248 pairs (view `rehearsal_pairs`) and its `rehearsal_*` views are computed over the 248 files. The public `site/data/facts.json` does not use any rehearsal figure, so the site figures are not affected. The same applies to `data/derived/cards/`: 408 files, of which 160 are current (`site/data/cards/`).

**Script:** `pipelines/rehearsal.py`. Tests: `tests/test_light.py` (11 functions), `tests/test_rehearsal.py` (26).

---

## 9. Facts ledger

**In:** persisted outputs only (step 2 to 8). No value typed by hand (STANDARDS 10.14).

**Does:** `tools/build_ledger.py` writes one row per fact, with footprint, kind, level, source and producer.

**Out:**
- `data/derived/facts/facts.duckdb`: table `facts`, 120,290 rows, 19 columns, plus 71 named views (`duckdb_views`).
- `data/derived/facts/facts.parquet`: same table, 1,170,560 bytes.

Row mix (`facts`):
- By subject: earth_window 75,765; mars_cell 36,922; pair 6,696; target 468; region 336; validation 65; body 34; mission_limit 4.
- By kind: derived 101,109; published 14,567; measured 4,614.
- By footprint: local 85,645; point 23,412; regional 7,439; global 3,794.
- Distinct earth_window ids: 4,225 (= 4,065 pool windows + 160 refined candidates). Distinct pair ids: 248 (see the stale-file note in 8b).

**Rules** (`tools/check_ledger.py`, run 2026-11-15 about 15:34, read-only):

| Rule | What it checks | Offending rows |
|---|---|---|
| R1 | Mission % with a null or different baseline is tagged `reference`, never `compliance` | 0 (OK) |
| R2 | A point footprint is never on a region subject | 0 (OK) |
| R3 | Every fact has a `source_id` or `produced_by` | 0 (OK) |
| R4 | No two facts share (subject, property, scale) with different values | 0 (OK) |
| R5 | Every `{{fact:...}}` and `{{agg:...}}` placeholder resolves to exactly one fact or view | 0 (OK) |
| R6 | Feature facts come from records with the current `measure_key` | 0 (OK) |

STANDARDS 10.14 lists R1 to R5. The code also runs R6 (`tools/check_ledger.py` docstring); this is a stricter rule than the standard.

**Tests:** `tests/test_check_ledger.py` (13 functions), `tests/test_render_facts.py` (5).

---

## 10. Site exports

**In:** the ledger and the persisted outputs. The site reads only `site/data/` (README "Layout", STANDARDS section 1).

**Out, by exporter** (counts from the files on disk, 2026-11-15 about 15:34):

| Exporter | Writes | Counts |
|---|---|---|
| `pipelines/export_viz.py` | `site/data/targets.json`, `rankings/`, `cards/`, `terrain/`, `bodies.json`, `missions.json`, `validation.json`, `viz.json` | 16 targets, 16 rankings (160 entries), 160 cards, 167 terrain folders (30 m grid, n = 269) |
| `pipelines/mars_atlas.py` | `site/data/atlas/mars_cells.json` | 1,838 cells, 3 twins each (`data/derived/atlas/mars_run.json`) |
| `pipelines/discoveries.py` | `site/data/discoveries.json` | 1,813 unique windows; 1,786 places (1,736 new, 50 known); 22 known regions (`data/derived/context/run_log.jsonl`) |
| `pipelines/coverage_grids.py` | `site/data/coverage/{mars,moon,earth}.json` | 1 degree grid, 64,800 cells each. Mars: 1,621 unlocked, 6,988 to discover. Moon: 10 unlocked, 3,591 to discover. Earth: 2,057 unlocked, 997 to discover (`grid` counts) |
| `pipelines/light.py` | `site/data/light.json` | 16 targets, 4,065 windows |
| `pipelines/rehearsal.py` | `site/data/rehearsal/` | 160 pair files |
| `pipelines/export_query.py` | `site/data/query/` | Columnar binary tables for the browser |
| `pipelines/export_ties.py` | `site/data/ties.json` | Ties per target (`ties` rows must match the rankings) |
| `pipelines/export_sources.py` | `site/data/sources.json` | Source labels for the site |
| `tools/export_site_facts.py` | `site/data/facts.json`, `site/data/explain.json` | 26 public figures in `facts.json`, each named after its ledger view |
| `tools/export_tilt.py` | `site/data/tilt.json` | Overall tilt and downhill direction per terrain |
| `tools/export_arctic.py` | `site/data/arctic.json` | Experiment (probe stage) |

Public figures (`site/data/facts.json`) include: 16 sites (6 Mars, 10 Moon); 2,730 Earth places (1,965 NASADEM, 765 Arctic); 1,335 excluded; 1,838 Mars places; Mars gap 84 (4.6%, Wilson 3.7 to 5.6%); NASADEM-only Mars gap 215 (11.7%); Moon gap 1 site (all bands) and 3 (NASADEM); Earth maximum grazing 18.6%; validation AUC 0.6948.

**Check:** `tools/check_site_data.py`, run 2026-11-15 about 15:34 (read-only). Result: checked 16 targets, 16 rankings, 160 cards, 167 terrain folders. Orphans 0. RESULT OK. Coverage, atlas and discoveries are not covered by this check; `tests/test_export_query.py`, `tests/test_export_ties.py`, `tests/test_export_sources.py`, `tests/test_export_site_facts.py`, `tests/test_coverage_grids.py` and `tests/test_discoveries.py` cover them.

**Scripts:** the table above.

---

## 11. Validation

The v1.2 result is kept as it came out (`data/derived/validation/v1.2.json`). v1.3 is a single blind run on 15 new regions (`data/derived/validation/v1.3.json`). Thresholds were written before each run (`config/measure.json` `validation`). The values below are the exact numbers in the files; the README rounds them.

| Gate | Pass rule | v1.2 (15 dev regions, 4 features) | v1.3 (15 new holdout regions, 3 features) |
|---|---|---|---|
| V0 feature redundancy | max abs Spearman <= 0.80 | pass (max 0.6225) | `[not found]` in `v1.3.json` |
| V1 sensor noise | report median and p95 | median 0.1407, p95 1.2021 (n = 15) | rugged (n = 13) p95 0.4150; flat (n = 2) p95 1.1017 (`noise_v1.3.json`) |
| V2 AUC | >= 0.70 | **0.6926, fail** | **0.6948, fail** (short by 0.0052) |
| V2 AUC 95% CI lower bound | > 0.5 | 0.4419, fail | 0.5058, pass |
| V2 permutation p | < 0.05 | 0.0059, pass | 0.0068, pass |
| Nearest-region class | v1.2: >= 4 of 5; v1.3: >= 7 of 15 | **2 of 5, fail** (one-sided binomial p 0.263) | **6 of 15, fail** (binomial p 0.061; 7 of 15 would give p 0.018) |
| Mission control (Jezero, Gale >= 50% landable) | pass | pass (`README.md`: 99.5%, 99.98%) | pass for six control sites (`README.md`) |

**Reading:** the measure separates terrain classes better than chance, and the separation holds on blind data (AUC about 0.69, permutation p about 0.007 both times). It does not reach the pre-registered 0.70 AUC, and the nearest-region test gave 6 of 15 against 7 required. v1.3 failed by one region and by 0.005 AUC. The result is reported as it came out.

Source of the v1.3 holdout list: `data/derived/validation/v1.3.json`, `design.holdout_regions`.

---

## 12. Tests and checks

| Item | Status |
|---|---|
| Test files | 29 test files and `tests/conftest.py`; 301 test functions (`grep "def test_" tests/*.py`) |
| Tests run for this review | Not run. Project rule: only the files touched, never the full suite (`feedback_pruebas_por_muestreo`) |
| `tools/check_ledger.py` (R1 to R6) | Run, read-only: 6 of 6 OK, 0 offending rows |
| `tools/check_site_data.py` | Run, read-only: RESULT OK, 0 orphans |
| Test for neighbours exactness on real data | `tests/test_neighbors.py::test_exactness_sample_200_queries_on_real_data` (listed in `docs/ARCTIC_INTEGRATION_MAP.md` section 6); not run here |
| Run time of the full chain | `[not found]`: only partial stage timings exist (`docs/ARCTIC_INTEGRATION_MAP.md` section 5) |

---

## 13. Points to settle before the presentation

1. **Stale rehearsal and card files.** `data/derived/rehearsal/` holds 248 pair files, of which 160 are current. The ledger reads all 248 (section 8b). Stale cards: 408 in `data/derived/cards/`, 160 current. The site copy is correct (160).
2. **Refined count.** Log 67 against 72 computed (section 6b).
3. **Context count.** `earth_context.json` has 2,760 entries, and `run.json` reports 2,565 windows with complete context of 2,730 (section 7b).
4. **Old figures in the docs.** `docs/ARCTIC_INTEGRATION_MAP.md` and `docs/CHANGELOG.md` cite "211 Mars gap cells" and "87 closed" from the 400-window probe. The current NASADEM-only count is 215, and the all-bands count is 84.
5. **Sigma timing.** Sigma was calibrated on 2,000 windows before the ice rule (section 5).
6. **Validation display.** `site/data/facts.json` shows the v1.3 AUC as "0.69" (value 0.6948). The README shows 0.695. Pick one rounding.
7. **Mars mission limits.** No Mars limit has a 100 m baseline (section 3).
8. **Config and docstring names.** `config/earth_pool_rules.json` names `pool_add_arctic.py` (does not exist). `pipelines/light.py` says "2000 Earth windows" (file holds 4,065). STANDARDS 10.14 lists R1 to R5; the code runs R6 too.
9. **Site data is moving.** Another agent is moving orphans out of `site/data`. Counted at about 15:31, `site/data/terrain` had 255 directories; at 15:34 `check_site_data` counted 167 terrain folders. The DATA_STATUS counts are from a later pass.

---

## 14. Not found

- Total run time per stage: `[not found]`.
- Size of `data/raw/`: `[not found]` (not counted; not needed for the site).
- Test results: not run (see section 12).
- Reconciliation of the refined-candidate count (67 vs 72): `[not found]`.
- Reconciliation of context entries (2,760 entries vs 2,730 windows, 2,600 with entry, 2,565 complete): `[not found]` beyond the counts in `run.json`.
