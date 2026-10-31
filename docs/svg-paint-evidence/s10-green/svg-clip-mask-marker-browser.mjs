import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
const {chromium}=createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const model=JSON.parse(readFileSync('gen/dom-api.json','utf8'));
const ids={SVGClipPathElement:'clip',SVGMaskElement:'mask',SVGMarkerElement:'marker'};
const fields=model.functions.filter(f=>f.kind==='getter'&&ids[f.interface]).map(f=>({interface:f.interface,id:ids[f.interface],member:f.member,function:f.function,root:f.returns.root}));
const browser=await chromium.launch({headless:true});
try{
  const page=await browser.newPage({viewport:{width:400,height:300}});
  await page.setContent('<style>body{margin:0}</style>'+readFileSync('tests/fixtures/svg-clip-mask-marker.svg','utf8'));
  const result=await page.evaluate(fields=>{
    const root=document.getElementById('root'),rows=[],error=f=>{try{f();return null;}catch(e){return e.name;}};
    for(const field of fields){
      const target=document.getElementById(field.id),row={...field,brand:target.constructor.name};
      if(!(field.member in target)){row.state='NotExposed';rows.push(row);continue;}row.state='Available';
      const animated=target[field.member],base=field.root==='SVGStringList'?animated:animated.baseVal;
      if(typeof base==='number'){row.initial=base;animated.baseVal=base===1?2:1;row.changed=animated.baseVal;animated.baseVal=base;row.invalid=error(()=>{animated.baseVal=999;});}
      else if(field.root==='SVGAnimatedLength'||field.root==='SVGAnimatedAngle'){row.initial=base.value;row.unitType=base.unitType;row.readonly=error(()=>{animated.animVal.value=99;});base.value=row.initial+1;row.changed=base.value;base.value=row.initial;}
      else if(field.root==='SVGAnimatedRect'){row.initial=[base.x,base.y,base.width,base.height];row.readonly=error(()=>{animated.animVal.width=99;});base.width+=1;row.changed=[base.x,base.y,base.width,base.height];base.width-=1;}
      else if(field.root==='SVGAnimatedPreserveAspectRatio'){row.initial={align:base.align,meetOrSlice:base.meetOrSlice};row.readonly=error(()=>{animated.animVal.align=6;});base.align=base.align===1?6:1;row.changed={align:base.align,meetOrSlice:base.meetOrSlice};base.align=row.initial.align;}
      else if(field.root==='SVGAnimatedTransformList'){row.initial=base.numberOfItems;row.readonly=error(()=>animated.animVal.clear());const t=root.createSVGTransform();t.setTranslate(3,4);base.appendItem(t);row.changed=['a','b','c','d','e','f'].map(k=>base.getItem(0).matrix[k]);base.clear();}
      else if(field.root==='SVGStringList'){row.initial=base.numberOfItems;base.appendItem('zz');row.changed=base.getItem(0);base.clear();}
      rows.push(row);
    }
    const marker=document.getElementById('marker'),angle=root.createSVGAngle();angle.value=90;marker.setOrientToAngle(angle);
    const methods={angle90:{type:marker.orientType.baseVal,angle:marker.orientAngle.baseVal.value},wrong:error(()=>marker.setOrientToAngle({})),nullInput:error(()=>marker.setOrientToAngle(null))};marker.setOrientToAuto();methods.auto={type:marker.orientType.baseVal,angle:marker.orientAngle.baseVal.value};
    return {userAgent:navigator.userAgent,rows,methods};
  },fields);
  writeFileSync('artifacts/svg-clip-mask-marker-browser.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
}finally{await browser.close();}
