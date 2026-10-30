import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
const {chromium}=createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const font=readFileSync('C:/wk/src/Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf').toString('base64');
const markup=readFileSync('tests/fixtures/svg-surfaces.html','utf8').replace('{{FONT_BASE64}}',font);
const browser=await chromium.launch({headless:true});
try {
  const page=await browser.newPage({viewport:{width:500,height:300}});
  await page.setContent(markup);
  await page.evaluate(async()=>{await document.fonts.load('20px SvgProbe');await document.fonts.ready;});
  const result=await page.evaluate(async()=>{
    let assertions=0;
    const expect=(ok,label)=>{assertions++;if(!ok)throw new Error(label);};
    const close=(a,b,label)=>expect(a.length===b.length&&a.every((x,i)=>Math.abs(x-b[i])<0.001),label+': '+JSON.stringify(a));
    const exception=(f,name,label)=>{let actual;try{f();}catch(e){actual=e.name;}expect(actual===name,label+': '+actual);};
    const rect=r=>[r.x,r.y,r.width,r.height];
    const matrix=m=>['a','b','c','d','e','f'].map(k=>m[k]);
    const root=document.getElementById('root'),box=document.getElementById('box');root.pauseAnimations();
    const query=root.createSVGRect();Object.assign(query,{x:5,y:5,width:30,height:30});
    for(const kind of ['Intersection','Enclosure']){
      const list=Array.from(root['get'+kind+'List'](query,null));
      expect(list.length===1&&list[0]===box,kind+' list identity');
      expect(root['check'+kind](box,query),kind+' predicate');
    }
    root.width.baseVal.value=600;close(matrix(box.getCTM()),[1,0,0,1,50,0],'root viewport width centering');root.width.baseVal.value=500;
    const view=document.getElementById('detail');view.viewBox.baseVal.width=200;close(matrix(box.getCTM()),[1,0,0,1,0,0],'inactive view does not claim root application');
    const plain=document.getElementById('plain'),pathText=document.getElementById('pathText');
    for(const [target,y] of [[plain,100],[pathText,150]]){
      expect(target.getNumberOfChars()===3,'character count');expect(target.getComputedTextLength()===60,'text length');expect(target.getSubStringLength(0,2)===40,'substring length');expect(target.getSubStringLength(1,99)===40,'substring clamping');
      for(let i=0;i<3;i++){
        const p=target.getStartPositionOfChar(i);close([p.x,p.y],[10+i*20,y],'character start');
        const end=target.getEndPositionOfChar(i),expectedEnd=target===plain?[[30,100],[49.6961555,103.4729614],[68.7938538,106.8404007]][i]:[30+i*20,150];close([end.x,end.y],expectedEnd,'character end');
        expect(Math.abs(target.getRotationOfChar(i)-(target===plain?i*10:0))<0.001,'character rotation');
        if(i===0)close(rect(target.getExtentOfChar(i)),[10,y-16,20,20],'Ahem extent');
      }
      exception(()=>target.getExtentOfChar(99),'IndexSizeError','invalid extent index');exception(()=>target.selectSubString(99,1),'IndexSizeError','invalid selection index');
      expect(target.getCharNumAtPosition({x:15,y:y-5})===0&&target.getCharNumAtPosition({x:-100,y:-100})===-1,'character hit query');target.selectSubString(1,1);expect(document.getSelection().toString()==='B','actual text substring selection');
    }
    const xFirst=plain.x.baseVal.getItem(0);exception(()=>{plain.x.animVal.getItem(0).value=99;},'NoModificationAllowedError','text animated x read-only');xFirst.value=20;close([plain.getStartPositionOfChar(0).x,plain.getStartPositionOfChar(0).y],[20,100],'typed text x list placement');xFirst.value=10;plain.lengthAdjust.baseVal=2;plain.textLength.baseVal.value=90;
    const adjustedText={computed:plain.getComputedTextLength(),bbox:rect(plain.getBBox()),end:{x:plain.getEndPositionOfChar(2).x,y:plain.getEndPositionOfChar(2).y},authored:plain.getAttribute('textLength'),lengthAdjust:plain.lengthAdjust.baseVal};
    pathText.startOffset.baseVal.value=30;const shifted=pathText.getStartPositionOfChar(0);close([shifted.x,shifted.y],[30,150],'text-path offset placement');
    expect(pathText.method.baseVal===1&&pathText.spacing.baseVal===2,'text-path properties');
    const cases=[['circle',[70,10,20,20],[['cx',100],['r',12]],[88,8,24,24]],['ellipse',[115,10,30,20],[['cx',135],['ry',15]],[120,5,30,30]],['line',[10,40,40,20],[['x2',70],['y2',80]],[10,40,60,40]],['box',[10,10,20,20],[['width',50],['height',30],['rx',10],['ry',5]],[10,10,50,30]]];
    for(const [id,initial,edits,after] of cases){const shape=document.getElementById(id);close(rect(shape.getBBox()),initial,id+' initial bounds');for(const [field,value] of edits){const animated=shape[field],base=animated.baseVal;expect(base===animated.baseVal,id+' live base identity');exception(()=>{animated.animVal.value=value+1;},'NoModificationAllowedError',id+' animated read-only');base.value=value;expect(base.value===value&&animated.animVal.value===value,id+' base/animated values');expect(shape.getAttribute(field)!==null,id+' attribute reflection');}close(rect(shape.getBBox()),after,id+' edited bounds');}
    for(const [id,index,field,value,after] of [['polygon',0,'x',170,[170,10,30,20]],['polyline',2,'y',40,[220,10,20,30]]]){const s=document.getElementById(id);s.points.getItem(index)[field]=value;close(rect(s.getBBox()),after,id+' points update geometry');}
    const path=document.getElementById('shapePath');expect(path instanceof SVGPathElement,'actual SVG path type');expect(path.getAttribute('d')==='M10 200H110','authored d read');path.setAttribute('d','M10 200H110V240H10Z');close(rect(path.getBBox()),[10,200,100,40],'authored d bounds');expect(path.getTotalLength()===280,'authored d engine length');path.setAttribute('d','');expect(path.getAttribute('d')==='','empty d remains present');path.removeAttribute('d');expect(path.getAttribute('d')===null&&path.getTotalLength()===0,'removed d is absent/zero-length');
    const convolve=document.getElementById('convolve');expect(convolve.preserveAlpha.baseVal===false,'real Boolean initial');convolve.preserveAlpha.baseVal=true;expect(convolve.preserveAlpha.animVal===true&&convolve.getAttribute('preserveAlpha')==='true','real Boolean mutation');expect(convolve.orderX.baseVal===3,'real integer initial');convolve.orderX.baseVal=4;expect(convolve.orderX.animVal===4,'real integer mutation');
    const animation=document.getElementById('animation'),animated=document.getElementById('animated'),events=[];
    for(const event of ['beginEvent','endEvent','repeatEvent'])animation.addEventListener(event,()=>events.push(event));
    expect(animation.targetElement===animated,'SMIL target identity');exception(()=>animation.getStartTime(),'InvalidStateError','unstarted start time');exception(()=>document.getElementById('indefinite').getSimpleDuration(),'NotSupportedError','indefinite duration');
    root.setCurrentTime(0);animation.beginElement();root.setCurrentTime(1);
    expect(animation.getStartTime()===0&&animation.getSimpleDuration()===2&&animation.getCurrentTime()===1,'SMIL real timing');close(rect(animated.getBBox()),[250,60,20,20],'SMIL seek geometry');expect(animated.x.baseVal.value===200&&animated.x.animVal.value===250,'SMIL base/animated distinction');
    animation.endElement();root.setCurrentTime(1.5);close(rect(animated.getBBox()),[250,60,20,20],'SMIL end freeze');
    for(const operation of ['beginElementAt','endElementAt'])for(const invalid of [NaN,Infinity,-Infinity])exception(()=>animation[operation](invalid),'TypeError','SMIL restricted offset');
    const live=document.getElementById('liveAnimation'),liveTarget=document.getElementById('liveTarget');
    const liveEvents=[];
    for(const event of ['beginEvent','endEvent','repeatEvent'])live.addEventListener(event,()=>liveEvents.push(event));
    const ended=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('SMIL real-time end event timeout: '+JSON.stringify(liveEvents))),2000);live.addEventListener('endEvent',()=>{clearTimeout(timer);resolve();},{once:true});});
    const beforeResume=root.getCurrentTime();live.beginElementAt(0.02);root.unpauseAnimations();expect(!root.animationsPaused(),'SMIL resumed state');await ended;root.pauseAnimations();
    expect(root.animationsPaused()&&root.getCurrentTime()>beforeResume,'SMIL real clock advances then pauses');
    expect(liveEvents.includes('beginEvent')&&liveEvents.includes('repeatEvent')&&liveEvents.includes('endEvent'),'real running SMIL event delivery: '+JSON.stringify(liveEvents));
    close(rect(liveTarget.getBBox()),[370,220,20,20],'SMIL running animation changes actual geometry');
    const stopped=root.getCurrentTime();await new Promise(resolve=>setTimeout(resolve,30));expect(root.getCurrentTime()===stopped,'paused clock stays fixed');
    live.beginElement();live.endElementAt(0.05);root.setCurrentTime(stopped+0.05);close(rect(liveTarget.getBBox()),[360,220,20,20],'positive endElementAt freezes interpolated geometry');
    const retainedBoolean=convolve.preserveAlpha,retainedInteger=convolve.orderX;root.remove();expect(retainedBoolean.baseVal===true&&retainedInteger.baseVal===4,'retained real values after detach');
    return {userAgent:navigator.userAgent,assertions,adjustedText,pausedSeekEvents:events,liveEvents,currentViewCapability:typeof root.currentView==='undefined'?'NotExposed':'Available',pathDataCapability:'authored d through actual SVGPathElement attribute operations and engine geometry',fontReady:document.fonts.check('20px SvgProbe')};
  });
  writeFileSync('artifacts/svg-surfaces-browser-proof.json',JSON.stringify(result,null,2)+'\n');console.log('PASS SVG surfaces browser:',JSON.stringify(result));
} finally {await browser.close();}
