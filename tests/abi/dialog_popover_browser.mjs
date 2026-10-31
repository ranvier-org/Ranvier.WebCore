// Chromium oracle for tests/fixtures/dialog-popover-cases.json: writes tests/fixtures/dialog-popover-oracle.json.
// Each case runs on a fresh page. DOM steps run in the page; press and mouse steps are trusted Playwright input.
// A flush step waits two animation frames and a task, so queued toggle and close events are delivered.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const spec = JSON.parse(readFileSync('tests/fixtures/dialog-popover-cases.json', 'utf8'));
const browser = await chromium.launch({headless: true});
const version = browser.version();
const cases = [];
const install = types => {
  const label = node => node ? (node.id || node.nodeName) : null;
  window.__label = label;
  window.__events = [];
  window.__prevent = [];
  for (const type of types) {
    document.addEventListener(type, event => {
      const entry = {type: event.type, target: label(event.target), trusted: event.isTrusted, cancelable: event.cancelable};
      if (event instanceof ToggleEvent) Object.assign(entry, {oldState: event.oldState, newState: event.newState, source: label(event.source)});
      if (typeof CommandEvent !== 'undefined' && event instanceof CommandEvent) Object.assign(entry, {command: event.command, source: label(event.source)});
      const index = window.__prevent.indexOf(event.type);
      if (index >= 0) {
        window.__prevent.splice(index, 1);
        event.preventDefault();
        entry.prevented = event.defaultPrevented;
      }
      window.__events.push(entry);
    }, {capture: true});
  }
};
const domStep = s => {
  const label = window.__label;
  const byId = id => id === null ? null : document.getElementById(id);
  const build = (name, type, init) => {
    const dict = {...init};
    if ('source' in dict) dict.source = byId(dict.source);
    const event = name === 'ToggleEvent' ? new ToggleEvent(type, dict) : new CommandEvent(type, dict);
    return event;
  };
  const describe = event => {
    const base = {type: event.type, bubbles: event.bubbles, cancelable: event.cancelable, trusted: event.isTrusted};
    if (event instanceof ToggleEvent) Object.assign(base, {oldState: event.oldState, newState: event.newState, source: label(event.source)});
    else Object.assign(base, {command: event.command, source: label(event.source)});
    return base;
  };
  const value = v => v instanceof Element ? label(v) : v === undefined ? null : v;
  try {
    const t = byId(s.id ?? null);
    switch (s.op) {
      case 'prop': return {status: 'ok', value: value(t[s.name])};
      case 'set': t[s.name] = s.name.endsWith('Element') ? byId(s.value) : s.value; return {status: 'ok', value: null};
      case 'hasAttr': return {status: 'ok', value: t.hasAttribute(s.name)};
      case 'matches': return {status: 'ok', value: t.matches(s.selector)};
      case 'show': case 'showModal': case 'hidePopover': t[s.op](); return {status: 'ok', value: null};
      case 'close': case 'requestClose': 'value' in s ? t[s.op](s.value) : t[s.op](); return {status: 'ok', value: null};
      case 'showPopover': 'source' in s ? t.showPopover({source: byId(s.source)}) : t.showPopover(); return {status: 'ok', value: null};
      case 'togglePopover': return {status: 'ok', value: 'force' in s ? t.togglePopover(s.force) : t.togglePopover()};
      case 'focus': t.focus(); return {status: 'ok', value: null};
      case 'active': return {status: 'ok', value: label(document.activeElement)};
      case 'hit': return {status: 'ok', value: label(document.elementFromPoint(s.x, s.y))};
      case 'click': t.click(); return {status: 'ok', value: null};
      case 'prevent': window.__prevent.push(s.type); return {status: 'ok', value: null};
      case 'construct': return {status: 'ok', value: describe(build(s.interface, s.type, s.init))};
      case 'dispatch': return {status: 'ok', value: t.dispatchEvent(build(s.interface, s.type, s.init))};
    }
    return {status: 'unknown-op'};
  } catch (error) {
    return {status: error.name};
  }
};
try {
  const only = process.argv[2];
  for (const c of spec.cases.filter(c => !only || c.name === only)) {
    const page = await browser.newPage({viewport: {width: spec.viewport[0], height: spec.viewport[1]}});
    await page.route('**/*', route => route.abort());
    await page.setContent(spec.markup);
    await page.evaluate(install, spec.eventTypes);
    const steps = [];
    for (const s of c.steps) {
      let result;
      const activation = await page.evaluate(() => ({isActive: navigator.userActivation.isActive, hasBeenActive: navigator.userActivation.hasBeenActive}));
      if (s.op === 'press') {
        await page.keyboard.press(s.key);
        result = {status: 'ok', value: null};
      } else if (s.op === 'mouse') {
        await page.mouse.click(s.x, s.y);
        result = {status: 'ok', value: null};
      } else if (s.op === 'flush') {
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(resolve, 0)))));
        result = {status: 'ok', value: null};
      } else {
        result = await page.evaluate(domStep, s);
      }
      result.events = await page.evaluate(() => window.__events.splice(0));
      steps.push({...s, ...result, activationBefore: activation});
    }
    cases.push({name: c.name, steps});
    await page.close();
  }
} finally {
  await browser.close();
}
const oracle = {browser: version, headless: 'new', cases};
if (process.argv[2]) console.log(JSON.stringify(oracle, null, 2));
else writeFileSync('tests/fixtures/dialog-popover-oracle.json', JSON.stringify(oracle, null, 2) + '\n');
console.log('Chromium', version, cases.length, 'cases');
