import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
const {chromium}=createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const font=readFileSync('C:/wk/src/Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf').toString('base64');
const markup=readFileSync('tests/fixtures/svg-surfaces.html','utf8').replace('{{FONT_BASE64}}',font);
const browser=await chromium.launch({headless:true});
try {
  const page=await browser.newPage({viewport:{width:500,height:300}});
  await page.setContent(markup);await page.evaluate(async()=>{await document.fonts.load('20px SvgProbe');await document.fonts.ready;});
  const result=await page.evaluate(()=>{
    const plain=document.getElementById('plain'),rows=[];
    for(const rotation of ['0 0 0','0 10 20'])for(const adjust of [1,2]){
      plain.setAttribute('rotate',rotation);plain.lengthAdjust.baseVal=adjust;plain.textLength.baseVal.value=90;
      const point=p=>[p.x,p.y],rect=r=>[r.x,r.y,r.width,r.height];
      rows.push({rotation,adjust,computed:plain.getComputedTextLength(),substring01:plain.getSubStringLength(0,2),substring12:plain.getSubStringLength(1,2),starts:[0,1,2].map(i=>point(plain.getStartPositionOfChar(i))),ends:[0,1,2].map(i=>point(plain.getEndPositionOfChar(i))),extents:[0,1,2].map(i=>rect(plain.getExtentOfChar(i))),bbox:rect(plain.getBBox())});
    }
    return {userAgent:navigator.userAgent,rows};
  });
  writeFileSync('artifacts/svg-text-adjustment-oracle.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
} finally {await browser.close();}
