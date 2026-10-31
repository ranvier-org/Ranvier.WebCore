"""I04 pen and pointer fidelity probe: rv_host_pointer pen samples delivered as trusted pointer events with pointerType
pen, pointerId 2^30 + id, pressure, tangential pressure, tilt, twist, altitude and azimuth, contact size and movement,
pen pointer capture, rv_host_mouse's buttons, pressure and movement, and argument errors."""
import argparse
import ctypes
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pointer_support import (Harness, sample, OK, NULL_ARGUMENT, UNSUPPORTED, MOUSE, PEN, MOVE, DOWN, UP, CANCEL,
                             STATIONARY, BUTTON_NONE, BUTTON_LEFT, PEN_BASE, i32, f64, p)

PAGE = (b'<!doctype html><style>html,body{margin:0}#t{position:absolute;left:20px;top:20px;width:200px;height:100px}'
        b'#u{position:absolute;left:20px;top:150px;width:200px;height:60px}</style><body><div id=t></div><div id=u></div>')
EVENTS = ['pointerdown', 'pointermove', 'pointerup', 'pointercancel', 'gotpointercapture', 'lostpointercapture',
          'mousedown', 'mousemove', 'mouseup']


def angles(tiltX, tiltY):
    # https://w3c.github.io/pointerevents/#converting-between-tiltx-tilty-and-altitudeangle-azimuthangle
    tx, ty = math.radians(tiltX), math.radians(tiltY)
    if tiltX == 0 and tiltY == 0:
        return math.pi / 2, 0.0
    if tiltX == 0:
        return math.pi / 2 - abs(ty), (math.pi / 2 if tiltY > 0 else 3 * math.pi / 2)
    if tiltY == 0:
        return math.pi / 2 - abs(tx), (0.0 if tiltX > 0 else math.pi)
    azimuth = math.atan2(math.tan(ty), math.tan(tx))
    return math.atan(1 / math.sqrt(math.tan(tx) ** 2 + math.tan(ty) ** 2)), azimuth + (2 * math.pi if azimuth < 0 else 0)


def verify(directory, evidence):
    h = Harness(directory)
    b = h.bind
    altitude = b('rv_dom_pointer_event_get_altitude_angle', i32, [p, ctypes.POINTER(f64)])
    azimuth = b('rv_dom_pointer_event_get_azimuth_angle', i32, [p, ctypes.POINTER(f64)])
    set_capture = b('rv_dom_element_set_pointer_capture', i32, [p, i32])
    has_capture = b('rv_dom_element_has_pointer_capture', i32, [p, i32, ctypes.POINTER(i32)])
    h.expect(h.abi_has(b'pointer-input') == 1, 'pointer-input advertised')
    result = {'steps': []}

    def angle_fields(event, record):
        value = f64()
        if record['type'].startswith('pointer') and altitude(event, ctypes.byref(value)) == OK:
            record['altitudeAngle'] = value.value
        if record['type'].startswith('pointer') and azimuth(event, ctypes.byref(value)) == OK:
            record['azimuthAngle'] = value.value
    h.on_extra = angle_fields
    h.open(PAGE, EVENTS)

    def step(name, *samples):
        status = h.send(*samples)
        events = h.take()
        result['steps'].append({'name': name, 'status': status, 'events': events})
        h.expect(status in (0, 1), name + ' status ' + str(status))
        return events

    def one(events, kind):
        found = [e for e in events if e['type'] == kind]
        h.expect(len(found) == 1, f'one {kind}: {[e["type"] for e in events]}')
        return found[0]

    pen = lambda action, x, y, **k: sample(PEN, action, x, y, id=3, **k)
    # Hover, press with pressure, barrel pressure, tilt and twist, drag, release.
    hover = one(step('hover', pen(MOVE, 60, 40)), 'pointermove')
    h.expect(hover['pointerType'] == 'pen' and hover['pointerId'] == PEN_BASE + 3 and hover['trusted'] == 1, 'pen hover identity')
    h.expect(hover['pressure'] == 0 and hover['buttons'] == 0 and hover['isPrimary'] == 1, 'pen hover pressure 0')
    events = step('press', pen(DOWN, 60, 40, button=BUTTON_LEFT, buttons=1, clickCount=1, pressure=0.6, tangentialPressure=0.2,
                                tiltX=30, tiltY=-20, twist=45, width=3, height=2))
    down = one(events, 'pointerdown')
    h.expect(math.isclose(down['pressure'], 0.6, abs_tol=1e-6) and math.isclose(down['tangentialPressure'], 0.2, abs_tol=1e-6), 'press pressures')
    h.expect((down['tiltX'], down['tiltY'], down['twist'], down['width'], down['height']) == (30, -20, 45, 3, 2), 'press tilt, twist, contact')
    alt, az = angles(30, -20)
    h.expect(math.isclose(down['altitudeAngle'], alt, abs_tol=1e-9) and math.isclose(down['azimuthAngle'], az, abs_tol=1e-9), 'press altitude and azimuth from tilt')
    h.expect(down['buttons'] == 1 and down['target'] == 't', 'press buttons and target')
    mouse_down = one(events, 'mousedown')
    h.expect(mouse_down['buttons'] == 1 and events.index(down) < events.index(mouse_down), 'compatibility mousedown after pointerdown')
    drag = one(step('drag', pen(MOVE, 70, 45, buttons=1, pressure=0.7, tiltX=10, twist=90, movementX=10, movementY=5)), 'pointermove')
    h.expect(math.isclose(drag['pressure'], 0.7, abs_tol=1e-6) and (drag['tiltX'], drag['tiltY'], drag['twist']) == (10, 0, 90), 'drag pen fields')
    h.expect((drag['movementX'], drag['movementY'], drag['clientX'], drag['clientY']) == (10, 5, 70, 45), 'drag movement and position')
    alt, az = angles(10, 0)
    h.expect(math.isclose(drag['altitudeAngle'], alt, abs_tol=1e-9) and math.isclose(drag['azimuthAngle'], az, abs_tol=1e-9), 'drag angles')
    up = one(step('release', pen(UP, 70, 45, button=BUTTON_LEFT, clickCount=1)), 'pointerup')
    h.expect(up['pressure'] == 0 and up['buttons'] == 0 and up['pointerId'] == PEN_BASE + 3, 'release pressure 0')
    # A pen without pressure: the engine's 0.5 while a button is down.
    nopress = one(step('press without pressure', pen(DOWN, 60, 40, button=BUTTON_LEFT, buttons=1, clickCount=1)), 'pointerdown')
    h.expect(nopress['pressure'] == 0.5 and (nopress['tiltX'], nopress['twist'], nopress['width']) == (0, 0, 1), 'pen defaults')
    step('release again', pen(UP, 60, 40, button=BUTTON_LEFT, clickCount=1))

    # Pen pointer capture: #t captures the pen, which then moves over #u.
    t = h.node('#t')
    step('press for capture', pen(DOWN, 60, 40, button=BUTTON_LEFT, buttons=1, clickCount=1, pressure=0.5))
    h.expect(set_capture(t, PEN_BASE + 3) == OK, 'set pen capture')
    captured = step('move over u', pen(MOVE, 60, 170, buttons=1, pressure=0.5))
    got = one(captured, 'gotpointercapture')
    h.expect(got['pointerId'] == PEN_BASE + 3 and got['pointerType'] == 'pen' and got['target'] == 't', 'gotpointercapture pen')
    h.expect(one(captured, 'pointermove')['target'] == 't', 'captured move targets #t')
    flag = i32()
    h.expect(has_capture(t, PEN_BASE + 3, ctypes.byref(flag)) == OK and flag.value == 1, 'hasPointerCapture pen')
    h.expect(has_capture(t, 1, ctypes.byref(flag)) == OK and flag.value == 0, 'mouse not captured')
    released = step('release captured', pen(UP, 60, 170, button=BUTTON_LEFT, clickCount=1))
    h.expect(one(released, 'lostpointercapture')['pointerId'] == PEN_BASE + 3, 'lostpointercapture pen')
    h.node_release(t)

    # A platform-cancelled pen contact ends as a release.
    step('press before cancel', pen(DOWN, 60, 40, button=BUTTON_LEFT, buttons=1, clickCount=1, pressure=0.5))
    cancelled = step('cancel', pen(CANCEL, 60, 40))
    h.expect(one(cancelled, 'pointerup')['buttons'] == 0, 'cancelled pen releases')

    # rv_host_mouse: buttons held, pressure 0.5 while held, movement from the previous position.
    h.log = []
    h.expect(h.mouse(h.host, 0, 30, 30, BUTTON_NONE, 0, 0) in (0, 1), 'mouse move')
    h.expect(h.mouse(h.host, 0, 50, 45, BUTTON_NONE, 0, 0) in (0, 1), 'mouse move 2')
    h.expect(h.mouse(h.host, 1, 50, 45, BUTTON_LEFT, 1, 0) in (0, 1), 'mouse down')
    h.expect(h.mouse(h.host, 2, 50, 45, BUTTON_LEFT, 1, 0) in (0, 1), 'mouse up')
    mouse = h.take()
    result['mouse'] = mouse
    moves = [e for e in mouse if e['type'] == 'pointermove']
    h.expect(len(moves) == 2 and (moves[1]['movementX'], moves[1]['movementY']) == (20, 15), 'mouse movement 20,15')
    md = [e for e in mouse if e['type'] == 'pointerdown'][0]
    h.expect(md['pointerType'] == 'mouse' and md['pointerId'] == 1 and md['buttons'] == 1 and md['pressure'] == 0.5, 'mouse press pressure 0.5')
    mu = [e for e in mouse if e['type'] == 'pointerup'][0]
    h.expect(mu['buttons'] == 0 and mu['pressure'] == 0, 'mouse release pressure 0')
    # A mouse sample through rv_host_pointer.
    mm = one(step('mouse sample', sample(MOUSE, MOVE, 80, 50, movementX=3, movementY=4)), 'pointermove')
    h.expect(mm['pointerType'] == 'mouse' and (mm['movementX'], mm['movementY']) == (3, 4), 'mouse sample movement')

    # Argument errors.
    h.expect(h.send(sample(PEN, MOVE, 1, 1), sample(PEN, MOVE, 2, 2)) == UNSUPPORTED, 'two pen samples')
    h.expect(h.send(sample(PEN, STATIONARY, 1, 1)) == UNSUPPORTED, 'stationary pen')
    h.expect(h.send(sample(MOUSE, CANCEL, 1, 1)) == UNSUPPORTED, 'cancelled mouse')
    h.expect(h.send(sample(5, MOVE, 1, 1)) == UNSUPPORTED, 'unknown pointer type')
    h.expect(h.send(sample(PEN, MOVE, 1, 1, button=7)) == UNSUPPORTED, 'unknown button')
    h.expect(h.send(sample(PEN, MOVE, 1, 1, width=-1)) == UNSUPPORTED, 'negative width')
    h.expect(h.take() == [], 'refused samples dispatch nothing')
    h.close()
    h.finish()
    result['checks'] = h.checks
    if evidence:
        Path(evidence).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f'PASS pen input: {h.checks} assertions', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence-json')
    options = parser.parse_args()
    verify(options.native_directory, options.evidence_json)
