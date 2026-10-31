// Chromium oracle for tests/fixtures/form-collections-cases.json: writes tests/fixtures/form-collections-oracle.json.
// Each case runs in a fresh page, synchronously, so the result is recorded before any form navigation starts.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const spec = JSON.parse(readFileSync('tests/fixtures/form-collections-cases.json', 'utf8'));
const browser = await chromium.launch({headless: true});
const cases = [];
const version = browser.version();
try {
  const only = process.argv[2];
  for (const c of spec.cases.filter(c => !only || c.name === only)) {
    const page = await browser.newPage();
    await page.route('**/*', route => route.abort());
    await page.setContent(spec.markup);
    const steps = await page.evaluate(steps => {
      const label = node => node ? (node.id || node.nodeName) : null;
      const byId = id => id === null ? null : document.getElementById(id);
      const vars = {};
      const entries = data => [...data.entries()].map(([name, value]) => [name, typeof value === 'string' ? value : {file: true}]);
      const entry = value => value === null ? null : typeof value === 'string' ? value : {file: true};
      const named = value => value === null ? null : value instanceof RadioNodeList ? {radioNodeList: [...value].map(label)} : {element: label(value)};
      let events = [];
      const describe = event => {
        const base = {type: event.type, trusted: event.isTrusted, bubbles: event.bubbles, cancelable: event.cancelable};
        if (event instanceof SubmitEvent) base.submitter = label(event.submitter);
        if (event instanceof FormDataEvent) base.entries = entries(event.formData);
        return base;
      };
      const attempt = action => {
        events = [];
        try {
          const value = action();
          return {status: 'ok', value: value === undefined ? null : value, events};
        } catch (error) {
          return {status: error.name, events};
        }
      };
      const run = s => {
        switch (s.op) {
          case 'elementsList': return [...byId(s.form).elements].map(label);
          case 'elementsLength': return byId(s.form).elements.length;
          case 'elementsItem': return label(byId(s.form).elements.item(s.index));
          case 'elementsNamed': return named(byId(s.form).elements.namedItem(s.name));
          case 'remove': byId(s.id).remove(); return null;
          case 'append': byId(s.parent).append(byId(s.id)); return null;
          case 'setAttribute': byId(s.id).setAttribute(s.name, s.value); return null;
          case 'removeAttribute': byId(s.id).removeAttribute(s.name); return null;
          case 'optionsList': return [...byId(s.select).options].map(label);
          case 'optionsLength': return byId(s.select).options.length;
          case 'optionsItem': return label(byId(s.select).options.item(s.index));
          case 'optionsNamed': return label(byId(s.select).options.namedItem(s.name));
          case 'selectedIndex': return byId(s.select).options.selectedIndex;
          case 'setSelectedIndex': byId(s.select).options.selectedIndex = s.value; return null;
          case 'optionsAdd': return attempt(() => {
            const created = document.querySelector('#' + s.element) || window.__created[s.element];
            const before = s.before === null ? null : 'index' in s.before ? s.before.index : byId(s.before.element);
            byId(s.select).options.add(created, before);
          });
          case 'optionsRemove': byId(s.select).options.remove(s.index); return null;
          case 'optionsSetLength': byId(s.select).options.length = s.length; return null;
          case 'optionsSetItem': return attempt(() => {
            byId(s.select).options[s.index] = s.option === null ? null : (byId(s.option) || window.__created[s.option]);
          });
          case 'listen': {
            byId(s.form).addEventListener(s.type, event => {
              if (s.action === 'preventDefault') event.preventDefault();
              if (s.action === 'edit') for (const e of s.edits) {
                if (e.op === 'append') event.formData.append(e.name, e.value);
                if (e.op === 'delete') event.formData.delete(e.name);
                if (e.op === 'set') event.formData.set(e.name, e.value);
              }
              events.push(describe(event));
            });
            return null;
          }
          case 'requestSubmit': return attempt(() => {
            const submitter = byId(s.submitter);
            if (s.submitter === null) byId(s.form).requestSubmit(); else byId(s.form).requestSubmit(submitter);
          });
          case 'submit': return attempt(() => { byId(s.form).submit(); });
          case 'formDataNew': return attempt(() => {
            vars[s.var] = s.form === null ? new FormData() : new FormData(byId(s.form), byId(s.submitter));
          });
          case 'formDataEntries': return entries(vars[s.var]);
          case 'formDataAppend': vars[s.var].append(s.name, s.value); return null;
          case 'formDataSet': vars[s.var].set(s.name, s.value); return null;
          case 'formDataDelete': vars[s.var].delete(s.name); return null;
          case 'formDataGet': return entry(vars[s.var].get(s.name));
          case 'formDataGetAll': return vars[s.var].getAll(s.name).map(entry);
          case 'formDataHas': return vars[s.var].has(s.name);
          case 'constructSubmitEvent': return attempt(() => describe(new SubmitEvent(s.type, {submitter: byId(s.submitter), bubbles: s.bubbles, cancelable: s.cancelable})));
          case 'constructFormDataEvent': {
            const event = new FormDataEvent(s.type, {formData: vars[s.var], bubbles: s.bubbles, cancelable: s.cancelable});
            return {sameFormData: event.formData === vars[s.var], event: describe(event)};
          }
          case 'dispatchFormDataEvent': return attempt(() => {
            const event = new FormDataEvent(s.type, {formData: vars[s.var]});
            return {dispatched: byId(s.form).dispatchEvent(event), event: describe(event)};
          });
        }
        throw new Error('unknown op ' + s.op);
      };
      window.__created = {};
      const results = [];
      for (const s of steps) {
        if (s.op === 'create') {
          const e = document.createElement(s.tag); e.id = s.id; e.textContent = s.text; window.__created[s.id] = e;
          results.push({op: s.op, result: null});
          continue;
        }
        results.push({op: s.op, result: run(s)});
      }
      return results;
    }, c.steps);
    cases.push({name: c.name, steps});
    await page.close();
  }
} finally {
  await browser.close();
}
writeFileSync('tests/fixtures/form-collections-oracle.json', JSON.stringify({browser: 'chromium ' + version, cases}, null, 2) + '\n');
console.log('FORM_COLLECTIONS_ORACLE', version, cases.length, 'cases');
