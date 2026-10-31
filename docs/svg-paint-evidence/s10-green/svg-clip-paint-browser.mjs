import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
const {chromium}=createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser=await chromium.launch({headless:true});
try{
 const page=await browser.newPage({viewport:{width:400,height:300}});
 await page.setContent('<style>body{margin:0}</style>'+readFileSync('tests/fixtures/svg-clip-mask-marker.svg','utf8'));
 const rows=[];
 for(const phase of ['initial','maskExtension','maskLanguage','maskBlack','maskAlpha','maskAlphaRepaint','markerNone','markerMeet']){
  rows.push(await page.evaluate(async phase=>{
   const n=id=>document.getElementById(id);
   if(phase==='maskExtension')n('mask').requiredExtensions.appendItem('zz');
   if(phase==='maskLanguage'){n('mask').requiredExtensions.clear();n('mask').systemLanguage.appendItem('zz');}
   if(phase==='maskBlack')n('mask').systemLanguage.clear();
   if(phase==='maskBlack')n('maskGeometry').setAttribute('fill','black');
   if(phase==='maskAlpha')n('mask').style.setProperty('mask-type','alpha');
   if(phase==='maskAlphaRepaint')n('maskGeometry').setAttribute('x','151');
   if(phase==='markerNone')n('marker').viewBox.baseVal.width=20;
   if(phase==='markerMeet')n('marker').preserveAspectRatio.baseVal.align=6;
   await new Promise(requestAnimationFrame);
   return {phase,maskType:getComputedStyle(n('mask')).maskType,markerBox:n('marker').getAttribute('viewBox'),aspect:n('marker').getAttribute('preserveAspectRatio')};
  },phase));
  await page.screenshot({path:`artifacts/svg-clip-${phase}.png`});
 }
 writeFileSync('artifacts/svg-clip-paint-browser.json',JSON.stringify({userAgent:await page.evaluate(()=>navigator.userAgent),rows},null,2));
 console.log(JSON.stringify(rows));
}finally{await browser.close();}
