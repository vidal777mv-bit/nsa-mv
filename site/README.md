# Common Ground - local terrain experience

## Open

Double-click `OPEN_ATLAS.cmd` in the project root. It starts a local-only server at
http://127.0.0.1:8767/ and opens the default browser. It reuses an existing atlas server.
Python is the existing `.venv/Scripts/python.exe`. No site build is required.

Manual alternative, from the project root:

```powershell
.venv/Scripts/python.exe -m http.server 8767 --directory site --bind 127.0.0.1
```

Three.js 0.160.0 remains pinned through the import map and requires access to its CDN.

## The journey

1. Select Mars or the Moon, then a measured destination.
2. Explore the blue terrain and select **Find Earth analogs**.
3. Select a named Earth location and **Compare terrains**.
4. Use **Side by side**, **Overlay terrains**, or **Swipe**. The swipe divider can be dragged or moved with arrow keys, Home and End.
5. Select a scored property to read its values, similarity criterion and limitations.
6. Open **Show cross-section** to move a west-east cut from north to south.
7. Open the evidence drawers for complete measurements, alignment and limits.

Target terrain is blue; Earth is green. Gold marks whole-area similarity from the existing card, not a local surface-match map. Both terrains use the same pair-specific vertical exaggeration, light and scale. Profiles show metres relative to each disk mean and preserve missing data.

## Data

`js/config.js` contains the single `DATA_BASE` switch: `data/` for real exports or `data/sample/` for labelled examples. Scientific exports, D, tie groups and frozen validation results were not changed by this redesign. Optional coverage/atlas layers still follow `data-availability.json`.

## Implementation

- `js/app.js`: navigation, interrupted selections, retry, content and integration.
- `js/comparison-view.js`: synchronized render modes, camera, profile lines, pause/disposal.
- `js/comparison-profile.js`: display-only alignment and section sampling with nodata.
- `js/comparison-inspector.js`: exported property explanations and SVG section plot.
- `css/expedition.css`: responsive atlas, comparison and inspector composition.

The original `hologram.js` is retained for reference but is no longer imported by the app.

## Verification of the redesign

JavaScript syntax and `tools/check_site_data.py` passed (16 targets, 16 rankings, 160 cards, 140 terrain folders).
`tools/test_ui_redesign.cjs` exercises the controller and real datasets in jsdom with mocked renderers. Both animated and reduced-motion paths pass: Mars/Moon journeys, selection, comparison modes, divider keyboard, profile reset, explanations, validation, six mission controls, rapid selections and a failed request followed by retry.

Run the DOM suite with Node and jsdom 26.1.0. Supply an external jsdom installation through `UI_QA_JSDOM` if it is not on the module path:

```powershell
$env:UI_QA_JSDOM = '<path-to>/node_modules/jsdom'
node --experimental-vm-modules tools/test_ui_redesign.cjs
```

**Verification limit:** browser access was unavailable in the implementation session. Actual WebGL rendering, visual mobile fit, animation quality, GPU performance and a live keyboard walkthrough remain unverified. DOM tests are not a substitute for these checks. Screenshots in `README_screens/` (current UI, real data, 1920 px): `README_screens/mars-layer-sites-1920.png` (default: textured Mars with the named sites), `README_screens/mars-layer-cells-1920.png` (Unlocked cells: warm points), `README_screens/mars-layer-coverage-1920.png` (Coverage: thin teal edges around the to-discover ground). `README_screens/compare-1366.png` and `README_screens/compare-360.png` show the comparison. Phone captures are postponed.

## Recovery and handoff

Original edited files were copied to `_ui_backups/20261114-003147/`, with a SHA-256 manifest. Keep that backup until visual review is accepted. Detailed design intent and remaining local-comparison work: `docs/UI_REDESIGN_HANDOFF.md`. Delivery status: `docs/UI_REDESIGN_DELIVERY.md`.

The working name is provisional. Nothing has been published or committed by this redesign.


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

## Unlocked atlas (STANDARDS 10.13) - 2026-11-14

Files read, each only where `data-availability.json` (per base path) says it exists:

- `coverage/{mars,moon,earth}.json`: the fog. Class 2 (unlocked) stays clear, class 1 (fine elevation exists, not measured yet) is a hatched veil, class 0 (no elevation model fine enough, <= 50 m) is dark. Shares in the Map key are area-weighted by cos(latitude). The file's `notes` (for Mars: the bounding-box upper bound and the 7.7% single-CTX full-disk rate) appear in the legend and as the to-discover tooltip. Coverage loads per body on demand.
- `discoveries.json`: the hero counter (sites unlocked from `targets.json`; Earth places scanned from the v1.2 pool size; `from.mars_cells`; `counts.new`). Its `windows` list gives coordinates and context for every atlas twin, because cell records carry no coordinates.
- `atlas/mars_cells.json`: Mars cells as markers on the Mars globe. Selecting one loads its three Earth twins into the candidate list and Earth globe; the cell card shows its measured properties and mission shares. Cells have no terrain folder, so the 3D comparison covers the 16 named sites.

Earth context (Köppen label, elevation, nearest town with country and distance, sources) and novelty (New / Known analog region) are read from each card and cell twin. Refined offsets (`card.refined`) are shown as "best window within 4 km".

Size: the raw atlas is about 8.4 MB and the discoveries file 1.8 MB; both are sent gzip-compressed by GitHub Pages (about 0.6 MB and 0.1 MB). The atlas is requested after the first paint, but it is still above the 3 MB raw budget of the brief. Trimming the repeated source strings in `windows` and `atlas` would bring it down.

Screenshots in `README_screens/` (current UI, real data, 1920 px unless noted): `README_screens/mars-layer-sites-1920.png` (default: clean Mars with the named sites), `README_screens/mars-layer-cells-1920.png` (Unlocked cells: soft glow), `README_screens/mars-layer-coverage-1920.png` (Coverage: feathered veil), `cell-1920.png` is not current and was removed; `README_screens/compare-1366.png` and `README_screens/compare-360.png` show the comparison (unchanged by this round).

## Ask the atlas and Earth orientation (STANDARDS 10.14 P-Q, 2026-11-14)

The Earth globe opens on 25N 30E. The "Ask the atlas" panel (nav entry, or the panel in the workspace) reads site/data/query only when it is opened: five preset questions with live counts, sliders for the numeric thresholds (nearest town in km, landing share in %), each answer citing its table and columns and its evidence tag. The Earth-gap answer marks the cells on the Mars globe and carries the pool caveat (2,000-window bare-ground pool, 56S-60N; polar regions not included). Screenshots: README_screens/ask-gap-1920.png, README_screens/earth-default-gap-1920.png.
