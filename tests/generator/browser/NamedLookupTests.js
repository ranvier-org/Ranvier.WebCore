import { sheets, sheet, value, assign, remove } from './NamedLookupBrowser.js';

let assertions = 0;
const failures = [];
function same(actual, expected, label) {
  assertions++;
  if (actual !== expected) failures.push(`${label}: expected ${String(expected)}, received ${String(actual)}`);
}
function style(doc, id, parent = doc.head) {
  const element = doc.createElement('style');
  element.id = id;
  element.textContent = '.named-probe { color: rgb(17, 23, 31); }';
  parent.append(element);
  return element;
}
function documentCases(doc) {
  const list = sheets(doc);
  same(list, doc.styleSheets, 'typed getter preserves list identity');
  same(doc.styleSheets.length, 0, 'initially empty document');
  same(sheet(list, 'length'), null, 'empty list reserved name');
  const first = style(doc, 'first');
  const second = style(doc, 'second');
  same(doc.styleSheets.length, doc.defaultView ? 2 : 0, 'provider list population');
  same(first.sheet !== null && second.sheet !== null, true, 'sheet creation precondition');
  same(sheet(list, 'first'), first.sheet, 'first document ID');
  same(sheet(list, 'second'), second.sheet, 'second document ID');
  for (const name of ['length', 'item', '0', '__proto__', 'a]b:#λ']) {
    same(sheet(doc.styleSheets, name), null, `missing ${name}`);
    second.id = name;
    same(sheet(doc.styleSheets, name), second.sheet, `present ${name}`);
    same(sheet(doc.styleSheets, 'first'), first.sheet, `first remains distinct for ${name}`);
    second.id = 'second';
    same(sheet(doc.styleSheets, name), null, `renamed ${name}`);
  }
  first.id = 'duplicate';
  second.id = 'duplicate';
  same(sheet(doc.styleSheets, 'duplicate'), first.sheet, 'first duplicate style wins');
  const blocker = doc.createElement('div');
  blocker.id = 'duplicate';
  doc.head.prepend(blocker);
  same(sheet(doc.styleSheets, 'duplicate'), null, 'preceding non-style ID blocks style');
  blocker.remove();
  first.remove();
  same(sheet(doc.styleSheets, 'duplicate'), second.sheet, 'removal exposes later duplicate');
  second.id = 'second';
  second.setAttribute('name', 'name-only');
  same(sheet(doc.styleSheets, 'name-only'), null, 'name attribute is not an ID');
  const link = doc.createElement('link');
  link.id = 'link';
  link.rel = 'stylesheet';
  doc.head.append(link);
  same(sheet(doc.styleSheets, 'link'), null, 'link ID excluded');
  const svgStyle = doc.createElementNS('http://www.w3.org/2000/svg', 'style');
  svgStyle.id = 'svg-style';
  svgStyle.textContent = '.named-probe { opacity: 0.5; }';
  doc.body.append(svgStyle);
  same(sheet(doc.styleSheets, 'svg-style'), null, 'SVG style ID excluded');
  second.id = '';
  same(sheet(doc.styleSheets, ''), null, 'empty ID');
  same(sheet(doc.styleSheets, null), null, 'managed null name normalized to empty');
}
try {
  documentCases(document.implementation.createHTMLDocument('named lookup'));
  const frame = document.createElement('iframe');
  document.body.append(frame);
  documentCases(frame.contentDocument);

  const remote = await new Promise((resolve, reject) => {
    const script = frame.contentDocument.createElement('script');
    script.type = 'module';
    const moduleUrl = new URL('./NamedLookupBrowser.js', import.meta.url).href;
    frame.contentWindow.completeNamedLookup = resolve;
    script.textContent = `import * as api from ${JSON.stringify(moduleUrl)}; globalThis.completeNamedLookup(api);`;
    script.onerror = () => reject(new Error('iframe facade module failed to load'));
    frame.contentDocument.body.append(script);
  });
  const remoteDocument = frame.contentDocument.implementation.createHTMLDocument('remote facade');
  const remoteList = remote.sheets(remoteDocument);
  same(remoteList.length, 0, 'remote list initially empty');
  const remoteStyle = style(remoteDocument, 'remote-style');
  same(remoteList.length, 0, 'remote detached list stays empty');
  same(sheet(remoteList, 'remote-style'), remoteStyle.sheet, 'child getter to parent named lookup');
  const localDocument = document.implementation.createHTMLDocument('parent facade');
  const localList = sheets(localDocument);
  same(localList.length, 0, 'local list initially empty');
  const localStyle = style(localDocument, 'local-style');
  same(localList.length, 0, 'local detached list stays empty');
  same(remote.sheet(localList, 'local-style'), localStyle.sheet, 'parent getter to child named lookup');
  frame.remove();

  const host = document.createElement('div');
  document.body.append(host);
  const shadow = host.attachShadow({ mode: 'open' });
  const outside = style(document, 'shadow-name');
  style(document, 'shadow-name', shadow);
  same(shadow.styleSheets.length, 1, 'shadow stylesheet precondition');
  same(sheet(shadow.styleSheets, 'shadow-name'), null, 'shadow list does not use document ID');
  same(sheet(document.styleSheets, 'shadow-name'), outside.sheet, 'document lookup preserves association');
  outside.remove();
  host.remove();

  for (const [namespace, tag] of [['http://www.w3.org/2000/svg', 'svg'], ['http://www.w3.org/1998/Math/MathML', 'math']]) {
    const element = document.createElementNS(namespace, tag);
    const map = element.dataset;
    const prototype = Object.getPrototypeOf(map);
    same(typeof map, 'object', `${tag} dataset precondition`);
    for (const name of ['ordinary', 'toString', 'constructor', 'hasOwnProperty', '__proto__']) {
      same(value(map, name), '', `${tag} missing ${name}`);
      assign(map, name, `${tag}:${name}`);
      same(value(map, name), `${tag}:${name}`, `${tag} present ${name}`);
      same(Object.getPrototypeOf(map), prototype, `${tag} assignment preserves prototype ${name}`);
      remove(map, name);
      same(value(map, name), '', `${tag} removed ${name}`);
    }
  }
} catch (error) {
  failures.push(error.stack || String(error));
}
document.body.dataset.result = failures.length ? 'NAMED_LOOKUP_FAIL' : 'NAMED_LOOKUP_PASS';
document.body.dataset.assertions = String(assertions);
document.body.textContent = JSON.stringify({ assertions, failures });
