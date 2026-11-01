"""RED measurement of the R04 canvas paint surface on a runtime: which of the exports in r04-names.txt exist.
Usage: red_native.py <native directory> <output json>."""
import ctypes, json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parents[1] / 'tests/abi'))
from svg_paint_probe import SvgProbe

NAMES = (here / 'r04-names.txt').read_text(encoding='utf-8').split()
out = {}
with SvgProbe(sys.argv[1], 320, 240) as p:
    lib = p.library
    out['abi'] = p.bind('rv_abi_version', p.integer, [])()
    out['exports'] = {n: hasattr(lib, n) for n in NAMES}
    has = p.bind('rv_abi_has', p.integer, [ctypes.c_char_p])
    out['abiHas'] = {n: has(n.encode()) for n in ['dom:CanvasGradient', 'dom:CanvasPattern', 'dom:ImageBitmap', 'canvas-filters']}
    out['r03Present'] = hasattr(lib, 'rv_dom_canvas_rendering_context2_d_save')
out['red'] = not any(out['exports'].values()) and out['abiHas']['dom:ImageBitmap'] == 0
Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in out.items() if k != 'exports'}), sum(out['exports'].values()), 'of', len(NAMES), 'exports present')
