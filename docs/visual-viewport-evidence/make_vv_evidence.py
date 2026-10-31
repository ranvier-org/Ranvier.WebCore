"""Collects the G03 visual viewport evidence into docs/visual-viewport-evidence: RED, the batch GREEN, the 30x repeats,
teardown and the measured qualifications, each file with its SHA-256.

Usage: python -I make_vv_evidence.py <candidate> <repeat file>"""
import hashlib
import json
import sys
from pathlib import Path

repo = Path('C:/wk/native-vv')
candidate = sys.argv[1]
evidence = repo / 'docs/visual-viewport-evidence'
batch = repo / 'artifacts' / (candidate + '-batch')
copies = {
    'build_vv_candidate.py': repo / 'artifacts/build_vv_candidate.py',
    'visual-viewport-repeat30.txt': Path(sys.argv[2]),
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts' / (candidate + '-frozen') / 'runtime-receipt.json',
    'source-patches.json': repo / 'artifacts' / candidate / 'source-patches.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'visual-viewport-probe.log': batch / 'visual_viewport.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
oracle = json.loads((repo / 'tests/fixtures/visual-viewport-oracle.json').read_text())
repeats = (evidence / 'visual-viewport-repeat30.txt').read_text().splitlines()
assertions = next(item['assertions'] for item in records if item['name'] == 'visual_viewport')
result = {
    'group': ['G03 #48'],
    'native': receipt['nativeVersion'],
    'abi': receipt['abiVersion'],
    'features': ['visual-viewport', 'dom:VisualViewport', 'page-scale', 'obscured-insets'],
    'members': ['Window.visualViewport', 'VisualViewport.offsetLeft/offsetTop/pageLeft/pageTop/width/height/scale',
                'resize and scroll events through rv_event_target_add_listener', 'rv_host_set_page_scale', 'rv_host_page_scale',
                'rv_host_set_obscured_insets'],
    'excluded': ['VisualViewport.onresize/onscroll handler attributes (EventHandler; the managed service subscribes with listeners)',
                 'onscrollend (Chromium only; not in the pinned WebKit IDL)'],
    'sourceHeadOfBatch': receipt['sourceHead'],
    'batchRunHead': {'head': '8ced3b8', 'note': 'b654195 plus tests/abi/crypto_random.py ABI = 45 only; the runtime is the b654195 build'},
    'stackedOn': 'B22 c78a71a (Native36/ABI44), T06 901ced5 (Native35/ABI43), D14 23dd017 (Native34/ABI42, patch 0037), H13 3c7e8d4 (Native33/ABI41), G09 fb87eb0 (Native32/ABI40)',
    'red': {'files': ['red-chromium.json', 'red-native.json', 'red-navigation-chromium.json'],
            'native32': 'no VisualViewport exports, no page scale or obscured inset input; VisualViewportAPIEnabled off in WebCore'},
    'green': {'visualViewportAssertions': assertions, 'repeats': len(repeats), 'repeatsDistinct': sorted(set(repeats)),
              'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions', 0) for item in records),
              'probesRun': [{'name': item['name'], 'exitCode': item['exitCode'], 'assertions': item.get('assertions')} for item in records],
              'teardownCases': len(teardown), 'teardownCasesAdded': len([r for r in teardown if 'visual viewport' in r['probe']]),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown)},
    'chromiumOracle': {'browser': oracle['browser'], 'steps': len(oracle['steps'])},
    'catalogueRegenerated': {'names': ['dom:VisualViewport', 'visual-viewport', 'page-scale', 'obscured-insets', 'dom:CaretPosition'],
                             'capabilitiesNativeChecks': [7340, 7522],
                             'note': 'capability catalogue regeneration; dom:CaretPosition was missing from the G09 catalogue at fb87eb0'},
    'settingEnabled': {'setting': 'VisualViewportAPIEnabled', 'effect': 'every other probe kept its assertion count and output'},
    'measured': {
        'pageScale': 'non-finite or <= 0 returns RV_ERR_UNSUPPORTED; others apply unclamped (0.01, 0.25, 10, 20 checked); sizes are LayoutUnits (320 / 1.5 reads 213.328125)',
        'obscuredInsets': 'shrink VisualViewport width/height and innerWidth/innerHeight by the covered edges; window resize then visualViewport resize; '
                          'document coordinates stay in place, top inset included; rv_host_element_at finds nothing in the covered right and bottom areas',
        'detached': 'members of a VisualViewport held past rv_host_destroy return RV_ERR_DETACHED',
    },
    'qualifications': [
        {'name': 'layout viewport at the origin while page-scaled', 'steps': ['scrollTo(100, 50) at page scale 2', 'wheel 30, 40 at 150, 100 at page scale 2'],
         'native': 'offsetLeft/offsetTop equal pageLeft/pageTop (100/50, 115/70)', 'chromium': 'offsets 0/0 and 15/20'},
        {'name': 'pans scroll the window', 'steps': ['scrollTo(100, 50) at page scale 2', 'wheel 30, 40 at 150, 100 at page scale 2', 'page scale 1 at 100,50'],
         'native': 'window scroll and visualViewport scroll fire together; the wheel moves scrollX to 115', 'chromium': 'the wheel pans only the visual viewport (scrollX stays 100)'},
        {'name': 'innerWidth at page scale 2', 'native': 150, 'chromium': 300},
        {'name': 'window reuse across a page replacement', 'native': 'LoadSvg keeps the frame window and its VisualViewport, which follows the new page',
         'chromium': 'a navigated frame gets a new VisualViewport; the held one reads zeros (red-navigation-chromium.json)',
         'managed': 'the native provider reads Detached once the host shows another document'},
        {'name': 'browser-only', 'chromium': ['onscrollend', 'all-zero members (scale 0) of a detached frame'], 'managed': 'the browser provider reads Detached'},
    ],
    'files': {},
}
for path in sorted(evidence.iterdir()):
    if path.is_file() and path.name != 'final-evidence.json':
        result['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green']['rawAssertions'], result['green']['teardownCases'], hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
