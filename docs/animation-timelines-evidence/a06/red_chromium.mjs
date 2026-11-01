// RED oracle (anim3): A06 document/custom timelines, A07 scroll timelines, A08 view timelines and ranges, in Chromium.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
export const PAGE = `<!doctype html><style>body{margin:0}#s{width:100px;height:100px;overflow:auto}#c{width:300px;height:400px}
#v{position:relative;width:100px;height:100px;overflow:auto}#vc{height:500px}#t{position:absolute;top:200px;width:20px;height:50px}
#n{width:80px;height:80px;overflow:auto}#nc{height:240px}#vis{width:100px;height:100px;overflow:visible}</style>
<div id=a style="width:40px;height:40px;background:red"></div>
<div id=s><div id=c><div id=n><div id=nc></div></div></div></div>
<div id=v><div id=vc></div><div id=t></div></div><div id=vis><div style="height:300px"></div></div>`;
const frames = (tab, n = 2) => tab.evaluate((n) => new Promise((r) => { const f = () => (--n ? requestAnimationFrame(f) : r()); requestAnimationFrame(f); }), n);
const browser = await chromium.launch({headless: true});
const out = {browser: 'Chromium ' + browser.version()};
try {
  const tab = await (await browser.newContext({viewport: {width: 320, height: 240}, deviceScaleFactor: 1})).newPage();
  await tab.setContent(PAGE);
  await tab.evaluate(() => {
    window.num = (v) => v === null ? null : typeof v === 'number' ? {number: v} : {value: v.value, unit: v.unit};
    window.range = (v) => typeof v === 'string' ? v : {rangeName: v.rangeName, offset: num(v.offset)};
  });
  // A06
  out.a06 = await tab.evaluate(() => {
    const dt = document.timeline, t = dt.currentTime;
    const own = new DocumentTimeline({originTime: 100}), dflt = new DocumentTimeline(), future = new DocumentTimeline({originTime: 1e9});
    const detached = document.implementation.createHTMLDocument('');
    const anim = new Animation(new KeyframeEffect(null, [{opacity: 0}, {opacity: 1}], 1000), detached.timeline);
    anim.play();
    return {
      isDocumentTimeline: dt instanceof DocumentTimeline, currentTimeType: typeof t, duration: dt.duration,
      ownMinusOrigin: own.currentTime === dt.currentTime - 100, defaultEqual: dflt.currentTime === dt.currentTime,
      futureNegative: future.currentTime < 0, ownDuration: own.duration, ownIsNew: own !== dt,
      detachedCurrentTime: detached.timeline.currentTime, detachedSame: detached.timeline === detached.timeline,
      detachedAnimation: {playState: anim.playState, currentTime: anim.currentTime, startTime: anim.startTime, pending: anim.pending},
      gates: {maximumFrameRate: 'maximumFrameRate' in DocumentTimeline.prototype, frameRate: 'frameRate' in Animation.prototype,
              customAnimate: typeof DocumentTimeline.prototype.animate},
    };
  });
  await tab.evaluate(() => {
    const el = document.getElementById('a');
    window.own = new DocumentTimeline({originTime: 100});
    window.a1 = el.animate([{opacity: 0}, {opacity: 1}], 10000);
    window.a2 = el.animate([{opacity: 0}, {opacity: 1}], 10000);
    window.a3 = new Animation(new KeyframeEffect(el, [{opacity: 0}, {opacity: 1}], 10000), own); a3.play();
  });
  await frames(tab);
  out.a06.synchronized = await tab.evaluate(() => ({
    sameStart: a1.startTime === a2.startTime, ownStartOffset: a1.startTime - a3.startTime, sameCurrent: a1.currentTime === a3.currentTime,
    started: a1.startTime !== null && a3.startTime !== null, playState: [a1.playState, a3.playState]}));
  out.a06.iframe = await tab.evaluate(async () => {
    const f = document.createElement('iframe'); document.body.appendChild(f);
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    const tl = f.contentDocument.timeline, before = tl.currentTime;
    const doc = f.contentDocument; f.remove();
    return {beforeType: typeof before, afterRemove: tl.currentTime, docTimelineSame: doc.timeline === tl};
  });
  await tab.evaluate(() => { a1.cancel(); a2.cancel(); a3.cancel(); });
  // A07
  out.a07 = await tab.evaluate(() => {
    const s = document.getElementById('s');
    window.tb = new ScrollTimeline({source: s}); window.ti = new ScrollTimeline({source: s, axis: 'inline'});
    window.tx = new ScrollTimeline({source: s, axis: 'x'}); window.ty = new ScrollTimeline({source: s, axis: 'y'});
    window.tdef = new ScrollTimeline(); window.tnull = new ScrollTimeline({source: null});
    window.tvis = new ScrollTimeline({source: document.getElementById('vis')});
    window.tn = new ScrollTimeline({source: document.getElementById('n')});
    window.sa = document.getElementById('a').animate([{opacity: 0}, {opacity: 1}], {timeline: tb});
    return {axes: [tb.axis, ti.axis, tx.axis, ty.axis], sourceIsS: tb.source === s, defaultSource: tdef.source === document.scrollingElement,
            nullSource: tnull.source, duration: num(tb.duration), isTimeline: tb instanceof AnimationTimeline, animTimeline: sa.timeline === tb};
  });
  out.a07.points = [];
  for (const [top, left, nested] of [[0, 0, 0], [150, 100, 80], [300, 200, 160], [75, 50, 40]]) {
    await tab.evaluate(([top, left, nested]) => { const s = document.getElementById('s'); s.scrollTop = top; s.scrollLeft = left; document.getElementById('n').scrollTop = nested; }, [top, left, nested]);
    await frames(tab);
    out.a07.points.push(await tab.evaluate(([top, left, nested]) => ({top, left, nested, block: num(tb.currentTime), inline: num(ti.currentTime), x: num(tx.currentTime), y: num(ty.currentTime),
      nestedBlock: num(tn.currentTime), nullSource: num(tnull.currentTime), visible: num(tvis.currentTime), def: num(tdef.currentTime),
      anim: num(sa.currentTime), animStart: num(sa.startTime), animState: sa.playState, opacity: getComputedStyle(document.getElementById('a')).opacity}), [top, left, nested]));
  }
  await tab.evaluate(() => { document.getElementById('c').style.height = '250px'; });
  await frames(tab);
  out.a07.resized = await tab.evaluate(() => ({scrollTop: document.getElementById('s').scrollTop, block: num(tb.currentTime), opacity: getComputedStyle(document.getElementById('a')).opacity}));
  await tab.evaluate(() => sa.cancel());
  // A08
  out.a08 = await tab.evaluate(() => {
    const t = document.getElementById('t');
    window.vt = new ViewTimeline({subject: t}); window.vi = new ViewTimeline({subject: t, inset: '10px'});
    window.vi2 = new ViewTimeline({subject: t, inset: [CSS.px(10), CSS.px(20)]});
    window.va = document.getElementById('a').animate([{opacity: 0}, {opacity: 1}], {timeline: vt, rangeStart: 'entry 0%', rangeEnd: 'exit 100%'});
    window.vc = document.getElementById('a').animate([{opacity: 0}, {opacity: 1}], {timeline: vt, rangeStart: {rangeName: 'contain', offset: CSS.percent(10)}, rangeEnd: 'contain 90%'});
    let ctorError = null; try { new ViewTimeline(); } catch (e) { ctorError = e.name; }
    return {subjectIsT: vt.subject === t, source: vt.source && vt.source.id, axis: vt.axis, ctorNoSubject: ctorError,
            rangeStart: range(va.rangeStart), rangeEnd: range(va.rangeEnd), rangeStartC: range(vc.rangeStart), rangeEndC: range(vc.rangeEnd)};
  });
  out.a08.points = [];
  for (const top of [0, 50, 100, 150, 200, 250, 300, 400]) {
    await tab.evaluate((top) => { document.getElementById('v').scrollTop = top; }, top);
    await frames(tab);
    out.a08.points.push(await tab.evaluate((top) => ({top, scrollTop: document.getElementById('v').scrollTop, current: num(vt.currentTime), inset: num(vi.currentTime), inset2: num(vi2.currentTime),
      start: num(vt.startOffset), end: num(vt.endOffset), insetStart: num(vi.startOffset), insetEnd: num(vi.endOffset), inset2Start: num(vi2.startOffset), inset2End: num(vi2.endOffset),
      anim: num(va.currentTime), animC: num(vc.currentTime), animCState: vc.playState}), top));
  }
  out.a08.setRange = await tab.evaluate(() => {
    va.rangeStart = 'cover 20%'; va.rangeEnd = {rangeName: 'cover', offset: CSS.percent(80)};
    const first = {rangeStart: range(va.rangeStart), rangeEnd: range(va.rangeEnd)};
    let bad = null; try { va.rangeStart = 'bogus 10%'; } catch (e) { bad = e.name; }
    return {...first, bad, afterBad: range(va.rangeStart)};
  });
} finally {
  await browser.close();
}
writeFileSync(process.argv[2] || 'C:/wk/waapi-tl-artifacts/red/chromium.json', JSON.stringify(out, null, 1) + '\n');
console.log(JSON.stringify(out));
