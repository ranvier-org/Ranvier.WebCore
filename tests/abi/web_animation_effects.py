"""Replays the A02 effect inspection and mutation steps of tests/abi/web_animation_effects_browser.mjs through the
generated functions (getTiming, getComputedTiming, updateTiming, getKeyframes, setKeyframes, target, pseudoElement,
composite and iterationComposite) and compares each step with the Chromium oracle
tests/fixtures/web-animation-effects-oracle.json. Numbers compare within 1e-3, and matrix entries within 1e-3, since
the easing curves of the engines round differently. It also checks the owned results' releases, the context and
host errors of updateTiming and setKeyframes, and the null, thread and interface errors."""

import argparse
import ctypes
import json
import math
from pathlib import Path
import re
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, P, I, U, OK, NULL_ARGUMENT, WRONG_THREAD, DOM_EXCEPTION, WRONG_INTERFACE, ABI  # noqa: E402
from web_animations import (Arena, StringInput, Span, KeyframeProperties, AnimationOptions, KeyframeAnimationOptions, Time,  # noqa: E402
                            exception_name, FILL, DIRECTION, COMPOSITES, ITERATION_COMPOSITES, D)

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
WRONG_HOST = -12
FILLS = {v: k for k, v in FILL.items()}
DIRECTIONS = {v: k for k, v in DIRECTION.items()}
TOLERANCE = 1e-3
# The oracle page of web_animation_effects_browser.mjs.
PAGE = ('<!doctype html><html><head><style>html,body{margin:0;background:white}'
        '.box{position:absolute;width:40px;height:40px;background:rgb(0,0,255)}#a{left:0;top:0}#b{left:50px;top:0}'
        "#b::before{content:'';display:block;width:10px;height:10px;background:red}</style></head>"
        '<body><div id=a class=box></div><div id=b class=box></div></body></html>')


class Duration(ctypes.Structure):
    _fields_ = [('present', I), ('tag', I), ('arm0', D), ('arm1', P), ('arm2', Span)]


class Numberish(ctypes.Structure):
    _fields_ = [('present', I), ('tag', I), ('arm0', D), ('arm1', P)]


TIMING = [('size', U), ('delay', D), ('end_delay', D), ('fill', I), ('iteration_start', D), ('iterations', D),
          ('duration', ctypes.POINTER(Duration)), ('direction', I), ('easing', StringInput)]


class EffectTiming(ctypes.Structure):
    _fields_ = TIMING


class ComputedEffectTiming(ctypes.Structure):
    _fields_ = TIMING + [('end_time', ctypes.POINTER(Numberish)), ('active_duration', ctypes.POINTER(Numberish)),
                         ('local_time', ctypes.POINTER(Numberish)), ('progress', ctypes.POINTER(D)), ('current_iteration', ctypes.POINTER(D))]


class StringOrDouble(ctypes.Structure):
    _fields_ = [('present', I), ('tag', I), ('arm0', D), ('arm1', Span)]


class OptionalEffectTiming(ctypes.Structure):
    _fields_ = [('size', U), ('delay', ctypes.POINTER(D)), ('end_delay', ctypes.POINTER(D)), ('fill', ctypes.POINTER(I)),
                ('iteration_start', ctypes.POINTER(D)), ('iterations', ctypes.POINTER(D)), ('duration', ctypes.POINTER(StringOrDouble)),
                ('direction', ctypes.POINTER(I)), ('easing', StringInput)]


class KeyframeProperty(ctypes.Structure):
    _fields_ = [('size', U), ('name', StringInput), ('value', StringInput)]


class ComputedKeyframe(ctypes.Structure):
    _fields_ = [('size', U), ('offset', ctypes.POINTER(D)), ('computed_offset', D), ('easing', StringInput),
                ('composite', StringInput), ('properties', ctypes.POINTER(KeyframeProperties))]


class ComputedKeyframes(ctypes.Structure):
    _fields_ = [('present', I), ('count', I), ('items', ctypes.POINTER(ctypes.POINTER(ComputedKeyframe)))]


def text(value):
    return ctypes.string_at(value.data, value.length).decode('utf-8') if value.present else None


def span_text(value):
    return ctypes.string_at(value.data, value.length).decode('utf-8') if value.length >= 0 else None


def numberish(pointer):
    if not pointer or not pointer.contents.present:
        return None
    value = pointer.contents
    assert value.tag == 1, 'CSSNumberish is a number'
    return value.arm0


def duration(pointer):
    value = pointer.contents
    return value.arm0 if value.tag == 1 else span_text(value.arm2)


class Effects:
    def __init__(self, native, directory):
        self.n = native
        self.host = native.bind('rv_host_create', P, [I, I])(320, 240)
        native.ok('rv_host_load_html', [P, ctypes.c_char_p, I], self.host, PAGE.encode('utf-8'), len(PAGE.encode('utf-8')))  # utf8
        self.document = native.bind('rv_host_document', P, [P])(self.host)
        by_id_utf8 = native.bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p, I])
        by_id = lambda host, element_id: by_id_utf8(host, element_id, len(element_id))
        self.a, self.b = by_id(self.host, b'a'), by_id(self.host, b'b')

    def timing(self, effect, computed=False):
        result = ctypes.POINTER(ComputedEffectTiming if computed else EffectTiming)()
        name = 'rv_dom_animation_effect_get_computed_timing' if computed else 'rv_dom_animation_effect_get_timing'
        self.n.ok(name, [P, ctypes.c_void_p], effect, ctypes.byref(result))
        value = result.contents
        self.n.expect(value.size == ctypes.sizeof(type(value)), name + ': size is the struct size')
        out = {'delay': value.delay, 'endDelay': value.end_delay, 'fill': FILLS[value.fill], 'iterationStart': value.iteration_start,
               'iterations': value.iterations, 'duration': duration(value.duration), 'direction': DIRECTIONS[value.direction],
               'easing': text(value.easing)}
        if computed:
            out.update(endTime=numberish(value.end_time), activeDuration=numberish(value.active_duration),
                       localTime=numberish(value.local_time), progress=value.progress.contents.value if value.progress else None,
                       currentIteration=value.current_iteration.contents.value if value.current_iteration else None)
            self.n.bind('rv_dom_computed_effect_timing_release', None, [P])(ctypes.cast(result, P))
        else:
            self.n.bind('rv_dom_effect_timing_release', None, [P])(ctypes.cast(result, P))
        return out

    def keyframes(self, effect):
        result = ComputedKeyframes()
        self.n.ok('rv_dom_keyframe_effect_get_keyframes', [P, ctypes.c_void_p], effect, ctypes.byref(result))
        frames = []
        for index in range(result.count):
            frame = result.items[index].contents
            properties = frame.properties.contents
            pairs = []
            for j in range(properties.count):
                item = ctypes.cast(properties.items[j], ctypes.POINTER(KeyframeProperty)).contents
                pairs.append([text(item.name), text(item.value)])
            frames.append({'offset': frame.offset.contents.value if frame.offset else None, 'computedOffset': frame.computed_offset,
                           'easing': text(frame.easing), 'composite': text(frame.composite), 'properties': sorted(pairs)})
        self.n.bind('rv_dom_sequence_computed_keyframe_release', None, [P])(ctypes.byref(result))
        return frames

    def update(self, effect, context=None, **fields):
        arena, value = Arena(), OptionalEffectTiming()
        value.size = ctypes.sizeof(OptionalEffectTiming)
        for name, key in [('delay', 'delay'), ('endDelay', 'end_delay'), ('iterationStart', 'iteration_start'), ('iterations', 'iterations')]:
            if name in fields:
                setattr(value, key, ctypes.pointer(arena.keep(D(fields[name]))))
        if 'fill' in fields:
            value.fill = ctypes.pointer(arena.keep(I(FILL[fields['fill']])))
        if 'direction' in fields:
            value.direction = ctypes.pointer(arena.keep(I(DIRECTION[fields['direction']])))
        if 'duration' in fields:
            item = fields['duration']
            if isinstance(item, str):
                data = arena.keep(ctypes.create_string_buffer(item.encode()))
                union = StringOrDouble(1, 2, 0.0, Span(ctypes.cast(data, P), len(item.encode())))
            else:
                union = StringOrDouble(1, 1, float(item), Span(None, 0))
            value.duration = ctypes.pointer(arena.keep(union))
        value.easing = arena.string(fields.get('easing'))
        return self.n.call('rv_dom_animation_effect_update_timing', [P, P, P], effect, context or self.document, ctypes.byref(value))

    def set_keyframes(self, effect, frames, context=None):
        arena = Arena()
        return self.n.call('rv_dom_keyframe_effect_set_keyframes', [P, P, P], effect, context or self.document, arena.keyframes(frames))

    def computed(self, element, prop):
        buffer, length = ctypes.create_string_buffer(512), I()
        self.n.ok('rv_element_computed_style', [P, ctypes.c_char_p, P, I, ctypes.POINTER(I)], element, prop.encode(), buffer, 512, ctypes.byref(length))
        return buffer.raw[:length.value].decode('utf-8')

    def target_id(self, effect):
        target = self.n.handle('rv_dom_keyframe_effect_get_target', [P], effect)
        if not target:
            return None
        value = self.n.text('rv_dom_element_get_id', [P], target)
        self.n.bind('rv_node_release', None, [P])(target)
        return value

    def status(self, status):
        return 'ok' if status == OK else exception_name(self.n) if status == DOM_EXCEPTION else 'status ' + str(status)

    def steps(self):
        n, arena = self.n, Arena()
        steps = []
        record = lambda name, value: steps.append({'name': name, 'value': value})
        frames = [{'props': {'opacity': '0'}}, {'props': {'opacity': '1'}, 'offset': 0.5, 'easing': 'ease-in'}, {'props': {'opacity': '0.5'}}]
        options = arena.options(AnimationOptions, KeyframeAnimationOptions, {'duration': 1000, 'delay': 100, 'endDelay': 50, 'iterations': 2,
                                'direction': 'alternate', 'fill': 'both', 'easing': 'linear', 'iterationStart': 0.25})
        animation = P()
        n.ok('rv_dom_element_animate', [P, P, P, ctypes.POINTER(P)], self.a, arena.keyframes(frames), options, ctypes.byref(animation))
        animation = animation.value
        n.ok('rv_dom_web_animation_pause', [P], animation)
        effect = n.handle('rv_dom_web_animation_get_effect', [P], animation, nullable=False)
        seek = lambda t: n.ok('rv_dom_web_animation_set_current_time', [P, ctypes.POINTER(Time)], animation, ctypes.byref(Time(1, 1, float(t), None)))
        record('timing', self.timing(effect))
        seek(600)
        record('computed at 600', self.timing(effect, True))
        record('keyframes', self.keyframes(effect))
        n.expect(self.update(effect, duration=2000, delay=0, iterations=1, direction='normal', iterationStart=0) == OK, 'updateTiming')
        record('timing after update', self.timing(effect))
        seek(500)
        record('computed after update', self.timing(effect, True))
        record('opacity after update', self.computed(self.a, 'opacity'))
        n.expect(self.update(effect, duration='auto') == OK, 'updateTiming auto')
        record('auto duration', self.timing(effect))
        n.expect(self.update(effect, duration=2000, easing='ease-out', fill='forwards', endDelay=0) == OK, 'updateTiming second')
        record('timing after second update', self.timing(effect))
        n.expect(self.set_keyframes(effect, [{'props': {'transform': 'translateX(0px)'}},
                                             {'props': {'transform': 'translateX(100px)'}, 'composite': 'add'}]) == OK, 'setKeyframes')
        record('keyframes after set', self.keyframes(effect))
        record('style after set', [self.computed(self.a, 'opacity'), self.computed(self.a, 'transform')])
        n.ok('rv_dom_keyframe_effect_set_target', [P, P], effect, self.b)
        record('retarget', {'target': self.target_id(effect), 'a': self.computed(self.a, 'transform'), 'b': self.computed(self.b, 'transform')})
        n.ok('rv_dom_keyframe_effect_set_pseudo_element', [P, P, I], effect, b'::before', 8)
        record('pseudo', {'pseudoElement': n.text('rv_dom_keyframe_effect_get_pseudo_element', [P], effect), 'target': self.target_id(effect)})
        n.ok('rv_dom_keyframe_effect_set_pseudo_element', [P, P, I], effect, None, -1)
        n.ok('rv_dom_keyframe_effect_set_composite', [P, I], effect, COMPOSITES.index('add'))
        n.ok('rv_dom_keyframe_effect_set_iteration_composite', [P, I], effect, ITERATION_COMPOSITES.index('accumulate'))
        record('composites', [COMPOSITES[n.integer('rv_dom_keyframe_effect_get_composite', effect)],
                              ITERATION_COMPOSITES[n.integer('rv_dom_keyframe_effect_get_iteration_composite', effect)]])
        n.ok('rv_dom_keyframe_effect_set_composite', [P, I], effect, 0)
        n.ok('rv_dom_keyframe_effect_set_iteration_composite', [P, I], effect, 0)
        bogus = ctypes.create_string_buffer(b'bogus')
        record('invalid', {
            'updateTiming negative duration': self.status(self.update(effect, duration=-1)),
            'updateTiming bad duration string': self.status(self.update(effect, duration='bogus')),
            'updateTiming bad easing': self.status(self.update(effect, easing='bogus')),
            'updateTiming negative iterations': self.status(self.update(effect, iterations=-1)),
            'updateTiming NaN iterations': self.status(self.update(effect, iterations=float('nan'))),
            'updateTiming negative iterationStart': self.status(self.update(effect, iterationStart=-1)),
            'setKeyframes unsorted': self.status(self.set_keyframes(effect, [{'props': {'opacity': '1'}, 'offset': 1}, {'props': {'opacity': '0'}, 'offset': 0}])),
            'setKeyframes bad easing': self.status(self.set_keyframes(effect, [{'props': {'opacity': '1'}, 'easing': 'bogus'}])),
            'pseudoElement bogus': self.status(n.call('rv_dom_keyframe_effect_set_pseudo_element', [P, P, I], effect, bogus, 5)),
        })
        n.ok('rv_dom_keyframe_effect_set_pseudo_element', [P, P, I], effect, None, -1)
        record('timing after invalid', self.timing(effect))
        record('keyframes after invalid', self.keyframes(effect))
        n.ok('rv_node_remove', [P], self.b)
        connected = n.integer('rv_dom_node_get_is_connected', self.b)
        record('removed target', {'target': self.target_id(effect), 'connected': bool(connected), 'progress': self.timing(effect, True)['progress']})
        n.ok('rv_dom_keyframe_effect_set_target', [P, P], effect, None)
        record('null target', {'target': self.target_id(effect), 'progress': self.timing(effect, True)['progress'], 'keyframes': len(self.keyframes(effect))})
        n.ok('rv_dom_web_animation_cancel', [P], animation)
        record('cancelled', self.timing(effect, True))
        self.contract(effect)
        n.bind('rv_dom_animation_effect_release', None, [P])(effect)
        n.bind('rv_event_target_release', None, [P])(animation)
        return steps

    def contract(self, effect):
        """The context, host, null, thread and interface errors of the effect members."""
        n = self.n
        other = n.bind('rv_host_create', P, [I, I])(64, 64)
        n.ok('rv_host_load_html', [P, ctypes.c_char_p, I], other, b'<p>other</p>', len(b'<p>other</p>'))  # utf8
        foreign = n.bind('rv_host_document', P, [P])(other)
        n.expect(self.update(effect, foreign, delay=1) == WRONG_HOST, 'updateTiming with another document is the wrong host')
        n.expect(self.set_keyframes(effect, [], foreign) == WRONG_HOST, 'setKeyframes with another document is the wrong host')
        n.expect(self.update(effect, self.a, delay=1) == WRONG_INTERFACE, 'updateTiming with an element context')
        n.expect(self.timing(effect)['delay'] == 0, 'rejected updates leave the timing')
        n.bind('rv_node_release', None, [P])(foreign)
        n.bind('rv_host_destroy', None, [P])(other)
        result = P()
        n.expect(n.call('rv_dom_animation_effect_get_timing', [P, ctypes.c_void_p], None, ctypes.byref(result)) == NULL_ARGUMENT, 'getTiming NULL target')
        n.expect(n.call('rv_dom_animation_effect_get_timing', [P, ctypes.c_void_p], effect, None) == NULL_ARGUMENT, 'getTiming NULL result')
        n.expect(n.call('rv_dom_keyframe_effect_get_keyframes', [P, ctypes.c_void_p], effect, None) == NULL_ARGUMENT, 'getKeyframes NULL result')
        n.expect(n.call('rv_dom_animation_effect_update_timing', [P, P, P], effect, None, None) == NULL_ARGUMENT, 'updateTiming NULL context')
        n.expect(n.call('rv_dom_animation_effect_update_timing', [P, P, P], effect, self.document, None) == OK, 'updateTiming NULL timing is {}')
        status = []
        worker = threading.Thread(target=lambda: status.append(n.call('rv_dom_animation_effect_get_timing', [P, ctypes.c_void_p], effect, ctypes.byref(result))))
        worker.start(); worker.join()
        n.expect(status == [WRONG_THREAD], 'getTiming off the owning thread')
        n.bind('rv_dom_effect_timing_release', None, [P])(None)
        n.bind('rv_dom_computed_effect_timing_release', None, [P])(None)
        empty = ComputedKeyframes()
        n.bind('rv_dom_sequence_computed_keyframe_release', None, [P])(ctypes.byref(empty))
        n.expect(True, 'releases accept NULL and an empty sequence')

    def close(self):
        for node in (self.a, self.b, self.document):
            self.n.bind('rv_node_release', None, [P])(node)
        self.n.bind('rv_host_destroy', None, [P])(self.host)


def same(actual, wanted):
    if isinstance(wanted, float) or isinstance(actual, float):
        if isinstance(actual, (int, float)) and isinstance(wanted, (int, float)):
            return (math.isnan(actual) and math.isnan(wanted)) or abs(actual - wanted) <= TOLERANCE
        return False
    if isinstance(wanted, str) and isinstance(actual, str) and wanted.startswith('matrix('):
        a, b = [list(map(float, re.findall(r'-?[\d.]+(?:e-?\d+)?', v))) for v in (actual, wanted)]
        return len(a) == len(b) and all(abs(x - y) <= TOLERANCE for x, y in zip(a, b))
    if isinstance(wanted, dict):
        return isinstance(actual, dict) and actual.keys() == wanted.keys() and all(same(actual[k], wanted[k]) for k in wanted)
    if isinstance(wanted, list):
        return isinstance(actual, list) and len(actual) == len(wanted) and all(same(x, y) for x, y in zip(actual, wanted))
    return actual == wanted


def verify(directory):
    oracle = json.loads((FIXTURES / 'web-animation-effects-oracle.json').read_text(encoding='utf-8'))
    native = Native(directory)
    native.expect(native.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
    effects = Effects(native, directory)
    failures = []
    try:
        steps = effects.steps()
    finally:
        effects.close()
    native.expect([s['name'] for s in steps] == [s['name'] for s in oracle['steps']], 'step names match the oracle')
    for actual, wanted in zip(steps, oracle['steps']):
        native.assertions += 1
        if not same(actual['value'], wanted['value']):
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
    print(f'PASS web animation effects: {native.assertions} assertions against {browser}')


if __name__ == '__main__':
    main()
