// Chromium oracle for tests/abi/visual_viewport.py: writes tests/fixtures/visual-viewport-oracle.json.
// Records window.visualViewport and the ordered distinct visualViewport and window resize/scroll events of each step
// under viewport resizes, device scales, page scales (Emulation.setPageScaleFactor) and a wheel pan at page scale 2.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

export const page = '<!doctype html><style>html,body{margin:0}body{width:2000px;height:3000px}</style><body>';
// Each step: [name, operation, arguments]. Page scale origins are the scroll position the native host sets.
export const steps = [
  ['initial', 'none', []],
  ['scrollTo(10, 20)', 'scrollTo', [10, 20]],
  ['scrollTo(0, 0)', 'scrollTo', [0, 0]],
  ['resize 300x200', 'resize', [300, 200]],
  ['device scale 2', 'deviceScale', [2]],
  ['device scale 1', 'deviceScale', [1]],
  ['page scale 2 at 0,0', 'pageScale', [2, 0, 0]],
  ['page scale 1 at 0,0', 'pageScale', [1, 0, 0]],
  ['page scale 2 at 0,0 again', 'pageScale', [2, 0, 0]],
  ['scrollTo(100, 50) at page scale 2', 'scrollTo', [100, 50]],
  ['wheel 30, 40 at 150, 100 at page scale 2', 'wheel', [150, 100, 30, 40]],
  ['page scale 1 at 100,50', 'pageScale', [1, 100, 50]],
  ['scrollTo(0, 0) at page scale 1', 'scrollTo', [0, 0]],
  ['resize 320x240', 'resize', [320, 240]],
];

if (import.meta.url === `file:///${process.argv[1].replaceAll('\\', '/')}`) {
  const browser = await chromium.launch({headless: true});
  const result = {browser: browser.version(), page, viewport: [320, 240], steps: [], qualifiedBrowserOnly: {}};
  try {
    const context = await browser.newContext({viewport: {width: 320, height: 240}});
    const tab = await context.newPage();
    await tab.setContent(page);
    const cdp = await context.newCDPSession(tab);
    const frames = () => tab.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
    const settle = async () => { for (let i = 0; i < 4; i++) { await frames(); await new Promise(r => setTimeout(r, 100)); } };
    await tab.evaluate(() => {
      const v = visualViewport;
      window.state = () => ({offsetLeft: v.offsetLeft, offsetTop: v.offsetTop, pageLeft: v.pageLeft, pageTop: v.pageTop,
        width: v.width, height: v.height, scale: v.scale, scrollX, scrollY, innerWidth, innerHeight});
      window.log = [];
      for (const type of ['resize', 'scroll']) {
        v.addEventListener(type, () => log.push('visualViewport:' + type));
        window.addEventListener(type, event => { if (event.target === window || event.target === document) log.push('window:' + type); });
      }
    });
    let size = [320, 240], dpr = 1;
    const metrics = () => cdp.send('Emulation.setDeviceMetricsOverride', {width: size[0], height: size[1], deviceScaleFactor: dpr, mobile: false});
    await metrics();
    await settle();
    for (const [name, operation, args] of steps) {
      await settle();
      await tab.evaluate(() => log.splice(0));
      if (operation === 'scrollTo') await tab.evaluate(([x, y]) => scrollTo(x, y), args);
      else if (operation === 'resize') { size = args; await tab.setViewportSize({width: args[0], height: args[1]}); await metrics(); }
      else if (operation === 'deviceScale') { dpr = args[0]; await metrics(); }
      else if (operation === 'pageScale') await cdp.send('Emulation.setPageScaleFactor', {pageScaleFactor: args[0]});
      else if (operation === 'wheel') { await tab.mouse.move(args[0], args[1]); await tab.mouse.wheel(args[2], args[3]); }
      await settle();
      const observed = await tab.evaluate(() => ({state: state(), events: log.splice(0)}));
      result.steps.push({name, operation, args, state: observed.state, events: [...new Set(observed.events)]});
    }
    result.qualifiedBrowserOnly.onscrollend = await tab.evaluate(() => 'onscrollend' in VisualViewport.prototype);
    result.qualifiedBrowserOnly.detachedFrame = await tab.evaluate(async () => {
      const frame = document.createElement('iframe');
      document.body.append(frame);
      const v = frame.contentWindow.visualViewport;
      frame.remove();
      return {offsetLeft: v.offsetLeft, offsetTop: v.offsetTop, pageLeft: v.pageLeft, pageTop: v.pageTop, width: v.width, height: v.height, scale: v.scale};
    });
  } finally { await browser.close(); }
  writeFileSync(new URL('../fixtures/visual-viewport-oracle.json', import.meta.url), JSON.stringify(result, null, 1) + '\n');
  console.log('visual viewport oracle', result.browser, result.steps.length);
}
