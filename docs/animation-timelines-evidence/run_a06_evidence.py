"""A06 (document/custom timelines) native evidence. A06 adds no export: the runtime is the A01 lane's waapi-candidate-3, whose
full batch (92029 raw assertions) stays valid unchanged. This runs what A06 adds on that frozen runtime: the
animation_timelines probe, its 30 repeats, and the frames and teardown driver runs of this tree (teardown gains the
"document timeline" kind: 108 records, each collected).
usage: run_a06_evidence.py <out dir> [repeats]"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys

repo = Path(__file__).resolve().parents[2]
out = Path(sys.argv[1])
repeats = int(sys.argv[2]) if len(sys.argv) > 2 else 30
out.mkdir(parents=True, exist_ok=True)
a01 = Path('C:/wk/native-waapi/artifacts')
freeze = a01 / 'waapi-candidate-3-frozen'
runtime = freeze / 'runtimes/win-x64/native'
receipt = json.loads((freeze / 'runtime-receipt.json').read_text())
baseline = a01 / 'waapi-candidate-3-batch/results.json'
TEARDOWN = 108


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_runtime(directory):
    for entry in receipt['shippingFiles']:
        assert digest(Path(directory) / entry['name']) == entry['sha256'], entry['name']


verify_runtime(runtime)
head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
dirty = subprocess.run(['git', 'status', '--porcelain', '--', 'tests', 'host', 'gen'], cwd=repo, capture_output=True, text=True, check=True).stdout
evidence = {'sourceHead': head, 'sourceDirty': dirty.splitlines(), 'runtimeReceipt': str(freeze / 'runtime-receipt.json'),
            'runtimeReceiptSha256': digest(freeze / 'runtime-receipt.json'), 'baselineBatch': str(baseline), 'baselineBatchSha256': digest(baseline),
            'baselineRaw': sum(item.get('assertions', 0) for item in json.loads(baseline.read_text())), 'runs': {}}
probe = repo / 'tests/abi/animation_timelines.py'
command = ['C:/Python314/python.exe', '-I', '-X', 'utf8', str(probe), '--native-directory', str(runtime)]
first = subprocess.run(command + ['--evidence', str(out / 'animation-timelines.json')], cwd=repo, capture_output=True, text=True, timeout=600)
(out / 'animation-timelines.log').write_text(first.stdout + first.stderr + f'\nEXIT_CODE={first.returncode}\n', encoding='utf-8')
print(first.stdout.strip(), flush=True)
assert first.returncode == 0, first.stdout + first.stderr
assertions = int(re.search(r'PASS[^\n]*?(\d+) assertions', first.stdout).group(1))
evidence['runs']['animation_timelines'] = {'assertions': assertions, 'log': str(out / 'animation-timelines.log'), 'logSha256': digest(out / 'animation-timelines.log'),
                                           'probeSha256': digest(probe)}
lines = []
for run in range(1, repeats + 1):
    result = subprocess.run(command, cwd=repo, capture_output=True, text=True, timeout=600)
    lines.append(f'run {run}: exit {result.returncode} ' + (result.stdout.strip().splitlines() or [''])[-1])
(out / 'animation-timelines-repeat.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
passed = sum(1 for line in lines if f'exit 0 PASS animation timelines: {assertions} assertions' in line)
evidence['runs']['repeat'] = {'runs': repeats, 'passed': passed, 'file': str(out / 'animation-timelines-repeat.txt')}
print('repeat', passed, '/', repeats, flush=True)
driver = repo / 'artifacts/a06-driver'
assert (driver / 'RanvierWebCoreAbi.Driver.dll').exists(), 'build the driver first'
for entry in receipt['shippingFiles']:
    destination = driver / entry['name']
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(runtime / entry['name'], destination)
verify_runtime(driver)
for name in ['frames', 'teardown']:
    env = dict(os.environ, RANVIER_WEBKIT_SOURCE='C:/wk/src', RANVIER_WEBCORE_OUT=str(out / name), RANVIER_TRACE='1')
    if name == 'teardown':
        env['RANVIER_WEBCORE_PROBE'] = 'teardown'
    else:
        env.pop('RANVIER_WEBCORE_PROBE', None)
    result = subprocess.run(['dotnet', str(driver / 'RanvierWebCoreAbi.Driver.dll')], cwd=repo, env=env, capture_output=True, timeout=900)
    log = out / (name + '.log')
    log.write_bytes(result.stdout + result.stderr + f'\nEXIT_CODE={result.returncode}\n'.encode())
    evidence['runs'][name] = {'exitCode': result.returncode, 'log': str(log), 'logSha256': digest(log), 'driverSha256': digest(driver / 'RanvierWebCoreAbi.Driver.dll')}
    print(name, 'exit', result.returncode, flush=True)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
teardown = json.loads((out / 'teardown/teardown-probes.json').read_text())
collected = all(item['documentRefsAfterCollection'] == -1 and item['targetRefsAfterCollection'] == -1 for item in teardown)
evidence['runs']['teardown'].update({'records': len(teardown), 'allCollected': collected,
                                     'documentTimeline': [item for item in teardown if 'document timeline' in json.dumps(item)]})
assert len(teardown) == TEARDOWN and collected, (len(teardown), collected)
assert passed == repeats
(out / 'a06-evidence.json').write_text(json.dumps(evidence, indent=1) + '\n', encoding='utf-8')
print(f'A06_EVIDENCE probe={assertions} repeat={passed}/{repeats} teardown={len(teardown)} baselineRaw={evidence["baselineRaw"]}', flush=True)
