"""RED for patch 0050: rv_image_bitmap_create from a canvas (kind 0) or ImageData (kind 2) on a runtime, then 250 ms of
run loop. Without the patch every source aborts the process in an accelerated Skia ImageBuffer (Ganesh is a stub).
Usage: red_bitmap_buffer.py <native directory> <kind> [ctx]"""
import ctypes, sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[2] / 'tests/abi'))
from svg_paint_probe import SvgProbe
kind = int(sys.argv[2])
with SvgProbe(sys.argv[1], 100, 100) as p:
    P, I = p.pointer, p.integer
    p.load('<!doctype html><body><canvas id=c width=4 height=2></canvas>', standalone=False)
    c = p.node('c')
    Completion = ctypes.CFUNCTYPE(None, P, I, I, I)
    got = []
    cb = Completion(lambda ctx, o, w, h: got.append((o, w, h)))
    create = p.bind('rv_image_bitmap_create', I, [P, I, P, P, Completion, P, ctypes.POINTER(ctypes.c_uint64)])
    src = c
    if kind == 2:
        out = P(); p.bind('rv_image_data_create', I, [ctypes.c_uint32, ctypes.c_uint32, P, ctypes.c_int64, I, I, ctypes.POINTER(P)])(2, 2, None, 0, 0, 0, ctypes.byref(out)); src = out.value
    if kind == 0 and len(sys.argv) > 3:
        ctx = P(); p.bind('rv_canvas_get_context', I, [P, I, P, ctypes.POINTER(P)])(c, 1, None, ctypes.byref(ctx))
    op = ctypes.c_uint64()
    print('create', flush=True)
    print(create(p.host, kind, src, None, cb, None, ctypes.byref(op)), flush=True)
    cyc = p.bind('rv_run_loop_cycle', I, [I])
    for _ in range(50):
        cyc(5)
    print(got, flush=True)
