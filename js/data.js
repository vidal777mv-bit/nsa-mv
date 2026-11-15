// Loads the data contract (STANDARDS 10.5, 10.6, 10.9, 10.12) from DATA_BASE. No rendering here.
import { DATA_BASE } from "./config.js";

const cache = new Map();

function fetchOnce(relPath, kind) {
  const key = kind + ":" + relPath;
  if (!cache.has(key)) {
    const p = fetch(DATA_BASE + relPath).then((r) => {
      if (!r.ok) throw new Error(`${relPath}: HTTP ${r.status}`);
      return kind === "json" ? r.json() : r.arrayBuffer();
    });
    p.catch(() => cache.delete(key));
    cache.set(key, p);
  }
  return cache.get(key);
}

// Place name from the export (analog_place.name, "admin1, country"). Never a pool id.
export function placeName(row) {
  const name = row && row.analog_place && row.analog_place.name;
  return name || "Unnamed place";
}

// Small secondary code for a search-pool analog. Ids may carry the target prefix:
// "pool__pool_01913" and "jezero__pool__pool_00226" both give "pool 01913" / "pool 00226".
export function analogCode(id) {
  if (!id) return "";
  const pool = /(?:^|__)pool__pool_(\d+)$/.exec(id);
  if (pool) return `pool ${pool[1]}`;
  return id.replace(/__/g, " ").replace(/_/g, " ");
}

export async function getJSON(relPath) {
  const doc = await fetchOnce(relPath, "json");
  if (!relPath.startsWith("rankings/")) return doc;
  const rows = doc.analogs || doc.ranking || [];
  return { ...doc, analogs: rows.map((row) => ({ ...row, name: placeName(row), code: analogCode(row.analog_id) })) };
}

export async function loadIndex() {
  const [targets, viz, validation, bodies, missions] = await Promise.all([
    getJSON("targets.json"),
    getJSON("viz.json"),
    getJSON("validation.json"),
    getJSON("bodies.json"),
    getJSON("missions.json"),
  ]);
  const targetRows = Array.isArray(targets) ? targets : targets.targets || [];
  const normalizedTargets = { ...(!Array.isArray(targets) ? targets : {}), targets: targetRows.map((t) => ({
    ...t, ranking: t.ranking || `rankings/${t.id}.json`
  })) };
  return { targets: normalizedTargets, viz: { horizontal_m_per_unit: 1000, ...viz }, validation,
    bodies: bodies.bodies || bodies, missions };
}

// terrainDir is "terrain/<id>/" as written in a card's files block.
export async function loadTerrain(terrainDir, body) {
  const meta = await getJSON(terrainDir + "meta.json");
  const layerBody = body || meta.body;
  if (!["earth", "moon", "mars"].includes(layerBody)) throw new Error(`${terrainDir}: invalid layer body`);
  const [hBuf, lBuf] = await Promise.all([
    fetchOnce(terrainDir + "height.bin", "bin"),
    fetchOnce(terrainDir + `layers_${layerBody}.bin`, "bin"),
  ]);
  const n = meta.n;
  if (hBuf.byteLength !== n * n * 4) throw new Error(`${terrainDir}height.bin: wrong size`);
  if (lBuf.byteLength !== n * n) throw new Error(`${terrainDir}layers_${layerBody}.bin: wrong size`);
  // Float32 little-endian, read explicitly so the byte order never depends on the machine.
  const view = new DataView(hBuf);
  const height = new Float32Array(n * n);
  for (let i = 0; i < n * n; i++) height[i] = view.getFloat32(i * 4, true);
  return {
    n,
    L: meta.L,
    R: meta.R,
    height,
    layers: new Uint8Array(lBuf),
    meta,
  };
}
