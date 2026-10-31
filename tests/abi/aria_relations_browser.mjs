// Chromium oracle for tests/abi/aria_relations.py: writes tests/fixtures/aria-relations-oracle.json.
// Records each step's reflected element arrays, content attributes, accessible name and description, and the
// accessibility relations of the subject, through both the attribute route and the element reflection route.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

export const page = '<!doctype html><body><span id=l1>First</span><span id=l2>Second</span><p id=d1>Describe</p>' +
  '<p id=d2>More</p><p id=e1>Error</p><p id=x1>Detail</p><p id=f1>Next</p><button id=b>Plain</button>' +
  '<div id=list role=listbox aria-label=Choices tabindex=0><div id=o1 role=option>One</div><div id=o2 role=option>Two</div></div>' +
  '<input id=i aria-invalid=true><div id=host></div>';
// Each step: [name, subject, operation, attribute or member, argument]. Operations: attr sets a content attribute
// (null removes it), elements sets the reflection to the listed IDs (null clears), remove removes the element with the
// argument's ID, shadow sets the reflection to an element inside #host's shadow root.
export const members = ['ariaActionsElements', 'ariaControlsElements', 'ariaDescribedByElements', 'ariaDetailsElements',
  'ariaErrorMessageElements', 'ariaFlowToElements', 'ariaLabelledByElements'];
export const relations = {activedescendant: 'aria-activedescendant', controls: 'aria-controls', describedby: 'aria-describedby',
  details: 'aria-details', errormessage: 'aria-errormessage', flowto: 'aria-flowto', labelledby: 'aria-labelledby', owns: 'aria-owns'};
export const steps = [
  ['attribute labelledby l2 l1', 'b', 'attr', 'aria-labelledby', 'l2 l1'],
  ['attribute describedby d1', 'b', 'attr', 'aria-describedby', 'd1'],
  ['attribute controls list', 'i', 'attr', 'aria-controls', 'list'],
  ['attribute errormessage e1', 'i', 'attr', 'aria-errormessage', 'e1'],
  ['attribute details x1', 'b', 'attr', 'aria-details', 'x1'],
  ['attribute flowto f1', 'b', 'attr', 'aria-flowto', 'f1'],
  ['attribute owns o1', 'list', 'attr', 'aria-owns', 'o1'],
  ['attribute activedescendant o2', 'list', 'attr', 'aria-activedescendant', 'o2'],
  ['reset b and i', 'b', 'reset', null, null],
  ['elements labelledby [l1, l2]', 'b', 'elements', 'ariaLabelledByElements', ['l1', 'l2']],
  ['elements labelledby [l2, l1, l2]', 'b', 'elements', 'ariaLabelledByElements', ['l2', 'l1', 'l2']],
  ['elements labelledby [l2, l1]', 'b', 'elements', 'ariaLabelledByElements', ['l2', 'l1']],
  ['elements describedby [d2, d1]', 'b', 'elements', 'ariaDescribedByElements', ['d2', 'd1']],
  ['elements details [x1]', 'b', 'elements', 'ariaDetailsElements', ['x1']],
  ['elements flowto [f1]', 'b', 'elements', 'ariaFlowToElements', ['f1']],
  ['elements actions [l1]', 'b', 'elements', 'ariaActionsElements', ['l1']],
  ['elements controls [list]', 'i', 'elements', 'ariaControlsElements', ['list']],
  ['elements errormessage [e1]', 'i', 'elements', 'ariaErrorMessageElements', ['e1']],
  ['attribute labelledby l1 replaces the elements', 'b', 'attr', 'aria-labelledby', 'l1'],
  ['elements labelledby [l2] replaces the attribute', 'b', 'elements', 'ariaLabelledByElements', ['l2']],
  ['remove d2', 'b', 'remove', null, 'd2'],
  ['shadow-root target', 'b', 'shadow', 'ariaLabelledByElements', null],
  ['elements describedby null clears', 'b', 'elements', 'ariaDescribedByElements', null],
  ['elements controls [] empties', 'i', 'elements', 'ariaControlsElements', []],
];

if (import.meta.url === `file:///${process.argv[1].replaceAll('\\', '/')}`) {
  const browser = await chromium.launch({headless: true});
  const result = {browser: browser.version(), page, members, relations, steps: []};
  try {
    const context = await browser.newContext();
    const tab = await context.newPage();
    await tab.setContent(page);
    await tab.evaluate(() => { const root = document.getElementById('host').attachShadow({mode: 'open'}); const s = document.createElement('span'); s.id = 'inner'; s.textContent = 'Inner'; root.append(s); });
    const cdp = await context.newCDPSession(tab);
    await cdp.send('Accessibility.enable');
    await cdp.send('DOM.getDocument');
    const axOf = async id => {
      const {result: object} = await cdp.send('Runtime.evaluate', {expression: `document.getElementById('${id}')`});
      const {node} = await cdp.send('DOM.describeNode', {objectId: object.objectId});
      const {nodes} = await cdp.send('Accessibility.getPartialAXTree', {backendNodeId: node.backendNodeId, fetchRelatives: false});
      const n = nodes[0];
      const related = name => ((n.properties || []).find(p => p.name === name)?.value?.relatedNodes || []).map(r => r.idref ?? null);
      return {name: n.name?.value ?? '', description: n.description?.value ?? '',
              relations: Object.fromEntries(Object.keys(relations).map(k => [k, related(k)]))};
    };
    for (const [name, subject, operation, key, argument] of steps) {
      const state = await tab.evaluate(([subject, operation, key, argument, members, relations]) => {
        const s = document.getElementById(subject);
        if (operation === 'attr') argument === null ? s.removeAttribute(key) : s.setAttribute(key, argument);
        else if (operation === 'elements') s[key] = argument === null ? null : argument.map(id => document.getElementById(id));
        else if (operation === 'remove') document.getElementById(argument).remove();
        else if (operation === 'shadow') s[key] = [document.getElementById('host').shadowRoot.getElementById('inner')];
        else if (operation === 'reset') for (const e of [document.getElementById('b'), document.getElementById('i')]) for (const a of Object.values(relations)) e.removeAttribute(a);
        const reflected = Object.fromEntries(members.map(m => [m, s[m] === null ? null : s[m].map(e => e.id)]));
        reflected.ariaActiveDescendantElement = s.ariaActiveDescendantElement?.id ?? null;
        const attributes = Object.fromEntries(Object.values(relations).map(a => [a, s.getAttribute(a)]));
        return {reflected, attributes, sameArray: s.ariaLabelledByElements === s.ariaLabelledByElements};
      }, [subject, operation, key, argument, members, relations]);
      result.steps.push({name, subject, operation, key, argument, ...state, ax: await axOf(subject)});
    }
  } finally { await browser.close(); }
  writeFileSync(new URL('../fixtures/aria-relations-oracle.json', import.meta.url), JSON.stringify(result, null, 1) + '\n');
  console.log('aria relations oracle', result.browser, result.steps.length);
}
