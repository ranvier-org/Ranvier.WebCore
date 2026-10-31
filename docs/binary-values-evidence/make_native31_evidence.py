"""Collects the H11 Native31 evidence into docs/binary-values-evidence: RED, batch GREEN, teardown, the probe report
and the measured qualifications, each file with its SHA-256."""
import hashlib
import json
from pathlib import Path

repo = Path('C:/wk/native-binary')
evidence = repo / 'docs/binary-values-evidence'
batch = repo / 'artifacts/native31-batch'
copies = {
    'build_native31_candidate.py': repo / 'artifacts/build_native31_candidate.py',
    'run_native31_batch.py': repo / 'artifacts/run_native31_batch.py',
    'make_native31_evidence.py': repo / 'artifacts/make_native31_evidence.py',
    'measure_binary_red.py': repo / 'artifacts/measure_binary_red.py',
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts/native31-frozen/runtime-receipt.json',
    'source-exemption.json': repo / 'artifacts/native31-candidate-4/source-exemption.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'binary-values-report.json': repo / 'artifacts/h11-native31-green.json',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
report = json.loads((evidence / 'binary-values-report.json').read_text())
red = json.loads((evidence / 'red-native30.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
oracle = json.loads((repo / 'tests/fixtures/binary-values-oracle.json').read_text(encoding='utf-8'))
probe = next(item for item in records if item['name'] == 'binary_values')
added = [r for r in teardown if 'blob slice' in r['probe']]
result = {
    'group': ['H11 #114'],
    'native': receipt['nativeVersion'],
    'abi': 39,
    'features': ['dom-binary-values', 'dom:Blob', 'dom:File', 'dom:FileList', 'dom-constructor:Blob', 'dom-constructor:File'],
    'sourceHeadOfBatch': receipt['sourceHead'],
    'candidate': 'artifacts/native31-candidate-4 (forms-candidate-4 objects; RanvierDomGlue regenerated; four host units)',
    'sourceExemption': receipt['sourceExemption'],
    'red': {'runtime': 'native-dialog/artifacts/native30-frozen (Native30/ABI38)', 'abiVersion': red['abiVersion'],
            'exportsPresent': sum(red['exports'].values()), 'exportsChecked': len(red['exports']),
            'features': red['features'], 'emptyFileInputEntry': red['emptyFileInputEntry'],
            'probe': 'binary_values.py fails: dom-binary-values advertised', 'files': ['red-native30.json', 'red-probe-native30.log']},
    'green': {'binaryValuesAssertions': probe['assertions'], 'probes': len(records) - 2,
              'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions', 0) for item in records), 'teardownCases': len(teardown),
              'teardownCasesAdded': len(added),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown),
              'probeHeldPastDestroy': report['heldPastDestroy']},
    'chromiumOracle': {'browser': oracle['browser'], 'fixture': 'tests/fixtures/binary-values-oracle.json', 'cases': len(oracle['cases'])},
    'valueDifferences': 0,
    'conventionDivergence': {'case': 'invalid UTF-8 in a string BlobPart',
                             'behaviour': 'RV_ERR_NULL_ARGUMENT (documented in the rv_dom_blob_create and rv_dom_file_create header comments)',
                             'generatedGlueConvention': 'a NUL-terminated const char* string argument converts invalid UTF-8 to a null String without an error'},
    'commentOnlyAfterBatch': 'the header and glue comment that documents it was added after the batch; no code changed and the runtime was not rebuilt',
    'qualifications': [
        {'qualification': 'platform line endings', 'case': 'endings native',
         'reason': 'expected value depends on the platform: CRLF on Windows (equal to Windows Chromium 610d0a620d0a630d0a64), LF elsewhere; asserted per platform'},
        {'qualification': 'no promise or FileReader engine object', 'case': 'Blob.text/arrayBuffer/bytes, FileReader',
         'reason': 'the host loader has no blob-URL path; rv_blob_read_bytes reads memory-backed blobs during the call; text, data URL and cancellation are managed (BinaryValueContract, BinaryValueService.ReadBytes)'},
        {'qualification': 'integer slice arguments', 'case': 'slice(1.9, 4.2)',
         'reason': 'the [Clamp] conversion of a JavaScript number is browser-only; the ABI takes int64 start and end'},
        {'qualification': 'UTF-8 string parts', 'case': 'USVString parts',
         'reason': 'the caller writes a USVString as UTF-8, with U+FFFD for a lone surrogate; invalid UTF-8 returns RV_ERR_NULL_ARGUMENT'},
    ],
    'files': {},
}
for path in sorted(evidence.iterdir()):
    if path.name != 'final-evidence.json':
        result['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green']['rawAssertions'], result['green']['teardownCases'], result['green']['probes'], hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
