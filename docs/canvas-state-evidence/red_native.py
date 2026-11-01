"""RED measurement of the R03 canvas state, transform and compositing surface on a runtime: which exports exist, and
the CanvasFiltersEnabled and CanvasLayersEnabled defaults. Usage: red_native.py <native directory> <output json>."""
import ctypes, json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parents[1] / 'tests/abi'))
from svg_paint_probe import SvgProbe

CONTEXT = 'rv_dom_canvas_rendering_context2_d_'
NAMES = [CONTEXT + n for n in ['get_global_alpha', 'set_global_alpha', 'get_global_composite_operation', 'set_global_composite_operation',
                               'get_filter', 'set_filter', 'save', 'restore', 'reset', 'begin_layer', 'end_layer', 'scale', 'rotate',
                               'translate', 'transform', 'get_transform', 'set_transform_6', 'set_transform_1', 'reset_transform']]
out = {}
with SvgProbe(sys.argv[1], 320, 240) as p:
    lib = p.library
    out['abi'] = p.bind('rv_abi_version', p.integer, [])()
    out['exports'] = {n: hasattr(lib, n) for n in NAMES}
    out['r02Present'] = hasattr(lib, CONTEXT + 'fill_2')
out['webkitDefaults'] = {'CanvasFiltersEnabled': False, 'CanvasLayersEnabled': False,
                         'source': 'Source/WTF/Scripts/Preferences/UnifiedWebPreferences.yaml (status testable, WebCore default false)'}
out['red'] = not any(out['exports'].values())
Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in out.items() if k != 'exports'}), sum(out['exports'].values()), 'of', len(NAMES), 'exports present')
