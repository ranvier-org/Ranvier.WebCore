import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import threading
import zlib


def png(width, height, corrupt=False):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    rows = b''.join(b'\x00' + b'\xff\x00\x00\xff' * width for _ in range(height))
    body = zlib.compress(rows)
    if corrupt:
        body = b'\x78\x9c' + bytes(range(1, 40))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', body) + chunk(b'IEND', b''))


def verify(directory, evidence_json=None):
    directory = Path(directory).resolve()
    before = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    print('RUNTIME_BEFORE=' + json.dumps(before, sort_keys=True), flush=True)
    if sys.platform == 'win32':
        os.add_dll_directory(str(directory))
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer, u64 = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint64
    assertions = 0
    cases = {}

    def expect(condition, message):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(message)

    def bind(name, result, arguments):
        function = getattr(library, name)
        function.restype, function.argtypes = result, arguments
        return function

    has = bind('rv_abi_has', integer, [ctypes.c_char_p])
    expect(has(b'image-decode') == 1, 'image-decode feature')
    create = bind('rv_host_create', pointer, [integer, integer])
    destroy = bind('rv_host_destroy', None, [pointer])
    load_html = bind('rv_host_load_html', integer, [pointer, ctypes.c_char_p])
    load_svg = bind('rv_host_load_svg', integer, [pointer, ctypes.c_char_p])
    by_id = bind('rv_document_get_element_by_id', pointer, [pointer, ctypes.c_char_p])
    set_attribute = bind('rv_element_set_attribute', integer, [pointer, ctypes.c_char_p, ctypes.c_char_p])
    release_node = bind('rv_node_release', None, [pointer])
    remove_node = bind('rv_node_remove', integer, [pointer])
    ref_count = bind('rv_node_ref_count', integer, [pointer])
    watch = bind('rv_node_watch', pointer, [pointer])
    alive = bind('rv_watch_alive', integer, [pointer])
    release_watch = bind('rv_watch_release', None, [pointer])
    collect = bind('rv_collect_garbage', None, [])
    cycle = bind('rv_run_loop_cycle', integer, [integer])
    Handler = ctypes.CFUNCTYPE(None, pointer, pointer, ctypes.c_char_p)
    set_handler = bind('rv_host_set_resource_handler', integer, [pointer, Handler, pointer])
    finish = bind('rv_resource_load_finish', integer, [pointer, ctypes.c_char_p, integer, ctypes.c_char_p])
    fail = bind('rv_resource_load_fail', integer, [pointer])
    Completion = ctypes.CFUNCTYPE(None, pointer, integer, integer, integer)
    decode = bind('rv_image_decode', integer, [pointer, pointer, Completion, pointer, ctypes.POINTER(u64)])
    cancel = bind('rv_resource_cancel', integer, [u64])
    release = bind('rv_resource_release', integer, [u64])

    served = {}
    pending = {}
    requests = []

    def serve(context, load, url):
        url = url.decode('utf-8')
        requests.append(url)
        if url in served:
            body, kind = served[url]
            if body is None:
                fail(load)
            else:
                finish(load, body, len(body), kind)
        else:
            pending[url] = load
    handler = Handler(serve)

    results = []
    state = {'inside': False, 'reentered': False}

    def complete(context, outcome, width, height):
        if state['inside']:
            state['reentered'] = True
        results.append((context or 0, outcome, width, height))
    completion = Completion(complete)

    def start(host, node, tag):
        operation = u64(0)
        state['inside'] = True
        status = decode(host, node, completion, tag, ctypes.byref(operation))
        state['inside'] = False
        expect(not state['reentered'], 'No completion inside rv_image_decode')
        return status, operation.value

    def wait(tag, limit=200):
        for _ in range(limit):
            matches = [r for r in results if r[0] == tag]
            if matches:
                return matches
            cycle(5)
        return [r for r in results if r[0] == tag]

    def page(host, body):
        expect(load_html(host, ('<!DOCTYPE html><html><body>' + body + '</body></html>').encode()) == 0, 'Load page')
        cycle(5)

    host = create(200, 120)
    expect(bool(host), 'Host creation')
    expect(set_handler(host, handler, None) == 0, 'Resource handler')
    served['https://h05.test/ok.png'] = (png(3, 2), b'image/png')
    served['https://h05.test/corrupt.png'] = (png(3, 2, corrupt=True), b'image/png')
    served['https://h05.test/missing.png'] = (None, None)
    svg_doc = b'<svg xmlns="http://www.w3.org/2000/svg" width="5" height="7"><rect width="5" height="7" fill="blue"/></svg>'
    served['https://h05.test/vector.svg'] = (svg_doc, b'image/svg+xml')

    # Bitmap success: decoder completion, natural size.
    page(host, '<img id="ok" src="https://h05.test/ok.png">')
    node = by_id(host, b'ok')
    baseline = ref_count(node)
    status, op = start(host, node, 1)
    expect(status == 0 and op != 0, 'Decode starts')
    got = wait(1)
    expect(got == [(1, 0, 3, 2)], 'Bitmap SUCCEEDED 3x2: ' + repr(got))
    cases['bitmap'] = got
    expect(ref_count(node) == baseline, 'Terminal operation holds no element reference')
    expect(release(op) == 0 and release(op) == 0, 'Release is idempotent')
    cycle(5)
    expect(len([r for r in results if r[0] == 1]) == 1, 'One terminal after release')
    release_node(node)

    # Corrupt bitmap and 404.
    for tag, name, expected in [(2, 'corrupt', 2), (3, 'missing', 1)]:
        page(host, '<img id="i" src="https://h05.test/' + name + '.png">')
        node = by_id(host, b'i')
        status, op = start(host, node, tag)
        got = wait(tag)
        cases[name] = got
        expect(status == 0 and len(got) == 1 and got[0][1] == expected, name + ' outcome ' + repr(got))
        release(op)
        release_node(node)

    # A terminal reached inside the call (no source) is delivered on a later cycle.
    page(host, '<img id="empty">')
    node = by_id(host, b'empty')
    status, op = start(host, node, 4)
    expect(status == 0 and not [r for r in results if r[0] == 4], 'Start-time terminal deferred')
    got = wait(4)
    cases['no-source'] = got
    expect(got == [(4, 1, 0, 0)], 'No source LOAD_FAILED ' + repr(got))
    release(op)
    release_node(node)

    # Source changes while the load is pending.
    for tag, attribute, value in [(5, b'src', b'https://h05.test/ok.png'), (6, b'srcset', b'https://h05.test/ok.png 1x'), (7, b'crossorigin', b'anonymous')]:
        url = 'https://h05.test/slow' + str(tag) + '.png'
        page(host, '<img id="i" src="' + url + '">')
        node = by_id(host, b'i')
        status, op = start(host, node, tag)
        expect(status == 0, 'Start pending decode')
        cycle(5)
        expect(set_attribute(node, attribute, value) == 0, 'Change ' + attribute.decode())
        got = wait(tag)
        cases['change-' + attribute.decode()] = got
        expect(len(got) == 1 and got[0][1] == 4, attribute.decode() + ' INVALIDATED ' + repr(got))
        if url in pending:
            finish(pending.pop(url), png(1, 1), len(png(1, 1)), b'image/png')
        cycle(5)
        expect(len([r for r in results if r[0] == tag]) == 1, 'Late load adds no terminal')
        release(op)
        release_node(node)

    # Cancel, then release.
    url = 'https://h05.test/slow8.png'
    page(host, '<img id="i" src="' + url + '">')
    node = by_id(host, b'i')
    status, op = start(host, node, 8)
    expect(cancel(op) == 0 and [r for r in results if r[0] == 8] == [(8, 3, 0, 0)], 'Cancel delivers CANCELLED synchronously')
    expect(cancel(op) == 0 and release(op) == 0, 'Cancel/release after terminal')
    finish(pending.pop(url), png(1, 1), len(png(1, 1)), b'image/png')
    cycle(20)
    expect(len([r for r in results if r[0] == 8]) == 1, 'Exactly one terminal after cancel')
    release_node(node)

    # Navigation invalidation: load_html and load_svg.
    for tag, navigate in [(9, lambda: load_html(host, b'<html><body></body></html>')), (10, lambda: load_svg(host, svg_doc))]:
        url = 'https://h05.test/slow' + str(tag) + '.png'
        page(host, '<img id="i" src="' + url + '">')
        node = by_id(host, b'i')
        status, op = start(host, node, tag)
        cycle(5)
        expect(navigate() == 0, 'Navigate')
        got = [r for r in results if r[0] == tag]
        cases['navigate-' + str(tag)] = got
        expect(got == [(tag, 4, 0, 0)], 'Navigation INVALIDATED ' + repr(got))
        expect(release(op) == 0, 'Release after invalidation')
        if url in pending:
            fail(pending.pop(url))
        release_node(node)
        cycle(5)

    # SVG <image> natural size (bitmap and SVG sources) and SVG image semantics.
    expect(load_svg(host, b'<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50"><image id="b" href="https://h05.test/ok.png" width="40" height="40"/><image id="v" href="https://h05.test/vector.svg" width="40" height="40"/></svg>') == 0, 'SVG page')
    cycle(5)
    for tag, name, size in [(11, b'b', (3, 2)), (12, b'v', (5, 7))]:
        node = by_id(host, name)
        status, op = start(host, node, tag)
        got = wait(tag)
        cases['svg-image-' + name.decode()] = got
        expect(status == 0 and got == [(tag, 0) + size], 'SVG image size ' + repr(got))
        release(op)
        release_node(node)

    # Expiry: a terminal operation keeps no node alive.
    page(host, '<img id="gone" src="https://h05.test/ok.png">')
    node = by_id(host, b'gone')
    weak = watch(node)
    status, op = start(host, node, 13)
    wait(13)
    expect(remove_node(node) == 0, 'Remove node')
    release_node(node)
    for _ in range(5):
        collect()
        cycle(5)
    expect(alive(weak) == 0, 'Node destroyed while its terminal operation is still registered')
    release_watch(weak)
    expect(release(op) == 0, 'Release after expiry')

    # Wrong element type and wrong thread.
    page(host, '<div id="d"></div><img id="i" src="https://h05.test/ok.png">')
    div = by_id(host, b'd')
    status, op = start(host, div, 14)
    expect(status == -9 and op == 0, 'Non-image element UNSUPPORTED')
    image = by_id(host, b'i')
    seen = []
    thread = threading.Thread(target=lambda: seen.append(decode(host, image, completion, 15, ctypes.byref(u64(0)))))
    thread.start()
    thread.join()
    expect(seen == [-2], 'Wrong thread ' + repr(seen))
    release_node(div)

    # Host destroy invalidates in-flight operations.
    url = 'https://h05.test/slow16.png'
    page(host, '<img id="i" src="' + url + '">')
    node = by_id(host, b'i')
    status, op = start(host, node, 16)
    cycle(5)
    release_node(image)
    release_node(node)
    destroy(host)
    got = [r for r in results if r[0] == 16]
    cases['destroy'] = got
    expect(got == [(16, 4, 0, 0)], 'Destroy INVALIDATED ' + repr(got))
    expect(release(op) == 0, 'Release after destroy')
    expect(not state['reentered'], 'No re-entry')
    after = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    expect(before == after, 'Runtime unchanged')
    summary = dict(assertions=assertions, requests=len(requests), cases={k: [list(r) for r in v] for k, v in cases.items()})
    if evidence_json:
        Path(evidence_json).write_text(json.dumps(summary, indent=2))
    print('PASS image decode: %d assertions' % assertions, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence-json')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.evidence_json)
