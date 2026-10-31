// Chromium oracle for tests/abi/animation_events.py: writes tests/fixtures/animation-events-oracle.json.
// Replays tests/fixtures/animation-events-cases.json: engine CSS animation and transition events seen at the document,
// and the playback events of Element.animate animations, with the generic listener checks.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const spec = JSON.parse(readFileSync(new URL('../fixtures/animation-events-cases.json', import.meta.url), 'utf8'));
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version()};
try {
  const tab = await (await browser.newContext({viewport: {width: 320, height: 240}, deviceScaleFactor: 1})).newPage();
  await tab.setContent(spec.markup);
  Object.assign(out, await tab.evaluate(async (spec) => {
    const frames = (n) => new Promise(r => { const f = () => (--n <= 0 ? r() : requestAnimationFrame(f)); requestAnimationFrame(f); });
    const until = async (check) => { for (let i = 0; i < 600 && !check(); i++) await frames(1); if (!check()) throw new Error('hang guard'); };
    const elapsed = (e) => e.type.endsWith('cancel') ? 'number' : Math.round(e.elapsedTime * 1e6) / 1e6;
    const cases = {};
    for (const c of spec.cases) {
      const events = [];
      const el = document.getElementById(c.el);
      const record = (e) => {
        if (e.target !== el) return;
        events.push({type: e.type, interface: e.constructor.name, target: e.target.id,
          name: e.animationName ?? e.propertyName, elapsedTime: elapsed(e), pseudoElement: e.pseudoElement});
        // The cancel follows the first event of the case, or the first event of type after.
        if (c.cancel && e.type === (c.after || events[0].type) && events.filter(x => x.type === e.type).length === 1)
          requestAnimationFrame(() => { el.className = c.cancel; });
      };
      for (const t of spec.types) document.addEventListener(t, record);
      await frames(2);
      el.className = c.className;
      await until(() => events.some(e => e.type === c.last));
      await frames(4);
      for (const t of spec.types) document.removeEventListener(t, record);
      cases[c.name] = events;
    }
    const playback = {};
    for (const c of spec.playback) {
      const events = [];
      const a = document.getElementById(c.el).animate([{opacity: 0}, {opacity: 1}], c.duration);
      for (const t of ['finish', 'cancel', 'remove'])
        a.addEventListener(t, e => events.push({type: e.type, interface: e.constructor.name,
          currentTime: e.currentTime === null ? null : Math.round(e.currentTime * 1e6) / 1e6, timelineTime: e.timelineTime === null ? null : 'number',
          timelineAfterCurrent: e.timelineTime !== null && e.currentTime !== null ? e.timelineTime >= e.currentTime : null}));
      await a.ready;
      if (c.cancel) a.cancel();
      await until(() => events.some(e => e.type === c.last));
      await frames(3);
      playback[c.name] = events;
    }
    // Generic subscription: a capture listener on the element and a bubbling one on the document both see the event;
    // after removal neither does.
    const g = document.getElementById('css');
    g.className = '';
    await frames(2);
    const seen = [];
    const capture = (e) => seen.push('capture:' + e.type + ':' + e.eventPhase), bubble = (e) => { if (e.target === g) seen.push('bubble:' + e.type + ':' + e.eventPhase); };
    document.addEventListener('animationstart', capture, true);
    document.addEventListener('animationstart', bubble);
    g.className = 'on';
    await until(() => seen.length >= 2);
    document.removeEventListener('animationstart', capture, true);
    document.removeEventListener('animationstart', bubble);
    g.className = ''; await frames(2); g.className = 'on'; await frames(6);
    return {cases, playback, generic: seen};
  }, spec));
} finally { await browser.close(); }
writeFileSync(process.env.ORACLE_OUT || new URL('../fixtures/animation-events-oracle.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
