// RED survey of IntersectionObserver in Chromium: writes chromium.json next to this file.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const page = `<!doctype html><style>html,body{margin:0}body{width:600px;height:2000px;position:relative}
#far{position:absolute;left:10px;top:400px;width:50px;height:50px}
#s{position:absolute;left:100px;top:20px;width:200px;height:100px;overflow:auto}
#s>.pad{height:500px;position:relative}
#u{position:absolute;left:10px;top:150px;width:50px;height:50px}
#x{position:absolute;left:10px;top:150px;width:50px;height:50px}
#c{position:absolute;left:10px;top:10px;width:80px;height:100px;overflow:hidden}
#c>.pad{height:300px;position:relative}
#v{position:absolute;left:0;top:110px;width:50px;height:50px}
#r{position:absolute;left:400px;top:0;width:10px;height:10px}</style>
<body><div id=far></div><div id=s><div class=pad><div id=u></div></div></div><div id=x></div>
<div id=c><div class=pad><div id=v></div></div></div><div id=r></div>`;
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version(), steps: []};
try {
  const context = await browser.newContext({viewport: {width: 320, height: 240}, deviceScaleFactor: 1});
  const tab = await context.newPage();
  await tab.setContent(page);
  out.members = await tab.evaluate(() => ({
    scrollMargin: 'scrollMargin' in IntersectionObserver.prototype, takeRecords: 'takeRecords' in IntersectionObserver.prototype,
    delay: 'delay' in IntersectionObserver.prototype, trackVisibility: 'trackVisibility' in IntersectionObserver.prototype}));
  await tab.evaluate(() => {
    const rect = r => r ? [r.x, r.y, r.width, r.height] : null;
    const entry = e => ({target: e.target.id, time: e.time, rootBounds: rect(e.rootBounds), boundingClientRect: rect(e.boundingClientRect),
      intersectionRect: rect(e.intersectionRect), isIntersecting: e.isIntersecting, intersectionRatio: e.intersectionRatio});
    window.log = [];
    window.entry = entry;
    window.keep = {u, s};
    const make = (name, options) => {
      const io = new IntersectionObserver(entries => {
        const now = performance.now();
        window.log.push({kind: 'io', name, now, entries: entries.map(entry)});
        const other = window.takePair && window.takePair[name];
        if (other) {
          window.takePair = null;
          const taken = window.io[other].takeRecords();
          window.log.push({kind: 'taken', from: other, entries: taken.map(entry)});
        }
      }, options);
      io.label = name;
      return io;
    };
    window.io = {
      implicit: make('implicit', {threshold: [0, 0.5, 1]}),
      docroot: make('docroot', {root: document, rootMargin: '10%', threshold: [0, 0.5, 1]}),
      element: make('element', {root: s, rootMargin: '10px', threshold: [0, 0.5, 1]}),
      elementPct: make('elementPct', {root: s, rootMargin: '10% 0px', threshold: [0]}),
      scroll20: make('scroll20', {scrollMargin: '20px', threshold: [0, 0.2]}),
      scroll0: make('scroll0', {threshold: [0, 0.2]}),
    };
    window.margins = Object.fromEntries(Object.entries(window.io).map(([k, v]) => [k, [v.rootMargin, v.scrollMargin, v.thresholds, v.root ? (v.root.id || v.root.nodeName) : null]]));
    const ro = new ResizeObserver(() => window.log.push({kind: 'ro', now: performance.now()}));
    ro.observe(r);
    const raf = () => { window.log.push({kind: 'raf', now: performance.now()}); };
    requestAnimationFrame(raf);
    window.io.implicit.observe(far);
    window.io.docroot.observe(far);
    window.io.element.observe(u);
    window.io.element.observe(x);
    window.io.elementPct.observe(u);
    window.io.scroll20.observe(v);
    window.io.scroll0.observe(v);
  });
  const settle = () => tab.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 30)))));
  const step = async (name, act) => {
    await tab.evaluate(() => { window.log = []; window.before = performance.now(); });
    const result = await tab.evaluate(act);
    await settle();
    const s = await tab.evaluate(() => ({log: window.log, before: window.before, after: performance.now()}));
    out.steps.push({name, result, ...s});
  };
  await step('initial', () => null);
  out.margins = await tab.evaluate(() => window.margins);
  await step('scroll window 0,200', () => scrollTo(0, 200));
  await step('scroll #s to 100', () => { s.scrollTop = 100; });
  await step('scroll #s to 165 (u 0.9)', () => { s.scrollTop = 165; });
  await step('takeRecords of the other observer inside the first callback: window 0,0', () => { window.takePair = {implicit: 'docroot', docroot: 'implicit'}; scrollTo(0, 0); });
  await step('takeRecords synchronously after a layout change', () => { scrollTo(0, 200); return window.io.implicit.takeRecords().map(window.entry); });
  await step('unobserve far on implicit, scroll 0,0', () => { window.io.implicit.unobserve(far); scrollTo(0, 0); });
  await step('remove intersecting #u from the DOM', () => { u.remove(); });
  await step('disconnect element; takeRecords after', () => { window.io.element.disconnect(); s.scrollTop = 50; return window.io.element.takeRecords().length; });
  await step('observe x with non-ancestor root again, change x', () => { window.io.element.observe(x); x.style.top = '20px'; });
  await step('reinsert #u, scroll #s to 100', () => { keep.s.firstElementChild.appendChild(keep.u); keep.s.scrollTop = 100; });
  await step('root #s removed from DOM while u intersects', () => { keep.s.remove(); });
  await step('observe then unobserve before a rendering update', () => { window.io.implicit.observe(far); window.io.implicit.unobserve(far); });
} finally { await browser.close(); }
writeFileSync(new URL('./chromium.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log(JSON.stringify(out, null, 0).slice(0, 200));
