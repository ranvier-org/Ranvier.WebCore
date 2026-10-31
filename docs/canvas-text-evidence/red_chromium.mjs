// Chromium oracle for R05 canvas text: writes red-chromium.json next to this file.
// The page loads WebKit's pinned Ahem fixture as the @font-face family RvAhem from a data: URL, and waits for it through
// document.fonts.load before measuring. The native probe tests/abi/canvas_text.py replays the same steps on a 120x60 canvas.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const ahem = readFileSync('C:/wk/src/Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf').toString('base64');
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version()};
try {
  const context = await browser.newContext({viewport: {width: 320, height: 240}, deviceScaleFactor: 1});
  const tab = await context.newPage();
  await tab.setContent('<!doctype html><style>@font-face{font-family:RvAhem;src:url(data:font/ttf;base64,' + ahem + ')}'
    + 'html,body{margin:0;background:#fff}canvas{display:block}#c{width:120px;height:60px}</style>'
    + '<body><canvas id=c width=120 height=60></canvas><canvas id=r dir=rtl width=120 height=60></canvas>');
  Object.assign(out, await tab.evaluate(async () => {
    const px = (ctx, x, y) => Array.from(ctx.getImageData(x, y, 1, 1).data);
    const names = ['width', 'actualBoundingBoxLeft', 'actualBoundingBoxRight', 'fontBoundingBoxAscent', 'fontBoundingBoxDescent',
      'actualBoundingBoxAscent', 'actualBoundingBoxDescent', 'emHeightAscent', 'emHeightDescent', 'hangingBaseline',
      'alphabeticBaseline', 'ideographicBaseline'];
    const metrics = m => Object.fromEntries(names.map(n => [n, m[n]]));
    const r = {};
    const c = document.getElementById('c'), ctx = c.getContext('2d');
    const rtl = document.getElementById('r').getContext('2d');
    r.defaults = {font: ctx.font, textAlign: ctx.textAlign, textBaseline: ctx.textBaseline, direction: ctx.direction,
      letterSpacing: ctx.letterSpacing, wordSpacing: ctx.wordSpacing};
    r.loaded = (await document.fonts.load('20px RvAhem')).length;
    // 1. Setters and their validation.
    ctx.font = '20px RvAhem'; r.font = ctx.font;
    ctx.font = 'bogus'; r.fontKept = ctx.font;
    ctx.font = 'italic bold 20px/30px RvAhem'; r.fontShorthand = ctx.font;
    ctx.font = '1em RvAhem'; r.fontEm = ctx.font;
    ctx.textAlign = 'center'; r.textAlignCenter = ctx.textAlign; ctx.textAlign = 'middle'; r.textAlignKept = ctx.textAlign;
    ctx.textBaseline = 'top'; r.textBaselineTop = ctx.textBaseline;
    ctx.direction = 'rtl'; r.directionRtl = ctx.direction;
    ctx.letterSpacing = '2px'; r.letterSpacing = ctx.letterSpacing; ctx.letterSpacing = 'wide'; r.letterSpacingKept = ctx.letterSpacing;
    ctx.letterSpacing = '0.5em'; r.letterSpacingEm = ctx.letterSpacing;
    ctx.wordSpacing = '3px'; r.wordSpacing = ctx.wordSpacing; ctx.wordSpacing = '3'; r.wordSpacingKept = ctx.wordSpacing;
    ctx.reset(); r.afterReset = {font: ctx.font, textAlign: ctx.textAlign, textBaseline: ctx.textBaseline, direction: ctx.direction,
      letterSpacing: ctx.letterSpacing, wordSpacing: ctx.wordSpacing};
    ctx.save(); ctx.font = '20px RvAhem'; ctx.textAlign = 'end'; ctx.restore(); r.afterRestore = {font: ctx.font, textAlign: ctx.textAlign};
    // 2. Metrics of 20px Ahem: every glyph of 'X' fills the em box, 'p' its descent, 'É' its ascent.
    ctx.font = '20px RvAhem';
    r.measureX = metrics(ctx.measureText('XXX'));
    r.measureP = metrics(ctx.measureText('p'));
    r.measureE = metrics(ctx.measureText('É'));
    r.measureEmpty = metrics(ctx.measureText(''));
    r.measureSpace = metrics(ctx.measureText('X X'));
    for (const a of ['start', 'end', 'left', 'right', 'center']) { ctx.textAlign = a; r['align_' + a] = metrics(ctx.measureText('XX')); }
    ctx.textAlign = 'start';
    for (const b of ['top', 'hanging', 'middle', 'alphabetic', 'ideographic', 'bottom']) { ctx.textBaseline = b; r['baseline_' + b] = metrics(ctx.measureText('X')); }
    ctx.textBaseline = 'alphabetic';
    ctx.letterSpacing = '5px'; r.letterSpaced = metrics(ctx.measureText('XXX')); ctx.letterSpacing = '0px';
    ctx.wordSpacing = '7px'; r.wordSpaced = metrics(ctx.measureText('X X')); ctx.wordSpacing = '0px';
    ctx.direction = 'rtl'; r.rtlStart = metrics(ctx.measureText('XX')); ctx.direction = 'inherit';
    rtl.font = '20px RvAhem'; r.inheritRtl = {direction: rtl.direction, metrics: metrics(rtl.measureText('XX'))};
    // 3. Pixels, each sampled at least 2px from a glyph edge: fillText at an alphabetic baseline, maxWidth compression,
    // alignment, direction, strokeText and letter spacing.
    const at = (points) => points.map(([x, y]) => px(ctx, x, y));
    ctx.fillStyle = '#ff0000'; ctx.fillText('X', 10, 30);
    r.fill = at([[20, 22], [20, 16], [20, 32], [20, 11], [20, 37], [7, 22], [33, 22]]);
    ctx.clearRect(0, 0, 120, 60); ctx.fillText('XXXX', 0, 30, 40);
    r.maxWidth = at([[37, 22], [43, 22], [70, 22]]);
    ctx.clearRect(0, 0, 120, 60);
    ctx.fillText('XX', 0, 30, 0); ctx.fillText('XX', 0, 30, -1); ctx.fillText('XX', 0, 30, NaN);
    ctx.fillText('', 0, 30); ctx.fillText('X', NaN, 30);
    r.nothingDrawn = at([[10, 22], [30, 22]]);
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('X', 60, 30);
    r.centered = at([[60, 30], [52, 30], [47, 30], [68, 30], [73, 30], [60, 22], [60, 17], [60, 38], [60, 43]]);
    ctx.clearRect(0, 0, 120, 60); ctx.textAlign = 'start'; ctx.textBaseline = 'alphabetic';
    ctx.direction = 'rtl'; ctx.fillText('X', 100, 30); r.rtlFill = at([[90, 22], [103, 22], [77, 22]]);
    ctx.direction = 'inherit'; ctx.clearRect(0, 0, 120, 60);
    ctx.lineWidth = 2; ctx.strokeStyle = '#0000ff'; ctx.strokeText('X', 10, 30);
    r.stroke = at([[10, 22], [20, 22], [6, 22], [30, 22]]);
    ctx.clearRect(0, 0, 120, 60);
    ctx.letterSpacing = '10px'; ctx.fillText('XX', 0, 30); r.letterSpacedFill = at([[10, 22], [25, 22], [40, 22], [55, 22]]);
    ctx.letterSpacing = '0px';
    rtl.fillStyle = '#00ff00'; rtl.fillText('X', 100, 30);
    r.inheritRtlFill = [[90, 22], [103, 22], [77, 22]].map(([x, y]) => px(rtl, x, y));
    return r;
  }));
} finally { await browser.close(); }
writeFileSync(new URL('./red-chromium.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log(JSON.stringify(out).slice(0, 3000));
