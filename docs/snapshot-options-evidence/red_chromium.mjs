// R12 RED survey in Chromium: DOM capture members, canvas encodings, quality and color spaces. Writes red-chromium.json.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version()};
try {
  const tab = await browser.newPage();
  await tab.setContent('<!doctype html><body><div id=d style="width:20px;height:10px;background:red"></div>');
  out.result = await tab.evaluate(async () => {
    const members = {
      drawElementImage: 'drawElementImage' in CanvasRenderingContext2D.prototype,
      drawElement: 'drawElement' in CanvasRenderingContext2D.prototype,
      layoutsubtree: 'layoutSubtree' in HTMLCanvasElement.prototype,
      getDisplayMedia: typeof navigator.mediaDevices?.getDisplayMedia,
      elementCapture: typeof globalThis.RestrictionTarget, cropTarget: typeof globalThis.CropTarget,
      html2canvasLike: typeof document.elementSnapshot,
    };
    const c = new OffscreenCanvas(20, 10); const g = c.getContext('2d'); g.fillStyle = 'red'; g.fillRect(0, 0, 20, 10);
    const encodings = {};
    for (const type of ['image/png', 'image/jpeg', 'image/webp', 'image/avif', 'image/bmp', 'image/gif', 'image/x-unknown']) {
      try { const b = await c.convertToBlob({type, quality: 0.5}); encodings[type] = {type: b.type, size: b.size}; }
      catch (e) { encodings[type] = {error: e.name}; } }
    const quality = {};
    for (const q of [0, 0.5, 1]) { const b = await c.convertToBlob({type: 'image/jpeg', quality: q}); quality[q] = b.size; }
    const colorSpaces = {};
    for (const colorSpace of ['srgb', 'display-p3', 'rec2100-pq']) {
      try { const x = new OffscreenCanvas(1, 1).getContext('2d', {colorSpace}); colorSpaces[colorSpace] = x.getContextAttributes().colorSpace; }
      catch (e) { colorSpaces[colorSpace] = 'error ' + e.name; } }
    const p3 = new OffscreenCanvas(1, 1).getContext('2d', {colorSpace: 'display-p3'}); p3.fillStyle = 'color(display-p3 1 0 0)'; p3.fillRect(0, 0, 1, 1);
    const readback = {srgb: Array.from(p3.getImageData(0, 0, 1, 1, {colorSpace: 'srgb'}).data), p3: Array.from(p3.getImageData(0, 0, 1, 1).data)};
    return {members, encodings, quality, colorSpaces, readback};
  });
} finally { await browser.close(); }
writeFileSync(new URL('red-chromium.json', import.meta.url), JSON.stringify(out, null, 1));
console.log(JSON.stringify(out, null, 1));
