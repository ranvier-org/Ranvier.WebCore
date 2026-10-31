// Chromium oracle for tests/abi/value_factories.py: writes tests/fixtures/value-factories-oracle.json.
// Each measurement is a flat key of the native probe. Numbers that JSON cannot carry are written as strings.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');

const browser = await chromium.launch({headless: true});
const version = browser.version();
const page = await browser.newPage();
// A secure origin exposes PointerEvent.getCoalescedEvents and getPredictedEvents.
const markup = '<!doctype html><html><body><p id="p">hello</p><iframe id="f"></iframe></body></html>';
await page.route('https://app.test/', route => route.fulfill({status: 200, contentType: 'text/html', body: markup}));
await page.goto('https://app.test/');

const values = await page.evaluate(() => {
  const r = {};
  const number = v => Number.isFinite(v) ? v : String(v);
  const fails = f => { try { f(); return null; } catch (e) { return e.name; } };
  const p = document.getElementById('p');
  const t0 = p.firstChild;

  // Nodes.
  let t = new Text();
  r['text.default'] = [t.nodeType, t.data, t.ownerDocument === document, t.isConnected, t.parentNode === null];
  t = new Text('h\u00e9llo \u{1F600}');
  r['text.data'] = t.data;
  t.data = 'changed';
  r['text.mutated'] = t.data;
  const c = new Comment('note');
  r['comment'] = [c.nodeType, c.data, c.ownerDocument === document, c.isConnected];
  r['comment.default'] = new Comment().data;
  const f = new DocumentFragment();
  r['fragment'] = [f.nodeType, f.childNodes.length, f.ownerDocument === document, f.isConnected];
  f.appendChild(new Text('x'));
  r['fragment.appended'] = [f.childNodes.length, f.firstChild.data];
  const rg = new Range();
  r['range.default'] = [rg.startContainer === document, rg.startOffset, rg.endContainer === document, rg.endOffset, rg.collapsed];
  rg.setStart(t0, 1);
  rg.setEnd(t0, 3);
  r['range.set'] = [rg.startContainer === t0, rg.startOffset, rg.endOffset, rg.collapsed];
  r['range.outOfBounds'] = fails(() => rg.setEnd(t0, 9));

  const d = new Document();
  r['document'] = [d.nodeType, d.contentType, d.characterSet, d.compatMode, d.childNodes.length, d.documentElement === null, d === document];
  const root = d.createElement('root');
  r['document.createElement'] = [root.namespaceURI, root.tagName, root.ownerDocument === d];
  d.appendChild(root);
  const moved = new Text('y');
  root.appendChild(moved);
  r['document.adopted'] = [moved.ownerDocument === d, moved.isConnected, d.documentElement === root];

  const parsed = Document.parseHTMLUnsafe('<!doctype html><p id="a">one</p><p>two</p>');
  r['parse'] = [parsed.nodeType, parsed.contentType, parsed.compatMode, parsed.characterSet, parsed === document,
                parsed.body.childNodes.length, parsed.body.firstChild.tagName, parsed.firstChild.nodeType];
  r['parse.empty'] = [Document.parseHTMLUnsafe('').body.childNodes.length, Document.parseHTMLUnsafe('').compatMode];

  // StaticRange.
  const sr = new StaticRange({startContainer: t0, startOffset: 1, endContainer: t0, endOffset: 9});
  r['static'] = [sr.startContainer === t0, sr.startOffset, sr.endContainer === t0, sr.endOffset, sr.collapsed];
  const collapsed = new StaticRange({startContainer: p, startOffset: 0, endContainer: p, endOffset: 0});
  r['static.collapsed'] = collapsed.collapsed;
  r['static.attr'] = fails(() => new StaticRange({startContainer: document.createAttribute('x'), startOffset: 0, endContainer: t0, endOffset: 0}));
  r['static.doctype'] = fails(() => new StaticRange({startContainer: t0, startOffset: 0, endContainer: parsed.firstChild, endOffset: 0}));
  r['static.missing'] = fails(() => new StaticRange({startContainer: t0, startOffset: 0, endOffset: 0}));

  // Events.
  const base = e => [e.type, e.bubbles, e.cancelable, e.composed, e.isTrusted, e.detail];
  let e = new InputEvent('beforeinput');
  r['input.default'] = [...base(e), e.data, e.isComposing, e.inputType, e.getTargetRanges().length];
  e = new InputEvent('beforeinput', {bubbles: true, cancelable: true, composed: true, detail: 2, data: 'ab\u00e9', isComposing: true, inputType: 'insertText'});
  r['input.full'] = [...base(e), e.data, e.isComposing, e.inputType, e.getTargetRanges().length];
  r['input.emptyData'] = new InputEvent('input', {data: ''}).data;

  const wheel = e => [e.deltaX, e.deltaY, e.deltaZ, e.deltaMode, e.wheelDeltaX, e.wheelDeltaY, e.wheelDelta, e.clientX, e.clientY,
                      e.screenX, e.screenY, e.button, e.buttons, e.ctrlKey, e.shiftKey, e.altKey, e.metaKey, e.relatedTarget === p];
  e = new WheelEvent('wheel');
  r['wheel.default'] = [...base(e), ...wheel(e)];
  e = new WheelEvent('wheel', {bubbles: true, cancelable: true, deltaX: 3.5, deltaY: -120, deltaZ: 1, deltaMode: 1, clientX: 10, clientY: 20,
                                 screenX: 1, screenY: 2, ctrlKey: true, metaKey: true, buttons: 1, relatedTarget: p});
  r['wheel.full'] = [...base(e), ...wheel(e)];
  e = new WheelEvent('wheel', {wheelDeltaX: 240, wheelDeltaY: -120});
  r['wheel.legacy'] = [e.deltaX, e.deltaY, e.wheelDeltaX, e.wheelDeltaY];

  const pointer = e => [e.pointerId, e.width, e.height, number(e.pressure), number(e.tangentialPressure), e.tiltX, e.tiltY, e.twist,
                        e.pointerType, e.isPrimary, e.clientX, e.clientY, e.button, e.buttons, e.relatedTarget === p,
                        e.getCoalescedEvents().length, e.getPredictedEvents().length];
  e = new PointerEvent('pointerdown');
  r['pointer.default'] = [...base(e), ...pointer(e)];
  const sub = new PointerEvent('pointermove', {pointerId: 7});
  e = new PointerEvent('pointermove', {bubbles: true, cancelable: true, composed: true, pointerId: 7, width: 2.5, height: 3.5, pressure: 0.5,
                                       tangentialPressure: -0.25, tiltX: 30, tiltY: -20, twist: 90, pointerType: 'pen', isPrimary: true,
                                       clientX: 12.5, clientY: 7.25, button: 1, buttons: 4, relatedTarget: p,
                                       coalescedEvents: [sub], predictedEvents: [sub, sub]});
  r['pointer.full'] = [...base(e), ...pointer(e)];
  r['pointer.coalescedIdentity'] = e.getCoalescedEvents()[0] === sub;
  r['pointer.pressure'] = number(new PointerEvent('pointerdown', {pressure: 0.1}).pressure);

  // Dispatch outcomes.
  const seen = [];
  const listener = event => { seen.push([event.eventPhase, event.target === p, event.currentTarget === p, event.isTrusted]); event.preventDefault(); };
  p.addEventListener('wheel', listener);
  const cancelable = new WheelEvent('wheel', {cancelable: true, bubbles: true});
  r['dispatch.cancelable'] = [p.dispatchEvent(cancelable), cancelable.defaultPrevented];
  const plain = new WheelEvent('wheel');
  r['dispatch.plain'] = [p.dispatchEvent(plain), plain.defaultPrevented];
  p.removeEventListener('wheel', listener);
  r['dispatch.seen'] = seen;
  r['dispatch.redispatch'] = fails(() => { const once = new InputEvent('input'); p.dispatchEvent(once); p.dispatchEvent(once); });

  // Matrices.
  const six = [0.1, 0, 0, 1, 5, 6];
  const sixteen = [1, 2, 0, 0, 3, 4, 0, 0, 0, 0, 1, 0, 5, 6, 0, 1];
  let m = DOMMatrix.fromFloat32Array(new Float32Array(six));
  r['matrix.f32'] = [m.constructor.name, m.a, m.b, m.c, m.d, m.e, m.f, m.is2D, m.isIdentity];
  m = DOMMatrix.fromFloat64Array(new Float64Array(six));
  r['matrix.f64'] = [m.constructor.name, m.a, m.e, m.f, m.is2D];
  m.a = 2;
  r['matrix.mutated'] = m.a;
  m = DOMMatrix.fromFloat64Array(new Float64Array(sixteen));
  r['matrix.f64.16'] = [m.m11, m.m12, m.m21, m.m22, m.m41, m.m42, m.m33, m.m44, m.is2D];
  m = DOMMatrix.fromFloat64Array(new Float64Array([NaN, 0, 0, 1, Infinity, 0]));
  r['matrix.nonfinite'] = [number(m.a), number(m.e), m.is2D];
  r['matrix.short'] = fails(() => DOMMatrix.fromFloat64Array(new Float64Array(5)));
  r['matrix.empty'] = fails(() => DOMMatrix.fromFloat32Array(new Float32Array(0)));
  r['matrix.long'] = fails(() => DOMMatrix.fromFloat32Array(new Float32Array(17)));
  const ro = DOMMatrixReadOnly.fromFloat32Array(new Float32Array(six));
  r['readonly.f32'] = [ro.constructor.name, ro.a, ro.is2D];
  ro.a = 3;
  r['readonly.unchanged'] = ro.a;
  r['readonly.f64'] = [DOMMatrixReadOnly.fromFloat64Array(new Float64Array(sixteen)).constructor.name, DOMMatrixReadOnly.fromFloat64Array(new Float64Array(sixteen)).m41];

  // A factory of another document's realm makes a node of that document.
  const idoc = document.getElementById('f').contentDocument;
  const ForeignText = document.getElementById('f').contentWindow.Text;
  const foreign = new ForeignText('z');
  r['crossDocument'] = [foreign.ownerDocument === idoc, foreign.ownerDocument === document];
  return r;
});

writeFileSync('tests/fixtures/value-factories-oracle.json', JSON.stringify({browser: `chromium ${version}`, values}, null, 2) + '\n');
await browser.close();
console.log(`value-factories oracle: ${Object.keys(values).length} measurements, chromium ${version}`);
