// RED survey of Web Animations creation (A01) in Chromium: writes chromium.json next to this file.
// Every scenario pauses and seeks, so each value is deterministic (no frame timing enters a result).
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const page = `<!doctype html><style>html,body{margin:0;background:white}
.box{position:absolute;width:40px;height:40px;background:rgb(0,0,255)}
#a{left:0;top:0}#b{left:50px;top:0}#c{left:100px;top:0;transform:translateX(10px)}#d{left:0;top:50px}#e{left:50px;top:50px;opacity:0.5}</style>
<body><div id=a class=box></div><div id=b class=box></div><div id=c class=box></div><div id=d class=box></div><div id=e class=box></div>`;
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version(), scenarios: []};
try {
  const context = await browser.newContext({viewport: {width: 320, height: 240}, deviceScaleFactor: 1});
  const tab = await context.newPage();
  await tab.setContent(page);
  out.members = await tab.evaluate(() => ({
    animate: typeof Element.prototype.animate, KeyframeEffect: typeof KeyframeEffect, Animation: typeof Animation,
    DocumentTimeline: typeof DocumentTimeline, timeline: String(document.timeline)}));
  // Each scenario: create, pause, then seek to each time; record state + computed style at every point.
  const scenarios = [
    {name: 'opacity fill both', el: 'a', kind: 'animate', keyframes: [{opacity: 0}, {opacity: 1}], options: {duration: 1000, fill: 'both'}, times: [0, 500, 1000], props: ['opacity']},
    {name: 'opacity fill none', el: 'a', kind: 'animate', keyframes: [{opacity: 0}, {opacity: 0.5}], options: 1000, times: [0, 500, 1000], props: ['opacity']},
    {name: 'transform', el: 'b', kind: 'animate', keyframes: [{transform: 'translateX(0px)'}, {transform: 'translateX(100px)'}], options: {duration: 1000, fill: 'both'}, times: [0, 500, 1000], props: ['transform']},
    {name: 'delay no fill', el: 'a', kind: 'animate', keyframes: [{opacity: 0}, {opacity: 1}], options: {duration: 1000, delay: 500}, times: [0, 250, 500, 1000, 1500], props: ['opacity']},
    {name: 'delay fill backwards', el: 'a', kind: 'animate', keyframes: [{opacity: 0.2}, {opacity: 1}], options: {duration: 1000, delay: 500, fill: 'backwards'}, times: [0, 250, 1000], props: ['opacity']},
    {name: 'direction reverse', el: 'a', kind: 'animate', keyframes: [{opacity: 0}, {opacity: 1}], options: {duration: 1000, direction: 'reverse', fill: 'both'}, times: [0, 250, 1000], props: ['opacity']},
    {name: 'direction alternate x2', el: 'a', kind: 'animate', keyframes: [{opacity: 0}, {opacity: 1}], options: {duration: 1000, iterations: 2, direction: 'alternate', fill: 'both'}, times: [250, 1250, 2000], props: ['opacity']},
    {name: 'composite add transform', el: 'c', kind: 'animate', keyframes: [{transform: 'translateX(0px)'}, {transform: 'translateX(100px)'}], options: {duration: 1000, composite: 'add', fill: 'both'}, times: [0, 500, 1000], props: ['transform']},
    {name: 'composite accumulate transform', el: 'c', kind: 'animate', keyframes: [{transform: 'translateX(0px)'}, {transform: 'translateX(100px)'}], options: {duration: 1000, composite: 'accumulate', fill: 'both'}, times: [500], props: ['transform']},
    {name: 'composite replace transform', el: 'c', kind: 'animate', keyframes: [{transform: 'translateX(0px)'}, {transform: 'translateX(100px)'}], options: {duration: 1000, composite: 'replace', fill: 'both'}, times: [500], props: ['transform']},
    {name: 'keyframe composite add opacity', el: 'e', kind: 'animate', keyframes: [{opacity: 0, composite: 'add'}, {opacity: 0.25, composite: 'add'}], options: {duration: 1000, fill: 'both'}, times: [0, 500, 1000], props: ['opacity']},
    {name: 'offsets and easing', el: 'a', kind: 'animate', keyframes: [{opacity: 0}, {opacity: 0.8, offset: 0.8}, {opacity: 1}], options: {duration: 1000, fill: 'both'}, times: [400, 800, 900], props: ['opacity']},
    {name: 'keyframe easing step-end', el: 'a', kind: 'animate', keyframes: [{opacity: 0, easing: 'step-end'}, {opacity: 1}], options: {duration: 1000, fill: 'both'}, times: [500, 1000], props: ['opacity']},
    {name: 'two properties', el: 'd', kind: 'animate', keyframes: [{opacity: 0, transform: 'scale(1)'}, {opacity: 1, transform: 'scale(2)'}], options: {duration: 1000, fill: 'both', easing: 'linear', id: 'two'}, times: [500], props: ['opacity', 'transform']},
    {name: 'implicit from keyframe', el: 'e', kind: 'animate', keyframes: [{opacity: 1}], options: {duration: 1000, fill: 'both'}, times: [0, 500], props: ['opacity']},
    {name: 'KeyframeEffect + Animation(document.timeline)', el: 'b', kind: 'construct', keyframes: [{transform: 'translateX(0px)'}, {transform: 'translateX(40px)'}], options: {duration: 1000, fill: 'forwards'}, times: [500, 1000], props: ['transform']},
    {name: 'KeyframeEffect copy', el: 'b', kind: 'copy', keyframes: [{opacity: 0}, {opacity: 1}], options: {duration: 2000, fill: 'both'}, times: [500], props: ['opacity']},
    {name: 'number options', el: 'a', kind: 'animate', keyframes: [{opacity: 0}, {opacity: 1}], options: 2000, times: [500], props: ['opacity']},
  ];
  for (const s of scenarios) {
    const result = await tab.evaluate((s) => {
      const el = document.getElementById(s.el);
      let anim;
      if (s.kind === 'animate') anim = el.animate(s.keyframes, s.options);
      else if (s.kind === 'construct') anim = new Animation(new KeyframeEffect(el, s.keyframes, s.options), document.timeline);
      else anim = new Animation(new KeyframeEffect(new KeyframeEffect(el, s.keyframes, s.options)), document.timeline);
      anim.pause();
      const created = {id: anim.id, playState: anim.playState, pending: anim.pending, timelineIsDocument: anim.timeline === document.timeline,
        effectTargetId: anim.effect && anim.effect.target ? anim.effect.target.id : null, composite: anim.effect.composite,
        iterationComposite: anim.effect.iterationComposite, pseudoElement: anim.effect.pseudoElement};
      const points = s.times.map(t => {
        anim.currentTime = t;
        const cs = getComputedStyle(el);
        return {time: t, currentTime: anim.currentTime, playState: anim.playState, values: Object.fromEntries(s.props.map(p => [p, cs.getPropertyValue(p)]))};
      });
      window.__held = anim;
      return {created, points};
    }, s);
    // Rendered: seek to the midpoint and read the element's centre pixel.
    const mid = s.times[Math.floor(s.times.length / 2)];
    await tab.evaluate((t) => { window.__held.currentTime = t; }, mid);
    const box = await tab.evaluate((id) => { const r = document.getElementById(id).getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }, s.el);
    const shot = await tab.screenshot({clip: {x: 0, y: 0, width: 320, height: 240}});
    out.scenarios.push({name: s.name, keyframes: s.keyframes, options: s.options, ...result, renderedAt: mid, box, shot: shot.toString('base64')});
    await tab.evaluate(() => { window.__held.cancel(); });
  }
  out.errors = await tab.evaluate(() => {
    const el = document.getElementById('a');
    const attempt = (f) => { try { const a = f(); const r = {ok: true, playState: a && a.playState, keyframes: a && a.effect ? a.effect.getKeyframes().length : null}; if (a && a.cancel) a.cancel(); return r; } catch (e) { return {ok: false, name: e.name}; } };
    return {
      'unsorted offsets': attempt(() => el.animate([{opacity: 0, offset: 0.8}, {opacity: 1, offset: 0.2}], 1000)),
      'offset above one': attempt(() => el.animate([{opacity: 0, offset: 1.5}], 1000)),
      'invalid keyframe easing': attempt(() => el.animate([{opacity: 0, easing: 'bogus'}], 1000)),
      'invalid timing easing': attempt(() => el.animate([{opacity: 0}], {duration: 1000, easing: 'bogus'})),
      'negative duration': attempt(() => el.animate([{opacity: 0}], -1)),
      'NaN duration': attempt(() => el.animate([{opacity: 0}], NaN)),
      'negative iterations': attempt(() => el.animate([{opacity: 0}], {duration: 1, iterations: -1})),
      'null keyframes': attempt(() => el.animate(null, 1000)),
      'empty keyframes': attempt(() => el.animate([], 1000)),
      'unknown property ignored': attempt(() => el.animate([{bogusProperty: '1'}, {opacity: 1}], 1000)),
      'invalid value kept': attempt(() => el.animate([{opacity: 'red'}, {opacity: 1}], 1000)),
      'invalid pseudo': attempt(() => new KeyframeEffect(el, [], {pseudoElement: 'bogus'})),
      'KeyframeEffect null target': attempt(() => new Animation(new KeyframeEffect(null, [{opacity: 0}], 1000))),
      'Animation no effect': (() => { const a = new Animation(); return {playState: a.playState, effect: a.effect, timelineIsDocument: a.timeline === document.timeline, currentTime: a.currentTime}; })(),
      'Animation null timeline': (() => { const a = new Animation(new KeyframeEffect(el, [{opacity: 0}], 1000), null); a.play(); return {timeline: a.timeline, playState: a.playState, currentTime: a.currentTime}; })(),
    };
  });
} finally {
  await browser.close();
}
writeFileSync(new URL('./chromium.json', import.meta.url), JSON.stringify(out, null, 1));
console.log('scenarios', out.scenarios.length);
