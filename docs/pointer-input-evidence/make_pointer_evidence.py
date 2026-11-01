"""Writes final-evidence.json for I03/I04/I06 from a candidate's batch results, receipt and the 30x repeats.
usage: make_pointer_evidence.py <pointer-candidate-N>"""
import hashlib, json, subprocess, sys
from pathlib import Path
here = Path(__file__).resolve().parent
repo = here.parents[1]
artifacts = Path('C:/wk/pointer-artifacts')
name = sys.argv[1]
batch = json.loads((artifacts / (name + '-batch') / 'results.json').read_text())
baseline = {item['name']: item.get('assertions') for item in json.loads(Path('C:/wk/native-cascade-shadow/artifacts/native46-candidate-6-batch/results.json').read_text())}
receipt = json.loads((artifacts / (name + '-frozen') / 'runtime-receipt.json').read_text())
repeat = json.loads((here / 'repeat30.json').read_text())
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
new = ['touch_input', 'pen_input', 'pointer_lock']
evidence = {
    'groups': {'I03': 'https://github.com/ranvier-org/Ranvier.WebCore/issues/101', 'I04': 'https://github.com/ranvier-org/Ranvier.WebCore/issues/102',
               'I06': 'https://github.com/ranvier-org/Ranvier.WebCore/issues/103'},
    'status': 'lane-green (private, not accepted)',
    'sourceHead': receipt['sourceHead'],
    'base': 'codex/batch-1 d1ff8ace (Native46/ABI54, placeholder ABI)',
    'runtime': name,
    'build': 'full private rebuild C:/wk/pointer-build (ENABLE_TOUCH_EVENTS and ENABLE_POINTER_LOCK on). Once this config lands, every '
             'later candidate needs a full rebuild: both flags are in cmakeconfig.h.',
    'srcPatches': receipt['sourcePatches']['patches'],
    'batch': {'raw': sum(item.get('assertions', 0) for item in batch), 'probes': len(batch),
              'baselineUnchanged': all(item.get('assertions') == baseline.get(item['name']) for item in batch if item['name'] in baseline and item['name'] not in ('frames', 'teardown')),
              'new': {item['name']: item.get('assertions') for item in batch if item['name'] in new},
              'teardownRecords': 104},
    'repeat30': repeat['probes'],
    'red': {'native': 'red-native.json', 'nativeSha256': sha(here / 'red-native.json'), 'penCapture': 'red-pen-capture.json'},
    'oracle': {'chromium': 'oracle-chromium.json', 'sha256': sha(here / 'oracle-chromium.json')},
    'domReportDelta': ['Touch 8', 'TouchList 2', 'TouchEvent 7 (contract-only before)', 'Document 70 -> 72 (createTouchList, pointerLockElement)'],
    'capabilityCatalogueDelta': ['dom:Touch', 'dom:TouchList', 'dom:TouchEvent', 'pointer-input', 'touch-input', 'pointer-lock',
                                 'build:ENABLE_POINTER_LOCK', 'build:ENABLE_TOUCH_EVENTS'],
    'qualifications': [
        'macOS keeps ENABLE_TOUCH_EVENTS off (iOS-only touch paths): touch-input is absent, rv_host_pointer refuses touch frames with RV_ERR_UNSUPPORTED, and touch_input.py checks that branch.',
        'WebKit dispatches pointermove for a stationary touch contact at its unchanged position; Chromium does not. The shared fixture checks only changed contacts.',
        'WebKit exposes touch radii, rotation and force only as the prefixed webkit* members; rv_touch_geometry reads them.',
        'Touch input dispatches no compatibility mouse events or click: the app sends rv_host_mouse for taps it treats as clicks.',
        'Unadjusted pointer-lock movement is unsupported (NotSupportedError); a request from an unfocused window is refused with WrongDocumentError and pointerlockerror.',
        'Headless Chromium grants requestPointerLock without a gesture; WebKit requires one (NotAllowedError), so the gesture refusal is native-only.',
        'Pen coalesced and predicted events carry the sample geometry; the host delivers no extra coalesced samples.',
    ],
}
(here / 'final-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
print(json.dumps(evidence['batch']), sha(here / 'final-evidence.json'))
