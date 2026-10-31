// Chromium oracle for tests/abi/animation_timelines.py: writes tests/fixtures/animation-timelines-oracle.json.
// A06: document timeline time origins, inactive timelines, start-time synchronization, teardown and the frame-rate gates.
// A07: scroll timeline axes, sources and progress at scroll positions, animations on them, a resize and a removed source.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const spec = JSON.parse(readFileSync(new URL('../fixtures/animation-timelines-cases.json', import.meta.url), 'utf8'));
const frames = (tab) => tab.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));

// A07: scroll timelines over #s (300 px of block and 200 px of inline scroll), the nested #n, the root scroller, an
// unscrollable #vis, a null source and the default source; animations on two of them; a resize; the source removed.
async function a07(tab) {
  await tab.setContent(spec.scrollMarkup);
  await tab.evaluate(() => {
    window.unit = (v) => v === null ? null : typeof v === 'number' ? {number: v} : {value: v.value, unit: v.unit};
    const s = document.getElementById('s');
    window.tl = {block: new ScrollTimeline({source: s}), inline: new ScrollTimeline({source: s, axis: 'inline'}),
      x: new ScrollTimeline({source: s, axis: 'x'}), y: new ScrollTimeline({source: s, axis: 'y'}), def: new ScrollTimeline(),
      nullSource: new ScrollTimeline({source: null}), visible: new ScrollTimeline({source: document.getElementById('vis')}),
      nested: new ScrollTimeline({source: document.getElementById('n')})};
    window.sa = document.getElementById('a').animate([{opacity: 0}, {opacity: 1}], {timeline: tl.block, fill: 'both'});
    window.sb = new Animation(new KeyframeEffect(document.getElementById('b'), [{opacity: 0}, {opacity: 1}], {fill: 'both'}), tl.inline);
    sb.play();
  });
  const frames = () => tab.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  await frames();
  const read = () => tab.evaluate(() => {
    const times = Object.fromEntries(Object.entries(tl).map(([k, v]) => [k, unit(v.currentTime)]));
    const opacity = (id) => getComputedStyle(document.getElementById(id)).opacity;
    return {times, a: {currentTime: unit(sa.currentTime), startTime: unit(sa.startTime), playState: sa.playState, opacity: opacity('a')},
      b: {currentTime: unit(sb.currentTime), playState: sb.playState, opacity: opacity('b')}};
  });
  const result = await tab.evaluate(() => {
    const s = document.getElementById('s');
    return {axes: ['block', 'inline', 'x', 'y'].map((k) => tl[k].axis), source: tl.block.source === s, nestedSource: tl.nested.source.id,
      defaultSource: tl.def.source === document.scrollingElement, nullSource: tl.nullSource.source, visibleSource: tl.visible.source.id,
      duration: unit(tl.block.duration), nullDuration: unit(tl.nullSource.duration), interfaceName: tl.block.constructor.name,
      animationTimeline: sa.timeline === tl.block};
  });
  result.points = [];
  for (const point of spec.a07.points) {
    await tab.evaluate((p) => {
      const s = document.getElementById('s');
      s.scrollTop = p.top; s.scrollLeft = p.left; document.getElementById('n').scrollTop = p.nested; window.scrollTo(0, p.root);
    }, point);
    await frames();
    result.points.push({...point, ...await read()});
  }
  await tab.evaluate((height) => { document.getElementById('c').style.height = height; }, spec.a07.resizedHeight);
  await frames();
  result.resized = {scrollTop: await tab.evaluate(() => document.getElementById('s').scrollTop), ...await read()};
  await tab.evaluate(() => document.getElementById('s').remove());
  await frames();
  result.removed = await read();
  await tab.evaluate(() => { for (const id of ['a', 'b']) document.getElementById(id).setAttribute('style', 'color:red'); });
  await frames();
  result.restyled = await tab.evaluate(() => ({a: getComputedStyle(document.getElementById('a')).opacity,
    b: getComputedStyle(document.getElementById('b')).opacity}));
  return result;
}

const browser = await chromium.launch({headless: true});
const out = {browser: 'Chromium ' + browser.version()};
try {
  const context = await browser.newContext({viewport: {width: 320, height: 240}, deviceScaleFactor: 1});
  const tab = await context.newPage();
  await tab.setContent(spec.markup);
  const a06 = await tab.evaluate((spec) => {
    const dt = document.timeline;
    const made = Object.fromEntries(spec.a06.origins.map((o) => [String(o), new DocumentTimeline({originTime: o})]));
    const dflt = new DocumentTimeline();
    const t = dt.currentTime;
    const detached = document.implementation.createHTMLDocument('');
    const anim = new Animation(new KeyframeEffect(null, [{opacity: 0}, {opacity: 1}], spec.a06.duration), detached.timeline);
    anim.play();
    const result = {
      documentTimeline: {interfaceName: dt.constructor.name, currentTimeIsNumber: typeof t === 'number', duration: dt.duration},
      // Times are doubles: an offset holds to within a microsecond; the sign of a small origin depends on the page's age.
      origins: spec.a06.origins.map((o) => ({origin: o, offsetClose: Math.abs(made[String(o)].currentTime - (t - o)) < 1e-6,
        duration: made[String(o)].duration, interfaceName: made[String(o)].constructor.name, distinct: made[String(o)] !== dt})),
      futureNegative: made[String(spec.a06.futureOrigin)].currentTime < 0,
      defaultEqual: dflt.currentTime === t,
      inactive: {currentTime: detached.timeline.currentTime, duration: detached.timeline.duration, identity: detached.timeline === detached.timeline,
        animation: {playState: anim.playState, currentTime: anim.currentTime, startTime: anim.startTime}},
      gates: {maximumFrameRate: 'maximumFrameRate' in DocumentTimeline.prototype, frameRate: 'frameRate' in Animation.prototype},
    };
    anim.cancel();
    const el = document.getElementById('a');
    window.own = new DocumentTimeline({originTime: spec.a06.syncOrigin});
    window.a1 = el.animate([{opacity: 0}, {opacity: 1}], spec.a06.duration);
    window.a2 = el.animate([{opacity: 0}, {opacity: 1}], spec.a06.duration);
    window.a3 = new Animation(new KeyframeEffect(el, [{opacity: 0}, {opacity: 1}], spec.a06.duration), own);
    a3.play();
    result.beforeFrame = {pending: [a1.pending, a3.pending], startTime: [a1.startTime, a3.startTime]};
    return result;
  }, spec);
  await frames(tab);
  a06.synchronized = await tab.evaluate((spec) => {
    const r = {sameStart: a1.startTime === a2.startTime, ownStartOffsetClose: Math.abs(a1.startTime - a3.startTime - spec.a06.syncOrigin) < 1e-6,
      currentClose: Math.abs(a1.currentTime - a3.currentTime) < 1e-6, started: a1.startTime !== null && a3.startTime !== null,
      playState: [a1.playState, a2.playState, a3.playState], pending: [a1.pending, a3.pending]};
    a1.cancel(); a2.cancel(); a3.cancel();
    return r;
  }, spec);
  a06.teardown = await tab.evaluate(async () => {
    const f = document.createElement('iframe');
    document.body.appendChild(f);
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    const tl = f.contentDocument.timeline, own = new f.contentWindow.DocumentTimeline({originTime: 100});
    const before = typeof tl.currentTime === 'number';
    f.remove();
    return {before, timeline: tl.currentTime, own: own.currentTime};
  });
  out.a06 = a06;
  out.a07 = await a07(await context.newPage());
} finally {
  await browser.close();
}
writeFileSync(process.env.ORACLE_OUT || new URL('../fixtures/animation-timelines-oracle.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log('oracle: ' + out.browser);
