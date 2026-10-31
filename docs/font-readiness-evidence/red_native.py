"""RED measurement of font readiness on a runtime: which FontFaceSet-equivalent exports exist, and what a host can
observe about a delayed CSS @font-face load (served late through rv_host_set_resource_handler) with ABI30 alone.
Usage: red_native.py <runtime> <webkit-source> <out.json>"""
import ctypes, hashlib, json, os, sys
from pathlib import Path

runtime, source, out_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]), Path(sys.argv[3])
os.add_dll_directory(str(runtime))
lib = ctypes.CDLL(str(runtime / 'RanvierWebCoreHost.dll'))
P, I, D = ctypes.c_void_p, ctypes.c_int32, ctypes.c_double


def bind(name, result, arguments):
    function = getattr(lib, name)
    function.restype, function.argtypes = result, arguments
    return function


out = {'runtimeSha256': hashlib.sha256((runtime / 'RanvierWebCoreHost.dll').read_bytes()).hexdigest(), 'steps': []}
out['abi'] = bind('rv_abi_version', I, [])()
has = bind('rv_abi_has', I, [ctypes.c_char_p])
out['features'] = {f: has(f.encode()) for f in ['font-load', 'image-decode', 'font-readiness', 'fonts']}
out['exports'] = {n: hasattr(lib, n) for n in ['rv_fonts_status', 'rv_fonts_check', 'rv_fonts_load', 'rv_fonts_ready',
                                                'rv_fonts_watch', 'rv_fonts_unwatch', 'rv_font_load', 'rv_image_decode',
                                                'rv_resource_cancel', 'rv_resource_release']}
font = (source / 'Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf').read_bytes()
create = bind('rv_host_create', P, [I, I])
destroy = bind('rv_host_destroy', None, [P])
load_html = bind('rv_host_load_html', I, [P, ctypes.c_char_p])
by_id = bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])
release_node = bind('rv_node_release', None, [P])
rect = bind('rv_element_rect', I, [P] + [ctypes.POINTER(D)] * 4)
update = bind('rv_host_update', I, [P])
cycle = bind('rv_run_loop_cycle', I, [I])
Handler = ctypes.CFUNCTYPE(None, P, P, ctypes.c_char_p)
set_handler = bind('rv_host_set_resource_handler', I, [P, Handler, P])
finish = bind('rv_resource_load_finish', I, [P, ctypes.c_char_p, I, ctypes.c_char_p])
held = []


def serve(context, load, url):
    held.append((url.decode(), load))


handler = Handler(serve)
host = create(400, 100)
set_handler(host, handler, None)
page = (b'<!DOCTYPE html><style>@font-face{font-family:RvLate;src:url(https://t01.test/ahem.ttf)}'
        b'#s{font:20px RvLate, monospace;white-space:pre}</style><body><span id=s>XXXX</span>')
load_html(host, page)


def width():
    update(host)
    node = by_id(host, b's')
    x, y, w, h = D(), D(), D(), D()
    rect(node, ctypes.byref(x), ctypes.byref(y), ctypes.byref(w), ctypes.byref(h))
    release_node(node)
    return w.value


for _ in range(10):
    cycle(5)
out['steps'].append({'name': 'font requested, response held', 'width': width(), 'heldUrls': [u for u, _ in held]})
for url, load in held:
    finish(load, font, len(font), b'font/ttf')
held.clear()
for _ in range(10):
    cycle(5)
out['steps'].append({'name': 'response served', 'width': width()})
out['gap'] = ('ABI30 has no FontFaceSet status, check, load or ready, and no loading events: a host can see the late '
              'font only as a changed layout width, polled after an unknown number of run-loop cycles.')
destroy(host)
out_path.write_text(json.dumps(out, indent=1), encoding='utf-8')
print(json.dumps(out, indent=1))
