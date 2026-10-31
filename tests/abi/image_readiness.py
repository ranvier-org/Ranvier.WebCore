"""R09 image readiness: rv_image_decode on an <img> whose response the resource handler holds settles once the bytes
arrive and decode, the decoded image paints, a failed late response reports its outcome, and an operation released
while its response is held receives nothing afterwards."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import zlib


def png(width, height, rgb):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    rows = b''.join(b'\x00' + bytes(rgb) * width for _ in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def verify(directory, evidence_json=None):
    directory = Path(directory).resolve()
    before = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    if sys.platform == 'win32':
        os.add_dll_directory(str(directory))
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    library = ctypes.CDLL(str(directory / filename))
    P, I, U64 = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint64
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

    expect(bind('rv_abi_has', I, [ctypes.c_char_p])(b'image-decode') == 1, 'image-decode feature')
    create = bind('rv_host_create', P, [I, I])
    destroy = bind('rv_host_destroy', None, [P])
    load_html = bind('rv_host_load_html', I, [P, ctypes.c_char_p])
    by_id = bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])
    release_node = bind('rv_node_release', None, [P])
    cycle = bind('rv_run_loop_cycle', I, [I])
    update = bind('rv_host_update', I, [P])
    paint = bind('rv_host_paint_rgba', I, [P, ctypes.c_char_p, I])
    Handler = ctypes.CFUNCTYPE(None, P, P, ctypes.c_char_p)
    set_handler = bind('rv_host_set_resource_handler', I, [P, Handler, P])
    finish = bind('rv_resource_load_finish', I, [P, ctypes.c_char_p, I, ctypes.c_char_p])
    fail = bind('rv_resource_load_fail', I, [P])
    Completion = ctypes.CFUNCTYPE(None, P, I, I, I)
    decode = bind('rv_image_decode', I, [P, P, Completion, P, ctypes.POINTER(U64)])
    release = bind('rv_resource_release', I, [U64])
    held, results = {}, []
    state = {'inside': False, 'reentered': False}

    def serve(context, load, url):
        held[url.decode().rsplit('/', 1)[-1]] = load
    handler = Handler(serve)

    def complete(context, outcome, width, height):
        if state['inside']:
            state['reentered'] = True
        results.append((context or 0, outcome, width, height))
    completion = Completion(complete)

    def of(tag):
        return [r for r in results if r[0] == tag]

    # Hang guard: waits count no assertion, so totals do not depend on timing.
    def settle(condition, label, limit=400):
        for _ in range(limit):
            if condition():
                return
            cycle(5)
        raise AssertionError('Timed out: ' + label)

    def drain(turns=20):
        for _ in range(turns):
            cycle(5)

    def start(node, tag):
        operation = U64(0)
        state['inside'] = True
        status = decode(host, node, completion, tag, ctypes.byref(operation))
        state['inside'] = False
        return status, operation.value

    def pixel(x, y):
        update(host)
        buffer = ctypes.create_string_buffer(64 * 64 * 4)
        expect(paint(host, buffer, len(buffer)) == 0, 'Paint')
        offset = (y * 64 + x) * 4
        return list(buffer.raw[offset:offset + 4])

    host = create(64, 64)
    expect(bool(host), 'Host creation')
    expect(set_handler(host, handler, None) == 0, 'Resource handler')
    expect(load_html(host, b'<!DOCTYPE html><style>html,body{margin:0;background:#fff}img{display:block;width:16px;height:16px}</style>'
                     b'<img id=a src="https://r09.test/red.png"><img id=b src="https://r09.test/late-fail.png"><img id=c src="https://r09.test/dropped.png">') == 0, 'Load page')
    nodes = {name: by_id(host, name.encode()) for name in 'abc'}
    for tag, name in [(1, 'a'), (2, 'b'), (3, 'c')]:
        status, operation = start(nodes[name], tag)
        expect(status == 0 and operation != 0, 'Decode of ' + name + ' starts before its bytes exist')
        cases[name] = operation
    settle(lambda: len(held) == 3, 'three requests held')
    drain()
    expect(results == [], 'Nothing settles while the responses are held: ' + repr(results))
    expect(pixel(8, 8) == [255, 255, 255, 255], 'The held image paints nothing')

    # Released while held: the late bytes reach an operation that no longer exists.
    expect(release(cases['c']) == 0 and of(3) == [(3, 3, 0, 0)], 'Release while held delivers CANCELLED once')
    red = png(4, 4, (255, 0, 0))
    expect(finish(held.pop('dropped.png'), red, len(red), b'image/png') == 0, 'Serve the dropped image')
    expect(finish(held.pop('red.png'), red, len(red), b'image/png') == 0, 'Serve the delayed image')
    expect(fail(held.pop('late-fail.png')) == 0, 'Fail the delayed image')
    settle(lambda: of(1) and of(2), 'delayed decodes settle')
    cases['outcomes'] = dict(red=of(1), failed=of(2), dropped=of(3))
    expect(of(1) == [(1, 0, 4, 4)], 'Delayed decode SUCCEEDED 4x4: ' + repr(of(1)))
    expect(of(2) == [(2, 1, 0, 0)], 'Delayed failure LOAD_FAILED: ' + repr(of(2)))
    expect(pixel(8, 8) == [255, 0, 0, 255], 'The decoded image paints red')
    drain()
    expect(len(of(1)) == 1 and len(of(2)) == 1 and len(of(3)) == 1, 'One terminal each; nothing reaches the released operation')
    for name in 'ab':
        expect(release(cases[name]) == 0, 'Release ' + name)
    for node in nodes.values():
        release_node(node)
    destroy(host)
    expect(not state['reentered'], 'No completion inside rv_image_decode')
    after = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    expect(before == after, 'Runtime unchanged')
    summary = dict(assertions=assertions, cases=cases['outcomes'])
    if evidence_json:
        Path(evidence_json).write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print('PASS image readiness: %d assertions' % assertions, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence-json')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.evidence_json)
