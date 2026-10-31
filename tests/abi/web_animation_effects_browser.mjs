// Chromium oracle for tests/abi/web_animation_effects.py (A02): writes tests/fixtures/web-animation-effects-oracle.json.
// One effect is read, retimed, rekeyed, retargeted and given invalid options; every read is from a paused animation.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

export const PAGE = '<!doctype html><html><head><style>html,body{margin:0;background:white}'
  + '.box{position:absolute;width:40px;height:40px;background:rgb(0,0,255)}#a{left:0;top:0}#b{left:50px;top:0}'
  + "#b::before{content:'';display:block;width:10px;height:10px;background:red}</style></head>"
  + '<body><div id=a class=box></div><div id=b class=box></div></body></html>';

const browser = await chromium.launch({headless: true});
const out = {browser: 'Chromium ' + browser.version()};
try {
  const tab = await (await browser.newContext({viewport: {width: 320, height: 240}, deviceScaleFactor: 1})).newPage();
  await tab.setContent(PAGE);
  out.steps = await tab.evaluate(() => {
    const steps = [];
    const record = (name, value) => steps.push({name, value});
    const timing = (t) => ({delay: t.delay, endDelay: t.endDelay, fill: t.fill, iterationStart: t.iterationStart, iterations: t.iterations,
      duration: t.duration, direction: t.direction, easing: t.easing});
    const computed = (t) => ({...timing(t), endTime: t.endTime, activeDuration: t.activeDuration, localTime: t.localTime,
      progress: t.progress, currentIteration: t.currentIteration});
    const keyframes = (list) => list.map((k) => {
      const props = Object.keys(k).filter((n) => !['offset', 'computedOffset', 'easing', 'composite'].includes(n)).sort().map((n) => [n, k[n]]);
      return {offset: k.offset, computedOffset: k.computedOffset, easing: k.easing, composite: k.composite, properties: props};
    });
    const attempt = (f) => { try { f(); return 'ok'; } catch (e) { return e.name; } };
    const a = document.getElementById('a'), b = document.getElementById('b');
    const anim = a.animate([{opacity: 0}, {opacity: 1, offset: 0.5, easing: 'ease-in'}, {opacity: 0.5}],
      {duration: 1000, delay: 100, endDelay: 50, iterations: 2, direction: 'alternate', fill: 'both', easing: 'linear', iterationStart: 0.25});
    anim.pause();
    const effect = anim.effect;
    record('timing', timing(effect.getTiming()));
    anim.currentTime = 600;
    record('computed at 600', computed(effect.getComputedTiming()));
    record('keyframes', keyframes(effect.getKeyframes()));
    effect.updateTiming({duration: 2000, delay: 0, iterations: 1, direction: 'normal', iterationStart: 0});
    record('timing after update', timing(effect.getTiming()));
    anim.currentTime = 500;
    record('computed after update', computed(effect.getComputedTiming()));
    record('opacity after update', getComputedStyle(a).opacity);
    effect.updateTiming({duration: 'auto'});
    record('auto duration', timing(effect.getTiming()));
    effect.updateTiming({duration: 2000, easing: 'ease-out', fill: 'forwards', endDelay: 0});
    record('timing after second update', timing(effect.getTiming()));
    effect.setKeyframes([{transform: 'translateX(0px)'}, {transform: 'translateX(100px)', composite: 'add'}]);
    record('keyframes after set', keyframes(effect.getKeyframes()));
    record('style after set', [getComputedStyle(a).opacity, getComputedStyle(a).transform]);
    effect.target = b;
    record('retarget', {target: effect.target.id, a: getComputedStyle(a).transform, b: getComputedStyle(b).transform});
    effect.pseudoElement = '::before';
    record('pseudo', {pseudoElement: effect.pseudoElement, target: effect.target.id});
    effect.pseudoElement = null;
    effect.composite = 'add';
    effect.iterationComposite = 'accumulate';
    record('composites', [effect.composite, effect.iterationComposite]);
    effect.composite = 'replace';
    effect.iterationComposite = 'replace';
    record('invalid', {
      'updateTiming negative duration': attempt(() => effect.updateTiming({duration: -1})),
      'updateTiming bad duration string': attempt(() => effect.updateTiming({duration: 'bogus'})),
      'updateTiming bad easing': attempt(() => effect.updateTiming({easing: 'bogus'})),
      'updateTiming negative iterations': attempt(() => effect.updateTiming({iterations: -1})),
      'updateTiming NaN iterations': attempt(() => effect.updateTiming({iterations: NaN})),
      'updateTiming negative iterationStart': attempt(() => effect.updateTiming({iterationStart: -1})),
      'setKeyframes unsorted': attempt(() => effect.setKeyframes([{opacity: 1, offset: 1}, {opacity: 0, offset: 0}])),
      'setKeyframes bad easing': attempt(() => effect.setKeyframes([{opacity: 1, easing: 'bogus'}])),
      'pseudoElement bogus': attempt(() => { effect.pseudoElement = 'bogus'; }),
    });
    effect.pseudoElement = null;
    record('timing after invalid', timing(effect.getTiming()));
    record('keyframes after invalid', keyframes(effect.getKeyframes()));
    b.remove();
    record('removed target', {target: effect.target.id, connected: effect.target.isConnected, progress: effect.getComputedTiming().progress});
    effect.target = null;
    record('null target', {target: effect.target, progress: effect.getComputedTiming().progress, keyframes: effect.getKeyframes().length});
    anim.cancel();
    record('cancelled', computed(effect.getComputedTiming()));
    return steps;
  });
} finally {
  await browser.close();
}
writeFileSync(process.env.ORACLE_OUT || new URL('../fixtures/web-animation-effects-oracle.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log('oracle: ' + out.steps.length + ' steps');
