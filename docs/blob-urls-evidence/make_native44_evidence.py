"""Collects the #144 blob URL evidence into docs/blob-urls-evidence: RED (Native42 absent exports and the candidate-1
cross-host leak), the batch GREEN, the 30x repeats, the Chromium oracle repeats, teardown and the receipts, each file
with its SHA-256.

Usage: python -I make_native44_evidence.py <candidate> <repeat file> <oracle repeat file> <batch head> <stacked-on note>"""
import hashlib
import json
import sys
from pathlib import Path

repo = Path('C:/wk/native-blob')
candidate = sys.argv[1]
evidence = repo / 'docs/blob-urls-evidence'
batch = repo / 'artifacts' / (candidate + '-batch')
copies = {
    'blob-urls-repeat30.txt': Path(sys.argv[2]),
    'oracle-repeat30.txt': Path(sys.argv[3]),
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts' / (candidate + '-frozen') / 'runtime-receipt.json',
    'source-patches.json': repo / 'artifacts' / candidate / 'source-patches.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'blob-urls-probe.log': batch / 'blob_urls.log',
    'red-candidate1-cross-host-leak.json': Path('C:/wk/blob-artifacts/exp1.json'),
    'red-chromium-measure.json': Path('C:/wk/blob-artifacts/red/chromium.json'),
    'gif-decode-check.txt': Path('C:/wk/blob-artifacts/gifcheck.txt'),
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
oracle = json.loads((repo / 'tests/fixtures/blob-urls-oracle.json').read_text(encoding='utf-8'))
qualified = json.loads((repo / 'tests/fixtures/blob-urls-qualified.json').read_text(encoding='utf-8'))['differences']
leak = json.loads((evidence / 'red-candidate1-cross-host-leak.json').read_text(encoding='utf-8'))['isolation']
repeats = (evidence / 'blob-urls-repeat30.txt').read_text().splitlines()
oracle_repeats = (evidence / 'oracle-repeat30.txt').read_text().splitlines()
assertions = next(item['assertions'] for item in records if item['name'] == 'blob_urls')
blob_teardown = [r for r in teardown if 'blob' in r['probe']]
result = {
    'group': ['#144 blob URLs, blob: loading and FileReader'],
    'status': 'green (private Windows x64 slim; not accepted)',
    'native': receipt['nativeVersion'],
    'abi': receipt['abiVersion'],
    'features': ['blob-urls', 'dom:FileReader', 'dom-constructor:FileReader'],
    'members': ['rv_dom_domurl_create_object_url', 'rv_dom_domurl_revoke_object_url', 'rv_dom_file_reader_*', 'rv_blob_read',
                'rv_blob_url_read', 'rv_blob_read_result', 'rv_blob_read_type', 'rv_blob_read_error', 'rv_file_create_from_path',
                'rv_file_reader_result', 'rv_file_reader_error'],
    'hostLoader': 'RvLoaderStrategy starts blob: loads in WebCore (BlobRegistryImpl builtin BlobResourceHandle), as data:; the host '
                  'resource handler never sees a blob: URL; every other scheme is unchanged (the full batch is unchanged)',
    'sourcePatch': 'none',
    'sourceHeadOfBatch': receipt['sourceHead'],
    'batchRunHead': sys.argv[4],
    'stackedOn': sys.argv[5],
    'red': {
        'native42': {'file': 'red-native42.json', 'script': 'red_native42.py', 'runtime': 'C:/wk/native-inspect/artifacts/native42-candidate-3',
                     'result': json.loads((evidence / 'red-native42.json').read_text()),
                     'loader': 'the host loader handed blob: URLs to the resource handler, which failed them'},
        'crossHostLeak': {'file': 'red-candidate1-cross-host-leak.json', 'candidate': 'native44-candidate-1 (pre-fix)',
                          'otherRead': leak['otherRead'], 'otherImage': leak['otherImage'],
                          'fix': 'rv_blob_url_read refuses a URL the document origin cannot request (LOAD_FAILED, NotFoundError)'},
        'chromium': 'red-chromium-measure.json',
    },
    'green': {'blobUrlsAssertions': assertions, 'repeats': len(repeats), 'repeatsDistinct': sorted(set(repeats)),
              'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions', 0) for item in records),
              'probesRun': [{'name': item['name'], 'exitCode': item['exitCode'], 'assertions': item.get('assertions')} for item in records],
              'teardownCases': len(teardown), 'blobTeardownCases': len(blob_teardown),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown)},
    'chromiumOracle': {'browser': oracle['browser'], 'readerCases': sorted(oracle['reader']), 'repeats': len(oracle_repeats),
                       'repeatsDistinct': sorted(set(oracle_repeats))},
    'qualified': qualified,
    'measured': {
        'format': 'blob:null/<UUID v4> natively and in Chromium about:blank; blob:<origin>/<UUID v4> for an http origin',
        'fileReader': 'event order and final state equal Chromium for every read method; abort() fires abort and loadend before it '
                      'returns; abort in load is ignored; readAs while LOADING throws InvalidStateError; readAs in loadend is allowed; '
                      'progress events are collapsed and never counted',
        'fileBacked': 'name, size, type, text, slice and URL read equal Chromium; a file deleted between create and read fires error '
                      'and loadend (no loadstart) with NotFoundError, as Chromium',
        'isolation': 'a URL of host A neither loads as an image nor reads in host B, in both directions; it stops after A\'s document '
                     'is replaced or A is destroyed (Chromium: two about:blank pages are isolated; same-origin http pages share URLs)',
        'teardown': 'document replacement: a read in flight is INVALIDATED (qualified), a FileReader in flight fires nothing and is DONE '
                    '(Chromium iframe removal alike); host destroy: INVALIDATED, no FileReader event',
        'iframe': 'browser-only: the host has no subframes (EmptyFrameLoaderClient::createFrame returns null); natively Unsupported',
        'gif': 'not a gap: the earlier test GIF was malformed (Chromium tolerant); a canonical GIF decodes natively (gif-decode-check.txt)',
    },
    'files': {},
}
for path in sorted(evidence.iterdir()):
    if path.is_file() and path.name != 'final-evidence.json':
        result['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green']['rawAssertions'], result['green']['teardownCases'], hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
