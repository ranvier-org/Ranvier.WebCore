import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def hashes(native):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(native.glob('*.dylib'))}


def pixels(blob):
    return {'sha256': hashlib.sha256(blob).hexdigest(),
            'nonwhitePixels': sum(blob[index:index + 4] != b'\xff' * 4 for index in range(0, len(blob), 4))}


def child(args):
    native = Path(args.native_directory).resolve()
    output = Path(args.output).resolve()
    if output.is_relative_to(native):
        raise RuntimeError('diagnostic output must be outside the native input directory')
    output.mkdir(parents=True, exist_ok=False)
    report = {'systemReduced': args.system, 'rows': [], 'failures': [], 'nativeBefore': hashes(native)}
    write_json(output / 'clock.json', report)
    if report['nativeBefore'].get('libWebCore.dylib') != args.expected_engine_sha256:
        raise RuntimeError('engine hash does not match the requested immutable input')
    engine = C.CDLL(str(native / 'libWebCore.dylib'), mode=C.RTLD_GLOBAL)
    helper = C.CDLL(str(Path(args.helper).resolve()))
    render = helper.project2_native_progress_clock
    render.argtypes = [C.c_int32, C.c_double, C.c_double, C.c_double,
                       C.POINTER(C.c_uint8), C.c_size_t, C.POINTER(C.c_int32)]
    render.restype = C.c_int32
    getter_implementation = helper.project2_native_progress_getter_implementation
    getter_implementation.argtypes = []
    getter_implementation.restype = C.c_size_t
    report['getterImplementationBefore'] = getter_implementation()
    raw = {}
    try:
        for position in (-1.0, 0.0, 0.5):
            for elapsed in (0.0, 0.125, 0.25, 0.5, 1.0, 1.5, 2.0, 0.5):
                label = f'position-{position}-elapsed-{elapsed}-row-{len(report["rows"])}'
                buffer = (C.c_uint8 * (512 * 40 * 4))()
                calls = C.c_int32(-1)
                status = render(args.system, 1000.0, 1000.0 + elapsed, position,
                                buffer, len(buffer), C.byref(calls))
                row = {'label': label, 'position': position, 'elapsed': elapsed,
                       'status': status, 'systemGetterCalls': calls.value}
                report['rows'].append(row)
                if status:
                    report['failures'].append(f'{label}: native status {status}')
                    write_json(output / 'clock.json', report)
                    raise RuntimeError(report['failures'][-1])
                blob = bytes(buffer)
                row.update(pixels(blob))
                (output / (label + '.rgba')).write_bytes(blob)
                raw.setdefault(position, []).append(blob)
                write_json(output / 'clock.json', report)

        for position, frames in raw.items():
            if frames[3] != frames[-1]:
                report['failures'].append(f'position {position}: fixed-clock repeat changed')
            if not any(pixel != 255 for pixel in frames[3]):
                report['failures'].append(f'position {position}: fixed-clock image is empty white')
            if position >= 0 and len(set(frames)) != 1:
                report['failures'].append(f'determinate position {position}: clock changed pixels')
        report['advancingIndeterminateUniqueImages'] = len(set(raw[-1.0]))
        if report['advancingIndeterminateUniqueImages'] <= 1:
            report['failures'].append('advancing native indeterminate clock produced no pixel change')
        report['fixedPhaseDifferenceFromEmptyTrackPixels'] = sum(
            raw[-1.0][3][index:index + 4] != raw[0.0][3][index:index + 4]
            for index in range(0, len(raw[-1.0][3]), 4))
        if not report['fixedPhaseDifferenceFromEmptyTrackPixels']:
            report['failures'].append('fixed-phase indeterminate matches empty determinate track')
        wrong_thread = []
        buffer = (C.c_uint8 * (512 * 40 * 4))()
        calls = C.c_int32(-1)
        worker = threading.Thread(target=lambda: wrong_thread.append(
            render(args.system, 1000.0, 1000.5, -1.0, buffer, len(buffer), C.byref(calls))))
        worker.start()
        worker.join(5)
        report['wrongThreadResult'] = wrong_thread
        if worker.is_alive() or wrong_thread != [-1]:
            report['failures'].append('wrong-thread call was not rejected before drawing')
        report['invalidCapacityResult'] = render(args.system, 1000.0, 1000.5, -1.0,
                                                 buffer, len(buffer) - 1, C.byref(calls))
        if report['invalidCapacityResult'] != -2:
            report['failures'].append('invalid-capacity call was not rejected')
    finally:
        report['getterImplementationAfter'] = getter_implementation()
        if not report['getterImplementationBefore'] or report['getterImplementationBefore'] != report['getterImplementationAfter']:
            report['failures'].append('NSWorkspace getter implementation was not restored')
        report['nativeAfter'] = hashes(native)
        if report['nativeBefore'] != report['nativeAfter']:
            report['failures'].append('native input bytes changed')
        write_json(output / 'clock.json', report)
        del engine
    return int(bool(report['failures']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--expected-engine-sha256', required=True)
    parser.add_argument('--helper', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--system', type=int, choices=(0, 1))
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('this diagnostic requires macOS')
    if args.system is not None:
        return child(args)
    output = Path(args.output).resolve()
    if output.is_relative_to(Path(args.native_directory).resolve()):
        raise RuntimeError('diagnostic output must be outside the native input directory')
    output.mkdir(parents=True, exist_ok=False)
    record = {'scope': 'raw native CoreUI clock diagnostic; not rendered-DOM or product qualification',
              'helperSha256': hashlib.sha256(Path(args.helper).read_bytes()).hexdigest(), 'children': []}
    for system in (0, 1):
        argv = [sys.executable, '-I', str(Path(__file__).resolve()),
                '--native-directory', args.native_directory,
                '--expected-engine-sha256', args.expected_engine_sha256,
                '--helper', args.helper, '--output', str(output / f'system-{system}'), '--system', str(system)]
        try:
            result = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', timeout=30)
            status, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as error:
            status, stdout, stderr = 124, str(error.stdout or ''), str(error.stderr or '')
        (output / f'system-{system}.log').write_text(stdout + stderr, encoding='utf-8')
        record['children'].append({'systemReduced': system, 'argv': argv, 'exit': status})
        write_json(output / 'clock-matrix.json', record)
    if not any(item['exit'] for item in record['children']):
        left = json.loads((output / 'system-0/clock.json').read_text(encoding='utf-8'))
        right = json.loads((output / 'system-1/clock.json').read_text(encoding='utf-8'))
        if len(left['rows']) != len(right['rows']):
            raise RuntimeError('system comparison row count differs')
        record['systemComparisons'] = []
        for a, b in zip(left['rows'], right['rows'], strict=True):
            if (a['label'], a['position'], a['elapsed']) != (b['label'], b['position'], b['elapsed']):
                raise RuntimeError('system comparison inputs differ')
            before = (output / 'system-0' / (a['label'] + '.rgba')).read_bytes()
            after = (output / 'system-1' / (b['label'] + '.rgba')).read_bytes()
            record['systemComparisons'].append({
                'position': a['position'], 'elapsed': a['elapsed'],
                'changedPixels': sum(before[i:i + 4] != after[i:i + 4] for i in range(0, len(before), 4)),
                'getterCallsOff': a['systemGetterCalls'], 'getterCallsOn': b['systemGetterCalls']})
        write_json(output / 'clock-matrix.json', record)
    return int(any(item['exit'] for item in record['children']))


if __name__ == '__main__':
    raise SystemExit(main())
