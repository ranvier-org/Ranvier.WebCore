"""RED for WebCore #145: replays tests/abi/host_string_nul.py's cases through the NUL-terminated const char* transport of
the current head's hand-written exports and RvClipboardWrite, and records every case whose value differs from the
Chromium oracle, or from the WebKit value of a qualified difference. C2 copies multi-byte text without U+0000 and matches
through either transport. usage: host_string_nul_red.py <tree> <runtime dir> <out.json>"""
import ctypes, json, sys
from pathlib import Path
tree, directory, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
sys.path.insert(0, str(tree / 'tests' / 'abi'))
import host_string_nul as probe
from utf8_inputs import Utf8, bind as bind_utf8

class Legacy:
    clipboard_write = ctypes.CFUNCTYPE(None, probe.P, ctypes.c_char_p, ctypes.c_char_p, probe.I)
    @staticmethod
    def bind(native, name, result, arguments):
        function = getattr(native.library, name)
        function.restype = result
        function.argtypes = [ctypes.c_char_p if a is Utf8 else a for a in arguments]
        marks = [a is Utf8 for a in arguments]
        return lambda *values: function(*[(None if v is None else v.encode('utf-8') if isinstance(v, str) else v) if m else v
                                          for m, v in zip(marks, values)])
    @staticmethod
    def written(arguments):
        context, kind, data, first = arguments
        return kind.decode('utf-8'), (data or b'').decode('utf-8'), first

# Generated rv_dom_* inputs keep the ABI-51 length transport; only hand-written exports go through Legacy.
cases = json.loads((probe.FIXTURES / 'host-string-nul-cases.json').read_text(encoding='utf-8'))['cases']
oracle = json.loads((probe.FIXTURES / 'host-string-nul-oracle.json').read_text(encoding='utf-8'))
native = probe.Native(directory)
abi = native.bind('rv_abi_version', probe.I, [])()
qualified = json.loads((probe.FIXTURES / 'host-string-nul-qualified.json').read_text(encoding='utf-8'))['differences']
differ = probe.replay(native, Legacy(), cases, oracle, check=False, qualified=qualified)
families = {}
for entry in cases:
    families.setdefault(entry['family'], [0, 0])[0] += 1
    if entry['id'] in differ: families[entry['family']][1] += 1
report = {'abi': abi, 'runtime': directory, 'browser': oracle['browser'], 'cases': len(cases), 'differ': len(differ),
          'byFamily': {k: {'cases': v[0], 'differ': v[1]} for k, v in sorted(families.items())}, 'casesDiffer': differ}
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
print(json.dumps(report['byFamily']), 'differ', len(differ), 'of', len(cases))
