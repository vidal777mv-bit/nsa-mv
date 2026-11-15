// One travelling globe for the v2 design. Paper background (transparent canvas), no stars.
// Texture convention matches js/globe.js (u = (lon + 180) / 360, east positive).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const HOME = 3.7;
const NEAR = 2.15;

export function latLonToVec(lat, lon, r = 1) {
  const phi = ((lon + 180) / 360) * Math.PI * 2;
  const lam = (lat * Math.PI) / 180;
  return new THREE.Vector3(-Math.cos(phi) * Math.cos(lam) * r, Math.sin(lam) * r, Math.sin(phi) * Math.cos(lam) * r);
}

function ease(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }

function dotTexture(ring, label = "") {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d");
  g.beginPath(); g.arc(32, 32, ring ? 26 : 22, 0, Math.PI * 2);
  g.fillStyle = "#fff"; g.fill();
  g.lineWidth = ring ? 8 : 6; g.strokeStyle = "rgba(20,19,16,0.9)"; g.stroke();
  if (label) { g.fillStyle = "#1b1a17"; g.font = "bold 27px Arial"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(label, 32, 33); }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export class Globe2 {
  constructor(stage, { onPick } = {}) {
    this.stage = stage;
    this.onPick = onPick;
    this.body = null;
    this.anim = null;
    this.pins = [];
    this.pinLabel = document.createElement("div");
    this.pinLabel.className = "map-pin-label";
    this.pinLabel.hidden = true;
    stage.append(this.pinLabel);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setClearColor(0x000000, 0);
    stage.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(34, 1, 0.05, 100);
    this.camera.position.set(0, 0.6, HOME);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enablePan = false;
    this.controls.enableZoom = false;
    this.controls.enableDamping = true;
    this.controls.rotateSpeed = 0.5;

    this.scene.add(new THREE.AmbientLight(0xffffff, 1.15));
    this.key = new THREE.DirectionalLight(0xfff6ea, 1.9);
    this.scene.add(this.key);

    this.globe = new THREE.Mesh(new THREE.SphereGeometry(1, 128, 80),
      new THREE.MeshStandardMaterial({ color: 0xd9d2c4, roughness: 0.95, metalness: 0 }));
    this.scene.add(this.globe);

    // Illustrative knowledge veil: circular clearings communicate known points, not survey footprints.
    this.knowledgeMaterial = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false,
      uniforms: { uCount: { value: 0 }, uPoints: { value: Array.from({ length: 32 }, () => new THREE.Vector3()) }, uEnabled: { value: 0 } },
      vertexShader: `varying vec3 direction; void main(){ direction=normalize(position); gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
      fragmentShader: `uniform vec3 uPoints[32]; uniform int uCount; uniform float uEnabled; varying vec3 direction;
        void main(){ float clear=0.0; vec3 d=normalize(direction);
          for(int i=0;i<32;i++){ if(i>=uCount) break; float distanceToSite=length(d-uPoints[i]); clear=max(clear,1.0-smoothstep(0.12,0.31,distanceToSite)); }
          float texture = sin(d.x*19.0 + sin(d.y*13.0))*sin(d.z*17.0-d.y*11.0);
          float veil = 0.53 + 0.055*texture;
          gl_FragColor=vec4(0.025,0.035,0.048,uEnabled*veil*(1.0-clear)); }`,
    });
    this.knowledgeVeil = new THREE.Mesh(new THREE.SphereGeometry(1.003, 128, 80), this.knowledgeMaterial);
    this.knowledgeVeil.renderOrder = 1;
    this.scene.add(this.knowledgeVeil);
    this.beaconGroup = new THREE.Group();
    this.scene.add(this.beaconGroup);
    this.reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

    // Ink graticule ring at the limb: the globe reads as a printed plate, not a space render.
    this.pinGroup = new THREE.Group();
    this.scene.add(this.pinGroup);
    this.cellGroup = new THREE.Group();
    this.scene.add(this.cellGroup);
    this.dot = dotTexture(false);
    this.dotSel = dotTexture(true);
    this.ray = new THREE.Raycaster();

    new ResizeObserver(() => this.resize()).observe(stage);
    this.resize();
    let down = null;
    const cv = this.renderer.domElement;
    cv.addEventListener("pointerdown", (e) => { down = [e.clientX, e.clientY]; });
    cv.addEventListener("pointerup", (e) => {
      if (!down) return;
      const moved = Math.hypot(e.clientX - down[0], e.clientY - down[1]);
      down = null;
      if (moved < 6) this.pick(e);
    });
    cv.addEventListener("pointermove", (e) => { const index = this.hit(e); this.hoverPin = index === null ? null : this.pins[index]; cv.style.cursor = index !== null ? "pointer" : "grab"; });
    cv.addEventListener("pointerleave", () => { this.hoverPin = null; });
    this.frame = this.frame.bind(this);
    requestAnimationFrame(this.frame);
  }

  setBody(body) {
    if (body === this.body) return Promise.resolve();
    this.body = body;
    const request = this.textureRequest = (this.textureRequest || 0) + 1;
    return new Promise((res) => {
      new THREE.TextureLoader().load(new URL(`assets/globes/${body}.jpg`, document.baseURI).href, (tex) => {
        if (request !== this.textureRequest) { tex.dispose(); res(); return; }
        this.globe.material.map?.dispose();
        tex.colorSpace = THREE.SRGBColorSpace;
        tex.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
        this.globe.material.map = tex;
        this.globe.material.color.set(0xffffff);
        this.globe.material.needsUpdate = true;
        res();
      }, undefined, () => res());
    });
  }

  // Points are exported coordinates. Clearings and beams are visual cues, not coverage outlines.
  setKnowledge({ detailed = [], measured = [] } = {}) {
    for (const object of this.beaconGroup.children) {
      object.geometry?.dispose(); object.material.map?.dispose(); object.material.dispose();
    }
    this.beaconGroup.clear();
    const valid = (p) => Number.isFinite(p.lat) && Number.isFinite(p.lon) && Math.abs(p.lat) <= 90;
    const known = detailed.filter(valid);
    const measuredOnly = measured.filter(valid);
    this.knowledgeMaterial.uniforms.uCount.value = Math.min(32, known.length);
    this.knowledgeMaterial.uniforms.uEnabled.value = known.length || measuredOnly.length ? 1 : 0;
    known.slice(0, 32).forEach((p, i) => this.knowledgeMaterial.uniforms.uPoints.value[i].copy(latLonToVec(p.lat, p.lon)));
    const beam = (item) => {
      const direction = latLonToVec(item.lat, item.lon).normalize();
      const length = 0.20;
      // Crossed translucent light sheets fade across their width and toward their tip.
      for (const angle of [0, Math.PI / 2]) {
        const geometry = new THREE.PlaneGeometry(0.07, length);
        const material = new THREE.ShaderMaterial({
          transparent: true, depthWrite: false, side: THREE.DoubleSide,
          blending: THREE.AdditiveBlending,
          uniforms: { uOpacity: { value: 0.56 } },
          vertexShader: `varying vec2 vUv; void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
          fragmentShader: `varying vec2 vUv; uniform float uOpacity; void main(){
            float side=pow(max(0.0,1.0-abs(vUv.x*2.0-1.0)),2.0);
            float tip=pow(1.0-vUv.y,1.65);
            gl_FragColor=vec4(1.0,0.46,0.20,uOpacity*side*tip);}`
        });
        const mesh = new THREE.Mesh(geometry, material);
        mesh.position.copy(direction).multiplyScalar(1.014 + length / 2);
        mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction);
        mesh.rotateY(angle);
        mesh.userData.strong = true;
        this.beaconGroup.add(mesh);
      }
      // A radial glow stays visible when the beam points toward the viewer.
      const canvas = document.createElement("canvas"); canvas.width = canvas.height = 64;
      const context = canvas.getContext("2d");
      const gradient = context.createRadialGradient(32, 32, 0, 32, 32, 32);
      gradient.addColorStop(0, "rgba(255,195,143,0.7)");
      gradient.addColorStop(0.25, "rgba(255,132,73,0.3)");
      gradient.addColorStop(1, "rgba(255,100,50,0)");
      context.fillStyle = gradient; context.fillRect(0, 0, 64, 64);
      const texture = new THREE.CanvasTexture(canvas);
      const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true,
        blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0.8 }));
      halo.position.copy(direction).multiplyScalar(1.018); halo.scale.set(0.17, 0.17, 1);
      this.beaconGroup.add(halo);
    };
    known.forEach(p => beam(p));
    if (measuredOnly.length) {
      const positions = new Float32Array(measuredOnly.length * 3);
      measuredOnly.forEach((point, i) => {
        const v = latLonToVec(point.lat, point.lon, 1.008);
        positions.set([v.x, v.y, v.z], i * 3);
      });
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      this.beaconGroup.add(new THREE.Points(geometry, new THREE.PointsMaterial({
        color: 0xd0b69b, size: 3, sizeAttenuation: false, transparent: true, opacity: 0.7, depthWrite: false
      })));
    }
  }

  // items: [{lat, lon, id, colour}]
  setPins(items, selectedId = null) {
    this.pinGroup.children.forEach(pin => { if (pin.userData.ownTexture) pin.material.map.dispose(); pin.material.dispose(); });
    this.pinGroup.clear();
    this.pins = items;
    this.hoverPin = null;
    this.selectedPin = items.find(it => it.id === selectedId) || null;
    items.forEach((it, i) => {
      const sel = it.id === selectedId;
      const map = it.label ? dotTexture(sel, String(it.label)) : sel ? this.dotSel : this.dot;
      const m = new THREE.SpriteMaterial({ map, color: it.label ? 0xffffff : it.colour, depthTest: true, transparent: true });
      const s = new THREE.Sprite(m);
      const sz = it.label ? (sel ? 0.13 : 0.10) : sel ? 0.1 : 0.065;
      s.scale.set(sz, sz, 1);
      s.position.copy(latLonToVec(it.lat, it.lon, 1.012));
      s.userData.index = i;
      s.userData.ownTexture = !!it.label;
      this.pinGroup.add(s);
    });
  }

  // Many small marks (Earth-gap cells). items: [{lat, lon}]
  setCells(items, colour = 0xb4462b) {
    this.cellGroup.children.forEach(cell => { cell.geometry.dispose(); cell.material.dispose(); });
    this.cellGroup.clear();
    if (!items.length) return;
    const pos = new Float32Array(items.length * 3);
    items.forEach((it, i) => { const v = latLonToVec(it.lat, it.lon, 1.006); pos.set([v.x, v.y, v.z], i * 3); });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    const pts = new THREE.Points(g, new THREE.PointsMaterial({ color: colour, size: 2, transparent: true, opacity: 0.45, sizeAttenuation: false }));
    this.cellGroup.add(pts);
  }

  flyTo(lat, lon, near = true) {
    const dir = latLonToVec(lat, lon, 1).normalize();
    const from = this.camera.position.clone();
    const dist0 = from.length();
    const dist1 = near ? NEAR : HOME;
    const a = from.clone().normalize();
    const t0 = performance.now();
    const dur = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 1 : 1400;
    if (this.cancelFlight) this.cancelFlight();
    this.controls.enabled = false;
    return new Promise((res) => {
      this.cancelFlight = () => { this.anim = null; this.cancelFlight = null; res(); };
      this.anim = (now) => {
        const t = Math.min(1, (now - t0) / dur);
        const k = ease(t);
        const q = new THREE.Quaternion().setFromUnitVectors(a, dir);
        const qk = new THREE.Quaternion().slerp(q, k);
        // A small lift mid-flight so long trips read as travel.
        const lift = Math.sin(Math.PI * k) * 0.5;
        this.camera.position.copy(a.clone().applyQuaternion(qk).multiplyScalar(dist0 + (dist1 - dist0) * k + lift));
        this.camera.lookAt(0, 0, 0);
        if (t >= 1) { this.anim = null; this.cancelFlight = null; this.controls.enabled = true; res(); }
      };
    });
  }

  hit(e) {
    const r = this.renderer.domElement.getBoundingClientRect();
    const p = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    this.ray.setFromCamera(p, this.camera);
    const h = this.ray.intersectObjects(this.pinGroup.children, false);
    if (!h.length) return null;
    // Ignore pins on the far side.
    const g = this.ray.intersectObject(this.globe, false);
    if (g.length && g[0].distance < h[0].distance - 0.01) return null;
    return h[0].object.userData.index;
  }

  pick(e) {
    const i = this.hit(e);
    if (i !== null && this.onPick) this.onPick(this.pins[i]);
  }

  resize() {
    const w = this.stage.clientWidth || 1, h = this.stage.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  setAutoRotate(enabled) {
    this.controls.autoRotate = enabled && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.controls.autoRotateSpeed = 0.35;
  }

  frame(now) {
    if (this.anim) this.anim(now); else this.controls.update();
    this.key.position.copy(this.camera.position).normalize().multiplyScalar(10).add(new THREE.Vector3(2, 3, 0));
    for (const beam of this.beaconGroup.children) {
      if (beam.userData.strong) beam.material.uniforms.uOpacity.value = this.reducedMotion.matches ? 0.56 : 0.51 + 0.05 * Math.sin(now / 1400);
    }
    this.renderer.render(this.scene, this.camera);
    const labelledPin = this.hoverPin || this.selectedPin;
    if (labelledPin) {
      const position = latLonToVec(labelledPin.lat, labelledPin.lon, 1.03);
      const visible = position.dot(this.camera.position.clone().sub(position)) > 0;
      const projected = position.project(this.camera);
      this.pinLabel.hidden = !visible || Math.abs(projected.x) > 0.85 || Math.abs(projected.y) > 0.9;
      this.pinLabel.textContent = labelledPin.shortName || labelledPin.name?.split(/[:(]/)[0].trim() || labelledPin.label || "Selected site";
      const x = (projected.x + 1) * this.stage.clientWidth / 2;
      const y = (1 - projected.y) * this.stage.clientHeight / 2;
      this.pinLabel.style.transform = `translate(${Math.max(4, Math.min(this.stage.clientWidth - this.pinLabel.offsetWidth - 4, x - this.pinLabel.offsetWidth / 2))}px, ${Math.max(2, y - 35)}px)`;
    } else this.pinLabel.hidden = true;
    requestAnimationFrame(this.frame);
  }
}
