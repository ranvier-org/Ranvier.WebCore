"""I03 touch input probe: rv_host_pointer touch frames delivered as trusted touchstart, touchmove, touchend and
touchcancel with touches, targetTouches and changedTouches (identity, coordinates, radii, rotation, force, target), the
touch pointer events WebKit dispatches with them, argument errors, the wrong thread, and teardown with contacts down.
Where WebKit builds without TOUCH_EVENTS (macOS), touch input is RV_ERR_UNSUPPORTED and the touch interfaces absent."""
import argparse
import ctypes
import json
import math
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pointer_support import (Harness, TouchGeometry, sample, OK, NULL_ARGUMENT, WRONG_THREAD, UNSUPPORTED, TOUCH, PEN,
                             MOVE, DOWN, UP, CANCEL, STATIONARY, i32, f64, p)

PAGE = (b'<!doctype html><style>html,body{margin:0}#t{position:absolute;left:20px;top:20px;width:200px;height:100px}'
        b'#u{position:absolute;left:20px;top:150px;width:200px;height:60px}</style><body><div id=t></div><div id=u></div>')
TOUCH_EVENTS = ['touchstart', 'touchmove', 'touchend', 'touchcancel']
POINTER_EVENTS = ['pointerdown', 'pointermove', 'pointerup', 'pointercancel', 'gotpointercapture', 'lostpointercapture']


def contact(id, action, x, y, rx, ry, angle, force):
    return sample(TOUCH, action, x, y, id=id, width=2 * rx, height=2 * ry, twist=angle, pressure=force)


def verify(directory, evidence):
    h = Harness(directory)
    b = h.bind
    supported = h.abi_has(b'touch-input') == 1
    h.expect(h.abi_has(b'pointer-input') == 1, 'pointer-input advertised')
    result = {'touchInput': supported, 'frames': [], 'teardown': []}
    if not supported:
        # The macOS build: touch frames are refused and the touch interfaces are absent.
        h.open(PAGE, [])
        h.expect(h.send(contact(0, DOWN, 50, 50, 4, 6, 30, 0.4)) == UNSUPPORTED, 'touch unsupported without TOUCH_EVENTS')
        h.expect(not hasattr(h.library, 'rv_dom_touch_get_identifier') or
                 b('rv_dom_touch_get_identifier', i32, [p, ctypes.POINTER(i32)])(None, None) in (UNSUPPORTED, NULL_ARGUMENT), 'touch getters unavailable')
        h.close()
        h.finish()
        Path(evidence).write_text(json.dumps(result, indent=2), encoding='utf-8') if evidence else None
        print(f'PASS touch input (unsupported build): {h.checks} assertions', flush=True)
        return
    list_get = {n: b('rv_dom_touch_event_get_' + n, i32, [p, ctypes.POINTER(p)]) for n in ['touches', 'target_touches', 'changed_touches']}
    list_length = b('rv_dom_touch_list_get_length', i32, [p, ctypes.POINTER(ctypes.c_uint32)])
    list_item = b('rv_dom_touch_list_item', i32, [p, ctypes.c_uint32, ctypes.POINTER(p)])
    list_release = b('rv_dom_touch_list_release', None, [p])
    touch_release = b('rv_dom_touch_release', None, [p])
    identifier = b('rv_dom_touch_get_identifier', i32, [p, ctypes.POINTER(i32)])
    coords = {n: b('rv_dom_touch_get_' + n, i32, [p, ctypes.POINTER(f64)]) for n in ['client_x', 'client_y', 'page_x', 'page_y', 'screen_x', 'screen_y']}
    touch_target = b('rv_dom_touch_get_target', i32, [p, ctypes.POINTER(p)])
    geometry = b('rv_touch_geometry', i32, [p, ctypes.POINTER(TouchGeometry)])

    def touch_record(touch):
        value, record = i32(), {}
        h.expect(identifier(touch, ctypes.byref(value)) == OK, 'identifier')
        record['id'] = value.value
        for name, fn in coords.items():
            number = f64()
            h.expect(fn(touch, ctypes.byref(number)) == OK, name)
            record[name] = number.value
        target = p()
        h.expect(touch_target(touch, ctypes.byref(target)) == OK, 'touch target')
        record['target'] = h.id_of(target.value)
        if target.value:
            h.node_release(target.value)
        g = TouchGeometry(size=ctypes.sizeof(TouchGeometry))
        h.expect(geometry(touch, ctypes.byref(g)) == OK, 'geometry')
        record.update(radiusX=g.radiusX, radiusY=g.radiusY, rotationAngle=round(g.rotationAngle, 4), force=round(g.force, 4))
        return record

    def lists(event, record):
        if not record['type'].startswith('touch'):
            return
        for name, fn in list_get.items():
            handle = p()
            h.expect(fn(event, ctypes.byref(handle)) == OK and bool(handle.value), name)
            count = ctypes.c_uint32()
            h.expect(list_length(handle, ctypes.byref(count)) == OK, name + ' length')
            items = []
            for index in range(count.value):
                touch = p()
                h.expect(list_item(handle, index, ctypes.byref(touch)) == OK and bool(touch.value), name + ' item')
                items.append(touch_record(touch))
                touch_release(touch)
            list_release(handle)
            record[name] = items
    h.on_extra = lists
    h.open(PAGE, TOUCH_EVENTS + POINTER_EVENTS)
    # The app declares its touch screen's contacts: Navigator.maxTouchPoints, 0 until set, per host.
    set_points = b('rv_host_set_max_touch_points', i32, [p, i32])
    get_points = b('rv_host_max_touch_points', i32, [p, ctypes.POINTER(i32)])
    value = i32()
    h.expect(get_points(h.host, ctypes.byref(value)) == OK and value.value == 0, 'maxTouchPoints 0 by default')
    h.expect(set_points(h.host, 5) == OK and get_points(h.host, ctypes.byref(value)) == OK and value.value == 5, 'maxTouchPoints 5')
    other = h.host_create(10, 10)
    h.expect(get_points(other, ctypes.byref(value)) == OK and value.value == 0, 'maxTouchPoints per host')
    h.host_destroy(other)
    h.expect(set_points(h.host, -1) == UNSUPPORTED and set_points(None, 1) == NULL_ARGUMENT, 'maxTouchPoints errors')
    h.expect(h.load_html(h.host, PAGE) == OK, 'reload')
    h.node_release(h.document)
    h.document = h.host_document(h.host)
    for listener in h.listeners:
        h.expect(h.listener_remove(listener) == OK, 'listener moved')
    h.listeners = [h.add_listener(h.document, name.encode(), 0, h.callback, None) for name in TOUCH_EVENTS + POINTER_EVENTS]
    h.expect(get_points(h.host, ctypes.byref(value)) == OK and value.value == 5, 'maxTouchPoints survives document replacement')
    h.expect(set_points(h.host, 0) == OK and get_points(h.host, ctypes.byref(value)) == OK and value.value == 0, 'maxTouchPoints reset')
    h.expect(set_points(h.host, 5) == OK, 'maxTouchPoints 5 for the frames')

    def frame(name, *samples):
        status = h.send(*samples)
        events = h.take()
        result['frames'].append({'name': name, 'status': status, 'events': events})
        return status, events

    def of(events, kind):
        return [e for e in events if e['type'] == kind]

    def ids(items):
        return [t['id'] for t in items]

    # Contact 0 down on #t.
    status, events = frame('start 0', contact(0, DOWN, 50, 50, 4, 6, 30, 0.4))
    h.expect(status in (0, 1), 'start 0 status')
    start = of(events, 'touchstart')
    h.expect(len(start) == 1 and start[0]['trusted'] == 1 and start[0]['target'] == 't', 'touchstart trusted at #t')
    h.expect(ids(start[0]['touches']) == [0] and ids(start[0]['changed_touches']) == [0] and ids(start[0]['target_touches']) == [0], 'start 0 lists')
    t0 = start[0]['changed_touches'][0]
    h.expect((t0['client_x'], t0['client_y'], t0['page_x'], t0['page_y']) == (50, 50, 50, 50), 'start 0 coordinates')
    h.expect((t0['radiusX'], t0['radiusY'], t0['rotationAngle'], t0['force']) == (4, 6, 30, 0.4), 'start 0 radii, rotation, force')
    h.expect(t0['target'] == 't', 'start 0 touch target')
    down = of(events, 'pointerdown')
    h.expect(len(down) == 1 and down[0]['pointerType'] == 'touch' and down[0]['pointerId'] == 2, 'pointerdown touch id 2')
    h.expect(down[0]['isPrimary'] == 1 and down[0]['width'] == 8 and down[0]['height'] == 12 and math.isclose(down[0]['pressure'], 0.4, abs_tol=1e-6), 'pointerdown primary geometry')
    h.expect(down[0]['trusted'] == 1 and down[0]['target'] == 't', 'pointerdown trusted at #t')
    h.expect(events.index(down[0]) < events.index(start[0]), 'pointerdown precedes touchstart')

    # Contact 1 down on #t while 0 holds.
    status, events = frame('start 1', contact(0, STATIONARY, 50, 50, 4, 6, 30, 0.4), contact(1, DOWN, 100, 60, 2, 2, 0, 0.8))
    start = of(events, 'touchstart')
    h.expect(len(start) == 1 and ids(start[0]['touches']) == [0, 1] and ids(start[0]['changed_touches']) == [1], 'start 1 lists')
    h.expect(start[0]['changed_touches'][0]['force'] == 0.8 and start[0]['changed_touches'][0]['client_x'] == 100, 'start 1 force and position')
    down = of(events, 'pointerdown')
    h.expect(len(down) == 1 and down[0]['pointerId'] == 3 and down[0]['isPrimary'] == 0, 'second contact pointerdown non-primary id 3')
    got = of(events, 'gotpointercapture')
    h.expect(len(got) == 1 and got[0]['pointerId'] == 2, 'implicit touch capture of contact 0')

    # Contact 1 moves; 0 stays.
    status, events = frame('move 1', contact(0, STATIONARY, 50, 50, 4, 6, 30, 0.4), contact(1, MOVE, 120, 70, 2, 2, 0, 0.9))
    move = of(events, 'touchmove')
    h.expect(len(move) == 1 and ids(move[0]['changed_touches']) == [1] and ids(move[0]['touches']) == [0, 1], 'move 1 lists')
    moved = move[0]['changed_touches'][0]
    h.expect((moved['client_x'], moved['client_y'], moved['force']) == (120, 70, 0.9), 'move 1 position and force')
    pm = of(events, 'pointermove')
    h.expect([e['pointerId'] for e in pm] == [2, 3] and (pm[1]['clientX'], pm[1]['clientY']) == (120, 70), 'pointermove contact 1')
    # WebKit dispatches a pointermove for a stationary contact too, at its unchanged position (Chromium does not).
    h.expect((pm[0]['clientX'], pm[0]['clientY']) == (50, 50), 'stationary contact pointermove unchanged')
    got = of(events, 'gotpointercapture')
    h.expect(len(got) == 1 and got[0]['pointerId'] == 3 and got[0]['target'] == 't', 'implicit touch capture of contact 1')

    # Contact 1 lifts.
    status, events = frame('end 1', contact(0, STATIONARY, 50, 50, 4, 6, 30, 0.4), contact(1, UP, 120, 70, 2, 2, 0, 0.9))
    end = of(events, 'touchend')
    h.expect(len(end) == 1 and ids(end[0]['changed_touches']) == [1] and ids(end[0]['touches']) == [0] and ids(end[0]['target_touches']) == [0], 'end 1 lists')
    up = of(events, 'pointerup')
    h.expect(len(up) == 1 and up[0]['pointerId'] == 3 and up[0]['buttons'] == 0, 'pointerup contact 1')
    lost = of(events, 'lostpointercapture')
    h.expect(len(lost) == 1 and lost[0]['pointerId'] == 3, 'implicit capture released')

    # The platform cancels contact 0.
    status, events = frame('cancel 0', contact(0, CANCEL, 50, 50, 4, 6, 30, 0.4))
    cancel = of(events, 'touchcancel')
    h.expect(len(cancel) == 1 and ids(cancel[0]['changed_touches']) == [0] and cancel[0]['touches'] == [] and cancel[0]['target_touches'] == [], 'cancel 0 lists')
    pc = of(events, 'pointercancel')
    h.expect(len(pc) == 1 and pc[0]['pointerId'] == 2, 'pointercancel contact 0')

    # Ended contacts leave the pointer state: mouse input dispatches pointer events again.
    h.expect(h.mouse(h.host, 0, 60, 60, -1, 0, 0) in (0, 1), 'mouse after touch')
    h.expect([e['pointerType'] for e in of(h.take(), 'pointermove')] == ['mouse'], 'mouse pointermove after touch ends')

    # A contact that starts on #u targets #u for its whole life, and the second frame's move keeps the original target.
    status, events = frame('start on u', contact(4, DOWN, 40, 160, 1, 1, 0, 0.5))
    h.expect(of(events, 'touchstart')[0]['target'] == 'u', 'touch on #u')
    status, events = frame('move off u', contact(4, MOVE, 40, 60, 1, 1, 0, 0.5))
    h.expect(of(events, 'touchmove')[0]['target'] == 'u' and of(events, 'touchmove')[0]['changed_touches'][0]['target'] == 'u', 'moved touch keeps #u')
    status, events = frame('end on t', contact(4, UP, 40, 60, 1, 1, 0, 0.5))
    h.expect(of(events, 'touchend')[0]['target'] == 'u', 'touchend at the original target')

    # Argument errors leave the page unchanged.
    good = contact(7, DOWN, 50, 50, 1, 1, 0, 0.5)
    h.expect(h.pointer(None, ctypes.byref(good), 1) == NULL_ARGUMENT, 'NULL host')
    h.expect(h.pointer(h.host, None, 1) == NULL_ARGUMENT, 'NULL samples')
    h.expect(h.pointer(h.host, ctypes.byref(good), 0) == UNSUPPORTED, 'zero count')
    bad = contact(7, DOWN, 50, 50, 1, 1, 0, 0.5)
    bad.size = 8
    h.expect(h.send(bad) == UNSUPPORTED, 'short size')
    h.expect(h.send(contact(7, DOWN, 50, 50, 1, 1, 0, 0.5), contact(7, DOWN, 60, 50, 1, 1, 0, 0.5)) == UNSUPPORTED, 'repeated id')
    h.expect(h.send(contact(7, STATIONARY, 50, 50, 1, 1, 0, 0.5)) == UNSUPPORTED, 'no changed contact')
    h.expect(h.send(contact(7, DOWN, 50, 50, 1, 1, 0, 0.5), sample(PEN, DOWN, 50, 50)) == UNSUPPORTED, 'mixed device frame')
    h.expect(h.send(contact(7, 9, 50, 50, 1, 1, 0, 0.5)) == UNSUPPORTED, 'unknown action')
    h.expect(h.send(contact(-1, DOWN, 50, 50, 1, 1, 0, 0.5)) == UNSUPPORTED, 'negative id')
    h.expect(h.send(sample(TOUCH, DOWN, math.nan, 50)) == UNSUPPORTED, 'non-finite position')
    off_thread = []
    thread = threading.Thread(target=lambda: off_thread.append(h.pointer(h.host, ctypes.byref(good), 1)))
    thread.start()
    thread.join()
    h.expect(off_thread == [WRONG_THREAD], 'wrong thread')
    h.expect(h.take() == [], 'refused frames dispatch nothing')

    # A page with pointer listeners and no touch listeners still receives the touch pointer events.
    h.close()
    h.open(PAGE, POINTER_EVENTS)
    h.send(contact(0, DOWN, 50, 50, 1, 1, 0, 0.5))
    h.send(contact(0, UP, 50, 50, 1, 1, 0, 0.5))
    quiet = h.take()
    h.expect([(e['type'], e['pointerId']) for e in quiet] == [('pointerdown', 2), ('gotpointercapture', 2), ('pointerup', 2), ('lostpointercapture', 2)], 'pointer listeners alone receive touch pointer events')
    result['noTouchListener'] = quiet
    h.close()

    # Teardown: destroy with a contact down, and remove a listener after destroy.
    h.open(PAGE, TOUCH_EVENTS)
    h.send(contact(0, DOWN, 50, 50, 1, 1, 0, 0.5))
    kept = h.listeners
    h.listeners = []
    h.node_release(h.document)
    h.host_destroy(h.host)
    h.host = None
    h.expect([h.listener_remove(listener) for listener in kept] == [OK] * len(kept), 'listeners removed after destroy')
    result['teardown'].append({'case': 'destroy-with-contact-down', 'listeners': f'{len(kept)} removed after destroy'})
    h.log = []
    h.finish()
    result['checks'] = h.checks
    if evidence:
        Path(evidence).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f'PASS touch input: {h.checks} assertions; teardown {len(result["teardown"])} cases', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence-json')
    options = parser.parse_args()
    verify(options.native_directory, options.evidence_json)
