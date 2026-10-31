"""Measures document.characterSet of host documents with and without a <meta charset> on the runtimes given, and
prints one JSON record per runtime."""
import ctypes
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests/abi'))
from svg_paint_probe import SvgProbe

P, I = ctypes.c_void_p, ctypes.c_int32
MARKUP = {
    'none': '<!doctype html><p>x</p>',
    'meta-utf-8': '<!doctype html><meta charset="utf-8"><p>x</p>',
    'meta-windows-1252': '<!doctype html><meta charset="windows-1252"><p>x</p>',
}
records = []
for directory in sys.argv[1:]:
    runtime = Path(directory)
    measured = {}
    for name, markup in MARKUP.items():
        with SvgProbe(str(runtime), 200, 100) as probe:
            probe.load(markup, standalone=False)
            document = probe.bind('rv_host_document', P, [P])(probe.host)
            buffer, length = ctypes.create_string_buffer(64), I()
            status = probe.bind('rv_dom_document_get_character_set', I, [P, ctypes.c_char_p, I, ctypes.POINTER(I)])(document, buffer, len(buffer), ctypes.byref(length))
            probe.bind('rv_node_release', None, [P])(document)
            measured[name] = buffer.value.decode() if status == 0 else 'status ' + str(status)
    records.append({'runtime': runtime.as_posix(), 'hostSha256': hashlib.sha256((runtime / 'RanvierWebCoreHost.dll').read_bytes()).hexdigest(),
                    'characterSet': measured})
print(json.dumps(records, indent=2))
