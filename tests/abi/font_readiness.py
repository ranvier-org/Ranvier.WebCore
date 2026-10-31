"""T01 font readiness: rv_fonts_status/check/load/ready and the font set event watch over a CSS @font-face whose
response the resource handler holds, with a broken and a missing face, cancellation, navigation and destroy."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import threading

AHEM_SHA256 = '63d2abd0041c3e3b4b52ad8d382353b53c51c6785e76ce56ed9dacad2d2e31c4'
LOADING, LOADINGDONE, LOADINGERROR = 0, 1, 2
FAMILY = 'Rvé字'


def verify(directory, webkit_source, evidence_json=None):
    directory = Path(directory).resolve()
    before = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    if sys.platform == 'win32':
        os.add_dll_directory(str(directory))
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    library = ctypes.CDLL(str(directory / filename))
    P, I, U64, D = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint64, ctypes.c_double
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

    font = (Path(webkit_source) / 'Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf').read_bytes()
    expect(hashlib.sha256(font).hexdigest() == AHEM_SHA256, 'Pinned Ahem fixture')
    has = bind('rv_abi_has', I, [ctypes.c_char_p])
    expect(has(b'font-readiness') == 1 and has(b'font-load') == 1, 'font-readiness and font-load features')
    create = bind('rv_host_create', P, [I, I])
    destroy = bind('rv_host_destroy', None, [P])
    load_html = bind('rv_host_load_html', I, [P, ctypes.c_char_p])
    by_id = bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])
    release_node = bind('rv_node_release', None, [P])
    rect = bind('rv_element_rect', I, [P] + [ctypes.POINTER(D)] * 4)
    update = bind('rv_host_update', I, [P])
    cycle = bind('rv_run_loop_cycle', I, [I])
    last_exception = bind('rv_last_exception', I, [I, ctypes.c_char_p, I, ctypes.POINTER(I)])
    Handler = ctypes.CFUNCTYPE(None, P, P, ctypes.c_char_p)
    set_handler = bind('rv_host_set_resource_handler', I, [P, Handler, P])
    finish = bind('rv_resource_load_finish', I, [P, ctypes.c_char_p, I, ctypes.c_char_p])
    fail = bind('rv_resource_load_fail', I, [P])
    Completion = ctypes.CFUNCTYPE(None, P, I, I, I)
    Event = ctypes.CFUNCTYPE(None, P, I, ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)), ctypes.POINTER(I), I)
    status_of = bind('rv_fonts_status', I, [P, ctypes.POINTER(I)])
    check_of = bind('rv_fonts_check', I, [P, ctypes.c_char_p, I, ctypes.c_char_p, I, ctypes.POINTER(I)])
    load_of = bind('rv_fonts_load', I, [P, ctypes.c_char_p, I, ctypes.c_char_p, I, Completion, P, ctypes.POINTER(U64)])
    ready_of = bind('rv_fonts_ready', I, [P, Completion, P, ctypes.POINTER(U64)])
    watch_of = bind('rv_fonts_watch', I, [P, Event, P, ctypes.POINTER(P)])
    unwatch = bind('rv_fonts_unwatch', None, [P])
    cancel = bind('rv_resource_cancel', I, [U64])
    release = bind('rv_resource_release', I, [U64])

    held = {}
    results = []
    events = []
    state = {'inside': False, 'reentered': False}

    def serve(context, load, url):
        held[url.decode().rsplit('/', 1)[-1]] = load
    handler = Handler(serve)

    def complete(context, outcome, width, height):
        if state['inside']:
            state['reentered'] = True
        results.append((context or 0, outcome, width, height))
    completion = Completion(complete)

    def on_event(context, kind, families, lengths, count):
        if state['inside']:
            state['reentered'] = True
        names = [bytes(families[i][:lengths[i]]).decode('utf-8') for i in range(count)]
        events.append((context or 0, kind, names))
    event_callback = Event(on_event)

    def inside(function, *arguments):
        state['inside'] = True
        try:
            return function(*arguments)
        finally:
            state['inside'] = False

    def text(value):
        data = value.encode('utf-8')
        return data, len(data)

    def check(host, font_value, sample=None):
        loaded = I(-1)
        f, fl = text(font_value)
        s, sl = text(sample) if sample is not None else (None, 0)
        return inside(check_of, host, f, fl, s, sl, ctypes.byref(loaded)), loaded.value

    def load(host, font_value, tag):
        operation = U64(0)
        f, fl = text(font_value)
        status = inside(load_of, host, f, fl, None, 0, completion, tag, ctypes.byref(operation))
        expect(not [r for r in results if r[0] == tag], 'No load terminal inside rv_fonts_load')
        return status, operation.value

    def ready(host, tag):
        operation = U64(0)
        status = inside(ready_of, host, completion, tag, ctypes.byref(operation))
        expect(not [r for r in results if r[0] == tag], 'No ready terminal inside rv_fonts_ready')
        return status, operation.value

    def status(host):
        value = I(-1)
        expect(inside(status_of, host, ctypes.byref(value)) == 0, 'Status call')
        return value.value

    def of(tag):
        return [r for r in results if r[0] == tag]

    # Hang guard: waits count no assertion, so totals do not depend on timing.
    def settle(condition, label, limit=400):
        for _ in range(limit):
            if condition():
                return
            cycle(5)
        raise AssertionError('Timed out: ' + label)

    def drain(turns=10):
        for _ in range(turns):
            cycle(5)

    def exception_name():
        buffer, length = ctypes.create_string_buffer(64), I()
        last_exception(0, buffer, len(buffer), ctypes.byref(length))
        return buffer.raw[:length.value].decode()

    def width(host):
        update(host)
        node = by_id(host, b's')
        x, y, w, h = D(), D(), D(), D()
        expect(rect(node, ctypes.byref(x), ctypes.byref(y), ctypes.byref(w), ctypes.byref(h)) == 0, 'Measure span')
        release_node(node)
        return w.value

    def page(generation=''):
        query = ('?' + generation) if generation else ''
        return ('<!DOCTYPE html><style>'
                '@font-face{font-family:RvLate;src:url(https://t01.test/ahem.ttf' + query + ')}'
                '@font-face{font-family:RvBroken;src:url(https://t01.test/broken.ttf' + query + ')}'
                '@font-face{font-family:RvMissing;src:url(https://t01.test/missing.ttf' + query + ')}'
                '@font-face{font-family:RvHeld;src:url(https://t01.test/held.ttf' + query + ')}'
                '@font-face{font-family:"' + FAMILY + '";src:url(https://t01.test/named.ttf' + query + ')}'
                '#s{font:20px RvLate, monospace;white-space:pre}</style><body><span id=s>XXXX</span>').encode('utf-8')

    host = create(400, 100)
    expect(bool(host), 'Host creation')
    expect(set_handler(host, handler, None) == 0, 'Resource handler')
    expect(load_html(host, page()) == 0, 'Load page')
    watch = P()
    expect(inside(watch_of, host, event_callback, 1, ctypes.byref(watch)) == 0 and bool(watch.value), 'Watch')
    update(host)
    settle(lambda: 'ahem.ttf' in held, 'layout requests the late face')
    fallback = width(host)
    cases['fallbackWidth'] = fallback

    # Loading: the late face is requested and held.
    expect(status(host) == 1, 'Status LOADING while the response is held')
    expect(check(host, '20px RvLate') == (0, 0), 'check false while loading')
    expect(check(host, '20px NoSuchFamily') == (0, 1), 'check true when no face matches')
    expect(check(host, '20px RvLate', 'X') == (0, 0), 'check with text')
    status_code, value = check(host, 'not a font')
    expect(status_code == -3 and value == -1 and exception_name() == 'SyntaxError', 'check SyntaxError leaves the result')
    loaded = I(-1)
    expect(inside(check_of, host, b'\xff\xfe', 2, None, 0, ctypes.byref(loaded)) == -9 and loaded.value == -1, 'Non-UTF-8 font UNSUPPORTED')
    expect(inside(check_of, host, None, 0, None, 0, ctypes.byref(loaded)) == -1, 'NULL font')
    expect(inside(check_of, host, b'x', 1, None, 3, ctypes.byref(loaded)) == -1, 'NULL text with length')
    drain()
    cases['eventsWhileHeld'] = list(events)
    expect(events == [(1, LOADING, [])], 'LOADING once, without faces: ' + repr(events))

    status_code, ready_held = ready(host, 10)
    expect(status_code == 0 and ready_held != 0, 'Ready starts while loading')
    status_code, late = load(host, '20px RvLate', 11)
    expect(status_code == 0 and late != 0, 'Load of the late face starts')
    operation = U64(0)
    f, fl = text('not a font')
    expect(inside(load_of, host, f, fl, None, 0, completion, 12, ctypes.byref(operation)) == -3 and operation.value == 0
           and exception_name() == 'SyntaxError', 'load SyntaxError creates no operation')
    status_code, none = load(host, '20px NoSuchFamily', 13)
    expect(status_code == 0, 'Load without a matching face starts')
    settle(lambda: of(13), 'no-match load')
    expect(of(13) == [(13, 0, 0, 0)], 'No matching face SUCCEEDED with 0 faces: ' + repr(of(13)))
    drain()
    expect(not of(10) and not of(11), 'Ready and load wait for the held response')

    # The response arrives: load, ready and the events settle, and the measurement uses the loaded face.
    expect(finish(held.pop('ahem.ttf'), font, len(font), b'font/ttf') == 0, 'Serve the late face')
    settle(lambda: of(10) and of(11), 'late face settles')
    cases['late'] = dict(load=of(11), ready=of(10))
    expect(of(11) == [(11, 0, 1, 0)], 'Late load SUCCEEDED with 1 face: ' + repr(of(11)))
    expect(of(10) == [(10, 0, 0, 0)], 'Ready SUCCEEDED: ' + repr(of(10)))
    measured = width(host)
    cases['readyWidth'] = measured
    expect(abs(measured - 80.0) <= 1.0 and abs(fallback - 80.0) > 1.0, 'Measured after ready with Ahem metrics: %r (fallback %r)' % (measured, fallback))
    settle(lambda: len(events) >= 2, 'loadingdone')
    drain()
    expect(events == [(1, LOADING, []), (1, LOADINGDONE, ['RvLate'])], 'LOADINGDONE with the loaded face: ' + repr(events))
    expect(status(host) == 0 and check(host, '20px RvLate') == (0, 1), 'Status LOADED and check true')

    # A ready taken when everything has loaded settles on a later delivery, never inside the call.
    status_code, ready_now = ready(host, 14)
    expect(status_code == 0 and not of(14), 'Ready of a settled set is deferred')
    settle(lambda: of(14), 'deferred ready')
    expect(of(14) == [(14, 0, 0, 0)], 'Deferred ready SUCCEEDED')
    status_code, loaded_again = load(host, '20px RvLate', 15)
    settle(lambda: of(15), 'load of a loaded face')
    expect(of(15) == [(15, 0, 1, 0)], 'Load of a loaded face SUCCEEDED on a later delivery')
    for op in [ready_held, late, none, ready_now, loaded_again]:
        expect(release(op) == 0 and release(op) == 0, 'Release is idempotent')

    # A broken and a missing face fail their loads; the set reports loadingdone without them, then loadingerror.
    count = len(events)
    status_code, broken = load(host, '20px RvBroken', 20)
    expect(status_code == 0, 'Broken load starts')
    status_code, missing = load(host, '20px RvMissing', 21)
    expect(status_code == 0, 'Missing load starts')
    settle(lambda: 'broken.ttf' in held and 'missing.ttf' in held, 'broken and missing requested')
    expect(finish(held.pop('broken.ttf'), b'not a font', 10, b'font/ttf') == 0 and fail(held.pop('missing.ttf')) == 0, 'Serve broken, fail missing')
    settle(lambda: of(20) and of(21), 'failed faces settle')
    cases['failed'] = dict(broken=of(20), missing=of(21))
    expect(of(20) == [(20, 1, 0, 0)] and of(21) == [(21, 1, 0, 0)], 'Broken and missing LOAD_FAILED: ' + repr((of(20), of(21))))
    settle(lambda: len(events) >= count + 3, 'loadingerror')
    drain()
    later = events[count:]
    cases['failedEvents'] = later
    expect([e[1] for e in later] == [LOADING, LOADINGDONE, LOADINGERROR], 'LOADING, LOADINGDONE, LOADINGERROR: ' + repr(later))
    expect(later[1][2] == [] and sorted(later[2][2]) == ['RvBroken', 'RvMissing'], 'loadingerror lists the failed faces: ' + repr(later))
    expect(release(broken) == 0 and release(missing) == 0, 'Release failed loads')
    status_code, failed_again = load(host, '20px RvBroken', 22)
    settle(lambda: of(22), 'load of a failed face')
    expect(of(22) == [(22, 1, 0, 0)], 'Load of an already failed face LOAD_FAILED on a later delivery')
    release(failed_again)

    # A non-ASCII family round-trips through the event as UTF-8 bytes.
    count = len(events)
    status_code, named = load(host, '20px "' + FAMILY + '"', 23)
    settle(lambda: 'named.ttf' in held, 'named face requested')
    expect(finish(held.pop('named.ttf'), font, len(font), b'font/ttf') == 0, 'Serve named face')
    settle(lambda: of(23) and len(events) >= count + 2, 'named face settles')
    drain()
    expect(of(23) == [(23, 0, 1, 0)] and events[count + 1] == (1, LOADINGDONE, [FAMILY]), 'Named family round-trips: ' + repr(events[count:]))
    release(named)

    # Cancel delivers CANCELLED synchronously; the late response adds nothing.
    status_code, held_load = load(host, '20px RvHeld', 30)
    status_code, held_ready = ready(host, 31)
    settle(lambda: 'held.ttf' in held, 'held face requested')
    expect(cancel(held_load) == 0 and of(30) == [(30, 3, 0, 0)], 'Cancel delivers CANCELLED')
    expect(release(held_ready) == 0 and of(31) == [(31, 3, 0, 0)], 'Release of a pending ready delivers CANCELLED')
    expect(finish(held.pop('held.ttf'), font, len(font), b'font/ttf') == 0, 'Serve the cancelled face')
    drain(20)
    expect(len(of(30)) == 1 and len(of(31)) == 1, 'One terminal after cancel and release')
    release(held_load)

    # Navigation invalidates pending operations and ends the watch.
    expect(load_html(host, page('2')) == 0, 'Navigate')
    update(host)
    settle(lambda: 'ahem.ttf?2' in held, 'new document requests the late face')
    status_code, nav_load = load(host, '20px RvLate', 40)
    status_code, nav_ready = ready(host, 41)
    count = len(events)
    expect(load_html(host, page('3')) == 0, 'Navigate again')
    expect(of(40) == [(40, 4, 0, 0)] and of(41) == [(41, 4, 0, 0)], 'Navigation INVALIDATED: ' + repr((of(40), of(41))))
    for name in list(held):
        finish(held.pop(name), font, len(font), b'font/ttf')
    drain(20)
    expect(len(events) == count, 'An ended watch receives nothing')
    expect(release(nav_load) == 0 and release(nav_ready) == 0, 'Release after navigation')
    inside(unwatch, watch)
    inside(unwatch, watch)
    inside(unwatch, None)

    # A new watch on the new document, then destroy.
    second = P()
    expect(load_html(host, page('4')) == 0, 'Navigate to a fourth document')
    expect(watch_of(host, event_callback, 2, ctypes.byref(second)) == 0, 'Second watch')
    update(host)
    settle(lambda: 'ahem.ttf?4' in held, 'fourth document requests the late face')
    drain()
    expect([e for e in events if e[0] == 2] == [(2, LOADING, [])], 'Second watch sees LOADING')
    status_code, doomed = load(host, '20px RvLate', 50)

    # Argument and thread guards.
    operation = U64(0)
    expect(load_of(host, b'20px RvLate', -1, None, 0, completion, 51, ctypes.byref(operation)) == -1, 'Negative font length')
    expect(ready_of(host, completion, 51, None) == -1 and watch_of(host, event_callback, 51, None) == -1, 'NULL out arguments')
    seen = []
    thread = threading.Thread(target=lambda: seen.extend([status_of(host, ctypes.byref(I())), ready_of(host, completion, 52, ctypes.byref(U64()))]))
    thread.start()
    thread.join()
    expect(seen == [-2, -2], 'Wrong thread ' + repr(seen))

    destroy(host)
    expect(of(50) == [(50, 4, 0, 0)], 'Destroy INVALIDATED: ' + repr(of(50)))
    for load_handle in held.values():
        fail(load_handle)
    drain(10)
    expect(release(doomed) == 0 and len([e for e in events if e[0] == 2]) == 1, 'Release after destroy; the ended watch is silent')
    unwatch(second)
    expect(not state['reentered'], 'No callback inside an rv_* call')
    after = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    expect(before == after, 'Runtime unchanged')
    summary = dict(assertions=assertions, cases=cases, events=events)
    if evidence_json:
        Path(evidence_json).write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print('PASS font readiness: %d assertions' % assertions, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--webkit-source', required=True)
    parser.add_argument('--evidence-json')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.webkit_source, arguments.evidence_json)
