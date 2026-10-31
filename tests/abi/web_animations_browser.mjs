// Chromium oracle for tests/abi/web_animations.py: writes tests/fixtures/web-animations-oracle.json.
// Replays tests/fixtures/web-animations-cases.json: each case creates an animation, pauses it, and at each seek time
// records the play state, current time, computed values and the rendered pixels at the element's static and current
// centres. The error cases record whether creation threw and the exception name.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
import {inflateSync} from 'node:zlib';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const spec = JSON.parse(readFileSync(new URL('../fixtures/web-animations-cases.json', import.meta.url), 'utf8'));

// Reads an 8-bit RGB or RGBA non-interlaced PNG, as Playwright writes them.
function decodePng(buffer) {
  let pos = 8, width = 0, height = 0, channels = 0;
  const idat = [];
  while (pos < buffer.length) {
    const length = buffer.readUInt32BE(pos), kind = buffer.toString('ascii', pos + 4, pos + 8);
    const body = buffer.subarray(pos + 8, pos + 8 + length);
    if (kind === 'IHDR') { width = body.readUInt32BE(0); height = body.readUInt32BE(4); channels = body[9] === 6 ? 4 : 3; }
    if (kind === 'IDAT') idat.push(body);
    pos += 12 + length;
  }
  const raw = inflateSync(Buffer.concat(idat)), stride = width * channels, rows = [];
  let prev = new Uint8Array(stride);
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)], line = Uint8Array.from(raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1)));
    for (let i = 0; i < stride; i++) {
      const a = i >= channels ? line[i - channels] : 0, b = prev[i], c = i >= channels ? prev[i - channels] : 0;
      const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
      const predictor = [0, a, b, (a + b) >> 1, pa <= pb && pa <= pc ? a : pb <= pc ? b : c][filter];
      line[i] = (line[i] + predictor) & 255;
    }
    rows.push(line); prev = line;
  }
  return (x, y) => Array.from(rows[y].subarray(x * channels, x * channels + 3));
}

const browser = await chromium.launch({headless: true});
const out = {browser: 'Chromium ' + browser.version(), cases: [], errors: []};
try {
  const context = await browser.newContext({viewport: {width: 320, height: 240}, deviceScaleFactor: 1});
  const tab = await context.newPage();
  await tab.setContent(spec.markup);
  await tab.evaluate(() => {
    window.toKeyframes = (list) => list === null ? null : list.map((k) => {
      const o = {...k.props};
      if ('offset' in k) o.offset = k.offset === 'NaN' ? NaN : k.offset;
      if ('easing' in k) o.easing = k.easing;
      if ('composite' in k) o.composite = k.composite;
      return o;
    });
    window.toOptions = (o) => o === 'NaN' ? NaN : o;
    window.centre = (r) => [Math.floor(r.x + r.width / 2), Math.floor(r.y + r.height / 2)];
  });
  for (const c of spec.cases) {
    const created = await tab.evaluate((c) => {
      const el = document.getElementById(c.el);
      window.staticCentre = centre(el.getBoundingClientRect());
      const keyframes = toKeyframes(c.keyframes), options = toOptions(c.options);
      let anim;
      if (c.kind === 'animate') anim = el.animate(keyframes, options);
      else if (c.kind === 'animate-timeline') anim = el.animate(keyframes, {...options, timeline: document.timeline});
      else if (c.kind === 'construct') anim = new Animation(new KeyframeEffect(el, keyframes, options), document.timeline);
      else if (c.kind === 'construct-default') anim = new Animation(new KeyframeEffect(el, keyframes, options));
      else anim = new Animation(new KeyframeEffect(new KeyframeEffect(el, keyframes, options)), document.timeline);
      anim.pause();
      window.held = anim;
      return {id: anim.id, playState: anim.playState, timelineIsDocument: anim.timeline === document.timeline,
        target: anim.effect.target ? anim.effect.target.id : null, composite: anim.effect.composite,
        iterationComposite: anim.effect.iterationComposite, pseudoElement: anim.effect.pseudoElement};
    }, c);
    const points = [];
    for (const time of c.times) {
      const point = await tab.evaluate(({c, time}) => {
        const el = document.getElementById(c.el);
        held.currentTime = time;
        const cs = getComputedStyle(el);
        return {time, currentTime: held.currentTime, playState: held.playState,
          values: Object.fromEntries(c.props.map((p) => [p, cs.getPropertyValue(p)])),
          samples: [staticCentre, centre(el.getBoundingClientRect())]};
      }, {c, time});
      const pixel = decodePng(await tab.screenshot({clip: {x: 0, y: 0, width: 320, height: 240}}));
      point.samples = point.samples.map(([x, y]) => ({x, y, rgb: x >= 0 && y >= 0 && x < 320 && y < 240 ? pixel(x, y) : null}));
      points.push(point);
    }
    await tab.evaluate(() => held.cancel());
    out.cases.push({name: c.name, created, points});
  }
  for (const e of spec.errors) {
    out.errors.push({name: e.name, ...await tab.evaluate((e) => {
      const el = document.getElementById('a');
      try {
        let anim;
        const keyframes = toKeyframes(e.keyframes), options = toOptions(e.options);
        if (e.kind === 'effect') anim = new Animation(new KeyframeEffect(el, keyframes, options));
        else if (e.kind === 'effect-null-target') anim = new Animation(new KeyframeEffect(null, keyframes, options));
        else if (e.kind === 'animation-empty') anim = new Animation();
        else if (e.kind === 'animation-null-timeline') { anim = new Animation(new KeyframeEffect(el, keyframes, options), null); anim.play(); }
        else anim = el.animate(keyframes, options);
        const result = {ok: true, playState: anim.playState, hasEffect: anim.effect !== null,
          timeline: anim.timeline === null ? 'null' : anim.timeline === document.timeline ? 'document' : 'other',
          currentTime: anim.currentTime, keyframes: anim.effect ? anim.effect.getKeyframes().length : null};
        anim.cancel();
        return result;
      } catch (error) {
        return {ok: false, exception: error.name};
      }
    }, e)});
  }
} finally {
  await browser.close();
}
writeFileSync(process.env.ORACLE_OUT || new URL('../fixtures/web-animations-oracle.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log(`oracle: ${out.cases.length} cases, ${out.errors.length} error cases`);
