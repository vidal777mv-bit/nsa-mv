// Mission dossier (STANDARDS 10.15): the five steps of one target and its Earth twin, and the front-page Earth-gap line.
// Every step reads persisted files only: the comparison card, light.json, rehearsal/<card file>.json and the query
// tables. A file that is missing or unreadable shows "not available yet" in its own step: no fallback, no guessed value.
import { h, fmt, latlon, sourceLink } from "./dom.js";
import { BODY_NAMES, CLASS_LABELS } from "./config.js";
import { getJSON } from "./data.js";
import { loadTable, numAt, textAt } from "./query.js";
import { noveltyBadge } from "./panels.js";

const NOT_YET = "not available yet";
const $ = (sel) => document.querySelector(sel);
const count = (n) => Number(n).toLocaleString("en-US");

// One persisted file. A 404 or an unreadable file comes back as an error, never as a substitute value.
async function readFile(path) {
  try { return { data: await getJSON(path) }; }
  catch (err) { return { error: err && err.message ? err.message : String(err) }; }
}

// light.json is read by two steps (02 and 03). A failed read is not kept, so a later visit tries again.
let lightRead = null;
function readLight() {
  if (!lightRead) {
    lightRead = readFile("light.json").then((res) => {
      if (res.error) lightRead = null;
      return res;
    });
  }
  return lightRead;
}

// The visible replacement for a step's content when its file is not there.
function notYet(what, detail) {
  return h("div", { class: "dossier-unavailable" },
    h("p", {}, `${what}: ${NOT_YET}.`),
    detail ? h("p", { class: "note" }, detail) : null);
}

const pct = (v) => (Number.isFinite(v) ? fmt(v, 1, "% of the year") : "not in file");

// ---------------------------------------------------------------- 01 THE SITE

export function renderSite(target, card) {
  const mp = card.mission_pct || {};
  const limit = (kind) => (Number.isFinite(mp[kind]?.limit_deg) ? `${fmt(mp[kind].limit_deg, 1)}° slope` : "not in card");
  $("#siteFacts").replaceChildren(
    h("dt", {}, "Target"), h("dd", {}, target.name),
    h("dt", {}, "Body"), h("dd", {}, BODY_NAMES[target.body] || target.body),
    h("dt", {}, "Mission"), h("dd", {}, [target.mission, target.year].filter(Boolean).join(", ") || "not in export"),
    h("dt", {}, "Landing class"), h("dd", {}, CLASS_LABELS[target.landing_class] || "not in export"));
  $("#siteNeeds").replaceChildren(
    h("dt", {}, "Landing limit"), h("dd", {}, limit("landing")),
    h("dt", {}, "Driving limit"), h("dd", {}, limit("driving")));
  $("#siteOutcome").textContent = target.outcome_note || "";
}

// ---------------------------------------------------------------- 03 THE EARTH TWIN

export function renderTwinPlace(card, entry) {
  const place = card.analog_place || entry.analog_place || {};
  $("#twinPlace").replaceChildren(
    h("dt", {}, "Place"), h("dd", {}, place.admin1 || entry.name || "not in export"),
    h("dt", {}, "Country"), h("dd", {}, place.country || "not in export"),
    h("dt", {}, "Distance D"), h("dd", {}, Number.isFinite(card.D) ? `${fmt(card.D, 3)} (lower is closer)` : "not in export"),
    h("dt", {}, "Novelty"), h("dd", {}, noveltyBadge(card.novelty ?? entry.novelty) || "not in export"),
    h("dt", {}, "Earth location"), h("dd", {}, Number.isFinite(entry.lat) && Number.isFinite(entry.lon) ? latlon(entry.lat, entry.lon) : "not in export"));
}

// Grazing light of the Earth twin beside the target's (light.json: earth_windows by window id, targets by id).
// The window id is the tail of the card's analog_id: "<target>__pool__pool_NNNNN" -> "pool_NNNNN".
export async function fillTwinLight(target, card, isCurrent) {
  const root = $("#twinLight");
  root.replaceChildren(h("p", { class: "note" }, "Loading the light file..."));
  const res = await readLight();
  if (!isCurrent()) return;
  if (res.error) { root.replaceChildren(notYet("Twin grazing light", res.error)); return; }
  const winId = /(pool_\d+)$/.exec(card.analog_id || "")?.[1];
  const win = winId ? res.data?.earth_windows?.[winId] : null;
  if (!win) { root.replaceChildren(notYet("Twin grazing light", winId ? `window ${winId} is not in light.json` : `no window id in ${card.analog_id || "the card"}`)); return; }
  const tgt = res.data?.targets?.[target.id];
  root.replaceChildren(
    h("dl", { class: "mini-facts" },
      h("dt", {}, "Grazing light, Earth twin"), h("dd", {}, pct(win.grazing_pct)),
      h("dt", {}, "Grazing light, target"), h("dd", {}, tgt ? pct(tgt.grazing_pct) : "not in file")),
    h("p", { class: "note" }, "Grazing light: share of the year the Sun is up but below 10° high. Sun geometry only, no terrain."));
}

// ---------------------------------------------------------------- 02 THE EVIDENCE: light

// Local horizon (Moon only; light.json targets[id].local_horizon). Its own label is shown; when it is null the reason is.
function horizonBlock(rec) {
  const hz = rec.local_horizon;
  if (!hz || typeof hz !== "object" || (hz.status && hz.status !== "ok")) {
    const reason = rec.local_horizon_reason || hz?.reason || "reason not given";
    return h("p", { class: "note dossier-muted" }, `Local horizon not computed: ${reason}.`);
  }
  const reach = Number.isFinite(hz.horizon_reach_km) ? `within ${fmt(hz.horizon_reach_km, 2)} km` : "reach not in file";
  return h("div", {},
    h("dl", { class: "mini-facts" },
      h("dt", {}, "Local horizon, highest"), h("dd", {}, Number.isFinite(hz.horizon_max_deg) ? fmt(hz.horizon_max_deg, 1, "°") : "not in file"),
      h("dt", {}, "Sun above the local horizon"), h("dd", {}, Number.isFinite(hz.sun_time_relief_pct) ? fmt(hz.sun_time_relief_pct, 1, "% of the year") : "not in file")),
    h("p", { class: "note" }, hz.label || `near horizon only (${reach}); far mountains not included`));
}

export async function fillLight(target, isCurrent) {
  const root = $("#lightBody");
  root.replaceChildren(h("p", { class: "note" }, "Loading the light file..."));
  const res = await readLight();
  if (!isCurrent()) return;
  if (res.error) { root.replaceChildren(notYet("Light", res.error)); return; }
  const rec = res.data?.targets?.[target.id];
  if (!rec) { root.replaceChildren(notYet("Light", "no record for this target in light.json")); return; }
  const num = (v, digits, suffix = "") => (Number.isFinite(v) ? fmt(v, digits, suffix) : "not in file");
  const nodes = [h("dl", { class: "mini-facts" },
    h("dt", {}, "Noon Sun, highest"), h("dd", {}, num(rec.noon_sun_max_deg, 1, "°") + " (highest of the year)"),
    h("dt", {}, "Noon Sun, lowest"), h("dd", {}, num(rec.noon_sun_min_deg, 1, "°") + " (lowest of the year)"),
    h("dt", {}, "Grazing light"), h("dd", {}, pct(rec.grazing_pct) + ", the Sun up but below 10°"))];
  if (target.body === "moon") nodes.push(horizonBlock(rec));
  nodes.push(h("p", { class: "note" }, "Sun geometry from the body's tilt and this latitude. No terrain, except the Moon local horizon above."));
  root.replaceChildren(...nodes);
}

// ---------------------------------------------------------------- 04 REHEARSE HERE / THIS PLACE CANNOT TEACH YOU

const ICON = { yes: "✓", partial: "◐", no: "✗" };
const ICON_LABEL = { yes: "Yes", partial: "Partly", no: "No" };

// Units as the rehearsal files write them, shown the short way ("percent" -> "%", "m/s2" -> "m/s²").
const UNIT_TEXT = { percent: "%", "m/s2": "m/s²", "K / Koppen class": "K" };

function valueText(v, unit) {
  if (v === null || v === undefined || v === "") return "n/a";
  const u = UNIT_TEXT[unit] ?? unit;
  // Ranges like "95-390" carry the unit; class names like "BWk" do not.
  if (typeof v !== "number") return /^-?[\d.]+\s*-\s*-?[\d.]+$/.test(String(v)) && u ? `${v} ${u}` : String(v);
  if (!Number.isFinite(v)) return "n/a";
  // Tiny non-zero values (the Moon's surface pressure) keep their magnitude instead of rounding to 0.
  const num = v !== 0 && Math.abs(v) < 0.01 ? v.toExponential(1)
    : v.toLocaleString("en-US", { minimumFractionDigits: Math.abs(v) >= 100 ? 0 : 1, maximumFractionDigits: Math.abs(v) >= 100 ? 0 : 1 });
  if (!u) return num;
  return u === "%" || u === "°" ? `${num}${u}` : `${num} ${u}`;
}

function sourceOf(source) {
  if (typeof source === "string" && /^https?:\/\//.test(source)) return sourceLink(source);
  return typeof source === "string" && source ? source : "not given";
}

// One line of the plan. A null status shows its reason in muted text; the line keeps its values when it has them.
function rehearsalLine(line) {
  const status = ICON[line.status] ? line.status : null;
  const hasValues = (line.target_value !== null && line.target_value !== undefined) || (line.analog_value !== null && line.analog_value !== undefined);
  return h("li", { class: "rehearsal-line is-" + (status || "null") },
    h("div", { class: "rehearsal-head" },
      h("span", { class: "rehearsal-icon", role: "img", "aria-label": status ? ICON_LABEL[status] : "Not assessed" }, status ? ICON[status] : "–"),
      h("strong", {}, line.label || line.id || "Line"),
      h("span", { class: "evidence-tag" }, line.evidence || "evidence not given")),
    hasValues ? h("dl", { class: "rehearsal-values" },
      h("dt", {}, "Target"), h("dd", {}, valueText(line.target_value, line.unit)),
      h("dt", {}, "Earth twin"), h("dd", {}, valueText(line.analog_value, line.unit))) : null,
    status === null ? h("p", { class: "note rehearsal-reason" }, line.reason || "Not assessed: no reason given.") : null,
    line.rule ? h("p", { class: "note" }, line.rule) : null,
    h("p", { class: "note" }, "Source: ", sourceOf(line.source)));
}

// The plan file has the same name as the card (STANDARDS 10.15): rehearsal/<card file name>.
export async function fillRehearsal(cardPath, isCurrent) {
  const root = $("#rehearsalBody");
  root.replaceChildren(h("p", { class: "note" }, "Loading the rehearsal plan..."));
  const file = "rehearsal/" + cardPath.split("/").pop();
  const res = await readFile(file);
  if (!isCurrent()) return;
  if (res.error) { root.replaceChildren(notYet("Rehearsal plan", res.error)); return; }
  const lines = Array.isArray(res.data) ? res.data : Array.isArray(res.data?.lines) ? res.data.lines : null;
  if (!lines) { root.replaceChildren(notYet("Rehearsal plan", `${file} has no lines`)); return; }
  const column = (group, title, empty) => {
    const rows = lines.filter((l) => l && l.group === group);
    return h("section", { class: "rehearsal-col" }, h("h3", {}, title),
      rows.length ? h("ol", { class: "rehearsal-list" }, ...rows.map(rehearsalLine)) : h("p", { class: "note" }, empty));
  };
  root.replaceChildren(
    column("rehearse", "Rehearse here", "No rehearsal lines in this plan."),
    column("cannot", "This place cannot teach you", "No limits listed in this plan."));
}

// ---------------------------------------------------------------- 05 WHERE EARTH RUNS OUT

// Mars cells of the atlas (query/mars_cells, column gap: 1 = no Earth window within the tie threshold, 0 = there is one).
let marsGap = null;
export function loadMarsGapCoords() {
  return loadTable("mars_cells", ["gap", "lat", "lon"]).then((t) => {
    const out = [];
    for (let k = 0; k < t.rows; k++) if (numAt(t, "gap", k) === 1) out.push({ lat: numAt(t, "lat", k), lon: numAt(t, "lon", k) });
    return out;
  });
}

export function loadMarsGap() {
  if (!marsGap) {
    marsGap = loadTable("mars_cells", ["gap"]).then((t) => {
      if (!t.data.gap) throw new Error("column gap is not in query/mars_cells");
      let total = 0, gap = 0;
      for (let k = 0; k < t.rows; k++) {
        const v = numAt(t, "gap", k);
        if (v === null) continue;
        total++;
        if (v === 1) gap++;
      }
      if (!total) throw new Error("no Mars cell has a gap value");
      return { gap, total };
    });
    marsGap.catch(() => { marsGap = null; });
  }
  return marsGap;
}

// Targets (query/targets, column gap) of the Moon: the Moon targets with an Earth gap, by name.
let moonGap = null;
function loadMoonGap() {
  if (!moonGap) {
    moonGap = loadTable("targets", ["gap", "body", "name"]).then((t) => {
      for (const c of ["gap", "body", "name"]) if (!t.data[c]) throw new Error(`column ${c} is not in query/targets`);
      const moon = [];
      for (let k = 0; k < t.rows; k++) if (textAt(t, "body", k) === "moon") moon.push(k);
      return {
        total: moon.length,
        names: moon.filter((k) => numAt(t, "gap", k) === 1).map((k) => textAt(t, "name", k) || "unnamed target"),
      };
    });
    moonGap.catch(() => { moonGap = null; });
  }
  return moonGap;
}

export async function fillGap(target, earthPool, isCurrent) {
  const root = $("#gapBody");
  root.replaceChildren(h("p", { class: "note" }, "Loading the Earth-gap figure..."));
  try {
    if (target.body === "moon") {
      const { total, names } = await loadMoonGap();
      if (!isCurrent()) return;
      root.replaceChildren(
        h("p", { class: "gap-figure" }, `${count(names.length)} of ${count(total)} Moon targets`),
        h("p", {}, "have no Earth window within the tie threshold of their relief class.", names.length ? ` Targets: ${names.join("; ")}.` : ""));
    } else {
      const { gap, total } = await loadMarsGap();
      if (!isCurrent()) return;
      root.replaceChildren(
        h("p", { class: "gap-figure" }, `${count(gap)} of ${count(total)} Mars cells`),
        h("p", {}, `(${fmt(100 * gap / total, 1)}% of measured Mars) have no Earth window within the tie threshold of their relief class.`));
    }
    if (Number.isFinite(earthPool)) root.append(h("p", { class: "note" }, `Earth pool: ${count(earthPool)} bare-ground places, 56° S to 84° N (NASA NASADEM to 60° N, Copernicus GLO-30 in the Arctic). Places with 20% or more ice and Antarctica are not included.`));
  } catch (err) {
    if (isCurrent()) root.replaceChildren(notYet("Earth gap", err.message));
  }
}

// ---------------------------------------------------------------- front page line

// "Earth can rehearse X% of measured Mars. Here is the Y% it can't." Both shares come from the same Mars cell table.
export async function fillHero(textEl, button, body = "mars") {
  const put = (main, sub) => textEl.replaceChildren(h("span", { class: "hero-main" }, main), " ", h("span", { class: "hero-sub-line" }, sub));
  try {
    if (body === "moon") {
      const { total, names } = await loadMoonGap();
      put(`Earth has ground like ${total - names.length} of ${total} measured Moon sites.`,
        "The low polar Sun is the part no place on Earth can rehearse.");
      button.hidden = true;
      return;
    }
    const { gap, total } = await loadMarsGap();
    const gapPct = Number((100 * gap / total).toFixed(1));
    const rehearsePct = (100 - gapPct).toFixed(1);
    put(`Earth can rehearse ${rehearsePct}% of measured Mars.`, `The coral points are the ${gapPct.toFixed(1)}% it can't.`);
    button.hidden = false;
    button.disabled = false;
  } catch (err) {
    textEl.textContent = `Earth-gap figure ${NOT_YET} (${err.message}).`;
  }
}
