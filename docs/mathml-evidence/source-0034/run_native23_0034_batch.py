from pathlib import Path
import hashlib, json, os, re, shutil, subprocess

repo = Path('C:/wk/native-mathml')
candidate = repo / 'artifacts/mathml-candidate-23-0034b/runtime'
freeze = repo / 'artifacts/native23-0034b-frozen'
runtime = freeze / 'runtimes/win-x64/native'
out = repo / 'artifacts/native23-0034b-batch'
out.mkdir(parents=True, exist_ok=True)
names = ['brotlicommon.dll', 'brotlidec.dll', 'harfbuzz-icu.dll', 'harfbuzz.dll', 'icudt77.dll', 'icuin77.dll', 'icuuc77.dll', 'JavaScriptCore.dll',
         'jpeg62.dll', 'libpng16.dll', 'libsharpyuv.dll', 'libwebp.dll', 'libwebpdemux.dll', 'libwebpmux.dll', 'libxml2.dll', 'RanvierWebCoreHost.dll',
         'WebCore.dll', 'zlib1.dll', 'WebKit.resources/icons/missingImage.png', 'WebKit.resources/icons/missingImage@2x.png',
         'WebKit.resources/icons/missingImage@3x.png', 'WebKit.resources/icons/panIcon.png', 'WebKit.resources/icons/textAreaResizeCorner.png',
         'WebKit.resources/icons/textAreaResizeCorner@2x.png']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
if not (freeze / 'runtime-receipt.json').exists():
    for name in names:
        destination = runtime / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate / name, destination)
    receipt = {'sourceHead': head, 'nativeVersion': json.loads((repo / 'pins.json').read_text())['package']['version'], 'abiVersion': 31,
               'platform': 'private win-x64 slim', 'buildScript': 'artifacts/build_mathml_0034_candidate.py', 'buildHead': head, 'sourcePatch': '0034-svg-string-list-null-attribute', 'buildRuntimeSha256': json.loads((repo / 'artifacts/mathml-candidate-23-0034b/runtime-sha256.json').read_text()),
               'shippingFiles': [{'name': name, 'bytes': (runtime / name).stat().st_size, 'sha256': digest(runtime / name)} for name in names]}
    (freeze / 'runtime-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
receipt = json.loads((freeze / 'runtime-receipt.json').read_text())


def verify_runtime():
    for entry in receipt['shippingFiles']:
        assert digest(runtime / entry['name']) == entry['sha256'], entry['name']


records = json.loads((out / 'results.json').read_text()) if (out / 'results.json').exists() else []


def run(name, command, expected=None, environment=None, executed=None, timeout=300):
    existing = next((item for item in records if item['name'] == name and item['exitCode'] == 0), None)
    if existing:
        assert digest(Path(existing['log'])) == existing['logSha256']
        verify_runtime()
        print(name, 'retained prior exit0', flush=True)
        return
    verify_runtime()
    before = {str(p): digest(p) for p in (executed or [])}
    sources = {str(p): digest(p) for p in [repo / 'tests/abi' / (name + '.py'), repo / 'tests/abi/svg_paint_probe.py'] if p.exists()}
    result = subprocess.run(['rtk', 'proxy', *command], cwd=repo, env=environment, capture_output=True, timeout=timeout)
    log = out / (name + '.log')
    if log.exists():
        number = 1
        while log.with_name(log.stem + f'-previous{number}.log').exists():
            number += 1
        log.rename(log.with_name(log.stem + f'-previous{number}.log'))
    log.write_bytes(result.stdout + result.stderr + f'\nEXIT_CODE={result.returncode}\n'.encode())
    verify_runtime()
    assert before == {str(p): digest(p) for p in (executed or [])}, 'Executed managed assets changed'
    record = {'name': name, 'exitCode': result.returncode, 'log': str(log), 'logSha256': digest(log), 'executedSources': sources,
              'executedAssets': before, 'runtimeReceipt': str(freeze / 'runtime-receipt.json')}
    match = re.search(rb'PASS[^\n]*?(\d+) assertions', result.stdout)
    if match:
        record['assertions'] = int(match.group(1))
    records[:] = [item for item in records if item['name'] != name]
    records.append(record)
    (out / 'results.json').write_text(json.dumps(records, indent=2))
    print(name, 'exit', result.returncode, record.get('assertions'), flush=True)
    if result.returncode:
        print((result.stdout + result.stderr).decode('utf-8', 'replace')[-4000:], flush=True)
        raise SystemExit(result.returncode)
    if expected is not None:
        assert record.get('assertions') == expected, name + ' expected ' + str(expected) + ' got ' + str(record.get('assertions'))


# Source 0034 recompiles UnifiedSource-svg-14 (SVGStringList); these probes exercise SVGTests lists, switch and
# conditional processing, and the SVG/MathML surfaces built on that object.
probes = [('svg_tests_lists', None), ('svg_geometry', 639), ('svg_surfaces', 1594), ('svg_mathml_surface', 95), ('svg_paint_servers', None),
          ('svg_clip_mask_marker', None), ('svg_resources', 454), ('mathml_surface', 371), ('capabilities', None)]
for name, expected in probes:
    arguments = ['C:/Python314/python.exe', '-I', '-X', 'utf8', str(repo / 'tests/abi' / (name + '.py')), '--native-directory', str(runtime)]
    if name == 'svg_surfaces':
        arguments += ['--webkit-source', 'C:/wk/src']
    run(name, arguments, expected)
(out / 'results.json').write_text(json.dumps(records, indent=2))
print('NATIVE23_0034_AFFECTED_BATCH=' + str(sum(item.get('assertions', 0) for item in records)) + ' RAW', flush=True)
