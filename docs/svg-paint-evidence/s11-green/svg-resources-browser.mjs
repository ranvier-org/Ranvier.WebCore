import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
import {inflateSync, deflateSync, crc32} from 'node:zlib';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

function png(rgb) {
  const chunk = (kind, data) => {
    const length = Buffer.alloc(4); length.writeUInt32BE(data.length);
    const body = Buffer.concat([Buffer.from(kind), data]);
    const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(body) >>> 0);
    return Buffer.concat([length, body, crc]);
  };
  const header = Buffer.alloc(13); header.writeUInt32BE(1, 0); header.writeUInt32BE(1, 4); header[8] = 8; header[9] = 2;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', header), chunk('IDAT', deflateSync(Buffer.from([0, ...rgb]))), chunk('IEND', Buffer.alloc(0))]);
}
const images = {'blue.png': png([0, 0, 255]), 'green.png': png([0, 255, 0]), 'red.png': png([255, 0, 0]), 'broken.png': Buffer.from('not a png')};

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

const browser = await chromium.launch({headless: true});
try {
  const page = await browser.newPage({viewport: {width: 400, height: 300}, deviceScaleFactor: 1});
  const requests = [], held = {};
  await page.route('https://fixture.test/**', route => {
    const url = route.request().url(); requests.push(url);
    const name = url.split('/').pop();
    if (name.startsWith('slow')) { held[name] = route; return; }
    if (images[name]) return route.fulfill({status: 200, contentType: 'image/png', body: images[name], headers: {'access-control-allow-origin': '*'}});
    return route.abort('failed');
  });
  const markup = readFileSync('tests/fixtures/svg-resources.svg', 'utf8').replace(/<script[\s\S]*?<\/script>/, '');
  await page.setContent('<style>body{margin:0}</style>' + markup);
  await page.evaluate(() => {
    const script = document.createElementNS('http://www.w3.org/2000/svg', 'script');
    script.id = 'script'; script.setAttribute('type', 'text/ecmascript');
    window.inertScript = script;
  });
  const settle = async () => { for (let i = 0; i < 5; i++) await page.evaluate(() => new Promise(r => requestAnimationFrame(() => setTimeout(r, 20)))); };
  const px = async (x, y) => pixelOf(await page.screenshot({clip: {x, y, width: 1, height: 1}}));
  const run = (body) => page.evaluate(body);
  await page.waitForFunction(() => document.getElementById('image').getBBox && true);
  await settle();
  const initialPoints = [[20, 20], [60, 10], [110, 10], [160, 10], [210, 10], [210, 30], [260, 10], [20, 110], [50, 110]];
  const pixels = {initial: []};
  for (const [x, y] of initialPoints) pixels.initial.push([x, y, await px(x, y)]);
  const state = {};
  state.a = await run(() => {
    const a = document.getElementById('link');
    const out = {target: a.target.baseVal, href: a.href.baseVal, hreflang: a.hreflang, rel: a.rel, type: a.type, relListLength: a.relList.length, relListContainsNext: a.relList.contains('next')};
    a.target.baseVal = '_self'; a.hreflang = 'fr'; a.type = 'image/svg+xml'; a.relList.add('help');
    Object.assign(out, {changedTarget: a.getAttribute('target'), changedHreflang: a.getAttribute('hreflang'), changedType: a.getAttribute('type'), changedRel: a.rel});
    a.href.baseVal = 'https://fixture.test/other'; out.changedHref = a.getAttribute('href');
    return out;
  });
  state.script = await run(() => {
    const s = window.inertScript;
    const out = {type: s.type, href: s.href.baseVal, async_: s.async};
    s.type = 'module'; s.async = false; s.href.baseVal = 'https://fixture.test/script.js';
    return Object.assign(out, {changedType: s.getAttribute('type'), changedAsync: s.async, changedHref: s.getAttribute('href')});
  });
  state.style = await run(() => { const s = document.getElementById('style'); return {type: s.type, media: s.media, title: s.title}; });
  await run(() => { document.getElementById('style').disabled = true; }); await settle();
  const disabledPaint = await px(110, 10);
  await run(() => { const s = document.getElementById('style'); s.disabled = false; s.media = 'print'; }); await settle();
  const printMediaPaint = await px(110, 10);
  await run(() => { const s = document.getElementById('style'); s.media = 'all'; s.title = 'renamed'; }); await settle();
  Object.assign(state.style, {disabledPaint, printMediaPaint, restoredPaint: await px(110, 10), changedTitle: await run(() => document.getElementById('style').getAttribute('title'))});

  const decodeResult = async () => run(() => document.getElementById('image').decode().then(() => 'resolved', e => 'rejected:' + e.name));
  const browserOnly = {decodeLoaded: await decodeResult()};
  state.image = await run(() => {
    const i = document.getElementById('image');
    const out = {crossOrigin: i.crossOrigin, href: i.href.baseVal};
    i.crossOrigin = 'anonymous'; out.anonymous = i.crossOrigin;
    i.crossOrigin = 'bogus'; out.invalidKeyword = i.crossOrigin;
    i.crossOrigin = null; out.cleared = i.crossOrigin;
    out.geometry = ['x', 'y', 'width', 'height'].map(f => i[f].baseVal.value);
    out.align = i.preserveAspectRatio.baseVal.align;
    try { i.preserveAspectRatio.animVal.align = 6; out.readonlyAlign = 'mutated'; } catch (e) { out.readonlyAlign = e.name; }
    i.preserveAspectRatio.baseVal.align = 6;
    return out;
  });
  await settle(); state.image.meetPaint = [await px(2, 110), await px(20, 110)];
  await run(() => { const i = document.getElementById('image'); i.preserveAspectRatio.baseVal.align = 1; i.x.baseVal.value = 10; }); await settle();
  state.image.movedPaint = [await px(5, 110), await px(45, 110)];
  const setHref = async url => { await run(url => { const i = document.getElementById('image'); i.x.baseVal.value = 0; i.href.baseVal = url; }, url); await settle(); };
  await page.evaluate(() => 0);
  await run(() => { document.getElementById('image').x.baseVal.value = 0; });
  await page.evaluate(url => { document.getElementById('image').href.baseVal = url; }, 'https://fixture.test/missing.png'); await settle();
  state.image.networkErrorPaint = await px(20, 110); browserOnly.decodeNetworkError = await decodeResult();
  await page.evaluate(url => { document.getElementById('image').href.baseVal = url; }, 'https://fixture.test/broken.png'); await settle();
  state.image.brokenBytesPaint = await px(20, 110); browserOnly.decodeBrokenBytes = await decodeResult();
  await page.evaluate(url => { document.getElementById('image').href.baseVal = url; }, 'https://fixture.test/green.png'); await settle();
  state.image.greenPaint = await px(20, 110);
  await page.evaluate(url => { document.getElementById('image').href.baseVal = url; }, 'https://fixture.test/slow-red.png'); await settle();
  state.image.pendingPaint = await px(20, 110);
  await page.evaluate(url => { document.getElementById('image').href.baseVal = url; }, 'https://fixture.test/blue.png'); await settle();
  state.image.replacementPaint = await px(20, 110);
  await held['slow-red.png'].fulfill({status: 200, contentType: 'image/png', body: images['red.png']}).catch(e => { browserOnly.staleFulfil = String(e.message).split('\n')[0]; });
  delete held['slow-red.png']; await settle();
  state.image.staleCompletionPaint = await px(20, 110);
  await page.evaluate(url => { document.getElementById('image').href.baseVal = url; }, 'https://fixture.test/slow-late.png'); await settle();
  await run(() => document.getElementById('image').remove());
  await held['slow-late.png'].fulfill({status: 200, contentType: 'image/png', body: images['red.png']}).catch(e => { browserOnly.lateFulfil = String(e.message).split('\n')[0]; });
  delete held['slow-late.png']; await settle();
  state.image.removedLatePaint = await px(20, 110);

  state.use = await run(() => { const u = document.getElementById('useRect'); return {href: u.href.baseVal, geometry: ['x', 'y', 'width', 'height'].map(f => u[f].baseVal.value)}; });
  await run(() => { document.getElementById('useRect').x.baseVal.value = 60; }); await settle();
  state.use.movedPaint = [await px(55, 10), await px(75, 10)];
  await run(() => document.getElementById('green').setAttribute('fill', 'black')); await settle();
  state.use.targetEditPaint = await px(75, 10);
  await run(() => { document.getElementById('useRect').href.baseVal = '#blueTarget'; }); await settle();
  state.use.hrefPaint = await px(75, 10);
  await run(() => { document.getElementById('useSymbol').width.baseVal.value = 20; }); await settle();
  state.use.symbolWidthPaint = [await px(10, 30), await px(30, 30)];
  await run(() => { document.getElementById('symbol').viewBox.baseVal.width = 20; }); await settle();
  state.use.symbolViewBoxPaint = [await px(5, 30), await px(15, 30)];
  await run(() => document.getElementById('langRect').systemLanguage.clear()); await settle();
  state.switch = {clearedPaint: await px(160, 10), attribute: await run(() => document.getElementById('langRect').getAttribute('systemLanguage'))};
  state.foreignObject = await run(() => { const f = document.getElementById('foreign'); return {geometry: ['x', 'y', 'width', 'height'].map(k => f[k].baseVal.value)}; });
  await run(() => { document.getElementById('foreign').width.baseVal.value = 5; }); await settle();
  state.foreignObject.clippedPaint = [await px(202, 10), await px(220, 10)];
  await run(() => { document.getElementById('foreign').y.baseVal.value = 30; }); await settle();
  state.foreignObject.movedPaint = [await px(202, 10), await px(202, 40)];
  const result = {userAgent: await page.evaluate(() => navigator.userAgent), requests, pixels, state, browserOnly};
  writeFileSync('artifacts/svg-resources-browser.json', JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result));
} finally { await browser.close(); }
