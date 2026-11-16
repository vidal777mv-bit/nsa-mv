# Ledger: estado ANTES (2026-11-15)

Respaldo previo a cualquier cambio: `_ui_backups/pre_ledger/` (facts.json, README.md, project_page.md, facts.duckdb,
facts.parquet, ledger_views_before.json con el valor de cada vista).

## Chequeo P-R (tools/check_ledger.py) antes del cambio

```
R1 OK: mission % without a baseline or with a baseline different from the scale must be comparison 'reference' (0 offending rows)
R2 OK: a point footprint never attaches to a region-scale subject (0 offending rows)
R3 OK: every fact has a source_id or a produced_by (0 offending rows)
R4 OK: no two facts with the same (subject_id, property, scale_m) and different values (0 offending rows)
R5 OK: every placeholder resolves to exactly one fact or aggregate (0 offending rows)
R6 OK: every feature fact comes from a record whose measure_key equals the current config's key (features unchanged across config versions; a record produced with a different feature definition is a violation) (0 offending rows)
```
Exit 0: R1 a R6 con 0 filas.

## Conteos

| Medida | Valor |
|---|---|
| Hechos (facts, filas) | 120.290 |
| Vistas nombradas | 71 |
| Sujetos pair distintos (rehearsal) | 248 (160 vigentes + 88 huérfanos) |
| Sujetos earth_window distintos | 4.225 |
| Cifras en site/data/facts.json | 26 |

Hechos por subject_type: body 34, earth_window 75.765, mars_cell 36.922, mission_limit 4, pair 6.696, region 336,
target 468, validation 65.

## Ficheros de data/derived (antes)

| Carpeta | Archivos .json | Vigentes | Huérfanos |
|---|---|---|---|
| data/derived/cards | 408 | 160 | 248 |
| data/derived/rehearsal | 248 (+ run_log.jsonl) | 160 | 88 |
| site/data/cards | 160 | 160 | 0 |
| site/data/rehearsal | 160 | 160 | 0 |

Vigentes = los 160 pares de site/data/rankings (16 sitios x 10 filas, campo `card`).

## Hashes

- site/data/facts.json (sha256): 50de87cdf537bb23f2e5d4ce15694f499681f2af6f66a16234d11554dc4bfda1
- data/derived/facts/facts.duckdb (sha256): 8dcf2db0ba31a3455790f7bcb09486aab0d33e624df401d21151aa45c5bea360
