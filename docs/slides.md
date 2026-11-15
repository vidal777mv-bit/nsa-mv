# Common Ground: slides (7)

NASA Space Apps Challenge 2026. Challenges: Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars; Interplanetary Survival Guide: Martian Map.

---

## Slide 1. Earth can rehearse part of Mars. Not all of it.

- Earth has a twin within sensor noise for 95.4% of measured Mars. For the other 4.6% it has none.
- We measured 1,838 Mars windows (8 km disks) and searched 2,730 bare-ground Earth windows for each.
- Common Ground: pick a site, see what the mission needs, find its Earth twin, and see where Earth runs out.

Visual: the Earth-gap screen ("Where Earth runs out"): the Mars globe with measured windows coloured by whether an Earth twin exists (site/README_screens/earth-default-gap-1920.png, or the ask-gap screen).

Speaker notes: Every analog study starts from a place on Earth. We start from the place on Mars and ask the other way round: does Earth have anything like it? The answer is yes for most measured terrain and no for a part of it, and that part is where robots go first.

---

## Slide 2. Pick a site. See what the mission needs.

- 16 sites: 6 on Mars, 10 on the Moon (including 7 Artemis III candidate regions).
- A game-like map: 1,621 Mars cells unlocked (measured), 6,988 to discover, the rest out of reach.
- Land, drive, live. Limits come from NASA documents: Mars landing 15 degrees, Moon landing 12 degrees. Each has its source.

Visual: the destination screen: Mars globe with the "unlocked / to discover" layer and the target cards (site/README_screens/mars-layer-coverage-1920.png and mars-layer-sites-1920.png).

Speaker notes: The team chose to present the atlas as a map you unlock, because most of Mars has no elevation model good enough to measure. The mission needs come from NASA reports, not from us, and each limit shows its source and the baseline it was given at, which is usually none.

---

## Slide 3. Measured evidence, not a picture

- Terrain from NASA and USGS elevation models: slope, hypsometry and roughness scaling on a 100 m grid, identical on Mars, the Moon and Earth.
- Mission-proven %: the share of the site within a limit a completed mission demonstrated. Jezero 99.5% for landing, Apollo 17 91.0%. A reference comparison, not a success probability.
- Light from a closed-form model: the Sun is in the grazing band 6.25% of the time at Jezero and 6.23% at Apollo 17.

Visual: the evidence panel of a site page: terrain view, slope-share bars and the mission-proven % with its 100 m baseline note.

Speaker notes: We label every number as measured, derived or published. The mission percentage compares a 100 m slope with limits that were published without a baseline, so it is a reference, not a forecast. IM-2 shows why: 98% landable at this scale, and it still tipped over in a small crater.

---

## Slide 4. Its Earth twin

- Exact nearest-neighbour search over 2,730 Earth windows, on 3 features: slope p95, hypsometric integral, Hurst exponent.
- Jezero's closest twin: Tagant, Mauritania, D = 0.057 (tie flag with the next twin: statistically_tied).
- Twins closer than sensor noise are shown as tied. The threshold is 0.42 for rugged terrain.
- 1,786 distinct Earth places are a top-three twin of some site or Mars window; 1,736 are outside the well-known analog regions.

Visual: the compare screen: Jezero (blue) and its Earth twin (green) side by side with the same vertical exaggeration, and the cross-section (site/README_screens/compare-1366.png).

Speaker notes: The distance is simple on purpose: three features, each divided by a robust spread measured on the Earth pool, no labels. The search is exact, tested against brute force. "New" only means outside the circles we drew around famous analog regions.

---

## Slide 5. The dossier: rehearse here, cannot teach you

- Rehearse here: landing terrain, driving terrain, cold, low sun. Each line is a rule with a source. Jezero and its Tagant twin: landing yes, driving yes, cold no, low sun yes.
- Cannot teach you: gravity (Mars 3.73 vs Earth 9.82 m/s2), pressure (Mars 636 Pa vs Earth 101400 Pa), temperature, day length, and low sun at the poles (Haworth is in the grazing band 50% of the time; Earth at most 18.6%).
- Mars day: 24.7 h. Moon day: 709 h.

Visual: the mission screen: the five-step dossier, with the "rehearse here" and "cannot teach you" lists for one site-twin pair.

Speaker notes: A twin tells you the ground is alike, not that the day is. We list what Earth cannot teach for every pair, always, from NASA fact sheets. A team can rehearse driving and landing logistics on the twin, and must plan gravity, vacuum and cold some other way.

---

## Slide 6. Where Earth runs out

- Earth gap: Mars terrain where no Earth window is within sensor noise. Result: 4.6% of 1,838 measured Mars windows (95% interval 3.7 to 5.6%); 1 of 16 sites have a gap.
- The Arctic: NASADEM stops at 60 N. Adding Arctic rock from Copernicus (60 to 84 N, ice sheets left out) brings the Mars gap from 11.7% to 4.6%, and the Moon sites without a twin from 3 to 1.
- Earth pool: 1,965 NASADEM + 765 Arctic rock windows; 1,335 left out, each with its reason. Arctic closures are ties within sensor noise.
- Only 0.077 of random Mars points have one CTX model covering a full 8 km disk (2,000 accepted of 25,914 tries).
- Where there is no twin, rehearsal on Earth is not possible. Our reading: robots go first. That is interpretation, not measurement.

Visual: the Earth-gap map: Mars windows with no twin highlighted, next to the Earth map of pool windows (site/README_screens/ask-gap-1920.png).

Speaker notes: This is the Martian map for the Survival Guide challenge: which terrain people can practise for and which they cannot. The gap is a statement about our Earth pool: NASADEM covers 56 S to 60 N, and Copernicus GLO-30 covers 60 N to 84 N for rock ground only, with windows that have 20% or more ice left out. Adding those Arctic windows is the test: it closes part of the gap, within sensor noise.

---

## Slide 7. Honest by design

- Both pre-registered tests narrowly failed. v1.2: AUC 0.693, nearest-region 2 of 5. v1.3 blind holdout (15 regions): AUC 0.695 (needed 0.70), nearest-region 6 of 15 (needed 7).
- The signal is real (permutation p 0.007, CI 0.51 to 0.92) but modest. It measures operability, not geological origin.
- Code written with AI assistance (Claude, Anthropic) under our direction. The idea, the unlocked / to-discover atlas and the mission framing are the team's. Every number here is generated from a facts ledger.

Visual: the validation panel of the site (v1.2 and v1.3 results with pass/fail marks), then the credits list: NASA NASADEM, LOLA, LROC, CTX; ESA Copernicus and WorldCover; USGS; Natural Earth.

Speaker notes: We wrote the thresholds before the runs, changed the measure once, ran a fresh blind holdout once, and stopped when it missed. We prefer a measured, modest result over a tuned one. Every figure on these slides is rendered from the ledger, so none of it was typed by hand.
