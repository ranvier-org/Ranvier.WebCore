import {createRequire} from 'node:module';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const browser = await chromium.launch({headless: true});
try {
  const page = await browser.newPage();
  const out = await page.evaluate(() => {
    const result = {};
    for (const [name, attr] of [['href', 'href'], ['xlink', 'xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href']]) {
      const host = document.createElement('div');
      host.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg"><defs><filter id="f"><feImage id="image-${name}" ${attr}="data:,a"/></filter></defs></svg>`;
      document.body.append(host);
      const image = host.querySelector('feImage');
      image.href.baseVal = 'data:,b';
      result[name] = {attributes: [...image.attributes].map(a => [a.name, a.namespaceURI, a.value]), baseVal: image.href.baseVal, getHref: image.getAttribute('href'), getXlink: image.getAttributeNS('http://www.w3.org/1999/xlink', 'href')};
    }
    return result;
  });
  out.userAgent = await page.evaluate(() => navigator.userAgent);
  console.log(JSON.stringify(out));
} finally { await browser.close(); }
