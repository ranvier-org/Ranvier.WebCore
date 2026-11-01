"""Writes final-evidence.json: the R04 native proof summary with the SHA-256 of every evidence file next to it."""
import hashlib, json, subprocess
from pathlib import Path
here = Path(__file__).resolve().parent
results = json.loads((here / 'batch-results.json').read_text(encoding='utf-8'))
receipt = json.loads((here / 'runtime-receipt.json').read_text(encoding='utf-8'))
repeat = (here / 'canvas-paints-repeat30.txt').read_text(encoding='utf-8').splitlines()
summary = {
    'group': 'R04 canvas paints (ranvier-org/Ranvier.WebCore#93)',
    'nativeHead': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=here, capture_output=True, text=True, check=True).stdout.strip(),
    'runtimeSourceHead': receipt['sourceHead'], 'abi': receipt['abiVersion'],
    'runtime': {e['name']: e['sha256'] for e in receipt['shippingFiles'] if e['name'].endswith('.dll') and e['name'].startswith(('WebCore', 'Ranvier', 'JavaScript'))},
    'canvasPaintsAssertions': next(r['assertions'] for r in results if r['name'] == 'canvas_paints'),
    'repeat30': {'runs': len(repeat), 'distinct': sorted(set(repeat))},
    'fullBatchRaw': sum(r.get('assertions', 0) for r in results), 'probes': len(results),
    'teardownProbes': len(json.loads((here / 'teardown-probes.json').read_text(encoding='utf-8'))),
    'qualifications': ['ImageBitmap and CSSStyleImageValue arms of createPattern have no producer before R06/R07 and are not drawn; canvas and decoded <img> sources are',
                       'gradient and blurred-shadow pixels are compared within 6 levels of Chromium per channel; stroke, dash, pattern and solid shadow pixels exactly'],
    'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(here.iterdir()) if p.is_file() and p.name != 'final-evidence.json'},
}
(here / 'final-evidence.json').write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in summary.items() if k != 'files'}))
