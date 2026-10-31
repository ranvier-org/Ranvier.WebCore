import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const { chromium } = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('@playwright/test');
const markup = readFileSync(new URL('./SmilRed.fs', import.meta.url), 'utf8').match(/let markup =\s*([\s\S]*?)\n\n/)[1].split('\n').map(l => l.trim().replace(/^\+\s*/, '')).map(l => JSON.parse(l.replace(/^"/, '"'))).join('');
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage(); await page.setContent('<!doctype html><body></body>');
  console.log((await page.evaluate(async markup => {
    document.body.innerHTML = markup; const out = [], s = document.getElementById('s'), el = id => document.getElementById(id), w = id => document.getElementById(id + '-t').width.animVal.value;
    const st = id => { try { return el(id).getStartTime(); } catch (e) { return e.name; } };
    s.pauseAnimations(); s.setCurrentTime(0); for (const id of ['a', 'b']) el(id).beginElement(); s.setCurrentTime(5); for (const id of ['a', 'b']) el(id).endElement(); s.setCurrentTime(6); for (const id of ['a', 'b']) el(id).beginElementAt(1); s.setCurrentTime(8);
    for (const id of ['a', 'b']) out.push(`PAUSED-SEEK ${id} endAttr=${id === 'b'} width@8=${w(id)} start=${st(id)}`);
    s.setCurrentTime(20); s.unpauseAnimations(); const c = el('c'); c.beginElement(); const wait = ms => new Promise(r => setTimeout(r, ms));
    await wait(300); c.endElement(); await wait(300); const frozen = w('c'); c.beginElementAt(0.2); await wait(700);
    out.push(`RUNNING c frozen=${frozen} after-new-begin=${w('c')} restarted=${w('c') < frozen}`); return out.join('\n');
  }, markup)));
} finally { await browser.close(); }
