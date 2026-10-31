"""Replays the A04 commitStyles cases of tests/abi/web_animation_commit_browser.mjs: a paused animation seeked to its
midpoint commits its styles and is cancelled; the style attribute, the inline values and priorities and the computed
values match the Chromium oracle tests/fixtures/web-animation-commit-oracle.json, and unrelated inline properties keep
their values and priorities. The error cases (detached, not rendered, no target, a pseudo-element target, no effect)
match the oracle's exception names. tests/fixtures/web-animation-commit-qualified.json records the two engine
differences: declaration order in the style attribute, and the value committed over an important inline declaration."""

import argparse
import ctypes
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, P, I, OK, DOM_EXCEPTION, ABI  # noqa: E402
from web_animations import Arena, AnimationOptions, KeyframeAnimationOptions, EffectOptions, KeyframeEffectOptions, Time, exception_name  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
# The oracle page of web_animation_commit_browser.mjs.
PAGE = ('<!doctype html><html><head><style>html,body{margin:0}.box{position:absolute;width:40px;height:40px}'
        '#hidden{display:none}</style></head><body>'
        '<div id=a class=box style="color: rgb(1, 2, 3) !important; margin-top: 0px"></div>'
        '<div id=b class=box style="opacity: 0.2 !important"></div>'
        '<div id=c class=box></div><div id=hidden class=box></div></body></html>')
CASES = [
    {'name': 'opacity and transform', 'el': 'a', 'keyframes': [{'props': {'opacity': '0', 'transform': 'translateX(0px)'}},
                                                               {'props': {'opacity': '1', 'transform': 'translateX(100px)'}}],
     'props': ['opacity', 'transform', 'color', 'margin-top']},
    {'name': 'over an important inline value', 'el': 'b', 'keyframes': [{'props': {'opacity': '0'}}, {'props': {'opacity': '1'}}], 'props': ['opacity']},
    {'name': 'composite add over a stylesheet value', 'el': 'c',
     'keyframes': [{'props': {'marginLeft': '0px'}, 'composite': 'add'}, {'props': {'marginLeft': '10px'}, 'composite': 'add'}], 'props': ['margin-left']},
]
PLAY_STATES = ['idle', 'running', 'paused', 'finished']


def utf8(text):
    data = text.encode('utf-8')
    return ctypes.create_string_buffer(data), len(data)


def string_result(native, name, arguments, *values):
    buffer, length = ctypes.create_string_buffer(1024), I()
    native.ok(name, arguments + [P, I, ctypes.POINTER(I)], *values, buffer, 1024, ctypes.byref(length))
    return None if length.value < 0 else buffer.raw[:length.value].decode('utf-8')


def verify(directory):
    oracle = json.loads((FIXTURES / 'web-animation-commit-oracle.json').read_text(encoding='utf-8'))
    n = Native(directory)
    n.expect(n.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
    host = n.bind('rv_host_create', P, [I, I])(320, 240)
    n.ok('rv_host_load_html', [P, ctypes.c_char_p], host, PAGE.encode('utf-8'))
    document = n.bind('rv_host_document', P, [P])(host)
    by_id = n.bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])
    release_node = n.bind('rv_node_release', None, [P])
    held, results, errors, failures = [], [], {}, []

    def animate(element, frames, options=1000):
        arena = Arena()
        animation = P()
        status = n.call('rv_dom_element_animate', [P, P, P, ctypes.POINTER(P)], element, arena.keyframes(frames),
                        arena.options(AnimationOptions, KeyframeAnimationOptions, options), ctypes.byref(animation))
        n.expect(status == OK, 'animate')
        held.append(animation.value)
        return animation.value

    def attribute(element):
        name, length = utf8('style')
        return string_result(n, 'rv_dom_element_get_attribute', [P, P, I], element, name, length)

    def computed(element, prop):
        buffer, length = ctypes.create_string_buffer(512), I()
        n.ok('rv_element_computed_style', [P, ctypes.c_char_p, P, I, ctypes.POINTER(I)], element, prop.encode(), buffer, 512, ctypes.byref(length))
        return buffer.raw[:length.value].decode('utf-8')

    def commit(animation):
        status = n.call('rv_dom_web_animation_commit_styles', [P], animation)
        return 'ok' if status == OK else exception_name(n) if status == DOM_EXCEPTION else 'status ' + str(status)

    try:
        for case in CASES:
            element = by_id(host, case['el'].encode())
            animation = animate(element, case['keyframes'])
            n.ok('rv_dom_web_animation_pause', [P], animation)
            n.ok('rv_dom_web_animation_set_current_time', [P, ctypes.POINTER(Time)], animation, ctypes.byref(Time(1, 1, 500.0, None)))
            n.expect(commit(animation) == 'ok', case['name'] + ': commitStyles')
            committed = attribute(element)
            n.ok('rv_dom_web_animation_cancel', [P], animation)
            style = n.handle('rv_dom_html_element_get_style', [P], element, nullable=False)
            inline = {}
            for prop in case['props']:
                data, length = utf8(prop)
                inline[prop] = [string_result(n, 'rv_dom_css_style_declaration_get_property_value', [P, P, I], style, data, length),
                                string_result(n, 'rv_dom_css_style_declaration_get_property_priority', [P, P, I], style, data, length)]
            n.bind('rv_dom_css_style_declaration_release', None, [P])(style)
            results.append({'name': case['name'], 'committed': committed, 'afterCancel': attribute(element), 'inline': inline,
                            'computed': {prop: computed(element, prop) for prop in case['props']},
                            'playState': PLAY_STATES[n.integer('rv_dom_web_animation_get_play_state', animation)]})
            release_node(element)
        create = n.bind('rv_document_create_element', P, [P, ctypes.c_char_p])
        detached = create(host, b'div')
        errors['detached element'] = commit(animate(detached, [{'props': {'opacity': '0'}}, {'props': {'opacity': '1'}}]))
        hidden = by_id(host, b'hidden')
        errors['element not rendered'] = commit(animate(hidden, [{'props': {'opacity': '0'}}, {'props': {'opacity': '1'}}]))
        arena, effect, animation = Arena(), P(), P()
        n.ok('rv_dom_keyframe_effect_create_3', [P, P, P, P, ctypes.POINTER(P)], document, None, arena.keyframes([{'props': {'opacity': '0'}}]),
             arena.options(EffectOptions, KeyframeEffectOptions, 1000), ctypes.byref(effect))
        n.ok('rv_dom_web_animation_create', [P, P, P, I, ctypes.POINTER(P)], document, effect, None, 0, ctypes.byref(animation))
        n.bind('rv_dom_animation_effect_release', None, [P])(effect)
        held.append(animation.value)
        errors['no target'] = commit(animation.value)
        c = by_id(host, b'c')
        errors['pseudo-element target'] = commit(animate(c, [{'props': {'opacity': '0'}}, {'props': {'opacity': '1'}}], {'duration': 1000, 'pseudoElement': '::before'}))
        empty = P()
        n.ok('rv_dom_web_animation_create', [P, P, P, I, ctypes.POINTER(P)], document, None, None, 0, ctypes.byref(empty))
        held.append(empty.value)
        errors['no effect'] = commit(empty.value)
        n.expect(n.call('rv_dom_web_animation_commit_styles', [P], None) == -1, 'commitStyles NULL target')
        for node in (detached, hidden, c):
            release_node(node)
    finally:
        for animation in held:
            n.call('rv_dom_web_animation_cancel', [P], animation)
            n.bind('rv_event_target_release', None, [P])(animation)
        release_node(document)
        n.bind('rv_host_destroy', None, [P])(host)
    qualified = json.loads((FIXTURES / 'web-animation-commit-qualified.json').read_text(encoding='utf-8'))['cases']
    for actual, wanted in zip(results, oracle['cases']):
        n.assertions += 1
        entry = qualified.get(actual['name'])
        if entry and entry['field'] == 'committed/afterCancel':
            # The declarations match exactly; only their order differs, as recorded.
            expected_native = dict(wanted, committed=entry['webkit'], afterCancel=entry['webkit'])
            same = actual == expected_native and wanted['committed'] == entry['chromium']
        elif entry:
            same = actual == dict(wanted, **entry['webkit']) and all(wanted[k] == v for k, v in entry['chromium'].items())
        else:
            same = actual == wanted
        if not same:
            failures.append({'case': actual['name'], 'native': actual, 'chromium': wanted})
    for name, wanted in oracle['errors'].items():
        n.assertions += 1
        if errors.get(name) != wanted:
            failures.append({'case': name, 'native': errors.get(name), 'chromium': wanted})
    return n, results, errors, failures, oracle['browser']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence')
    args = parser.parse_args()
    n, results, errors, failures, browser = verify(args.native_directory)
    if args.evidence:
        Path(args.evidence).write_text(json.dumps({'oracle': browser, 'assertions': n.assertions, 'failures': failures, 'cases': results,
                                                   'errors': errors}, indent=1) + '\n', encoding='utf-8')
    for failure in failures:
        print('MISMATCH', json.dumps(failure))
    if failures:
        raise SystemExit(f'{len(failures)} checks differ from {browser}')
    print(f'PASS web animation commit: {n.assertions} assertions against {browser}')


if __name__ == '__main__':
    main()
