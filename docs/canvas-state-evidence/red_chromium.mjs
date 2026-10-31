// Chromium oracle for R03 canvas state, transforms and compositing: writes red-chromium.json next to this file.
// The native probe tests/abi/canvas_state.py replays the same drawing on a 60x40 canvas and compares interior pixels only.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version()};
try {
  const context = await browser.newContext({viewport: {width: 320, height: 240}, deviceScaleFactor: 1});
  const tab = await context.newPage();
  await tab.setContent('<!doctype html><style>html,body{margin:0}canvas{display:block;width:60px;height:40px}</style><body><canvas id=c width=60 height=40></canvas>');
  Object.assign(out, await tab.evaluate(() => {
    const px = (ctx, x, y) => Array.from(ctx.getImageData(x, y, 1, 1).data);
    const round = v => typeof v === 'number' ? Math.round(v * 1e6) / 1e6 + 0 : v;
    const m = t => [t.a, t.b, t.c, t.d, t.e, t.f, t.is2D, t.isIdentity].map(round);
    const thrown = f => { try { f(); return null; } catch (e) { return e.name; } };
    const r = {};
    const c = document.getElementById('c');
    const ctx = c.getContext('2d');
    r.members = Object.fromEntries(['filter', 'beginLayer', 'endLayer', 'reset', 'getTransform'].map(n => [n, n in CanvasRenderingContext2D.prototype]));
    r.defaults = {transform: m(ctx.getTransform()), globalAlpha: ctx.globalAlpha, composite: ctx.globalCompositeOperation, filter: ctx.filter};
    // 1. Transforms: translate, scale, rotate, transform, setTransform, resetTransform and getTransform.
    ctx.translate(10, 5); r.translate = m(ctx.getTransform());
    ctx.scale(2, 3); r.scale = m(ctx.getTransform());
    ctx.resetTransform(); ctx.rotate(Math.PI / 2); r.rotate = m(ctx.getTransform());
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.transform(1, 0, 0, 1, 5, 5); ctx.transform(2, 0, 0, 2, 0, 0); r.transform = m(ctx.getTransform());
    ctx.setTransform({a: 1, b: 0, c: 0, d: 1, e: 7, f: 8}); r.setTransformInit = m(ctx.getTransform());
    ctx.setTransform({m41: 3, m42: 4}); r.setTransformM = m(ctx.getTransform());
    ctx.setTransform(); r.setTransformDefault = m(ctx.getTransform());
    r.setTransformConflict = thrown(() => ctx.setTransform({a: 1, m11: 2}));
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.translate(NaN, 1); ctx.scale(Infinity, 1); ctx.setTransform(NaN, 0, 0, 1, 0, 0); r.nonFinite = m(ctx.getTransform());
    const held = ctx.getTransform(); ctx.translate(1, 1); r.getTransformIsCopy = m(held);
    ctx.resetTransform();
    // Drawing under a transform.
    ctx.translate(20, 10); ctx.scale(2, 2); ctx.fillStyle = '#ff0000'; ctx.fillRect(0, 0, 5, 5);
    ctx.resetTransform();
    r.drawTransformed = {inside: px(ctx, 25, 15), outsideOrigin: px(ctx, 2, 2), beyond: px(ctx, 32, 15)};
    ctx.setTransform(1, 0, 0, 1, 40, 0); ctx.beginPath(); ctx.rect(0, 0, 10, 10);
    ctx.resetTransform();
    r.currentPathKeepsConstructionTransform = {hitTransformed: ctx.isPointInPath(45, 5), hitOrigin: ctx.isPointInPath(5, 5)};
    const square = new Path2D(); square.rect(0, 0, 10, 10);
    ctx.translate(40, 0);
    r.path2dUsesCurrentTransform = {at45: ctx.isPointInPath(square, 45, 5), at5: ctx.isPointInPath(square, 5, 5)};
    ctx.resetTransform();
    // 2. save/restore: fillStyle, transform, alpha, composite and clip, nested, and an unmatched restore.
    c.width = c.width;
    ctx.fillStyle = '#0000ff'; ctx.globalAlpha = 0.5; ctx.translate(5, 5);
    ctx.save();
    ctx.fillStyle = '#00ff00'; ctx.globalAlpha = 1; ctx.translate(10, 0); ctx.globalCompositeOperation = 'copy';
    ctx.beginPath(); ctx.rect(0, 0, 20, 20); ctx.clip();
    ctx.save(); ctx.fillStyle = '#ff0000'; ctx.restore();
    r.innerRestore = {fillStyle: ctx.fillStyle};
    ctx.restore();
    r.restored = {fillStyle: ctx.fillStyle, alpha: ctx.globalAlpha, composite: ctx.globalCompositeOperation, transform: m(ctx.getTransform())};
    ctx.restore(); ctx.restore(); r.unmatchedRestore = {fillStyle: ctx.fillStyle, transform: m(ctx.getTransform())};
    ctx.resetTransform(); ctx.globalAlpha = 1; ctx.fillStyle = '#ff0000'; ctx.fillRect(0, 0, 60, 40);
    r.clipRestored = px(ctx, 50, 35);
    // 3. reset(): bitmap, state stack, path, transform and styles return to defaults.
    ctx.save(); ctx.translate(3, 3); ctx.fillStyle = '#123456'; ctx.globalAlpha = 0.25; ctx.globalCompositeOperation = 'xor';
    ctx.beginPath(); ctx.rect(0, 0, 10, 10);
    ctx.reset();
    r.reset = {pixel: px(ctx, 50, 35), fillStyle: ctx.fillStyle, alpha: ctx.globalAlpha, composite: ctx.globalCompositeOperation,
      transform: m(ctx.getTransform()), path: ctx.isPointInPath(5, 5)};
    ctx.restore(); r.reset.restoreAfterReset = ctx.fillStyle;
    // 4. globalAlpha: range and drawing.
    ctx.globalAlpha = 0.5; ctx.fillStyle = '#ff0000'; ctx.fillRect(0, 0, 10, 10);
    r.alphaPixel = px(ctx, 5, 5);
    ctx.globalAlpha = 2; r.alphaAboveOne = ctx.globalAlpha; ctx.globalAlpha = -1; r.alphaNegative = ctx.globalAlpha; ctx.globalAlpha = NaN; r.alphaNaN = ctx.globalAlpha;
    ctx.globalAlpha = 1;
    // 5. globalCompositeOperation: names, invalid values and pixels.
    const ops = ['source-over', 'source-in', 'source-out', 'source-atop', 'destination-over', 'destination-in', 'destination-out', 'destination-atop',
      'lighter', 'copy', 'xor', 'multiply', 'screen', 'overlay', 'darken', 'lighten', 'color-dodge', 'color-burn', 'hard-light', 'soft-light',
      'difference', 'exclusion', 'hue', 'saturation', 'color', 'luminosity'];
    r.compositeNames = ops.filter(op => { ctx.globalCompositeOperation = op; return ctx.globalCompositeOperation === op; });
    ctx.globalCompositeOperation = 'multiply'; ctx.globalCompositeOperation = 'bogus'; r.compositeInvalidKept = ctx.globalCompositeOperation;
    ctx.globalCompositeOperation = 'darker'; r.compositeDarker = ctx.globalCompositeOperation;
    ctx.globalCompositeOperation = 'Copy'; r.compositeCase = ctx.globalCompositeOperation;
    const tile = (op, x) => {
      ctx.globalCompositeOperation = 'source-over'; ctx.fillStyle = '#0000ff'; ctx.fillRect(x, 20, 10, 10);
      ctx.globalCompositeOperation = op; ctx.fillStyle = '#ff0000'; ctx.fillRect(x + 5, 20, 10, 10); ctx.globalCompositeOperation = 'source-over';
      return {overlap: px(ctx, x + 7, 25), dst: px(ctx, x + 2, 25), src: px(ctx, x + 12, 25)};
    };
    c.width = c.width;
    r.compositePixels = {'source-over': tile('source-over', 0), 'destination-over': tile('destination-over', 15), 'xor': tile('xor', 30), 'lighter': tile('lighter', 45)};
    c.width = c.width;
    r.compositePixels2 = {'source-in': tile('source-in', 0), 'destination-out': tile('destination-out', 15), 'multiply': tile('multiply', 30), 'screen': tile('screen', 45)};
    c.width = c.width;
    r.compositeCopy = tile('copy', 0);
    // 6. filter.
    c.width = c.width;
    r.filter = {initial: ctx.filter};
    ctx.filter = 'blur(2px)'; r.filter.blur = ctx.filter;
    ctx.filter = 'not a filter'; r.filter.invalidKept = ctx.filter;
    ctx.filter = 'invert(1)'; ctx.fillStyle = '#ff0000'; ctx.fillRect(0, 0, 10, 10); r.filter.invertPixel = px(ctx, 5, 5);
    ctx.filter = 'none'; ctx.fillRect(10, 0, 10, 10); r.filter.nonePixel = px(ctx, 15, 5);
    ctx.filter = 'opacity(50%)'; ctx.fillRect(20, 0, 10, 10); r.filter.opacityPixel = px(ctx, 25, 5);
    ctx.filter = 'blur(2px)'; ctx.fillRect(40, 10, 10, 10);
    r.filter.blurPixels = {centre: px(ctx, 45, 15), insideEdge: px(ctx, 40, 15), outsideEdge: px(ctx, 39, 15), far: px(ctx, 35, 15)};
    ctx.filter = 'none';
    // 7. layers.
    if ('beginLayer' in ctx) {
      c.width = c.width;
      ctx.globalAlpha = 0.5; ctx.beginLayer(); ctx.globalAlpha = 1; ctx.fillStyle = '#ff0000'; ctx.fillRect(0, 0, 20, 20); ctx.fillStyle = '#0000ff'; ctx.fillRect(10, 0, 20, 20); ctx.endLayer();
      r.layers = {overlap: px(ctx, 15, 5), red: px(ctx, 5, 5), alphaAfter: ctx.globalAlpha, unmatchedEnd: thrown(() => ctx.endLayer())};
    }
    return r;
  }));
} finally { await browser.close(); }
writeFileSync(new URL('./red-chromium.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log(JSON.stringify(out));
