import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import threading

# Screen wake locks (B10, WebCore #118) against tests/fixtures/wake-lock-cases.json, the cases
# tests/abi/wake_lock_browser.mjs measures in Chromium.

CASES = Path(__file__).resolve().parents[1] / 'fixtures' / 'wake-lock-cases.json'
DOM_EXCEPTION, NULL_ARGUMENT, WRONG_THREAD, WRONG_INTERFACE = -3, -1, -2, -11
BUBBLES, CANCELABLE, TRUSTED = 1, 2, 16


def verify(directory, evidence_json=None):
    directory = Path(directory).resolve()
    before = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    print('RUNTIME_BEFORE=' + json.dumps(before, sort_keys=True), flush=True)
    if sys.platform == 'win32':
        os.add_dll_directory(str(directory))
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer, u64 = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint64
    fixture = json.loads(CASES.read_text(encoding='utf-8'))['cases']
    assertions = 0
    measured = {}

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
    expect(has(b'wake-locks') == 1, 'wake-locks feature')
    Policy = ctypes.CFUNCTYPE(integer, pointer, pointer, integer)
    SleepCallback = ctypes.CFUNCTYPE(None, pointer, u64, integer, ctypes.c_char_p, integer)
    EventCallback = ctypes.CFUNCTYPE(integer, pointer, pointer)
    set_sleep_callback = bind('rv_set_sleep_disabler_callback', integer, [SleepCallback, pointer])
    sleep_log = []

    def on_sleep(context, identifier, display, reason, held):
        sleep_log.append((identifier, display, reason.decode('utf-8') if reason else None, held))
    sleep_callback = SleepCallback(on_sleep)
    expect(set_sleep_callback(sleep_callback, None) == WRONG_THREAD, 'Sleep callback before the first host')

    create = bind('rv_host_create', pointer, [integer, integer])
    destroy = bind('rv_host_destroy', None, [pointer])
    load_html_bytes = bind('rv_host_load_html', integer, [pointer, ctypes.c_char_p, ctypes.c_int32])  # utf8 bytes and length (#145)
    load_html = lambda a0, a1: load_html_bytes(a0, a1, -1 if a1 is None else len(a1))  # utf8 length
    set_visible = bind('rv_host_set_visible', integer, [pointer, integer])
    set_policy = bind('rv_host_set_wake_lock_policy', integer, [pointer, Policy, pointer])
    request_raw = bind('rv_wake_lock_request', integer, [pointer, integer, ctypes.POINTER(pointer)])
    release = bind('rv_wake_lock_release', integer, [pointer])
    state_raw = bind('rv_wake_lock_state', integer, [pointer, ctypes.POINTER(integer), ctypes.POINTER(integer)])
    release_all = bind('rv_host_release_wake_locks', integer, [pointer])
    target_release = bind('rv_event_target_release', None, [pointer])
    target_equals = bind('rv_event_target_equals', integer, [pointer, pointer])
    create_target = bind('rv_host_create_event_target', pointer, [pointer])
    add_listener_bytes = bind('rv_event_target_add_listener', pointer, [pointer, ctypes.c_char_p, ctypes.c_int32, integer, EventCallback, pointer])  # utf8 bytes and length (#145)
    add_listener = lambda a0, a1, a2, a3, a4: add_listener_bytes(a0, a1, -1 if a1 is None else len(a1), a2, a3, a4)  # utf8 length
    remove_listener = bind('rv_listener_remove', integer, [pointer])
    event_flags = bind('rv_event_flags', integer, [pointer])
    event_type = bind('rv_event_type', integer, [pointer, ctypes.c_char_p, integer, ctypes.POINTER(integer)])
    event_target = bind('rv_event_get_target', pointer, [pointer, integer])
    last_exception = bind('rv_last_exception', integer, [integer, ctypes.c_char_p, integer, ctypes.POINTER(integer)])
    capability_fact = bind('rv_host_capability_fact', integer, [pointer, integer, ctypes.c_char_p, integer, ctypes.POINTER(integer)])
    capability_number = bind('rv_host_capability_value_number', integer, [pointer, integer, ctypes.c_char_p, ctypes.POINTER(ctypes.c_double)])
    cycle = bind('rv_run_loop_cycle', integer, [integer])

    def exception_name():
        buffer, length = ctypes.create_string_buffer(256), integer(0)
        expect(last_exception(0, buffer, 256, ctypes.byref(length)) == 0, 'rv_last_exception')
        return buffer.raw[:length.value].decode('utf-8')

    def request(host, kind=0):
        out = pointer(1)
        status = request_raw(host, kind, ctypes.byref(out))
        if status == 0:
            expect(bool(out.value), 'Granted request writes a sentinel')
            return out.value
        expect(status == DOM_EXCEPTION and out.value is None, 'Failed request status ' + str(status))
        return exception_name()

    def state(sentinel):
        released, kind = integer(-1), integer(-1)
        expect(state_raw(sentinel, ctypes.byref(released), ctypes.byref(kind)) == 0, 'rv_wake_lock_state')
        expect(kind.value == 0, 'Sentinel type is screen')
        return released.value

    def facility(host, name):
        implemented, value = integer(-9), ctypes.c_double(-9)
        expect(capability_fact(host, 4, name, 1, ctypes.byref(implemented)) == 0, 'capability fact ' + name.decode())
        expect(capability_number(host, 4, name, ctypes.byref(value)) == 0, 'capability value ' + name.decode())
        return implemented.value, value.value

    log = []
    keep = []
    listeners = []

    def listen(sentinel, label, record_event=False):
        def run(context, event):
            if record_event:
                buffer, length = ctypes.create_string_buffer(32), integer(0)
                expect(event_type(event, buffer, 32, ctypes.byref(length)) == 0, 'event type')
                flags = event_flags(event)
                target = event_target(event, 0)
                same = target_equals(target, sentinel) == 1
                target_release(target)
                log.append([label, buffer.raw[:length.value].decode(), bool(flags & BUBBLES), bool(flags & CANCELABLE), bool(flags & TRUSTED), same])
            else:
                log.append([label])
            return 0
        callback = EventCallback(run)
        keep.append(callback)
        handle = add_listener(sentinel, b'release', 0, callback, None)
        expect(bool(handle), 'listener ' + label)
        listeners.append(handle)

    host = create(64, 64)
    expect(bool(host), 'Host created')
    expect(set_sleep_callback(sleep_callback, None) == 0, 'Sleep callback set')
    expect(load_html(host, b'<p>wake</p>') == 0, 'load')
    expect(facility(host, b'screen-wake-lock') == (1, 0.0), 'Policy facility without a policy')
    expect(facility(host, b'sleep-disabler-callback') == (1, 1.0), 'Sleep callback facility')

    # No policy denies, as an ungranted browser does.
    measured['ungranted-request'] = request(host)
    calls = []

    def decide(context, decided_host, kind):
        calls.append((decided_host, kind))
        return verdict[0]
    verdict = [0]
    policy = Policy(decide)
    expect(set_policy(host, policy, None) == 0, 'Policy set')
    expect(facility(host, b'screen-wake-lock') == (1, 1.0), 'Policy facility with a policy')
    expect(request(host) == 'NotAllowedError' and calls == [(host, 0)], 'Denying policy ' + repr(calls))
    calls.clear()
    measured['unknown-type'] = request(host, 1)
    expect(calls == [], 'An unknown type never reaches the policy')
    verdict[0] = 1

    # Request, release and the release event.
    a = request(host)
    b = request(host)
    measured['default-type'] = 'screen' if state(b) == 0 else 'released'
    measured['distinct-sentinels'] = target_equals(a, b) == 0
    expect(calls == [(host, 0), (host, 0)], 'Policy runs per request')
    displays = [entry for entry in sleep_log if entry[3] == 1]
    expect(len(displays) == 1 and displays[0][1:] == (1, 'Screen Wake Lock', 1), 'One display disabler ' + repr(sleep_log))
    listen(a, 'a-on', True)
    listen(a, 'a-listener')
    listen(b, 'b-listener')
    expect(release(a) == 0, 'release a')
    log.append(['after-release-call', state(a) == 1])
    cycle(0)
    log.append(['after-await', state(a) == 1])
    expect(release(a) == 0, 'second release a')
    log.append(['second-release', state(a) == 1])
    expect(len(sleep_log) == 1, 'b still holds the display ' + repr(sleep_log))
    expect(release(b) == 0, 'release b')
    measured['release-log'] = [list(entry) for entry in log]
    expect(len(sleep_log) == 2 and sleep_log[1][0] == sleep_log[0][0] and sleep_log[1][3] == 0, 'Display disabler ends ' + repr(sleep_log))
    for sentinel in (a, b):
        target_release(sentinel)

    # Application revocation releases in acquisition order.
    log.clear()
    sleep_log.clear()
    a, b = request(host), request(host)
    listen(a, 'a')
    listen(b, 'b')
    expect(release_all(host) == 0, 'release all')
    expect(log == [['a'], ['b']] and state(a) == 1 and state(b) == 1, 'Revocation order ' + repr(log))
    expect([entry[3] for entry in sleep_log] == [1, 0], 'Revocation ends the display disabler ' + repr(sleep_log))
    for sentinel in (a, b):
        target_release(sentinel)

    # A hidden page releases its locks and refuses requests.
    log.clear()
    a, b = request(host), request(host)
    listen(a, 'a')
    listen(b, 'b')
    expect(set_visible(host, 0) == 0, 'hide')
    cycle(0)
    measured['hidden-release'] = [[label, 'release'] for [label] in log]
    calls.clear()
    measured['hidden-request'] = request(host)
    expect(calls == [], 'A hidden request never reaches the policy')
    expect(set_visible(host, 1) == 0, 'show')
    c = request(host)
    expect(state(c) == 0, 'Visible again grants')
    expect(release(c) == 0, 'release c')
    for sentinel in (a, b, c):
        target_release(sentinel)

    # Replacing the document releases its locks with no event.
    log.clear()
    sleep_log.clear()
    a = request(host)
    listen(a, 'a')
    expect(load_html(host, b'<p>next</p>') == 0, 'replace document')
    cycle(0)
    measured['document-teardown'] = {'released': state(a) == 1, 'events': [entry[0] for entry in log]}
    expect([entry[3] for entry in sleep_log] == [1, 0], 'Teardown ends the display disabler ' + repr(sleep_log))
    expect(release(a) == 0 and log == [], 'Release after teardown dispatches nothing')
    target_release(a)

    # Argument, interface and thread errors.
    plain = create_target(host)
    released, kind = integer(-1), integer(-1)
    expect(state_raw(plain, ctypes.byref(released), ctypes.byref(kind)) == WRONG_INTERFACE, 'state of another target')
    expect(release(plain) == WRONG_INTERFACE, 'release of another target')
    target_release(plain)
    expect(request_raw(None, 0, ctypes.byref(pointer())) == NULL_ARGUMENT, 'request without host')
    expect(request_raw(host, 0, None) == NULL_ARGUMENT, 'request without output')
    expect(release(None) == NULL_ARGUMENT and state_raw(None, ctypes.byref(released), ctypes.byref(kind)) == NULL_ARGUMENT, 'null sentinel')
    expect(set_policy(None, policy, None) == NULL_ARGUMENT and release_all(None) == NULL_ARGUMENT, 'null host')
    seen = []
    thread = threading.Thread(target=lambda: seen.extend([request_raw(host, 0, ctypes.byref(pointer())), release_all(host),
                                                          set_policy(host, policy, None), set_sleep_callback(sleep_callback, None)]))
    thread.start()
    thread.join()
    expect(seen == [WRONG_THREAD] * 4, 'Wrong thread ' + repr(seen))

    # Host destruction releases with no event; the sentinel stays valid.
    log.clear()
    sleep_log.clear()
    a = request(host)
    listen(a, 'a')
    for handle in listeners:
        expect(remove_listener(handle) == 0, 'listener removal')
    listeners.clear()
    destroy(host)
    expect(state(a) == 1 and release(a) == 0 and log == [], 'Destroyed host releases silently')
    expect([entry[3] for entry in sleep_log] == [1, 0], 'Destroy ends the display disabler ' + repr(sleep_log))
    target_release(a)

    # Without a callback, later disablers are not reported.
    expect(set_sleep_callback(SleepCallback(), None) == 0, 'Sleep callback removed')
    sleep_log.clear()
    host = create(64, 64)
    expect(set_policy(host, policy, None) == 0, 'Policy on a new host')
    expect(load_html(host, b'<p>again</p>') == 0, 'load again')
    a = request(host)
    expect(release(a) == 0 and sleep_log == [], 'Unreported disablers ' + repr(sleep_log))
    expect(facility(host, b'sleep-disabler-callback') == (1, 0.0), 'Sleep callback facility after removal')
    target_release(a)
    destroy(host)

    for name, value in measured.items():
        expected = fixture[name]['native']
        if expected is not None:
            expect(value == expected, name + ' ' + repr(value) + ' != ' + repr(expected))
    after = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    expect(before == after, 'Runtime unchanged')
    summary = dict(assertions=assertions, measured=measured,
                   qualified=sorted(name for name, case in fixture.items() if 'qualification' in case))
    if evidence_json:
        Path(evidence_json).write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print('PASS wake locks: %d assertions' % assertions, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence-json')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.evidence_json)
