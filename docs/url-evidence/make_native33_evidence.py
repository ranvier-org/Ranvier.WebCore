"""Collects the H13 Native33 evidence into docs/url-evidence: route measurement, RED, batch GREEN, the WPT corpus,
teardown and the measured qualifications, each file with its SHA-256."""
import hashlib
import json
import sys
from pathlib import Path

repo = Path('C:/wk/native-url')
sys.path.insert(0, str(repo / 'tests/abi'))
from url_wpt_score import score  # noqa: E402

evidence = repo / 'docs/url-evidence'
batch = repo / 'artifacts/native33-batch-2'
copies = {
    'build_native33_candidate.py': repo / 'artifacts/build_native33_candidate.py',
    'run_native33_full_batch.py': repo / 'artifacts/run_native33_full_batch.py',
    'url-values-repeat30.txt': Path('C:/wk/h13-artifacts/url-values-repeat30-2.txt'),
    'make_native33_evidence.py': repo / 'artifacts/make_native33_evidence.py',
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts/native33-frozen-2/runtime-receipt.json',
    'source-patches.json': repo / 'artifacts/native33-candidate-6/source-patches.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'url-values-probe.log': batch / 'url_values.log',
    'url-wpt-probe.log': batch / 'url_wpt.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
oracle = json.loads((repo / 'tests/fixtures/url-oracle.json').read_text(encoding='utf-8'))
qualified = json.loads((repo / 'tests/fixtures/url-qualified.json').read_text(encoding='utf-8'))
wpt_qualified = json.loads((repo / 'tests/fixtures/url-wpt-qualified.json').read_text(encoding='utf-8'))
chromium = json.loads((repo / 'tests/fixtures/url-wpt-chromium.json').read_text(encoding='utf-8'))
system_uri = json.loads((evidence / 'route-red-system-uri.json').read_text(encoding='utf-8'))
values_log = (batch / 'url_values.log').read_text(encoding='utf-8')
assertions = int(values_log.split('url_values: ')[1].split(' assertions')[0])
cases = json.loads((repo / 'tests/fixtures/url-cases.json').read_text(encoding='utf-8'))
added = [r for r in teardown if 'url ' in r['probe']]
packed = [p for p in (repo / 'src').rglob('*') if 'wpt' in p.as_posix().lower()]
result = {
    'group': ['H13 #115'],
    'native': receipt['nativeVersion'],
    'abi': 41,
    'features': ['dom:DOMURL', 'dom:URLSearchParams', 'dom:URLPattern', 'dom-url-static', 'dom-url-search-params-entries'],
    'members': ['URL constructor, parse, canParse, href/origin/protocol/username/password/host/hostname/port/pathname/search/hash, '
                'searchParams, toJSON', 'URLSearchParams constructor (sequence, record, string), size, append, delete, get, getAll, has, '
                'set, sort, entries, toString', 'URLPattern constructors, test, exec (URLPatternResult), component getters, hasRegExpGroups'],
    'excluded': ['URL.createObjectURL', 'URL.revokeObjectURL (later blob-URL group)'],
    'sourceHeadOfBatch': receipt['sourceHead'],
    'route': {'decision': 'native: WebKit WTF URLParser and WebCore URLPattern through generated exports',
              'systemUriHrefAgreement': f"{system_uri['agree']}/{system_uri['total']}", 'files': ['route-red-cases.json', 'route-red-chromium.json',
                                                                                                    'route-red-system-uri.json']},
    'red': {'runtime': 'native-caret/artifacts/native32-frozen (Native32/ABI40)', 'files': ['red-url-values-native32.log', 'red-url-wpt-native32.log'],
            'nul': {'runtime': 'native-url/artifacts/native33-frozen (previous H13 head)', 'files': ['red-nul-old-head.log', 'red-nul-old-head-differences.json'],
                    'case': 'getAll of a=x%00y&a=%00 returned [x, ""]; a sequence init lost the text after U+0000'},
            'earlier': 'native-dialog native30-candidate-1: url_values.py fails at the missing rv_dom_domurl_release'},
    'green': {'urlValuesAssertions': assertions, 'ownCases': {k: len(cases[k]) for k in ['parse', 'setters', 'params', 'linked', 'patterns']},
              'qualifiedDifferences': len(qualified['differences']), 'wpt': wpt_qualified['counts'],
              'wptDisagreements': len(wpt_qualified['disagree']), 'wptBothFail': len(wpt_qualified['bothFail']),
              'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
              'batchParsedAssertions': sum(item.get('assertions', 0) for item in records),
              'batchParsedNote': 'the batch runner parses "PASS ... N assertions" and "<probe>: N assertions" lines; url_wpt reports engine calls',
              'rawAssertions': sum(item.get('assertions', 0) for item in records),
              'urlWptCalls': int((batch / 'url_wpt.log').read_text(encoding='utf-8').split('url_wpt: ')[1].split(' calls')[0]),
              'newProbes': ['url_values', 'url_wpt'],
              'probesRun': [{'name': item['name'], 'exitCode': item['exitCode'], 'assertions': item.get('assertions'),
                             'runtimeReceipt': item['runtimeReceipt']} for item in records],
              'teardownCases': len(teardown), 'teardownCasesAdded': len(added),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown)},
    'chromiumOracle': {'browser': oracle['browser'], 'wptRecordBrowser': chromium['browser'], 'wptCommit': chromium['wpt']},
    'qualifications': [{'case': key, 'note': value['note']} for key, value in qualified['differences'].items()] + [
        {'name': 'WPT disagreements', 'count': len(wpt_qualified['disagree']),
         'reason': '149 cases the engine passes and Chromium fails; urlpattern[347] is a JavaScript overload-conversion TypeError with no C ABI call'},
        ],
    'packaging': {'wptUnderSrc': [str(p) for p in packed], 'packedManagedPackage': json.loads((evidence / 'package-wpt-check.json').read_text()),
                  'note': 'Ranvier.WebCore packed from this head carries no tests/fixtures or WPT entry; the native flavor packages carry only runtimes'},
    'files': {},
}
for path in sorted(evidence.iterdir()):
    if path.name != 'final-evidence.json':
        result['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green'], hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
