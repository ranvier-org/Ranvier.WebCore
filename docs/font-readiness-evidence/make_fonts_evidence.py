"""Collects the WebCore T01/R09 evidence into docs/font-readiness-evidence: RED, the batch GREEN against the C25
baseline batch, the font_readiness and image_readiness reports and repeats, teardown and the per-probe comparison,
each file with its SHA-256.

Usage: python -I make_fonts_evidence.py <candidate> <baseline batch dir> <baseline head>"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
candidate, baseline, baseline_head = sys.argv[1:4]
baseline = Path(baseline)
evidence = repo / 'docs/font-readiness-evidence'
batch = repo / 'artifacts' / (candidate + '-batch')
runtime = repo / 'artifacts' / (candidate + '-frozen') / 'runtimes/win-x64/native'
copies = {
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts' / (candidate + '-frozen') / 'runtime-receipt.json',
    'source-patches.json': repo / 'artifacts' / candidate / 'source-patches.json',
    'build-receipt.json': repo / 'artifacts' / candidate / 'runtime-sha256.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'font-readiness-probe.log': batch / 'font_readiness.log',
    'image-readiness-probe.log': batch / 'image_readiness.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
reports = {'font': evidence / 'font-readiness-report.json', 'image': repo / 'docs/image-readiness-evidence/image-readiness-report.json'}
subprocess.run([sys.executable, '-I', '-X', 'utf8', str(repo / 'tests/abi/font_readiness.py'), '--native-directory', str(runtime),
                '--webkit-source', 'C:/wk/src', '--evidence-json', str(reports['font'])], check=True, capture_output=True)
subprocess.run([sys.executable, '-I', '-X', 'utf8', str(repo / 'tests/abi/image_readiness.py'), '--native-directory', str(runtime),
                '--evidence-json', str(reports['image'])], check=True, capture_output=True)
records = json.loads((batch / 'results.json').read_text(encoding='utf-8'))
base = {item['name']: item for item in json.loads((baseline / 'results.json').read_text(encoding='utf-8'))}
comparison = []
for item in records:
    previous = base.get(item['name'])
    entry = {'name': item['name'], 'assertions': item.get('assertions'), 'exitCode': item['exitCode']}
    if previous:
        entry['baselineAssertions'] = previous.get('assertions')
        entry['sameCount'] = previous.get('assertions') == item.get('assertions')
    else:
        entry['new'] = True
    comparison.append(entry)
(evidence / 'baseline-comparison.json').write_text(json.dumps(comparison, indent=2) + '\n', encoding='utf-8', newline='\n')
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text(encoding='utf-8'))
base_teardown = json.loads((baseline / 'teardown/teardown-probes.json').read_text(encoding='utf-8'))
receipt = json.loads((evidence / 'runtime-receipt.json').read_text(encoding='utf-8'))
repeats = (evidence / 'repeat30-runs.txt').read_text(encoding='utf-8').splitlines()
font = json.loads(reports['font'].read_text(encoding='utf-8'))
image = json.loads(reports['image'].read_text(encoding='utf-8'))
result = {
    'group': ['T01 font loading/readiness (ranvier-org/Ranvier.WebCore#72)', 'R09 image readiness and decoding (ranvier-org/Ranvier.WebCore#97)'],
    'native': receipt['nativeVersion'],
    'abi': receipt['abiVersion'],
    'abiNote': 'placeholder: ABI stays 54; the integration batch assigns the number',
    'features': ['font-readiness (new)', 'image-decode (existing, R09 adds no export)'],
    'members': ['rv_fonts_status', 'rv_fonts_check', 'rv_fonts_load', 'rv_fonts_ready', 'rv_fonts_watch', 'rv_fonts_unwatch',
                'RV_FONTS_LOADED/LOADING', 'RV_FONTS_EVENT_LOADING/LOADINGDONE/LOADINGERROR', 'RvFontsEventCallback', 'RvFontsWatch'],
    'sourcePatch': 'none: CSSFontFaceSet FontEventClient and a native window load listener in host/RanvierResourceGlue.cpp',
    'qualifications': [
        'The engine dispatches only the loading DOM event on document.fonts; rv_fonts_watch synthesizes loadingdone and '
        'loadingerror from FontEventClient, matching the spec and Chromium, while DOM listeners in the slim document see only loading.',
        'A watch created during a loading period receives LOADING at once; its LOADINGDONE/LOADINGERROR list only faces '
        'that finished after it was created.',
        'rv_fonts_load succeeds with the number of matching faces, not the FontFace objects.',
    ],
    'sourceHeadOfBatch': receipt['sourceHead'],
    'baseline': {'batch': str(baseline), 'head': baseline_head,
                 'rawAssertions': sum(item.get('assertions', 0) for item in base.values() if item['name'] not in ('frames', 'teardown')),
                 'teardownCases': len(base_teardown)},
    'red': {'native': 'red-native.json (red_native.py)', 'chromium': 'oracle-chromium.json (oracle_chromium.mjs)',
            'image': '../image-readiness-evidence/red-native.json (red_native.py)',
            'finding': 'ABI54 has no font-readiness feature or FontFaceSet exports: a late @font-face shows only as a width '
                       'change 57.77 -> 80; rv_image_decode already waits for a held image and the box paints red after it'},
    'green': {
        'fontReadinessAssertions': next(item['assertions'] for item in records if item['name'] == 'font_readiness'),
        'imageReadinessAssertions': next(item['assertions'] for item in records if item['name'] == 'image_readiness'),
        'fontReport': font['cases'], 'fontEvents': font['events'], 'imageReport': image['cases'],
        'repeats': len(repeats), 'repeatsDistinct': sorted(set(repeats)),
        'imageReadinessOnParentAbi54': '../image-readiness-evidence/parent-runtime.json',
        'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
        'rawAssertions': sum(item.get('assertions', 0) for item in records),
        'baselineProbesSameCount': all(entry.get('sameCount', True) for entry in comparison),
        'changedCounts': [entry for entry in comparison if entry.get('sameCount') is False],
        'newProbes': [entry['name'] for entry in comparison if entry.get('new')],
        'teardownCases': len(teardown),
        'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown),
    },
    'files': {},
}
for folder in [evidence, repo / 'docs/image-readiness-evidence']:
    for path in sorted(folder.rglob('*')):
        if path.is_file() and path.name != 'final-evidence.json':
            result['files'][path.relative_to(repo / 'docs').as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green']['rawAssertions'], result['green']['teardownCases'], result['green']['baselineProbesSameCount'],
      hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
