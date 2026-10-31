// Chromium oracle for R06 canvas image/pixel operations: writes red-chromium.json next to this file.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version()};
// 2x2 PNG: red, lime / blue, transparent.
const PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR4nGP4z8DwHwwZGP6DCAYAP9IF+9wCo9QAAAAASUVORK5CYII=';
try {
  const context = await browser.newContext({viewport: {width: 320, height: 240}, deviceScaleFactor: 1});
  const tab = await context.newPage();
  await tab.setContent('<!doctype html><body><canvas id=c width=8 height=8></canvas><canvas id=d width=4 height=4></canvas>'
    + '<canvas id=z width=0 height=4></canvas><img id=i src="' + PNG + '"><img id=broken src="data:image/png;base64,AAAA"><img id=empty>');
  Object.assign(out, await tab.evaluate(async (png) => {
    const r = {};
    const err = f => { try { const v = f(); return v === undefined ? 'ok' : v; } catch (e) { return e.name; } };
    const bytes = d => Array.from(d.data);
    const c = document.getElementById('c'), ctx = c.getContext('2d');
    const d = document.getElementById('d'), dctx = d.getContext('2d', {willReadFrequently: true});
    // ImageData construction.
    const blank = new ImageData(2, 3);
    r.construct = {width: blank.width, height: blank.height, length: blank.data.length, colorSpace: blank.colorSpace,
      pixelFormat: blank.pixelFormat ?? null, zero: blank.data.every(v => v === 0), dataType: blank.data.constructor.name};
    r.constructErrors = {zeroWidth: err(() => new ImageData(0, 2)), zeroHeight: err(() => new ImageData(2, 0)),
      huge: err(() => new ImageData(65536, 65536)), notMultipleOf4: err(() => new ImageData(new Uint8ClampedArray(6), 1)),
      notMultipleOfRow: err(() => new ImageData(new Uint8ClampedArray(12), 2)), heightMismatch: err(() => new ImageData(new Uint8ClampedArray(16), 2, 3)),
      emptyData: err(() => new ImageData(new Uint8ClampedArray(0), 1)), p3: err(() => new ImageData(1, 1, {colorSpace: 'display-p3'}).colorSpace),
      badColorSpace: err(() => new ImageData(1, 1, {colorSpace: 'bogus'}))};
    const fromData = new ImageData(new Uint8ClampedArray([1, 2, 3, 4, 5, 6, 7, 8]), 1);
    r.constructFromData = {width: fromData.width, height: fromData.height, data: bytes(fromData)};
    // createImageData.
    const created = ctx.createImageData(-3, 2);
    r.createImageData = {negative: [created.width, created.height], zero: err(() => ctx.createImageData(0, 1)),
      copyOf: (() => { const x = ctx.createImageData(fromData); return [x.width, x.height, x.data.every(v => v === 0)]; })(),
      colorSpace: created.colorSpace};
    // put/get round trip with opaque, transparent and half-alpha pixels.
    const src = new ImageData(new Uint8ClampedArray([255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 10, 20, 30, 0,
      255, 255, 255, 128, 0, 0, 0, 255, 200, 100, 50, 255, 1, 2, 3, 255]), 4, 2);
    ctx.putImageData(src, 1, 1);
    r.roundTrip = bytes(ctx.getImageData(1, 1, 4, 2));
    r.outside = bytes(ctx.getImageData(-1, -1, 2, 2));
    r.negativeRect = bytes(ctx.getImageData(3, 2, -2, -1));
    r.getErrors = {zeroWidth: err(() => ctx.getImageData(0, 0, 0, 1)), zeroHeight: err(() => ctx.getImageData(0, 0, 1, 0))};
    r.getColorSpace = ctx.getImageData(0, 0, 1, 1).colorSpace;
    // putImageData ignores compositing and alpha state.
    ctx.globalAlpha = 0.5; ctx.globalCompositeOperation = 'lighter';
    ctx.putImageData(new ImageData(new Uint8ClampedArray([9, 8, 7, 255]), 1), 0, 0);
    ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
    r.putIgnoresState = bytes(ctx.getImageData(0, 0, 1, 1));
    // Dirty rectangle: only the dirty part of the source lands, offset by dx/dy.
    ctx.clearRect(0, 0, 8, 8);
    const solid = new ImageData(new Uint8ClampedArray(Array(3 * 3).fill([0, 0, 255, 255]).flat()), 3, 3);
    ctx.putImageData(solid, 2, 2, 1, 1, 1, 1);
    r.dirty = {inside: bytes(ctx.getImageData(3, 3, 1, 1)), corner: bytes(ctx.getImageData(2, 2, 1, 1))};
    ctx.putImageData(solid, 4, 4, 2, 2, -2, -2);
    r.dirtyNegative = {at5: bytes(ctx.getImageData(5, 5, 1, 1)), at6: bytes(ctx.getImageData(6, 6, 1, 1)), at4: bytes(ctx.getImageData(4, 4, 1, 1))};
    r.putPartlyOutside = err(() => ctx.putImageData(solid, 7, 7));
    r.partlyOutsidePixel = bytes(ctx.getImageData(7, 7, 1, 1));
    // drawImage from a canvas.
    dctx.fillStyle = '#ff0000'; dctx.fillRect(0, 0, 2, 4); dctx.fillStyle = '#0000ff'; dctx.fillRect(2, 0, 2, 4);
    ctx.clearRect(0, 0, 8, 8);
    ctx.drawImage(d, 0, 0);
    r.drawCanvas = {left: bytes(ctx.getImageData(0, 0, 1, 1)), right: bytes(ctx.getImageData(3, 0, 1, 1)), beyond: bytes(ctx.getImageData(5, 0, 1, 1))};
    ctx.clearRect(0, 0, 8, 8);
    ctx.drawImage(d, 0, 0, 8, 8);
    r.drawCanvasScaled = {left: bytes(ctx.getImageData(1, 6, 1, 1)), right: bytes(ctx.getImageData(6, 6, 1, 1))};
    ctx.clearRect(0, 0, 8, 8);
    ctx.drawImage(d, 2, 0, 2, 4, 0, 0, 2, 4);
    r.drawCanvasSubRect = {left: bytes(ctx.getImageData(0, 0, 1, 1)), right: bytes(ctx.getImageData(1, 3, 1, 1)), beyond: bytes(ctx.getImageData(2, 0, 1, 1))};
    r.drawErrors = {zeroSizeCanvas: err(() => ctx.drawImage(document.getElementById('z'), 0, 0)),
      zeroSourceRect: err(() => ctx.drawImage(d, 0, 0, 0, 4, 0, 0, 4, 4)),
      nonFinite: err(() => ctx.drawImage(d, NaN, 0)), emptyImage: err(() => ctx.drawImage(document.getElementById('empty'), 0, 0))};
    // drawImage from a decoded <img>.
    const img = document.getElementById('i');
    await new Promise(res => img.complete ? res() : (img.onload = res));
    ctx.clearRect(0, 0, 8, 8);
    ctx.drawImage(img, 0, 0);
    r.drawImage = {natural: [img.naturalWidth, img.naturalHeight], pixels: bytes(ctx.getImageData(0, 0, 2, 2))};
    const broken = document.getElementById('broken');
    await new Promise(res => broken.complete ? res() : (broken.onerror = res));
    r.drawBroken = err(() => ctx.drawImage(broken, 0, 0));
    // Tainting: a cross-origin image is not reachable here; record the API shape only.
    r.imageDataDataWritable = (() => { const x = new ImageData(1, 1); x.data[0] = 300; x.data[1] = -5; return [x.data[0], x.data[1]]; })();
    return r;
  }, PNG));
} finally { await browser.close(); }
writeFileSync(new URL('./red-chromium.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log(JSON.stringify(out));
