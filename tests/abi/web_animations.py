"""Replays tests/fixtures/web-animations-cases.json through the generated Web Animations creation functions
(rv_dom_element_animate, rv_dom_keyframe_effect_create_3/_1, rv_dom_web_animation_create, rv_dom_document_timeline_create)
and compares every paused, seeked point with the Chromium oracle tests/fixtures/web-animations-oracle.json: play state,
current time, computed values and rendered pixels. It also checks the error cases, the null, thread and interface errors,
and that the keyframe transport runs no script: the page's canary script stays unrun, and once the page has loaded JSC
is told to crash on any VM entry the host's DisallowVMEntry refuses (Options::setOption crashOnDisallowedVMEntry) for the
calls that take no JavaScript lock: Animation construction and control, the effect and timeline members and the timeline
constructor. A child process proves the crash is armed: a second page load, which attempts a VM entry, aborts it.
Element.animate, the KeyframeEffect constructor and setKeyframes take the lock; its release attempts a microtask drain,
which DisallowVMEntry refuses (qualified): no script runs, the canary proves it, and 3 rounds of 1000 calls keep the
private memory flat."""

import argparse
import ctypes
import json
import os
from pathlib import Path
import sys
import threading

import subprocess
sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, P, I, U, OK, NULL_ARGUMENT, WRONG_THREAD, DOM_EXCEPTION, WRONG_INTERFACE, ABI  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
D = ctypes.c_double
WIDTH, HEIGHT = 320, 240
# Pixel channels may differ by this much: Chromium and WebKit round alpha blending differently.
PIXEL_TOLERANCE = 2
PLAY_STATES = ['idle', 'running', 'paused', 'finished']
COMPOSITES = ['replace', 'add', 'accumulate']
ITERATION_COMPOSITES = ['replace', 'accumulate']
FILL = {'none': 0, 'forwards': 1, 'backwards': 2, 'both': 3, 'auto': 4}
DIRECTION = {'normal': 0, 'reverse': 1, 'alternate': 2, 'alternate-reverse': 3}


class StringInput(ctypes.Structure):
    _fields_ = [('present', I), ('data', P), ('length', I)]


class KeyframeProperty(ctypes.Structure):
    _fields_ = [('size', U), ('name', StringInput), ('value', StringInput)]


class KeyframeProperties(ctypes.Structure):
    _fields_ = [('present', I), ('count', I), ('items', ctypes.POINTER(ctypes.POINTER(KeyframeProperty)))]


class Keyframe(ctypes.Structure):
    _fields_ = [('size', U), ('offset', ctypes.POINTER(D)), ('easing', StringInput), ('composite', StringInput),
                ('properties', ctypes.POINTER(KeyframeProperties))]


class Keyframes(ctypes.Structure):
    _fields_ = [('present', I), ('count', I), ('items', ctypes.POINTER(ctypes.POINTER(Keyframe)))]


class Span(ctypes.Structure):
    _fields_ = [('data', P), ('length', I)]


class Duration(ctypes.Structure):
    _fields_ = [('present', I), ('tag', I), ('arm0', D), ('arm1', P), ('arm2', Span)]


EFFECT_TIMING = [('size', U), ('delay', D), ('end_delay', D), ('fill', I), ('iteration_start', D), ('iterations', D),
                 ('duration', ctypes.POINTER(Duration)), ('direction', I), ('easing', StringInput)]
EFFECT_OPTIONS = EFFECT_TIMING + [('iteration_composite', I), ('composite', I), ('pseudo_element', StringInput)]


class KeyframeEffectOptions(ctypes.Structure):
    _fields_ = EFFECT_OPTIONS


class KeyframeAnimationOptions(ctypes.Structure):
    _fields_ = EFFECT_OPTIONS + [('id', StringInput), ('timeline', ctypes.POINTER(P))]


class AnimationOptions(ctypes.Structure):
    _fields_ = [('present', I), ('tag', I), ('arm0', D), ('arm1', ctypes.POINTER(KeyframeAnimationOptions))]


class EffectOptions(ctypes.Structure):
    _fields_ = [('present', I), ('tag', I), ('arm0', D), ('arm1', ctypes.POINTER(KeyframeEffectOptions))]


class TimelineOptions(ctypes.Structure):
    _fields_ = [('size', U), ('origin_time', D)]


class Time(ctypes.Structure):
    _fields_ = [('present', I), ('tag', I), ('arm0', D), ('arm1', P)]


class Animations(ctypes.Structure):
    _fields_ = [('present', I), ('count', I), ('items', ctypes.POINTER(P))]


class Arena:
    """Owns the ctypes buffers one call borrows."""

    def __init__(self):
        self.kept = []

    def keep(self, value):
        self.kept.append(value)
        return value

    def string(self, text):
        if text is None:
            return StringInput(0, None, 0)
        data = self.keep(ctypes.create_string_buffer(text.encode('utf-8')))
        return StringInput(1, ctypes.cast(data, P), len(text.encode('utf-8')))

    def keyframes(self, frames):
        if frames is None:
            return None
        items = (ctypes.POINTER(Keyframe) * max(len(frames), 1))()
        for index, frame in enumerate(frames):
            props = list(frame['props'].items())
            entries = (ctypes.POINTER(KeyframeProperty) * max(len(props), 1))()
            for j, (name, value) in enumerate(props):
                entries[j] = ctypes.pointer(self.keep(KeyframeProperty(ctypes.sizeof(KeyframeProperty), self.string(name), self.string(value))))
            properties = self.keep(KeyframeProperties(1, len(props), entries if props else None))
            self.keep(entries)
            offset = None
            if 'offset' in frame:
                offset = ctypes.pointer(self.keep(D(float('nan') if frame['offset'] == 'NaN' else frame['offset'])))
            keyframe = self.keep(Keyframe(ctypes.sizeof(Keyframe), offset, self.string(frame.get('easing')),
                                          self.string(frame.get('composite')), ctypes.pointer(properties)))
            items[index] = ctypes.pointer(keyframe)
        self.keep(items)
        return ctypes.pointer(self.keep(Keyframes(1, len(frames), items if frames else None)))

    def timing(self, struct, options, timeline=None):
        value = struct()
        value.size = ctypes.sizeof(struct)
        value.fill, value.iterations, value.direction = FILL['auto'], 1.0, DIRECTION['normal']
        value.easing = self.string(options.get('easing'))
        value.delay, value.end_delay = options.get('delay', 0), options.get('endDelay', 0)
        value.iteration_start = options.get('iterationStart', 0)
        if 'iterations' in options:
            value.iterations = options['iterations']
        if 'fill' in options:
            value.fill = FILL[options['fill']]
        if 'direction' in options:
            value.direction = DIRECTION[options['direction']]
        if 'duration' in options:
            value.duration = ctypes.pointer(self.keep(Duration(1, 1, options['duration'], None, Span(None, 0))))
        value.composite = COMPOSITES.index(options.get('composite', 'replace'))
        value.iteration_composite = ITERATION_COMPOSITES.index(options.get('iterationComposite', 'replace'))
        value.pseudo_element = self.string(options.get('pseudoElement'))
        if struct is KeyframeAnimationOptions:
            value.id = self.string(options.get('id', ''))
            if timeline is not None:
                value.timeline = ctypes.pointer(self.keep(P(timeline)))
        return self.keep(value)

    def options(self, union, struct, options, timeline=None):
        if options is None:
            return None
        if isinstance(options, (int, float, str)):
            return ctypes.pointer(self.keep(union(1, 1, float('nan') if options == 'NaN' else float(options), None)))
        return ctypes.pointer(self.keep(union(1, 2, 0.0, ctypes.pointer(self.timing(struct, options, timeline)))))


class Page:
    def __init__(self, native, markup):
        self.n = native
        self.host = native.bind('rv_host_create', P, [I, I])(WIDTH, HEIGHT)
        native.expect(bool(self.host), 'host created')
        utf8 = markup.encode('utf-8')
        native.ok('rv_host_load_html', [P, ctypes.c_char_p, I], self.host, utf8, len(utf8))
        self.document = native.bind('rv_host_document', P, [P])(self.host)
        by_id_utf8 = native.bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p, I])
        self.by_id = lambda host, element_id: by_id_utf8(host, element_id, len(element_id))
        self.elements = {}

    def element(self, name):
        if name not in self.elements:
            self.elements[name] = self.by_id(self.host, name.encode())
            self.n.expect(bool(self.elements[name]), 'element ' + name)
        return self.elements[name]

    def guard(self, label):
        """The host's DisallowVMEntry holds: the call entered no script."""
        self.n.expect(self.n.call('rv_host_vm_entry_disallowed', [P], self.host) == 1, label + ': VM entry still disallowed')
        self.n.expect(self.n.call('rv_host_scripts_enabled', [P], self.host) == 0, label + ': scripts still disabled')

    def timeline(self):
        return self.n.handle('rv_dom_document_get_timeline', [P], self.document, nullable=False)

    def close(self):
        release = self.n.bind('rv_node_release', None, [P])
        for node in self.elements.values():
            release(node)
        release(self.document)
        self.n.bind('rv_host_destroy', None, [P])(self.host)


# JSC's exported Options::setOption(const char*, bool), MSVC and Itanium manglings.
SET_OPTION = ['?setOption@Options@JSC@@SA_NPEBD_N@Z', '_ZN3JSC7Options9setOptionEPKcb']


def arm_vm_entry_crash(directory, crash=True):
    """Makes a VM entry under DisallowVMEntry crash the process; returns False where JSC does not export the setter."""
    names = {'win32': ['JavaScriptCore.dll'], 'darwin': ['JavaScriptCore.framework/JavaScriptCore', 'libJavaScriptCore.dylib']}
    for name in names.get(sys.platform, ['libRanvierWebCoreHost.so', 'libJavaScriptCore.so']):
        path = Path(directory) / name
        if not path.exists():
            continue
        library = ctypes.CDLL(str(path))
        for symbol in SET_OPTION:
            function = getattr(library, symbol, None)
            if function is not None:
                function.restype, function.argtypes = ctypes.c_bool, [ctypes.c_char_p, ctypes.c_bool]
                return bool(function(b'crashOnDisallowedVMEntry=' + (b'true' if crash else b'false'), False))
    return False


def vm_entry_control(directory):
    """The positive control, in a child process: with the crash armed, a page load (which enters the VM) aborts."""
    native = Native(directory)
    host = native.bind('rv_host_create', P, [I, I])(64, 64)
    native.call('rv_host_load_html', [P, ctypes.c_char_p, I], host, b'<p>first</p>', len(b'<p>first</p>'))  # utf8
    if not arm_vm_entry_crash(directory):
        raise SystemExit(3)
    native.call('rv_host_load_html', [P, ctypes.c_char_p, I], host, b'<p>second</p>', len(b'<p>second</p>'))  # utf8
    print('VM_ENTRY_CONTROL_SURVIVED', flush=True)


def exception_name(native):
    buffer, length = ctypes.create_string_buffer(256), I()
    native.ok('rv_last_exception', [I, P, I, ctypes.POINTER(I)], 0, buffer, 256, ctypes.byref(length))
    return buffer.raw[:length.value].decode('utf-8')


def animate(native, page, kind, element, keyframes, options, arena):
    """Creates the case's animation; returns (status, animation handle or None)."""
    result = P()
    if kind in ('animate', 'animate-timeline'):
        timeline = page.timeline() if kind == 'animate-timeline' else None
        status = native.call('rv_dom_element_animate', [P, P, P, ctypes.POINTER(P)], element, arena.keyframes(keyframes),
                             arena.options(AnimationOptions, KeyframeAnimationOptions, options, timeline), ctypes.byref(result))
        if timeline:
            native.bind('rv_dom_animation_timeline_release', None, [P])(timeline)
        return status, result.value
    effect = P()
    status = native.call('rv_dom_keyframe_effect_create_3', [P, P, P, P, ctypes.POINTER(P)], page.document,
                         None if kind == 'effect-null-target' else element, arena.keyframes(keyframes),
                         arena.options(EffectOptions, KeyframeEffectOptions, options), ctypes.byref(effect))
    if status != OK:
        return status, None
    if kind == 'copy':
        copy = P()
        native.ok('rv_dom_keyframe_effect_create_1', [P, P, ctypes.POINTER(P)], page.document, effect, ctypes.byref(copy))
        native.expect(copy.value != effect.value, 'copy is a new effect')
        native.bind('rv_dom_animation_effect_release', None, [P])(effect)
        effect = copy
    timeline = page.timeline() if kind in ('construct', 'copy') else None
    present = 0 if kind in ('construct-default', 'effect', 'effect-null-target') else 1
    status = native.call('rv_dom_web_animation_create', [P, P, P, I, ctypes.POINTER(P)], page.document, effect,
                         timeline, present, ctypes.byref(result))
    native.bind('rv_dom_animation_effect_release', None, [P])(effect)
    if timeline:
        native.bind('rv_dom_animation_timeline_release', None, [P])(timeline)
    return status, result.value


def current_time(native, animation):
    value = Time()
    native.ok('rv_dom_web_animation_get_current_time', [P, ctypes.POINTER(Time)], animation, ctypes.byref(value))
    native.expect(value.present == 0 or value.tag == 1, 'currentTime is a number')
    return value.arm0 if value.present else None


def seek(native, animation, time):
    native.ok('rv_dom_web_animation_set_current_time', [P, ctypes.POINTER(Time)], animation, ctypes.byref(Time(1, 1, float(time), None)))


def play_state(native, animation):
    return PLAY_STATES[native.integer('rv_dom_web_animation_get_play_state', animation)]


def describe(native, page, animation):
    effect = native.handle('rv_dom_web_animation_get_effect', [P], animation)
    timeline = native.handle('rv_dom_web_animation_get_timeline', [P], animation)
    document_timeline = page.timeline()
    target = native.handle('rv_dom_keyframe_effect_get_target', [P], effect) if effect else None
    target_id = native.text('rv_dom_element_get_id', [P], target) if target else None
    created = {'id': native.text('rv_dom_web_animation_get_id', [P], animation), 'playState': play_state(native, animation),
               'timelineIsDocument': timeline == document_timeline, 'target': target_id,
               'composite': COMPOSITES[native.integer('rv_dom_keyframe_effect_get_composite', effect)],
               'iterationComposite': ITERATION_COMPOSITES[native.integer('rv_dom_keyframe_effect_get_iteration_composite', effect)],
               'pseudoElement': native.text('rv_dom_keyframe_effect_get_pseudo_element', [P], effect)}
    if target:
        native.bind('rv_node_release', None, [P])(target)
    native.bind('rv_dom_animation_effect_release', None, [P])(effect)
    for handle in (timeline, document_timeline):
        if handle:
            native.bind('rv_dom_animation_timeline_release', None, [P])(handle)
    return created


def computed(native, element, prop):
    buffer, length = ctypes.create_string_buffer(512), I()
    native.ok('rv_element_computed_style', [P, ctypes.c_char_p, P, I, ctypes.POINTER(I)], element, prop.encode(), buffer, 512, ctypes.byref(length))
    return buffer.raw[:length.value].decode('utf-8')


def paint(native, page):
    native.call('rv_host_update', [P], page.host)
    pixels = (ctypes.c_uint8 * (WIDTH * HEIGHT * 4))()
    native.ok('rv_host_paint_rgba', [P, P, I], page.host, pixels, len(pixels))
    return lambda x, y: list(pixels[(y * WIDTH + x) * 4:(y * WIDTH + x) * 4 + 3])


def run_case(native, page, case, oracle):
    element = page.element(case['el'])
    arena = Arena()
    status, animation = animate(native, page, case['kind'], element, case['keyframes'], case['options'], arena)
    native.expect(status == OK and animation, case['name'] + ': created, status ' + str(status))
    page.guard(case['name'] + ' creation')
    native.ok('rv_dom_web_animation_pause', [P], animation)
    result = {'name': case['name'], 'created': describe(native, page, animation), 'points': []}
    for time, wanted in zip(case['times'], oracle['points']):
        seek(native, animation, time)
        point = {'time': time, 'currentTime': current_time(native, animation), 'playState': play_state(native, animation),
                 'values': {prop: computed(native, element, prop) for prop in case['props']}}
        pixel = paint(native, page)
        point['samples'] = [{'x': s['x'], 'y': s['y'], 'rgb': pixel(s['x'], s['y']) if s['rgb'] is not None else None} for s in wanted['samples']]
        result['points'].append(point)
    native.ok('rv_dom_web_animation_cancel', [P], animation)
    native.bind('rv_event_target_release', None, [P])(animation)
    return result


def compare(native, actual, wanted, failures):
    def check(label, ok):
        native.assertions += 1
        if not ok:
            failures.append({'case': actual['name'], 'check': label})
    for key, value in wanted['created'].items():
        check(f'created.{key}: native {actual["created"][key]!r} chromium {value!r}', actual['created'][key] == value)
    for point, expected in zip(actual['points'], wanted['points']):
        for key in ('currentTime', 'playState'):
            check(f't={point["time"]} {key}: native {point[key]!r} chromium {expected[key]!r}', point[key] == expected[key])
        for prop, value in expected['values'].items():
            check(f't={point["time"]} {prop}: native {point["values"][prop]!r} chromium {value!r}', point['values'][prop] == value)
        for sample, other in zip(point['samples'], expected['samples']):
            if other['rgb'] is None:
                continue
            close = all(abs(a - b) <= PIXEL_TOLERANCE for a, b in zip(sample['rgb'], other['rgb']))
            check(f't={point["time"]} pixel {other["x"]},{other["y"]}: native {sample["rgb"]} chromium {other["rgb"]}', close)


def run_error(native, page, case):
    arena = Arena()
    kind = case.get('kind', 'animate')
    element = page.element('a')
    if kind == 'animation-empty':
        result = P()
        status = native.call('rv_dom_web_animation_create', [P, P, P, I, ctypes.POINTER(P)], page.document, None, None, 0, ctypes.byref(result))
        animation = result.value
    elif kind == 'animation-null-timeline':
        effect = P()
        native.ok('rv_dom_keyframe_effect_create_3', [P, P, P, P, ctypes.POINTER(P)], page.document, element, arena.keyframes(case['keyframes']),
                  arena.options(EffectOptions, KeyframeEffectOptions, case['options']), ctypes.byref(effect))
        result = P()
        status = native.call('rv_dom_web_animation_create', [P, P, P, I, ctypes.POINTER(P)], page.document, effect, None, 1, ctypes.byref(result))
        native.bind('rv_dom_animation_effect_release', None, [P])(effect)
        animation = result.value
        if status == OK:
            native.ok('rv_dom_web_animation_play', [P], animation)
    else:
        status, animation = animate(native, page, kind, element, case['keyframes'], case['options'], arena)
    if status != OK:
        native.expect(status == DOM_EXCEPTION, case['name'] + ': DOM exception status, got ' + str(status))
        return {'name': case['name'], 'ok': False, 'exception': exception_name(native)}
    effect = native.handle('rv_dom_web_animation_get_effect', [P], animation)
    timeline = native.handle('rv_dom_web_animation_get_timeline', [P], animation)
    document_timeline = page.timeline()
    out = {'name': case['name'], 'ok': True, 'playState': play_state(native, animation), 'hasEffect': bool(effect),
           'timeline': 'null' if not timeline else 'document' if timeline == document_timeline else 'other',
           'currentTime': current_time(native, animation)}
    for release, handle in [('rv_dom_animation_effect_release', effect), ('rv_dom_animation_timeline_release', timeline),
                            ('rv_dom_animation_timeline_release', document_timeline)]:
        if handle:
            native.bind(release, None, [P])(handle)
    native.ok('rv_dom_web_animation_cancel', [P], animation)
    native.bind('rv_event_target_release', None, [P])(animation)
    return out


def contract_errors(native, page):
    """Null, thread and interface errors of the creation functions, and the timeline constructor."""
    element, arena = page.element('a'), Arena()
    keyframes = arena.keyframes([{'props': {'opacity': '0'}}])
    result = P()
    expect = native.expect
    animate_fn = native.bind('rv_dom_element_animate', I, [P, P, P, ctypes.POINTER(P)])
    expect(animate_fn(None, keyframes, None, ctypes.byref(result)) == NULL_ARGUMENT, 'animate NULL target')
    expect(animate_fn(element, keyframes, None, None) == NULL_ARGUMENT, 'animate NULL result')
    expect(animate_fn(page.document, keyframes, None, ctypes.byref(result)) == WRONG_INTERFACE, 'animate on a document')
    bad = Arena()
    broken = bad.keyframes([{'props': {'opacity': '0'}}])
    broken.contents.items[0].contents.properties.contents.items[0].contents.name = StringInput(1, None, 3)
    expect(animate_fn(element, broken, None, ctypes.byref(result)) == NULL_ARGUMENT, 'animate NULL property name with length')
    invalid = Arena()
    utf8 = invalid.keyframes([{'props': {'opacity': '0'}}])
    raw = invalid.keep(ctypes.create_string_buffer(b'\xff\xfe'))
    utf8.contents.items[0].contents.properties.contents.items[0].contents.value = StringInput(1, ctypes.cast(raw, P), 2)
    expect(animate_fn(element, utf8, None, ctypes.byref(result)) == NULL_ARGUMENT, 'animate invalid UTF-8 value')
    status = []
    worker = threading.Thread(target=lambda: status.append(animate_fn(element, keyframes, None, ctypes.byref(result))))
    worker.start(); worker.join()
    expect(status == [WRONG_THREAD], 'animate off the owning thread')
    # A null keyframes pointer is null keyframes: an empty effect.
    expect(animate_fn(element, None, None, ctypes.byref(result)) == OK and result.value, 'animate NULL keyframes')
    native.ok('rv_dom_web_animation_cancel', [P], result.value)
    # An event target of another interface where an animation is expected.
    effect = native.handle('rv_dom_web_animation_get_effect', [P], result.value, nullable=False)
    other = native.bind('rv_host_create_event_target', P, [P])(page.host)
    expect(native.call('rv_dom_web_animation_pause', [P], other) == WRONG_INTERFACE, 'pause on a plain event target')
    native.bind('rv_event_target_release', None, [P])(other)
    timeline = page.timeline()
    expect(native.text('rv_dom_animation_effect_get_interface_name', [P], effect) == 'KeyframeEffect', 'effect runtime type KeyframeEffect')
    expect(native.text('rv_dom_animation_timeline_get_interface_name', [P], timeline) == 'DocumentTimeline', 'timeline runtime type DocumentTimeline')
    created = P()
    expect(native.call('rv_dom_keyframe_effect_create_1', [P, P, ctypes.POINTER(P)], page.document, None, ctypes.byref(created)) == NULL_ARGUMENT,
           'copy constructor NULL source')
    expect(native.call('rv_dom_keyframe_effect_create_3', [P, P, P, P, ctypes.POINTER(P)], element, element, keyframes, None,
                       ctypes.byref(created)) == WRONG_INTERFACE, 'effect constructor on an element receiver')
    expect(native.call('rv_dom_keyframe_effect_set_keyframes', [P, P, P], effect, element, keyframes) == WRONG_INTERFACE,
           'setKeyframes with an element context')
    native.ok('rv_dom_keyframe_effect_set_keyframes', [P, P, P], effect, page.document, arena.keyframes([{'props': {'opacity': '0.3'}}]))
    expect(native.call('rv_dom_keyframe_effect_set_keyframes', [P, P, P], effect, page.document,
                       arena.keyframes([{'props': {'opacity': '0'}, 'offset': 0.9}, {'props': {'opacity': '1'}, 'offset': 0.1}])) == DOM_EXCEPTION
           and exception_name(native) == 'TypeError', 'setKeyframes unsorted offsets TypeError')
    native.bind('rv_dom_animation_effect_release', None, [P])(effect)
    native.bind('rv_event_target_release', None, [P])(result.value)
    # A new document timeline: a timeline of its own, readable and distinct from document.timeline.
    own = P()
    native.ok('rv_dom_document_timeline_create', [P, P, ctypes.POINTER(P)], page.document,
              ctypes.byref(TimelineOptions(ctypes.sizeof(TimelineOptions), 0.0)), ctypes.byref(own))
    expect(own.value and own.value != timeline, 'new DocumentTimeline is its own timeline')
    value = Time()
    native.ok('rv_dom_animation_timeline_get_current_time', [P, ctypes.POINTER(Time)], own, ctypes.byref(value))
    expect(value.present == 1 and value.tag == 1 and value.arm0 >= 0, 'new DocumentTimeline has a current time')
    native.bind('rv_dom_animation_timeline_release', None, [P])(own)
    native.bind('rv_dom_animation_timeline_release', None, [P])(timeline)
    # The bridge from a CSS-animation handle is tested by the A05 probe; here the export exists.
    expect(hasattr(native.library, 'rv_animation_as_event_target'), 'rv_animation_as_event_target exported')


def private_bytes():
    """The process's committed private memory in bytes, or None where the probe cannot read it."""
    if sys.platform == 'win32':
        class Counters(ctypes.Structure):
            _fields_ = [('cb', ctypes.c_uint32), ('PageFaultCount', ctypes.c_uint32)] + [
                (name, ctypes.c_size_t) for name in ['PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                                                     'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage',
                                                     'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage']]
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        info = ctypes.windll.psapi.GetProcessMemoryInfo
        info.argtypes = [P, ctypes.POINTER(Counters), ctypes.c_uint32]
        if not info(process, ctypes.byref(counters), counters.cb):
            return None
        return counters.PrivateUsage
    statm = Path('/proc/self/statm')
    if statm.exists():
        return int(statm.read_text().split()[5]) * os.sysconf('SC_PAGE_SIZE')
    return None


# Each round creates this many animations and effects; growth between the later rounds stays under the bound.
GROWTH_ROUND, GROWTH_BOUND = 1000, 16 * 1024 * 1024


def growth(native, page):
    """1000 animate and 1000 KeyframeEffect calls per round, each taking and releasing the JavaScript lock (a refused
    microtask drain), with the private memory sampled after a full collection: the second and third rounds stay flat."""
    element, arena = page.element('d'), Arena()
    keyframes = arena.keyframes([{'props': {'opacity': '0'}}, {'props': {'opacity': '1'}}])
    options = arena.options(AnimationOptions, KeyframeAnimationOptions, 1000)
    release_target = native.bind('rv_event_target_release', None, [P])
    release_effect = native.bind('rv_dom_animation_effect_release', None, [P])
    collect = native.bind('rv_collect_garbage', None, [])
    animate_fn = native.bind('rv_dom_element_animate', I, [P, P, P, ctypes.POINTER(P)])
    effect_fn = native.bind('rv_dom_keyframe_effect_create_3', I, [P, P, P, P, ctypes.POINTER(P)])
    cancel = native.bind('rv_dom_web_animation_cancel', I, [P])

    def one_round():
        statuses = set()
        for _ in range(GROWTH_ROUND):
            animation, effect = P(), P()
            statuses.add(animate_fn(element, keyframes, options, ctypes.byref(animation)))
            statuses.add(cancel(animation))
            release_target(animation)
            statuses.add(effect_fn(page.document, element, keyframes, None, ctypes.byref(effect)))
            release_effect(effect)
        native.expect(statuses == {OK}, 'growth round statuses ' + str(statuses))
        native.bind('rv_run_loop_cycle', I, [I])(20)
        collect()
        return private_bytes()

    samples = [one_round() for _ in range(3)]
    page.guard('growth rounds')
    if None in samples:
        return {'samples': samples, 'checked': False}
    native.expect(samples[2] - samples[1] < GROWTH_BOUND, 'memory flat across rounds: ' + str(samples))
    return {'samples': samples, 'checked': True, 'round': GROWTH_ROUND, 'bound': GROWTH_BOUND}


def lock_free_calls(native, page):
    """With the VM-entry crash armed: Animation construction and control, effect and timeline members and the timeline
    constructor take no JavaScript lock, so a VM entry by any of them would abort the probe."""
    element, arena = page.element('b'), Arena()
    effect = P()
    native.ok('rv_dom_keyframe_effect_create_3', [P, P, P, P, ctypes.POINTER(P)], page.document, element,
              arena.keyframes([{'props': {'opacity': '0'}}, {'props': {'opacity': '1'}}]),
              arena.options(EffectOptions, KeyframeEffectOptions, {'duration': 1000, 'fill': 'both'}), ctypes.byref(effect))
    timeline = page.timeline()
    if not arm_vm_entry_crash(page.directory):
        native.bind('rv_dom_animation_effect_release', None, [P])(effect)
        native.bind('rv_dom_animation_timeline_release', None, [P])(timeline)
        return False
    animation = P()
    native.ok('rv_dom_web_animation_create', [P, P, P, I, ctypes.POINTER(P)], page.document, effect, timeline, 1, ctypes.byref(animation))
    animation = animation.value
    native.ok('rv_dom_web_animation_play', [P], animation)
    native.ok('rv_dom_web_animation_pause', [P], animation)
    seek(native, animation, 250)
    native.expect(current_time(native, animation) == 250 and play_state(native, animation) == 'paused', 'armed: paused at 250')
    native.expect(computed(native, element, 'opacity') == '0.25', 'armed: computed opacity at 250')
    # Painting runs a rendering update, which attempts its own VM entry before any animation code (pre-existing, out of
    # the armed scope); the rendered values are compared unarmed above.
    name = ctypes.create_string_buffer(b'armed')
    native.ok('rv_dom_web_animation_set_id', [P, P, I], animation, name, 5)
    native.expect(native.text('rv_dom_web_animation_get_id', [P], animation) == 'armed', 'armed: id')
    native.ok('rv_dom_web_animation_update_playback_rate', [P, D], animation, 2.0)
    native.ok('rv_dom_keyframe_effect_set_composite', [P, I], effect, 1)
    native.expect(native.integer('rv_dom_keyframe_effect_get_composite', effect) == 1, 'armed: composite add')
    native.ok('rv_dom_web_animation_finish', [P], animation)
    native.expect(play_state(native, animation) == 'finished', 'armed: finished')
    native.ok('rv_dom_web_animation_cancel', [P], animation)
    native.expect(play_state(native, animation) == 'idle' and current_time(native, animation) is None, 'armed: cancelled')
    own = P()
    native.ok('rv_dom_document_timeline_create', [P, P, ctypes.POINTER(P)], page.document, None, ctypes.byref(own))
    native.bind('rv_dom_animation_timeline_release', None, [P])(own)
    page.guard('armed lock-free calls')
    native.bind('rv_event_target_release', None, [P])(animation)
    native.bind('rv_dom_animation_effect_release', None, [P])(effect)
    native.bind('rv_dom_animation_timeline_release', None, [P])(timeline)
    return True


def verify(directory, arm=True):
    spec = json.loads((FIXTURES / 'web-animations-cases.json').read_text(encoding='utf-8'))
    oracle = json.loads((FIXTURES / 'web-animations-oracle.json').read_text(encoding='utf-8'))
    native = Native(directory)
    native.expect(native.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
    has = native.bind('rv_abi_has', I, [ctypes.c_char_p])
    for capability in [b'dom:WebAnimation', b'dom:AnimationEffect', b'dom:KeyframeEffect', b'dom:AnimationTimeline',
                       b'dom:DocumentTimeline', b'dom-constructor:KeyframeEffect', b'dom-constructor:WebAnimation',
                       b'dom-constructor:DocumentTimeline']:
        native.expect(has(capability) == 1, 'rv_abi_has ' + capability.decode())
    page = Page(native, spec['markup'])
    page.directory = directory
    failures, results, errors = [], [], []
    armed, memory = False, None
    try:
        title = native.text('rv_dom_document_get_title', [P], page.document)
        native.expect(title != 'script ran', 'the page script did not run')
        expected = {case['name']: case for case in oracle['cases']}
        for case in spec['cases']:
            actual = run_case(native, page, case, expected[case['name']])
            results.append(actual)
            compare(native, actual, expected[case['name']], failures)
        wanted_errors = {case['name']: case for case in oracle['errors']}
        for case in spec['errors']:
            actual = run_error(native, page, case)
            page.guard(case['name'])
            errors.append(actual)
            wanted = {k: v for k, v in wanted_errors[case['name']].items() if k != 'keyframes'}
            native.assertions += 1
            if actual != wanted:
                failures.append({'case': case['name'], 'check': f'native {actual} chromium {wanted}'})
        contract_errors(native, page)
        page.guard('contract errors')
        memory = growth(native, page)
        native.expect(native.text('rv_dom_document_get_title', [P], page.document) == title, 'no script ran during the probe')
        # Last: arm the VM-entry crash for the calls that take no JavaScript lock, and prove it armed in a child process.
        armed = arm and lock_free_calls(native, page)
        if armed:
            control = subprocess.run([sys.executable, '-I', '-X', 'utf8', __file__, '--native-directory', str(directory), '--vm-entry-control'],
                                     capture_output=True, text=True, timeout=120)
            native.expect(control.returncode not in (0, 3) and 'VM_ENTRY_CONTROL_SURVIVED' not in control.stdout,
                          'the armed VM-entry crash aborts a page load (control exit ' + str(control.returncode) + ')')
        native.expect(native.text('rv_dom_document_get_title', [P], page.document) == title, 'no script ran after arming')
    finally:
        # Host teardown is outside the armed scope: it releases the lock-taking work above.
        if armed:
            arm_vm_entry_crash(directory, False)
        page.close()
    return native, results, errors, failures, oracle['browser'], armed, memory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence')
    parser.add_argument('--vm-entry-control', action='store_true')
    parser.add_argument('--diagnose-without-vm-entry-crash', action='store_true')
    args = parser.parse_args()
    if args.vm_entry_control:
        vm_entry_control(args.native_directory)
        return
    native, results, errors, failures, browser, armed, memory = verify(args.native_directory, not args.diagnose_without_vm_entry_crash)
    if args.evidence:
        Path(args.evidence).write_text(json.dumps({'oracle': browser, 'assertions': native.assertions, 'failures': failures, 'vmEntryCrashArmed': armed, 'memoryGrowth': memory,
                                                   'cases': results, 'errors': errors}, indent=1) + '\n', encoding='utf-8')
    for failure in failures:
        print('MISMATCH', json.dumps(failure))
    if failures:
        raise SystemExit(f'{len(failures)} checks differ from {browser}')
    print(f'PASS web animations: {native.assertions} assertions against {browser}; VM-entry crash armed: {armed}')


if __name__ == '__main__':
    main()
