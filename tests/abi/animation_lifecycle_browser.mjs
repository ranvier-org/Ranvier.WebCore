// Chromium oracle for tests/abi/animation_lifecycle.py: writes tests/fixtures/animation-lifecycle-oracle.json.
// Replays tests/fixtures/animation-lifecycle-cases.json: the state-machine program and the ordering scenarios. Each
// scenario records its promise settlements and its animation playback events as two separate ordered lists (and the
// merged order, informational), plus the final states. Times that depend on frame timing are recorded as presence only.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const spec = JSON.parse(readFileSync(new URL('../fixtures/animation-lifecycle-cases.json', import.meta.url), 'utf8'));
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version()};
try {
  const tab = await (await browser.newContext({viewport: {width: 320, height: 240}, deviceScaleFactor: 1})).newPage();
  await tab.setContent(spec.markup);
  Object.assign(out, await tab.evaluate(async (spec) => {
    const frames = (n) => new Promise(r => { const f = () => (--n <= 0 ? r() : requestAnimationFrame(f)); requestAnimationFrame(f); });
    const kf = [{opacity: 0}, {opacity: 1}];
    const el = (id) => document.getElementById(id);
    const state = (x, timed) => ({playState: x.playState, pending: x.pending, replaceState: x.replaceState,
      currentTime: x.currentTime === null ? null : (timed ? 'number' : x.currentTime), startTime: x.startTime === null ? null : 'number',
      playbackRate: x.playbackRate});
    // State machine.
    const states = [];
    let a = null, ready = null, finished = null;
    for (const step of spec.program) {
      switch (step.op) {
        case 'animate': a = el('a').animate(kf, step.duration); break;
        case 'pause': a.pause(); break;
        case 'play': a.play(); break;
        case 'reverse': a.reverse(); break;
        case 'finish': a.finish(); break;
        case 'cancel': a.cancel(); break;
        case 'persist': a.persist(); break;
        case 'seek': a.currentTime = step.value; break;
        case 'updatePlaybackRate': a.updatePlaybackRate(step.value); break;
        case 'setPlaybackRate': a.playbackRate = step.value; break;
        case 'awaitReady': await a.ready; break;
        case 'state': {
          const entry = {label: step.label, ...state(a, step.timed)};
          if (step.sameReady) entry.sameReady = a.ready === ready;
          if (step.sameFinished) entry.sameFinished = a.finished === finished;
          states.push(entry);
          break;
        }
      }
      // The promises current before the next action, for the identity checks of the state step after it.
      if (step.op === 'state' || step.op === 'animate') { ready = a.ready; finished = a.finished; }
    }
    a.cancel();
    // Ordering scenarios.
    const scenarios = {};
    const run = async (name, body) => {
      const log = {promises: [], events: [], merged: []};
      const watch = (anim, label) => {
        for (const t of ['finish', 'cancel', 'remove'])
          anim.addEventListener(t, e => {
            const text = `${label}:${e.type}:${e.currentTime === null ? 'null' : 'number'}:${e.timelineTime === null ? 'null' : 'number'}`;
            log.events.push(text); log.merged.push('event ' + text);
          });
        const settle = (kind) => [() => { log.promises.push(`${label}:${kind}`); log.merged.push(`promise ${label}:${kind}`); },
                                  (e) => { log.promises.push(`${label}:${kind}:${e.name}`); log.merged.push(`promise ${label}:${kind}:${e.name}`); }];
        anim.ready.then(...settle('ready'));
        anim.finished.then(...settle('finished'));
      };
      const [finals, cleanup] = await body(watch, log);
      scenarios[name] = {promises: [...log.promises], events: [...log.events], merged: [...log.merged], states: finals};
      cleanup(); await frames(2);
    };
    await run('finish()', async (watch) => {
      const b = el('b').animate(kf, 1000); watch(b, 'b');
      b.finish(); await frames(3); return [{b: state(b)}, () => b.cancel()];
    });
    await run('cancel pending', async (watch) => {
      const c = el('c').animate(kf, 1000); watch(c, 'c');
      c.cancel(); await frames(3); return [{c: state(c)}, () => {}];
    });
    await run('cancel running', async (watch) => {
      const d = el('c').animate(kf, 1000); watch(d, 'd');
      await d.ready; d.cancel(); await frames(3); return [{d: state(d)}, () => {}];
    });
    await run('cancel in listener', async (watch, log) => {
      const e = el('a').animate(kf, 1000), f = el('b').animate(kf, 1000);
      watch(e, 'e'); watch(f, 'f');
      e.addEventListener('finish', () => f.cancel());
      await f.ready; await e.ready; e.finish(); await frames(3);
      return [{e: state(e), f: state(f)}, () => e.cancel()];
    });
    await run('cancel in ready', async (watch) => {
      const g = el('a').animate(kf, 1000); watch(g, 'g');
      g.ready.then(() => g.cancel()); await frames(3); return [{g: state(g)}, () => {}];
    });
    await run('replace', async (watch) => {
      const x = el('b').animate(kf, {duration: 30, fill: 'forwards'}), y = el('b').animate(kf, {duration: 30, fill: 'forwards'});
      watch(x, 'x'); watch(y, 'y');
      await y.finished; await frames(3);
      const s = {x: state(x, true), y: state(y, true)}; x.persist(); s.xPersisted = state(x, true); return [s, () => { x.cancel(); y.cancel(); }];
    });
    await run('rewind finished', async (watch) => {
      const z = el('c').animate(kf, 1000); z.finish(); await frames(2); const old = z.finished; watch(z, 'z');
      z.currentTime = 0; const replaced = z.finished !== old; watch(z, 'z2'); await frames(3);
      return [{z: state(z, true), finishedReplaced: replaced}, () => z.cancel()];
    });
    return {states, scenarios};
  }, spec));
} finally { await browser.close(); }
writeFileSync(process.env.ORACLE_OUT || new URL('../fixtures/animation-lifecycle-oracle.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
