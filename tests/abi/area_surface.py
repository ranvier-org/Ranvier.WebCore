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
    pointers, numbers = ctypes.POINTER(pointer), ctypes.POINTER(integer)
    retained = []
    count = 0

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

    def text(name, args, *values):
        buffer, length = ctypes.create_string_buffer(2048), integer()
        call(name, args + [pointer, integer, numbers], *values, buffer, len(buffer), ctypes.byref(length))
        return buffer.value.decode('utf-8')

    def handle(name, node, release):
        result = pointer()
        call(name, [pointer, pointers], node, ctypes.byref(result))
        expect(bool(result.value), name + ': null result')
        retained.append((release, result.value))
        return result.value

    prefix = 'rv_dom_html_area_element_'
    bind(prefix + 'get_href', integer, [pointer, pointer, integer, numbers])
    host = bind('rv_host_create', pointer, [integer, integer])(320, 240)
    expect(bool(host), 'host creation')
    try:
        create = bind('rv_document_create_element', pointer, [pointer, string])
        area, wrong, image_map = [create(host, tag) for tag in [b'area', b'div', b'map']]
        for node in [area, wrong, image_map]:
            expect(bool(node), 'node creation')
            retained.append(('rv_node_release', node))

        reflected = {'alt': 'native-\u03bb', 'coords': '0,0,20,20', 'rel': 'noopener',
                     'shape': 'rect', 'download': 'sample.txt', 'referrer_policy': 'no-referrer',
                     'href': 'https://example.invalid/area', 'target': 'sample-frame'}
        for member, value in reflected.items():
            call(prefix + 'set_' + member, [pointer, Utf8], area, value.encode())
            expect(text(prefix + 'get_' + member, [pointer], area) == value, member + ' reflection')
            buffer, length = ctypes.create_string_buffer(128), integer()
            getter = bind(prefix + 'get_' + member, integer, [pointer, pointer, integer, numbers])
            expect(getter(wrong, buffer, len(buffer), ctypes.byref(length)) == -11, member + ' wrong interface')

        call(prefix + 'set_no_href', [pointer, integer], area, 1)
        value = integer()
        call(prefix + 'get_no_href', [pointer, numbers], area, ctypes.byref(value))
        expect(value.value == 1, 'noHref boolean reflection')
        expect(bind(prefix + 'get_no_href', integer, [pointer, numbers])(wrong, ctypes.byref(value)) == -11,
               'noHref wrong interface')

        initial = b'https://example.invalid:8443/start?q=old#old'
        components = {'protocol': 'http:', 'username': 'fixture-user', 'password': 'fixture-value',
                      'host': 'other.invalid:9443', 'hostname': 'other.invalid', 'port': '9443',
                      'pathname': '/next/path', 'search': '?q=new', 'hash': '#next'}
        for member, value in components.items():
            call(prefix + 'set_href', [pointer, Utf8], area, initial)
            call(prefix + 'set_' + member, [pointer, Utf8], area, value.encode())
            expect(text(prefix + 'get_' + member, [pointer], area) == value, member + ' URL component')
            expect(text(prefix + 'get_href', [pointer], area) != initial.decode(), member + ' updates href')
        call(prefix + 'set_href', [pointer, Utf8], area, initial)
        expect(text(prefix + 'get_origin', [pointer], area) == 'https://example.invalid:8443', 'URL origin')

        tokens = handle(prefix + 'get_rel_list', area, 'rv_dom_dom_token_list_release')
        expect(text('rv_dom_dom_token_list_get_value', [pointer], tokens) == 'noopener', 'relList initial tokens')
        call('rv_dom_dom_token_list_set_value', [pointer, Utf8], tokens, b'noreferrer external')
        expect(text(prefix + 'get_rel', [pointer], area) == 'noreferrer external', 'token mutation updates rel')
        call(prefix + 'set_rel', [pointer, Utf8], area, b'noopener')
        expect(text('rv_dom_dom_token_list_get_value', [pointer], tokens) == 'noopener', 'retained tokens remain live')

        areas = handle('rv_dom_html_map_element_get_areas', image_map, 'rv_dom_html_collection_release')
        length = ctypes.c_uint32()

        def length_is(expected):
            call('rv_dom_html_collection_get_length', [pointer, ctypes.POINTER(ctypes.c_uint32)], areas, ctypes.byref(length))
            expect(length.value == expected, 'live map.areas length ' + str(expected))

        length_is(0)
        call('rv_node_append_child', [pointer, pointer], image_map, area)
        length_is(1)
        call('rv_node_remove_child', [pointer, pointer], image_map, area)
        length_is(0)
    finally:
        for release, node in reversed(retained):
            bind(release, None, [pointer])(node)
        bind('rv_host_destroy', None, [pointer])(host)
        if search:
            search.close()
    print(f'PASS HTML area surface: {count} assertions; retained handles released')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
