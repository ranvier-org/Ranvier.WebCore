// Chromium oracle for tests/abi/host_string_nul.py: writes tests/fixtures/host-string-nul-oracle.json. Each case of
// tests/fixtures/host-string-nul-cases.json passes a string holding U+0000 to the web platform member a hand-written
// export runs, and records the value read back. Input-method, key and text-insertion cases drive the DevTools Input
// domain, or execCommand('insertText') for the paste and drop insertions.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const cases = JSON.parse(readFileSync('tests/fixtures/host-string-nul-cases.json', 'utf8')).cases;
const out = process.argv[2] || 'tests/fixtures/host-string-nul-oracle.json';
// The web platform member each op stands for, where it is not the member the export calls.
const equivalents = {
  loadHtml: 'DOMParser text/html', loadHtmlInner: 'DOMParser text/html', loadHtmlTitle: 'DOMParser text/html',
  loadSvg: 'DOMParser image/svg+xml', parseFragment: 'Range.createContextualFragment',
  parseFragmentComment: 'Range.createContextualFragment', imeComposition: 'Input.imeSetComposition',
  imeCommit: 'Input.imeSetComposition then Input.insertText', axSetValueInput: 'HTMLInputElement.value',
  axSetValueTextarea: 'HTMLTextAreaElement.value', clipboardOffer: "execCommand('insertText')",
  clipboardWrite: 'Element.outerHTML of the selected paragraph, for the copied text/html', dragDataAdd: "execCommand('insertText')",
  hostKeyChar: 'Input.insertText; a DevTools char key event carries at most four UTF-16 units, ending at U+0000', createEventType: 'Document.createEvent and Event.initEvent',
  constructEventType: 'new Event', targetListenerType: 'new EventTarget',
};
const inserted = new Set(['imeComposition', 'imeCommit', 'hostKeyChar']);
const browser = await chromium.launch({headless: true});
try {
  const page = await browser.newPage();
  await page.route('http://localhost/strings', route => route.fulfill({contentType: 'text/html', body: '<!doctype html><title>strings</title><body>'}));
  await page.goto('http://localhost/strings');
  const cdp = await page.context().newCDPSession(page);
  const values = {};
  for (const entry of cases) {
    if (inserted.has(entry.op)) {
      await page.evaluate(() => { document.body.replaceChildren(); const t = document.body.appendChild(document.createElement('textarea')); t.focus(); });
      const v = entry.value;
      if (entry.op === 'imeComposition')
        await cdp.send('Input.imeSetComposition', {text: v, selectionStart: v.length, selectionEnd: v.length});
      if (entry.op === 'imeCommit') {
        await cdp.send('Input.imeSetComposition', {text: 'x', selectionStart: 1, selectionEnd: 1});
        await cdp.send('Input.insertText', {text: v});
      }
      if (entry.op === 'hostKeyChar')
        await cdp.send('Input.insertText', {text: v});
      values[entry.id] = await page.evaluate(() => document.querySelector('textarea').value);
      continue;
    }
    values[entry.id] = await page.evaluate(entry => {
      const v = entry.value;
      document.body.replaceChildren();
      const div = () => document.body.appendChild(document.createElement('div'));
      const html = () => new DOMParser().parseFromString(v, 'text/html');
      const fragment = () => { const r = document.createRange(); r.selectNodeContents(document.body); return r.createContextualFragment(v); };
      const insertInto = () => { const t = document.body.appendChild(document.createElement('textarea')); t.focus(); document.execCommand('insertText', false, v); return t.value; };
      const fires = target => {
        const fired = [];
        target.addEventListener(v, () => fired.push(v));
        target.addEventListener(v.split('\0')[0], () => fired.push('prefix'));
        target.dispatchEvent(new Event(v));
        return [fired.includes(v), fired.includes('prefix')];
      };
      switch (entry.op) {
        case 'loadHtml': return html().body.textContent;
        case 'loadHtmlInner': return html().body.innerHTML;
        case 'loadHtmlTitle': return html().title;
        case 'loadSvg': return new DOMParser().parseFromString(v, 'image/svg+xml').getElementsByTagName('parsererror').length > 0;
        case 'parseFragment': return fragment().textContent;
        case 'parseFragmentComment': return fragment().firstChild.data;
        case 'setInnerHtml': { const e = div(); e.innerHTML = v; return e.innerHTML; }
        case 'setTextContent': case 'setStringTextContent': { const e = div(); e.textContent = v; return e.textContent; }
        case 'createText': return document.createTextNode(v).data;
        case 'createComment': return document.createComment(v).data;
        case 'setStringData': { const t = document.createTextNode('x'); t.data = v; return t.data; }
        case 'setStringValueInput': case 'axSetValueInput': { const e = document.body.appendChild(document.createElement('input')); e.value = v; return e.value; }
        case 'setStringValueTextarea': case 'axSetValueTextarea': { const e = document.body.appendChild(document.createElement('textarea')); e.value = v; return e.value; }
        case 'setStringTitleDocument': { const d = document.implementation.createHTMLDocument(''); d.title = v; return d.title; }
        case 'setStringTitleElement': { const e = div(); e.title = v; return e.getAttribute('title'); }
        case 'setStringValueOption': { const e = document.createElement('option'); e.value = v; return e.getAttribute('value'); }
        case 'setAttribute': { const e = div(); e.setAttribute('data-v', v); return e.getAttribute('data-v'); }
        case 'getElementById': {
          div().id = v.split('\0')[0];
          div().id = v;
          const found = document.getElementById(v);
          return found ? found.id : null;
        }
        case 'classAdd': { const e = div(); e.classList.add(v); return e.getAttribute('class'); }
        case 'classContains': { const e = div(); e.setAttribute('class', v); return e.classList.contains(v); }
        case 'classRemove': { const e = div(); e.setAttribute('class', v + ' a'); e.classList.remove(v); return e.getAttribute('class'); }
        case 'clipboardOffer': case 'dragDataAdd': return insertInto();
        case 'clipboardWrite': { const e = document.body.appendChild(document.createElement('p')); e.textContent = v; return e.outerHTML.includes(v); }
        case 'setStyleCustom': { const e = div(); e.style.setProperty('--x', v); return e.style.getPropertyValue('--x'); }
        case 'setStyleContent': { const e = div(); e.style.setProperty('content', v); return e.style.getPropertyValue('content'); }
        case 'nodeListenerType': return fires(div());
        case 'createEventType': { const e = document.createEvent('Event'); e.initEvent(v, false, false); return e.type; }
        case 'constructEventType': return new Event(v).type;
        case 'targetListenerType': return fires(new EventTarget());
      }
      throw new Error('unknown op ' + entry.op);
    }, entry);
  }
  const result = {browser: browser.version(), headless: 'new', origin: 'http://localhost', equivalents, values};
  writeFileSync(out, JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(values));
} finally {
  await browser.close();
}
