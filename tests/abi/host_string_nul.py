"""WebCore #145 probe against an actual runtime directory: every hand-written free-text string input of
host/RanvierWebCoreAbi.h is UTF-8 bytes with an explicit byte length, so a string holding U+0000 reaches WebCore whole,
and the RvClipboardWrite callback delivers its data the same way. Replays tests/fixtures/host-string-nul-cases.json, one
case per export and use, and compares each value read back with the Chromium 156 oracle
tests/fixtures/host-string-nul-oracle.json: markup loaders (markup), text and values (text), attribute values, IDs and
class tokens (attribute), input-method composition and commit (ime), accessibility values (ax), clipboard and drag data
in and out (clipboard; the outbound case copies multi-byte text, since WebKit drops U+0000 from a copied selection), and style values, key text and event types (low). It also checks each changed export's
argument errors: a length below -1, -1 for a nonnullable string, a NULL pointer with a positive length, and invalid
UTF-8."""

import argparse
import ctypes
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, P, I
from utf8_inputs import Utf8, bind as bind_utf8

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
OK, NULL_ARGUMENT, UNSUPPORTED = 0, -1, -9
ABI = 60
NUL = chr(0)
C = ctypes.c_char_p
CALLBACK = ctypes.CFUNCTYPE(I, P, P)
CLIPBOARD_READ = ctypes.CFUNCTYPE(None, P, P)
TEXT_CONTENT, INNER_HTML, DATA, VALUE, TITLE = 1, 4, 5, 6, 8
CLASS_CONTAINS, CLASS_ADD, CLASS_REMOVE = 0, 1, 2
EDIT_COPY, EDIT_PASTE_PLAIN, EDIT_SELECT_ALL = 0, 3, 4
KEY_CHAR, DRAG_OVER, DRAG_DROP, DROP_COPY = 2, 0, 2, 1


class EventInit(ctypes.Structure):
    _fields_ = [('size', I), ('bubbles', I), ('cancelable', I), ('composed', I), ('detail', I), ('modifiers', I),
                ('screen_x', ctypes.c_double), ('screen_y', ctypes.c_double), ('client_x', ctypes.c_double),
                ('client_y', ctypes.c_double), ('button', I), ('buttons', I), ('key', C), ('code', C),
                ('location', I), ('repeat', I), ('is_composing', I), ('related_target', P), ('custom_detail_json', C)]


class Transport:
    """Length-delimited hand-written inputs (ABI 55): an argument marked Utf8 is a pointer and a byte count, -1 for
    null; RvClipboardWrite receives its data as a pointer and a byte count."""

    clipboard_write = ctypes.CFUNCTYPE(None, P, C, P, I, I)

    @staticmethod
    def bind(native, name, result, arguments):
        return bind_utf8(native.library, name, result, arguments)

    @staticmethod
    def written(arguments):
        context, kind, data, length, first = arguments
        return kind.decode('utf-8'), ctypes.string_at(data, length).decode('utf-8') if length else '', first


class Probe:
    def __init__(self, native, transport):
        self.n, self.t = native, transport
        self.keep = []

    def call(self, name, result, arguments, *values):
        """A hand-written export, its string inputs marked Utf8."""
        return self.t.bind(self.n, name, result, arguments)(*values)

    def release(self, name, handle):
        if handle:
            self.n.bind(name, None, [P])(handle)

    def open(self, markup, width=320, height=200):
        n = self.n
        host = n.bind('rv_host_create', P, [I, I])(width, height)
        n.expect(bool(host), 'host')
        n.expect(self.call('rv_host_load_html', I, [P, Utf8], host, markup) == OK, 'load')
        return host

    def document(self, host):
        return self.n.bind('rv_host_document', P, [P])(host)

    def by_id(self, host, identifier):
        node = self.call('rv_document_get_element_by_id', P, [P, Utf8], host, identifier)
        self.n.expect(bool(node), 'node ' + identifier)
        return node

    def string(self, node, property):
        return self.n.text('rv_node_get_string', [P, I], node, property)

    def value_of(self, node):
        return self.string(node, VALUE)

    def with_host(self, markup, action, width=320, height=200):
        host = self.open(markup, width, height)
        handles = []
        try:
            return action(host, handles)
        finally:
            for name, handle in reversed(handles):
                self.release(name, handle)
            self.n.bind('rv_host_destroy', None, [P])(host)

    def held(self, handles, name, handle):
        handles.append((name, handle))
        return handle

    def status(self, status, expected=OK):
        return None if status == expected else f'status {status}'

    def focused_area(self, host, handles):
        n = self.n
        area = self.held(handles, 'rv_node_release', self.by_id(host, 't'))
        n.ok('rv_host_set_focused', [P, I], host, 1)
        n.ok('rv_element_focus', [P], area)
        return area

    def fired(self, add, dispatch, value):
        """Whether listeners for the value and for its prefix before U+0000 run when an event of the value's type
        is dispatched."""
        fired = []

        def listener(name):
            def on_event(context, event):
                fired.append(name)
                return 0
            callback = CALLBACK(on_event)
            self.keep.append(callback)
            return callback

        listeners = [add(value, listener('value')), add(value.split(NUL)[0], listener('prefix'))]
        try:
            if not all(listeners):
                return 'listener NULL'
            failure = dispatch(value)
            return failure or ['value' in fired, 'prefix' in fired]
        finally:
            for handle in listeners:
                if handle:
                    self.n.call('rv_listener_remove', [P], handle)

    def run(self, entry):
        n, op, v = self.n, entry['op'], entry['value']
        area = '<!doctype html><style>body{margin:0}textarea{position:absolute;left:0;top:0;width:200px;height:60px}' \
               '</style><textarea id=t></textarea>'

        if op in ('loadHtml', 'loadHtmlInner', 'loadHtmlTitle', 'loadSvg'):
            def loaded(host, handles):
                if op == 'loadSvg':
                    failure = self.status(self.call('rv_host_load_svg', I, [P, Utf8], host, v))
                    if failure:
                        return failure
                else:
                    n.ok('rv_host_load_html', [P, Utf8], host, '<!doctype html><title>x</title>')
                    failure = self.status(self.call('rv_host_load_html', I, [P, Utf8], host, v))
                    if failure:
                        return failure
                document = self.held(handles, 'rv_node_release', self.document(host))
                if op == 'loadSvg':
                    found = n.handle('rv_dom_document_query_selector', [P, Utf8], document, 'parsererror')
                    self.release('rv_node_release', found)
                    return bool(found)
                if op == 'loadHtmlTitle':
                    return n.text('rv_dom_document_get_title', [P], document)
                body = self.held(handles, 'rv_node_release', n.bind('rv_document_body', P, [P])(host))
                return self.string(body, INNER_HTML if op == 'loadHtmlInner' else TEXT_CONTENT)
            return self.with_host('<!doctype html>', loaded)

        if op in ('parseFragment', 'parseFragmentComment'):
            def parsed(host, handles):
                body = self.held(handles, 'rv_node_release', n.bind('rv_document_body', P, [P])(host))
                fragment = self.call('rv_node_parse_fragment', P, [P, Utf8], body, v)
                if not fragment:
                    return 'fragment NULL'
                self.held(handles, 'rv_node_release', fragment)
                if op == 'parseFragment':
                    return self.string(fragment, TEXT_CONTENT)
                child = self.held(handles, 'rv_node_release', n.bind('rv_node_relative', P, [P, I])(fragment, 1))
                return self.string(child, DATA)
            return self.with_host('<!doctype html><body>', parsed)

        if op in ('setInnerHtml', 'setTextContent', 'setStringTextContent', 'setStringTitleElement', 'setAttribute',
                  'classAdd', 'classContains', 'classRemove', 'setStyleCustom', 'setStyleContent', 'nodeListenerType'):
            def element(host, handles):
                node = self.held(handles, 'rv_node_release', self.by_id(host, 'd'))
                if op == 'setInnerHtml':
                    return self.status(self.call('rv_node_set_string', I, [P, I, Utf8], node, INNER_HTML, v)) or \
                        n.text('rv_dom_element_get_inner_html', [P], node)
                if op == 'setTextContent':
                    return self.status(self.call('rv_node_set_text_content', I, [P, Utf8], node, v)) or \
                        n.text('rv_dom_node_get_text_content', [P], node)
                if op == 'setStringTextContent':
                    return self.status(self.call('rv_node_set_string', I, [P, I, Utf8], node, TEXT_CONTENT, v)) or \
                        self.string(node, TEXT_CONTENT)
                if op == 'setStringTitleElement':
                    return self.status(self.call('rv_node_set_string', I, [P, I, Utf8], node, TITLE, v)) or \
                        n.text('rv_dom_element_get_attribute', [P, Utf8], node, 'title')
                if op == 'setAttribute':
                    return self.status(self.call('rv_element_set_attribute', I, [P, C, Utf8], node, b'data-v', v)) or \
                        n.text('rv_dom_element_get_attribute', [P, Utf8], node, 'data-v')
                if op == 'classAdd':
                    return self.status(self.call('rv_element_class', I, [P, Utf8, I], node, v, CLASS_ADD), 1) or \
                        n.text('rv_dom_element_get_attribute', [P, Utf8], node, 'class')
                if op == 'classContains':
                    n.ok('rv_dom_element_set_attribute', [P, Utf8, Utf8], node, 'class', v)
                    return self.call('rv_element_class', I, [P, Utf8, I], node, v, CLASS_CONTAINS) == 1
                if op == 'classRemove':
                    n.ok('rv_dom_element_set_attribute', [P, Utf8, Utf8], node, 'class', v + ' a')
                    return self.status(self.call('rv_element_class', I, [P, Utf8, I], node, v, CLASS_REMOVE), 0) or \
                        n.text('rv_dom_element_get_attribute', [P, Utf8], node, 'class')
                if op in ('setStyleCustom', 'setStyleContent'):
                    property = b'--x' if op == 'setStyleCustom' else b'content'
                    return self.status(self.call('rv_element_set_style', I, [P, C, Utf8, I], node, property, v, 0)) or \
                        n.text('rv_element_get_style', [P, C], node, property)
                if op == 'nodeListenerType':
                    def add(kind, callback):
                        return self.call('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P], node, kind, 0,
                                         callback, None)

                    def dispatch(kind):
                        return self.status(self.call('rv_node_dispatch_event', I, [P, Utf8, I, I, P], node, kind, 0, 0,
                                                     None))
                    return self.fired(add, dispatch, v)
            return self.with_host('<!doctype html><body><div id=d></div>', element)

        if op in ('createText', 'createComment'):
            def created(host, handles):
                function = 'rv_document_create_text' if op == 'createText' else 'rv_document_create_comment'
                node = self.call(function, P, [P, Utf8], host, v)
                if not node:
                    return 'node NULL'
                self.held(handles, 'rv_node_release', node)
                return n.text('rv_dom_character_data_get_data', [P], node)
            return self.with_host('<!doctype html>', created)

        if op == 'setStringData':
            def data(host, handles):
                node = self.held(handles, 'rv_node_release', self.call('rv_document_create_text', P, [P, Utf8], host, 'x'))
                return self.status(self.call('rv_node_set_string', I, [P, I, Utf8], node, DATA, v)) or \
                    n.text('rv_dom_character_data_get_data', [P], node)
            return self.with_host('<!doctype html>', data)

        if op in ('setStringValueInput', 'setStringValueTextarea', 'setStringValueOption'):
            markup = {'setStringValueInput': '<input id=f>', 'setStringValueTextarea': '<textarea id=f></textarea>',
                      'setStringValueOption': '<select><option id=f>o</option></select>'}[op]

            def value(host, handles):
                node = self.held(handles, 'rv_node_release', self.by_id(host, 'f'))
                failure = self.status(self.call('rv_node_set_string', I, [P, I, Utf8], node, VALUE, v))
                if failure:
                    return failure
                if op == 'setStringValueOption':
                    return n.text('rv_dom_element_get_attribute', [P, Utf8], node, 'value')
                return self.value_of(node)
            return self.with_host('<!doctype html>' + markup, value)

        if op == 'setStringTitleDocument':
            def title(host, handles):
                document = self.held(handles, 'rv_node_release', self.document(host))
                return self.status(self.call('rv_node_set_string', I, [P, I, Utf8], document, TITLE, v)) or \
                    n.text('rv_dom_document_get_title', [P], document)
            return self.with_host('<!doctype html><title>x</title>', title)

        if op == 'getElementById':
            def found(host, handles):
                body = self.held(handles, 'rv_node_release', n.bind('rv_document_body', P, [P])(host))
                document = self.held(handles, 'rv_node_release', self.document(host))
                for identifier in (v.split(NUL)[0], v):
                    element = n.handle('rv_dom_document_create_element', [P, Utf8, P], document, 'div', None)
                    n.ok('rv_dom_element_set_id', [P, Utf8], element, identifier)
                    n.ok('rv_node_append_child', [P, P], body, element)
                    self.release('rv_node_release', element)
                node = self.call('rv_document_get_element_by_id', P, [P, Utf8], host, v)
                if not node:
                    return None
                self.held(handles, 'rv_node_release', node)
                return n.text('rv_dom_element_get_id', [P], node)
            return self.with_host('<!doctype html><body>', found)

        if op in ('imeComposition', 'imeCommit', 'hostKeyChar', 'clipboardOffer'):
            def typed(host, handles):
                target = self.focused_area(host, handles)
                if op == 'imeComposition':
                    length = len(v.encode('utf-16-le')) // 2
                    failure = self.status(self.call('rv_host_ime_set_composition', I, [P, Utf8, I, I], host, v, length,
                                                    length))
                elif op == 'imeCommit':
                    n.ok('rv_host_ime_set_composition', [P, Utf8, I, I], host, 'x', 1, 1)
                    failure = self.status(self.call('rv_host_ime_commit', I, [P, Utf8], host, v))
                elif op == 'hostKeyChar':
                    status = self.call('rv_host_key', I, [P, I, C, C, Utf8, I, I], host, KEY_CHAR, b'a', b'KeyA', v, 0, 0)
                    failure = None if status >= 0 else f'status {status}'
                else:
                    def read(context, request):
                        self.call('rv_clipboard_offer', I, [P, C, Utf8], request, b'text/plain', v)
                    reader = CLIPBOARD_READ(read)
                    self.keep.append(reader)
                    n.ok('rv_host_set_clipboard', [P, I, P, P, P], host, 0, None, ctypes.cast(reader, P), None)
                    status = n.call('rv_host_edit', [P, I], host, EDIT_PASTE_PLAIN)
                    failure = None if status == 1 else f'status {status}'
                return failure or self.value_of(target)
            return self.with_host(area, typed)

        if op in ('axSetValueInput', 'axSetValueTextarea'):
            markup = '<input id=f aria-label=f>' if op == 'axSetValueInput' else '<textarea id=f aria-label=f></textarea>'

            def accessible(host, handles):
                node = self.held(handles, 'rv_node_release', self.by_id(host, 'f'))
                n.ok('rv_host_set_accessibility', [P, I, P, P], host, 1, None, None)
                try:
                    root = n.bind('rv_host_ax_root', P, [P])(host)
                    self.release('rv_ax_release', root)
                    ax = n.bind('rv_node_ax', P, [P])(node)
                    n.expect(bool(ax), 'ax node')
                    try:
                        status = self.call('rv_ax_set_value', I, [P, Utf8], ax, v)
                    finally:
                        self.release('rv_ax_release', ax)
                    return self.status(status, 1) or self.value_of(node)
                finally:
                    n.ok('rv_host_set_accessibility', [P, I, P, P], host, 0, None, None)
            return self.with_host('<!doctype html>' + markup, accessible)

        if op == 'clipboardWrite':
            def copied(host, handles):
                paragraph = self.held(handles, 'rv_node_release', self.by_id(host, 's'))
                n.ok('rv_dom_node_set_text_content', [P, Utf8], paragraph, v)
                written = []

                def write(*arguments):
                    written.append(self.t.written(arguments))
                writer = self.t.clipboard_write(write)
                self.keep.append(writer)
                n.ok('rv_host_set_clipboard', [P, I, P, P, P], host, 0, ctypes.cast(writer, P), None, None)
                n.expect(n.call('rv_host_edit', [P, I], host, EDIT_SELECT_ALL) == 1, 'select all')
                status = n.call('rv_host_edit', [P, I], host, EDIT_COPY)
                if status != 1:
                    return f'status {status}'
                plain = [data for kind, data, first in written if kind == 'text/plain']
                return plain[0] if len(plain) == 1 else f'written {written!r}'
            return self.with_host('<!doctype html><body><p id=s></p>', copied)

        if op == 'dragDataAdd':
            def dropped(host, handles):
                target = self.focused_area(host, handles)
                n.ok('rv_host_set_drag', [P, I], host, 0)
                data = n.bind('rv_drag_data_create', P, [])()
                try:
                    failure = self.status(self.call('rv_drag_data_add', I, [P, C, Utf8], data, b'text/plain', v))
                    if failure:
                        return failure
                    drag = n.bind('rv_host_drag', I, [P, I, I, I, I, P, I])
                    n.expect(drag(host, DRAG_OVER, 20, 20, DROP_COPY, data, 0) == DROP_COPY, 'dragover accepts copy')
                    n.expect(drag(host, DRAG_DROP, 20, 20, DROP_COPY, data, 0) >= 0, 'drop')
                finally:
                    n.bind('rv_drag_data_release', None, [P])(data)
                return self.value_of(target)
            return self.with_host(area, dropped)

        if op in ('createEventType', 'constructEventType'):
            def event(host, handles):
                if op == 'createEventType':
                    created = self.call('rv_host_create_event', P, [P, I, Utf8, I, I], host, 0, v, 0, 0)
                else:
                    init = EventInit()
                    init.size = ctypes.sizeof(init)
                    created = self.call('rv_host_construct_event', P, [P, I, Utf8, ctypes.POINTER(EventInit)], host, 0, v,
                                        ctypes.byref(init))
                if not created:
                    return 'event NULL'
                self.held(handles, 'rv_event_release', created)
                return n.text('rv_event_type', [P], created)
            return self.with_host('<!doctype html>', event)

        if op == 'targetListenerType':
            def target(host, handles):
                created = self.held(handles, 'rv_event_target_release',
                                    n.bind('rv_host_create_event_target', P, [P])(host))

                def add(kind, callback):
                    return self.call('rv_event_target_add_listener', P, [P, Utf8, I, CALLBACK, P], created, kind, 0,
                                     callback, None)

                def dispatch(kind):
                    event = self.call('rv_host_create_event', P, [P, I, Utf8, I, I], host, 0, kind, 0, 0)
                    if not event:
                        return 'event NULL'
                    try:
                        return self.status(n.call('rv_event_target_dispatch', [P, P, P], created, event, None))
                    finally:
                        self.release('rv_event_release', event)
                return self.fired(add, dispatch, v)
            return self.with_host('<!doctype html>', target)

        raise ValueError(op)


def replay(native, transport, cases, oracle, check=True, qualified=None):
    """Runs every case and returns the cases whose value differs from the expected value: the oracle's, or the WebKit
    value of a qualified difference, which must differ from the oracle's and from the input's prefix before U+0000.
    check asserts each case."""
    probe = Probe(native, transport)
    differ = {}
    for entry in cases:
        observed = probe.run(entry)
        expected = oracle['values'][entry['id']]
        if qualified and entry['id'] in qualified:
            native.expect(qualified[entry['id']]['webkit'] != expected, f"{entry['id']}: qualified value equals the oracle")
            native.expect(qualified[entry['id']]['webkit'] != entry['value'].split(NUL)[0],
                          f"{entry['id']}: qualified value is the input's prefix before U+0000")
            expected = qualified[entry['id']]['webkit']
        if check:
            native.expect(observed == expected, f"{entry['id']} {entry['op']}: {observed!r} vs {expected!r}")
        if observed != expected:
            differ[entry['id']] = {'family': entry['family'], 'op': entry['op'], 'observed': observed,
                                   'expected': expected}
    return differ


# Each changed export, its argument types with the string input marked Utf8, the valid values around it, and whether
# it returns a handle (NULL on an argument error) or a status (RV_ERR_NULL_ARGUMENT).
def changed_exports(host, node, text_node, ax, request, data, target):
    callback = CALLBACK(lambda context, event: 0)
    init = EventInit()
    init.size = ctypes.sizeof(init)
    return callback, [
        ('rv_host_load_html', I, [P, Utf8], [host]),
        ('rv_host_load_svg', I, [P, Utf8], [host]),
        ('rv_node_parse_fragment', P, [P, Utf8], [node]),
        ('rv_node_set_text_content', I, [P, Utf8], [node]),
        ('rv_document_create_text', P, [P, Utf8], [host]),
        ('rv_document_create_comment', P, [P, Utf8], [host]),
        ('rv_node_set_string', I, [P, I, Utf8], [text_node, DATA]),
        ('rv_element_set_attribute', I, [P, C, Utf8], [node, b'data-e']),
        ('rv_document_get_element_by_id', P, [P, Utf8], [host]),
        ('rv_element_class', I, [P, Utf8, I], [node, ..., CLASS_CONTAINS]),
        ('rv_host_ime_set_composition', I, [P, Utf8, I, I], [host, ..., 0, 0]),
        ('rv_host_ime_commit', I, [P, Utf8], [host]),
        ('rv_ax_set_value', I, [P, Utf8], [ax]),
        ('rv_clipboard_offer', I, [P, C, Utf8], [request, b'text/plain']),
        ('rv_drag_data_add', I, [P, C, Utf8], [data, b'text/plain']),
        ('rv_element_set_style', I, [P, C, Utf8, I], [node, b'--e', ..., 0]),
        ('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P], [node, ..., 0, callback, None]),
        ('rv_node_dispatch_event', I, [P, Utf8, I, I, P], [node, ..., 0, 0, None]),
        ('rv_host_create_event', P, [P, I, Utf8, I, I], [host, 0, ..., 0, 0]),
        ('rv_host_construct_event', P, [P, I, Utf8, ctypes.POINTER(EventInit)], [host, 0, ..., ctypes.byref(init)]),
        ('rv_event_target_add_listener', P, [P, Utf8, I, CALLBACK, P], [target, ..., 0, callback, None]),
    ]


def errors(native, report):
    """The transport's argument errors on every changed export, and rv_host_key's null text."""
    n = native
    probe = Probe(n, Transport())
    raw = []

    def run(host, handles):
        node = probe.held(handles, 'rv_node_release', probe.by_id(host, 'd'))
        text_node = probe.held(handles, 'rv_node_release', probe.call('rv_document_create_text', P, [P, Utf8], host, 'x'))
        n.ok('rv_host_set_accessibility', [P, I, P, P], host, 1, None, None)
        probe.release('rv_ax_release', n.bind('rv_host_ax_root', P, [P])(host))
        field = probe.held(handles, 'rv_node_release', probe.by_id(host, 'f'))
        ax = n.bind('rv_node_ax', P, [P])(field)
        n.expect(bool(ax), 'ax node')
        data = n.bind('rv_drag_data_create', P, [])()
        target = n.bind('rv_host_create_event_target', P, [P])(host)
        requests = []

        def read(context, request):
            requests.append(request)
            checks(request)
        reader = CLIPBOARD_READ(read)

        def checks(request):
            callback, exports = changed_exports(host, node, text_node, ax, request, data, target)
            valid = ctypes.create_string_buffer(b'v', 1)
            invalid = ctypes.create_string_buffer(b'\xff\xfe', 2)
            for name, result, arguments, values in exports:
                if name in ('rv_host_load_html', 'rv_host_load_svg') or (request is None) == (name == 'rv_clipboard_offer'):
                    continue
                at = values.index(...) if ... in values else len(values)
                function = n.bind(name, result, arguments[:at] + [P, I] + arguments[at + 1:])

                def call(pointer, length):
                    return function(*values[:at], pointer, length, *values[at + 1:])
                for label, pointer, length in (('length below -1', valid, -2), ('-1 for a nonnullable string', valid, -1),
                                               ('NULL data with a positive length', None, 3),
                                               ('invalid UTF-8', invalid, 2)):
                    status = call(pointer if pointer is None else ctypes.cast(pointer, P), length)
                    if result is P:
                        n.expect(not status, f'{name}: {label} returns NULL')
                    else:
                        n.expect(status == NULL_ARGUMENT, f'{name}: {label}: status {status}')
                raw.append(name)

        checks(None)
        for name in ('rv_host_load_html', 'rv_host_load_svg'):
            function = n.bind(name, I, [P, P, I])
            for label, length in (('length below -1', -2), ('-1 for a nonnullable string', -1)):
                n.expect(function(host, ctypes.cast(ctypes.create_string_buffer(b'x', 1), P), length) == NULL_ARGUMENT,
                         f'{name}: {label}')
            n.expect(function(host, None, 3) == NULL_ARGUMENT, f'{name}: NULL data with a positive length')
            n.expect(function(host, ctypes.cast(ctypes.create_string_buffer(b'\xff\xfe', 2), P), 2) == NULL_ARGUMENT,
                     f'{name}: invalid UTF-8')
            raw.append(name)
        n.ok('rv_host_set_clipboard', [P, I, P, P, P], host, 0, None, ctypes.cast(reader, P), None)
        area = probe.held(handles, 'rv_node_release', probe.by_id(host, 't'))
        n.ok('rv_element_focus', [P], area)
        n.call('rv_host_edit', [P, I], host, EDIT_PASTE_PLAIN)
        n.expect(len(requests) == 1, 'one paste request')
        # A prefix length reads the bytes within the length only.
        n.expect(n.call('rv_node_set_text_content', [P, P, I], node, ctypes.cast(ctypes.create_string_buffer(b'abc', 3), P),
                        1) == OK, 'prefix length')
        n.expect(n.text('rv_dom_node_get_text_content', [P], node) == 'a', 'value within the length')
        # rv_host_key's text is nullable: -1 is no text.
        key = n.bind('rv_host_key', I, [P, I, C, C, P, I, I])
        n.expect(key(host, KEY_CHAR, b'a', b'KeyA', None, -1, 0, 0) >= 0, 'rv_host_key: -1 is no text')
        n.expect(key(host, KEY_CHAR, b'a', b'KeyA', None, -2, 0, 0) == NULL_ARGUMENT, 'rv_host_key: length below -1')
        n.expect(key(host, KEY_CHAR, b'a', b'KeyA', None, 3, 0, 0) == NULL_ARGUMENT,
                 'rv_host_key: NULL data with a positive length')
        n.expect(key(host, KEY_CHAR, b'a', b'KeyA', ctypes.cast(ctypes.create_string_buffer(b'\xff\xfe', 2), P), 2, 0, 0)
                 == NULL_ARGUMENT, 'rv_host_key: invalid UTF-8')
        raw.append('rv_host_key')
        probe.release('rv_event_target_release', target)
        n.bind('rv_drag_data_release', None, [P])(data)
        probe.release('rv_ax_release', ax)
        n.ok('rv_host_set_accessibility', [P, I, P, P], host, 0, None, None)

    probe.with_host('<!doctype html><body><div id=d></div><input id=f aria-label=f><textarea id=t></textarea>', run)
    report['errorExports'] = sorted(set(raw))


def verify(native_directory):
    cases = json.loads((FIXTURES / 'host-string-nul-cases.json').read_text(encoding='utf-8'))['cases']
    oracle = json.loads((FIXTURES / 'host-string-nul-oracle.json').read_text(encoding='utf-8'))
    qualified = json.loads((FIXTURES / 'host-string-nul-qualified.json').read_text(encoding='utf-8'))['differences']
    native = Native(native_directory)
    native.expect(native.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
    report = {'browser': oracle['browser'], 'platform': sys.platform, 'cases': len(cases),
              'families': sorted({entry['family'] for entry in cases})}
    replay(native, Transport(), cases, oracle, qualified=qualified)
    report['qualified'] = sorted(qualified)
    errors(native, report)
    report['assertions'] = native.assertions
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--report')
    args = parser.parse_args()
    report = verify(args.native_directory)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f"PASS host_string_nul: {report['assertions']} assertions, {len(report['qualified'])} qualified", flush=True)


if __name__ == '__main__':
    main()
