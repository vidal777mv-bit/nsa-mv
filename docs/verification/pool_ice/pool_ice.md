# Pool ice check: are the 2000 pool windows rock or ice?

Script: `pool_ice_classes.py` (full). Same method as the Arctic check (WorldCover 2021 class 70, 4 km disk, full-disk denominator). Rule: ROCK share70 < 0.2; MIXED 0.2 to 0.5; ICE >= 0.5. Wilson 95% per class.

## Rates by latitude band (ICE | MIXED | ROCK, count (rate, Wilson 95%))

| banda | n | ICE | MIXED | ROCK |
|---|---|---|---|---|
| <0 | 104 | 2 (2%, 1-7) | 0 (0%, 0-4) | 102 (98%, 93-99) |
| 0-30 | 1142 | 1 (0%, 0-0) | 0 (0%, 0-0) | 1141 (100%, 100-100) |
| 30-45 | 689 | 10 (1%, 1-3) | 11 (2%, 1-3) | 668 (97%, 95-98) |
| 45-60 | 65 | 7 (11%, 5-21) | 3 (5%, 2-13) | 55 (85%, 74-91) |
| ALL | 2000 | 20 (1%, 1-2) | 14 (1%, 0-1) | 1966 (98%, 98-99) |

Tile errors: 0.

## Non-ROCK windows (ICE or MIXED)

| id | lat | lon | band | s70 | class | twins (discoveries) | top-3 of target (effective ranking) |
|---|---|---|---|---|---|---|---|
| pool_01622 | 36.07 | 90.97 | 30-45 | 1.0000 | ICE | Mars atlas cell | none |
| pool_01990 | 57.07 | -132.23 | 45-60 | 1.0000 | ICE | Mars atlas cell | none |
| pool_00002 | -49.13 | -73.13 | <0 | 0.9833 | ICE | none | none |
| pool_01832 | 42.07 | 79.87 | 30-45 | 0.9808 | ICE | none | none |
| pool_01568 | 34.87 | 77.77 | 30-45 | 0.9792 | ICE | none | none |
| pool_01610 | 36.07 | 75.07 | 30-45 | 0.9792 | ICE | none | none |
| pool_01998 | 59.77 | -138.23 | 45-60 | 0.9750 | ICE | none | none |
| pool_00006 | -46.13 | -73.13 | <0 | 0.9667 | ICE | Mars atlas cell | none |
| pool_01995 | 58.87 | -134.03 | 45-60 | 0.9625 | ICE | Mars atlas cell | none |
| pool_01688 | 38.77 | 72.07 | 30-45 | 0.8846 | ICE | none | none |
| pool_01543 | 33.97 | 75.97 | 30-45 | 0.8542 | ICE | none | none |
| pool_01997 | 59.77 | -150.23 | 45-60 | 0.8125 | ICE | none | none |
| pool_01957 | 45.97 | 7.87 | 45-60 | 0.7833 | ICE | Mars atlas cell | none |
| pool_01719 | 39.07 | 74.77 | 30-45 | 0.7500 | ICE | none | none |
| pool_01987 | 56.77 | -132.23 | 45-60 | 0.6750 | ICE | none | none |
| pool_01661 | 37.87 | 72.07 | 30-45 | 0.6731 | ICE | none | none |
| pool_01833 | 42.07 | 81.07 | 30-45 | 0.6346 | ICE | none | none |
| pool_01109 | 27.97 | 87.07 | 0-30 | 0.6042 | ICE | none | none |
| pool_01981 | 50.77 | -116.93 | 45-60 | 0.5938 | ICE | none | none |
| pool_01717 | 39.07 | 72.07 | 30-45 | 0.5577 | ICE | none | none |
| pool_01310 | 30.07 | 81.07 | 30-45 | 0.4167 | MIXED | none | none |
| pool_01984 | 54.07 | -128.03 | 45-60 | 0.3971 | MIXED | none | none |
| pool_01591 | 35.77 | 79.87 | 30-45 | 0.3750 | MIXED | none | none |
| pool_01982 | 51.07 | -124.13 | 45-60 | 0.3750 | MIXED | none | none |
| pool_01689 | 38.77 | 72.97 | 30-45 | 0.3654 | MIXED | Mars atlas cell | none |
| pool_01716 | 39.07 | 71.77 | 30-45 | 0.3654 | MIXED | none | none |
| pool_01892 | 43.87 | 84.07 | 30-45 | 0.3333 | MIXED | Mars atlas cell | none |
| pool_01891 | 43.87 | 83.77 | 30-45 | 0.3167 | MIXED | none | none |
| pool_01801 | 41.77 | 79.87 | 30-45 | 0.3077 | MIXED | none | none |
| pool_01660 | 37.87 | 71.77 | 30-45 | 0.2885 | MIXED | Mars atlas cell | none |
| pool_01718 | 39.07 | 73.87 | 30-45 | 0.2885 | MIXED | none | none |
| pool_01985 | 55.87 | -127.13 | 45-60 | 0.2361 | MIXED | none | none |
| pool_01611 | 36.07 | 76.87 | 30-45 | 0.2292 | MIXED | Mars atlas cell | none |
| pool_01638 | 36.97 | 73.87 | 30-45 | 0.2292 | MIXED | none | none |

## Twin check: ranking top-3 vs discoveries (per target)

| target | match |
|---|---|
| apollo17_taurus_littrow | yes |
| cabeus_b_peak | yes |
| de_gerlache_rim_2 | yes |
| gale | yes |
| haworth | yes |
| im1_odysseus | yes |
| im2_athena | yes |
| insight_elysium | yes |
| jezero | yes |
| malapert_massif | yes |
| mons_mouton_plateau | yes |
| nobile_rim_1 | yes |
| nobile_rim_2 | yes |
| oxia_planum | yes |
| spirit_columbia | yes |
| zhurong | yes |
