"""Replays the A05 discovery steps of tests/abi/web_animation_discovery_browser.mjs: document, element and subtree
getAnimations over a CSS animation, a CSS transition and script animations, each described by its interface
(rv_dom_web_animation_get_interface_name), id, CSSAnimation.animationName or CSSTransition.transitionProperty, effect
target, timeline and effect type, and compares every step with the Chromium oracle
tests/fixtures/web-animation-discovery-oracle.json. Identity is handle equality: across the lists, and from the
hand-written CSS-animation handle through rv_animation_as_event_target. Each list is released once."""

import argparse
import ctypes
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, P, I, U, OK, NULL_ARGUMENT, WRONG_INTERFACE, ABI  # noqa: E402
from web_animations import Arena, AnimationOptions, KeyframeAnimationOptions  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
# The oracle page of web_animation_discovery_browser.mjs.
PAGE = ('<!doctype html><html><head><style>html,body{margin:0}.box{position:absolute;width:40px;height:40px}'
        '@keyframes fade{from{opacity:0}to{opacity:1}}@keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(90deg)}}'
        '#css{left:0;top:0;animation:fade 100s linear}#tr{left:50px;top:0;transition:opacity 100s linear}'
        '#tree{position:absolute;left:100px;top:0}#c2{animation:spin 100s linear}</style></head><body>'
        '<div id=css class=box></div><div id=tr class=box></div>'
        '<div id=tree><div id=c1 class=box></div><div id=c2 class=box></div></div></body></html>')
# The browser's constructor names of the query's IDL interface names.
PUBLIC = {'WebAnimation': 'Animation', 'CSSAnimation': 'CSSAnimation', 'CSSTransition': 'CSSTransition'}


class Animations(ctypes.Structure):
    _fields_ = [('present', I), ('count', I), ('items', ctypes.POINTER(P))]


class Options(ctypes.Structure):
    _fields_ = [('size', U), ('subtree', I)]


class Discovery:
    def __init__(self, native):
        self.n = native
        self.host = native.bind('rv_host_create', P, [I, I])(320, 240)
        native.ok('rv_host_load_html', [P, ctypes.c_char_p, I], self.host, PAGE.encode('utf-8'), len(PAGE.encode('utf-8')))  # utf8
        self.document = native.bind('rv_host_document', P, [P])(self.host)
        by_id_utf8 = native.bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p, I])
        by_id = lambda host, element_id: by_id_utf8(host, element_id, len(element_id))
        self.nodes = {name: by_id(self.host, name.encode()) for name in ['css', 'tr', 'tree', 'c1', 'c2']}
        self.timeline = native.handle('rv_dom_document_get_timeline', [P], self.document, nullable=False)
        self.lists = 0

    def listed(self, name, target, subtree=None):
        """The handles of one getAnimations list, each retained, and the list released."""
        result = Animations()
        if name == 'document':
            self.n.ok('rv_dom_document_get_animations', [P, ctypes.c_void_p], target, ctypes.byref(result))
        else:
            options = ctypes.byref(Options(ctypes.sizeof(Options), 1)) if subtree else None
            self.n.ok('rv_dom_element_get_animations', [P, P, ctypes.c_void_p], target, options, ctypes.byref(result))
        retain = self.n.bind('rv_event_target_retain', P, [P])
        handles = [retain(result.items[i]) for i in range(result.count)]
        self.n.expect(result.count == 0 or result.items, name + ': items')
        self.n.bind('rv_dom_sequence_web_animation_release', None, [P])(ctypes.byref(result))
        self.lists += 1
        return handles

    def describe(self, animation):
        n = self.n
        kind = n.text('rv_dom_web_animation_get_interface_name', [P], animation)
        effect = n.handle('rv_dom_web_animation_get_effect', [P], animation)
        timeline = n.handle('rv_dom_web_animation_get_timeline', [P], animation)
        target = n.handle('rv_dom_keyframe_effect_get_target', [P], effect) if effect else None
        out = {'type': PUBLIC[kind], 'id': n.text('rv_dom_web_animation_get_id', [P], animation),
               'animationName': n.text('rv_dom_css_animation_get_animation_name', [P], animation) if kind == 'CSSAnimation' else None,
               'transitionProperty': n.text('rv_dom_css_transition_get_transition_property', [P], animation) if kind == 'CSSTransition' else None,
               'target': n.text('rv_dom_element_get_id', [P], target) if target else None,
               'timelineIsDocument': timeline == self.timeline,
               'keyframeEffect': bool(effect) and n.text('rv_dom_animation_effect_get_interface_name', [P], effect) == 'KeyframeEffect'}
        if kind != 'CSSAnimation':
            n.expect(n.call('rv_dom_css_animation_get_animation_name', [P, P, I, ctypes.POINTER(I)], animation, None, 0, ctypes.byref(I())) == WRONG_INTERFACE,
                     'animationName of a ' + kind + ' is the wrong interface')
        if kind != 'CSSTransition':
            n.expect(n.call('rv_dom_css_transition_get_transition_property', [P, P, I, ctypes.POINTER(I)], animation, None, 0, ctypes.byref(I())) == WRONG_INTERFACE,
                     'transitionProperty of a ' + kind + ' is the wrong interface')
        if target:
            n.bind('rv_node_release', None, [P])(target)
        if effect:
            n.bind('rv_dom_animation_effect_release', None, [P])(effect)
        if timeline:
            n.bind('rv_dom_animation_timeline_release', None, [P])(timeline)
        return out

    def release(self, handles):
        for handle in handles:
            self.n.bind('rv_event_target_release', None, [P])(handle)

    def steps(self):
        n, nodes, arena = self.n, self.nodes, Arena()
        steps = []
        record = lambda name, value: steps.append({'name': name, 'value': value})
        buffer = ctypes.create_string_buffer(64)
        n.ok('rv_element_computed_style', [P, ctypes.c_char_p, P, I, ctypes.POINTER(I)], nodes['tr'], b'opacity', buffer, 64, ctypes.byref(I()))
        n.ok('rv_element_set_style', [P, ctypes.c_char_p, ctypes.c_char_p, I, I], nodes['tr'], b'opacity', b'0.2', len(b'0.2'), 0)  # utf8
        animate = lambda element, frames, ident: self._animate(element, frames, ident, arena)
        scripted = animate(nodes['c1'], [{'props': {'opacity': '0'}}, {'props': {'opacity': '1'}}], 'scripted')
        second = animate(nodes['css'], [{'props': {'transform': 'translateX(0px)'}}, {'props': {'transform': 'translateX(10px)'}}], 'second')
        everything = self.listed('document', self.document)
        record('document', [self.describe(a) for a in everything])
        for label, target, subtree in [('tree', 'tree', False), ('tree subtree', 'tree', True), ('css element', 'css', False), ('transition element', 'tr', False)]:
            found = self.listed('element', nodes[target], subtree)
            record(label, [self.describe(a) for a in found])
            self.release(found)
        again = self.listed('document', self.document)
        c2 = self.listed('element', nodes['c2'])
        subtree = self.listed('element', nodes['tree'], True)
        effects = [n.handle('rv_dom_web_animation_get_effect', [P], a) for a in everything]
        record('identity', {'documentAgain': again == everything, 'elementInDocument': c2[0] in everything,
                            'scriptedInDocument': scripted in everything, 'subtreeInDocument': all(a in everything for a in subtree),
                            'effectsDistinct': len(set(effects)) == len(effects)})
        for effect in effects:
            n.bind('rv_dom_animation_effect_release', None, [P])(effect)
        self.release(again + c2 + subtree)
        # The hand-written CSS-animation handle is the same animation as the generated one.
        count = I()
        # A zero capacity reports the count (RV_ERR_BUFFER_TOO_SMALL while animations exist).
        n.call('rv_element_animations', [P, I, P, I, ctypes.POINTER(I)], nodes['css'], 0, None, 0, ctypes.byref(count))
        legacy = (P * max(count.value, 1))()
        n.ok('rv_element_animations', [P, I, P, I, ctypes.POINTER(I)], nodes['css'], 0, legacy, count.value, ctypes.byref(count))
        bridged = [n.bind('rv_animation_as_event_target', P, [P])(legacy[i]) for i in range(count.value)]
        equals = n.bind('rv_event_target_equals', I, [P, P])
        n.expect(count.value == 2 and all(any(equals(b, a) == 1 for a in everything) for b in bridged),
                 'rv_animation_as_event_target equals the listed animation')
        n.expect(n.bind('rv_animation_as_event_target', P, [P])(None) is None, 'the bridge of NULL is NULL')
        self.release(bridged)
        for handle in legacy[:count.value]:
            n.bind('rv_animation_release', None, [P])(handle)
        fade = next(a for a in everything if n.text('rv_dom_web_animation_get_interface_name', [P], a) == 'CSSAnimation'
                    and n.text('rv_dom_css_animation_get_animation_name', [P], a) == 'fade')
        n.ok('rv_dom_web_animation_cancel', [P], fade)
        remaining = self.listed('element', nodes['css'])
        record('css cancelled', {'playState': ['idle', 'running', 'paused', 'finished'][n.integer('rv_dom_web_animation_get_play_state', fade)],
                                 'remaining': [self.describe(a) for a in remaining]})
        self.release(remaining)
        n.ok('rv_dom_web_animation_cancel', [P], scripted)
        tree = self.listed('element', nodes['tree'], True)
        documents = self.listed('document', self.document)
        record('scripted cancelled', {'playState': ['idle', 'running', 'paused', 'finished'][n.integer('rv_dom_web_animation_get_play_state', scripted)],
                                      'tree': [self.describe(a) for a in tree], 'document': len(documents)})
        self.release(tree + documents)
        transition = self.listed('element', nodes['tr'])
        n.ok('rv_dom_web_animation_cancel', [P], transition[0])
        self.release(transition)
        n.ok('rv_dom_web_animation_cancel', [P], second)
        last = self.listed('document', self.document)
        record('after all cancelled', [self.describe(a) for a in last])
        self.release(last + everything + [scripted, second])
        self.contract()
        return steps

    def _animate(self, element, frames, ident, arena):
        animation = P()
        self.n.ok('rv_dom_element_animate', [P, P, P, ctypes.POINTER(P)], element, arena.keyframes(frames),
                  arena.options(AnimationOptions, KeyframeAnimationOptions, {'duration': 100000, 'id': ident}), ctypes.byref(animation))
        return animation.value

    def contract(self):
        n = self.n
        other = n.bind('rv_host_create_event_target', P, [P])(self.host)
        n.expect(n.call('rv_dom_web_animation_get_interface_name', [P, P, I, ctypes.POINTER(I)], other, None, 0, ctypes.byref(I())) == WRONG_INTERFACE,
                 'interface name of a plain event target is the wrong interface')
        n.expect(n.call('rv_dom_web_animation_get_interface_name', [P, P, I, ctypes.POINTER(I)], None, None, 0, ctypes.byref(I())) == NULL_ARGUMENT,
                 'interface name of NULL')
        n.bind('rv_event_target_release', None, [P])(other)
        n.expect(n.call('rv_dom_document_get_animations', [P, ctypes.c_void_p], self.document, None) == NULL_ARGUMENT, 'getAnimations NULL result')
        empty = Animations()
        n.bind('rv_dom_sequence_web_animation_release', None, [P])(ctypes.byref(empty))
        n.expect(True, 'releasing an empty list')

    def close(self):
        for node in self.nodes.values():
            self.n.bind('rv_node_release', None, [P])(node)
        self.n.bind('rv_dom_animation_timeline_release', None, [P])(self.timeline)
        self.n.bind('rv_node_release', None, [P])(self.document)
        self.n.bind('rv_host_destroy', None, [P])(self.host)


def verify(directory):
    oracle = json.loads((FIXTURES / 'web-animation-discovery-oracle.json').read_text(encoding='utf-8'))
    native = Native(directory)
    native.expect(native.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
    for capability in [b'dom:CSSAnimation', b'dom:CSSTransition', b'dom-type-query:WebAnimation']:
        native.expect(native.bind('rv_abi_has', I, [ctypes.c_char_p])(capability) == 1, 'rv_abi_has ' + capability.decode())
    discovery = Discovery(native)
    try:
        steps = discovery.steps()
    finally:
        discovery.close()
    failures = []
    native.expect([s['name'] for s in steps] == [s['name'] for s in oracle['steps']], 'step names match the oracle')
    for actual, wanted in zip(steps, oracle['steps']):
        native.assertions += 1
        if actual['value'] != wanted['value']:
            failures.append({'step': actual['name'], 'native': actual['value'], 'chromium': wanted['value']})
    return native, steps, failures, oracle['browser']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence')
    args = parser.parse_args()
    native, steps, failures, browser = verify(args.native_directory)
    if args.evidence:
        Path(args.evidence).write_text(json.dumps({'oracle': browser, 'assertions': native.assertions, 'failures': failures, 'steps': steps},
                                                  indent=1) + '\n', encoding='utf-8')
    for failure in failures:
        print('MISMATCH', json.dumps(failure))
    if failures:
        raise SystemExit(f'{len(failures)} steps differ from {browser}')
    print(f'PASS web animation discovery: {native.assertions} assertions against {browser}')


if __name__ == '__main__':
    main()
