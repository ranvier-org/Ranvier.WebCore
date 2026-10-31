import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
import {inflateSync} from 'node:zlib';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

// Chromium oracle for SVGTests string lists after their attribute is removed, emptied, restored or cleared.
// Chromium repaints a conditional element only when its renderer is rebuilt, so `reinserted` re-appends the
// element (and the switch) before sampling the SVGTests validity in paint.
export const markup = `<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60">
<rect id="requiredExtensions" x="0" y="0" width="40" height="40" fill="lime" requiredExtensions="urn:x"/>
<rect id="systemLanguage" x="50" y="0" width="40" height="40" fill="lime" systemLanguage="zz"/>
<switch><rect id="first" x="100" y="0" width="40" height="40" fill="lime" systemLanguage="zz"/><rect x="100" y="0" width="40" height="40" fill="blue"/></switch>
</svg>`;

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
  const page = await browser.newPage({viewport: {width: 200, height: 60}, deviceScaleFactor: 1});
  await page.setContent(`<!doctype html><body style="margin:0">${markup}</body>`);
  const frame = () => page.evaluate(() => new Promise(r => requestAnimationFrame(() => setTimeout(r, 10))));
  const px = async x => { await frame(); return pixelOf(await page.screenshot({clip: {x, y: 20, width: 1, height: 1}})); };
  const result = {};
  for (const [field, x, value] of [['requiredExtensions', 20, 'urn:x'], ['systemLanguage', 70, 'zz']]) {
    const run = step => page.evaluate(([field, value, step]) => {
      const e = document.getElementById(field);
      window.lists = window.lists || {};
      window.lists[field] = window.lists[field] || e[field];
      if (step === 'removed') e.removeAttribute(field);
      if (step === 'empty') e.setAttribute(field, '');
      if (step === 'restored') e.setAttribute(field, value);
      if (step === 'cleared') e[field].clear();
      if (step === 'appended') { e.setAttribute(field, value); e[field].appendItem(value); }
      if (step === 'removedAgain') e.removeAttribute(field);
      if (step === 'reinserted') e.parentNode.appendChild(e);
      return {items: e[field].numberOfItems, attribute: e.getAttribute(field), sameList: e[field] === window.lists[field]};
    }, [field, value, step]);
    result[field] = {};
    for (const step of ['initial', 'removed', 'empty', 'restored', 'cleared', 'appended', 'removedAgain', 'reinserted'])
      result[field][step] = {...await run(step), paint: await px(x)};
  }
  result.switch = {initial: await px(120)};
  await page.evaluate(() => document.getElementById('first').removeAttribute('systemLanguage'));
  result.switch.removed = await px(120);
  await page.evaluate(() => { const s = document.getElementById('first').parentNode; s.parentNode.appendChild(s); });
  result.switch.reinserted = await px(120);
  const text = JSON.stringify({browser: browser.version(), markup, result}, null, 2) + '\n';
  if (process.argv[2]) writeFileSync(process.argv[2], text);
  console.log(JSON.stringify(result));
} finally { await browser.close(); }
