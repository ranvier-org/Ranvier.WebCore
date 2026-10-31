// Chromium oracle for tests/abi/viewport_scroll.py: writes tests/fixtures/viewport-scroll-oracle.json.
// Records fractional viewport and element scroll positions, relative scrolls, options, clamping and the scroll and
// scrollend events of each step, at device scales 1, 1.5 and 2.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

export const page = '<!doctype html><style>html,body{margin:0}body{height:2000.5px;width:2000.25px}' +
  '#box{position:absolute;left:0;top:0;width:100px;height:100px;overflow:auto}#content{width:1000.25px;height:1000.5px}</style>' +
  '<body><div id="box"><div id="content"></div></div>';
// Each step: [name, scroller, operation]. The operation runs in the page with `s` bound to the scroller.
export const steps = [
  ['scrollTo(10.25, 20.5)', 'scrollTo', [10.25, 20.5]],
  ['scrollTo(10.75, 20.75)', 'scrollTo', [10.75, 20.75]],
  ['scrollTo(10.4, 20.4) from 10.75, 20.75', 'scrollTo', [10.4, 20.4]],
  ['scrollTo({left: 3.3, top: 7.7, behavior: instant})', 'scrollTo', [{left: 3.3, top: 7.7, behavior: 'instant'}]],
  ['scrollTo({top: 9.6}) keeps left', 'scrollTo', [{top: 9.6}]],
  ['scroll(5.5, 6.5)', 'scroll', [5.5, 6.5]],
  ['scrollBy(0.4, 0.4)', 'scrollBy', [0.4, 0.4]],
  ['scrollBy(0.4, 0.4) again', 'scrollBy', [0.4, 0.4]],
  ['scrollBy({top: 0.6})', 'scrollBy', [{top: 0.6}]],
  ['scrollBy(-0.3, -0.3)', 'scrollBy', [-0.3, -0.3]],
  ['scrollTo(-5.5, -5.5) clamps to 0', 'scrollTo', [-5.5, -5.5]],
  ['scrollTo(1e6, 1e6) clamps to the maximum', 'scrollTo', [1e6, 1e6]],
  ['scrollBy(-0.5, -0.5) from the maximum', 'scrollBy', [-0.5, -0.5]],
  ['scrollTop = 33.3, scrollLeft = 11.6', 'set', [11.6, 33.3]],
  ['scrollTo({left: 0.5, top: 50.5, behavior: smooth})', 'scrollTo', [{left: 0.5, top: 50.5, behavior: 'smooth'}]],
  ['scrollTo(0, 0)', 'scrollTo', [0, 0]],
];
const scales = [1, 1.5, 2];

if (import.meta.url === `file:///${process.argv[1].replaceAll('\\', '/')}`) {
  const browser = await chromium.launch({headless: true});
  const result = {browser: browser.version(), page, viewport: [320, 240], scales, cases: [], platformNotes: []};
  try {
    const context = await browser.newContext({viewport: {width: 320, height: 240}});
    const tab = await context.newPage();
    await tab.setContent(page);
    const cdp = await context.newCDPSession(tab);
    const frames = () => tab.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
    const settle = async () => { for (let i = 0; i < 4; i++) { await frames(); await new Promise(r => setTimeout(r, 150)); } };
    await tab.evaluate(() => {
      const box = document.getElementById('box');
      window.log = [];
      const state = () => ({scrollX, scrollY, pageXOffset, pageYOffset, documentLeft: document.documentElement.scrollLeft,
        documentTop: document.documentElement.scrollTop, boxLeft: box.scrollLeft, boxTop: box.scrollTop});
      window.state = state;
      for (const type of ['scroll', 'scrollend']) {
        window.addEventListener(type, event => log.push({listener: 'window', type, target: event.target === document ? 'document' : 'other', ...state()}));
        box.addEventListener(type, event => log.push({listener: 'box', type, target: event.target === box ? 'box' : 'other', ...state()}));
      }
    });
    for (const scale of scales) {
      await cdp.send('Emulation.setDeviceMetricsOverride', {width: 320, height: 240, deviceScaleFactor: scale, mobile: false});
      await settle();
      for (const scroller of ['viewport', 'box']) {
        await tab.evaluate(() => { scrollTo(0, 0); document.getElementById('box').scrollTo(0, 0); });
        await settle();
        await tab.evaluate(() => log.splice(0));
        const maximum = await tab.evaluate(scroller => {
          const s = scroller === 'box' ? document.getElementById('box') : document.documentElement;
          return {width: s.scrollWidth - s.clientWidth, height: s.scrollHeight - s.clientHeight};
        }, scroller);
        const record = {scale, scroller, devicePixelRatio: await tab.evaluate(() => devicePixelRatio), maximum, steps: []};
        for (const [name, operation, args] of steps) {
          await tab.evaluate(([scroller, operation, args]) => {
            const s = scroller === 'box' ? document.getElementById('box') : window;
            if (operation === 'set') {
              const element = scroller === 'box' ? s : document.documentElement;
              element.scrollTop = args[1];
              element.scrollLeft = args[0];
            } else s[operation](...args);
          }, [scroller, operation, args]);
          await settle();
          record.steps.push({name, operation, args, after: await tab.evaluate(() => state()), events: await tab.evaluate(() => log.splice(0))});
        }
        result.cases.push(record);
      }
    }
    result.platformNotes.push('Chromium stores fractional scroll offsets and snaps them to device pixels: at scale s a CSS offset is a multiple of 1/s.');
  } finally {
    await browser.close();
  }
  writeFileSync('tests/fixtures/viewport-scroll-oracle.json', JSON.stringify(result, null, 2) + '\n');
  for (const c of result.cases)
    console.log(c.scale, c.scroller, JSON.stringify(c.maximum), c.steps.map(s => s.name + ' => ' + (c.scroller === 'box' ? [s.after.boxLeft, s.after.boxTop] : [s.after.scrollX, s.after.scrollY]).join(',') + ' [' + s.events.map(e => e.listener + ':' + e.type).join(' ') + ']').join('\n  '));
}
