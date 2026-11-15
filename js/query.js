// "Ask the atlas" data layer (STANDARDS 10.14, P-Q). Reads site/data/query only, and only when the panel opens.
// Numeric columns are Float32 LE (missing = NaN). Ranges use <col>.order.u32 (rows sorted by value, NaN excluded)
// with binary search. Text columns are Uint16 codes into a dictionary (65535 = missing). No free text, no model.
import { DATA_BASE } from "./config.js";

const BASE = "query/";
const MISSING_CODE = 65535;

async function bytes(path) {
  const r = await fetch(DATA_BASE + BASE + path);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.arrayBuffer();
}

async function json(path) {
  const r = await fetch(DATA_BASE + BASE + path);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

export function loadQuestions() {
  return json("questions.json");
}

const tables = new Map();

async function loadColumn(table, meta) {
  if (meta.type === "text") {
    const [codes, dict] = await Promise.all([bytes(`${table}/${meta.name}.codes.u16`), json(`${table}/${meta.name}.dict.json`)]);
    return { type: "text", codes: new Uint16Array(codes), dict };
  }
  const col = { type: "f32", values: new Float32Array(await bytes(`${table}/${meta.name}.f32`)), order: null };
  if (meta.order) col.order = new Uint32Array(await bytes(`${table}/${meta.name}.order.u32`));
  return col;
}

// Loads a table's manifest and the named columns (each at most once).
export async function loadTable(name, wanted) {
  if (!tables.has(name)) {
    tables.set(name, json(`${name}/manifest.json`).then((m) => ({
      name,
      rows: m.rows,
      meta: Object.fromEntries(m.columns.map((c) => [c.name, c])),
      data: {},
      loading: {},
    })));
  }
  const t = await tables.get(name);
  await Promise.all([...new Set(wanted)].filter((c) => t.meta[c] && !t.data[c]).map((c) => {
    if (!t.loading[c]) t.loading[c] = loadColumn(name, t.meta[c]).then((col) => { t.data[c] = col; });
    return t.loading[c];
  }));
  return t;
}

// Mission-percentage columns are comparisons with a published limit (evidence "reference comparison").
export const MISSION_COLUMNS = ["landing_pct", "driving_pct", "landing_pct_mars", "landing_pct_moon"];

function lowerBound(order, values, v, strict) {
  // first position whose value is >= v (or > v when strict)
  let lo = 0, hi = order.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    const x = values[order[mid]];
    if (strict ? x <= v : x < v) lo = mid + 1; else hi = mid;
  }
  return lo;
}

function conditionMask(col, cond, n, v) {
  const m = new Uint8Array(n);
  if (col.type === "text") {
    const wanted = new Set((cond.op === "in" ? v : [v]).map((s) => col.dict.indexOf(s)).filter((i) => i >= 0));
    for (let k = 0; k < n; k++) {
      const c = col.codes[k];
      if (c !== MISSING_CODE && wanted.has(c)) m[k] = 1;
    }
    return m;
  }
  const values = col.values;
  const isRange = cond.op === "le" || cond.op === "lt" || cond.op === "ge" || cond.op === "gt";
  if (isRange && col.order) {
    // Binary search on the sorted order: the matching rows are one contiguous block of order[].
    let lo = 0, hi = col.order.length;
    if (cond.op === "le") hi = lowerBound(col.order, values, v, true);
    else if (cond.op === "lt") hi = lowerBound(col.order, values, v, false);
    else if (cond.op === "ge") lo = lowerBound(col.order, values, v, false);
    else lo = lowerBound(col.order, values, v, true);
    for (let p = lo; p < hi; p++) m[col.order[p]] = 1;
    return m;
  }
  const list = cond.op === "in" ? v : null;
  for (let k = 0; k < n; k++) {
    const x = values[k];
    if (Number.isNaN(x)) continue;
    let ok;
    switch (cond.op) {
      case "eq": ok = x === v; break;
      case "in": ok = list.includes(x); break;
      case "le": ok = x <= v; break;
      case "lt": ok = x < v; break;
      case "ge": ok = x >= v; break;
      case "gt": ok = x > v; break;
      default: throw new Error(`unknown op ${cond.op}`);
    }
    if (ok) m[k] = 1;
  }
  return m;
}

// conditions: [{col, op, value}] with optional overrides from the visitor's sliders (values[i]).
// Returns the matching row indices, in table order.
export function runFilter(table, conditions, overrides = []) {
  const n = table.rows;
  const mask = new Uint8Array(n).fill(1);
  conditions.forEach((cond, i) => {
    const col = table.data[cond.col];
    if (!col) throw new Error(`column not loaded: ${table.name}.${cond.col}`);
    const m = conditionMask(col, cond, n, overrides[i] ?? cond.value);
    for (let k = 0; k < n; k++) mask[k] &= m[k];
  });
  let count = 0;
  for (let k = 0; k < n; k++) count += mask[k];
  const rows = new Uint32Array(count);
  let j = 0;
  for (let k = 0; k < n; k++) if (mask[k]) rows[j++] = k;
  return rows;
}

export function numAt(table, col, row) {
  const c = table.data[col];
  if (!c || c.type !== "f32") return null;
  const x = c.values[row];
  return Number.isNaN(x) ? null : x;
}

export function textAt(table, col, row) {
  const c = table.data[col];
  if (!c || c.type !== "text") return null;
  const code = c.codes[row];
  return code === MISSING_CODE ? null : c.dict[code];
}

// Row of a text value (e.g. a Mars cell id) or -1.
export function rowOfText(table, col, value) {
  const c = table.data[col];
  if (!c || c.type !== "text") return -1;
  const code = c.dict.indexOf(value);
  if (code < 0) return -1;
  for (let k = 0; k < table.rows; k++) if (c.codes[k] === code) return k;
  return -1;
}
