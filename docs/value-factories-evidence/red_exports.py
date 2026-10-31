"""RED: the D17 factory exports are absent from a runtime directory, and gen/dom-report.txt lists them as left out."""
import ctypes, json, os, re, sys
from pathlib import Path
directory, repo, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
os.add_dll_directory(str(directory))
lib = ctypes.CDLL(str(directory / 'RanvierWebCoreHost.dll'))
abi = lib.rv_abi_version; abi.restype = ctypes.c_int32
names = ['rv_dom_text_create', 'rv_dom_comment_create', 'rv_dom_document_fragment_create', 'rv_dom_range_create',
         'rv_dom_static_range_create', 'rv_dom_document_create', 'rv_dom_document_parse_html_unsafe',
         'rv_dom_input_event_create', 'rv_dom_wheel_event_create', 'rv_dom_pointer_event_create',
         'rv_dom_dom_matrix_from_float32_array', 'rv_dom_dom_matrix_from_float64_array',
         'rv_dom_dom_matrix_read_only_from_float32_array', 'rv_dom_dom_matrix_read_only_from_float64_array']
present = {n: hasattr(lib, n) for n in names}
report = (repo / 'gen/dom-report.txt').read_text(encoding='utf-8')
members = ['Text.constructor', 'Comment.constructor', 'DocumentFragment.constructor', 'Range.constructor',
           'StaticRange.constructor', 'Document.constructor', 'Document.parseHTMLUnsafe', 'InputEvent.constructor',
           'WheelEvent.constructor', 'PointerEvent.constructor', 'DOMMatrix.fromFloat32Array', 'DOMMatrix.fromFloat64Array',
           'DOMMatrixReadOnly.fromFloat32Array', 'DOMMatrixReadOnly.fromFloat64Array']
left = {m: (re.search(r'^  ' + re.escape(m) + r': (.*)$', report, re.M) or [None, None])[1] for m in members}
result = {'abi': abi(), 'runtime': str(directory), 'exportsPresent': present, 'leftOut': left,
          'red': not any(present.values()) and all(left.values())}
out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=1))
sys.exit(0 if result['red'] else 1)
