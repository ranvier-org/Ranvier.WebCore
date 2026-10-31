"""G01/G15 media query probe against an actual runtime directory. Replays tests/fixtures/media-queries.json through
rv_host_resize, rv_host_set_device_scale and rv_host_set_media_preferences: every MediaQueryList reports the step's
matches, each list whose matches changed fires one change event in creation order, and style sees the supplied state.
The Chromium oracle tests/fixtures/media-queries-oracle.json agrees with every step it can emulate. Then checks the
readback, capability facts, text scale, an owned subscription removed before a change, errors, threads, document
replacement and lists held past rv_host_destroy. --repeat runs the whole probe that many times in one process."""

import argparse
import ctypes
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8

OK, NULL_ARGUMENT, WRONG_THREAD, UNSUPPORTED = 0, -1, -2, -9
ABI = 55
FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p)
VALUES = {
    'colorScheme': {'light': 1, 'dark': 2},
    'reducedMotion': {'no-preference': 1, 'reduce': 2},
    'contrast': {'no-preference': 1, 'more': 2},
    'pointer': {'none': 1, 'coarse': 2, 'fine': 3},
    'anyPointer': {'none': 1, 'coarse': 2, 'fine': 3, 'coarse and fine': 4},
    'hover': {'none': 1, 'hover': 2},
    'anyHover': {'none': 1, 'hover': 2},
}
FIELDS = [('colorScheme', 'color_scheme'), ('reducedMotion', 'reduced_motion'), ('contrast', 'contrast'), ('pointer', 'pointer'),
          ('hover', 'hover'), ('anyPointer', 'any_pointer'), ('anyHover', 'any_hover')]
FACILITIES = {'media-color-scheme': ['color_scheme'], 'media-reduced-motion': ['reduced_motion'], 'media-contrast': ['contrast'],
              'media-pointer': ['pointer', 'any_pointer'], 'media-hover': ['hover', 'any_hover'], 'media-text-scale': ['text_scale']}
ABSENT = ['media-forced-colors', 'media-contrast-less', 'media-reduced-transparency', 'media-reduced-data']


class MediaPreferences(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32)] + [(name, ctypes.c_int32) for _, name in FIELDS] + [('text_scale', ctypes.c_float)]


def preferences_of(step, text_scale=0.0):
    value = MediaPreferences(size=ctypes.sizeof(MediaPreferences), text_scale=text_scale)
    for key, field in FIELDS:
        if key in step['preferences']:
            setattr(value, field, VALUES[key][step['preferences'][key]])
    return value


def fields(value):
    return tuple(getattr(value, name) for name, _ in MediaPreferences._fields_)


class Media:
    def __init__(self, p):
        P, I = p.pointer, p.integer
        self.p = p
        self.set = p.bind('rv_host_set_media_preferences', I, [P, ctypes.POINTER(MediaPreferences)])
        self.get = p.bind('rv_host_media_preferences', I, [P, ctypes.POINTER(MediaPreferences)])
        self.match_media = p.bind('rv_host_match_media', P, [P, ctypes.c_char_p])
        self.matches_of = p.bind('rv_media_query_matches', I, [P, ctypes.POINTER(I)])
        self.add_listener = p.bind('rv_event_target_add_listener', P, [P, Utf8, I, CALLBACK, P])
        self.remove_listener = p.bind('rv_listener_remove', I, [P])
        self.release = p.bind('rv_event_target_release', None, [P])
        self.equals = p.bind('rv_event_target_equals', I, [P, P])
        self.get_target = p.bind('rv_event_get_target', P, [P, I])
        self.cycle = p.bind('rv_run_loop_cycle', I, [I])
        self.fact_of = p.bind('rv_host_capability_fact', I, [P, I, ctypes.c_char_p, I, ctypes.POINTER(I)])
        self.style_of = p.bind('rv_element_computed_style', I, [P, ctypes.c_char_p, ctypes.c_char_p, I, ctypes.POINTER(I)])
        self.rect = p.bind('rv_element_rect', I, [P] + [ctypes.POINTER(ctypes.c_double)] * 4)
        self.callbacks = []

    def height(self, element):
        values = [ctypes.c_double() for _ in range(4)]
        self.p.expect(self.rect(element, *[ctypes.byref(v) for v in values]) == OK, 'element rect')
        return values[3].value

    def supply(self, value, label):
        self.p.expect(self.set(self.p.host, ctypes.byref(value)) == OK, label + ': supplied')

    def readback(self):
        value = MediaPreferences(size=ctypes.sizeof(MediaPreferences))
        self.p.expect(self.get(self.p.host, ctypes.byref(value)) == OK, 'readback')
        return value

    def matches(self, target):
        value = self.p.integer(-1)
        self.p.expect(self.matches_of(target, ctypes.byref(value)) == OK and value.value in (0, 1), 'MediaQueryList.matches')
        return value.value

    def listen(self, target, log, label):
        def run(context, event):
            current = self.get_target(event, 1)
            value = self.p.integer(-1)
            self.matches_of(current, ctypes.byref(value))
            log.append((label, value.value))
            self.release(current)
            return 0
        callback = CALLBACK(run)
        self.callbacks.append(callback)
        listener = self.add_listener(target, b'change', 0, callback, None)
        self.p.expect(bool(listener), 'change listener ' + str(label))
        return listener

    def settle(self):
        """Runs rendering updates until the media query evaluation has run; a hang guard counting no assertions."""
        for _ in range(3):
            self.p.bind('rv_host_update', self.p.integer, [self.p.pointer])(self.p.host)
            self.cycle(10)
        self.p.bind('rv_host_update', self.p.integer, [self.p.pointer])(self.p.host)

    def fact(self, name, dimension):
        value = self.p.integer(42)
        self.p.expect(self.fact_of(self.p.host, 4, name.encode(), dimension, ctypes.byref(value)) == OK, 'capability fact ' + name)
        return value.value

    def style(self, element, name):
        buffer, length = ctypes.create_string_buffer(256), self.p.integer()
        self.p.expect(self.style_of(element, name.encode(), buffer, len(buffer), ctypes.byref(length)) == OK, 'computed ' + name)
        return buffer.raw[:length.value].decode('utf-8')


def run_once(native_directory, fixture, oracle):
    with SvgProbe(native_directory, 320, 240) as p:
        P, I = p.pointer, p.integer
        m = Media(p)
        p.expect(p.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
        p.expect(p.bind('rv_abi_has', I, [ctypes.c_char_p])(b'media-preferences') == 1, 'rv_abi_has("media-preferences")')
        p.load(fixture['page'], standalone=False)
        m.settle()
        element = p.node('t')
        resize = p.bind('rv_host_resize', I, [P, I, I])
        scale = p.bind('rv_host_set_device_scale', I, [P, ctypes.c_float])

        # Capability facts: implemented, not supplied; preferences the engine has no input for are absent.
        for name in ['media-preferences'] + list(FACILITIES):
            p.expect(m.fact(name, 1) == 1 and m.fact(name, 2) == 0, name + ' implemented and not supplied')
        for name in ABSENT:
            p.expect(m.fact(name, 1) == 0, name + ' not implemented')
        p.expect(fields(m.readback()) == fields(MediaPreferences(size=ctypes.sizeof(MediaPreferences))), 'initial readback is the default')

        # Every step: matches, one change per changed list in creation order, style and the readback.
        lists, log = [], []
        for index, query in enumerate(fixture['queries']):
            target = m.match_media(p.host, query.encode())
            p.expect(bool(target), 'matchMedia ' + query)
            lists.append(target)
            m.listen(target, log, index)
        previous = None
        native_steps = []
        for step in fixture['steps']:
            name = step['name']
            p.expect(resize(p.host, *step['viewport']) == OK and scale(p.host, step['scale']) == OK, name + ': viewport')
            supplied = preferences_of(step)
            m.supply(supplied, name)
            m.settle()
            matching = [query for query, target in zip(fixture['queries'], lists) if m.matches(target)]
            p.expect(matching == [q for q in fixture['queries'] if q in step['matches']], name + ': matches ' + str(matching))
            changed = [i for i, q in enumerate(fixture['queries']) if previous is not None and (q in previous['matches']) != (q in step['matches'])]
            p.expect([label for label, _ in log] == changed, name + ': one change per changed list in creation order ' + str(log))
            p.expect(all(value == int(fixture['queries'][label] in step['matches']) for label, value in log), name + ': matches at each change')
            log.clear()
            p.expect(m.style(element, 'order') == str(fixture['styleOrder'][name]), name + ': style sees the preferences')
            p.expect(fields(m.readback()) == fields(supplied), name + ': readback')
            for facility, members in FACILITIES.items():
                p.expect(m.fact(facility, 2) == int(any(getattr(supplied, member) for member in members)), name + ': ' + facility + ' supplied')
            native_steps.append(name)
            previous = step

        # The Chromium oracle agrees with every step it emulates.
        emulated = [step['name'] for step in fixture['steps'] if step.get('chromium', True)]
        p.expect([entry['name'] for entry in oracle['steps']] == emulated, 'Chromium steps')
        for entry in oracle['steps']:
            p.expect(entry['matchesFixture'] and entry['changesFixture'] and entry['orderFixture'], entry['name'] + ': Chromium agrees')

        # Text scale scales laid-out text; the computed font-size and media queries do not read it.
        last = fixture['steps'][-1]
        height = m.height(element)
        before = [m.matches(target) for target in lists]
        m.supply(preferences_of(last, 2.0), 'text scale 2')
        m.settle()
        scaled = m.height(element)
        p.expect(scaled >= 2 * height - 1, 'text scale 2 doubles the line: ' + str((height, scaled)))
        p.expect(m.style(element, 'font-size') == '16px', 'computed font-size is the page size')
        p.expect([m.matches(target) for target in lists] == before and log == [], 'text scale changes no media query')
        p.expect(m.fact('media-text-scale', 2) == 1 and m.readback().text_scale == 2.0, 'text scale supplied')
        m.supply(preferences_of(last), 'text scale default')
        m.settle()
        p.expect(m.height(element) == height, 'default text scale')

        # An owned subscription: a listener removed before a change gets no callback; the kept one gets exactly one.
        owned, kept_log, removed_log = m.match_media(p.host, b'(prefers-reduced-motion: reduce)'), [], []
        kept = m.listen(owned, kept_log, 'kept')
        removed = m.listen(owned, removed_log, 'removed')
        p.expect(m.remove_listener(removed) == OK, 'listener removed before the change')
        reduce = preferences_of(last)
        reduce.reduced_motion = VALUES['reducedMotion']['reduce']
        m.supply(reduce, 'reduced motion')
        m.settle()
        p.expect(kept_log == [('kept', 1)] and removed_log == [], 'owned subscription: ' + str((kept_log, removed_log)))
        p.expect(m.remove_listener(kept) == OK, 'kept listener removed')
        m.supply(preferences_of(last), 'no preference')
        m.settle()
        p.expect(kept_log == [('kept', 1)] and removed_log == [], 'no callback after removal')
        m.release(owned)
        log.clear()

        # Errors leave the supplied preferences unchanged.
        current = fields(m.readback())
        result = MediaPreferences(size=ctypes.sizeof(MediaPreferences))
        p.expect(m.set(None, ctypes.byref(result)) == NULL_ARGUMENT and m.set(p.host, None) == NULL_ARGUMENT, 'NULL host or preferences')
        p.expect(m.get(None, ctypes.byref(result)) == NULL_ARGUMENT and m.get(p.host, None) == NULL_ARGUMENT, 'NULL readback')
        small = preferences_of(last)
        small.size = ctypes.sizeof(MediaPreferences) - 4
        p.expect(m.set(p.host, ctypes.byref(small)) == UNSUPPORTED and m.get(p.host, ctypes.byref(small)) == UNSUPPORTED, 'small size')
        for field, bad in [('color_scheme', 3), ('reduced_motion', 3), ('contrast', 3), ('pointer', 4), ('hover', 3), ('any_pointer', 5),
                           ('any_hover', 3), ('color_scheme', -1), ('text_scale', 0.2), ('text_scale', 9.0), ('text_scale', -1.0)]:
            value = preferences_of(last)
            setattr(value, field, bad)
            p.expect(m.set(p.host, ctypes.byref(value)) == UNSUPPORTED, field + ' ' + str(bad) + ' rejected')
        p.expect(fields(m.readback()) == current, 'rejected preferences apply nothing')
        m.settle()
        p.expect(log == [], 'rejected preferences fire no change')

        # Threads: both calls stay on the owning thread.
        statuses = []

        def worker():
            value = preferences_of(last)
            statuses.append((m.set(p.host, ctypes.byref(value)), m.get(p.host, ctypes.byref(value))))

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        p.expect(statuses == [(WRONG_THREAD, WRONG_THREAD)], 'thread rules: ' + str(statuses))

        # Document replacement: a list of the old document fires no change; the supplied preferences stay.
        old_log = []
        old = m.match_media(p.host, b'(prefers-color-scheme: dark)')
        m.listen(old, old_log, 'old')
        p.release_nodes()
        p.load(fixture['page'], standalone=False)
        m.settle()
        dark = preferences_of(last)
        dark.color_scheme = VALUES['colorScheme']['dark']
        m.supply(dark, 'dark after replacement')
        m.settle()
        p.expect(old_log == [], 'no change for a list of the replaced document: ' + str(old_log))
        fresh = m.match_media(p.host, b'(prefers-color-scheme: dark)')
        p.expect(m.matches(fresh) == 1 and fields(m.readback()) == fields(dark), 'the new document sees the supplied preferences')
        coarse = m.match_media(p.host, b'(pointer: coarse)')
        p.expect(m.matches(coarse) == 1, 'pointer preference survives replacement')
        p.expect(m.style(p.node('t'), 'order') == '3', 'style of the new document')
        for target in lists:
            m.release(target)
        m.release(old)
        held = [fresh, coarse]
        assertions = p.assertions

    # Lists held past rv_host_destroy keep their last matches and stay releasable.
    held_matches = []
    for target in held:
        value = ctypes.c_int32(-1)
        held_matches.append((m.matches_of(target, ctypes.byref(value)), value.value))
        m.release(target)
    if held_matches != [(OK, 1), (OK, 1)]:
        raise AssertionError('lists held past destroy: ' + str(held_matches))
    return assertions + 1, len(fixture['steps']), len(oracle['steps'])


def run(native_directory, repeat):
    fixture = json.loads((FIXTURES / 'media-queries.json').read_text(encoding='utf-8'))
    oracle = json.loads((FIXTURES / 'media-queries-oracle.json').read_text(encoding='utf-8'))
    totals = set()
    for _ in range(repeat):
        totals.add(run_once(native_directory, fixture, oracle))
    if len(totals) != 1:
        raise AssertionError('assertion counts vary across repeats: ' + str(totals))
    assertions, steps, emulated = totals.pop()
    print(f'media queries PASS: {assertions} assertions, {steps} fixture steps, {emulated} with Chromium, {repeat} run(s)', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--repeat', type=int, default=1)
    args = parser.parse_args()
    run(args.native_directory, args.repeat)
