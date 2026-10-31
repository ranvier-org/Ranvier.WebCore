// Chromium oracle for R04 canvas paints: writes red-chromium.json next to this file.
// The native probe tests/abi/canvas_paints.py replays the same drawing on a 60x40 canvas, with a 4x4 canvas as the pattern
// source, and compares representative pixels within the probe's stated tolerances.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version()};
try {
  const context = await browser.newContext({viewport: {width: 320, height: 240}, deviceScaleFactor: 1});
  const tab = await context.newPage();
  await tab.setContent('<!doctype html><style>html,body{margin:0}canvas{display:block}#c{width:60px;height:40px}</style><body><canvas id=c width=60 height=40></canvas><canvas id=s width=4 height=4></canvas>');
  Object.assign(out, await tab.evaluate(() => {
    const px = (ctx, x, y) => Array.from(ctx.getImageData(x, y, 1, 1).data);
    const thrown = f => { try { f(); return null; } catch (e) { return e.name; } };
    const r = {};
    const c = document.getElementById('c'), s = document.getElementById('s');
    const ctx = c.getContext('2d');
    // The pattern source: a 4x4 canvas, red in its left half and blue in its right half.
    const sctx = s.getContext('2d'); sctx.fillStyle = '#ff0000'; sctx.fillRect(0, 0, 2, 4); sctx.fillStyle = '#0000ff'; sctx.fillRect(2, 0, 2, 4);
    r.defaults = {strokeStyle: ctx.strokeStyle, lineWidth: ctx.lineWidth, lineCap: ctx.lineCap, lineJoin: ctx.lineJoin, miterLimit: ctx.miterLimit,
      lineDash: ctx.getLineDash(), lineDashOffset: ctx.lineDashOffset, shadowOffsetX: ctx.shadowOffsetX, shadowOffsetY: ctx.shadowOffsetY,
      shadowBlur: ctx.shadowBlur, shadowColor: ctx.shadowColor, imageSmoothingEnabled: ctx.imageSmoothingEnabled, imageSmoothingQuality: ctx.imageSmoothingQuality};
    // 1. Line styles and their validation.
    ctx.lineWidth = 4; ctx.lineWidth = 0; ctx.lineWidth = -1; ctx.lineWidth = NaN; ctx.lineWidth = Infinity; r.lineWidthKept = ctx.lineWidth;
    ctx.miterLimit = 3; ctx.miterLimit = 0; ctx.miterLimit = -2; r.miterLimitKept = ctx.miterLimit;
    ctx.lineCap = 'round'; r.lineCapRound = ctx.lineCap; ctx.lineJoin = 'bevel'; r.lineJoinBevel = ctx.lineJoin;
    ctx.setLineDash([4, 2]); r.lineDash = ctx.getLineDash(); ctx.setLineDash([1, 2, 3]); r.lineDashOdd = ctx.getLineDash();
    ctx.setLineDash([1, -1]); r.lineDashNegativeKept = ctx.getLineDash(); ctx.setLineDash([1, NaN]); r.lineDashNaNKept = ctx.getLineDash();
    ctx.lineDashOffset = 1.5; ctx.lineDashOffset = NaN; r.lineDashOffsetKept = ctx.lineDashOffset;
    ctx.shadowBlur = 3; ctx.shadowBlur = -1; r.shadowBlurKept = ctx.shadowBlur;
    ctx.shadowColor = 'rgba(0, 0, 255, 0.5)'; r.shadowColorRgba = ctx.shadowColor; ctx.shadowColor = 'nope'; r.shadowColorKept = ctx.shadowColor;
    ctx.imageSmoothingEnabled = false; r.smoothingOff = ctx.imageSmoothingEnabled; ctx.imageSmoothingQuality = 'high'; r.qualityHigh = ctx.imageSmoothingQuality;
    ctx.strokeStyle = '#00ff00'; r.strokeStyleHex = ctx.strokeStyle; ctx.strokeStyle = 'bogus'; r.strokeStyleKept = ctx.strokeStyle;
    ctx.reset();
    // 2. Strokes: a 4px line with butt and square caps, and a dashed line.
    ctx.lineWidth = 4; ctx.strokeStyle = '#ff0000';
    ctx.beginPath(); ctx.moveTo(10, 5); ctx.lineTo(30, 5); ctx.stroke();
    ctx.lineCap = 'square'; ctx.beginPath(); ctx.moveTo(10, 15); ctx.lineTo(30, 15); ctx.stroke();
    r.caps = {buttInside: px(ctx, 20, 5), buttBeyond: px(ctx, 9, 5), squareBeyond: px(ctx, 9, 15), squareFar: px(ctx, 7, 15), edgeOutside: px(ctx, 20, 8)};
    ctx.lineCap = 'butt'; ctx.lineWidth = 2; ctx.setLineDash([4, 4]); ctx.strokeStyle = '#0000ff';
    ctx.beginPath(); ctx.moveTo(0, 25); ctx.lineTo(60, 25); ctx.stroke();
    r.dash = {on: px(ctx, 2, 25), off: px(ctx, 6, 25), on2: px(ctx, 10, 25)};
    ctx.lineDashOffset = 4; ctx.strokeStyle = '#00ff00'; ctx.beginPath(); ctx.moveTo(0, 35); ctx.lineTo(60, 35); ctx.stroke();
    r.dashOffset = {at2: px(ctx, 2, 35), at6: px(ctx, 6, 35)};
    // 3. Gradients.
    ctx.reset();
    const linear = ctx.createLinearGradient(0, 0, 60, 0); linear.addColorStop(0, '#ff0000'); linear.addColorStop(1, '#0000ff');
    ctx.fillStyle = linear; ctx.fillRect(0, 0, 60, 10);
    r.linear = {left: px(ctx, 0, 5), middle: px(ctx, 30, 5), right: px(ctx, 59, 5)};
    const radial = ctx.createRadialGradient(30, 20, 0, 30, 20, 10); radial.addColorStop(0, '#00ff00'); radial.addColorStop(1, '#000000');
    ctx.fillStyle = radial; ctx.fillRect(10, 10, 40, 20);
    r.radial = {centre: px(ctx, 30, 20), half: px(ctx, 35, 20), outside: px(ctx, 45, 20)};
    const conic = ctx.createConicGradient(0, 30, 35, 0); conic.addColorStop(0, '#ff0000'); conic.addColorStop(0.5, '#0000ff'); conic.addColorStop(1, '#ff0000');
    ctx.fillStyle = conic; ctx.fillRect(20, 30, 20, 10);
    r.conic = {east: px(ctx, 38, 35), west: px(ctx, 22, 35)};
    const empty = ctx.createLinearGradient(0, 0, 10, 0); ctx.fillStyle = empty; ctx.fillRect(0, 0, 10, 10); r.emptyGradient = px(ctx, 5, 5);
    r.addColorStopErrors = {below: thrown(() => linear.addColorStop(-0.1, 'red')), above: thrown(() => linear.addColorStop(1.1, 'red')),
      nan: thrown(() => linear.addColorStop(NaN, 'red')), color: thrown(() => linear.addColorStop(0.5, 'not a colour'))};
    r.createGradientNonFinite = thrown(() => ctx.createLinearGradient(NaN, 0, 1, 1));
    r.radialNegative = thrown(() => ctx.createRadialGradient(0, 0, -1, 0, 0, 1));
    r.fillStyleIsGradient = ctx.fillStyle === empty;
    // 4. Patterns from the 4x4 canvas.
    ctx.reset();
    const repeat = ctx.createPattern(s, 'repeat'); ctx.fillStyle = repeat; ctx.fillRect(0, 0, 20, 8);
    r.patternRepeat = {a: px(ctx, 0, 0), b: px(ctx, 3, 0), c: px(ctx, 4, 0), d: px(ctx, 6, 5)};
    const noRepeat = ctx.createPattern(s, 'no-repeat'); ctx.translate(20, 0); ctx.fillStyle = noRepeat; ctx.fillRect(0, 0, 20, 8); ctx.resetTransform();
    r.patternNoRepeat = {inside: px(ctx, 21, 1), outside: px(ctx, 30, 1)};
    const repeatX = ctx.createPattern(s, 'repeat-x'); ctx.translate(40, 0); ctx.fillStyle = repeatX; ctx.fillRect(0, 0, 20, 8); ctx.resetTransform();
    r.patternRepeatX = {row: px(ctx, 45, 1), below: px(ctx, 45, 6)};
    r.patternEmptyRepetition = ctx.createPattern(s, '') !== null;
    r.patternBadRepetition = thrown(() => ctx.createPattern(s, 'diagonal'));
    const scaled = ctx.createPattern(s, 'repeat'); scaled.setTransform({a: 4, d: 4}); ctx.imageSmoothingEnabled = false; ctx.fillStyle = scaled; ctx.fillRect(0, 10, 32, 16);
    r.patternScaled = {red: px(ctx, 3, 12), blue: px(ctx, 10, 12), redAgain: px(ctx, 17, 12)};
    r.patternSetTransformConflict = thrown(() => scaled.setTransform({a: 1, m11: 2}));
    const emptyCanvas = document.createElement('canvas'); emptyCanvas.width = 0;
    r.patternZeroSizeSource = thrown(() => ctx.createPattern(emptyCanvas, 'repeat'));
    ctx.strokeStyle = repeat; r.strokeStyleIsPattern = ctx.strokeStyle === repeat;
    // 5. Shadows.
    ctx.reset();
    ctx.shadowColor = '#0000ff'; ctx.shadowOffsetX = 20; ctx.shadowOffsetY = 0; ctx.fillStyle = '#ff0000'; ctx.fillRect(5, 5, 10, 10);
    r.shadow = {shape: px(ctx, 10, 10), shadow: px(ctx, 30, 10), none: px(ctx, 45, 10)};
    ctx.shadowBlur = 4; ctx.shadowOffsetX = 0; ctx.shadowOffsetY = 20; ctx.fillRect(40, 0, 10, 10);
    r.shadowBlurred = {centre: px(ctx, 45, 25), edgeOut: px(ctx, 45, 31), far: px(ctx, 45, 38)};
    ctx.reset(); ctx.shadowOffsetX = 20; ctx.fillStyle = '#ff0000'; ctx.fillRect(5, 5, 10, 10);
    r.shadowTransparentDefault = px(ctx, 30, 10);
    return r;
  }));
} finally { await browser.close(); }
writeFileSync(new URL('./red-chromium.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log(JSON.stringify(out));
