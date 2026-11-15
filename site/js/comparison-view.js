// Synchronized terrain views. Every mode uses the same pair scale and illumination.
// The blue/green overlay is geometric context, never a computed similarity mask.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { validFrom, buildIndex, shadeFromNormals } from "./terrain.js";
import { alignHeights, levelHeights, sampleProfile, terrainFitDistance } from "./comparison-profile.js";

const BLUE = 0x559bff, GREEN = 0x58cb91;
// Natural tones: the relief reads as ground, not plastic. Mars ochre, Moon grey, Earth sandstone-sage.
const WORLD_TONE = { mars: 0xd08a5c, moon: 0xbdb8b0, earth: 0x9fb28c };
const WIRE_TONE = { mars: 0xf3a06c, moon: 0xece7de };   // target mesh in Align & inspect: same world colour, brighter
const SUN = [-0.5, Math.SQRT1_2, -0.5];
const ease = t => t < .5 ? 4*t*t*t : 1 - Math.pow(-2*t+2, 3)/2;
const clamp = v => Math.max(0, Math.min(1, Number(v) || 0));

function geometry(height, n, L, k, valid) {
  const xyz = new Float32Array(n*n*3), c = (n-1)/2;
  for (let i=0; i<n; i++) for (let j=0; j<n; j++) {
    const v=i*n+j;
    xyz[v*3]=(j-c)*L; xyz[v*3+1]=valid[v] ? height[v]*k : 0; xyz[v*3+2]=(i-c)*L;
  }
  const g=new THREE.BufferGeometry();
  g.setAttribute("position",new THREE.BufferAttribute(xyz,3));
  g.setIndex(new THREE.BufferAttribute(buildIndex(n,valid),1));
  g.computeVertexNormals();
  return g;
}

function shade(g, color) {
  const base=new THREE.Color(color), normal=g.attributes.normal;
  const shades=shadeFromNormals(normal.array,normal.count,SUN);
  const colors=new Float32Array(normal.count*3);
  for (let v=0;v<normal.count;v++) {
    colors[v*3]=base.r*shades[v]; colors[v*3+1]=base.g*shades[v]; colors[v*3+2]=base.b*shades[v];
  }
  g.setAttribute("color",new THREE.BufferAttribute(colors,3));
}

function gridLines(g, valid, n) {
  const p=g.attributes.position.array, segments=[];
  const add=(a,b)=>{ if(valid[a] && valid[b]) {segments.push(...p.subarray(a*3,a*3+3),...p.subarray(b*3,b*3+3));} };
  for(let i=0;i<n;i++) for(let j=0;j<n;j++) {
    const v=i*n+j;
    if(i%8===0 && j<n-1) add(v,v+1);
    if(j%8===0 && i<n-1) add(v,v+n);
  }
  const lines=new THREE.BufferGeometry();
  lines.setAttribute("position",new THREE.Float32BufferAttribute(segments,3));
  return lines;
}

function freeGroup(group) {
  group.traverse(o=>{
    o.geometry?.dispose();
    if(Array.isArray(o.material)) o.material.forEach(m=>m.dispose());
    else o.material?.dispose();
  });
  group.clear();
}

export class ComparisonView {
  constructor(stage, {onProfile}={}) {
    this.stage=stage; this.onProfile=onProfile;
    this.renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1,2));
    this.renderer.setClearColor(0x090d12,0);
    this.renderer.autoClear=false;
    this.renderer.domElement.style.cssText="display:block;width:100%;height:100%;touch-action:none;";
    this.renderer.domElement.tabIndex=0;
    this.renderer.domElement.setAttribute("aria-label","Terrain comparison. Drag to orbit; arrow keys rotate; plus and minus zoom.");
    stage.append(this.renderer.domElement);
    this.scene=new THREE.Scene();
    this.camera=new THREE.PerspectiveCamera(36,1,.1,500);
    this.camera.position.set(0,12,18);
    this.controls=new OrbitControls(this.camera,this.renderer.domElement);
    this.controls.enablePan=false; this.controls.enableDamping=true; this.controls.dampingFactor=.09;
    // Complete azimuth orbit and an almost full pole-to-pole elevation arc.
    // Keep a tiny pole margin to avoid the orbit singularity.
    this.controls.maxPolarAngle=Math.PI-.025; this.controls.minPolarAngle=.025;
    this.controls.minAzimuthAngle=-Infinity;this.controls.maxAzimuthAngle=Infinity;
    this.controls.rotateSpeed=.7;
    this.targetGroup=new THREE.Group(); this.earthGroup=new THREE.Group();
    this.scene.add(this.targetGroup,this.earthGroup);
    this.mode="split"; this.stage.dataset.terrainMode="split"; this.spread=1; this.overlay=0; this.swipe=.5; this.opacity=.8;
    this.overlayLayer="both";this.separation=0;
    this.animation=null; this.running=false; this.disposed=false; this.raf=null; this.inView=true;
    this.data=null; this.profileFraction=null;
    this.size={w:1,h:1}; this.lastFit=null;
    this.right=new THREE.Vector3(); this.up=new THREE.Vector3(); this.offset=new THREE.Vector3();
    this.frame=this.frame.bind(this);
    this.onKey=e=>{
      const actions={ArrowLeft:"left",ArrowRight:"right",ArrowUp:"up",ArrowDown:"down","+":"in","=":"in","-":"out"};
      if(actions[e.key]) {e.preventDefault();this.nudge(actions[e.key]);}
    };
    this.renderer.domElement.addEventListener("keydown",this.onKey);
    this.onVisibility=()=>{ if(document.hidden) this.cancelFrame(); else this.schedule(); };
    document.addEventListener("visibilitychange",this.onVisibility);
    this.resizeObserver=new ResizeObserver(()=>this.resize()); this.resizeObserver.observe(stage);
    this.intersectionObserver=new IntersectionObserver(entries=>{
      this.inView=entries[0].isIntersecting;
      if(this.inView) this.schedule(); else this.cancelFrame();
    });
    this.intersectionObserver.observe(stage);
    this.resize();
  }

  // levelled (default off): true = Levelled display (Earth rotated by rotationDeg, each overall tilt removed);
  // false = True orientation (both north up, real slopes). The measures never change.
  load({target,analog,rotationDeg=0,levelled=false,verticalExaggeration=1,horizontalM=1000,reduced=false,preserveCamera=false,body="mars"}) {
    if(!target || !analog || target.n!==analog.n || target.L!==analog.L || target.R!==analog.R)
      throw new Error("Comparison requires matching terrain grids.");
    if(!Number.isFinite(verticalExaggeration) || verticalExaggeration<=0 || !Number.isFinite(horizontalM) || horizontalM<=0)
      throw new Error("Comparison scale is invalid.");
    const n=target.n;
    if(target.height.length!==n*n || analog.height.length!==n*n) throw new Error("Terrain size is invalid.");
    this.levelled=!!levelled;
    this.source={target,analog,rotationDeg,verticalExaggeration,horizontalM,reduced,body};
    freeGroup(this.targetGroup); freeGroup(this.earthGroup);
    const aligned=alignHeights(analog.height,n,target.L,target.R,this.levelled?rotationDeg:0);
    const shownTarget=this.levelled?levelHeights(target.height,n,target.L,target.R):target.height;
    const shownAnalog=this.levelled?levelHeights(aligned,n,target.L,target.R):aligned;
    const tv=validFrom(shownTarget), av=validFrom(shownAnalog), k=verticalExaggeration/horizontalM;
    // The cross-section (comparison-profile) reads these same arrays, so the chart and the mesh never disagree.
    this.data={n,L:target.L,R:target.R,Lunits:target.L/horizontalM,k,target:shownTarget,analog:shownAnalog,reduced:!!reduced};
    this.stage.dataset.levelled=String(this.levelled);
    this.controls.enableDamping=!reduced;
    const tg=geometry(shownTarget,n,this.data.Lunits,k,tv), eg=geometry(shownAnalog,n,this.data.Lunits,k,av);
    shade(tg,WORLD_TONE[body]||WORLD_TONE.mars); shade(eg,WORLD_TONE.earth);
    this.targetMesh=new THREE.Mesh(tg,new THREE.MeshBasicMaterial({vertexColors:true,side:THREE.DoubleSide,transparent:true}));
    this.earthMesh=new THREE.Mesh(eg,new THREE.MeshBasicMaterial({vertexColors:true,side:THREE.DoubleSide}));
    this.targetMesh.renderOrder=2; this.earthMesh.renderOrder=1;
    // Dashed, subdued lines locate the target behind Earth; solid lines show
    // the target in front. No blended fill suggests a shared surface.
    this.wire=new THREE.LineSegments(gridLines(tg,tv,n),new THREE.LineDashedMaterial({color:WIRE_TONE[body]||WIRE_TONE.mars,transparent:true,opacity:0,depthTest:false,depthWrite:false,dashSize:.12,gapSize:.09}));
    this.wire.computeLineDistances();
    this.frontWire=new THREE.LineSegments(this.wire.geometry.clone(),new THREE.LineBasicMaterial({color:WIRE_TONE[body]||WIRE_TONE.mars,transparent:true,opacity:0,depthTest:true,depthWrite:false}));
    this.frontWire.renderOrder=4;
    this.wire.renderOrder=3;
    this.targetGroup.add(this.targetMesh,this.wire,this.frontWire); this.earthGroup.add(this.earthMesh);
    this.profileTarget=new THREE.LineSegments(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:0xd8e8ff,transparent:true,depthTest:false,depthWrite:false}));
    this.profileEarth=new THREE.LineSegments(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:0xd5ffe7,transparent:true,depthTest:false,depthWrite:false}));
    this.profileTarget.renderOrder=5;this.profileEarth.renderOrder=5;
    this.targetGroup.add(this.profileTarget);this.earthGroup.add(this.profileEarth);
    let relief=0;
    for(let v=0;v<n*n;v++) {
      if(tv[v]) relief=Math.max(relief,Math.abs(shownTarget[v]*k));
      if(av[v]) relief=Math.max(relief,Math.abs(shownAnalog[v]*k));
    }
    this.radius=target.R/horizontalM;this.relief=relief;
    this.animation=null;this.spread=this.mode==="split"?1:0;this.overlay=this.mode==="overlay"?1:0;
    if(preserveCamera && this.lastFit) this.fit(true); else this.resetCamera();
    this.setProfile(this.profileFraction);this.updateScene();this.draw();
  }

  resize() {
    const w=this.stage.clientWidth,h=this.stage.clientHeight;
    if(w<2 || h<2 || this.disposed) return;
    this.size={w,h};this.mobile=w<620;
    this.stage.dataset.terrainLayout=this.mobile?"stacked":"horizontal";
    this.renderer.setSize(w,h,false);
    this.camera.aspect=w/h;this.camera.updateProjectionMatrix();
    this.fit(true);this.updateScene();this.draw();
  }

  fit(preserveZoom=true) {
    if(!this.data) return;
    const current=this.camera.position.distanceTo(this.controls.target);
    const ratio=preserveZoom && this.lastFit ? current/this.lastFit : 1;
    const dir=this.camera.position.clone().sub(this.controls.target).normalize();
    if(dir.lengthSq()<.5) dir.set(0,.574,.819);
    const elevation=Math.asin(THREE.MathUtils.clamp(dir.y,-1,1));
    const distance=terrainFitDistance(this.radius,this.relief+this.layerOffset(),this.camera.aspect,
      THREE.MathUtils.degToRad(this.camera.fov),this.spread,this.mobile,elevation);
    this.camera.position.copy(this.controls.target).addScaledVector(dir,distance*ratio);
    this.controls.minDistance=distance*.38;this.controls.maxDistance=distance*2.5;
    this.camera.near=.05;this.camera.far=Math.max(500,distance*5);this.camera.updateProjectionMatrix();
    this.camera.lookAt(this.controls.target);this.lastFit=distance;
    this.controls.update();
  }

  resetCamera() {
    // Consume pending orbit deltas before restoring a deterministic camera.
    const damping=this.controls.enableDamping;
    this.controls.enableDamping=false;this.controls.update();this.controls.enableDamping=damping;
    this.animation=null;this.spread=this.mode==="split"?1:0;this.overlay=this.mode==="overlay"?1:0;
    this.controls.target.set(0,0,0);this.camera.position.set(0,Math.sin(Math.PI*35/180),Math.cos(Math.PI*35/180));
    this.lastFit=null;this.fit(false);this.updateScene();this.draw();
  }

  // Named inspection angles use the current azimuth so direction stays familiar.
  setCameraView(name) {
    if(name==="reset") {this.resetCamera();return;}
    const elevations={top:88.5,profile:3,underside:-45};
    if(!(name in elevations) || !this.data) return;
    const damping=this.controls.enableDamping;
    this.controls.enableDamping=false;this.controls.update();this.controls.enableDamping=damping;
    const delta=this.camera.position.clone().sub(this.controls.target);
    const azimuth=Math.atan2(delta.x,delta.z),elevation=elevations[name]*Math.PI/180;
    this.camera.position.copy(this.controls.target).add(new THREE.Vector3(
      Math.sin(azimuth)*Math.cos(elevation),Math.sin(elevation),Math.cos(azimuth)*Math.cos(elevation)));
    this.lastFit=null;this.fit(false);this.updateScene();this.draw();
  }

  setOverlayLayer(layer) {
    if(!["both","target","earth"].includes(layer)) return;
    this.overlayLayer=layer;this.stage.dataset.overlayLayer=layer;
    this.updateScene();this.draw();
  }

  // Display-only exploded view: never modify source heights or profile samples.
  setSeparation(value) {
    this.separation=clamp(value);this.stage.dataset.layerSeparation=String(this.separation);
    this.fit(true);this.updateScene();this.draw();
  }
  layerOffset() {return this.mode==="overlay" ? (this.radius || 0)*.35*this.separation : 0;}

  setMode(mode) {
    if(!["split","overlay","swipe","target"].includes(mode)) return;
    if(this.mode===mode && !this.animation) return;
    this.mode=mode;this.stage.dataset.terrainMode=mode;
    const spread=mode==="split"?1:0,overlay=mode==="overlay"?1:0;
    if(!this.data || this.data.reduced) {
      this.animation=null;this.spread=spread;this.overlay=overlay;this.fit(true);this.updateScene();this.draw();return;
    }
    this.animation={start:performance.now(),fromSpread:this.spread,fromOverlay:this.overlay,toSpread:spread,toOverlay:overlay};
    this.schedule();
  }

  // Switches Levelled / True orientation by rebuilding both meshes from the loaded source; the camera is kept.
  setLevelled(on) {
    if(!this.source || this.levelled===!!on) return;
    this.load({...this.source,levelled:!!on,preserveCamera:true});
  }

  setSwipe(value) {this.swipe=clamp(value);this.draw();}
  setOpacity(value) {this.opacity=clamp(value);this.updateScene();this.draw();}

  setProfile(fraction) {
    this.profileFraction=fraction==null?null:clamp(fraction);
    if(!this.data) return [];
    const {n,L,Lunits,k,target,analog}=this.data;
    const samples=fraction==null?[]:sampleProfile(target,analog,n,L,this.profileFraction);
    const row=fraction==null?0:Math.round(this.profileFraction*(n-1)), c=(n-1)/2;
    for(const [line,key] of [[this.profileTarget,"target"],[this.profileEarth,"analog"]]) {
      const points=[];
      for(let j=0;j<samples.length-1;j++) {
        const a=samples[j][key],b=samples[j+1][key];
        if(a==null || b==null) continue;
        points.push((j-c)*Lunits,a*k+.008,(row-c)*Lunits,(j+1-c)*Lunits,b*k+.008,(row-c)*Lunits);
      }
      line.geometry.dispose();line.geometry=new THREE.BufferGeometry();
      line.geometry.setAttribute("position",new THREE.Float32BufferAttribute(points,3));
      line.visible=fraction!=null;
    }
    this.onProfile?.(samples);this.draw();return samples;
  }

  nudge(action) {
    const s=new THREE.Spherical().setFromVector3(this.camera.position.clone().sub(this.controls.target));
    if(action==="left") s.theta-=.13;
    else if(action==="right") s.theta+=.13;
    else if(action==="up") s.phi=Math.max(this.controls.minPolarAngle,s.phi-.1);
    else if(action==="down") s.phi=Math.min(this.controls.maxPolarAngle,s.phi+.1);
    else if(action==="in") s.radius=Math.max(this.controls.minDistance,s.radius*.88);
    else if(action==="out") s.radius=Math.min(this.controls.maxDistance,s.radius/ .88);
    this.camera.position.copy(this.controls.target).add(new THREE.Vector3().setFromSpherical(s));
    this.controls.update();this.updateScene();this.draw();
  }

  updateScene() {
    if(!this.data) return;
    this.camera.updateMatrixWorld();
    this.right.setFromMatrixColumn(this.camera.matrixWorld,0);
    this.up.setFromMatrixColumn(this.camera.matrixWorld,1);
    this.offset.copy(this.mobile?this.up:this.right).multiplyScalar(this.radius*1.12*this.spread);
    this.targetGroup.position.copy(this.offset).multiplyScalar(this.mobile?1:-1);
    this.earthGroup.position.copy(this.offset).multiplyScalar(this.mobile?-1:1);
    const inspect=this.mode==="overlay", isolated=inspect && this.overlayLayer!=="both";
    this.targetGroup.position.y+=this.layerOffset();this.earthGroup.position.y-=this.layerOffset();
    this.targetGroup.visible=!inspect || this.overlayLayer!=="earth";
    this.earthGroup.visible=this.mode!=="target" && (!inspect || this.overlayLayer!=="target");
    const elevation=Math.asin(THREE.MathUtils.clamp(this.camera.position.clone().sub(this.controls.target).normalize().y,-1,1))*180/Math.PI;
    this.stage.dataset.cameraBelow=String(elevation<0);
    this.stage.dataset.viewElevation=String(Math.round(elevation));
    // During merge into swipe, retain both surfaces until the clip takes over.
    const blend=this.mode==="swipe" && this.animation ? Math.max(.6,this.overlay) : this.overlay;
    this.targetMesh.material.opacity=isolated ? 1 : 1-blend;
    this.targetMesh.material.depthWrite=isolated || blend<.01;this.targetMesh.material.depthTest=isolated || blend<.01;
    this.wire.material.opacity=blend*.30*this.opacity;
    this.frontWire.material.opacity=blend*Math.min(1,this.opacity+.25);
    this.wire.visible=!isolated && blend>.001;this.frontWire.visible=!isolated && blend>.001;
  }

  draw() {
    if(this.disposed || !this.data || this.size.w<2 || this.size.h<2) return;
    const {w,h}=this.size, r=this.renderer;
    r.setScissorTest(false);r.setViewport(0,0,w,h);r.clear();
    if(this.mode==="swipe" && !this.animation) {
      const cut=Math.round(w*this.swipe);
      r.setScissorTest(true);
      this.targetGroup.visible=true;this.earthGroup.visible=false;
      r.setScissor(0,0,cut,h);r.render(this.scene,this.camera);
      this.targetGroup.visible=false;this.earthGroup.visible=true;
      r.setScissor(cut,0,w-cut,h);r.render(this.scene,this.camera);
      r.setScissorTest(false);this.targetGroup.visible=true;
    } else r.render(this.scene,this.camera);
  }

  schedule() {
    if(this.running && this.inView && !document.hidden && !this.disposed && this.raf===null)
      this.raf=requestAnimationFrame(this.frame);
  }
  cancelFrame() {if(this.raf!==null) cancelAnimationFrame(this.raf);this.raf=null;}
  start() {this.running=true;this.resize();this.schedule();}
  stop() {this.running=false;this.cancelFrame();}
  frame(now) {
    this.raf=null;
    if(!this.running || this.disposed) return;
    if(this.animation) {
      const a=this.animation,t=Math.min(1,(now-a.start)/650),e=ease(t);
      this.spread=a.fromSpread+(a.toSpread-a.fromSpread)*e;
      this.overlay=a.fromOverlay+(a.toOverlay-a.fromOverlay)*e;
      this.fit(true);if(t===1)this.animation=null;
    }
    this.controls.update();this.updateScene();this.draw();this.schedule();
  }
  dispose() {
    if(this.disposed)return;
    this.stop();this.disposed=true;this.resizeObserver.disconnect();this.intersectionObserver.disconnect();
    document.removeEventListener("visibilitychange",this.onVisibility);
    this.renderer.domElement.removeEventListener("keydown",this.onKey);
    this.controls.dispose();freeGroup(this.targetGroup);freeGroup(this.earthGroup);
    this.renderer.dispose();this.renderer.forceContextLoss();this.renderer.domElement.remove();this.data=null;
  }
}

