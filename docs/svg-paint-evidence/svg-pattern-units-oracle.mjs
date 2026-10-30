import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
const {chromium}=createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser=await chromium.launch({headless:true});
try {
  const page=await browser.newPage({viewport:{width:500,height:300}});
  await page.setContent('<style>body{margin:0}</style>'+readFileSync('tests/fixtures/svg-paint-servers.svg','utf8'));
  const rows=[];
  for(const [units,content] of [[2,1],[2,2],[1,1]]){
    rows.push(await page.evaluate(([units,content])=>{const p=document.getElementById('pattern');for(const [k,v] of Object.entries({x:0,y:0,width:1,height:1}))p[k].baseVal.value=v;p.patternUnits.baseVal=units;p.patternContentUnits.baseVal=content;return {units:p.patternUnits.baseVal,content:p.patternContentUnits.baseVal,x:p.x.baseVal.value,y:p.y.baseVal.value,width:p.width.baseVal.value,height:p.height.baseVal.value};},[units,content]));
    await page.screenshot({path:`artifacts/pattern-units-${units}-${content}.png`});
  }
  writeFileSync('artifacts/svg-pattern-units-oracle.json',JSON.stringify(rows,null,2)+'\n');console.log(JSON.stringify(rows));
} finally {await browser.close();}
