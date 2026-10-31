// RED measurement of ElementInternals and reflected ARIA element relationships in Chromium, with the accessibility
// node each change produces. Writes red-chromium.json next to this file.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const page = '<!doctype html><body><span id=l1>First</span><span id=l2>Second</span><p id=d1>Describe</p>' +
  '<button id=b>Plain</button><div id=list role=listbox aria-label=Choices><div id=o1 role=option>One</div><div id=o2 role=option>Two</div></div>' +
  '<x-toggle id=t></x-toggle><x-plain id=p></x-plain><input id=i>';
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version(), page, steps: []};
try {
  const context = await browser.newContext();
  const tab = await context.newPage();
  await tab.setContent(page);
  const cdp = await context.newCDPSession(tab);
  await cdp.send('Accessibility.enable');
  await cdp.send('DOM.getDocument');
  const ax = async id => {
    const {result} = await cdp.send('Runtime.evaluate', {expression: `document.getElementById('${id}')`});
    const {node} = await cdp.send('DOM.describeNode', {objectId: result.objectId});
    const {nodes} = await cdp.send('Accessibility.getPartialAXTree', {backendNodeId: node.backendNodeId, fetchRelatives: false});
    const n = nodes[0];
    const prop = name => (n.properties || []).find(p => p.name === name)?.value;
    const rel = name => (prop(name)?.relatedNodes || []).map(r => r.idref ?? r.text ?? r.backendDOMNodeId);
    return {role: n.role?.value, name: n.name?.value, description: n.description?.value, pressed: prop('pressed')?.value,
            activedescendant: rel('activedescendant'), controls: rel('controls'), labelledby: rel('labelledby'), describedby: rel('describedby'), ignored: n.ignored};
  };
  const step = async (name, script, ids) => {
    let result, error = null;
    try { result = await tab.evaluate(script); } catch (e) { error = String(e.message || e).split('\n')[0]; }
    const tree = {};
    for (const id of ids) tree[id] = await ax(id);
    out.steps.push({name, result, error, ax: tree});
  };
  await step('define x-toggle with attachInternals', `(() => {
    customElements.define('x-toggle', class extends HTMLElement { constructor() { super(); this.internals = this.attachInternals(); } });
    customElements.define('x-plain', class extends HTMLElement {});
    const t = document.getElementById('t');
    const attempt = f => { try { f(); return 'ok'; } catch (e) { return e.name; } };
    return {hasInternals: !!t.internals,
            internalsMembers: Object.getOwnPropertyNames(ElementInternals.prototype).filter(n => n.startsWith('aria') || n === 'role').length,
            secondAttach: attempt(() => t.attachInternals()),
            builtinElement: attempt(() => document.getElementById('b').attachInternals()),
            undefinedCustomElement: attempt(() => document.createElement('x-undefined').attachInternals())};
  })()`, ['t']);
  await step('internals.role = button, ariaLabel, ariaPressed', `(() => { const i = document.getElementById('t').internals; i.role = 'button'; i.ariaLabel = 'Toggle'; i.ariaPressed = 'true';
    return {role: i.role, ariaLabel: i.ariaLabel, hostRoleAttribute: document.getElementById('t').getAttribute('role')}; })()`, ['t']);
  await step('host attributes override internals', `(() => { const t = document.getElementById('t'); t.setAttribute('aria-label', 'Host label'); t.setAttribute('role', 'switch');
    return {internalsLabel: t.internals.ariaLabel}; })()`, ['t']);
  await step('remove host attributes', `(() => { const t = document.getElementById('t'); t.removeAttribute('aria-label'); t.removeAttribute('role'); return null; })()`, ['t']);
  await step('internals.ariaLabelledByElements', `(() => { const t = document.getElementById('t'); t.removeAttribute('aria-label'); const i = t.internals; i.ariaLabel = null;
    i.ariaLabelledByElements = [document.getElementById('l1'), document.getElementById('l2')];
    return {count: i.ariaLabelledByElements.length}; })()`, ['t']);
  await step('button.ariaLabelledByElements = [l2, l1]', `(() => { const b = document.getElementById('b'); b.ariaLabelledByElements = [document.getElementById('l2'), document.getElementById('l1')];
    return {attribute: b.getAttribute('aria-labelledby'), ids: b.ariaLabelledByElements.map(e => e.id), frozen: Object.isFrozen(b.ariaLabelledByElements), sameArray: b.ariaLabelledByElements === b.ariaLabelledByElements}; })()`, ['b']);
  await step('button.ariaDescribedByElements = [d1]', `(() => { const b = document.getElementById('b'); b.ariaDescribedByElements = [document.getElementById('d1')];
    return {attribute: b.getAttribute('aria-describedby'), ids: b.ariaDescribedByElements.map(e => e.id)}; })()`, ['b']);
  await step('setAttribute aria-labelledby replaces the elements', `(() => { const b = document.getElementById('b'); b.setAttribute('aria-labelledby', 'l1');
    return {ids: b.ariaLabelledByElements.map(e => e.id)}; })()`, ['b']);
  await step('listbox.ariaActiveDescendantElement = o2', `(() => { const l = document.getElementById('list'); l.ariaActiveDescendantElement = document.getElementById('o2');
    return {attribute: l.getAttribute('aria-activedescendant'), id: l.ariaActiveDescendantElement?.id}; })()`, ['list']);
  await step('input.ariaControlsElements = [list]', `(() => { const i = document.getElementById('i'); i.ariaControlsElements = [document.getElementById('list')];
    return {attribute: i.getAttribute('aria-controls'), ids: i.ariaControlsElements.map(e => e.id)}; })()`, ['i']);
  await step('remove o2 from the document', `(() => { const l = document.getElementById('list'); document.getElementById('o2').remove();
    return {id: l.ariaActiveDescendantElement?.id ?? null}; })()`, ['list']);
  await step('an element in a shadow root is hidden from the light tree', `(() => { const host = document.createElement('div'); document.body.append(host); const root = host.attachShadow({mode: 'open'});
    const inner = document.createElement('span'); inner.id = 'inner'; inner.textContent = 'Inner'; root.append(inner); const b = document.getElementById('b'); b.ariaLabelledByElements = [inner];
    return {ids: b.ariaLabelledByElements.map(e => e.id)}; })()`, ['b']);
  await step('null clears', `(() => { const b = document.getElementById('b'); b.ariaLabelledByElements = null; b.ariaDescribedByElements = null;
    return {labelled: b.ariaLabelledByElements, attribute: b.getAttribute('aria-labelledby')}; })()`, ['b']);
  out.members = await tab.evaluate(() => ({element: Object.getOwnPropertyNames(Element.prototype).filter(n => /^aria.*Element/.test(n)),
    internals: Object.getOwnPropertyNames(ElementInternals.prototype)}));
} finally { await browser.close(); }
writeFileSync(new URL('./red-chromium.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log('ok', out.browser, out.steps.length);
