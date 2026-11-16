// Download of the Earth options of the chosen site (CSV or GeoJSON). Reads the analog rows already loaded in app.js (S.analogs); no fetch here.
// A field the export does not carry is written empty (CSV) or null (GeoJSON), never guessed.

const COLUMNS = ["rank", "place", "admin1", "country", "lat", "lon", "D", "tie_group", "novelty", "koppen", "nearest_town", "nearest_town_km", "source"];

// Number or text as given; missing, NaN or null become "".
const clean = (v) => (v === null || v === undefined || (typeof v === "number" && !Number.isFinite(v)) ? "" : v);

export function earthOptionRows(analogs) {
  return analogs.map((a, i) => {
    const place = a.analog_place || {};
    const ctx = a.context || {};
    const town = ctx.nearest_town || {};
    return {
      rank: clean(a.rank ?? i + 1),
      place: clean(place.name),
      admin1: clean(place.admin1),
      country: clean(place.country),
      lat: clean(a.lat),
      lon: clean(a.lon),
      D: clean(a.D),
      tie_group: clean(a.tie_group),
      novelty: clean(a.novelty),
      koppen: clean(ctx.koppen_class),
      nearest_town: clean(town.name),
      nearest_town_km: clean(town.distance_km),
      source: clean(place.source),
    };
  });
}

const csvField = (v) => {
  const s = String(v);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

// UTF-8 with a byte-order mark so spreadsheets read accented place names correctly.
export function toCsv(rows) {
  const lines = [COLUMNS.join(","), ...rows.map((r) => COLUMNS.map((c) => csvField(r[c])).join(","))];
  return "﻿" + lines.join("\r\n") + "\r\n";
}

export function toGeoJson(rows, name) {
  return {
    type: "FeatureCollection",
    name,
    features: rows.map((r) => {
      const properties = {};
      for (const c of COLUMNS) properties[c] = r[c] === "" ? null : r[c];
      const hasPoint = typeof r.lat === "number" && typeof r.lon === "number";
      return { type: "Feature", properties, geometry: hasPoint ? { type: "Point", coordinates: [r.lon, r.lat] } : null };
    }),
  };
}

function download(filename, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// kind: "csv" or "geojson". site: the site id (S.target.id), used in the file name only.
export function saveEarthOptions(kind, site, analogs) {
  const rows = earthOptionRows(analogs);
  const base = `commonground_${String(site).replace(/[^a-z0-9_-]+/gi, "_")}_earth_options`;
  if (kind === "csv") download(`${base}.csv`, toCsv(rows), "text/csv;charset=utf-8");
  else download(`${base}.geojson`, JSON.stringify(toGeoJson(rows, base), null, 2), "application/geo+json;charset=utf-8");
}
