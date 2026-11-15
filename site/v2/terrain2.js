import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { rotateField, validFrom, buildIndex, paintLayers, shadeFromNormals } from '../js/terrain.js';

function surface(t, height, layers, k, base) {
  const {n,L}=t, valid=validFrom(height), p=new Float32Array(n*n*3), c=(n-1)/2;
  for(let i=0;i<n;i++) for(let j=0;j<n;j++){const v=i*n+j;p[3*v]=(j-c)*L/1000;p[3*v+1]=valid[v]?height[v]*k:0;p[3*v+2]=(i-c)*L/1000;}
  const g=new THREE.BufferGeometry(); g.setAttribute('position',new THREE.BufferAttribute(p,3));
  g.setAttribute('color',new THREE.BufferAttribute(new Float32Array(n*n*3),3));
  g.setIndex(new THREE.BufferAttribute(buildIndex(n,valid),1)); g.computeVertexNormals();
  const shade=shadeFromNormals(g.attributes.normal.array,n*n,[-0.5,0.7071068,-0.5]);
  return {mesh:new THREE.Mesh(g,new THREE.MeshBasicMaterial({vertexColors:true,side:THREE.DoubleSide})),n,L,height,layers,valid,k,base,shade};
}
function surveyLines(s){
  const p=[],{n,L,height,valid,k}=s,c=(n-1)/2,step=Math.max(1,Math.round((n-1)/18));
  const add=(a,b)=>{if(!valid[a]||!valid[b])return;for(const v of [a,b])p.push((v%n-c)*L/1000,height[v]*k,(Math.floor(v/n)-c)*L/1000);};
  for(let i=0;i<n;i+=step)for(let j=0;j<n-1;j++){add(i*n+j,i*n+j+1);add(j*n+i,(j+1)*n+i);}
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(p,3));
  const lines=new THREE.LineSegments(g,new THREE.LineBasicMaterial({color:0xff835e,transparent:true,opacity:0.9,depthTest:false,depthWrite:false}));lines.renderOrder=10;return lines;
}
export class TerrainComparison {
  constructor(stage){
    this.stage=stage;this.renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});this.renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));this.renderer.setClearColor(0x101b1f,1);
    const canvas=this.renderer.domElement;canvas.style.cssText='display:block;width:100%;height:100%';canvas.tabIndex=0;canvas.setAttribute('aria-label','Terrain comparison. Arrow keys rotate, plus and minus zoom.');stage.appendChild(canvas);
    this.scene=new THREE.Scene();this.camera=new THREE.PerspectiveCamera(36,1,0.05,500);this.camera.position.set(0,8,12);
    this.controls=new OrbitControls(this.camera,canvas);this.controls.enablePan=false;this.controls.enableDamping=false;this.controls.maxPolarAngle=Math.PI*0.49;this.controls.addEventListener('change',()=>this.render());
    this.mode='side';this.swipe=0.5;this.toggles={};this.isolation='both';this.hasFitted=false;
    this.keyHandler=(e)=>{const s=new THREE.Spherical().setFromVector3(this.camera.position.clone().sub(this.controls.target));if(e.key==='ArrowLeft')s.theta-=0.12;else if(e.key==='ArrowRight')s.theta+=0.12;else if(e.key==='ArrowUp')s.phi=Math.max(0.1,s.phi-0.12);else if(e.key==='ArrowDown')s.phi=Math.min(this.controls.maxPolarAngle,s.phi+0.12);else if(e.key==='+'||e.key==='=')s.radius=Math.max(this.controls.minDistance,s.radius*0.9);else if(e.key==='-')s.radius=Math.min(this.controls.maxDistance,s.radius*1.1);else return;e.preventDefault();this.camera.position.copy(this.controls.target).add(new THREE.Vector3().setFromSpherical(s));this.controls.update();this.render();};
    canvas.addEventListener('keydown',this.keyHandler);this.observer=new ResizeObserver(()=>this.resize());this.observer.observe(stage);this.resize();
  }
  load({target,analog,rotationDeg,verticalExaggeration}){
    if(target.n!==analog.n||target.L!==analog.L||target.R!==analog.R)throw new Error('Terrain grids do not match');
    if(!Number.isFinite(verticalExaggeration)||verticalExaggeration<=0)throw new Error('Missing or invalid vertical exaggeration');
    if(!Number.isFinite(rotationDeg))throw new Error('Missing or invalid rotation');
    for (const t of [target, analog]) {
      if (!Number.isInteger(t.n) || t.n < 2 || !Number.isFinite(t.L) || t.L <= 0 || !Number.isFinite(t.R) || t.R <= 0 || t.height.length !== t.n*t.n || t.layers.length !== t.n*t.n || !Array.from(t.height).some(Number.isFinite)) throw new Error('Invalid terrain data');
    }
    this.clear();const k=verticalExaggeration/1000;
    const height=rotateField(analog.height,analog.n,analog.L,analog.R,rotationDeg,false),layers=rotateField(analog.layers,analog.n,analog.L,analog.R,rotationDeg,true);
    this.target=surface(target,target.height,target.layers,k,[0.80,0.48,0.34]);this.earth=surface(analog,height,layers,k,[0.69,0.68,0.58]);this.lines=surveyLines(this.target);
    this.scene.add(this.target.mesh,this.earth.mesh,this.lines);let relief=0;for(const h of [target.height,height])for(const v of h)if(Number.isFinite(v))relief=Math.max(relief,Math.abs(v*k));
    this.radius=Math.hypot(target.R/1000,relief)*1.08;this.paint();if (!this.hasFitted) this.fit();this.render();
  }
  paint(){for(const s of [this.target,this.earth])if(s){paintLayers(s.layers,s.valid,s.base,this.toggles,s.mesh.geometry.attributes.color.array,s.shade);s.mesh.geometry.attributes.color.needsUpdate=true;}}
  setLayers(toggles){this.toggles={...toggles};this.paint();this.render();}
  setMode(mode){if(!['side','swipe','overlay'].includes(mode))throw new Error('Unknown comparison mode');this.mode=mode;this.fit();this.render();}
  setIsolation(value){if(!['both','target','earth'].includes(value))throw new Error('Unknown isolation');this.isolation=value;this.render();}
  resetView(){this.setView('oblique');this.fit();this.render();}
  setView(view){
    const directions={top:[0,1,0.001],oblique:[0,8,12],profile:[0,0.35,14]};
    if(!directions[view])throw new Error('Unknown camera view');
    const distance=this.camera.position.distanceTo(this.controls.target);
    this.camera.position.copy(this.controls.target).add(new THREE.Vector3(...directions[view]).normalize().multiplyScalar(distance));
    this.controls.update();this.render();
  }
  // East-west sampled row in metres; null marks missing data. This is a display slice, not a derived score.
  getProfile(fraction=0.5){
    if(!this.target || !this.earth)return null;
    const f=Number(fraction);if(!Number.isFinite(f))throw new Error('Invalid profile position');
    const {n,L}=this.target,row=Math.round(Math.max(0,Math.min(1,f))*(n-1)),center=(n-1)/2;
    const samples=[];for(let j=0;j<n;j++){const i=row*n+j,t=this.target.height[i],e=this.earth.height[i];samples.push({distanceM:(j-center)*L,target:Number.isFinite(t)?t:null,earth:Number.isFinite(e)?e:null});}
    return {fraction:row/(n-1),offsetM:(center-row)*L,samples};
  }
  setSwipe(value){if(Number.isFinite(Number(value)))this.swipe=Math.max(0,Math.min(1,Number(value)));this.render();}
  fit(){if(!this.radius||!this.width||!this.height)return;const aspect=(this.mode==='side'?this.width/2:this.width)/this.height,vfov=THREE.MathUtils.degToRad(this.camera.fov),hfov=2*Math.atan(Math.tan(vfov/2)*aspect),distance=this.radius/Math.sin(Math.min(vfov,hfov)/2)*1.06,dir=this.camera.position.clone().sub(this.controls.target).normalize();this.camera.position.copy(this.controls.target).addScaledVector(dir,distance);this.controls.minDistance=distance*0.45;this.controls.maxDistance=distance*2.5;this.hasFitted=true;this.controls.update();}
  resize(){const w=this.stage.clientWidth,h=this.stage.clientHeight;if(w<2||h<2)return;this.width=w;this.height=h;this.renderer.setSize(w,h,false);this.fit();this.render();}
  render(){if(!this.width||!this.height)return;const r=this.renderer,w=this.width,h=this.height;r.setScissorTest(true);
    const draw=(x,width,target,earth,lines,full=false)=>{if(width<=0)return;if(this.target)this.target.mesh.visible=target;if(this.earth)this.earth.mesh.visible=earth;if(this.lines)this.lines.visible=lines;const vw=full?w:width;r.setViewport(full?0:x,0,vw,h);r.setScissor(x,0,width,h);this.camera.aspect=vw/h;this.camera.updateProjectionMatrix();r.render(this.scene,this.camera);};
    if(this.mode==='side'){const half=Math.floor(w/2);draw(0,half,true,false,false);draw(half,w-half,false,true,false);}else if(this.mode==='swipe'){const split=Math.round(w*this.swipe);draw(0,split,true,false,false,true);draw(split,w-split,false,true,false,true);}else if(this.isolation==='target')draw(0,w,true,false,false);else if(this.isolation==='earth')draw(0,w,false,true,false);else draw(0,w,false,true,true);r.setScissorTest(false);
  }
  clear(){for(const o of [this.target?.mesh,this.earth?.mesh,this.lines])if(o){this.scene.remove(o);o.geometry.dispose();o.material.dispose();}this.target=this.earth=this.lines=null;}
  dispose(){this.observer.disconnect();this.renderer.domElement.removeEventListener('keydown',this.keyHandler);this.controls.dispose();this.clear();this.renderer.dispose();this.renderer.domElement.remove();}
}
