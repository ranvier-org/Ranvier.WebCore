"""I06 pointer lock probe: rv_element_request_pointer_lock under the engine's gesture, document, focus and option rules,
the app's grant or denial through rv_host_pointer_lock_state and rv_host_pointer_lock_resolve, relative movement while
locked (target held at the lock element, clientX/Y held at the lock position, no pointer capture), exit, platform loss,
focus loss, removal of the lock element, relock rules, argument errors and teardown with a request pending."""
import argparse
import ctypes
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pointer_support import (Harness, CALLBACK, sample, OK, NULL_ARGUMENT, DOM_EXCEPTION, NOT_ELEMENT, UNSUPPORTED, MOUSE,
                             PEN, MOVE, DOWN, UP, BUTTON_NONE, BUTTON_LEFT, LOCK_NONE, LOCK_PENDING, LOCK_LOCKED, i32, p)

PAGE = (b'<!doctype html><style>html,body{margin:0}#t{position:absolute;left:20px;top:20px;width:200px;height:100px}'
        b'#u{position:absolute;left:20px;top:150px;width:200px;height:60px}</style><body><div id=t></div><div id=u></div>')
EVENTS = ['pointerlockchange', 'pointerlockerror', 'pointermove', 'mousemove', 'pointerdown', 'mousedown', 'pointerup',
          'mouseup', 'click']
WRONG_INTERFACE = -11


def verify(directory, evidence):
    h = Harness(directory)
    b = h.bind
    supported = h.abi_has(b'pointer-lock') == 1
    h.expect(supported, 'pointer-lock advertised')
    state_of = b('rv_host_pointer_lock_state', i32, [p, ctypes.POINTER(i32), ctypes.POINTER(p)])
    resolve = b('rv_host_pointer_lock_resolve', i32, [p, i32])
    lose = b('rv_host_pointer_lock_lose', i32, [p])
    request = b('rv_element_request_pointer_lock', i32, [p, i32])
    exit_lock = b('rv_document_exit_pointer_lock', i32, [p])
    lock_element = b('rv_dom_document_get_pointer_lock_element', i32, [p, ctypes.POINTER(p)])
    has_capture = b('rv_dom_element_has_pointer_capture', i32, [p, i32, ctypes.POINTER(i32)])
    remove = b('rv_node_remove', i32, [p])
    result = {'steps': []}
    h.open(PAGE, EVENTS)
    h.expect(h.set_focused(h.host, 1) == OK, 'focus host')
    t, u = h.node('#t'), h.node('#u')

    def state():
        value, element = i32(), p()
        h.expect(state_of(h.host, ctypes.byref(value), ctypes.byref(element)) == OK, 'state')
        name = h.id_of(element.value)
        if element.value:
            h.node_release(element.value)
        return value.value, name

    def lock_owner():
        element = p()
        h.expect(lock_element(h.document, ctypes.byref(element)) == OK, 'pointerLockElement')
        name = h.id_of(element.value)
        if element.value:
            h.node_release(element.value)
        return name

    def types(events):
        return [e['type'] for e in events if e['type'].startswith('pointerlock')]

    # Requests from a trusted mousedown listener on #t, with the mode the step sets.
    gesture = {'unadjusted': 0, 'statuses': []}

    def on_down(context, event):
        gesture['statuses'].append(request(t, gesture['unadjusted']))
        return 0
    down_callback = CALLBACK(on_down)
    down_listener = h.add_listener(t, b'mousedown', 0, down_callback, None)

    def click(x=60, y=60):
        h.expect(h.mouse(h.host, 0, x, y, BUTTON_NONE, 0, 0) in (0, 1), 'move to press')
        h.expect(h.mouse(h.host, 1, x, y, BUTTON_LEFT, 1, 0) in (0, 1), 'press')
        h.expect(h.mouse(h.host, 2, x, y, BUTTON_LEFT, 1, 0) in (0, 1), 'release')
        statuses, gesture['statuses'] = gesture['statuses'], []
        return statuses

    def record(name, value):
        result['steps'].append({'name': name, 'value': value})

    # No gesture: NotAllowedError and pointerlockerror.
    h.expect(request(t, 0) == DOM_EXCEPTION and h.exception_name() == 'NotAllowedError', 'no gesture: NotAllowedError')
    events = h.take()
    h.expect(types(events) == ['pointerlockerror'] and state() == (LOCK_NONE, None), 'no gesture: error, no lock')
    h.expect(resolve(h.host, 1) == UNSUPPORTED, 'nothing to resolve')

    # A gesture request the app denies.
    h.expect(click() == [OK], 'gesture request accepted')
    h.expect(state() == (LOCK_PENDING, 't'), 'pending on #t')
    h.expect(lock_owner() is None, 'pending: pointerLockElement null')
    h.expect(resolve(h.host, 0) == OK, 'deny')
    events = h.take()
    h.expect(types(events) == ['pointerlockerror'] and state() == (LOCK_NONE, None), 'denied: error, no lock')

    # A gesture request the app grants.
    h.expect(click(60, 60) == [OK], 'second gesture request')
    h.expect(resolve(h.host, 1) == OK, 'grant')
    h.expect(resolve(h.host, 1) == UNSUPPORTED, 'grant answered once')
    events = h.take()
    h.expect(types(events) == ['pointerlockchange'] and state() == (LOCK_LOCKED, 't'), 'granted: change, locked on #t')
    h.expect(lock_owner() == 't', 'pointerLockElement #t')

    # Locked: relative movement over #u still targets #t, at the lock position, without pointer capture.
    h.expect(h.send(sample(MOUSE, MOVE, 100, 180, movementX=30, movementY=20)) in (0, 1), 'locked move')
    events = h.take()
    record('locked move', events)
    moves = [e for e in events if e['type'] in ('pointermove', 'mousemove')]
    h.expect([e['type'] for e in moves] == ['pointermove', 'mousemove'], 'locked move events')
    h.expect(all(e['target'] == 't' and (e['clientX'], e['clientY']) == (60, 60) and (e['movementX'], e['movementY']) == (30, 20) for e in moves), 'locked move at lock position')
    flag = i32()
    h.expect(has_capture(t, 1, ctypes.byref(flag)) == OK and flag.value == 0, 'lock is not pointer capture')
    h.expect(h.send(sample(MOUSE, DOWN, 100, 180, button=BUTTON_LEFT, buttons=1, clickCount=1)) in (0, 1), 'locked press')
    h.expect(h.send(sample(MOUSE, UP, 100, 180, button=BUTTON_LEFT, clickCount=1)) in (0, 1), 'locked release')
    events = h.take()
    record('locked click', events)
    # A request from the lock target while it holds the lock keeps the lock.
    h.expect(gesture['statuses'] == [OK] and state() == (LOCK_LOCKED, 't'), 'request while locked keeps the lock')
    gesture['statuses'] = []
    h.expect([e['target'] for e in events if e['type'] in ('mousedown', 'mouseup', 'click')] == ['t', 't', 't'], 'locked click targets #t')

    # Exit: pointerlockchange; relock without a gesture is then allowed.
    h.expect(exit_lock(h.document) == OK, 'exit')
    events = h.take()
    h.expect(types(events) == ['pointerlockchange'] and state() == (LOCK_NONE, None) and lock_owner() is None, 'exited')
    h.expect(request(t, 0) == OK and state() == (LOCK_PENDING, 't'), 'relock after exit without gesture')
    h.expect(resolve(h.host, 1) == OK, 'grant relock')
    h.take()
    h.expect(state() == (LOCK_LOCKED, 't'), 'relocked')

    # Platform loss: pointerlockchange; relock then needs a gesture again.
    h.expect(lose(h.host) == OK, 'lose')
    events = h.take()
    h.expect(types(events) == ['pointerlockchange'] and state() == (LOCK_NONE, None), 'lost')
    h.expect(lose(h.host) == OK, 'lose without lock')
    h.expect(request(t, 0) == DOM_EXCEPTION and h.exception_name() == 'NotAllowedError', 'relock after loss needs gesture')
    h.take()

    # Unadjusted movement is unavailable; a disconnected element cannot lock.
    gesture['unadjusted'] = 1
    h.expect(click() == [DOM_EXCEPTION] and h.exception_name() == 'NotSupportedError', 'unadjusted movement unsupported')
    gesture['unadjusted'] = 0
    h.take()

    # Focus loss: a held lock ends, a request while unfocused fails.
    h.expect(click() == [OK] and resolve(h.host, 1) == OK, 'lock for focus loss')
    h.take()
    h.expect(h.set_focused(h.host, 0) == OK, 'blur')
    events = h.take()
    h.expect(types(events) == ['pointerlockchange'] and state() == (LOCK_NONE, None), 'blur ends lock')
    # An unfocused window denies at once, as the engine treats a window without focus: WrongDocumentError.
    h.expect(click() == [DOM_EXCEPTION] and h.exception_name() == 'WrongDocumentError', 'unfocused request refused')
    events = h.take()
    h.expect(types(events) == ['pointerlockerror'] and state() == (LOCK_NONE, None), 'unfocused window: pointerlockerror')
    h.expect(h.set_focused(h.host, 1) == OK, 'refocus')
    # Blur with a request pending denies it.
    h.expect(click() == [OK] and state()[0] == LOCK_PENDING, 'pending before blur')
    h.expect(h.set_focused(h.host, 0) == OK and h.set_focused(h.host, 1) == OK, 'blur and refocus')
    events = h.take()
    h.expect(types(events) == ['pointerlockerror'] and state() == (LOCK_NONE, None) and resolve(h.host, 1) == UNSUPPORTED, 'blur denies pending')

    # Removing the lock element ends the lock.
    h.expect(click(60, 170) == [], 'press on #u requests nothing')
    h.expect(click() == [OK] and resolve(h.host, 1) == OK, 'lock before removal')
    h.take()
    h.expect(remove(t) == OK, 'remove #t')
    events = h.take()
    h.expect(types(events) == ['pointerlockchange'] and state() == (LOCK_NONE, None), 'removal ends lock')
    h.expect(request(t, 0) == DOM_EXCEPTION and h.exception_name() == 'WrongDocumentError', 'disconnected element: WrongDocumentError')
    h.take()

    # Argument errors.
    status = i32()
    h.expect(state_of(None, ctypes.byref(status), None) == NULL_ARGUMENT and state_of(h.host, None, None) == NULL_ARGUMENT, 'state NULL')
    h.expect(state_of(h.host, ctypes.byref(status), None) == OK and status.value == LOCK_NONE, 'state without element out')
    h.expect(resolve(None, 1) == NULL_ARGUMENT and lose(None) == NULL_ARGUMENT, 'resolve and lose NULL')
    h.expect(request(None, 0) == NULL_ARGUMENT and exit_lock(None) == NULL_ARGUMENT, 'request and exit NULL')
    h.expect(request(h.document, 0) == NOT_ELEMENT, 'request on a document')
    h.expect(exit_lock(u) == WRONG_INTERFACE, 'exit on an element')
    h.expect(h.listener_remove(down_listener) == OK, 'gesture listener removed')
    h.node_release(t)
    h.node_release(u)
    h.close()

    # Teardown with a request pending, and with a lock held.
    teardown = []
    for granted in (False, True):
        h.open(PAGE, EVENTS)
        h.set_focused(h.host, 1)
        t = h.node('#t')
        gesture['statuses'] = []
        listener = h.add_listener(t, b'mousedown', 0, down_callback, None)
        h.expect(click() == [OK], 'teardown request')
        if granted:
            h.expect(resolve(h.host, 1) == OK, 'teardown grant')
            h.take()
        kept = h.listeners + [listener]
        h.listeners = []
        h.node_release(t)
        h.node_release(h.document)
        h.host_destroy(h.host)
        h.host = None
        h.expect([h.listener_remove(item) for item in kept] == [OK] * len(kept), 'listeners removed after destroy')
        h.drain()
        h.log = []
        teardown.append({'case': 'destroy-with-lock-' + ('held' if granted else 'pending'), 'listeners': f'{len(kept)} removed after destroy'})
    result['teardown'] = teardown
    h.finish()
    result['checks'] = h.checks
    if evidence:
        Path(evidence).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f'PASS pointer lock: {h.checks} assertions; teardown {len(teardown)} cases', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence-json')
    options = parser.parse_args()
    verify(options.native_directory, options.evidence_json)
