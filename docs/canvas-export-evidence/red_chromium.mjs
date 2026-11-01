// Chromium oracle for R07 canvas export and bitmap transport: writes red-chromium.json next to this file.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version()};
try {
  const context = await browser.newContext({viewport: {width: 320, height: 240}, deviceScaleFactor: 1});
  const tab = await context.newPage();
  await tab.setContent('<!doctype html><body><canvas id=c width=4 height=2></canvas><canvas id=z width=0 height=2></canvas><canvas id=b width=4 height=2></canvas>');
  Object.assign(out, await tab.evaluate(async () => {
    const r = {};
    const err = async f => { try { const v = await f(); return v === undefined ? 'ok' : v; } catch (e) { return e.name; } };
    const c = document.getElementById('c'), ctx = c.getContext('2d');
    ctx.fillStyle = '#ff0000'; ctx.fillRect(0, 0, 2, 2); ctx.fillStyle = '#0000ff'; ctx.fillRect(2, 0, 2, 2);
    const bytesOf = async blob => Array.from(new Uint8Array(await blob.arrayBuffer()));
    const decode = async (blob, w, h) => { const bmp = await createImageBitmap(blob); const k = new OffscreenCanvas(w, h).getContext('2d'); k.drawImage(bmp, 0, 0); return Array.from(k.getImageData(0, 0, w, h).data); };
    // toDataURL
    const png = c.toDataURL();
    r.toDataURL = {prefix: png.slice(0, 22), defaultIsPng: png === c.toDataURL('image/png'), jpegPrefix: c.toDataURL('image/jpeg').slice(0, 23),
      webpPrefix: c.toDataURL('image/webp').slice(0, 23), unknownFallsBackToPng: c.toDataURL('image/bogus') === png,
      upperCase: c.toDataURL('IMAGE/JPEG').slice(0, 23), zeroSize: document.getElementById('z').toDataURL()};
    // toBlob
    const blob = await new Promise(res => c.toBlob(res));
    r.toBlob = {type: blob.type, signature: (await bytesOf(blob)).slice(0, 8), decoded: await decode(blob, 4, 2)};
    const jpeg = await new Promise(res => c.toBlob(res, 'image/jpeg', 0.9));
    r.toBlobJpeg = {type: jpeg.type, signature: (await bytesOf(jpeg)).slice(0, 3)};
    const bogus = await new Promise(res => c.toBlob(res, 'image/bogus'));
    r.toBlobUnknown = bogus.type;
    r.toBlobZeroSize = await new Promise(res => document.getElementById('z').toBlob(res));
    // createImageBitmap
    const bmp = await createImageBitmap(c);
    r.bitmap = {width: bmp.width, height: bmp.height};
    const crop = await createImageBitmap(c, 1, 0, 2, 2);
    const k = document.createElement('canvas'); k.width = 4; k.height = 2; const kc = k.getContext('2d');
    kc.drawImage(crop, 0, 0); r.cropPixels = Array.from(kc.getImageData(0, 0, 2, 1).data);
    const flipped = await createImageBitmap(new ImageData(new Uint8ClampedArray([255,0,0,255, 0,0,255,255]), 1, 2), {imageOrientation: 'flipY'});
    kc.clearRect(0, 0, 4, 2); kc.drawImage(flipped, 0, 0); r.flipY = Array.from(kc.getImageData(0, 0, 1, 2).data);
    const resized = await createImageBitmap(c, {resizeWidth: 8, resizeHeight: 4, resizeQuality: 'pixelated'});
    r.resized = [resized.width, resized.height];
    r.fromImageData = await (async () => { const b = await createImageBitmap(new ImageData(2, 3)); return [b.width, b.height]; })();
    r.fromBlob = await (async () => { const b = await createImageBitmap(blob); return [b.width, b.height]; })();
    r.errors = {zeroCrop: await err(() => createImageBitmap(c, 0, 0, 0, 2)), zeroCanvas: await err(() => createImageBitmap(document.getElementById('z'))),
      badBlob: await err(() => createImageBitmap(new Blob([new Uint8Array([1, 2, 3])]))),
      closedSource: await err(async () => { const b = await createImageBitmap(c); b.close(); return createImageBitmap(b); }),
      drawClosed: await err(async () => { const b = await createImageBitmap(c); b.close(); kc.drawImage(b, 0, 0); })};
    bmp.close();
    r.closed = {width: bmp.width, height: bmp.height};
    // bitmaprenderer
    const bctx = document.getElementById('b').getContext('bitmaprenderer');
    r.bitmapRenderer = {type: String(bctx), canvas: bctx.canvas === document.getElementById('b'), attributes: JSON.stringify(bctx.getContextAttributes?.() ?? null)};
    const moving = await createImageBitmap(c);
    bctx.transferFromImageBitmap(moving);
    r.transfer = {sourceAfter: [moving.width, moving.height], canvasData: document.getElementById('b').toDataURL() === png};
    r.transferClosed = await err(async () => bctx.transferFromImageBitmap(moving));
    bctx.transferFromImageBitmap(null);
    r.transferNull = {canvas: [document.getElementById('b').width, document.getElementById('b').height]};
    r.other2d = document.getElementById('b').getContext('2d');
    return r;
  }));
} finally { await browser.close(); }
writeFileSync(new URL('./red-chromium.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log(JSON.stringify(out));
