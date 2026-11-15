// "Ask the atlas" panel (STANDARDS 10.14). Five preset questions over the exported query tables: no free text,
// no model. Each answer cites its table and columns and carries an evidence tag. Results act on the globes or
// open a comparison through `api` (wired in app.js). Data loads only when the panel is opened.
import { h, fmt } from "./dom.js";
import { analogCode } from "./data.js";
import { loadQuestions, loadTable, runFilter, numAt, textAt, rowOfText, MISSION_COLUMNS } from "./query.js";
import { noveltyBadge } from "./panels.js";

// Columns read per table: the filter columns of the questions plus what a result row shows.
const DISPLAY = {
  mars_cells: ["id", "lat", "lon", "relief_class", "d_nearest", "gap"],
  earth_windows: ["id", "place_name", "place_country", "novelty", "koppen_label", "elevation_m", "nearest_town_km", "lat", "lon"],
  twins: ["query_id", "query_kind", "rank", "earth_row", "D", "novelty", "nearest_town_km"],
  targets: ["id", "name", "mission", "gap", "landing_class"],
};
// Thresholds the visitor can move (only numeric le/ge conditions get a slider).
const SLIDERS = {
  nearest_town_km: { label: "Nearest town within", unit: "km", min: 0, max: 200, step: 1 },
  landing_pct: { label: "Landing share at least", unit: "%", min: 0, max: 100, step: 1 },
};
// Default order of the result list.
const SORT = {
  mars_cells: ["d_nearest", -1],
  earth_windows: ["nearest_town_km", 1],
  twins: ["D", 1],
  targets: ["name", 1],
};
const LIMIT = 60;
const TABLE_LABEL = { mars_cells: "Mars cells", earth_windows: "Earth windows", twins: "Twins", targets: "Targets" };
const GAP_CAVEAT = "Within our 2,730-place bare-ground Earth pool (56° S to 84° N, Arctic included; ice-covered places and Antarctica not included).";

export function createAsk(panel, api) {
  const cardsEl = panel.querySelector("[data-role=cards]");
  const answerEl = panel.querySelector("[data-role=answer]");
  const state = { questions: null, tables: null, active: null, values: {}, busy: 0 };

  const question = (id) => state.questions.questions.find((q) => q.id === id);
  const valuesFor = (q) => state.values[q.id] || [];
  const isGap = (q) => q.filter.table === "mars_cells" && q.filter.all.some((c) => c.col === "gap");
  const evidenceOf = (q) => (q.filter.all.some((c) => MISSION_COLUMNS.includes(c.col))
    ? "reference comparison: mission percentage against a published limit, not a success probability"
    : "derived observation: computed from exported measurements and place records");

  function columnsFor(q) {
    return [...new Set(q.filter.all.map((c) => c.col))];
  }

  async function ensureData() {
    if (state.questions) return;
    state.questions = await loadQuestions();
    const need = {};
    for (const name of Object.keys(DISPLAY)) need[name] = [...DISPLAY[name]];
    for (const q of state.questions.questions) need[q.filter.table] = [...(need[q.filter.table] || []), ...columnsFor(q)];
    const names = Object.keys(need);
    const loaded = await Promise.all(names.map((n) => loadTable(n, need[n])));
    state.tables = Object.fromEntries(names.map((n, i) => [n, loaded[i]]));
  }

  const countOf = (q) => runFilter(state.tables[q.filter.table], q.filter.all, valuesFor(q)).length;

  function renderCards() {
    cardsEl.replaceChildren(...state.questions.questions.map((q, i) => h("button", {
      type: "button", class: "ask-card", "aria-pressed": String(state.active === q.id),
      "data-question": q.id, onclick: () => select(q.id),
    },
      h("span", { class: "ask-card-index" }, `0${i + 1}`),
      h("strong", {}, q.title),
      h("span", { class: "ask-note" }, q.note),
      h("span", { class: "ask-count-line" }, h("b", { class: "ask-count" }, String(countOf(q))), " results"))));
  }

  function sortRows(tname, rows) {
    const [col, dir] = SORT[tname];
    const t = state.tables[tname];
    const key = (r) => (col === "name" ? (textAt(t, col, r) || "") : (numAt(t, col, r) ?? Infinity));
    const sorted = Array.from(rows);
    sorted.sort((a, b) => {
      const ka = key(a), kb = key(b);
      if (ka < kb) return -dir;
      if (ka > kb) return dir;
      return a - b;
    });
    return sorted;
  }

  function resultItem(q, tname, row) {
    const t = state.tables[tname];
    let title, sub = [], key = null, badge = null, action = null;
    if (tname === "mars_cells") {
      title = `Mars cell ${textAt(t, "id", row)}`;
      sub = [`${fmt(numAt(t, "lat", row), 2)}°, ${fmt(numAt(t, "lon", row), 2)}°`, textAt(t, "relief_class", row)];
      key = `nearest Earth D ${fmt(numAt(t, "d_nearest", row), 3)}`;
      if (numAt(t, "gap", row) === 1) badge = h("span", { class: "badge-gap" }, "Earth gap");
    } else if (tname === "earth_windows") {
      title = textAt(t, "place_name", row) || textAt(t, "place_country", row) || textAt(t, "id", row);
      const elev = numAt(t, "elevation_m", row);
      const town = numAt(t, "nearest_town_km", row);
      sub = [textAt(t, "place_country", row), textAt(t, "koppen_label", row),
        elev === null ? null : `${fmt(elev, 0)} m`, town === null ? null : `town ${fmt(town, 1)} km`];
      badge = noveltyBadge(textAt(t, "novelty", row));
    } else if (tname === "twins") {
      const kind = textAt(t, "query_kind", row);
      const qid = textAt(t, "query_id", row);
      const er = numAt(t, "earth_row", row);
      const e = state.tables.earth_windows;
      title = (er === null ? null : textAt(e, "place_name", er) || textAt(e, "id", er)) || "Earth twin";
      sub = [kind === "target" ? `for target ${qid}` : `for Mars cell ${qid}`, `rank ${fmt(numAt(t, "rank", row), 0)}`];
      key = `D ${fmt(numAt(t, "D", row), 3)}`;
      badge = noveltyBadge(textAt(t, "novelty", row));
      action = kind === "target" ? "Compare terrains" : "Show the Mars cell";
    } else {
      title = textAt(t, "name", row);
      sub = [textAt(t, "mission", row), textAt(t, "landing_class", row)];
      key = `Earth gap: ${numAt(t, "gap", row) === 1 ? "yes" : "no"}`;
    }
    return h("li", {}, h("button", {
      type: "button", class: "ask-result", onclick: () => act(tname, row),
    },
      h("strong", {}, title),
      h("span", { class: "ask-sub" }, sub.filter(Boolean).join(" · ")),
      key ? h("span", { class: "ask-key" }, key) : null,
      badge,
      action ? h("span", { class: "ask-action" }, action + " ›") : null));
  }

  // Places of a result set for the side globe: Mars cells on Mars, Earth windows and twins on Earth (each twin at its
  // Earth window). Targets carry no coordinates in the export, so they mark nothing.
  function placesOf(tname, rows) {
    const n = (k, one, many) => `${k} ${k === 1 ? one : many}`;
    const t = state.tables[tname];
    const e = state.tables.earth_windows;
    const at = (tb, r) => ({ lat: numAt(tb, "lat", r), lon: numAt(tb, "lon", r) });
    const ok = (c) => c.lat !== null && c.lon !== null;
    if (tname === "mars_cells") {
      const coords = Array.from(rows, (r) => at(t, r)).filter(ok);
      return { body: "mars", coords, label: `Coral: ${n(coords.length, "Mars cell", "Mars cells")} in this answer.` };
    }
    if (tname === "earth_windows") {
      const coords = Array.from(rows, (r) => at(t, r)).filter(ok);
      return { body: "earth", coords, label: `Green: ${n(coords.length, "Earth place", "Earth places")} in this answer.` };
    }
    if (tname === "twins") {
      const seen = new Set();
      const coords = [];
      for (const r of rows) {
        const er = numAt(t, "earth_row", r);
        if (er === null || seen.has(er)) continue;
        seen.add(er);
        const c = at(e, er);
        if (ok(c)) coords.push(c);
      }
      return { body: "earth", coords, label: `Green: ${n(coords.length, "Earth place", "Earth places")} behind ${n(rows.length, "twin", "twins")}.` };
    }
    const places = Array.from(rows, (r) => api.targetPlace?.(textAt(t, "id", r))).filter(Boolean);
    const body = places.length && places.every((p) => p.body === places[0].body) ? places[0].body : null;
    if (!body) return { body: null, coords: [], label: "Targets are opened from the list; they are not marked here." };
    return { body, coords: places, label: `Coral: ${n(places.length, "target", "targets")} in this answer (named-site centres).` };
  }

  async function act(tname, row) {
    const t = state.tables[tname];
    const lat = tname === "twins" ? numAt(state.tables.earth_windows, "lat", numAt(t, "earth_row", row)) : (tname === "targets" ? null : numAt(t, "lat", row));
    const lon = tname === "twins" ? numAt(state.tables.earth_windows, "lon", numAt(t, "earth_row", row)) : (tname === "targets" ? null : numAt(t, "lon", row));
    if (lat !== null && lon !== null) api.flyAskGlobe?.(tname === "mars_cells" ? "mars" : "earth", lat, lon);
    if (tname === "mars_cells") return api.focusMarsCell(numAt(t, "lat", row), numAt(t, "lon", row));
    if (tname === "earth_windows") return api.focusEarth(numAt(t, "lat", row), numAt(t, "lon", row));
    if (tname === "targets") return api.openTarget(textAt(t, "id", row));
    const kind = textAt(t, "query_kind", row);
    const qid = textAt(t, "query_id", row);
    if (kind === "target") {
      const earthId = textAt(state.tables.earth_windows, "id", numAt(t, "earth_row", row));
      return api.openTwin(qid, earthId);
    }
    const mc = state.tables.mars_cells;
    const mr = rowOfText(mc, "id", qid);
    if (mr >= 0) return api.focusMarsCell(numAt(mc, "lat", mr), numAt(mc, "lon", mr));
  }

  // The result list, count and Mars marks; slider moves refresh only this part, so focus stays on the slider.
  function renderResults(q, turn = false) {
    const t = state.tables[q.filter.table];
    const rows = runFilter(t, q.filter.all, valuesFor(q));
    const shown = sortRows(q.filter.table, rows).slice(0, LIMIT);
    answerEl.querySelector("[data-role=count]").replaceChildren(h("b", { class: "ask-count" }, String(rows.length)), " results");
    answerEl.querySelector("[data-role=results]").replaceChildren(...shown.map((r) => resultItem(q, q.filter.table, r)));
    answerEl.querySelector("[data-role=more]").textContent = rows.length > LIMIT
      ? `Showing the first ${LIMIT} of ${rows.length}, in the order shown above.` : "";
    if (isGap(q)) {
      const coords = Array.from(rows, (r) => ({ lat: numAt(t, "lat", r), lon: numAt(t, "lon", r) }));
      api.setMarks(coords);
    }
    const where = placesOf(q.filter.table, rows);
    api.setAskMarks?.(where.body, where.coords, where.label, turn);
    renderCards();
  }

  function slidersFor(q) {
    return q.filter.all.map((c, i) => {
      const cfg = SLIDERS[c.col];
      if (!cfg || (c.op !== "le" && c.op !== "ge")) return null;
      const v = valuesFor(q)[i] ?? c.value;
      return h("label", { class: "ask-slider" },
        h("span", {}, `${cfg.label} `), h("output", {}, `${v} ${cfg.unit}`),
        h("input", {
          type: "range", min: cfg.min, max: cfg.max, step: cfg.step, value: v, "aria-label": `${cfg.label} ${cfg.unit}`,
          oninput: (e) => {
            const value = Number(e.target.value);
            const list = (state.values[q.id] = [...valuesFor(q)]);
            list[i] = value;
            e.target.parentElement.querySelector("output").textContent = `${value} ${cfg.unit}`;
            renderResults(q);
          },
        }));
    }).filter(Boolean);
  }

  async function select(id) {
    const q = question(id);
    if (!q) return;
    const token = ++state.busy;
    state.active = id;
    if (isGap(q)) await api.showMars();
    if (token !== state.busy) return;
    const t = state.tables[q.filter.table];
    const cols = columnsFor(q);
    const idx = state.questions.questions.indexOf(q) + 1;
    answerEl.replaceChildren(...[
      h("p", { class: "eyebrow" }, `Question ${idx} of ${state.questions.questions.length} · ${evidenceOf(q).split(":")[0]}`),
      h("h3", {}, q.title),
      h("p", { class: "ask-note" }, q.note),
      ...slidersFor(q),
      h("p", { class: "ask-result-count", "data-role": "count" }),
      h("p", { class: "ask-cite" }, `Computed from ${TABLE_LABEL[q.filter.table]} (${t.rows} rows; ${q.filter.table}/manifest.json): ${cols.join(", ")}.`),
      h("p", { class: "ask-evidence" }, evidenceOf(q) + "."),
      isGap(q) ? h("p", { class: "ask-caveat" }, GAP_CAVEAT) : null,
      h("ol", { class: "ask-results", "data-role": "results" }),
      h("p", { class: "note", "data-role": "more" })].filter(Boolean));
    if (!isGap(q)) api.setMarks(null);
    renderResults(q, true);
    renderCards();
  }

  async function open() {
    try {
      await ensureData();
      renderCards();
      if (state.active) select(state.active);
    } catch (err) {
      answerEl.replaceChildren(h("p", { class: "error-line" }, `The atlas tables could not be loaded: ${err.message}`));
    }
  }

  return { open, select, state };
}

