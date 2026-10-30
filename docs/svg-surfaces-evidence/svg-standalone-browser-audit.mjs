import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
import {createServer} from 'node:http';
const {chromium}=createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser=await chromium.launch({headless:true});
const source='<svg xmlns="http://www.w3.org/2000/svg" id="root" width="500" height="300" viewBox="0 0 500 300"><view id="detail" viewBox="0 0 100 50"/><rect id="box" x="10" y="10" width="20" height="20" fill="red"/></svg>';
const server=createServer((request,response)=>{response.writeHead(200,{'Content-Type':'image/svg+xml'});response.end(source);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
try {
  const page=await browser.newPage({viewport:{width:500,height:300}});
  await page.goto(`http://127.0.0.1:${server.address().port}/diagram.svg`);
  const result=await page.evaluate(async()=>{
    const r=document.documentElement,v=document.getElementById('detail'),box=document.getElementById('box');const rows=[];
    const fields=m=>['a','b','c','d','e','f'].map(k=>m[k]);
    const rect=e=>{const b=e.getBoundingClientRect();return [b.x,b.y,b.width,b.height];};
    const snapshot=label=>rows.push({label,contentType:document.contentType,scale:r.currentScale,translate:[r.currentTranslate.x,r.currentTranslate.y],ctm:fields(box.getCTM()),screen:fields(box.getScreenCTM()),bcr:rect(box),rootBcr:rect(r),window:{innerWidth,innerHeight,devicePixelRatio},visualViewport:{width:visualViewport.width,height:visualViewport.height,scale:visualViewport.scale},hash:location.hash});
    snapshot('initial');r.currentScale=2;r.currentTranslate.x=20;r.currentTranslate.y=30;await new Promise(requestAnimationFrame);snapshot('scaleTranslate');
    r.currentTranslate.x=60;r.currentTranslate.y=60;await new Promise(requestAnimationFrame);snapshot('panAgain');
    r.currentScale=1;r.currentTranslate.x=0;r.currentTranslate.y=0;location.hash='detail';await new Promise(requestAnimationFrame);snapshot('activateView');
    v.viewBox.baseVal.width=200;await new Promise(requestAnimationFrame);snapshot('activeViewWidth200');
    location.hash='root';await new Promise(requestAnimationFrame);snapshot('resetView');
    return {userAgent:navigator.userAgent,rows};
  });
  await page.evaluate(()=>{const r=document.documentElement;r.currentScale=2;r.currentTranslate.x=20;r.currentTranslate.y=30;location.hash='root';});
  await page.screenshot({path:'artifacts/svg-standalone-browser-scale-translate.png'});
  await page.evaluate(()=>{const r=document.documentElement;r.currentTranslate.x=60;r.currentTranslate.y=60;});
  await page.screenshot({path:'artifacts/svg-standalone-browser-pan-again.png'});
  writeFileSync('artifacts/svg-standalone-browser-audit.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
} finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
