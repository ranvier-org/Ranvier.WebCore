import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium}=createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser=await chromium.launch({headless:true});
try{
  const page=await browser.newPage({viewport:{width:100,height:100}});
  await page.setContent('<style>body{margin:0}</style><svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><defs><filter id="filter" filterUnits="userSpaceOnUse" x="0" y="0" width="80" height="80"><feImage id="image" preserveAspectRatio="xMidYMid meet" href="data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'40\' height=\'20\'%3E%3Crect width=\'40\' height=\'20\' fill=\'red\'/%3E%3C/svg%3E"/></filter></defs><rect x="20" y="20" width="20" height="20" filter="url(#filter)"/></svg>');
  await page.waitForTimeout(50);const rows=[];
  for(const phase of ['initial','typedNone','authoredNone']){
    rows.push(await page.evaluate(phase=>{const i=document.getElementById('image');if(phase==='typedNone')i.preserveAspectRatio.baseVal.align=1;if(phase==='authoredNone')i.setAttribute('preserveAspectRatio','none');return {phase,align:i.preserveAspectRatio.baseVal.align,attribute:i.getAttribute('preserveAspectRatio')};},phase));
    await page.screenshot({path:`artifacts/feimage-${phase}.png`});
  }
  writeFileSync('artifacts/svg-feimage-browser-oracle.json',JSON.stringify(rows,null,2)+'\n');console.log(JSON.stringify(rows));
}finally{await browser.close();}
