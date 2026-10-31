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

const browser = await chromium.launch({headless: true});
try {
  const page = await browser.newPage({viewport: {width: 320, height: 240}, deviceScaleFactor: 1});
  await page.setContent(readFileSync('tests/fixtures/mathml-surface.html', 'utf8'));
  const frame = () => page.evaluate(() => new Promise(r => requestAnimationFrame(() => setTimeout(r, 10))));
  const px = async (x, y) => pixelOf(await page.screenshot({clip: {x: Math.floor(x), y: Math.floor(y), width: 1, height: 1}}));
  const rect = id => page.evaluate(id => { const r = document.getElementById(id).getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }, id);
  await frame();
  const ids = ['math', 'row', 'mi', 'mo', 'frac', 'num', 'den', 'sqrt', 'rad', 'inline', 'focusable', 'second', 'plain'];
  const identity = await page.evaluate(ids => Object.fromEntries(ids.map(id => {
    const e = document.getElementById(id);
    return [id, {localName: e.localName, namespace: e.namespaceURI, mathml: e instanceof MathMLElement, math: typeof MathMLMathElement !== 'undefined' && e instanceof MathMLMathElement, html: e instanceof HTMLElement}];
  })), ids);
  const members = await page.evaluate(ids => Object.fromEntries(ids.map(id => {
    const e = document.getElementById(id);
    return [id, {tabIndex: e.tabIndex, autofocus: e.autofocus, nonce: e.nonce, nonceAttribute: e.getAttribute('nonce'), dataKind: e.dataset.kind ?? null}];
  })), ids);
  const layout = {};
  const [mi0, mo0, frac0, num0, den0, sqrt0, rad0] = await Promise.all(['mi', 'mo', 'frac', 'num', 'den', 'sqrt', 'rad'].map(rect));
  layout.initial = {numAboveDen: num0[1] + num0[3] <= den0[1] + 0.5, fracTallerThanMi: frac0[3] > mi0[3], sqrtWiderThanRadicand: sqrt0[2] > rad0[2], moRightOfMi: mo0[0] >= mi0[0] + mi0[2] - 0.5};
  await page.evaluate(() => document.getElementById('mi').attributeStyleMap.set('padding-left', CSS.px(10)));
  await frame();
  const mo1 = await rect('mo');
  layout.paddingShift = Math.round((mo1[0] - mo0[0]) * 2) / 2;
  layout.paddingTyped = await page.evaluate(() => { const v = document.getElementById('mi').attributeStyleMap.get('padding-left'); return [v.constructor.name, v.value, v.unit]; });
  await page.evaluate(() => document.getElementById('math').style.setProperty('font-size', '40px'));
  await frame();
  const mi2 = await rect('mi');
  layout.fontScale = (mi2[2] - 10) / (mi0[2]);
  layout.fontScaleRange = layout.fontScale > 1.6 && layout.fontScale < 2.4;
  await page.evaluate(() => document.getElementById('frac').attributeStyleMap.set('background-color', 'rgb(0, 0, 255)'));
  await frame();
  const frac2 = await rect('frac');
  layout.fracBackground = await px(frac2[0] + 1, frac2[1] + 1);
  const fracDisplayHeight = frac2[3];
  await page.evaluate(() => document.getElementById('math').style.setProperty('math-style', 'compact'));
  await frame();
  layout.compactShrinksFraction = (await rect('frac'))[3] < fracDisplayHeight;
  layout.mathStyle = await page.evaluate(() => getComputedStyle(document.getElementById('frac')).mathStyle);
  const focus = await page.evaluate(() => {
    const out = {};
    const active = () => document.activeElement && document.activeElement.id;
    out.initialActive = active();
    document.getElementById('focusable').focus({preventScroll: true}); out.afterFocus = active();
    document.getElementById('plain').focus(); out.afterUnfocusable = active();
    document.getElementById('focusable').blur(); out.afterBlur = active();
    const plain = document.getElementById('plain'); plain.tabIndex = 0; out.plainTabIndex = plain.getAttribute('tabindex');
    plain.focus(); out.afterTabIndexFocus = active(); plain.blur(); plain.removeAttribute('tabindex');
    const f = document.getElementById('focusable'); f.autofocus = false; out.autofocusAttribute = f.getAttribute('autofocus');
    f.nonce = 'changed'; out.nonceAfterSet = f.nonce; out.nonceAttributeAfterSet = f.getAttribute('nonce');
    const m = document.getElementById('math'); m.dataset.newKey = 'value-λ'; out.datasetAttribute = m.getAttribute('data-new-key');
    delete m.dataset.kind; out.datasetDeleted = m.getAttribute('data-kind');
    document.getElementById('focusable').focus();
    return out;
  });
  await page.keyboard.press('Tab');
  focus.afterTab = await page.evaluate(() => document.activeElement && document.activeElement.id);
  const result = {userAgent: await page.evaluate(() => navigator.userAgent), identity, members, layout, focus};
  writeFileSync('artifacts/mathml-surface-browser.json', JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result));
} finally { await browser.close(); }
