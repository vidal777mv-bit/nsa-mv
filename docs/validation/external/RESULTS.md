# Validacion externa: RESULTADOS

Pre-registro: `docs/validation/external/PREREG.md` (2026-11-15 17:35). Generado por `pipelines/validate_external.py`; no editar a mano.

**Veredicto: insuficiente**. Pares validos: 5 de 6 minimos (5 listados).

- Mediana de percentiles: 26.84
- Wilcoxon unilateral (percentil < 50), p = 0.2188
- Pares dentro del umbral de empate: 5
- Umbrales de empate (run.json): rugged 0.4150, flat 1.1017; corte de clase 3.0 deg
- Pool: 2724 ventanas con D (de 2730 filas)

| Region | Fuente (cita) | Objetivo | D | Percentil | Empate |
|---|---|---|---|---|---|
| holuhraun_iceland | The Holuhraun eruption 'serves as a terrestrial analog for volcanic terrains in Elysium Planitia' (Planetar... | site insight_elysium (mars), 1 celdas, mejor: insight_elysium [flat] | 0.7853 | 18.10 | si (umbral 1.1017) |
| pinacate_gran_desierto | Planetary Science Institute (2024): 'Investigations of Lava Flows in the Pinacate Volcanic Field as Analogu... | set mars_cells (mars), 1838 celdas, mejor: mars_00925 [rugged] | 0.1061 | 37.70 | si (umbral 0.4150) |
| qaidam_basin | The landscape has some similarity with Mars: almost total lack of vegetation and wind-formed landscape (USG... | set mars_cells (mars), 1838 celdas, mejor: mars_01409 [flat] | 0.0874 | 26.84 | si (umbral 1.1017) |
| meteor_crater | Graduate students train to study impact craters on Earth, the Moon, Mars, and other planets. | set mars_cells+moon_targets (moon+mars), 1848 celdas, mejor: mars_01675 [rugged] | 0.0573 | 9.58 | si (umbral 0.4150) |
| kilbourne_hole | NASA Goddard field team: Kilbourne Hole 'a perfect analog site for testing ... to investigate volcanic area... | set mars_cells+moon_targets (moon+mars), 1848 celdas, mejor: mars_00670 [rugged] | 0.2908 | 82.71 | si (umbral 0.4150) |

## Excluidos por regla (PREREG 2)

- mcmurdo_dry_valleys: lat -77.5: fuera de la banda de sensor (NASADEM 56 S-60 N; Copernicus 60-84 N). Pendiente de decision de Mario.
- haughton_crater: La fuente no nombra terreno ni sitio de Marte (regla B).

## Verificacion de segunda forma (Python puro, sin cKDTree)

| Region | D principal | D segunda forma | diff D | Percentil principal | Percentil segunda forma | diff pct |
|---|---|---|---|---|---|---|
| holuhraun_iceland | 0.785300 | 0.785300 | 0.0e+00 | 18.0984 | 18.0984 | 0.0e+00 |
| pinacate_gran_desierto | 0.106145 | 0.106145 | 0.0e+00 | 37.7019 | 37.7019 | 0.0e+00 |
