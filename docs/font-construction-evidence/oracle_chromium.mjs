// Chromium oracle for T02 font construction/registration: FontFace from bytes (TTF, CFF OTF, WOFF, WOFF2, invalid,
// empty) and from URL sources served through page.route, descriptor getters/setters and their errors, load/loaded,
// FontFaceSet add/delete/clear/has/size/iteration with CSS-connected faces, measurement, and a reload.
// Usage: node oracle_chromium.mjs <webkit-source> ; writes oracle-chromium.json next to this file.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const source = process.argv[2];
const files = {
  ahemTtf: 'Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf',
  ahemCff: 'Tools/TestWebKitAPI/Resources/cocoa/Ahem-CFF.otf',
  robotoOtf: 'Source/ThirdParty/skia/modules/canvaskit/tests/assets/Roboto-Regular.otf',
  robotoWoff: 'Source/ThirdParty/skia/modules/canvaskit/tests/assets/Roboto-Regular.woff',
  robotoWoff2: 'Source/ThirdParty/skia/modules/canvaskit/tests/assets/Roboto-Regular.woff2',
};
const bytes = Object.fromEntries(Object.entries(files).map(([k, p]) => [k, [...readFileSync(source + '/' + p)]]));
const ahem = readFileSync(source + '/' + files.ahemTtf);
const page = '<!doctype html><style>@font-face{font-family:RvCss;src:url(https://t02.test/css.ttf)}' +
  '#s{font:20px monospace;white-space:pre}</style><body><span id=s>XXXX</span>';
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version()};
const held = [];
try {
  const tab = await browser.newPage();
  await tab.route('https://t02.test/**', route => held.push(route));
  await tab.route('https://t02.page/', route => route.fulfill({status: 200, contentType: 'text/html', body: page}));
  await tab.goto('https://t02.page/', {waitUntil: 'domcontentloaded'});
  await tab.evaluate(b => { window.fixtures = Object.fromEntries(Object.entries(b).map(([k, v]) => [k, new Uint8Array(v)])); }, bytes);
  await tab.evaluate(() => {
    window.settle = p => p.then(f => ['resolved', f.status], e => ['rejected', e.name]);
    window.width = family => { s.style.fontFamily = family + ', monospace'; return s.getBoundingClientRect().width; };
  });
  out.fallbackWidth = await tab.evaluate(() => width('NoSuchFamily'));
  // Byte sources: status right after construction, then the loaded promise.
  out.bytes = await tab.evaluate(async () => {
    const result = {};
    const cases = {...fixtures, invalid: new TextEncoder().encode('not a font'), empty: new Uint8Array(0),
      arrayBuffer: fixtures.ahemTtf.buffer.slice(0)};
    for (const [name, data] of Object.entries(cases)) {
      const face = new FontFace('RvBytes_' + name, data);
      const initial = face.status;
      result[name] = {initial, loaded: await settle(face.loaded), status: face.status};
    }
    return result;
  });
  // Descriptors: defaults, normalisation, constructor errors and setter errors.
  out.descriptors = await tab.evaluate(async () => {
    const face = new FontFace('RvDesc', fixtures.ahemTtf, {weight: 'bold', style: 'italic', stretch: 'condensed',
      unicodeRange: 'U+0-7F', featureSettings: '"liga" 0', display: 'swap', sizeAdjust: '90%'});
    const read = f => ({family: f.family, style: f.style, weight: f.weight, stretch: f.stretch, unicodeRange: f.unicodeRange,
      featureSettings: f.featureSettings, display: f.display, sizeAdjust: f.sizeAdjust, ascentOverride: f.ascentOverride});
    const defaults = read(new FontFace('RvDefault', fixtures.ahemTtf));
    const given = read(face);
    const errors = {};
    for (const [key, value] of [['weight', 'heavy'], ['style', 'sideways'], ['stretch', 'wide'], ['unicodeRange', 'U+ZZ'],
                                ['display', 'later'], ['featureSettings', 'liga'], ['sizeAdjust', '-5%']]) {
      const bad = new FontFace('RvBad_' + key, fixtures.ahemTtf, {[key]: value});
      errors[key] = {status: bad.status, loaded: await settle(bad.loaded)};
    }
    const setters = {};
    for (const [key, value] of [['weight', '300'], ['weight', 'heavy'], ['style', 'oblique 10deg'], ['family', 'Renamed'],
                                ['unicodeRange', 'U+20-7E'], ['display', 'later']]) {
      try { face[key] = value; setters[key + '=' + value] = ['ok', face[key]]; } catch (e) { setters[key + '=' + value] = ['threw', e.name, face[key]]; }
    }
    const nulFamily = new FontFace('Rv\u0000Nul', fixtures.ahemTtf).family;
    const badSource = new FontFace('RvBadSource', 'nonsense(');
    const urlBad = new FontFace('RvUrlBad', 'url(https://t02.test/never.ttf)', {weight: 'heavy'});
    const urlBadDescriptor = {status: urlBad.status, load: await settle(urlBad.load())};
    return {defaults, given, errors, setters, nulFamily, urlBadDescriptor, badSource: {status: badSource.status, loaded: await settle(badSource.loaded)}};
  });
  // URL sources served late.
  await tab.evaluate(() => {
    window.urlFace = new FontFace('RvUrl', 'url(https://t02.test/ahem.ttf)');
    window.missingFace = new FontFace('RvMissingUrl', 'url(https://t02.test/missing.ttf)');
    window.brokenFace = new FontFace('RvBrokenUrl', 'url(https://t02.test/broken.ttf) format("truetype")');
    window.skippedFace = new FontFace('RvSkipped', 'url(https://t02.test/eot.eot) format("embedded-opentype"), url(https://t02.test/ahem2.ttf)');
    window.urlLog = {initial: [urlFace.status, missingFace.status, brokenFace.status, skippedFace.status]};
    window.urlLoad = settle(urlFace.load());
    urlLog.afterLoad = urlFace.status;
    window.missingLoad = settle(missingFace.load());
    window.brokenLoad = settle(brokenFace.load());
    window.skippedLoad = settle(skippedFace.load());
    urlLog.checkWhileLoading = document.fonts.check('20px RvUrl');
  });
  await tab.waitForTimeout(200);
  out.requested = held.map(r => r.request().url());
  for (const route of held.splice(0)) {
    const url = route.request().url();
    if (url.endsWith('missing.ttf')) await route.fulfill({status: 404, body: ''});
    else if (url.endsWith('broken.ttf')) await route.fulfill({status: 200, contentType: 'font/ttf', body: 'not a font'});
    else if (url.endsWith('css.ttf')) held.push(route);
    else await route.fulfill({status: 200, contentType: 'font/ttf', body: ahem});
  }
  out.url = await tab.evaluate(async () => ({...urlLog, url: await urlLoad, missing: await missingLoad, broken: await brokenLoad,
    skipped: await skippedLoad, reloadFailed: await settle(missingFace.load()), loadAgain: await settle(urlFace.load()),
    statuses: [urlFace.status, missingFace.status, brokenFace.status, skippedFace.status]}));
  // FontFaceSet registration with a CSS-connected face present.
  out.set = await tab.evaluate(async () => {
    const r = {};
    const names = () => [...document.fonts].map(f => f.family);
    r.initial = {size: document.fonts.size, names: names()};
    const css = [...document.fonts][0];
    const a = new FontFace('RvAdded', fixtures.ahemTtf);
    const b = new FontFace('RvSecond', fixtures.robotoWoff2);
    r.widthBefore = width('RvAdded');
    r.checkBefore = document.fonts.check('20px RvAdded');
    r.addReturnsSet = document.fonts.add(a) === document.fonts;
    document.fonts.add(b);
    document.fonts.add(a);
    r.afterAdd = {size: document.fonts.size, names: names(), hasA: document.fonts.has(a), hasCss: document.fonts.has(css)};
    r.widthAfterAdd = width('RvAdded');
    r.checkAfterAdd = document.fonts.check('20px RvAdded');
    r.addUrlUnloaded = (() => { const u = new FontFace('RvLazy', 'url(https://t02.test/lazy.ttf)'); document.fonts.add(u);
      return {status: u.status, check: document.fonts.check('20px RvLazy')}; })();
    try { document.fonts.add(css); r.addCss = 'ok'; } catch (e) { r.addCss = e.name; }
    r.deleteCss = document.fonts.delete(css);
    r.deleteA = document.fonts.delete(a);
    r.deleteAgain = document.fonts.delete(a);
    r.afterDelete = {size: document.fonts.size, names: names()};
    r.widthAfterDelete = width('RvAdded');
    document.fonts.add(a);
    document.fonts.clear();
    r.afterClear = {size: document.fonts.size, names: names(), hasA: document.fonts.has(a), statusA: a.status};
    r.widthAfterClear = width('RvAdded');
    return r;
  });
  for (const route of held.splice(0)) await route.fulfill({status: 404, body: ''});
  // Reload: the new document's set holds only its own CSS faces.
  await tab.reload({waitUntil: 'domcontentloaded'});
  out.reload = await tab.evaluate(() => ({size: document.fonts.size, names: [...document.fonts].map(f => f.family + ':' + f.status)}));
  for (const route of held.splice(0)) await route.fulfill({status: 404, body: ''});
} finally { await browser.close(); }
writeFileSync(new URL('./oracle-chromium.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log(JSON.stringify(out, null, 1));
