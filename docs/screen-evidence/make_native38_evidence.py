"""Collects the G04 Native38 evidence into docs/screen-evidence, each file with its SHA-256."""
import hashlib
import json
from pathlib import Path

repo = Path('C:/wk/native-screen')
lane = Path('C:/wk/crypto-artifacts')
candidate = repo / 'artifacts/native38-candidate-7'
evidence = repo / 'docs/screen-evidence'
batch = repo / 'artifacts/native38-batch-7'
copies = {
    'build_native38_candidate.py': lane / 'build_native38_candidate.py',
    'run_native38_full_batch.py': lane / 'run_native38_full_batch.py',
    'make_native38_evidence.py': lane / 'make_native38_evidence.py',
    'screen-repeat30.txt': lane / 'screen-repeat30.txt',
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts/native38-frozen-7/runtime-receipt.json',
    'source-patches.json': candidate / 'source-patches.json',
    'replacement-objects.json': candidate / 'replacement-objects.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'screen-metrics-probe.log': batch / 'screen_metrics.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
oracle = json.loads((repo / 'tests/fixtures/screen-oracle.json').read_text(encoding='utf-8'))
red = json.loads((evidence / 'red-no-0038.json').read_text())
green = json.loads((evidence / 'green-0038-candidate4.json').read_text())
patches = json.loads((evidence / 'source-patches.json').read_text())
log = (batch / 'screen_metrics.log').read_text(encoding='utf-8')
result = {
    'group': ['G04 #49'],
    'native': receipt['nativeVersion'],
    'abi': 46,
    'features': ['screen', 'dom-screen', 'dom-screen-orientation'],
    'members': ['rv_host_set_screen (RvScreenMetrics: size, work area, color depth, orientation)',
                'Screen width/height/availLeft/availTop/availWidth/availHeight/colorDepth/pixelDepth (Window.screen)',
                'ScreenOrientation type/angle (Window.screen.orientation, ScreenOrientationAPIEnabled on)'],
    'excluded': ['ScreenOrientation.lock/unlock and onchange as native exports: locking stays off (Unsupported); changes are '
                 'delivered by the Views provider after SetScreen/Resize'],
    'sourceHeadOfBatch': receipt['sourceHead'],
    'sourcePatches': {'list': ['0035 (G09 native32-candidate-3 UnifiedSource-dom-7, reused)', '0037 (recompiled)', '0038 (recompiled)'],
                      'recompiled0037And0038': list(patches['patches']), 'recompiledUnits': len(patches['recompiledUnits'])},
    'patch0038': {'sha256': 'edd1af84fafbc5ce7ac74cd16263799445405d638af46e859f892eacf56da8bd',
                  'files': ['Source/WebCore/platform/PlatformScreen.cpp', 'Source/WebCore/platform/win/PlatformScreenWin.cpp']},
    'red': {'windowsMonitorLeak': {'engine': red['engine'], 'primaryMonitor': red['primaryMonitor'], 'engineEqualsHostSize': red['engineEqualsHostSize']},
            'noPlatformScreenOnWindows': 'red-link-no-platformscreen.log (updateSingletonProperties undefined at host link)',
            'generator': 'generator-red.log', 'chromium': 'chromium-red.json'},
    'greenBefore0038Applied': {'candidate': 'native38-candidate-4 (mirror sources)', 'default': green['default']},
    'green': {'screenMetricsAssertions': int(log.split('screen_metrics: ')[1].split(' assertions')[0]),
              'repeat30': (evidence / 'screen-repeat30.txt').read_text().strip(),
              'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions', 0) for item in records), 'newProbes': ['screen_metrics'],
              'probesRun': [{'name': item['name'], 'exitCode': item['exitCode'], 'assertions': item.get('assertions')} for item in records],
              'teardownCases': len(teardown), 'teardownCasesAdded': len([r for r in teardown if 'screen' in r['probe']]),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown)},
    'chromiumOracle': {'browser': oracle['browser'], 'cases': len(oracle['cases']), 'lock': oracle['lock']},
    'defaultScreen': 'every RID: the host size in CSS pixels, all of it available, depth 24, landscape-primary unless taller than wide; '
                     'follows rv_host_resize until rv_host_set_screen (the host publishes it through PlatformScreen, which 0038 makes '
                     'Windows read; WPE and Mac read it already)',
    'qualifications': [
        {'name': 'orientation lock', 'reason': 'native locking stays off and reads Unsupported; Chromium headless resolves lock(portrait) '
                                                'without changing the type (oracle lock field)'},
        {'name': 'angle', 'reason': 'the angle follows from the type on the natural landscape orientation (WebKit table); the app sets the type'},
        {'name': 'event order', 'reason': 'the order of orientation change and resize events is never asserted'},
        {'name': 'detached document', 'reason': 'a document kept past rv_host_destroy has no frame, and its Screen reports 0'},
        {'name': 'browser size-only change', 'reason': 'Chromium fires no event for a screen size change without an orientation or '
                                                        'viewport change, so the browser provider delivers changes it can observe'}],
    'files': {},
}
for path in sorted(evidence.iterdir()):
    if path.name != 'final-evidence.json' and path.is_file():
        result['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green']['rawAssertions'], result['green']['probes'], result['green']['teardownCases'],
      hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
