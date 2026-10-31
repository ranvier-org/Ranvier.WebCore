"""Event-loop task latency probe: a task queued by an rv_* call runs on the next rv_run_loop_cycle, also after a style
resolution from the style-recalc timer has queued a C++ microtask (speculation rules) while VM entry is disallowed.
The sequence is the Views I03 denial: a pointer-lock request without a gesture is refused and the element's style
changes, then after a gesture the app denies a request, without a drain in between. Each pointerlockerror must arrive on the first turn after the call that queued it.
The turn count and elapsed time of each delivery are recorded; a hang guard bounds the wait at 10 s."""
import argparse
import ctypes
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pointer_support import Harness, CALLBACK, OK, DOM_EXCEPTION, BUTTON_NONE, BUTTON_LEFT, i32, p  # noqa: E402

PAGE = (b'<!doctype html><style>html,body{margin:0}#t{position:absolute;left:0;top:0;width:100px;height:100px}</style>'
        b'<body><div id=t></div>')
STYLE = b'left:1px'


def verify(directory, evidence):
    h = Harness(directory)
    b = h.bind
    request = b('rv_element_request_pointer_lock', i32, [p, i32])
    resolve = b('rv_host_pointer_lock_resolve', i32, [p, i32])
    set_attribute = b('rv_element_set_attribute', i32, [p, ctypes.c_char_p, ctypes.c_char_p, i32])
    h.open(PAGE, ['pointerlockerror'])
    h.expect(h.set_focused(h.host, 1) == OK, 'focus host')
    target = h.node('#t')

    def turns_until_error():
        turns, started = 0, time.perf_counter()
        while not [e for e in h.log if e['type'] == 'pointerlockerror']:
            if time.perf_counter() - started > 10:
                raise AssertionError('pointerlockerror not delivered within 10 s')
            h.run_loop(0)
            turns += 1
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        h.log = []
        return turns, elapsed

    deliveries = {}
    # The refusal's task arms the event loop before the style change arms the style-recalc timer, so the turn runs the
    # task first, then resolves style from the timer.
    h.expect(request(target, 0) == DOM_EXCEPTION, 'no gesture: refused')
    h.expect(set_attribute(target, b'style', STYLE, len(STYLE)) == OK, 'style changed')
    deliveries['refusal'] = turns_until_error()
    statuses = []
    down = CALLBACK(lambda context, event: statuses.append(request(target, 0)) or 0)
    listener = h.add_listener(target, b'mousedown', 0, down, None)
    for action, buttons, count in ((0, BUTTON_NONE, 0), (1, BUTTON_LEFT, 1), (2, BUTTON_LEFT, 1)):
        h.mouse(h.host, action, 50, 50, buttons, count, 0)
    h.expect(statuses == [OK], 'gesture request pending')
    h.expect(resolve(h.host, 0) == OK, 'deny')
    deliveries['denial'] = turns_until_error()
    measured = {name: {'turns': turns, 'milliseconds': ms} for name, (turns, ms) in deliveries.items()}
    print('MEASURED', json.dumps(measured), flush=True)
    for name, (turns, _) in deliveries.items():
        h.expect(turns == 1, name + ': pointerlockerror on the first turn')
    h.expect(h.listener_remove(listener) == OK, 'gesture listener removed')
    h.node_release(target)
    h.close()
    h.finish()
    result = {'deliveries': measured, 'checks': h.checks}
    if evidence:
        Path(evidence).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f'PASS event loop latency: {h.checks} assertions', json.dumps(result['deliveries']), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence-json')
    options = parser.parse_args()
    verify(options.native_directory, options.evidence_json)
