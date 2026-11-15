// The core view: analog (Earth) terrain as a solid mesh shaded from its own height normals, and the
// target terrain as a hologram on top: grid lines and a fresnel edge over a low fill.
// Same grid, same scale, same vertical exaggeration for both (the pair's card value). Units: 1 unit = 1 km.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { rotateField, validFrom, buildIndex, paintLayers, shadeFromNormals } from "./terrain.js";

// Sun: azimuth 315 deg (north-west), altitude 45 deg, the same for every hillshade.
// Scene axes: x east, y up, z south (so -z is north).
const SUN_DIR = new THREE.Vector3(-0.5, 0.7071, -0.5).normalize();
const SUN = [SUN_DIR.x, SUN_DIR.y, SUN_DIR.z];
const HOLO_BASE = [0.35, 0.93, 1.0];
const SOLID_BASE = [0.66, 0.62, 0.55];
const ELEVATION_DEG = 35;     // default camera elevation above the disk

const HOLO_VERT = `
varying vec3 vWorld;
varying vec3 vNormalW;
varying vec2 vGrid;
varying vec3 vCol;
void main() {
  vec4 wp = modelMatrix * vec4(position, 1.0);
  vWorld = wp.xyz;
  vNormalW = normalize(mat3(modelMatrix) * normal);
  vGrid = uv;
  vCol = color;
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;

// Fill alpha is at most 0.22 (target 0.15-0.25) so the solid terrain reads underneath.
// Grid lines and the fresnel edge carry the hologram. uOpacity is the "Hologram opacity" slider (0-1).
const HOLO_FRAG = `
uniform float uTime;
uniform float uOpacity;
uniform vec3 uCam;
varying vec3 vWorld;
varying vec3 vNormalW;
varying vec2 vGrid;
varying vec3 vCol;
void main() {
  vec3 V = normalize(uCam - vWorld);
  float ndv = clamp(abs(dot(normalize(vNormalW), V)), 0.0, 1.0);
  float fres = pow(1.0 - ndv, 2.2);
  // wireframe every 8 grid cells (240 m)
  float fx = fract(vGrid.x / 8.0);
  float fy = fract(vGrid.y / 8.0);
  float grid = 1.0 - smoothstep(0.0, 0.07, min(min(fx, 1.0 - fx), min(fy, 1.0 - fy)));
  float scan = 0.5 + 0.5 * sin(vWorld.z * 60.0 - uTime * 2.2);
  float fill = 0.22 * uOpacity;
  float lines = 0.9 * grid * uOpacity;
  float edge = 0.85 * fres * uOpacity;
  float a = clamp(fill + lines + edge + 0.05 * scan * uOpacity, 0.0, 1.0);
  vec3 col = vCol * (0.8 + 0.6 * fres + 0.3 * grid) + vec3(0.08, 0.16, 0.18) * fres;
  gl_FragColor = vec4(col, a);
}`;

function makeMesh(d, heights, material) {
  const { n, Lkm, k, valid, index } = d;
  const pos = new Float32Array(n * n * 3);
  const uv = new Float32Array(n * n * 2);
  const c = (n - 1) / 2;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const v = i * n + j;
      pos[v * 3] = (j - c) * Lkm;
      pos[v * 3 + 2] = (i - c) * Lkm;
      pos[v * 3 + 1] = valid[v] ? heights[v] * k : 0;
      uv[v * 2] = j;
      uv[v * 2 + 1] = i;
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
  geo.setAttribute("color", new THREE.BufferAttribute(new Float32Array(n * n * 3), 3));
  geo.setIndex(new THREE.BufferAttribute(index, 1));
  geo.computeVertexNormals();
  return new THREE.Mesh(geo, material);
}

export class Hologram {
  constructor(stage) {
    this.stage = stage;
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setClearColor(0x04070f, 1);
    stage.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(36, 1, 0.05, 200);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(0, 0, 0);
    this.controls.enableDamping = true;
    this.renderer.domElement.tabIndex = 0;
    this.renderer.domElement.setAttribute("aria-label", "Terrain view: arrow keys orbit; plus and minus zoom");
    this.renderer.domElement.addEventListener("keydown", (event) => {
      const step = 0.12, orbit = new THREE.Spherical().setFromVector3(this.camera.position.clone().sub(this.controls.target));
      if (event.key === "ArrowLeft") orbit.theta -= step;
      else if (event.key === "ArrowRight") orbit.theta += step;
      else if (event.key === "ArrowUp") orbit.phi = Math.max(0.15, orbit.phi - step);
      else if (event.key === "ArrowDown") orbit.phi = Math.min(this.controls.maxPolarAngle, orbit.phi + step);
      else if (event.key === "+" || event.key === "=") orbit.radius = Math.max(this.controls.minDistance, orbit.radius * 0.9);
      else if (event.key === "-") orbit.radius = Math.min(this.controls.maxDistance, orbit.radius * 1.1);
      else return;
      event.preventDefault();
      this.camera.position.copy(this.controls.target).add(new THREE.Vector3().setFromSpherical(orbit));
      this.controls.update();
    });
    this.controls.enablePan = false;
    this.controls.minDistance = 3;
    this.controls.maxDistance = 25;
    this.controls.maxPolarAngle = Math.PI * 0.48;

    this.uniforms = {
      uTime: { value: 0 },
      uOpacity: { value: 0.8 },
      uCam: { value: new THREE.Vector3() },
    };
    this.holoMat = new THREE.ShaderMaterial({
      vertexShader: HOLO_VERT,
      fragmentShader: HOLO_FRAG,
      uniforms: this.uniforms,
      vertexColors: true,
      transparent: true,
      depthWrite: false,
      depthTest: false,   // the whole target shape stays visible over the Earth terrain
      blending: THREE.NormalBlending,
      side: THREE.DoubleSide,
    });
    // The solid terrain is shaded per vertex from its own normals (hillshade-style sun), so the relief
    // reads at any camera angle. The PNG hillshade is not used on the mesh.
    this.solidMat = new THREE.MeshBasicMaterial({ vertexColors: true });

    this.group = new THREE.Group();
    this.scene.add(this.group);
    this.data = null;
    this.solid = null;
    this.holo = null;
    this.solidShade = null;
    this.toggles = { slope: false, ridges: false, valleys: false };
    this.morph = 1;
    this.holoSource = null;
    this.raf = null;
    this.running = false;

    this.frame = this.frame.bind(this);
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(stage);
    this.resize();
    this.resetCamera();
  }

  resize() {
    const w = this.stage.clientWidth;
    const h = this.stage.clientHeight;
    if (w < 2 || h < 2) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.fit();
  }

  // Camera at ELEVATION_DEG above the disk, looking at its centre. Distance is set by fit().
  resetCamera() {
    const el = THREE.MathUtils.degToRad(ELEVATION_DEG);
    this.camera.position.set(0, Math.sin(el), Math.cos(el)).multiplyScalar(10);
    this.controls.target.set(0, 0, 0);
    this.fit();
  }

  // Distance so the whole bounding sphere fits both the vertical and the horizontal field of view.
  fit() {
    if (!this.fitRadius) return;
    const vfov = (this.camera.fov * Math.PI) / 180;
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * this.camera.aspect);
    const half = Math.min(vfov, hfov) / 2;
    const dist = (this.fitRadius / Math.sin(half)) * 1.05;
    const target = this.controls.target;
    const dir = this.camera.position.clone().sub(target);
    if (dir.lengthSq() < 1e-6) dir.set(0, Math.sin(THREE.MathUtils.degToRad(ELEVATION_DEG)), Math.cos(THREE.MathUtils.degToRad(ELEVATION_DEG)));
    dir.normalize();
    this.camera.position.copy(target).addScaledVector(dir, dist);
    this.camera.lookAt(target);
    this.controls.minDistance = dist * 0.4;
    this.controls.maxDistance = dist * 2.5;
    this.controls.update();
  }

  // target and analog: { n, L, R, height, layers, meta } (see data.js loadTerrain).
  // verticalExaggeration is the pair's value (card.vertical_exaggeration), applied to both terrains.
  load({ target, analog, rotationDeg, verticalExaggeration, horizontalM, reduced }) {
    if (target.n !== analog.n) throw new Error("Target and analog terrains have different grids");
    if (target.L !== analog.L || target.R !== analog.R) throw new Error("Target and analog terrains have different grids");
    const n = target.n;
    horizontalM = horizontalM || 1000;
    const k = verticalExaggeration / horizontalM;   // metres -> scene units
    const valid = validFrom(target.height);
    const analogH = rotateField(analog.height, n, target.L, target.R, rotationDeg, false);
    const analogLayers = rotateField(analog.layers, n, target.L, target.R, rotationDeg, true);
    const analogValid = validFrom(analogH);
    this.data = {
      n, k, valid, index: buildIndex(n, valid), analogValid, analogIndex: buildIndex(n, analogValid), Lkm: target.L / horizontalM,
      targetH: target.height, targetLayers: target.layers,
      analogH, analogLayers, reduced: !!reduced,
    };

    for (const child of this.group.children) {
      child.geometry.dispose();
      if (child.material !== this.solidMat && child.material !== this.holoMat) child.material.dispose();
    }
    this.group.clear();
    this.solid = makeMesh({ ...this.data, valid: analogValid, index: this.data.analogIndex }, analogH, this.solidMat);
    this.solidShade = shadeFromNormals(this.solid.geometry.attributes.normal.array, n * n, SUN);
    this.holo = makeMesh(this.data, analogH, this.holoMat);
    this.holo.renderOrder = 2;   // drawn after the solid terrain
    this.solid.renderOrder = 1;
    this.group.add(this.solid, this.holo);
    const relief = Math.max(...[target.meta.z_min, target.meta.z_max, analog.meta.z_min, analog.meta.z_max].filter(Number.isFinite).map(Math.abs), 0) * k;
    this.fitRadius = Math.hypot(target.R / horizontalM * 1.16, relief + 0.3);   // disk + relief, in scene units
    this.resetCamera();

    const rUnits = target.R / horizontalM;
    // Decorative instrument rings sit outside the measured disk; neither terrain is moved.
    const ringMaterial = (opacity) => new THREE.MeshBasicMaterial({
      color: 0x41eaff, transparent: true, opacity, side: THREE.DoubleSide, depthWrite: false
    });
    for (const [scale, width, opacity] of [[1.025, 0.006, 0.6], [1.09, 0.004, 0.25], [1.14, 0.006, 0.4]]) {
      const radius = rUnits * scale;
      const ring = new THREE.Mesh(new THREE.RingGeometry(radius - width, radius, 192), ringMaterial(opacity));
      ring.rotation.x = -Math.PI / 2;
      ring.position.y = -relief - 0.12;
      this.group.add(ring);
    }
    const ticks = [];
    for (let i = 0; i < 72; i++) {
      const angle = i * Math.PI * 2 / 72;
      const inner = rUnits * (i % 6 === 0 ? 1.075 : 1.095);
      const outer = rUnits * 1.13;
      const y = -relief - 0.115;
      ticks.push(Math.cos(angle) * inner, y, Math.sin(angle) * inner,
                 Math.cos(angle) * outer, y, Math.sin(angle) * outer);
    }
    const tickGeometry = new THREE.BufferGeometry();
    tickGeometry.setAttribute("position", new THREE.Float32BufferAttribute(ticks, 3));
    this.group.add(new THREE.LineSegments(tickGeometry,
      new THREE.LineBasicMaterial({ color: 0x50dcf1, transparent: true, opacity: 0.48 })));

    this.holoSource = null;
    this.paintAll();
    this.setMorph(this.morph);
  }

  // Hologram opacity slider: 0 (invisible) to 1 (lines full, fill 22%).
  setOpacity(v) {
    this.uniforms.uOpacity.value = Math.max(0, Math.min(1, Number(v)));
  }

  // t = 0: hologram is the analog shape; t = 1: hologram is the target shape.
  setMorph(t) {
    this.morph = t;
    if (!this.data || !this.holo) return;
    const d = this.data;
    const pos = this.holo.geometry.attributes.position.array;
    for (let v = 0; v < d.n * d.n; v++) {
      pos[v * 3 + 1] = d.valid[v] ? ((1 - t) * (d.analogValid[v] ? d.analogH[v] : d.targetH[v]) + t * d.targetH[v]) * d.k : 0;
    }
    this.holo.geometry.attributes.position.needsUpdate = true;
    this.holo.geometry.computeVertexNormals();
    // Layers follow the shape: the target's layers once the hologram is mostly the target.
    const source = t >= 0.5 ? "target" : "analog";
    if (source !== this.holoSource) {
      this.holoSource = source;
      this.paintHolo();
    }
  }

  setLayers(toggles) {
    this.toggles = { ...toggles };
    this.paintAll();
  }

  paintAll() {
    if (!this.data) return;
    const d = this.data;
    paintLayers(d.analogLayers, d.analogValid, SOLID_BASE, this.toggles, this.solid.geometry.attributes.color.array, this.solidShade);
    this.solid.geometry.attributes.color.needsUpdate = true;
    this.paintHolo();
  }

  paintHolo() {
    if (!this.data || !this.holo) return;
    const d = this.data;
    const layers = this.holoSource === "analog" ? d.analogLayers : d.targetLayers;
    paintLayers(layers, d.valid, HOLO_BASE, this.toggles, this.holo.geometry.attributes.color.array, null);
    this.holo.geometry.attributes.color.needsUpdate = true;
  }

  start() {
    this.running = true;
    if (this.raf === null) this.raf = requestAnimationFrame(this.frame);
  }

  stop() {
    this.running = false;
  }

  frame(time) {
    if (!this.running) {
      this.raf = null;
      return;
    }
    this.controls.update();
    this.uniforms.uTime.value = this.data && this.data.reduced ? 0 : time / 1000;
    this.uniforms.uCam.value.copy(this.camera.position);
    this.renderer.render(this.scene, this.camera);
    this.raf = requestAnimationFrame(this.frame);
  }
}
