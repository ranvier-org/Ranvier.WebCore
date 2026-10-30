import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
const {chromium}=createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser=await chromium.launch({headless:true});
try {
  const page=await browser.newPage({viewport:{width:500,height:400}});
  await page.setContent('<style>body{margin:0}</style>'+readFileSync('tests/fixtures/svg-filters.svg','utf8'));
  const rows=[];
  for(const phase of ['initial','typedKernel','bias','authoredKernel']){
    rows.push(await page.evaluate(phase=>{const c=document.getElementById('convolve');if(phase==='typedKernel')for(let i=0;i<9;i++)c.kernelMatrix.baseVal.getItem(i).value=0;if(phase==='bias')c.bias.baseVal=0.5;if(phase==='authoredKernel')c.setAttribute('kernelMatrix','0 0 0 0 0 0 0 0 0');return {phase,kernel:Array.from({length:9},(_,i)=>c.kernelMatrix.baseVal.getItem(i).value),attribute:c.getAttribute('kernelMatrix'),bias:c.bias.baseVal,divisor:c.divisor.baseVal};},phase));
    await page.screenshot({path:'artifacts/convolve-'+phase+'.png'});
  }
  writeFileSync('artifacts/svg-convolve-paint-oracle.json',JSON.stringify(rows,null,2)+'\n');console.log(JSON.stringify(rows));
} finally {await browser.close();}
