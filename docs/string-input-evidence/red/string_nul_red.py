"""RED for WebCore #142: replays tests/abi/string_nul.py's cases through the NUL-terminated const char* transport of the
current head (ABI 47) and records every case whose value differs from the Chromium oracle."""
import ctypes, json, sys
from pathlib import Path
tree, directory, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
sys.path.insert(0, str(tree / 'tests' / 'abi'))
import string_nul as probe

class Legacy(probe.Transport):
    plain_types = [ctypes.c_char_p]
    span_type = ctypes.c_char_p
    input_type = ctypes.c_char_p
    def plain(self, value):
        return [None if value is None else value.encode('utf-8')]
    def span(self, value):
        return value.encode('utf-8')
    def input(self, value):
        return None if value is None else value.encode('utf-8')
    @staticmethod
    def read(span):
        return (span or b'').decode('utf-8')

cases = json.loads((probe.FIXTURES / 'string-nul-cases.json').read_text(encoding='utf-8'))['cases']
oracle = json.loads((probe.FIXTURES / 'string-nul-oracle.json').read_text(encoding='utf-8'))
native = probe.Native(directory)
abi = native.bind('rv_abi_version', probe.I, [])()
differ = probe.replay(native, Legacy(), cases, oracle, check=False)
by_category = {}
for entry in cases:
    by_category.setdefault(entry['category'], [0, 0])[0] += 1
    if entry['id'] in differ: by_category[entry['category']][1] += 1
report = {'abi': abi, 'runtime': directory, 'browser': oracle['browser'], 'cases': len(cases), 'differ': len(differ),
          'byCategory': {k: {'cases': v[0], 'differ': v[1]} for k, v in sorted(by_category.items())}, 'cases_differ': differ}
out.write_text(json.dumps(report, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
print(json.dumps(report['byCategory']), 'differ', len(differ), 'of', len(cases))
