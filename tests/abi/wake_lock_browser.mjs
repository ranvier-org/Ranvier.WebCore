// Chromium oracle for tests/abi/wake_locks.py (B10, WebCore #118): measures each case of
// tests/fixtures/wake-lock-cases.json that Chromium can observe and checks it against the fixture.
//   node tests/abi/wake_lock_browser.mjs <package.json with playwright> <out.json>
import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
const [packageJson, out] = process.argv.slice(2);
const require = createRequire(packageJson);
const { chromium } = require('playwright');
const text = await readFile(new URL('../fixtures/wake-lock-cases.json', import.meta.url), 'utf-8');
const fixture = JSON.parse(text).cases;
const server = createServer((request, response) => {
  response.setHeader('Content-Type', 'text/html');
  if (request.url.startsWith('/no-policy')) response.setHeader('Permissions-Policy', 'screen-wake-lock=()');
  response.end('<!doctype html><body></body>');
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const url = `http://127.0.0.1:${server.address().port}/`;
const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(url);
  const measured = {};
  measured['ungranted-request'] = await page.evaluate(async () => {
    try { await navigator.wakeLock.request('screen'); return 'ok'; } catch (e) { return e.name; }
  });
  await context.grantPermissions(['screen-wake-lock'], { origin: url });
  Object.assign(measured, await page.evaluate(async url => {
    const result = {};
    const outcome = async f => { try { await f(); return 'ok'; } catch (e) { return e.name; } };
    result['unknown-type'] = await outcome(() => navigator.wakeLock.request('system'));
    const log = [];
    const a = await navigator.wakeLock.request('screen');
    const b = await navigator.wakeLock.request();
    result['default-type'] = b.type;
    result['distinct-sentinels'] = a !== b;
    a.onrelease = e => log.push(['a-on', e.type, e.bubbles, e.cancelable, e.isTrusted, e.target === a]);
    a.addEventListener('release', () => log.push(['a-listener']));
    b.addEventListener('release', () => log.push(['b-listener']));
    const pending = a.release();
    log.push(['after-release-call', a.released]);
    await pending;
    log.push(['after-await', a.released]);
    await a.release();
    log.push(['second-release', a.released]);
    await b.release();
    result['release-log'] = log;
    const load = frame => new Promise(resolve => { frame.onload = resolve; document.body.append(frame); });
    const frame = document.createElement('iframe');
    frame.src = url;
    await load(frame);
    const lock = frame.contentWindow.navigator.wakeLock;
    const sentinel = await lock.request('screen');
    const events = [];
    sentinel.onrelease = () => events.push('release');
    frame.remove();
    await new Promise(resolve => setTimeout(resolve, 50));
    result['document-teardown'] = { released: sentinel.released, events };
    result['detached-request'] = await outcome(() => lock.request('screen'));
    const none = document.createElement('iframe');
    none.src = url;
    none.allow = "screen-wake-lock 'none'";
    await load(none);
    result['permissions-policy-none'] = await outcome(() => none.contentWindow.navigator.wakeLock.request('screen'));
    return result;
  }, url));
  const header = await context.newPage();
  await header.goto(url + 'no-policy');
  measured['permissions-policy-header'] = await header.evaluate(async () => {
    try { await navigator.wakeLock.request('screen'); return 'ok'; } catch (e) { return e.name; }
  });
  let assertions = 0;
  for (const [name, value] of Object.entries(measured)) {
    const expected = fixture[name].chromium;
    assertions++;
    if (JSON.stringify(value) !== JSON.stringify(expected))
      throw new Error(`${name}: ${JSON.stringify(value)} != ${JSON.stringify(expected)}`);
  }
  const unmeasured = Object.keys(fixture).filter(name => fixture[name].chromium === null);
  const evidence = { browser: await browser.version(), casesSha256: createHash('sha256').update(text).digest('hex'),
    assertions, measured, unmeasured };
  await writeFile(out, JSON.stringify(evidence, null, 2));
  console.log(`PASS Chromium wake locks: ${assertions} assertions (${evidence.browser})`);
} finally {
  await browser.close();
  server.close();
}
