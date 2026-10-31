import argparse
import ctypes
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from utf8_inputs import Utf8, bind as bind_utf8


TAGS = {
    'HTMLBaseElement': ['base'], 'HTMLBRElement': ['br'], 'HTMLDataElement': ['data'],
    'HTMLDirectoryElement': ['dir'], 'HTMLDListElement': ['dl'], 'HTMLFontElement': ['font'],
    'HTMLHeadingElement': ['h1', 'h6'], 'HTMLHRElement': ['hr'], 'HTMLHtmlElement': ['html'],
    'HTMLMapElement': ['map'], 'HTMLMarqueeElement': ['marquee'], 'HTMLMenuElement': ['menu'],
    'HTMLMetaElement': ['meta'], 'HTMLModElement': ['del', 'ins'], 'HTMLParamElement': ['param'],
    'HTMLPreElement': ['pre', 'listing', 'xmp'], 'HTMLQuoteElement': ['blockquote', 'q'],
    'HTMLSourceElement': ['source'], 'HTMLTimeElement': ['time'], 'HTMLTitleElement': ['title'],
}


def verify(native_directory):
    directory = pathlib.Path(native_directory).resolve()
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer = ctypes.c_void_p, ctypes.c_int32
    functions = json.loads((pathlib.Path(__file__).resolve().parents[2] / 'gen/dom-api.json').read_text(encoding='utf-8'))['functions']
    lookup = {(f['interface'], f['member'], f['kind']): f for f in functions}
    count = 0
    nodes = []
    collections = []

    def bind(name, result, parameters):
        return bind_utf8(library, name, result, parameters)

    create = bind('rv_host_create', pointer, [integer, integer])
    destroy = bind('rv_host_destroy', None, [pointer])
    element = bind('rv_document_create_element', pointer, [pointer, ctypes.c_char_p])
    release = bind('rv_node_release', None, [pointer])
    append = bind('rv_node_append_child', integer, [pointer, pointer])
    remove = bind('rv_node_remove_child', integer, [pointer, pointer])
    release_collection = bind('rv_dom_html_collection_release', None, [pointer])
    collection_length = bind('rv_dom_html_collection_get_length', integer, [pointer, ctypes.POINTER(ctypes.c_uint32)])

    def expect(condition, message):
        nonlocal count
        if not condition:
            raise AssertionError(message)
        count += 1

    host = create(320, 240)
    expect(bool(host), 'host creation')
    try:
        wrong = element(host, b'div')
        expect(bool(wrong), 'wrong-interface test node')
        nodes.append(wrong)
        for interface, tags in TAGS.items():
            setters = [f for f in functions if f['interface'] == interface and f['kind'] == 'setter']
            for tag in tags:
                node = element(host, tag.encode())
                expect(bool(node), tag + ' creation')
                nodes.append(node)
                for setter in setters:
                    getter = lookup[(interface, setter['member'], 'getter')]
                    label = tag + '.' + setter['member']
                    kind = setter['parameters'][1]['ctype']
                    if kind == 'const uint8_t*':
                        put = bind(setter['function'], integer, [pointer, Utf8])
                        get = bind(getter['function'], integer, [pointer, pointer, integer, ctypes.POINTER(integer)])
                        value = b'https://example.invalid/reflection' if setter['member'] in ['href', 'src', 'cite'] else 'native-api-λ'.encode()
                        expect(put(node, value) == 0, label + ' setter')
                        buffer, length = ctypes.create_string_buffer(1024), integer()
                        expect(get(node, buffer, len(buffer), ctypes.byref(length)) == 0, label + ' getter')
                        expect(buffer.value == value, label + ' roundtrip')
                        expect(get(wrong, buffer, len(buffer), ctypes.byref(length)) == -11, label + ' interface guard')
                    else:
                        scalar = {'int32_t': integer, 'uint32_t': ctypes.c_uint32, 'uint8_t': ctypes.c_uint8}[kind]
                        value = 1 if setter['arguments'][0]['idl']['name'] == 'boolean' else 3
                        put = bind(setter['function'], integer, [pointer, scalar])
                        get = bind(getter['function'], integer, [pointer, ctypes.POINTER(scalar)])
                        result = scalar()
                        expect(put(node, value) == 0, label + ' setter')
                        expect(get(node, ctypes.byref(result)) == 0, label + ' getter')
                        expect(result.value == value, label + ' roundtrip')
                        expect(get(wrong, ctypes.byref(result)) == -11, label + ' interface guard')
        for interface, tag, member, child_tag in [
            ('HTMLDataListElement', 'datalist', 'options', 'option'),
            ('HTMLMapElement', 'map', 'areas', 'area'),
        ]:
            parent = element(host, tag.encode())
            child = element(host, child_tag.encode())
            expect(bool(parent) and bool(child), tag + ' collection node creation')
            nodes.extend([parent, child])
            collection = pointer()
            get_collection = bind(lookup[(interface, member, 'getter')]['function'], integer, [pointer, ctypes.POINTER(pointer)])
            expect(get_collection(parent, ctypes.byref(collection)) == 0 and bool(collection.value), tag + ' collection')
            collections.append(collection.value)
            length = ctypes.c_uint32()
            expect(collection_length(collection, ctypes.byref(length)) == 0 and length.value == 0, tag + ' initial length')
            expect(append(parent, child) == 0, tag + ' append')
            expect(collection_length(collection, ctypes.byref(length)) == 0 and length.value == 1, tag + ' live append')
            expect(remove(parent, child) == 0, tag + ' remove')
            expect(collection_length(collection, ctypes.byref(length)) == 0 and length.value == 0, tag + ' live removal')
    finally:
        for collection in reversed(collections):
            release_collection(collection)
        for node in reversed(nodes):
            release(node)
        destroy(host)
        if search:
            search.close()
    print(f'PASS HTML reflection surface: {count} assertions; retained nodes released')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
