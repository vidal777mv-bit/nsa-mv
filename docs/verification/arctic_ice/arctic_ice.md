# Arctic ice check: are the closing windows rock or ice?

Script: `arctic_ice_classes.py` (class shares, re-read of the WorldCover tiles with classes kept) and `arctic_ice_closure.py` (this file + JSON). Figures: `closing_contact.png`, `pool_contact.png`.

Class rule: ROCK share70 < 0.2; MIXED 0.2 to 0.5; ICE >= 0.5. Share = WorldCover class 70 / all pixels within 4 km. Wilson 95% on the share of each class.

## Counts (ROCK | MIXED | ICE)

| Set | n | ROCK | MIXED | ICE |
|---|---|---|---|---|
| 39 closing windows | 39 | 17 (44%, 29-59) | 2 (5%, 1-17) | 20 (51%, 36-66) |
| 40 sample of the other 361 (seed 20261114) | 40 | 10 (25%, 14-40) | 3 (8%, 3-20) | 27 (68%, 52-80) |
| all 400 measured (extra) | 400 | 144 (36%, 31-41) | 13 (3%, 2-5) | 243 (61%, 56-65) |

## Mars gap cells closed (211 gap cells, tie threshold per cell)

| Windows used | closed | share | Wilson 95% |
|---|---|---|---|
| all 400 | 87 | 41.2% | 34.8-48.0% |
| ROCK only (144 windows) | 64 | 30.3% | 24.5-36.8% |

Closures lost when ICE/MIXED windows are removed: 23.

## Pool-rule note

The stored candidate share (`measures.json` worldcover_share) tests only a +-5 px box around the centre (`WIN_PX` in build_pool_index). At these latitudes the 4 km disk is wider than that box in longitude, so the stored share differs from the full-disk share in 157 of 400 windows (max 0.1555). The replica of the box rule reproduces the stored value in 387 of 400 windows checked. The class rule here uses the full disk.

## 39 closing windows (sorted by share70)

| arctic_id | lat | lon | class | s70 | s60 | s100 | disk px | slope_p95 |
|---|---|---|---|---|---|---|---|---|
| arc_00163 | 61.87 | -47.93 | ICE | 1.0 | 0.0 | 0.0 | 88 | 6.97 |
| arc_00006 | 65.77 | -38.93 | ICE | 1.0 | 0.0 | 0.0 | 100 | 5.73 |
| arc_00297 | 75.07 | -81.23 | ICE | 1.0 | 0.0 | 0.0 | 160 | 6.92 |
| arc_00313 | 77.77 | -65.93 | ICE | 1.0 | 0.0 | 0.0 | 192 | 7.88 |
| arc_00050 | 80.77 | -75.23 | ICE | 1.0 | 0.0 | 0.0 | 252 | 6.7 |
| arc_00316 | 80.77 | 61.87 | ICE | 1.0 | 0.0 | 0.0 | 252 | 8.77 |
| arc_00244 | 74.77 | -82.13 | ICE | 1.0 | 0.0 | 0.0 | 156 | 12.36 |
| arc_00361 | 77.77 | -66.23 | ICE | 1.0 | 0.0 | 0.0 | 192 | 10.18 |
| arc_00225 | 75.97 | 62.77 | ICE | 1.0 | 0.0 | 0.0 | 168 | 4.52 |
| arc_00331 | 70.87 | -73.13 | ICE | 1.0 | 0.0 | 0.0 | 128 | 15.07 |
| arc_00162 | 81.07 | -20.93 | ICE | 0.9394 | 0.0492 | 0.0114 | 264 | 11.28 |
| arc_00388 | 79.87 | -94.13 | ICE | 0.9237 | 0.0339 | 0.0339 | 236 | 26.04 |
| arc_00065 | 81.97 | -42.23 | ICE | 0.9075 | 0.0548 | 0.0377 | 292 | 18.83 |
| arc_00013 | 80.77 | -17.93 | ICE | 0.9048 | 0.0913 | 0.004 | 252 | 34.29 |
| arc_00172 | 81.97 | -71.93 | ICE | 0.9041 | 0.0959 | 0.0 | 292 | 29.17 |
| arc_00189 | 78.97 | -78.23 | ICE | 0.838 | 0.0787 | 0.0833 | 216 | 35.01 |
| arc_00287 | 79.87 | 98.77 | ICE | 0.7373 | 0.2585 | 0.0042 | 236 | 8.61 |
| arc_00191 | 79.87 | -19.13 | ICE | 0.7034 | 0.1822 | 0.089 | 236 | 29.69 |
| arc_00105 | 81.97 | -44.03 | ICE | 0.5616 | 0.1336 | 0.2123 | 292 | 33.33 |
| arc_00261 | 81.97 | -35.03 | ICE | 0.5205 | 0.274 | 0.1267 | 292 | 30.83 |
| arc_00067 | 69.97 | -69.23 | MIXED | 0.3167 | 0.275 | 0.2583 | 120 | 39.05 |
| arc_00186 | 76.87 | -87.23 | MIXED | 0.2333 | 0.4833 | 0.2833 | 180 | 10.15 |
| arc_00214 | 81.97 | -53.03 | ROCK | 0.1507 | 0.3151 | 0.3288 | 292 | 26.92 |
| arc_00180 | 80.77 | 48.07 | ROCK | 0.1468 | 0.4603 | 0.3294 | 252 | 5.85 |
| arc_00089 | 72.07 | -78.23 | ROCK | 0.1176 | 0.3456 | 0.5294 | 136 | 26.09 |
| arc_00051 | 74.77 | -21.23 | ROCK | 0.0769 | 0.4423 | 0.4615 | 156 | 31.47 |
| arc_00146 | 67.87 | -68.03 | ROCK | 0.0648 | 0.5833 | 0.2407 | 108 | 14.35 |
| arc_00041 | 81.97 | -65.03 | ROCK | 0.0137 | 0.7671 | 0.2158 | 292 | 27.03 |
| arc_00153 | 78.97 | -82.13 | ROCK | 0.0093 | 0.338 | 0.5556 | 216 | 32.77 |
| arc_00385 | 72.97 | -81.23 | ROCK | 0.0 | 0.0714 | 0.8 | 140 | 24.16 |
| arc_00099 | 71.77 | -82.13 | ROCK | 0.0 | 0.0625 | 0.9375 | 128 | 18.58 |
| arc_00264 | 71.77 | 107.77 | ROCK | 0.0 | 0.0 | 1.0 | 128 | 10.76 |
| arc_00257 | 81.97 | -59.93 | ROCK | 0.0 | 0.8733 | 0.0 | 292 | 12.98 |
| arc_00349 | 80.77 | -26.03 | ROCK | 0.0 | 0.0952 | 0.8968 | 252 | 28.79 |
| arc_00378 | 68.77 | 93.97 | ROCK | 0.0 | 0.0 | 0.9018 | 112 | 20.98 |
| arc_00323 | 65.77 | -15.23 | ROCK | 0.0 | 0.27 | 0.62 | 100 | 14.13 |
| arc_00187 | 78.97 | -66.23 | ROCK | 0.0 | 0.3935 | 0.4907 | 216 | 26.97 |
| arc_00122 | 69.07 | 94.87 | ROCK | 0.0 | 0.2768 | 0.7232 | 112 | 17.49 |
| arc_00227 | 64.87 | -73.13 | ROCK | 0.0 | 0.1042 | 0.8333 | 96 | 8.84 |
