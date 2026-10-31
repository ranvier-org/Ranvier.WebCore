// Chromium oracle for tests/abi/custom_highlights.py: writes tests/fixtures/custom-highlights-oracle.json.
// Loads tests/fixtures/custom-highlights.html (pinned Ahem, 20px squares; text "X X X X X X X X") and records
// CSS.highlights (maplike) and Highlight (setlike) results in iteration order, iteration during mutation, and the
// colour sampled at the centre of each 20px cell of the first line after each paint step. Ranges name the cells
// they cover by text offset.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
import {inflateSync} from 'node:zlib';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const here = new URL('.', import.meta.url);
const font = readFileSync(process.env.RV_AHEM ?? 'C:/wk/src/Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf');
const page = readFileSync(new URL('../fixtures/custom-highlights.html', here), 'utf8').replace('{{FONT_BASE64}}', font.toString('base64'));
export const CELLS = 16;

function pixelOf(buffer) {
  let offset = 8, idat = [], colorType = 0;
  while (offset < buffer.length) {
    const length = buffer.readUInt32BE(offset), kind = buffer.toString('latin1', offset + 4, offset + 8);
    const data = buffer.subarray(offset + 8, offset + 8 + length);
    if (kind === 'IHDR') colorType = data[9];
    if (kind === 'IDAT') idat.push(data);
    offset += 12 + length;
  }
  const raw = inflateSync(Buffer.concat(idat));
  return [...raw.subarray(1, 4)];
}

// [step, script run in the page before sampling]. The native probe runs the same steps in the same order.
const steps = [
  ['base', () => {}],
  ['red', () => { window.rr = R(4, 11); window.red = new Highlight(rr); CSS.highlights.set('red', red); }],
  ['redThenGreen', () => { window.green = new Highlight(R(8, 15)); CSS.highlights.set('green', green); }],
  ['redPriority1', () => { red.priority = 1; }],
  ['redPriority0', () => { red.priority = 0; }],
  ['redSetAgain', () => { CSS.highlights.set('red', red); }],
  ['redReplaced', () => { window.red2 = new Highlight(rr); CSS.highlights.set('red', red2); }],
  ['redDeletedAndSet', () => { CSS.highlights.delete('red'); CSS.highlights.set('red', red2); }],
  ['greenDeleted', () => { CSS.highlights.delete('green'); }],
  ['liveRangeShrunk', () => { rr.setEnd(T(), 5); }],
  ['textInserted', () => { T().insertData(0, 'X '); }],
  ['staticAdded', () => { red2.add(new StaticRange({startContainer: T(), startOffset: 12, endContainer: T(), endOffset: 13})); }],
  ['rangeRemovedFromHighlight', () => { red2.delete(rr); }],
  ['unstyledOnly', () => { CSS.highlights.set('unstyled', new Highlight(rr)); CSS.highlights.delete('red'); }],
  ['cleared', () => { CSS.highlights.clear(); }],
];

const browser = await chromium.launch({headless: true});
const out = {browser: browser.version(), cells: CELLS, steps: steps.map(([name]) => name)};
try {
  const tab = await browser.newPage({viewport: {width: 320, height: 60}, deviceScaleFactor: 1});
  await tab.setContent(page);
  await tab.evaluate(() => document.fonts.ready);
  if (await tab.evaluate(() => document.getElementById('w').getBoundingClientRect().width) !== 160) throw new Error('Ahem not applied');
  await tab.evaluate(() => {
    window.T = () => document.getElementById('t').firstChild;
    window.R = (start, end) => { const r = new Range(); r.setStart(T(), start); r.setEnd(T(), end); return r; };
  });
  const frame = () => tab.evaluate(() => new Promise(r => requestAnimationFrame(() => setTimeout(r, 10))));
  const row = async () => {
    await frame();
    const cells = [];
    for (let i = 0; i < CELLS; i++) cells.push(pixelOf(await tab.screenshot({clip: {x: i * 20 + 10, y: 10, width: 1, height: 1}})));
    return cells;
  };

  out.api = await tab.evaluate(() => {
    const reg = CSS.highlights, log = {};
    const h1 = new Highlight(), h2 = new Highlight(R(0, 1)), h4 = new Highlight();
    const label = v => v === h1 ? 'h1' : v === h2 ? 'h2' : v === h4 ? 'h4' : '?';
    log['registry.empty'] = reg.size;
    reg.set('a', h1); reg.set('b', h2); reg.set('c', h1);
    log['registry.order'] = [[...reg.keys()], reg.size];
    reg.set('a', h4);
    log['registry.replace'] = [[...reg.keys()], label(reg.get('a')), reg.size];
    log['registry.delete'] = [reg.delete('b'), reg.delete('b'), [...reg.keys()], reg.has('b'), reg.get('zz') ?? null, reg.has('a')];
    reg.set('b', h2);
    log['registry.reinsert'] = [...reg.keys()];
    log['registry.entries'] = [...reg.entries()].map(([k, v]) => [k, label(v)]);
    log['registry.sameHighlightTwice'] = [label(reg.get('a')), label(reg.get('c')), reg.get('c') === reg.get('c')];
    // Live iteration while mutating, against a snapshot taken before.
    const snapshot = [...reg.keys()], seen = [];
    for (const [key] of reg) { seen.push(key); if (key === 'a') { reg.delete('c'); reg.set('d', h1); } }
    log['registry.iterationSnapshot'] = snapshot;
    log['registry.iterationLive'] = seen;
    log['registry.afterIteration'] = [...reg.keys()];
    reg.clear();
    log['registry.clear'] = [reg.size, [...reg.keys()], h2.size];

    const r1 = R(0, 1), r2 = R(2, 3), r3 = R(4, 5), r4 = R(8, 9);
    const s1 = new StaticRange({startContainer: T(), startOffset: 6, endContainer: T(), endOffset: 7});
    const name = r => r === r1 ? 'r1' : r === r2 ? 'r2' : r === r3 ? 'r3' : r === r4 ? 'r4' : r === s1 ? 's1' : '?';
    log['highlight.emptyConstructor'] = new Highlight().size;
    const h = new Highlight(r1, r2, r1);
    log['highlight.constructor'] = [h.size, [...h].map(name), h.priority, h.type];
    h.add(r3); h.add(r1);
    log['highlight.addKeepsPosition'] = [[...h].map(name), h.size];
    h.add(s1);
    log['highlight.addStatic'] = [...h].map(name);
    log['highlight.delete'] = [h.delete(r2), h.delete(r2), h.has(r2), h.has(r1), [...h].map(name)];
    const before = [...h].map(name), visited = [];
    for (const r of h) { visited.push(name(r)); if (r === r1) { h.delete(r3); h.add(r4); } }
    log['highlight.iterationSnapshot'] = before;
    log['highlight.iterationLive'] = visited;
    log['highlight.afterIteration'] = [...h].map(name);
    const priorities = []; for (const v of [5, -1, 2147483647, -2147483648, 0]) { h.priority = v; priorities.push(h.priority); }
    log['highlight.priority'] = priorities;
    const types = []; for (const v of ['spelling-error', 'grammar-error', 'highlight']) { h.type = v; types.push(h.type); }
    log['highlight.type'] = types;
    h.type = 'bogus';
    log['highlight.invalidType'] = h.type;
    h.clear();
    log['highlight.clear'] = [h.size, [...h].length];
    log['text'] = T().data;
    return log;
  });
  out.paint = {};
  for (const [name, script] of steps) {
    await tab.evaluate(script);
    out.paint[name] = await row();
  }
  out.textAfter = await tab.evaluate(() => [document.getElementById('t').textContent, document.getElementById('t').childNodes.length]);
} finally {
  await browser.close();
}
writeFileSync(new URL('../fixtures/custom-highlights-oracle.json', here), JSON.stringify(out, null, 1) + '\n');
console.log('custom highlights oracle: ' + Object.keys(out.api).length + ' API keys, ' + Object.keys(out.paint).length + ' paint steps, ' + out.browser);
