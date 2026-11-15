// Common Ground controller: routing between the screens, data flow, and wiring of the controls.
import { DATA_BASE, FEATURE_INFO, BODY_NAMES, CLASS_LABELS } from "./config.js";
import { loadIndex, getJSON, loadTerrain, placeName, analogCode } from "./data.js";
import { ComparisonView } from "./comparison-view.js";
import { renderInspector, renderProfile } from "./comparison-inspector.js";
import { GlobeView, EARTH_MARK_COLOUR } from "./globe.js";
import { createAsk } from "./ask.js";
import { h, fmt, latlon, sampleTag, sourceLink } from "./dom.js";
import { renderFeatures, renderMissionBlock, renderValidation, renderControls, renderContext, refinedSummary, noveltyBadge, scoringKeys } from "./panels.js";
import { renderSite, renderTwinPlace, fillLight, fillTwinLight, fillRehearsal, fillGap, fillHero, loadMarsGapCoords } from "./dossier.js";

const $ = (sel) => document.querySelector(sel);
let reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const SCREENS = ["destination", "region", "scan", "twin", "how", "about"];
const TITLES = {
  destination: "Choose your destination",
  region: "Explore the terrain",
  scan: "Scan Earth",
  twin: "Compare terrains",
  how: "How we know",
  about: "About",
};
// Mission controls (STANDARDS 10.3): both reference sites must have at least 50% of their circle within the limit.
const CONTROL_IDS = ["jezero", "gale", "insight_elysium", "spirit_columbia", "zhurong", "apollo17_taurus_littrow"];

const S = {
  viz: null,
  validation: null,
  targets: [],            // targets.json entries
  isSample: false,
  body: "mars",
  homeLayer: "sites",
  earthLayer: "sites",
  homeGlobe: null,
  bodies: null,
  missions: null,
  regionalCells: null,
  regionalVisible: false,
  selectionToken: 0,
  coverage: {},          // coverage/<body>.json (STANDARDS 10.13): undefined = not requested, null = absent
  atlasCells: undefined,  // atlas/mars_cells.json: undefined = not requested, null = absent
  discoveries: null,      // discoveries.json or null
  windowById: new Map(),  // Earth windows from discoveries.json: coordinates and context for atlas twins
  flags: {},              // data-availability.json entry for DATA_BASE
  cell: null,             // the Mars atlas cell loaded into the workspace, or null
  cellIndex: null,        // its index in atlasCells
  target: null,           // the chosen target entry (or a Mars atlas cell in cell mode)
  analogs: [],            // twin rows of the chosen target, in rank order
  pinToAnalog: [],        // Scan Earth pin index -> analog index (only twins with coordinates get a pin)
  regionCard: null,       // one comparison card of the target (target-side values and mission %)
  selected: null,         // analog index chosen on the scan screen, or null
  twinEntry: null,        // the twin row opened on the twin screen
  card: null,             // the card currently shown (twin and mission read it)
  loadedTwin: null,       // card path currently loaded in the hologram
  globe: null,
  holo: null,
  regionView: null, regionLoaded: null, mode: "split", property: null, profileOpen: false,
  levelled: true,         // comparison orientation: true = Levelled (default), false = True orientation
  tilt: undefined,        // site/data/tilt.json: undefined = not requested yet, null = absent
  routeToken: 0, twinToken: 0, currentScreen: null, routeAnimation: null,
  toggles: { slope: false, ridges: false, valleys: false },
  controls: null,         // mission controls, loaded when How we know opens
};

function showError(err) {
  const box = $("#globalError");
  box.hidden = false;
  box.replaceChildren(h("strong", {}, "This view could not be loaded. "), h("span", {}, err?.message || String(err)),
    h("button", {type: "button", class: "btn ghost", onclick: () => { box.hidden = true; (S.retry || route)(); }}, "Try again"));
  status("");
}
function status(message) {
  $("#routeStatus").textContent = message;
  $("#routeStatus").hidden = !message;
}
function goto(name) {
  if (location.hash === "#" + name) route();
  else location.hash = name;
}
function updateJourney(name) {
  const step = ["destination", "region"].includes(name) ? "01 / EXPLORE" : name === "scan" ? "02 / FIND AN ANALOG" : name === "twin" ? "03 / COMPARE" : "EVIDENCE";
  $("#journeyStep").textContent = step;
  $("#journeyLocation").textContent = S.target ? `${BODY_NAMES[S.target.body]} / ${S.target.name}${S.twinEntry && name === "twin" ? " / " + S.twinEntry.name : ""}` : "A field atlas of other worlds";
  $("#journeyBack").hidden = name === "destination";
  for (const a of document.querySelectorAll("[data-nav]")) {
    const active = a.dataset.nav === name || name === "region" && a.dataset.nav === "destination";
    if (active) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    const blocked = a.dataset.nav === "scan" && !S.target || a.dataset.nav === "twin" && !S.twinEntry;
    a.setAttribute("aria-disabled", String(!!blocked));
  }
}
const inWorkspace = () => !["how","about"].includes(S.currentScreen);
async function route() {
  const token=++S.routeToken;
  let name=location.hash.slice(1);
  if(name==="ask"){const p=$("#askPanel");if(p){p.open=true;p.scrollIntoView?.({block:"start"});}name="destination";}
  if(!SCREENS.includes(name)) name="destination";
  const workspace=!["how","about"].includes(name);
  const wasWorkspace=S.currentScreen && inWorkspace();
  S.currentScreen=name;
  const host=$("#explorationWorkspace");if(host)host.hidden=!workspace;
  for(const key of SCREENS) {
    const active=workspace ? !["how","about","region"].includes(key) : key===name;
    $("#screen-"+key).classList.toggle("active",active);
  }
  S.homeGlobe?.stop();S.globe?.stop();S.holo?.stop();S.regionView?.stop();
  updateJourney(name);
  $("#journeyStep").textContent=workspace ? "EXPLORE / COMPARE / UNDERSTAND" : "EVIDENCE";
  $("#journeyBack").hidden=workspace;
  document.title=workspace ? "Two worlds, one terrain / Common Ground" : `${TITLES[name]} / Common Ground`;
  try {
    if(workspace) {
      renderTargets();await enterScan();
      $("#twinNeeds").hidden=true;
      if(S.twinEntry) {await enterTwin();enterMission();}
      else {$("#twinBody").hidden=true;}
      if(!wasWorkspace && S.target) S.homeGlobe?.setSelected(targetsForBody().findIndex(t=>t.id===S.target.id));
    } else {S.selectionToken++;await ENTER[name]();}
  } catch(err) {if(token===S.routeToken)showError(err);}
  if(token!==S.routeToken)return;
  status("");
  if(!workspace) {$("#h-"+name)?.focus({preventScroll:true});window.scrollTo({top:0,behavior:"instant"});}
  else if(name==="twin" && S.card) $("#screen-twin")?.scrollIntoView?.({behavior:reduced?"instant":"smooth",block:"start"});
}

const ENTER = {
  destination: async () => renderTargets(),
  region: async () => enterRegion(),
  scan: async () => enterScan(),
  twin: async () => enterTwin(),
  how: async () => enterHow(),
  about: async () => {},
};

// ---------------------------------------------------------------- names, ties and novelty

// Twins are named by place (analog_place.name) and shown with their search id underneath.
function twinTie(row) {
  if (row.tie_group === null || row.tie_group === undefined) return "Not tied with another twin";
  const others = S.analogs.filter((a) => a.tie_group === row.tie_group).length - 1;
  if (others <= 0) return "Not tied with another twin";
  return `Tied with ${others} other${others === 1 ? "" : "s"} (within sensor noise)`;
}

function tieNoteFor(row, list) {
  if (row.tie_group === null || row.tie_group === undefined) return "Not tied with another twin";
  const others = list.filter((a) => a.tie_group === row.tie_group).length - 1;
  return others <= 0 ? "Not tied with another twin" : `Tied with ${others} other${others === 1 ? "" : "s"} (within sensor noise)`;
}

// ---------------------------------------------------------------- coverage, legend, counter

// Share of the sphere per coverage class, area-weighted by cos(latitude) of each 1-degree row.
function coverageShares(cov) {
  if (!cov || !Array.isArray(cov.grid) || cov.grid.length !== cov.width * cov.height) return null;
  const W = cov.width;
  const H = cov.height;
  const sums = { 0: 0, 1: 0, 2: 0 };
  let total = 0;
  for (let r = 0; r < H; r++) {
    const w = Math.cos(((90 - r - 0.5) * Math.PI) / 180);
    for (let c = 0; c < W; c++) {
      const k = cov.grid[r * W + c];
      if (sums[k] === undefined) continue;
      sums[k] += w;
      total += w;
    }
  }
  if (!total) return null;
  return { unlocked: (100 * sums[2]) / total, todo: (100 * sums[1]) / total, fog: (100 * sums[0]) / total };
}

function renderLegend() {
  const cov = S.coverage[S.body] || null;
  const sh = coverageShares(cov);
  const share = (k) => (sh ? `${fmt(sh[k], 1)}% of the sphere` : "not in this export yet");
  $("#shareUnlocked").textContent = share("unlocked");
  $("#shareTodo").textContent = share("todo");
  $("#shareFog").textContent = share("fog");
  const notes = coverageNotes(cov);
  $("#todoRow").title = notes.join(" ");
  $("#coverageNotes").replaceChildren(...notes.map((n) => h("p", { class: "note" }, n)));
  $("#coverageNotes").hidden = !notes.length;
  $("#cellLegend").hidden = !(S.body === "mars" && Array.isArray(S.atlasCells) && S.atlasCells.length);
}

// Coverage notes from the export: a string, a list, or the object written by the pipeline
// (class1_is, single_ctx_full_disk_rate). Shown in the legend and as the tooltip of the to-discover row.
function coverageNotes(cov) {
  const n = cov && cov.notes;
  if (!n) return [];
  if (typeof n === "string") return [n];
  if (Array.isArray(n)) return n.filter((x) => typeof x === "string");
  const out = [];
  const rate = n.single_ctx_full_disk_rate;
  if (rate && Number.isFinite(rate.value)) out.push(`${fmt(100 * rate.value, 1)}% of Mars has a single CTX DTM covering a full 8 km disk.`);
  if (typeof n.class1_is === "string") out.push(`${n.class1_is.charAt(0).toUpperCase()}${n.class1_is.slice(1)}.`);
  if (typeof n.class2_is === "string") out.push(n.class2_is);
  return out;
}

const count = (n) => Number(n).toLocaleString("en-US");

// Atlas counter in the hero: every number is read from the exports, never typed in.
function renderDiscoveries() {
  const el = $("#atlasCounter");
  const sites = S.targets.filter((t) => t.unlocked).length;
  const scanned = S.facts?.figures?.earth_places_searched?.value ?? S.validation?.["v1.2"]?.V0?.n_pool;
  const cells = S.discoveries?.from?.mars_cells ?? (Array.isArray(S.atlasCells) ? S.atlasCells.length : null);
  const news = S.discoveries?.place_counts?.new;   // by Earth place: a place that is a twin of several sites counts once
  const pieces = [
    `${count(sites)} measured sites unlocked`,
    Number.isFinite(scanned) ? `${count(scanned)} Earth places scanned` : null,
    Number.isFinite(cells) ? `${count(cells)} Mars places measured` : null,
    Number.isFinite(news) ? `${count(news)} new Earth twins discovered` : null,
  ].filter(Boolean);
  el.replaceChildren(
    ...pieces.flatMap((p, i) => (i ? [h("span", { class: "sep", "aria-hidden": "true" }, " · "), p] : [p])),
    ...(S.isSample ? [" ", sampleTag()] : []));
}

// Optional atlas data is requested only where data-availability.json says it exists (never a 404).
async function ensureCoverage(body) {
  if (S.coverage[body] !== undefined) return S.coverage[body];
  if (!S.flags.coverage || !S.flags.coverage[body]) { S.coverage[body] = null; return null; }
  try { S.coverage[body] = await getJSON(`coverage/${body}.json`); }
  catch (_) { S.coverage[body] = null; }
  return S.coverage[body];
}

async function ensureAtlas() {
  if (S.atlasCells !== undefined) return S.atlasCells;
  if (!S.flags.atlas) { S.atlasCells = null; return null; }
  try {
    const cells = await getJSON("atlas/mars_cells.json");
    S.atlasCells = Array.isArray(cells) ? cells : (cells.cells || null);
  } catch (_) { S.atlasCells = null; }
  renderDiscoveries();
  refreshHome();
  return S.atlasCells;
}

const NO_CELLS = [];

// Removes the canvas and labels of a globe that could not start, keeping its layer controls.
function clearStage(el) {
  for (const child of [...el.children]) {
    if (!child.classList.contains("layer-stack") && !child.classList.contains("layer-switch")) child.remove();
  }
  return el;
}

// Home globe layers: clean by default (named sites only); cells and coverage are opened by the visitor.
const HOME_LAYER_NOTES = {
  sites: "Named sites in blue. Open a layer for unlocked cells or coverage; the full key is under the globe.",
  cells: "Warm points: unlocked Mars cells. Zoom in to select one and load its Earth twins.",
  coverage: "Teal outline: fine elevation exists, not measured yet. Full key: Map key & coverage.",
};

function setHomeLayer(layer) {
  if (layer === "cells" && (S.body !== "mars" || !Array.isArray(S.atlasCells))) layer = "sites";
  S.homeLayer = layer;
  S.homeGlobe?.setLayer?.(layer);
  document.querySelectorAll("[data-home-layer]").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.homeLayer === layer));
    if (b.dataset.homeLayer === "cells") b.disabled = S.body !== "mars" || !Array.isArray(S.atlasCells);
  });
  $("#homeLayerNote").textContent = HOME_LAYER_NOTES[layer];
}

// Mars first: the home globe always shows where Earth runs out (coral), read from the same Mars cell table as the headline.
function paintHomeGap() {
  if (S.body !== "mars") { S.homeGlobe?.setMarks?.(null); return; }
  loadMarsGapCoords().then((coords) => { if (S.body === "mars") S.homeGlobe?.setMarks?.(coords, undefined, 9); }).catch(() => {});
}

function setEarthLayer(layer) {
  S.earthLayer = layer;
  S.globe?.setLayer?.(layer);
  document.querySelectorAll("[data-earth-layer]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.earthLayer === layer)));
}

// Label of the named site under the pointer, focused in the list, or chosen.
// Layout B (Mario 2026-11-15): a line from the chosen site on the home globe to the small Earth inset.
function updateLink(x, y, visible, gi) {
  const seg = $("#linkSeg"), svg = $("#linkLine"), inset = $("#earthInset"), stage = $("#homeGlobe");
  if (!seg || !svg || !inset || !stage) return;
  const list = targetsForBody();
  const sel = S.target ? list.findIndex((t) => t === S.target || (t.id && t.id === S.target.id)) : -1;
  if (sel >= 0 && gi === sel) S.linkFrom = visible ? { x, y } : null;
  if (sel < 0) S.linkFrom = null;
  const show = !!S.linkFrom && inset.offsetParent !== null;
  svg.style.opacity = show ? "1" : "0";
  if (show && !S.linkShown) { seg.classList.remove("draw"); void svg.getBoundingClientRect(); seg.classList.add("draw"); }
  S.linkShown = show;
  if (!show) return;
  const scene = stage.parentElement.getBoundingClientRect(), st = stage.getBoundingClientRect(), r = inset.getBoundingClientRect();
  const x1 = st.left - scene.left + S.linkFrom.x, y1 = st.top - scene.top + S.linkFrom.y;
  const cx = r.left - scene.left + r.width / 2, cy = r.top - scene.top + r.height / 2;
  const dx = x1 - cx, dy = y1 - cy, d = Math.hypot(dx, dy) || 1, rad = r.width / 2;
  seg.setAttribute("x1", x1); seg.setAttribute("y1", y1);
  seg.setAttribute("x2", cx + dx / d * rad); seg.setAttribute("y2", cy + dy / d * rad);
  const grad = $("#linkGrad");
  if (grad) { grad.setAttribute("x1", x1); grad.setAttribute("y1", y1); grad.setAttribute("x2", cx); grad.setAttribute("y2", cy); }
}

function placeHomeLabel(x, y, visible, gi) {
  updateLink(x, y, visible, gi);
  const el = $("#homePinLabel");
  if (!el) return;
  const t = targetsForBody()[gi];
  if (!t || !visible) { el.hidden = true; return; }
  el.hidden = false;
  el.style.transform = `translate(${x}px, ${y}px) translate(-50%, calc(-100% - 10px))`;
  if (el.dataset.key !== String(gi) || el.dataset.body !== S.body) {
    el.dataset.key = String(gi);
    el.dataset.body = S.body;
    el.replaceChildren(h("strong", {}, t.name));
  }
}

// Earth coverage is not a terrain-analog map: class 0 is not bare ground (ocean, vegetation, crops).
function renderEarthCoverage(cov) {
  const el = $("#earthCoverageNote");
  const sh = coverageShares(cov);
  el.textContent = sh
    ? `Teal outline: bare ground with no measured window yet (${fmt(sh.todo, 1)}% of the sphere). Untouched: not bare ground, ${fmt(sh.fog, 1)}%.` : "Earth coverage is not in this export yet.";
}

// Fog, cells and legend for the current Mars/Moon home globe.
function refreshHome() {
  S.homeGlobe?.setCoverage(S.coverage[S.body] || null);
  S.homeGlobe?.setCells(S.body === "mars" && Array.isArray(S.atlasCells) ? S.atlasCells : NO_CELLS);
  renderLegend();
  setHomeLayer(S.homeLayer || "sites");
}

// ---------------------------------------------------------------- destination

function targetsForBody() { return S.targets.filter((t) => t.body === S.body); }

function renderTargets() {
  document.querySelectorAll("[data-body]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.body === S.body)));
  const targets = targetsForBody();
  if (!S.homeGlobe && !S.homeGlobeUnavailable) {
    try { S.homeGlobe = new GlobeView($("#homeGlobe"), {
      body: S.body,
      reduced,
      onPick: (i) => { const t = targetsForBody()[i]; if (t && t.unlocked) chooseTarget(t, i); },
      onPickCell: (ci) => openCell(ci),
      onProject: (x, y, visible, gi) => placeHomeLabel(x, y, visible, gi),
    }); } catch(error) { S.homeGlobeUnavailable=true; clearStage($("#homeGlobe")).append(h("p",{class:"webgl-fallback"},"The 3D globe is unavailable on this device. Select a region from the list to explore its evidence.")); }
    if (S.homeGlobe) S.homeGlobe.zoomDist = 3.0;   // Mars stays a planet when a site is chosen: closer, never filling the frame.
  }
  S.homeGlobe?.setBody(S.body);
  S.homeGlobe?.setPins(targets);
  refreshHome();
  setHomeLayer(S.homeLayer);
  S.homeGlobe?.setRegionalCells(S.body === "mars" && S.regionalVisible ? S.regionalCells : []);
  S.homeGlobe?.start();
  const body = S.body;
  ensureCoverage(body).then(() => { if (S.body === body) refreshHome(); });
  if (body === "mars") ensureAtlas();
  const regionalToggle = $("#regionalToggle");
  regionalToggle.hidden = S.body !== "mars" || !S.regionalCells;
  regionalToggle.setAttribute("aria-pressed", String(S.regionalVisible));
  $("#targetCards").replaceChildren(...targets.map((t, i) => h("button", {
    type: "button", class: "target-card", disabled: !t.unlocked, onclick: () => chooseTarget(t, i), onfocus: () => S.homeGlobe?.setHighlight?.(i), onblur: () => S.homeGlobe?.setHighlight?.(null),
  },
    h("span", { class: "target-number" }, String(i + 1).padStart(2, "0")),
    h("span", { class: "target-copy" },
      h("strong", {}, t.name),
      h("small", {}, CLASS_LABELS[t.landing_class] || "Class not available", " / ", t.unlocked ? "measured" : "not yet measured")),
    h("span", {}, ">"))));
}

// ---------------------------------------------------------------- Mars atlas cell (home globe)

const cellTitle = (cell) => `Mars cell ${String(cell.id || "").replace(/^mars_/, "")}`;

// The three twins of a cell. Cell records carry no coordinates, so each twin is placed by the
// coordinates and context of its Earth window in discoveries.json (same analog_id).
function cellTwins(cell) {
  return (cell.twins || []).map((tw, i) => {
    const w = S.windowById.get(tw.analog_id) || {};
    return {
      rank: i + 1, analog_id: tw.analog_id, name: placeName(tw), code: analogCode(tw.analog_id),
      D: tw.D, tie_group: tw.tie_group,
      lat: Number.isFinite(w.lat) ? w.lat : null, lon: Number.isFinite(w.lon) ? w.lon : null,
      novelty: tw.novelty ?? w.novelty ?? null, known_region_id: tw.known_region_id ?? w.known_region_id ?? null,
      context: tw.context ?? w.context ?? null, analog_place: tw.analog_place, card: null, cell: true,
    };
  });
}

function openCell(ci) {
  const cell = Array.isArray(S.atlasCells) ? S.atlasCells[ci] : null;
  if (cell) loadCell(cell, ci);
}

// A Mars cell loads its Earth twins into the same candidate list and Earth globe as a region does.
async function loadCell(cell, ci) {
  const token = ++S.selectionToken;
  S.twinToken++;
  S.cell = cell;
  S.cellIndex = ci;
  S.homeGlobe?.setCellSelected?.(ci);
  S.homeGlobe?.flyToCell?.(ci);
  S.target = { id: cell.id, body: "mars", name: cellTitle(cell), lat: cell.lat, lon: cell.lon, unlocked: true, landing_class: null, mission: null, year: null, outcome_note: null, center_note: null };
  S.analogs = cellTwins(cell);
  Object.assign(S, { regionCard: null, selected: null, twinEntry: null, card: null, loadedTwin: null });
  $("#twinBody").hidden = true;
  $("#overlayGuide").hidden = true;
  const empty = $("#workspaceEmpty");
  if (empty) empty.hidden = true;
  document.querySelectorAll("#targetCards button").forEach((button) => button.setAttribute("aria-pressed", "false"));
  renderCellCard(cell);
  updateJourney("destination");
  await enterScan();
  if (token !== S.selectionToken) return;
  renderPicked();
  status(`${cellTitle(cell)}: ${S.analogs.length} Earth twins loaded.`);
}

// Measured properties and mission shares of the cell. No terrain folder, so no 3D pair.
function renderCellCard(cell) {
  const box = $("#cellCard");
  box.hidden = false;
  const f = cell.features || {};
  const m = cell.mission_pct || {};
  const measure = (key) => {
    const info = FEATURE_INFO[key];
    const v = f[key];
    return h("div", { class: "cell-measure" }, h("span", {}, info.label),
      h("strong", {}, Number.isFinite(v) ? `${v.toFixed(info.digits)}${info.unit === "deg" ? " deg" : info.unit}` : "not in export"));
  };
  const share = (kind) => {
    const v = m[kind] || {};
    return h("div", { class: "cell-measure" }, h("span", {}, kind === "landing" ? "Landing share" : "Driving share"),
      h("strong", {}, Number.isFinite(v.pct) ? `${fmt(v.pct, 1)}% within ${fmt(v.limit_deg, 0)} deg` : "not in export"));
  };
  box.replaceChildren(
    h("div", { class: "cell-head" }, h("p", { class: "eyebrow" }, "MARS ATLAS CELL"), h("button", { type: "button", class: "btn small ghost", onclick: closeCell }, "Close")),
    h("h3", {}, cellTitle(cell)),
    h("p", { class: "note" }, latlon(cell.lat, cell.lon), cell.sample ? " " : "", cell.sample ? sampleTag() : null),
    h("div", { class: "cell-measures" }, ...Object.keys(FEATURE_INFO).map(measure), share("landing"), share("driving")),
    h("p", { class: "note" }, "Measured properties of this 8 km window. Its Earth twins are in the candidate list. The 3D comparison covers the 16 named sites: atlas cells have no terrain folder."));
}

function closeCell() {
  const box = $("#cellCard");
  box.hidden = true;
  box.replaceChildren();
  S.cellIndex = null;
  S.homeGlobe?.setCellSelected?.(-1);
}

// ---------------------------------------------------------------- region

// Mission figures for one kind: the card's values, the limit and a short source link.
function missionDetails(cardMission, kind) {
  const mp = cardMission || {};
  const lim = (S.missions && S.missions.limits && S.missions.limits[S.target.body] && S.missions.limits[S.target.body][kind]) || {};
  const limitDeg = mp.limit_deg ?? lim.limit_deg ?? null;
  const cardSource = typeof mp.source === "string" ? mp.source : null;
  const isUrl = cardSource && /^https?:\/\//.test(cardSource);
  const url = isUrl ? cardSource : (lim.limit_deg === limitDeg ? lim.source_url : null);
  const text = cardSource && !isUrl ? cardSource : null;
  return {
    target: mp.target ?? null,
    analog: mp.analog ?? null,
    limit_deg: limitDeg,
    source: url || text || "Source not available",
    note: lim.entry && lim.limit_deg === limitDeg ? lim.entry : null,
  };
}

async function enterRegion() {
  if (!S.target) return;
  const t = S.target, card = S.regionCard;
  $("#h-region").textContent = t.name;
  $("#regionTerrainLabel").textContent = `${BODY_NAMES[t.body]} / ${t.name}`;
  const scored = card ? scoringKeys(card).scored : [];
  $("#regionContent").replaceChildren(
    h("p", {class:"eyebrow"}, [t.mission, t.year].filter(Boolean).join(" / ")),
    h("p", {class:"lead"}, t.outcome_note || "A measured region awaiting comparison."),
    h("p", {class:"note"}, latlon(t.lat,t.lon)),
    t.center_note ? h("p", {class:"note"}, "Centre: " + t.center_note) : null,
    h("div", {class:"region-readings"}, ...scored.map(key => h("div", {}, h("span",{},FEATURE_INFO[key].label), h("strong",{},fmt(card.features[key]?.target,FEATURE_INFO[key].digits,FEATURE_INFO[key].unit === "deg" ? " deg" : ""))))),
    h("p", {class:"note"}, `8 km measured circle. ${card ? "Relief shown at x" + fmt(card.vertical_exaggeration || S.viz.vertical_exaggeration,1) + " vertical exaggeration." : "No terrain export available."}`));
  $("#regionEvidence").replaceChildren(...["landing","driving"].map(kind => {
    const m=missionDetails(card?.mission_pct?.[kind],kind);
    return h("div",{class:"region-mission"}, h("h3",{},kind === "landing" ? "Landing slope limit" : "Driving slope limit"),h("p",{},`${fmt(m.target,1)}% within ${fmt(m.limit_deg,1)} deg / `,sourceLink(m.source)),h("p",{class:"note"},"Slope measured at a 100 m baseline. Not a probability of success."));
  }));
  $("#regionTwins").replaceChildren(...S.analogs.map((entry,i)=>h("button",{type:"button",class:"rank-btn",disabled:!entry.card,onclick:()=>{S.selected=i;S.twinEntry=entry;goto("twin");}},h("strong",{},`#${entry.rank} ${entry.name}`),h("span",{},`D ${fmt(entry.D,2)} / ${twinTie(entry)}`),h("span",{},"Compare terrains >"))));
  if (!card) { $("#regionStatus").textContent="Terrain unavailable for this region."; return; }
  $("#regionStatus").textContent="Loading measured relief...";
  try {
    if (!S.regionView) S.regionView = new ComparisonView($("#regionStage"));
    if (S.regionLoaded !== t.id) {
      $("#regionStage").dataset.loading="true";
      const target=await loadTerrain(card.files.target,t.body);
      if (S.target !== t || S.currentScreen !== "region") return;
      S.regionView.load({target,analog:target,rotationDeg:0,verticalExaggeration:card.vertical_exaggeration || S.viz.vertical_exaggeration,horizontalM:1000,reduced,body:S.target?.body});
      S.regionLoaded=t.id;
    }
    $("#regionStage").dataset.loading="false";
    $("#regionStage img")?.remove();
    S.regionView.setMode("target"); S.regionView.start();
    $("#regionStatus").textContent="Drag to explore the relief. Heights come from the elevation model.";
  } catch(err) {
    if (S.target !== t || S.currentScreen !== "region") return;
    $("#regionStage").dataset.loading="false";
    $("#regionStatus").textContent="3D unavailable. The measured values and Earth comparisons remain available.";
    if(t.thumbnail) { const stage=$("#regionStage"); if(!stage.querySelector("img")) stage.append(h("img",{src:DATA_BASE+t.thumbnail,alt:`Hillshade of ${t.name}`})); }
  }
}
async function chooseTarget(t,i) {
  if(!t.unlocked) return;
  const token=++S.selectionToken;
  S.twinToken++;
  status(`Approaching ${t.name}...`);
  document.querySelectorAll("#rankList button").forEach(button=>button.disabled=true);
  $("#globalError").hidden=true;
  if(S.homeGlobe && i != null) {S.homeGlobe.setSelected(i);S.homeGlobe.flyTo(i);}
  try {
    const [ranking]=await Promise.all([getJSON(t.ranking || `rankings/${t.id}.json`),new Promise(resolve=>setTimeout(resolve,reduced ? 0 : 850))]);
    const analogs=[...ranking.analogs].sort((a,b)=>a.rank-b.rank);
    const first=analogs.find(a=>a.card);
    const regionCard=first ? await getJSON(first.card) : null;
    if(token!==S.selectionToken || !inWorkspace()) return;
    closeCell();
    Object.assign(S,{target:t,analogs,regionCard,selected:null,twinEntry:null,card:null,loadedTwin:null,cell:null});
    $("#twinBody").hidden=true;
    $("#overlayGuide").hidden=true;
    const empty=$("#workspaceEmpty");if(empty)empty.hidden=true;
    document.querySelectorAll("#targetCards button").forEach((button,index)=>button.setAttribute("aria-pressed",String(index===i)));
    updateJourney("destination");
    await enterScan();
    if(token!==S.selectionToken || !inWorkspace())return;
    const firstIndex=S.analogs.findIndex(a=>a.card);
    if(firstIndex>=0) await selectAnalog(firstIndex);
    status("");
  } catch(err) { if(token===S.selectionToken) {S.retry=()=>chooseTarget(t,i);showError(err);} }
}

// ---------------------------------------------------------------- scan

async function enterScan() {
  $("#scanTarget").textContent = S.target ? `${S.target.name} (${BODY_NAMES[S.target.body]})` : "Choose a region on the other world to reveal Earth candidates";
  if (!S.globe && !S.globeUnavailable) {
    try { S.globe = new GlobeView($("#globeStage"), {
      reduced,
      focus: { lat: 25, lon: 30 },
      pinColour: 0x58cb91,
      onPick: (gi) => selectAnalog(S.pinToAnalog[gi]),
      onNote: (text) => { $("#globeNote").textContent = text; },
      onProject: (x, y, visible, gi) => placePinLabel(x, y, visible, gi),
    }); } catch(error) { S.globeUnavailable=true; clearStage($("#globeStage")).append(h("p",{class:"webgl-fallback"},"The 3D globe is unavailable. Select an Earth analog from the ranked list.")); }
    if (S.globe) S.globe.orientOnly = true;   // Earth is the small orientation globe: it turns to a candidate but never zooms in.
  }
  // One pin per twin with coordinates (not per tie group; see README).
  S.pinToAnalog = S.analogs.map((a, i) => (Number.isFinite(a.lat) && Number.isFinite(a.lon) ? i : -1)).filter((i) => i >= 0);
  S.globe?.setPins(S.pinToAnalog.map((i) => ({ lat: S.analogs[i].lat, lon: S.analogs[i].lon })));
  S.globe?.setCoverage(S.coverage.earth || null);
  S.globe?.setLayer?.(S.earthLayer);
  renderEarthCoverage(S.coverage.earth || null);
  ensureCoverage("earth").then((cov) => { if (S.globe) S.globe.setCoverage(cov); renderEarthCoverage(cov); });
  S.globe?.setSelected(pinOf(S.selected));
  renderRankList();
  renderPicked();
  S.globe?.start();
}

function pinOf(analogIndex) {
  return analogIndex === null ? -1 : S.pinToAnalog.indexOf(analogIndex);
}

// Label for the selected pin on the globe (text set with textContent; position from the globe each frame).
function placePinLabel(x, y, visible, gi) {
  const el = $("#pinLabel");
  const a = S.analogs[S.pinToAnalog[gi]];
  if (!a || !visible) { el.hidden = true; return; }
  el.hidden = false;
  el.style.transform = `translate(${x}px, ${y}px) translate(-50%, calc(-100% - 10px))`;
  if (el.dataset.key !== String(gi)) {
    el.dataset.key = String(gi);
    el.replaceChildren(h("strong", {}, `#${a.rank} ${a.name}`), h("small", {}, a.code));
  }
}

function renderRankList() {
  $("#rankList").replaceChildren(...S.analogs.map((a, i) => h("li", {},
    h("button", {
      type: "button",
      class: "rank-btn",
      "aria-pressed": String(S.selected === i),
      onclick: () => selectAnalog(i),   // stays on screen: the small Earth turns to the place; "Compare" scrolls
      onpointerenter: () => S.globe?.setSelected(pinOf(i)),
      onpointerleave: () => S.globe?.setSelected(pinOf(S.selected)),
      onfocus: () => S.globe?.setSelected(pinOf(i)),
      onblur: () => S.globe?.setSelected(pinOf(S.selected)),
    },
      h("span", { class: "rank-num" }, `#${a.rank}`),
      h("span", { class: "rank-name" }, a.name, S.isSample ? " " : "", S.isSample ? sampleTag() : null),
      h("small", { class: "rank-code" }, a.code),
      h("span", { class: "rank-meta muted" }, `D ${fmt(a.D, 2)}`, " ", noveltyBadge(a.novelty))))));
  // One tie statement for the whole set instead of repeating it on every card.
  const head = $("#rankHead");
  if (head) {
    const groups = new Set(S.analogs.map((a) => a.tie_group).filter((g) => g !== null && g !== undefined));
    const n = S.analogs.length;
    head.textContent = !n ? "" : groups.size === 1 && S.analogs.every((a) => a.tie_group !== null && a.tie_group !== undefined)
      ? `All ${n} are tied: their differences are within sensor noise, so none is "the" twin. Lower D = closer.`
      : S.analogs.map((a) => `#${a.rank} ${twinTie(a).toLowerCase()}`).filter((t) => !t.includes("not tied")).length
        ? "Candidates with the same tie group differ by less than sensor noise. Lower D = closer." : "Lower D = closer.";
  }
  const go = $("#compareGo");
  if (go) {
    const pick = S.analogs[S.selected];
    go.hidden = !pick;
    if (pick) go.textContent = `Compare ${S.target?.name?.split(":")[0] || "the site"} with ${pick.name} ↓`;
  }
  const ws = $("#explorationWorkspace");
  if (ws && S.analogs.length && S.linkedTarget !== S.target) {
    // New site: replay the entrance (Mars turns, the line draws, Earth grows, the cards arrive).
    S.linkedTarget = S.target;
    ws.classList.remove("has-options");
    void ws.offsetWidth;
    S.linkShown = false;
    ws.classList.add("entering");
    clearTimeout(S.enterTimer);
    S.enterTimer = setTimeout(() => ws.classList.remove("entering"), 2400);
  }
  ws?.classList.toggle("has-options", S.analogs.length > 0);
  if (S.analogs.length) ws?.classList.remove("show-sites");
  requestAnimationFrame(() => S.globe?.resize?.());
}

async function selectAnalog(i) {
  if(!S.analogs[i])return;
  S.selected = i;
  const gi = pinOf(i);
  S.globe?.setSelected(gi);
  if (gi >= 0) S.globe?.flyTo(gi);
  renderRankList();
  renderPicked();
  const entry=S.analogs[i];
  if(!entry.card)return;
  S.twinEntry=entry;
  status(`Comparing ${S.target.name} with ${entry.name}...`);
  try {
    await enterTwin();
    if(S.twinEntry!==entry || !inWorkspace())return;
    enterMission();updateJourney("twin");
    const body=$("#twinBody");
    if(!reduced && body.animate)body.animate([{opacity:.35,transform:"translateY(8px)"},{opacity:1,transform:"translateY(0)"}],{duration:420,easing:"ease-out"});
    status("");
  } catch(err) {if(S.twinEntry===entry){S.retry=()=>selectAnalog(i);showError(err);}}
}

function renderPicked() {
  const box = $("#picked");
  const open = $("#openTwin");
  if (S.selected === null || !S.analogs[S.selected]) {
    box.hidden = true;
    open.disabled = true;
    return;
  }
  const a = S.analogs[S.selected];
  box.hidden = false;
  box.replaceChildren(
    h("h3", {}, a.name),
    h("p", { class: "muted" }, a.code, " ", noveltyBadge(a.novelty)),
    h("p", {}, `#${a.rank} · D ${fmt(a.D, 2)} · ${twinTie(a)}`),
    Number.isFinite(a.lat) ? h("p", { class: "muted" }, `Location ${latlon(a.lat, a.lon)}`, S.isSample ? " " : "", S.isSample ? sampleTag() : null) : h("p", { class: "note" }, "No coordinates in this export; no pin."),
    a.card ? null : h("p", { class: "note" }, S.cell ? "Atlas twins have no terrain comparison; the 3D view covers the 16 named sites." : "Comparison data is not available for this twin."));
  open.disabled = !a.card;
}

// ---------------------------------------------------------------- twin

async function enterTwin() {
  if(!S.twinEntry) return;
  const entry=S.twinEntry, targetSite=S.target, token=++S.twinToken;
  $("#twinNeeds").hidden=true;$("#twinBody").hidden=false;
  const card=await getJSON(entry.card);
  const stale=()=>token!==S.twinToken || !inWorkspace() || S.twinEntry!==entry;
  if(stale()) return;
  S.card=card; renderTwinText(card,entry);
  // Dossier steps 01, 03, 04 and 05 (02 mission shares come from enterMission). Each one checks it is still current.
  const current=()=>token===S.twinToken && inWorkspace() && S.twinEntry===entry && S.target===targetSite;
  renderSite(targetSite,card); renderTwinPlace(card,entry);
  fillLight(targetSite,current); fillTwinLight(targetSite,card,current); fillRehearsal(entry.card,current);
  fillGap(targetSite,S.facts?.figures?.earth_places_searched?.value,current);
  $("#profileToggle").disabled=false;
  $("#holoStage .terrain-fallback")?.remove();
  $("#holoStatus").textContent="Loading the two elevation models...";
  if(S.loadedTwin!==entry.card) {
    $("#holoStage").dataset.loading="true";
    S.holo?.stop();
    const [target,analog]=await Promise.all([loadTerrain(card.files.target,targetSite.body),loadTerrain(card.files.analog,targetSite.body)]);
    if(stale()) return;
    if(!S.holo) {
      try { S.holo=new ComparisonView($("#holoStage")); }
      catch(error) {
        $("#holoStage").dataset.loading="false";
        $("#profileToggle").disabled=true;
        $("#holoStatus").textContent="3D unavailable on this device. Compare the measured properties in the evidence panel.";
        $("#holoStage canvas")?.remove();
        $("#swipeHandle").hidden=true;
        $("#holoStage").append(h("div",{class:"terrain-fallback"},h("img",{src:DATA_BASE+card.files.target+"hillshade.png",alt:`${targetSite.name} hillshade`}),h("img",{src:DATA_BASE+card.files.analog+"hillshade.png",alt:`${entry.name} hillshade`})));
        return;
      }
    }
    S.holo.load({target,analog,rotationDeg:card.rotation_deg,levelled:S.levelled,verticalExaggeration:card.vertical_exaggeration || S.viz.vertical_exaggeration,horizontalM:S.viz.horizontal_m_per_unit || 1000,reduced,preserveCamera:!!S.loadedTwin,body:targetSite.body});
    S.loadedTwin=entry.card;
    S.holo.setProfile(null);
    S.profileOpen=false; $("#profileControls").hidden=true;
    $("#profileToggle").setAttribute("aria-expanded","false");$("#profileToggle").textContent="Show cross-section";
  }
  $("#holoStage").dataset.loading="false";
  S.holo.setOpacity(Number($("#holoOpacity").value));
  S.holo.setOverlayLayer?.(document.querySelector("[data-overlay-layer][aria-pressed=true]")?.dataset.overlayLayer || "both");
  S.holo.setSeparation?.(Number($("#layerSeparation")?.value || 0)/100);
  if(S.mode==="overlay")setProfileOpen(true);
  setMode(S.mode); S.holo.start();
  if(S.profileOpen) updateProfile();
  renderLevel(); loadTilt().then(renderLevel);
}
function setMode(mode) {
  if(!S.holo) return;
  const enteringOverlay=mode==="overlay" && S.mode!=="overlay";
  $("#overlayGuide").hidden=mode!=="overlay";
  if(enteringOverlay) setProfileOpen(true);
  // Align & inspect opens from the Oblique view (data-camera-view="reset"), not Profile.
  if(enteringOverlay) document.querySelector('[data-camera-view="reset"]')?.click();
  S.mode=mode; S.holo?.setMode(mode);
  document.querySelectorAll("[data-mode]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.mode===mode)));
  $("#swipeControl").hidden=mode!=="swipe";
  $("#swipeHandle").hidden=mode!=="swipe";
  setSwipe(Number($("#swipePosition").value)/100);
  $("#holoStage").dataset.mode=mode;
  $("#holoStatus").textContent=mode==="split" ? "One camera, one scale. Both terrains move together." : mode==="overlay" ? "Target mesh over the Earth surface. Use the open cross-section below to inspect where the relative heights separate. This view does not measure shared terrain." : "Drag the divider to reveal each landscape at the same position.";
}
function setSwipe(value) {
  const v=Math.max(0,Math.min(1,value));
  S.holo?.setSwipe(v);
  $("#swipePosition").value=String(Math.round(v*100));
  $("#swipeHandle").style.left=`${v*100}%`;
  $("#swipeHandle").setAttribute("aria-valuenow",String(Math.round(v*100)));
}
function setProfileOpen(open) {
  S.profileOpen=open;
  $("#profileControls").hidden=!open;
  $("#profileToggle").setAttribute("aria-expanded",String(open));
  $("#profileToggle").textContent=open ? "Hide cross-section" : "Show cross-section";
  updateProfile();
}
function updateProfile() {
  if(!S.holo) return;
  const samples=S.holo.setProfile(S.profileOpen ? Number($("#profilePosition").value)/100 : null);
  if(S.profileOpen) renderProfile($("#profileChart"),samples || []);
}
// ---------------------------------------------------------------- levelled / true orientation (display only)

const LEVEL_NOTE = "Overall tilt removed for display only; the measures are unchanged.";
function setLevel(levelled) {
  S.levelled = levelled;
  if(S.holo?.data) { S.holo.setLevelled(levelled); updateProfile(); }
  renderLevel();
}
// tilt.json is written by the terrain pipeline; until it exists the line says so instead of failing.
async function loadTilt() {
  if(S.tilt !== undefined) return S.tilt;
  try { S.tilt = await getJSON("tilt.json"); } catch { S.tilt = null; }
  return S.tilt;
}
function tiltEntry(file) {
  const id = String(file || "").replace(/^terrain\//, "").replace(/\/$/, "");
  const row = S.tilt?.terrains?.[id];
  return row && Number.isFinite(row.tilt_deg) ? row : null;
}
function slopeText(row) {
  const toward = row.downhill || (Number.isFinite(row.downhill_azimuth_deg) ? `${fmt(row.downhill_azimuth_deg, 0)}°` : "an unknown direction");
  return `toward the ${toward} (${fmt(row.tilt_deg, 1)}°)`;
}
function tiltLine() {
  const targetName = (S.target?.name || "Target").split(/[:(]/)[0].trim();
  const earthName = S.twinEntry?.name || "Earth place";
  const t = tiltEntry(S.card?.files?.target), e = tiltEntry(S.card?.files?.analog);
  const left = t ? `${targetName} slopes down ${slopeText(t)}` : `${targetName} slope direction not available yet`;
  const right = e ? `${earthName} ${slopeText(e)}` : `${earthName} slope direction not available yet`;
  return `${left} · ${right}`;
}
function renderLevel() {
  document.querySelectorAll("[data-level]").forEach(b => b.setAttribute("aria-pressed", String((b.dataset.level === "levelled") === S.levelled)));
  const note = $("#levelNote");
  if(note) note.textContent = S.levelled ? LEVEL_NOTE : (S.card ? tiltLine() : "");
  const rot = $("#rotNote");
  if(rot && S.card) rot.textContent = S.levelled
    ? `Earth terrain rotated ${fmt(S.card.rotation_deg,0)} degrees for display. Rotation does not change the score. Heights are relative to each disk's mean.`
    : "Earth terrain shown north up (0 degrees) in True orientation, with its real slopes. Rotation does not change the score. Heights are relative to each disk's mean.";
}

function renderTwinText(card,entry) {
  $("#twinKicker").textContent=`${S.target.name} / Earth analog ${card.rank}${S.isSample ? " / SAMPLE" : ""}`;
  $("#twinTitle").textContent=entry.name;
  $("#pairTarget").textContent=`${BODY_NAMES[S.target.body]} / ${S.target.name}`;
  $("#labelTarget").textContent=`${BODY_NAMES[S.target.body]} / ${S.target.name}`;
  $("#labelEarth").textContent=`Earth / ${entry.name}`;
  $("#twinCode").textContent=entry.code;
  const ve=card.vertical_exaggeration || S.viz.vertical_exaggeration;
  $("#pairScale").textContent=` / 8 km circles / relief x${fmt(ve,1)}`;
  const refined=refinedSummary(card);
  $("#twinFacts").replaceChildren(h("dt",{},"Distance D (lower is closer)"),h("dd",{},fmt(card.D,3)),h("dt",{},"Ranking"),h("dd",{},twinTie(entry)),h("dt",{},"Novelty"),h("dd",{},noveltyBadge(card.novelty ?? entry.novelty) ?? "not in export"),h("dt",{},"Earth location"),h("dd",{},latlon(entry.lat,entry.lon)),h("dt",{},"Vertical exaggeration"),h("dd",{},`x${fmt(ve,1)} for both terrains`),h("dt",{},"Measurement baseline"),h("dd",{},"100 m; display grid 30 m"),...(refined ? [h("dt",{},"Best window"),h("dd",{},refined)] : []));
  $("#rotNote").textContent=`Earth terrain rotated ${fmt(card.rotation_deg,0)} degrees for display. Rotation does not change the score. Heights are relative to each disk's mean.`;
  renderInspector(card,S.target,entry,key=>{S.property=key;},S.property);
  renderFeatures($("#featureBars"),card);renderContext($("#context"),card);
}

// ---------------------------------------------------------------- mission

// Dossier step 02: the mission-proven shares of this pair (reference comparison, 100 m baseline).
function enterMission() {
  if (!S.card) return;
  const names = { target: S.target.name, analog: S.twinEntry.name };
  const isSample = !!(S.card.provenance && S.card.provenance.sample);
  renderMissionBlock($("#mission-landing"), "landing", missionDetails(S.card.mission_pct?.landing, "landing"), names, isSample);
  renderMissionBlock($("#mission-driving"), "driving", missionDetails(S.card.mission_pct?.driving, "driving"), names, isSample);
}

// ---------------------------------------------------------------- how we know

// Landing share of the two mission control sites, read from their own comparison cards.
async function loadControls() {
  if (S.controls) return S.controls;
  const rows = [];
  for (const id of CONTROL_IDS) {
    const t = S.targets.find((x) => x.id === id);
    if (!t) continue;
    try {
      const ranking = await getJSON(t.ranking || `rankings/${t.id}.json`);
      const first = ranking.analogs.find((a) => a.card);
      const card = first ? await getJSON(first.card) : null;
      rows.push({ id, name: t.name, value: card?.mission_pct?.landing?.target ?? null, limit: card?.mission_pct?.landing?.limit_deg ?? null });
    } catch (_) {
      rows.push({ id, name: t.name, value: null, limit: null });
    }
  }
  const named = rows.map((r) => r.id === "jezero" ? "Jezero" : r.id === "gale" ? "Gale" : r.name);
  S.controls = rows.length ? [{
    label: "Mission controls: six completed landings",
    values: rows.map((r) => r.value),
    text: rows.map((r, i) => `${named[i]} ${Number.isFinite(r.value) ? fmt(r.value, 1) + "%" : "not available"}`).join(" · ") +
      `. Share of the 8 km circle within the landing limit${rows[0] && Number.isFinite(rows[0].limit) ? ` (${fmt(rows[0].limit, 0)}°)` : ""}; each must reach 50%.`,
  }] : [];
  return S.controls;
}

async function enterHow() {
  renderValidation($("#valList"), S.validation, S.isSample);
  const v12 = S.validation && S.validation["v1.2"];
  const v13 = S.validation && S.validation["v1.3"];
  $("#valStatus").replaceChildren(
    S.isSample ? sampleTag() : "",
    ` v1.2: ${v12 && v12.status ? v12.status : "not available"}. v1.3: ${v13 && v13.status ? v13.status : "not available"}. Numbers are shown as they came out.`);
  renderControls($("#controlsList"), await loadControls());
}

// ---------------------------------------------------------------- wiring

function wire() {
  window.matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change",event=>{
    reduced=event.matches;
    if(reduced)S.routeAnimation?.cancel();
    for(const globe of [S.homeGlobe,S.globe,askGlobe]) if(globe){globe.reduced=reduced;if(reduced&&globe.anim)globe.animateTo(globe.anim.dirB,globe.anim.d1);}
    for(const view of [S.holo,S.regionView]) if(view){if(view.data)view.data.reduced=reduced;view.controls.enableDamping=!reduced;view.setMode(view.mode);}
  });
  for(const b of document.querySelectorAll("[data-body]")) b.addEventListener("click",()=>{S.selectionToken++;status("");S.homeGlobe?.setMarks?.(null);S.body=b.dataset.body;S.twinToken++;
    Object.assign(S,{target:null,analogs:[],regionCard:null,selected:null,twinEntry:null,card:null,loadedTwin:null,cell:null});
    S.holo?.stop();$("#twinBody").hidden=true;$("#overlayGuide").hidden=true;
    const empty=$("#workspaceEmpty");if(empty)empty.hidden=false;
    closeCell();$("#explorationWorkspace").classList.remove("has-options","show-sites");S.linkFrom=null;S.linkedTarget=null;S.linkShown=false;renderTargets();enterScan();updateJourney("destination");fillHero($("#heroGapText"),$("#heroAskGap"),S.body);paintHomeGap();const wn=$("#worldName");if(wn)wn.textContent=S.body==="moon"?"the Moon.":"Mars.";if(S.homeGlobe){S.homeGlobe.focus=S.body==="moon"?{lat:-62,lon:0}:{lat:12,lon:-40};S.homeGlobe.resetView();}});
  $("#regionalToggle").addEventListener("click",()=>{S.regionalVisible=!S.regionalVisible;renderTargets();});
  $("#compareGo")?.addEventListener("click",()=>$("#step-evidence")?.scrollIntoView?.({behavior:reduced?"instant":"smooth",block:"start"}));
  $("#backToSites")?.addEventListener("click",()=>{$("#explorationWorkspace").classList.add("show-sites");S.linkFrom=null;S.linkedTarget=null;S.linkShown=false;$("#linkLine").style.opacity="0";});
  document.querySelectorAll("[data-home-layer]").forEach((b)=>b.addEventListener("click",()=>setHomeLayer(b.dataset.homeLayer)));
  document.querySelectorAll("[data-earth-layer]").forEach((b)=>b.addEventListener("click",()=>setEarthLayer(b.dataset.earthLayer)));
  $("#scanFromRegion").addEventListener("click",()=>goto("scan"));
  document.querySelectorAll("[data-action]").forEach(b=>b.addEventListener("click",()=>(b.dataset.view==="home" ? S.homeGlobe : S.globe)?.nudge(b.dataset.action)));
  $("#openTwin").addEventListener("click",()=>{if(S.selected!==null){S.twinEntry=S.analogs[S.selected];goto("twin");}});
  $("#resetView").addEventListener("click",()=>S.globe?.resetView());
  $("#resetCamera").addEventListener("click",()=>S.holo?.resetCamera());
  $("#regionReset").addEventListener("click",()=>S.regionView?.resetCamera());
  document.querySelectorAll("[data-mode]").forEach(b=>b.addEventListener("click",()=>setMode(b.dataset.mode)));
  document.querySelectorAll("[data-level]").forEach(b=>b.addEventListener("click",()=>setLevel(b.dataset.level==="levelled")));
  document.querySelectorAll("[data-camera]").forEach(b=>b.addEventListener("click",()=>S.holo?.nudge(b.dataset.camera)));
  $("#swipePosition").addEventListener("input",e=>setSwipe(Number(e.target.value)/100));
  const divider=$("#swipeHandle");
  const dragDivider=e=>{const r=$("#holoStage").getBoundingClientRect();setSwipe((e.clientX-r.left)/r.width);};
  divider.addEventListener("pointerdown",e=>{e.preventDefault();divider.setPointerCapture(e.pointerId);dragDivider(e);});
  divider.addEventListener("pointermove",e=>{if(divider.hasPointerCapture(e.pointerId))dragDivider(e);});
  divider.addEventListener("pointerup",e=>{if(divider.hasPointerCapture(e.pointerId))divider.releasePointerCapture(e.pointerId);});
  divider.addEventListener("keydown",e=>{const keys=["ArrowLeft","ArrowRight","Home","End"];if(!keys.includes(e.key))return;e.preventDefault();const v=Number($("#swipePosition").value);setSwipe((e.key==="Home" ? 0 : e.key==="End" ? 100 : v+(e.key==="ArrowLeft" ? -5 : 5))/100);});
  $("#holoOpacity").addEventListener("input",e=>S.holo?.setOpacity(Number(e.target.value)));
  $("#profileToggle").addEventListener("click",()=>setProfileOpen(!S.profileOpen));
  $("#profilePosition").addEventListener("input",updateProfile);
  document.querySelectorAll("[data-camera-view]").forEach(button=>button.addEventListener("click",()=>{
    S.holo?.setCameraView?.(button.dataset.cameraView);
    document.querySelectorAll("[data-camera-view]").forEach(b=>b.setAttribute("aria-pressed",String(b===button)));
    const note=$("#inspectionNote");if(note)note.textContent=button.dataset.cameraView==="underside" ? "Underside shows the reverse of the measured surface, not underground geology." : "Orbit freely through 360 degrees; tilt below the horizon to inspect both surfaces.";
  }));
  document.querySelectorAll("[data-overlay-layer]").forEach(button=>button.addEventListener("click",()=>{
    S.holo?.setOverlayLayer?.(button.dataset.overlayLayer);
    document.querySelectorAll("[data-overlay-layer]").forEach(b=>b.setAttribute("aria-pressed",String(b===button)));
  }));
  $("#layerSeparation")?.addEventListener("input",e=>{
    const value=Number(e.target.value)/100;S.holo?.setSeparation?.(value);
    const output=$("#separationValue");if(output)output.textContent=value ? `${Math.round(value*100)}% visual separation` : "Aligned";
    const note=$("#inspectionNote");if(note)note.textContent=value ? "Artificial display offset separates the layers. It is not a measured terrain difference. Set to zero to restore alignment." : "Surfaces restored to their aligned relative heights.";
  });
  $("#journeyBack").addEventListener("click",()=>goto(({region:"destination",scan:"region",twin:"scan",how:S.twinEntry ? "twin" : "destination",about:"destination"})[S.currentScreen] || "destination"));
  $("#heroAskGap").addEventListener("click",openGapQuestion);
  document.querySelectorAll("[data-nav]").forEach(a=>a.addEventListener("click",e=>{if(a.getAttribute("aria-disabled")==="true"){e.preventDefault();status(a.dataset.nav==="scan" ? "Choose a region first." : "Choose an Earth analog first.");}}));
  document.addEventListener("visibilitychange",()=>{if(document.hidden){S.homeGlobe?.stop();S.globe?.stop();S.holo?.stop();S.regionView?.stop();}else{if(inWorkspace()){S.homeGlobe?.start();S.globe?.start();S.holo?.start();}}});
}

// ---------------------------------------------------------------- Ask the atlas (STANDARDS 10.14)

let ask = null;

// Front-page line: opens the Ask-the-atlas question mars_no_twin through the panel's own API (ask.open, ask.select).
// ask.select needs the question tables, so the panel is opened and loaded first, exactly as its toggle does.
async function openGapQuestion() {
  const panel = $("#askPanel");
  panel.open = true;
  if (location.hash !== "#ask") location.hash = "ask";
  if (!ask) return;
  await ask.open();
  if (!ask.state.questions) return;
  await ask.select("mars_no_twin");
  panel.scrollIntoView?.({ block: "start", behavior: reduced ? "instant" : "smooth" });
}

// Side globe of "Ask the atlas": created only on wide screens, the first time an answer needs it.
const askWide = window.matchMedia("(min-width: 1200px)");
let askGlobe = null;
let askGlobeUnavailable = false;
function ensureAskGlobe() {
  if (askGlobe || askGlobeUnavailable || !askWide.matches) return askGlobe;
  const stage = $("#askGlobe");
  if (!stage) return null;
  try { askGlobe = new GlobeView(stage, { body: "mars", reduced }); askGlobe.start(); }
  catch (error) { askGlobeUnavailable = true; stage.closest(".ask-globe").hidden = true; }
  return askGlobe;
}

const askApi = {
  setAskMarks: (body, coords, label, turn) => {
    const g = ensureAskGlobe();
    const note = $("#askGlobeNote");
    if (note) note.textContent = label || "";
    if (!g) return;
    if (body) g.setBody(body);
    g.setMarks(coords, body === "earth" ? EARTH_MARK_COLOUR : undefined, 12);
    if (!turn) return;
    // Face the mean direction of the marks; when they spread around the planet, keep the default view.
    let x = 0, y = 0, z = 0;
    for (const c of coords) {
      const la = c.lat * Math.PI / 180, lo = c.lon * Math.PI / 180;
      x += Math.cos(la) * Math.cos(lo); y += Math.cos(la) * Math.sin(lo); z += Math.sin(la);
    }
    const r = Math.hypot(x, y, z);
    if (coords.length && r / coords.length > 0.35) g.faceLatLon(Math.asin(z / r) * 180 / Math.PI, Math.atan2(y, x) * 180 / Math.PI);
    else g.resetView();
  },
  targetPlace: (id) => { const t = S.targets.find((x) => x.id === id); return t && t.lat != null && t.lon != null ? { lat: t.lat, lon: t.lon, body: t.body } : null; },
  flyAskGlobe: (body, lat, lon) => {
    const g = ensureAskGlobe();
    if (!g) return;
    g.setBody(body);
    g.flyToLatLon(lat, lon);
  },
  showMars: async () => { if (S.body !== "mars") document.querySelector('[data-body="mars"]')?.click(); },
  setMarks: (coords) => S.homeGlobe?.setMarks?.(coords),
  focusMarsCell: async (lat, lon) => { await askApi.showMars(); S.homeGlobe?.flyToLatLon?.(lat, lon); },
  focusEarth: async (lat, lon) => { await enterScan(); S.globe?.flyToLatLon?.(lat, lon); },
  openTarget: async (id) => {
    const t = S.targets.find((x) => x.id === id);
    if (!t) return;
    if (S.body !== t.body) document.querySelector(`[data-body="${t.body}"]`)?.click();
    await chooseTarget(t, targetsForBody().indexOf(t));
  },
  openTwin: async (targetId, earthId) => {
    await askApi.openTarget(targetId);
    const idx = S.analogs.findIndex((a) => earthId && analogCode(a.analog_id) === analogCode(earthId));
    if (idx >= 0) await selectAnalog(idx);
  },
};

function initAsk() {
  const panel = $("#askPanel");
  if (!panel) return;
  ask = createAsk(panel, askApi);
  panel.addEventListener("toggle", () => { if (panel.open) { ask.open(); askGlobe?.start(); } else askGlobe?.stop(); });
}

// Sticky bar height -> CSS variable, so headings are never hidden under it.
function trackTopbar() {
  const bar = document.querySelector(".topbar");
  const set = () => document.documentElement.style.setProperty("--topbar-h", `${bar.offsetHeight + 12}px`);
  set();
  new ResizeObserver(set).observe(bar);
}

async function boot() {
  wire();
  trackTopbar();
  initAsk();
  try {
    const index = await loadIndex();
    S.viz = index.viz;
    S.bodies = index.bodies;
    S.missions = index.missions;
    S.validation = index.validation;
    S.targets = index.targets.targets;
    S.isSample = !!(index.viz.sample || index.targets.sample);
  } catch (err) {
    S.retry=()=>location.reload();
    showError(err);
    return;
  }
  $("#sampleBanner").hidden = !S.isSample;
  $("#sampleBadge").hidden = !S.isSample;


  // Optional data (STANDARDS 10.13 and regional): read only where data-availability.json says it exists,
  // so an absent file is never requested. Coverage and the atlas load on demand (see renderTargets).
  let availability = {};
  try {
    availability = await fetch("data-availability.json").then((r) => (r.ok ? r.json() : {}));
  } catch (_) { /* no availability file: nothing optional is loaded */ }
  const flags = availability[DATA_BASE] || {};
  S.flags = flags;
  if (flags.discoveries) {
    try { S.discoveries = await getJSON("discoveries.json"); } catch (_) { S.discoveries = null; }
  }
  try { S.facts = await getJSON("facts.json"); } catch (_) { S.facts = null; }
  S.windowById = new Map((S.discoveries?.windows || []).map((w) => [w.analog_id, w]));
  renderDiscoveries();
  fillHero($("#heroGapText"), $("#heroAskGap"), S.body);
  paintHomeGap();

  window.addEventListener("hashchange", route);
  route();

  if (flags.regional_mars) {
    try {
      const response = await fetch(DATA_BASE + "regional/mars.json");
      if (response.ok) {
        const regional = await response.json();
        const cells = Array.isArray(regional) ? regional : regional.cells;
        if (Array.isArray(cells) && cells.length) {
          S.regionalCells = cells.filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lon));
          if (S.regionalCells.length && (location.hash === "" || location.hash === "#destination")) renderTargets();
        }
      }
    } catch (_) { /* Optional dataset unavailable. */ }
  }
}

boot();
