// Chromium oracle for tests/abi/resize_observation.py: replays tests/fixtures/resize-observation-cases.json and writes
// tests/fixtures/resize-observation-oracle.json. Each scenario runs in a fresh document at forced device scales
// 1, 1.5 and 2 (playwright's deviceScaleFactor leaves devicePixelContentBoxSize at scale 1).
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const cases = JSON.parse(readFileSync(new URL('../fixtures/resize-observation-cases.json', import.meta.url), 'utf8'));

// Runs in the page.
const run = async scenario => {
  const frame = () => new Promise(r => requestAnimationFrame(() => setTimeout(r, 0)));
  const log = [], entries = [], statuses = [];
  const observers = {}, elements = {}, armed = [];
  const $ = id => elements[id] || document.getElementById(id);
  const size = s => s && s.length ? [s[0].inlineSize, s[0].blockSize] : null;
  const exec = async step => {
    const [kind, ...args] = step;
    if (kind === 'create') {
      const name = args[0];
      observers[name] = new ResizeObserver(es => {
        log.push(name + ':' + es.map(e => e.target.id).join(','));
        for (const e of es) {
          const r = e.contentRect;
          entries.push({o: name, t: e.target.id, rect: [r.x, r.y, r.width, r.height], content: size(e.contentBoxSize), border: size(e.borderBoxSize),
            device: size(e.devicePixelContentBoxSize)});
        }
        for (const e of es) {
          const index = armed.findIndex(a => a.o === name && a.t === e.target.id);
          if (index >= 0) { const [a] = armed.splice(index, 1); exec(a.step); }
        }
      });
    } else if (kind === 'observe') {
      try { args[2] === null ? observers[args[0]].observe($(args[1])) : observers[args[0]].observe($(args[1]), {box: args[2]}); statuses.push('ok'); }
      catch (e) { statuses.push(e.name); }
    } else if (kind === 'unobserve') observers[args[0]].unobserve($(args[1]));
    else if (kind === 'disconnect') observers[args[0]].disconnect();
    else if (kind === 'style') $(args[0]).style.setProperty(args[1], args[2]);
    else if (kind === 'attribute') $(args[0]).setAttribute(args[1], args[2]);
    else if (kind === 'update') { await frame(); log.push('|'); }
    else if (kind === 'settle') { await frame(); await frame(); }
    else if (kind === 'arm') armed.push({o: args[0], t: args[1], step: args[2]});
    else if (kind === 'errors') window.addEventListener('error', e => { log.push('error:' + e.message); e.preventDefault(); });
    else if (kind === 'intersect') {
      const io = new IntersectionObserver(es => log.push(args[0] + ':' + es.map(e => e.target.id).join(',')));
      io.observe($(args[1]));
    } else if (kind === 'element') { const el = document.createElement('div'); el.id = args[0]; el.style.cssText = args[1]; elements[args[0]] = el; }
    else if (kind === 'append') (args[1] ? $(args[1]) : document.body).append($(args[0]));
    else if (kind === 'remove') $(args[0]).remove();
    else throw new Error('unknown step ' + kind);
  };
  for (const step of scenario.steps) await exec(step);
  for (const o of Object.values(observers)) o.disconnect();
  return {log, entries, statuses};
};

const result = {browser: null, scales: {}};
for (const scale of [1, 1.5, 2]) {
  const browser = await chromium.launch({headless: true, args: scale === 1 ? [] : ['--force-device-scale-factor=' + scale]});
  try {
    result.browser = browser.version();
    const tab = await browser.newPage({viewport: {width: 800, height: 600}});
    const scenarios = {};
    for (const scenario of cases.scenarios) {
      await tab.setContent(cases.markup);
      scenarios[scenario.name] = await tab.evaluate(run, scenario);
    }
    result.scales[scale] = scenarios;
  } finally {
    await browser.close();
  }
}
writeFileSync(new URL('../fixtures/resize-observation-oracle.json', import.meta.url), JSON.stringify(result, null, 2) + '\n');
console.log('ORACLE resize-observation: ' + cases.scenarios.length + ' scenarios x ' + Object.keys(result.scales).length + ' scales, Chromium ' + result.browser);
