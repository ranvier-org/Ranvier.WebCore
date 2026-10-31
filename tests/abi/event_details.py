"""Native39/ABI51 I08 event detail probe against an actual runtime directory: the constructors and getters of the event
detail interfaces, rv_dom_event_get_interface_name, engine-dispatched payloads and teardown, compared with the Chromium
oracle tests/fixtures/event-details-oracle.json. Every difference must be listed in tests/fixtures/event-details-qualified.json."""
import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8, StringInput, bind as bind_utf8, string_input

ABI = 54
OK, NULL_ARGUMENT, WRONG_THREAD, DOM_EXCEPTION, BUFFER_TOO_SMALL, UNSUPPORTED, WRONG_INTERFACE = 0, -1, -2, -3, -6, -9, -11
TRUSTED = 16
MOUSE_MOVE, MOUSE_DOWN, MOUSE_UP, BUTTON_LEFT, BUTTON_NONE = 0, 1, 2, 0, -1
KEY_DOWN, KEY_UP, KEY_CHAR = 0, 1, 2
ROOT = Path(__file__).resolve().parents[2]
i32, u32, f64, p, cstr = ctypes.c_int32, ctypes.c_uint32, ctypes.c_double, ctypes.c_void_p, ctypes.c_char_p


class EventInit(ctypes.Structure):
    _fields_ = [('size', i32), ('bubbles', i32), ('cancelable', i32), ('composed', i32), ('detail', i32), ('modifiers', i32),
                ('screenX', f64), ('screenY', f64), ('clientX', f64), ('clientY', f64), ('button', i32), ('buttons', i32),
                ('key', cstr), ('code', cstr), ('location', i32), ('repeat', i32), ('isComposing', i32), ('relatedTarget', p),
                ('customDetailJson', cstr)]


def construct_init():
    value = EventInit()
    value.size = ctypes.sizeof(EventInit)
    return ctypes.byref(value)


class Numberish(ctypes.Structure):
    _fields_ = [('present', i32), ('tag', i32), ('arm0', f64), ('arm1', p)]


def struct(name, fields):
    return type(name, (ctypes.Structure,), {'_fields_': [('size', u32), ('bubbles', i32), ('cancelable', i32), ('composed', i32), *fields]})


# The generated RvDom*EventInit layouts of host/RanvierWebCoreDom.h, by native prefix.
INITS = {
    'error_event': struct('ErrorEventInit', [('message', StringInput), ('filename', StringInput), ('lineno', u32), ('colno', u32)]),
    'progress_event': struct('ProgressEventInit', [('length_computable', i32), ('loaded', f64), ('total', f64)]),
    'css_animation_event': struct('AnimationEventInit', [('animation_name', StringInput), ('elapsed_time', f64), ('pseudo_element', StringInput)]),
    'css_transition_event': struct('TransitionEventInit', [('property_name', StringInput), ('elapsed_time', f64), ('pseudo_element', StringInput)]),
    'content_visibility_auto_state_change_event': struct('ContentVisibilityInit', [('skipped', i32)]),
    'animation_playback_event': struct('AnimationPlaybackEventInit', [('current_time', ctypes.POINTER(Numberish)), ('timeline_time', ctypes.POINTER(Numberish))]),
    'page_transition_event': struct('PageTransitionEventInit', [('persisted', i32)]),
    'hash_change_event': struct('HashChangeEventInit', [('old_url', StringInput), ('new_url', StringInput)]),
    'media_query_list_event': struct('MediaQueryListEventInit', [('media', StringInput), ('matches', i32)]),
    'pop_state_event': struct('PopStateEventInit', [('has_ua_visual_transition', i32)]),
    'composition_event': struct('CompositionEventInit', [('detail', i32), ('data', StringInput)]),
    'submit_event': struct('SubmitEventInit', [('submitter', p)]),
    'form_data_event': struct('FormDataEventInit', [('form_data', p)]),
    'toggle_event': struct('ToggleEventInit', [('old_state', StringInput), ('new_state', StringInput), ('source', p)]),
    'command_event': struct('CommandEventInit', [('source', p), ('command', StringInput)]),
}
# The IDL fields of each interface the dispatched scenario and the constructed cases read: native getter prefix, C type.
FIELDS = {
    'ErrorEvent': ('error_event', {'message': 'string', 'filename': 'string', 'lineno': 'uint32', 'colno': 'uint32'}),
    'ProgressEvent': ('progress_event', {'lengthComputable': 'bool', 'loaded': 'double', 'total': 'double'}),
    'AnimationEvent': ('css_animation_event', {'animationName': 'string', 'elapsedTime': 'double', 'pseudoElement': 'string'}),
    'TransitionEvent': ('css_transition_event', {'propertyName': 'string', 'elapsedTime': 'double', 'pseudoElement': 'string'}),
    'ContentVisibilityAutoStateChangeEvent': ('content_visibility_auto_state_change_event', {'skipped': 'bool'}),
    'AnimationPlaybackEvent': ('animation_playback_event', {'currentTime': 'numberish', 'timelineTime': 'numberish'}),
    'PageTransitionEvent': ('page_transition_event', {'persisted': 'bool'}),
    'HashChangeEvent': ('hash_change_event', {'oldURL': 'string', 'newURL': 'string'}),
    'MediaQueryListEvent': ('media_query_list_event', {'media': 'string', 'matches': 'bool'}),
    'PopStateEvent': ('pop_state_event', {'hasUAVisualTransition': 'bool'}),
    'CompositionEvent': ('composition_event', {'data': 'string', 'detail': 'int32'}),
    'ToggleEvent': ('toggle_event', {'oldState': 'string', 'newState': 'string'}),
    'PointerEvent': ('pointer_event', {'pointerType': 'string', 'isPrimary': 'bool', 'button': 'int16'}),
    'MouseEvent': ('mouse_event', {'button': 'int16', 'detail': 'int32'}),
    'WheelEvent': ('wheel_event', {'deltaMode': 'uint32'}),
    'KeyboardEvent': ('keyboard_event', {'key': 'string', 'code': 'string'}),
    'InputEvent': ('input_event', {'data': 'string', 'inputType': 'string'}),
    'FocusEvent': ('focus_event', {}),
}
# Getters declared on a base interface rather than the named one.
INHERITED = {'detail': 'ui_event', 'button': 'mouse_event'}


def snake(name):
    out = ''
    for index, char in enumerate(name):
        if char.isupper() and index and (not name[index - 1].isupper() or (index + 1 < len(name) and name[index + 1].islower())):
            out += '_'
        out += char.lower()
    return out


def verify(directory, oracle_path, qualified_path, evidence):
    checks = 0

    def expect(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(message)

    directory = Path(directory).resolve()
    before = {str(q.relative_to(directory)): hashlib.sha256(q.read_bytes()).hexdigest() for q in directory.rglob('*') if q.is_file()}
    if sys.platform == 'win32':
        os.add_dll_directory(str(directory))
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    library = ctypes.CDLL(str(directory / filename))
    callback_type = ctypes.CFUNCTYPE(i32, p, p)

    def bind(name, returns, arguments):
        return bind_utf8(library, name, returns, arguments)

    spec = json.loads((ROOT / 'tests/fixtures/event-details-cases.json').read_text(encoding='utf-8'))
    oracle = json.loads(Path(oracle_path).read_text(encoding='utf-8'))
    qualified = json.loads(Path(qualified_path).read_text(encoding='utf-8'))
    expect(bind('rv_abi_version', i32, [])() == ABI, f'ABI version {ABI}')
    has = bind('rv_abi_has', i32, [cstr])
    expect(has(b'dom-type-query:Event') == 1, 'dom-type-query:Event advertised')
    for case in spec['constructed']:
        source = 'CSS' + case['interface'] if case['interface'] in ('AnimationEvent', 'TransitionEvent') else case['interface']
        expect(has(f'dom:{source}'.encode()) == 1 and has(f'dom-constructor:{source}'.encode()) == 1, source + ' advertised')
    expect(has(b'dom:BeforeUnloadEvent') == 1, 'dom:BeforeUnloadEvent advertised')

    host_create = bind('rv_host_create', p, [i32, i32])
    host_destroy = bind('rv_host_destroy', None, [p])
    load_html = bind('rv_host_load_html', i32, [p, cstr])
    host_document = bind('rv_host_document', p, [p])
    update = bind('rv_host_update', i32, [p])
    cycle = bind('rv_run_loop_cycle', i32, [i32])
    resize = bind('rv_host_resize', i32, [p, i32, i32])
    mouse = bind('rv_host_mouse', i32, [p, i32, i32, i32, i32, i32, i32])
    wheel = bind('rv_host_wheel', i32, [p, i32, i32, ctypes.c_float, ctypes.c_float, i32])
    key = bind('rv_host_key', i32, [p, i32, cstr, cstr, cstr, i32, i32])
    set_focused = bind('rv_host_set_focused', i32, [p, i32])
    by_id = bind('rv_document_get_element_by_id', p, [p, cstr])
    set_attribute = bind('rv_element_set_attribute', i32, [p, cstr, cstr])
    get_attribute = bind('rv_element_get_attribute', i32, [p, cstr, cstr, i32, ctypes.POINTER(i32)])
    node_release = bind('rv_node_release', None, [p])
    node_string = bind('rv_node_get_string', i32, [p, i32, cstr, i32, ctypes.POINTER(i32)])
    window_target = bind('rv_host_window_event_target', p, [p])
    match_media = bind('rv_host_match_media', p, [p, cstr])
    add_listener = bind('rv_event_target_add_listener', p, [p, cstr, i32, callback_type, p])
    listener_remove = bind('rv_listener_remove', i32, [p])
    target_release = bind('rv_event_target_release', None, [p])
    target_as_node = bind('rv_event_target_as_node', p, [p])
    target_equals = bind('rv_event_target_equals', i32, [p, p])
    get_target = bind('rv_event_get_target', p, [p, i32])
    event_release = bind('rv_event_release', None, [p])
    event_flags = bind('rv_event_flags', i32, [p])
    construct = bind('rv_host_construct_event', p, [p, i32, cstr, p])
    last_exception = bind('rv_last_exception', i32, [i32, cstr, i32, ctypes.POINTER(i32)])
    interface_name = bind('rv_dom_event_get_interface_name', i32, [p, cstr, i32, ctypes.POINTER(i32)])
    numberish_release = bind('rv_dom_union_double_or_css_numeric_value_nullable_release', None, [ctypes.POINTER(Numberish)])
    dialog_show = bind('rv_dom_html_dialog_element_show', i32, [p])
    form_data_create = bind('rv_dom_dom_form_data_create', i32, [p, p, p, ctypes.POINTER(p)])
    form_data_release = bind('rv_dom_dom_form_data_release', None, [p])
    base_bool = {name: bind(f'rv_dom_event_get_{name}', i32, [p, ctypes.POINTER(i32)]) for name in ['bubbles', 'cancelable', 'composed', 'is_trusted']}
    base_type = bind('rv_dom_event_get_type', i32, [p, cstr, i32, ctypes.POINTER(i32)])
    creators = {prefix: bind(f'rv_dom_{prefix}_create', i32, [p, cstr, i32, ctypes.POINTER(INITS[prefix]), ctypes.POINTER(p)]) for prefix in INITS}

    def text(function, *head):
        buffer, length = ctypes.create_string_buffer(512), i32(-1)
        status = function(*head, buffer, 512, ctypes.byref(length))
        return status, buffer.raw[:max(length.value, 0)].decode('utf-8') if status == OK else None

    def name_of(event):
        status, value = text(interface_name, event)
        expect(status == OK, f'interface name status {status}')
        return value

    def exception_name():
        return text(last_exception, 0)[1]

    getters = {}

    def getter(prefix, field, kind):
        key_ = (prefix, field)
        if key_ not in getters:
            name = f'rv_dom_{INHERITED.get(field, prefix) if prefix in ("pointer_event", "mouse_event", "composition_event", "wheel_event") and field in INHERITED else prefix}_get_{snake(field)}'
            if kind == 'string':
                getters[key_] = (bind(name, i32, [p, cstr, i32, ctypes.POINTER(i32)]), kind)
            elif kind == 'numberish':
                getters[key_] = (bind(name, i32, [p, ctypes.POINTER(Numberish)]), kind)
            else:
                ctype = {'bool': i32, 'double': f64, 'uint32': u32, 'int32': i32, 'int16': ctypes.c_int16}[kind]
                getters[key_] = (bind(name, i32, [p, ctypes.POINTER(ctype)]), kind)
        return getters[key_]

    def read_field(event, prefix, field, kind):
        function, kind = getter(prefix, field, kind)
        if kind == 'string':
            status, value = text(function, event)
            expect(status == OK, f'{prefix}.{field} status {status}')
            return value
        if kind == 'numberish':
            value = Numberish()
            status = function(event, ctypes.byref(value))
            expect(status == OK, f'{prefix}.{field} status {status}')
            result = None if not value.present else (value.arm0 if value.tag == 1 else 'CSSNumericValue')
            numberish_release(ctypes.byref(value))
            return result
        ctype = {'bool': i32, 'double': f64, 'uint32': u32, 'int32': i32, 'int16': ctypes.c_int16}[kind]
        value = ctype(-7)
        status = function(event, ctypes.byref(value))
        expect(status == OK, f'{prefix}.{field} status {status}')
        return bool(value.value) if kind == 'bool' else value.value

    def base(event):
        values = {}
        for name, function in base_bool.items():
            value = i32(-7)
            expect(function(event, ctypes.byref(value)) == OK, 'Event.' + name)
            values[{'is_trusted': 'isTrusted'}.get(name, name)] = bool(value.value)
        return {'interface': name_of(event), 'type': text(base_type, event)[1], **values}

    def same(left, right):
        if isinstance(left, float) or isinstance(right, float):
            return isinstance(left, (int, float)) and isinstance(right, (int, float)) and not isinstance(left, bool) and math.isclose(left, right, abs_tol=1e-9)
        return left == right

    differences = []
    report = {'constructed': [], 'typeQuery': [], 'dispatched': [], 'teardown': []}

    def compare(scope, expected, actual):
        keys = sorted(set(expected) | set(actual))
        for name in keys:
            if not same(expected.get(name), actual.get(name)):
                differences.append({'scope': scope, 'field': name, 'chromium': expected.get(name), 'native': actual.get(name)})

    def init_for(prefix, case, full):
        value = INITS[prefix]()
        value.size = ctypes.sizeof(INITS[prefix])
        keep = []
        if full:
            value.bubbles = value.cancelable = value.composed = 1
            for field, item in case['init'].items():
                c_name = snake(field)
                if c_name in ('current_time', 'timeline_time'):
                    number = Numberish(1, 1, float(item), None)
                    keep.append(number)
                    setattr(value, c_name, ctypes.pointer(number))
                elif isinstance(item, str):
                    setattr(value, c_name, string_input(item))
                else:
                    setattr(value, c_name, item)
        return value, keep

    host = host_create(200, 200)
    expect(load_html(host, b'<!doctype html><html><body></body></html>') == OK, 'load')
    document = host_document(host)

    # Constructed events: IDL defaults (NULL init) and the full init dictionary.
    held = []
    for case, chromium in zip(spec['constructed'], oracle['constructed']):
        expect(case['interface'] == chromium['interface'], 'oracle order')
        prefix = case['native']
        type_bytes = case['type'].encode()
        for variant in ('defaults', 'full'):
            event = p()
            if variant == 'defaults':
                status = creators[prefix](document, type_bytes, len(type_bytes), None, ctypes.byref(event))
            else:
                init, keep = init_for(prefix, case, True)
                status = creators[prefix](document, type_bytes, len(type_bytes), ctypes.byref(init), ctypes.byref(event))
            expect(status == OK and event.value, f'{case["interface"]} {variant} constructor status {status}')
            actual = {**base(event), 'fields': {field: read_field(event, prefix, field, kind) for field, kind in case['fields'].items()}}
            expected = chromium[variant]
            compare(f'{case["interface"]} {variant}', {k: v for k, v in expected.items() if k != 'fields'}, {k: v for k, v in actual.items() if k != 'fields'})
            compare(f'{case["interface"]} {variant} fields', expected['fields'], actual['fields'])
            report['constructed'].append({'interface': case['interface'], 'variant': variant, 'native': actual})
            held.append(event)
        for attribute in chromium['engineOnlyAttributes']:
            differences.append({'scope': f'{case["interface"]} attributes', 'field': attribute, 'chromium': 'present', 'native': 'absent'})
    # A getter of another interface reports the wrong interface; NULL arguments are rejected.
    plain = construct(host, 0, b'x', construct_init())
    expect(plain, 'plain Event')
    for prefix, fields in [(FIELDS[name][0], FIELDS[name][1]) for name in ['ErrorEvent', 'ProgressEvent', 'AnimationEvent', 'MediaQueryListEvent']]:
        field, kind = next(iter(fields.items()))
        function, kind = getter(prefix, field, kind)
        if kind == 'string':
            expect(text(function, plain)[0] == WRONG_INTERFACE, f'{prefix} on Event')
            expect(function(None, None, 0, None) == NULL_ARGUMENT, f'{prefix} NULL')
        else:
            value = (f64 if kind == 'double' else i32)(-7)
            expect(function(plain, ctypes.byref(value)) == WRONG_INTERFACE and value.value == -7, f'{prefix} on Event')
    value = Numberish()
    expect(getter('animation_playback_event', 'currentTime', 'numberish')[0](plain, ctypes.byref(value)) == WRONG_INTERFACE, 'numberish on Event')
    expect(creators['error_event'](document, b'x', 1, None, None) == NULL_ARGUMENT, 'constructor NULL result')
    expect(name_of(plain) == 'Event', 'plain Event name')
    expect(interface_name(None, None, 0, ctypes.byref(i32())) == NULL_ARGUMENT, 'interface name NULL')
    small, length = ctypes.create_string_buffer(2), i32(-1)
    expect(interface_name(held[0], small, 2, ctypes.byref(length)) == BUFFER_TOO_SMALL and length.value == len('ErrorEvent'), 'interface name capacity')
    errors = []
    worker = threading.Thread(target=lambda: errors.append(interface_name(plain, small, 2, ctypes.byref(i32()))))
    worker.start()
    worker.join()
    expect(errors == [WRONG_THREAD], 'interface name off thread')
    # BeforeUnloadEvent has no constructor; Document.createEvent makes one.
    create_event = bind('rv_dom_document_create_event', i32, [p, Utf8, ctypes.POINTER(p)])
    unload = p()
    expect(create_event(document, b'BeforeUnloadEvent', ctypes.byref(unload)) == OK and unload.value, 'createEvent BeforeUnloadEvent')
    expect(name_of(unload) == 'BeforeUnloadEvent', 'BeforeUnloadEvent name')
    set_return = bind('rv_dom_before_unload_event_set_return_value', i32, [p, Utf8])
    get_return = bind('rv_dom_before_unload_event_get_return_value', i32, [p, cstr, i32, ctypes.POINTER(i32)])
    expect(text(get_return, unload) == (OK, ''), 'returnValue default')
    expect(set_return(unload, b'stay') == OK and text(get_return, unload) == (OK, 'stay'), 'returnValue set')
    report['constructed'].append({'interface': 'BeforeUnloadEvent', 'variant': 'createEvent', 'native': {'returnValue': 'stay'}})
    held += [plain, unload]

    # Interface names of the I02, D13, D14 and D16 events.
    for case, chromium in zip(spec['typeQuery'], oracle['typeQuery']):
        expect(case['interface'] == chromium['interface'], 'type query order')
        event = p()
        keep = None
        if case['construct'] == 'rv':
            event = p(construct(host, case['kind'], b'x', construct_init()))
        elif case['native'] == 'form_data_event':
            keep = p()
            expect(form_data_create(document, None, None, ctypes.byref(keep)) == OK, 'FormData')
            init = INITS['form_data_event'](ctypes.sizeof(INITS['form_data_event']), 0, 0, 0, keep)
            expect(creators['form_data_event'](document, b'x', 1, ctypes.byref(init), ctypes.byref(event)) == OK, 'FormDataEvent')
        else:
            expect(creators[case['native']](document, b'x', 1, None, ctypes.byref(event)) == OK, case['interface'])
        name = name_of(event)
        report['typeQuery'].append({'interface': case['interface'], 'name': name})
        compare(f'type query {case["interface"]}', {'name': chromium['name']}, {'name': name})
        event_release(event)
        if keep:
            form_data_release(keep)
    host_destroy(host)
    # Teardown: events constructed before destroy stay readable, constructors on the destroyed host's document fail.
    teardown = {}
    status, message = text(getter('error_event', 'message', 'string')[0], held[1])
    teardown['ErrorEvent.message after destroy'] = message
    expect(status == OK and message == 'boom', 'ErrorEvent readable after destroy')
    expect(name_of(held[1]) == 'ErrorEvent', 'interface name after destroy')
    for prefix in ['error_event', 'pop_state_event']:
        event = p(12345)
        status = creators[prefix](document, b'x', 1, None, ctypes.byref(event))
        teardown[f'{prefix} on a destroyed host document'] = [status, exception_name(), event.value]
        expect(status == DOM_EXCEPTION and exception_name() == 'InvalidStateError' and event.value == 12345, f'{prefix} detached document')
    event = p()
    status = creators['progress_event'](document, b'x', 1, None, ctypes.byref(event))
    teardown['progress_event on a destroyed host document'] = status
    expect(status == OK and event.value, 'ProgressEvent needs no browsing context')
    held.append(event)
    for item in held:
        event_release(item)
    node_release(document)
    report['teardown'].append(teardown)

    # Engine-dispatched payloads.
    scenario = spec['dispatched']
    host = host_create(*scenario['viewport'])
    set_focused(host, 1)
    events = []
    window = window_target(host)
    media_step = next(step for step in scenario['steps'] if step['op'] == 'resize')
    media = None

    def label(event):
        target = get_target(event, 0)
        if not target:
            return None
        try:
            if target_equals(target, window):
                return 'window'
            if media and target_equals(target, media):
                return 'media'
            node = target_as_node(target)
            if not node:
                return 'other'
            status, value = text(get_attribute, node, b'id')
            if status != OK or not value:
                status, value = text(node_string, node, 0)
            node_release(node)
            return value
        finally:
            target_release(target)

    @callback_type
    def record(context, event):
        name = name_of(event)
        entry = {'type': text(base_type, event)[1], 'interface': name, 'trusted': bool(event_flags(event) & TRUSTED), 'target': label(event)}
        prefix, fields = FIELDS.get(name, (None, {}))
        for field in scenario['fields'].get(name, []):
            entry[field] = read_field(event, prefix, field, fields[field])
        events.append(entry)
        return 0

    listeners = [add_listener(window, kind.encode(), 1, record, None) for kind in scenario['types']]
    expect(all(listeners), 'listeners')

    def drain(until, start):
        deadline = time.monotonic() + 10
        while not all(any(e['type'] == kind for e in events[start:]) for kind in until):
            # A hang guard, not an assertion: the number of cycles depends on timing.
            if time.monotonic() > deadline:
                raise AssertionError(f'events {until} not dispatched within 10 s')
            update(host)
            cycle(16)
        update(host)
        cycle(0)

    def element(id_):
        node = by_id(host, id_.encode())
        expect(node, 'element ' + id_)
        return node

    for step, chromium in zip(scenario['steps'], oracle['dispatched']):
        start = len(events)
        op = step['op']
        if op == 'load':
            expect(load_html(host, scenario['markup'].encode()) == OK, 'load markup')
            # A media query list belongs to the document it was matched in.
            media = match_media(host, media_step['media'].encode())
            listeners.append(add_listener(media, b'change', 0, record, None))
            expect(media and listeners[-1], 'media query listener')
        elif op == 'class':
            node = element(step['id'])
            expect(set_attribute(node, b'class', step['value'].encode()) == OK, 'class')
            node_release(node)
        elif op == 'resize':
            expect(resize(host, step['width'], step['height']) == OK, 'resize')
        elif op == 'dialogShow':
            node = element(step['id'])
            expect(dialog_show(node) == OK, 'dialog show')
            node_release(node)
        elif op == 'click':
            update(host)
            mouse(host, MOUSE_MOVE, step['x'], step['y'], BUTTON_NONE, 0, 0)
            mouse(host, MOUSE_DOWN, step['x'], step['y'], BUTTON_LEFT, 1, 0)
            mouse(host, MOUSE_UP, step['x'], step['y'], BUTTON_LEFT, 1, 0)
        elif op == 'wheel':
            update(host)
            mouse(host, MOUSE_MOVE, step['x'], step['y'], BUTTON_NONE, 0, 0)
            wheel(host, step['x'], step['y'], 0.0, float(step['deltaY']), 0)
        elif op == 'focusAndType':
            update(host)
            mouse(host, MOUSE_MOVE, step['x'], step['y'], BUTTON_NONE, 0, 0)
            mouse(host, MOUSE_DOWN, step['x'], step['y'], BUTTON_LEFT, 1, 0)
            mouse(host, MOUSE_UP, step['x'], step['y'], BUTTON_LEFT, 1, 0)
            key(host, KEY_DOWN, step['key'].encode(), step['code'].encode(), None, 0, 0)
            key(host, KEY_CHAR, step['key'].encode(), step['code'].encode(), step['key'].encode(), 0, 0)
            key(host, KEY_UP, step['key'].encode(), step['code'].encode(), None, 0, 0)
        drain(step.get('until', []), start)
        native = events[start:]
        expected = chromium['events']
        dedupe = lambda items: [item for index, item in enumerate(items) if index == 0 or item != items[index - 1]]
        if step.get('order') == 'set':
            # Numbers compare by value: Chromium serializes 0 where the native getter reads 0.0.
            key_ = lambda item: json.dumps({k: float(v) if isinstance(v, int) and not isinstance(v, bool) else v for k, v in item.items()}, sort_keys=True)
            native_view, expected_view = sorted(map(key_, native)), sorted(map(key_, expected))
            for item in sorted(set(expected_view) ^ set(native_view)):
                differences.append({'scope': f'{step["name"]} events', 'field': 'event', 'chromium': json.loads(item) if item in expected_view else None,
                                    'native': json.loads(item) if item in native_view else None})
        else:
            native_view, expected_view = dedupe(native), dedupe(expected)
            if native_view != expected_view:
                differences.append({'scope': f'{step["name"]} events', 'field': 'sequence', 'chromium': expected_view, 'native': native_view})
        report['dispatched'].append({'name': step['name'], 'events': native})
    for listener in listeners:
        expect(listener_remove(listener) == OK, 'listener remove')
    host_destroy(host)
    target_release(media)
    target_release(window)

    # Every difference is qualified, and every qualification is still measured.
    canonical = lambda item: json.dumps(item, sort_keys=True)
    measured = sorted(map(canonical, differences))
    listed = sorted(canonical({k: v for k, v in item.items() if k != 'reason'}) for item in qualified['differences'])
    unexpected = sorted(set(measured) - set(listed))
    stale = sorted(set(listed) - set(measured))
    expect(all(item.get('reason') for item in qualified['differences']), 'each qualification has a reason')
    after = {str(q.relative_to(directory)): hashlib.sha256(q.read_bytes()).hexdigest() for q in directory.rglob('*') if q.is_file()}
    expect(before == after, 'runtime directory unchanged')
    report.update({'browser': oracle['browser'], 'differences': differences, 'unexpected': [json.loads(x) for x in unexpected],
                   'stale': [json.loads(x) for x in stale]})
    if evidence:
        Path(evidence).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    expect(not unexpected, 'unqualified differences: ' + json.dumps([json.loads(x) for x in unexpected])[:4000])
    expect(not stale, 'qualifications no longer measured: ' + json.dumps([json.loads(x) for x in stale])[:2000])
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--oracle', default=str(ROOT / 'tests/fixtures/event-details-oracle.json'))
    parser.add_argument('--qualified', default=str(ROOT / 'tests/fixtures/event-details-qualified.json'))
    parser.add_argument('--evidence')
    args = parser.parse_args()
    checks = verify(args.native_directory, args.oracle, args.qualified, args.evidence)
    print(f'event_details: {checks} assertions')


if __name__ == '__main__':
    main()
