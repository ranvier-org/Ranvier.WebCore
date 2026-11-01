// Chromium oracle for tests/abi/media_queries.py: writes tests/fixtures/media-queries-oracle.json. Replays every step of
// tests/fixtures/media-queries.json that has a Chromium equivalent through CDP: Emulation.setDeviceMetricsOverride for
// the viewport and scale, Emulation.setEmulatedMedia for prefers-color-scheme, prefers-reduced-motion and
// prefers-contrast, and Emulation.setTouchEmulationEnabled for a coarse pointer without hover. Records each list's
// matches, the change events fired since the previous step and the order of #t, each compared with the fixture.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const here = new URL('.', import.meta.url);
const fixture = JSON.parse(readFileSync(new URL('../fixtures/media-queries.json', here), 'utf8'));
const same = (left, right) => left.length === right.length && left.every((value, index) => value === right[index]);

const browser = await chromium.launch({channel: 'chromium', headless: true});
const result = {browser: browser.version(), headless: 'new (channel chromium)', steps: [],
  unsupported: {textScale: 'no web API or CDP emulation supplies a platform text scale', engineDefaults: 'Chromium always reports a pointing device'}};
try {
  const context = await browser.newContext({viewport: {width: 320, height: 240}});
  const tab = await context.newPage();
  await tab.setContent(fixture.page);
  const cdp = await context.newCDPSession(tab);
  await tab.evaluate(queries => {
    window.changes = [];
    window.lists = queries.map(query => {
      const list = matchMedia(query);
      list.addEventListener('change', event => changes.push({media: event.media, matches: event.matches, ownList: event.target === list}));
      return list;
    });
  }, fixture.queries);
  let previous = null;
  for (const step of fixture.steps.filter(s => s.chromium !== false)) {
    const p = step.preferences;
    await cdp.send('Emulation.setDeviceMetricsOverride', {width: step.viewport[0], height: step.viewport[1], deviceScaleFactor: step.scale, mobile: false});
    await cdp.send('Emulation.setEmulatedMedia', {features: [
      {name: 'prefers-color-scheme', value: p.colorScheme ?? ''}, {name: 'prefers-reduced-motion', value: p.reducedMotion ?? ''},
      {name: 'prefers-contrast', value: p.contrast ?? ''}]});
    await cdp.send('Emulation.setTouchEmulationEnabled', {enabled: p.pointer === 'coarse', maxTouchPoints: 5});
    await tab.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
    const state = await tab.evaluate(() => ({matches: lists.filter(l => l.matches).map(l => l.media), changes: changes.splice(0),
      order: Number(getComputedStyle(document.getElementById('t')).order)}));
    const expected = previous ? fixture.queries.filter(q => previous.matches.includes(q) !== step.matches.includes(q)) : [];
    const fired = state.changes.map(c => c.media);
    result.steps.push({name: step.name, matches: state.matches, changes: state.changes, order: state.order,
      matchesFixture: same([...state.matches].sort(), [...step.matches].sort()),
      changesFixture: same([...fired].sort(), [...expected].sort()) && state.changes.every(c => c.ownList && c.matches === step.matches.includes(c.media)),
      orderFixture: state.order === fixture.styleOrder[step.name]});
    previous = step;
  }
} finally {
  await browser.close();
}
writeFileSync(new URL('../fixtures/media-queries-oracle.json', here), JSON.stringify(result, null, 2) + '\n');
const failed = result.steps.filter(s => !(s.matchesFixture && s.changesFixture && s.orderFixture));
console.log(`Chromium ${result.browser}: ${result.steps.length - failed.length}/${result.steps.length} steps match the fixture`);
for (const s of failed) console.log('MISMATCH', s.name, JSON.stringify(s));
if (failed.length) process.exitCode = 1;
