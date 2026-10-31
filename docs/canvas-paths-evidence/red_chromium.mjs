// Chromium oracle for R02 canvas paths and hit testing: writes red-chromium.json next to this file.
// The native probe tests/abi/canvas_paths.py replays the same drawing on a 60x40 canvas and compares interior pixels only.
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
    const thrown = f => { try { f(); return null; } catch (e) { return e.name; } };
    const r = {};
    const c = document.getElementById('c');
    const ctx = c.getContext('2d');
    // 1. Current path: a triangle filled red, hit tested against fill and stroke.
    ctx.beginPath(); ctx.moveTo(10, 10); ctx.lineTo(50, 10); ctx.lineTo(30, 30); ctx.closePath();
    ctx.fillStyle = '#ff0000'; ctx.fill();
    r.triangle = {inside: px(ctx, 30, 15), outside: px(ctx, 5, 35),
      hitInside: ctx.isPointInPath(30, 15), hitOutside: ctx.isPointInPath(5, 35),
      strokeOnEdge: ctx.isPointInStroke(30, 10), strokeInside: ctx.isPointInStroke(30, 15)};
    // 2. beginPath empties the current path.
    ctx.beginPath(); r.afterBeginPath = ctx.isPointInPath(30, 15);
    // 3. Path2D reuse: a 10x10 square filled blue at the origin, then added to another path translated by 40.
    const square = new Path2D(); square.rect(0, 0, 10, 10);
    ctx.fillStyle = 'rgb(0, 0, 255)'; ctx.fill(square);
    const moved = new Path2D(); moved.addPath(square, {e: 40, f: 0});
    ctx.fillStyle = '#00ff00'; ctx.fill(moved);
    r.reuse = {square: px(ctx, 5, 5), moved: px(ctx, 45, 5), between: px(ctx, 25, 5),
      hitSquare: ctx.isPointInPath(square, 5, 5), hitMovedAtOrigin: ctx.isPointInPath(moved, 5, 5), hitMoved: ctx.isPointInPath(moved, 45, 5),
      squareUnchanged: ctx.isPointInPath(square, 45, 5)};
    // 4. SVG path data, the copy constructor, and independence of the copy.
    const fromData = new Path2D('M20 20 h10 v10 h-10 Z');
    const copy = new Path2D(fromData); fromData.rect(50, 30, 5, 5);
    r.pathData = {inside: ctx.isPointInPath(fromData, 25, 25), outside: ctx.isPointInPath(fromData, 35, 25),
      copyInside: ctx.isPointInPath(copy, 25, 25), copyMissesLaterRect: ctx.isPointInPath(copy, 52, 32), originalHasLaterRect: ctx.isPointInPath(fromData, 52, 32)};
    r.invalidPathData = {threw: thrown(() => new Path2D('M 0 0 L bogus')), hit: ctx.isPointInPath(new Path2D('M 0 0 L bogus'), 0, 0)};
    // 5. Fill rules: two nested squares, same winding.
    const nested = new Path2D(); nested.rect(0, 20, 20, 20); nested.rect(5, 25, 10, 10);
    r.fillRule = {nonzero: ctx.isPointInPath(nested, 10, 30), evenodd: ctx.isPointInPath(nested, 10, 30, 'evenodd'),
      ring: ctx.isPointInPath(nested, 2, 30, 'evenodd')};
    ctx.fillStyle = '#ffff00'; ctx.fill(nested, 'evenodd');
    r.fillRule.ringPixel = px(ctx, 2, 30); r.fillRule.holePixel = px(ctx, 10, 30);
    // 6. Curves, arcs and rounded rectangles as hit tests on the current path.
    const hits = (build, pts) => { ctx.beginPath(); build(); return pts.map(([x, y]) => ctx.isPointInPath(x, y)); };
    r.shapes = {
      arc: hits(() => ctx.arc(30, 20, 10, 0, Math.PI * 2), [[30, 20], [30, 32], [37, 20]]),
      halfArc: hits(() => { ctx.arc(30, 20, 10, 0, Math.PI); }, [[30, 25], [30, 15]]),
      anticlockwiseArc: hits(() => { ctx.arc(30, 20, 10, 0, Math.PI, true); }, [[30, 25], [30, 15]]),
      ellipse: hits(() => ctx.ellipse(30, 20, 20, 5, 0, 0, Math.PI * 2), [[45, 20], [30, 24], [30, 27]]),
      rotatedEllipse: hits(() => ctx.ellipse(30, 20, 20, 5, Math.PI / 2, 0, Math.PI * 2), [[45, 20], [30, 35]]),
      quadratic: hits(() => { ctx.moveTo(0, 0); ctx.quadraticCurveTo(30, 40, 60, 0); ctx.closePath(); }, [[30, 10], [30, 25]]),
      bezier: hits(() => { ctx.moveTo(0, 0); ctx.bezierCurveTo(0, 40, 60, 40, 60, 0); ctx.closePath(); }, [[30, 20], [30, 35]]),
      arcTo: hits(() => { ctx.moveTo(0, 0); ctx.arcTo(40, 0, 40, 40, 20); ctx.lineTo(40, 40); ctx.lineTo(0, 40); ctx.closePath(); }, [[10, 10], [38, 2], [25, 5]]),
      rect: hits(() => ctx.rect(10, 10, 20, 10), [[15, 15], [35, 15]]),
      roundRectList: hits(() => ctx.roundRect(0, 0, 40, 40, [10]), [[1, 1], [20, 20], [5, 20]]),
      roundRectValue: hits(() => ctx.roundRect(0, 0, 40, 40, 10), [[1, 1], [20, 20]]),
      roundRectPoint: hits(() => ctx.roundRect(0, 0, 40, 40, {x: 20, y: 5}), [[2, 10], [2, 2], [20, 20]]),
      roundRectFour: hits(() => ctx.roundRect(0, 0, 40, 40, [0, 0, 0, 20]), [[1, 1], [39, 39], [1, 39]]),
    };
    // 7. Argument errors and non-finite values.
    r.errors = {
      arcNegative: thrown(() => ctx.arc(0, 0, -1, 0, 1)),
      ellipseNegative: thrown(() => ctx.ellipse(0, 0, -1, 1, 0, 0, 1)),
      arcToNegative: thrown(() => ctx.arcTo(0, 0, 1, 1, -1)),
      roundRectNegative: thrown(() => ctx.roundRect(0, 0, 10, 10, [-1])),
      roundRectFive: thrown(() => ctx.roundRect(0, 0, 10, 10, [1, 2, 3, 4, 5])),
      roundRectEmpty: thrown(() => ctx.roundRect(0, 0, 10, 10, [])),
      addPathConflict: thrown(() => new Path2D().addPath(square, {a: 1, m11: 2})),
      addPathNonFinite: thrown(() => new Path2D().addPath(square, {a: NaN})),
    };
    ctx.beginPath(); ctx.rect(0, 0, 10, 10); ctx.lineTo(NaN, 5); ctx.moveTo(Infinity, 0);
    r.nonFinite = {pathKept: ctx.isPointInPath(5, 5), hitNaN: ctx.isPointInPath(NaN, 5), strokeNaN: ctx.isPointInStroke(5, NaN)};
    // 8. Clip to a path: only the clipped square receives the fill.
    c.width = c.width;
    const clipSquare = new Path2D(); clipSquare.rect(20, 10, 20, 20);
    ctx.clip(clipSquare); ctx.fillStyle = '#ff0000'; ctx.fillRect(0, 0, 60, 40);
    r.clip = {inside: px(ctx, 30, 20), outside: px(ctx, 5, 5)};
    // clip(fillRule) on the current path; resetting the bitmap clears the earlier clip.
    c.width = c.width;
    ctx.beginPath(); ctx.rect(0, 0, 30, 40); ctx.clip('nonzero'); ctx.fillStyle = 'rgb(0, 0, 255)'; ctx.fillRect(0, 0, 60, 40);
    r.clipCurrent = {inside: px(ctx, 10, 20), outside: px(ctx, 45, 20)};
    // 9. Stroke and strokeRect at the default 1px width on pixel centres; isPointInStroke on a Path2D.
    c.width = c.width;
    const line = new Path2D(); line.moveTo(0, 5.5); line.lineTo(60, 5.5);
    ctx.stroke(line);
    ctx.strokeRect(10.5, 10.5, 20, 20);
    ctx.beginPath(); ctx.moveTo(0, 35.5); ctx.lineTo(60, 35.5); ctx.stroke();
    r.stroke = {line: px(ctx, 30, 5), belowLine: px(ctx, 30, 7), rectEdge: px(ctx, 10, 20), rectInside: px(ctx, 20, 20), current: px(ctx, 30, 35),
      hitLine: ctx.isPointInStroke(line, 30, 5.5), missLine: ctx.isPointInStroke(line, 30, 8)};
    return r;
  }));
} finally { await browser.close(); }
writeFileSync(new URL('./red-chromium.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log(JSON.stringify(out));
