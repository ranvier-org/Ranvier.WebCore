// Chromium oracle for tests/abi/coordinate_spaces.py: writes tests/fixtures/coordinate-spaces-oracle.json.
// Page points of local points of each element, composed from Chromium's computed transform, transform-origin,
// perspective, perspective-origin and transform-style with untransformed layout offsets. Each composition is checked
// against getBoundingClientRect: the bounding box of the mapped border-box corners equals the rect plus the scroll.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

export const PAGE = '<!doctype html><style>html,body{margin:0}body{width:2000px;height:3000px}'
  + '#o{position:absolute;left:100px;top:50px;width:200px;height:100px;box-sizing:border-box;border:3px solid;padding:5px;transform:rotate(30deg) scale(1.5)}'
  + '#i{margin-left:20px;width:40px;height:40px;transform:translate(10px,5px) rotate(45deg)}'
  + '#p{position:absolute;left:400px;top:50px;width:200px;height:200px;perspective:400px}'
  + '#q{width:100px;height:100px;transform:rotateY(40deg)}'
  + '#r{position:relative;left:10px;top:10px;width:30px;height:30px;transform:rotateX(30deg)}'
  + '#u{position:absolute;left:650px;top:50px;width:200px;height:200px;perspective:300px;perspective-origin:20% 70%}'
  + '#v{width:120px;height:120px;transform-style:preserve-3d;transform:rotateY(30deg) translateZ(20px)}'
  + '#w{position:absolute;left:20px;top:30px;width:50px;height:40px;transform:rotateX(40deg);transform-origin:10px 5px 7px}'
  + '#s{position:absolute;left:0;top:300px;width:150px;height:100px;overflow:auto}'
  + '#t{margin-top:150px;width:20px;height:20px;transform:rotate(10deg)}'
  + '.pad{height:400px}'
  + '#b{position:absolute;left:0;top:40px;width:50px;height:50px}'
  + '#f{position:fixed;left:10px;top:120px;width:30px;height:30px}'
  + '#z{position:absolute;left:700px;top:400px;width:20px;height:20px;transform:scale(0)}'
  + '#y{position:absolute;left:750px;top:400px;width:20px;height:20px;transform:rotateY(90deg)}'
  + '#n{display:none}'
  + '#e{position:absolute;left:200px;top:250px;width:80px;height:60px;transform:perspective(250px) rotateY(-35deg) rotateX(20deg)}'
  + '#g{margin:10px;width:30px;height:20px;transform:perspective(200px) rotateX(30deg)}'
  + '#c{position:absolute;left:150px;top:150px;width:80px;height:50px;transform:rotateY(-35deg) rotateX(20deg)}'
  + '#d{margin:5px;width:30px;height:20px;transform:rotateX(50deg) rotate(15deg)}'
  + '#m{position:absolute;left:300px;top:400px;width:60px;height:40px;border:2px solid;padding:4px 6px;margin:3px 5px 7px 9px}'
  + '</style><body><div id=o><div id=i></div></div><div id=p><div id=q><div id=r></div></div></div>'
  + '<div id=u><div id=v><div id=w></div></div></div><div id=s><div id=t></div><div class=pad></div></div>'
  + '<div id=b></div><div id=f></div><div id=z></div><div id=y></div><div id=n></div><span id=k>text</span><div id=m></div><div id=e><div id=g></div></div><div id=c><div id=d></div></div>';
export const ELEMENTS = ['o', 'i', 'p', 'q', 'r', 'u', 'v', 'w', 's', 't', 'b', 'f', 'm', 'e', 'g', 'c', 'd', 'z', 'y'];
export const SCROLLER_TOP = 40;

if (import.meta.url === `file:///${process.argv[1].replaceAll('\\', '/')}`) {
  const browser = await chromium.launch({headless: true});
  const out = {browser: browser.version(), page: PAGE, viewport: [320, 240], scrollerTop: SCROLLER_TOP, elements: {}};
  try {
    const context = await browser.newContext({viewport: {width: 320, height: 240}});
    const tab = await context.newPage();
    await tab.setContent(PAGE);
    out.elements = await tab.evaluate(({ids, top}) => {
      document.getElementById('s').scrollTop = top;
      const all = [...document.querySelectorAll('*')];
      const page = r => [r.x + scrollX, r.y + scrollY];
      const inline = all.map(e => e.style.transform);
      all.forEach(e => e.style.setProperty('transform', 'none', 'important'));
      const origin = new Map(all.map(e => [e, page(e.getBoundingClientRect())]));
      const size = new Map(all.map(e => { const r = e.getBoundingClientRect(); return [e, [r.width, r.height]]; }));
      all.forEach((e, k) => { e.style.removeProperty('transform'); if (inline[k]) e.style.transform = inline[k]; });
      const px = (value, length) => value.endsWith('%') ? parseFloat(value) / 100 * length : parseFloat(value);
      const project = p => [p.x / p.w, p.y / p.w];
      // Local border-box point of e to page, one 3D rendering context at a time.
      const map = (e, x, y) => {
        let point = new DOMPoint(x, y, 0, 1), m = new DOMMatrix(), steps = [];
        for (let current = e; current !== document.body; current = current.parentElement) {
          const style = getComputedStyle(current), parent = current.parentElement, parentStyle = getComputedStyle(parent);
          const [ox, oy, oz = '0px'] = style.transformOrigin.split(' ');
          const t = new DOMMatrix(style.transform === 'none' ? undefined : style.transform);
          let local = new DOMMatrix().translate(parseFloat(ox), parseFloat(oy), parseFloat(oz)).multiply(t).translate(-parseFloat(ox), -parseFloat(oy), -parseFloat(oz));
          const [cx, cy] = origin.get(current), [qx, qy] = origin.get(parent);
          local = new DOMMatrix().translate(cx - qx, cy - qy).multiply(local);
          if (parentStyle.perspective !== 'none') {
            const [w, h] = size.get(parent), [pox, poy] = parentStyle.perspectiveOrigin.split(' ');
            const d = parseFloat(parentStyle.perspective), ax = px(pox, w), ay = px(poy, h);
            const perspective = new DOMMatrix([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, -1 / d, 0, 0, 0, 1]);
            local = new DOMMatrix().translate(ax, ay).multiply(perspective).translate(-ax, -ay).multiply(local);
          }
          m = local.multiply(m);
          steps.push(current.id || current.localName);
          if (parentStyle.transformStyle !== 'preserve-3d') {
            const [px2, py2] = project(m.transformPoint(point));
            point = new DOMPoint(px2, py2, 0, 1);
            m = new DOMMatrix();
          }
        }
        const [bx, by] = origin.get(document.body);
        return [point.x + bx, point.y + by];
      };
      const result = {};
      for (const id of ids) {
        const e = document.getElementById(id), [w, h] = size.get(e);
        const points = [[0, 0], [w, 0], [w, h], [0, h], [w / 2, h / 2], [w / 4, h * 3 / 4]];
        const mapped = points.map(([x, y]) => map(e, x, y));
        // Projective: a perspective() function, the perspective property or preserve-3d in the chain.
        let projective = false;
        for (let a = e; a && a !== document.body; a = a.parentElement) {
          const s = getComputedStyle(a), m = new DOMMatrix(s.transform === 'none' ? undefined : s.transform);
          if (m.m14 || m.m24 || m.m34 || (a !== e && (s.perspective !== 'none' || s.transformStyle === 'preserve-3d'))) projective = true;
        }
        const r = e.getBoundingClientRect(), [rx, ry] = page(r);
        const xs = mapped.slice(0, 4).map(p => p[0]), ys = mapped.slice(0, 4).map(p => p[1]);
        const bbox = [Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)];
        const rect = [rx, ry, r.width, r.height];
        result[id] = {size: [w, h], points, page: mapped, projective, rect, bboxError: Math.max(...bbox.map((v, k) => Math.abs(v - rect[k])))};
      }
      const m = getComputedStyle(document.getElementById('m'));
      result.m.box = {border: [m.borderTopWidth, m.borderRightWidth, m.borderBottomWidth, m.borderLeftWidth].map(parseFloat),
        padding: [m.paddingTop, m.paddingRight, m.paddingBottom, m.paddingLeft].map(parseFloat),
        margin: [m.marginTop, m.marginRight, m.marginBottom, m.marginLeft].map(parseFloat)};
      return result;
    }, {ids: ELEMENTS, top: SCROLLER_TOP});
  } finally { await browser.close(); }
  out.maxBboxError = Math.max(...Object.values(out.elements).map(e => e.bboxError));
  writeFileSync(new URL('../fixtures/coordinate-spaces-oracle.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
  console.log('oracle', out.browser, 'max bbox error', out.maxBboxError, Object.fromEntries(Object.entries(out.elements).map(([k, v]) => [k, v.bboxError])));
}
