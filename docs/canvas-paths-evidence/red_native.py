"""RED measurement of the R02 canvas path and hit-testing surface on a runtime: which path exports exist, and which
capability rows the runtime reports. Usage: red_native.py <native directory> <output json>."""
import json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parents[1] / 'tests/abi'))
from svg_paint_probe import SvgProbe
import ctypes

CONTEXT = 'rv_dom_canvas_rendering_context2_d_'
NAMES = [CONTEXT + n for n in ['stroke_rect', 'begin_path', 'close_path', 'move_to', 'line_to', 'quadratic_curve_to', 'bezier_curve_to',
                               'arc_to', 'rect', 'round_rect_5_list', 'round_rect_5_value', 'arc', 'ellipse', 'fill_1', 'fill_2',
                               'stroke_0', 'stroke_1', 'clip_1', 'clip_2', 'is_point_in_path_3', 'is_point_in_path_4',
                               'is_point_in_stroke_2', 'is_point_in_stroke_3']]
NAMES += ['rv_dom_path2_d_' + n for n in ['create_0', 'create_1_path', 'create_1_d', 'add_path', 'close_path', 'move_to', 'line_to',
                                         'quadratic_curve_to', 'bezier_curve_to', 'arc_to', 'rect', 'round_rect_5_list',
                                         'round_rect_5_value', 'arc', 'ellipse', 'retain', 'release']]
out = {}
with SvgProbe(sys.argv[1], 320, 240) as p:
    lib = p.library
    out['abi'] = p.bind('rv_abi_version', p.integer, [])()
    out['exports'] = {n: hasattr(lib, n) for n in NAMES}
    has = p.bind('rv_abi_has', p.integer, [ctypes.c_char_p])
    out['abiHas'] = {n: has(n.encode()) for n in ['canvas-context', 'dom:CanvasRenderingContext2D', 'dom:Path2D']}
    out['r01Present'] = hasattr(lib, CONTEXT + 'fill_rect')
out['red'] = not any(out['exports'].values()) and out['abiHas']['dom:Path2D'] == 0
Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in out.items() if k != 'exports'}), sum(out['exports'].values()), 'of', len(NAMES), 'exports present')
