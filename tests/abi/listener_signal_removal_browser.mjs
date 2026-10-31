// Chromium oracle for tests/abi/listener_signal_removal.py: the same scenarios, with each group an
// AbortController whose signal is passed to addEventListener, and a group's removal its abort().
//   node tests/abi/listener_signal_removal_browser.mjs <package.json with playwright> <out.json>
import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
const [packageJson, out] = process.argv.slice(2);
const require = createRequire(packageJson);
const { chromium } = require('playwright');
const text = await readFile(new URL('../fixtures/listener-signal-removal-cases.json', import.meta.url), 'utf-8');
const cases = JSON.parse(text);
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const results = await page.evaluate(scenarios => scenarios.map(scenario => {
    document.body.innerHTML = '<div id="parent"><div id="child"></div></div><div id="other"></div>';
    const log = [], controllers = {}, callbacks = {}, fired = new Set();
    const controller = group => controllers[group] ??= new AbortController();
    const register = spec => {
      const actions = spec.onFire ?? [];
      const callback = callbacks[spec.label] ??= () => {
        log.push(spec.label);
        for (const action of actions) {
          const key = JSON.stringify(action);
          if (action.once && fired.has(key)) continue;
          fired.add(key);
          if (action.do === 'remove') controller(action.group).abort();
          else if (action.do === 'add') register(action.listener);
        }
      };
      document.getElementById(spec.node).addEventListener('ping', callback,
        { capture: !!spec.capture, signal: controller(spec.group).signal });
    };
    scenario.listeners.forEach(register);
    const observed = [];
    for (const step of scenario.steps) {
      if (step.do === 'dispatch') {
        log.length = 0;
        document.getElementById(step.node).dispatchEvent(new Event('ping', { bubbles: true }));
        observed.push([...log]);
      } else if (step.do === 'remove') controller(step.group).abort();
    }
    return { name: scenario.name, observed, expected: scenario.expected };
  }), cases.scenarios);
  let assertions = 0;
  for (const result of results) {
    assertions++;
    if (JSON.stringify(result.observed) !== JSON.stringify(result.expected))
      throw new Error(`${result.name}: ${JSON.stringify(result.observed)} != ${JSON.stringify(result.expected)}`);
  }
  const evidence = { browser: await browser.version(), casesSha256: createHash('sha256').update(text).digest('hex'),
    assertions, cases: Object.fromEntries(results.map(r => [r.name, r.observed])) };
  await writeFile(out, JSON.stringify(evidence, null, 2));
  console.log(`PASS Chromium listener signal removal: ${assertions} assertions (${evidence.browser})`);
} finally {
  await browser.close();
}
