"""RED measurement of font construction/registration on a runtime: which FontFace and FontFaceSet exports exist, and
what a host can do with rv_font_load (H05), the only byte-backed font path on the parent ABI.
Usage: red_native.py <runtime> <webkit-source> <out.json>"""
import ctypes, hashlib, json, os, sys
from pathlib import Path

runtime, source, out_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]), Path(sys.argv[3])
os.add_dll_directory(str(runtime))
lib = ctypes.CDLL(str(runtime / 'RanvierWebCoreHost.dll'))
P, I, D, U64 = ctypes.c_void_p, ctypes.c_int32, ctypes.c_double, ctypes.c_uint64


def bind(name, result, arguments):
    function = getattr(lib, name)
    function.restype, function.argtypes = result, arguments
    return function


out = {'runtimeSha256': hashlib.sha256((runtime / 'RanvierWebCoreHost.dll').read_bytes()).hexdigest(), 'steps': []}
out['abi'] = bind('rv_abi_version', I, [])()
has = bind('rv_abi_has', I, [ctypes.c_char_p])
out['features'] = {f: has(f.encode()) for f in ['font-load', 'font-readiness', 'dom:FontFace', 'dom:FontFaceSet',
                                                'dom-constructor:FontFace', 'dom-font-face-set-values', 'font-face-load']}
out['exports'] = {n: hasattr(lib, n) for n in [
    'rv_font_load', 'rv_fonts_load', 'rv_dom_document_get_fonts', 'rv_dom_font_face_create', 'rv_dom_font_face_get_status',
    'rv_dom_font_face_set_weight', 'rv_dom_font_face_set_add', 'rv_dom_font_face_set_delete', 'rv_dom_font_face_set_clear',
    'rv_dom_font_face_set_has', 'rv_dom_font_face_set_get_size', 'rv_dom_font_face_set_values', 'rv_font_face_load',
    'rv_font_face_loaded']}
font = (source / 'Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf').read_bytes()
create = bind('rv_host_create', P, [I, I])
destroy = bind('rv_host_destroy', None, [P])
load_html = bind('rv_host_load_html', I, [P, ctypes.c_char_p])
by_id = bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])
release_node = bind('rv_node_release', None, [P])
rect = bind('rv_element_rect', I, [P] + [ctypes.POINTER(D)] * 4)
update = bind('rv_host_update', I, [P])
cycle = bind('rv_run_loop_cycle', I, [I])
Completion = ctypes.CFUNCTYPE(None, P, I, I, I)
load_font = bind('rv_font_load', I, [P, ctypes.c_char_p, ctypes.c_char_p, I, Completion, P, ctypes.POINTER(U64)])
release = bind('rv_resource_release', I, [U64])
outcomes = []
completion = Completion(lambda context, outcome, w, h: outcomes.append(outcome))
host = create(400, 100)
load_html(host, b'<!DOCTYPE html><style>#s{font:20px RvBytes, monospace;white-space:pre}</style><body><span id=s>XXXX</span>')


def width():
    update(host)
    node = by_id(host, b's')
    x, y, w, h = D(), D(), D(), D()
    rect(node, ctypes.byref(x), ctypes.byref(y), ctypes.byref(w), ctypes.byref(h))
    release_node(node)
    return w.value


out['steps'].append({'name': 'no face', 'width': width()})
operation = U64()
status = load_font(host, b'RvBytes', font, len(font), completion, None, ctypes.byref(operation))
for _ in range(5):
    cycle(5)
out['steps'].append({'name': 'rv_font_load bytes', 'status': status, 'outcomes': list(outcomes), 'width': width()})
release(operation.value)
out['steps'].append({'name': 'rv_resource_release removes the face', 'width': width()})
out['gap'] = ('The parent ABI builds a font only from bytes through rv_font_load, with no descriptors (weight, style, '
              'stretch, unicode-range, feature settings, display, size-adjust), no URL source, no FontFace handle or '
              'status, and no FontFaceSet has/size/add/delete/clear/iteration: a registered face leaves the set only '
              'when its operation is released, and a host cannot see CSS-connected faces.')
destroy(host)
out_path.write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
print(json.dumps(out, indent=1))
