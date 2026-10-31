import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8, bind as bind_utf8


def verify(directory, webkit_source, evidence_json=None):
    directory = Path(directory).resolve()
    before = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    print('RUNTIME_BEFORE=' + json.dumps(before, sort_keys=True), flush=True)
    if sys.platform == 'win32':
        os.add_dll_directory(str(directory))
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer, u64, double = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint64, ctypes.c_double
    assertions = 0
    cases = {}

    def expect(condition, message):
        nonlocal assertions
        assertions += 1
        if not condition:
            raise AssertionError(message)

    def bind(name, result, arguments):
        return bind_utf8(library, name, result, arguments)

    font = (Path(webkit_source) / 'Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf').read_bytes()
    expect(hashlib.sha256(font).hexdigest() == '63d2abd0041c3e3b4b52ad8d382353b53c51c6785e76ce56ed9dacad2d2e31c4', 'Pinned Ahem fixture')
    has = bind('rv_abi_has', integer, [ctypes.c_char_p])
    expect(has(b'font-load') == 1, 'font-load feature')
    create = bind('rv_host_create', pointer, [integer, integer])
    destroy = bind('rv_host_destroy', None, [pointer])
    load_html = bind('rv_host_load_html', integer, [pointer, Utf8])
    by_id = bind('rv_document_get_element_by_id', pointer, [pointer, Utf8])
    release_node = bind('rv_node_release', None, [pointer])
    rect = bind('rv_element_rect', integer, [pointer, ctypes.POINTER(double), ctypes.POINTER(double), ctypes.POINTER(double), ctypes.POINTER(double)])
    update = bind('rv_host_update', integer, [pointer])
    cycle = bind('rv_run_loop_cycle', integer, [integer])
    Completion = ctypes.CFUNCTYPE(None, pointer, integer, integer, integer)
    load_font = bind('rv_font_load', integer, [pointer, ctypes.c_char_p, ctypes.c_char_p, integer, Completion, pointer, ctypes.POINTER(u64)])
    cancel = bind('rv_resource_cancel', integer, [u64])
    release = bind('rv_resource_release', integer, [u64])

    results = []
    state = {'inside': False, 'reentered': False}

    def complete(context, outcome, width, height):
        if state['inside']:
            state['reentered'] = True
        results.append((context or 0, outcome, width, height))
    completion = Completion(complete)

    def start(host, family, data, tag):
        operation = u64(0)
        state['inside'] = True
        status = load_font(host, family, data, len(data), completion, tag, ctypes.byref(operation))
        state['inside'] = False
        expect(not state['reentered'], 'No completion inside rv_font_load')
        return status, operation.value

    def wait(tag, limit=200):
        for _ in range(limit):
            matches = [r for r in results if r[0] == tag]
            if matches:
                return matches
            cycle(5)
        return [r for r in results if r[0] == tag]

    def width(host):
        update(host)
        node = by_id(host, b's')
        x, y, w, h = double(), double(), double(), double()
        expect(rect(node, ctypes.byref(x), ctypes.byref(y), ctypes.byref(w), ctypes.byref(h)) == 0, 'Measure span')
        release_node(node)
        return w.value

    page = b'<!DOCTYPE html><html><body><span id="s" style="font: 20px RvAhem, monospace; white-space: pre">XXXX</span></body></html>'
    host = create(400, 100)
    expect(bool(host), 'Host creation')
    expect(load_html(host, page) == 0, 'Load page')
    cycle(5)
    fallback = width(host)
    cases['fallbackWidth'] = fallback

    # Ahem succeeds only through the face's loaded state; the delivered outcome is deferred past the call.
    status, op = start(host, b'RvAhem', font, 1)
    expect(status == 0 and op != 0 and not [r for r in results if r[0] == 1], 'Font load starts, outcome deferred')
    got = wait(1)
    cases['ahem'] = got
    expect(got == [(1, 0, 0, 0)], 'Ahem SUCCEEDED ' + repr(got))
    loaded = width(host)
    cases['ahemWidth'] = loaded
    expect(abs(loaded - 80.0) <= 1.0 and abs(loaded - fallback) > 1.0, 'Ahem metrics in layout: %r vs fallback %r' % (loaded, fallback))
    expect(release(op) == 0 and release(op) == 0, 'Release is idempotent')
    after = width(host)
    cases['afterReleaseWidth'] = after
    expect(abs(after - fallback) <= 1.0, 'Released font leaves the document: %r' % after)
    expect(len([r for r in results if r[0] == 1]) == 1, 'One terminal')

    # Malformed and empty bytes.
    for tag, name, data in [(2, 'malformed', b'not a font at all, just bytes' * 4), (3, 'empty', b'')]:
        status, op = start(host, b'RvBroken', data, tag)
        got = wait(tag)
        cases[name] = got
        expect(status == 0 and len(got) == 1 and got[0][1] == 2, name + ' DECODE_FAILED ' + repr(got))
        expect(release(op) == 0, 'Release ' + name)

    # Cancel before delivery, then release.
    status, op = start(host, b'RvAhem', font, 4)
    expect(cancel(op) == 0, 'Cancel')
    got = [r for r in results if r[0] == 4]
    cases['cancel'] = got
    expect(len(got) == 1 and got[0][1] in (0, 3), 'Cancel delivers the reached or cancelled outcome once ' + repr(got))
    expect(release(op) == 0, 'Release after cancel')
    cycle(20)
    expect(len([r for r in results if r[0] == 4]) == 1, 'Exactly one terminal after cancel')
    expect(abs(width(host) - fallback) <= 1.0, 'Released cancelled font leaves the document')

    # A held font lease ends with navigation; the delivered outcome stays registered until release.
    status, op = start(host, b'RvAhem', font, 5)
    expect(wait(5) == [(5, 0, 0, 0)], 'Lease font loaded')
    expect(load_html(host, page) == 0, 'Navigate')
    cycle(5)
    expect(abs(width(host) - fallback) <= 1.0, 'New document has no leased font')
    expect(len([r for r in results if r[0] == 5]) == 1, 'Navigation adds no terminal to a delivered font')
    expect(release(op) == 0, 'Release after navigation')

    # Argument and thread guards.
    operation = u64(0)
    expect(load_font(host, b'', font, len(font), completion, 6, ctypes.byref(operation)) == -9 and operation.value == 0, 'Empty family UNSUPPORTED')
    expect(load_font(host, b'RvAhem', font, -1, completion, 6, ctypes.byref(operation)) == -1, 'Negative length')
    seen = []
    thread = threading.Thread(target=lambda: seen.append(load_font(host, b'RvAhem', font, len(font), completion, 7, ctypes.byref(u64(0)))))
    thread.start()
    thread.join()
    expect(seen == [-2], 'Wrong thread ' + repr(seen))

    # Destroy ends a held lease; nothing is delivered twice.
    status, op = start(host, b'RvAhem', font, 8)
    expect(wait(8) == [(8, 0, 0, 0)], 'Lease before destroy')
    destroy(host)
    expect(release(op) == 0 and len([r for r in results if r[0] == 8]) == 1, 'Release after destroy, one terminal')
    expect(not state['reentered'], 'No re-entry')
    after_files = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    expect(before == after_files, 'Runtime unchanged')
    summary = dict(assertions=assertions, cases={k: (v if isinstance(v, float) else [list(r) for r in v]) for k, v in cases.items()})
    if evidence_json:
        Path(evidence_json).write_text(json.dumps(summary, indent=2))
    print('PASS font load: %d assertions' % assertions, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--webkit-source', required=True)
    parser.add_argument('--evidence-json')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.webkit_source, arguments.evidence_json)
