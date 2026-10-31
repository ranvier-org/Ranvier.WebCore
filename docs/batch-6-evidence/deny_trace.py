"""Cause of the one-cycle-later pointerlockerror after a denied pointer-lock request (batch 6, patch 0052).
usage: deny_trace.py <runtime dir with pdbs> [trace]
Runs the I03 sequence of tests/NativeApi.Conformance/Native.fs (a no-gesture refusal, then a gesture request the app
denies) and calls only rv_run_loop_cycle(0) after the denial, recording the cycle on which pointerlockerror arrives
(bounded at 200 cycles). With 'trace', hardware breakpoints (vm1's hwtrace) count, per phase, the unhandled-rejection
tracker, checkpoint tasks queued by 0052, event-loop schedules and event-loop runs."""
import ctypes
import json
import os
from pathlib import Path
import sys

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / 'tests/abi'))
from pointer_support import Harness, CALLBACK, OK, DOM_EXCEPTION, BUTTON_NONE, BUTTON_LEFT, i32, p  # noqa: E402

runtime = sys.argv[1]
trace = 'trace' in sys.argv[2:]
tracer = None
if trace:
    sys.path.insert(0, 'C:/wk/vm1-artifacts/probe')
    import hwtrace
    tracer = hwtrace.Tracer(runtime + ';C:/wk/build-win-slim/bin')
    names = [('RejectedPromiseTracker::promiseRejected', 'WebCore!WebCore::RejectedPromiseTracker::promiseRejected'),
             ('runAtEndOfMicrotaskCheckpoint', 'WebCore!WebCore::EventLoopTaskGroup::runAtEndOfMicrotaskCheckpoint'),
             ('EventLoop::scheduleToRunIfNeeded', 'WebCore!WebCore::EventLoop::scheduleToRunIfNeeded'),
             ('EventLoop::run', 'WebCore!WebCore::EventLoop::run')]
    armed = []
    for label, name in names:
        try:
            armed.append((label, tracer.address(name)))
        except Exception as error:  # a symbol the build inlined
            print('no symbol', name, error, file=sys.stderr)
    tracer.arm(armed)
mark = (lambda text: tracer.mark(text)) if tracer else (lambda text: None)

first = None
if 'first' in sys.argv[2:]:
    # The I03 Views run keeps the shared fixture's host alive, after a granted lock and an exit on it.
    first = Harness(runtime)
    first.open(b'<!doctype html><style>html,body{margin:0}#t{position:absolute;left:0;top:0;width:100px;height:100px}</style>'
               b'<body><div id=t></div>', ['pointerlockerror', 'pointerlockchange'])
    first.set_focused(first.host, 1)
    ft = first.node('#t')
    first_request = first.bind('rv_element_request_pointer_lock', i32, [p, i32])
    first_down = CALLBACK(lambda context, event: first_request(ft, 0) or 0)
    first.add_listener(ft, b'mousedown', 0, first_down, None)
    for action, buttons, count in ((0, BUTTON_NONE, 0), (1, BUTTON_LEFT, 1), (2, BUTTON_LEFT, 1)):
        first.mouse(first.host, action, 50, 50, buttons, count, 0)
    first.bind('rv_host_pointer_lock_resolve', i32, [p, i32])(first.host, 1)
    first.drain()
    first.bind('rv_document_exit_pointer_lock', i32, [p])(first.document)
    first.drain()
h = Harness(runtime)
b = h.bind
resolve = b('rv_host_pointer_lock_resolve', i32, [p, i32])
request = b('rv_element_request_pointer_lock', i32, [p, i32])
h.open(b'<!doctype html><style>html,body{margin:0}#t{position:absolute;left:0;top:0;width:100px;height:100px}</style>'
       b'<body><div id=t></div>', ['pointerlockerror', 'pointerlockchange'])
h.expect(h.set_focused(h.host, 1) == OK, 'focus host')
t = h.node('#t')
statuses = []
down = CALLBACK(lambda context, event: statuses.append(request(t, 0)) or 0)
h.add_listener(t, b'mousedown', 0, down, None)


def errors():
    return [e['type'] for e in h.log if e['type'] == 'pointerlockerror']


result = {'runtime': runtime}
mark('no-gesture request')
result['noGesture'] = request(t, 0) == DOM_EXCEPTION
h.drain()
h.log = []
mark('click')
for action, buttons, count in ((0, BUTTON_NONE, 0), (1, BUTTON_LEFT, 1), (2, BUTTON_LEFT, 1)):
    h.mouse(h.host, action, 50, 50, buttons, count, 0)
result['gestureStatuses'] = statuses
mark('deny')
result['deny'] = resolve(h.host, 0)
import time
cycles, started, durations = 0, time.perf_counter(), []
while not errors() and cycles < 200:
    mark(f'cycle {cycles + 1}')
    before = time.perf_counter()
    h.run_loop(0)
    durations.append(round((time.perf_counter() - before) * 1000, 2))
    cycles += 1
result['cyclesUntilPointerlockerror'] = cycles if errors() else None
result['millisecondsUntilPointerlockerror'] = round((time.perf_counter() - started) * 1000, 2)
result['cycleMilliseconds'] = durations
result['events'] = [e['type'] for e in h.log]
if tracer:
    tracer.enabled = False
    hits = {}
    for label, extra, stack, m in tracer.hits:
        key = (tracer.marks[m - 1] if m else '-') + ' | ' + label
        hits[key] = hits.get(key, 0) + 1
    result['hits'] = hits
    lines = tracer.report(frames=12, skip=('hwtrace', 'KiUserExceptionDispatcher', 'RtlDispatchException', 'ntdll!', '_ctypes', 'python', 'libffi'))
    Path(os.environ.get('DENY_STACKS', os.devnull)).write_text('\n'.join(lines[:3000]), encoding='utf-8')
print(json.dumps(result, indent=1))
