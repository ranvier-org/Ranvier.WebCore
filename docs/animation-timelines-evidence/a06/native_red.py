"""RED (anim3): what the A01 runtime offers for A06 document/custom timelines, A07 scroll timelines and A08 view timelines
and ranges. argv: <native runtime directory> <output json>. Runs the A06 measurements of red_chromium.mjs with the A01 exports."""
import ctypes, json, sys
from pathlib import Path
sys.path.insert(0, 'C:/wk/native-waapi-tl/tests/abi')
from form_collections import Native, P, I, U, OK  # noqa: E402

D = ctypes.c_double
src = Path('C:/wk/waapi-tl-artifacts/red/red_chromium.mjs').read_text(encoding='utf-8')
PAGE = src[src.index('`') + 1:src.index('`', src.index('`') + 1)]
WANTED = {
    'A06': ['rv_dom_document_get_timeline', 'rv_dom_document_timeline_create', 'rv_dom_animation_timeline_get_current_time',
            'rv_dom_animation_timeline_get_duration', 'rv_dom_document_timeline_get_maximum_frame_rate', 'rv_dom_document_timeline_animate',
            'rv_dom_web_animation_get_frame_rate', 'rv_dom_web_animation_set_frame_rate'],
    'A07': ['rv_dom_scroll_timeline_create', 'rv_dom_scroll_timeline_get_source', 'rv_dom_scroll_timeline_get_axis'],
    'A08': ['rv_dom_view_timeline_create', 'rv_dom_view_timeline_get_subject', 'rv_dom_view_timeline_get_start_offset',
            'rv_dom_view_timeline_get_end_offset', 'rv_dom_web_animation_get_range_start', 'rv_dom_web_animation_set_range_start',
            'rv_dom_web_animation_get_range_end', 'rv_dom_web_animation_set_range_end'],
}


class Time(ctypes.Structure):
    _fields_ = [('present', I), ('tag', I), ('arm0', D), ('arm1', P)]


class TimelineOptions(ctypes.Structure):
    _fields_ = [('size', U), ('origin_time', D)]


n = Native(sys.argv[1])
out = {'abi': n.bind('rv_abi_version', I, [])(), 'exports': {g: {name: hasattr(n.library, name) for name in names} for g, names in WANTED.items()}}
has = n.bind('rv_abi_has', I, [ctypes.c_char_p])
out['features'] = {f: has(f.encode()) for f in ['dom:AnimationTimeline', 'dom:DocumentTimeline', 'dom:ScrollTimeline', 'dom:ViewTimeline',
                                                 'dom-constructor:DocumentTimeline', 'dom-constructor:ScrollTimeline', 'dom-constructor:ViewTimeline']}


def time(handle, fn='rv_dom_animation_timeline_get_current_time'):
    value = Time()
    status = n.call(fn, [P, ctypes.POINTER(Time)], handle, ctypes.byref(value))
    if status != OK:
        return {'status': status}
    return None if not value.present else {'number': value.arm0} if value.tag == 1 else {'handle': bool(value.arm1)}


def own_timeline(document, origin):
    result = P()
    n.ok('rv_dom_document_timeline_create', [P, P, ctypes.POINTER(P)], document, ctypes.byref(TimelineOptions(ctypes.sizeof(TimelineOptions), origin)), ctypes.byref(result))
    return result.value


host = n.bind('rv_host_create', P, [I, I])(320, 240)
n.ok('rv_host_load_html', [P, ctypes.c_char_p], host, PAGE.encode())
document = n.bind('rv_host_document', P, [P])(host)
dt = n.handle('rv_dom_document_get_timeline', [P], document, nullable=False)
own, future, dflt = own_timeline(document, 100.0), own_timeline(document, 1e9), own_timeline(document, 0.0)
t, o, f, z = time(dt), time(own), time(future), time(dflt)
a06 = {'currentTime': t, 'duration': time(dt, 'rv_dom_animation_timeline_get_duration'), 'ownMinusOrigin': o['number'] == t['number'] - 100,
       'defaultEqual': z == t, 'futureNegative': f['number'] < 0, 'ownDuration': time(own, 'rv_dom_animation_timeline_get_duration')}
implementation = n.handle('rv_dom_document_get_implementation', [P], document, nullable=False)
detached = P()
n.ok('rv_dom_dom_implementation_create_html_document', [P, P, I, ctypes.POINTER(P)], implementation, None, 0, ctypes.byref(detached))
detached_timeline = n.handle('rv_dom_document_get_timeline', [P], detached.value, nullable=False)
a06['detachedCurrentTime'] = time(detached_timeline)
anim = P()
n.ok('rv_dom_web_animation_create', [P, P, P, I, ctypes.POINTER(P)], document, None, detached_timeline, 1, ctypes.byref(anim))
n.ok('rv_dom_web_animation_play', [P], anim.value)
a06['detachedAnimation'] = {'playState': n.integer('rv_dom_web_animation_get_play_state', anim.value),
                            'currentTime': time(anim.value, 'rv_dom_web_animation_get_current_time'),
                            'startTime': time(anim.value, 'rv_dom_web_animation_get_start_time')}
out['a06'] = a06
for handle in (own, future, dflt, detached_timeline):
    n.bind('rv_dom_animation_timeline_release', None, [P])(handle)
n.bind('rv_event_target_release', None, [P])(anim.value)
n.bind('rv_node_release', None, [P])(detached.value)
n.bind('rv_dom_dom_implementation_release', None, [P])(implementation)
n.bind('rv_host_destroy', None, [P])(host)
# Teardown: the document timeline handle outlives its host.
out['a06']['afterHostDestroy'] = time(dt)
n.bind('rv_dom_animation_timeline_release', None, [P])(dt)
out['missing'] = {g: [k for k, v in e.items() if not v] for g, e in out['exports'].items()}
Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
print(json.dumps(out))
