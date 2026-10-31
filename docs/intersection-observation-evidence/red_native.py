"""RED: what the native intersection observer exposes today (rv_host_observe_intersection: target, isIntersecting,
ratio; viewport root only), replayed over the Chromium RED page. Writes the JSON named by the second argument."""
import ctypes, json, sys
from pathlib import Path
sys.path.insert(0, 'C:/wk/native-intersect/tests/abi')
from form_collections import Native, P, I

D = ctypes.c_double
INTERSECT = ctypes.CFUNCTYPE(None, P, P, I, D)
RESIZE = ctypes.CFUNCTYPE(None, P, P, D, D)
FRAME = ctypes.CFUNCTYPE(None, P)
src = Path('C:/wk/intersect-artifacts/red/red_chromium.mjs').read_text(encoding='utf-8')
PAGE = src[src.index('`') + 1:src.index('`', src.index('`') + 1)].replace('${', '')

n = Native(sys.argv[1])
host = n.bind('rv_host_create', P, [I, I])(320, 240)
out = {'abi': n.bind('rv_abi_version', I, [])(), 'exports': {name: hasattr(n.library, name) for name in [
    'rv_host_observe_intersection', 'rv_host_observe_intersection_entries', 'rv_observer_take_records', 'rv_observer_disconnect',
    'rv_host_observe_resize_entries', 'rv_host_now', 'rv_host_performance_now']}}
n.ok('rv_host_load_html', [P, ctypes.c_char_p], host, PAGE.encode())
by_id = n.bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])
update = lambda: n.call('rv_host_update', [P], host)
scroll = lambda x, y: n.call('rv_host_scroll_to', [P, I, I], host, x, y)
scroll_top = lambda el, v: n.call('rv_dom_element_set_scroll_top', [P, I], el, v)
rect = n.bind('rv_element_rect', I, [P] + [ctypes.POINTER(D)] * 4)
make = n.bind('rv_host_observe_intersection', P, [P, INTERSECT, P, ctypes.c_char_p, ctypes.POINTER(D), I])
observe = lambda o, el: n.call('rv_observer_observe', [P, P], o, el)
unobserve = lambda o, el: n.call('rv_observer_unobserve', [P, P], o, el)
release = n.bind('rv_observer_release', None, [P])
el = {i: by_id(host, i.encode()) for i in ['far', 's', 'u', 'x', 'c', 'v', 'r']}
name = {v: k for k, v in el.items()}
log, keep = [], []


def observer(tag, margin, thresholds):
    cb = INTERSECT(lambda c, t, i, r: log.append([tag, name.get(t, '?'), i, round(r, 4)]))
    keep.append(cb)
    array = (D * len(thresholds))(*thresholds) if thresholds else None
    return make(host, cb, None, margin.encode() if margin is not None else None, array, len(thresholds))


rcb = RESIZE(lambda c, t, w, h: log.append(['ro', name.get(t, '?')]))
fcb = FRAME(lambda c: log.append(['frame-callback']))
n.call('rv_host_set_frame_callback', [P, FRAME, P], host, fcb, None)
io = {'implicit': observer('implicit', '0px', [0, 0.5, 1]), 'pct': observer('pct', '10%', [0, 0.5, 1]),
      'px': observer('px', '10px', [0]), 'scroll': observer('scroll', None, [0, 0.2])}
ro = n.bind('rv_host_observe_resize', P, [P, RESIZE, P])(host, rcb, None)
observe(ro, el['r'])
observe(io['scroll'], el['v']); observe(io['implicit'], el['far']); observe(io['pct'], el['far']); observe(io['px'], el['far'])
out['invalid'] = {'bogus margin': bool(observer('bad', 'bogus', [])), 'threshold 2': bool(observer('bad', '0px', [2.0])),
                  'em margin': bool(observer('bad', '1em', [])), 'descending thresholds': bool(observer('bad', '0px', [1, 0]))}
steps = []


def step(label, action):
    log.clear()
    result = action()
    u1 = update(); u2 = update()
    r = {}
    for k in ['far', 'u', 'v']:
        values = [D(), D(), D(), D()]
        rect(el[k], *[ctypes.byref(x) for x in values])
        r[k] = [x.value for x in values]
    steps.append({'name': label, 'result': result, 'updates': [u1, u2], 'log': list(log), 'rects': r})


step('initial', lambda: None)
step('scroll window 0,200', lambda: scroll(0, 200))
step('scroll window 0,165', lambda: scroll(0, 165))
step('unobserve far on implicit, scroll 0,0', lambda: (unobserve(io['implicit'], el['far']), scroll(0, 0))[0])
step('observe then unobserve before update', lambda: (observe(io['implicit'], el['far']), unobserve(io['implicit'], el['far']))[0])
step('observe far again on implicit, scroll 0,200', lambda: (observe(io['implicit'], el['far']), scroll(0, 200))[0])
step('remove intersecting far', lambda: n.call('rv_node_remove', [P], el['far']))
step('release pct, scroll 0,0', lambda: (release(io.pop('pct')), scroll(0, 0))[0])
out['steps'] = steps
for o in io.values():
    release(o)
release(ro)
n.call('rv_host_set_frame_callback', [P, P, P], host, None, None)
for v in el.values():
    n.bind('rv_node_release', None, [P])(v)
n.bind('rv_host_destroy', None, [P])(host)
Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
print(json.dumps(out['exports']), out['abi'], out['invalid'])
for s in steps:
    print(s['name'], s['updates'], s['log'], s['rects']['far'])
