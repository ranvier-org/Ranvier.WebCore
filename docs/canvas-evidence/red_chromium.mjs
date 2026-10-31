// Chromium oracle for R01 canvas 2D context lifecycle: writes red-chromium.json next to this file.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version()};
try {
  const context = await browser.newContext({viewport: {width: 320, height: 240}, deviceScaleFactor: 1});
  const tab = await context.newPage();
  await tab.setContent('<!doctype html><style>html,body{margin:0}canvas{display:block}</style><body><canvas id=c width=40 height=20></canvas><canvas id=d></canvas><canvas id=e></canvas><canvas id=f></canvas>');
  Object.assign(out, await tab.evaluate(() => {
    const px = (ctx, x, y) => Array.from(ctx.getImageData(x, y, 1, 1).data);
    const r = {};
    const c = document.getElementById('c'), d = document.getElementById('d'), e = document.getElementById('e'), f = document.getElementById('f');
    r.defaults = {width: d.width, height: d.height};
    r.members = {getContext: typeof c.getContext, isContextLost: 'isContextLost' in CanvasRenderingContext2D.prototype,
      reset: 'reset' in CanvasRenderingContext2D.prototype, getContextAttributes: 'getContextAttributes' in CanvasRenderingContext2D.prototype};
    const ctx = c.getContext('2d');
    r.identity = {same: ctx === c.getContext('2d'), canvas: ctx.canvas === c, ignoresLaterSettings: ctx === c.getContext('2d', {willReadFrequently: true})};
    r.otherTypesAfter2d = Object.fromEntries(['webgl', 'webgl2', 'bitmaprenderer', 'webgpu', 'bogus', '2D', ''].map(t => [t, c.getContext(t)]));
    r.unknownOnFresh = {bogus: e.getContext('bogus'), then2d: !!e.getContext('2d')};
    r.attributes = {defaults: ctx.getContextAttributes(),
      willRead: d.getContext('2d', {willReadFrequently: true, desynchronized: false}).getContextAttributes(),
      p3: f.getContext('2d', {colorSpace: 'display-p3', alpha: false}).getContextAttributes()};
    r.initialFillStyle = ctx.fillStyle;
    r.initialPixel = px(ctx, 0, 0);
    ctx.fillStyle = '#ff0000'; r.fillStyleHex = ctx.fillStyle;
    ctx.fillStyle = 'not a colour'; r.fillStyleInvalidKept = ctx.fillStyle;
    ctx.fillStyle = 'rgba(0, 0, 255, 0.5)'; r.fillStyleRgba = ctx.fillStyle;
    ctx.fillStyle = 'lime'; r.fillStyleNamed = ctx.fillStyle;
    ctx.fillStyle = '#ff0000';
    ctx.fillRect(0, 0, 20, 20);
    ctx.fillStyle = 'rgb(0, 0, 255)';
    ctx.fillRect(20, 0, 20, 20);
    r.drawn = {left: px(ctx, 5, 5), right: px(ctx, 30, 5)};
    ctx.clearRect(5, 5, 4, 4);
    r.cleared = {inside: px(ctx, 6, 6), outside: px(ctx, 10, 10)};
    ctx.fillRect(NaN, 0, 5, 5); ctx.fillRect(0, 0, Infinity, 5); r.nonFiniteIgnored = px(ctx, 6, 6);
    ctx.fillStyle = 'rgba(0, 255, 0, 0.5)'; ctx.fillRect(0, 10, 40, 10);
    r.halfAlphaOverRed = px(ctx, 5, 15); r.halfAlphaOverBlue = px(ctx, 30, 15);
    ctx.fillStyle = '#123456';
    c.width = c.width;
    r.resetSameWidth = {pixel: px(ctx, 5, 5), fillStyle: ctx.fillStyle, width: c.width, same: ctx === c.getContext('2d')};
    ctx.fillStyle = '#00ff00'; ctx.fillRect(0, 0, 40, 20);
    c.height = 30;
    r.resetHeight = {pixel: px(ctx, 5, 5), fillStyle: ctx.fillStyle, height: c.height};
    c.setAttribute('width', '50'); r.attributeWidth = {width: c.width, pixel: px(ctx, 5, 5)};
    c.width = 4294967295; r.hugeWidth = c.width;
    c.width = 0; r.zeroWidth = {width: c.width, attributes: ctx.getContextAttributes()};
    c.width = 40; c.height = 20;
    c.remove();
    ctx.fillStyle = '#ff00ff'; ctx.fillRect(0, 0, 10, 10);
    r.detached = {pixel: px(ctx, 1, 1), canvasConnected: ctx.canvas.isConnected, same: ctx === c.getContext('2d')};
    document.body.prepend(c);
    ctx.fillStyle = '#ff0000'; ctx.fillRect(0, 0, 20, 20); ctx.fillStyle = 'rgb(0, 0, 255)'; ctx.fillRect(20, 0, 20, 20);
    return r;
  }));
  const shot = await tab.locator('#c').screenshot();
  out.screenshotBytes = shot.length;
} finally { await browser.close(); }
writeFileSync(new URL('./red-chromium.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log(JSON.stringify(out));
