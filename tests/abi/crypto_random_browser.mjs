// B22 oracle: Chromium's crypto.getRandomValues, crypto.randomUUID and crypto.subtle, measured as properties.
// Random outputs are never recorded: only lengths, types, formats, version/variant bits and inequality.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const out = process.argv[2] || 'tests/fixtures/crypto-random-oracle.json';
const browser = await chromium.launch({headless: true});
try {
  const page = await browser.newPage();
  await page.goto('about:blank');
  const insecure = await page.evaluate(() => ({isSecureContext, randomUUID: typeof crypto.randomUUID,
    subtle: typeof crypto.subtle, getRandomValues: typeof crypto.getRandomValues}));
  await page.route('http://localhost/crypto', route => route.fulfill({contentType: 'text/html', body: '<!doctype html><title>crypto</title>'}));
  await page.goto('http://localhost/crypto');
  const result = await page.evaluate(async () => {
    const kinds = ['Int8Array', 'Uint8Array', 'Uint8ClampedArray', 'Int16Array', 'Uint16Array', 'Int32Array',
      'Uint32Array', 'BigInt64Array', 'BigUint64Array', 'Float16Array', 'Float32Array', 'Float64Array', 'DataView'];
    const error = e => ({name: e && e.name, isDOMException: e instanceof DOMException, ctor: e && e.constructor && e.constructor.name});
    const make = (kind, bytes) => {
      const C = globalThis[kind];
      if (!C) return null;
      return kind === 'DataView' ? new DataView(new ArrayBuffer(bytes)) : new C(bytes / C.BYTES_PER_ELEMENT);
    };
    const typed = {};
    for (const kind of kinds) {
      const entry = {exists: typeof globalThis[kind] === 'function'};
      if (entry.exists) {
        for (const [label, bytes] of [['empty', 0], ['small', 16], ['limit', 65536], ['over', 65544]]) {
          const view = make(kind, bytes);
          try {
            const back = crypto.getRandomValues(view);
            entry[label] = {ok: true, sameObject: back === view, byteLength: back.byteLength};
          } catch (e) { entry[label] = {ok: false, ...error(e)}; }
        }
      }
      typed[kind] = entry;
    }
    // A subarray view: bytes outside the view keep their value.
    const base = new Uint8Array(32);
    const sub = base.subarray(8, 24);
    crypto.getRandomValues(sub);
    const outsideUntouched = base.subarray(0, 8).every(b => b === 0) && base.subarray(24).every(b => b === 0);
    // Two calls differ (16 bytes: equal with probability 2^-128).
    const a = crypto.getRandomValues(new Uint8Array(16)), b = crypto.getRandomValues(new Uint8Array(16));
    const differ = a.some((x, i) => x !== b[i]);
    const nonView = {};
    for (const [label, value] of [['arrayBuffer', new ArrayBuffer(8)], ['null', null], ['number', 5], ['array', [1, 2]]]) {
      try { crypto.getRandomValues(value); nonView[label] = {ok: true}; } catch (e) { nonView[label] = {ok: false, ...error(e)}; }
    }
    let shared = null;
    try { crypto.getRandomValues(new Uint8Array(new SharedArrayBuffer(8))); shared = {ok: true}; }
    catch (e) { shared = typeof SharedArrayBuffer === 'undefined' ? {ok: false, name: 'SharedArrayBuffer undefined'} : {ok: false, ...error(e)}; }
    // Quota boundary in elements for 4-byte views.
    const quota32 = {};
    for (const n of [16384, 16385]) {
      try { crypto.getRandomValues(new Uint32Array(n)); quota32[n] = {ok: true}; } catch (e) { quota32[n] = {ok: false, ...error(e)}; }
    }
    // randomUUID.
    const re = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
    const uuids = Array.from({length: 64}, () => crypto.randomUUID());
    const uuid = {
      type: typeof uuids[0], length: uuids[0].length, allMatchV4: uuids.every(u => re.test(u)),
      allLowercase: uuids.every(u => u === u.toLowerCase()), allDistinct: new Set(uuids).size === uuids.length,
      versionNibble: [...new Set(uuids.map(u => u[14]))], variantNibbles: [...new Set(uuids.map(u => u[19]))].sort(),
    };
    // SubtleCrypto: which algorithms generateKey or digest supports.
    const subtle = {isSecureContext, present: typeof crypto.subtle === 'object' && crypto.subtle !== null, algorithms: {}};
    const enc = new TextEncoder();
    const hex = buf => [...new Uint8Array(buf)].map(x => x.toString(16).padStart(2, '0')).join('');
    for (const h of ['SHA-1', 'SHA-256', 'SHA-384', 'SHA-512']) {
      try { subtle.algorithms[h] = {digestAbc: hex(await crypto.subtle.digest(h, enc.encode('abc')))}; }
      catch (e) { subtle.algorithms[h] = {ok: false, ...error(e)}; }
    }
    const gens = {
      'AES-CBC': [{name: 'AES-CBC', length: 128}, ['encrypt']], 'AES-CTR': [{name: 'AES-CTR', length: 128}, ['encrypt']],
      'AES-GCM': [{name: 'AES-GCM', length: 128}, ['encrypt']], 'AES-KW': [{name: 'AES-KW', length: 128}, ['wrapKey']],
      'HMAC': [{name: 'HMAC', hash: 'SHA-256'}, ['sign']],
      'ECDSA': [{name: 'ECDSA', namedCurve: 'P-256'}, ['sign']], 'ECDH': [{name: 'ECDH', namedCurve: 'P-256'}, ['deriveBits']],
      'Ed25519': [{name: 'Ed25519'}, ['sign']], 'X25519': [{name: 'X25519'}, ['deriveBits']],
      'RSASSA-PKCS1-v1_5': [{name: 'RSASSA-PKCS1-v1_5', modulusLength: 1024, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256'}, ['sign']],
      'RSA-PSS': [{name: 'RSA-PSS', modulusLength: 1024, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256'}, ['sign']],
      'RSA-OAEP': [{name: 'RSA-OAEP', modulusLength: 1024, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256'}, ['encrypt', 'decrypt']],
      'AES-CFB-8': [{name: 'AES-CFB-8', length: 128}, ['encrypt']],
    };
    for (const [name, [alg, usages]] of Object.entries(gens)) {
      try { const k = await crypto.subtle.generateKey(alg, true, usages); subtle.algorithms[name] = {generateKey: k.type || 'pair'}; }
      catch (e) { subtle.algorithms[name] = {generateKey: false, ...error(e)}; }
    }
    for (const name of ['PBKDF2', 'HKDF']) {
      try { const k = await crypto.subtle.importKey('raw', enc.encode('pw'), name, false, ['deriveBits']); subtle.algorithms[name] = {importKey: k.type}; }
      catch (e) { subtle.algorithms[name] = {importKey: false, ...error(e)}; }
    }
    return {typed, outsideUntouched, differ, nonView, shared, quota32, uuid, subtle};
  });
  result.insecureContext = insecure;
  result.browser = browser.version();
  result.headless = 'new';
  writeFileSync(out, JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result, null, 1));
} finally {
  await browser.close();
}
