"""Collects the G09 Native32 evidence into docs/caret-hit-evidence: RED, the 0035 RED/GREEN, batch GREEN, teardown and the
measured qualifications, each file with its SHA-256."""
import hashlib
import json
from pathlib import Path

repo = Path('C:/wk/native-caret')
evidence = repo / 'docs/caret-hit-evidence'
batch = repo / 'artifacts/native32-batch'
copies = {
    'build_native32_candidate.py': repo / 'artifacts/build_native32_candidate.py',
    'run_native32_batch.py': repo / 'artifacts/run_native32_batch.py',
    'make_native32_evidence.py': repo / 'artifacts/make_native32_evidence.py',
    'absence_g09.py': repo / 'artifacts/absence_g09.py',
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts/native32-frozen/runtime-receipt.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'caret-hit-probe.log': batch / 'caret_hit.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
red = json.loads((evidence / 'red-measure.json').read_text())
red0035 = json.loads((evidence / 'red-0035-candidate-1-measure.json').read_text())
oracle = json.loads((repo / 'tests/fixtures/caret-hit-oracle.json').read_text(encoding='utf-8'))
qualified = json.loads((repo / 'tests/fixtures/caret-hit-qualified.json').read_text(encoding='utf-8'))
probe = next(item for item in records if item['name'] == 'caret_hit')
added = [r for r in teardown if 'caret position' in r['probe']]
leaks = [d for d in red0035['differences'] if d['member'] == 'shadowRoots' and d['native'] and d['native'].get('node', {}).get('scope') == '#document-fragment']
result = {
    'group': ['G09 #54'],
    'native': receipt['nativeVersion'],
    'abi': 40,
    'features': ['dom:CaretPosition'],
    'members': ['Document.caretPositionFromPoint', 'CaretPosition.offsetNode', 'CaretPosition.offset', 'CaretPosition.getClientRect',
                'CaretPositionFromPointOptions.shadowRoots'],
    'sourceHeadOfBatch': receipt['sourceHead'],
    'sourcePatch': {'patch': '0035-caret-position-text-control-shadow-roots.patch', 'approvedBy': 'root 2026-10-31',
                    'red': {'runtime': 'artifacts/native32-candidate-1 (no 0035)', 'file': 'red-0035-candidate-1-measure.json',
                            'userAgentShadowLeaks': len(leaks),
                            'case': 'caretPositionFromPoint over <input> with shadowRoots [open, closed] returned a Text node of the input UA shadow root'},
                    'green': {'runtime': 'artifacts/native32-candidate-2 and later', 'file': 'green-0035-candidate-2-measure.json',
                              'case': 'INPUT@1 with and without shadowRoots at device scales 1, 1.5 and 2'}},
    'red': {'runtime': 'native-scroll/artifacts/native29-candidate-1 (Native29/ABI37)', 'abiVersion': red['abiVersion'], 'missingExports': red['missing'],
            'legacyCaretRangeFromPoint': {c['scale'].__str__() + ' ' + c['scroll']: f"{sum(h['rangeMatches'] for h in c['hits'])}/{len(c['hits'])}" for c in red['cases']},
            'files': ['red-measure.json', 'red-chromium-oracle.log']},
    'green': {'caretHitAssertions': probe['assertions'], 'oracleChecks': qualified['checked'], 'qualifiedDifferences': len(qualified['differences']),
              'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions', 0) for item in records), 'teardownCases': len(teardown), 'teardownCasesAdded': len(added),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown),
              'repeatRuns': '30/30 on native32-candidate-2'},
    'chromiumOracle': {'browser': oracle['browser'], 'headless': oracle['headless'], 'fixture': 'tests/fixtures/caret-hit.html',
                       'cases': len(oracle['cases']), 'points': len(oracle['points']), 'scales': oracle['scales'],
                       'scrolls': [s[0] for s in oracle['scrolls']]},
    'qualifications': qualified['qualifications'] + [
        {'name': 'whole-pixel scroll (G05)', 'count': None,
         'reason': 'scrollTo(0.5, 20.5) leaves the native engine at (0, 20) and Chromium at (1, 21). Each runtime is checked against the oracle case at its own '
                   'actual offset (the native engine against Chromium scrolled to (0, 20)); no hit differs beyond the four groups above.'},
        {'name': 'Linux FreeType quantisation', 'count': None,
         'reason': 'rectangles compare within 0.01 px and qualified values round to 0.01, for the 16.16 Ahem advances on Linux'}],
    'files': {},
}
for path in sorted(evidence.iterdir()):
    if path.name != 'final-evidence.json':
        result['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green']['rawAssertions'], result['green']['teardownCases'], result['green']['probes'], hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
