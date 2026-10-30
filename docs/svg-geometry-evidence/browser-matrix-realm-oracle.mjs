import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
const require = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json');
const { chromium } = require('playwright');
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const result = await page.evaluate(async () => {
    const frame = document.createElement('iframe');
    const loaded = new Promise(resolve => frame.onload = resolve);
    frame.srcdoc = '<!doctype html><body></body>';
    document.body.append(frame);
    await loaded;
    const windows = [window, frame.contentWindow];
    const roots = windows.map(w => {
      const r = w.document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      w.document.body.append(r);
      return r;
    });
    const rows = [];
    const fields = ['a', 'b', 'c', 'd', 'e', 'f'];
    for (let targetRealm = 0; targetRealm < 2; targetRealm++) {
      for (let matrixRealm = 0; matrixRealm < 2; matrixRealm++) {
        for (const operation of ['rootFactory', 'setMatrix', 'listFactory']) {
          const root = roots[targetRealm];
          const matrix = roots[matrixRealm].createSVGMatrix();
          const normalized = DOMMatrix.fromMatrix({m11: 2, m12: 3, m21: 4, m22: 5, m41: 6, m42: 7});
          for (const field of fields) matrix[field] = normalized[field];
          try {
            let transform;
            if (operation === 'rootFactory') transform = root.createSVGTransformFromMatrix(matrix);
            if (operation === 'setMatrix') { transform = root.createSVGTransform(); transform.setMatrix(matrix); }
            if (operation === 'listFactory') transform = root.transform.baseVal.createSVGTransformFromMatrix(matrix);
            const before = fields.map(k => transform.matrix[k]);
            matrix.a = 99;
            rows.push({targetRealm, matrixRealm, operation, status: 'ok', matrix: before,
              independentCopy: transform.matrix.a === 2,
              transformOwnRealm: Object.getPrototypeOf(transform) === windows[targetRealm].SVGTransform.prototype,
              matrixOwnRealm: Object.getPrototypeOf(transform.matrix) === windows[targetRealm].SVGMatrix.prototype});
          } catch (error) { rows.push({targetRealm, matrixRealm, operation, status:'error', error:error.name, message:error.message}); }
        }
      }
    }
    frame.remove();
    return {userAgent:navigator.userAgent, rows};
  });
  writeFileSync('artifacts/svg-matrix-realm-oracle.json', JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result));
} finally { await browser.close(); }
