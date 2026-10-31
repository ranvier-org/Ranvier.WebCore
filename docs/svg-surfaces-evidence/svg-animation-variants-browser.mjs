import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
const {chromium}=createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser=await chromium.launch({headless:true});
try {
  const page=await browser.newPage({viewport:{width:500,height:300}});
  await page.setContent('<style>body{margin:0}</style>'+readFileSync('tests/fixtures/svg-animation-variants.svg','utf8'));
  const result=await page.evaluate(()=>{
    let assertions=0;const expect=(value,label)=>{assertions++;if(!value)throw new Error(label);};
    const matrix=m=>['a','b','c','d','e','f'].map(k=>m[k]);const close=(a,b,label)=>expect(a.length===b.length&&a.every((v,i)=>Math.abs(v-b[i])<0.002),label+': '+JSON.stringify(a));
    const root=document.getElementById('root');root.pauseAnimations();root.setCurrentTime(0);
    const pairs=['motion','transform','set'].map(id=>[document.getElementById(id),document.getElementById(id+'Target')]);
    for(const [animation,target] of pairs){expect(animation.targetElement===target,'real concrete target');animation.beginElement();}
    expect(pairs[0][0] instanceof SVGAnimateMotionElement&&pairs[1][0] instanceof SVGAnimateTransformElement&&pairs[2][0] instanceof SVGSetElement,'actual concrete interfaces');
    const reference=document.getElementById('motionReference');expect(reference instanceof SVGMPathElement&&reference.href.baseVal==='#motionPath','actual mpath');
    root.setCurrentTime(1);
    close(matrix(pairs[0][1].getScreenCTM()),[1,0,0,1,70,30],'motion path midpoint');
    close(matrix(pairs[1][1].getScreenCTM()),[Math.SQRT1_2,Math.SQRT1_2,-Math.SQRT1_2,Math.SQRT1_2,0,0],'transform rotation midpoint');
    expect(pairs[2][1].getBBox().x===350,'set actual geometry');
    for(const [animation] of pairs)animation.endElement();root.setCurrentTime(1.5);
    close(matrix(pairs[0][1].getScreenCTM()),[1,0,0,1,70,30],'motion end freeze');
    return {userAgent:navigator.userAgent,assertions,motion:matrix(pairs[0][1].getScreenCTM()),transform:matrix(pairs[1][1].getScreenCTM()),setX:pairs[2][1].getBBox().x};
  });
  await page.screenshot({path:'artifacts/svg-animation-variants-browser.png'});
  writeFileSync('artifacts/svg-animation-variants-browser.json',JSON.stringify(result,null,2)+'\n');console.log('PASS SVG concrete browser',JSON.stringify(result));
} finally {await browser.close();}
