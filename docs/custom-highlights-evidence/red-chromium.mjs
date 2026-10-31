// RED: Chromium behaviour of CSS.highlights, Highlight and ::highlight() painting.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
import {inflateSync} from 'node:zlib';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
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
  return colorType === 6 ? [...raw.subarray(1, 5)] : [...raw.subarray(1, 4), 255];
}
const font = readFileSync('C:/wk/src/Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf').toString('base64');
const html = `<!doctype html><style>@font-face{font-family:Ahem;src:url(data:font/ttf;base64,${font})}
html,body{margin:0;background:#fff}#t{font:20px/20px Ahem;color:#000;white-space:pre;margin:0}
::highlight(red){background-color:rgb(255,0,0);color:rgb(0,0,255)}
::highlight(green){background-color:rgb(0,128,0);color:rgb(255,255,0)}</style><p id=t>X X X X X X X X</p>`;
const browser = await chromium.launch({headless: true});
const out = {version: browser.version()};
try {
  const page = await browser.newPage({viewport: {width: 320, height: 60}, deviceScaleFactor: 1});
  await page.setContent(html);
  await page.evaluate(() => document.fonts.ready);
  const frame = () => page.evaluate(() => new Promise(r => requestAnimationFrame(() => setTimeout(r, 10))));
  const row = async () => { await frame(); const r = []; for (let i = 0; i < 15; i++) r.push((await pixelOf(await page.screenshot({clip: {x: i * 20 + 10, y: 10, width: 1, height: 1}}))).slice(0, 3).join(',')); return r; };
  out.api = await page.evaluate(() => {
    const t = document.getElementById('t').firstChild, R = (s, e) => { const r = new Range(); r.setStart(t, s); r.setEnd(t, e); return r; };
    const reg = CSS.highlights, log = {};
    log.types = [String(reg), typeof Highlight, typeof HighlightRegistry, 'highlightsFromPoint' in reg, typeof reg.highlightsFromPoint];
    const h1 = new Highlight(), h2 = new Highlight(), h4 = new Highlight();
    log.empty = [reg.size, reg.set('a', h1) === reg, reg.set('b', h2) === reg, reg.set('c', h1) === reg, [...reg.keys()]];
    reg.set('a', h4); log.reset = [[...reg.keys()], reg.get('a') === h4, reg.get('c') === h1, reg.size];
    log.del = [reg.delete('b'), reg.delete('b'), [...reg.keys()], reg.has('b'), reg.get('zz'), reg.has('a')];
    reg.set('b', h2); const fe = []; reg.forEach((v, k, m) => fe.push([k, v === reg.get(k), m === reg])); log.forEach = fe;
    log.entries = [...reg.entries()].map(([k, v]) => [k, v === h4 ? 'h4' : v === h1 ? 'h1' : 'h2']);
    try { reg.set('x', {}); log.badSet = 'ok'; } catch (e) { log.badSet = e.name; }
    reg.clear(); log.clear = [reg.size, [...reg.keys()]];
    const r1 = R(0, 1), r2 = R(2, 3), r3 = R(4, 5), s1 = new StaticRange({startContainer: t, startOffset: 6, endContainer: t, endOffset: 7});
    const name = r => r === r1 ? 'r1' : r === r2 ? 'r2' : r === r3 ? 'r3' : r === s1 ? 's1' : '?';
    const h = new Highlight(r1, r2, r1);
    log.ctor = [h.size, [...h].map(name), h.priority, h.type];
    log.add = [h.add(r3) === h, h.add(r1) === h, [...h].map(name), h.size, h.add(s1) === h, [...h.values()].map(name), [...h.keys()].map(name), [...h.entries()].map(([a, b]) => name(a) + name(b))];
    log.hdel = [h.delete(r2), h.delete(r2), h.has(r2), h.has(r1), [...h].map(name)];
    const hf = []; h.forEach((v, k, s) => hf.push([name(v), name(k), s === h])); log.hforEach = hf;
    try { h.add({}); log.badAdd = 'ok'; } catch (e) { log.badAdd = e.name; }
    try { new Highlight(r1, 5); log.badCtor = 'ok'; } catch (e) { log.badCtor = e.name; }
    const pr = []; for (const v of [5, -1, 2147483647, -2147483648, 2.7, 2147483648, NaN]) { h.priority = v; pr.push(h.priority); } log.priority = pr;
    const ty = []; for (const v of ['spelling-error', 'grammar-error', 'bogus', 'highlight']) { try { h.type = v; ty.push(h.type); } catch (e) { ty.push(e.name); } } log.type = ty;
    h.clear(); log.hclear = [h.size, [...h]];
    log.selfHighlights = [document.defaultView.CSS.highlights === reg];
    return log;
  });
  out.paint = {};
  out.paint.base = await row();
  await page.evaluate(() => { const t = document.getElementById('t').firstChild, R = (s, e) => { const r = new Range(); r.setStart(t, s); r.setEnd(t, e); return r; };
    window.rr = R(4, 11); window.red = new Highlight(rr); CSS.highlights.set('red', red); });
  out.paint.red = await row();
  await page.evaluate(() => { const t = document.getElementById('t').firstChild, r = new Range(); r.setStart(t, 8); r.setEnd(t, 15); window.green = new Highlight(r); CSS.highlights.set('green', green); });
  out.paint.redThenGreen = await row();
  await page.evaluate(() => { red.priority = 1; });
  out.paint.redPriority1 = await row();
  await page.evaluate(() => { red.priority = 0; CSS.highlights.delete('red'); CSS.highlights.set('red', red); });
  out.paint.greenThenRed = await row();
  await page.evaluate(() => { CSS.highlights.delete('green'); });
  out.paint.redOnly = await row();
  await page.evaluate(() => { rr.setEnd(rr.endContainer, 5); });
  out.paint.liveRangeShrunk = await row();
  await page.evaluate(() => { const t = document.getElementById('t').firstChild; red.add(new StaticRange({startContainer: t, startOffset: 12, endContainer: t, endOffset: 13})); });
  out.paint.staticAdded = await row();
  await page.evaluate(() => { CSS.highlights.set('unstyled', new Highlight(rr)); CSS.highlights.delete('red'); });
  out.paint.unstyledOnly = await row();
  await page.evaluate(() => { CSS.highlights.clear(); });
  out.paint.cleared = await row();
  out.paint.textAfter = await page.evaluate(() => [document.getElementById('t').textContent, document.getElementById('t').childNodes.length]);
} finally { await browser.close(); }
writeFileSync(process.argv[2] ?? 'C:/wk/t03-artifacts/red/chromium.json', JSON.stringify(out, null, 1));
console.log(JSON.stringify(out));
