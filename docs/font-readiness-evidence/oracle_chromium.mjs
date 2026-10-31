// Chromium oracle for T01 font readiness: a CSS @font-face served late through page.route, plus a broken face.
// Usage: node oracle_chromium.mjs <Ahem.ttf> ; writes oracle-chromium.json next to this file.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const font = readFileSync(process.argv[2]);
const page = '<!doctype html><style>@font-face{font-family:RvLate;src:url(https://t01.test/ahem.ttf)}' +
  '@font-face{font-family:RvBroken;src:url(https://t01.test/broken.ttf)}' +
  '@font-face{font-family:RvMissing;src:url(https://t01.test/missing.ttf)}' +
  '#s{font:20px RvLate, monospace;white-space:pre}</style><body><span id=s>XXXX</span>';
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version(), steps: []};
const held = [];
try {
  const tab = await browser.newPage();
  await tab.route('https://t01.test/**', route => held.push(route));
  await tab.route('https://t01.page/', route => route.fulfill({status: 200, contentType: 'text/html', body: page}));
  await tab.addInitScript(() => {
    window.log = [];
    for (const kind of ['loading', 'loadingdone', 'loadingerror'])
      document.fonts.addEventListener(kind, e => log.push([kind, e.fontfaces.map(f => f.family + ':' + f.status)]));
    document.fonts.ready.then(() => log.push(['ready', document.fonts.status]));
    addEventListener('load', () => log.push(['window load', document.fonts.status]));
  });
  await tab.goto('https://t01.page/', {waitUntil: 'domcontentloaded'});
  const state = name => tab.evaluate(n => ({name: n, status: document.fonts.status, width: s.getBoundingClientRect().width,
    check: document.fonts.check('20px RvLate'), checkUnknown: document.fonts.check('20px NoSuchFamily'),
    faces: [...document.fonts].map(f => f.family + ':' + f.status), log: [...log]}), name);
  await tab.waitForTimeout(200);
  out.steps.push(await state('late font requested, response held'));
  await tab.evaluate(() => { document.fonts.ready.then(() => log.push(['ready (taken while loading)', document.fonts.status, s.getBoundingClientRect().width])); });
  out.checkSyntax = await tab.evaluate(() => { try { return document.fonts.check('not a font'); } catch (e) { return e.name; } });
  out.loadSyntax = await tab.evaluate(() => document.fonts.load('not a font').then(v => 'resolved ' + v.length, e => e.name));
  out.loadNoMatch = await tab.evaluate(() => document.fonts.load('20px NoSuchFamily').then(v => v.length, e => e.name));
  await tab.evaluate(() => { window.late = document.fonts.load('20px RvLate').then(v => ['resolved', v.map(f => f.family)], e => ['rejected', e.name]); });
  for (const route of held.splice(0)) await route.fulfill({status: 200, contentType: 'font/ttf', body: font});
  out.lateLoad = await tab.evaluate(() => late);
  await tab.waitForTimeout(200);
  out.steps.push(await state('late font served'));
  await tab.evaluate(() => {
    window.broken = document.fonts.load('20px RvBroken').then(v => ['resolved', v.length], e => ['rejected', e.name]);
    window.missing = document.fonts.load('20px RvMissing').then(v => ['resolved', v.length], e => ['rejected', e.name]);
  });
  await tab.waitForTimeout(100);
  for (const route of held.splice(0))
    route.request().url().endsWith('broken.ttf') ? await route.fulfill({status: 200, contentType: 'font/ttf', body: 'not a font'}) : await route.fulfill({status: 404, body: ''});
  out.brokenLoad = await tab.evaluate(() => broken);
  out.missingLoad = await tab.evaluate(() => missing);
  await tab.waitForTimeout(200);
  out.steps.push(await state('broken and missing settled'));
  out.loadSucceededAgain = await tab.evaluate(() => document.fonts.load('20px RvLate').then(v => v.map(f => f.status)));
} finally { await browser.close(); }
writeFileSync(new URL('./oracle-chromium.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log(JSON.stringify(out, null, 1));
