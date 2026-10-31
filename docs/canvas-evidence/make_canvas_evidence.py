"""Collects the R01 canvas context evidence into docs/canvas-evidence: RED, the batch GREEN, the 30x repeat, teardown
and the receipts, each file with its SHA-256.

Usage: python -I make_canvas_evidence.py <candidate> <repeat file> <batch head> <baseline batch-green.json>"""
import hashlib
import json
import sys
from pathlib import Path

repo = Path('C:/wk/native-canvas')
candidate = sys.argv[1]
evidence = repo / 'docs/canvas-evidence'
batch = repo / 'artifacts' / (candidate + '-batch')
copies = {
    'canvas-context-repeat30.txt': Path(sys.argv[2]),
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts' / (candidate + '-frozen') / 'runtime-receipt.json',
    'source-patches.json': repo / 'artifacts' / candidate / 'source-patches.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'canvas-context-probe.log': batch / 'canvas_context.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
baseline = json.loads(Path(sys.argv[4]).read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
patches = json.loads((evidence / 'source-patches.json').read_text())
red = json.loads((evidence / 'red-native.json').read_text())
fallback = json.loads((evidence / 'red-fallback-rendering.json').read_text())
chromium = json.loads((evidence / 'red-chromium.json').read_text())
report = json.loads((evidence / 'canvas-context-report.json').read_text())
repeats = (evidence / 'canvas-context-repeat30.txt').read_text().splitlines()
assertions = next(item['assertions'] for item in records if item['name'] == 'canvas_context')
baseline_counts = {item['name']: item.get('assertions') for item in baseline if item['name'] not in ('frames', 'teardown')}
record_counts = {item['name']: item.get('assertions') for item in records}
result = {
    'group': ['R01 #90'],
    'status': 'green (private Windows x64 slim; not accepted)',
    'native': receipt['nativeVersion'],
    'abi': receipt['abiVersion'],
    'abiNote': 'placeholder ABI55 on batch-1 ABI54; root assigns NativeNN/ABI at integration',
    'features': ['canvas-context', 'dom:HTMLCanvasElement', 'dom:CanvasRenderingContext2D', 'dom:CanvasGradient', 'dom:CanvasPattern'],
    'members': ['rv_canvas_get_context', 'rv_canvas_context_2d_attributes', 'RvCanvas2DSettings', 'RV_CANVAS_CONTEXT_*',
                'RV_CANVAS_COLOR_SPACE_*', 'RV_CANVAS_COLOR_TYPE_*', 'rv_dom_html_canvas_element_get/set_width/height',
                'rv_dom_canvas_rendering_context2_d_get_canvas', 'rv_dom_canvas_rendering_context2_d_get/set_fill_style',
                'rv_dom_canvas_rendering_context2_d_fill_rect', 'rv_dom_canvas_rendering_context2_d_clear_rect',
                'rv_dom_canvas_rendering_context2_d_release/retain', 'rv_dom_canvas_gradient_release/retain',
                'rv_dom_canvas_pattern_release/retain', 'rv_dom_union_dom_string_or_canvas_gradient_or_canvas_pattern_release'],
    'engine': 'HTMLCanvasElement::getContext2d and CanvasRenderingContext2DBase from host/RanvierCanvasGlue.cpp (compiled into '
              'WebCore); generated members from gen/domgen.py memberSelections; WebKit patch 0042 renders a context-bearing canvas '
              'without script',
    'sourcePatch': {'patch': '0042-canvas-renders-embedder-context.patch', 'units': list(patches.get('ownPatchUnits', {})),
                    'privateProofDisassemblyEqual': (patches.get('privateCanvasSource') or {}).get('disassemblyEqual'),
                    'patch0040': patches.get('patch0040')},
    'sourceHeadOfBatch': receipt['sourceHead'],
    'batchRunHead': sys.argv[3],
    'red': {'exports': red['exports'], 'abi': red['abi'],
            'nonReplacedLayout': {'canvasDisplayBlockNoCssSize': red['snapshotSize'], 'chromium': chromium['blockCanvasWithoutContext']},
            'fallbackRendering': fallback['reading'], 'cause': fallback['cause']},
    'green': {'canvasContextAssertions': assertions, 'repeats': len(repeats), 'repeatsDistinct': sorted(set(repeats)),
              'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions') or 0 for item in records),
              'baselineRawAssertions': sum(item.get('assertions') or 0 for item in baseline),
              'baselineProbesChanged': {n: [baseline_counts[n], record_counts.get(n)] for n in baseline_counts if record_counts.get(n) != baseline_counts[n]},
              'teardownCases': len(teardown),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown)},
    'measured': report,
    'chromiumOracle': {'browser': chromium['browser'], 'file': 'red-chromium.json'},
    'qualifications': [
        'Profile: 2D contexts only, alpha true, sRGB, unorm8; other types and settings return RV_ERR_UNSUPPORTED on every provider.',
        'WebKit ignores the alpha setting (FIXME in CanvasRenderingContext2DSettings.idl) and draws a float16 colorType into an 8-bit '
        'buffer while reporting float16; the ABI rejects both requests instead of reporting them.',
        'display-p3 needs ENABLE_PREDEFINED_COLOR_SPACE_DISPLAY_P3 (OFF on the slim build).',
        'BITMAP_RENDERER is deferred to R07; WebGL/WebGL2/WebGPU are Unsupported (ENABLE_WEBGL OFF, GPU paused).',
        'WebKit has no CanvasRenderingContext2D.isContextLost; R01 does not expose it.',
        'Pixels are read from the host software paint and rv_element_snapshot; R01 has no getImageData (R06).',
    ],
}
files = sorted(p for p in evidence.iterdir() if p.is_file() and p.name != 'final-evidence.json')
result['files'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(evidence / 'final-evidence.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result['green'], indent=1))
