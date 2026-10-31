"""Collects the I11 component accessibility evidence into docs/element-internals-evidence: RED, the batch GREEN, the 30x repeats,
teardown and the measured qualifications, each file with its SHA-256.

Usage: python -I make_ei_evidence.py <candidate> <repeat file>"""
import hashlib
import json
import sys
from pathlib import Path

repo = Path('C:/wk/native-elinternals')
candidate = sys.argv[1]
evidence = repo / 'docs/element-internals-evidence'
batch = repo / 'artifacts' / (candidate + '-batch')
copies = {
    'build_ei_candidate.py': repo / 'artifacts/build_ei_candidate_g04.py',
    'aria-relations-repeat30.txt': Path(sys.argv[2]),
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts' / (candidate + '-frozen') / 'runtime-receipt.json',
    'source-patches.json': repo / 'artifacts' / candidate / 'source-patches.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'aria-relations-probe.log': batch / 'aria_relations.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
oracle = json.loads((repo / 'tests/fixtures/aria-relations-oracle.json').read_text())
repeats = (evidence / 'aria-relations-repeat30.txt').read_text().splitlines()
assertions = next(item['assertions'] for item in records if item['name'] == 'aria_relations')
result = {
    'group': ['I11 #106'],
    'native': receipt['nativeVersion'],
    'abi': receipt['abiVersion'],
    'features': ['accessibility-relations', 'dom:Element (ARIAMixin element arrays)'],
    'members': ['Element.ariaActionsElements', 'Element.ariaControlsElements', 'Element.ariaDescribedByElements', 'Element.ariaDetailsElements',
                'Element.ariaErrorMessageElements', 'Element.ariaFlowToElements', 'Element.ariaLabelledByElements',
                'rv_ax_relations (activedescendant, controls, describedby, details, errormessage, flowto, labelledby, owns)'],
    'excluded': ['Element.ariaOwnsElements (not in Chromium 156)'],
    'blocked': {'ElementInternals': 'deferred with D07: HTMLElement::attachInternals needs a custom element reaction queue and a defined or '
                                    'precustomized custom element, which a scriptless host cannot define (CustomElementRegistry.define takes a '
                                    'JavaScript constructor); browser side deferred too, to keep one shared contract. Chromium measured in red-chromium.json.'},
    'sourceHeadOfBatch': receipt['sourceHead'],
    'stackedOn': 'T03 828fb2b (Native40/ABI48), I08 2a9cf7d (Native39/ABI47), G04 15e1bc9 (Native38/ABI46, patch 0038), G03 cdf1a4e (Native37/ABI45)',
    'sourcePatch0039': {'file': 'Source/WebCore/dom/Element.cpp', 'patch': 'patches/0039-element-array-attribute-empty-relations.patch',
                        'red': 'red-0039-empty-relations.json (6 kinds stale after [])', 'green': 'green-0039-empty-relations.json', 'unit': 'UnifiedSource-dom-9'},
    'red': {'files': ['red-chromium.json', 'red-native.json', 'red-0039-empty-relations.json']},
    'green': {'ariaRelationsAssertions': assertions, 'repeats': len(repeats), 'repeatsDistinct': sorted(set(repeats)),
              'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions', 0) for item in records),
              'probesRun': [{'name': item['name'], 'exitCode': item['exitCode'], 'assertions': item.get('assertions')} for item in records],
              'teardownCases': len(teardown), 'teardownCasesAdded': len([r for r in teardown if 'aria relations' in r['probe']]),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown)},
    'chromiumOracle': {'browser': oracle['browser'], 'steps': len(oracle['steps'])},
    'isolation': {'domApi': '+14 functions (7 getters, 7 setters), 0 removed or changed, +1 container RvDomSequenceElementNullable',
                  'abiLayouts': '12 -> 15 assertions (RvWindowMetrics added)'},
    'qualifications': [
        {'name': 'duplicate element kept', 'step': 'elements labelledby [l2, l1, l2]', 'native': ['l2', 'l1', 'l2'], 'chromium': ['l2', 'l1'],
         'note': 'both relations list l2, l1'},
        {'name': 'ariaActionsElements gated', 'native': 'RV_ERR_UNSUPPORTED (ARIAActionsSupportEnabled off in every WebKit configuration)', 'chromium': 'reflects'},
        {'name': 'array identity', 'native': 'each read is a new snapshot; repeated reads give the same elements', 'chromium': 'the same frozen array'},
    ],
    'files': {},
}
for path in sorted(evidence.iterdir()):
    if path.is_file() and path.name != 'final-evidence.json':
        result['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green']['rawAssertions'], result['green']['teardownCases'], hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
