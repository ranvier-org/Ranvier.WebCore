import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import threading

# Notifications (B09, WebCore #117) against tests/fixtures/notification-cases.json, the cases
# tests/abi/notifications_browser.mjs measures in Chromium.

CASES = Path(__file__).resolve().parents[1] / 'fixtures' / 'notification-cases.json'
NULL_ARGUMENT, WRONG_THREAD, BUFFER_TOO_SMALL, UNSUPPORTED, WRONG_INTERFACE = -1, -2, -6, -9, -11
BUBBLES, CANCELABLE, TRUSTED = 1, 2, 16
DEFAULT, DENIED, GRANTED = 0, 1, 2
SHOW, CANCEL, DESTROYED = 0, 1, 2
EVENT_SHOW, EVENT_CLICK, EVENT_CLOSE, EVENT_ERROR = 0, 1, 2, 3
PERMISSIONS = {DEFAULT: 'default', DENIED: 'denied', GRANTED: 'granted'}
DIRS = {0: 'auto', 1: 'ltr', 2: 'rtl'}


class Options(ctypes.Structure):
    _fields_ = [('size', ctypes.c_int32), ('dir', ctypes.c_int32), ('silent', ctypes.c_int32), ('body_length', ctypes.c_int32),
                ('tag_length', ctypes.c_int32), ('lang_length', ctypes.c_int32), ('icon_length', ctypes.c_int32),
                ('reserved', ctypes.c_int32), ('body', ctypes.c_char_p), ('tag', ctypes.c_char_p), ('lang', ctypes.c_char_p),
                ('icon', ctypes.c_char_p)]


def options(body=None, tag=None, lang=None, icon=None, dir=0, silent=-1):
    value = Options()
    value.size, value.dir, value.silent = ctypes.sizeof(Options), dir, silent
    for name, text in (('body', body), ('tag', tag), ('lang', lang), ('icon', icon)):
        data = None if text is None else text.encode('utf-8')
        setattr(value, name, data)
        setattr(value, name + '_length', -1 if data is None else len(data))
    return value


def verify(directory, evidence_json=None):
    directory = Path(directory).resolve()
    before = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    print('RUNTIME_BEFORE=' + json.dumps(before, sort_keys=True), flush=True)
    if sys.platform == 'win32':
        os.add_dll_directory(str(directory))
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer = ctypes.c_void_p, ctypes.c_int32
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

    expect(bind('rv_abi_has', integer, [ctypes.c_char_p])(b'notifications') == 1, 'notifications feature')
    Presenter = ctypes.CFUNCTYPE(None, pointer, pointer, pointer, integer)
    EventCallback = ctypes.CFUNCTYPE(integer, pointer, pointer)
    create = bind('rv_host_create', pointer, [integer, integer])
    destroy = bind('rv_host_destroy', None, [pointer])
    load_html = bind('rv_host_load_html', integer, [pointer, ctypes.c_char_p])
    set_presenter = bind('rv_host_set_notification_presenter', integer, [pointer, Presenter, pointer])
    set_permission = bind('rv_host_set_notification_permission', integer, [pointer, integer])
    permission_raw = bind('rv_host_notification_permission', integer, [pointer, ctypes.POINTER(integer)])
    create_raw = bind('rv_notification_create', integer, [pointer, ctypes.c_char_p, integer, ctypes.POINTER(Options), ctypes.POINTER(pointer)])
    close = bind('rv_notification_close', integer, [pointer])
    report = bind('rv_notification_report', integer, [pointer, integer])
    string_raw = bind('rv_notification_string', integer, [pointer, integer, ctypes.c_char_p, integer, ctypes.POINTER(integer)])
    flags_raw = bind('rv_notification_flags', integer, [pointer, ctypes.POINTER(integer), ctypes.POINTER(integer)])
    target_release = bind('rv_event_target_release', None, [pointer])
    target_retain = bind('rv_event_target_retain', pointer, [pointer])
    target_equals = bind('rv_event_target_equals', integer, [pointer, pointer])
    create_target = bind('rv_host_create_event_target', pointer, [pointer])
    add_listener = bind('rv_event_target_add_listener', pointer, [pointer, ctypes.c_char_p, integer, EventCallback, pointer])
    remove_listener = bind('rv_listener_remove', integer, [pointer])
    event_flags = bind('rv_event_flags', integer, [pointer])
    event_type = bind('rv_event_type', integer, [pointer, ctypes.c_char_p, integer, ctypes.POINTER(integer)])
    capability_number = bind('rv_host_capability_value_number', integer, [pointer, integer, ctypes.c_char_p, ctypes.POINTER(ctypes.c_double)])
    cycle = bind('rv_run_loop_cycle', integer, [integer])

    requests = []
    keep = []
    listeners = []
    events = []
    in_call = [False]
    actions = {}

    def present(context, host, target, request):
        expect(not in_call[0], 'Presenter runs only inside rv_run_loop_cycle')
        requests.append((target_retain(target), request))
        for event in actions.get(request, []):
            expect(report(target, event) == 0, 'report from the presenter')
    presenter = Presenter(present)

    def call(function, *arguments):
        in_call[0] = True
        try:
            return function(*arguments)
        finally:
            in_call[0] = False

    def drain(until=None):
        # Runs the loop until the condition holds, raising after a hang guard, then a fixed settle for late extras.
        if until is not None:
            for _ in range(400):
                if until():
                    break
                cycle(5)
            else:
                raise AssertionError('Run loop did not reach the expected state: ' + repr(events) + repr(requests))
        for _ in range(10):
            cycle(5)

    def new(host, title, value=None):
        out = pointer()
        status = call(create_raw, host, None if title is None else title.encode('utf-8'),
                      -1 if title is None else len(title.encode('utf-8')), None if value is None else ctypes.byref(value), ctypes.byref(out))
        expect(status == 0 and bool(out.value), 'rv_notification_create ' + str(status))
        return out.value

    def listen(target):
        for kind in ('show', 'error', 'click', 'close'):
            def run(context, event, kind=kind):
                buffer, length = ctypes.create_string_buffer(16), integer(0)
                expect(event_type(event, buffer, 16, ctypes.byref(length)) == 0, 'event type')
                flags = event_flags(event)
                events.append([buffer.raw[:length.value].decode(), bool(flags & BUBBLES), bool(flags & CANCELABLE), bool(flags & TRUSTED)])
                return 0
            callback = EventCallback(run)
            keep.append(callback)
            handle = add_listener(target, kind.encode(), 0, callback, None)
            expect(bool(handle), 'listener ' + kind)
            listeners.append(handle)

    def text(target, field):
        length = integer(-1)
        expect(string_raw(target, field, None, 0, ctypes.byref(length)) in (0, BUFFER_TOO_SMALL), 'string length')
        buffer = ctypes.create_string_buffer(max(length.value, 1))
        expect(string_raw(target, field, buffer, length.value, ctypes.byref(length)) == 0, 'string read')
        return buffer.raw[:length.value].decode('utf-8')

    def fields(target):
        dir, silent = integer(-9), integer(-9)
        expect(flags_raw(target, ctypes.byref(dir), ctypes.byref(silent)) == 0, 'flags')
        return {'title': text(target, 0), 'body': text(target, 1), 'tag': text(target, 2), 'lang': text(target, 3),
                'dir': DIRS[dir.value], 'silent': None if silent.value == -1 else bool(silent.value), 'icon': text(target, 4)}

    def permission(host):
        value = integer(-9)
        expect(permission_raw(host, ctypes.byref(value)) == 0, 'permission read')
        return PERMISSIONS[value.value]

    def presenter_value(host):
        value = ctypes.c_double(-9)
        expect(capability_number(host, 4, b'notification-presenter', ctypes.byref(value)) == 0, 'presenter facility')
        return value.value

    host = create(64, 64)
    expect(load_html(host, b'<p>notify</p>') == 0, 'load')
    measured['default-permission'] = permission(host)
    expect(presenter_value(host) == 0.0, 'No presenter at creation')

    # A show without permission fires error and never reaches a presenter.
    expect(set_presenter(host, presenter, None) == 0, 'presenter set')
    expect(presenter_value(host) == 1.0, 'Presenter facility')
    first = new(host, 'T', options(body='B'))
    listen(first)
    drain(lambda: len(events) >= 1)
    measured['show-without-permission'] = list(events)
    expect(requests == [], 'Denied show reaches no presenter ' + repr(requests))
    expect(set_permission(host, DENIED) == 0 and permission(host) == 'denied', 'denied permission')
    events.clear()
    second = new(host, 'T')
    listen(second)
    drain(lambda: len(events) >= 1)
    expect(events == [['error', False, False, True]] and requests == [], 'Denied permission errors ' + repr(events) + repr(requests))

    # Fields and defaults.
    expect(set_permission(host, GRANTED) == 0 and permission(host) == 'granted', 'granted permission ' + permission(host) + ' default was ' + str(measured))
    expect(set_presenter(host, Presenter(), None) == 0, 'presenter removed')
    rich = new(host, 'Title é', options(body='Body', tag='t1', lang='en-GB', icon='https://example.test/icons/a.png', dir=2, silent=1))
    measured['fields'] = fields(rich)
    relative = new(host, 'R', options(icon='icons/a.png'))
    expect(text(relative, 4) == '', 'A relative icon has no base URL to resolve against')
    empty = new(host, None)
    measured['defaults'] = fields(empty)
    events.clear()
    listen(rich)
    drain(lambda: len(events) >= 1)
    expect(events == [['error', False, False, True]], 'Granted show without a presenter errors ' + repr(events))
    out = pointer()
    measured['bad-dir'] = 'unsupported' if call(create_raw, host, b'a', 1, ctypes.byref(options(dir=5)), ctypes.byref(out)) == UNSUPPORTED else 'accepted'
    wrong = options()
    wrong.size = 8
    expect(call(create_raw, host, b'a', 1, ctypes.byref(wrong), ctypes.byref(out)) == UNSUPPORTED, 'Wrong options size')
    expect(set_permission(host, 3) == UNSUPPORTED, 'Unknown permission')

    # A presented notification: show, click, then close after the cancel request.
    expect(set_presenter(host, presenter, None) == 0, 'presenter set again')
    events.clear()
    requests.clear()
    actions[SHOW] = [EVENT_SHOW, EVENT_CLICK]
    actions[CANCEL] = [EVENT_CLOSE]
    shown = new(host, 'Shown', options(tag='t2'))
    listen(shown)
    expect(requests == [], 'Create delivers no request')
    drain(lambda: len(requests) >= 1 and len(events) >= 2)
    expect([request for _, request in requests] == [SHOW] and target_equals(requests[0][0], shown) == 1, 'Show request ' + repr(requests))
    expect(call(close, shown) == 0 and len(requests) == 1, 'Close delivers no request inside the call')
    drain(lambda: len(requests) >= 2 and len(events) >= 3)
    measured['show-granted'] = list(events)
    expect([request for _, request in requests] == [SHOW, CANCEL], 'Cancel request ' + repr(requests))
    expect(call(close, shown) == 0, 'second close')
    drain()
    expect(len(requests) == 2 and len(events) == 3, 'A closed notification requests and dispatches nothing more')

    # Replacing the document destroys its notifications; their reports dispatch nothing.
    actions.clear()
    events.clear()
    requests.clear()
    kept = new(host, 'Kept')
    listen(kept)
    drain(lambda: len(requests) >= 1)
    expect(call(load_html, host, b'<p>next</p>') == 0, 'replace document')
    drain(lambda: any(request == DESTROYED for _, request in requests))
    mine = [request for target, request in requests if target_equals(target, kept) == 1]
    expect(mine == [SHOW, DESTROYED], 'Destroyed request ' + repr(mine))
    expect(all(request == DESTROYED for target, request in requests if target_equals(target, kept) != 1), 'Every other notification of the document is destroyed')
    expect(report(kept, EVENT_CLICK) == 0, 'report after teardown')
    drain()
    expect(events == [], 'A stopped notification dispatches nothing ' + repr(events))
    expect(text(kept, 0) == 'Kept', 'Fields stay readable after teardown')

    # Argument, interface and thread errors.
    plain = create_target(host)
    dir, silent, length = integer(), integer(), integer()
    expect(close(plain) == WRONG_INTERFACE and report(plain, 0) == WRONG_INTERFACE, 'close and report of another target')
    expect(flags_raw(plain, ctypes.byref(dir), ctypes.byref(silent)) == WRONG_INTERFACE, 'flags of another target')
    expect(string_raw(plain, 0, None, 0, ctypes.byref(length)) == WRONG_INTERFACE, 'string of another target')
    target_release(plain)
    expect(report(kept, 9) == UNSUPPORTED and string_raw(kept, 9, None, 0, ctypes.byref(length)) == UNSUPPORTED, 'unknown event and field')
    expect(create_raw(None, b'a', 1, None, ctypes.byref(out)) == NULL_ARGUMENT and create_raw(host, b'a', 1, None, None) == NULL_ARGUMENT, 'null create')
    expect(close(None) == NULL_ARGUMENT and permission_raw(host, None) == NULL_ARGUMENT, 'null arguments')
    seen = []
    thread = threading.Thread(target=lambda: seen.extend([create_raw(host, b'a', 1, None, ctypes.byref(pointer())), close(kept), report(kept, 0),
                                                          set_permission(host, GRANTED), set_presenter(host, presenter, None)]))
    thread.start()
    thread.join()
    expect(seen == [WRONG_THREAD] * 5, 'Wrong thread ' + repr(seen))

    # Host destruction drops pending requests; a presenter may destroy its host.
    requests.clear()
    pending = new(host, 'Pending')
    for handle in listeners:
        expect(remove_listener(handle) == 0, 'listener removal')
    listeners.clear()
    destroy(host)
    drain()
    expect(requests == [], 'Destroy drops pending requests')
    expect(text(pending, 0) == 'Pending', 'A notification stays readable after host destroy')
    other = create(64, 64)
    expect(set_permission(other, GRANTED) == 0, 'second host permission')

    def destroying(context, host, target, request):
        requests.append((target_retain(target), request))
        destroy(host)
    destroyer = Presenter(destroying)
    expect(set_presenter(other, destroyer, None) == 0, 'destroying presenter')
    doomed = [new(other, 'A'), new(other, 'B')]
    drain(lambda: len(requests) >= 1)
    expect([request for _, request in requests] == [SHOW], 'Delivery stops at a destroyed host ' + repr(requests))
    for target in [first, second, rich, relative, empty, shown, kept, pending, *doomed] + [target for target, _ in requests]:
        target_release(target)

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
    print('PASS notifications: %d assertions' % assertions, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence-json')
    arguments = parser.parse_args()
    verify(arguments.native_directory, arguments.evidence_json)
