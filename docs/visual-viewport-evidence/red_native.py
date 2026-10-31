"""RED measurement on a runtime directory: which visual viewport members and host inputs the runtime exports, and
the window metrics the host can drive. Writes red-native.json next to this file."""
import ctypes, json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parents[1] / 'tests/abi'))
sys.path.insert(0, str(here))
from svg_paint_probe import SvgProbe
from pe_exports import exports

directory = Path(sys.argv[1])
host_exports = exports(directory / 'RanvierWebCoreHost.dll')
webcore_exports = exports(directory / 'WebCore.dll')
pattern = ['visual', 'page_scale', 'pagescale', 'obscured', 'inset', 'zoom', 'window_metrics', 'device_scale', 'scroll_to', 'wheel', 'resize']
out = {'runtime': str(directory), 'hostExports': sorted(n for n in host_exports if n.startswith('rv_host') and any(t in n.lower() for t in pattern)),
       'hostVisualViewportExports': sorted(n for n in host_exports if 'visual' in n.lower()),
       'webcoreEngineEntryPoints': sorted(n for n in webcore_exports if any(t in n for t in ['setPageScaleFactor@Page', 'setObscuredContentInsets@Page', 'VisualViewportAPIEnabled', 'VisualViewport@WebCore', 'visualViewport@LocalDOMWindow']))}


class WindowMetrics(ctypes.Structure):
    _fields_ = [('size', ctypes.c_int32), ('innerWidth', ctypes.c_int32), ('innerHeight', ctypes.c_int32),
                ('outerWidth', ctypes.c_int32), ('outerHeight', ctypes.c_int32), ('devicePixelRatio', ctypes.c_double)]


with SvgProbe(str(directory), 320, 240) as p:
    P, I = p.pointer, p.integer
    out['abi'] = p.bind('rv_abi_version', I, [])()
    has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
    out['features'] = {name: has(name.encode()) for name in ['viewport', 'scroll', 'dom-window-scrolling', 'visual-viewport', 'page-scale', 'obscured-insets', 'resize', 'input']}
    p.load('<!doctype html><style>html,body{margin:0}body{width:2000px;height:3000px}</style><body>', standalone=False)
    metrics = p.bind('rv_host_window_metrics', I, [P, ctypes.POINTER(WindowMetrics)])
    rows = []
    for width, height, scale in [(320, 240, 1.0), (300, 200, 1.0), (300, 200, 2.0), (300, 200, 1.5)]:
        p.call('rv_host_resize', [P, I, I], p.host, width, height)
        p.call('rv_host_set_device_scale', [P, ctypes.c_float], p.host, scale)
        p.update()
        m = WindowMetrics(size=ctypes.sizeof(WindowMetrics))
        metrics(p.host, ctypes.byref(m))
        rows.append({'resize': [width, height], 'deviceScale': scale, 'innerWidth': m.innerWidth, 'innerHeight': m.innerHeight, 'devicePixelRatio': m.devicePixelRatio})
    out['windowMetrics'] = rows
(here / 'red-native.json').write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps(out, indent=1))
