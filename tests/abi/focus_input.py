"""Native26/ABI34 window event target, activation, modality, touch capacity and pointer capture probe."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8, bind as bind_utf8

OK, NULL_ARGUMENT, WRONG_THREAD, DOM_EXCEPTION = 0, -1, -2, -3
MOUSE_MOVE, MOUSE_DOWN, MOUSE_UP = 0, 1, 2
BUTTON_NONE, BUTTON_LEFT = -1, 0
KEY_DOWN, KEY_UP = 0, 1
LISTENER_CAPTURE = 1
CONSTRUCT_EVENT = 0
EVENT_POINTER = 3

PAGE = (b'<body style="margin:0">'
        b'<div id=a tabindex=0 style="width:100px;height:40px">a</div>'
        b'<div id=b tabindex=0 style="width:100px;height:40px">b</div>'
        b'<div id=c style="width:100px;height:100px">c</div></body>')


class EventInit(ctypes.Structure):
    _fields_ = [('size', ctypes.c_int32), ('bubbles', ctypes.c_int32), ('cancelable', ctypes.c_int32),
                ('composed', ctypes.c_int32), ('detail', ctypes.c_int32), ('modifiers', ctypes.c_int32),
                ('screenX', ctypes.c_double), ('screenY', ctypes.c_double), ('clientX', ctypes.c_double),
                ('clientY', ctypes.c_double), ('button', ctypes.c_int32), ('buttons', ctypes.c_int32),
                ('key', ctypes.c_char_p), ('code', ctypes.c_char_p), ('location', ctypes.c_int32),
                ('repeat', ctypes.c_int32), ('isComposing', ctypes.c_int32), ('relatedTarget', ctypes.c_void_p),
                ('customDetailJson', ctypes.c_char_p)]


def verify(directory, evidence):
    checks = 0
    teardown = []

    def expect(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(message)

    directory = Path(directory).resolve()
    before = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    if sys.platform == 'win32':
        os.add_dll_directory(str(directory))
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    library = ctypes.CDLL(str(directory / filename))
    i32, p, f64 = ctypes.c_int32, ctypes.c_void_p, ctypes.c_double
    callback_type = ctypes.CFUNCTYPE(i32, p, p)

    def bind(name, returns, arguments):
        return bind_utf8(library, name, returns, arguments)

    expect(bind('rv_abi_version', i32, [])() == 54, 'ABI version 54')
    expect(bind('rv_abi_has', i32, [ctypes.c_char_p])(b'input-state') == 1, 'input-state advertised')
    window_target = bind('rv_host_window_event_target', p, [p])
    max_touch_points = bind('rv_host_max_touch_points', i32, [p, ctypes.POINTER(i32)])
    host_create = bind('rv_host_create', p, [i32, i32])
    host_destroy = bind('rv_host_destroy', None, [p])
    load_html = bind('rv_host_load_html', i32, [p, ctypes.c_char_p])
    host_document = bind('rv_host_document', p, [p])
    query = bind('rv_node_query_selector', p, [p, ctypes.c_char_p, ctypes.POINTER(i32)])
    node_release = bind('rv_node_release', None, [p])
    mouse = bind('rv_host_mouse', i32, [p, i32, i32, i32, i32, i32, i32])
    key = bind('rv_host_key', i32, [p, i32, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, i32, i32])
    set_focused = bind('rv_host_set_focused', i32, [p, i32])
    has_focus = bind('rv_dom_document_has_focus', i32, [p, ctypes.POINTER(i32)])
    matches = bind('rv_dom_element_matches', i32, [p, Utf8, ctypes.POINTER(i32)])
    element_rect = bind('rv_element_rect', i32, [p, ctypes.POINTER(f64), ctypes.POINTER(f64), ctypes.POINTER(f64), ctypes.POINTER(f64)])
    focus_element = bind('rv_element_focus', i32, [p])
    set_capture = bind('rv_dom_element_set_pointer_capture', i32, [p, i32])
    has_capture = bind('rv_dom_element_has_pointer_capture', i32, [p, i32, ctypes.POINTER(i32)])
    target_release = bind('rv_event_target_release', None, [p])
    target_as_node = bind('rv_event_target_as_node', p, [p])
    node_as_target = bind('rv_node_as_event_target', p, [p])
    equals = bind('rv_event_target_equals', i32, [p, p])
    add_listener = bind('rv_event_target_add_listener', p, [p, ctypes.c_char_p, i32, callback_type, p])
    listener_remove = bind('rv_listener_remove', i32, [p])
    dispatch = bind('rv_event_target_dispatch', i32, [p, p, ctypes.POINTER(i32)])
    get_target = bind('rv_event_get_target', p, [p, i32])
    event_type = bind('rv_event_type', i32, [p, p, i32, ctypes.POINTER(i32)])
    interface = bind('rv_event_interface', i32, [p])
    pointer_id = bind('rv_dom_pointer_event_get_pointer_id', i32, [p, ctypes.POINTER(i32)])
    pointer_type = bind('rv_dom_pointer_event_get_pointer_type', i32, [p, p, i32, ctypes.POINTER(i32)])
    construct = bind('rv_host_construct_event', p, [p, i32, ctypes.c_char_p, ctypes.POINTER(EventInit)])
    event_release = bind('rv_event_release', None, [p])
    collect = bind('rv_collect_garbage', None, [])

    def text(getter, handle):
        buffer = ctypes.create_string_buffer(256)
        length = i32(0)
        expect(getter(handle, buffer, 256, ctypes.byref(length)) == OK, 'string read')
        return buffer.raw[:length.value].decode('utf-8')

    def selector(element, value):
        result = i32(-1)
        expect(matches(element, value, ctypes.byref(result)) == OK, f'matches {value!r}')
        return result.value == 1

    def focused(document):
        result = i32(-1)
        expect(has_focus(document, ctypes.byref(result)) == OK, 'hasFocus')
        return result.value == 1

    def centre(element):
        x, y, w, h = f64(), f64(), f64(), f64()
        expect(element_rect(element, ctypes.byref(x), ctypes.byref(y), ctypes.byref(w), ctypes.byref(h)) == OK, 'rect')
        return int(x.value + w.value / 2), int(y.value + h.value / 2)

    # Each listener records the type, whether currentTarget is the listening window, and pointer details.
    records = []
    windows = {}

    def on_event(context, event):
        current = get_target(event, 1)
        name = text(event_type, event)
        entry = {'type': name, 'window': context, 'currentIsWindow': bool(current) and equals(current, windows[context]) == 1}
        if current:
            target_release(current)
        if interface(event) == EVENT_POINTER:
            identifier = i32(-1)
            expect(pointer_id(event, ctypes.byref(identifier)) == OK, 'pointerId')
            entry['pointerId'] = identifier.value
            entry['pointerType'] = text(pointer_type, event)
        records.append(entry)
        return 0
    callback = callback_type(on_event)

    def drain():
        items = list(records)
        records.clear()
        return items

    def listen(window, context, types, flags):
        return [add_listener(window, name, flags, callback, context) for name in types]

    expect(window_target(None) is None, 'NULL host has no window')
    expect(max_touch_points(None, ctypes.byref(i32())) == NULL_ARGUMENT, 'NULL host touch points')

    host = host_create(320, 240)
    expect(bool(host), 'host')
    kept_window = None
    kept_listeners = []
    try:
        expect(load_html(host, PAGE) == OK, 'page load')
        expect(max_touch_points(host, None) == NULL_ARGUMENT, 'NULL touch-points result')
        touch = i32(-1)
        expect(max_touch_points(host, ctypes.byref(touch)) == OK and touch.value == 0, f'maxTouchPoints {touch.value}')

        # Identity: each call is a new reference to one window, which is not a node.
        window = window_target(host)
        again = window_target(host)
        expect(bool(window) and bool(again), 'window target')
        expect(equals(window, again) == 1, 'one window per document')
        expect(target_as_node(window) is None, 'window is not a node')
        document = host_document(host)
        document_target = node_as_target(document)
        expect(equals(window, document_target) == 0, 'window differs from document')
        target_release(document_target)
        target_release(again)
        windows[1] = window

        # Any event type reaches a window listener, with the window as currentTarget.
        custom_listener = add_listener(window, b'viewportchange', 0, callback, 1)
        init = EventInit(size=ctypes.sizeof(EventInit))
        custom = construct(host, CONSTRUCT_EVENT, b'viewportchange', ctypes.byref(init))
        prevented = i32(-1)
        expect(dispatch(window, custom, ctypes.byref(prevented)) == OK and prevented.value == 0, 'dispatch to window')
        expect(drain() == [{'type': 'viewportchange', 'window': 1, 'currentIsWindow': True}], 'custom window event')
        event_release(custom)
        expect(listener_remove(custom_listener) == OK, 'custom listener removed')

        # Activation: the host starts unfocused; each change fires one window event.
        listeners = listen(window, 1, [b'focus', b'blur'], 0)
        expect(not focused(document), 'host starts unfocused')
        expect(set_focused(host, 1) == OK and focused(document), 'focused host')
        observed = drain()
        expect(observed == [{'type': 'focus', 'window': 1, 'currentIsWindow': True}], f'window focus event {observed}')
        expect(set_focused(host, 0) == OK and not focused(document), 'unfocused host')
        expect(drain() == [{'type': 'blur', 'window': 1, 'currentIsWindow': True}], 'window blur event')
        expect(set_focused(host, 0) == OK and drain() == [], 'unchanged activation fires nothing')
        expect(set_focused(host, 1) == OK and drain()[0]['type'] == 'focus', 'refocused host')
        for listener in listeners:
            expect(listener_remove(listener) == OK, 'activation listener removed')

        # Modality: capture-phase input reaches the window before the target.
        listeners = listen(window, 1, [b'keydown', b'pointerdown', b'gotpointercapture', b'lostpointercapture'], LISTENER_CAPTURE)
        status = i32()
        a = query(document, b'#a', ctypes.byref(status))
        b = query(document, b'#b', ctypes.byref(status))
        c = query(document, b'#c', ctypes.byref(status))
        ax, ay = centre(a)
        mouse(host, MOUSE_MOVE, ax, ay, BUTTON_NONE, 0, 0)
        mouse(host, MOUSE_DOWN, ax, ay, BUTTON_LEFT, 1, 0)
        mouse(host, MOUSE_UP, ax, ay, BUTTON_LEFT, 1, 0)
        pointer = [r for r in drain() if r['type'] == 'pointerdown']
        expect(pointer == [{'type': 'pointerdown', 'window': 1, 'currentIsWindow': True, 'pointerId': 1, 'pointerType': 'mouse'}], f'pointerdown at window {pointer}')
        expect(selector(a, b':focus') and not selector(a, b':focus-visible'), 'click focus is not focus-visible')
        key(host, KEY_DOWN, b'Tab', b'Tab', None, 0, 0)
        key(host, KEY_UP, b'Tab', b'Tab', None, 0, 0)
        expect([r['type'] for r in drain()] == ['keydown'], 'keydown at window')
        expect(selector(b, b':focus') and selector(b, b':focus-visible'), 'Tab focus is focus-visible')
        expect(focus_element(a) == OK and selector(a, b':focus-visible'), 'script focus after keyboard is focus-visible')

        # Pointer capture: gained at the next pointer event during a press, lost on release.
        cx, cy = centre(c)
        mouse(host, MOUSE_MOVE, cx, cy, BUTTON_NONE, 0, 0)
        mouse(host, MOUSE_DOWN, cx, cy, BUTTON_LEFT, 1, 0)
        drain()
        expect(set_capture(c, 1) == OK, 'setPointerCapture')
        captured = i32(-1)
        expect(has_capture(c, 1, ctypes.byref(captured)) == OK and captured.value == 1, 'hasPointerCapture after set')
        expect(drain() == [], 'capture gain waits for the next pointer event')
        mouse(host, MOUSE_MOVE, 300, 230, BUTTON_LEFT, 0, 0)
        expect(drain() == [{'type': 'gotpointercapture', 'window': 1, 'currentIsWindow': True, 'pointerId': 1, 'pointerType': 'mouse'}], 'gotpointercapture')
        mouse(host, MOUSE_UP, 300, 230, BUTTON_LEFT, 1, 0)
        expect(drain() == [{'type': 'lostpointercapture', 'window': 1, 'currentIsWindow': True, 'pointerId': 1, 'pointerType': 'mouse'}], 'lostpointercapture')
        expect(has_capture(c, 1, ctypes.byref(captured)) == OK and captured.value == 0, 'capture released')
        expect(set_capture(c, 1) == OK and drain() == [], 'inactive pointer capture is a no-op')
        expect(set_capture(c, 7) == DOM_EXCEPTION, 'unknown pointer id is NotFoundError')
        for listener in listeners:
            expect(listener_remove(listener) == OK, 'input listener removed')
        for node in [a, b, c, document]:
            node_release(node)

        # Wrong thread.
        outcome = {}

        def off_thread():
            outcome['window'] = window_target(host)
            value = i32(-5)
            outcome['touch'] = (max_touch_points(host, ctypes.byref(value)), value.value)
        worker = threading.Thread(target=off_thread)
        worker.start()
        worker.join()
        expect(outcome == {'window': None, 'touch': (WRONG_THREAD, -5)}, f'wrong thread {outcome}')

        # Teardown: replacing the document keeps the window and its listeners.
        expect(load_html(host, PAGE) == OK, 'document replacement')
        replacement = window_target(host)
        windows[2] = replacement
        expect(equals(window, replacement) == 1, 'replacement keeps the window')
        drain()
        kept = listen(window, 1, [b'blur'], 0)
        expect(set_focused(host, 0) == OK and drain() == [{'type': 'blur', 'window': 1, 'currentIsWindow': True}], 'listener added before replacement still fires')
        for listener in kept:
            expect(listener_remove(listener) == OK, 'pre-replacement listener removed')
        new_listeners = listen(replacement, 2, [b'focus', b'blur'], 0)
        expect(set_focused(host, 1) == OK and drain() == [{'type': 'focus', 'window': 2, 'currentIsWindow': True}], 'replacement window listener')
        target_release(window)
        teardown.append({'case': 'document-replacement', 'window': 'kept by the host', 'listeners': 'kept, removed'})

        # Kept past destroy: the window reference and its listeners.
        kept_window = replacement
        kept_listeners = new_listeners + [add_listener(replacement, b'viewportchange', 0, callback, 2)]
    finally:
        host_destroy(host)
    collect()
    expect(drain() == [], 'destroy fires no window listener')
    removed = [listener_remove(listener) for listener in kept_listeners]
    expect(removed == [OK] * len(kept_listeners), f'listeners removed after destroy {removed}')
    target_release(kept_window)
    collect()
    teardown.append({'case': 'release-after-destroy', 'window': 'released after destroy', 'listeners': f'{len(kept_listeners)} removed after destroy'})

    # Release before destroy.
    host = host_create(320, 240)
    try:
        early = window_target(host)
        listener = add_listener(early, b'focus', 0, callback, 3)
        expect(listener_remove(listener) == OK, 'early listener removed')
        target_release(early)
    finally:
        host_destroy(host)
    teardown.append({'case': 'release-before-destroy', 'window': 'released', 'listener': 'removed'})

    after = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    expect(before == after, 'runtime unchanged')
    result = {'checks': checks, 'teardown': teardown, 'runtime': before}
    if evidence:
        Path(evidence).write_text(json.dumps(result, indent=2))
    print(f'PASS focus input: {checks} assertions; teardown {len(teardown)} cases', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence-json')
    options = parser.parse_args()
    verify(options.native_directory, options.evidence_json)
