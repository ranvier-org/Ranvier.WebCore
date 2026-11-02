"""Check renderer-backed UTF-16 accessibility style runs and failure outputs."""
import argparse
import ctypes as C
import json
import os
from pathlib import Path
import threading


def run(directory):
    search = os.add_dll_directory(str(directory)) if os.name == 'nt' else None
    native = C.CDLL(str(directory / ('RanvierWebCoreHost.dll' if os.name == 'nt' else 'libRanvierWebCoreHost.so')))
    def bind(name, result, *arguments):
        function = getattr(native, name)
        function.restype, function.argtypes = result, arguments
        return function
    pointer, integer = C.c_void_p, C.c_int32
    out = C.POINTER(integer)
    create = bind('rv_host_create', pointer, integer, integer)
    destroy = bind('rv_host_destroy', None, pointer)
    load = bind('rv_host_load_html', integer, pointer, C.c_char_p, integer)
    update = bind('rv_host_update', integer, pointer)
    enable = bind('rv_host_set_accessibility', integer, pointer, integer, pointer, pointer)
    element = bind('rv_document_get_element_by_id', pointer, pointer, C.c_char_p, integer)
    ax = bind('rv_node_ax', pointer, pointer)
    release = bind('rv_ax_release', None, pointer)
    release_node = bind('rv_node_release', None, pointer)
    remove = bind('rv_node_remove', integer, pointer)
    text_length = bind('rv_ax_text_length', integer, pointer)
    style = bind('rv_ax_text_style_run', integer, pointer, integer, C.c_char_p, out, out, pointer, integer, out)
    has = bind('rv_abi_has', integer, C.c_char_p)
    assert has(b'accessibility-text-style') == 1
    html = '''<!doctype html><body style="font-weight:400">
<p id="rich" aria-label="Rich">A<span style="font-weight:700">😀B</span>C</p>
<p id="hidden" aria-label="Hidden">A<span hidden>gone</span>B<span style="display:none">gone</span>C</p>
<p id="nested" aria-label="Nested" style="font-weight:700">A<span>B<i style="font-weight:400">C</i>D</span>E</p>
<p id="empty" aria-label="Empty"></p></body>'''.encode()
    host = create(400, 300)
    assert host
    handles, nodes, rows = [], [], []
    def check(name, condition, actual=None):
        rows.append(dict(name=name, passed=bool(condition), actual=actual))
    def get(identifier):
        encoded = identifier.encode()
        node = element(host, encoded, len(encoded))
        assert node, identifier
        nodes.append(node)
        handle = ax(node)
        assert handle, identifier
        handles.append(handle)
        return handle
    def query(handle, offset, property=b'font-weight', capacity=128):
        start, end, length = integer(91), integer(92), integer(93)
        buffer = C.create_string_buffer(b'!' * 128, 129)
        status = style(handle, offset, property, C.byref(start), C.byref(end), buffer, capacity, C.byref(length))
        value = buffer.raw[:length.value].decode() if status == 0 else buffer.value.decode()
        return status, start.value, end.value, length.value, value
    try:
        assert load(host, html, len(html)) == 0
        assert enable(host, 1, None, None) == 0
        assert update(host) == 0
        rich = get('rich')
        check('UTF-16 non-BMP text length', text_length(rich) == 5, text_length(rich))
        for offset, start, end, value in [(0, 0, 1, '400'), (1, 1, 4, '700'), (2, 1, 4, '700'), (3, 1, 4, '700'), (4, 4, 5, '400'), (5, 4, 5, '400')]:
            actual = query(rich, offset)
            check('non-BMP run ' + str(offset), actual == (0, start, end, 3, value), actual)
        hidden = get('hidden')
        actual = query(hidden, 1)
        check('hidden text omitted and adjacent values merge', text_length(hidden) == 3 and actual == (0, 0, 3, 3, '400'), actual)
        nested = get('nested')
        for offset, start, end, value in [(0, 0, 2, '700'), (1, 0, 2, '700'), (2, 2, 3, '400'), (3, 3, 5, '700'), (4, 3, 5, '700')]:
            actual = query(nested, offset)
            check('inherited/nested run ' + str(offset), actual == (0, start, end, 3, value), actual)
        for offset in [-1, 6]:
            actual = query(rich, offset)
            check('invalid offset clears outputs ' + str(offset), actual[:4] == (-9, 0, 0, 0), actual[:4])
        for prop in [b'width', b'future-property']:
            actual = query(rich, 0, prop)
            check('unsupported property clears outputs ' + prop.decode(), actual[:4] == (-9, 0, 0, 0), actual[:4])
        actual = query(rich, 1, capacity=2)
        check('short buffer untouched with complete run/count', actual[:4] == (-6, 1, 4, 3) and actual[4] == '!' * 128, actual[:4])
        actual = query(rich, 1, capacity=-1)
        check('negative capacity clears outputs', actual[:4] == (-9, 0, 0, 0), actual[:4])
        start, end, length = integer(1), integer(2), integer(3)
        check('null property clears outputs', style(rich, 0, None, C.byref(start), C.byref(end), None, 0, C.byref(length)) == -1 and (start.value, end.value, length.value) == (0, 0, 0))
        foreign = []
        def wrong_thread():
            foreign.append(query(1, 0)[:4])
        worker = threading.Thread(target=wrong_thread)
        worker.start(); worker.join(timeout=5)
        check('wrong thread rejected before invalid handle access', not worker.is_alive() and foreign == [(-2, 0, 0, 0)], foreign)
        assert remove(nodes[0]) == 0
        assert update(host) == 0
        actual = query(rich, 0)
        check('removed node detached with cleared outputs', actual[:4] == (-10, 0, 0, 0), actual[:4])
        assert load(host, b'<body>replacement</body>', 24) == 0
        actual = query(nested, 0)
        check('replaced document detached with cleared outputs', actual[:4] == (-10, 0, 0, 0), actual[:4])
    finally:
        for handle in handles: release(handle)
        for node in nodes: release_node(node)
        destroy(host)
        if search: search.close()
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    arguments = parser.parse_args()
    results = run(arguments.native_directory.resolve())
    arguments.report.write_text(json.dumps(results, indent=2))
    print(json.dumps(dict(assertions=len(results), failures=[row for row in results if not row['passed']])))
    raise SystemExit(any(not row['passed'] for row in results))
