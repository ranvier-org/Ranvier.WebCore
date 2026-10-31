"""RED measurement of coordinate spaces on a candidate runtime: what rv_element_rect, rv_host_element_at, rv_host_mouse
and the window/visual-viewport metrics report under nested transforms, scroll, page scale and device scale, and which
conversion exports exist. Writes the JSON named by the second argument."""
import ctypes, json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parents[1] / 'tests/abi'))
from svg_paint_probe import SvgProbe

CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p)
PAGE = ('<!doctype html><style>html,body{margin:0}body{width:2000px;height:3000px}'
        '#o{position:absolute;left:100px;top:50px;width:200px;height:100px;transform:rotate(30deg) scale(1.5)}'
        '#i{margin-left:20px;width:40px;height:40px;transform:translate(10px,5px) rotate(45deg)}'
        '#p{position:absolute;left:400px;top:50px;width:200px;height:200px;perspective:400px}'
        '#q{width:100px;height:100px;transform:rotateY(40deg)}'
        '#b{position:absolute;left:0;top:40px;width:50px;height:50px}</style>'
        '<body><div id=o><div id=i></div></div><div id=p><div id=q></div></div><div id=b></div>')


class WindowMetrics(ctypes.Structure):
    _fields_ = [('size', ctypes.c_int32), ('innerWidth', ctypes.c_int32), ('innerHeight', ctypes.c_int32),
                ('outerWidth', ctypes.c_int32), ('outerHeight', ctypes.c_int32), ('devicePixelRatio', ctypes.c_double)]


out = {'steps': []}
with SvgProbe(sys.argv[1], 320, 240) as p:
    P, I, D = p.pointer, p.integer, ctypes.c_double
    lib = p.library
    out['abi'] = p.bind('rv_abi_version', I, [])()
    out['exports'] = {n: hasattr(lib, n) for n in [
        'rv_dom_window_webkit_convert_point_from_node_to_page', 'rv_dom_window_webkit_convert_point_from_page_to_node',
        'rv_dom_element_get_box_quads', 'rv_dom_node_convert_quad_from_node', 'rv_dom_node_convert_point_from_node',
        'rv_coords_convert', 'rv_node_convert_points', 'rv_dom_element_get_client_rects', 'rv_dom_dom_matrix_create',
        'rv_dom_dom_quad_from_rect', 'rv_host_window_metrics', 'rv_host_page_scale']}
    p.load(PAGE, standalone=False)
    rect = p.bind('rv_element_rect', I, [P] + [ctypes.POINTER(D)] * 4)
    element_at = p.bind('rv_host_element_at', P, [P, I, I])
    release = p.bind('rv_node_release', None, [P])
    metrics = p.bind('rv_host_window_metrics', I, [P, ctypes.POINTER(WindowMetrics)])
    position = p.bind('rv_host_scroll_position', I, [P, ctypes.POINTER(I), ctypes.POINTER(I)])
    page_scale = p.bind('rv_host_page_scale', I, [P, ctypes.POINTER(D)])
    set_scale = p.bind('rv_host_set_page_scale', I, [P, D, I, I])
    device = p.bind('rv_host_set_device_scale', I, [P, ctypes.c_float])
    paint_size = p.bind('rv_host_paint_size', I, [P, ctypes.POINTER(I), ctypes.POINTER(I)])
    mouse = p.bind('rv_host_mouse', I, [P, I, I, I, I, I, I])
    number = p.bind('rv_event_number', I, [P, I, ctypes.POINTER(D)])
    target_of = p.bind('rv_event_target', P, [P, I])
    add = p.bind('rv_node_add_event_listener', P, [P, ctypes.c_char_p, I, CALLBACK, P])
    computed = p.bind('rv_element_computed_style', I, [P, ctypes.c_char_p, ctypes.c_char_p, I, ctypes.POINTER(I)])
    scroll_to = p.bind('rv_host_scroll_to', I, [P, I, I])
    document = p.bind('rv_host_document', P, [P])(p.host)
    nodes = {n: p.node(n) for n in ['o', 'i', 'p', 'q', 'b']}
    seen = []

    def on_down(context, event):
        x, y = D(), D()
        number(event, 0, ctypes.byref(x)); number(event, 1, ctypes.byref(y))
        node = target_of(event, 0)
        seen.append({'clientX': x.value, 'clientY': y.value, 'target': p.attribute(node, 'id') if node else None})
        return 0
    callback = CALLBACK(on_down)
    listener = add(document, b'mousedown', 0, callback, None)

    def hit(x, y):
        node = element_at(p.host, x, y)
        if not node:
            return None
        try:
            return p.attribute(node, 'id') or 'other'
        finally:
            release(node)

    def style(node, name):
        buffer, length = ctypes.create_string_buffer(256), I()
        computed(node, name.encode(), buffer, 256, ctypes.byref(length))
        return buffer.raw[:length.value].decode()

    def state():
        p.update()
        values = {}
        for n, node in nodes.items():
            r = [D(), D(), D(), D()]; rect(node, *[ctypes.byref(v) for v in r])
            values['rect_' + n] = [v.value for v in r]
        m = WindowMetrics(size=ctypes.sizeof(WindowMetrics)); metrics(p.host, ctypes.byref(m))
        x, y = I(), I(); position(p.host, ctypes.byref(x), ctypes.byref(y))
        s = D(); page_scale(p.host, ctypes.byref(s))
        w, h = I(), I(); paint_size(p.host, ctypes.byref(w), ctypes.byref(h))
        b = values['rect_b']
        cx, cy = int(b[0] + 25), int(b[1] + 25)
        values.update(innerWidth=m.innerWidth, innerHeight=m.innerHeight, dpr=m.devicePixelRatio, scroll=[x.value, y.value],
                      pageScale=s.value, paint=[w.value, h.value], b_center_client=[cx, cy], hit_b_center=hit(cx, cy))
        seen.clear()
        mouse(p.host, 1, cx, cy, 0, 1, 0); mouse(p.host, 2, cx, cy, 0, 1, 0)
        values['mouse_at_b_center'] = list(seen)
        # The point that rv_host_mouse needs to reach #b's centre under page scale s and scroll.
        seen.clear()
        sx, sy = int(cx * s.value), int(cy * s.value)
        mouse(p.host, 1, sx, sy, 0, 1, 0); mouse(p.host, 2, sx, sy, 0, 1, 0)
        values['mouse_at_scaled_center'] = {'at': [sx, sy], 'events': list(seen)}
        return values

    def step(name, action):
        result = action()
        out['steps'].append({'name': name, 'result': result, 'state': state()})

    out['transforms'] = {n: style(nodes[n], 'transform') for n in ['o', 'i', 'q']}
    out['transformOrigin'] = {n: style(nodes[n], 'transform-origin') for n in ['o', 'i', 'q']}
    step('initial', lambda: None)
    step('scroll 10,20', lambda: scroll_to(p.host, 10, 20))
    step('scroll 0,0', lambda: scroll_to(p.host, 0, 0))
    step('device scale 2', lambda: device(p.host, 2.0))
    step('page scale 2 at 0,0 (device 2)', lambda: set_scale(p.host, 2.0, 0, 0))
    step('page scale 2 at 40,60', lambda: set_scale(p.host, 2.0, 40, 60))
    step('page scale 1, device 1', lambda: (set_scale(p.host, 1.0, 0, 0), device(p.host, 1.0))[0])
    p.bind('rv_listener_remove', I, [P])(listener)
Path(sys.argv[2]).write_text(json.dumps(out, indent=1, default=str) + '\n', encoding='utf-8')
print(json.dumps(out['exports'])); print(out['transforms'], out['transformOrigin'])
for s in out['steps']:
    print(s['name'], json.dumps(s['state']))
