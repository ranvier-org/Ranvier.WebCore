"""WebCore #142 probe against an actual runtime directory: every generated string input is UTF-8 bytes with an explicit
byte length, so a string holding U+0000 reaches WebCore whole. Replays tests/fixtures/string-nul-cases.json, one case per
DOM member, and compares each value read back with the Chromium 156 oracle tests/fixtures/string-nul-oracle.json:
plain string arguments (C), strings inside unions and sequences (A), dictionary string fields (B), and strings inside
container results (R). It also checks the transport's errors: a length below -1, -1 for a nonnullable string, a NULL
pointer with a positive length, invalid UTF-8, and a NULL pointer with length 0 as the empty string."""

import argparse
import ctypes
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, Case, P, I, U

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
OK, NULL_ARGUMENT = 0, -1
ABI = 54
NODE_ARM, STRING_ARM = 1, 2
HIDDEN_STRING_ARM = 3


class Span(ctypes.Structure):
    _fields_ = [('data', P), ('length', I)]


class StringInput(ctypes.Structure):
    _fields_ = [('present', I), ('data', P), ('length', I)]


class Transport:
    """Length-delimited strings: a plain argument is a pointer and a byte length, -1 for null or absent; a container
    string is an RvDomUtf8StringSpan; a dictionary field is an RvDomUtf8StringInput with present 0 for its default."""

    plain_types = [P, I]
    span_type = Span
    input_type = StringInput

    def __init__(self):
        self.keep = []

    def bytes(self, value):
        data = value.encode('utf-8')
        buffer = ctypes.create_string_buffer(data, len(data) + 1)
        self.keep.append(buffer)
        return ctypes.cast(buffer, P), len(data)

    def plain(self, value):
        return [None, -1] if value is None else list(self.bytes(value))

    def span(self, value):
        return Span(*self.bytes(value))

    def input(self, value):
        return StringInput(0, None, 0) if value is None else StringInput(1, *self.bytes(value))

    @staticmethod
    def read(span):
        return ctypes.string_at(span.data, span.length).decode('utf-8') if span.length > 0 else ''


def structs(t):
    class NodeOrString(ctypes.Structure):
        _fields_ = [('present', I), ('tag', I), ('arm0', P), ('arm1', t.span_type)]

    class NodesOrStrings(ctypes.Structure):
        _fields_ = [('present', I), ('count', I), ('items', ctypes.POINTER(NodeOrString))]

    class Strings(ctypes.Structure):
        _fields_ = [('present', I), ('count', I), ('items', ctypes.POINTER(t.span_type))]

    class Hidden(ctypes.Structure):
        _fields_ = [('present', I), ('tag', I), ('arm0', I), ('arm1', ctypes.c_double), ('arm2', t.span_type)]

    class ToggleEventInit(ctypes.Structure):
        _fields_ = [('size', U), ('bubbles', I), ('cancelable', I), ('composed', I), ('old_state', t.input_type),
                    ('new_state', t.input_type), ('source', P)]

    class CommandEventInit(ctypes.Structure):
        _fields_ = [('size', U), ('bubbles', I), ('cancelable', I), ('composed', I), ('source', P),
                    ('command', t.input_type)]

    class CompositionEventInit(ctypes.Structure):
        _fields_ = [('size', U), ('bubbles', I), ('cancelable', I), ('composed', I), ('detail', I), ('data', t.input_type)]

    class ErrorEventInit(ctypes.Structure):
        _fields_ = [('size', U), ('bubbles', I), ('cancelable', I), ('composed', I), ('message', t.input_type),
                    ('filename', t.input_type), ('lineno', U), ('colno', U)]

    class BlobPropertyBag(ctypes.Structure):
        _fields_ = [('size', U), ('type', t.input_type), ('endings', I)]

    class Ranges(ctypes.Structure):
        _fields_ = [('present', I), ('count', I), ('items', P)]

    return dict(Ranges=Ranges, NodeOrString=NodeOrString, NodesOrStrings=NodesOrStrings, Strings=Strings, Hidden=Hidden,
                ToggleEventInit=ToggleEventInit, CommandEventInit=CommandEventInit,
                CompositionEventInit=CompositionEventInit, ErrorEventInit=ErrorEventInit, BlobPropertyBag=BlobPropertyBag)


class Strings:
    def __init__(self, native, case, transport):
        self.n, self.case, self.t = native, case, transport
        self.s = structs(transport)
        self.document = case.document
        self.body = native.handle('rv_dom_document_get_body', [P], self.document, nullable=False)
        case.owned.append(self.body)

    def element(self, name='div'):
        n, t = self.n, self.t
        element = n.handle('rv_dom_document_create_element', [P] + t.plain_types + [P], self.document, *t.plain(name), None,
                           nullable=False)
        self.case.owned.append(element)
        appended = n.handle('rv_dom_node_append_child', [P, P], self.body, element, nullable=False)
        n.bind('rv_node_release', None, [P])(appended)
        return element

    def created(self, function, value):
        node = self.n.handle(function, [P] + self.t.plain_types, self.document, *self.t.plain(value), nullable=False)
        self.case.owned.append(node)
        return node

    def attribute(self, element, name):
        return self.n.text('rv_dom_element_get_attribute', [P] + self.t.plain_types, element, *self.t.plain(name))

    def set_attribute(self, element, name, value):
        t = self.t
        self.n.ok('rv_dom_element_set_attribute', [P] + t.plain_types * 2, element, *t.plain(name), *t.plain(value))

    def character_data(self, node):
        return self.n.text('rv_dom_character_data_get_data', [P], node)

    def nodes(self, function, element, values):
        s = self.s
        items = (s['NodeOrString'] * len(values))(*[s['NodeOrString'](1, STRING_ARM, None, self.t.span(v)) for v in values])
        sequence = s['NodesOrStrings'](1, len(values), items)
        self.n.ok(function, [P, ctypes.POINTER(s['NodesOrStrings'])], element, ctypes.byref(sequence))

    def tokens(self, function, element, values):
        n, s = self.n, self.s
        tokens = n.handle('rv_dom_element_get_class_list', [P], element, nullable=False)
        try:
            items = (self.t.span_type * len(values))(*[self.t.span(v) for v in values])
            sequence = s['Strings'](1, len(values), items)
            n.ok(function, [P, ctypes.POINTER(s['Strings'])], tokens, ctypes.byref(sequence))
        finally:
            n.bind('rv_dom_dom_token_list_release', None, [P])(tokens)

    def event(self, interface, init, getters):
        n = self.n
        init.size = ctypes.sizeof(init)
        event = n.handle(f'rv_dom_{interface}_create', [P, P, I, ctypes.POINTER(type(init))], self.document,
                         *self.t.bytes('x'), ctypes.byref(init), nullable=False)
        try:
            values = [n.text(f'rv_dom_{interface}_get_{getter}', [P], event) for getter in getters]
        finally:
            n.bind('rv_event_release', None, [P])(event)
        return values if len(values) > 1 else values[0]

    def run(self, entry):
        n, t, s = self.n, self.t, self.s
        op, v = entry['op'], entry.get('value')
        if op == 'setAttribute':
            element = self.element()
            self.set_attribute(element, 'data-v', v)
            return self.attribute(element, 'data-v')
        if op in ('textContent', 'textContentNull'):
            element = self.element()
            n.ok('rv_dom_node_set_text_content', [P] + t.plain_types, element, *t.plain('x'))
            n.ok('rv_dom_node_set_text_content', [P] + t.plain_types, element, *t.plain(v))
            return n.text('rv_dom_node_get_text_content', [P], element)
        if op == 'createTextNode':
            return self.character_data(self.created('rv_dom_document_create_text_node', v))
        if op == 'createComment':
            return self.character_data(self.created('rv_dom_document_create_comment', v))
        if op == 'appendData':
            text = self.created('rv_dom_document_create_text_node', 'a')
            n.ok('rv_dom_character_data_append_data', [P] + t.plain_types, text, *t.plain(v))
            return self.character_data(text)
        if op == 'id':
            element = self.element()
            n.ok('rv_dom_element_set_id', [P] + t.plain_types, element, *t.plain(v))
            return self.attribute(element, 'id')
        if op == 'setAttributeNS':
            element = self.element()
            n.ok('rv_dom_element_set_attribute_ns', [P] + t.plain_types * 3, element, *t.plain(None), *t.plain('data-n'),
                 *t.plain(v))
            return n.text('rv_dom_element_get_attribute_ns', [P] + t.plain_types * 2, element, *t.plain(None),
                          *t.plain('data-n'))
        if op == 'createHTMLDocumentAbsent':
            implementation = n.handle('rv_dom_document_get_implementation', [P], self.document, nullable=False)
            try:
                created = n.handle('rv_dom_dom_implementation_create_html_document', [P] + t.plain_types, implementation,
                                   *t.plain(None), nullable=False)
                self.case.owned.append(created)
                return n.text('rv_dom_document_get_title', [P], created)
            finally:
                n.bind('rv_dom_dom_implementation_release', None, [P])(implementation)
        if op in ('append', 'prepend', 'replaceChildren'):
            element = self.element()
            if op != 'append':
                n.ok('rv_dom_node_set_text_content', [P] + t.plain_types, element, *t.plain('x' if op == 'prepend' else 'old'))
            function = {'append': 'rv_dom_element_append', 'prepend': 'rv_dom_element_prepend',
                        'replaceChildren': 'rv_dom_element_replace_children'}[op]
            self.nodes(function, element, [v, 'z'] if op == 'replaceChildren' else [v])
            return n.text('rv_dom_node_get_text_content', [P], element)
        if op == 'classListAdd':
            element = self.element()
            self.tokens('rv_dom_dom_token_list_add', element, [v])
            return self.attribute(element, 'class')
        if op == 'classListRemove':
            element = self.element()
            self.set_attribute(element, 'class', v + ' a')
            self.tokens('rv_dom_dom_token_list_remove', element, [v])
            return self.attribute(element, 'class')
        if op == 'hidden':
            element = self.element()
            value = s['Hidden'](1, HIDDEN_STRING_ARM, 0, 0.0, t.span(v))
            n.ok('rv_dom_html_element_set_hidden', [P, ctypes.POINTER(s['Hidden'])], element, ctypes.byref(value))
            return self.attribute(element, 'hidden')
        if op == 'toggleEvent':
            init = s['ToggleEventInit'](0, 0, 0, 0, t.input(v), t.input(entry['other']), None)
            return self.event('toggle_event', init, ['old_state', 'new_state'])
        if op == 'commandEvent':
            return self.event('command_event', s['CommandEventInit'](0, 0, 0, 0, None, t.input(v)), ['command'])
        if op == 'compositionEvent':
            return self.event('composition_event', s['CompositionEventInit'](0, 0, 0, 0, 0, t.input(v)), ['data'])
        if op == 'errorEvent':
            init = s['ErrorEventInit'](0, 0, 0, 0, t.input(v), t.input(None), 0, 0)
            return self.event('error_event', init, ['message'])
        if op == 'blobType':
            bag = s['BlobPropertyBag'](0, t.input(v), 0)
            bag.size = ctypes.sizeof(bag)
            blob = n.handle('rv_dom_blob_create', [P, P, ctypes.POINTER(s['BlobPropertyBag'])], self.document, None,
                            ctypes.byref(bag), nullable=False)
            try:
                return n.text('rv_dom_blob_get_type', [P], blob)
            finally:
                n.bind('rv_dom_blob_release', None, [P])(blob)
        if op == 'highlightRegistry':
            registry = n.handle('rv_dom_css_get_highlights', [P], self.document, nullable=False)
            ranges = s['Ranges'](1, 0, None)
            highlight = n.handle('rv_dom_highlight_create', [P, ctypes.POINTER(s['Ranges'])], self.document,
                                 ctypes.byref(ranges), nullable=False)
            try:
                n.ok('rv_dom_highlight_registry_set', [P] + t.plain_types + [P], registry, *t.plain(v), highlight)
                found = []
                for key in (v, v.split(chr(0))[0]):
                    present = I()
                    n.ok('rv_dom_highlight_registry_has', [P] + t.plain_types + [ctypes.POINTER(I)], registry, *t.plain(key),
                         ctypes.byref(present))
                    found.append(present.value == 1)
                n.ok('rv_dom_highlight_registry_delete', [P] + t.plain_types + [ctypes.POINTER(I)], registry, *t.plain(v),
                     ctypes.byref(I()))
                return found
            finally:
                n.bind('rv_dom_highlight_release', None, [P])(highlight)
                n.bind('rv_dom_highlight_registry_release', None, [P])(registry)
        if op == 'getAttributeNames':
            element = self.element()
            self.set_attribute(element, v, '1')
            self.set_attribute(element, 'b', '2')
            names = s['Strings']()
            n.ok('rv_dom_element_get_attribute_names', [P, ctypes.POINTER(s['Strings'])], element, ctypes.byref(names))
            try:
                n.expect(names.present == 1, 'getAttributeNames present')
                return [t.read(names.items[index]) for index in range(names.count)]
            finally:
                n.bind('rv_dom_sequence_dom_string_release', None, [ctypes.POINTER(s['Strings'])])(ctypes.byref(names))
        if op == 'hiddenGetter':
            element = self.element()
            self.set_attribute(element, 'hidden', 'until-found')
            value = s['Hidden']()
            n.ok('rv_dom_html_element_get_hidden', [P, ctypes.POINTER(s['Hidden'])], element, ctypes.byref(value))
            try:
                n.expect(value.present == 1 and value.tag == HIDDEN_STRING_ARM, f'hidden getter arm {value.tag}')
                return t.read(value.arm2)
            finally:
                n.bind('rv_dom_union_boolean_or_unrestricted_double_or_dom_string_nullable_release', None,
                       [ctypes.POINTER(s['Hidden'])])(ctypes.byref(value))
        raise ValueError(op)


def replay(native, transport, cases, oracle, check=True):
    """Runs every case and returns the cases whose value differs from the oracle; check asserts each case."""
    case = Case(native, '<!doctype html><title>strings</title><body>')
    differ = {}
    try:
        strings = Strings(native, case, transport)
        for entry in cases:
            observed = strings.run(entry)
            expected = oracle['values'][entry['id']]
            if check:
                native.expect(observed == expected, f"{entry['id']}: {observed!r} vs {expected!r}")
            if observed != expected:
                differ[entry['id']] = {'category': entry['category'], 'observed': observed, 'expected': expected}
    finally:
        case.close()
    return differ


def errors(native, report):
    """The transport's argument errors, on rv_dom_element_set_attribute (nonnullable) and rv_dom_node_set_text_content
    (nullable)."""
    n = native
    t = Transport()
    case = Case(n, '<p id=p>x</p>')
    try:
        paragraph = case.node('p')
        name = t.plain('data-e')
        set_attribute = n.bind('rv_dom_element_set_attribute', I, [P, P, I, P, I])
        set_text = n.bind('rv_dom_node_set_text_content', I, [P, P, I])
        value = t.bytes('v')
        n.expect(set_attribute(paragraph, *name, value[0], -1) == NULL_ARGUMENT, 'nonnullable string length -1')
        n.expect(set_attribute(paragraph, *name, value[0], -2) == NULL_ARGUMENT, 'length below -1')
        n.expect(set_attribute(paragraph, *name, None, 3) == NULL_ARGUMENT, 'NULL data with a positive length')
        invalid = ctypes.create_string_buffer(b'\xff\xfe', 2)
        n.expect(set_attribute(paragraph, *name, ctypes.cast(invalid, P), 2) == NULL_ARGUMENT, 'invalid UTF-8')
        n.expect(set_text(paragraph, None, -2) == NULL_ARGUMENT, 'nullable length below -1')
        n.expect(set_attribute(paragraph, *name, None, 0) == OK, 'NULL data with length 0')
        n.expect(n.text('rv_dom_element_get_attribute', [P, P, I], paragraph, *name) == '', 'length 0 is the empty string')
        n.expect(set_attribute(paragraph, *name, value[0], 1) == OK, 'a prefix length')
        n.expect(n.text('rv_dom_element_get_attribute', [P, P, I], paragraph, *name) == 'v', 'value within the length')
        n.expect(set_text(paragraph, None, -1) == OK, 'nullable length -1')
        n.expect(n.text('rv_dom_node_get_text_content', [P], paragraph) == '', 'null textContent')
    finally:
        case.close()
    report['errors'] = 'checked'


def verify(native_directory):
    cases = json.loads((FIXTURES / 'string-nul-cases.json').read_text(encoding='utf-8'))['cases']
    oracle = json.loads((FIXTURES / 'string-nul-oracle.json').read_text(encoding='utf-8'))
    native = Native(native_directory)
    native.expect(native.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
    report = {'browser': oracle['browser'], 'platform': sys.platform, 'cases': len(cases),
              'categories': sorted({entry['category'] for entry in cases})}
    replay(native, Transport(), cases, oracle)
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
    print(f"PASS string_nul: {report['assertions']} assertions", flush=True)


if __name__ == '__main__':
    main()
