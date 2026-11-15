# Common Ground — measured Earth analogs for Mars and Moon sites

NASA Space Apps Challenge 2026 · Challenge: *Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars*.
Team **marsvia** · NASA Space Apps Challenge 2026, local event San Salvador, El Salvador ([team page](https://www.spaceappschallenge.org/2026/find-a-team/marsvia/)).

## What it does

Common Ground is a Mars-first atlas. For each Mars or Moon site it measures the terrain from elevation models, searches
{{agg:n_pool_windows:int}} bare-ground windows on Earth for the most similar terrain, and explains **what is similar, how similar, and where
the analogy breaks**. Each site page reads like a page of an interplanetary survival guide: where a lander could set
down, where a rover could drive, and where on Earth a team could rehearse.

- **{{agg:n_targets}} sites**: Mars — Jezero, Gale, InSight (Elysium), Spirit (Gusev), Zhurong (Utopia), Oxia Planum (future
  ExoMars rover site); Moon — Apollo 17, IM-1, IM-2, and {{agg:n_moon_candidates}} Artemis III candidate regions.
- **The same measure on three worlds**: every window is an {{agg:window_diameter_km:f0}} km circle on a {{fact:config_v1.3:grid_L_m:f0}} m grid, computed identically from
  NASA/partner elevation models of Mars (CTX DTMs, {{fact:jezero:native_res_m:f0}} m), the Moon (LOLA {{fact:haworth:native_res_m:f0}} m and
  {{fact:im1_odysseus:native_res_m:f0}} m, LROC NAC {{fact:apollo17_taurus_littrow:native_res_m:f0}} m) and Earth
  (NASADEM {{fact:pool__pool_00226:native_res_m:f1}} m; Copernicus GLO-30 for sensor checks and for the Arctic part of the pool, 60 N to 84 N).
- **Mission-proven terrain %**: share of each site whose slope (100 m baseline) is within limits that completed
  missions demonstrated (Apollo LM/LRV for the Moon; MER/Perseverance for Mars). It is *not* a probability of success.
- **Holographic comparison**: the Mars/Moon terrain is overlaid on its Earth twin at the same scale and vertical
  exaggeration, with layers for slope, ridges and hollows.

## Method (STANDARDS.md has the exact contract)

| Measure (in the score, v1.3) | Meaning for operations |
|---|---|
| `slope_p95_deg` — 95th percentile slope | landing and driving risk |
| `hurst` — roughness scaling over {{fact:config_v1.3:hurst_scale_min_m:int}}–{{fact:config_v1.3:hurst_scale_max_m:int}} m | how bumpiness grows with distance |
| `hi` — robust hypsometric integral | bowl vs. plateau |

Context measures (computed and shown, not scored): grain direction (`coherence`), ridges and hollows (TPI).
Distance D = root-mean-square of the differences in units of σ, with σ = 1.4826·MAD over the {{agg:n_pool_windows:int}}-window Earth pool
(label-free). Twins whose D differs by less than the measured sensor noise are shown as statistically tied.

## Validation — reported as it came out

All thresholds were written down before each test ran.

| Test | v1.2 ({{agg:n_features_total}} → {{agg:n_features_v12}} features) | v1.3 ({{agg:n_features_in_distance}} features), fresh blind holdout of {{agg:n_holdout_regions}} regions |
|---|---|---|
| Features independent (Spearman ≤ {{fact:config_v1.3:redundancy_max_abs_spearman:f2}}) | pass (max {{fact:v1.2:v0_max_abs_rho:f2}}) | pass |
| Separates {{fact:config_v1.3:n_classes:f0}} terrain classes: AUC ≥ {{fact:config_v1.3:auc_min:f2}} | **{{fact:v1.2:auc:f3}} — fail** | **{{fact:v1.3:auc:f3}} — fail** |
| AUC 95% CI above chance | {{fact:v1.2:auc_ci_lo:f2}}–{{fact:v1.2:auc_ci_hi:f2}} — fail | {{fact:v1.3:auc_ci_lo:f2}}–{{fact:v1.3:auc_ci_hi:f2}} — pass |
| Permutation p < {{fact:config_v1.3:p_max:f2}} | {{fact:v1.2:perm_p:f3}} — pass | {{fact:v1.3:perm_p:f3}} — pass |
| Nearest-region class correct | {{fact:v1.2:nn_correct:f0}}/{{fact:v1.2:nn_n:f0}} — fail | {{fact:v1.3:nn_correct:f0}}/{{fact:v1.3:nn_n:f0}} (needed {{fact:config_v1.3:nn_min_correct_v13:f0}}; chance {{fact:v1.3:nn_chance_count:f0}}) — fail |
| Mission control sites ≥ 50% landable | Jezero {{fact:jezero:mission_pct_landing:f1}}%, Gale {{fact:gale:mission_pct_landing:f2}}% | Jezero, Gale, InSight, Spirit, Zhurong, Apollo 17: all pass |

**What it means.** The signal is real and replicated on blind data (AUC ≈ {{fact:v1.3:auc:f2}}, p ≈ {{fact:v1.3:perm_p:f3}} twice) but modest: the
measure captures how *operable* terrain is (slope, roughness, shape), not its geological origin — craters were mistaken
for volcanic fields or canyons, while dunes and plains were recognised. We stopped iterating rather than tune the
measure until it passed. Known limits: slope is measured at 100 m (IM-2 sits on {{fact:im2_athena:mission_pct_landing:f0}}% landable terrain at that scale yet
tipped over in a ~20 m crater); the NASADEM part of the Earth pool (56 S to 60 N) is dominated by the Sahara, Arabia and Central Asia because that is
where bare ground is; mission slope limits are published without a baseline length; flat-terrain sensor noise rests
on {{agg:n_flat_noise_regions}} regions; Earth cannot reproduce reduced gravity, vacuum or thin atmosphere, or radiation.

## Run it

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt   # Windows paths; use bin/ elsewhere
python pipelines/fetch_data.py verify                 # check every source
python pipelines/fetch_data.py earth-clip             # validation regions
python pipelines/build_pool_index.py items            # then coarse, spacing, candidates, clip, index
python pipelines/build_measure.py --kind target,region,pool
python pipelines/calibrate_sigma.py
python pipelines/validate.py --noise                  # --holdout runs once and refuses to rerun
python pipelines/search.py
python pipelines/mission_pct.py
python pipelines/export_viz.py
python tools/check_site_data.py                       # contract check of site/data
python -m http.server 8765 --directory site           # open http://127.0.0.1:8765/
```

Every pipeline accepts `--sample` (sample-first rule) and `--ids`. Tests run one file at a time:
`python -m pytest tests/test_metrics.py`.

## Layout

`config/` frozen settings and sources · `src/analog/` math (`core/`), grid loader, I/O · `pipelines/` one stage per
script · `data/raw` inputs (not versioned) · `data/derived` outputs · `site/` the static web atlas (reads only
`site/data/`) · `STANDARDS.md` the contract · `docs/CHANGELOG.md` every decision, with its numbers.

## Data and credits

NASA: NASADEM, LOLA (PGDA), LROC NAC DTM, CTX DTMs via USGS Astrogeology, NASA Planetary Fact Sheets, Blue Marble,
LROC colour map. Partners and others: Copernicus GLO-30 (ESA), ESA WorldCover, HRSC-MOLA blend (USGS/ESA), Gale CTX
DTMs (figshare, CC BY 4.0), Natural Earth (public domain). Full list with licences and DOIs: `REFERENCES.md`.
No NASA logos are used.

## AI assistance

Concept, design decisions and scientific choices by the team. Code written with AI assistance (Claude by Anthropic;
Codex by OpenAI) under the team's direction; every number reported here was checked by an independent recomputation.
No AI-generated images. Outputs carry a `generated_with` field.

## Licence

Code: MIT. Derived data: CC BY 4.0, subject to the licences of the source data.
