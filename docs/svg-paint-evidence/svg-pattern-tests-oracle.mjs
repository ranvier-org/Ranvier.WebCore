import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
const {chromium}=createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser=await chromium.launch({headless:true});
try{
  const page=await browser.newPage({viewport:{width:500,height:300}});
  await page.setContent('<style>body{margin:0}</style>'+readFileSync('tests/fixtures/svg-paint-servers.svg','utf8'));
  const rows=[];
  for(const phase of ['initial','extensionList','extensionAuthored','extensionClear','languageList','languageAuthored','languageClear']){
    rows.push(await page.evaluate(phase=>{const p=document.getElementById('pattern');if(phase==='extensionList')p.requiredExtensions.appendItem('urn:unsupported-svg-extension');if(phase==='extensionAuthored')p.setAttribute('requiredExtensions','urn:unsupported-svg-extension');if(phase==='extensionClear')p.requiredExtensions.clear();if(phase==='languageList')p.systemLanguage.appendItem('zz');if(phase==='languageAuthored')p.setAttribute('systemLanguage','zz');if(phase==='languageClear')p.systemLanguage.clear();return {phase,extensions:p.requiredExtensions.numberOfItems,language:p.systemLanguage.numberOfItems,requiredExtensions:p.getAttribute('requiredExtensions'),systemLanguage:p.getAttribute('systemLanguage')};},phase));
    await page.screenshot({path:'artifacts/pattern-tests-'+phase+'.png'});
  }
  writeFileSync('artifacts/svg-pattern-tests-oracle.json',JSON.stringify(rows,null,2)+'\n');console.log(JSON.stringify(rows));
}finally{await browser.close();}
