import { h, fmt } from "./dom.js";
import { FEATURE_INFO, BODY_NAMES } from "./config.js";
import { scoringKeys } from "./panels.js";

const EXPLAIN = {
  slope_p95_deg: {title:"How steep is the ground?", description:"The 95th-percentile slope describes the steeper part of each measured area. It is measured over a 100 m baseline, not at the scale of a wheel or a landing foot.", limit:"Similar slopes do not establish that either location is safe to land on."},
  hi: {title:"Where does the terrain sit between low and high?", description:"This index places the mean height between the 5th and 95th elevation percentiles. It describes the balance of lower and higher ground within the whole circle.", limit:"A similar index does not mean the depressions have the same origin or line up point for point."},
  hurst: {title:"How does roughness change with scale?", description:"This exponent describes how height differences grow across several spatial lags. It compares the texture of the relief across scales.", limit:"This is a comparative terrain measure. It does not identify rocks, soil or geological composition."},
};
export function renderInspector(card,target,entry,onSelect,preferred) {
  const root=document.querySelector("#propertyList"), detail=document.querySelector("#propertyDetail");
  const keys=scoringKeys(card).scored;
  const matches=keys.filter(k=>(card.similar || []).includes(k));
  document.querySelector("#whySummary").textContent=`${matches.length} of ${keys.length} scored properties are within one calibrated standard deviation. Distance D ${fmt(card.D,3)}; lower means closer on these properties.`;
  let current=keys.includes(preferred) ? preferred : keys[0];
  const buttons=keys.map(key=>{
    const match=(card.similar || []).includes(key), different=(card.different || []).includes(key);
    return h("button",{type:"button",class:"property-button " + (match ? "match" : "differs"),"aria-pressed":String(key===current),onclick:()=>select(key)},
      h("span",{},FEATURE_INFO[key].label),h("small",{},match ? "Similar across this area" : different ? "Different across this area" : "No comparison value"));
  });
  root.replaceChildren(...buttons);
  function select(key) {
    current=key;
    buttons.forEach((b,i)=>b.setAttribute("aria-pressed",String(keys[i]===key)));
    const f=card.features?.[key] || {}, info=FEATURE_INFO[key], copy=EXPLAIN[key] || {title:info.label,description:"A property of the complete measured area.",limit:"A whole-area measure does not establish point-by-point agreement."};
    const unit=info.unit === "deg" ? " deg" : info.unit;
    const valid=Number.isFinite(f.z_diff), match=(card.similar || []).includes(key);
    detail.replaceChildren(h("h3",{},copy.title),h("p",{},copy.description),
      h("div",{class:"property-values"},h("div",{class:"pair-target"},h("span",{},BODY_NAMES[target.body]),h("strong",{},fmt(f.target,info.digits,unit))),h("div",{class:"pair-earth"},h("span",{},"Earth"),h("strong",{},fmt(f.analog,info.digits,unit)))),
      h("p",{class:match ? "similarity-verdict" : "difference-verdict"},valid ? `${fmt(Math.abs(f.z_diff),2)} sigma apart / ${match ? "within" : "outside"} the 1 sigma similarity criterion.` : "Comparison value unavailable."),
      h("p",{class:"note"},"Sigma is the calibrated spread of this property in the Earth search pool."),h("p",{class:"scope-note"},copy.limit));
    onSelect?.(key);
  }
  if(current) select(current);
  renderUseCase(card,target,entry);
}

export function renderProfile(svg,samples) {
  const ns="http://www.w3.org/2000/svg";
  const el=(tag,attrs,text)=>{const n=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!=null)n.textContent=text;return n;};
  svg.replaceChildren();
  const heights=samples.flatMap(s=>[s.target,s.analog]).filter(Number.isFinite);
  if(!samples.length || !heights.length){svg.append(el("text",{x:35,y:90,fill:"currentColor"},"No valid heights along this cut."));return;}
  const lo=Math.min(...heights),hi=Math.max(...heights),span=Math.max(hi-lo,1),pad=span*.12;
  const xs=samples.map(s=>s.distanceKm).filter(Number.isFinite),xmin=Math.min(...xs),xmax=Math.max(...xs);
  const X=x=>65+(x-xmin)/Math.max(xmax-xmin,.001)*800, Y=y=>178-(y-lo+pad)/(span+2*pad)*150;
  for(let i=0;i<4;i++){const v=lo+(hi-lo)*i/3,y=Y(v);svg.append(el("line",{x1:65,x2:865,y1:y,y2:y,stroke:"#34404c","stroke-width":1}),el("text",{x:55,y:y+4,"text-anchor":"end",fill:"#aab7c5","font-size":12},Math.round(v)+" m"));}
  for(const [key,color] of [["target","#559BFF"],["analog","#58CB91"]]){
    let path="",pen=false;
    for(const s of samples){if(!Number.isFinite(s[key])){pen=false;continue;}path+=(pen ? "L" : "M")+X(s.distanceKm).toFixed(2)+","+Y(s[key]).toFixed(2);pen=true;}
    svg.append(el("path",{d:path,stroke:color,"stroke-width":2.5,fill:"none","vector-effect":"non-scaling-stroke"}));
  }
  svg.append(el("text",{x:65,y:205,fill:"#aab7c5","font-size":12},`${xmin.toFixed(1)} km / west`),el("text",{x:865,y:205,"text-anchor":"end",fill:"#aab7c5","font-size":12},`${xmax.toFixed(1)} km / east`));
}


// Explain the practical question after the visitor has inspected the geometry.
// These are exported slope shares, never inferred mission success probabilities.
function renderUseCase(card,target,entry) {
  const root=document.querySelector("#useCaseSummary");
  if(!root) return;
  const keys=scoringKeys(card).scored;
  const similar=keys.filter(k=>(card.similar || []).includes(k)).map(k=>FEATURE_INFO[k].label.toLowerCase());
  const different=keys.filter(k=>(card.different || []).includes(k)).map(k=>FEATURE_INFO[k].label.toLowerCase());
  // The mission-proven shares are shown once, in step 02 of the dossier; this step only states the use.
  const parts=[
    h("p",{class:"eyebrow"},"From resemblance to a useful question"),
    h("h3",{},"What could this place help us study?"),
    h("p",{},similar.length ? `${entry.name} offers a candidate for comparing ${similar.join(", ")} with ${target.name}.` : `This pair has no scored properties within the current similarity criterion. Inspect its differences before considering a terrain analogy.`),
    different.length ? h("p",{class:"note"},`The analogy is weaker for ${different.join(", ")}.`) : null,
    h("p",{class:"scope-note"},"The mission-proven shares in step 02 describe terrain within a slope limit. Mission suitability also depends on surface material, hazards, gravity and environment; the shares do not predict mission success.")];
  root.replaceChildren(...parts.filter(Boolean));
}
