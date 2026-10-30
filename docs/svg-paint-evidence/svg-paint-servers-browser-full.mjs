import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
const {chromium}=createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser=await chromium.launch({headless:true});
try{
  const page=await browser.newPage({viewport:{width:500,height:300}});
  await page.setContent('<style>body{margin:0}</style>'+readFileSync('tests/fixtures/svg-paint-servers.svg','utf8'));
  const steps=['initial','linear50','gradientTranslate','spreadRepeat','gradientObjectUnits','missingGradient','radialMoved','radialFocal','stopGreen','stopOpacity','patternMoved','patternMovedY','patternTransform','patternViewBox','patternObjectUnits','patternContentUnits','patternTests','patternMissing'];
  const records=[];
  for(const phase of steps){
    const row=await page.evaluate(phase=>{
      const root=document.getElementById('root'),linear=document.getElementById('linear'),radial=document.getElementById('radial'),pattern=document.getElementById('pattern'),inherited=document.getElementById('inherited'),stop=document.getElementById('start');
      let assertions=0;const expect=(value,label)=>{assertions++;if(!value)throw new Error(label);};const error=(f,name,label)=>{let found;try{f();}catch(e){found=e.name;}expect(found===name,label+': '+found);};
      const move=(element,x,y,field)=>{const t=root.createSVGTransform();t.setTranslate(x,y);element[field].baseVal.appendItem(t);};
      if(phase==='initial'){
        for(const [target,fields] of [[linear,{x1:0,y1:0,x2:100,y2:0}],[radial,{cx:200,cy:50,r:50,fx:200,fy:50,fr:0}],[pattern,{x:0,y:120,width:10,height:10}]])for(const [field,initial] of Object.entries(fields)){const value=target[field];expect(value.baseVal.value===initial,'actual coordinate '+field);expect(value.baseVal===value.baseVal,'live base identity');error(()=>{value.animVal.value=99;},'NoModificationAllowedError','animated read-only');value.baseVal.value=initial+1;expect(target.getAttribute(field)===String(initial+1),'coordinate authored reflection');value.baseVal.value=initial;}
        for(const [target,fields] of [[linear,['gradientUnits','spreadMethod']],[pattern,['patternUnits','patternContentUnits']]])for(const field of fields){expect(target[field].baseVal===1,'actual enum');error(()=>{target[field].baseVal=999;},'TypeError','invalid enum');expect(target[field].baseVal===1,'atomic invalid enum');}
        expect(inherited.x2.baseVal.value===500&&inherited.href.baseVal==='#linear','authored default versus inherited rendering');
      }
      if(phase==='linear50')linear.x2.baseVal.value=50;
      if(phase==='gradientTranslate'){move(linear,20,0,'gradientTransform');error(()=>linear.gradientTransform.animVal.clear(),'NoModificationAllowedError','animated transform list');}
      if(phase==='spreadRepeat'){linear.gradientTransform.baseVal.clear();linear.spreadMethod.baseVal=3;}
      if(phase==='gradientObjectUnits'){linear.spreadMethod.baseVal=1;linear.gradientUnits.baseVal=2;}
      if(phase==='missingGradient'){linear.gradientUnits.baseVal=1;inherited.href.baseVal='#missing';}
      if(phase==='radialMoved'){inherited.href.baseVal='#linear';for(const [key,value] of Object.entries({cx:225,cy:55,r:20,fx:225,fy:55}))radial[key].baseVal.value=value;}
      if(phase==='radialFocal')radial.fr.baseVal.value=10;
      if(phase==='stopGreen'){stop.offset.baseVal=0.5;stop.style.setProperty('stop-color','rgb(0, 255, 0)');expect(stop.getAttribute('offset')==='0.5','stop offset reflection');}
      if(phase==='stopOpacity')stop.style.setProperty('stop-opacity','0.5');
      if(phase==='patternMoved')for(const [key,value] of Object.entries({x:5,width:20,height:20}))pattern[key].baseVal.value=value;
      if(phase==='patternMovedY')pattern.y.baseVal.value=125;
      if(phase==='patternTransform'){move(pattern,3,4,'patternTransform');error(()=>pattern.patternTransform.animVal.clear(),'NoModificationAllowedError','pattern animated transform list');}
      if(phase==='patternViewBox'){pattern.setAttribute('viewBox','0 0 20 20');Object.assign(pattern.viewBox.baseVal,{x:0,y:0,width:10,height:10});expect(pattern.preserveAspectRatio.baseVal.align===6,'default pattern alignment');pattern.preserveAspectRatio.baseVal.align=1;}
      if(phase==='patternObjectUnits'){pattern.patternTransform.baseVal.clear();pattern.removeAttribute('viewBox');for(const [key,value] of Object.entries({x:0,y:0,width:1,height:1}))pattern[key].baseVal.value=value;pattern.patternUnits.baseVal=2;}
      if(phase==='patternContentUnits')pattern.patternContentUnits.baseVal=2;
      if(phase==='patternTests'){pattern.patternUnits.baseVal=1;pattern.patternContentUnits.baseVal=1;for(const [key,value] of Object.entries({x:0,y:120,width:10,height:10}))pattern[key].baseVal.value=value;for(const [field,value] of [['requiredExtensions','urn:unsupported-svg-extension'],['systemLanguage','zz']]){expect(pattern[field].numberOfItems===0,'initial SVGTests list');expect(pattern[field].appendItem(value)===value&&pattern[field].getItem(0)===value&&pattern[field].numberOfItems===1,'real SVGTests edit');pattern[field].clear();expect(pattern[field].numberOfItems===0,'real SVGTests clear');}}
      if(phase==='patternMissing'){const derived=document.getElementById('patternDerived');expect(derived.href.baseVal==='#pattern','pattern reference');derived.href.baseVal='#missing';}
      return {phase,assertions};
    },phase);
    await page.screenshot({path:`artifacts/svg-paint-full-${phase}.png`});records.push(row);
  }
  const retained=await page.evaluate(()=>{const length=document.getElementById('linear').x2.baseVal;document.getElementById('root').remove();const before=length.value;length.value=88;return {before,after:length.value};});
  if(retained.before!==50||retained.after!==88)throw new Error('retained actual gradient length after detach');
  const result={userAgent:await page.evaluate(()=>navigator.userAgent),assertions:records.reduce((n,r)=>n+r.assertions,0)+2,records,retained};
  writeFileSync('artifacts/svg-paint-servers-browser-full.json',JSON.stringify(result,null,2)+'\n');console.log('PASS SVG paint browser state',JSON.stringify(result));
}finally{await browser.close();}
