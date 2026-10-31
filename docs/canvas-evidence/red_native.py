"""RED measurement of the R01 canvas 2D context surface on a runtime: which canvas exports exist, and what a <canvas>
paints when the app has no way to draw into it. Usage: red_native.py <native directory> <output json>."""
import ctypes, json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parents[1] / 'tests/abi'))
from svg_paint_probe import SvgProbe

NAMES = ['rv_canvas_get_context_2d', 'rv_canvas_get_context', 'rv_canvas_context_type', 'rv_canvas_context_2d_attributes',
         'rv_dom_html_canvas_element_get_width', 'rv_dom_html_canvas_element_set_width',
         'rv_dom_html_canvas_element_get_height', 'rv_dom_html_canvas_element_set_height',
         'rv_dom_canvas_rendering_context2_d_get_canvas', 'rv_dom_canvas_rendering_context2_d_get_fill_style',
         'rv_dom_canvas_rendering_context2_d_set_fill_style', 'rv_dom_canvas_rendering_context2_d_fill_rect',
         'rv_dom_canvas_rendering_context2_d_clear_rect', 'rv_dom_canvas_rendering_context2_d_release',
         'rv_dom_canvas_rendering_context2_d_retain']
out = {}
with SvgProbe(sys.argv[1], 320, 240) as p:
    lib = p.library
    out['abi'] = p.bind('rv_abi_version', p.integer, [])()
    out['exports'] = {n: hasattr(lib, n) for n in NAMES}
    has = p.bind('rv_abi_has', p.integer, [ctypes.c_char_p])
    out['abiHas'] = {n: has(n.encode()) for n in ['canvas-context', 'dom:HTMLCanvasElement', 'dom:CanvasRenderingContext2D', 'dom-generated']}
    p.load('<!doctype html><style>html,body{margin:0}canvas{display:block}</style><body><canvas id=c width=40 height=20></canvas>', standalone=False)
    c = p.node('c')
    out['attributes'] = p.attributes(c)
    p.update()
    snapshot = p.bind('rv_element_snapshot', p.integer, [p.pointer, p.pointer, p.integer, ctypes.POINTER(p.integer), ctypes.POINTER(p.integer)])
    w, h = p.integer(), p.integer()
    out['snapshotSizeStatus'] = snapshot(c, None, 0, ctypes.byref(w), ctypes.byref(h))
    rgba = (ctypes.c_uint8 * (w.value * h.value * 4))()
    out['snapshotStatus'] = snapshot(c, rgba, len(rgba), ctypes.byref(w), ctypes.byref(h))
    out['snapshotSize'] = [w.value, h.value]
    out['snapshotDistinctPixels'] = sorted({tuple(rgba[i:i + 4]) for i in range(0, len(rgba), 4)})
    try:
        p.bind('rv_canvas_get_context_2d', p.integer, [p.pointer, p.pointer, ctypes.POINTER(p.pointer)])
        out['getContext'] = 'present'
    except AssertionError as error:
        out['getContext'] = str(error)
out['red'] = not any(out['exports'].values())
Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
print(json.dumps(out))
