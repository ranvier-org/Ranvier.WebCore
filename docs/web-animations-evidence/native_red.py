"""RED: what the native library offers Web Animations creation today (A01), over the Chromium RED page.
argv: <native runtime directory> <output json>. The only animations it can hold are CSS animations/transitions
listed by rv_element_animations; no export creates one from keyframes, constructs an effect or an Animation."""
import ctypes, json, sys
from pathlib import Path
sys.path.insert(0, 'C:/wk/native-waapi/tests/abi')
from form_collections import Native, P, I

src = Path('C:/wk/waapi-artifacts/red/red_chromium.mjs').read_text(encoding='utf-8')
PAGE = src[src.index('`') + 1:src.index('`', src.index('`') + 1)]
WANTED = [
    # A01 creation
    'rv_dom_element_animate', 'rv_dom_keyframe_effect_create', 'rv_dom_keyframe_effect_create_1', 'rv_dom_web_animation_create',
    'rv_dom_document_timeline_create', 'rv_dom_document_get_timeline',
    # A01 control of a created animation (generated Animation members)
    'rv_dom_web_animation_pause', 'rv_dom_web_animation_set_current_time', 'rv_dom_web_animation_get_play_state', 'rv_dom_web_animation_get_effect',
    # A02 inspection
    'rv_dom_animation_effect_get_timing', 'rv_dom_animation_effect_get_computed_timing', 'rv_dom_animation_effect_update_timing',
    'rv_dom_keyframe_effect_get_keyframes', 'rv_dom_keyframe_effect_set_keyframes', 'rv_dom_keyframe_effect_get_target',
    # A04 / A05
    'rv_dom_web_animation_commit_styles', 'rv_dom_element_get_animations', 'rv_dom_document_get_animations', 'rv_dom_css_animation_get_animation_name',
    'rv_dom_css_transition_get_transition_property', 'rv_dom_web_animation_get_id',
    # existing hand-written animation ABI
    'rv_element_animations', 'rv_host_animations', 'rv_animation_control', 'rv_animation_seek', 'rv_animation_name', 'rv_animation_target']

n = Native(sys.argv[1])
out = {'abi': n.bind('rv_abi_version', I, [])(), 'exports': {name: hasattr(n.library, name) for name in WANTED}}
has = n.bind('rv_abi_has', I, [ctypes.c_char_p])
out['features'] = {f: has(f.encode()) for f in ['animation', 'dom-generated', 'dom:WebAnimation', 'dom:KeyframeEffect', 'dom:AnimationEffect', 'dom:DocumentTimeline']}
host = n.bind('rv_host_create', P, [I, I])(320, 240)
n.ok('rv_host_load_html', [P, ctypes.c_char_p], host, PAGE.encode())
by_id = n.bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])
a = by_id(host, b'a')
count = I()
n.ok('rv_element_animations', [P, I, P, I, ctypes.POINTER(I)], a, 0, None, 0, ctypes.byref(count))
out['element a animations before'] = count.value
# The page has no CSS animation, so the existing ABI has nothing to seek: nothing creates one from keyframes.
cs = ctypes.create_string_buffer(256)
length = I()
n.ok('rv_element_computed_style', [P, ctypes.c_char_p, P, I, ctypes.POINTER(I)], a, b'opacity', cs, 256, ctypes.byref(length))
out['element a opacity'] = cs.raw[:length.value].decode()
out['missing'] = [k for k, v in out['exports'].items() if not v]
n.call('rv_node_release', [P], a)
n.call('rv_host_destroy', [P], host)
Path(sys.argv[2]).write_text(json.dumps(out, indent=1), encoding='utf-8')
print(json.dumps(out, indent=1))
