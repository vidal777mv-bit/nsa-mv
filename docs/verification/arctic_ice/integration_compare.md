# Arctic integration: hand vs engine, before vs after (2026-11-14)

## 1. Hand prediction (before the run) vs engine (after)

| Figure | Hand | Engine | Match |
| --- | --- | --- | --- |
| Mars places without twin, NASADEM band only | 215 | 215 | yes |
| Mars places without twin, NASADEM + Arctic rock | 84 | 84 | yes |
| Moon sites without twin, NASADEM only | ['de_gerlache_rim_2', 'mons_mouton_plateau', 'nobile_rim_1'] | ['de_gerlache_rim_2', 'mons_mouton_plateau', 'nobile_rim_1'] | yes |
| Moon sites without twin, with Arctic rock | ['de_gerlache_rim_2'] | ['de_gerlache_rim_2'] | yes |
| Arctic features, engine record vs probe measurement (765 windows) | - | max abs diff 0.00e+00 | yes |

## 2. Headline figures, before vs after

| Figure | Before | After |
| --- | --- | --- |
| earth_places_searched | 2,000 | 2,730 |
| mars_gap_places | 211 | 84 |
| mars_gap_pct | 11.5% | 4.6% |
| mars_rehearsable_pct | 88.5% | 95.4% |
| moon_gap_sites | 3 | 1 |
| twin_places | 1,301 | 1,786 |
| new_twin_places | 1,244 | 1,736 |
| known_twin_places | 57 | 50 |
| earth_places_nasadem (new) | - | 1,965 |
| earth_places_arctic (new) | - | 765 |
| earth_places_excluded (new) | - | 1,335 |
| mars_gap_pct_nasadem (new) | - | 11.7% |
| moon_gap_sites_nasadem (new) | - | 3 |

## 3. Per site: the 10 Earth candidates, before vs after

| Site | Same in top 10 | Arctic in top 10 | Top 1 before (D) | Top 1 after (D) | Tied with #1 before -> after |
| --- | --- | --- | --- | --- | --- |
| apollo17_taurus_littrow | 8/10 | 2 | Semnan, Iran (0.058) | Semnan, Iran (0.058) | 10 -> 10 |
| cabeus_b_peak | 2/10 | 8 | Tacna, Peru (0.307) | Tacna, Peru (0.307) | 5 -> 10 |
| de_gerlache_rim_2 | 2/10 | 8 | Tacna, Peru (0.332) | Tacna, Peru (0.332) | 6 -> 10 |
| gale | 6/10 | 4 | Xinjiang, China (0.091) | Nationalparken, Greenland (0.078) | 10 -> 10 |
| haworth | 2/10 | 8 | Ma`an, Jordan (0.372) | Krasnoyarsk, Russia (0.286) | 7 -> 10 |
| im1_odysseus | 2/10 | 8 | Kamchatka, Russia (0.126) | Xizang, China (0.169) | 9 -> 10 |
| im2_athena | 3/10 | 7 | Ash Sharqiyah, Saudi Arabia (0.155) | Ash Sharqiyah, Saudi Arabia (0.155) | 10 -> 10 |
| insight_elysium | 7/10 | 3 | Bari, Somalia (0.056) | Bari, Somalia (0.056) | 10 -> 10 |
| jezero | 7/10 | 3 | Tagant, Mauritania (0.057) | Tagant, Mauritania (0.057) | 10 -> 10 |
| malapert_massif | 1/10 | 9 | Hormozgan, Iran (0.274) | Krasnoyarsk, Russia (0.176) | 6 -> 10 |
| mons_mouton_plateau | 0/10 | 10 | Ma`an, Jordan (0.423) | Nunavut, Canada (0.275) | 6 -> 10 |
| nobile_rim_1 | 2/10 | 8 | Atacama, Chile (0.407) | Nationalparken, Greenland (0.332) | 10 -> 10 |
| nobile_rim_2 | 3/10 | 7 | Antofagasta, Chile (0.229) | Krasnoyarsk, Russia (0.221) | 10 -> 10 |
| oxia_planum | 7/10 | 3 | Namibe, Angola (0.080) | Namibe, Angola (0.080) | 10 -> 10 |
| spirit_columbia | 10/10 | 0 | Béchar, Algeria (0.140) | Béchar, Algeria (0.140) | 10 -> 10 |
| zhurong | 10/10 | 0 | Ouargla, Algeria (0.024) | Ouargla, Algeria (0.024) | 10 -> 10 |

## 4. What can be rehearsed (160 pairs), before vs after

| Line:status | Before | After |
| --- | --- | --- |
| cold:no | 66 | 35 |
| cold:partial | 94 | 125 |
| landing:no | 23 | 34 |
| landing:partial | 24 | 11 |
| landing:yes | 113 | 115 |
