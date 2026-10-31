import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium}=createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser=await chromium.launch({headless:true});
try{
  const page=await browser.newPage({viewport:{width:100,height:100}});const rows=[];
  for(const route of ['input','order']){
    await page.setContent('<style>body{margin:0}</style><svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><defs><filter id="filter" filterUnits="userSpaceOnUse" x="0" y="0" width="80" height="80" color-interpolation-filters="sRGB"><feFlood flood-color="blue" result="blue"/><feConvolveMatrix id="convolve" in="SourceGraphic" order="3" kernelMatrix="0 0 0 0 1 0 0 0 0" divisor="1" bias="0.25" targetX="1" targetY="1" preserveAlpha="true"/></filter></defs><rect x="20" y="20" width="20" height="20" fill="red" filter="url(#filter)"/></svg>');
    await page.screenshot({path:`artifacts/convolve-${route}-before.png`});
    rows.push(await page.evaluate(route=>{const c=document.getElementById('convolve');if(route==='input')c.in1.baseVal='blue';else c.orderX.baseVal=2;return {route,attributes:Object.fromEntries(Array.from(c.attributes).map(a=>[a.name,a.value]))};},route));
    await page.screenshot({path:`artifacts/convolve-${route}-after.png`});
  }
  writeFileSync('artifacts/svg-convolve-cache-browser.json',JSON.stringify(rows,null,2)+'\n');console.log(JSON.stringify(rows));
}finally{await browser.close();}
