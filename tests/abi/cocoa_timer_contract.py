"""Exercise real WTF timers through the integrated public Cocoa host pump."""
import argparse
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import sys
import subprocess
import signal
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cocoa_wtf_timer_probe as baseline


def run(directory, helper_path, captured=None, checkpoint=None, mode='baseline', repeat_milliseconds=0.01):
    if sys.platform != 'darwin':
        raise RuntimeError('Actual macOS is required.')
    helper = C.CDLL(str(Path(helper_path).resolve()))
    bind = baseline.bind
    dispatch = bind(helper, 'rv_test_wtf_due_dispatch', baseline.I, [])
    report = captured if captured is not None else {}
    report.update(mode=mode, failures=[], stage='loading')
    if mode == 'baseline':
        report.update(baseline.run(directory, helper_path))
    report['scope'] = 'Actual rebuilt Host/JSC public rv_run_loop_cycle, including nested callbacks. Test helper creates genuine WTF timers; no selected-method overrides or manual private dispatch.'
    if mode == 'baseline':
        return report
    report['extended'] = []
    def stage(name):
        report['stage'] = name
        if checkpoint:
            checkpoint(report)
    P, I, D = baseline.P, baseline.I, baseline.D
    hostlib = C.CDLL(str(Path(directory).resolve() / 'libRanvierWebCoreHost.dylib'))
    host = bind(hostlib, 'rv_host_create', P, [I, I])(64, 64)
    assert host
    destroy_host = bind(hostlib, 'rv_host_destroy', None, [P])
    create = bind(helper, 'rv_test_wtf_timer_create', P, [])
    arm = bind(helper, 'rv_test_wtf_timer_arm', I, [P, D, I, I])
    state = bind(helper, 'rv_test_wtf_timer_state', I, [P, C.POINTER(I), C.POINTER(I), C.POINTER(I)])
    destroy = bind(helper, 'rv_test_wtf_timer_destroy', I, [P])
    cancel = bind(helper, 'rv_test_wtf_timer_cancel', I, [P])
    live = bind(helper, 'rv_test_wtf_timer_live', I, [])
    total = bind(helper, 'rv_test_wtf_timer_total_callbacks', C.c_ulonglong, [])
    seconds = bind(helper, 'rv_test_wtf_timer_seconds', I, [P, C.POINTER(D), C.POINTER(D)])
    nested_status = bind(helper, 'rv_test_wtf_timer_nested_status', I, [P])
    starting_live = live()
    assert starting_live == 0
    def read(handle):
        callbacks, active, off_owner = I(), I(), I()
        assert state(handle, C.byref(callbacks), C.byref(active), C.byref(off_owner)) == 0
        return {'callbacks': callbacks.value, 'active': active.value, 'offOwnerCallbacks': off_owner.value}
    try:
        if mode == 'owner-fatal-reference':
            stage(mode)
            fatal = bind(helper, 'rv_test_wtf_timer_owner_fatal_reference', I, [])
            status = fatal()
            raise AssertionError('owner-main fatal reference returned: ' + str(status))
        if mode == 'cross-thread-destroy-contract':
            stage(mode)
            handle = create()
            assert handle and arm(handle, 1000, 0, 0) == 0
            destroy_unchecked = bind(helper, 'rv_test_wtf_timer_destroy_unchecked', I, [P])
            worker = threading.Thread(target=lambda: destroy_unchecked(handle))
            worker.start()
            worker.join(timeout=10)
            raise AssertionError('active timer destruction on a foreign thread did not terminate at the ownership assertion')
        for action, name in ((3, 'nested-repeat'), (4, 'self-destroy')):
            if mode != name:
                continue
            stage(name)
            handle = create()
            assert handle
            try:
                before = total()
                assert arm(handle, 1.0 if action == 3 else 0, int(action == 3), action) == 0
                time.sleep(0.003)
                assert dispatch() == 0
                if action == 4:
                    handle = None
                    assert live() == starting_live
                    assert total() == before + 1
                    result = {'callbacks': 1, 'live': live()}
                else:
                    result = read(handle)
                    assert nested_status(handle) == 1, 'nested public zero pump did not complete exactly one cycle'
                    assert result == {'callbacks': 1, 'active': 1, 'offOwnerCallbacks': 0}, result
                    inside, outside = D(), D()
                    assert seconds(handle, C.byref(inside), C.byref(outside)) == 0
                    result['secondsInsideCallback'] = inside.value
                    result['secondsAfterCallback'] = outside.value
                    assert inside.value == 0 and math.isfinite(outside.value) and outside.value >= 0, result
                report['extended'].append({'scenario': name, 'result': result})
            finally:
                if handle:
                    assert destroy(handle) == 0
        if mode == '72-due-one-shots':
            handles = [create() for _ in range(72)]
            stage('72-due-one-shots')
            assert all(handles)
            try:
                before = total()
                for handle in handles:
                    assert arm(handle, 0, 0, 0) == 0
                assert dispatch() == 0
                first = total() - before
                assert 0 < first <= 72, first
                for _ in range(3):
                    assert dispatch() == 0
                states = [read(handle) for handle in handles]
                assert all(row == {'callbacks': 1, 'active': 0, 'offOwnerCallbacks': 0} for row in states), states
                report['extended'].append({'scenario': '72-due-one-shots', 'firstDispatchCallbacks': first, 'states': states})
            finally:
                for handle in handles:
                    assert destroy(handle) == 0
        if mode == '72-fast-repeat-fairness':
            handles = [create() for _ in range(72)]
            stage('72-fast-repeat-fairness')
            assert math.isfinite(repeat_milliseconds) and repeat_milliseconds > 0
            report['repeatMilliseconds'] = repeat_milliseconds
            try:
                for handle in handles:
                    assert arm(handle, repeat_milliseconds, 1, 0) == 0
                time.sleep(0.003)
                for _ in range(8):
                    assert dispatch() == 0
                states = [read(handle) for handle in handles]
                report['extended'].append({'scenario': '72-fast-repeat-fairness', 'states': states})
                if any(row['callbacks'] == 0 for row in states):
                    report['failures'].append('bounded dispatch starves an already-due repeating timer')
            finally:
                for handle in handles:
                    assert destroy(handle) == 0
        if mode == 'wrong-owner-rejection':
            handle = create()
            stage('wrong-owner-rejection')
            try:
                assert arm(handle, 0, 0, 0) == 0
                results = []
                worker = threading.Thread(target=lambda: results.extend((dispatch(), cancel(handle), destroy(handle))))
                worker.start()
                worker.join(timeout=10)
                assert not worker.is_alive() and results == [-2, -2, -2], results
                assert dispatch() == 0
                assert read(handle) == {'callbacks': 1, 'active': 0, 'offOwnerCallbacks': 0}
                report['extended'].append({'scenario': 'wrong-owner-rejection', 'statuses': results})
            finally:
                assert destroy(handle) == 0
        if mode == 'concurrent-cross-thread-arm':
            stage('concurrent-cross-thread-arm')
            handle = create()
            try:
                results = []
                worker = threading.Thread(target=lambda: results.extend(arm(handle, 1.0, 0, 0) for _ in range(500)))
                worker.start()
                for _ in range(64):
                    assert dispatch() == 0
                worker.join(timeout=10)
                assert not worker.is_alive() and results == [0] * 500
                time.sleep(0.003)
                assert dispatch() == 0
                result = read(handle)
                assert result['callbacks'] >= 1 and result['offOwnerCallbacks'] == 0 and not result['active'], result
                assert cancel(handle) == 0
                callbacks = total()
                assert dispatch() == 0 and total() == callbacks
                report['extended'].append({'scenario': 'concurrent-cross-thread-arm', 'arms': len(results), 'result': result})
            finally:
                assert destroy(handle) == 0
        assert live() == starting_live
        report['liveAfter'] = live()
        stage('complete')
    finally:
        destroy_host(host)
    return report


MODES = ('baseline', 'nested-repeat', 'self-destroy', '72-due-one-shots',
         '72-fast-repeat-fairness', 'wrong-owner-rejection', 'concurrent-cross-thread-arm',
         'cross-thread-destroy-contract')


def expected_owner_assertion(code, output, reference=None):
    fatal_signals = {-signal.SIGABRT, -signal.SIGILL}
    if hasattr(signal, 'SIGTRAP'):
        fatal_signals.add(-signal.SIGTRAP)
    if reference and reference.get('platform') == 'darwin' and reference.get('exit') == code == -9:
        same_helper = reference.get('helperBefore') == reference.get('helperAfter') and bool(reference.get('helperBefore'))
        reference_output = reference.get('output', '')
        if same_helper and 'WTF_TIMER_OWNER_FATAL_REFERENCE_BEFORE_ASSERT' in reference_output and 'WTF_TIMER_OWNER_FATAL_REFERENCE_RETURNED' not in reference_output:
            fatal_signals.add(-9)
    return code in fatal_signals and 'WTF_TIMER_NEGATIVE_BEFORE_OWNER_VIOLATION' in output and 'WTF_TIMER_NEGATIVE_DESTRUCTOR_RETURNED' not in output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--helper', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=(*MODES, 'owner-fatal-reference'))
    parser.add_argument('--repeat-milliseconds', type=float, default=0.01,
                        help='Fairness interval; original 0.000001 ms subquantum case remains explicitly replayable')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not args.mode:
        report = {'scope': 'Isolated integrated Cocoa host timer modes; no failed mode hides another.', 'results': []}
        for mode in MODES:
            target = args.output.with_name(args.output.stem + '-' + mode + '.json')
            command = [sys.executable, '-I', str(Path(__file__).resolve()), '--native-directory', args.native_directory,
                       '--helper', args.helper, '--output', str(target), '--mode', mode]
            command += ['--repeat-milliseconds', str(args.repeat_milliseconds)]
            try:
                child = subprocess.run(command, capture_output=True, text=True, timeout=120)
                code, output = child.returncode, child.stdout + child.stderr
            except subprocess.TimeoutExpired as error:
                code, output = -999, repr(error)
            log = target.with_suffix('.log')
            log.write_text(output)
            if mode == 'cross-thread-destroy-contract':
                reference = None
                if code == -9 and sys.platform == 'darwin':
                    helper = Path(args.helper).resolve()
                    helper_before = hashlib.sha256(helper.read_bytes()).hexdigest()
                    reference_target = target.with_name(target.stem + '-reference.json')
                    reference_command = [sys.executable, '-I', str(Path(__file__).resolve()),
                        '--native-directory', args.native_directory, '--helper', args.helper,
                        '--output', str(reference_target), '--mode', 'owner-fatal-reference']
                    try:
                        child_reference = subprocess.run(reference_command, capture_output=True, text=True, timeout=30)
                        reference_exit = child_reference.returncode
                        reference_output = child_reference.stdout + child_reference.stderr
                    except subprocess.TimeoutExpired as error:
                        reference_exit, reference_output = -999, repr(error)
                    reference = {'platform': sys.platform, 'argv': reference_command, 'exit': reference_exit,
                        'output': reference_output, 'helperBefore': helper_before,
                        'helperAfter': hashlib.sha256(helper.read_bytes()).hexdigest()}
                    reference_target.with_suffix('.log').write_text(reference_output, encoding='utf-8')
                    report['ownerFatalReference'] = reference
                expected_failure = expected_owner_assertion(code, output, reference)
                verdict = 0 if expected_failure else 1
            else:
                expected_failure, verdict = False, int(code != 0)
            report['results'].append({'mode': mode, 'exit': code, 'expectedOwnerAssertionTermination': expected_failure,
                                      'verdict': verdict, 'report': target.name, 'log': log.name})
            args.output.write_text(json.dumps(report, indent=2))
            print(mode, code, flush=True)
        return int(any(row['verdict'] != 0 for row in report['results']))
    report = {'mode': args.mode, 'stage': 'starting', 'failures': []}
    args.output.write_text(json.dumps(report, indent=2))
    try:
        run(args.native_directory, args.helper, report,
            lambda data: args.output.write_text(json.dumps(data, indent=2)), args.mode, args.repeat_milliseconds)
    except Exception as error:
        report.setdefault('failures', []).append(repr(error))
    finally:
        args.output.write_text(json.dumps(report, indent=2))
    print('COCOA_TIMER_CONTRACT', args.mode, 'zero misses', report.get('zeroMisses'), 'failures', report['failures'])
    return int(bool(report.get('zeroMisses', 0) or report['failures']))


if __name__ == '__main__':
    raise SystemExit(main())
