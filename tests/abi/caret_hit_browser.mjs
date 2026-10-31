// Chromium oracle for tests/abi/caret_hit.py: writes tests/fixtures/caret-hit-oracle.json.
// Hit-tests tests/fixtures/caret-hit.html (pinned Ahem, 20px squares) with caretPositionFromPoint and caretRangeFromPoint
// over wrapped text, inline boundaries, bidi runs, shadow roots, a text control, empty and outside-content points,
// non-finite coordinates, and scrolled viewports, at device scales 1, 1.5 and 2.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const here = new URL('.', import.meta.url);
const font = readFileSync(process.env.RV_AHEM ?? 'C:/wk/src/Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf');
const template = readFileSync(new URL('../fixtures/caret-hit.html', here), 'utf8');
export const page = template.replace('{{FONT_BASE64}}', font.toString('base64'));

// [name, x, y]; a string coordinate is a non-finite number.
export const points = [
  ['wrap line 1 glyph 0 left half', 5, 10], ['wrap line 1 glyph 0 right half', 15, 10], ['wrap line 1 glyph 1 boundary', 20, 10],
  ['wrap line 1 last glyph right half', 75, 10], ['wrap line 1 past end inside box', 90, 10], ['wrap line 1 past box', 150, 10],
  ['wrap line 2 start', 2, 30], ['wrap line 2 middle', 45, 30], ['wrap line 3 end', 79, 50], ['wrap below last line', 10, 65],
  ['wrap fractional 10.5, 10.25', 10.5, 10.25], ['wrap fractional 9.99', 9.99, 10], ['wrap fractional 10.01', 10.01, 10],
  ['inline AA|BB left', 39, 90], ['inline AA|BB right', 41, 90], ['inline BB|CC', 81, 90], ['inline CC|DD', 119, 90], ['inline end', 159, 90],
  ['bidi ltr before bdo', 35, 120], ['bidi bdo visual left', 45, 120], ['bidi bdo visual middle', 80, 120], ['bidi bdo visual right', 115, 120],
  ['bidi after bdo', 125, 120], ['rtl line 1 right edge', 295, 150], ['rtl line 1 left edge', 225, 150], ['rtl line 2 middle', 250, 170],
  ['rtl left of line 1', 190, 150],
  ['open shadow text', 25, 200], ['closed shadow text', 225, 200], ['text control', 25, 230],
  ['empty box', 220, 20], ['body beside text control', 150, 235], ['negative x', -5, 10], ['negative y', 10, -5],
  ['past viewport x', 400, 10], ['past viewport y', 10, 260], ['viewport last pixel', 319, 239], ['huge', 1e9, 1e9],
  ['NaN x', 'NaN', 10], ['Infinity y', 10, 'Infinity'], ['-Infinity x', '-Infinity', 10],
];
// [name, scrollX, scrollY]; every point above is replayed after each scroll. A runtime checks a scroll against the case
// whose actual offset equals its own: 'scrolled 0, 20' is the native engine's truncation of 'scrolled 0.5, 20.5'.
export const scrolls = [['unscrolled', 0, 0], ['scrolled 50, 590', 50, 590], ['scrolled 0.5, 20.5', 0.5, 20.5], ['scrolled 0, 20', 0, 20]];
export const scales = [1, 1.5, 2];

export function inPage() {
  // Runs in the page: describes nodes by stable paths so the native probe can name the same nodes.
  const describe = n => {
    if (!n) return null;
    const root = n.getRootNode();
    const scope = root === document ? 'document' : root === window.openRoot ? 'open' : root === window.closedRoot ? 'closed' : root.nodeName;
    if (n.nodeType === 3) {
      const p = n.parentNode;
      return {kind: 'text', parent: p.id || p.nodeName, index: [...p.childNodes].indexOf(n), scope};
    }
    return {kind: n.nodeType === 1 ? 'element' : n.nodeName, id: n.id || null, name: n.nodeName, scope};
  };
  const rect = r => r && {x: r.x, y: r.y, width: r.width, height: r.height};
  const number = v => typeof v === 'string' ? Number(v) : v;
  window.hit = ([x, y]) => {
    const one = options => {
      try {
        const c = options ? document.caretPositionFromPoint(number(x), number(y), options) : document.caretPositionFromPoint(number(x), number(y));
        return c && {node: describe(c.offsetNode), offset: c.offset, rect: rect(c.getClientRect())};
      } catch (e) { return {error: e.name}; }
    };
    let range;
    try {
      const r = document.caretRangeFromPoint(number(x), number(y));
      range = r && {node: describe(r.startContainer), offset: r.startOffset, collapsed: r.collapsed};
    } catch (e) { range = {error: e.name}; }
    return {position: one(), shadowRoots: one({shadowRoots: [window.openRoot, window.closedRoot]}), range};
  };
  window.openRoot = document.getElementById('host').attachShadow({mode: 'open'});
  window.openRoot.innerHTML = '<span id="s">SSSS</span>';
  window.closedRoot = document.getElementById('closed').attachShadow({mode: 'closed'});
  window.closedRoot.innerHTML = '<span id="t">TTTT</span>';
}

if (import.meta.url === `file:///${process.argv[1].replaceAll('\\', '/')}`) {
  const browser = await chromium.launch({channel: 'chromium', headless: true});
  const result = {browser: browser.version(), headless: 'new (channel chromium)', fixture: 'tests/fixtures/caret-hit.html',
    fontSha256: createHash('sha256').update(font).digest('hex'), viewport: [320, 240], scales, points, scrolls, cases: [], lifetime: [], platformNotes: []};
  try {
    const context = await browser.newContext({viewport: {width: 320, height: 240}});
    const tab = await context.newPage();
    const cdp = await context.newCDPSession(tab);
    const frames = () => tab.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
    for (const scale of scales) {
      await cdp.send('Emulation.setDeviceMetricsOverride', {width: 320, height: 240, deviceScaleFactor: scale, mobile: false});
      await tab.setContent(page);
      await tab.evaluate(inPage);
      await tab.evaluate(() => document.fonts.ready);
      await frames();
      const ready = await tab.evaluate(() => document.getElementById('wrap').firstChild.length && document.getElementById('inline').getBoundingClientRect().width);
      if (ready !== 160) throw new Error('Ahem not applied: inline width ' + ready);
      for (const [scrollName, sx, sy] of scrolls) {
        await tab.evaluate(([sx, sy]) => scrollTo(sx, sy), [sx, sy]);
        await frames();
        const record = {scale, scroll: scrollName, devicePixelRatio: await tab.evaluate(() => devicePixelRatio),
          scrollX: await tab.evaluate(() => scrollX), scrollY: await tab.evaluate(() => scrollY), hits: []};
        for (const [name, x, y] of points)
          record.hits.push({name, x, y, ...(await tab.evaluate(p => window.hit(p), [x, y]))});
        result.cases.push(record);
      }
      await tab.evaluate(() => scrollTo(0, 0));
      // Lifetime: a CaretPosition held past its node's removal and past a text change.
      result.lifetime.push({scale, ...(await tab.evaluate(() => {
        const read = c => ({offset: c.offset, connected: c.offsetNode.isConnected, data: c.offsetNode.data,
          rect: (r => r && {x: r.x, y: r.y, width: r.width, height: r.height})(c.getClientRect())});
        const held = document.caretPositionFromPoint(45, 30);
        const before = read(held);
        const wrap = document.getElementById('wrap');
        wrap.firstChild.data = 'AA';
        const shortened = read(held);
        wrap.remove();
        const removed = read(held);
        const detached = document.implementation.createHTMLDocument('');
        detached.body.textContent = 'AAAA';
        const inert = detached.caretPositionFromPoint(5, 10);
        return {before, shortened, removed, detachedDocument: inert === null ? null : 'nonnull'};
      }))});
    }
    result.platformNotes.push('Chromium keeps fractional scroll offsets snapped to device pixels, so a 0.5 scroll moves the content by 0.5 CSS px at scale 2.');
  } finally {
    await browser.close();
  }
  writeFileSync(new URL('../fixtures/caret-hit-oracle.json', here), JSON.stringify(result, null, 2) + '\n');
  for (const c of result.cases) {
    console.log('scale', c.scale, c.scroll, 'scroll', c.scrollX, c.scrollY);
    for (const h of c.hits) {
      const p = h.position, s = h.shadowRoots, r = h.range;
      const f = v => !v ? 'null' : v.error ? 'throws ' + v.error : `${v.node.kind === 'text' ? v.node.parent + '#' + v.node.index : v.node.name + (v.node.id ? '#' + v.node.id : '')}@${v.node.scope}:${v.offset}`;
      console.log('  ', h.name.padEnd(36), f(p).padEnd(28), p && p.rect ? JSON.stringify(p.rect) : '', ' shadow', f(s), ' range', f(r));
    }
  }
  console.log(JSON.stringify(result.lifetime));
}
