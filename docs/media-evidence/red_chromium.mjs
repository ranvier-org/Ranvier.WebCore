// G01 RED: Chromium 156 media features under CDP emulation. usage: node red_chromium.mjs <queries.json> <out.json>
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const queries = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const browser = await chromium.launch({channel: 'chromium', headless: true});
const out = {browser: browser.version(), states: {}};
const evaluate = tab => tab.evaluate(qs => Object.fromEntries(qs.map(q => { const l = matchMedia(q); return [q, [l.matches ? 1 : 0, l.media]]; })), queries);
for (const [label, options] of [['default', {}], ['hasTouch', {hasTouch: true}], ['isMobile', {hasTouch: true, isMobile: true}]]) {
  const context = await browser.newContext({viewport: {width: 320, height: 240}, ...options});
  const tab = await context.newPage();
  await tab.setContent('<!doctype html><body>x</body>');
  out.states[label] = await evaluate(tab);
  if (label === 'default') {
    const cdp = await context.newCDPSession(tab);
    await tab.evaluate(() => { window.log = []; for (const q of ['(prefers-color-scheme: dark)', '(prefers-reduced-motion: reduce)', '(prefers-contrast: more)', '(forced-colors: active)', '(min-width: 300px)', '(resolution: 2dppx)'])
      matchMedia(q).addEventListener('change', e => log.push([e.media, e.matches, e.constructor.name, e.target instanceof MediaQueryList])); });
    await cdp.send('Emulation.setEmulatedMedia', {features: [{name: 'prefers-color-scheme', value: 'dark'}, {name: 'prefers-reduced-motion', value: 'reduce'},
      {name: 'prefers-contrast', value: 'more'}, {name: 'forced-colors', value: 'active'}]});
    out.states.emulated = await evaluate(tab);
    await cdp.send('Emulation.setDeviceMetricsOverride', {width: 200, height: 400, deviceScaleFactor: 2, mobile: false});
    out.states.metrics200x400dpr2 = await evaluate(tab);
    await tab.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
    out.changeLog = await tab.evaluate(() => log);
  }
  await context.close();
}
await browser.close();
writeFileSync(process.argv[3], JSON.stringify(out, null, 1));
