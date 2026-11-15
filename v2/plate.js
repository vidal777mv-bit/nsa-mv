// Terrain plate: an 8 km disc of measured elevation drawn as a survey plate
// (hillshade + elevation tint + contour lines). Both worlds are drawn at the same
// horizontal scale, the same shading exaggeration and the same contour interval,
// so what differs on screen is the ground, not the drawing.

export const SHADE_EXAGGERATION = 3;

const TINTS = {
  mars: [[0.0, [120, 46, 26]], [0.5, [186, 92, 52]], [1.0, [236, 184, 140]]],
  moon: [[0.0, [70, 74, 80]], [0.5, [138, 140, 142]], [1.0, [222, 222, 216]]],
  earth: [[0.0, [96, 78, 52]], [0.5, [168, 140, 94]], [1.0, [232, 214, 170]]],
};

function tint(body, t) {
  const stops = TINTS[body] || TINTS.earth;
  t = Math.max(0, Math.min(1, t));
  for (let i = 1; i < stops.length; i++) {
    if (t <= stops[i][0]) {
      const [t0, c0] = stops[i - 1], [t1, c1] = stops[i];
      const k = (t - t0) / (t1 - t0);
      return [c0[0] + (c1[0] - c0[0]) * k, c0[1] + (c1[1] - c0[1]) * k, c0[2] + (c1[2] - c0[2]) * k];
    }
  }
  return stops[stops.length - 1][1];
}

export function niceStep(range, lines = 14) {
  const raw = range / lines;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= raw) return m * p;
  return 10 * p;
}

function percentile(arr, q) {
  const a = arr.filter(Number.isFinite).sort((x, y) => x - y);
  if (!a.length) return 0;
  return a[Math.min(a.length - 1, Math.max(0, Math.round(q * (a.length - 1))))];
}

export function reliefRange(terrain) {
  const lo = percentile(Array.from(terrain.height), 0.01);
  const hi = percentile(Array.from(terrain.height), 0.99);
  return { lo, hi, range: Math.max(1e-6, hi - lo) };
}

// terrain: {n, L (m per cell), height: Float32Array}. opts: {body, size, contour}
export function drawPlate(canvas, terrain, { body, size = 560, contour }) {
  const { n, L, height } = terrain;
  canvas.width = size;
  canvas.height = size;
  const g = canvas.getContext("2d");
  const img = g.createImageData(size, size);
  const { lo, range } = reliefRange(terrain);

  // Hillshade on the grid (multi-directional, altitude 45 deg).
  const shade = new Float32Array(n * n).fill(NaN);
  const zf = SHADE_EXAGGERATION;
  const dirs = [[315, 0.5], [270, 0.25], [0, 0.25]].map(([az, w]) => [((360 - az + 90) * Math.PI) / 180, w]);
  const alt = (45 * Math.PI) / 180;
  const at = (x, y) => height[y * n + x];
  for (let y = 1; y < n - 1; y++) {
    for (let x = 1; x < n - 1; x++) {
      const zc = at(x, y);
      if (!Number.isFinite(zc)) continue;
      const zl = at(x - 1, y), zr = at(x + 1, y), zu = at(x, y - 1), zd = at(x, y + 1);
      if (![zl, zr, zu, zd].every(Number.isFinite)) { shade[y * n + x] = 0.7; continue; }
      const dzdx = ((zr - zl) / (2 * L)) * zf;
      const dzdy = ((zd - zu) / (2 * L)) * zf;
      const slope = Math.atan(Math.hypot(dzdx, dzdy));
      const aspect = Math.atan2(dzdy, -dzdx);
      let s = 0;
      for (const [azr, w] of dirs) {
        s += w * Math.max(0, Math.cos(alt) * Math.cos(slope) + Math.sin(alt) * Math.sin(slope) * Math.cos(azr - aspect));
      }
      shade[y * n + x] = s;
    }
  }

  // Sample (bilinear) at plate resolution.
  const zs = new Float32Array(size * size).fill(NaN);
  const ss = new Float32Array(size * size).fill(NaN);
  const scale = (n - 1) / (size - 1);
  for (let py = 0; py < size; py++) {
    const gy = py * scale, y0 = Math.floor(gy), y1 = Math.min(n - 1, y0 + 1), fy = gy - y0;
    for (let px = 0; px < size; px++) {
      const gx = px * scale, x0 = Math.floor(gx), x1 = Math.min(n - 1, x0 + 1), fx = gx - x0;
      const i00 = y0 * n + x0, i10 = y0 * n + x1, i01 = y1 * n + x0, i11 = y1 * n + x1;
      const h = [height[i00], height[i10], height[i01], height[i11]];
      if (!h.every(Number.isFinite)) continue;
      const k = py * size + px;
      zs[k] = (h[0] * (1 - fx) + h[1] * fx) * (1 - fy) + (h[2] * (1 - fx) + h[3] * fx) * fy;
      const s = [shade[i00], shade[i10], shade[i01], shade[i11]].map((v) => (Number.isFinite(v) ? v : 0.7));
      ss[k] = (s[0] * (1 - fx) + s[1] * fx) * (1 - fy) + (s[2] * (1 - fx) + s[3] * fx) * fy;
    }
  }

  const ci = contour;
  for (let py = 0; py < size; py++) {
    for (let px = 0; px < size; px++) {
      const k = py * size + px, o = k * 4;
      const z = zs[k];
      if (!Number.isFinite(z)) { img.data[o + 3] = 0; continue; }
      const c = tint(body, (z - lo) / range);
      const sh = 0.35 + 0.85 * ss[k];
      let r = c[0] * sh, gg = c[1] * sh, b = c[2] * sh;
      // Contour: the band index changes towards the right or lower neighbour.
      if (ci > 0 && px < size - 1 && py < size - 1) {
        const band = Math.floor(z / ci);
        const zr = zs[k + 1], zd = zs[k + size];
        const br = Number.isFinite(zr) ? Math.floor(zr / ci) : band;
        const bd = Number.isFinite(zd) ? Math.floor(zd / ci) : band;
        if (br !== band || bd !== band) {
          const major = Math.max(br, bd, band) % 5 === 0;
          const a = major ? 0.62 : 0.32;
          r = r * (1 - a) + 26 * a; gg = gg * (1 - a) + 25 * a; b = b * (1 - a) + 22 * a;
        }
      }
      img.data[o] = r; img.data[o + 1] = gg; img.data[o + 2] = b; img.data[o + 3] = 255;
    }
  }
  g.putImageData(img, 0, 0);
}
