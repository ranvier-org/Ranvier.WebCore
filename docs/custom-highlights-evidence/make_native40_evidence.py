"""Collects the T03 custom highlight evidence into docs/custom-highlights-evidence: RED, the batch GREEN, the 30x repeats,
teardown and the measured qualifications, each file with its SHA-256.

Usage: python -I make_native40_evidence.py <candidate> <repeat file> <batch head> <stacked-on note>"""
import hashlib
import json
import sys
from pathlib import Path

repo = Path('C:/wk/native-highlight')
candidate = sys.argv[1]
evidence = repo / 'docs/custom-highlights-evidence'
batch = repo / 'artifacts' / (candidate + '-batch')
red = Path('C:/wk/t03-artifacts/red')
copies = {
    'red-chromium.json': red / 'chromium.json',
    'red-native.json': red / 'native.json',
    'red-chromium.mjs': red / 'highlight_red.mjs',
    'generator-noop-proof.json': Path('C:/wk/t03-artifacts/generator-noop-proof.json'),
    'custom-highlights-repeat30.txt': Path(sys.argv[2]),
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts' / (candidate + '-frozen') / 'runtime-receipt.json',
    'source-patches.json': repo / 'artifacts' / candidate / 'source-patches.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'custom-highlights-probe.log': batch / 'custom_highlights.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
oracle = json.loads((repo / 'tests/fixtures/custom-highlights-oracle.json').read_text())
qualified = json.loads((repo / 'tests/fixtures/custom-highlights-qualified.json').read_text())
repeats = (evidence / 'custom-highlights-repeat30.txt').read_text().splitlines()
assertions = next(item['assertions'] for item in records if item['name'] == 'custom_highlights')
result = {
    'group': ['T03 #74'],
    'native': receipt['nativeVersion'],
    'abi': receipt['abiVersion'],
    'features': ['dom-custom-highlights', 'dom:Highlight', 'dom:HighlightRegistry', 'dom-constructor:Highlight'],
    'members': ['CSS.highlights (rv_dom_css_get_highlights)', 'new Highlight(...ranges)', 'Highlight size/has/values/add/delete/clear',
                'Highlight.priority', 'Highlight.type', 'HighlightRegistry size/has/get/entries/set/delete/clear', '::highlight(name) painting'],
    'excluded': ['HighlightRegistry.highlightsFromPoint (absent from the pinned WebKit; browser-only, the managed service answers Unsupported)'],
    'sourceHeadOfBatch': receipt['sourceHead'],
    'batchRunHead': sys.argv[3],
    'stackedOn': sys.argv[4],
    'red': {'files': ['red-chromium.json', 'red-native.json', 'red-chromium.mjs'],
            'native35': 'Highlight and HighlightRegistry compiled in and ungated; no export; gen/idl.py skipped setlike and maplike'},
    'generator': {'proof': 'generator-noop-proof.json',
                  'note': 'setlikeBindings and maplikeBindings are opt-in; with no binding configured every generated output is unchanged'},
    'green': {'customHighlightsAssertions': assertions, 'repeats': len(repeats), 'repeatsDistinct': sorted(set(repeats)),
              'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions', 0) for item in records),
              'probesRun': [{'name': item['name'], 'exitCode': item['exitCode'], 'assertions': item.get('assertions')} for item in records],
              'teardownCases': len(teardown),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown)},
    'chromiumOracle': {'browser': oracle['browser'], 'apiKeys': len(oracle['api']), 'paintSteps': len(oracle['steps']),
                       'repeats': 'oracle regenerated 30 times, identical 30/30'},
    'measured': {
        'paintOrder': 'equal-priority overlap paints the highlight later in registry iteration order (highlightNames); priority 1 paints above 0; delete then set moves a name last',
        'liveRanges': 'Range.setEnd and Text.insertData repaint the highlighted cells; a StaticRange paints its offsets',
        'teardown': 'document replacement and rv_host_destroy clear the document registry and empty every highlight registered in it; an unregistered highlight keeps its ranges; every handle stays usable until released',
        'registryClear': 'registry.clear() unregisters names one by one and leaves each highlight its ranges, as Chromium does (WebKit HighlightRegistry::clear empties them)',
        'order': 'a range added again and a name set again keep their positions; the constructor adds a repeated range once; values() and entries() are snapshot copies',
    },
    'assertionCount': 'custom_highlights counts 378 on every run. Before f079f62 the Ahem font wait counted assertions on each '
                      'iteration (385 on native40-candidate-3); no case was removed.',
    'qualifications': qualified['differences'],
    'files': {},
}
for path in sorted(evidence.iterdir()):
    if path.is_file() and path.name != 'final-evidence.json':
        result['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green']['rawAssertions'], result['green']['teardownCases'], hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
