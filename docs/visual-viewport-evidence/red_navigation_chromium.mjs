// Chromium: a VisualViewport held across a frame navigation. Writes red-navigation-chromium.json next to this file.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const browser = await chromium.launch({headless: true});
const out = {browser: browser.version(), cases: []};
try {
  const page = await browser.newPage({viewport: {width: 320, height: 240}});
  await page.setContent('<!doctype html><body style=margin:0><iframe id=f style="width:200px;height:100px;border:0"></iframe>');
  out.cases = await page.evaluate(async () => {
    const f = document.getElementById('f');
    const read = v => ({width: v.width, height: v.height, scale: v.scale, pageTop: v.pageTop});
    const loaded = () => new Promise(r => f.addEventListener('load', r, {once: true}));
    const frames = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const result = [];
    // The initial about:blank window, then a first navigation.
    const initialWindow = f.contentWindow, initial = initialWindow.visualViewport;
    let wait = loaded(); f.srcdoc = '<body style="margin:0;height:900px">first'; await wait; await frames();
    result.push({case: 'initial about:blank, then srcdoc', sameWindow: f.contentWindow === initialWindow,
                 sameViewport: f.contentWindow.visualViewport === initial, held: read(initial), current: read(f.contentWindow.visualViewport)});
    // A loaded document, then a second navigation.
    const firstWindow = f.contentWindow, first = firstWindow.visualViewport;
    f.style.width = '150px'; await frames();
    const before = read(first);
    wait = loaded(); f.srcdoc = '<body style="margin:0;height:900px">second'; await wait; await frames();
    f.style.width = '120px'; await frames();
    result.push({case: 'loaded srcdoc, then another srcdoc', sameWindow: f.contentWindow === firstWindow,
                 sameViewport: f.contentWindow.visualViewport === first, heldBefore: before, held: read(first), current: read(f.contentWindow.visualViewport)});
    // document.open() keeps the Window.
    const openWindow = f.contentWindow, opened = openWindow.visualViewport;
    f.contentDocument.open(); f.contentDocument.write('<body style=margin:0>third'); f.contentDocument.close(); await frames();
    result.push({case: 'document.open replacement', sameWindow: f.contentWindow === openWindow,
                 sameViewport: f.contentWindow.visualViewport === opened, held: read(opened), current: read(f.contentWindow.visualViewport)});
    return result;
  });
} finally { await browser.close(); }
writeFileSync(new URL('./red-navigation-chromium.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log(JSON.stringify(out, null, 1));
