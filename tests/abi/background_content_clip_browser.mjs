import {createRequire} from 'node:module';
import {mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';

const require = createRequire(process.env.RANVIER_BROWSER_PACKAGE);
const {chromium} = require('playwright');
const cases = JSON.parse(readFileSync(new URL('../fixtures/background-content-clip-cases.json', import.meta.url)));
const output = process.argv[2];
if (!output) throw new Error('Pass an output directory');
mkdirSync(output, {recursive: true});
const reports = [];
for (const scale of cases.scales) {
  const browser = await chromium.launch({headless: true, args: [`--force-device-scale-factor=${scale}`]});
  try {
    for (const test of cases.cases) {
      const context = await browser.newContext({viewport: {width: 800, height: 600}, deviceScaleFactor: scale});
      try {
        const page = await context.newPage();
        const tag = test.element ?? 'div';
        await page.setContent(`<!doctype html><head><style>${cases.style}${test.css ?? ''}</style></head><body>${test.before ?? ''}<${tag} id="f">${test.inside ?? ''}</${tag}>${test.after ?? ''}</body>`);
        if (test.scroll) await page.evaluate(([id, x, y]) => document.getElementById(id).scrollTo(x, y), test.scroll);
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        const metadata = await page.evaluate(() => {
          const rect = document.getElementById('f').getBoundingClientRect();
          return {devicePixelRatio, borderBox: [rect.x, rect.y, rect.width, rect.height]};
        });
        if (metadata.devicePixelRatio !== scale) throw new Error('Actual device scale mismatch');
        const png = `${test.name}-${scale}.png`;
        await page.screenshot({path: join(output, png), scale: 'device'});
        reports.push({name: test.name, scale, ...metadata, png});
      } finally { await context.close(); }
    }
    writeFileSync(join(output, 'capture.json'), JSON.stringify({browser: browser.version(), playwright: require('playwright/package.json').version, reports}, null, 2) + '\n');
  } finally { await browser.close(); }
}
console.log(`Captured ${reports.length} physical paint controls`);
