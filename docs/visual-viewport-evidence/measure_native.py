"""Exploratory measurement of a candidate runtime: VisualViewport members and events under resize, device scale,
page scale, wheel pans, window scrolls and obscured insets. Writes the JSON named by the second argument."""
import ctypes, json, math, sys
from pathlib import Path
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parents[1] / 'tests/abi'))
from svg_paint_probe import SvgProbe

CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p)
FIELDS = ['offset_left', 'offset_top', 'page_left', 'page_top', 'width', 'height', 'scale']
PAGE = '<!doctype html><style>html,body{margin:0}body{width:2000px;height:3000px}#a{position:absolute;left:0;top:0;width:50px;height:50px}#b{position:absolute;left:0;top:200px;width:50px;height:50px}</style><body><div id=a></div><div id=b></div>'


class WindowMetrics(ctypes.Structure):
    _fields_ = [('size', ctypes.c_int32), ('innerWidth', ctypes.c_int32), ('innerHeight', ctypes.c_int32),
                ('outerWidth', ctypes.c_int32), ('outerHeight', ctypes.c_int32), ('devicePixelRatio', ctypes.c_double)]


out = {'steps': []}
with SvgProbe(sys.argv[1], 320, 240) as p:
    P, I, D = p.pointer, p.integer, ctypes.c_double
    out['abi'] = p.bind('rv_abi_version', I, [])()
    has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
    out['features'] = {n: has(n.encode()) for n in ['visual-viewport', 'page-scale', 'obscured-insets', 'dom:VisualViewport']}
    p.load(PAGE, standalone=False)
    document = p.bind('rv_host_document', P, [P])(p.host)
    get_vv = p.bind('rv_dom_window_get_visual_viewport', I, [P, ctypes.POINTER(P)])
    getters = {f: p.bind('rv_dom_visual_viewport_get_' + f, I, [P, ctypes.POINTER(D)]) for f in FIELDS}
    metrics = p.bind('rv_host_window_metrics', I, [P, ctypes.POINTER(WindowMetrics)])
    position = p.bind('rv_host_scroll_position', I, [P, ctypes.POINTER(I), ctypes.POINTER(I)])
    add = p.bind('rv_event_target_add_listener', P, [P, ctypes.c_char_p, I, CALLBACK, P])
    window_target = p.bind('rv_host_window_event_target', P, [P])(p.host)
    event_type = p.bind('rv_event_type', I, [P, P, I, ctypes.POINTER(I)])
    cycle = p.bind('rv_run_loop_cycle', I, [I])
    set_scale = p.bind('rv_host_set_page_scale', I, [P, D, I, I])
    page_scale = p.bind('rv_host_page_scale', I, [P, ctypes.POINTER(D)])
    insets = p.bind('rv_host_set_obscured_insets', I, [P, D, D, D, D])
    scroll2 = p.bind('rv_dom_window_scroll_to_2', I, [P, D, D])
    element_at = p.bind('rv_host_element_at', P, [P, I, I])
    node_release = p.bind('rv_node_release', None, [P])
    rect = p.bind('rv_element_rect', I, [P, ctypes.POINTER(D), ctypes.POINTER(D), ctypes.POINTER(D), ctypes.POINTER(D)])
    box_a = p.bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])(p.host, b'a')

    def hit(x, y):
        node = element_at(p.host, x, y)
        if not node:
            return None
        try:
            return p.attribute(node, 'id') or 'other'
        finally:
            node_release(node)
    vv = P()
    out['getStatus'] = get_vv(document, ctypes.byref(vv))
    log = []

    def listener(name):
        def run(context, event):
            buffer, length = ctypes.create_string_buffer(32), I()
            event_type(event, buffer, 32, ctypes.byref(length))
            log.append(name + ':' + buffer.raw[:length.value].decode())
            return 0
        return CALLBACK(run)
    callbacks = [listener('vv'), listener('window')]
    for t in [b'resize', b'scroll']:
        add(vv, t, 0, callbacks[0], None)
        add(window_target, t, 0, callbacks[1], None)

    def settle():
        for _ in range(4):
            p.update()
            cycle(20)
        p.update()

    def state():
        values = {}
        for f in FIELDS:
            v = D(-999)
            status = getters[f](vv, ctypes.byref(v))
            values[f] = v.value if status == 0 else ('status', status)
        m = WindowMetrics(size=ctypes.sizeof(WindowMetrics)); metrics(p.host, ctypes.byref(m))
        x, y = I(), I(); position(p.host, ctypes.byref(x), ctypes.byref(y))
        s = D(); page_scale(p.host, ctypes.byref(s))
        r = [D(), D(), D(), D()]; rect(box_a, *[ctypes.byref(v) for v in r])
        values.update(hit10_10=hit(10, 10), hit10_30=hit(10, 30), hit10_190=hit(10, 190), rectA=[v.value for v in r])
        values.update(innerWidth=m.innerWidth, innerHeight=m.innerHeight, scrollX=x.value, scrollY=y.value, pageScale=s.value)
        return values

    def step(name, action):
        settle(); log.clear()
        result = action()
        settle()
        out['steps'].append({'name': name, 'result': result, 'state': state(), 'events': list(log)})

    step('initial', lambda: None)
    step('scrollTo(10, 20)', lambda: scroll2(document, 10, 20))
    step('scrollTo(0, 0)', lambda: scroll2(document, 0, 0))
    step('resize 300x200', lambda: p.call('rv_host_resize', [P, I, I], p.host, 300, 200))
    step('device scale 2', lambda: p.bind('rv_host_set_device_scale', I, [P, ctypes.c_float])(p.host, 2.0))
    step('device scale 1', lambda: p.bind('rv_host_set_device_scale', I, [P, ctypes.c_float])(p.host, 1.0))
    step('page scale 2 at 0,0', lambda: set_scale(p.host, 2.0, 0, 0))
    step('scrollTo(100, 50) at scale 2', lambda: scroll2(document, 100, 50))
    step('wheel 30,40 at 150,100', lambda: p.bind('rv_host_wheel', I, [P, I, I, ctypes.c_float, ctypes.c_float, I])(p.host, 150, 100, 30, 40, 0))
    step('page scale 1 at 100,50', lambda: set_scale(p.host, 1.0, 100, 50))
    step('scrollTo(0, 0) again', lambda: scroll2(document, 0, 0))
    step('page scale 2 at 40,60', lambda: set_scale(p.host, 2.0, 40, 60))
    step('page scale 1 at 0,0', lambda: set_scale(p.host, 1.0, 0, 0))
    for value in [0.0, -1.0, float('nan'), float('inf'), 0.01, 20.0, 1.0]:
        step('page scale %r' % value, lambda value=value: set_scale(p.host, value, 0, 0))
    for args in [(20, 0, 40, 0), (0, 30, 0, 10), (-1, 0, 0, 0), (float('nan'), 0, 0, 0), (0, 0, 0, 0)]:
        step('insets %r' % (args,), lambda args=args: insets(p.host, *args))
    step('insets 20,0,40,0 then scrollTo(0,100)', lambda: (insets(p.host, 20, 0, 40, 0), scroll2(document, 0, 100))[0])
    step('insets 0 again', lambda: insets(p.host, 0, 0, 0, 0))
    node_release(box_a)
    p.dispose_host()
    v = D(-999)
    out['afterDestroy'] = {f: (getters[f](vv, ctypes.byref(v)), v.value) for f in FIELDS}
    p.bind('rv_event_target_release', None, [P])(vv)
Path(sys.argv[2]).write_text(json.dumps(out, indent=1, default=str) + '\n')
for s in out['steps']:
    print(s['name'], s['result'], {k: (round(v, 3) if isinstance(v, float) else v) for k, v in s['state'].items()}, s['events'])
print(out['features'], out['getStatus'], out['afterDestroy'])
