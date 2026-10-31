// Chromium oracle for tests/fixtures/form-submission-cases.json: writes tests/fixtures/form-submission-oracle.json.
// Each case runs on a fresh page. Every request to https://app.test/ is recorded as a submission and answered with
// 204 No Content, so the document stays. press and mouse steps are trusted Playwright input; a flush waits two
// animation frames and 150 ms, so scheduled form navigations start.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const spec = JSON.parse(readFileSync('tests/fixtures/form-submission-cases.json', 'utf8'));
const browser = await chromium.launch({headless: true});
const version = browser.version();
const cases = [];
const boundary = (type, body) => {
  const match = /boundary=(.+)$/.exec(type || '');
  return match ? [type.replace(match[1], 'BOUNDARY'), (body || '').split(match[1]).join('BOUNDARY')] : [type, body];
};
const install = types => {
  const label = node => node ? (node.id || node.nodeName) : null;
  window.__label = label;
  window.__events = [];
  window.__prevent = [];
  window.__append = null;
  window.__removeOnSubmit = null;
  const entries = data => [...data.entries()].map(([name, value]) => [name, typeof value === 'string' ? value : {file: value.name}]);
  for (const type of types) {
    document.addEventListener(type, event => {
      const entry = {type: event.type, target: label(event.target), trusted: event.isTrusted, cancelable: event.cancelable};
      if (event instanceof SubmitEvent) entry.submitter = label(event.submitter);
      if (event instanceof FormDataEvent) {
        if (window.__append) event.formData.append(window.__append[0], window.__append[1]);
        entry.entries = entries(event.formData);
      }
      if (event.type === 'submit' && window.__removeOnSubmit) {
        document.getElementById(window.__removeOnSubmit).remove();
        window.__removeOnSubmit = null;
      }
      const index = window.__prevent.indexOf(event.type);
      if (index >= 0) {
        window.__prevent.splice(index, 1);
        event.preventDefault();
        entry.prevented = true;
      }
      window.__events.push(entry);
    }, {capture: true});
  }
};
const domStep = s => {
  const byId = id => document.getElementById(id);
  try {
    const t = s.id ? byId(s.id) : null;
    switch (s.op) {
      case 'requestSubmit': 'submitter' in s ? t.requestSubmit(byId(s.submitter)) : t.requestSubmit(); return {status: 'ok', value: null};
      case 'submit': t.submit(); return {status: 'ok', value: null};
      case 'submitTwice': t.requestSubmit(); t.requestSubmit(); return {status: 'ok', value: null};
      case 'click': t.click(); return {status: 'ok', value: null};
      case 'focus': t.focus(); return {status: 'ok', value: null};
      case 'setAttribute': t.setAttribute(s.name, s.value); return {status: 'ok', value: null};
      case 'setValue': t.value = s.value; return {status: 'ok', value: null};
      case 'checkValidity': return {status: 'ok', value: t.checkValidity()};
      case 'prevent': window.__prevent.push(s.type); return {status: 'ok', value: null};
      case 'appendOnFormData': window.__append = [s.name, s.value]; return {status: 'ok', value: null};
      case 'removeOnSubmit': window.__removeOnSubmit = s.id; return {status: 'ok', value: null};
    }
    return {status: 'unknown-op'};
  } catch (error) {
    return {status: error.name, value: null};
  }
};
try {
  const only = process.argv[2];
  for (const c of spec.cases.filter(c => !only || c.name === only)) {
    const context = await browser.newContext({viewport: {width: spec.viewport[0], height: spec.viewport[1]}});
    const submissions = [];
    await context.route('**/*', route => {
      const request = route.request();
      if (!request.url().startsWith('https://app.test/')) return route.abort();
      const [contentType, body] = boundary(request.headers()['content-type'] || null, request.postData());
      let newWindow;
      try { newWindow = request.frame() !== page.mainFrame(); } catch { newWindow = true; }
      submissions.push({method: request.method(), url: request.url(), contentType, body: body ?? null,
                        newWindow});
      return route.fulfill({status: 204, body: ''});
    });
    const page = await context.newPage();
    await page.setContent(spec.markup);
    await page.evaluate(install, spec.eventTypes);
    const steps = [];
    for (const s of c.steps) {
      let result;
      if (s.op === 'press') {
        await page.keyboard.press(s.key);
        result = {status: 'ok', value: null};
      } else if (s.op === 'mouse') {
        await page.mouse.click(s.x, s.y);
        result = {status: 'ok', value: null};
      } else if (s.op === 'flush') {
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(resolve, 150)))));
        result = {status: 'ok', value: null};
      } else {
        result = await page.evaluate(domStep, s);
      }
      result.events = await page.evaluate(() => window.__events.splice(0));
      result.submissions = submissions.splice(0);
      steps.push({...s, ...result});
    }
    cases.push({name: c.name, steps});
    await context.close();
  }
} finally {
  await browser.close();
}
const oracle = {browser: version, headless: 'new', cases};
if (process.argv[2]) console.log(JSON.stringify(oracle, null, 2));
else writeFileSync('tests/fixtures/form-submission-oracle.json', JSON.stringify(oracle, null, 2) + '\n');
console.log('Chromium', version, cases.length, 'cases');
