// Chromium oracle for tests/fixtures/data-transfer-cases.json: writes tests/fixtures/data-transfer-oracle.json.
// The drop goes through CDP Input.dispatchDragEvent with the case's files written to a temporary directory; the paste
// writes the case's strings and image to the clipboard and presses Control+V. Snapshots take the shape of
// tests/abi/data_transfer.py's.
import {createRequire} from 'node:module';
import {mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const spec = JSON.parse(readFileSync('tests/fixtures/data-transfer-cases.json', 'utf8'));
const directory = mkdtempSync(join(tmpdir(), 'data-transfer-'));
const paths = spec.drop.files.map(([name, content]) => { const path = join(directory, name); writeFileSync(path, content); return path; });

const browser = await chromium.launch({headless: true});
const context = await browser.newContext({viewport: {width: spec.viewport[0], height: spec.viewport[1]}});
await context.grantPermissions(['clipboard-read', 'clipboard-write'], {origin: 'https://app.test'});
const page = await context.newPage();
await page.route('https://app.test/**', route => route.fulfill({contentType: 'text/html', body: spec.markup}));
await page.goto('https://app.test/');

await page.evaluate(() => {
  window.snap = dt => dt && ({types: [...dt.types], text: dt.getData('text/plain'), html: dt.getData('text/html'),
    uri: dt.getData('text/uri-list'), files: [...dt.files].map(f => [f.name, f.type, f.size]),
    items: [...dt.items].map(i => [i.kind, i.type]), dropEffect: dt.dropEffect, effectAllowed: dt.effectAllowed});
  window.writeAttempt = dt => {
    const before = [...dt.types];
    dt.setData('text/x-probe', 'w');
    const added = dt.items.add('w2', 'text/uri-list');
    return {setData: dt.types.includes('text/x-probe') && !before.includes('text/x-probe'), itemsAdd: !!added};
  };
  window.log = [];
  window.held = [];
  window.on = (node, type, cancel, write) => node.addEventListener(type, event => {
    const dt = event.dataTransfer || event.clipboardData || null;
    const record = {interface: event.constructor.name, dt: snap(dt)};
    if (event instanceof InputEvent)
      Object.assign(record, {inputType: event.inputType, data: event.data,
        ranges: event.getTargetRanges().map(r => [r.startOffset, r.endOffset])});
    if (write && dt)
      record.write = writeAttempt(dt);
    record.type = type;
    if (dt)
      held.push([type, dt]);
    if (cancel)
      event.preventDefault();
    log.push(record);
  });
  window.take = () => {
    const result = {log, after: Object.fromEntries(held.map(([type, dt]) => [type, snap(dt)]))};
    log = [];
    held = [];
    return result;
  };
});

const constructed = await page.evaluate(() => {
  const dt = new DataTransfer();
  const r = {};
  r.initial = {dropEffect: dt.dropEffect, effectAllowed: dt.effectAllowed, types: [...dt.types]};
  for (const value of ['bogus', 'link']) {
    dt.dropEffect = value;
    dt.effectAllowed = value === 'link' ? 'copyMove' : value;
    r[value] = [dt.dropEffect, dt.effectAllowed];
  }
  dt.setData('Text', 'a'); dt.setData('text/html', '<b>h</b>'); dt.setData('application/x-custom', 'c');
  r.types = [...dt.types]; r.text = dt.getData('text/plain'); r.url = dt.getData('URL');
  const z = new File(['zz'], 'z.txt', {type: 'text/plain'});
  const item = dt.items.add(z);
  if (item.getAsFile() !== z) throw new Error('getAsFile identity');
  r.afterFile = {types: [...dt.types], items: [...dt.items].map(i => [i.kind, i.type]), files: [...dt.files].map(f => f.name)};
  try { dt.items.add('dup', 'text/plain'); r.dup = 'no throw'; } catch (e) { r.dup = e.name; }
  dt.items.remove(0); r.removed = [...dt.types];
  dt.clearData('text/html'); r.cleared = [...dt.types];
  dt.clearData(); r.clearAll = {types: [...dt.types], files: dt.files.length};
  dt.items.clear(); r.itemsClear = {types: [...dt.types], files: dt.files.length};
  return r;
});

await page.evaluate(() => {
  const t = document.getElementById('t');
  for (const type of ['dragenter', 'dragover', 'dragleave', 'drop'])
    on(t, type, type !== 'dragleave', type === 'dragover' || type === 'drop');
});
const cdp = await context.newCDPSession(page);
const [x, y] = spec.drop.point;
const data = {items: spec.drop.strings.map(([mimeType, value]) => ({mimeType, data: value})), files: paths,
  dragOperationsMask: spec.drop.allowed};
for (const type of ['dragEnter', 'dragOver', 'drop'])
  await cdp.send('Input.dispatchDragEvent', {type, x, y, data});
const drop = await page.evaluate(() => take());

await page.evaluate(async ({strings, file}) => {
  const bytes = new Uint8Array(file[2].match(/../g).map(h => parseInt(h, 16)));
  const parts = Object.fromEntries(strings.map(([type, value]) => [type, new Blob([value], {type})]));
  parts[file[1]] = new Blob([bytes], {type: file[1]});
  await navigator.clipboard.write([new ClipboardItem(parts)]);
  const e = document.getElementById('e');
  on(e, 'paste', false, true);
  on(e, 'beforeinput', false, false);
  on(e, 'input', false, false);
}, spec.paste);
await page.focus('#e');
await page.keyboard.press('Control+A');
await page.keyboard.press('Control+V');
await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
const paste = await page.evaluate(() => ({...take(), html: document.getElementById('e').innerHTML}));

writeFileSync('tests/fixtures/data-transfer-oracle.json', JSON.stringify({chromium: browser.version(), constructed, drop, paste}, null, 1) + '\n');
await browser.close();
console.log('DATA_TRANSFER_ORACLE_WRITTEN');
