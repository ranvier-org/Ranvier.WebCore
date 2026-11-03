"""Exercise a test-only real WTF RunLoop::Timer seam against a macOS host.

The helper must be compiled against the same WebKit build as the host. This is a
qualification probe; it is not a public ABI. No timer or handle is used after
owner-thread destruction.
"""
import argparse
import ctypes as ct
import hashlib
import json
import platform
import statistics
import sys
import threading
import time
from pathlib import Path

P, I, D = ct.c_void_p, ct.c_int32, ct.c_double


def bind(lib, name, result, args):
    fn = getattr(lib, name)
    fn.restype, fn.argtypes = result, args
    return fn


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def run(directory, helper_path):
    if sys.platform != 'darwin':
        raise RuntimeError('macOS is required')
    native = Path(directory).resolve(strict=True) / 'libRanvierWebCoreHost.dylib'
    helper_path = Path(helper_path).resolve(strict=True)
    hostlib = ct.CDLL(str(native))
    helper = ct.CDLL(str(helper_path))
    create_host = bind(hostlib, 'rv_host_create', P, [I, I])
    destroy_host = bind(hostlib, 'rv_host_destroy', None, [P])
    cycle = bind(hostlib, 'rv_run_loop_cycle', I, [I])
    abi = bind(hostlib, 'rv_abi_version', I, [])()
    create = bind(helper, 'rv_test_wtf_timer_create', P, [])
    arm = bind(helper, 'rv_test_wtf_timer_arm', I, [P, D, I, I])
    state = bind(helper, 'rv_test_wtf_timer_state', I, [P, ct.POINTER(I), ct.POINTER(I), ct.POINTER(I)])
    cancel = bind(helper, 'rv_test_wtf_timer_cancel', I, [P])
    destroy = bind(helper, 'rv_test_wtf_timer_destroy', I, [P])
    total = bind(helper, 'rv_test_wtf_timer_total_callbacks', ct.c_ulonglong, [])
    host = create_host(64, 64)
    assert host, 'host creation failed'
    records, failures = [], []

    def read(handle):
        callbacks, active, off_owner = I(), I(), I()
        status = state(handle, ct.byref(callbacks), ct.byref(active), ct.byref(off_owner))
        assert status == 0, status
        return {'callbacks':callbacks.value, 'active':active.value, 'offOwnerCallbacks':off_owner.value}

    def call(milliseconds):
        start = time.perf_counter()
        count = cycle(milliseconds)
        return {'cycles':count, 'elapsedMs':(time.perf_counter() - start) * 1000}

    def new_timer():
        handle = create()
        assert handle, 'WTF timer creation failed'
        return handle

    def pump_until(handle, minimum, timeout_ms=1000):
        deadline = time.monotonic() + timeout_ms / 1000
        cycles = []
        result = read(handle)
        while result['callbacks'] < minimum and time.monotonic() < deadline:
            cycles.append(call(10))
            result = read(handle)
        return cycles, result

    def pump_for(milliseconds):
        deadline = time.monotonic() + milliseconds / 1000
        cycles = []
        while time.monotonic() < deadline:
            cycles.append(call(10))
        return cycles

    try:
        for scenario in ('immediate', 'already_due'):
            for index in range(32):
                handle = new_timer()
                try:
                    assert arm(handle, 0.0, 0, 0) == 0
                    before = read(handle)
                    if scenario == 'already_due':
                        time.sleep(0.003)
                    zero = call(0)
                    after_zero = read(handle)
                    positive, final = pump_until(handle, 1) if not after_zero['callbacks'] else ([], after_zero)
                    records.append({'scenario':scenario, 'index':index, 'before':before, 'zero':zero, 'afterZero':after_zero, 'positive':positive, 'final':final})
                    if before['active'] != 1 or zero['cycles'] != 1 or final != {'callbacks':1, 'active':0, 'offOwnerCallbacks':0}:
                        failures.append(f'{scenario} {index}: state, cycle or ownership')
                finally:
                    assert destroy(handle) == 0

        handle = new_timer()
        try:
            armed_at = time.monotonic()
            assert arm(handle, 50.0, 0, 0) == 0
            early = call(0)
            early_state = read(handle)
            early_observed_ms = (time.monotonic() - armed_at) * 1000
            time.sleep(0.06)
            due = call(0)
            due_state = read(handle)
            positive, final = pump_until(handle, 1) if not due_state['callbacks'] else ([], due_state)
            records.append({'scenario':'future', 'early':early, 'earlyState':early_state, 'earlyObservedMs':early_observed_ms, 'due':due, 'dueState':due_state, 'positive':positive, 'final':final})
            if early_observed_ms >= 50:
                failures.append('future: early control did not complete before deadline')
            elif early_state['callbacks']:
                failures.append('future: callback delivered early')
            if final != {'callbacks':1, 'active':0, 'offOwnerCallbacks':0}:
                failures.append('future: missing, repeated or wrong-thread callback')
        finally:
            assert destroy(handle) == 0

        handle = new_timer()
        try:
            assert arm(handle, 10.0, 0, 0) == 0
            worker_status = []
            worker = threading.Thread(target=lambda: worker_status.extend([cancel(handle), destroy(handle)]))
            worker.start(); worker.join()
            active_after_refusal = read(handle)
            assert cancel(handle) == 0
            after_cancel_cycles = pump_for(20)
            final = read(handle)
            records.append({'scenario':'wrong-thread-cancel-destroy', 'workerStatus':worker_status, 'afterRefusal':active_after_refusal, 'afterCancelCycles':after_cancel_cycles, 'final':final})
            if worker_status != [-2, -2] or active_after_refusal['active'] != 1 or final != {'callbacks':0, 'active':0, 'offOwnerCallbacks':0}:
                failures.append('wrong-thread rejection or owner cancel')
        finally:
            assert destroy(handle) == 0

        handle = new_timer()
        assert arm(handle, 10.0, 0, 0) == 0
        before_destroy = total()
        assert destroy(handle) == 0
        after_destroy_cycles = pump_for(20)
        after_destroy = total()
        records.append({'scenario':'destroy-active', 'before':before_destroy, 'after':after_destroy, 'cycles':after_destroy_cycles})
        if after_destroy != before_destroy:
            failures.append('callback after active timer destruction')

        handle = new_timer()
        try:
            assert arm(handle, 5.0, 1, 0) == 0
            duration, before_cancel = pump_until(handle, 2)
            assert cancel(handle) == 0
            after_cancel_cycles = pump_for(20)
            final = read(handle)
            records.append({'scenario':'repeat-external-cancel', 'cycles':duration, 'beforeCancel':before_cancel, 'afterCancelCycles':after_cancel_cycles, 'final':final})
            if before_cancel['callbacks'] < 2 or before_cancel['active'] != 1 or final['callbacks'] != before_cancel['callbacks'] or final['active'] or final['offOwnerCallbacks']:
                failures.append('repeat count or external cancellation')
        finally:
            assert destroy(handle) == 0

        for action, expected in [(1, 1), (2, 2)]:
            handle = new_timer()
            try:
                assert arm(handle, 5.0 if action == 1 else 0.0, int(action == 1), action) == 0
                duration, reached = pump_until(handle, expected)
                after = pump_for(20)
                final = read(handle)
                records.append({'scenario':'cancel-in-callback' if action == 1 else 'rearm-in-callback', 'cycles':duration, 'reached':reached, 'afterCycle':after, 'final':final})
                if final != {'callbacks':expected, 'active':0, 'offOwnerCallbacks':0}:
                    failures.append('callback cancel or rearm')
            finally:
                assert destroy(handle) == 0

        handle = new_timer()
        try:
            result = []
            worker = threading.Thread(target=lambda: result.append(arm(handle, 5.0, 0, 0)))
            worker.start(); worker.join()
            before = read(handle)
            duration, final = pump_until(handle, 1)
            records.append({'scenario':'cross-thread-arm', 'workerStatus':result, 'before':before, 'cycles':duration, 'final':final})
            if result != [0] or before['active'] != 1 or final != {'callbacks':1, 'active':0, 'offOwnerCallbacks':0}:
                failures.append('cross-thread arm or owner callback')
        finally:
            assert destroy(handle) == 0
    finally:
        destroy_host(host)

    samples = [r['zero']['elapsedMs'] for r in records if 'zero' in r]
    if statistics.median(samples) >= 10:
        failures.append('zero-cycle median exceeded 10 ms')
    misses = sum(r['afterZero']['callbacks'] == 0 for r in records if 'afterZero' in r)
    return {'platform':platform.platform(), 'macVersion':platform.mac_ver(), 'abi':abi, 'hostSha256':sha(native), 'helperSha256':sha(helper_path), 'scope':'actual WTF RunLoop::Timer via test-only helper', 'zeroMisses':misses, 'records':records, 'failures':failures}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--helper', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--require-due-delivery', action='store_true')
    args = parser.parse_args()
    report = run(args.native_directory, args.helper)
    Path(args.output).write_text(json.dumps(report, indent=2))
    print('WTF_TIMER_PROBE', 'zero misses', report['zeroMisses'], 'failures', len(report['failures']))
    if report['failures']:
        return 1
    return 2 if args.require_due_delivery and report['zeroMisses'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
