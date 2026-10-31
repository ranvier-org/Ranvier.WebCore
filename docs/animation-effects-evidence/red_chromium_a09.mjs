// RED survey for A09 (custom effects) in Chromium: presence of CustomEffect / DocumentTimeline.animate, and the
// progress a null-target effect computes for the timing cases (the value a custom effect's callback receives).
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version()};
try {
  const tab = await (await browser.newContext({viewport: {width: 320, height: 240}})).newPage();
  await tab.setContent('<!doctype html><body><div id=a></div>');
  out.result = await tab.evaluate(async () => {
    const R = {};
    R.presence = {
      CustomEffect: typeof window.CustomEffect,
      timelineAnimate: typeof document.timeline.animate,
      KeyframeEffect: typeof window.KeyframeEffect,
    };
    const cases = [
      {name: 'linear', timing: {duration: 1000}},
      {name: 'delay', timing: {duration: 1000, delay: 200}},
      {name: 'reverse', timing: {duration: 1000, direction: 'reverse'}},
      {name: 'alternate2', timing: {duration: 500, iterations: 2, direction: 'alternate'}},
      {name: 'easeIn', timing: {duration: 1000, easing: 'ease-in'}},
      {name: 'fillBoth', timing: {duration: 1000, delay: 100, fill: 'both'}},
      {name: 'iterStart', timing: {duration: 1000, iterationStart: 0.25}},
    ];
    const times = [0, 100, 250, 500, 750, 999, 1000, 1200];
    R.progress = cases.map(c => {
      const e = new KeyframeEffect(null, [], c.timing);
      const a = new Animation(e, document.timeline);
      a.pause();
      return {name: c.name, timing: c.timing, samples: times.map(t => { a.currentTime = t; return [t, e.getComputedTiming().progress]; })};
    });
    // Errors the constructor raises for invalid timing.
    const err = (f) => { try { f(); return 'ok'; } catch (x) { return x.name; } };
    R.errors = {
      negativeDuration: err(() => new KeyframeEffect(null, [], {duration: -1})),
      badEasing: err(() => new KeyframeEffect(null, [], {duration: 1, easing: 'nope'})),
      nanIterations: err(() => new KeyframeEffect(null, [], {duration: 1, iterations: NaN})),
      durationString: err(() => new KeyframeEffect(null, [], {duration: 'x'})),
    };
    return R;
  });
} finally {
  await browser.close();
}
writeFileSync(process.argv[2] || 'chromium-a09.json', JSON.stringify(out, null, 1));
console.log(JSON.stringify(out.result.presence), JSON.stringify(out.result.errors));
