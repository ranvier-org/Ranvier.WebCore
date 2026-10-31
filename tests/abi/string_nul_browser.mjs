// Chromium oracle for tests/abi/string_nul.py: writes tests/fixtures/string-nul-oracle.json. Each case of
// tests/fixtures/string-nul-cases.json passes a string holding U+0000 to a DOM member and records the value read back.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const cases = JSON.parse(readFileSync('tests/fixtures/string-nul-cases.json', 'utf8')).cases;
const out = process.argv[2] || 'tests/fixtures/string-nul-oracle.json';
const browser = await chromium.launch({headless: true});
try {
  const page = await browser.newPage();
  await page.route('http://localhost/strings', route => route.fulfill({contentType: 'text/html', body: '<!doctype html><title>strings</title><body>'}));
  await page.goto('http://localhost/strings');
  const values = await page.evaluate(cases => {
    const run = entry => {
      const v = entry.value;
      const div = () => document.body.appendChild(document.createElement('div'));
      switch (entry.op) {
        case 'setAttribute': { const e = div(); e.setAttribute('data-v', v); return e.getAttribute('data-v'); }
        case 'textContent': { const e = div(); e.textContent = v; return e.textContent; }
        case 'textContentNull': { const e = div(); e.textContent = 'x'; e.textContent = null; return e.textContent; }
        case 'createTextNode': return document.createTextNode(v).data;
        case 'appendData': { const t = document.createTextNode('a'); t.appendData(v); return t.data; }
        case 'id': { const e = div(); e.id = v; return e.getAttribute('id'); }
        case 'setAttributeNS': { const e = div(); e.setAttributeNS(null, 'data-n', v); return e.getAttributeNS(null, 'data-n'); }
        case 'createComment': return document.createComment(v).data;
        case 'createHTMLDocumentAbsent': return document.implementation.createHTMLDocument().title;
        case 'append': { const e = div(); e.append(v); return e.textContent; }
        case 'prepend': { const e = div(); e.textContent = 'x'; e.prepend(v); return e.textContent; }
        case 'replaceChildren': { const e = div(); e.textContent = 'old'; e.replaceChildren(v, 'z'); return e.textContent; }
        case 'classListAdd': { const e = div(); e.classList.add(v); return e.getAttribute('class'); }
        case 'classListRemove': { const e = div(); e.setAttribute('class', v + ' a'); e.classList.remove(v); return e.getAttribute('class'); }
        case 'hidden': { const e = div(); e.hidden = v; return e.getAttribute('hidden'); }
        case 'toggleEvent': { const e = new ToggleEvent('toggle', {oldState: v, newState: entry.other}); return [e.oldState, e.newState]; }
        case 'commandEvent': return new CommandEvent('command', {command: v}).command;
        case 'compositionEvent': return new CompositionEvent('compositionend', {data: v}).data;
        case 'errorEvent': return new ErrorEvent('error', {message: v}).message;
        case 'blobType': return new Blob([], {type: v}).type;
        case 'getAttributeNames': { const e = div(); e.setAttribute(v, '1'); e.setAttribute('b', '2'); return e.getAttributeNames(); }
        case 'hiddenGetter': { const e = div(); e.setAttribute('hidden', 'until-found'); return e.hidden; }
      }
      throw new Error('unknown op ' + entry.op);
    };
    const result = {};
    for (const entry of cases) result[entry.id] = run(entry);
    return result;
  }, cases);
  const result = {browser: browser.version(), headless: 'new', origin: 'http://localhost', values};
  writeFileSync(out, JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result, null, 1));
} finally {
  await browser.close();
}
