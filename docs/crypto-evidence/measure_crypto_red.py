"""B22 RED: what a runtime exposes for crypto.getRandomValues, crypto.randomUUID and crypto.subtle."""
import ctypes, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests' / 'abi'))
from form_collections import Native, Case, P, I

NAMES = ['rv_dom_crypto_get_random_values', 'rv_dom_crypto_random_uuid', 'rv_dom_window_get_crypto',
         'rv_dom_crypto_get_subtle', 'rv_dom_subtle_crypto_digest', 'rv_crypto_digest']
FEATURES = ['dom-crypto-random', 'dom:Crypto', 'dom:SubtleCrypto', 'dom-crypto-subtle']


def main(directory, out):
    n = Native(directory)
    exports = {name: hasattr(n.library, name) for name in NAMES}
    has = n.bind('rv_abi_has', I, [ctypes.c_char_p])
    features = {f: has(f.encode()) for f in FEATURES}
    case = Case(n, '<p id=p>x</p>')
    case.close()
    report = {'runtime': str(directory), 'abiVersion': n.bind('rv_abi_version', I, [])(), 'exports': exports,
              'exportsPresent': sum(exports.values()), 'features': features}
    Path(out).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


main(sys.argv[1], sys.argv[2])
