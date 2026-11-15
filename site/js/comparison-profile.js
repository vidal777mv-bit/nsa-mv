// Display-only sampling. Heights remain metres relative to each disk mean.
// No metric, score, threshold, or scientific classification is computed here.
export function alignHeights(src, n, L, R, degrees = 0) {
  const out = new Float32Array(n * n).fill(NaN);
  const c = (n - 1) / 2;
  const a = degrees * Math.PI / 180, co = Math.cos(a), si = Math.sin(a);
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    const x = (j - c) * L, y = (c - i) * L;
    if (Math.hypot(x, y) > R) continue;
    const fi = c - (x * si + y * co) / L;
    const fj = c + (x * co - y * si) / L;
    if (fi < -1e-6 || fj < -1e-6 || fi > n - 1 + 1e-6 || fj > n - 1 + 1e-6) continue;
    const ri = Math.max(0, Math.min(n - 1, fi)), rj = Math.max(0, Math.min(n - 1, fj));
    const i0 = Math.floor(ri), j0 = Math.floor(rj), i1 = Math.min(n - 1, i0 + 1), j1 = Math.min(n - 1, j0 + 1);
    const di = ri - i0, dj = rj - j0;
    const points = [[i0, j0, (1-di)*(1-dj)], [i0, j1, (1-di)*dj], [i1, j0, di*(1-dj)], [i1, j1, di*dj]];
    let value = 0, ok = true;
    for (const [r, q, weight] of points) {
      if (weight < 1e-8) continue;
      const v = src[r * n + q];
      if (!Number.isFinite(v)) { ok = false; break; }
      value += weight * v;
    }
    if (ok) out[i * n + j] = value;
  }
  return out;
}

// Display-only levelling ("Levelled"): remove each disk's overall tilt, the least-squares
// plane z = a*x + b*y + c fitted on its valid pixels inside the 8 km circle (x east, y north,
// metres), then its mean, so both disks share one midpoint. Finite pixels outside the fit
// are kept with the same plane removed. Source heights are never modified.
export function levelHeights(src, n, L, R) {
  const c = (n - 1) / 2;
  // Normal equations for [x y 1] using the disk pixels only.
  const S = [[0, 0, 0], [0, 0, 0], [0, 0, 0]], T = [0, 0, 0];
  let count = 0;
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    const v = src[i * n + j];
    const x = (j - c) * L, y = (c - i) * L;
    if (!Number.isFinite(v) || Math.hypot(x, y) > R) continue;
    const row = [x, y, 1];
    for (let p = 0; p < 3; p++) { T[p] += row[p] * v; for (let q = 0; q < 3; q++) S[p][q] += row[p] * row[q]; }
    count++;
  }
  let coef = null;
  if (count >= 3) coef = solve3(S, T);
  const plane = (x, y) => coef ? coef[0] * x + coef[1] * y + coef[2] : 0;
  const out = new Float32Array(n * n).fill(NaN);
  // Mean of the residuals over the fitted disk pixels: the common midpoint.
  let sum = 0, fitted = 0;
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
    const v = src[i * n + j];
    const x = (j - c) * L, y = (c - i) * L;
    if (!Number.isFinite(v)) continue;
    out[i * n + j] = v - plane(x, y);
    if (Math.hypot(x, y) <= R) { sum += out[i * n + j]; fitted++; }
  }
  const mean = fitted ? sum / fitted : 0;
  for (let v = 0; v < out.length; v++) if (Number.isFinite(out[v])) out[v] -= mean;
  return out;
}

// Solves a 3x3 linear system by Cramer's rule; null when the system is singular.
function solve3(M, b) {
  const det = (m) => m[0][0]*(m[1][1]*m[2][2]-m[1][2]*m[2][1]) - m[0][1]*(m[1][0]*m[2][2]-m[1][2]*m[2][0]) + m[0][2]*(m[1][0]*m[2][1]-m[1][1]*m[2][0]);
  const d = det(M);
  if (!Number.isFinite(d) || Math.abs(d) < 1e-12) return null;
  const out = [0, 0, 0];
  for (let k = 0; k < 3; k++) {
    const m = M.map((row, r) => row.map((val, col) => col === k ? b[r] : val));
    out[k] = det(m) / d;
  }
  return out;
}

// Fraction moves a west-to-east section from north (0) to south (1).
// Snap to the nearest exported row, preserving all nodata gaps.
// Distance is signed kilometres east of the window centre.
export function sampleProfile(target, analog, n, L, fraction) {
  const row = Math.round(Math.max(0, Math.min(1, fraction)) * (n - 1));
  const c = (n - 1) / 2;
  return Array.from({length: n}, (_, j) => ({
    distanceKm: (j - c) * L / 1000,
    target: Number.isFinite(target[row*n+j]) ? target[row*n+j] : null,
    analog: Number.isFinite(analog[row*n+j]) ? analog[row*n+j] : null,
  }));
}

// Conservative perspective bound of a disk and its relief, including the second
// disk's screen-plane offset. The bound adapts to camera elevation, so resetting
// or resizing a near-top-down view does not crop the terrain with a fixed ratio.
export function terrainFitDistance(radius, relief, aspect, fov, spread, stacked, elevation) {
  const sin=Math.abs(Math.sin(elevation)), cos=Math.abs(Math.cos(elevation));
  const sep=radius*1.12*spread;
  const halfW=radius+(stacked?0:sep);
  const halfH=radius*sin+relief*cos+(stacked?sep:0);
  const depth=radius*cos+relief*sin;
  const tanV=Math.tan(fov/2),tanH=tanV*aspect;
  return Math.max(halfW/tanH,halfH/tanV)*1.08+depth+.01;
}
