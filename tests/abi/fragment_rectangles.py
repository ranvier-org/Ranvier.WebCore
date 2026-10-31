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
    pointer, integer, unsigned, number = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32, ctypes.c_double
    assertions = 0
    nodes, lists, rectangles, ranges = [], [], [], []

    def bind(name, result, arguments):
        return bind_utf8(library, name, result, arguments)

    def expect(condition, label):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(label)

    element_rects = bind('rv_dom_element_get_client_rects', integer, [pointer, ctypes.POINTER(pointer)])
    range_rects = bind('rv_dom_range_get_client_rects', integer, [pointer, ctypes.POINTER(pointer)])
    list_length = bind('rv_dom_dom_rect_list_get_length', integer, [pointer, ctypes.POINTER(unsigned)])
    list_item = bind('rv_dom_dom_rect_list_item', integer, [pointer, unsigned, ctypes.POINTER(pointer)])
    release_list = bind('rv_dom_dom_rect_list_release', None, [pointer])
    release_rectangle = bind('rv_dom_dom_rect_read_only_release', None, [pointer])
    release_node = bind('rv_node_release', None, [pointer])

    def length(items):
        result = unsigned(42)
        expect(list_length(items, ctypes.byref(result)) == 0, 'read rectangle list length')
        return result.value

    def item(items, index):
        result = pointer(42)
        expect(list_item(items, index, ctypes.byref(result)) == 0, 'read nullable rectangle list item')
        if result.value:
            rectangles.append(result.value)
        return result.value

    def values(rectangle):
        result = {}
        for name in ['x', 'y', 'width', 'height', 'top', 'right', 'bottom', 'left']:
            value = number()
            status = bind('rv_dom_dom_rect_read_only_get_' + name, integer, [pointer, ctypes.POINTER(number)])(
                rectangle, ctypes.byref(value))
            expect(status == 0, 'read rectangle ' + name)
            result[name] = value.value
        return result

    def query(operation, target):
        result = pointer()
        expect(operation(target, ctypes.byref(result)) == 0 and bool(result.value), 'retain rectangle list')
        lists.append(result.value)
        return result.value

    host = bind('rv_host_create', pointer, [integer, integer])(320, 240)
    expect(bool(host), 'create host')
    try:
        body = bind('rv_document_body', pointer, [pointer])(host)
        nodes.append(body)
        document = pointer()
        expect(bind('rv_dom_node_get_owner_document', integer, [pointer, ctypes.POINTER(pointer)])(body, ctypes.byref(document)) == 0,
               'retain document')
        nodes.append(document.value)
        markup = b'''<style>
            #box { position:absolute; left:10.25px; top:20.5px; width:80px; font:10px/12px monospace; }
            #hidden { display:none; }
            </style><div id="box"><span id="wrapped">alpha beta gamma delta epsilon zeta eta theta</span></div>
            <div id="hidden">hidden</div>'''
        expect(bind('rv_dom_element_set_inner_html', integer, [pointer, Utf8])(body, markup) == 0, 'insert wrapped text')
        find = bind('rv_document_get_element_by_id', pointer, [pointer, ctypes.c_char_p])
        wrapped, hidden, box = (find(host, name) for name in [b'wrapped', b'hidden', b'box'])
        nodes.extend([wrapped, hidden, box])
        expect(all([wrapped, hidden, box]), 'find fixture elements')
        fragments = query(element_rects, wrapped)
        count = length(fragments)
        expect(count > 1, 'wrapped inline has multiple fragments')
        geometry = [values(item(fragments, index)) for index in range(count)]
        for index, rectangle in enumerate(geometry):
            expect(rectangle['width'] > 0 and rectangle['height'] > 0, 'positive fragment size')
            expect(rectangle['width'] <= 80.02, 'fragment fits containing block')
            if index:
                expect(rectangle['top'] > geometry[index - 1]['top'], 'fragments retain line order')
        expect(abs(geometry[0]['left'] - 10.25) < 0.001, 'fractional x survives double transport')
        expect(item(fragments, count) is None, 'out-of-range item returns null')
        expect(item(fragments, 0xFFFFFFFF) is None, 'maximum unsigned index returns null')
        bounds = pointer()
        expect(bind('rv_dom_element_get_bounding_client_rect', integer, [pointer, ctypes.POINTER(pointer)])(
            wrapped, ctypes.byref(bounds)) == 0 and bool(bounds.value), 'retain bounding rectangle')
        rectangles.append(bounds.value)
        bounding = values(bounds.value)
        for name, expected in [('left', min(r['left'] for r in geometry)), ('top', min(r['top'] for r in geometry)),
                               ('right', max(r['right'] for r in geometry)), ('bottom', max(r['bottom'] for r in geometry))]:
            expect(abs(bounding[name] - expected) < 0.02, 'bounding union ' + name)
        expect(length(query(element_rects, hidden)) == 0, 'display-none element has no fragments')
        selection = pointer()
        expect(bind('rv_dom_document_create_range', integer, [pointer, ctypes.POINTER(pointer)])(
            document, ctypes.byref(selection)) == 0 and bool(selection.value), 'retain range')
        ranges.append(selection.value)
        expect(length(query(range_rects, selection)) == 0, 'new empty document range has no fragments')
        expect(bind('rv_dom_range_select_node_contents', integer, [pointer, pointer])(selection, wrapped) == 0, 'select wrapped contents')
        range_fragments = query(range_rects, selection)
        expect(length(range_fragments) == count, 'range exposes each wrapped text line')
        range_geometry = [values(item(range_fragments, index)) for index in range(count)]
        for actual, expected in zip(range_geometry, geometry):
            for name in ['left', 'right', 'top', 'bottom']:
                expect(abs(actual[name] - expected[name]) < 0.02, 'range matches inline fragment ' + name)
        expect(bind('rv_node_remove', integer, [pointer])(box) == 0, 'detach fixture')
        expect(length(query(element_rects, wrapped)) == 0, 'detached element has no current fragments')
        expect(length(fragments) == count, 'retained list is a snapshot after detach')
        expect(values(item(fragments, 0)) == geometry[0], 'retained rectangle values survive detach')

        result = pointer(42)
        expect(element_rects(document, ctypes.byref(result)) == -11 and result.value == 42, 'wrong element receiver preserves output')
        expect(list_item(fragments, 0, None) == -1, 'null item output rejected')
        expect(element_rects(wrapped, None) == -1, 'null list output rejected')
        statuses = []

        def wrong_thread():
            result = pointer(42)
            statuses.append((list_item(fragments, 0, ctypes.byref(result)), result.value))

        worker = threading.Thread(target=wrong_thread)
        worker.start()
        worker.join()
        expect(statuses == [(-2, 42)], 'wrong-thread list item preserves output')
        retained = item(fragments, 0)
        release_list(fragments)
        lists.remove(fragments)
        expect(values(retained) == geometry[0], 'retained item survives list release')
    finally:
        for rectangle in rectangles:
            release_rectangle(rectangle)
        for items in lists:
            release_list(items)
        for selection in ranges:
            bind('rv_dom_abstract_range_release', None, [pointer])(selection)
        for node in reversed(nodes):
            if node:
                release_node(node)
        bind('rv_host_destroy', None, [pointer])(host)
        if search:
            search.close()
    print(f'PASS fragment rectangles: {assertions} assertions; retained handles released')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
