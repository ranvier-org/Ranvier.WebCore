"""Qualify two GPU clipping controls against the frozen P7 Windows artifact."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

SOURCE = '6f10bea17d7a1f22e5e97d472819c055fba3ef06'
PACKAGE = 'aa9ca63366cf04c3c9e7b27d90c0758f5129bf5c64532e7540c27f857b8adb41'
MANIFEST = 'd659c45fde66a7ea91339a57ad198452512285124458c87c9effc1d4aca18b40'
ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def stage_artifact(package, manifest, stage):
    assert sha(package) == PACKAGE and sha(manifest) == MANIFEST
    data = json.loads(manifest.read_text())
    assert data['source'] == {'commit': SOURCE, 'dirty': False, 'builder': 'ci'}
    assert (data['rid'], data['flavor'], data['abi'], data['version']) == ('win-x64', 'gpu', 62, '0.1.1-preview.7')
    files = data['files']
    assert len(files) == len({row['name'] for row in files}) == 26
    stage.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(package) as archive:
        for row in files:
            out = (stage / row['name']).resolve()
            assert out.is_relative_to(stage.resolve())
            payload = archive.read('runtimes/win-x64/native/' + row['name'])
            assert len(payload) == row['bytes'] and hashlib.sha256(payload).hexdigest() == row['sha256']
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(payload)
    return {row['name']: row['sha256'] for row in files}


def check_results(report, model):
    assert report['completeKeys'] == 54 and report['strictContentMaskKeys'] == 12
    failures = report['failures']
    assert len(failures) == 2
    assert {(x['name'], x['scale']) for x in failures} == {
        ('composited-translate', 1.5), ('composited-translate', 2)
    }
    assert all(not x['strictFixedCase'] for x in failures)
    assert model['result'] == 'PASS'
    cases = model['cases']
    assert len(cases) == 2
    assert {(x['scale'], x['checkedPixels'], x['failures']) for x in cases} == {
        (1.5, 1080000, 0), (2, 1920000, 0)
    }


def run(command, cwd, timeout):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    assert result.returncode == 0, (command, result.returncode, result.stdout, result.stderr)
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    policy = args.work / 'policy'
    shutil.copytree(ROOT / 'tests/p7_gpu_qualification', policy)
    stage = policy / 'precision-runtime' / 'runtimes' / 'win-x64' / 'native'
    hashes = stage_artifact(args.package, args.manifest, stage)
    shutil.copy2(args.manifest, policy / 'precision-runtime' / 'manifest.json')
    try:
        run([sys.executable, '-I', str(ROOT / 'scripts/capture_p7_clipping.py'), str(stage), str(args.work)], ROOT, 90)
        report = json.loads((args.work / 'original-report.json').read_text())
        captured_renderer = json.loads((args.work / 'capture-profile.json').read_text())['renderer']
        run([sys.executable, '-I', str(policy / 'vertex-precision-probe.py')], policy, 90)
        run([sys.executable, '-I', str(policy / 'sampler_grid_probe.py')], policy, 180)
        precision = json.loads((policy / 'vertex-fragment-precision.json').read_text())
        grid = json.loads((policy / 'sampler-grid-probe.json').read_text())
        assert 'Direct3D11' in precision['renderer'] and grid['renderer'] == precision['renderer'] == captured_renderer
        assert precision['nativeUnchanged'] and grid['runtimeUnchanged']
        assert len(grid['gridRows']) == 16 and sum(x['samples'] for x in grid['gridRows']) == 1048576
        inputs = json.loads((policy / 'gpu-model-inputs-v2.json').read_text())
        inputs['shaderPrecision'] = precision
        inputs['gpu']['renderer'] = precision['renderer']
        inputs['gpu']['vendor'] = precision['vendor']
        inputs['gpu']['version'] = precision['version']
        for label in ('low', 'medium', 'high'):
            item = precision['shaderPrecision']['fragment'][label]
            inputs['gpu']['fragment' + label.title() + 'Float'] = {'range': item['range'], 'precision': item['fractionBits']}
        (args.work / 'ci-inputs.json').write_text(json.dumps(inputs, indent=2))
        for row in report['results']:
            row['width'], row['height'] = int(800 * row['scale']), int(600 * row['scale'])
        (args.work / 'ci-capture.json').write_text(json.dumps({'results': report['results']}))
        output = args.work / 'model.json'
        run([sys.executable, '-I', str(policy / 'gpu_pixel_gate_v3.py'), '--inputs', str(args.work / 'ci-inputs.json'),
             '--capture', str(args.work / 'ci-capture.json'), '--output', str(output)], policy, 90)
        model = json.loads(output.read_text())
        check_results(report, model)
        negatives = []
        for mutation in ('shift', 'erase', 'recolor', 'bleed', 'solid-lsb', 'pink-to-red', 'edge-channel',
                         'filter-low-bound', 'filter-high-bound'):
            path = args.work / ('negative-' + mutation + '.json')
            command = [sys.executable, '-I', str(policy / 'gpu_pixel_gate_v3.py'), '--inputs', str(args.work / 'ci-inputs.json'),
                       '--capture', str(args.work / 'ci-capture.json'), '--mutation', mutation, '--output', str(path)]
            result = subprocess.run(command, cwd=policy, capture_output=True, text=True, timeout=90)
            negative = json.loads(path.read_text())
            assert result.returncode == 1 and negative['result'] == 'FAIL'
            assert len(negative['cases']) == 2 and all(x['failures'] > 0 for x in negative['cases'])
            negatives.append({'mutation': mutation, 'sha256': sha(path)})
        old = args.work / 'negative-old-cpu.json'
        result = subprocess.run([sys.executable, '-I', str(policy / 'gpu_pixel_gate_v3.py'), '--inputs', str(args.work / 'ci-inputs.json'),
                                 '--capture', str(policy / 'baseline-a9.json'), '--output', str(old)],
                                cwd=policy, capture_output=True, text=True, timeout=90)
        old_model = json.loads(old.read_text())
        assert result.returncode == 1 and old_model['result'] == 'FAIL'
        assert len(old_model['cases']) == 2 and all(x['failures'] > 0 for x in old_model['cases'])
        negatives.append({'mutation': 'old-cpu-path', 'sha256': sha(old)})
        assert {name: sha(stage / name) for name in hashes} == hashes
        receipt = {'source': SOURCE, 'packageSha256': PACKAGE, 'manifestSha256': MANIFEST,
                   'profile': precision['renderer'], 'originalReportSha256': sha(args.work / 'original-report.json'),
                   'modelSha256': sha(output), 'precisionSha256': sha(policy / 'vertex-fragment-precision.json'),
                   'samplerSha256': sha(policy / 'sampler-grid-probe.json'), 'negativeControls': negatives,
                   'nativeUnchanged': True,
                   'scope': 'Windows ANGLE/D3D11 two-control tested-profile policy; original 12 strict and 52 other controls retained'}
        (args.work / 'qualification.json').write_text(json.dumps(receipt, indent=2))
        print(json.dumps(receipt))
    finally:
        shutil.rmtree(stage)


if __name__ == '__main__':
    main()
