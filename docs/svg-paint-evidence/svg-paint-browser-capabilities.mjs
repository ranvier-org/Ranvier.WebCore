import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
const {chromium}=createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const manifest=JSON.parse(readFileSync('artifacts/svg-paint-browser-manifest.json','utf8'));
const browser=await chromium.launch({headless:true});
try {
  const page=await browser.newPage();
  const result=await page.evaluate(({members,tags})=>{
    const ns='http://www.w3.org/2000/svg',aliases={SVGGradientElement:'linearGradient',SVGComponentTransferFunctionElement:'feFuncR',SVGFilterPrimitiveStandardAttributes:'feGaussianBlur',SVGTests:'mask',SVGURIReference:'image'};
    const svgDocument=new DOMParser().parseFromString('<svg xmlns="'+ns+'"/>','image/svg+xml');
    const summarize=value=>{
      if(value===null)return {kind:'null'};
      const kind=typeof value;
      if(kind!=='object')return {kind,value:kind==='function'?'function':value};
      const summary={kind,brand:value.constructor?.name};
      if('baseVal' in value){const base=value.baseVal;summary.baseVal=typeof base==='object'?{brand:base?.constructor?.name,valueAsString:base?.valueAsString,numberOfItems:base?.numberOfItems}:base;}
      else if('numberOfItems' in value)summary.numberOfItems=value.numberOfItems;
      return summary;
    };
    const rows=members.map(member=>{
      const tag=aliases[member.interface]||tags.find(t=>t.implementationInterface===member.interface||t.interface===member.interface)?.tag;
      const target=member.interface==='Document'?svgDocument:document.createElementNS(ns,tag||'svg');
      const row={group:member.group,interface:member.interface,member:member.member,tag:tag||null,actualBrand:target.constructor?.name};
      try {row.state=member.member in target?'Available':'NotExposed';row.result=summarize(target[member.member]);}
      catch(error){row.state='AvailableGetterError';row.error={name:error.name,message:error.message};}
      return row;
    });
    const script=document.createElementNS(ns,'script');
    script.type='application/ecmascript';script.setAttribute('async','');script.href.baseVal='#inert-reference';
    return {userAgent:navigator.userAgent,rows,inertScript:{connected:script.isConnected,type:script.type,async:script.async,href:script.href.baseVal},units:{unknown:SVGUnitTypes.SVG_UNIT_TYPE_UNKNOWN,userSpaceOnUse:SVGUnitTypes.SVG_UNIT_TYPE_USERSPACEONUSE,objectBoundingBox:SVGUnitTypes.SVG_UNIT_TYPE_OBJECTBOUNDINGBOX}};
  },manifest);
  writeFileSync('artifacts/svg-paint-browser-capabilities.json',JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify({rows:result.rows.length,missing:result.rows.filter(r=>r.state!=='Available'),inertScript:result.inertScript,units:result.units}));
} finally {await browser.close();}
