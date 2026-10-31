// RED measurement of window.visualViewport in Chromium: writes red-chromium.json next to this file.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const page = '<!doctype html><style>html,body{margin:0}body{width:2000px;height:3000px}</style><body><iframe id=f style="width:100px;height:80px;border:0" srcdoc="<body style=margin:0>x"></iframe>';
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version(), page, viewport: [320, 240], steps: []};
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
      width: v.width, height: v.height, scale: v.scale, scrollX, scrollY, innerWidth, innerHeight,
      clientWidth: document.documentElement.clientWidth, clientHeight: document.documentElement.clientHeight, dpr: devicePixelRatio});
    window.log = [];
    v.addEventListener('resize', () => log.push({type: 'resize', ...state()}));
    v.addEventListener('scroll', () => log.push({type: 'scroll', ...state()}));
    window.addEventListener('resize', () => log.push({type: 'window-resize'}));
    window.addEventListener('scroll', () => log.push({type: 'window-scroll'}));
    window.handlerCalls = [];
    v.onresize = () => handlerCalls.push('onresize');
    v.onscroll = () => handlerCalls.push('onscroll');
  });
  const step = async (name, action) => {
    await tab.evaluate(() => { log.splice(0); handlerCalls.splice(0); });
    let error = null;
    try { await action(); } catch (e) { error = String(e.message || e).split('\n')[0]; }
    await settle();
    const r = await tab.evaluate(() => ({state: state(), log: log.splice(0), handlers: handlerCalls.splice(0),
      sub: (() => { const w = document.getElementById('f').contentWindow; const s = w.visualViewport; return {scale: s.scale, width: s.width, height: s.height, offsetLeft: s.offsetLeft, pageLeft: s.pageLeft}; })()}));
    out.steps.push({name, error, ...r});
  };
  await step('initial', async () => {});
  await step('scrollTo(10.5, 20.5)', () => tab.evaluate(() => scrollTo(10.5, 20.5)));
  await step('scrollTo(0, 0)', () => tab.evaluate(() => scrollTo(0, 0)));
  await step('resize 300x200', () => tab.setViewportSize({width: 300, height: 200}));
  await step('device scale 2', () => cdp.send('Emulation.setDeviceMetricsOverride', {width: 300, height: 200, deviceScaleFactor: 2, mobile: false}));
  await step('device scale 1.5', () => cdp.send('Emulation.setDeviceMetricsOverride', {width: 300, height: 200, deviceScaleFactor: 1.5, mobile: false}));
  await step('device scale 1', () => cdp.send('Emulation.setDeviceMetricsOverride', {width: 300, height: 200, deviceScaleFactor: 1, mobile: false}));
  await step('Emulation.setPageScaleFactor 2', () => cdp.send('Emulation.setPageScaleFactor', {pageScaleFactor: 2}));
  await step('scrollTo(100, 50) at page scale 2', () => tab.evaluate(() => scrollTo(100, 50)));
  await step('wheel 30,40 at page scale 2', () => tab.mouse.wheel(30, 40));
  await step('Emulation.setPageScaleFactor 1', () => cdp.send('Emulation.setPageScaleFactor', {pageScaleFactor: 1}));
  await step('scrollTo(0, 0) again', () => tab.evaluate(() => scrollTo(0, 0)));
  await step('pinch 2x at 150,100', () => cdp.send('Input.synthesizePinchGesture', {x: 150, y: 100, scaleFactor: 2, gestureSourceType: 'touch'}));
  await step('pinch 0.5x at 150,100', () => cdp.send('Input.synthesizePinchGesture', {x: 150, y: 100, scaleFactor: 0.5, gestureSourceType: 'touch'}));
  await step('setDeviceMetricsOverride viewport scale 2 (visible-area override)', () => cdp.send('Emulation.setDeviceMetricsOverride', {width: 300, height: 200, deviceScaleFactor: 1, mobile: false, viewport: {x: 20, y: 30, width: 150, height: 100, scale: 2}}));
  await step('clear override', () => cdp.send('Emulation.clearDeviceMetricsOverride'));
  await step('mobile metrics page scale 2', async () => { await tab.setViewportSize({width: 300, height: 200}); await cdp.send('Emulation.setDeviceMetricsOverride', {width: 300, height: 200, deviceScaleFactor: 1, mobile: true}); await cdp.send('Emulation.setPageScaleFactor', {pageScaleFactor: 2}); });
  await step('mobile scrollTo(40, 60)', () => tab.evaluate(() => scrollTo(40, 60)));
  await step('mobile pageScale 1', async () => { await cdp.send('Emulation.setPageScaleFactor', {pageScaleFactor: 1}); });
  await step('remove listeners and handlers, then resize', async () => { await tab.evaluate(() => { visualViewport.onresize = null; }); await cdp.send('Emulation.clearDeviceMetricsOverride'); await tab.setViewportSize({width: 280, height: 190}); });
  out.detached = await tab.evaluate(() => { const f = document.getElementById('f'); const w = f.contentWindow; const v = w.visualViewport; f.remove();
    return {width: v.width, height: v.height, scale: v.scale, offsetLeft: v.offsetLeft, pageTop: v.pageTop, windowVisualViewport: String(w.visualViewport)}; });
  out.handlerTypes = await tab.evaluate(() => ({onresize: typeof visualViewport.onresize, onscroll: typeof visualViewport.onscroll, proto: Object.getOwnPropertyNames(VisualViewport.prototype)}));
} finally { await browser.close(); }
writeFileSync(new URL('./red-chromium.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log('ok', out.browser, out.steps.length);
