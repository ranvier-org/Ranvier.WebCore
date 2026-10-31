"""Collects the T06 Native35 evidence into docs/text-segmentation-evidence, each file with its SHA-256."""
import hashlib
import json
import sys
from pathlib import Path

repo = Path('C:/wk/native-segment')
suffix = sys.argv[1] if len(sys.argv) > 1 else ''
candidate = sys.argv[2] if len(sys.argv) > 2 else 'native35-candidate-7'
evidence = repo / 'docs/text-segmentation-evidence'
batch = repo / 'artifacts' / ('native35-batch' + suffix)
copies = {
    'build_native35_candidate.py': repo / 'artifacts/build_native35_candidate.py',
    'run_native35_full_batch.py': repo / 'artifacts/run_native35_full_batch.py',
    'make_native35_evidence.py': repo / 'artifacts/make_native35_evidence.py',
    'units_for_headers.py': Path('C:/wk/t06-artifacts/units_for_headers.py'),
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts' / ('native35-frozen' + suffix) / 'runtime-receipt.json',
    'source-patches.json': repo / 'artifacts' / candidate / 'source-patches.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'text-segmentation-probe.log': batch / 'text_segmentation.log',
    'text-segmentation-repeat30.txt': Path('C:/wk/t06-artifacts/segment-repeat30-final.txt'),
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
qualified = json.loads((repo / 'tests/fixtures/text-segmentation-qualified.json').read_text(encoding='utf-8'))
oracle = json.loads((repo / 'tests/fixtures/text-segmentation-oracle.json').read_text(encoding='utf-8'))
icu = json.loads((evidence / 'icu.json').read_text(encoding='utf-8'))
dotnet = json.loads((evidence / 'dotnet-stringinfo.json').read_text(encoding='utf-8'))
probe = next(item for item in records if item['name'] == 'text_segmentation')
log = (batch / 'text_segmentation.log').read_text(encoding='utf-8')
result = {
    'group': ['T06 #76'],
    'native': receipt['nativeVersion'],
    'abi': 43,
    'features': ['text-segmentation'],
    'members': ['rv_text_segment', 'rv_text_segments_release', 'rv_text_segmentation_version'],
    'sourceHeadOfBatch': receipt['sourceHead'],
    'route': {'decision': 'native: WebKit CachedTextBreakIterator (graphemes, lines) and ICU ubrk with the locale (words, sentences) behind a hand-written export',
              'icuVsChromium': icu['agreement'], 'dotnetStringInfoGraphemes': f"{dotnet['graphemeAgree']}/{dotnet['total']}",
              'files': ['cases.json', 'chromium.json', 'icu.json', 'dotnet-stringinfo.json', 'icu_segment.py', 'chromium_segmenter.mjs']},
    'green': {'textSegmentationAssertions': probe.get('assertions'), 'version': log.strip().split(', ')[-1],
              'qualifiedDifferences': len(qualified['differences']), 'probes': len(records) - 2,
              'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions', 0) for item in records), 'teardownCases': len(teardown),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown)},
    'chromiumOracle': {'browser': oracle['browser'], 'cases': len(oracle['cases']), 'locales': len(oracle['locales']),
                       'line': 'Intl.v8BreakIterator({type: "line"}); Intl.Segmenter has no line granularity'},
    'platformIcu': {'win-x64': 'packaged ICU 77.1 (Unicode 16.0): exact results checked',
                    'linux-x64': 'system ICU (Ubuntu 24.04 runner); invariants checked, version reported by rv_text_segmentation_version in the CI log',
                    'linux-arm64': 'system ICU (Ubuntu 24.04 arm runner); invariants checked, version in the CI log',
                    'osx-arm64': 'system libicucore; invariants checked, version in the CI log'},
    'qualifications': [
        {'name': 'full stop between letters', 'count': len([k for k in qualified['differences'] if k != 'cases[4].word']),
         'reason': qualified['differences'][next(k for k in qualified['differences'] if k != 'cases[4].word')]['note']},
        {'name': 'Hangul jamo join', 'count': 1, 'reason': qualified['differences']['cases[4].word']['note']},
        {'name': 'resolved locale', 'count': None, 'reason': qualified['resolvedLocales']['note']},
        {'name': 'line oracle', 'count': None, 'reason': 'No standard browser line segmenter exists; the oracle is Chromium\'s non-standard Intl.v8BreakIterator.'},
        {'name': 'system ICU', 'count': None, 'reason': 'Linux and macOS segmentation follows the system ICU version; exact results are measured on ICU 77.1.'},
    ],
    'files': {},
}
for path in sorted(evidence.iterdir()):
    if path.name != 'final-evidence.json':
        result['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green'], hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
