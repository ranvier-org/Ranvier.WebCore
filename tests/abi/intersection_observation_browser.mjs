// Chromium oracle for tests/abi/intersection_observation.py: replays tests/fixtures/intersection-observation-cases.json and
// writes tests/fixtures/intersection-observation-oracle.json. Each scenario runs in a fresh document.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const cases = JSON.parse(readFileSync(new URL('../fixtures/intersection-observation-cases.json', import.meta.url), 'utf8'));

// Runs in the page.
const run = async scenario => {
  // Chromium queues entries in a frame's rendering update and delivers them in a later task.
  const frame = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0))));
  const statuses = [], segments = [], times = [];
  let segment = [];
  const observers = {}, elements = {};
  let pair = null;
  const $ = id => id === '#body' ? document.body : elements[id] || document.getElementById(id);
  for (const id of ['far', 's', 'sp', 'u', 'x', 'c', 'cp', 'v']) elements[id] = document.getElementById(id);
  const rect = r => r ? [r.x, r.y, r.width, r.height] : null;
  const entry = e => ({t: e.target.id, time: e.time, root: rect(e.rootBounds), bounds: rect(e.boundingClientRect),
    intersection: rect(e.intersectionRect), intersecting: e.isIntersecting, ratio: e.intersectionRatio});
  const exec = async step => {
    const [kind, ...args] = step;
    if (kind === 'create') {
      const [name, init] = args;
      const options = {...init};
      if ('root' in init) options.root = init.root === '#document' ? document : init.root === null ? null : $(init.root);
      try {
        observers[name] = new IntersectionObserver(es => {
          if (pair && (name === pair[0] || name === pair[1])) {
            const other = name === pair[0] ? pair[1] : pair[0];
            const [a, b] = pair;
            pair = null;
            const taken = observers[other].takeRecords().map(entry);
            const own = es.map(entry);
            segment.push({o: 'pair:' + a + '+' + b, entries: {[a]: name === a ? own : taken, [b]: name === b ? own : taken}});
            return;
          }
          segment.push({o: name, entries: es.map(entry)});
        }, options);
        statuses.push('ok');
      } catch (e) { statuses.push(e.name); }
    } else if (kind === 'observe') observers[args[0]].observe($(args[1]));
    else if (kind === 'unobserve') observers[args[0]].unobserve($(args[1]));
    else if (kind === 'disconnect') observers[args[0]].disconnect();
    else if (kind === 'take') segment.push({o: 'take:' + args[0], entries: observers[args[0]].takeRecords().map(entry)});
    else if (kind === 'pair') pair = [args[0], args[1]];
    else if (kind === 'scroll') scrollTo(args[0], args[1]);
    else if (kind === 'scrollTop') $(args[0]).scrollTop = args[1];
    else if (kind === 'style') $(args[0]).style.setProperty(args[1], args[2]);
    else if (kind === 'element') { const el = document.createElement('div'); el.id = args[0]; elements[args[0]] = el; }
    else if (kind === 'append') $(args[0]).append($(args[1]));
    else if (kind === 'remove') $(args[0]).remove();
    else if (kind === 'update') {
      const before = performance.now();
      await frame();
      times.push([before, performance.now()]);
      segments.push(segment);
      segment = [];
    } else throw new Error('unknown step ' + kind);
  };
  // setContent keeps the previous document's scroll position.
  scrollTo(0, 0);
  await frame();
  for (const step of scenario.steps) await exec(step);
  // A late delivery would land here, after a further wait.
  await new Promise(r => setTimeout(r, 100));
  segments.push(segment);
  for (const o of Object.values(observers)) o.disconnect();
  return {statuses, segments, times};
};

const result = {browser: null, scenarios: {}, qualified: {}};
const browser = await chromium.launch({headless: true});
try {
  result.browser = browser.version();
  const tab = await browser.newPage({viewport: {width: cases.viewport[0], height: cases.viewport[1]}});
  for (const [key, list] of [['scenarios', cases.scenarios], ['qualified', cases.qualifiedScenarios]]) {
    for (const scenario of list) {
      await tab.setContent(cases.markup);
      result[key][scenario.name] = await tab.evaluate(run, scenario);
    }
  }
} finally {
  await browser.close();
}
writeFileSync(new URL('../fixtures/intersection-observation-oracle.json', import.meta.url), JSON.stringify(result, null, 1) + '\n');
console.log('ORACLE intersection-observation: ' + cases.scenarios.length + ' scenarios + ' + cases.qualifiedScenarios.length + ' qualified, Chromium ' + result.browser);
