from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys
CANDIDATE = sys.argv[1]

repo = Path('C:/wk/native-crypto')
candidate = repo / 'artifacts' / CANDIDATE / 'runtime'
freeze = repo / 'artifacts' / ('native36-frozen' + (sys.argv[2] if len(sys.argv) > 2 else ''))
runtime = freeze / 'runtimes/win-x64/native'
out = repo / 'artifacts' / ('native36-batch' + (sys.argv[2] if len(sys.argv) > 2 else ''))
out.mkdir(parents=True, exist_ok=True)
names = ['brotlicommon.dll', 'brotlidec.dll', 'harfbuzz-icu.dll', 'harfbuzz.dll', 'icudt77.dll', 'icuin77.dll', 'icuuc77.dll', 'JavaScriptCore.dll',
         'jpeg62.dll', 'libpng16.dll', 'libsharpyuv.dll', 'libwebp.dll', 'libwebpdemux.dll', 'libwebpmux.dll', 'libxml2.dll', 'RanvierWebCoreHost.dll',
         'WebCore.dll', 'zlib1.dll', 'WebKit.resources/icons/missingImage.png', 'WebKit.resources/icons/missingImage@2x.png',
         'WebKit.resources/icons/missingImage@3x.png', 'WebKit.resources/icons/panIcon.png', 'WebKit.resources/icons/textAreaResizeCorner.png',
         'WebKit.resources/icons/textAreaResizeCorner@2x.png']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# The capability catalogue must match the header before any probe runs.
subprocess.run([sys.executable, '-I', str(repo / 'scripts/capability_catalogue.py'), '--check'], cwd=repo, check=True)
head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
if not (freeze / 'runtime-receipt.json').exists():
    for name in names:
        destination = runtime / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate / name, destination)
    receipt = {'sourceHead': head, 'nativeVersion': json.loads((repo / 'pins.json').read_text())['package']['version'], 'abiVersion': 44,
               'platform': 'private win-x64 slim', 'buildScript': 'C:/wk/crypto-artifacts/build_native36_candidate.py', 'buildHead': head, 'sourcePatches': '0000-0035 and 0037 (0035: G09 native32-candidate-3 UnifiedSource-dom-7; 0037: recompiled units in source-patches.json)', 'buildRuntimeSha256': json.loads((repo / 'artifacts' / CANDIDATE / 'runtime-sha256.json').read_text()),
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
    # Probes report either "... PASS ... N assertions" or "<probe>: N assertions".
    match = re.search(rb'PASS[^\n]*?(\d+) assertions', result.stdout) or re.search(rb'(?m)^[a-z_]+: (\d+) assertions', result.stdout)
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


probes = [('css_supports', 72), ('computed_style', 93), ('fragment_rectangles', 140), ('table_surface', 44), ('element_reflection', 269),
          ('area_surface', 117), ('cssom_surface', 407), ('keyframe_rules', 93), ('counter_style_rules', 86), ('detached_cssom_context', 389),
          ('svg_mathml_surface', 95), ('style_property_maps', 189), ('declared_style_maps', 2069), ('style_map_entries', 144),
          ('typed_style_values', 190), ('custom_properties', 231), ('geometry_values', 260), ('matrix_values', 1091), ('css_transforms', 405),
          ('svg_geometry', 639), ('svg_surfaces', 1594), ('svg_documents', 78), ('svg_view_controls', 318), ('svg_animation_variants', 70),
          ('capabilities', None), ('svg_view_selection', None),
          ('svg_paint_servers', None), ('svg_filters', None), ('svg_clip_mask_marker', None), ('svg_resources', 454), ('mathml_surface', 371), ('svg_tests_lists', 191), ('image_decode', 73), ('font_load', 42), ('event_construction', 82), ('tree_traversal', None), ('focus_input', 80), ('viewport_events', 364), ('form_collections', 1168), ('form_navigation', None), ('viewport_scroll', None), ('dialog_popover', None), ('binary_values', None), ('caret_hit', None), ('url_values', None), ('url_wpt', None), ('form_submission', None), ('text_segmentation', None), ('crypto_random', 275)]
for name, expected in probes:
    arguments = ['C:/Python314/python.exe', '-I', '-X', 'utf8', str(repo / 'tests/abi' / (name + '.py')), '--native-directory', str(runtime)]
    if name in ('svg_surfaces', 'font_load', 'caret_hit'):
        arguments += ['--webkit-source', 'C:/wk/src']
    if name == 'dialog_popover':
        arguments += ['--abi', '44']
    run(name, arguments, expected)

driver = repo / 'artifacts' / ('native36-driver' + (sys.argv[2] if len(sys.argv) > 2 else ''))
assert (driver / 'RanvierWebCoreAbi.Driver.dll').exists(), 'build the driver from the merged tree first'
for entry in receipt['shippingFiles']:
    destination = driver / entry['name']
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(runtime / entry['name'], destination)
    assert digest(destination) == entry['sha256']
for name in ['frames', 'teardown']:
    env = dict(os.environ, RANVIER_WEBKIT_SOURCE='C:/wk/src', RANVIER_WEBCORE_OUT=str(out / name), RANVIER_TRACE='1')
    if name == 'teardown':
        env['RANVIER_WEBCORE_PROBE'] = 'teardown'
    else:
        env.pop('RANVIER_WEBCORE_PROBE', None)
    assets = [p for p in driver.rglob('*') if p.is_file() and p.suffix.lower() in ['.dll', '.exe', '.json']]
    run(name, ['dotnet', str(driver / 'RanvierWebCoreAbi.Driver.dll')], environment=env, executed=assets, timeout=900)
teardown = json.loads((out / 'teardown/teardown-probes.json').read_text())
assert len(teardown) == 86 and all(item['documentRefsAfterCollection'] == -1 and item['targetRefsAfterCollection'] == -1 for item in teardown)
(out / 'results.json').write_text(json.dumps(records, indent=2))
print('NATIVE36_FULL_BATCH=' + str(sum(item.get('assertions', 0) for item in records)) + ' RAW +86 TEARDOWN', flush=True)
