"""Collects the B22 Native36 evidence into docs/crypto-evidence: RED, generator RED/GREEN, batch GREEN, the crypto probe
log, the 30x repeat, teardown and the qualifications, each file with its SHA-256. Usage: make_native36_evidence.py <candidate>"""
import hashlib
import json
import sys
from pathlib import Path

repo = Path('C:/wk/native-crypto')
lane = Path('C:/wk/crypto-artifacts')
candidate = repo / 'artifacts' / sys.argv[1]
evidence = repo / 'docs/crypto-evidence'
batch = repo / 'artifacts/native36-batch-4'
copies = {
    'build_native36_candidate.py': lane / 'build_native36_candidate.py',
    'run_native36_full_batch.py': lane / 'run_native36_full_batch.py',
    'make_native36_evidence.py': lane / 'make_native36_evidence.py',
    'crypto-random-repeat30.txt': lane / 'crypto-random-repeat30.txt',
    'batch-green.json': batch / 'results.json',
    'runtime-receipt.json': repo / 'artifacts/native36-frozen-4/runtime-receipt.json',
    'source-patches.json': candidate / 'source-patches.json',
    'teardown-probes.json': batch / 'teardown/teardown-probes.json',
    'crypto-random-probe.log': batch / 'crypto_random.log',
}
for name, source in copies.items():
    (evidence / name).write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
records = json.loads((batch / 'results.json').read_text())
teardown = json.loads((batch / 'teardown/teardown-probes.json').read_text())
receipt = json.loads((evidence / 'runtime-receipt.json').read_text())
oracle = json.loads((repo / 'tests/fixtures/crypto-random-oracle.json').read_text(encoding='utf-8'))
red = json.loads((evidence / 'red-native31.json').read_text())
chromium_red = json.loads((evidence / 'chromium-red.json').read_text())
log = (batch / 'crypto_random.log').read_text(encoding='utf-8')
assertions = int(log.split('crypto_random: ')[1].split(' assertions')[0])
added = [r for r in teardown if 'crypto' in r['probe']]
result = {
    'group': ['B22 #119'],
    'native': receipt['nativeVersion'],
    'abi': 44,
    'features': ['dom-crypto-random'],
    'members': ['Crypto.getRandomValues (rv_dom_crypto_get_random_values: element kind, in/out bytes, byte length)',
                'Crypto.randomUUID (rv_dom_crypto_random_uuid)'],
    'excluded': ['SubtleCrypto (promise-only; digest comes from System.Security.Cryptography on .NET and crypto.subtle on Chromium; '
                 'keys, import, export, sign, verify, encrypt and derive are a follow-up group)'],
    'sourceHeadOfBatch': receipt['sourceHead'],
    'webCrypto': {
        'pin': 'WebKit b95c91b1c0: SubtleCrypto compiles on every port; the backend registers the algorithms',
        'win-x64/win-arm64': 'slim patch 0003 USE_CRYPTO_STUB: SHA-1/256/384/512 only (WebCore imports CryptCreateHash, no libcrypto)',
        'linux-x64/linux-arm64': 'WPE USE_GCRYPT: libgcrypt.so.20 + libtasn1.so.6 NEEDED; AES-CBC/CTR/GCM/KW, ECDH, ECDSA, Ed25519, X25519, '
                                 'HKDF, HMAC, PBKDF2, RSASSA-PKCS1-v1_5, RSA-OAEP, RSA-PSS, SHA-*',
        'osx-arm64': 'Cocoa CommonCrypto: the WPE set plus AES-CFB',
        'checkedBinaries': 'preview.15 and preview.19 shipped RID packages; config/slim.cmake, wpe.cmake, mac.cmake and patch 0003 '
                           'unchanged since (last change 63ddf43, unrelated)'},
    'red': {'runtime': red['runtime'], 'abiVersion': red['abiVersion'], 'exportsPresent': red['exportsPresent'],
            'exportsChecked': len(red['exports']), 'features': red['features'],
            'probe': 'crypto_random.py fails on Native32: dom-crypto-random advertised',
            'generator': 'three generator tests failed before windowObjectBindings and typedArrayViewTypes',
            'files': ['red-native31.json', 'red-probe-native32.log', 'generator-red.log', 'chromium-red.json']},
    'green': {'cryptoRandomAssertions': assertions, 'repeat30': (evidence / 'crypto-random-repeat30.txt').read_text().strip(),
              'probes': len(records) - 2, 'allExitZero': all(item['exitCode'] == 0 for item in records),
              'rawAssertions': sum(item.get('assertions', 0) for item in records),
              'batchParsedNote': 'the batch runner parses "PASS ... N assertions" and "<probe>: N assertions" lines',
              'newProbes': ['crypto_random'],
              'probesRun': [{'name': item['name'], 'exitCode': item['exitCode'], 'assertions': item.get('assertions'),
                             'runtimeReceipt': item['runtimeReceipt']} for item in records],
              'teardownCases': len(teardown), 'teardownCasesAdded': len(added),
              'teardownAllCollected': all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1 for r in teardown)},
    'chromiumOracle': {'browser': oracle['browser'], 'origin': 'http://localhost (secure context)', 'fixture': 'tests/fixtures/crypto-random-oracle.json',
                       'insecureContext': chromium_red['insecureContext']},
    'qualifications': [
        {'name': 'secure context', 'reason': 'the native host exposes no page script, so randomUUID is available without [SecureContext]; '
                                              'a Fable provider in an insecure context reads randomUUID and digest as Unsupported'},
        {'name': 'copied ranges', 'reason': 'the glue fills a copy of the caller bytes and copies it back, so a range needs no element alignment; '
                                             'a byte length that is not a multiple of the element size raises RangeError'},
        {'name': 'after host destroy', 'reason': 'a retained document keeps its Window and crypto object, as a detached browser window does; '
                                                  'both functions keep working (probe afterDestroy, teardown case "crypto")'},
        {'name': 'random properties', 'reason': 'no random value is asserted: lengths, kinds, v4 format, version/variant bits, '
                                                 'neighbour bytes untouched and two fills differing (probability 2^-128 of a false failure)'}],
    'files': {},
}
for path in sorted(evidence.iterdir()):
    if path.name != 'final-evidence.json':
        result['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
open(evidence / 'final-evidence.json', 'w', newline='\n').write(json.dumps(result, indent=2) + '\n')
print(result['green']['rawAssertions'], result['green']['probes'], result['green']['teardownCases'],
      hashlib.sha256((evidence / 'final-evidence.json').read_bytes()).hexdigest())
