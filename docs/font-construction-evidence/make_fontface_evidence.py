"""Collects the WebCore T02 evidence into docs/font-construction-evidence: RED, the Chromium oracle, the batch GREEN
against the T01 baseline batch, the font_construction report and repeats, the generator delta and checks, teardown and
the per-probe comparison, each file with its SHA-256.

Usage: python -I make_fontface_evidence.py <candidate> <baseline batch dir> <baseline head>"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
candidate, baseline, baseline_head = sys.argv[1:4]
baseline = Path(baseline)
evidence = repo / 'docs/font-construction-evidence'
batch = repo / 'artifacts' / (candidate + '-batch')
runtime = repo / 'artifacts' / (candidate + '-frozen') / 'runtimes/win-x64/native'
copies = {
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts' / (candidate + '-frozen') / 'runtime-receipt.json',
    'source-patches.json': repo / 'artifacts' / candidate / 'source-patches.json',
    'build-receipt.json': repo / 'artifacts' / candidate / 'runtime-sha256.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'font-construction-probe.log': batch / 'font_construction.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
report = evidence / 'font-construction-report.json'
subprocess.run([sys.executable, '-I', '-X', 'utf8', str(repo / 'tests/abi/font_construction.py'), '--native-directory', str(runtime),
                '--webkit-source', 'C:/wk/src', '--evidence-json', str(report)], check=True, capture_output=True)
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
cases = json.loads(report.read_text(encoding='utf-8'))
oracle = json.loads((evidence / 'oracle-chromium.json').read_text(encoding='utf-8'))
result = {
    'group': ['T02 font construction/registration (ranvier-org/Ranvier.WebCore#73)'],
    'native': receipt['nativeVersion'],
    'abi': receipt['abiVersion'],
    'abiNote': 'placeholder: ABI stays 54; the integration batch assigns the number',
    'features': ['font-face-load (new)', 'dom:FontFace', 'dom:FontFaceSet', 'dom-constructor:FontFace', 'dom-font-face-set-values'],
    'members': ['rv_font_face_load', 'rv_font_face_loaded', 'rv_dom_font_face_create', 'rv_dom_font_face_get_*/set_* (family, style, '
                'weight, width, stretch, unicodeRange, featureSettings, display, ascent/descent/lineGapOverride, sizeAdjust)',
                'rv_dom_font_face_get_status', 'rv_dom_document_get_fonts', 'rv_dom_font_face_set_get_size/get_status/has/add/delete/clear/check/values',
                'RV_DOM_FONT_FACE_LOAD_STATUS_*', 'RV_DOM_FONT_FACE_SET_LOAD_STATUS_*', 'RvDomFontFaceDescriptors',
                'RvDomUnionDOMStringOrArrayBufferOrArrayBufferView', 'RvDomSequenceFontFace'],
    'sourcePatch': '0048-fontface-loaded-rejection.patch (root-applied): DOMPromiseProxyWithResolveCallback::rejectionCode and '
                   'FontFace::loadedPromise, inline, no layout change; its 25 reached units are recompiled',
    'generator': {'delta': 'gen-delta.txt', 'checks': 'gen-check.txt (Windows and WSL Ubuntu)',
                  'teachings': ['byte-span typedef BinaryData: ArrayBuffer then ArrayBufferView arms',
                                '[CallWith]/[SetterCallWith] on contextSettingsObjects through the script execution context',
                                'value-iterable snapshots (FontFaceSet.values)']},
    'qualifications': [
        'WebKit serializes unicode-range in lowercase hexadecimal (U+0-10ffff); Chromium in uppercase.',
        'WebKit FontFaceSet.check is true for an unloaded URL face it does not load; Chromium is false. Neither starts the load.',
        'A family holding U+0000 reads back as the escaped CSS string "Rv\\0 Nul" in WebKit; Chromium keeps the raw NUL. The '
        'family reaches the engine whole, so the transport is length-delimited.',
        'The engine accepts a face built in another document or host into a document\'s set (FontFaceSet.add); '
        'rv_font_face_load on such a face from the wrong host is RV_ERR_WRONG_HOST, and on a replaced document RV_ERR_DETACHED.',
        'FontFaceSet construction, its load and ready promises and on* handlers stay out of the generated surface; T01 rv_fonts_* '
        'cover load, ready and events for document.fonts.',
        'The metric-override descriptors (ascentOverride, descentOverride, lineGapOverride) are attributes only; '
        'FontFaceDescriptors leaves its setting-gated fields out.',
        'TTF, CFF OTF, WOFF and WOFF2 load from bytes on win-x64 as in Chromium; other ports report through the CI probe.',
    ],
    'sourceHeadOfBatch': receipt['sourceHead'],
    'baseline': {'batch': str(baseline), 'head': baseline_head,
                 'rawAssertions': sum(item.get('assertions', 0) for item in base.values() if item['name'] not in ('frames', 'teardown')),
                 'teardownCases': len(base_teardown)},
    'red': {'native': 'red-native.json (red_native.py)', 'chromium': 'oracle-chromium.json (oracle_chromium.mjs, ' + oracle['browser'] + ')',
            'finding': 'ABI54 builds a font only from bytes through rv_font_load: no descriptors, URL source, FontFace handle or '
                       'status, and no FontFaceSet registration; width 57.77 -> 80 -> 57.77 only on release'},
    'green': {
        'fontConstructionAssertions': next(item['assertions'] for item in records if item['name'] == 'font_construction'),
        'report': cases['cases'],
        'repeats': len(repeats), 'repeatsDistinct': sorted(set(repeats)),
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
for path in sorted(evidence.rglob('*')):
    if path.is_file() and path.name != 'final-evidence.json':
        result['files'][path.relative_to(repo / 'docs').as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green']['rawAssertions'], result['green']['teardownCases'], result['green']['baselineProbesSameCount'],
      hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
