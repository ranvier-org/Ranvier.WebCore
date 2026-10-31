// Chromium oracle for tests/abi/inspector_diagnostics.py: writes tests/fixtures/inspector-diagnostics-oracle.json.
// Records the content, padding, border and margin boxes of tests/fixtures/inspector-diagnostics.html (pinned Ahem)
// from getBoundingClientRect and the computed border, padding and margin widths, unscrolled, scrolled and at page
// scale 2. Browsers expose no matched-rule list or render tree to pages: the oracle records both as unsupported.
import {createRequire} from 'node:module';
import {readFileSync, writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const here = new URL('.', import.meta.url);
const font = readFileSync(process.env.RV_AHEM ?? 'C:/wk/src/Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf');
const template = readFileSync(new URL('../fixtures/inspector-diagnostics.html', here), 'utf8');
export const page = template.replace('{{FONT_BASE64}}', font.toString('base64'));
// Untransformed boxes, whose padding and content boxes follow from the border box and the computed widths.
export const elements = ['target', 'flow', 'zoomed', 'action'];
// [name, scrollX, scrollY, pageScale]
export const cases = [['base', 0, 0, 1], ['scrolled', 30, 45, 1], ['page scale 2', 0, 0, 2]];

export function boxes(ids) {
  const out = {};
  for (const id of ids) {
    const element = document.getElementById(id);
    const style = getComputedStyle(element);
    const px = name => parseFloat(style.getPropertyValue(name));
    const r = element.getBoundingClientRect();
    // getBoundingClientRect includes the element's zoom; the computed widths are unzoomed CSS values.
    const zoom = parseFloat(style.zoom) || 1;
    const side = prefix => ['top', 'right', 'bottom', 'left'].map(s => px(prefix.replace('*', s)) * zoom);
    const [bt, br, bb, bl] = side('border-*-width'), [pt, pr, pb, pl] = side('padding-*'), [mt, mr, mb, ml] = side('margin-*');
    const border = {x: r.x, y: r.y, width: r.width, height: r.height};
    const padding = {x: r.x + bl, y: r.y + bt, width: r.width - bl - br, height: r.height - bt - bb};
    const content = {x: padding.x + pl, y: padding.y + pt, width: padding.width - pl - pr, height: padding.height - pt - pb};
    const margin = {x: r.x - ml, y: r.y - mt, width: r.width + ml + mr, height: r.height + mt + mb};
    out[id] = {content, padding, border, margin};
  }
  return out;
}

if (import.meta.url === `file:///${process.argv[1].replaceAll('\\', '/')}`) {
  const browser = await chromium.launch({channel: 'chromium', headless: true});
  const result = {browser: browser.version(), headless: 'new (channel chromium)', fixture: 'tests/fixtures/inspector-diagnostics.html',
    fontSha256: createHash('sha256').update(font).digest('hex'), viewport: [320, 240], elements, cases: [],
    unsupported: {matchedRules: 'no web API lists the style rules matching an element', renderTree: 'no web API dumps the render tree',
      developerToolsFrontend: 'a page cannot observe or attach a developer-tools frontend'}};
  try {
    const context = await browser.newContext({viewport: {width: 320, height: 240}});
    const tab = await context.newPage();
    const cdp = await context.newCDPSession(tab);
    const frames = () => tab.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
    for (const [name, sx, sy, scale] of cases) {
      await tab.setContent(page);
      await tab.evaluate(() => document.fonts.ready);
      await cdp.send('Emulation.setPageScaleFactor', {pageScaleFactor: scale});
      await frames();
      const width = await tab.evaluate(() => document.getElementById('target').firstChild.length && document.getElementById('inline').getBoundingClientRect().width);
      if (width !== 20) throw new Error('Ahem not applied: inline width ' + width);
      await tab.evaluate(([x, y]) => scrollTo(x, y), [sx, sy]);
      await frames();
      result.cases.push({name, pageScale: scale, scrollX: await tab.evaluate(() => scrollX), scrollY: await tab.evaluate(() => scrollY),
        visualScale: await tab.evaluate(() => visualViewport.scale), boxes: await tab.evaluate(boxes, elements)});
    }
  } finally {
    await browser.close();
  }
  writeFileSync(new URL('../fixtures/inspector-diagnostics-oracle.json', here), JSON.stringify(result, null, 2) + '\n');
  for (const c of result.cases) console.log(c.name, c.scrollX, c.scrollY, c.visualScale, JSON.stringify(c.boxes.target.border));
}
