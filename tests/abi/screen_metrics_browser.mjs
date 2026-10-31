// Chromium oracle for tests/abi/screen_metrics.py: writes tests/fixtures/screen-oracle.json. Each case drives the screen
// through CDP Emulation.setDeviceMetricsOverride and records what Screen and ScreenOrientation report. CDP sets no
// separate work area or depth, so each case's available area is the whole screen and its depth is 24.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const out = process.argv[2] || 'tests/fixtures/screen-oracle.json';
// type and angle pairs of the natural landscape orientation, as WebKit derives the angle.
const cases = {
  'landscape 1920x1080': {width: 1920, height: 1080, type: 'landscape-primary', cdp: 'landscapePrimary', angle: 0},
  'portrait 1080x1920': {width: 1080, height: 1920, type: 'portrait-primary', cdp: 'portraitPrimary', angle: 90},
  'landscape-secondary 2560x1440': {width: 2560, height: 1440, type: 'landscape-secondary', cdp: 'landscapeSecondary', angle: 180},
  'portrait-secondary 768x1024': {width: 768, height: 1024, type: 'portrait-secondary', cdp: 'portraitSecondary', angle: 270},
};
const browser = await chromium.launch({headless: true});
try {
  const context = await browser.newContext({viewport: {width: 320, height: 200}});
  const page = await context.newPage();
  await page.route('http://localhost/screen', route => route.fulfill({contentType: 'text/html', body: '<!doctype html><title>screen</title>'}));
  await page.goto('http://localhost/screen');
  const cdp = await context.newCDPSession(page);
  const result = {browser: browser.version(), headless: 'new', origin: 'http://localhost', cases: {}};
  for (const [label, entry] of Object.entries(cases)) {
    await cdp.send('Emulation.setDeviceMetricsOverride', {width: 320, height: 200, deviceScaleFactor: 1, mobile: false,
      screenWidth: entry.width, screenHeight: entry.height, screenOrientation: {type: entry.cdp, angle: entry.angle}});
    await page.evaluate(() => new Promise(r => requestAnimationFrame(() => setTimeout(r, 50))));
    const chromium = await page.evaluate(() => ({width: screen.width, height: screen.height, availLeft: screen.availLeft,
      availTop: screen.availTop, availWidth: screen.availWidth, availHeight: screen.availHeight, colorDepth: screen.colorDepth,
      pixelDepth: screen.pixelDepth, type: screen.orientation.type, angle: screen.orientation.angle,
      deviceWidth: matchMedia(`(device-width: ${screen.width}px)`).matches, deviceHeight: matchMedia(`(device-height: ${screen.height}px)`).matches}));
    result.cases[label] = {metrics: {width: entry.width, height: entry.height, availLeft: 0, availTop: 0, availWidth: entry.width,
      availHeight: entry.height, colorDepth: 24, type: entry.type}, chromium};
  }
  result.lock = await page.evaluate(async () => {
    try { await screen.orientation.lock('portrait'); return {resolved: true, type: screen.orientation.type}; }
    catch (e) { return {resolved: false, name: e.name}; }
  });
  writeFileSync(out, JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result, null, 1));
} finally {
  await browser.close();
}
