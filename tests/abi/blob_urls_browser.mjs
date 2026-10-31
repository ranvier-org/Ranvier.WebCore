// Chromium oracle for tests/abi/blob_urls.py: replays tests/fixtures/blob-urls-cases.json and writes
// tests/fixtures/blob-urls-oracle.json. Records object URL format and lifetime, blob: image loads and reads, FileReader
// event order and state, Blob.text/arrayBuffer/bytes, file-backed blobs, cross-page isolation and teardown.
// Progress events are collapsed: consecutive events of one type are recorded once.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync, mkdtempSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const cases = JSON.parse(readFileSync(new URL('../fixtures/blob-urls-cases.json', import.meta.url), 'utf8'));

// Runs in the page.
const measure = async cases => {
  const bytesOf = hex => { const out = new Uint8Array(hex.length / 2); for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16); return out; };
  const make = name => {
    const spec = cases.blobs[name];
    const parts = spec.parts.map(p => p.text !== undefined ? p.text : p.hex !== undefined ? bytesOf(p.hex) : new Uint8Array(p.count).fill(parseInt(p.repeat, 16)));
    return new Blob(parts, {type: spec.type});
  };
  const hex = bytes => [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');
  const checksum = bytes => { let sum = 0; for (const b of bytes) sum = (sum * 33 + b) >>> 0; return sum; };
  const describeBytes = async bytes => bytes.length <= 64 ? {length: bytes.length, hex: hex(bytes)} : {length: bytes.length, checksum: checksum(bytes)};
  const describeResult = async value => value === null ? {kind: 'null'} : value instanceof ArrayBuffer
    ? {kind: 'bytes', ...(await describeBytes(new Uint8Array(value)))} : {kind: 'string', value};
  const kind = value => value === null ? 'null' : value instanceof ArrayBuffer ? 'bytes' : 'string';
  const result = {};
  const bounded = (promise, value) => Promise.race([promise, new Promise(r => setTimeout(() => r(value), 3000))]);

  const read = spec => new Promise(resolve => {
    const r = new FileReader();
    const events = [], states = {};
    let threw = null, second = null, acted = false;
    const act = () => {
      acted = true;
      if (spec.action === 'abort') r.abort();
      else try { r.readAsText(make('y')); second = 'ok'; } catch (e) { second = e.name; }
    };
    let ends = 0;
    for (const type of ['loadstart', 'progress', 'load', 'abort', 'error', 'loadend'])
      r.addEventListener(type, () => {
        if (events[events.length - 1] !== type) events.push(type);
        if (!(type in states)) states[type] = {readyState: r.readyState, result: kind(r.result), error: r.error && r.error.name};
        if (spec.hook === type && !acted) { act(); events.push('acted'); }
        if (type === 'loadend' && ++ends === (spec.action === 'readY' && spec.hook === 'loadend' ? 2 : 1))
          setTimeout(async () => resolve({events, states, threw, second,
            final: {readyState: r.readyState, result: await describeResult(r.result), error: r.error && r.error.name}}), 0);
      });
    try { spec.encoding === undefined ? r[spec.method](make(spec.blob)) : r[spec.method](make(spec.blob), spec.encoding); } catch (e) { threw = e.name; }
    events.push('return');
    if (spec.hook === 'sync') { act(); events.push('acted'); }
  });
  result.reader = {};
  for (const spec of cases.reader) result.reader[spec.name] = await bounded(read(spec), {timeout: true});
  result.readerAbortWhenEmpty = (() => { const r = new FileReader(); const fired = []; for (const t of ['abort', 'loadend']) r.addEventListener(t, () => fired.push(t)); r.abort(); return {readyState: r.readyState, fired, result: r.result, error: r.error}; })();
  result.readerConstants = [FileReader.EMPTY, FileReader.LOADING, FileReader.DONE];
  result.readerInitial = (() => { const r = new FileReader(); return {readyState: r.readyState, result: r.result, error: r.error}; })();

  result.promises = {};
  for (const spec of cases.promises) {
    const blob = make(spec.blob);
    result.promises[spec.name] = spec.mode === 'text'
      ? {ok: true, value: await blob.text()}
      : {ok: true, ...(await describeBytes(await blob.bytes()))};
  }
  const urlRead = url => fetch(url).then(async r => ({ok: true, status: r.status, type: r.headers.get('content-type'), ...(await describeBytes(new Uint8Array(await r.arrayBuffer())))}),
    e => ({ok: false, name: e.name}));
  const uuid = /^blob:(.*)\/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  const first = URL.createObjectURL(make('abc')), again = URL.createObjectURL(make('abc'));
  result.format = {matches: uuid.test(first), origin: (first.match(uuid) || [])[1] ?? null, distinct: first !== again};
  result.urlReads = {};
  for (const spec of cases.urlReads) {
    const blob = spec.slice ? make(spec.blob).slice(...spec.slice) : make(spec.blob);
    result.urlReads[spec.name] = await urlRead(URL.createObjectURL(blob) + (spec.fragment || ''));
  }
  URL.revokeObjectURL(first);
  result.revoked = {read: await urlRead(first), other: await urlRead(again)};
  result.revokeNoOp = (() => { try { URL.revokeObjectURL(first); URL.revokeObjectURL('not a url'); URL.revokeObjectURL('https://x/'); return 'ok'; } catch (e) { return e.name; } })();
  result.unknown = await urlRead('blob:' + self.origin + '/00000000-0000-4000-8000-000000000000');
  const image = url => new Promise(resolve => {
    const i = new Image();
    i.onload = () => resolve({outcome: 'load', width: i.naturalWidth, height: i.naturalHeight});
    i.onerror = () => resolve({outcome: 'error', width: i.naturalWidth, height: i.naturalHeight});
    i.src = url;
  });
  result.images = {};
  for (const spec of cases.images) result.images[spec.name] = await bounded(image(URL.createObjectURL(make(spec.blob))), {timeout: true});
  const svgUrl = URL.createObjectURL(make('svg'));
  URL.revokeObjectURL(svgUrl);
  result.imageRevoked = await bounded(image(svgUrl), {timeout: true});
  // Teardown: a removed iframe's document revokes its URLs and ends its reads.
  result.teardown = await new Promise(resolve => {
    const f = document.createElement('iframe');
    f.srcdoc = '<p>x</p>';
    f.onload = async () => {
      const w = f.contentWindow;
      const url = w.URL.createObjectURL(new w.Blob(['child']));
      const before = await urlRead(url);
      const reader = new w.FileReader();
      const events = [];
      for (const t of ['loadstart', 'progress', 'load', 'abort', 'error', 'loadend']) reader.addEventListener(t, () => events.push(t));
      reader.readAsArrayBuffer(new w.Blob([new Uint8Array(1 << 20)]));
      let settled = 'pending';
      new w.Blob(['p']).text().then(() => { settled = 'resolved'; }, e => { settled = 'rejected:' + e.name; });
      f.remove();
      await new Promise(r => setTimeout(r, 200));
      resolve({before, after: await urlRead(url), readerEvents: events, readerState: reader.readyState, promise: settled});
    };
    document.body.append(f);
  });
  return result;
};

const fileCases = async (tab, path) => {
  await tab.setContent('<!doctype html><body><input type=file id=f></body>');
  await tab.setInputFiles('#f', path);
  return tab.evaluate(async () => {
    const f = document.getElementById('f').files[0];
    window.__file = f;
    const r = await fetch(URL.createObjectURL(f));
    return {name: f.name, size: f.size, type: f.type, text: await f.text(), urlRead: {status: r.status, type: r.headers.get('content-type'), text: await r.text()},
      slice: await f.slice(1, 3).text()};
  });
};
const deletedCases = tab => tab.evaluate(async () => {
  const f = window.__file;
  const reader = await new Promise(resolve => {
    const r = new FileReader();
    const events = [];
    for (const t of ['loadstart', 'progress', 'load', 'abort', 'error', 'loadend'])
      r.addEventListener(t, () => { if (events[events.length - 1] !== t) events.push(t); if (t === 'loadend') resolve({events, readyState: r.readyState, result: r.result, error: r.error && r.error.name}); });
    r.readAsText(f);
  });
  const text = await f.text().then(v => ({ok: true, v}), e => ({ok: false, name: e.name}));
  const urlRead = await fetch(URL.createObjectURL(f)).then(r => r.text()).then(v => ({ok: true, v}), e => ({ok: false, name: e.name}));
  return {reader, text, urlRead};
});
const tryRead = (tab, url) => tab.evaluate(u => fetch(u).then(async r => { const b = new Uint8Array(await r.arrayBuffer()); return {ok: true, type: r.headers.get('content-type'), length: b.length, hex: [...b].map(x => x.toString(16).padStart(2, '0')).join('')}; }, e => ({ok: false, name: e.name})), url);
const tryImage = (tab, url) => tab.evaluate(u => new Promise(resolve => { const i = new Image(); i.onload = () => resolve('load'); i.onerror = () => resolve('error'); i.src = u; setTimeout(() => resolve('timeout'), 3000); }), url);
const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="7" height="5"><rect width="7" height="5"/></svg>';

if (import.meta.url === `file:///${process.argv[1].replaceAll('\\', '/')}`) {
  const browser = await chromium.launch({headless: true});
  const dir = mkdtempSync(join(tmpdir(), 'rv-blob-'));
  try {
    const context = await browser.newContext();
    const tab = await context.newPage();
    await tab.setContent('<!doctype html><body></body>');
    const blank = await tab.evaluate(measure, cases);
    // Isolation between two about:blank pages (two opaque origins), and after the creating document is replaced.
    const other = await context.newPage();
    await other.setContent('<!doctype html><body></body>');
    const make = page => page.evaluate(s => ({text: URL.createObjectURL(new Blob(['iso'])), image: URL.createObjectURL(new Blob([s], {type: 'image/svg+xml'}))}), svg);
    const urls = await make(tab);
    const isolation = {otherRead: await tryRead(other, urls.text), otherImage: await tryImage(other, urls.image),
      selfRead: await tryRead(tab, urls.text), selfImage: await tryImage(tab, urls.image)};
    await tab.goto('about:blank');
    isolation.afterReplaceRead = await tryRead(tab, urls.text);
    isolation.afterReplaceImage = await tryImage(tab, urls.image);
    // Same origin across pages (http), the case Chromium partitions by origin.
    await context.route('http://rv.test/**', route => route.fulfill({contentType: 'text/html', body: '<!doctype html><body></body>'}));
    await context.route('http://rv2.test/**', route => route.fulfill({contentType: 'text/html', body: '<!doctype html><body></body>'}));
    await tab.goto('http://rv.test/a');
    await other.goto('http://rv.test/b');
    const httpUrls = await make(tab);
    isolation.sameOriginRead = await tryRead(other, httpUrls.text);
    await other.goto('http://rv2.test/b');
    isolation.crossOriginRead = await tryRead(other, httpUrls.text);
    isolation.crossOriginImage = await tryImage(other, httpUrls.image);
    await tab.close();
    isolation.afterCloseRead = await tryRead(other, httpUrls.text);
    const page = await context.newPage();
    const path = join(dir, 'data.txt');
    writeFileSync(path, 'file-bytes');
    const file = await fileCases(page, path);
    rmSync(path);
    const deleted = await deletedCases(page);
    const result = {browser: browser.version(), headless: 'new', ...blank, isolation, file, deleted};
    writeFileSync(new URL('../fixtures/blob-urls-oracle.json', import.meta.url), JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify({browser: result.browser, isolation, teardown: result.teardown, deleted}, null, 1));
  } finally {
    await browser.close();
    rmSync(dir, {recursive: true, force: true});
  }
}
