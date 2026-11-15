# Data notes (final state of the data layer, 2026-11-14)

Sources and licences: `REFERENCES.md`. Machine-readable records: `config/sources.json` (42 entries: 23 used, 19 not used with the reason in `use`), `config/regions.json` (56 regions), `config/sites.json` (16 targets), `config/missions.json`, `config/bodies.json`. Manifest: `data/raw/manifest.json` (2,096 entries).

## 1. Targets (config/sites.json, 16)

- Mars, 6: jezero (Perseverance, 2021), gale (Curiosity, 2012), insight_elysium (InSight, 2018), spirit_columbia (Spirit, 2004), zhurong (Zhurong, 2021), all landing_demonstrated; oxia_planum (ExoMars Rosalind Franklin, planned 2030), future_mission.
- Moon, 10: apollo17_taurus_littrow (Apollo 17, 1972, landing_demonstrated); im1_odysseus (2024) and im2_athena (2025), landed_tipped; haworth, malapert_massif, nobile_rim_1, nobile_rim_2, de_gerlache_rim_2, cabeus_b_peak, mons_mouton_plateau, candidate (Artemis III candidate regions, no landing).
- Every target has the 10.9 fields (landing_class, mission, year, outcome_note, outcome_source, center_note). Centres from primary sources: spirit_columbia, apollo17_taurus_littrow, im1_odysseus, im2_athena (intended site), the LROC ROI centres (proxies) and the PGDA DEM/ROI centres (proxies). Secondary: jezero, gale, insight_elysium, zhurong, oxia_planum (center_note says so).
- DEMs: full 5 m files for the five Artemis III PGDA regions; 6 km remote windows (window-clip, original body CRS kept) for the other nine targets. Each window's CRS was read from the file: Mars (2015) sphere 3,396,190 m; Moon sphere 1,737,400 m (LOLA polar stereographic and LROC equirectangular). Disk valid fraction at 4 km: 0.995 to 1.000 for all nine.

## 2. Earth regions (config/regions.json, 56)

- Validation, 20: dev 15 (tenoumer_crater, gosses_bluff, aorounga_crater, harrat_khaybar, payun_matru, al_haruj, namib_sand_sea, badain_jaran, algodones_dunes, fish_river_canyon, cotahuasi_canyon, wadi_mujib, nullarbor_plain, tenere_plain, ustyurt_plateau) and reserved 5 (roter_kamm_crater, cima_volcanic_field, rub_al_khali, charyn_canyon, calansho_desert_serir). All approved after the lead's review (gosses_bluff and cima_volcanic_field on the 2026-11-13 rule: no water, trees or crops; WorldCover share reported, not a criterion). Dev regions have NASADEM and Copernicus GLO-30 at 5 km; reserved regions have NASADEM.
- Dropped, 1: simpson_desert (dunes not resolved at 30 m). Files kept, not used.
- Known analogs, 15: role known_analog, excluded from the search (25 km) and from V2; not measured.
- Blind holdout (v1.3, STANDARDS 10.11), 15: role holdout_v13, status approved, 3 per class (impact_crater: upheaval_dome, tin_bider, ouarkziz; volcanic_field: lunar_crater, pali_aike, harrat_kishb; dune_field: grand_erg_oriental, sharqiya, taklamakan; canyon_valley: talampaya, wadi_rum, buckskin_gulch; plain: tanezrouft, betpak_dala, tanami). Chosen and visually checked by landform only; NASADEM 5 km windows, valid fraction only, no features computed.
- Rejected by the lead's visual check, 5: role holdout_rejected, files kept, not used: holdout_crater_gweni_fada, holdout_dune_erg_chech, holdout_dune_great_victoria, holdout_canyon_monument_valley, holdout_plain_sturt_stony.
- Search pool (STANDARDS 10.2): 2,000 NASADEM windows, half width 4.5 km, valid fraction at least 0.9966 (`data/raw/earth/pool/pool_NNNNN.tif`, index in `index.json`, candidate list `candidates.json`). Pool sha256 values match `data/raw/fetch_log.jsonl`.
- Caches not in the manifest, by design: `data/raw/earth/pool/_worldcover_coarse/*.npy` (2,074 WorldCover coarse arrays, derived from the ESA WorldCover tiles and regenerable) and two cache index files. They are not inputs to any feature.

## 3. Manifest and raw data

- Manifest: 2,096 entries. All exist, sizes match, sha256 matches for every file under 50 MB (checked 2026-11-14). Added in the final audit: the 2,000 pool windows, the 7 extracted Natural Earth files, the 4 De Gerlache ROI files, 2 Gale sidecars, the pool candidate list.
- No `.part` leftovers, no empty folders. Nothing deleted in the audit.
- Largest stored file: the Gale figshare zip (372 MB); the 2.7 GB LOLA 20 m file is read by window only and never stored (STANDARDS 9).

## 4. Search and validation status

- Search pool, validation and holdout runs are not part of this data layer. Validation (v1.2) failed V2 and V2-R; v1.3 is pre-registered (STANDARDS 10.11) and runs once on the 15 holdout regions.

## 5. Doubts (open, for the lead)

- Jezero centre 18.4447, 77.4508: not confirmed by NASA/JPL (Wikipedia rounds to 18.44, 77.45).
- de Gerlache Rim 2: Site11 chosen; SL2 is the other 'de Gerlache rim' DEM.
- Mars landing limit: 15 deg (MER, general) or 30 deg (MSL, at 2-5 m baselines); decision for the lead (`config/missions.json`).
- NASADEM licence: the STAC label 'proprietary' conflicts with the EOSDIS policy; confirm before publication.
- Copernicus DEM: the Art. 6 notice applies to any distribution.
- PGDA citation: product 90 cites Barker et al. 2023 (Planetary Science Journal), not checked by DOI.
- Oxia landing year 2030 from an ESA-affiliated abstract, not an esa.int page; zhurong outcome from abstracts read via snippets.
- Holdout visual checks flagged for the lead: Buckskin Gulch is a narrow slot canyon (class borderline), Betpak-Dala saline depressions, Tanami dune presence. Taklamakan centre moved by the lead to 38.9452, 82.4309.
