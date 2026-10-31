import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
const {chromium}=createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser=await chromium.launch({headless:true});
try{
  const page=await browser.newPage({viewport:{width:500,height:400}});
  await page.setContent('<style>body{margin:0}</style>'+readFileSync('tests/fixtures/svg-filters.svg','utf8'));
  const phases=['initial','blend','matrix','funcR','funcG','funcB','funcA','composite','convolve','distant','diffuse','displacement','shadow','flood','blur','imageAspect','imageBlue','merge','morphDilate','morphErode','offset','point','spotCone','specularZero','tile','turbSeed7','turbSeed0'];
  const rows=[];
  for(const phase of phases){
    rows.push(await page.evaluate(async phase=>{
      const node=id=>document.getElementById(id),number=(id,k,v)=>{node(id)[k].baseVal=v;},list=(id,k,values)=>values.forEach((v,i)=>{node(id)[k].baseVal.getItem(i).value=v;});
      if(phase==='blend')number('blend','mode',2);
      if(phase==='matrix')list('matrix','values',[0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,1,0]);
      if(['funcR','funcG','funcB','funcA'].includes(phase)){number(phase,'slope',0);number(phase,'intercept',{funcR:1,funcG:0,funcB:1,funcA:0.5}[phase]);}
      if(phase==='composite'){number('composite','k2',0);number('composite','k3',1);}
      if(phase==='convolve'){list('convolve','kernelMatrix',[0,0,0,0,0,0,0,0,0]);number('convolve','bias',0.5);}
      if(phase==='distant')number('distant','elevation',80);
      if(phase==='diffuse')number('diffuse','diffuseConstant',0);
      if(phase==='displacement')number('displacement','scale',20);
      if(phase==='shadow'){number('shadow','dx',10);number('shadow','dy',10);}
      if(phase==='flood')node('flood').style.setProperty('flood-color','rgb(0,255,0)');
      if(phase==='blur')node('blur').setStdDeviation(5,0);
      if(phase==='imageAspect')node('image').preserveAspectRatio.baseVal.align=1;
      if(phase==='imageBlue')node('image').href.baseVal=node('image').href.baseVal.replace("fill='red'","fill='blue'");
      if(phase==='merge')node('mergeNode').in1.baseVal='blue';
      if(phase==='morphDilate'){number('morphology','operator',2);number('morphology','radiusX',3);number('morphology','radiusY',3);}
      if(phase==='morphErode')number('morphology','operator',1);
      if(phase==='offset'){number('offset','dx',10);number('offset','dy',10);}
      if(phase==='point')number('point','z',10);
      if(phase==='spotCone'){number('spot','pointsAtX',100);number('spot','limitingConeAngle',5);}
      if(phase==='specularZero'){number('spot','pointsAtX',30);number('spot','limitingConeAngle',90);number('specular','specularConstant',0);}
      if(phase==='tile')node('tile').in1.baseVal='blue';
      if(phase==='turbSeed7')number('turbulence','seed',7);
      if(phase==='turbSeed0')number('turbulence','seed',0);
      if(phase==='initial'||phase==='imageBlue'){const image=new Image();image.src=node('image').href.baseVal;await image.decode();}
      await new Promise(requestAnimationFrame);
      return {phase};
    },phase));
    await page.screenshot({path:`artifacts/svg-filter-paint-${phase}.png`});
  }
  writeFileSync('artifacts/svg-filter-paint-browser.json',JSON.stringify({userAgent:await page.evaluate(()=>navigator.userAgent),rows},null,2)+'\n');console.log('Actual SVG browser filter paint phases',rows.length);
}finally{await browser.close();}
