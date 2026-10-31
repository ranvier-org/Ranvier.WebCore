"""Writes final-evidence.json: the R03 native proof summary with the SHA-256 of every evidence file next to it."""
import hashlib, json, subprocess
from pathlib import Path
here = Path(__file__).resolve().parent
results = json.loads((here / 'batch-results.json').read_text(encoding='utf-8'))
receipt = json.loads((here / 'runtime-receipt.json').read_text(encoding='utf-8'))
repeat = (here / 'canvas-state-repeat30.txt').read_text(encoding='utf-8').splitlines()
summary = {
    'group': 'R03 canvas state, transforms and compositing (ranvier-org/Ranvier.WebCore#92)',
    'nativeHead': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=here, capture_output=True, text=True, check=True).stdout.strip(),
    'runtimeSourceHead': receipt['sourceHead'], 'abi': receipt['abiVersion'],
    'runtime': {e['name']: e['sha256'] for e in receipt['shippingFiles'] if e['name'].endswith('.dll') and e['name'].startswith(('WebCore', 'Ranvier', 'JavaScript'))},
    'canvasStateAssertions': next(r['assertions'] for r in results if r['name'] == 'canvas_state'),
    'repeat30': {'runs': len(repeat), 'distinct': sorted(set(repeat))},
    'fullBatchRaw': sum(r.get('assertions', 0) for r in results), 'probes': len(results),
    'teardownProbes': len(json.loads((here / 'teardown-probes.json').read_text(encoding='utf-8'))),
    'qualifications': ['canvas layers (beginLayer/endLayer) return RV_ERR_UNSUPPORTED: CanvasLayersEnabled stays off and Chromium 156 has no layers to compare with',
                       'WebKit accepts its own operator names darker, plus-darker, plus-lighter and clear, which Chromium ignores (engine difference)',
                       'viewport_scroll counted 3231 instead of 3232 once while another probe ran in parallel; its rerun and 5 standalone runs on the R02 and R03 runtimes count 3232 (viewport-scroll-timing-3231.log); the probe has a timing-dependent count outside this group'],
    'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(here.iterdir()) if p.is_file() and p.name != 'final-evidence.json'},
}
(here / 'final-evidence.json').write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in summary.items() if k != 'files'}))
