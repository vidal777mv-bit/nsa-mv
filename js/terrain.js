// Pure terrain transforms: no DOM, no three.js. Used by hologram.js.

// Overlay colours for the layer toggles (RGB 0-1). Bits per STANDARDS 10.6:
// bit0 slope > landing limit, bit1 slope > driving limit, bit2 ridge, bit3 valley.
export const LAYER_COLOURS = {
  slopeHigh: [1.0, 0.3, 0.22],   // above the landing limit
  slopeMid: [1.0, 0.72, 0.18],   // above the driving limit only
  ridge: [0.55, 1.0, 0.5],
  valley: [0.66, 0.55, 1.0],
};

// Valid = finite height (NaN outside the 4 km disk).
export function validFrom(height) {
  const v = new Uint8Array(height.length);
  for (let i = 0; i < height.length; i++) v[i] = Number.isFinite(height[i]) ? 1 : 0;
  return v;
}

function bilinear(src, n, fi, fj) {
  if (fi < 0 || fj < 0 || fi > n - 1 || fj > n - 1) return NaN;
  const i0 = Math.min(Math.floor(fi), n - 2);
  const j0 = Math.min(Math.floor(fj), n - 2);
  const di = fi - i0;
  const dj = fj - j0;
  const a = src[i0 * n + j0];
  const b = src[i0 * n + j0 + 1];
  const c = src[(i0 + 1) * n + j0];
  const d = src[(i0 + 1) * n + j0 + 1];
  if (Number.isFinite(a) && Number.isFinite(b) && Number.isFinite(c) && Number.isFinite(d)) {
    return a * (1 - di) * (1 - dj) + b * (1 - di) * dj + c * di * (1 - dj) + d * di * dj;
  }
  const near = src[Math.round(fi) * n + Math.round(fj)];
  return Number.isFinite(near) ? near : NaN;
}

// Re-samples a terrain field into the frame of the target. Each target pixel p (inside R) takes
// the analog value at R(theta) p, counter-clockwise, north up. Heights are bilinear; layers nearest.
// Rotation only changes what is shown, never the score (STANDARDS 10.6).
export function rotateField(src, n, L, R, deg, isLayers) {
  const out = isLayers ? new Uint8Array(n * n) : new Float32Array(n * n).fill(NaN);
  const c = (n - 1) / 2;
  const th = (deg * Math.PI) / 180;
  const cs = Math.cos(th);
  const sn = Math.sin(th);
  for (let i = 0; i < n; i++) {
    const y = (c - i) * L;
    for (let j = 0; j < n; j++) {
      const x = (j - c) * L;
      const idx = i * n + j;
      if (Math.hypot(x, y) > R) continue;
      const xs = x * cs - y * sn;
      const ys = x * sn + y * cs;
      const fi = c - ys / L;
      const fj = c + xs / L;
      if (isLayers) {
        const ii = Math.round(fi);
        const jj = Math.round(fj);
        out[idx] = ii >= 0 && jj >= 0 && ii < n && jj < n ? src[ii * n + jj] : 0;
      } else {
        out[idx] = bilinear(src, n, fi, fj);
      }
    }
  }
  return out;
}

// Triangle index for every grid cell whose 4 corners are valid. Winding faces up (+y).
export function buildIndex(n, valid) {
  const idx = [];
  for (let i = 0; i < n - 1; i++) {
    for (let j = 0; j < n - 1; j++) {
      const a = i * n + j;
      const b = a + 1;
      const c = a + n;
      const d = c + 1;
      if (valid[a] && valid[b] && valid[c] && valid[d]) {
        idx.push(a, c, b, b, c, d);
      }
    }
  }
  return Uint32Array.from(idx);
}

// Hillshade-style brightness per vertex, computed from the mesh normals (which already include the
// pair's vertical exaggeration). sun = [x, y, z] unit vector, scene axes (y up). Result 0.28 to 1.
// Normals are flipped to face up, so the shading does not depend on triangle winding.
export function shadeFromNormals(normals, count, sun) {
  const out = new Float32Array(count);
  for (let v = 0; v < count; v++) {
    let nx = normals[v * 3];
    let ny = normals[v * 3 + 1];
    let nz = normals[v * 3 + 2];
    if (ny < 0) { nx = -nx; ny = -ny; nz = -nz; }
    const lambert = Math.max(0, nx * sun[0] + ny * sun[1] + nz * sun[2]);
    out[v] = Math.min(1, 0.28 + 0.8 * lambert);
  }
  return out;
}

// Colours every vertex: base colour (or shade-multiplied base), then the enabled layers on top
// (slope wins over ridge/valley). shade is optional; when given, every colour is multiplied by it
// so the relief stays visible through the layers.
export function paintLayers(layers, valid, base, toggles, out, shade = null) {
  for (let k = 0; k < layers.length; k++) {
    let c = base;
    if (valid[k]) {
      const bits = layers[k];
      if (toggles.ridges && bits & 4) c = LAYER_COLOURS.ridge;
      if (toggles.valleys && bits & 8) c = LAYER_COLOURS.valley;
      if (toggles.slope && bits & 3) c = bits & 1 ? LAYER_COLOURS.slopeHigh : LAYER_COLOURS.slopeMid;
    }
    const s = shade ? shade[k] : 1;
    out[k * 3] = c[0] * s;
    out[k * 3 + 1] = c[1] * s;
    out[k * 3 + 2] = c[2] * s;
  }
  return out;
}
