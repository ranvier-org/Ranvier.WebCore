"""Collects the R06 canvas pixel evidence into docs/canvas-pixels-evidence: RED, the batch GREEN, the 30x repeat, the
probe report, teardown and the receipts, each file with its SHA-256.

Usage: python -I make_pixels_evidence.py <candidate> <batch head>"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

repo = Path('C:/wk/native-canvas-pixels')
candidate = sys.argv[1]
evidence = repo / 'docs/canvas-pixels-evidence'
batch = repo / 'artifacts' / (candidate + '-batch')
frozen = repo / 'artifacts' / (candidate + '-frozen') / 'runtimes/win-x64/native'
subprocess.run([sys.executable, '-I', '-X', 'utf8', str(repo / 'tests/abi/canvas_pixels.py'), '--native-directory', str(frozen),
                '--evidence-json', str(evidence / 'canvas-pixels-report.json')], check=True)
copies = {
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts' / (candidate + '-frozen') / 'runtime-receipt.json',
    'source-patches.json': repo / 'artifacts' / candidate / 'source-patches.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'canvas-pixels-probe.log': batch / 'canvas_pixels.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
baseline = json.loads((evidence / 'baseline-r01-results.json').read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
patches = json.loads((evidence / 'source-patches.json').read_text())
red = json.loads((evidence / 'red-native.json').read_text())
chromium = json.loads((evidence / 'red-chromium.json').read_text())
report = json.loads((evidence / 'canvas-pixels-report.json').read_text())
repeats = (evidence / 'canvas-pixels-repeat30.txt').read_text().splitlines()
baseline_counts = {item['name']: item.get('assertions') for item in baseline if item['name'] not in ('frames', 'teardown')}
record_counts = {item['name']: item.get('assertions') for item in records}
# Each probe key the Chromium oracle measured as well, with both values.
compared = {key: {'native': report[key], 'chromium': chromium[key]} for key in report if key in chromium}
result = {
    'group': ['R06 #95'],
    'status': 'green (private Windows x64 slim; not accepted)',
    'native': receipt['nativeVersion'],
    'abi': receipt['abiVersion'],
    'abiNote': 'placeholder ABI55 on the R01 base; root assigns NativeNN/ABI at integration',
    'features': ['canvas-pixels', 'dom:ImageData', 'dom:ImageBitmap'],
    'members': ['rv_image_data_create', 'rv_image_data_layout', 'rv_image_data_read', 'rv_image_data_write', 'RvImageDataLayout',
                'rv_dom_image_data_get_width/height', 'rv_dom_image_data_release/retain', 'rv_dom_image_bitmap_release/retain',
                'rv_dom_canvas_rendering_context2_d_create_image_data_3/_1', 'rv_dom_canvas_rendering_context2_d_get_image_data',
                'rv_dom_canvas_rendering_context2_d_put_image_data_3/_7', 'rv_dom_canvas_rendering_context2_d_draw_image_3/_5/_9',
                'RvDomImageDataSettings', 'RV_DOM_IMAGE_DATA_PIXEL_FORMAT_*',
                'rv_dom_union_html_image_element_or_html_canvas_element_or_svg_image_element_or_image_bitmap_or_css_style_image_value_release'],
    'engine': 'ImageData and CanvasRenderingContext2DBase from host/RanvierCanvasPixelsGlue.cpp (compiled into WebCore) and the '
              'generated members (gen/dom.json memberSelections; unionArgumentConversions converts CanvasImageSource into the '
              "engine's Variant)",
    'hostGlue': patches.get('hostGlue'),
    'sourceHeadOfBatch': receipt['sourceHead'],
    'batchRunHead': sys.argv[2],
    'red': {'exports': red['exports'], 'abiHas': red['abiHas'], 'abi': red['abi']},
    'green': {'canvasPixelsAssertions': record_counts.get('canvas_pixels'), 'repeats': len(repeats), 'repeatsDistinct': sorted(set(repeats)),
              'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions') or 0 for item in records),
              'baselineRawAssertions': sum(item.get('assertions') or 0 for item in baseline),
              'baselineProbesChanged': {n: [baseline_counts[n], record_counts.get(n)] for n in baseline_counts if record_counts.get(n) != baseline_counts[n]},
              'teardownCases': len(teardown),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown)},
    'measured': report,
    'chromiumOracle': {'browser': chromium['browser'], 'file': 'red-chromium.json', 'compared': compared},
    'qualifications': [
        'Profile: sRGB ImageData in rgba-unorm8 only; display-p3 and rgba-float16 return RV_ERR_UNSUPPORTED (CanvasColorSpaceEnabled and '
        'CanvasColorTypeEnabled are off in WebCore on Windows and Linux), so RvDomImageDataSettings carries no fields.',
        'new ImageData(65536, 65536) raises RangeError in WebKit and IndexSizeError in Chromium 156.',
        'The ImageBitmap arm of drawImage is exercised in R07, which creates ImageBitmaps; HTMLVideoElement is outside the union '
        '(ENABLE_VIDEO OFF on slim) and CSSStyleImageValue is accepted but not drawn here.',
        'putImageData ignoring globalAlpha and globalCompositeOperation is in the Chromium oracle only: those setters belong to R03.',
        'Tainting is measured with a cross-origin <img> served by rv_host_set_resource_handler; crossorigin=anonymous stays readable.',
    ],
}
files = sorted(p for p in evidence.iterdir() if p.is_file() and p.name != 'final-evidence.json' and p.suffix != '.pyc')
result['files'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(evidence / 'final-evidence.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result['green'], indent=1))
