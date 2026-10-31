import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
const {chromium}=createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const manifest=JSON.parse(readFileSync('artifacts/svg-filter-manifest.json','utf8'));
const browser=await chromium.launch({headless:true});
try {
  const page=await browser.newPage({viewport:{width:500,height:400}});
  await page.setContent('<style>body{margin:0}</style>'+readFileSync('tests/fixtures/svg-filters.svg','utf8'));
  const result=await page.evaluate(({rows})=>{
    const attributes=e=>Object.fromEntries(Array.from(e.attributes).map(a=>[a.name,a.value]));
    const scalar=value=>typeof value==='number'||typeof value==='boolean'||typeof value==='string';
    const error=f=>{try{f();return null;}catch(e){return e.name;}};
    const results=[];
    for(const row of rows){
      const target=document.getElementById(row.id),out={...row,brand:target.constructor.name};
      if(!(row.member in target)){out.state='NotExposed';results.push(out);continue;}
      out.state='Available';const animated=target[row.member],base=animated.baseVal;
      out.baseIdentity=animated.baseVal===animated.baseVal;
      out.beforeAttributes=attributes(target);
      if(scalar(base)){
        out.initial=base;
        const changed=typeof base==='boolean'?!base:typeof base==='string'?(row.member==='in1'||row.member==='in2'?'SourceAlpha':row.member==='href'?base.replace("fill='red'","fill='blue'"):'typed-probe'):row.root==='SVGAnimatedEnumeration'?(base===1?2:1):base+1;
        animated.baseVal=changed;out.changed=animated.baseVal;out.afterAttributes=attributes(target);animated.baseVal=base;
        if(row.root==='SVGAnimatedEnumeration')out.invalidEnum=error(()=>{animated.baseVal=999;});
      }else if(row.root==='SVGAnimatedLength'){
        out.initial=base.value;out.units=base.unitType;out.animatedReadonly=error(()=>{animated.animVal.value=99;});base.value=out.initial+1;out.changed=base.value;out.afterAttributes=attributes(target);base.value=out.initial;
      }else if(row.root==='SVGAnimatedNumberList'){
        out.initial=Array.from({length:base.numberOfItems},(_,i)=>base.getItem(i).value);out.animatedReadonly=error(()=>{animated.animVal.getItem(0).value=99;});const item=base.getItem(0);item.value=out.initial[0]+0.25;out.changed=Array.from({length:base.numberOfItems},(_,i)=>base.getItem(i).value);out.afterAttributes=attributes(target);item.value=out.initial[0];
      }else if(row.root==='SVGAnimatedPreserveAspectRatio'){
        out.initial={align:base.align,meetOrSlice:base.meetOrSlice};out.animatedReadonly=error(()=>{animated.animVal.align=1;});base.align=1;out.changed={align:base.align,meetOrSlice:base.meetOrSlice};out.afterAttributes=attributes(target);base.align=out.initial.align;
      }
      results.push(out);
    }
    const methods=[];
    for(const id of ['blur','shadow']){
      const element=document.getElementById(id);element.setStdDeviation(0,0);
      for(const index of [0,1])for(const invalid of [NaN,Infinity,-Infinity]){
        const args=[0,0];args[index]=invalid;const failure=error(()=>element.setStdDeviation(...args));methods.push({id,index,input:String(invalid),error:failure,values:[element.stdDeviationX.baseVal,element.stdDeviationY.baseVal]});
      }
    }
    return {userAgent:navigator.userAgent,rows:results,methods};
  },manifest);
  writeFileSync('artifacts/svg-filter-member-oracle.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({rows:result.rows.length,missing:result.rows.filter(r=>r.state==='NotExposed'),methods:result.methods.length,methodErrors:[...new Set(result.methods.map(r=>r.error))]}));
} finally {await browser.close();}
