import argparse
import ctypes
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8, bind as bind_utf8


def verify(native_directory):
    directory = Path(native_directory).resolve()
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer = ctypes.c_void_p, ctypes.c_int32
    assertions = 0
    nodes, styles = [], []
    implementation = None

    def bind(name, result, args):
        return bind_utf8(library, name, result, args)

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    query = bind('rv_dom_window_get_computed_style', integer, [pointer, pointer, pointer, integer, ctypes.POINTER(pointer)])
    property_value = bind('rv_dom_css_style_declaration_get_property_value', integer,
                          [pointer, Utf8, pointer, integer, ctypes.POINTER(integer)])
    release_style = bind('rv_dom_css_style_declaration_release', None, [pointer])
    release_node = bind('rv_node_release', None, [pointer])
    host = bind('rv_host_create', pointer, [integer, integer])(320, 240)
    expect(bool(host), 'host creation')
    try:
        expect(bind('rv_abi_has', integer, [ctypes.c_char_p])(b'dom-computed-style') == 1, 'compiled binding capability')
        body = bind('rv_document_body', pointer, [pointer])(host)
        nodes.append(body)
        document = pointer()
        expect(bind('rv_dom_node_get_owner_document', integer, [pointer, ctypes.POINTER(pointer)])(body, ctypes.byref(document)) == 0,
               'document context')
        nodes.append(document.value)
        markup = b'''<style>
            #probe { width:120px; opacity:.5; color:rgb(1,2,3); --probe:held; }
            #probe::before { content:'before'; width:11px; opacity:.25; }
            #probe::after { content:'after'; width:22px; opacity:.75; }
            </style><div id="probe">probe</div><div id="plain">plain</div>'''
        expect(bind('rv_dom_element_set_inner_html', integer, [pointer, Utf8])(body, markup) == 0, 'fixture markup')
        find = bind('rv_document_get_element_by_id', pointer, [pointer, ctypes.c_char_p])
        element, plain = find(host, b'probe'), find(host, b'plain')
        nodes.extend([element, plain])
        expect(bool(element) and bool(plain), 'fixture elements')

        def get(pseudo=None, target=element):
            data = pseudo.encode('utf-8') if pseudo is not None else None
            buffer = ctypes.create_string_buffer(data) if data is not None else None
            result = pointer()
            status = query(document, target, buffer, len(data) if data is not None else -1, ctypes.byref(result))
            expect(status == 0 and bool(result.value), f'computed declaration {pseudo!r}: status={status}')
            styles.append(result.value)
            return result.value

        def read(style, name):
            buffer, length = ctypes.create_string_buffer(4096), integer()
            status = property_value(style, name.encode('utf-8'), buffer, len(buffer), ctypes.byref(length))
            expect(status == 0 and length.value >= 0, f'read {name}: status={status}, length={length.value}')
            return buffer.raw[:length.value].decode('utf-8')

        base = get()
        for name, expected in [('width', '120px'), ('opacity', '0.5'), ('color', 'rgb(1, 2, 3)'), ('--probe', 'held'), ('--missing', '')]:
            expect(read(base, name) == expected, 'base property ' + name)
        for pseudo, width, opacity, content in [('::before', '11px', '0.25', '"before"'), (':before', '11px', '0.25', '"before"'),
                                               ('::after', '22px', '0.75', '"after"')]:
            style = get(pseudo)
            for name, expected in [('width', width), ('opacity', opacity), ('content', content)]:
                expect(read(style, name) == expected, f'{pseudo} property {name}')
        for pseudo in ['', 'no-colon']:
            expect(read(get(pseudo), 'width') == '120px', 'base fallback ' + repr(pseudo))
        for pseudo in ['::not-real', '::before(', '::part(foo)', '::slotted(*)', ':hover', '::before\0junk']:
            style = get(pseudo)
            expect(read(style, 'width') == '', 'invalid/unresolved pseudo is empty ' + repr(pseudo))
            length = integer(42)
            expect(bind('rv_dom_css_style_declaration_get_length', integer, [pointer, ctypes.POINTER(integer)])(
                style, ctypes.byref(length)) == 0 and length.value == 0, 'invalid declaration has zero properties')
        absent = get('::before', plain)
        for name, expected in [('content', 'none'), ('opacity', '1'), ('width', 'auto')]:
            expect(read(absent, name) == expected, 'absent pseudo ' + name)
        expect(bind('rv_element_set_style', integer, [pointer, ctypes.c_char_p, ctypes.c_char_p, integer])(
            element, b'color', b'rgb(9,8,7)', 0) == 0, 'mutate inline style')
        expect(read(base, 'color') == 'rgb(9, 8, 7)', 'computed declaration is live')
        expect(bind('rv_dom_css_style_declaration_set_property', integer, [pointer, Utf8, Utf8, Utf8])(
            base, b'opacity', b'1', b'') == -3, 'computed declaration is read-only')
        expect(read(base, 'opacity') == '0.5', 'failed write preserves computed value')
        missing, length = ctypes.create_string_buffer(64), integer(42)
        expect(bind('rv_dom_element_get_attribute', integer, [pointer, Utf8, pointer, integer, ctypes.POINTER(integer)])(
            element, b'missing', missing, len(missing), ctypes.byref(length)) == 0 and length.value == -1,
            'nullable DOMString missing attribute preserves null')

        owner = pointer()
        expect(bind('rv_dom_document_get_implementation', integer, [pointer, ctypes.POINTER(pointer)])(
            document, ctypes.byref(owner)) == 0 and bool(owner.value), 'document implementation')
        implementation = owner.value
        detached = pointer()
        expect(bind('rv_dom_dom_implementation_create_html_document', integer, [pointer, Utf8, ctypes.POINTER(pointer)])(
            implementation, b'detached', ctypes.byref(detached)) == 0 and bool(detached.value), 'windowless document')
        nodes.append(detached.value)
        result = pointer(42)
        expect(query(detached, element, None, -1, ctypes.byref(result)) == -9 and result.value == 42,
               'windowless document is unsupported and preserves output')

        invalid = ctypes.create_string_buffer(b'\xff')
        for context, target, text, length, expected in [
            (document, element, None, -2, -1), (document, element, None, 1, -1),
            (document, element, invalid, 1, -1), (body, element, None, -1, -11),
            (document, document, None, -1, -11), (None, element, None, -1, -1),
        ]:
            result = pointer(42)
            status = query(context, target, text, length, ctypes.byref(result))
            expect(status == expected and result.value == 42, f'invalid context/input preserves output: {status}')
        result = pointer()
        expect(query(document, element, None, 0, ctypes.byref(result)) == 0 and bool(result.value), 'null zero span means empty')
        styles.append(result.value)
        expect(query(document, element, None, -1, None) == -1, 'null output rejected')
        statuses = []

        def wrong_thread():
            result = pointer(42)
            statuses.append((query(document, element, None, -1, ctypes.byref(result)), result.value))

        worker = threading.Thread(target=wrong_thread)
        worker.start()
        worker.join()
        expect(statuses == [(-2, 42)], 'wrong-thread query preserves output')
    finally:
        for style in styles:
            release_style(style)
        if implementation:
            bind('rv_dom_dom_implementation_release', None, [pointer])(implementation)
        for node in reversed(nodes):
            if node:
                release_node(node)
        bind('rv_host_destroy', None, [pointer])(host)
        if search:
            search.close()
    print(f'PASS computed style: {assertions} assertions; retained handles released')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
