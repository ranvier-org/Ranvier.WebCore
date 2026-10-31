// Chromium oracle for tests/abi/web_animation_commit.py (A04): writes tests/fixtures/web-animation-commit-oracle.json.
// Each case seeks a paused animation to its midpoint, commits its styles, cancels it, and records the style attribute,
// the inline values and priorities and the computed values; the error cases record the exception name.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

export const PAGE = '<!doctype html><html><head><style>html,body{margin:0}.box{position:absolute;width:40px;height:40px}'
  + '#hidden{display:none}</style></head><body>'
  + '<div id=a class=box style="color: rgb(1, 2, 3) !important; margin-top: 0px"></div>'
  + '<div id=b class=box style="opacity: 0.2 !important"></div>'
  + '<div id=c class=box></div><div id=hidden class=box></div></body></html>';

export const CASES = [
  {name: 'opacity and transform', el: 'a', keyframes: [{opacity: '0', transform: 'translateX(0px)'}, {opacity: '1', transform: 'translateX(100px)'}],
    props: ['opacity', 'transform', 'color', 'margin-top']},
  {name: 'over an important inline value', el: 'b', keyframes: [{opacity: '0'}, {opacity: '1'}], props: ['opacity']},
  {name: 'composite add over a stylesheet value', el: 'c', keyframes: [{marginLeft: '0px', composite: 'add'}, {marginLeft: '10px', composite: 'add'}], props: ['margin-left']},
];

const browser = await chromium.launch({headless: true});
const out = {browser: 'Chromium ' + browser.version()};
try {
  const tab = await (await browser.newContext({viewport: {width: 320, height: 240}, deviceScaleFactor: 1})).newPage();
  await tab.setContent(PAGE);
  out.cases = await tab.evaluate((cases) => cases.map((c) => {
    const el = document.getElementById(c.el);
    const anim = el.animate(c.keyframes, 1000);
    anim.pause();
    anim.currentTime = 500;
    anim.commitStyles();
    const committed = el.getAttribute('style');
    anim.cancel();
    const cs = getComputedStyle(el);
    return {name: c.name, committed, afterCancel: el.getAttribute('style'),
      inline: Object.fromEntries(c.props.map((p) => [p, [el.style.getPropertyValue(p), el.style.getPropertyPriority(p)]])),
      computed: Object.fromEntries(c.props.map((p) => [p, cs.getPropertyValue(p)])), playState: anim.playState};
  }), CASES);
  out.errors = await tab.evaluate(() => {
    const attempt = (f) => { try { f(); return 'ok'; } catch (e) { return e.name; } };
    const detached = document.createElement('div');
    const hidden = document.getElementById('hidden');
    const c = document.getElementById('c');
    return {
      'detached element': attempt(() => detached.animate([{opacity: 0}, {opacity: 1}], 1000).commitStyles()),
      'element not rendered': attempt(() => hidden.animate([{opacity: 0}, {opacity: 1}], 1000).commitStyles()),
      'no target': attempt(() => new Animation(new KeyframeEffect(null, [{opacity: 0}], 1000)).commitStyles()),
      'pseudo-element target': attempt(() => c.animate([{opacity: 0}, {opacity: 1}], {duration: 1000, pseudoElement: '::before'}).commitStyles()),
      'no effect': attempt(() => new Animation().commitStyles()),
    };
  });
} finally {
  await browser.close();
}
writeFileSync(process.env.ORACLE_OUT || new URL('../fixtures/web-animation-commit-oracle.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log('oracle: ' + out.cases.length + ' cases');
