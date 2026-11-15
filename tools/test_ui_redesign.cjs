const fs=require('node:fs/promises');
const path=require('node:path');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const {JSDOM}=require(process.env.UI_QA_JSDOM || 'jsdom');
const root=path.resolve(__dirname,'../site');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function run(reduced,noWebGL=false){
 const html=await fs.readFile(root+'/index.html','utf8');
 const dom=new JSDOM(html,{url:'http://localhost:8767/',runScripts:'outside-only',pretendToBeVisual:true});
 const w=dom.window, errors=[];
 w.addEventListener('error',e=>errors.push(e.error?.message||e.message));
 w.ResizeObserver=class{observe(){}disconnect(){}};
 w.matchMedia=()=>({matches:reduced,addEventListener(){},removeEventListener(){}});
 w.scrollTo=()=>{};w.__animations=0;w.__views={};w.__noWebGL=noWebGL;
 w.Element.prototype.animate=function(){w.__animations++;return {finished:Promise.resolve(),cancel(){}}};
 let failure=null;
 w.fetch=async rel=>{
  if(failure && String(rel).includes(failure)){failure=null;return {ok:false,status:503};}
  try{const b=await fs.readFile(path.join(root,String(rel)));return{ok:true,status:200,json:async()=>JSON.parse(b.toString()),arrayBuffer:async()=>b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength)}}catch{return{ok:false,status:404}}
 };
 const ctx=dom.getInternalVMContext(),mods=new Map();
 const fakeView=`export class ComparisonView{constructor(stage){if(window.__noWebGL)throw new Error('WebGL unavailable');this.stage=stage;this.controls={};this.mode='split';window.__views[stage.id]=this;}load(data){this.data=data;this.profileFraction=this.profileFraction??null;}setMode(mode){this.mode=mode;}setSwipe(v){this.swipe=v;}setOpacity(v){this.opacity=v;}setProfile(v){this.profileFraction=v;if(v==null)return [];const d=this.data.target,n=d.n,row=Math.round(v*(n-1));return Array.from({length:n},(_,j)=>({distanceKm:(j-(n-1)/2)*d.L/1000,target:Number.isFinite(d.height[row*n+j])?d.height[row*n+j]:null,analog:Number.isFinite(this.data.analog.height[row*n+j])?this.data.analog.height[row*n+j]:null}));}setCameraView(v){this.cameraView=v;}setOverlayLayer(v){this.overlayLayer=v;}setSeparation(v){this.separation=v;}resetCamera(){}start(){this.running=true;}stop(){this.running=false;}dispose(){}nudge(){}}`;
 const fakeGlobe=`export class GlobeView{constructor(stage,opts){if(window.__noWebGL)throw new Error('WebGL unavailable');this.stage=stage;this.controls={};this.opts=opts;}setBody(){}setPins(){}setCoverage(){}setCells(){}setRegionalCells(){}start(){}stop(){}setSelected(){}flyTo(){}flyToCell(){}flyToLatLon(){}setMarks(){}resetView(){}nudge(){}}`;
 async function getModule(file){
  file=path.resolve(file);if(mods.has(file))return mods.get(file);
  const code=file.endsWith('comparison-view.js')?fakeView:file.endsWith('globe.js')?fakeGlobe:await fs.readFile(file,'utf8');
  const m=new vm.SourceTextModule(code,{context:ctx,identifier:file});mods.set(file,m);return m;
 }
 const app=await getModule(root+'/js/app.js');
 await app.link((spec,ref)=>getModule(path.resolve(path.dirname(ref.identifier),spec)));
 await app.evaluate();
 const q=s=>w.document.querySelector(s);
 const wait=async(test,label)=>{for(let i=0;i<150;i++){if(test())return;await sleep(20);}throw new Error('Timeout: '+label+'; '+q('#globalError').textContent);};
 const active=name=>q('#screen-'+name).classList.contains('active');
 const go=async name=>{w.location.hash=name;await wait(()=>active(name),'route '+name);await sleep(20);};

 await wait(()=>q('#targetCards button'),'targets');
 q('#targetCards button').click();
 await wait(()=>!q('#twinBody').hidden && q('#useCaseSummary').textContent.includes('What could'),'automatic pair');
 await wait(()=>q('#holoStage').dataset.loading==='false','terrain ready');
 assert.ok(q('#rankList button'));assert.equal(q('#missionBody').hidden,false);
 assert.ok(q('#mission-landing').textContent.includes('%'));
 assert.ok(q('#useCaseSummary').textContent.includes('do not predict mission success'));
 assert.ok(q('#screen-destination').classList.contains('active'));
 assert.equal(w.document.querySelectorAll('#propertyList button').length,3);
 if(noWebGL){
   assert.equal(w.document.querySelectorAll('#holoStage .terrain-fallback img').length,2);
   q('#rankList li:nth-child(2) button').click();
   await wait(()=>q('#holoStage').dataset.loading==='false','fallback second');
   await sleep(60);
   assert.equal(w.document.querySelectorAll('#holoStage .terrain-fallback img').length,2);
 } else {
   q('[data-mode="overlay"]').click();
   assert.equal(q('#overlayGuide').hidden,false);assert.equal(q('#profileControls').hidden,false);
   assert.ok(q('#profileChart path'));
   q('[data-camera-view="underside"]').click();assert.equal(w.__views.holoStage.cameraView,'underside');
   q('[data-overlay-layer="earth"]').click();assert.equal(w.__views.holoStage.overlayLayer,'earth');
   const sep=q('#layerSeparation');if(sep){sep.value=50;sep.dispatchEvent(new w.Event('input'));assert.equal(w.__views.holoStage.separation,.5);}
   q('[data-mode="swipe"]').click();assert.equal(q('#swipeHandle').hidden,false);
   q('#swipeHandle').dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowRight'}));
   assert.equal(w.__views.holoStage.swipe,.55);
   const previous=q('#twinTitle').textContent;
   q('#rankList li:nth-child(2) button').click();
   await wait(()=>q('#twinTitle').textContent!==previous && q('#holoStage').dataset.loading==='false','inline second candidate');
   assert.equal(w.__views.holoStage.mode,'swipe');
 }
 q('[data-body="moon"]').click();
 const moon=[...w.document.querySelectorAll('#targetCards button')].find(b=>b.textContent.includes('Apollo'));
 moon.click();await wait(()=>q('#labelTarget').textContent.startsWith('Moon') && q('#holoStage').dataset.loading==='false','Moon auto pair');
 q('[data-body="mars"]').click();
 const bs=[...w.document.querySelectorAll('#targetCards button')];bs[1].click();bs[2].click();
 await wait(()=>q('#labelTarget').textContent.includes(bs[2].querySelector('strong').textContent) && q('#holoStage').dataset.loading==='false','latest target wins');
 // Ask the atlas: the panel loads only when opened; five preset counts; one preset; one slider change.
 const panel=q('#askPanel');assert.equal(panel.open,false);
 panel.open=true;panel.dispatchEvent(new w.Event('toggle'));
 await wait(()=>w.document.querySelectorAll('.ask-card').length===5,'ask cards');
 assert.deepEqual([...w.document.querySelectorAll('.ask-card .ask-count')].map(e=>e.textContent),['211','372','1','100','3']);
 w.document.querySelectorAll('.ask-card')[0].click();
 await wait(()=>q('[data-role=answer] h3')?.textContent.includes('Mars terrain with no Earth twin')&&q('[data-role=answer] .ask-caveat'),'gap answer');
 assert.equal(q('[data-role=answer] .ask-count').textContent,'211');
 assert.ok(q('[data-role=answer] .ask-caveat').textContent.includes('2,000-window bare-ground Earth pool'));
 w.document.querySelectorAll('.ask-card')[2].click();
 await wait(()=>q('[data-role=answer] h3')?.textContent.includes('Jezero rehearsal'),'jezero answer');
 assert.equal(q('[data-role=answer] .ask-count').textContent,'1');
 assert.ok(q('[data-role=answer] .ask-cite').textContent.includes('twins'));
 const slider=q('[data-role=answer] .ask-slider input');assert.equal(slider.value,'50');
 slider.value='200';slider.dispatchEvent(new w.Event('input'));
 assert.ok(Number(q('[data-role=answer] .ask-count').textContent)>1,'slider widens the town filter');
 slider.value='50';slider.dispatchEvent(new w.Event('input'));
 assert.equal(q('[data-role=answer] .ask-count').textContent,'1');
 await sleep(reduced?100:1000);assert.deepEqual(errors,[]);
 const ids=[...w.document.querySelectorAll('[id]')].map(n=>n.id);assert.equal(new Set(ids).size,ids.length);
 console.log(JSON.stringify({mode:noWebGL?'no-WebGL':reduced?'reduced-motion':'animated',result:'PASS',checks:['automatic candidates and comparison','inline candidate switching','real utility percentages','Mars and Moon','latest target wins','persistent workspace','unique IDs','no DOM exceptions']}));
 w.close();
}
(async()=>{await run(true);await run(false);await run(true,true);})().catch(e=>{console.error(e);process.exitCode=1;});
