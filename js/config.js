// Central settings for the Common Ground site.

// ONE base path for every data file the site reads (index files, rankings, cards, terrain).
// Real pipeline exports: "data/". Synthetic demonstration: "data/sample/".
// Change only this line to switch; never mix the two folders.
export const DATA_BASE = "data/";

// Optional globe texture. If the file is absent the globe is a plain coloured sphere.
export const GLOBE_TEXTURE = "assets/globes/earth.jpg";

// The six measures, in display order. Plain-English labels (STANDARDS 10.12 wording).
// displayMin/displayMax only set the bar length on screen; they are not scientific limits.
export const FEATURE_INFO = {
  slope_p95_deg: { label: "Steepness", unit: "deg", displayMin: 0, displayMax: 40, digits: 1 },
  hurst: { label: "Bumpiness across scales", unit: "", displayMin: 0, displayMax: 1.2, digits: 2 },
  hi: { label: "Bowl vs plateau", unit: "", displayMin: 0, displayMax: 1, digits: 2 },
  coherence: { label: "Grain direction", unit: "", displayMin: 0, displayMax: 1, digits: 2 },
  ridge_pct: { label: "Ridges", unit: "%", displayMin: 0, displayMax: 100, digits: 1 },
  valley_pct: { label: "Hollows", unit: "%", displayMin: 0, displayMax: 100, digits: 1 },
};

// Short link labels for source URLs. Any URL not listed here is shown as its host name.
export const SOURCE_LABELS = {
  "https://ntrs.nasa.gov/citations/19720018253": "Apollo LM landing slope (NASA, 1972)",
  "https://ntrs.nasa.gov/citations/19730008090": "Lunar Roving Vehicle slope (NASA TR R-401)",
  "https://marsoweb.nas.nasa.gov/landingsites/mer2003/doc/original.html": "MER landing-site requirements (NASA)",
  "https://pubs.usgs.gov/publication/70047380": "MSL landing-site selection (Golombek et al. 2012)",
  "https://science.nasa.gov/mission/mars-2020-perseverance/rover-components/": "Perseverance rover components (NASA)",
  "https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html": "Planetary Fact Sheet: Earth (NASA)",
  "https://nssdc.gsfc.nasa.gov/planetary/factsheet/moonfact.html": "Planetary Fact Sheet: Moon (NASA)",
  "https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html": "Planetary Fact Sheet: Mars (NASA)",
};

export const BODY_NAMES = { moon: "Moon", mars: "Mars", earth: "Earth" };

export const CLASS_LABELS = {
  landing_demonstrated: "Landing demonstrated",
  landed_tipped: "Landed, tipped",
  candidate: "Candidate",
  future_mission: "Future mission",
};
