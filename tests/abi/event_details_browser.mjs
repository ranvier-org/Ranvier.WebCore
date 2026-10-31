// Chromium oracle for tests/fixtures/event-details-cases.json: writes tests/fixtures/event-details-oracle.json.
// Constructed events are read on one page. The dispatched scenario loads the markup from https://app.test/, so the
// window receives pageshow, and aborts the missing image's request, so the image errors without a network lookup.
// Each step waits for the event types it names, then for two animation frames.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const spec = JSON.parse(readFileSync('tests/fixtures/event-details-cases.json', 'utf8'));
const browser = await chromium.launch({headless: true});
const version = browser.version();
const page = await browser.newPage();
await page.setContent('<!doctype html><html><body></body></html>');

const constructed = await page.evaluate(({cases, eventInit}) => {
  const value = v => v === null || ['string', 'number', 'boolean'].includes(typeof v) ? v : Object.prototype.toString.call(v);
  const read = (event, fields) => ({
    interface: event.constructor.name, type: event.type, bubbles: event.bubbles, cancelable: event.cancelable,
    composed: event.composed, isTrusted: event.isTrusted,
    fields: Object.fromEntries(Object.keys(fields).map(name => [name, value(event[name])])),
  });
  return cases.map(item => {
    const C = window[item.interface];
    const own = Object.getOwnPropertyNames(C.prototype).filter(name => Object.getOwnPropertyDescriptor(C.prototype, name).get);
    return {
      interface: item.interface,
      defaults: read(new C(item.type), item.fields),
      full: read(new C(item.type, {...eventInit, ...item.init}), item.fields),
      engineOnlyAttributes: own.filter(name => !(name in item.fields)),
    };
  });
}, {cases: spec.constructed, eventInit: spec.eventInit});

// FormDataEvent requires an init dictionary with formData.
const typeQuery = await page.evaluate(cases => cases.map(item => ({interface: item.interface,
  name: new window[item.interface]('x', item.interface === 'FormDataEvent' ? {formData: new FormData()} : {}).constructor.name})), spec.typeQuery);

// Dispatched payloads.
const scenario = spec.dispatched;
const view = await browser.newPage({viewport: {width: scenario.viewport[0], height: scenario.viewport[1]}});
await view.route('https://missing.invalid/**', route => route.abort());
await view.route('https://app.test/', route => route.fulfill({status: 200, contentType: 'text/html', body: scenario.markup}));
await view.addInitScript(({types, fields, media}) => {
  window.__events = [];
  const label = node => node && (node.id || node.nodeName) || null;
  const record = event => {
    const name = event.constructor.name;
    const entry = {type: event.type, interface: name, trusted: event.isTrusted, target: event.target === window ? 'window' : label(event.target)};
    if (event.target instanceof MediaQueryList) entry.target = 'media';
    for (const field of fields[name] || []) entry[field] = event[field];
    window.__events.push(entry);
  };
  for (const type of types) window.addEventListener(type, record, true);
  window.__media = matchMedia(media);
  window.__media.addEventListener('change', record);
}, {types: scenario.types, fields: scenario.fields, media: scenario.steps.find(step => step.op === 'resize').media});
const frames = () => view.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
const waitFor = async types => {
  for (const type of types || [])
    await view.waitForFunction(([t, from]) => window.__events.slice(from).some(e => e.type === t), [type, seen], {timeout: 5000});
  await frames();
};
const steps = [];
let seen = 0;
const take = async () => {
  const all = await view.evaluate(() => window.__events);
  const part = all.slice(seen);
  seen = all.length;
  return part;
};
for (const step of scenario.steps) {
  if (step.op === 'load') {
    await view.goto('https://app.test/');
    await waitFor(step.until);
  } else if (step.op === 'class') {
    await view.evaluate(({id, value}) => document.getElementById(id).classList.add(value), step);
    await waitFor(step.until);
  } else if (step.op === 'resize') {
    await view.setViewportSize({width: step.width, height: step.height});
    await waitFor(step.until);
  } else if (step.op === 'dialogShow') {
    await view.evaluate(id => document.getElementById(id).show(), step.id);
    await waitFor(step.until);
  } else if (step.op === 'click') {
    await view.mouse.click(step.x, step.y);
    await frames();
  } else if (step.op === 'wheel') {
    await view.mouse.move(step.x, step.y);
    await view.mouse.wheel(0, step.deltaY);
    await waitFor(['wheel']);
  } else if (step.op === 'focusAndType') {
    await view.mouse.click(step.x, step.y);
    await view.keyboard.press(step.key);
    await waitFor(['input', 'keyup']);
  }
  steps.push({name: step.name, order: step.order || 'sequence', events: await take()});
}

writeFileSync('tests/fixtures/event-details-oracle.json', JSON.stringify({browser: version, constructed, typeQuery, dispatched: steps}, null, 2) + '\n');
await browser.close();
console.log('event details oracle', version, constructed.length, typeQuery.length, steps.length);
