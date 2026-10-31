// Chromium oracle for tests/abi/viewport_events.py: writes tests/fixtures/viewport-events-oracle.json.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const sizes = [[320, 240], [333, 221]];
const scales = [1, 1.25, 1.5, 2, 0.75];
const browser = await chromium.launch({headless: true});
const result = {browser: browser.version(), metrics: [], steps: [], platformNotes: []};
try {
  const context = await browser.newContext({viewport: {width: 320, height: 240}});
  const page = await context.newPage();
  await page.setContent('<!doctype html><style>html,body{margin:0}body{height:2000px;width:2000px}</style><body>');
  const cdp = await context.newCDPSession(page);
  const frames = () => page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  const settle = async () => { for (let i = 0; i < 3; i++) { await frames(); await new Promise(r => setTimeout(r, 150)); } };
  const png = buffer => [buffer.readUInt32BE(16), buffer.readUInt32BE(20)];
  for (const [width, height] of sizes)
    for (const scale of scales) {
      await cdp.send('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: scale, mobile: false});
      await settle();
      const read = await page.evaluate(() => [innerWidth, innerHeight, devicePixelRatio]);
      const [paintWidth, paintHeight] = png(Buffer.from((await cdp.send('Page.captureScreenshot', {format: 'png'})).data, 'base64'));
      result.metrics.push({width, height, scale, innerWidth: read[0], innerHeight: read[1], devicePixelRatio: read[2], paintWidth, paintHeight});
    }
  await cdp.send('Emulation.setDeviceMetricsOverride', {width: 320, height: 240, deviceScaleFactor: 1, mobile: false});
  await settle();
  await page.evaluate(() => {
    window.log = [];
    const record = (source, event) => log.push({source, type: event.type, target: event.target === window ? 'window' : event.target === document ? 'document' : 'other',
      innerWidth, innerHeight, devicePixelRatio, scrollX, scrollY, visibilityState: document.visibilityState, hasFocus: document.hasFocus()});
    for (const type of ['resize', 'scroll', 'scrollend', 'visibilitychange', 'focus', 'blur']) window.addEventListener(type, event => record('window', event));
    const arm = () => {
      const query = window.armedQuery = matchMedia(`(resolution: ${devicePixelRatio}dppx)`);
      query.addEventListener('change', event => { record('media:' + query.media, event); arm(); }, {once: true});
    };
    arm();
  });
  const take = () => page.evaluate(() => log.splice(0));
  const step = async (name, action) => { await action(); await settle(); result.steps.push({name, events: await take(), after: await page.evaluate(() => ({devicePixelRatio, innerWidth, innerHeight, matchesOneDppx: matchMedia('(resolution: 1dppx)').matches}))}); };
  const {windowId} = await cdp.send('Browser.getWindowForTarget');
  await step('resize 400x300', () => cdp.send('Emulation.setDeviceMetricsOverride', {width: 400, height: 300, deviceScaleFactor: 1, mobile: false}));
  await step('scroll 0,100', () => page.evaluate(() => scrollTo(0, 100)));
  await step('scale 1.25', async () => { await cdp.send('Emulation.setDeviceMetricsOverride', {width: 400, height: 300, deviceScaleFactor: 1.25, mobile: false}); await new Promise(r => setTimeout(r, 1000)); });
  await step('resize 401x300 at 1.25', () => cdp.send('Emulation.setDeviceMetricsOverride', {width: 401, height: 300, deviceScaleFactor: 1.25, mobile: false}));
  await step('resize 401x301 and scale 1.5', () => cdp.send('Emulation.setDeviceMetricsOverride', {width: 401, height: 301, deviceScaleFactor: 1.5, mobile: false}));
  await cdp.send('Emulation.setFocusEmulationEnabled', {enabled: false});
  await step('blur', () => cdp.send('Browser.setWindowBounds', {windowId, bounds: {windowState: 'minimized'}}));
  await step('focus', () => cdp.send('Browser.setWindowBounds', {windowId, bounds: {windowState: 'normal'}}));
  result.platformNotes.push('Headless Chromium keeps visibilityState visible across window minimize, tab activation and lifecycle freeze; visibility is not driven here.');
  result.platformNotes.push('Chromium device-metrics emulation updates devicePixelRatio on a scale-only change but reports the resolution media query change only with the next viewport resize, after its resize event.');
} finally {
  await browser.close();
}
writeFileSync('tests/fixtures/viewport-events-oracle.json', JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify(result.steps.map(s => [s.name, s.events.map(e => e.source + ':' + e.type)])));
