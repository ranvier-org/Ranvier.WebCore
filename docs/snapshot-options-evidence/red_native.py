"""R12 RED survey of host/element snapshots on a candidate runtime: existing export behaviour at device scales and which
option exports exist. Writes the JSON named by the second argument."""
import ctypes, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests/abi'))
from svg_paint_probe import SvgProbe
out = {}
with SvgProbe(sys.argv[1], 40, 30) as p:
    P, I = p.pointer, p.integer
    lib = p.library
    has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
    out['abi'] = p.bind('rv_abi_version', I, [])()
    out['advertised'] = {n: has(n.encode()) for n in ['snapshot', 'partial-paint', 'snapshot-options', 'snapshot-encoding', 'image-encode']}
    out['exports'] = {n: hasattr(lib, n) for n in ['rv_host_snapshot', 'rv_element_snapshot_options', 'rv_snapshot_encode', 'rv_host_snapshot_encode',
        'rv_element_snapshot_encode', 'rv_snapshot_read', 'rv_host_paint_rgba_scaled', 'rv_image_encode', 'rv_snapshot_release']}
    p.load('<!doctype html><style>html,body{margin:0}#d{width:20px;height:10px;background:rgb(255,0,0)}</style><div id=d></div>', standalone=False)
    d = p.node('d')
    snap = p.bind('rv_element_snapshot', I, [P, ctypes.c_char_p, I, ctypes.POINTER(I), ctypes.POINTER(I)])
    scale = p.bind('rv_host_set_device_scale', I, [P, ctypes.c_float])
    paint_size = p.bind('rv_host_paint_size', I, [P, ctypes.POINTER(I), ctypes.POINTER(I)])
    rows = []
    for s in [1.0, 1.5, 2.0]:
        scale(p.host, s)
        w, h = I(), I()
        status = snap(d, None, 0, ctypes.byref(w), ctypes.byref(h))
        buf = ctypes.create_string_buffer(w.value * h.value * 4)
        status2 = snap(d, buf, len(buf), ctypes.byref(w), ctypes.byref(h))
        pw, ph = I(), I(); paint_size(p.host, ctypes.byref(pw), ctypes.byref(ph))
        rows.append({'deviceScale': s, 'sizeQuery': status, 'status': status2, 'size': [w.value, h.value], 'firstPixel': list(buf.raw[:4]), 'paintSize': [pw.value, ph.value]})
    out['elementSnapshot'] = rows
    out['note'] = 'scale is the host device scale only; no crop/encode/color-space/async options; output is unpremultiplied sRGB RGBA8'
Path(sys.argv[2]).write_text(json.dumps(out, indent=1), encoding='utf-8')
print(json.dumps(out, indent=1))
