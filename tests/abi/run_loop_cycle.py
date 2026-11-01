"""Run-loop cycle probe against an actual runtime directory: rv_run_loop_cycle(0) runs one pass of the host thread's
run loop and returns without waiting for a source, on every platform, and delivers the engine tasks due at its entry:
a queued popover toggle event runs in the first zero-millisecond cycle after it is due. A zero-millisecond cycle that
waits keeps a host's timers and idle periods from running on time (WebCore#155). Also checks the elapsed time of a
bounded cycle, the cycle count, and the argument and thread errors."""

import argparse
import ctypes
from pathlib import Path
import statistics
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, Case, I, P

WRONG_THREAD, UNSUPPORTED = -2, -9
ABI = 59
SAMPLES = 21
# A pass with nothing pending takes microseconds; the Cocoa RunLoop::cycle() wait is 50 ms.
ZERO_CYCLE_LIMIT_MS = 10.0
BOUNDED_MS = 20
TOGGLES = 20
CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p)


def timed(cycle, milliseconds):
    start = time.perf_counter()
    cycles = cycle(milliseconds)
    return cycles, (time.perf_counter() - start) * 1000.0


def queued_tasks(native, cycle):
    """Each showPopover/hidePopover queues a toggle event task; one cycle(0) after it is due delivers it."""
    case = Case(native, '<div id=p popover>x</div>')
    target = native.bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p, I])(case.host, b'p', 1)
    native.expect(bool(target), 'popover element')
    toggles = []
    callback = CALLBACK(lambda event, data: toggles.append(1) or 0)
    listener = native.bind('rv_node_add_event_listener', P, [P, ctypes.c_char_p, I, I, CALLBACK, P])(target, b'toggle', 6, 0, callback, None)
    native.expect(bool(listener), 'toggle listener')
    case.listeners.append(listener)
    show = native.bind('rv_dom_html_element_show_popover', I, [P, P])
    hide = native.bind('rv_dom_html_element_hide_popover', I, [P])
    cycle(20)
    for index in range(TOGGLES):
        before = len(toggles)
        native.expect((show(target, None) if index % 2 == 0 else hide(target)) == 0, f'toggle {index} status')
        time.sleep(0.002)
        cycle(0)
        native.expect(len(toggles) == before + 1, f'toggle {index}: task not delivered by the first cycle(0) after it was due')
    native.bind('rv_node_release', None, [P])(target)
    case.close()


def verify(native_directory):
    native = Native(native_directory)
    native.expect(native.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
    cycle = native.bind('rv_run_loop_cycle', I, [I])
    case = Case(native, '<p>x</p>')
    for _ in range(5):
        cycle(0)

    zero = []
    for _ in range(SAMPLES):
        cycles, elapsed = timed(cycle, 0)
        native.expect(cycles == 1, f'zero-millisecond cycle count {cycles} != 1')
        zero.append(elapsed)
    median = statistics.median(zero)
    native.expect(median < ZERO_CYCLE_LIMIT_MS,
                  f'zero-millisecond cycle waited: median {median:.2f} ms over {SAMPLES} (max {max(zero):.2f} ms)')

    cycles, elapsed = timed(cycle, BOUNDED_MS)
    native.expect(cycles >= 1, f'bounded cycle count {cycles} < 1')
    native.expect(elapsed >= BOUNDED_MS, f'bounded cycle returned after {elapsed:.2f} ms < {BOUNDED_MS} ms')

    native.expect(cycle(-1) == UNSUPPORTED, 'negative milliseconds')
    result = []
    worker = threading.Thread(target=lambda: result.append(cycle(0)))
    worker.start()
    worker.join()
    native.expect(result == [WRONG_THREAD], f'off-thread cycle {result}')
    case.close()
    queued_tasks(native, cycle)
    return native.assertions, median


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    args = parser.parse_args()
    assertions, median = verify(args.native_directory)
    print(f'PASS run_loop_cycle: {assertions} assertions (zero-millisecond median {median:.3f} ms)', flush=True)


if __name__ == '__main__':
    main()
