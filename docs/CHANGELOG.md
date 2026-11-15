# Changelog

## 1.0 — 2026-11-13
- STANDARDS.md and config/measure.json frozen (sigma pending calibration on the Earth dev pool).

## 1.0.1 — 2026-11-13
- fBm Hurst oracle: was H +/- 0.1 (wrong: lattice estimator gives 0.430 for H=0.3); now the generator's exact lattice expectation +/- 0.05. Verified independently by the lead.
- Bootstrap over regions excludes pairs of two copies of the same region.
- Written down: interior-only gradients, coherence 50-pixel minimum, geographic native_res = max(N,E), pipeline catches grid errors.
- No measurement existed yet; no data affected.

## 1.1 — 2026-11-13
- Plan v2 approved by Mario: sigma from search pool; V1 on dev regions (2 sensors); V2-R = 1-NN >= 4/5; V3 removed; mission-proven terrain %; card/visual contracts; sample-first rule. No measurement existed yet.

## 1.1.1 — 2026-11-13
- Phase 1 review: visual grid exempt from 2x-native rule; layers_<body>.bin; pool index accepts list or {windows}; VE rule written. Lead verified haworth/malapert/jezero slope_p95 and hi by an independent block-mean method (diff <= 0.4 deg, <= 0.002).

## Region review — 2026-11-13 (lead, visual check of the 15 dev regions on NASADEM hillshade, 8 km windows; reserved not viewed)
- OK as given: aorounga, gosses_bluff, tenoumer, harrat_khaybar, payun_matru, badain_jaran, cotahuasi, fish_river, nullarbor, ustyurt.
- Centre moved (by visual landform identification on a 50 km hillshade, never by the measured features):
  al_haruj -> 27.1324, 17.2929 (cone cluster; original centre was smooth lava plateau);
  wadi_mujib -> 31.4748, 35.6997 (canyon; original window was half Dead Sea water);
  namib_sand_sea -> -24.6343, 15.1775 (dunes; original centre on a pan);
  tenere_plain -> 17.7009, 10.7565 (flat; original centre on linear dunes).
- Replaced: simpson_desert (dunes not resolved at 30 m) -> algodones_dunes 32.9077, -115.0232 (Wikipedia coordinate 32.9167, -115.05 shifted 2.5 km E/1 km S onto the dune belt).
- Rule for validation regions: no water, trees or crops in the 8 km disk; WorldCover bare share is reported, not a criterion (it is the search-pool criterion). gosses_bluff and cima_volcanic_field approved on this rule.

## Gale check — 2026-11-13
- Centre elevation grid -4499.05 vs point sample -4497.51 (1.5 m) is the expected effect of GDAL bilinear downsampling (tent filter, half-width = output pixel 100 m): lead's independent tent-weighted mean = -4499.04. Centre checks compare against the tent-filtered value, not a point sample. Elevation offsets do not affect any feature (z + c invariance).
- Jezero re-measured at 18.4447, 77.4508 (4-decimal centre).

## 1.2 — 2026-11-13
- Mario: Mars is the priority; UI to be built by Codex (CODEX_UI_BRIEF.md). targets.json gains landing_class/mission/year/outcome_note/center_note/unlocked. Experimental regional scale (400 m, R 16 km) for whole-Mars coverage, sample first.

## Sigma calibration — 2026-11-14T02:53:43Z

- Script: pipelines/calibrate_sigma.py, pool = data/derived/measure/pool__*.json (status ok). Config sha256 is in the next validation provenance.
- slope_p95_deg: n=2000, median=3.39607, MAD=2.0511, sigma=1.4826*MAD=3.04096
- hi: n=1994, median=0.475203, MAD=0.0431762, sigma=1.4826*MAD=0.0640131
- coherence: n=2000, median=0.179671, MAD=0.105843, sigma=1.4826*MAD=0.156923
- hurst: n=2000, median=0.621964, MAD=0.135023, sigma=1.4826*MAD=0.200185
- ridge_pct: n=2000, median=1.23025, MAD=1.23025, sigma=1.4826*MAD=1.82397
- valley_pct: n=2000, median=0.4144, MAD=0.4144, sigma=1.4826*MAD=0.61439

## Phase 2a (agent A) — 2026-11-14
- build_measure on the search pool: 2000 windows, 2000 ok, 0 skipped, 0 missing, 0 errors (about 3 min). Sample of 50 first (data/derived/sample/measure), then all. Records: data/derived/measure/pool__*.json.
- build_measure now resumable (existing record with the same measure_key is reused; measure_key = sha256 of grid, tpi and hurst lags, the only config values a feature depends on), --kind target|region|pool, --force, progress line every 200 jobs. Measure records gain a measure_key field (pipeline field, no contract change).
- Targets re-measured with --force (status ok): haworth, malapert_massif, nobile_rim_1, nobile_rim_2, de_gerlache_rim_2, jezero, gale.
- Sigma written to config/measure.json by calibrate_sigma.py (entry above). Redundancy preview (not V0): |rho| > 0.80 for slope_p95-ridge_pct 0.955, slope_p95-valley_pct 0.945, ridge_pct-valley_pct 0.942; 6 pool windows are flat (hi null, slope ~1e-14).
- export_viz (STANDARDS 10.9): targets.json entries carry landing_class, mission, year, outcome_note, center_note, unlocked from config/sites.json (null when absent); site/data/bodies.json, missions.json, validation.json written (validation status "not run" until validate.py runs). Not yet run to site/data.

## measure 1.2 — 2026-11-13 (approved by Mario)
- Redundancy rule applied BEFORE validation (pool is label-free; validation not run): Spearman on the 2000-window pool slope_p95 vs ridge_pct 0.955, vs valley_pct 0.945, ridge vs valley 0.942 (lead recomputed independently). ridge_pct and valley_pct get weight 0 (excluded from D), kept as layers/context. D uses slope_p95_deg, hi, coherence, hurst (max |rho| 0.62). Sigma unchanged.

## Phase 2b (agent A) — 2026-11-14
- distance(): features with weight 0 are excluded from D and from min_shared_features (config v1.2: ridge_pct, valley_pct). Test added in tests/test_measure.py.
- build_measure --kind region: 15 dev regions x 2 sensors = 30 records, all ok (reserved regions not measured here).
- validate.py run ONCE on the frozen config (v1.2): data/derived/validation/v1.2.json. V0 now on the 4 in-distance features (validation file name = v<config version>, search and export read the same name). Result: V0 pass (max |rho| 0.623); V1 median 0.141, p95 1.202; V2 AUC 0.693 (CI 0.442-0.913, p 0.0059): FAIL; V2-R 2/5 correct (Wilson95 0.118-0.769, binomial p 0.263): FAIL. all_pass False. Reported, not rerun (STANDARDS 10.1). Top-10 analog tie groups: all in group 0 (p95 1.20 exceeds the top-10 D spread).
- search.py (7 targets, real run, data/derived/ranking/): 1994 candidates each (6 flat windows have hi null, 3 features: no D). Pool near_known_analog: 0 windows within 25 km (closest 30.1 km), checked independently.
- mission_pct.py (7 targets + ranked analogs): CONTROL passed: jezero landing 99.54%, gale landing 99.98% (limit 15 deg, 100 m baseline).
- export_viz.py real export for the 7 targets into site/data/ (unlocked computed from the measurement: native <= 50 m). Agent B's 9 new targets are not in this export (--ids).
- Search refusals now return exit 2 (previously a silent 0).

## 1.3 — 2026-11-13 (Mario: 'hacerlo bien')
- v1.2 validation FAILED (V2 AUC 0.6926 recomputed by lead; V2-R 2/5). Kept as is.
- v1.3 pre-registered before any holdout exists: D = slope_p95, hi, hurst; relief-conditional tie rule; fresh 15-region holdout; pass criteria in STANDARDS 10.11. Whole-Mars regional scale not pursued (E's sample: ~100 GB transfer, no validation).

## Phase 2c (agent A) — 2026-11-14
- v1.2 result kept: data/derived/validation/v1.2.json never rewritten (sha256 bdbeeecfb8535211ef445af8748192434dd9a42e3dc117a23530be25ebc76399). validation.json shows it as "failed" with all numbers.
- validate.py split into two modes: --noise (dev only, re-runnable: data/derived/validation/noise_v1.3.json, tie thresholds by relief class) and --holdout (STANDARDS 10.11 single run, refuses when v1.3.json exists). The v1.3 holdout validation has NOT been run (waiting for the lead's go and the holdout regions).
- Tie thresholds (v1.3, dev NASADEM vs Copernicus D by relief class of the dev region, rugged = slope_p95 >= 3 deg): rugged p95 0.4150 (n=13), flat p95 1.1017 (n=2; the flat threshold rests on two regions).
- build_measure: a target's raw file is now the one stored in its own folder. Before, four Moon sites sharing lola_20m_polar_ldem would have all been measured from im1_odysseus's clip. Nine new targets measured (ok, own files).
- mission_pct control extended (lead): jezero, gale, insight_elysium, spirit_columbia, zhurong, apollo17_taurus_littrow must be >= 50 landing: all pass.
- search, mission_pct, export_viz run for all 16 targets (v1.3). Stale v1.2-era outputs not referenced by the current rankings removed (site/data terrain 23 folders, site/data cards 35, data/derived/cards 35).

## Holdout v1.3 visual review — 2026-11-13 (lead; hillshade only, no features computed)
- Accepted (10): tin_bider, upheaval_dome (crater ring visible), harrat_kishb, lunar_crater, pali_aike, sharqiya, talampaya, wadi_rum, betpak_dala, tanezrouft.
- Rejected by landform criterion (5): gweni_fada (no crater form inside the 8 km disk), erg_chech (one dune ridge on a flat sheet), great_victoria (dunes not resolved at 30 m, like simpson), monument_valley (buttes on a plain, not a canyon), sturt_stony (smooth pan inside the disk). Replacements requested with the same blind procedure.

## Holdout replacements review — 2026-11-13 (lead; hillshade only)
- Accepted: ouarkziz (crater ring), grand_erg_oriental (dune crests), buckskin_gulch (canyon), tanami (flat).
- taklamakan: whole-degree Wikipedia centre fell on a flat sand sheet; centre moved by visual landform identification on a 50 km hillshade to 38.9452, 82.4309 (linear megadune belt). No features computed.
- Holdout v1.3 is complete: 15 regions, 3 per class. Visual check closed; status to 'approved'.

## v1.3 holdout validation — 2026-11-14 (ran ONCE; data/derived/validation/v1.3.json; never rerun)
- Result: FAIL. AUC 0.6948 (criterion >= 0.70); bootstrap 95% CI [0.5058, 0.9224] (lower bound > 0.5: pass); permutation p 0.0068 (< 0.05: pass); 1-NN 6/15 correct (criterion >= 7: fail; Wilson 95% [0.198, 0.643]; binomial p 0.061). Overall: FAIL.
- Independently recomputed by the agent (AUC 0.694815, 6/15): match. Pairs 105 = 15 same-class + 90 different-class; no null D.
- Holdout measured with --kind holdout (NASADEM, 15 ok). Dev regions: the 15 dev NASADEM records as before.

## Presentation fixes 10.12 (v1.3.1) — 2026-11-14
- card: vertical_exaggeration per pair = viz.pair_exaggeration (floor_0.1(0.2*2R/max relief of the pair), clamp [1,10]); range over the 160 cards: 1.0 to 10.0.
- card: in_distance / context_features; similar/different over in_distance only; context_similar/context_different over the rest.
- analog_place from an offline reverse-geocode (src/analog/io/places.py, shapely + own shapefile reader) against Natural Earth 1:10m admin-1 v5.1.1 (public domain): 160 of 160 analog windows inside a polygon, none needed the 50 km nearest rule. nearest_named_feature: null (no offline source).
- validation.json: v1.2 block carries a short diagnosis text (numbers verified: coherence AUC 0.50, hurst 0.82 single-feature). v1.3 block = holdout result (failed); v1.3_noise = thresholds.
- Note: the hillshade PNGs are baked with the global VE; a viewer applying the pair VE must derive shading from height.bin (or the PNG must be per pair).

## Cleanup — 2026-11-13 (approved by Mario)
- Deleted 23 orphan mission-share files of pool windows no longer in any ranking (42 KB; lead confirmed no reference in rankings or site/data). Run logs kept. data/derived/regional kept in place (already isolated and documented in docs/regional_feasibility.md; moving it would break those paths).

## 1.4 — 2026-11-13 (Mario: unlocked/to-discover atlas)
- USGS STAC CTX DTMs: 44,628 products, CC0, windowed reads OK (lead verified). ~17% of Mars has full 8 km disks (agent M Monte Carlo, Wilson 95% 16.0-18.1%). Contract 10.13: Mars pool of 2000 at the frozen v1.3 scale, fog grids for Mars/Moon/Earth, novelty flags, refined search, Earth context. Score and validation unchanged.

## Mars coverage sources decision — 2026-11-13 (lead)
- Mars fog and Mars pool use USGS CTX DTMs only (one sensor, CC0, verified windowed reads).
- HRSC: some products/MC-30 tiles at 50 m exist (agent M2), but int16 units/offset and the FU Berlin licence are unverified and it would mix sensors -> not used; noted as future work.
- HiRISE: footprints too narrow for an 8 km disk (M2: 0/20 by 4-corner footprint, median 0.685) -> not used.


## 2026-11-14 - Overlay readability correction

The aligned view previously mixed a transparent blue filled surface with opaque
Earth terrain, making apparent intersections easy to mistake for shared terrain.
It now uses green Earth relief and a blue target mesh: solid visible segments and
subdued dashed segments behind Earth. The mode is named `Align & inspect` and
includes an in-place reading key. Entering it opens the real height cross-section.
The visibility slider controls the mesh, not a blended fill. No local similarity
mask, score, data export or classification was added or modified.

Validation: JavaScript syntax checks and the DOM journey suite passed for animated,
reduced-motion and no-WebGL cases, including automatic profile opening and the
mode-specific key. Browser visual verification remains unavailable: the browser
access host reported unavailable. Actual rendering and readability still need a
visual check. Prior source is preserved in `_ui_backups/overlay-20261114-011031`.


## Continuous workspace delivery - 2026-11-14

Supersedes the earlier separated destination/region/scan/twin journey. The two globes,
target list, Earth candidates, comparison, contextual explanation, profiles and mission
evidence now share one workspace. Target selection automatically selects the first
exported candidate. Candidate changes update the pair in place and preserve camera
and comparison mode. Old navigation hashes resolve to the workspace.

Camera supports full azimuth, elevation below the horizon, top/profile/underside/oblique
presets, surface isolation and explicitly artificial vertical separation. The inspector
adds a practical interpretation using exported slope shares, with limits and no mission
success probability claim. See UI_CONTINUOUS_EXPERIENCE.md for the product contract.

Verification: syntax of all site JavaScript passed. Updated DOM integration suite passed
animated, reduced-motion and no-WebGL journeys, auto-selection, inline pair switching,
Mars/Moon switching, rapid selections, camera/isolation/separation bindings and unique
IDs. Renderer agent verified 56 analytic framing scenarios including negative elevation.
DOM tests mock the WebGL renderer; visual rendering and transitions still require browser
review because the browser access host is unavailable.

The current tools/check_site_data.py fails: it requires context, novelty, known_region_id
and refined fields absent from existing exported rankings. This data contract failure is
not resolved by the UI implementation. No data files or scientific thresholds were edited.

## Cleanup 2 — 2026-11-14 (approved by Mario)
- Deleted 656 orphan files under site/data (160 superseded frozen-search cards + 496 files of 124 superseded terrain folders, 50 MB), list taken from tools/check_site_data.py; checker OK afterwards (0 orphans). Site size 140 MB -> 90 MB.
- Mission-pct fix (agent A): source_url key bug; refined analog windows now have landing/driving % (160 cards, all non-null, with sources); checker now fails on nulls.

## 1.5 — 2026-11-14 (Mario: build it differently, in parts)
- Facts engine contract 10.14: ledger (DuckDB/Parquet) -> SQL rules -> exact KD-tree neighbours + Earth gap -> columnar query export -> generated numbers. Score/validation unchanged.

## 1.6 — 2026-11-14 (Mario: show better what the project does)
- 10.15 Mission dossier: light stage (closed form, optional Moon local horizon) + rehearsal plan stage (rules with sources); existing outputs untouched; ledger gains light + rehearsal facts.
- Light stage done (verified by the lead with an independent loop: jezero grazing 6.25, haworth 49.98, 2.77N 5.56, 59.77N 15.25 — identical). Notes: sun_time_pct is ~49.98 % for every subject (annual identity for a circular orbit) and is not used in rules or shown; the 50 % oracles hold within one sample step (exact 71/144 and 35/72 because e = 0 samples are excluded); |sin e| < 1e-12 snapped to 0. Moon source for 1.54 deg: Boue 2020, CMDA, doi 10.1007/s10569-020-09961-9. Finding: Earth grazing light peaks at ~18 % near 70N, far below the ~50 % of the lunar south pole -> no Earth latitude rehearses lunar-pole light. Local horizon only for the 5 Moon targets with a LOLA 5 m surface DEM (reach 10-15 km).
- Arctic probe (EXPERIMENT, isolated in data/derived/arctic_probe; frozen pool, sigma and results unchanged): 400 Copernicus GLO-30 windows 60-82N with the pool's rule. Closes 87 of 211 Mars gap cells (41.2 %, Wilson 34.8-48.0 %; a lower bound, still rising with n) and 2 of 3 Artemis gap targets (nobile_rim_1 D 0.288, mons_mouton_plateau 0.370; de_gerlache_rim_2 misses at 0.422 vs 0.415). All closures are ties within sensor noise (D <= p95 0.415); only 5 of 211 within the median noise. Arctic hurst median 0.885 vs pool 0.622 (sensor contribution above 60N not testable). Lead recomputed the three Moon D values and the 87/211 count independently: identical.
- Ledger 90,524 facts: gap aggregates (211/1838, 11.5 %, Wilson 10.1-13.0), Moon 3/10, Earth grazing max 18.64 % at 72.5 deg, rehearsal counts, Arctic experiment facts; site/data/arctic.json; texts rendered with no PENDING except repo URL. Verified by the lead.
