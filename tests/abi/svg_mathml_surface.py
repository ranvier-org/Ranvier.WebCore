import argparse
import ctypes
import os
import pathlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8, bind as bind_utf8


def verify(native_directory):
    directory = pathlib.Path(native_directory).resolve()
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer, string = ctypes.c_void_p, ctypes.c_int32, ctypes.c_char_p
    pointers = ctypes.POINTER(pointer)
    numbers = ctypes.POINTER(integer)
    count = 0
    handles = []
    focus_nodes = []

    def bind(name, result, args):
        return bind_utf8(library, name, result, args)

    def expect(condition, message):
        nonlocal count
        if not condition:
            raise AssertionError(message)
        count += 1

    def call(name, args, *values):
        status = bind(name, integer, args)(*values)
        expect(status == 0, name + ': status ' + str(status))

    def handle(name, args, *values, release='rv_node_release'):
        result = pointer()
        call(name, args + [pointers], *values, ctypes.byref(result))
        expect(bool(result.value), name + ': null handle')
        handles.append((release, result.value))
        return result.value

    def text(name, args, *values):
        buffer, length = ctypes.create_string_buffer(1024), integer()
        call(name, args + [pointer, integer, numbers], *values, buffer, len(buffer), ctypes.byref(length))
        return buffer.value.decode('utf-8')

    create = bind('rv_host_create', pointer, [integer, integer])
    destroy = bind('rv_host_destroy', None, [pointer])
    host = create(320, 240)
    expect(bool(host), 'host creation')
    try:
        body = bind('rv_document_body', pointer, [pointer])(host)
        expect(bool(body), 'document body')
        handles.append(('rv_node_release', body))
        document = handle('rv_dom_node_get_owner_document', [pointer], body)
        for prefix, namespace, tag in [
            ('svg_element', b'http://www.w3.org/2000/svg', b'svg'),
            ('math_ml_element', b'http://www.w3.org/1998/Math/MathML', b'math'),
        ]:
            node = handle('rv_dom_document_create_element_ns', [pointer, Utf8, Utf8, pointer], document, namespace, tag, None)
            focus_nodes.append(node)
            expect(text('rv_dom_element_get_namespace_uri', [pointer], node) == namespace.decode(), tag.decode() + ' namespace')
            call('rv_node_append_child', [pointer, pointer], body, node)
            rejected = pointer()
            wrong_style = bind('rv_dom_html_element_get_style', integer, [pointer, pointers])
            expect(wrong_style(node, ctypes.byref(rejected)) == -11 and not rejected.value, prefix + ' is not HTMLElement')
            style = handle('rv_dom_' + prefix + '_get_style', [pointer], node, release='rv_dom_css_style_declaration_release')
            call('rv_dom_css_style_declaration_set_property', [pointer, Utf8, Utf8, Utf8], style, b'color', b'red', b'important')
            expect(text('rv_dom_css_style_declaration_get_property_priority', [pointer, Utf8], style, b'color') == 'important', prefix + ' priority')
            expect(text('rv_dom_css_style_declaration_remove_property', [pointer, Utf8], style, b'color') == 'red', prefix + ' removed value')
            expect(text('rv_dom_css_style_declaration_get_property_priority', [pointer, Utf8], style, b'color') == '', prefix + ' priority removed')
            dataset = handle('rv_dom_' + prefix + '_get_dataset', [pointer], node, release='rv_dom_dom_string_map_release')
            call('rv_dom_dom_string_map_set_named_item', [pointer, Utf8, Utf8], dataset, b'probe', 'native-λ'.encode())
            expect(text('rv_dom_dom_string_map_named_item', [pointer, Utf8], dataset, b'probe') == 'native-λ', prefix + ' dataset')
            call('rv_dom_' + prefix + '_set_nonce', [pointer, Utf8], node, b'native-nonce')
            expect(text('rv_dom_' + prefix + '_get_nonce', [pointer], node) == 'native-nonce', prefix + ' nonce')
            call('rv_dom_' + prefix + '_set_autofocus', [pointer, integer], node, 1)
            value = integer()
            call('rv_dom_' + prefix + '_get_autofocus', [pointer, numbers], node, ctypes.byref(value))
            expect(value.value == 1, prefix + ' autofocus')
            call('rv_dom_' + prefix + '_set_tab_index', [pointer, integer], node, 0)
            call('rv_dom_' + prefix + '_get_tab_index', [pointer, numbers], node, ctypes.byref(value))
            expect(value.value == 0, prefix + ' tab index')
            call('rv_dom_node_set_text_content', [pointer, Utf8], node, b'x')
            call('rv_dom_css_style_declaration_set_property', [pointer, Utf8, Utf8, Utf8], style, b'width', b'40px', b'')
            call('rv_dom_css_style_declaration_set_property', [pointer, Utf8, Utf8, Utf8], style, b'height', b'20px', b'')
            call('rv_host_update', [pointer], host)
            call('rv_dom_' + prefix + '_focus', [pointer, pointer], node, None)
            active = bind('rv_document_active_element', pointer, [pointer])(host)
            expect(bool(active), prefix + ' active element')
            handles.append(('rv_node_release', active))
            call('rv_dom_node_is_same_node', [pointer, pointer, numbers], node, active, ctypes.byref(value))
            expect(value.value == 1, prefix + ' focus identity')
            call('rv_dom_' + prefix + '_blur', [pointer], node)
            after_blur = bind('rv_document_active_element', pointer, [pointer])(host)
            expect(bool(after_blur), prefix + ' active element after blur')
            handles.append(('rv_node_release', after_blur))
            call('rv_dom_node_is_same_node', [pointer, pointer, numbers], node, after_blur, ctypes.byref(value))
            expect(value.value == 0, prefix + ' blur changes active element')
            expect(text('rv_dom_element_get_namespace_uri', [pointer], node) == namespace.decode(), prefix + ' retains namespace')
        call('rv_dom_svg_element_focus', [pointer, pointer], focus_nodes[0], None)
        keyboard = bind('rv_host_key', integer, [pointer, integer, string, string, string, integer, integer])
        expect(keyboard(host, 0, b'Tab', b'Tab', b'', 0, 0) == 1, 'Tab handled by native focus traversal')
        active = bind('rv_document_active_element', pointer, [pointer])(host)
        expect(bool(active), 'active element after Tab')
        handles.append(('rv_node_release', active))
        call('rv_dom_node_is_same_node', [pointer, pointer, numbers], focus_nodes[1], active, ctypes.byref(value))
        expect(value.value == 1, 'Tab moves from SVG to MathML in document order')
    finally:
        for release, item in reversed(handles):
            bind(release, None, [pointer])(item)
        destroy(host)
        if search:
            search.close()
    print(f'PASS SVG/MathML shared members: {count} assertions; retained handles released')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
