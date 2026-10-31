// Chromium oracle for tests/abi/url_values.py: writes tests/fixtures/url-oracle.json from tests/fixtures/url-cases.json.
// Records URL parsing, relative resolution and setters, URLSearchParams operations and URLPattern matching.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const fixtures = new URL('../fixtures/', import.meta.url);
const cases = JSON.parse(readFileSync(new URL('url-cases.json', fixtures), 'utf8'));

// Runs in the page. Every result is plain JSON; an exception becomes {error: name}.
function record(cases) {
  const fields = ['href', 'origin', 'protocol', 'username', 'password', 'host', 'hostname', 'port', 'pathname', 'search', 'hash'];
  const components = ['protocol', 'username', 'password', 'hostname', 'port', 'pathname', 'search', 'hash'];
  const attempt = f => { try { return f(); } catch (e) { return {error: e.name}; } };
  const snapshot = u => Object.fromEntries(fields.map(k => [k, u[k]]));
  const parse = cases.parse.map(([input, base]) => {
    const args = base === null ? [input] : [input, base];
    return {
      url: attempt(() => snapshot(new URL(...args))),
      canParse: URL.canParse(...args),
      parse: (u => u === null ? null : u.href)(URL.parse(...args)),
      json: attempt(() => new URL(...args).toJSON()),
    };
  });
  const setters = cases.setters.map(([href, field, value]) => {
    const u = new URL(href);
    const thrown = attempt(() => { u[field] = value; return null; });
    return {threw: thrown === null ? null : thrown.error, url: snapshot(u)};
  });
  const create = ([kind, value]) => kind === 'record' ? new URLSearchParams(Object.fromEntries(value)) : new URLSearchParams(value);
  const run = (p, [op, ...args]) => attempt(() => {
    switch (op) {
      case 'get': return p.get(...args);
      case 'getAll': return p.getAll(...args);
      case 'has': return p.has(...args);
      case 'size': return p.size;
      case 'toString': return p.toString();
      case 'entries': return [...p];
      case 'sort': p.sort(); return null;
      case 'delete': p.delete(...args); return null;
      case 'set': p.set(...args); return null;
      case 'append': p.append(...args); return null;
    }
    throw new Error('unknown op ' + op);
  });
  const params = cases.params.map(c => attempt(() => { const p = create(c.init); return {ops: c.ops.map(op => run(p, op))}; }));
  const linked = cases.linked.map(([href, ops]) => {
    const u = new URL(href);
    return ops.map(([op, ...args]) => attempt(() => {
      if (op === 'href') return u.href;
      if (op === 'search') return u.search;
      if (op === 'search=') { u.search = args[0]; return null; }
      const r = run(u.searchParams, [op.replace('searchParams.', ''), ...args]);
      return r;
    }));
  });
  const input = ([kind, value]) => value;
  const groups = g => Object.entries(g).map(([k, v]) => [k, v === undefined ? null : v]);
  const execResult = r => r === null ? null : {
    inputs: r.inputs.map(i => typeof i === 'string' ? i : Object.fromEntries(Object.entries(i))),
    ...Object.fromEntries(components.map(c => [c, {input: r[c].input, groups: groups(r[c].groups)}])),
  };
  const patterns = cases.patterns.map(c => attempt(() => {
    const args = [input(c.input)];
    if (c.base !== undefined) args.push(c.base);
    if (c.options !== undefined) args.push(c.options);
    const p = new URLPattern(...args);
    return {
      components: Object.fromEntries([...components, 'hasRegExpGroups'].map(k => [k, p[k]])),
      tests: c.tests.map(([kind, value, base]) => {
        const a = base === null ? [value] : [value, base];
        return {test: attempt(() => p.test(...a)), exec: attempt(() => execResult(p.exec(...a)))};
      }),
    };
  }));
  return {parse, setters, params, linked, patterns};
}

const browser = await chromium.launch({headless: true});
try {
  const tab = await (await browser.newContext()).newPage();
  const result = await tab.evaluate(record, cases);
  writeFileSync(new URL('url-oracle.json', fixtures), JSON.stringify({browser: browser.version(), ...result}, null, 1) + '\n');
  console.log('url oracle', browser.version(), Object.fromEntries(Object.entries(result).map(([k, v]) => [k, v.length])));
} finally {
  await browser.close();
}
