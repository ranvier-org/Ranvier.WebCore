"""Collects the WebCore #145 evidence into docs/host-string-input-evidence: RED, the batch GREEN against the baseline
batch, the host_string_nul and oracle repeats, teardown and the per-probe output comparison, each file with its SHA-256.

Usage: python -I make_native47_evidence.py <candidate> <baseline batch dir> <baseline head> <stacked-on note> <teardown repeat note>"""
import hashlib
import json
import re
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
candidate, baseline, baseline_head, stacked, teardown_repeat = sys.argv[1:6]
baseline = Path(baseline)
evidence = repo / 'docs/host-string-input-evidence'
batch = repo / 'artifacts' / (candidate + '-batch')
copies = {
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts' / (candidate + '-frozen') / 'runtime-receipt.json',
    'source-patches.json': repo / 'artifacts' / candidate / 'source-patches.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'host-string-nul-probe.log': batch / 'host_string_nul.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))


def normalized(path):
    text = path.read_text(encoding='utf-8', errors='replace')
    text = re.sub(r'\[rtk\][^\n]*\n', '', text)
    return re.sub(r'[0-9a-f]{64}', '<sha256>', text).splitlines()


records = json.loads((batch / 'results.json').read_text())
base = {item['name']: item for item in json.loads((baseline / 'results.json').read_text())}
comparison = []
for item in records:
    previous = base.get(item['name'])
    entry = {'name': item['name'], 'assertions': item.get('assertions'), 'exitCode': item['exitCode']}
    if previous:
        entry['baselineAssertions'] = previous.get('assertions')
        entry['sameCount'] = previous.get('assertions') == item.get('assertions')
        entry['sameOutput'] = normalized(Path(previous['log'])) == normalized(Path(item['log']))
    else:
        entry['new'] = True
    comparison.append(entry)
(evidence / 'baseline-comparison.json').write_text(json.dumps(comparison, indent=2) + '\n', encoding='utf-8', newline='\n')
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
base_teardown = json.loads((baseline / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
repeats = json.loads((evidence / 'host-string-nul-repeat30.json').read_text(encoding='utf-8'))
red = json.loads((evidence / 'red/host-string-nul-red.json').read_text(encoding='utf-8'))
qualified = json.loads((repo / 'tests/fixtures/host-string-nul-qualified.json').read_text(encoding='utf-8'))['differences']
result = {
    'group': ['WebCore #145 length-delimited hand-written string inputs'],
    'native': receipt['nativeVersion'],
    'abi': receipt['abiVersion'],
    'abiBreaking': '21 hand-written exports take each free-text input as const uint8_t* plus int32_t byte length; '
                   'RvClipboardWrite delivers data with data_length',
    'changedExports': ['rv_host_load_html', 'rv_host_load_svg', 'rv_node_parse_fragment', 'rv_node_set_text_content',
                       'rv_document_create_text', 'rv_document_create_comment', 'rv_node_set_string', 'rv_element_set_attribute',
                       'rv_document_get_element_by_id', 'rv_element_class', 'rv_host_ime_set_composition', 'rv_host_ime_commit',
                       'rv_ax_set_value', 'rv_clipboard_offer', 'rv_drag_data_add', 'rv_element_set_style', 'rv_host_key',
                       'rv_node_add_event_listener', 'rv_node_dispatch_event', 'rv_host_create_event', 'rv_host_construct_event',
                       'rv_event_target_add_listener'],
    'changedCallbacks': ['RvClipboardWrite'],
    'nulTerminatedByDesign': 'element and attribute names, selectors, MIME and data types, style property names, RvEventInit '
                             'strings, URLs, capability names',
    'qualified': qualified,
    'outboundClipboard': 'No ABI path can put U+0000 into RvClipboardWrite data: WebKit drops it from editor.selectedText() '
                         "and from the copied markup (measured: 'a\\u0000b' copies as 'ab' in text/plain and text/html), and "
                         'page-supplied data needs ClipboardEvent.clipboardData and DataTransfer, which belong to the '
                         'clipboard and drag groups. host_string_nul C2 checks multi-byte delivery with data_length.',
    'sourceHeadOfBatch': receipt['sourceHead'],
    'stackedOn': stacked,
    'baseline': {'batch': str(baseline), 'head': baseline_head,
                 'rawAssertions': sum(item.get('assertions', 0) for item in base.values()), 'teardownCases': len(base_teardown)},
    'red': {'file': 'red/host-string-nul-red.json', 'script': 'host_string_nul_red.py', 'abi': red['abi'], 'cases': red['cases'],
            'differ': red['differ'], 'byFamily': red['byFamily']},
    'green': {
        'hostStringNulAssertions': next(item['assertions'] for item in records if item['name'] == 'host_string_nul'),
        'hostStringNulRepeats': repeats['count'], 'hostStringNulRepeatsDistinct': repeats['distinctPassLines'],
        'teardownHostStringRepeats': teardown_repeat,
        'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
        'rawAssertions': sum(item.get('assertions', 0) for item in records),
        'baselineProbesSameCount': all(entry.get('sameCount', True) for entry in comparison),
        'baselineProbesSameOutput': [entry['name'] for entry in comparison if entry.get('sameOutput')],
        'baselineProbesOtherOutput': {entry['name']: 'timing values only' if entry['name'] == 'frames' else
                                      'three added U+0000 input records' for entry in comparison
                                      if 'sameOutput' in entry and not entry['sameOutput']},
        'teardownCases': len(teardown),
        'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown),
    },
    'files': {},
}
for path in sorted(evidence.rglob('*')):
    if path.is_file() and path.name != 'final-evidence.json':
        result['files'][path.relative_to(evidence).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green']['rawAssertions'], result['green']['teardownCases'], result['green']['baselineProbesOtherOutput'],
      hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
