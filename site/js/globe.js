// Globe views. The planet is the image: sites (home) or candidates (Earth) are the only default marks.
// Unlocked cells are tiny warm points; coverage is a thin teal outline around the "to discover" cells.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLOBE_TEXTURE } from "./config.js";

const HOME_DIST = 3.4;            // planet fills about 85% of the panel height
const ZOOM_DIST = 1.9;
const SITE_COLOUR = 0x559bff;     // blue: the target world
const EARTH_COLOUR = 0x58cb91;    // green: Earth candidates
const SELECTED_COLOUR = 0xffffff;
const CELL_COLOUR = 0xfff1e0;     // warm white: unlocked cells, like city lights seen from orbit
const CELL_HIT = 0.013;           // invisible pick radius around a cell point
const CELL_ZOOM = 2.5;            // points grow, and become pickable, closer than this camera distance
const OUTLINE_RADIUS = 1.003;
const POINT_SIZE = 2;             // px, far
const POINT_SIZE_ZOOM = 4.5;      // px, near
const POINT_ALPHA = 0.6;
const ATMOSPHERE = { mars: 0xf0a070, earth: 0x7fc8ff };
export const EARTH_MARK_COLOUR = 0x9dffc8; // green: Earth places in an "Ask the atlas" answer
const MARK_COLOUR = 0xff8a66;   // coral: the Earth gap (no Earth window within sensor noise); not a score colour
const OUTLINE_SCALE = 4;          // texture pixels per coverage cell

// Texture convention of THREE.SphereGeometry: u = (lon + 180) / 360, east positive.
export function latLonToVec(lat, lon, radius = 1) {
  const phi = ((lon + 180) / 360) * Math.PI * 2;
  const lam = (lat * Math.PI) / 180;
  return new THREE.Vector3(
    -Math.cos(phi) * Math.cos(lam) * radius,
    Math.sin(lam) * radius,
    Math.sin(phi) * Math.cos(lam) * radius
  );
}

function easeInOutCubic(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

// Soft round sprite: a point of light with a gentle bloom falloff.
// A solid disc with a dark rim: reads on bright deserts and dark seas alike (the material colour tints only the fill).
function discTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 32;
  const ctx = c.getContext("2d");
  ctx.beginPath();
  ctx.arc(16, 16, 12, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(255,255,255,1)";
  ctx.fill();
  ctx.lineWidth = 5;
  ctx.strokeStyle = "rgba(4,7,15,0.92)";
  ctx.stroke();
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function spriteTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 32;
  const ctx = c.getContext("2d");
  const g = ctx.createRadialGradient(16, 16, 0, 16, 16, 16);
  g.addColorStop(0, "rgba(255,255,255,1)");
  g.addColorStop(0.25, "rgba(255,255,255,0.7)");
  g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 32, 32);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

// Thin feathered teal outline around the "to discover" cells (class 1). Only the cell edges that border a cell
// outside class 1 are drawn as hairlines, then softened; interiors stay clear. Class 0 and class 2 are not drawn here.
function outlineCanvas(cov) {
  const W = cov.width, H = cov.height, S = OUTLINE_SCALE;
  const edges = document.createElement("canvas");
  edges.width = W * S;
  edges.height = H * S;
  const ec = edges.getContext("2d");
  ec.fillStyle = "rgba(120, 226, 232, 0.42)";
  const is1 = (r, c) => r >= 0 && r < H && cov.grid[r * W + ((c + W) % W)] === 1;
  for (let r = 0; r < H; r++) {
    for (let c = 0; c < W; c++) {
      if (!is1(r, c)) continue;
      const x = c * S, y = r * S;
      if (!is1(r - 1, c)) ec.fillRect(x, y, S, 1);
      if (!is1(r + 1, c)) ec.fillRect(x, y + S - 1, S, 1);
      if (!is1(r, c - 1)) ec.fillRect(x, y, 1, S);
      if (!is1(r, c + 1)) ec.fillRect(x + S - 1, y, 1, S);
    }
  }
  const out = document.createElement("canvas");
  out.width = edges.width;
  out.height = edges.height;
  const oc = out.getContext("2d");
  oc.imageSmoothingEnabled = true;
  if ("filter" in oc) oc.filter = "blur(1.6px)";
  oc.drawImage(edges, 0, 0);
  return out;
}

export class GlobeView {
  // onPick(index) when a named site or candidate is clicked; onPickCell(index) when a Mars cell is clicked;
  // onNote(text) for the texture status line; onProject(x, y, visible, index) each frame for the labelled pin
  // (hover, then keyboard highlight, then selection).
  constructor(stage, { onPick, onPickCell, onNote, onProject, reduced, body = "earth", pinColour = SITE_COLOUR, focus = null }) {
    this.stage = stage;
    this.focus = focus;             // {lat, lon}: the default view of this globe (Earth: where most twins are)
    this.body = body;
    this.pinColour = pinColour;
    this.pinRadius = pinColour === EARTH_COLOUR ? 0.013 : 0.02;
    this.onPick = onPick;
    this.onPickCell = onPickCell;
    this.onNote = onNote;
    this.onProject = onProject;
    this.reduced = reduced;
    this.running = false;
    this.raf = null;
    this.anim = null;
    this.pins = [];
    this.hits = [];
    this.cellPins = [];
    this.selected = -1;
    this.highlight = null;
    this.hover = null;
    this.layer = "sites";
    this.fog = null;
    this.cellPoints = null;
    this.selPoint = null;
    this.selectedCell = -1;

    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setClearColor(0x0b0b0c, 1);
    stage.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(38, 1, 0.05, 100);
    this.camera.position.set(0, 0.5, HOME_DIST);
    if (focus) this.camera.position.copy(latLonToVec(focus.lat, focus.lon, 1).normalize().multiplyScalar(HOME_DIST));
    this.camera.lookAt(0, 0, 0);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enablePan = false;
    this.controls.enableDamping = true;
    this.controls.minDistance = 1.6;
    this.controls.maxDistance = 6;
    this.controls.autoRotate = !reduced && !focus;
    this.controls.autoRotateSpeed = 0.5;

    // Lighting from the viewer's side: the visible hemisphere is fully lit, with a gentle terminator only at the limb.
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.8));
    this.key = new THREE.DirectionalLight(0xfff4e8, 2.4);
    this.scene.add(this.key);
    this.key.position.copy(this.camera.position).normalize().multiplyScalar(10);
    this.scene.add(new THREE.HemisphereLight(0xdfeaff, 0x5a4636, 0.5));

    this.globe = new THREE.Mesh(
      new THREE.SphereGeometry(1, 128, 80),
      new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.9, metalness: 0 })
    );
    this.scene.add(this.globe);
    this.loadTexture();

    // A subtle atmosphere rim (none on the Moon).
    this.atmosphere = new THREE.Mesh(
      new THREE.SphereGeometry(1.06, 96, 64),
      new THREE.MeshBasicMaterial({ color: ATMOSPHERE.earth, transparent: true, opacity: 0.06, side: THREE.BackSide, depthWrite: false })
    );
    this.scene.add(this.atmosphere);
    this.setAtmosphere(body);
    this.scene.add(this.makeStars());

    this.sprite = spriteTexture();
    this.pinGroup = new THREE.Group();
    this.scene.add(this.pinGroup);
    this.cellGroup = new THREE.Group();
    this.cellGroup.visible = false;
    this.scene.add(this.cellGroup);
    this.regionalGroup = new THREE.Group();
    this.scene.add(this.regionalGroup);
    this.raycaster = new THREE.Raycaster();

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(stage);
    this.resize();

    this.downAt = null;
    const canvas = this.renderer.domElement;
    canvas.addEventListener("pointerdown", (e) => {
      this.downAt = [e.clientX, e.clientY];
    });
    canvas.addEventListener("pointermove", (e) => {
      if (this.downAt) return;
      const hit = this.hitTest(e);
      const gi = hit && hit.kind === "pin" ? hit.index : null;
      this.hover = gi;
      canvas.style.cursor = hit ? "pointer" : "";
    });
    canvas.addEventListener("pointerleave", () => { this.hover = null; });
    canvas.addEventListener("pointerup", (e) => {
      if (!this.downAt) return;
      const moved = Math.hypot(e.clientX - this.downAt[0], e.clientY - this.downAt[1]);
      this.downAt = null;
      if (moved > 6) return;
      this.pick(e);
    });

    this.frame = this.frame.bind(this);
  }

  loadTexture() {
    const url = new URL(`assets/globes/${this.body}.jpg`, document.baseURI).href;
    new THREE.TextureLoader().load(
      url,
      (tex) => {
        tex.colorSpace = THREE.SRGBColorSpace;
        tex.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
        this.globe.material.map = tex;
        this.globe.material.color.set(0xffffff);
        this.globe.material.needsUpdate = true;
        this.note("Globe texture loaded.");
      },
      undefined,
      () => this.note("No globe texture found (" + GLOBE_TEXTURE + "): plain sphere.")
    );
  }

  setBody(body) {
    if (body === this.body) return;
    this.body = body;
    this.setAtmosphere(body);
    this.loadTexture();
  }

  setAtmosphere(body) {
    this.atmosphere.visible = body !== "moon";
    this.atmosphere.material.color.set(ATMOSPHERE[body] || ATMOSPHERE.earth);
  }

  // The visible layer: "sites" (default), "cells" (Mars only) or "coverage" (teal outline, plus cell points on Mars).
  setLayer(layer) {
    this.layer = layer;
    if (this.fog) this.fog.visible = layer === "coverage";
    this.cellScaleKey = null;
    this.updateCellScale();
  }

  nudge(action) {
    const p = this.camera.position;
    if (action === "left" || action === "right") p.applyAxisAngle(new THREE.Vector3(0, 1, 0), action === "left" ? 0.25 : -0.25);
    if (action === "in" || action === "out") p.setLength(Math.max(1.6, Math.min(6, p.length() * (action === "in" ? 0.85 : 1.18))));
    this.controls.autoRotate = false;
    this.controls.update();
  }

  note(text) {
    if (this.onNote) this.onNote(text);
  }

  makeStars() {
    const count = 900;
    const pos = new Float32Array(count * 3);
    let seed = 20261114;
    const rnd = () => {
      seed = (seed * 16807) % 2147483647;
      return seed / 2147483647;
    };
    for (let i = 0; i < count; i++) {
      const u = rnd() * 2 - 1;
      const t = rnd() * Math.PI * 2;
      const r = 25 + rnd() * 25;
      const s = Math.sqrt(1 - u * u);
      pos[i * 3] = r * s * Math.cos(t);
      pos[i * 3 + 1] = r * u;
      pos[i * 3 + 2] = r * s * Math.sin(t);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    return new THREE.Points(geo, new THREE.PointsMaterial({ color: 0xdfe8ff, size: 0.09, sizeAttenuation: true }));
  }

  // Coverage outline (STANDARDS 10.13): cov = {width, height, grid, body} or null. Only class 1 is drawn.
  setCoverage(cov) {
    if (cov === this.coverageItem && (cov || this.fog === null)) return;
    this.coverageItem = cov;
    if (this.fog) {
      this.scene.remove(this.fog);
      this.fog.geometry.dispose();
      this.fog.material.map.dispose();
      this.fog.material.dispose();
      this.fog = null;
    }
    if (!cov || !Array.isArray(cov.grid) || cov.grid.length !== cov.width * cov.height) return;
    const tex = new THREE.CanvasTexture(outlineCanvas(cov));
    tex.colorSpace = THREE.SRGBColorSpace;
    this.fog = new THREE.Mesh(
      new THREE.SphereGeometry(OUTLINE_RADIUS, 128, 80),
      new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })
    );
    this.fog.visible = this.layer === "coverage";
    this.scene.add(this.fog);
  }

  // items: [{lat, lon, unlocked?}] in display order; the index is what onPick reports.
  // Named sites: solid markers with a soft halo. Earth candidates: small green points.
  setPins(items) {
    this.pinGroup.clear();
    this.pins = [];
    this.hits = [];
    this.selected = -1;
    items.forEach((g, gi) => {
      const pos = latLonToVec(g.lat, g.lon, 1.012);
      const colour = this.pinColour;
      const mesh = new THREE.Mesh(new THREE.SphereGeometry(this.pinRadius, 20, 14), new THREE.MeshBasicMaterial({ color: colour }));
      mesh.position.copy(pos);
      if (g.unlocked === false) { mesh.material.transparent = true; mesh.material.opacity = 0.35; }
      if (g.unlocked === true) {
        const halo = new THREE.Mesh(new THREE.SphereGeometry(this.pinRadius * 2.3, 16, 12), new THREE.MeshBasicMaterial({ color: colour, transparent: true, opacity: 0.2, depthWrite: false }));
        halo.position.copy(pos);
        this.pinGroup.add(halo);
      }
      const hit = new THREE.Mesh(new THREE.SphereGeometry(0.055, 12, 8), new THREE.MeshBasicMaterial({ visible: false }));
      hit.position.copy(pos);
      hit.userData.gi = gi;
      mesh.userData.gi = gi;
      this.pinGroup.add(mesh, hit);
      this.hits.push({ gi, mesh: hit });
      this.pins.push({ gi, mesh, dir: pos.clone().normalize(), colour });
    });
  }

  // Mars atlas cells: one warm point each (additive, soft bloom). Larger and pickable when zoomed in.
  setCells(items) {
    if (items === this.cellItems) return;
    this.cellItems = items;
    this.selectedCell = -1;
    this.cellScaleKey = null;
    this.cellGroup.clear();
    this.cellPins = [];
    if (this.cellPoints) {
      this.scene.remove(this.cellPoints);
      this.cellPoints.geometry.dispose();
      this.cellPoints.material.dispose();
      this.cellPoints = null;
    }
    if (this.selPoint) {
      this.scene.remove(this.selPoint);
      this.selPoint.geometry.dispose();
      this.selPoint.material.dispose();
      this.selPoint = null;
    }
    if (!items || !items.length) { this.updateCellScale(); return; }
    const positions = new Float32Array(items.length * 3);
    items.forEach((c, ci) => {
      const pos = latLonToVec(c.lat, c.lon, 1.012);
      positions.set([pos.x, pos.y, pos.z], ci * 3);
      const mesh = new THREE.Mesh(new THREE.SphereGeometry(CELL_HIT, 8, 6), new THREE.MeshBasicMaterial({ visible: false }));
      mesh.name = c.id || `cell ${ci}`;
      mesh.position.copy(pos);
      mesh.userData.ci = ci;
      this.cellGroup.add(mesh);
      this.cellPins.push({ ci, mesh, dir: pos.clone().normalize() });
    });
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    this.cellPoints = new THREE.Points(geo, new THREE.PointsMaterial({
      color: CELL_COLOUR, map: this.sprite, size: POINT_SIZE, sizeAttenuation: false,
      transparent: true, opacity: POINT_ALPHA, depthWrite: false, blending: THREE.AdditiveBlending,
    }));
    this.scene.add(this.cellPoints);
    const selGeo = new THREE.BufferGeometry();
    selGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(3), 3));
    this.selPoint = new THREE.Points(selGeo, new THREE.PointsMaterial({
      color: SELECTED_COLOUR, map: this.sprite, size: 9, sizeAttenuation: false,
      transparent: true, opacity: 1, depthWrite: false, blending: THREE.AdditiveBlending,
    }));
    this.selPoint.visible = false;
    this.scene.add(this.selPoint);
    this.updateCellScale();
  }

  // The chosen Mars cell gets a larger white point; -1 clears it.
  setCellSelected(ci) {
    this.selectedCell = ci;
    const cell = ci >= 0 && this.cellItems ? this.cellItems[ci] : null;
    if (this.selPoint) {
      if (cell) {
        const p = latLonToVec(cell.lat, cell.lon, 1.014);
        this.selPoint.geometry.attributes.position.setXYZ(0, p.x, p.y, p.z);
        this.selPoint.geometry.attributes.position.needsUpdate = true;
      }
      this.selPoint.visible = !!cell;
    }
    this.cellScaleKey = null;
    this.updateCellScale();
  }

  // Cell points show on the cells and coverage layers (Mars). They grow, and can be picked, when zoomed in.
  updateCellScale() {
    const d = this.camera.position.length();
    const zoomed = d < CELL_ZOOM;
    const onLayer = (this.layer === "cells" || this.layer === "coverage") && !!this.cellPoints;
    if (this.cellPoints) {
      this.cellPoints.visible = onLayer;
      this.cellPoints.material.size = zoomed ? POINT_SIZE_ZOOM : POINT_SIZE;
    }
    if (this.selPoint) this.selPoint.visible = onLayer && this.selectedCell >= 0 && !!this.cellItems;
    this.cellGroup.visible = onLayer && zoomed && this.cellPins.length > 0;
  }

  // Highlight a site from the keyboard list (focus); null clears it.
  setHighlight(gi) {
    this.highlight = gi === null || gi === undefined || gi < 0 ? null : gi;
  }

  // Regional cells are exploratory; their colour does not encode a score.
  setRegionalCells(cells) {
    for (const child of this.regionalGroup.children) { child.geometry.dispose(); child.material.dispose(); }
    this.regionalGroup.clear();
    if (!cells?.length) return;
    const positions = [];
    for (const cell of cells) { const v = latLonToVec(cell.lat, cell.lon, 1.006); positions.push(v.x, v.y, v.z); }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    this.regionalGroup.add(new THREE.Points(geometry, new THREE.PointsMaterial({ color: 0xf6a579, size: 0.018, transparent: true, opacity: 0.42, depthWrite: false })));
  }

  setSelected(gi) {
    this.selected = gi;
    for (const p of this.pins) {
      const on = p.gi === gi;
      p.mesh.material.color.set(on ? SELECTED_COLOUR : p.colour);
      p.mesh.scale.setScalar(on ? 1.7 : 1);
    }
  }

  hitTest(e) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1
    );
    this.raycaster.setFromCamera(ndc, this.camera);
    if (this.cellGroup.visible && this.cellPins.length) {
      const cell = this.raycaster.intersectObjects(this.cellPins.map((p) => p.mesh), false)[0];
      if (cell) return { kind: "cell", index: cell.object.userData.ci };
    }
    const pin = this.raycaster.intersectObjects(this.hits.map((p) => p.mesh), false)[0];
    if (pin) return { kind: "pin", index: pin.object.userData.gi };
    return null;
  }

  pick(e) {
    const hit = this.hitTest(e);
    if (!hit) return;
    if (hit.kind === "cell" && this.onPickCell) {
      this.setCellSelected(hit.index);
      this.onPickCell(hit.index);
    } else if (hit.kind === "pin" && this.onPick) {
      this.onPick(hit.index);
    }
  }

  // Camera flies over the globe's surface to the pin (spherical path, never through the globe).
  flyTo(gi) {
    const p = this.pins.find((x) => x.gi === gi);
    if (!p) return;
    this.animateTo(p.dir, this.orientOnly ? HOME_DIST : (this.zoomDist || ZOOM_DIST));
  }

  flyToCell(ci) {
    const p = this.cellPins.find((x) => x.ci === ci);
    if (!p) return;
    this.animateTo(p.dir, ZOOM_DIST);
  }

  resetView() {
    if (this.focus) this.animateTo(latLonToVec(this.focus.lat, this.focus.lon, 1), HOME_DIST);
    else this.animateTo(new THREE.Vector3(0, 0.15, 1).normalize(), HOME_DIST);
  }

  // Turns the whole planet to face a place, without zooming (the side globe of "Ask the atlas").
  faceLatLon(lat, lon) {
    this.animateTo(latLonToVec(lat, lon, 1), HOME_DIST);
  }

  // Turns the globe to a place (used by "Ask the atlas" results).
  flyToLatLon(lat, lon) {
    this.animateTo(latLonToVec(lat, lon, 1), ZOOM_DIST);
  }

  // Marks for the "Where Earth runs out" answer: coral points, drawn only while the answer is open. null clears them.
  setMarks(items, colour = MARK_COLOUR, size = 4) {
    if (this.marks) {
      this.scene.remove(this.marks);
      this.marks.geometry.dispose();
      this.marks.material.dispose();
      this.marks = null;
    }
    if (!items || !items.length) return;
    const positions = new Float32Array(items.length * 3);
    items.forEach((m, i) => {
      const v = latLonToVec(m.lat, m.lon, 1.02);
      positions.set([v.x, v.y, v.z], i * 3);
    });
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    this.marks = new THREE.Points(geo, new THREE.PointsMaterial({
      color: colour, map: size > 4 ? (this.disc ||= discTexture()) : this.sprite, size, sizeAttenuation: false, transparent: true, opacity: 0.95, depthWrite: false,
    }));
    this.scene.add(this.marks);
  }

  animateTo(dirB, dist) {
    this.controls.autoRotate = false;
    const pos = this.camera.position.clone();
    if (this.reduced) {
      this.camera.position.copy(dirB.clone().normalize().multiplyScalar(dist));
      this.camera.lookAt(0, 0, 0);
      this.anim = null;
      return;
    }
    this.anim = {
      dirA: pos.clone().normalize(),
      dirB: dirB.clone().normalize(),
      d0: pos.length(),
      d1: dist,
      t0: performance.now(),
      dur: 1300,
    };
    this.controls.enabled = false;
  }

  stepAnimation(now) {
    const a = this.anim;
    const e = easeInOutCubic(Math.min(1, (now - a.t0) / a.dur));
    const q = new THREE.Quaternion().setFromUnitVectors(a.dirA, a.dirB);
    const qi = new THREE.Quaternion().slerp(q, e);
    const dir = a.dirA.clone().applyQuaternion(qi);
    this.camera.position.copy(dir.multiplyScalar(a.d0 + (a.d1 - a.d0) * e));
    this.camera.lookAt(0, 0, 0);
    if (e >= 1) {
      this.anim = null;
      this.controls.enabled = true;
      this.controls.update();
    }
  }

  // The labelled pin: hover, then keyboard highlight, then selection. Position in CSS pixels of the stage.
  projectLabel() {
    if (!this.onProject) return;
    const gi = this.hover !== null ? this.hover : this.highlight !== null ? this.highlight : this.selected;
    const p = gi === null || gi < 0 ? null : this.pins.find((x) => x.gi === gi);
    if (!p) { this.onProject(0, 0, false, -1); return; }
    const toCamera = this.camera.position.clone().normalize();
    const visible = p.dir.dot(toCamera) > 0.12;
    const v = p.dir.clone().multiplyScalar(1.07).project(this.camera);
    const w = this.stage.clientWidth;
    const h = this.stage.clientHeight;
    this.onProject((v.x + 1) / 2 * w, (1 - v.y) / 2 * h, visible, gi);
  }

  resize() {
    const w = this.stage.clientWidth;
    const h = this.stage.clientHeight;
    if (w < 2 || h < 2) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  start() {
    this.running = true;
    if (this.raf === null) this.raf = requestAnimationFrame(this.frame);
  }

  stop() {
    this.running = false;
  }

  frame(now) {
    if (!this.running) {
      this.raf = null;
      return;
    }
    if (this.anim) this.stepAnimation(now);
    else this.controls.update();
    // Key light always comes from the viewer's side.
    this.key.position.copy(this.camera.position).normalize().multiplyScalar(10);
    this.updateCellScale();
    this.renderer.render(this.scene, this.camera);
    this.projectLabel();
    this.raf = requestAnimationFrame(this.frame);
  }
}
