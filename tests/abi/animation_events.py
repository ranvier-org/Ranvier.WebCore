"""Replays tests/fixtures/animation-events-cases.json and compares the engine's animation and transition events with the
Chromium oracle tests/fixtures/animation-events-oracle.json: each CSS animation or transition case records, at a document
listener, every event of the element in dispatch order with its interface (rv_dom_event_get_interface_name), target,
animationName or propertyName, elapsedTime and pseudoElement, read through the generated CSSAnimationEvent and
CSSTransitionEvent getters; the playback cases record the finish and cancel AnimationPlaybackEvents of Element.animate
animations with their currentTime and timelineTime. A generic capture listener and a bubbling listener at the document
both see an animationstart, in the capturing and bubbling phases, and neither does after removal.

Events dispatch inside rv_host_update; a cancel the oracle makes on the next animation frame is made after the update
that dispatched the triggering event. Waits use a hang guard that raises; no count depends on frame timing."""

import argparse
import ctypes
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, P, I, OK  # noqa: E402
import web_animations as wa  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
LISTENER = ctypes.CFUNCTYPE(I, P, P)
CAPTURE = 1
HANG_SECONDS = 5.0


class Probe:
    def __init__(self, native, markup):
        self.n = native
        self.page = wa.Page(native, markup)
        self.keep = []

    def text(self, name, event):
        buffer, length = ctypes.create_string_buffer(256), I()
        self.n.ok(name, [P, P, I, ctypes.POINTER(I)], event, buffer, 256, ctypes.byref(length))
        return buffer.raw[:length.value].decode('utf-8')

    def number(self, name, event):
        value = ctypes.c_double()
        self.n.ok(name, [P, ctypes.POINTER(ctypes.c_double)], event, ctypes.byref(value))
        return value.value

    def target_id(self, event):
        target = self.n.bind('rv_event_target', P, [P, I])(event, 0)
        self.n.expect(bool(target), 'event target')
        identifier = self.n.text('rv_dom_element_get_id', [P], target)
        self.n.bind('rv_node_release', None, [P])(target)
        return identifier

    def listen(self, node, event_type, callback, flags=0, target=False):
        function = LISTENER(callback)
        self.keep.append(function)
        if target:
            listener = self.n.bind('rv_event_target_add_listener', P, [P, ctypes.c_char_p, I, LISTENER, P])(node, event_type.encode(), flags, function, None)
        else:
            listener = self.n.bind('rv_node_add_event_listener', P, [P, ctypes.c_char_p, I, LISTENER, P])(node, event_type.encode(), flags, function, None)
        self.n.expect(bool(listener), 'listener ' + event_type)
        return listener

    def remove(self, listeners):
        for listener in listeners:
            self.n.call('rv_listener_remove', [P], listener)

    def frame(self):
        self.n.call('rv_run_loop_cycle', [I], 0)
        self.n.call('rv_host_update', [P], self.page.host)

    def until(self, condition, label, after=None):
        deadline = time.perf_counter() + HANG_SECONDS
        while not condition():
            if time.perf_counter() > deadline:
                raise AssertionError('hang guard: ' + label)
            self.frame()
            if after:
                after()
            time.sleep(0.002)

    def settle(self, rounds=6):
        for _ in range(rounds):
            self.frame()
            time.sleep(0.004)

    def set_class(self, element, value):
        self.n.ok('rv_element_set_attribute', [P, ctypes.c_char_p, ctypes.c_char_p], self.page.element(element), b'class', value.encode())


def rounded(value):
    value = round(value * 1e6) / 1e6
    return int(value) if float(value).is_integer() else value


def css_case(probe, case, types):
    n = probe.n
    events, pending = [], []

    def record(context, event):
        if probe.target_id(event) != case['el']:
            return 0
        interface = probe.text('rv_dom_event_get_interface_name', event)
        event_type = probe.text('rv_event_type', event)
        prefix = 'rv_dom_css_animation_event_get_' if interface == 'AnimationEvent' else 'rv_dom_css_transition_event_get_'
        elapsed = probe.number(prefix + 'elapsed_time', event)
        n.expect(elapsed >= 0, case['name'] + ': elapsedTime is not negative')
        events.append({'type': event_type, 'interface': interface, 'target': case['el'],
                       'name': probe.text(prefix + ('animation_name' if interface == 'AnimationEvent' else 'property_name'), event),
                       'elapsedTime': 'number' if event_type.endswith('cancel') else rounded(elapsed),
                       'pseudoElement': probe.text(prefix + 'pseudo_element', event)})
        trigger = case.get('after') or events[0]['type']
        if case.get('cancel') and event_type == trigger and [e['type'] for e in events].count(event_type) == 1:
            pending.append(case['cancel'])
        return 0

    listeners = [probe.listen(probe.page.document, event_type, record) for event_type in types]
    probe.settle(2)
    probe.set_class(case['el'], case['className'])

    def cancel_after_update():
        while pending:
            probe.set_class(case['el'], pending.pop())
    probe.until(lambda: any(e['type'] == case['last'] for e in events), case['name'], cancel_after_update)
    probe.settle()
    probe.remove(listeners)
    return events


def playback_case(probe, case):
    n = probe.n
    events = []
    animation = None
    arena = wa.Arena()
    result = P()
    n.ok('rv_dom_element_animate', [P, P, P, ctypes.POINTER(P)], probe.page.element(case['el']),
         arena.keyframes([{'props': {'opacity': '0'}}, {'props': {'opacity': '1'}}]),
         arena.options(wa.AnimationOptions, wa.KeyframeAnimationOptions, float(case['duration'])), ctypes.byref(result))
    animation = result.value

    def record(context, event):
        times = []
        for member in ('current_time', 'timeline_time'):
            value = wa.Time()
            n.ok('rv_dom_animation_playback_event_get_' + member, [P, ctypes.POINTER(wa.Time)], event, ctypes.byref(value))
            times.append(value.arm0 if value.present else None)
        current, timeline = times
        events.append({'type': probe.text('rv_event_type', event), 'interface': probe.text('rv_dom_event_get_interface_name', event),
                       'currentTime': None if current is None else rounded(current), 'timelineTime': None if timeline is None else 'number',
                       'timelineAfterCurrent': timeline >= current if timeline is not None and current is not None else None})
        return 0

    listeners = [probe.listen(animation, event_type, record, target=True) for event_type in ('finish', 'cancel', 'remove')]
    probe.until(lambda: not probe.n.integer('rv_dom_web_animation_get_pending', animation), case['name'] + ': ready')
    if case.get('cancel'):
        n.ok('rv_dom_web_animation_cancel', [P], animation)
    probe.until(lambda: any(e['type'] == case['last'] for e in events), case['name'])
    probe.settle()
    probe.remove(listeners)
    n.ok('rv_dom_web_animation_cancel', [P], animation)
    n.bind('rv_event_target_release', None, [P])(animation)
    return events


def generic(probe):
    seen = []
    element = probe.page.element('css')
    probe.set_class('css', '')
    probe.settle(2)

    def capture(context, event):
        seen.append('capture:' + probe.text('rv_event_type', event) + ':' + str(probe.n.call('rv_event_phase', [P], event)))
        return 0

    def bubble(context, event):
        if probe.target_id(event) == 'css':
            seen.append('bubble:' + probe.text('rv_event_type', event) + ':' + str(probe.n.call('rv_event_phase', [P], event)))
        return 0
    listeners = [probe.listen(probe.page.document, 'animationstart', capture, CAPTURE), probe.listen(probe.page.document, 'animationstart', bubble)]
    probe.set_class('css', 'on')
    probe.until(lambda: len(seen) >= 2, 'generic')
    probe.remove(listeners)
    probe.set_class('css', '')
    probe.settle(2)
    probe.set_class('css', 'on')
    probe.settle(8)
    return seen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--out')
    arguments = parser.parse_args()
    spec = json.loads((FIXTURES / 'animation-events-cases.json').read_text(encoding='utf-8'))
    oracle = json.loads((FIXTURES / 'animation-events-oracle.json').read_text(encoding='utf-8'))
    native = Native(arguments.native_directory)
    probe = Probe(native, spec['markup'])
    probe.settle(2)
    got = {'cases': {}, 'playback': {}}
    for case in spec['cases']:
        got['cases'][case['name']] = events = css_case(probe, case, spec['types'])
        wanted = oracle['cases'][case['name']]
        native.expect(events == wanted, case['name'] + ': ' + json.dumps(events) + ' != ' + json.dumps(wanted))
    for case in spec['playback']:
        got['playback'][case['name']] = events = playback_case(probe, case)
        wanted = oracle['playback'][case['name']]
        native.expect(events == wanted, case['name'] + ': ' + json.dumps(events) + ' != ' + json.dumps(wanted))
    got['generic'] = generic(probe)
    native.expect(got['generic'] == oracle['generic'], 'generic listeners: ' + json.dumps(got['generic']) + ' != ' + json.dumps(oracle['generic']))
    probe.page.close()
    if arguments.out:
        Path(arguments.out).write_text(json.dumps(got, indent=1) + '\n', encoding='utf-8')
    print(f'PASS animation events: {native.assertions} assertions against {oracle["browser"]}')


if __name__ == '__main__':
    main()
