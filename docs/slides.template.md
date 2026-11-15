# Common Ground: slides (7)

NASA Space Apps Challenge 2026. Challenges: Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars; Interplanetary Survival Guide: Martian Map.

---

## Slide 1. Earth can rehearse part of Mars. Not all of it.

- Earth has a twin within sensor noise for {{agg:mars_rehearsable_pct:f1}}% of measured Mars. For the other {{agg:mars_gap_pct:f1}}% it has none.
- We measured {{agg:n_mars_cells:int}} Mars windows ({{agg:window_diameter_km:f0}} km disks) and searched {{agg:n_pool_windows:int}} bare-ground Earth windows for each.
- Common Ground: pick a site, see what the mission needs, find its Earth twin, and see where Earth runs out.

Visual: the Earth-gap screen ("Where Earth runs out"): the Mars globe with measured windows coloured by whether an Earth twin exists (site/README_screens/earth-default-gap-1920.png, or the ask-gap screen).

Speaker notes: Every analog study starts from a place on Earth. We start from the place on Mars and ask the other way round: does Earth have anything like it? The answer is yes for most measured terrain and no for a part of it, and that part is where robots go first.

---

## Slide 2. Pick a site. See what the mission needs.

- {{agg:n_targets}} sites: {{agg:n_targets_mars}} on Mars, {{agg:n_targets_moon}} on the Moon (including {{agg:n_moon_candidates}} Artemis III candidate regions).
- A game-like map: {{fact:mars:cells_class_2:int}} Mars cells unlocked (measured), {{fact:mars:cells_class_1:int}} to discover, the rest out of reach.
- Land, drive, live. Limits come from NASA documents: Mars landing {{fact:mars_landing:limit_deg:f0}} degrees, Moon landing {{fact:moon_landing:limit_deg:f0}} degrees. Each has its source.

Visual: the destination screen: Mars globe with the "unlocked / to discover" layer and the target cards (site/README_screens/mars-layer-coverage-1920.png and mars-layer-sites-1920.png).

Speaker notes: The team chose to present the atlas as a map you unlock, because most of Mars has no elevation model good enough to measure. The mission needs come from NASA reports, not from us, and each limit shows its source and the baseline it was given at, which is usually none.

---

## Slide 3. Measured evidence, not a picture

- Terrain from NASA and USGS elevation models: slope, hypsometry and roughness scaling on a {{fact:config_v1.3:grid_L_m:f0}} m grid, identical on Mars, the Moon and Earth.
- Mission-proven %: the share of the site within a limit a completed mission demonstrated. Jezero {{fact:jezero:mission_pct_landing:f1}}% for landing, Apollo 17 {{fact:apollo17_taurus_littrow:mission_pct_landing:f1}}%. A reference comparison, not a success probability.
- Light from a closed-form model: the Sun is in the grazing band {{fact:jezero:grazing_pct:f2}}% of the time at Jezero and {{fact:apollo17_taurus_littrow:grazing_pct:f2}}% at Apollo 17.

Visual: the evidence panel of a site page: terrain view, slope-share bars and the mission-proven % with its 100 m baseline note.

Speaker notes: We label every number as measured, derived or published. The mission percentage compares a 100 m slope with limits that were published without a baseline, so it is a reference, not a forecast. IM-2 shows why: {{fact:im2_athena:mission_pct_landing:f0}}% landable at this scale, and it still tipped over in a small crater.

---

## Slide 4. Its Earth twin

- Exact nearest-neighbour search over {{agg:n_pool_windows:int}} Earth windows, on {{agg:n_features_in_distance}} features: slope p95, hypsometric integral, Hurst exponent.
- Jezero's closest twin: {{fact:jezero__pool__pool_00226:analog_place_name}}, D = {{fact:jezero:twin1_D:f3}} (tie flag with the next twin: {{fact:jezero:top1_vs_top2_tie}}).
- Twins closer than sensor noise are shown as tied. The threshold is {{fact:noise_v1.3:tie_p95_rugged:f2}} for rugged terrain.
- {{agg:n_discovery_places:int}} distinct Earth places are a top-three twin of some site or Mars window; {{agg:n_new_places:int}} are outside the well-known analog regions.

Visual: the compare screen: Jezero (blue) and its Earth twin (green) side by side with the same vertical exaggeration, and the cross-section (site/README_screens/compare-1366.png).

Speaker notes: The distance is simple on purpose: three features, each divided by a robust spread measured on the Earth pool, no labels. The search is exact, tested against brute force. "New" only means outside the circles we drew around famous analog regions.

---

## Slide 5. The dossier: rehearse here, cannot teach you

- Rehearse here: landing terrain, driving terrain, cold, low sun. Each line is a rule with a source. Jezero and its Tagant twin: landing {{fact:jezero__jezero__pool__pool_00226:rehearsal_landing_status}}, driving {{fact:jezero__jezero__pool__pool_00226:rehearsal_driving_status}}, cold {{fact:jezero__jezero__pool__pool_00226:rehearsal_cold_status}}, low sun {{fact:jezero__jezero__pool__pool_00226:rehearsal_low_sun_status}}.
- Cannot teach you: gravity (Mars {{fact:mars:gravity_m_s2:f2}} vs Earth {{fact:earth:gravity_m_s2:f2}} m/s2), pressure (Mars {{fact:mars:surface_pressure_pa:g}} Pa vs Earth {{fact:earth:surface_pressure_pa:g}} Pa), temperature, day length, and low sun at the poles (Haworth is in the grazing band {{fact:haworth:grazing_pct:f0}}% of the time; Earth at most {{agg:earth_grazing_max_pct:f1}}%).
- Mars day: {{fact:mars:day_length_h:f1}} h. Moon day: {{fact:moon:day_length_h:f0}} h.

Visual: the mission screen: the five-step dossier, with the "rehearse here" and "cannot teach you" lists for one site-twin pair.

Speaker notes: A twin tells you the ground is alike, not that the day is. We list what Earth cannot teach for every pair, always, from NASA fact sheets. A team can rehearse driving and landing logistics on the twin, and must plan gravity, vacuum and cold some other way.

---

## Slide 6. Where Earth runs out

- Earth gap: Mars terrain where no Earth window is within sensor noise. Result: {{agg:mars_gap_pct:f1}}% of {{agg:mars_cells_measured:int}} measured Mars windows (95% interval {{agg:mars_gap_wilson_lo:f1}} to {{agg:mars_gap_wilson_hi:f1}}%); {{agg:gap_targets}} of {{agg:n_targets}} sites have a gap.
- The Arctic: NASADEM stops at 60 N. Adding Arctic rock from Copernicus (60 to 84 N, ice sheets left out) brings the Mars gap from {{agg:mars_gap_pct_nasadem:f1}}% to {{agg:mars_gap_pct:f1}}%, and the Moon sites without a twin from {{agg:moon_gap_targets_nasadem:int}} to {{agg:moon_gap_targets:int}}.
- Earth pool: {{agg:n_pool_windows_nasadem:int}} NASADEM + {{agg:n_pool_windows_arctic:int}} Arctic rock windows; {{agg:n_pool_excluded:int}} left out, each with its reason. Arctic closures are ties within sensor noise.
- Only {{agg:mars_single_ctx_rate:f3}} of random Mars points have one CTX model covering a full 8 km disk ({{fact:mars:ctx_accepted:int}} accepted of {{fact:mars:ctx_attempts:int}} tries).
- Where there is no twin, rehearsal on Earth is not possible. Our reading: robots go first. That is interpretation, not measurement.

Visual: the Earth-gap map: Mars windows with no twin highlighted, next to the Earth map of pool windows (site/README_screens/ask-gap-1920.png).

Speaker notes: This is the Martian map for the Survival Guide challenge: which terrain people can practise for and which they cannot. The gap is a statement about our Earth pool: NASADEM covers 56 S to 60 N, and Copernicus GLO-30 covers 60 N to 84 N for rock ground only, with windows that have 20% or more ice left out. Adding those Arctic windows is the test: it closes part of the gap, within sensor noise.

---

## Slide 7. Honest by design

- Both pre-registered tests narrowly failed. v1.2: AUC {{fact:v1.2:auc:f3}}, nearest-region {{fact:v1.2:nn_correct:f0}} of {{fact:v1.2:nn_n:f0}}. v1.3 blind holdout ({{agg:n_holdout_regions}} regions): AUC {{fact:v1.3:auc:f3}} (needed {{fact:config_v1.3:auc_min:f2}}), nearest-region {{fact:v1.3:nn_correct:f0}} of {{fact:v1.3:nn_n:f0}} (needed {{fact:config_v1.3:nn_min_correct_v13:f0}}).
- The signal is real (permutation p {{fact:v1.3:perm_p:f3}}, CI {{fact:v1.3:auc_ci_lo:f2}} to {{fact:v1.3:auc_ci_hi:f2}}) but modest. It measures operability, not geological origin.
- Code written with AI assistance (Claude, Anthropic) under our direction. The idea, the unlocked / to-discover atlas and the mission framing are the team's. Every number here is generated from a facts ledger.

Visual: the validation panel of the site (v1.2 and v1.3 results with pass/fail marks), then the credits list: NASA NASADEM, LOLA, LROC, CTX; ESA Copernicus and WorldCover; USGS; Natural Earth.

Speaker notes: We wrote the thresholds before the runs, changed the measure once, ran a fresh blind holdout once, and stopped when it missed. We prefer a measured, modest result over a tuned one. Every figure on these slides is rendered from the ledger, so none of it was typed by hand.
