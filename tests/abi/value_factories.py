"""D17 value-factory probe against an actual runtime directory: the generated constructors of Text, Comment,
DocumentFragment, Range, StaticRange, Document, InputEvent, WheelEvent and PointerEvent, and the static factories
Document.parseHTMLUnsafe and DOMMatrix(ReadOnly).fromFloat32Array/fromFloat64Array. Factory defaults, mutability,
dispatch outcomes and receiver checks are compared with the Chromium oracle tests/fixtures/value-factories-oracle.json;
every difference must be listed in tests/fixtures/value-factories-qualified.json."""
import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8, StringInput, bind as bind_utf8, string_input

ABI = 54
OK, NULL_ARGUMENT, WRONG_THREAD, DOM_EXCEPTION, BUFFER_TOO_SMALL, UNSUPPORTED, WRONG_INTERFACE = 0, -1, -2, -3, -6, -9, -11
ROOT = Path(__file__).resolve().parents[2]
i16, u16, i32, u32, f32, f64, p, cstr = (ctypes.c_int16, ctypes.c_uint16, ctypes.c_int32, ctypes.c_uint32, ctypes.c_float,
                                         ctypes.c_double, ctypes.c_void_p, ctypes.c_char_p)
FEATURES = ['dom-constructor:Text', 'dom-constructor:Comment', 'dom-constructor:DocumentFragment', 'dom-constructor:Range',
            'dom-constructor:StaticRange', 'dom-constructor:Document', 'dom-constructor:InputEvent', 'dom-constructor:WheelEvent',
            'dom-constructor:PointerEvent', 'dom-document-parse-html', 'dom-geometry-matrix', 'dom-geometry-matrix-readonly']


class Sequence(ctypes.Structure):
    """RvDomSequencePointerEvent and RvDomSequenceStaticRange."""
    _fields_ = [('present', i32), ('count', i32), ('items', ctypes.POINTER(p))]


class StaticRangeInit(ctypes.Structure):
    _fields_ = [('size', u32), ('start_container', p), ('start_offset', u32), ('end_container', p), ('end_offset', u32)]


EVENT = [('size', u32), ('bubbles', i32), ('cancelable', i32), ('composed', i32), ('detail', i32)]
MOUSE = EVENT + [('ctrl_key', i32), ('shift_key', i32), ('alt_key', i32), ('meta_key', i32), ('modifier_alt_graph', i32),
                 ('modifier_caps_lock', i32), ('screen_x', f64), ('screen_y', f64), ('client_x', f64), ('client_y', f64),
                 ('button', i16), ('buttons', u16), ('related_target', p), ('movement_x', f64), ('movement_y', f64)]


class InputEventInit(ctypes.Structure):
    _fields_ = EVENT + [('data', StringInput), ('is_composing', i32), ('input_type', StringInput)]


class WheelEventInit(ctypes.Structure):
    _fields_ = MOUSE + [('delta_x', f64), ('delta_y', f64), ('delta_z', f64), ('delta_mode', u32), ('wheel_delta_x', i32),
                        ('wheel_delta_y', i32)]


class PointerEventInit(ctypes.Structure):
    _fields_ = MOUSE + [('pointer_id', i32), ('width', f64), ('height', f64), ('pressure', f32), ('tangential_pressure', f32),
                        ('tilt_x', ctypes.POINTER(i32)), ('tilt_y', ctypes.POINTER(i32)), ('twist', i32),
                        ('pointer_type', StringInput), ('is_primary', i32), ('coalesced_events', ctypes.POINTER(Sequence)),
                        ('predicted_events', ctypes.POINTER(Sequence))]


def number(value):
    return value if math.isfinite(value) else ('NaN' if math.isnan(value) else ('Infinity' if value > 0 else '-Infinity'))


def same(left, right):
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(left, right, rel_tol=0, abs_tol=1e-12)
    return left == right


def verify(directory, oracle_path, qualified_path, evidence):
    checks = 0

    def expect(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(message)

    directory = Path(directory).resolve()
    before = {str(item.relative_to(directory)): hashlib.sha256(item.read_bytes()).hexdigest() for item in directory.rglob('*') if item.is_file()}
    if sys.platform == 'win32':
        os.add_dll_directory(str(directory))
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    library = ctypes.CDLL(str(directory / filename))
    oracle = json.loads(Path(oracle_path).read_text(encoding='utf-8'))
    qualified = json.loads(Path(qualified_path).read_text(encoding='utf-8'))

    def bind(name, returns, arguments):
        function = getattr(library, name)
        function.restype, function.argtypes = returns, arguments
        return function

    def utf8(name, returns, arguments):
        return bind_utf8(library, name, returns, arguments)

    expect(bind('rv_abi_version', i32, [])() == ABI, f'ABI version {ABI}')
    has = bind('rv_abi_has', i32, [cstr])
    for feature in FEATURES:
        expect(has(feature.encode()) == 1, feature + ' advertised')
    host_create = bind('rv_host_create', p, [i32, i32])
    host_destroy = bind('rv_host_destroy', None, [p])
    load_html_bytes = bind('rv_host_load_html', i32, [p, cstr, i32])  # utf8 bytes and length (#145)

    def load_html(host, html):
        return load_html_bytes(host, html, len(html))

    host_document = bind('rv_host_document', p, [p])
    node_release = bind('rv_node_release', None, [p])
    event_release = bind('rv_event_release', None, [p])
    range_release = bind('rv_dom_abstract_range_release', None, [p])
    matrix_release = bind('rv_dom_dom_matrix_read_only_release', None, [p])
    sequence_pointer_release = bind('rv_dom_sequence_pointer_event_release', None, [ctypes.POINTER(Sequence)])
    sequence_range_release = bind('rv_dom_sequence_static_range_release', None, [ctypes.POINTER(Sequence)])
    last_exception = bind('rv_last_exception', i32, [i32, cstr, i32, ctypes.POINTER(i32)])
    node_as_target = bind('rv_node_as_event_target', p, [p])
    target_release = bind('rv_event_target_release', None, [p])
    callback_type = ctypes.CFUNCTYPE(i32, p, p)
    add_listener_bytes = bind('rv_event_target_add_listener', p, [p, cstr, i32, i32, callback_type, p])  # utf8 bytes and length (#145)

    def add_listener(target, event_type, flags, callback, context):
        return add_listener_bytes(target, event_type, len(event_type), flags, callback, context)

    listener_remove = bind('rv_listener_remove', i32, [p])
    node_dispatch = bind('rv_node_dispatch', i32, [p, p, ctypes.POINTER(i32)])
    prevent_default = bind('rv_event_prevent_default', None, [p])
    event_target = bind('rv_event_get_target', p, [p, i32])
    target_as_node = bind('rv_event_target_as_node', p, [p])

    create = {
        'text': utf8('rv_dom_text_create', i32, [p, Utf8, ctypes.POINTER(p)]),
        'comment': utf8('rv_dom_comment_create', i32, [p, Utf8, ctypes.POINTER(p)]),
        'fragment': bind('rv_dom_document_fragment_create', i32, [p, ctypes.POINTER(p)]),
        'range': bind('rv_dom_range_create', i32, [p, ctypes.POINTER(p)]),
        'document': bind('rv_dom_document_create', i32, [p, ctypes.POINTER(p)]),
        'parse': utf8('rv_dom_document_parse_html_unsafe', i32, [p, Utf8, ctypes.POINTER(p)]),
        'static': bind('rv_dom_static_range_create', i32, [p, ctypes.POINTER(StaticRangeInit), ctypes.POINTER(p)]),
        'input': utf8('rv_dom_input_event_create', i32, [p, Utf8, ctypes.POINTER(InputEventInit), ctypes.POINTER(p)]),
        'wheel': utf8('rv_dom_wheel_event_create', i32, [p, Utf8, ctypes.POINTER(WheelEventInit), ctypes.POINTER(p)]),
        'pointer': utf8('rv_dom_pointer_event_create', i32, [p, Utf8, ctypes.POINTER(PointerEventInit), ctypes.POINTER(p)]),
    }
    matrices = {(readonly, bits): bind(f'rv_dom_dom_matrix{"_read_only" if readonly else ""}_from_float{bits}_array', i32,
                                        [p, ctypes.POINTER(f32 if bits == 32 else f64), i32, ctypes.POINTER(p)])
                for readonly in (False, True) for bits in (32, 64)}

    def text(function, *head):
        length = i32(-7)
        status = function(*head, None, 0, ctypes.byref(length))
        if status == OK and length.value == -1:
            return None
        if status == OK and length.value == 0:
            return ''
        expect(status == BUFFER_TOO_SMALL, f'string length query status {status}')
        buffer = ctypes.create_string_buffer(length.value + 1)
        buffer.raw = b'!' * len(buffer)
        expect(function(*head, buffer, length.value, ctypes.byref(length)) == OK, 'string copy')
        expect(buffer.raw[length.value] == ord('!'), 'exact-byte protocol writes no terminator')
        return buffer.raw[:length.value].decode('utf-8')

    getters = {}

    def get(name, handle, kind):
        """A generated getter's value; kind is a ctypes type, 'string', 'node' or 'bool'."""
        if name not in getters:
            arguments = {'string': [p, cstr, i32, ctypes.POINTER(i32)], 'node': [p, ctypes.POINTER(p)],
                         'bool': [p, ctypes.POINTER(i32)]}.get(kind) or [p, ctypes.POINTER(kind)]
            getters[name] = bind('rv_dom_' + name, i32, arguments)
        function = getters[name]
        if kind == 'string':
            return text(function, handle)
        if kind == 'node':
            value = p()
            expect(function(handle, ctypes.byref(value)) == OK, name)
            return value.value
        value = (i32 if kind == 'bool' else kind)(-7)
        expect(function(handle, ctypes.byref(value)) == OK, name)
        return bool(value.value) if kind == 'bool' else value.value

    def is_node(name, handle, other):
        """Whether the node-valued getter returns other; the reference it returns is released."""
        value = get(name, handle, 'node')
        try:
            return value == other
        finally:
            if value:
                node_release(value)

    def exception_name():
        return text(last_exception, 0)

    def made(function, *arguments):
        result = p()
        status = function(*arguments, ctypes.byref(result))
        expect(status == OK and result.value, f'factory status {status}')
        return result.value

    values = {}
    owned = []
    hosts = []
    host = host_create(320, 240)
    expect(bool(host), 'host')
    hosts.append(host)
    expect(load_html(host, b'<!doctype html><html><body><p id="p">hello</p></body></html>') == OK, 'load')
    document = host_document(host)
    body = get('document_get_body', document, 'node')
    paragraph = get('node_get_first_child', body, 'node')
    t0 = get('node_get_first_child', paragraph, 'node')
    owned += [body, paragraph, t0]
    expect(get('element_get_tag_name', paragraph, 'string') == 'P', 'paragraph')

    def node_shape(handle):
        return [get('node_get_node_type', handle, u16)]

    # Text and Comment.
    t = made(create['text'], document, '')
    values['text.default'] = [get('node_get_node_type', t, u16), get('character_data_get_data', t, 'string'),
                              is_node('node_get_owner_document', t, document), get('node_get_is_connected', t, 'bool'),
                              get('node_get_parent_node', t, 'node') is None]
    node_release(t)
    t = made(create['text'], document, 'héllo \U0001F600')
    values['text.data'] = get('character_data_get_data', t, 'string')
    set_data = utf8('rv_dom_character_data_set_data', i32, [p, Utf8])
    expect(set_data(t, 'changed') == OK, 'Text.data setter')
    values['text.mutated'] = get('character_data_get_data', t, 'string')
    node_release(t)
    c = made(create['comment'], document, 'note')
    values['comment'] = [get('node_get_node_type', c, u16), get('character_data_get_data', c, 'string'),
                         is_node('node_get_owner_document', c, document), get('node_get_is_connected', c, 'bool')]
    node_release(c)
    c = made(create['comment'], document, '')
    values['comment.default'] = get('character_data_get_data', c, 'string')
    node_release(c)
    expect(create['text'](document, None, ctypes.byref(p())) == NULL_ARGUMENT, 'a null Text data is rejected')

    # DocumentFragment.
    append_child = bind('rv_dom_node_append_child', i32, [p, p, ctypes.POINTER(p)])
    child_nodes = bind('rv_dom_node_get_child_nodes', i32, [p, ctypes.POINTER(p)])
    list_length = bind('rv_dom_node_list_get_length', i32, [p, ctypes.POINTER(u32)])
    list_release = bind('rv_dom_node_list_release', None, [p])

    def child_count(node):
        nodes = p()
        expect(child_nodes(node, ctypes.byref(nodes)) == OK, 'childNodes')
        count = u32(0)
        expect(list_length(nodes, ctypes.byref(count)) == OK, 'NodeList.length')
        list_release(nodes)
        return count.value

    def append(parent, child):
        result = p()
        expect(append_child(parent, child, ctypes.byref(result)) == OK, 'appendChild')
        node_release(result.value)

    f = made(create['fragment'], document)
    values['fragment'] = [get('node_get_node_type', f, u16), child_count(f), is_node('node_get_owner_document', f, document),
                          get('node_get_is_connected', f, 'bool')]
    x = made(create['text'], document, 'x')
    append(f, x)
    first = get('node_get_first_child', f, 'node')
    values['fragment.appended'] = [child_count(f), get('character_data_get_data', first, 'string')]
    node_release(first)
    node_release(x)
    node_release(f)

    # Range.
    rg = made(create['range'], document)
    values['range.default'] = [is_node('abstract_range_get_start_container', rg, document), get('abstract_range_get_start_offset', rg, u32),
                               is_node('abstract_range_get_end_container', rg, document), get('abstract_range_get_end_offset', rg, u32),
                               get('abstract_range_get_collapsed', rg, 'bool')]
    set_start = bind('rv_dom_range_set_start', i32, [p, p, u32])
    set_end = bind('rv_dom_range_set_end', i32, [p, p, u32])
    expect(set_start(rg, t0, 1) == OK and set_end(rg, t0, 3) == OK, 'Range.setStart/setEnd')
    values['range.set'] = [is_node('abstract_range_get_start_container', rg, t0), get('abstract_range_get_start_offset', rg, u32),
                           get('abstract_range_get_end_offset', rg, u32), get('abstract_range_get_collapsed', rg, 'bool')]
    status = set_end(rg, t0, 9)
    values['range.outOfBounds'] = exception_name() if status == DOM_EXCEPTION else None
    range_release(rg)

    # Document.
    d = made(create['document'], document)
    values['document'] = [get('node_get_node_type', d, u16), get('document_get_content_type', d, 'string'),
                          get('document_get_character_set', d, 'string'), get('document_get_compat_mode', d, 'string'),
                          child_count(d), get('document_get_document_element', d, 'node') is None, d == document]
    create_element = utf8('rv_dom_document_create_element', i32, [p, Utf8, p, ctypes.POINTER(p)])
    root = p()
    expect(create_element(d, 'root', None, ctypes.byref(root)) == OK, 'createElement in a new Document')
    root = root.value
    values['document.createElement'] = [get('element_get_namespace_uri', root, 'string'), get('element_get_tag_name', root, 'string'),
                                        is_node('node_get_owner_document', root, d)]
    append(d, root)
    moved = made(create['text'], document, 'y')
    append(root, moved)
    values['document.adopted'] = [is_node('node_get_owner_document', moved, d), get('node_get_is_connected', moved, 'bool'),
                                  is_node('document_get_document_element', d, root)]
    node_release(moved)
    node_release(root)

    parsed = made(create['parse'], document, '<!doctype html><p id="a">one</p><p>two</p>')
    parsed_body = get('document_get_body', parsed, 'node')
    parsed_first = get('node_get_first_child', parsed_body, 'node')
    parsed_doctype = get('node_get_first_child', parsed, 'node')
    values['parse'] = [get('node_get_node_type', parsed, u16), get('document_get_content_type', parsed, 'string'),
                       get('document_get_compat_mode', parsed, 'string'), get('document_get_character_set', parsed, 'string'),
                       parsed == document, child_count(parsed_body), get('element_get_tag_name', parsed_first, 'string'),
                       get('node_get_node_type', parsed_doctype, u16)]
    node_release(parsed_first)
    node_release(parsed_body)
    empty = made(create['parse'], document, '')
    empty_body = get('document_get_body', empty, 'node')
    values['parse.empty'] = [child_count(empty_body), get('document_get_compat_mode', empty, 'string')]
    node_release(empty_body)
    node_release(empty)

    # StaticRange.
    def static(start, start_offset, end, end_offset, size=ctypes.sizeof(StaticRangeInit)):
        init = StaticRangeInit(size, start, start_offset, end, end_offset)
        result = p()
        status = create['static'](document, ctypes.byref(init), ctypes.byref(result))
        return status, result.value

    status, sr = static(t0, 1, t0, 9)
    expect(status == OK and sr, 'StaticRange')
    values['static'] = [is_node('abstract_range_get_start_container', sr, t0), get('abstract_range_get_start_offset', sr, u32),
                        is_node('abstract_range_get_end_container', sr, t0), get('abstract_range_get_end_offset', sr, u32),
                        get('abstract_range_get_collapsed', sr, 'bool')]
    range_release(sr)
    status, collapsed = static(paragraph, 0, paragraph, 0)
    values['static.collapsed'] = get('abstract_range_get_collapsed', collapsed, 'bool')
    range_release(collapsed)
    create_attribute = utf8('rv_dom_document_create_attribute', i32, [p, Utf8, ctypes.POINTER(p)])
    attr = p()
    expect(create_attribute(document, 'x', ctypes.byref(attr)) == OK, 'createAttribute')
    status, _ = static(attr.value, 0, t0, 0)
    values['static.attr'] = exception_name() if status == DOM_EXCEPTION else status
    node_release(attr.value)
    status, _ = static(t0, 0, parsed_doctype, 0)
    values['static.doctype'] = exception_name() if status == DOM_EXCEPTION else status
    node_release(parsed_doctype)
    node_release(parsed)
    status, _ = static(t0, 0, None, 0)
    values['static.missing'] = 'TypeError' if status == NULL_ARGUMENT else status
    status, _ = static(t0, 0, t0, 0, size=ctypes.sizeof(u32) + ctypes.sizeof(p))
    expect(status == NULL_ARGUMENT, 'a StaticRangeInit size short of its required members is rejected')

    # Events.
    def base(event):
        return [get('event_get_type', event, 'string'), get('event_get_bubbles', event, 'bool'), get('event_get_cancelable', event, 'bool'),
                get('event_get_composed', event, 'bool'), get('event_get_is_trusted', event, 'bool'), get('ui_event_get_detail', event, i32)]

    def init(cls, **fields):
        value = cls()
        value.size = ctypes.sizeof(cls)
        for name, item in fields.items():
            setattr(value, name, string_input(item) if isinstance(item, str) else item)
        return value

    def event(kind, type_, value=None):
        result = p()
        status = create[kind](document, type_, ctypes.byref(value) if value is not None else None, ctypes.byref(result))
        expect(status == OK and result.value, f'{kind} event status {status}')
        return result.value

    target_ranges = bind('rv_dom_input_event_get_target_ranges', i32, [p, ctypes.POINTER(Sequence)])

    def ranges(handle):
        value = Sequence()
        expect(target_ranges(handle, ctypes.byref(value)) == OK, 'getTargetRanges')
        count = value.count
        sequence_range_release(ctypes.byref(value))
        return count

    def input_values(handle):
        return [*base(handle), get('input_event_get_data', handle, 'string'), get('input_event_get_is_composing', handle, 'bool'),
                get('input_event_get_input_type', handle, 'string'), ranges(handle)]

    e = event('input', 'beforeinput')
    values['input.default'] = input_values(e)
    event_release(e)
    e = event('input', 'beforeinput', init(InputEventInit, bubbles=1, cancelable=1, composed=1, detail=2, data='abé',
                                           is_composing=1, input_type='insertText'))
    values['input.full'] = input_values(e)
    event_release(e)
    e = event('input', 'input', init(InputEventInit, data=''))
    values['input.emptyData'] = get('input_event_get_data', e, 'string')
    event_release(e)

    def related(handle):
        value = get('mouse_event_get_related_target', handle, 'node')
        try:
            return value == paragraph
        finally:
            if value:
                node_release(value)

    def wheel_values(handle):
        return [get('wheel_event_get_delta_x', handle, f64), get('wheel_event_get_delta_y', handle, f64), get('wheel_event_get_delta_z', handle, f64),
                get('wheel_event_get_delta_mode', handle, u32), get('wheel_event_get_wheel_delta_x', handle, i32),
                get('wheel_event_get_wheel_delta_y', handle, i32), get('wheel_event_get_wheel_delta', handle, i32),
                get('mouse_event_get_client_x', handle, f64), get('mouse_event_get_client_y', handle, f64),
                get('mouse_event_get_screen_x', handle, f64), get('mouse_event_get_screen_y', handle, f64),
                get('mouse_event_get_button', handle, i16), get('mouse_event_get_buttons', handle, u16),
                get('mouse_event_get_ctrl_key', handle, 'bool'), get('mouse_event_get_shift_key', handle, 'bool'),
                get('mouse_event_get_alt_key', handle, 'bool'), get('mouse_event_get_meta_key', handle, 'bool'), related(handle)]

    as_target = node_as_target(paragraph)
    expect(bool(as_target), 'paragraph as an EventTarget')
    e = event('wheel', 'wheel')
    values['wheel.default'] = [*base(e), *wheel_values(e)]
    event_release(e)
    e = event('wheel', 'wheel', init(WheelEventInit, bubbles=1, cancelable=1, delta_x=3.5, delta_y=-120, delta_z=1, delta_mode=1,
                                     client_x=10, client_y=20, screen_x=1, screen_y=2, ctrl_key=1, meta_key=1, buttons=1,
                                     related_target=as_target))
    values['wheel.full'] = [*base(e), *wheel_values(e)]
    event_release(e)
    e = event('wheel', 'wheel', init(WheelEventInit, wheel_delta_x=240, wheel_delta_y=-120))
    values['wheel.legacy'] = [get('wheel_event_get_delta_x', e, f64), get('wheel_event_get_delta_y', e, f64),
                              get('wheel_event_get_wheel_delta_x', e, i32), get('wheel_event_get_wheel_delta_y', e, i32)]
    event_release(e)

    coalesced_getter = bind('rv_dom_pointer_event_get_coalesced_events', i32, [p, ctypes.POINTER(Sequence)])
    predicted_getter = bind('rv_dom_pointer_event_get_predicted_events', i32, [p, ctypes.POINTER(Sequence)])

    def sequence(getter, handle):
        value = Sequence()
        expect(getter(handle, ctypes.byref(value)) == OK, 'pointer sequence getter')
        items = [value.items[index] for index in range(value.count)]
        sequence_pointer_release(ctypes.byref(value))
        return items

    def pointer_values(handle):
        return [get('pointer_event_get_pointer_id', handle, i32), get('pointer_event_get_width', handle, f64),
                get('pointer_event_get_height', handle, f64), number(get('pointer_event_get_pressure', handle, f32)),
                number(get('pointer_event_get_tangential_pressure', handle, f32)), get('pointer_event_get_tilt_x', handle, i32),
                get('pointer_event_get_tilt_y', handle, i32), get('pointer_event_get_twist', handle, i32),
                get('pointer_event_get_pointer_type', handle, 'string'), get('pointer_event_get_is_primary', handle, 'bool'),
                get('mouse_event_get_client_x', handle, f64), get('mouse_event_get_client_y', handle, f64),
                get('mouse_event_get_button', handle, i16), get('mouse_event_get_buttons', handle, u16), related(handle),
                len(sequence(coalesced_getter, handle)), len(sequence(predicted_getter, handle))]

    e = event('pointer', 'pointerdown')
    values['pointer.default'] = [*base(e), *pointer_values(e)]
    event_release(e)
    sub = event('pointer', 'pointermove', init(PointerEventInit, pointer_id=7, width=1, height=1))
    one = (p * 1)(sub)
    two = (p * 2)(sub, sub)
    coalesced = Sequence(1, 1, ctypes.cast(one, ctypes.POINTER(p)))
    predicted = Sequence(1, 2, ctypes.cast(two, ctypes.POINTER(p)))
    tilt_x, tilt_y = i32(30), i32(-20)
    e = event('pointer', 'pointermove', init(PointerEventInit, bubbles=1, cancelable=1, composed=1, pointer_id=7, width=2.5, height=3.5,
                                             pressure=0.5, tangential_pressure=-0.25, tilt_x=ctypes.pointer(tilt_x),
                                             tilt_y=ctypes.pointer(tilt_y), twist=90, pointer_type='pen', is_primary=1, client_x=12.5,
                                             client_y=7.25, button=1, buttons=4, related_target=as_target,
                                             coalesced_events=ctypes.pointer(coalesced), predicted_events=ctypes.pointer(predicted)))
    values['pointer.full'] = [*base(e), *pointer_values(e)]
    values['pointer.coalescedIdentity'] = sequence(coalesced_getter, e) == [sub]
    event_release(e)
    wrong = Sequence(1, 1, ctypes.cast((p * 1)(made(create['input'], document, 'input', None)), ctypes.POINTER(p)))
    result = p()
    status = create['pointer'](document, 'pointermove', ctypes.byref(init(PointerEventInit, width=1, height=1,
                                                                          coalesced_events=ctypes.pointer(wrong))), ctypes.byref(result))
    expect(status == WRONG_INTERFACE and not result.value, f'a coalesced event of another interface is rejected ({status})')
    event_release(wrong.items[0])
    event_release(sub)
    e = event('pointer', 'pointerdown', init(PointerEventInit, pressure=0.1, width=1, height=1))
    values['pointer.pressure'] = number(get('pointer_event_get_pressure', e, f32))
    event_release(e)

    # Dispatch outcomes: synchronous listeners on the paragraph see an untrusted event at target and cancel it.
    seen = []

    @callback_type
    def listener(context, event_handle):
        target = event_target(event_handle, 0)
        current = event_target(event_handle, 1)
        target_node, current_node = target_as_node(target), target_as_node(current)
        seen.append([get('event_get_event_phase', event_handle, u16), target_node == paragraph, current_node == paragraph,
                     get('event_get_is_trusted', event_handle, 'bool')])
        for handle in (target_node, current_node):
            node_release(handle)
        for handle in (target, current):
            target_release(handle)
        prevent_default(event_handle)
        return 0

    subscription = add_listener(as_target, b'wheel', 0, listener, None)
    expect(bool(subscription), 'wheel listener')

    def dispatched(handle):
        prevented = i32(-7)
        status = node_dispatch(paragraph, handle, ctypes.byref(prevented))
        expect(status == OK, f'dispatch status {status}')
        return [not prevented.value, get('event_get_default_prevented', handle, 'bool')]

    cancelable = event('wheel', 'wheel', init(WheelEventInit, cancelable=1, bubbles=1))
    values['dispatch.cancelable'] = dispatched(cancelable)
    plain = event('wheel', 'wheel')
    values['dispatch.plain'] = dispatched(plain)
    expect(listener_remove(subscription) == OK, 'listener removed')
    after = len(seen)
    dispatched(cancelable)
    expect(len(seen) == after, 'a removed listener sees no later dispatch')
    values['dispatch.seen'] = seen
    event_release(cancelable)
    event_release(plain)
    once = event('input', 'input')
    prevented = i32()
    first_status, second_status = node_dispatch(paragraph, once, ctypes.byref(prevented)), node_dispatch(paragraph, once, ctypes.byref(prevented))
    values['dispatch.redispatch'] = None if first_status == OK and second_status == OK else [first_status, second_status]
    event_release(once)
    target_release(as_target)

    # Matrices.
    def matrix(readonly, bits, items):
        array = ((f32 if bits == 32 else f64) * max(len(items), 1))(*items)
        result = p()
        status = matrices[(readonly, bits)](document, array, len(items), ctypes.byref(result))
        return status, result.value

    def m(handle, name):
        return get('dom_matrix_read_only_get_' + name, handle, 'bool' if name.startswith('is') else f64)

    six = [0.1, 0, 0, 1, 5, 6]
    sixteen = [1, 2, 0, 0, 3, 4, 0, 0, 0, 0, 1, 0, 5, 6, 0, 1]
    status, h = matrix(False, 32, six)
    expect(status == OK, 'fromFloat32Array')
    values['matrix.f32'] = ['DOMMatrix', m(h, 'a'), m(h, 'b'), m(h, 'c'), m(h, 'd'), m(h, 'e'), m(h, 'f'), m(h, 'is2_d'), m(h, 'is_identity')]
    matrix_release(h)
    status, h = matrix(False, 64, six)
    values['matrix.f64'] = ['DOMMatrix', m(h, 'a'), m(h, 'e'), m(h, 'f'), m(h, 'is2_d')]
    set_a = bind('rv_dom_dom_matrix_set_a', i32, [p, f64])
    expect(set_a(h, 2.0) == OK, 'DOMMatrix.a setter')
    values['matrix.mutated'] = m(h, 'a')
    matrix_release(h)
    status, h = matrix(False, 64, sixteen)
    values['matrix.f64.16'] = [m(h, 'm11'), m(h, 'm12'), m(h, 'm21'), m(h, 'm22'), m(h, 'm41'), m(h, 'm42'), m(h, 'm33'), m(h, 'm44'), m(h, 'is2_d')]
    matrix_release(h)
    status, h = matrix(False, 64, [math.nan, 0, 0, 1, math.inf, 0])
    values['matrix.nonfinite'] = [number(m(h, 'a')), number(m(h, 'e')), m(h, 'is2_d')]
    matrix_release(h)
    for key, (bits, count) in {'matrix.short': (64, 5), 'matrix.empty': (32, 0), 'matrix.long': (32, 17)}.items():
        status, h = matrix(False, bits, [0.0] * count)
        values[key] = exception_name() if status == DOM_EXCEPTION else status
        expect(not h, key + ' writes no matrix')
    expect(matrices[(False, 64)](document, None, 6, ctypes.byref(p())) == NULL_ARGUMENT, 'a null array with a count is rejected')
    expect(matrices[(False, 64)](document, None, -1, ctypes.byref(p())) == NULL_ARGUMENT, 'a negative count is rejected')
    status, h = matrix(True, 32, six)
    values['readonly.f32'] = ['DOMMatrixReadOnly', m(h, 'a'), m(h, 'is2_d')]
    expect(set_a(h, 3.0) == WRONG_INTERFACE, 'a read-only matrix rejects the DOMMatrix.a setter')
    values['readonly.unchanged'] = m(h, 'a')
    matrix_release(h)
    status, h = matrix(True, 64, sixteen)
    values['readonly.f64'] = ['DOMMatrixReadOnly', m(h, 'm41')]
    matrix_release(h)

    # Receivers: another node interface is rejected; another host's document owns what its factories make.
    for name, function, extra in [('text', create['text'], ('x',)), ('fragment', create['fragment'], ()), ('range', create['range'], ()),
                                  ('document', create['document'], ()), ('parse', create['parse'], ('',))]:
        result = p()
        expect(function(paragraph, *extra, ctypes.byref(result)) == WRONG_INTERFACE and not result.value, name + ' rejects an element receiver')
        expect(function(None, *extra, ctypes.byref(result)) == NULL_ARGUMENT, name + ' rejects a null receiver')
    result = p()
    expect(create['wheel'](paragraph, 'wheel', None, ctypes.byref(result)) == WRONG_INTERFACE, 'wheel rejects an element receiver')
    expect(matrices[(True, 32)](t0, (f32 * 6)(*six), 6, ctypes.byref(result)) == WRONG_INTERFACE, 'matrix rejects a text receiver')
    other = host_create(64, 64)
    expect(bool(other), 'second host')
    hosts.append(other)
    expect(load_html(other, b'<!doctype html><html><body></body></html>') == OK, 'second load')
    other_document = host_document(other)
    foreign = made(create['text'], other_document, 'z')
    values['crossDocument'] = [is_node('node_get_owner_document', foreign, other_document), is_node('node_get_owner_document', foreign, document)]

    # Off the owning thread every factory returns RV_ERR_WRONG_THREAD.
    statuses = []

    def off_thread():
        out = p()
        statuses.append(create['text'](document, 'w', ctypes.byref(out)))
        statuses.append(create['static'](document, ctypes.byref(StaticRangeInit(ctypes.sizeof(StaticRangeInit), t0, 0, t0, 0)), ctypes.byref(out)))
        statuses.append(create['pointer'](document, 'pointerdown', None, ctypes.byref(out)))
        statuses.append(matrices[(False, 64)](document, (f64 * 6)(*six), 6, ctypes.byref(out)))
    worker = threading.Thread(target=off_thread)
    worker.start()
    worker.join()
    expect(statuses == [WRONG_THREAD] * 4, f'off-thread statuses {statuses}')

    # Teardown: values outlive a replaced document, and the foreign node outlives its host.
    survivor = made(create['text'], document, 'kept')
    kept_event = event('wheel', 'wheel', init(WheelEventInit, delta_x=4))
    for handle in owned:
        node_release(handle)
    expect(load_html(host, b'<!doctype html><html><body></body></html>') == OK, 'document replaced')
    expect(get('character_data_get_data', survivor, 'string') == 'kept', 'a constructed node survives document replacement')
    expect(get('wheel_event_get_delta_x', kept_event, f64) == 4, 'a constructed event survives document replacement')
    node_release(survivor)
    event_release(kept_event)
    host_destroy(other)
    expect(get('character_data_get_data', foreign, 'string') == 'z', 'a constructed node survives its host')
    node_release(foreign)
    host_destroy(host)

    # Comparison with Chromium.
    differences = []
    expected = oracle['values']
    for key in sorted(set(expected) | set(values)):
        if not same(expected.get(key), values.get(key)):
            differences.append({'key': key, 'chromium': expected.get(key), 'native': values.get(key)})
    allowed = {item['key']: item for item in qualified['differences']}
    unexpected = [item for item in differences if item['key'] not in allowed or not same(allowed[item['key']]['native'], item['native'])
                  or not same(allowed[item['key']]['chromium'], item['chromium'])]
    stale = sorted(set(allowed) - {item['key'] for item in differences})
    expect(not unexpected, 'unqualified differences: ' + json.dumps(unexpected, ensure_ascii=True))
    expect(not stale, 'qualified differences that no longer occur: ' + ', '.join(stale))
    after_hashes = {str(item.relative_to(directory)): hashlib.sha256(item.read_bytes()).hexdigest() for item in directory.rglob('*') if item.is_file()}
    expect(before == after_hashes, 'runtime directory unchanged')
    report = {'abi': ABI, 'checks': checks, 'measurements': len(values), 'browser': oracle['browser'], 'differences': differences,
              'values': values, 'runtime': {name: digest for name, digest in before.items() if name.endswith(('.dll', '.so', '.dylib'))}}
    if evidence:
        Path(evidence).write_text(json.dumps(report, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--oracle', default=str(ROOT / 'tests/fixtures/value-factories-oracle.json'))
    parser.add_argument('--qualified', default=str(ROOT / 'tests/fixtures/value-factories-qualified.json'))
    parser.add_argument('--evidence')
    args = parser.parse_args()
    checks = verify(args.native_directory, args.oracle, args.qualified, args.evidence)
    print(f'value_factories: {checks} assertions')


if __name__ == '__main__':
    main()
