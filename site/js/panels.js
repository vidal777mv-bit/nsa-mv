// Text and gauge panels: measures (in the score / context), body facts, mission gauges, How we know.
import { FEATURE_INFO } from "./config.js";
import { h, fmt, sampleTag, sourceLink } from "./dom.js";

const ALL_KEYS = Object.keys(FEATURE_INFO);

function fmtFeature(key, v) {
  if (v === null || v === undefined || !Number.isFinite(v)) return "n/a";
  const info = FEATURE_INFO[key];
  return v.toFixed(info.digits) + (info.unit === "deg" ? "°" : info.unit);
}

// Bars show the signed difference relative to the target in sigma units, clipped at 3 sigma.
function bar(label, z, cls) {
  const valid = Number.isFinite(z);
  const width = valid ? Math.min(Math.abs(z) / 3, 1) * 50 : 0;
  const left = valid && z < 0 ? 50 - width : 50;
  return h("div", { class: "bar-row" }, h("span", { class: "bar-label" }, label),
    h("div", { class: "track", role: "img", "aria-label": `${label}: ${valid ? z.toFixed(2) + " sigma" : "not available"}`, style: "position:relative" },
      h("div", { class: "fill " + cls, style: `position:absolute;left:${left}%;width:${width}%` })));
}

// Scored measures are card.in_distance (STANDARDS 10.12). A card without in_distance (older export)
// is shown with all six measures as scored, labelled as such.
export function scoringKeys(card) {
  const scored = Array.isArray(card.in_distance) ? card.in_distance : ALL_KEYS;
  const context = Array.isArray(card.context_features) ? card.context_features : [];
  return { scored: ALL_KEYS.filter((k) => scored.includes(k)), context: ALL_KEYS.filter((k) => context.includes(k)),
    legacy: !Array.isArray(card.in_distance) };
}

function measureRow(card, key, kind) {
  const info = FEATURE_INFO[key];
  const f = (card.features && card.features[key]) || { target: null, analog: null };
  const isScoredMatch = (card.similar || []).includes(key);
  const isScoredDiffer = (card.different || []).includes(key);
  let cls = "context";
  let verdict = "Context, not scored";
  if (kind === "scored") {
    cls = isScoredMatch ? "match" : isScoredDiffer ? "differs" : "none";
    verdict = cls === "match" ? "Match" : cls === "differs" ? "Differs" : "No value";
  }
  const barCls = cls === "match" ? "fill-match" : cls === "differs" ? "fill-differs" : "fill-none";
  return h("div", { class: "feature " + cls },
    h("div", { class: "feature-head" },
      h("span", { class: "feature-name" }, info.label),
      h("span", { class: "feature-verdict" }, verdict)),
    h("p", { class: "feature-vals muted" }, `Target ${fmtFeature(key, f.target)} · Analog ${fmtFeature(key, f.analog)}`),
    h("p", { class: "note" }, `Difference (analog − target): ${Number.isFinite(f.z_diff) ? f.z_diff.toFixed(2) + " σ" : "n/a"}. Display clipped at ±3 σ.`),
    bar("Target", 0, "fill-target"),
    bar("Analog", f.z_diff, barCls));
}

// "Why this twin?" uses only the scored measures. Two groups below: in the score, and context.
export function renderFeatures(root, card) {
  root.replaceChildren();
  const { scored, context, legacy } = scoringKeys(card);
  const similar = (card.similar || []).filter((k) => scored.includes(k)).map((k) => FEATURE_INFO[k].label.toLowerCase());
  const different = (card.different || []).filter((k) => scored.includes(k)).map((k) => FEATURE_INFO[k].label.toLowerCase());
  const isSample = !!(card.provenance && card.provenance.sample);
  const list = (values) => (values.length ? values.join(", ") : "none");
  root.append(h("div", { class: "feature-summary" },
    h("h3", {}, "Why this twin?", isSample ? " " : "", isSample ? sampleTag() : null),
    h("p", {}, `Similar (within 1 sigma, in the score): ${list(similar)}.`),
    h("p", {}, `Different (more than 1 sigma, in the score): ${list(different)}.`),
    h("p", {}, `Distance D: ${fmt(card.D, 2)}. Lower D means a closer match on the scored measures.`),
    h("p", { class: "note" }, "Context measures are shown for information. They do not change D or the ranking."),
    isSample ? h("p", { class: "note" }, "SAMPLE: synthetic data and placeholder calibration; this is not a measured recommendation.") : null));

  root.append(h("h3", { class: "group-title" }, "In the score"));
  if (legacy) root.append(h("p", { class: "note" }, "This card does not list its scored measures; all six are treated as scored."));
  for (const key of scored) root.append(measureRow(card, key, "scored"));

  if (context.length) {
    root.append(h("h3", { class: "group-title" }, "Context (not scored)"));
    for (const key of context) root.append(measureRow(card, key, "context"));
  }
}

function gauge(label, value, colourVar) {
  const has = value !== null && value !== undefined && Number.isFinite(value);
  const p = has ? Math.max(0, Math.min(100, value)) : 0;
  return h(
    "figure",
    { class: "gauge-wrap" },
    h("div", {
      class: "gauge",
      style: `--p:${p.toFixed(2)};--c:var(${colourVar})`,
      role: "img",
      "aria-label": `${label}: ${has ? value.toFixed(1) + " percent" : "not available"}`,
    }, h("span", { class: "gauge-value" }, has ? `${value.toFixed(1)}%` : "n/a")),
    h("figcaption", {}, label)
  );
}

export function renderMissionBlock(root, kind, mp, names, isSample) {
  const title = kind === "landing" ? "Landing" : "Driving";
  const plain = kind === "landing"
    ? "Share of valid slopes in the 8 km circle at or below the landing limit that completed missions demonstrated."
    : "Share of valid slopes in the 8 km circle at or below the driving limit that rovers have used.";
  root.replaceChildren(
    h("h3", {}, title, isSample ? " " : "", isSample ? sampleTag() : null, " ", h("span", { class: "evidence-tag" }, "reference comparison")),
    h("p", {}, plain),
    h("div", { class: "gauges" },
      gauge(names.target, mp.target, "--c-target"),
      gauge(names.analog, mp.analog, "--c-analog")),
    h("dl", { class: "mini-facts" },
      h("dt", {}, "Limit"), h("dd", {}, Number.isFinite(mp.limit_deg) ? `${mp.limit_deg.toFixed(1)}° slope` : "Not available"),
      h("dt", {}, "Source"), h("dd", {}, sourceLink(mp.source))),
    h("p", { class: "note" }, "Slope measured at a 100 m baseline. Published limits may use another or no stated baseline, and may be design or planning criteria rather than measured mission performance.")
  );
}

// ---- How we know

const VERDICT = { pass: "Passed", fail: "Not passed", info: "Reported, no pass rule" };

function resultRow(label, result, verdict, kind) {
  return h("div", { class: "val-row" },
    h("div", { class: "val-id" }, h("strong", {}, label)),
    h("div", { class: "val-result" }, result),
    h("div", { class: "val-verdict " + kind }, verdict));
}

const ci = (pair, digits = 2) => (Array.isArray(pair) && pair.length === 2 ? `${fmt(pair[0], digits)} to ${fmt(pair[1], digits)}` : "not available");

function v12Block(b, sample) {
  const v0 = b.V0 || {};
  const v1 = b.V1 || {};
  const v2 = b.V2 || {};
  const v2r = b.V2R || {};
  const flagged = Array.isArray(v0.flagged) ? v0.flagged : [];
  const rows = [
    resultRow("V0 Redundancy",
      `${(v0.pairs || []).length} feature pairs checked on ${fmt(v0.n_pool, 0)} search-pool windows. Pairs above |rho| ${fmt(v0.max_abs_rho_threshold, 2)}: ${flagged.length ? flagged.join(", ") : "none"}.`,
      v0.pass ? VERDICT.pass : VERDICT.fail, v0.pass ? "ok" : "bad"),
    resultRow("V1 Sensor noise",
      `Median D ${fmt(v1.median, 2)}, p95 D ${fmt(v1.p95, 2)} over ${fmt(v1.n, 0)} regions measured with two elevation models (NASADEM and Copernicus GLO-30).`,
      VERDICT.info, ""),
    resultRow("V2 Discrimination",
      `AUC ${fmt(v2.auc, 2)} (95% CI ${ci(v2.bootstrap && [v2.bootstrap.ci_lo, v2.bootstrap.ci_hi])}), permutation p ${fmt(v2.permutation && v2.permutation.p, 3)}. Needs AUC at least 0.70, CI lower bound above 0.5, p below 0.05.`,
      v2.pass ? VERDICT.pass : VERDICT.fail, v2.pass ? "ok" : "bad"),
    resultRow("V2-R Reserve regions",
      `${fmt(v2r.k_correct, 0)} of ${fmt(v2r.n_computed, 0)} correct (Wilson 95% ${ci(v2r.wilson95)}). Needs at least ${fmt(v2r.reserve_min_correct, 0)} of 5.`,
      v2r.pass ? VERDICT.pass : VERDICT.fail, v2r.pass ? "ok" : "bad"),
  ];
  return h("section", { class: "val-block", "aria-label": "Version 1.2" },
    h("h3", {}, "Version 1.2 · first run", sample ? " " : "", sample ? sampleTag() : null),
    h("p", { class: "val-status bad" }, `Status: ${b.status || "not available"}. Reported as it came out.`),
    h("div", { class: "val-list" }, ...rows),
    b.diagnosis ? h("div", { class: "diagnosis" }, h("h4", {}, "Diagnosis"), h("p", {}, b.diagnosis)) : null);
}

function v13Block(b, noise, sample) {
  const auc = b.AUC || {};
  const nn = (b.NN && b.NN.summary) || {};
  const pass = b.pass || {};
  const rows = [
    resultRow("Discrimination on the fresh regions",
      `AUC ${fmt(auc.auc, 2)} (95% CI ${ci(auc.bootstrap && [auc.bootstrap.ci_lo, auc.bootstrap.ci_hi])}), permutation p ${fmt(auc.permutation && auc.permutation.p, 4)}. Needs AUC at least 0.70. Criteria: AUC ${pass.auc ? "passed" : "not passed"}; CI lower bound above 0.5 ${pass.auc_ci_lower ? "passed" : "not passed"}; permutation p ${pass.permutation_p ? "passed" : "not passed"}.`,
      pass.auc && pass.auc_ci_lower && pass.permutation_p ? VERDICT.pass : VERDICT.fail, pass.auc && pass.auc_ci_lower && pass.permutation_p ? "ok" : "bad"),
    resultRow("Nearest-twin test (1-NN)",
      `${fmt(nn.k_correct, 0)} of ${fmt(nn.n_computed, 0)} fresh regions matched to the right class among the 15 development regions (Wilson 95% ${ci(nn.wilson95)}). Needs at least ${fmt(nn.min_correct, 0)}. Chance is 1 in 5; one-sided binomial p ${fmt(nn.binomial_one_sided_p, 3)}.`,
      pass.nn_against_dev ? VERDICT.pass : VERDICT.fail, pass.nn_against_dev ? "ok" : "bad"),
  ];
  const holdoutRows = Array.isArray(b.NN && b.NN.rows) ? b.NN.rows : [];
  return h("section", { class: "val-block", "aria-label": "Version 1.3" },
    h("h3", {}, "Version 1.3 · fresh blind test", sample ? " " : "", sample ? sampleTag() : null),
    h("p", { class: "val-status bad" }, `Status: ${b.status || "not available"}. Fifteen new regions, chosen by landform only and measured once. Reported as it came out.`),
    h("p", { class: "note" }, "Measures in the score: steepness, bowl vs plateau and bumpiness across scales. Grain direction, ridges and hollows are context."),
    h("div", { class: "val-list" }, ...rows),
    holdoutRows.length ? h("details", { class: "region-table" },
      h("summary", {}, `Region by region (${holdoutRows.length} fresh regions)`),
      h("div", { class: "table-scroll" },
        h("table", {},
          h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Region"), h("th", { scope: "col" }, "Class"), h("th", { scope: "col" }, "Nearest dev region"), h("th", { scope: "col" }, "Predicted"), h("th", { scope: "col" }, "Correct"))),
          h("tbody", {}, ...holdoutRows.map((r) => h("tr", {},
            h("td", {}, String(r.region_id || "").replace(/^holdout_/, "").replace(/_/g, " ")),
            h("td", {}, String(r.true_class || "").replace(/_/g, " ")),
            h("td", {}, String(r.nearest_dev || "").replace(/_/g, " ")),
            h("td", {}, String(r.predicted_class || "").replace(/_/g, " ")),
            h("td", {}, r.correct ? "yes" : "no"))))))) : null,
    noise && noise.classes ? h("p", { class: "note" },
      `Sensor noise used for ties (p95 of D between the two elevation models): ` +
      Object.entries(noise.classes).map(([cls, c]) => `${cls} ${fmt(c.p95, 2)} (${c.n} regions)`).join("; ") + ".") : null);
}

// Mission controls: the two reference sites that must be well covered by the limit (STANDARDS 10.3).
export function renderControls(root, controls) {
  root.replaceChildren();
  if (!controls.length) { root.append(h("p", { class: "note" }, "Control values not available.")); return; }
  for (const c of controls) {
    const ok = c.values.every((v) => Number.isFinite(v) && v >= 50);
    root.append(h("div", { class: "val-row" },
      h("div", { class: "val-id" }, h("strong", {}, c.label)),
      h("div", { class: "val-result" }, c.text),
      h("div", { class: "val-verdict " + (ok ? "ok" : "bad") }, ok ? "Passed" : "Not passed")));
  }
}

export function renderValidation(root, validation, sample) {
  root.replaceChildren();
  if (!validation || (!validation["v1.2"] && !validation["v1.3"])) {
    root.append(h("p", { class: "note" }, "Validation results are not in this data set."));
    return;
  }
  if (validation["v1.2"]) root.append(v12Block(validation["v1.2"], sample));
  if (validation["v1.3"]) root.append(v13Block(validation["v1.3"], validation["v1.3_noise"] || {}, sample));
}

// ---- Unlocked atlas (STANDARDS 10.13): novelty badge, Earth context, refined offset

// "New" or "Known analog region"; nothing when the export does not say.
export function noveltyBadge(novelty) {
  if (novelty === "new") return h("span", { class: "badge-new" }, "New");
  if (novelty === "known_region") return h("span", { class: "badge-known" }, "Known analog region");
  return null;
}

// Earth context is not scored. Shown under "Can a team go there?" on the twin card.
// Refined search (STANDARDS 10.13): the export carries card.refined {refined_offset_km, D_before, ...}.
// Returns a sentence, or null when the export has no refinement for this twin.
export function refinedSummary(card) {
  const r = card.refined || null;
  const off = r && Array.isArray(r.refined_offset_km) ? r.refined_offset_km : (Array.isArray(card.refined_offset_km) ? card.refined_offset_km : null);
  if (!off || off.length !== 2) return null;
  const [east, north] = off;
  if (!east && !north) return "The centred window is already the best of the 4 km search.";
  const dir = [
    Math.abs(east) > 0 ? `${fmt(Math.abs(east), 1)} km ${east >= 0 ? "east" : "west"}` : null,
    Math.abs(north) > 0 ? `${fmt(Math.abs(north), 1)} km ${north >= 0 ? "north" : "south"}` : null,
  ].filter(Boolean).join(" and ");
  const before = r && Number.isFinite(r.D_before) ? r.D_before : card.refined_D_before;
  const after = Number.isFinite(card.D) ? card.D : card.refined_D_after;
  const delta = Number.isFinite(before) && Number.isFinite(after) ? ` D ${fmt(before, 2)} before, ${fmt(after, 2)} after.` : "";
  return `Best window within 4 km: shifted ${dir} from the pool centre.${delta} Ranking order may change.`;
}

// Earth context: climate, elevation, nearest town. Not scored. Sources may be an object of labels (export) or a list.
export function renderContext(root, card) {
  root.replaceChildren();
  const c = card.context || null;
  if (!c) {
    root.append(h("p", { class: "note" }, "Earth context (climate, elevation, nearest town) is not in this data set yet."));
  } else {
    const t = c.nearest_town || {};
    const town = t.name
      ? `${t.name}${t.country ? ` (${t.country})` : ""}${Number.isFinite(t.distance_km) ? `, ${fmt(t.distance_km, 1)} km away` : ""}`
      : "not available";
    root.append(h("dl", { class: "mini-facts" },
      h("dt", {}, "Climate"), h("dd", {}, c.koppen_label ? `${c.koppen_label} (${c.koppen_class || "class n/a"}, Köppen-Geiger)` : "not available"),
      h("dt", {}, "Elevation"), h("dd", {}, Number.isFinite(c.elevation_m) ? `${fmt(c.elevation_m, 0)} m (window mean)` : "not available"),
      h("dt", {}, "Nearest town"), h("dd", {}, town)));
    const src = c.sources;
    const items = Array.isArray(src)
      ? src.map((x) => (typeof x === "string" ? [x, null] : [x && x.label || x && x.url || "Source", x && x.url || null]))
      : src && typeof src === "object" ? Object.values(src).filter((x) => typeof x === "string").map((x) => [x, /^https?:\/\//.test(x) ? x : null]) : [];
    if (items.length) {
      root.append(h("details", { class: "note sources" },
        h("summary", {}, `Sources for this context (${items.length})`),
        h("ul", { class: "plain" }, ...items.map(([label, url]) => h("li", {}, url ? sourceLink(url, label) : label)))));
    }
  }
  if (c && c.sample) root.append(h("p", { class: "note" }, sampleTag(), " Context values are placeholders."));
}
