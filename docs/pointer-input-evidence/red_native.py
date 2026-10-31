"""RED measurement of touch, pen and pointer-lock input on a candidate runtime: which injection and pointer-lock
exports exist, what PointerEvent and MouseEvent report for input that rv_host_mouse delivers, whether touch events
are delivered, and the status of the pointer-lock getters. Writes the JSON named by the second argument."""
import ctypes, json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parents[1] / 'tests/abi'))
from svg_paint_probe import SvgProbe

CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p)
PAGE = ('<!doctype html><style>html,body{margin:0}#t{position:absolute;left:20px;top:20px;width:200px;height:100px}</style>'
        '<body><div id=t></div>')
EVENTS = ['pointerdown', 'pointermove', 'pointerup', 'pointercancel', 'mousedown', 'mousemove', 'mouseup',
          'touchstart', 'touchmove', 'touchend', 'touchcancel', 'pointerlockchange', 'pointerlockerror']

out = {}
with SvgProbe(sys.argv[1], 320, 240) as p:
    P, I, D, F = p.pointer, p.integer, ctypes.c_double, ctypes.c_float
    lib = p.library
    out['abi'] = p.bind('rv_abi_version', I, [])()
    has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
    out['abi_has'] = {f: has(f.encode()) for f in ['input', 'input-state', 'pointer-input', 'touch', 'pen', 'pointer-lock']}
    out['exports'] = {n: hasattr(lib, n) for n in [
        'rv_host_pointer', 'rv_host_touch', 'rv_host_pen', 'rv_host_pointer_lock_state', 'rv_host_pointer_lock_resolve',
        'rv_host_pointer_lock_lose', 'rv_element_request_pointer_lock', 'rv_document_exit_pointer_lock',
        'rv_dom_document_get_pointer_lock_element', 'rv_dom_shadow_root_get_pointer_lock_element',
        'rv_dom_touch_get_identifier', 'rv_dom_touch_event_get_changed_touches', 'rv_dom_touch_list_item',
        'rv_dom_pointer_event_get_tilt_x', 'rv_dom_mouse_event_get_movement_x', 'rv_dom_element_set_pointer_capture']}
    p.load(PAGE, standalone=False)
    mouse = p.bind('rv_host_mouse', I, [P, I, I, I, I, I, I])
    add = p.bind('rv_node_add_event_listener', P, [P, ctypes.c_char_p, I, CALLBACK, P])
    remove = p.bind('rv_listener_remove', I, [P])
    etype = p.bind('rv_event_type', I, [P, ctypes.c_char_p, I, ctypes.POINTER(I)])
    getters = {
        'pointerId': ('rv_dom_pointer_event_get_pointer_id', I), 'width': ('rv_dom_pointer_event_get_width', D),
        'height': ('rv_dom_pointer_event_get_height', D), 'pressure': ('rv_dom_pointer_event_get_pressure', F),
        'tangentialPressure': ('rv_dom_pointer_event_get_tangential_pressure', F),
        'tiltX': ('rv_dom_pointer_event_get_tilt_x', I), 'tiltY': ('rv_dom_pointer_event_get_tilt_y', I),
        'twist': ('rv_dom_pointer_event_get_twist', I), 'altitudeAngle': ('rv_dom_pointer_event_get_altitude_angle', D),
        'azimuthAngle': ('rv_dom_pointer_event_get_azimuth_angle', D), 'isPrimary': ('rv_dom_pointer_event_get_is_primary', I),
        'movementX': ('rv_dom_mouse_event_get_movement_x', D), 'movementY': ('rv_dom_mouse_event_get_movement_y', D)}
    bound = {k: (p.bind(n, I, [P, ctypes.POINTER(t)]), t) for k, (n, t) in getters.items()}
    pointer_type = p.bind('rv_dom_pointer_event_get_pointer_type', I, [P, ctypes.c_char_p, I, ctypes.POINTER(I)])
    max_touch = p.bind('rv_host_max_touch_points', I, [P, ctypes.POINTER(I)])
    lock_element = p.bind('rv_dom_shadow_root_get_pointer_lock_element', I, [P, ctypes.POINTER(P)])
    document = p.bind('rv_host_document', P, [P])(p.host)
    seen = []

    def text(fn, event):
        buffer, length = ctypes.create_string_buffer(64), I()
        status = fn(event, buffer, 64, ctypes.byref(length))
        return buffer.raw[:length.value].decode() if status == 0 else status

    def on_event(context, event):
        record = {'type': text(etype, event)}
        for k, (fn, t) in bound.items():
            v = t()
            status = fn(event, ctypes.byref(v))
            record[k] = v.value if status == 0 else ('status', status)
        record['pointerType'] = text(pointer_type, event)
        seen.append(record)
        return 0
    callback = CALLBACK(on_event)
    listeners = [add(document, e.encode(), 0, callback, None) for e in EVENTS]

    def run(name, *calls):
        seen.clear()
        out[name] = {'status': [mouse(p.host, *c) for c in calls], 'events': list(seen)}

    run('mouse_move_press_move_release', (0, 50, 50, -1, 0, 0), (1, 50, 50, 0, 1, 0), (0, 70, 65, 0, 0, 0), (2, 70, 65, 0, 1, 0))
    touch = I()
    out['maxTouchPoints'] = (max_touch(p.host, ctypes.byref(touch)), touch.value)
    shadow = p.bind('rv_element_attach_shadow', P, [P, I]) if hasattr(lib, 'rv_element_attach_shadow') else None
    out['shadow_pointer_lock_element_status_null_target'] = lock_element(None, ctypes.byref(P()))
    out['touch_events_seen'] = [e for e in out['mouse_move_press_move_release']['events'] if e['type'].startswith('touch')]
    for listener in listeners:
        remove(listener)
Path(sys.argv[2]).write_text(json.dumps(out, indent=1, default=str) + '\n', encoding='utf-8')
print(json.dumps({k: out[k] for k in ['abi', 'abi_has', 'exports', 'maxTouchPoints', 'shadow_pointer_lock_element_status_null_target']}, indent=1))
for e in out['mouse_move_press_move_release']['events']:
    print(json.dumps(e))
