import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
const {chromium}=createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser=await chromium.launch({headless:true});
try{
  const page=await browser.newPage({viewport:{width:500,height:300}});
  await page.setContent('<style>body{margin:0}</style>'+readFileSync('tests/fixtures/svg-paint-servers.svg','utf8'));
  const rows=[];
  for(const phase of ['translated','typedViewBox','authoredViewBox']){
    const row=await page.evaluate(phase=>{
      const p=document.getElementById('pattern'),r=document.getElementById('root');
      if(phase==='translated'){
        Object.assign(p.x.baseVal,{value:5});p.y.baseVal.value=125;p.width.baseVal.value=20;p.height.baseVal.value=20;
        const t=r.createSVGTransform();t.setTranslate(3,4);p.patternTransform.baseVal.appendItem(t);
      }else if(phase==='typedViewBox'){
        Object.assign(p.viewBox.baseVal,{x:0,y:0,width:10,height:10});p.preserveAspectRatio.baseVal.align=1;
      }else p.setAttribute('viewBox','0 0 10 10');
      const b=p.viewBox.baseVal;return {phase,viewBox:p.getAttribute('viewBox'),rect:[b.x,b.y,b.width,b.height],align:p.preserveAspectRatio.baseVal.align};
    },phase);
    await page.screenshot({path:'artifacts/pattern-'+phase+'.png'});rows.push(row);
  }
  writeFileSync('artifacts/svg-pattern-viewbox-oracle.json',JSON.stringify(rows,null,2)+'\n');console.log(JSON.stringify(rows));
}finally{await browser.close();}
