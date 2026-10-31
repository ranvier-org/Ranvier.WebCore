"""RED measurement of the R06 canvas pixel surface on a runtime: which pixel exports exist, and whether an app can read
back or write a canvas's pixels without JavaScript. Usage: red_native.py <native directory> <output json>."""
import ctypes, json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parents[1] / 'tests/abi'))
from svg_paint_probe import SvgProbe

NAMES = ['rv_image_data_create', 'rv_image_data_layout', 'rv_image_data_read', 'rv_image_data_write',
         'rv_dom_image_data_get_width', 'rv_dom_image_data_get_height', 'rv_dom_image_data_release', 'rv_dom_image_data_retain',
         'rv_dom_image_bitmap_release', 'rv_dom_image_bitmap_retain',
         'rv_dom_canvas_rendering_context2_d_create_image_data_3', 'rv_dom_canvas_rendering_context2_d_create_image_data_1',
         'rv_dom_canvas_rendering_context2_d_get_image_data', 'rv_dom_canvas_rendering_context2_d_put_image_data_3',
         'rv_dom_canvas_rendering_context2_d_put_image_data_7', 'rv_dom_canvas_rendering_context2_d_draw_image_3',
         'rv_dom_canvas_rendering_context2_d_draw_image_5', 'rv_dom_canvas_rendering_context2_d_draw_image_9']
out = {}
with SvgProbe(sys.argv[1], 320, 240) as p:
    lib = p.library
    out['abi'] = p.bind('rv_abi_version', p.integer, [])()
    out['exports'] = {n: hasattr(lib, n) for n in NAMES}
    has = p.bind('rv_abi_has', p.integer, [ctypes.c_char_p])
    out['abiHas'] = {n: has(n.encode()) for n in ['canvas-context', 'canvas-pixels', 'dom:ImageData', 'dom:ImageBitmap', 'dom:CanvasRenderingContext2D']}
    # R01 surface present: a 2D context draws, but the only readback is the element snapshot (premultiplied paint
    # over the page, at layout size), and nothing writes pixels.
    p.load('<!doctype html><style>html,body{margin:0}canvas{display:block}</style><body><canvas id=c width=4 height=2 style="width:4px;height:2px"></canvas>', standalone=False)
    c = p.node('c')
    ctx = p.pointer()
    get_context = p.bind('rv_canvas_get_context', p.integer, [p.pointer, p.integer, p.pointer, ctypes.POINTER(p.pointer)])
    out['getContext'] = get_context(c, 1, None, ctypes.byref(ctx))
    out['getImageDataReachable'] = hasattr(lib, 'rv_dom_canvas_rendering_context2_d_get_image_data')
    p.bind('rv_dom_canvas_rendering_context2_d_release', None, [p.pointer])(ctx)
out['red'] = not any(out['exports'].values()) and out['abiHas']['canvas-pixels'] == 0
Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
print(json.dumps(out))
