// Chromium oracle for tests/abi/custom_effects.py: writes tests/fixtures/custom-effects-oracle.json.
// Chromium has no CustomEffect: the progress a custom effect's tick receives is the progress of a null-target
// KeyframeEffect with the same timing, read at each seek time of a paused animation. The error cases record the
// exception name the constructor throws, and presence records which custom effect members Chromium has.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const spec = JSON.parse(readFileSync(new URL('../fixtures/custom-effects-cases.json', import.meta.url), 'utf8'));
const browser = await chromium.launch({headless: true});
const out = {browser: 'Chromium ' + browser.version()};
try {
  const tab = await (await browser.newContext({viewport: {width: 320, height: 240}})).newPage();
  await tab.setContent('<!doctype html><body>');
  Object.assign(out, await tab.evaluate((spec) => {
    const timing = (t) => typeof t === 'object' ? Object.fromEntries(Object.entries(t).map(([k, v]) => [k, v === 'NaN' ? NaN : v])) : t;
    const cases = spec.cases.map((c) => {
      const effect = new KeyframeEffect(null, [], timing(c.timing));
      const animation = new Animation(effect, document.timeline);
      animation.pause();
      return {name: c.name, samples: spec.times.map((t) => { animation.currentTime = t; return [t, effect.getComputedTiming().progress]; })};
    });
    const errors = spec.errors.map((c) => {
      try { new KeyframeEffect(null, [], timing(c.timing)); return {name: c.name, error: null}; }
      catch (e) { return {name: c.name, error: e.name}; }
    });
    const presence = {CustomEffect: typeof window.CustomEffect === 'function', timelineAnimate: typeof document.timeline.animate === 'function'};
    return {cases, errors, presence};
  }, spec));
} finally {
  await browser.close();
}
writeFileSync(process.env.ORACLE_OUT || new URL('../fixtures/custom-effects-oracle.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log('custom effects oracle:', out.cases.length, 'cases', out.errors.length, 'errors', JSON.stringify(out.presence));
