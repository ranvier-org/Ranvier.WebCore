"""Writes final-evidence.json: the R05 native proof summary, the native-vs-Chromium metric comparison, and the SHA-256
of every evidence file next to it."""
import hashlib, json, subprocess
from pathlib import Path
here = Path(__file__).resolve().parent
results = json.loads((here / 'batch-results.json').read_text(encoding='utf-8'))
receipt = json.loads((here / 'runtime-receipt.json').read_text(encoding='utf-8'))
repeat = (here / 'canvas-text-repeat30.txt').read_text(encoding='utf-8').splitlines()
native = json.loads((here / 'canvas-text-report.json').read_text(encoding='utf-8'))
chromium = json.loads((here / 'red-chromium.json').read_text(encoding='utf-8'))


def camel(name):
    head, *rest = name.split('_')
    return head + ''.join(part.capitalize() for part in rest)


pairs = {'measureX': 'measureX', 'measureP': 'measureP', 'measureE': 'measureE', 'measureEmpty': 'measureEmpty', 'measureSpace': 'measureSpace',
         'letterSpaced': 'letterSpaced', 'wordSpaced': 'wordSpaced', 'rtlStart': 'rtlStart'}
pairs.update({'align_' + a.upper(): 'align_' + a for a in ['start', 'end', 'left', 'right', 'center']})
pairs.update({'baseline_' + b.upper(): 'baseline_' + b for b in ['top', 'hanging', 'middle', 'alphabetic', 'ideographic', 'bottom']})
comparison = {}
for ours, theirs in pairs.items():
    row = {}
    for name, value in native[ours].items():
        other = chromium[theirs].get(camel(name))
        row[camel(name)] = {'native': value, 'chromium': other, 'delta': None if other is None else round(value - other, 6)}
    comparison[ours] = row
differences = {}
for case, row in comparison.items():
    for member, cell in row.items():
        if cell['delta'] is None:
            differences.setdefault(member, 'absent in Chromium')
        elif cell['delta'] != 0 and differences.get(member) != 'absent in Chromium':
            differences[member] = max(differences.get(member, 0), abs(cell['delta']))
summary = {
    'group': 'R05 canvas text (ranvier-org/Ranvier.WebCore#94)',
    'nativeHead': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=here, capture_output=True, text=True, check=True).stdout.strip(),
    'runtimeSourceHead': receipt['sourceHead'], 'abi': receipt['abiVersion'],
    'runtime': {e['name']: e['sha256'] for e in receipt['shippingFiles'] if e['name'].endswith('.dll') and e['name'].startswith(('WebCore', 'Ranvier', 'JavaScript'))},
    'canvasTextAssertions': next(r['assertions'] for r in results if r['name'] == 'canvas_text'),
    'repeat30': {'runs': sum(int(line.split()[0]) for line in repeat if line.strip()) if repeat and repeat[0].strip()[0].isdigit() else len(repeat), 'distinct': sorted(set(repeat))},
    'fullBatchRaw': sum(r.get('assertions', 0) for r in results), 'probes': len(results),
    'teardownProbes': len(json.loads((here / 'teardown-probes.json').read_text(encoding='utf-8'))),
    'metricDifferencesFromChromium': {'maxAbsDeltaByMember': differences, 'cases': len(comparison), 'detail': 'chromium-comparison.json'},
    'qualifications': [
        'fontKerning, fontStretch, fontVariantCaps and textRendering are Unsupported: the pinned WebKit IDL has none of them, and adding them needs new CanvasRenderingContext2DBase::State fields (a class layout change); the probe asserts no export exists',
        'Chromium 156 has no TextMetrics.emHeightAscent/emHeightDescent (undefined); WebKit reports them; Ranvier.Dom TextMeasurement carries them as float option (None in Chromium)',
        'Chromium inflates glyph ink bounds by 1px (actualBoundingBoxLeft 1 for Ahem); actual bounding boxes are compared within 1px',
        'WebKit reports the hanging baseline at the font ascent and aligns textBaseline=hanging like top; Chromium synthesises 0.8 of the ascent for fonts without a BASE table',
        'WebKit reads an inherited direction back resolved (ltr/rtl); Chromium reads "inherit"',
        "WebKit's actualBoundingBoxRight includes the trailing letterSpacing (75 for 'XXX' at 5px; Chromium 70+1)",
        'pixel samples are taken at least 2px from a glyph edge; strokeText edges are asserted blue-dominant (b>=200, r,g<=80) because both engines antialias them',
        'viewport_scroll is checked by exit code only (timing-dependent count); its count this run is recorded in batch-results.json',
        'the Ahem face loads through T01 rv_fonts_load from a data: URL @font-face; nothing sleeps',
        'text-candidate-1 was built from the working tree that was committed unchanged as caa223e (host/ and gen/ diff empty; the dirty list is in build-runtime-sha256.json); its parent is R04 paints-candidate-1 (65fe9d9) with RanvierDomGlue, T01 RanvierResourceGlue and the four host units recompiled',
    ],
    'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(here.iterdir()) if p.is_file() and p.name != 'final-evidence.json'},
}
(here / 'final-evidence.json').write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8')
(here / 'chromium-comparison.json').write_text(json.dumps(comparison, indent=1) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in summary.items() if k != 'files'}, indent=1))
