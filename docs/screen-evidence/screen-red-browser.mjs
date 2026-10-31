// G04 RED: Chromium's Screen and ScreenOrientation, with and without CDP Emulation.setDeviceMetricsOverride.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const out = process.argv[2];
const browser = await chromium.launch({headless: true});
const read = page => page.evaluate(() => ({
  width: screen.width, height: screen.height, availWidth: screen.availWidth, availHeight: screen.availHeight,
  availLeft: screen.availLeft, availTop: screen.availTop, colorDepth: screen.colorDepth, pixelDepth: screen.pixelDepth,
  orientation: screen.orientation ? {type: screen.orientation.type, angle: screen.orientation.angle} : null,
  inner: [innerWidth, innerHeight], dpr: devicePixelRatio,
  deviceWidthQuery: matchMedia(`(device-width: ${screen.width}px)`).matches,
  orientationQuery: matchMedia('(orientation: portrait)').matches ? 'portrait' : 'landscape',
  screenIsExtended: screen.isExtended,
}));
try {
  const context = await browser.newContext({viewport: {width: 800, height: 600}});
  const page = await context.newPage();
  await page.route('http://localhost/screen', route => route.fulfill({contentType: 'text/html', body: '<!doctype html><title>screen</title>'}));
  await page.goto('http://localhost/screen');
  const result = {browser: browser.version(), headless: 'new'};
  result.default = await read(page);
  result.lock = await page.evaluate(async () => {
    try { await screen.orientation.lock('portrait'); return {ok: true}; }
    catch (e) { return {ok: false, name: e.name, message: e.message}; }
  });
  result.unlock = await page.evaluate(() => { try { screen.orientation.unlock(); return {ok: true}; } catch (e) { return {ok: false, name: e.name}; } });
  const cdp = await context.newCDPSession(page);
  await page.evaluate(() => {
    window.__events = [];
    screen.orientation.addEventListener('change', () => window.__events.push(['orientation', screen.orientation.type, screen.orientation.angle]));
    screen.addEventListener?.('change', () => window.__events.push(['screen', screen.width, screen.height]));
    addEventListener('resize', () => window.__events.push(['resize', innerWidth, innerHeight]));
  });
  await cdp.send('Emulation.setDeviceMetricsOverride', {width: 400, height: 700, deviceScaleFactor: 2, mobile: false,
    screenWidth: 1080, screenHeight: 1920, screenOrientation: {type: 'portraitPrimary', angle: 0}});
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => setTimeout(r, 50))));
  result.portraitOverride = await read(page);
  result.eventsAfterPortrait = await page.evaluate(() => window.__events.splice(0));
  await cdp.send('Emulation.setDeviceMetricsOverride', {width: 700, height: 400, deviceScaleFactor: 1, mobile: false,
    screenWidth: 1920, screenHeight: 1080, screenOrientation: {type: 'landscapeSecondary', angle: 270}});
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => setTimeout(r, 50))));
  result.landscapeOverride = await read(page);
  result.eventsAfterLandscape = await page.evaluate(() => window.__events.splice(0));
  await cdp.send('Emulation.setDeviceMetricsOverride', {width: 700, height: 400, deviceScaleFactor: 1, mobile: true,
    screenWidth: 1920, screenHeight: 1080, screenOrientation: {type: 'landscapePrimary', angle: 90}});
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => setTimeout(r, 50))));
  result.mobileOverride = await read(page);
  result.mobileLock = await page.evaluate(async () => {
    try { await screen.orientation.lock('portrait'); return {ok: true, type: screen.orientation.type}; }
    catch (e) { return {ok: false, name: e.name, message: e.message}; }
  });
  result.eventsAfterMobile = await page.evaluate(() => window.__events.splice(0));
  await cdp.send('Emulation.clearDeviceMetricsOverride');
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => setTimeout(r, 50))));
  result.cleared = await read(page);
  result.eventsAfterClear = await page.evaluate(() => window.__events.splice(0));
  writeFileSync(out, JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result, null, 1));
} finally {
  await browser.close();
}
