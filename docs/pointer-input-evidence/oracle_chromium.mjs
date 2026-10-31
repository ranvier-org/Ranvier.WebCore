// Chromium oracle for touch, pen and pointer-lock input: what the page receives for CDP-injected touch contacts, pen
// samples and relative mouse movement. Writes oracle-chromium.json next to this file.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const {chromium} = createRequire('C:/wk/ranvier-views/tests/NativeApi.Conformance/package.json')('playwright');
const page = '<!doctype html><style>html,body{margin:0}#t{position:absolute;left:20px;top:20px;width:200px;height:100px;touch-action:none}</style><body><div id=t></div>';
const browser = await chromium.launch({headless: true});
const out = {browser: browser.version()};
try {
  const context = await browser.newContext({viewport: {width: 320, height: 240}, hasTouch: true});
  const tab = await context.newPage();
  await tab.setContent(page);
  const cdp = await context.newCDPSession(tab);
  await tab.evaluate(() => {
    window.log = [];
    const touch = t => ({id: t.identifier, x: t.clientX, y: t.clientY, rx: t.radiusX, ry: t.radiusY, angle: t.rotationAngle, force: t.force, target: t.target.id || t.target.nodeName});
    for (const type of ['touchstart', 'touchmove', 'touchend', 'touchcancel'])
      addEventListener(type, e => log.push({type, trusted: e.isTrusted, touches: [...e.touches].map(touch), changed: [...e.changedTouches].map(touch), targetTouches: [...e.targetTouches].map(touch)}));
    for (const type of ['pointerdown', 'pointermove', 'pointerup', 'pointercancel', 'gotpointercapture', 'lostpointercapture'])
      addEventListener(type, e => log.push({type, trusted: e.isTrusted, pointerType: e.pointerType, primary: e.isPrimary, x: e.clientX, y: e.clientY, buttons: e.buttons,
        pressure: e.pressure, tangentialPressure: e.tangentialPressure, tiltX: e.tiltX, tiltY: e.tiltY, twist: e.twist, width: e.width, height: e.height,
        altitudeAngle: e.altitudeAngle, azimuthAngle: e.azimuthAngle, movementX: e.movementX, movementY: e.movementY, pointerIdSame: undefined, pointerId: e.pointerId}));
    for (const type of ['mousemove', 'mousedown', 'mouseup'])
      addEventListener(type, e => log.push({type, x: e.clientX, y: e.clientY, buttons: e.buttons, movementX: e.movementX, movementY: e.movementY}));
    for (const type of ['pointerlockchange', 'pointerlockerror'])
      document.addEventListener(type, () => log.push({type, element: document.pointerLockElement?.id ?? null}));
  });
  const take = () => tab.evaluate(() => log.splice(0));
  const touch = (type, points) => cdp.send('Input.dispatchTouchEvent', {type, touchPoints: points});
  out.maxTouchPoints = await tab.evaluate(() => navigator.maxTouchPoints);
  // Two contacts: start 0, start 1, move 1, end 0, cancel 1.
  await touch('touchStart', [{x: 50, y: 50, id: 0, radiusX: 4, radiusY: 6, rotationAngle: 30, force: 0.4}]);
  await touch('touchStart', [{x: 50, y: 50, id: 0, radiusX: 4, radiusY: 6, rotationAngle: 30, force: 0.4}, {x: 100, y: 60, id: 1, radiusX: 2, radiusY: 2, force: 0.8}]);
  await touch('touchMove', [{x: 50, y: 50, id: 0, radiusX: 4, radiusY: 6, rotationAngle: 30, force: 0.4}, {x: 120, y: 70, id: 1, radiusX: 2, radiusY: 2, force: 0.9}]);
  await touch('touchEnd', [{x: 120, y: 70, id: 1, radiusX: 2, radiusY: 2, force: 0.9}]);
  await touch('touchCancel', []);
  out.touch = await take();
  // Pen: hover, press with pressure and tilt, move, release.
  const pen = (type, x, y, extra = {}) => cdp.send('Input.dispatchMouseEvent', {type, x, y, pointerType: 'pen', button: extra.button ?? 'none', buttons: extra.buttons ?? 0, clickCount: extra.clickCount ?? 0,
    force: extra.force ?? 0, tangentialPressure: extra.tangentialPressure ?? 0, tiltX: extra.tiltX ?? 0, tiltY: extra.tiltY ?? 0, twist: extra.twist ?? 0});
  await pen('mouseMoved', 60, 40);
  await pen('mousePressed', 60, 40, {button: 'left', buttons: 1, clickCount: 1, force: 0.6, tangentialPressure: 0.2, tiltX: 30, tiltY: -20, twist: 45});
  await pen('mouseMoved', 70, 45, {buttons: 1, force: 0.7, tiltX: 10, tiltY: 0, twist: 90});
  await pen('mouseReleased', 70, 45, {button: 'left', buttons: 0, clickCount: 1});
  out.pen = await take();
  // Mouse press: pressure 0.5 while a button is held; movement deltas.
  await tab.mouse.move(30, 30); await tab.mouse.move(50, 45); await tab.mouse.down(); await tab.mouse.up();
  out.mouse = await take();
  // Pointer lock: without a gesture (error), then with one (change), relative movement, exit.
  out.lockWithoutGesture = await tab.evaluate(() => t.requestPointerLock().then(() => 'resolved', e => e.name));
  await tab.waitForTimeout(100);
  out.lockWithoutGestureEvents = await take();
  await tab.evaluate(() => t.addEventListener('mousedown', () => { window.lockPromise = t.requestPointerLock().then(() => 'resolved', e => e.name); }, {once: true}));
  await tab.mouse.move(60, 60); await tab.mouse.down(); await tab.mouse.up();
  out.lockWithGesture = await tab.evaluate(() => window.lockPromise);
  await tab.waitForTimeout(100);
  await tab.mouse.move(90, 80);
  out.locked = await take();
  await tab.evaluate(() => document.exitPointerLock()); await tab.waitForTimeout(100);
  out.unlocked = await take();
} finally { await browser.close(); }
writeFileSync(new URL('./oracle-chromium.json', import.meta.url), JSON.stringify(out, null, 1) + '\n');
console.log(JSON.stringify(out, null, 1).slice(0, 6000));
