// Chromium outcomes for tests/abi/url_wpt.py: writes tests/fixtures/url-wpt-chromium.json from the pinned WPT URL data in
// tests/fixtures/wpt/url. Each outcome has the shape the runtime probe records, so the two compare case by case.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const fixtures = new URL('../fixtures/', import.meta.url);
const read = name => JSON.parse(readFileSync(new URL('wpt/url/' + name, fixtures), 'utf8'));
const data = {urls: read('urltestdata.json').filter(e => typeof e === 'object'), setters: read('setters_tests.json'),
              patterns: read('urlpatterntestdata.json')};

function record({urls, setters, patterns}) {
  const fields = ['href', 'origin', 'protocol', 'username', 'password', 'host', 'hostname', 'port', 'pathname', 'search', 'hash'];
  const components = ['protocol', 'username', 'password', 'hostname', 'port', 'pathname', 'search', 'hash'];
  const attempt = f => { try { return f(); } catch (e) { return {error: e.name}; } };
  const snapshot = u => ({...Object.fromEntries(fields.map(k => [k, u[k]])), searchParams: u.searchParams.toString()});
  const url = urls.map(e => attempt(() => snapshot(e.base === null || e.base === undefined ? new URL(e.input) : new URL(e.input, e.base))));
  const setterResults = Object.fromEntries(Object.entries(setters).filter(([g]) => g !== 'comment').map(([group, cases]) =>
    [group, cases.map(c => {
      let u;
      try { u = new URL(c.href); } catch (e) { return {base: {error: e.name}}; }
      const threw = attempt(() => { u[group] = c.new_value; return null; });
      return {threw: threw === null ? null : threw.error, url: snapshot(u)};
    })]));
  const groups = g => Object.entries(g).map(([k, v]) => [k, v === undefined ? null : v]);
  const execResult = r => r === null ? null : {
    inputs: r.inputs.map(i => typeof i === 'string' ? i : Object.fromEntries(Object.entries(i).filter(([, v]) => v !== undefined))),
    ...Object.fromEntries(components.map(c => [c, {input: r[c].input, groups: groups(r[c].groups)}])),
  };
  const urlpattern = patterns.map(entry => {
    let pattern;
    try { pattern = new URLPattern(...entry.pattern); } catch (e) { return {ctor: {error: e.name}}; }
    const out = {ctor: Object.fromEntries(components.map(c => [c, pattern[c]]))};
    if ('inputs' in entry || (entry.expected_match !== undefined && entry.expected_match !== null)) {
      const inputs = entry.inputs || [];
      out.test = attempt(() => pattern.test(...inputs));
      out.exec = attempt(() => execResult(pattern.exec(...inputs)));
    }
    return out;
  });
  // The harness derives a default component from the pattern's baseURL with this engine's URL parser.
  const patternBases = patterns.map(entry => {
    const p = entry.pattern;
    const base = p.length > 0 && typeof p[0] === 'object' && p[0].baseURL ? p[0].baseURL
      : p.length > 1 && typeof p[1] === 'string' ? p[1] : null;
    if (base === null) return null;
    return attempt(() => { const u = new URL(base); return Object.fromEntries(components.map(c => [c, u[c]])); });
  });
  return {url, setters: setterResults, urlpattern, patternBases};
}

const browser = await chromium.launch({headless: true});
try {
  const tab = await (await browser.newContext()).newPage();
  const result = await tab.evaluate(record, data);
  const commit = readFileSync(new URL('wpt/url/WPT_COMMIT.txt', fixtures), 'utf8').trim();
  writeFileSync(new URL('url-wpt-chromium.json', fixtures), JSON.stringify({browser: browser.version(), wpt: commit, ...result}) + '\n');
  console.log('url wpt chromium', browser.version(), result.url.length, Object.keys(result.setters).length, result.urlpattern.length);
} finally {
  await browser.close();
}
