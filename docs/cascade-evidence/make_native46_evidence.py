"""Collects the C25 cascade diagnostics evidence into docs/cascade-evidence: RED, the batch GREEN, the 30x repeats,
the Chromium oracle repeats, teardown and the receipts, each file with its SHA-256.

Usage: python -I make_native46_evidence.py <candidate> <repeat file> <oracle repeat file> <batch head> <stacked-on note>
                                           <baseline batch-green.json>"""
import hashlib
import json
import sys
from pathlib import Path

repo = Path('C:/wk/native-cascade')
candidate = sys.argv[1]
evidence = repo / 'docs/cascade-evidence'
batch = repo / 'artifacts' / (candidate + '-batch')
copies = {
    'cascade-diagnostics-repeat30.txt': Path(sys.argv[2]),
    'oracle-repeat30.txt': Path(sys.argv[3]),
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts' / (candidate + '-frozen') / 'runtime-receipt.json',
    'source-patches.json': repo / 'artifacts' / candidate / 'source-patches.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'cascade-diagnostics-probe.log': batch / 'cascade_diagnostics.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
baseline = json.loads(Path(sys.argv[6]).read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
patches = json.loads((evidence / 'source-patches.json').read_text())
fixture = json.loads((repo / 'tests/fixtures/cascade-diagnostics.json').read_text(encoding='utf-8'))
oracle = json.loads((repo / 'tests/fixtures/cascade-diagnostics-oracle.json').read_text(encoding='utf-8'))
repeats = (evidence / 'cascade-diagnostics-repeat30.txt').read_text().splitlines()
oracle_repeats = (evidence / 'oracle-repeat30.txt').read_text().splitlines()
assertions = next(item['assertions'] for item in records if item['name'] == 'cascade_diagnostics')
names = [item['name'] for item in records]
baseline_counts = {item['name']: item.get('assertions') for item in baseline}
result = {
    'group': ['C25 #45'],
    'status': 'green (private Windows x64 slim; not accepted)',
    'native': receipt['nativeVersion'],
    'abi': receipt['abiVersion'],
    'features': ['cascade-diagnostics', 'capability facility cascade-diagnostics'],
    'members': ['rv_host_inspect_cascade', 'RV_DIAGNOSTIC_CASCADE', 'RV_RULE_ORIGIN_PRESENTATIONAL_HINT', 'RV_CASCADE_* fields'],
    'engine': 'Style::ElementRuleCollector (ResolvingStyle) MatchResult and Style::PropertyCascade selection, from RanvierInspectGlue '
              '(compiled into WebCore); layer names, conditions and positions from the active CSSStyleSheet rule trees; no source patch',
    'glueInspectorSymbols': patches.get('inspectGlue', {}).get('inspectorSymbols'),
    'sourceHeadOfBatch': receipt['sourceHead'],
    'batchRunHead': sys.argv[4],
    'stackedOn': sys.argv[5],
    'red': {'file': 'red-native42.log', 'native42': 'the probe fails on its first absent binding, rv_host_inspect_cascade'},
    'green': {'cascadeDiagnosticsAssertions': assertions, 'fixtureCases': len(fixture['cases']),
              'tieBreaks': sorted({c['tieBreak'] for c in fixture['cases']}),
              'repeats': len(repeats), 'repeatsDistinct': sorted(set(repeats)),
              'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions', 0) for item in records),
              'baselineRawAssertions': sum(item.get('assertions', 0) for item in baseline),
              'baselineProbesUnchanged': all(baseline_counts[n] == next(i.get('assertions') for i in records if i['name'] == n)
                                             for n in baseline_counts if n not in ('frames', 'teardown')),
              'baselineProbesPresent': all(n in names for n in baseline_counts),
              'probesRun': [{'name': item['name'], 'exitCode': item['exitCode'], 'assertions': item.get('assertions')} for item in records],
              'teardownCases': len(teardown), 'cascadeTeardownCases': len([r for r in teardown if 'cascade' in r['probe']]),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown)},
    'chromiumOracle': {'browser': oracle['browser'], 'cases': len(oracle['cases']),
                       'allMatchFixture': all(c['matchesFixture'] for c in oracle['cases']),
                       'repeats': len(oracle_repeats), 'repeatsDistinct': sorted({line.split(' ', 1)[1] for line in oracle_repeats}),
                       'unsupported': oracle['unsupported']},
    'measured': {
        'winner': 'RV_CASCADE_WINNER comes from PropertyCascade\'s selected value; in every case the winner\'s value equals the native '
                  'computed value (or, for inherit, unset and var(), the deeper winner does) and the Chromium computed value equals the fixture',
        'noSideEffects': 'computed values and element rects of every case are unchanged across all queries; a class change reverted before '
                         'the next update leaves no transition after a cascade query in between (0), and starts one after a computed-style read '
                         'in between (control, >= 1), with a steps(2, jump-start) transition',
        'pending': 'a pending class change, a pending <style> insertion and a pending @property registration are read as the DOM holds them; '
                   'the result equals the query after the update',
        'stability': 'entries, including sheet, rule and declaration indices, are equal across two queries and after an unrelated insertion '
                     'and attribute change',
        'sharedBlocks': 'rules with identical declaration blocks (WebKit shares the StyleProperties) keep their own selector and position',
        'teardown': 'snapshots stay readable after disabling and rv_host_destroy; every snapshot is released',
    },
    'declaredLimits': ['a winning revert or revert-layer is reported as that keyword (no rollback trace)',
                       ':visited declarations, @starting-style rules and animations are absent',
                       'RV_CASCADE_VALUE is the declared value; var() resolution is rv_element_computed_style\'s',
                       'container conditions use the last layout, logical pairs the last computed writing mode'],
    'files': {},
}
for path in sorted(evidence.iterdir()):
    if path.is_file() and path.name != 'final-evidence.json':
        result['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green']['rawAssertions'], result['green']['teardownCases'], result['green']['baselineProbesUnchanged'],
      hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
