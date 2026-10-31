// Chromium oracle for tests/abi/notifications.py (B09, WebCore #117): measures each case of
// tests/fixtures/notification-cases.json that Chromium can observe and checks it against the fixture.
//   node tests/abi/notifications_browser.mjs <package.json with playwright> <out.json>
import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
const [packageJson, out] = process.argv.slice(2);
const require = createRequire(packageJson);
const { chromium } = require('playwright');
const text = await readFile(new URL('../fixtures/notification-cases.json', import.meta.url), 'utf-8');
const fixture = JSON.parse(text).cases;
const server = createServer((request, response) => {
  response.setHeader('Content-Type', 'text/html');
  response.end('<!doctype html><body></body>');
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const url = `http://127.0.0.1:${server.address().port}/`;
const browser = await chromium.launch({ headless: true });
const settle = () => new Promise(resolve => setTimeout(resolve, 200));
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(url);
  const shows = () => page.evaluate(async () => {
    const events = [];
    const n = new Notification('T', { body: 'B' });
    for (const type of ['show', 'error', 'click', 'close'])
      n.addEventListener(type, e => events.push([type, e.bubbles, e.cancelable, e.isTrusted]));
    await new Promise(resolve => setTimeout(resolve, 300));
    n.close();
    await new Promise(resolve => setTimeout(resolve, 100));
    return events;
  });
  const measured = {};
  measured['default-permission'] = await page.evaluate(() => Notification.permission);
  measured['show-without-permission'] = await shows();
  Object.assign(measured, await page.evaluate(async () => {
    const result = {};
    const n = new Notification('Title é', { body: 'Body', tag: 't1', lang: 'en-GB', dir: 'rtl', silent: true, icon: 'icons/a.png' });
    result.fields = { title: n.title, body: n.body, tag: n.tag, lang: n.lang, dir: n.dir, silent: n.silent,
      icon: n.icon.replace(location.origin, '') };
    const empty = new Notification('');
    result.defaults = { title: empty.title, body: empty.body, tag: empty.tag, lang: empty.lang, dir: empty.dir,
      silent: empty.silent, icon: empty.icon };
    n.close();
    empty.close();
    const outcome = f => { try { f(); return 'ok'; } catch (e) { return e.name; } };
    result['missing-title'] = outcome(() => new Notification());
    result['actions'] = outcome(() => new Notification('a', { actions: [{ action: 'x', title: 'X' }] }));
    result['bad-dir'] = outcome(() => new Notification('a', { dir: 'up' }));
    const badge = async f => { try { await f(); return 'ok'; } catch (e) { return e.name; } };
    result['badge-set'] = await badge(() => navigator.setAppBadge(3));
    result['badge-clear'] = await badge(() => navigator.clearAppBadge());
    result['badge-negative'] = await badge(() => navigator.setAppBadge(-1));
    return result;
  }));
  await context.grantPermissions(['notifications'], { origin: url });
  measured['request-granted'] = await page.evaluate(() => Notification.requestPermission());
  measured['show-granted'] = await shows();
  await settle();
  let assertions = 0;
  for (const [name, value] of Object.entries(measured)) {
    assertions++;
    if (JSON.stringify(value) !== JSON.stringify(fixture[name].chromium))
      throw new Error(`${name}: ${JSON.stringify(value)} != ${JSON.stringify(fixture[name].chromium)}`);
  }
  const unmeasured = Object.keys(fixture).filter(name => !(name in measured));
  const evidence = { browser: await browser.version(), casesSha256: createHash('sha256').update(text).digest('hex'),
    assertions, measured, unmeasured };
  await writeFile(out, JSON.stringify(evidence, null, 2));
  console.log(`PASS Chromium notifications: ${assertions} assertions (${evidence.browser})`);
} finally {
  await browser.close();
  server.close();
}
