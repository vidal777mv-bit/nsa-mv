# Arctic integration (2026-11-14): contract and data lineage

Decision (Mario): the Arctic goes INSIDE the analysis; it is the part of Earth that was missing for Mars.
Rules: `config/earth_pool_rules.json` (one place). Map of the chain: `docs/ARCTIC_INTEGRATION_MAP.md`.
Checks that led here: `docs/verification/arctic_ice/` (half of the Arctic closures were ice sheets),
`docs/verification/pool_ice/` (34 of the 2,000 NASADEM windows are ice or mixed).

## Frozen (never changed by this work)
`config/measure.json` (v1.3 features, sigma), `data/derived/validation/noise_v1.3.json` (tie thresholds),
`_common.measure_raw`, the validation results. `calibrate_sigma.py` and `validate.py` are NOT re-run.

## Where every Earth window comes from (lineage)
| Field in `data/raw/earth/pool/index.json` row | Meaning | Comes from |
| --- | --- | --- |
| `id` | `pool_00001..02000` NASADEM; `pool_02001..` Arctic (2000 + probe number) | build_pool_index.py / pool_rules.py |
| `probe_id` | `arc_NNNNN` (Arctic only) | data/raw/earth/arctic_probe/candidates.json |
| `lat`, `lon` | window centre | index (NASADEM) / candidates.json (Arctic) |
| `source_id`, `sensor` | `nasadem`/`nasadem` or `cop_dem_glo30`/`copdem` | config/earth_pool_rules.json bands |
| `path`, `valid_fraction` | elevation clip | index (NASADEM) / arctic_probe clip_log.json |
| `worldcover_share` | original coarse share (kept as it was) | build_pool_index / candidates.json |
| `bare_share_full`, `ice_share` | WorldCover 2021 classes 60/70/100 and 70 over the FULL 4 km disk | pool_rules.py (tile ids listed in data/derived/pool_rules/shares.json) |
| `near_known_analog` | within 25 km of config/regions.json role known_analog | build_pool_index (NASADEM) / pool_rules.py (Arctic) |
| `excluded` | null, or {rule, value, threshold}: ice_share >= 0.2 or bare_share_full < 0.8 | pool_rules.py with config/earth_pool_rules.json |

## Contracts between pieces (one owner each)
1. `pipelines/pool_rules.py` (new): computes shares for all 4,065 windows -> `data/derived/pool_rules/shares.json`;
   writes the Arctic rows and the `excluded` flags into the index (backup `index.json.backup`; idempotent);
   `data/derived/pool_rules/excluded.json` lists every excluded window with its reason.
2. `pipelines/build_measure.py`: measure record `sensor` and `source_id` from the index row; a row with
   `excluded` gives a record with `status = "excluded"` and the reason (every reader already keeps `status == ok`).
   `calibrate_sigma.py`: only `sensor == nasadem`, never excluded rows (guard; it is not re-run anyway).
3. `pipelines/refine_search.py`: candidates with `sensor != nasadem` are not refined (NASADEM does not exist
   above 60N); they stay at their pool centre with `refine_skipped: "no NASADEM above 60N"`.
4. `pipelines/neighbors.py`: Earth gap computed twice. New columns in targets/mars_cells parquet:
   `gap_nasadem`, `d_nearest_nasadem` (NASADEM band only) next to `gap`, `d_nearest` (all bands).
   `export_query.py` carries the new columns.
5. `tools/build_ledger.py`: `source_id` per window (from the measure record); the old Arctic-probe comparison
   (`arctic_rows`) is retired; new views `n_pool_windows_nasadem`, `n_pool_windows_arctic`, `n_pool_excluded`,
   `mars_gap_cells_nasadem`, `mars_gap_pct_nasadem`, `mars_rehearsable_pct_nasadem`, `moon_gap_targets_nasadem`.
   `tools/export_site_facts.py` exposes them with plain definitions.
6. Texts: `config/explain.json` scope, `docs/*.template.md`, `README.template.md`, `pipelines/coverage_grids.py`
   (Arctic class 1 from the Arctic coarse cache), `pipelines/earth_context.py` elevation source per window.

## Run order (Claude, after all pieces pass their tests and the Arctic measurement is complete)
Single backup of `site/data` and the derived stages -> pool_rules -> build_measure (pool) -> search -> refine ->
mission_pct -> earth_context -> mars_atlas -> light -> coverage_grids -> export_viz -> discoveries -> neighbors ->
export_query -> rehearsal -> export_ties -> export_sources -> build_ledger -> export_site_facts -> render_facts ->
check_ledger, check_site_data.

## Validation sample (approved design: census where small, sample where large)
The 211 Mars gap cells (closures must match the rock-only prediction), the 10 Moon sites, the 16 target lists
(before vs after, each change explained), the 34 excluded NASADEM windows (9 were Mars-cell twins), and a visual
check of every Arctic window that enters a top 10.
