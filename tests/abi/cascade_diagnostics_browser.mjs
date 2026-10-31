// Chromium oracle for tests/abi/cascade_diagnostics.py: writes tests/fixtures/cascade-diagnostics-oracle.json.
// Loads tests/fixtures/cascade-diagnostics.html and records getComputedStyle for every case of
// tests/fixtures/cascade-diagnostics.json, each compared with the case's expected computed value. Browsers expose no
// cascade provenance to pages: the oracle records the contributing declarations, origins and winner as unsupported.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const here = new URL('.', import.meta.url);
export const page = readFileSync(new URL('../fixtures/cascade-diagnostics.html', here), 'utf8');
export const fixture = JSON.parse(readFileSync(new URL('../fixtures/cascade-diagnostics.json', here), 'utf8'));

// A number case matches a computed value whose leading number equals it; a keyword case matches the value exactly.
export function matches(expected, actual) {
  return typeof expected === 'number' ? parseFloat(actual) === expected : actual.trim() === expected;
}

// A case's element is an id path: a document id, then ids in the open shadow root of each element before.
export function computed(cases) {
  const resolve = path => path.split('/').reduce((node, id) => (node ? node.shadowRoot : document).getElementById(id), null);
  return cases.map(c => getComputedStyle(resolve(c.element)).getPropertyValue(c.property));
}

if (import.meta.url === `file:///${process.argv[1].replaceAll('\\', '/')}`) {
  const browser = await chromium.launch({channel: 'chromium', headless: true});
  const result = {browser: browser.version(), headless: 'new (channel chromium)', fixture: fixture.fixture, viewport: [320, 240], cases: [],
    unsupported: {cascade: 'no web API lists the declarations contributing to a property, their origin, layer or position, or the winner'}};
  try {
    const context = await browser.newContext({viewport: {width: 320, height: 240}});
    const tab = await context.newPage();
    await tab.setContent(page);
    // The data: URL import applies once loaded; #imported then takes its layer-one order.
    await tab.waitForFunction(() => document.styleSheets[0].cssRules[0].styleSheet?.cssRules.length === 1);
    await tab.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
    const values = await tab.evaluate(computed, fixture.cases);
    fixture.cases.forEach((c, i) => result.cases.push({name: c.name, element: c.element, property: c.property, expected: c.computed,
      computed: values[i], matchesFixture: matches(c.computed, values[i])}));
  } finally {
    await browser.close();
  }
  writeFileSync(new URL('../fixtures/cascade-diagnostics-oracle.json', here), JSON.stringify(result, null, 2) + '\n');
  const failed = result.cases.filter(c => !c.matchesFixture);
  console.log(`Chromium ${result.browser}: ${result.cases.length - failed.length}/${result.cases.length} cases match the fixture`);
  for (const c of failed) console.log('MISMATCH', c.name, JSON.stringify(c.expected), JSON.stringify(c.computed));
  if (failed.length) process.exitCode = 1;
}
