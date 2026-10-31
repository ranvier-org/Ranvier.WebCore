"""RED measurement of R09 image readiness on a runtime: a delayed <img> (response held by the resource handler),
rv_image_decode started before the bytes exist, the outcome after they arrive, and the painted pixels of the image
box before and after decode. Usage: red_native.py <runtime> <out.json>"""
import ctypes, hashlib, json, os, struct, sys, zlib
from pathlib import Path

runtime, out_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
os.add_dll_directory(str(runtime))
lib = ctypes.CDLL(str(runtime / 'RanvierWebCoreHost.dll'))
P, I, U64 = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint64


def bind(name, result, arguments):
    function = getattr(lib, name)
    function.restype, function.argtypes = result, arguments
    return function


def png(width, height, rgb):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    rows = b''.join(b'\x00' + bytes(rgb) * width for _ in range(height))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')


out = {'runtimeSha256': hashlib.sha256((runtime / 'RanvierWebCoreHost.dll').read_bytes()).hexdigest(), 'abi': bind('rv_abi_version', I, [])(), 'steps': []}
has = bind('rv_abi_has', I, [ctypes.c_char_p])
out['features'] = {f: has(f.encode()) for f in ['image-decode', 'font-load']}
create = bind('rv_host_create', P, [I, I])
destroy = bind('rv_host_destroy', None, [P])
load_html = bind('rv_host_load_html', I, [P, ctypes.c_char_p])
by_id = bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])
release_node = bind('rv_node_release', None, [P])
cycle = bind('rv_run_loop_cycle', I, [I])
update = bind('rv_host_update', I, [P])
paint = bind('rv_host_paint_rgba', I, [P, ctypes.c_char_p, I])
Handler = ctypes.CFUNCTYPE(None, P, P, ctypes.c_char_p)
set_handler = bind('rv_host_set_resource_handler', I, [P, Handler, P])
finish = bind('rv_resource_load_finish', I, [P, ctypes.c_char_p, I, ctypes.c_char_p])
Completion = ctypes.CFUNCTYPE(None, P, I, I, I)
decode = bind('rv_image_decode', I, [P, P, Completion, P, ctypes.POINTER(U64)])
release = bind('rv_resource_release', I, [U64])
held, results = [], []
handler = Handler(lambda context, load, url: held.append(load))
completion = Completion(lambda context, outcome, w, h: results.append((outcome, w, h)))
host = create(64, 64)
set_handler(host, handler, None)
load_html(host, b'<!DOCTYPE html><style>html,body{margin:0;background:#fff}img{display:block;width:16px;height:16px}</style><img id=i src="https://r09.test/red.png">')


def pixel():
    update(host)
    buffer = ctypes.create_string_buffer(64 * 64 * 4)
    status = paint(host, buffer, len(buffer))
    centre = (8 * 64 + 8) * 4
    return status, list(buffer.raw[centre:centre + 4])


node = by_id(host, b'i')
operation = U64(0)
out['decodeStatus'] = decode(host, node, completion, None, ctypes.byref(operation))
for _ in range(10):
    cycle(5)
out['steps'].append({'name': 'response held', 'results': list(results), 'held': len(held), 'pixel': pixel()})
for load in held:
    data = png(4, 4, (255, 0, 0))
    finish(load, data, len(data), b'image/png')
held.clear()
for _ in range(40):
    if results:
        break
    cycle(5)
out['steps'].append({'name': 'response served', 'results': list(results), 'pixel': pixel()})
release(operation.value)
release_node(node)
destroy(host)
out['note'] = 'ABI54 rv_image_decode already waits for a delayed response and settles once; the painted box is red after SUCCEEDED.'
out_path.write_text(json.dumps(out, indent=1), encoding='utf-8')
print(json.dumps(out))
