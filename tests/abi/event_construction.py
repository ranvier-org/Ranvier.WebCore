"""Native24/ABI32 event construction and standalone EventTarget probe against an actual runtime directory."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import threading

OK, NULL_ARGUMENT, WRONG_THREAD, BUFFER_TOO_SMALL, UNSUPPORTED = 0, -1, -2, -6, -9
CONSTRUCT_EVENT, CONSTRUCT_CUSTOM, CONSTRUCT_UI, CONSTRUCT_MOUSE, CONSTRUCT_KEYBOARD, CONSTRUCT_FOCUS = range(6)
EVENT_EVENT, EVENT_UI, EVENT_MOUSE, EVENT_KEYBOARD, EVENT_FOCUS, EVENT_CUSTOM = 0, 1, 2, 4, 6, 8
SHIFT, CONTROL, ALT, META = 1, 2, 4, 8


class EventInit(ctypes.Structure):
    _fields_ = [('size', ctypes.c_int32), ('bubbles', ctypes.c_int32), ('cancelable', ctypes.c_int32),
                ('composed', ctypes.c_int32), ('detail', ctypes.c_int32), ('modifiers', ctypes.c_int32),
                ('screenX', ctypes.c_double), ('screenY', ctypes.c_double), ('clientX', ctypes.c_double),
                ('clientY', ctypes.c_double), ('button', ctypes.c_int32), ('buttons', ctypes.c_int32),
                ('key', ctypes.c_char_p), ('code', ctypes.c_char_p), ('location', ctypes.c_int32),
                ('repeat', ctypes.c_int32), ('isComposing', ctypes.c_int32), ('relatedTarget', ctypes.c_void_p),
                ('customDetailJson', ctypes.c_char_p)]


def init(**fields):
    value = EventInit()
    value.size = ctypes.sizeof(EventInit)
    for name, item in fields.items():
        setattr(value, name, item)
    return value


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
    i32, p = ctypes.c_int32, ctypes.c_void_p
    callback_type = ctypes.CFUNCTYPE(i32, p, p)

    def bind(name, returns, arguments):
        function = getattr(library, name)
        function.restype, function.argtypes = returns, arguments
        return function

    expect(bind('rv_abi_version', i32, [])() == 54, 'ABI version 54')
    has = bind('rv_abi_has', i32, [ctypes.c_char_p])
    expect(has(b'event-construction') == 1, 'event-construction advertised')
    host_create = bind('rv_host_create', p, [i32, i32])
    host_destroy = bind('rv_host_destroy', None, [p])
    construct = bind('rv_host_construct_event', p, [p, i32, ctypes.c_char_p, ctypes.POINTER(EventInit)])
    detail_json = bind('rv_custom_event_detail_json', i32, [p, p, i32, ctypes.POINTER(i32)])
    target_create = bind('rv_host_create_event_target', p, [p])
    target_retain = bind('rv_event_target_retain', p, [p])
    target_release = bind('rv_event_target_release', None, [p])
    node_as_target = bind('rv_node_as_event_target', p, [p])
    target_as_node = bind('rv_event_target_as_node', p, [p])
    equals = bind('rv_event_target_equals', i32, [p, p])
    add_listener = bind('rv_event_target_add_listener', p, [p, ctypes.c_char_p, i32, callback_type, p])
    listener_remove = bind('rv_listener_remove', i32, [p])
    dispatch = bind('rv_event_target_dispatch', i32, [p, p, ctypes.POINTER(i32)])
    node_dispatch = bind('rv_node_dispatch', i32, [p, p, ctypes.POINTER(i32)])
    get_target = bind('rv_event_get_target', p, [p, i32])
    get_related = bind('rv_event_get_related_target', p, [p])
    event_release = bind('rv_event_release', None, [p])
    event_retain = bind('rv_event_retain', p, [p])
    interface = bind('rv_event_interface', i32, [p])
    flags = bind('rv_event_flags', i32, [p])
    event_type = bind('rv_event_type', i32, [p, p, i32, ctypes.POINTER(i32)])
    event_key = bind('rv_event_key', i32, [p, p, i32, ctypes.POINTER(i32)])
    event_number = bind('rv_event_number', i32, [p, i32, ctypes.POINTER(ctypes.c_double)])
    event_string = bind('rv_event_string', i32, [p, i32, p, i32, ctypes.POINTER(i32)])
    composed = bind('rv_dom_event_get_composed', i32, [p, ctypes.POINTER(i32)])
    phase = bind('rv_dom_event_get_event_phase', i32, [p, ctypes.POINTER(ctypes.c_uint16)])
    screen_x = bind('rv_dom_mouse_event_get_screen_x', i32, [p, ctypes.POINTER(ctypes.c_double)])
    prevent = bind('rv_event_prevent_default', None, [p])
    stop_immediate = bind('rv_dom_event_stop_immediate_propagation', i32, [p])
    body = bind('rv_document_body', p, [p])
    node_release = bind('rv_node_release', None, [p])
    collect = bind('rv_collect_garbage', None, [])

    def text(getter, handle, *prefix):
        length = i32(-99)
        status = getter(handle, *prefix, None, 0, ctypes.byref(length))
        if status == UNSUPPORTED:
            return None
        expect(status in (OK, BUFFER_TOO_SMALL), 'string length query')
        if length.value < 0:
            return None
        buffer = ctypes.create_string_buffer(length.value + 1)
        buffer.raw = b'!' * len(buffer)
        expect(getter(handle, *prefix, buffer, length.value, ctypes.byref(length)) == OK, 'string copy')
        expect(buffer.raw[length.value] == ord('!'), 'exact-byte protocol writes no terminator')
        return buffer.raw[:length.value].decode('utf-8')

    def number(handle, which):
        value = ctypes.c_double(-12345)
        expect(event_number(handle, which, ctypes.byref(value)) == OK, f'number {which}')
        return value.value

    host = host_create(320, 240)
    expect(bool(host), 'host')
    try:
        # Construction through engine constructors.
        base = construct(host, CONSTRUCT_EVENT, b'plain', init(bubbles=1, cancelable=1, composed=1))
        expect(interface(base) == EVENT_EVENT and flags(base) & 3 == 3, 'Event bubbles and cancelable')
        value = i32(-1)
        expect(composed(base, ctypes.byref(value)) == OK and value.value == 1, 'composed from init')
        expect(text(event_type, base) == 'plain', 'type')
        expect(flags(base) & 16 == 0, 'constructed events are untrusted')
        ui = construct(host, CONSTRUCT_UI, b'ui', init(detail=7))
        expect(interface(ui) == EVENT_UI and number(ui, 5) == 7, 'UIEvent.detail')
        mouse = construct(host, CONSTRUCT_MOUSE, b'mouse', init(clientX=12.5, clientY=-3, screenX=40, button=2, buttons=5, modifiers=SHIFT | META, detail=2))
        expect(interface(mouse) == EVENT_MOUSE, 'MouseEvent kind')
        observed = (number(mouse, 0), number(mouse, 1), number(mouse, 2), number(mouse, 3), number(mouse, 4), number(mouse, 5))
        expect(observed == (12, -3, 2, 5, SHIFT | META, 2), f'MouseEventInit fields {observed}; the engine exposes clientX/clientY as integers')
        sx = ctypes.c_double(0)
        expect(screen_x(mouse, ctypes.byref(sx)) == OK and sx.value == 40, 'screenX')
        keyboard = construct(host, CONSTRUCT_KEYBOARD, b'keydown', init(key='ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©'.encode(), code=b'KeyE', location=1, repeat=1, isComposing=1, modifiers=CONTROL))
        expect(interface(keyboard) == EVENT_KEYBOARD, 'KeyboardEvent kind')
        expect(text(event_key, keyboard) == 'ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©' and text(event_string, keyboard, 0) == 'KeyE', 'key and code')
        expect(number(keyboard, 8) == 1 and number(keyboard, 9) == 1 and number(keyboard, 4) == CONTROL, 'location, repeat, modifiers')
        empty_key = construct(host, CONSTRUCT_KEYBOARD, b'keyup', init())
        expect(text(event_key, empty_key) == '', 'NULL key is empty')
        focus = construct(host, CONSTRUCT_FOCUS, b'focusin', init(bubbles=1))
        expect(interface(focus) == EVENT_FOCUS and flags(focus) & 1, 'FocusEvent kind')
        # Custom events carry a real engine detail.
        custom = construct(host, CONSTRUCT_CUSTOM, b'custom', init(cancelable=1, customDetailJson=json.dumps({'a': [1, 2.5, 'x', None, True], 'b': {}}).encode()))
        expect(interface(custom) == EVENT_CUSTOM, 'CustomEvent kind')
        collect()
        expect(json.loads(text(detail_json, custom)) == {'a': [1, 2.5, 'x', None, True], 'b': {}}, 'detail survives garbage collection')
        null_detail = construct(host, CONSTRUCT_CUSTOM, b'custom', init())
        expect(text(detail_json, null_detail) == 'null', 'NULL detail is null')
        length = i32(42)
        expect(detail_json(base, None, 0, ctypes.byref(length)) == UNSUPPORTED and length.value == 42, 'non-custom detail unsupported, length untouched')
        expect(detail_json(None, None, 0, ctypes.byref(length)) == NULL_ARGUMENT, 'null event')
        # Rejections return NULL.
        expect(not construct(host, CONSTRUCT_CUSTOM, b'custom', init(customDetailJson=b'{bad')), 'malformed JSON')
        expect(not construct(host, 99, b'x', init()), 'unknown kind')
        wrong = init()
        wrong.size = 8
        expect(not construct(host, CONSTRUCT_EVENT, b'x', ctypes.byref(wrong)), 'size mismatch')
        expect(not construct(host, CONSTRUCT_EVENT, b'\xff', init()), 'non-UTF-8 type')
        expect(not construct(host, CONSTRUCT_EVENT, None, init()), 'null type')
        expect(not construct(host, CONSTRUCT_EVENT, b'x', None), 'null init')
        off = []
        thread = threading.Thread(target=lambda: off.append(construct(host, CONSTRUCT_EVENT, b'x', init())))
        thread.start()
        thread.join()
        expect(off == [None], 'wrong thread returns NULL')

        # Standalone targets: listeners, dispatch order, cancellation, target and currentTarget.
        standalone = target_create(host)
        expect(bool(standalone) and not target_as_node(standalone), 'standalone target is not a node')
        calls = []

        def make(name, prevent_default=False, stop=False):
            def run(_context, event):
                current = get_target(event, 1)
                target = get_target(event, 0)
                ph = ctypes.c_uint16(0)
                phase(event, ctypes.byref(ph))
                calls.append((name, equals(current, standalone), equals(target, standalone), ph.value))
                target_release(current)
                target_release(target)
                if prevent_default:
                    prevent(event)
                if stop:
                    stop_immediate(event)
                return 0
            return callback_type(run)

        first, capture, third, fourth = make('first', prevent_default=True), make('capture'), make('third', stop=True), make('fourth')
        listeners = [add_listener(standalone, b'custom', 0, first, None), add_listener(standalone, b'custom', 1, capture, None),
                     add_listener(standalone, b'custom', 0, third, None), add_listener(standalone, b'custom', 0, fourth, None)]
        expect(all(listeners), 'listeners added')
        prevented = i32(-1)
        expect(dispatch(standalone, custom, ctypes.byref(prevented)) == OK, 'standalone dispatch')
        expect(calls == [('capture', 1, 1, 2), ('first', 1, 1, 2), ('third', 1, 1, 2)], f'capture first at target, then registration order, stopImmediatePropagation {calls}')
        expect(prevented.value == 1, 'cancelable custom event default prevented')
        after = get_target(custom, 0)
        expect(equals(after, standalone) == 1 and not get_target(custom, 1), 'target kept, currentTarget cleared after dispatch')
        target_release(after)
        expect(listener_remove(listeners[0]) == OK, 'remove listener')
        calls.clear()
        again = construct(host, CONSTRUCT_EVENT, b'custom', init())
        expect(dispatch(standalone, again, ctypes.byref(prevented)) == OK and prevented.value == 0, 'second dispatch')
        expect(calls == [('capture', 1, 1, 2), ('third', 1, 1, 2)], f'removed listener stays removed {calls}')
        for listener in listeners[1:]:
            expect(listener_remove(listener) == OK, 'remove listener')
        retained = target_retain(standalone)
        expect(equals(retained, standalone) == 1, 'retain returns the same target')
        target_release(retained)
        # Nodes through the EventTarget functions.
        body_node = body(host)
        body_target = node_as_target(body_node)
        round_trip = target_as_node(body_target)
        expect(round_trip == body_node, 'node round trip keeps identity')
        node_calls = []

        def on_body(_context, event):
            target = get_target(event, 0)
            node_calls.append(equals(target, body_target))
            target_release(target)
            return 0
        body_callback = callback_type(on_body)
        body_listener = add_listener(body_target, b'plain', 0, body_callback, None)
        expect(node_dispatch(body_node, base, ctypes.byref(prevented)) == OK and node_calls == [1], 'node listener through EventTarget API')
        expect(listener_remove(body_listener) == OK, 'remove node listener')
        # relatedTarget.
        related_mouse = construct(host, CONSTRUCT_MOUSE, b'mouseover', init(relatedTarget=standalone))
        related = get_related(related_mouse)
        expect(equals(related, standalone) == 1, 'mouse relatedTarget')
        target_release(related)
        related_focus = construct(host, CONSTRUCT_FOCUS, b'focusout', init(relatedTarget=body_target))
        related = get_related(related_focus)
        expect(equals(related, body_target) == 1, 'focus relatedTarget')
        target_release(related)
        expect(not get_related(base) and not get_related(keyboard), 'relatedTarget NULL for other kinds')
        for handle in [round_trip, body_node]:
            node_release(handle)
        target_release(body_target)
        for event in [base, ui, mouse, keyboard, empty_key, focus, null_detail, again, related_mouse, related_focus]:
            event_release(event)
        # Release before destroy.
        early_target = target_create(host)
        early_event = construct(host, CONSTRUCT_CUSTOM, b'early', init(customDetailJson=b'[1]'))
        early_listener = add_listener(early_target, b'early', 0, third, None)
        expect(listener_remove(early_listener) == OK, 'early listener removed')
        target_release(early_target)
        event_release(early_event)
        teardown.append({'case': 'release-before-destroy', 'target': 'released', 'event': 'released', 'listener': 'removed'})
        # Kept past destroy: the standalone target, its listener and the custom event.
        late_calls = []

        def on_late(_context, _event):
            late_calls.append(1)
            return 0
        late_callback = callback_type(on_late)
        late_listener = add_listener(standalone, b'late', 0, late_callback, None)
        retained_custom = event_retain(custom)
        event_release(custom)
        late_event = construct(host, CONSTRUCT_EVENT, b'late', init())
    finally:
        host_destroy(host)
    late_event_status = dispatch(standalone, late_event, ctypes.byref(prevented))
    expect(late_event_status == OK, 'dispatch on a standalone target after destroy')
    expect(late_calls == [1], 'listener runs after destroy')
    expect(dispatch(standalone, retained_custom, ctypes.byref(prevented)) == OK and late_calls == [1], 'other type does not reach the late listener')
    length = i32(-5)
    after_destroy = detail_json(retained_custom, None, 0, ctypes.byref(length))
    expect(after_destroy == UNSUPPORTED and length.value == -5, 'detail root dropped with the document')
    expect(listener_remove(late_listener) == OK, 'listener removed after destroy')
    target_release(standalone)
    event_release(retained_custom)
    event_release(late_event)
    collect()
    teardown.append({'case': 'release-after-destroy', 'target': 'released after destroy', 'event': 'released after destroy',
                     'listener': 'removed after destroy', 'dispatchAfterDestroy': late_event_status, 'detailAfterDestroy': after_destroy})
    after_hashes = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    expect(before == after_hashes, 'runtime unchanged')
    result = {'checks': checks, 'teardown': teardown, 'runtime': before}
    if evidence:
        Path(evidence).write_text(json.dumps(result, indent=2))
    print(f'PASS event construction: {checks} assertions; teardown {len(teardown)} cases', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence-json')
    options = parser.parse_args()
    verify(options.native_directory, options.evidence_json)
