"""G04 RED: what the Screen getters report on Windows without patch 0038 and without rv_host_set_screen, against the
build machine's primary monitor (GetSystemMetrics, SystemParametersInfo SPI_GETWORKAREA, GetDeviceCaps BITSPIXEL)."""
import ctypes
import ctypes.wintypes as wt
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests' / 'abi'))
from form_collections import Native, Case, P, I


def monitor():
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    work = wt.RECT()
    user32.SystemParametersInfoW(0x30, 0, ctypes.byref(work), 0)
    dc = user32.GetDC(None)
    bits = gdi32.GetDeviceCaps(dc, 12)
    user32.ReleaseDC(None, dc)
    return {'width': user32.GetSystemMetrics(0), 'height': user32.GetSystemMetrics(1), 'avail_left': work.left,
            'avail_top': work.top, 'avail_width': work.right - work.left, 'avail_height': work.bottom - work.top,
            'color_depth': 24 if bits == 32 else bits}


def main(directory, out):
    n = Native(directory)
    case = Case(n, '<p>x</p>')
    values = {}
    for name in ['width', 'height', 'avail_left', 'avail_top', 'avail_width', 'avail_height']:
        values[name] = n.integer('rv_dom_screen_get_' + name, case.document)
    values['color_depth'] = n.integer('rv_dom_screen_get_color_depth', case.document, ctypes.c_uint32)
    values['orientationTypeStatus'] = n.call('rv_dom_screen_orientation_get_type', [P, ctypes.POINTER(I)], case.document, ctypes.byref(I()))
    case.close()
    system = monitor()
    # The DPI awareness of this process may scale the system metrics; the comparison is recorded, not asserted.
    report = {'runtime': str(directory), 'abiVersion': n.bind('rv_abi_version', I, [])(),
              'setScreenExport': hasattr(n.library, 'rv_host_set_screen'), 'hostSize': [320, 200],
              'engine': values, 'primaryMonitor': system,
              'engineEqualsMonitor': {k: values[k] == system[k] for k in system},
              'engineEqualsHostSize': [values['width'], values['height']] == [320, 200]}
    Path(out).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


main(sys.argv[1], sys.argv[2])
