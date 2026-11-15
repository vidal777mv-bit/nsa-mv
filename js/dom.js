// Small DOM helpers. Text is always set with textContent or text nodes (no HTML from data files).
import { SOURCE_LABELS } from "./config.js";

export function h(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

export function fmt(x, digits = 1, suffix = "") {
  if (x === null || x === undefined || !Number.isFinite(x)) return "n/a";
  return x.toFixed(digits) + suffix;
}

export function latlon(lat, lon) {
  const ns = lat >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(4)}° ${ns}, ${Math.abs(lon).toFixed(4)}° ${ew}`;
}

// Short label for a source URL (SOURCE_LABELS), else the host name. Never the raw URL.
export function sourceLabel(url) {
  if (SOURCE_LABELS[url]) return SOURCE_LABELS[url];
  try {
    return `Source: ${new URL(url).hostname}`;
  } catch (_) {
    return "Source link";
  }
}

// A source as a link with a short label, or as plain text when there is no URL.
export function sourceLink(url, fallbackText = "Source not available") {
  if (!url || !/^https?:\/\//.test(url)) return fallbackText;
  return h("a", { href: url, target: "_blank", rel: "noopener noreferrer" }, sourceLabel(url));
}

export function sampleTag() {
  return h("span", { class: "sample-tag", title: "Placeholder or synthetic data, not a NASA result" }, "SAMPLE");
}
