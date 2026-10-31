"""Collects the R07 canvas export evidence into docs/canvas-export-evidence: RED, the batch GREEN, the 30x repeat, the
probe report, teardown and the receipts, each file with its SHA-256.

Usage: python -I make_export_evidence.py <candidate> <batch head>"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

repo = Path('C:/wk/native-canvas-pixels')
candidate = sys.argv[1]
evidence = repo / 'docs/canvas-export-evidence'
batch = repo / 'artifacts' / (candidate + '-batch')
frozen = repo / 'artifacts' / (candidate + '-frozen') / 'runtimes/win-x64/native'
subprocess.run([sys.executable, '-I', '-X', 'utf8', str(repo / 'tests/abi/canvas_export.py'), '--native-directory', str(frozen),
                '--evidence-json', str(evidence / 'canvas-export-report.json')], check=True)
copies = {
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts' / (candidate + '-frozen') / 'runtime-receipt.json',
    'source-patches.json': repo / 'artifacts' / candidate / 'source-patches.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'canvas-export-probe.log': batch / 'canvas_export.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
baseline = json.loads((repo / 'docs/canvas-pixels-evidence/batch-green.json').read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
patches = json.loads((evidence / 'source-patches.json').read_text())
red = json.loads((evidence / 'red-native.json').read_text())
chromium = json.loads((evidence / 'red-chromium.json').read_text())
report = json.loads((evidence / 'canvas-export-report.json').read_text())
repeats = (evidence / 'canvas-export-repeat30.txt').read_text().splitlines()
baseline_counts = {item['name']: item.get('assertions') for item in baseline if item['name'] not in ('frames', 'teardown')}
record_counts = {item['name']: item.get('assertions') for item in records}
# Each probe key the Chromium oracle measured as well, with both values.
compared = {key: {'native': report[key], 'chromium': chromium[key]} for key in report if key in chromium}
result = {
    'group': ['R07 #96'],
    'status': 'green (private Windows x64 slim; not accepted)',
    'native': receipt['nativeVersion'],
    'abi': receipt['abiVersion'],
    'abiNote': 'placeholder ABI55 on the R06 base with B06 and the R12 encoder merged; root assigns NativeNN/ABI at integration',
    'features': ['canvas-export', 'image-bitmaps', 'dom:ImageBitmapRenderingContext'],
    'members': ['rv_canvas_encode', 'rv_canvas_to_data_url', 'rv_canvas_to_blob', 'rv_canvas_get_bitmap_context',
                'rv_image_bitmap_create', 'rv_image_bitmap_result', 'rv_image_bitmap_error', 'RvImageBitmapOptions',
                'RV_IMAGE_BITMAP_SOURCE_*', 'RV_IMAGE_BITMAP_ORIENTATION_*', 'RV_IMAGE_BITMAP_PREMULTIPLY_*',
                'RV_IMAGE_BITMAP_COLOR_SPACE_CONVERSION_*', 'RV_IMAGE_BITMAP_RESIZE_*', 'rv_dom_image_bitmap_get_width/height',
                'rv_dom_image_bitmap_close', 'rv_dom_image_bitmap_rendering_context_transfer_from_image_bitmap', 'rv_dom_image_bitmap_rendering_context_release/retain'],
    'engine': 'HTMLCanvasElement buffers, Blob and the bitmaprenderer context from host/RanvierCanvasExportGlue.cpp, encoding through '
              'Ranvier::Internal::encodeImage (R12), and ImageBitmap::createCompletionHandler as a resource operation in '
              'host/RanvierResourceGlue.cpp',
    'sourcePatches': {name: patches['patches'][name] for name in ['0049-image-bitmap-crop-completion-handler.patch', '0050-image-bitmap-unaccelerated-buffers.patch']},
    'ownPatchUnits': patches.get('ownPatchUnits'),
    'patch0043Owner': patches.get('patch0043Owner'),
    'hostGlue': patches.get('hostGlue'),
    'sourceHeadOfBatch': receipt['sourceHead'],
    'batchRunHead': sys.argv[2],
    'red': {'exports': red['exports'], 'abiHas': red['abiHas'], 'abi': red['abi'], 'bitmapRendererStatus': red['bitmapRendererStatus'],
            'patch0049': 'red-patch-0049-compile.log', 'patch0050': 'red-patch-0050.log'},
    'green': {'canvasExportAssertions': record_counts.get('canvas_export'), 'repeats': len(repeats), 'repeatsDistinct': sorted(set(repeats)),
              'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions') or 0 for item in records),
              'baselineRawAssertions': sum(item.get('assertions') or 0 for item in baseline),
              'baselineProbesChanged': {n: [baseline_counts[n], record_counts.get(n)] for n in baseline_counts if record_counts.get(n) != baseline_counts[n]},
              'mediaCapabilitiesAssertions': record_counts.get('media_capabilities'),
              'teardownCases': len(teardown),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown)},
    'measured': report,
    'chromiumOracle': {'browser': chromium['browser'], 'file': 'red-chromium.json', 'compared': compared},
    'qualifications': [
        'An encoding the flavor cannot encode, RGBA8 and an unknown value return RV_ERR_UNSUPPORTED; Chromium falls back to PNG '
        '(red-chromium.json toDataURL.unknownFallsBackToPng, toBlobUnknown).',
        'WEBP depends on the flavor encoder: the probe asserts a RIFF/WEBP image or RV_ERR_UNSUPPORTED from the encoder status; '
        'the "image-encoding-*" platform facilities report unknown on this runtime (finding for R12 integration).',
        'toBlob completes during rv_canvas_to_blob: there is no callback, and a zero-size canvas gives a NULL Blob as the browser '
        'callback gets null.',
        'createImageBitmap sources: <img>, SVG <image>, <canvas>, ImageBitmap, ImageData and Blob. HTMLVideoElement, OffscreenCanvas and '
        'VideoFrame are outside slim (ENABLE_VIDEO, ENABLE_OFFSCREEN_CANVAS, ENABLE_WEB_CODECS OFF); CSSStyleImageValue is not a source kind.',
        'ImageBitmap transfer is transferFromImageBitmap, which detaches the source; postMessage transfer needs a script realm.',
        'ImageBitmap buffers are unaccelerated where canvases are (patch 0050); GPU work is paused.',
        'ImageBitmapRenderingContext.canvas is not generated: its single-arm union typedef ImageBitmapCanvas would name a second '
        'HTMLCanvasElement type in the F# model; the app holds the canvas it passed to rv_canvas_get_bitmap_context.',
    ],
}
files = sorted(p for p in evidence.iterdir() if p.is_file() and p.name != 'final-evidence.json' and p.suffix != '.pyc')
result['files'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(evidence / 'final-evidence.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result['green'], indent=1))
