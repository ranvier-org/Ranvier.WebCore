// Chromium oracle for tests/fixtures/tree-traversal-cases.json: writes tests/fixtures/tree-traversal-oracle.json.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const spec = JSON.parse(readFileSync('tests/fixtures/tree-traversal-cases.json', 'utf8'));
const browser = await chromium.launch({headless: true});
try {
  const only = process.argv[2];
  if (only) spec.cases = spec.cases.filter(c => c.name === only);
  const page = await browser.newPage();
  await page.setContent('<!doctype html><title>traversal</title>');
  const result = await page.evaluate(spec => {
    const label = node => {
      if (!node) return null;
      switch (node.nodeType) {
        case 1: return node.getAttribute('id');
        case 3: return '#' + node.data;
        case 7: return '?' + node.target + ' ' + node.data;
        case 8: return '!' + node.data;
        case 9: return '#document';
      }
      return node.nodeName;
    };
    const parse = () => new DOMParser().parseFromString(spec.markup, 'image/svg+xml');
    const find = (doc, wanted) => {
      if (wanted === '#document') return doc;
      const walker = doc.createTreeWalker(doc, 0xFFFFFFFF);
      for (let node = walker.currentNode; node; node = walker.nextNode()) if (label(node) === wanted) return node;
      throw new Error('no node ' + wanted);
    };
    const cases = [];
    for (const c of spec.cases) {
      const doc = parse();
      let calls = [], traversal = null, seen = {}, mutated = false, reentered = false;
      const f = c.filter;
      const filter = f === null ? null : node => {
        const name = label(node);
        calls.push(name);
        seen[name] = (seen[name] || 0) + 1;
        if (f.kind === 'map') return f.map[name] ?? 1;
        if (f.kind === 'throw' && name === f.on && seen[name] <= f.times) { calls.push('throw'); throw new Error('filter failure'); }
        if (f.kind === 'mutate' && name === f.on && !mutated) { mutated = true; const gone = find(doc, f.remove); gone.remove(); calls.push('removed:' + f.remove); }
        if (f.kind === 'reenter' && name === f.on && !reentered) {
          reentered = true;
          try { calls.push('reenter:' + label(traversal.nextNode())); } catch (e) { calls.push('reenter:' + e.name); }
        }
        if (f.kind === 'reenterOther' && name === f.on && !reentered) {
          reentered = true;
          const other = doc.createTreeWalker(find(doc, 'b'), 1, () => 1);
          calls.push('other:' + label(other.nextNode()) + ',' + label(other.nextNode()));
        }
        return 1;
      };
      const root = find(doc, c.root);
      traversal = c.kind === 'walker' ? doc.createTreeWalker(root, c.mask, filter) : doc.createNodeIterator(root, c.mask, filter);
      // Chromium 156 crashes the renderer when referenceNode is read after a filter re-entered its NodeIterator.
      const unreadable = () => c.kind === 'iterator' && reentered;
      const state = () => unreadable() ? 'unreadable' : c.kind === 'walker' ? [label(traversal.currentNode)]
        : [label(traversal.referenceNode), traversal.pointerBeforeReferenceNode];
      const getters = {root: label(traversal.root), whatToShow: traversal.whatToShow, filterSame: traversal.filter === filter, state: state()};
      const methods = {next: 'nextNode', prev: 'previousNode', parent: 'parentNode', first: 'firstChild', last: 'lastChild',
                       prevSib: 'previousSibling', nextSib: 'nextSibling', detach: 'detach'};
      const steps = [];
      for (const step of c.steps) {
        calls = [];
        let outcome;
        try {
          if (typeof step === 'string') outcome = step === 'detach' ? 'undefined' : label(traversal[methods[step]]());
          else if (step.set) { traversal.currentNode = find(doc, step.set); outcome = 'set'; }
          else { find(doc, step.remove).remove(); outcome = 'removed'; }
          if (step === 'detach') traversal.detach();
        } catch (e) { outcome = 'throw:' + e.name; }
        steps.push({result: outcome, calls, state: state()});
      }
      cases.push({name: c.name, getters, steps});
    }
    const doc = parse();
    const walker = doc.createTreeWalker(doc, 0xFFFFFFFF);
    let nullCurrent;
    try { walker.currentNode = null; nullCurrent = 'no exception'; } catch (e) { nullCurrent = e.name; }
    // acceptNode objects are a browser-only NodeFilter form: they traverse as the equivalent function.
    const order = make => { const w = doc.createTreeWalker(find(doc, 'root'), 1, make()); const out = []; for (let n; (n = w.nextNode());) out.push(label(n)); return out.join(','); };
    const mapped = node => ({b: 2, c: 3})[label(node)] ?? 1;
    const objectForm = order(() => ({acceptNode: mapped})) === order(() => mapped);
    return {cases, nullCurrent, objectFormMatchesFunction: objectForm, nullFilterGetter: doc.createNodeIterator(doc).filter};
  }, spec);
  const text = JSON.stringify({browser: browser.version(), ...result}, null, 1) + '\n';
  if (!only) writeFileSync('tests/fixtures/tree-traversal-oracle.json', text);
  console.log('cases', result.cases.length, 'nullCurrent', result.nullCurrent, 'objectForm', result.objectFormMatchesFunction);
} finally { await browser.close(); }
