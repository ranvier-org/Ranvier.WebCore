// RED survey of coordinate conversion in Chromium: writes red-chromium.json next to this file.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const page = '<!doctype html><style>html,body{margin:0}body{width:2000px;height:3000px}#b{position:absolute;left:0;top:40px;width:50px;height:50px}</style><body><div id=b></div>';
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version(), steps: []};
try {
  const context = await browser.newContext({viewport: {width: 320, height: 240}, deviceScaleFactor: 2});
  const tab = await context.newPage();
  await tab.setContent(page);
  const cdp = await context.newCDPSession(tab);
  out.members = await tab.evaluate(() => ({
    convertPointFromNode: 'convertPointFromNode' in Node.prototype, convertQuadFromNode: 'convertQuadFromNode' in Node.prototype,
    convertRectFromNode: 'convertRectFromNode' in Node.prototype, getBoxQuads: 'getBoxQuads' in Node.prototype,
    webkitConvertPointFromNodeToPage: 'webkitConvertPointFromNodeToPage' in window, DOMQuad: typeof DOMQuad, DOMMatrix: typeof DOMMatrix}));
  const state = () => tab.evaluate(() => { const r = b.getBoundingClientRect(), v = visualViewport;
    return {rect: [r.x, r.y], scroll: [scrollX, scrollY], vv: [v.offsetLeft, v.offsetTop, v.pageLeft, v.pageTop, v.width, v.height, v.scale], dpr: devicePixelRatio,
      hit: document.elementFromPoint(r.x + 25, r.y + 25)?.id ?? null}; });
  const down = (x, y) => tab.evaluate(() => new Promise(r => addEventListener('mousedown', e => r([e.clientX, e.clientY, e.target.id]), {once: true})))
  const step = async (name, act) => { await act(); await tab.waitForTimeout(150); out.steps.push({name, ...(await state())}); };
  await step('initial', async () => {});
  await step('scroll 10,20', () => tab.evaluate(() => scrollTo(10, 20)));
  await step('page scale 2', () => cdp.send('Emulation.setPageScaleFactor', {pageScaleFactor: 2}));
  await step('pan visual viewport 20,30', () => tab.evaluate(() => {}).then(() => cdp.send('Input.synthesizeScrollGesture', {x: 100, y: 100, xDistance: -40, yDistance: -60, speed: 4000})));
  const s = out.steps.at(-1);
  // Where Input.dispatchMouseEvent must land (CSS px of the widget) to hit #b's centre.
  const vx = (s.rect[0] + 25 - s.vv[0]) * s.vv[6], vy = (s.rect[1] + 25 - s.vv[1]) * s.vv[6];
  const p = down();
  await tab.mouse.move(vx, vy); await tab.mouse.down(); await tab.mouse.up();
  out.mouse = {at: [vx, vy], event: await p};
} finally { await browser.close(); }
writeFileSync(new URL('./red-chromium.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log(JSON.stringify(out, null, 1));
