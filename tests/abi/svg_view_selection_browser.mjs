import { createRequire } from 'node:module';
import { readFile,writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
const require=createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json');
const {chromium}=require('playwright');
const fixture=await readFile('tests/fixtures/svg-view-selection.svg');
const server=createServer((request,response)=>{
  response.setHeader('Content-Type','image/svg+xml');response.end(fixture);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true});
const stages=[];
try {
  const page=await browser.newPage({viewport:{width:200,height:120},deviceScaleFactor:1});
  await page.goto(`http://127.0.0.1:${server.address().port}/fixture.svg`);
  const settle=()=>page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  const snapshot=async name=>{
    await settle();
    const state=await page.evaluate(()=>{
      const root=document.documentElement,m=root.getScreenCTM();
      return {hash:location.hash,useCurrentViewPresent:'useCurrentView' in root,currentViewPresent:'currentView' in root,
        rootViewBox:root.getAttribute('viewBox'),namedViewBox:document.getElementById('zoom').getAttribute('viewBox'),
        ctm:[m.a,m.b,m.c,m.d,m.e,m.f]};
    });
    const png=await page.screenshot();
    const pngPath=`artifacts/h07/svg-view-browser-${name}.png`;
    await writeFile(pngPath,png);
    stages.push({name,...state,pngPath,pngSha256:createHash('sha256').update(png).digest('hex')});
  };
  await snapshot('baseline');
  await page.evaluate(()=>{location.hash='zoom';});await snapshot('named');
  await page.evaluate(()=>document.getElementById('zoom').setAttribute('viewBox','20 20 20 20'));await snapshot('active-edit');
  await page.evaluate(()=>{location.hash='';});await snapshot('clear');
  await page.evaluate(()=>document.getElementById('zoom').setAttribute('viewBox','40 40 10 10'));await snapshot('former-edit');
  await page.evaluate(()=>{location.hash='svgView(viewBox(10,20,30,40))';});await snapshot('explicit');
  const evidence={browser:await browser.version(),fixtureSha256:createHash('sha256').update(fixture).digest('hex'),
    scope:'Actual Chromium fragment navigation/rendering oracle; native provider does not claim URL/history/:target behavior.',stages};
  await writeFile('artifacts/h07/svg-view-selection-browser.json',JSON.stringify(evidence,null,2));
  console.log(JSON.stringify(evidence));
} finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
