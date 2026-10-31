// Chromium oracle for tests/abi/web_animation_discovery.py (A05): writes tests/fixtures/web-animation-discovery-oracle.json.
// Document, element and subtree getAnimations over a CSS animation, a CSS transition and script animations, with each
// animation's interface, id, CSS metadata, target, timeline and effect; identity across the lists; and cancellation.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

export const PAGE = '<!doctype html><html><head><style>html,body{margin:0}.box{position:absolute;width:40px;height:40px}'
  + '@keyframes fade{from{opacity:0}to{opacity:1}}@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(90deg)}}'
  + '#css{left:0;top:0;animation:fade 100s linear}#tr{left:50px;top:0;transition:opacity 100s linear}'
  + '#tree{position:absolute;left:100px;top:0}#c2{animation:spin 100s linear}</style></head><body>'
  + '<div id=css class=box></div><div id=tr class=box></div>'
  + '<div id=tree><div id=c1 class=box></div><div id=c2 class=box></div></div></body></html>';

const browser = await chromium.launch({headless: true});
const out = {browser: 'Chromium ' + browser.version()};
try {
  const tab = await (await browser.newContext({viewport: {width: 320, height: 240}, deviceScaleFactor: 1})).newPage();
  await tab.setContent(PAGE);
  out.steps = await tab.evaluate(() => {
    const steps = [];
    const record = (name, value) => steps.push({name, value});
    const describe = (x) => ({type: x.constructor.name, id: x.id, animationName: x.animationName ?? null,
      transitionProperty: x.transitionProperty ?? null, target: x.effect && x.effect.target ? x.effect.target.id : null,
      timelineIsDocument: x.timeline === document.timeline, keyframeEffect: x.effect instanceof KeyframeEffect});
    const tr = document.getElementById('tr'), tree = document.getElementById('tree');
    const c1 = document.getElementById('c1'), c2 = document.getElementById('c2'), css = document.getElementById('css');
    getComputedStyle(tr).opacity;
    tr.style.opacity = '0.2';
    const scripted = c1.animate([{opacity: 0}, {opacity: 1}], {duration: 100000, id: 'scripted'});
    const second = css.animate([{transform: 'translateX(0px)'}, {transform: 'translateX(10px)'}], {duration: 100000, id: 'second'});
    const all = document.getAnimations();
    record('document', all.map(describe));
    record('tree', tree.getAnimations().map(describe));
    record('tree subtree', tree.getAnimations({subtree: true}).map(describe));
    record('css element', css.getAnimations().map(describe));
    record('transition element', tr.getAnimations().map(describe));
    record('identity', {
      documentAgain: document.getAnimations().every((x, i) => x === all[i]),
      elementInDocument: c2.getAnimations()[0] === all.find((x) => x.effect.target === c2),
      scriptedInDocument: all.includes(scripted), subtreeInDocument: tree.getAnimations({subtree: true}).every((x) => all.includes(x)),
      effectsDistinct: new Set(all.map((x) => x.effect)).size === all.length});
    const cssAnimation = css.getAnimations().find((x) => x.animationName === 'fade');
    cssAnimation.cancel();
    record('css cancelled', {playState: cssAnimation.playState, remaining: css.getAnimations().map(describe)});
    scripted.cancel();
    record('scripted cancelled', {playState: scripted.playState, tree: tree.getAnimations({subtree: true}).map(describe),
      document: document.getAnimations().length});
    tr.getAnimations()[0].cancel();
    second.cancel();
    record('after all cancelled', document.getAnimations().map(describe));
    return steps;
  });
} finally {
  await browser.close();
}
writeFileSync(process.env.ORACLE_OUT || new URL('../fixtures/web-animation-discovery-oracle.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log('oracle: ' + out.steps.length + ' steps');
