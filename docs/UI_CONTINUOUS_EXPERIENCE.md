# Continuous terrain exploration

## Product contract

One persistent workspace connects target world, Earth candidates, terrain inspection,
explanation and practical limits. Selecting a target loads candidates automatically.
Selecting an Earth candidate updates the globe, terrain, measured-property explanation
and mission slope shares together. Changing candidates does not require navigation.

The visual priority is the paired landscapes. Target selection remains available;
candidates remain reachable; evidence expands in place. Mobile uses the same selection
state and reading order with stacked worlds and an accessible candidate list.

## Inspection contract

Target relief is blue; Earth is green. Alignment shows green terrain plus blue mesh,
with a reading key. Horizontal orbit is unrestricted. Camera elevation can cross the
horizon to inspect the underside; the underside is the reverse of the height surface,
not a model of subsurface geology. Top, profile, underside and reset presets provide
recovery from free orbit. Surface isolation and an explicitly labelled artificial
vertical separation support inspection. Returning separation to zero restores alignment.

## Evidence contract

Explain scored similarities and differences before detailed measurements. Mission
percentages describe valid slopes satisfying a stated limit and baseline; they are
never success probabilities. Keep sources and complete mission evidence accessible.
Gold denotes measured whole-area property similarity. No local match mask can be
inferred from mesh intersections, blending or the whole-area distance score.
Validation failures remain reported with their original results.

## Acceptance

- Pick Mars or Moon target and obtain Earth candidates without an intermediate action.
- Change candidate while keeping both location context and the comparison accessible.
- Inspect overlaid relief from above, the side and below; restore the initial view.
- Read what agrees, what differs and the meaning of each percentage beside the pair.
- Complete the same selection and comparison with keyboard or narrow-screen layout.
- Preserve missing-data gaps, cancelled requests, reduced-motion support and fallback.
