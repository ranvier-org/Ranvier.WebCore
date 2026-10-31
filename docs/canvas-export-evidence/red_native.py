"""RED measurement of the R07 canvas export and bitmap transport surface on a runtime: which export exports exist, and
what a bitmaprenderer request returns. Usage: red_native.py <native directory> <output json>."""
import ctypes, json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parents[1] / 'tests/abi'))
from svg_paint_probe import SvgProbe

NAMES = ['rv_canvas_encode', 'rv_canvas_to_data_url', 'rv_canvas_to_blob', 'rv_canvas_get_bitmap_context',
         'rv_image_bitmap_create', 'rv_image_bitmap_result', 'rv_image_bitmap_error',
         'rv_dom_image_bitmap_get_width', 'rv_dom_image_bitmap_get_height', 'rv_dom_image_bitmap_close',
         'rv_dom_image_bitmap_rendering_context_get_canvas', 'rv_dom_image_bitmap_rendering_context_transfer_from_image_bitmap',
         'rv_dom_image_bitmap_rendering_context_release', 'rv_image_encoding_supported']
out = {}
with SvgProbe(sys.argv[1], 320, 240) as p:
    lib = p.library
    out['abi'] = p.bind('rv_abi_version', p.integer, [])()
    out['exports'] = {n: hasattr(lib, n) for n in NAMES}
    has = p.bind('rv_abi_has', p.integer, [ctypes.c_char_p])
    out['abiHas'] = {n: has(n.encode()) for n in ['canvas-context', 'canvas-pixels', 'canvas-export', 'image-bitmaps',
                                                 'dom:ImageBitmap', 'dom:ImageBitmapRenderingContext', 'image-encoding-png']}
    p.load('<!doctype html><body><canvas id=c width=4 height=2></canvas>', standalone=False)
    c = p.node('c')
    ctx = p.pointer(1234)
    get_context = p.bind('rv_canvas_get_context', p.integer, [p.pointer, p.integer, p.pointer, ctypes.POINTER(p.pointer)])
    out['bitmapRendererStatus'] = get_context(c, 2, None, ctypes.byref(ctx))
    out['bitmapRendererContext'] = ctx.value
out['red'] = not any(v for k, v in out['exports'].items() if k != 'rv_image_encoding_supported') and out['abiHas']['canvas-export'] == 0 and out['bitmapRendererStatus'] == -9
Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
print(json.dumps(out))
