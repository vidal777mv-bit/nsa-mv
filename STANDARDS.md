# STANDARDS — the contract every piece of this project follows

Version 1.6, 2026-11-14 (Mars first; 10.9-10.15; score frozen at v1.3). Section 10 (v1.1) overrides earlier text where they conflict. Changing anything here = new version + note in `docs/CHANGELOG.md`.
Language of everything public (code, comments, docs, outputs): **English**.

## 1. Layout and ownership

```
config/            measure.json (frozen) · sources.json · sites.json · regions.json
src/analog/
  core/            PURE math, numpy/scipy only, no file or network I/O
    metrics.py     terrain features on a grid
    measure.py     feature vector + distance
    stats.py       Wilson, AUC, bootstrap, permutation, Spearman, robust sigma
  grid.py          load any DEM file -> standard local grid (Section 3)
  io/
    fetch.py       download / clip remote rasters into data/raw (never global mosaics)
    provenance.py  the provenance block (Section 5)
pipelines/         thin scripts: read config + data, call src/analog, write data/derived
tests/             one synthetic test per rule; run per file, never "all" by default
data/raw/<body>/<site_or_region>/   inputs (git-ignored)
data/derived/<stage>/                outputs (JSON), one folder per pipeline
docs/              CHANGELOG.md, data notes
```

Rules: data flows one way (raw -> derived/measure -> derived/validation -> derived/ranking -> derived/cards -> site).
No stage rewrites another stage's output. `core/` never imports `io/` or `grid.py`.

## 2. Conventions

| Item | Standard |
|---|---|
| Bodies | `earth`, `moon`, `mars` (lowercase ids) |
| Radii (m) | earth 6371008.8 (mean, IUGG); moon 1737400; mars 3396190 (IAU 2015) |
| Coordinates | planetocentric latitude, **east-positive longitude in [-180, 180)**, decimal degrees, 4+ decimals |
| CRS ids | earth `EPSG:4326`; moon `IAU_2015:30100`; mars `IAU_2015:49900` |
| Working projection | azimuthal equidistant centred on the site: `+proj=aeqd +lat_0={lat} +lon_0={lon} +x_0=0 +y_0=0 +R={radius} +units=m +no_defs` |
| Units | metres, degrees (angles), percent (0-100) for `_pct`, fractions (0-1) elsewhere |
| Missing value | `NaN` in arrays, `null` in JSON. Never 0, never -9999 |
| Ids | `snake_case`, ascii; file names = id |
| Time | ISO 8601 UTC (`2026-11-14T15:00:00Z`) |
| Random | every random step takes an explicit `seed` (default 20261114) |
| Numbers in JSON | full float precision; rounding only in the website |

## 3. The standard grid (contract between `grid.py` and `core/`)

`load_local_grid(path, lat, lon, body, L, R) -> (z, mask, meta)`

- `z`: 2-D `float64`, elevation in metres, north-up, square pixels of side `L` (m), shape `(n, n)`, `n = 2*ceil(R/L)+1`, centre pixel = site.
- `mask`: 2-D `bool`, True where the pixel centre is within distance `R` of the centre **and** `z` is finite.
- Resampling: bilinear (`rasterio.warp.reproject`, `Resampling.bilinear`) from the native CRS to the AEQD above.
- `meta`: `{native_res_m, coverage, L, R, crs_src, crs_dst}` where `coverage = mask.sum() / disk_pixels`.
- Validity (checked by the pipeline, not by core): `L >= 2 * native_res_m` and `coverage >= 0.9`, else the window is **skipped and logged**, never patched.

## 4. Feature definitions (exact; `config/measure.json` holds the numbers)

Notation: `L` pixel size (m); `M` = mask; gradients by central differences `np.gradient(z, L)` (`gy, gx`);
statistics only over pixels where `M` and the needed neighbours are valid.

| id | Definition | Undefined -> null when |
|---|---|---|
| `slope_p95_deg` | 95th percentile of `degrees(arctan(hypot(gx, gy)))` | fewer than 50 valid pixels |
| `hi` | `clip((mean(z) - P5(z)) / (P95(z) - P5(z)), 0, 1)` | `P95 - P5 < 1e-6` m |
| `coherence` | `J = [[<gx²>, <gx gy>], [<gx gy>, <gy²>]]` (means over valid pixels); eigenvalues `l1 >= l2`; `(l1 - l2)/(l1 + l2)` | `l1 + l2 < 1e-12` -> **0.0** (flat is isotropic) |
| `hurst` | `nu(k) = sqrt(mean of all squared differences z(x+k)-z(x) along x AND along y pooled)`, for lags `k = 1,2,4,8` px, both ends valid; `hurst` = least-squares slope of `log nu` vs `log(k)` | any `nu(k) == 0` |
| `tpi` | `z - mean(z over annulus 0 < d <= r_px)`, `r_px = 5`; only where the full disk is valid | — |
| `ridge_pct` | `100 * share of valid-TPI pixels with tpi > +t`, `t = tan(1°) * r_px * L` | no valid-TPI pixel |
| `valley_pct` | same with `tpi < -t` | idem |

Implementation rules (v1.0.1): gradients are used only at interior pixels whose 4 neighbours are valid (no one-sided
edge differences); `coherence` needs ≥ 50 valid gradient pixels like `slope_p95_deg`, else null; for a geographic
source CRS, `native_res_m = max(north, east)` metric pixel size at the site latitude; `load_local_grid` raises on bad
input and the **pipeline** catches it, logs the reason and writes null.

Distance between two feature vectors `a`, `b` (same version):
`D(a,b) = sqrt( sum_k w_k ((a_k - b_k)/sigma_k)^2 / sum_k w_k )`, over features where both are non-null;
if fewer than 4 features are shared, `D = null`. `sigma_k = 1.4826 * MAD_k` over the Earth **dev** pool,
computed once by `pipelines/calibrate_sigma.py` and written into `measure.json` before any validation.

## 5. Mathematical oracles — tests that must pass (use maths in our favour)

Every function is tested against a surface whose answer is known in closed form, plus invariances.
Tolerances in brackets. Grid for synthetic tests: `L = 100`, `R = 4000` (n = 81) unless stated.

**Closed form**

| Surface | Expected |
|---|---|
| Plane `z = x tan(θ)`, θ = 10° | `slope_p95 = 10°` [1e-9]; `coherence = 1` [1e-9]; `hurst = 1` [1e-9]; `hi = 0.5` [0.01]; `ridge = valley = 0` |
| Flat `z = c` | `slope_p95 = 0`; `coherence = 0`; `hurst = null`; `hi = null`; `ridge = valley = 0` |
| Cone `z = h (1 - r/R)` over the disk | `hi = (1/3 - (1-√0.95)) / ((1-√0.05) - (1-√0.95)) = 0.4101` [0.02]; `coherence ≈ 0` [0.05] |
| Fractional Brownian surface, H = 0.3 and 0.7 (spectral synthesis, power ∝ \|f\|^-(2H+2), n = 257, seed fixed) | `hurst` = the generator's exact lattice expectation, `slope of log sqrt(Σ_f P(f)(2-2cos(2π f_x k)) pooled x,y) vs log k` over k = 1,2,4,8 (= 0.430 for H = 0.3, 0.712 for H = 0.7) [0.05]. Note: on a lattice the 1-8 px estimator is biased upward for rough surfaces; it is a comparative feature, applied identically everywhere. |

**Invariances (exact, [1e-9] unless stated)**

| Transform | Must hold |
|---|---|
| `z + c` | every feature unchanged |
| `k z`, k > 0 | `hi`, `coherence`, `hurst` unchanged |
| `rot90(z)`, `transpose(z)` | every feature unchanged |
| `-z` | `ridge_pct` ↔ `valley_pct` swap; `slope_p95`, `coherence`, `hurst` unchanged |
| one pixel set to `+10 (P95-P5)` | `hi` moves < 0.01 |

**Distance**: `D(a,a) = 0`; `D(a,b) = D(b,a)`; triangle inequality on 1000 random triples (seeded); scaling all σ by s divides D by s.

**Stats** (published values): Wilson 95% `(0,10) -> [0, 0.2775]`, `(5,10) -> [0.2366, 0.7634]` [1e-4];
AUC perfect separation = 1, identical samples = 0.5; Spearman of a monotone transform = 1;
`robust_sigma` of N(0,1) sample n = 100000 = 1 [0.02].

## 6. Validation statistics (`core/stats.py`)

- AUC by Mann-Whitney U (ties count 1/2), "positive" = same class pair, score = `-D`.
- Pairs are not independent, so the p-value permutes **region class labels** (not pairs): `p = (1 + #{AUC_perm >= AUC_obs}) / (1 + B)`, `B = 9999`.
- AUC 95% CI: bootstrap over **regions** (resample regions, rebuild pairs), `B = 2000`, percentile interval. Pairs formed by two copies of the **same original region are excluded** (D = 0 would inflate same-class AUC).
- Rates (recall@k, pass rates): Wilson 95%.
- Redundancy: Spearman |ρ| over the dev pool; flag pairs with |ρ| > 0.80.
- Thresholds live in `measure.json -> validation` and are frozen before running.

## 7. Provenance block (every JSON in `data/derived`)

```json
{
  "schema": "analog.<stage>/1",
  "created": "2026-11-14T15:00:00Z",
  "config_version": "1.0",
  "config_sha256": "<sha256 of measure.json bytes>",
  "code_version": "<git short hash or 'uncommitted'>",
  "inputs": [{"source_id": "...", "path": "...", "sha256": "..."}],
  "generated_with": "Code written with AI assistance (Claude, Anthropic) under the team's direction; data computed by this code from the listed sources."
}
```

## 8. Source and site records

`config/sources.json` — one entry per product:
`id, body, product, provider, access (http|stac|s3), url_or_collection, page, doi, license, resolution_m, crs, notes,`
`verified: {status: ok|broken|untested, http_code, bytes, checked_utc}`.

`config/sites.json` (planetary targets) and `config/regions.json` (Earth windows) — one entry per place:
`id, body, name, lat, lon, center_source (url + how the centre was obtained), dem_source_id,`
`role (target | dev | reserved | known_analog | search), class (Earth only), status (proposed | approved), notes`.
**Reserved regions:** listed, never measured until the final test.

## 9. Coding rules

- Python 3.14, `.venv` in the project root, versions in `requirements.lock.txt`.
- Type hints and a docstring with the formula on every public function.
- No silent fallbacks: a missing or invalid input returns `null` + a logged reason.
- Tests: `.venv/Scripts/python.exe -m pytest tests/test_<module>.py` — only the file you touched.
- No downloads > 500 MB per file; nothing global; total raw data budget 3 GB.
- No git commits (the team lead commits).

## 10. v1.1 additions (override earlier sections where they conflict)

### 10.1 Calibration and validation
- `sigma_k = 1.4826 * MAD_k` over the **search pool** (label-free, ~2000 Earth windows), not the dev regions. Written into `measure.json` by `pipelines/calibrate_sigma.py`, once, before validation.
- V0 redundancy: Spearman over the search pool; flag |rho| > 0.80.
- V1 sensor noise: the 15 **dev** regions measured with NASADEM and with Copernicus GLO-30; report median and p95 of D(same place, two sensors). In rankings, analogs whose D differs by less than the p95 share a `tie_group`.
- V2 discrimination: 15 dev regions (5 classes x 3) -> 15 same-class pairs vs 90 different-class pairs; AUC >= 0.70, bootstrap 95% CI lower bound > 0.5, permutation p < 0.05.
- V2-R reserve: each of the 5 reserved regions gets the class of its nearest dev region (1-NN by D). Pass if >= 4 of 5 correct (chance 1/5; one-sided binomial p = 0.00672; 3/5 gives 0.0579). Report Wilson 95% CI.
- `pipelines/validate.py` runs **once** on the final frozen config. If a bug is found afterwards, it is reported, fixed, and the rerun is logged in `docs/CHANGELOG.md`; thresholds and features never change after seeing results.
- Known-analog recovery test: removed (Meteor Crater 1.2 km = 12 px at 100 m).

### 10.2 Search pool
- Earth windows on a regular lat/lon grid within NASADEM coverage (56S-60N), kept only if the ESA WorldCover share of classes 60/70/100 (bare-sparse / snow-ice / moss-lichen) in the 8 km disk is >= 0.8. Target n = 2000 (grid spacing chosen to reach it; seed fixed). Windows within 25 km of a known analog are excluded from rankings (kept for sigma).

### 10.3 Mission-proven terrain %
- `config/missions.json` entries: `body, mission, vehicle, kind (landing|driving), max_slope_deg, baseline_m, source_url, note`. Only values read from an official or peer-reviewed source.
- Per body and kind, `limit_deg` = the value chosen in `missions.json -> limits` with its source.
- `mission_pct(kind) = 100 * share of valid disk pixels (100 m grid) with slope <= limit_deg`. Baseline 100 m is stated wherever the number is shown.
- Control: Jezero and Gale landing % must be >= 50; otherwise stop and report before publishing.

### 10.4 Body facts
`config/bodies.json`: `gravity_m_s2, surface_pressure_pa, temp_min_k, temp_max_k, day_length_h, source_url` from the NASA Planetary Fact Sheet (nssdc.gsfc.nasa.gov/planetary/factsheet).

### 10.5 Card contract — `data/derived/cards/<target>__<analog>.json`
```
target_id, analog_id, rank, D, tie_group,
features: {<name>: {target, analog, z_diff}},     z_diff = (analog - target)/sigma
similar: [names with |z_diff| <= 1], different: [names with |z_diff| > 1],
mission_pct: {landing: {target, analog, limit_deg, source}, driving: {...}},
rotation_deg,
files: {target: "terrain/<id>/", analog: "terrain/<id>/"},
provenance
```
Index files: `site/data/targets.json` (targets with body, name, lat, lon, thumbnail) and `site/data/rankings/<target>.json` (ordered analogs with rank, D, tie_group, lat, lon, card path).

### 10.6 Visual terrain contract — `site/data/terrain/<id>/`
- Common grid L = 30 m, R = 4000 m -> n = 2*ceil(4000/30)+1 = 269; same AEQD rules as section 3.
- `height.bin`: Float32 little-endian, row-major north-up, n*n values, metres relative to the disk mean, NaN outside the disk.
- `layers.bin`: Uint8 n*n; bit0 slope > landing limit, bit1 slope > driving limit, bit2 ridge (tpi > +t), bit3 valley (tpi < -t); slope/TPI computed on the 100 m grid and nearest-neighbour upsampled to 30 m so layers show exactly what was measured.
- `hillshade.png`: 8-bit grey, sun azimuth 315 deg, altitude 45 deg, same for every terrain.
- `meta.json`: `id, body, name, lat, lon, n, L, R, z_min, z_max, source_id, provenance`.
- Vertical exaggeration: one global value for the whole site, `site/data/viz.json -> vertical_exaggeration`, never per terrain.
- Alignment rotation for a pair: 0-350 deg step 10, minimise RMS of standardised heights in the inner disk (r <= 0.9R); stored in the card as `rotation_deg`. Features are rotation-invariant (tested), so rotation only affects the display.

### 10.7 Sample-first rule (efficiency)
Every pipeline runs first on a **sample** (2 targets, 3 regions, 50 pool windows) and its outputs are checked against the contracts before the full run. Tests: one test file per module, run alone.

### 10.8 Decisions after phase 1 review (v1.1.1)
- The `L >= 2 x native` rule applies to **measurement** (100 m grid) only. The 30 m visual grid is display-only and exempt (Jezero/Gale CTX 20 m are exported at 30 m); layers still come from the 100 m measurement.
- Layer files are `layers_<body>.bin` (bits 0-1 depend on the target body's mission limits): a target writes its own body; an Earth analog writes one file per target body that ranks it.
- Pool index `data/raw/earth/pool/index.json`: readers accept either a top-level list or `{"windows": [...]}`; entry fields `id, lat, lon, worldcover_share, near_known_analog, path, valid_fraction`.
- `pipelines/_common.py` is the single place where a raw DEM becomes features.
- Measure records written before sigma calibration keep the pre-calibration config hash (features do not depend on sigma); validation records the post-calibration hash.
- Vertical exaggeration: `VE = floor_0.1(0.2 * 2R / max_terrains(P99 - P1 of 30 m heights))`, one global value.

### 10.9 Mars-first product (v1.2, 2026-11-13, decided by Mario)
Priority: **Mars first**, Moon second. The website (built by Codex from `CODEX_UI_BRIEF.md`) owns `site/` except `site/data/**`, which only `pipelines/export_viz.py` writes. Agents never edit `site/` outside `site/data/`.

`site/data/targets.json` entries gain:
`landing_class` (`landing_demonstrated` | `landed_tipped` | `candidate` | `future_mission`), `mission` (e.g. "Perseverance"), `year` (int or null),
`outcome_note` (one sentence, sourced), `center_note` (how the centre was obtained), `unlocked` (true when a fine DEM <= 50 m exists and the target was measured).
Additional files written by export: `site/data/bodies.json` (copy of config/bodies.json bodies), `site/data/validation.json` (summary of data/derived/validation), `site/data/missions.json` (limits + entries with sources).

### 10.10 Regional scale for whole-Mars coverage (EXPERIMENTAL — sample first, Mario decides after the sample)
- Same six features and formulas; grid `L = 400 m`, window `R = 16 km` (n = 81), TPI radius 5 px (2 km), threshold tan(1 deg) x 2000 m.
- Mars source: HRSC-MOLA blended 200 m (remote windowed reads); Earth source: NASADEM resampled to 400 m over the same pool centres (32 km windows).
- Own sigma (Earth regional pool, 1.4826 MAD), own config `config/measure_regional.json`, own outputs `data/derived/regional/`. Never mixed with the 100 m scale: a distance is only computed between two windows of the same scale.
- Validity of the regional scale is NOT established by the 100 m validation; until it has its own test it is shown as "exploratory" in the site.

### 10.11 Version 1.3 and its fresh holdout (pre-registered 2026-11-13, before the holdout exists)
- v1.2 result (kept, reported, never overwritten): V0 pass; V1 median 0.141, p95 1.202 (driven by 3 flat plains); V2 AUC 0.693, CI [0.44, 0.91], p 0.006 -> FAIL; V2-R 2/5 -> FAIL; mission control pass.
- v1.3 distance uses `slope_p95_deg`, `hi`, `hurst` (coherence excluded: alone AUC 0.50, flat-terrain sensor noise 1.2-2.4 sigma). Sigma unchanged (pool, label-free).
- Tie rule: threshold = p95 of the dev sensor-noise D within the target's relief class (rugged slope_p95 >= 3 deg, flat < 3 deg).
- v1.3 was designed looking at the v1.2 dev and reserve results, so those 20 regions cannot validate it. Validation uses **15 new regions** (`role: holdout_v13`, 3 per class, same selection rules, chosen and visually checked by landform only, never measured before the single run).
- Pass criteria (all on the holdout): AUC >= 0.70 with bootstrap 95% CI lower bound > 0.5 and permutation p < 0.05; and 1-NN of each holdout region against the 15 dev regions >= 7/15 correct (binomial p 0.018 vs chance 1/5). One run; result shown whatever it is.

### 10.12 Presentation fixes after the first real-data UI review (v1.3.1)
- **Vertical exaggeration per pair**: `card.vertical_exaggeration` = floor_0.1(0.2 * 2R / max(P99-P1 of the two 30 m height grids of the pair)), clamped to [1, 10]; the SAME value is applied to both terrains of that pair (fairness holds within the pair). `viz.json` keeps a global default only for single-terrain views.
- **Features in the score**: cards carry `in_distance: [feature names with weight > 0]` and `context_features: [the others]`; `similar`/`different` are computed over `in_distance` only, and `context_similar`/`context_different` over the context features.
- **Analog place names**: rankings and cards carry `analog_place: {name, admin1, country, source}` from an offline reverse-geocode of the window centre against Natural Earth 1:10m admin-1 states/provinces (public domain), name = "admin1, country"; plus `nearest_named_feature` if available (null otherwise). Never invented.

### 10.13 Unlocked / to-discover atlas (v1.4 product layer, 2026-11-13, decided by Mario)
The score (v1.3: slope_p95_deg, hi, hurst; sigma from the Earth pool) and the validation are FROZEN. Everything below
adds coverage and context; nothing re-tunes the measure.

**Mars pool (unlocked Mars).** Centres drawn seeded (20261114) uniformly on the sphere (uniform in sin(lat)); for each
centre, query USGS STAC `mro_ctx_controlled_usgs_dtms` (CC0) for DTMs whose bbox contains the 4.5 km half-width
square; take the one with the highest valid fraction in the 4 km disk from a remote window read of the `dem` asset
(half-width 4.5 km, original CRS kept, written to `data/raw/mars/pool/mars_NNNNN.tif`). Accept if valid >= 0.90 and the
CRS is a Mars body CRS; stop at 2000 accepted. Log every attempt (accepted / no DTM / low valid / read error) in
`data/raw/mars/pool/attempts.jsonl` and the accepted list in `data/raw/mars/pool/index.json`
(`id, lat, lon, product_id, path, valid_fraction`). The acceptance rate is itself an estimate of CTX coverage.

**Mars atlas export.** Each Mars pool window is measured with the frozen v1.3 config and gets its top-3 Earth twins
from the Earth pool. `site/data/atlas/mars_cells.json`: `[{id, lat, lon, features, twins:[{analog_id, D, tie_group,
analog_place}], mission_pct:{landing, driving}}]`. Same cell format later for the Moon if added.

**Coverage grids (the fog).** `site/data/coverage/<body>.json` = `{body, res_deg: 1, width: 360, height: 180, origin:
[-180, 90], classes: {"0":"out_of_reach","1":"to_discover","2":"unlocked"}, grid: [row-major ints], source}`.
Mars: 2 where a measured window centre falls, 1 where CTX DTM bboxes cover the cell (from config/mars_coverage.json),
0 elsewhere. Moon: 2 at measured sites, 1 within 80S–90S (LOLA 20 m polar DEM), 0 elsewhere. Earth: 2 at pool
windows, 1 where the coarse WorldCover bare share >= 0.8 (cached tiles), 0 elsewhere (ocean, vegetation, crops).

**Discoveries.** `config/known_analog_regions.json`: famous terrestrial analog regions `[{id, name, lat, lon,
radius_km, source_url}]` (circle approximation, stated as such). Every Earth twin gets
`novelty: "known_region" | "new"` (+ `known_region_id`); `site/data/discoveries.json` counts unique Earth windows that
are a top-3 twin of any Mars/Moon target or Mars cell and are "new".

**Refined search (targets only).** For each of the 16 targets' top-10 Earth twins, re-measure windows shifted on a
5 x 5 grid of 2 km steps (offsets -4..4 km) from one NASADEM clip (half-width 8.5 km) per candidate; keep the offset
with the lowest D; record `refined_offset_km` and the D before/after. Ranking order may change; tie rule unchanged.

**Earth context per twin (not scored).** `context: {koppen_class, koppen_label, elevation_m (window mean), nearest_town:
{name, distance_km}, sources}` from Köppen-Geiger 1 km (Beck et al. 2018/2023, CC BY 4.0) and Natural Earth populated
places 1:10m (public domain).

### 10.14 The facts engine — parts and contracts (v1.5, 2026-11-14, decided by Mario)
One direction, each part reads only the previous part's persisted output. Score and validation stay frozen (v1.3).

```
data/derived/** (existing outputs)
   │
P-L  ledger   tools/build_ledger.py  ─► data/derived/facts/facts.duckdb + facts.parquet
   │
P-R  rules    tools/check_ledger.py  (SQL assertions over facts; exit 1 on any violation)
   │
P-N  neighbors src/analog/core/neighbors.py (pure) + pipelines/neighbors.py ─► data/derived/neighbors/*.parquet
   │
P-Q  query    pipelines/export_query.py ─► site/data/query/<table>/...  (columnar binary for the browser)
   │
P-G  generate tools/render_facts.py  ─► numbers in README/slides/project text from facts only
   │
site  "Ask the atlas" + "Where Earth runs out" (reads site/data/query only)
```

**P-L Ledger.** Table `facts` (DuckDB, also exported as Parquet):
`fact_id, subject_type (target|mars_cell|earth_window|region|body|mission_limit|validation), subject_id, body,
property, value_num, value_text, unit, scale_m, footprint (point|local|regional|global), kind (measured|derived|published),
level (observation|interpretation|scenario), source_id, source_url, verified (bool), produced_by, config_version`.
Built only from persisted outputs (measure, cards, rankings, mission, atlas, coverage, validation, config). No hand-entered value.

**P-R Rules** (each a SQL query that must return zero rows):
R1 a threshold comparison (mission %) whose limit baseline is null or differs from the measurement scale is tagged
`comparison: reference` (never `compliance`); R2 a `point` footprint fact is never attached to a region-scale subject;
R3 every fact has `source_id` or `produced_by`; R4 no two facts with the same (subject_id, property, scale_m) and different
values; R5 every number rendered by P-G resolves to exactly one fact.

**P-N Neighbors.** Standardised vector `z_k = x_k / sigma_k` over the in-distance features (equal weights), so
`D(a,b) = ||z_a - z_b||_2 / sqrt(K)` (K = 3). `scipy.spatial.cKDTree` on the Earth pool gives EXACT k-nearest twins
(`query(k)`) and ties (`query_ball_point(r = tie_threshold * sqrt(K))`). Required test: identical results to brute force
on a seeded sample of 200 queries (indices and D to 1e-12). **Earth gap**: for every Mars cell and target,
`gap = D_nearest > tie_threshold(relief class)` — no Earth window is indistinguishable within sensor noise.

**P-Q Query export.** Per table (`targets`, `mars_cells`, `earth_windows`, `twins`): `manifest.json`
(rows, columns, type, unit, fact property), one `<column>.f32` (Float32 LE) per numeric column, `<column>.order.u32`
(row indices sorted by value, for binary-search ranges), `<column>.codes.u16` + `<column>.dict.json` for text.
Missing = NaN / code 65535. Total budget < 2 MB.

**P-G Generate.** Templates with placeholders `{{fact:<subject_id>:<property>[:format]}}` and
`{{agg:<sql-name>}}` (named SQL aggregates in the ledger) are rendered from the ledger; an unresolved placeholder fails.

### 10.15 Mission dossier: light + rehearsal plan (v1.6, 2026-11-14, decided by Mario)
Each target–twin pair is shown as a 5-step dossier: 01 the site and what the mission needs · 02 the evidence (terrain,
mission %, light) · 03 the Earth twin · 04 what you can rehearse there / what it cannot teach you · 05 where Earth runs out.
Score, validation and the existing outputs stay frozen; the new parts only ADD stages. One direction:

```
config/light.json ──► P-S light   src/analog/core/light.py (pure) + pipelines/light.py ─► data/derived/light/light.json
                                                                                       └► site/data/light.json
cards + light + config/bodies.json + config/rehearsal_rules.json
                  ──► P-P plan    src/analog/core/rehearsal.py (pure) + pipelines/rehearsal.py
                                   ─► data/derived/rehearsal/<target>__<analog>.json ─► site/data/rehearsal/ (same name as the card)
ledger (tools/build_ledger.py) adds light + rehearsal facts; site reads cards + rehearsal + light.json
```

**P-S Light (no relief; closed form + sampling).** `config/light.json`: obliquity per body with source
(Earth 23.44, Mars 25.19 from the NSSDC fact sheets; Moon 1.54 = lunar equator to ECLIPTIC, the angle that sets the
Sun's declination — NOT NSSDC's 6.68 deg, which is to the Moon's orbit around Earth; state the source used).
Circular orbit, Sun as a point. Year fraction f = i/72, i = 0..71: sin(dec) = sin(eps) sin(2 pi f). Hour angle
H = 2 pi j/144, j = 0..143. Elevation: sin(e) = sin(phi) sin(dec) + cos(phi) cos(dec) cos(H).
Per subject: `noon_sun_max_deg = 90 - max(0, |phi| - eps)`, `noon_sun_min_deg = 90 - (|phi| + eps)` (may be negative),
`sun_time_pct = 100 * share(e > 0)`, `grazing_pct = 100 * share(0 < e < 10 deg)` (share of ALL samples).
Subjects: the 16 targets (site/data/targets.json lat) and the 2000 Earth windows. Oracles (tests): eps = 0 at the equator
-> sun_time 50 %, noon max 90; any latitude with eps = 0 -> sun_time 50 %; phi = 90, eps = 23.44 -> sun_time 50 % and
noon max 23.44; closed forms equal the sampled max/min within one sample step.
**P-S1 Local horizon (Moon targets only, optional, labelled).** From the LOLA 5 m DEM already in data/raw/moon/<target>:
36 azimuths (10 deg), observer 2 m above the centre, max of atan((z(d) - d^2/(2R) - (z0 + 2)) / d) along each ray to the
tile edge (R = 1737.4 km). Outputs `horizon_max_deg`, `horizon_median_deg`, `sun_time_relief_pct` (e > horizon of the
nearest azimuth; azimuth = atan2(east, north) mod 360, north = cos(phi) sin(dec) - sin(phi) cos(dec) cos(H),
east = -cos(dec) sin(H)), `horizon_reach_km` (tile radius actually used). Label: "near horizon only (within <reach> km);
far mountains not included". Oracle: a flat plane gives a horizon slightly below 0 (curvature).

**P-P Rehearsal plan.** Rules live in `config/rehearsal_rules.json` (no limit without a source). Lines, each
`{id, group (rehearse|cannot), label, status (yes|partial|no), target_value, analog_value, unit, rule, evidence
(derived observation | reference comparison | published), source}`:
- `landing`: card mission_pct.landing; yes if |analog - target| <= 10 points, partial if <= 25, else no. evidence = reference comparison.
- `driving`: same with mission_pct.driving.
- `cold`: card context.koppen_class; yes if in the cold set {BWk, BSk, ET, EF, Dfc, Dfd, Dwc, Dwd, Dsc, Dsd}, else no;
  always shown with the body's temp range from bodies.json (an Earth cold desert never reaches it) -> best status is partial.
- `low_sun`: light grazing_pct; yes if analog >= target - 10 points, partial if analog >= target / 2, else no; when no,
  the line names the lowest latitude where grazing_pct reaches the target value (from the same closed form).
- cannot (always listed, group cannot, status no, evidence published, from bodies.json): `gravity` (ratio to Earth),
  `pressure` (ratio), `temperature` (range), `day_length` (h).
Missing input -> the line has status null and a `reason`; never a guess.
**10.15 addendum (ledger inputs).** The ledger (P-L) also reads the persisted outputs of P-N (`data/derived/neighbors`),
P-S (`data/derived/light`), P-P (`data/derived/rehearsal`) and the Arctic experiment (`data/derived/arctic_probe`); the flow
stays one-way (none of them reads the ledger). Subject types add `pair` (rehearsal lines) and `experiment` (arctic_probe).
The Arctic probe is an experiment: its facts never change pool, sigma, gap or any frozen result.
