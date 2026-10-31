"""Collects the H08 inspector diagnostics evidence into docs/inspector-evidence: RED, the batch GREEN, the 30x repeats,
the Chromium oracle repeats, teardown and the receipts, each file with its SHA-256.

Usage: python -I make_native42_evidence.py <candidate> <repeat file> <oracle repeat file> <batch head> <stacked-on note>"""
import hashlib
import json
import sys
from pathlib import Path

repo = Path('C:/wk/native-inspect')
candidate = sys.argv[1]
evidence = repo / 'docs/inspector-evidence'
batch = repo / 'artifacts' / (candidate + '-batch')
copies = {
    'inspector-diagnostics-repeat30.txt': Path(sys.argv[2]),
    'oracle-repeat30.txt': Path(sys.argv[3]),
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts' / (candidate + '-frozen') / 'runtime-receipt.json',
    'source-patches.json': repo / 'artifacts' / candidate / 'source-patches.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'inspector-diagnostics-probe.log': batch / 'inspector_diagnostics.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
patches = json.loads((evidence / 'source-patches.json').read_text())
oracle = json.loads((repo / 'tests/fixtures/inspector-diagnostics-oracle.json').read_text(encoding='utf-8'))
repeats = (evidence / 'inspector-diagnostics-repeat30.txt').read_text().splitlines()
oracle_repeats = (evidence / 'oracle-repeat30.txt').read_text().splitlines()
assertions = next(item['assertions'] for item in records if item['name'] == 'inspector_diagnostics')
diagnostics_teardown = [r for r in teardown if 'diagnostics' in r['probe']]
result = {
    'group': ['H08 #113'],
    'status': 'green (private Windows x64 slim; not accepted)',
    'native': receipt['nativeVersion'],
    'abi': receipt['abiVersion'],
    'features': ['diagnostics', 'capability facility diagnostics', 'capability facility inspector-frontend'],
    'members': ['rv_host_set_diagnostics', 'rv_host_inspect_render_tree', 'rv_host_inspect_matched_rules', 'rv_host_inspect_box_model',
                'rv_diagnostic_kind', 'rv_diagnostic_text', 'rv_diagnostic_count', 'rv_diagnostic_entry_string',
                'rv_diagnostic_entry_number', 'rv_diagnostic_release', 'rv_diagnostic_live_count'],
    'browserTooling': {'inspector': 'stub (USE_INSPECTOR_STUB, patch 0008)', 'jscInspector': 'stub (USE_JSC_INSPECTOR_STUB, patch 0009)',
                       'remoteInspector': 'ENABLE_REMOTE_INSPECTOR=OFF', 'webInspectorUI': 'not packaged (scripts/build.py)',
                       'inspectorFrontendFacility': 'implemented 0, available 0 on every flavor',
                       'glueInspectorSymbols': patches.get('inspectGlue', {}).get('inspectorSymbols')},
    'sourceHeadOfBatch': receipt['sourceHead'],
    'batchRunHead': sys.argv[4],
    'stackedOn': sys.argv[5],
    'red': {'file': 'red-native38.log', 'native38': 'the probe fails on its first absent binding, rv_host_set_diagnostics'},
    'green': {'inspectorDiagnosticsAssertions': assertions, 'repeats': len(repeats), 'repeatsDistinct': sorted(set(repeats)),
              'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions', 0) for item in records),
              'probesRun': [{'name': item['name'], 'exitCode': item['exitCode'], 'assertions': item.get('assertions')} for item in records],
              'teardownCases': len(teardown), 'diagnosticsTeardownCases': len(diagnostics_teardown),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown)},
    'chromiumOracle': {'browser': oracle['browser'], 'cases': [c['name'] for c in oracle['cases']], 'elements': oracle['elements'],
                       'repeats': len(oracle_repeats), 'repeatsDistinct': sorted({line.split(' ', 1)[1] for line in oracle_repeats}),
                       'unsupported': oracle['unsupported']},
    'measured': {
        'boxModel': 'equal to Chromium within 1/64 px for 4 elements x 4 boxes x 3 cases (unscrolled, scrolled 30,45, page scale 2), '
                    'including CSS zoom 2 and a positioned button; every value is a multiple of 1/64; the border box equals rv_element_rect',
        'matchedRules': 'user-agent div rule first; author rules ordered layer base, layer top, then unlayered :where (0,0,0), '
                        '.box list (0,1,0), @media .box (0,1,0), #target (1,0,0), :is (1,0,0), div.box#target (1,1,1); '
                        'the non-matching @media rule is absent; the inline entry is last with no selector',
        'renderTree': 'layer groups nest renderers one level at a time; one box per visible element, none for display:none; '
                      'the #target line agrees with the box model within the dump\'s whole-pixel snapping; 7 layers with all-layers',
        'optIn': 'a disabled host returns UNSUPPORTED before reading the node (a text node reads UNSUPPORTED, not NOT_ELEMENT)',
        'teardown': 'snapshots stay readable after disabling and rv_host_destroy; every snapshot is released (live count returns to baseline)',
    },
    'files': {},
}
for path in sorted(evidence.iterdir()):
    if path.is_file() and path.name != 'final-evidence.json':
        result['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green']['rawAssertions'], result['green']['teardownCases'], hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
