"""Replays tests/fixtures/animation-timelines-cases.json through the generated animation timeline functions and compares
the results with the Chromium oracle tests/fixtures/animation-timelines-oracle.json.
tests/fixtures/animation-timelines-qualified.json records the engine differences, asserting both engines' values.
A06: Document.timeline and DocumentTimeline time origins, the null duration, an inactive timeline (a document without a
browsing context) and an animation on it, start times shared by animations started in one rendering update, and a
timeline handle past host destroy. DocumentTimeline.maximumFrameRate and Animation.frameRate are Unsupported: their
WebKit setting is off and Chromium lacks both, so no export exists. DocumentTimeline.animate is covered by A09.
The timeline calls take no JavaScript lock: with the VM-entry crash armed (see web_animations.py) they run unchanged."""

import argparse
import ctypes
import json
from pathlib import Path
import subprocess
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, P, I, U, OK, NULL_ARGUMENT, WRONG_THREAD, WRONG_INTERFACE, ABI  # noqa: E402
from web_animations import (AnimationOptions, Arena, EffectOptions, KeyframeAnimationOptions, KeyframeEffectOptions, Page, Time,  # noqa: E402
                            TimelineOptions,
                            arm_vm_entry_crash, PLAY_STATES)

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
CLOSE = 1e-6
D = ctypes.c_double
UNSUPPORTED = -9
PROGRESS_CLOSE = 1e-4


class Probe:
    def __init__(self, native, page):
        self.n, self.page = native, page
        self.release_timeline = native.bind('rv_dom_animation_timeline_release', None, [P])
        self.release_target = native.bind('rv_event_target_release', None, [P])
        self.release_effect = native.bind('rv_dom_animation_effect_release', None, [P])

    def time(self, handle, fn='rv_dom_animation_timeline_get_current_time'):
        value = Time()
        self.n.ok(fn, [P, ctypes.POINTER(Time)], handle, ctypes.byref(value))
        if not value.present:
            return None
        self.n.expect(value.tag == 1, fn + ': a document timeline time is a number')
        return value.arm0

    def document_timeline(self, origin=None, document=None):
        result = P()
        options = None if origin is None else ctypes.byref(TimelineOptions(ctypes.sizeof(TimelineOptions), float(origin)))
        self.n.ok('rv_dom_document_timeline_create', [P, P, ctypes.POINTER(P)], document or self.page.document, options, ctypes.byref(result))
        return result.value

    def interface_name(self, timeline):
        return self.n.text('rv_dom_animation_timeline_get_interface_name', [P], timeline)

    def effect(self, target, duration):
        """A KeyframeEffect: its constructor takes the JavaScript lock (see web_animations.py)."""
        arena, effect = Arena(), P()
        self.n.ok('rv_dom_keyframe_effect_create_3', [P, P, P, P, ctypes.POINTER(P)], self.page.document, target,
                  arena.keyframes([{'props': {'opacity': '0'}}, {'props': {'opacity': '1'}}]),
                  arena.options(EffectOptions, KeyframeEffectOptions, duration), ctypes.byref(effect))
        return effect.value

    def animation(self, target, timeline, duration, effect=None):
        effect, animation = effect or self.effect(target, duration), P()
        self.n.ok('rv_dom_web_animation_create', [P, P, P, I, ctypes.POINTER(P)], self.page.document, effect, timeline, 1, ctypes.byref(animation))
        self.release_effect(effect)
        return animation.value

    def state(self, animation):
        return PLAY_STATES[self.n.integer('rv_dom_web_animation_get_play_state', animation)]

    def pending(self, animation):
        return bool(self.n.integer('rv_dom_web_animation_get_pending', animation))

    def frame(self):
        """One rendering update, as a browser frame: pending play tasks resolve their start times."""
        self.n.call('rv_run_loop_cycle', [I], 0)
        self.n.ok('rv_host_update', [P], self.page.host)


def a06(native, page, spec):
    probe, case = Probe(native, page), spec['a06']
    dt = page.timeline()
    made = {origin: probe.document_timeline(origin) for origin in case['origins']}
    dflt = probe.document_timeline()
    t = probe.time(dt)
    detached_document = P()
    implementation = native.handle('rv_dom_document_get_implementation', [P], page.document, nullable=False)
    native.ok('rv_dom_dom_implementation_create_html_document', [P, P, I, ctypes.POINTER(P)], implementation, None, 0, ctypes.byref(detached_document))
    native.bind('rv_dom_dom_implementation_release', None, [P])(implementation)
    detached = native.handle('rv_dom_document_get_timeline', [P], detached_document.value, nullable=False)
    detached_again = native.handle('rv_dom_document_get_timeline', [P], detached_document.value, nullable=False)
    anim = probe.animation(None, detached, case['duration'])
    native.ok('rv_dom_web_animation_play', [P], anim)
    result = {
        'documentTimeline': {'interfaceName': probe.interface_name(dt), 'currentTimeIsNumber': isinstance(t, float),
                             'duration': probe.time(dt, 'rv_dom_animation_timeline_get_duration')},
        'origins': [{'origin': origin, 'offsetClose': abs(probe.time(made[origin]) - (t - origin)) < CLOSE,
                     'duration': probe.time(made[origin], 'rv_dom_animation_timeline_get_duration'),
                     'interfaceName': probe.interface_name(made[origin]), 'distinct': made[origin] != dt} for origin in case['origins']],
        'futureNegative': probe.time(made[case['futureOrigin']]) < 0,
        'defaultEqual': probe.time(dflt) == t,
        'inactive': {'currentTime': probe.time(detached), 'duration': probe.time(detached, 'rv_dom_animation_timeline_get_duration'),
                     'identity': detached == detached_again,
                     'animation': {'playState': probe.state(anim), 'currentTime': probe.time(anim, 'rv_dom_web_animation_get_current_time'),
                                   'startTime': probe.time(anim, 'rv_dom_web_animation_get_start_time')}},
        'gates': {'maximumFrameRate': hasattr(native.library, 'rv_dom_document_timeline_get_maximum_frame_rate'),
                  'frameRate': hasattr(native.library, 'rv_dom_web_animation_get_frame_rate')
                  or hasattr(native.library, 'rv_dom_web_animation_set_frame_rate')},
    }
    native.ok('rv_dom_web_animation_cancel', [P], anim)
    probe.release_target(anim)
    for handle in list(made.values()) + [dflt, detached, detached_again]:
        probe.release_timeline(handle)
    native.bind('rv_node_release', None, [P])(detached_document.value)
    page.guard('A06 origins')

    # Animations started before one rendering update share its start time; a timeline whose origin is later by
    # syncOrigin gives the same instant a start time smaller by syncOrigin.
    element = page.element('a')
    own = probe.document_timeline(case['syncOrigin'])
    animations = [probe.animation(element, dt, case['duration']), probe.animation(element, dt, case['duration']),
                  probe.animation(element, own, case['duration'])]
    for animation in animations:
        native.ok('rv_dom_web_animation_play', [P], animation)
    a1, a2, a3 = animations
    result['beforeFrame'] = {'pending': [probe.pending(a1), probe.pending(a3)],
                             'startTime': [probe.time(a1, 'rv_dom_web_animation_get_start_time'), probe.time(a3, 'rv_dom_web_animation_get_start_time')]}
    for _ in range(2):
        probe.frame()
    start = [probe.time(a, 'rv_dom_web_animation_get_start_time') for a in animations]
    current = [probe.time(a, 'rv_dom_web_animation_get_current_time') for a in animations]
    result['synchronized'] = {'sameStart': start[0] == start[1], 'started': start[0] is not None and start[2] is not None,
                              'ownStartOffsetClose': None not in start and abs(start[0] - start[2] - case['syncOrigin']) < CLOSE,
                              'currentClose': None not in current and abs(current[0] - current[2]) < CLOSE,
                              'playState': [probe.state(a) for a in animations], 'pending': [probe.pending(a1), probe.pending(a3)]}
    # The qualified engine behaviour itself (animation-timelines-qualified.json): the start time is the document's.
    native.expect(None not in start and start[2] == start[0], 'WebKit: the later-origin animation starts at the document time')
    native.expect(None not in current and abs(current[2] - (current[0] - case['syncOrigin'])) < CLOSE,
                  'WebKit: the later-origin animation reads a current time smaller by originTime')
    diagnostics = {'startTime': start, 'currentTime': current, 'timelines': [probe.time(dt), probe.time(own)]}
    for animation in animations:
        native.ok('rv_dom_web_animation_cancel', [P], animation)
        probe.release_target(animation)
    probe.release_timeline(own)
    probe.release_timeline(dt)
    page.guard('A06 synchronized')
    return result, diagnostics


class ScrollTimelineOptions(ctypes.Structure):
    _fields_ = [('size', U), ('source', ctypes.POINTER(P)), ('axis', I)]


AXES = ['block', 'inline', 'x', 'y']
ABSENT = object()


def computed_value(native, element, prop):
    buffer, length = ctypes.create_string_buffer(512), I()
    native.ok('rv_element_computed_style', [P, ctypes.c_char_p, P, I, ctypes.POINTER(I)], element, prop.encode(), buffer, 512, ctypes.byref(length))
    return buffer.raw[:length.value].decode('utf-8')


class ScrollProbe(Probe):
    def unit(self, handle, fn='rv_dom_animation_timeline_get_current_time'):
        """A timeline or animation time: a number, a CSSNumericValue as value and unit, or None."""
        value = Time()
        self.n.ok(fn, [P, ctypes.POINTER(Time)], handle, ctypes.byref(value))
        if not value.present:
            return None
        if value.tag == 1:
            return {'number': value.arm0}
        self.n.expect(value.tag == 2 and bool(value.arm1), fn + ': a CSSNumericValue arm')
        number = D()
        self.n.ok('rv_dom_css_unit_value_get_value', [P, ctypes.POINTER(D)], value.arm1, ctypes.byref(number))
        unit = self.n.text('rv_dom_css_unit_value_get_unit', [P], value.arm1)
        self.n.bind('rv_dom_css_style_value_release', None, [P])(value.arm1)
        return {'value': number.value, 'unit': unit}

    def scroll_timeline(self, source=ABSENT, axis=None):
        """source ABSENT leaves the options' pointer NULL (the scrolling element); None passes a pointer to NULL."""
        options = ScrollTimelineOptions(ctypes.sizeof(ScrollTimelineOptions), None, AXES.index(axis or 'block'))
        cell = P(source) if source is not ABSENT else None
        if cell is not None:
            options.source = ctypes.pointer(cell)
        result = P()
        self.n.ok('rv_dom_scroll_timeline_create', [P, ctypes.POINTER(ScrollTimelineOptions), ctypes.POINTER(P)], self.page.document,
                  ctypes.byref(options), ctypes.byref(result))
        return result.value

    def source_id(self, timeline):
        source = self.n.handle('rv_dom_scroll_timeline_get_source', [P], timeline)
        if not source:
            return None
        name = self.n.text('rv_dom_element_get_id', [P], source)
        self.n.bind('rv_node_release', None, [P])(source)
        return name

    def opacity(self, element):
        return computed_value(self.n, element, 'opacity')

    def scroll(self, element, top=None, left=None):
        if top is not None:
            self.n.ok('rv_dom_element_set_scroll_top', [P, I], element, top)
        if left is not None:
            self.n.ok('rv_dom_element_set_scroll_left', [P, I], element, left)

    def settle(self):
        for _ in range(2):
            self.frame()


def a07(native, spec):
    """Scroll timelines over the oracle's scrollers; reads after two rendering updates, as the oracle after two frames."""
    page = Page(native, spec['scrollMarkup'])
    probe = ScrollProbe(native, page)
    try:
        s, n, vis, a, b, c = (page.element(name) for name in ('s', 'n', 'vis', 'a', 'b', 'c'))
        scrolling = native.handle('rv_dom_document_get_scrolling_element', [P], page.document, nullable=False)
        tl = {'block': probe.scroll_timeline(s), 'inline': probe.scroll_timeline(s, 'inline'), 'x': probe.scroll_timeline(s, 'x'),
              'y': probe.scroll_timeline(s, 'y'), 'def': probe.scroll_timeline(), 'nullSource': probe.scroll_timeline(None),
              'visible': probe.scroll_timeline(vis), 'nested': probe.scroll_timeline(n)}
        arena, sa = Arena(), P()
        native.ok('rv_dom_element_animate', [P, P, P, ctypes.POINTER(P)], a,
                  arena.keyframes([{'props': {'opacity': '0'}}, {'props': {'opacity': '1'}}]),
                  arena.options(AnimationOptions, KeyframeAnimationOptions, {'fill': 'both'}, tl['block']), ctypes.byref(sa))
        sa = sa.value
        effect = P()
        native.ok('rv_dom_keyframe_effect_create_3', [P, P, P, P, ctypes.POINTER(P)], page.document, b,
                  arena.keyframes([{'props': {'opacity': '0'}}, {'props': {'opacity': '1'}}]),
                  arena.options(EffectOptions, KeyframeEffectOptions, {'fill': 'both'}), ctypes.byref(effect))
        sb = probe.animation(b, tl['inline'], None, effect.value)
        native.ok('rv_dom_web_animation_play', [P], sb)
        page.guard('A07 creation')
        sa_timeline = native.handle('rv_dom_web_animation_get_timeline', [P], sa, nullable=False)
        def_source = native.handle('rv_dom_scroll_timeline_get_source', [P], tl['def'], nullable=False)
        result = {'axes': [AXES[native.integer('rv_dom_scroll_timeline_get_axis', tl[k])] for k in AXES],
                  'source': probe.source_id(tl['block']) == 's', 'nestedSource': probe.source_id(tl['nested']),
                  'defaultSource': def_source == scrolling, 'nullSource': probe.source_id(tl['nullSource']),
                  'visibleSource': probe.source_id(tl['visible']),
                  'duration': probe.unit(tl['block'], 'rv_dom_animation_timeline_get_duration'),
                  'nullDuration': probe.unit(tl['nullSource'], 'rv_dom_animation_timeline_get_duration'),
                  'interfaceName': probe.interface_name(tl['block']), 'animationTimeline': sa_timeline == tl['block']}
        for handle in (def_source, scrolling):
            native.bind('rv_node_release', None, [P])(handle)
        probe.release_timeline(sa_timeline)

        def read():
            return {'times': {k: probe.unit(v) for k, v in tl.items()},
                    'a': {'currentTime': probe.unit(sa, 'rv_dom_web_animation_get_current_time'),
                          'startTime': probe.unit(sa, 'rv_dom_web_animation_get_start_time'), 'playState': probe.state(sa),
                          'opacity': probe.opacity(a)},
                    'b': {'currentTime': probe.unit(sb, 'rv_dom_web_animation_get_current_time'), 'playState': probe.state(sb),
                          'opacity': probe.opacity(b)}}

        probe.settle()
        result['points'] = []
        for point in spec['a07']['points']:
            probe.scroll(s, point['top'], point['left'])
            probe.scroll(n, point['nested'])
            native.ok('rv_host_scroll_to', [P, I, I], page.host, 0, point['root'])
            probe.settle()
            result['points'].append({**point, **read()})
        name, value = b'style', ('height:' + spec['a07']['resizedHeight']).encode('utf-8')
        native.ok('rv_dom_element_set_attribute', [P, ctypes.c_char_p, I, ctypes.c_char_p, I], c, name, len(name), value, len(value))
        probe.settle()
        result['resized'] = {'scrollTop': native.integer('rv_dom_element_get_scroll_top', s), **read()}
        native.ok('rv_dom_element_remove', [P], s)
        probe.settle()
        result['removed'] = read()
        # A style change on the targets: their styles recompute without the inactive animations.
        for target in (a, b):
            native.ok('rv_dom_element_set_attribute', [P, ctypes.c_char_p, I, ctypes.c_char_p, I], target, name, len(name), b'color:red', 9)
        probe.settle()
        result['restyled'] = {'a': probe.opacity(a), 'b': probe.opacity(b)}
        page.guard('A07 reads')
        for animation in (sa, sb):
            native.ok('rv_dom_web_animation_cancel', [P], animation)
            probe.release_target(animation)
        for handle in tl.values():
            probe.release_timeline(handle)
    finally:
        page.close()
    return result


def a07_contract(native, page):
    """Null, receiver, interface, enumeration and thread errors of the ScrollTimeline functions, and the defaults."""
    expect, probe = native.expect, ScrollProbe(native, page)
    create = native.bind('rv_dom_scroll_timeline_create', I, [P, ctypes.POINTER(ScrollTimelineOptions), ctypes.POINTER(P)])
    result, element = P(), page.element('a')
    expect(create(None, None, ctypes.byref(result)) == NULL_ARGUMENT, 'ScrollTimeline NULL document')
    expect(create(page.document, None, None) == NULL_ARGUMENT, 'ScrollTimeline NULL result')
    expect(create(element, None, ctypes.byref(result)) == WRONG_INTERFACE, 'ScrollTimeline on an element receiver')
    text = native.handle('rv_dom_document_create_text_node', [P, ctypes.c_char_p, I], page.document, b'x', 1, nullable=False)
    cell = P(text)
    options = ScrollTimelineOptions(ctypes.sizeof(ScrollTimelineOptions), ctypes.pointer(cell), 0)
    expect(create(page.document, ctypes.byref(options), ctypes.byref(result)) == WRONG_INTERFACE, 'ScrollTimeline source of a text node')
    native.bind('rv_node_release', None, [P])(text)
    options = ScrollTimelineOptions(ctypes.sizeof(ScrollTimelineOptions), None, 9)
    expect(create(page.document, ctypes.byref(options), ctypes.byref(result)) == UNSUPPORTED, 'ScrollTimeline axis out of range')
    # A struct whose size stops before axis takes the IDL default block; NULL options take every default.
    short = ScrollTimelineOptions(ScrollTimelineOptions.axis.offset, None, 3)
    native.ok('rv_dom_scroll_timeline_create', [P, ctypes.POINTER(ScrollTimelineOptions), ctypes.POINTER(P)], page.document,
              ctypes.byref(short), ctypes.byref(result))
    expect(AXES[native.integer('rv_dom_scroll_timeline_get_axis', result.value)] == 'block', 'short options size: axis default block')
    probe.release_timeline(result.value)
    native.ok('rv_dom_scroll_timeline_create', [P, ctypes.POINTER(ScrollTimelineOptions), ctypes.POINTER(P)], page.document, None,
              ctypes.byref(result))
    expect(probe.interface_name(result.value) == 'ScrollTimeline', 'NULL options: a ScrollTimeline')
    status = []
    worker = threading.Thread(target=lambda: status.append(
        native.call('rv_dom_scroll_timeline_get_axis', [P, ctypes.POINTER(I)], result.value, ctypes.byref(I()))))
    worker.start(); worker.join()
    expect(status == [WRONG_THREAD], 'ScrollTimeline.axis off the owning thread')
    probe.release_timeline(result.value)
    document_timeline = page.timeline()
    expect(native.call('rv_dom_scroll_timeline_get_axis', [P, ctypes.POINTER(I)], document_timeline, ctypes.byref(I())) == WRONG_INTERFACE,
           'ScrollTimeline.axis on a DocumentTimeline')
    expect(native.call('rv_dom_scroll_timeline_get_source', [P, ctypes.POINTER(P)], document_timeline, ctypes.byref(P())) == WRONG_INTERFACE,
           'ScrollTimeline.source on a DocumentTimeline')
    probe.release_timeline(document_timeline)

def a06_teardown(native, spec):
    """A second host's document timeline and a DocumentTimeline of its document, both held past rv_host_destroy."""
    page = Page(native, spec['markup'])
    probe = Probe(native, page)
    for _ in range(2):
        probe.frame()
    timeline, own = page.timeline(), probe.document_timeline(100)
    before = probe.time(timeline) is not None
    native.bind('rv_node_release', None, [P])(page.document)
    native.bind('rv_host_destroy', None, [P])(page.host)
    result = {'before': before, 'timeline': probe.time(timeline), 'own': probe.time(own)}
    probe.release_timeline(timeline)
    probe.release_timeline(own)
    return result


def contract_errors(native, page):
    expect, probe = native.expect, Probe(native, page)
    value, result = Time(), P()
    get_time = native.bind('rv_dom_animation_timeline_get_current_time', I, [P, ctypes.POINTER(Time)])
    create = native.bind('rv_dom_document_timeline_create', I, [P, P, ctypes.POINTER(P)])
    expect(get_time(None, ctypes.byref(value)) == NULL_ARGUMENT, 'currentTime NULL timeline')
    timeline = page.timeline()
    expect(get_time(timeline, None) == NULL_ARGUMENT, 'currentTime NULL result')
    expect(create(None, None, ctypes.byref(result)) == NULL_ARGUMENT, 'DocumentTimeline NULL document')
    expect(create(page.document, None, None) == NULL_ARGUMENT, 'DocumentTimeline NULL result')
    expect(create(page.element('a'), None, ctypes.byref(result)) == WRONG_INTERFACE, 'DocumentTimeline on an element receiver')
    status = []
    worker = threading.Thread(target=lambda: status.append(get_time(timeline, ctypes.byref(value))))
    worker.start(); worker.join()
    expect(status == [WRONG_THREAD], 'currentTime off the owning thread')
    # An options struct whose size stops before originTime takes the IDL default 0.
    short = TimelineOptions(4, 5000.0)
    native.ok('rv_dom_document_timeline_create', [P, P, ctypes.POINTER(P)], page.document, ctypes.byref(short), ctypes.byref(result))
    expect(probe.time(result.value) == probe.time(timeline), 'short options size: originTime default 0')
    probe.release_timeline(result.value)
    probe.release_timeline(timeline)


def lock_free(native, page):
    """With the VM-entry crash armed, the DocumentTimeline and ScrollTimeline constructors, the timeline members and an
    animation constructed on a new timeline run unchanged; the effect is constructed before arming."""
    probe = Probe(native, page)
    element = page.element('a')
    effect = probe.effect(element, 1000)
    if not arm_vm_entry_crash(page.directory):
        probe.release_effect(effect)
        return False
    own = probe.document_timeline(250)
    dt = page.timeline()
    native.expect(abs(probe.time(own) - (probe.time(dt) - 250)) < CLOSE, 'armed: origin offset')
    native.expect(probe.time(own, 'rv_dom_animation_timeline_get_duration') is None, 'armed: duration null')
    # The ScrollTimeline constructor lays out the source's document; its members read the cached progress.
    scroll = ScrollProbe(native, page)
    scrolling = scroll.scroll_timeline()
    native.expect(scroll.unit(scrolling, 'rv_dom_animation_timeline_get_duration') == {'value': 100.0, 'unit': 'percent'}, 'armed: scroll duration')
    native.expect(scroll.unit(scrolling) is None, 'armed: the unscrollable root gives no current time')
    native.expect(AXES[native.integer('rv_dom_scroll_timeline_get_axis', scrolling)] == 'block', 'armed: scroll axis')
    source = native.handle('rv_dom_scroll_timeline_get_source', [P], scrolling, nullable=False)
    native.bind('rv_node_release', None, [P])(source)
    probe.release_timeline(scrolling)
    animation = probe.animation(element, own, 1000, effect)
    native.ok('rv_dom_web_animation_pause', [P], animation)
    native.ok('rv_dom_web_animation_set_current_time', [P, ctypes.POINTER(Time)], animation, ctypes.byref(Time(1, 1, 500.0, None)))
    native.expect(probe.time(animation, 'rv_dom_web_animation_get_current_time') == 500, 'armed: seek on a new timeline')
    timeline = native.handle('rv_dom_web_animation_get_timeline', [P], animation, nullable=False)
    native.expect(timeline == own, 'armed: Animation.timeline is the new timeline')
    # finish settles the pending pause task first: cancel would otherwise reject the ready promise, which attempts a
    # VM entry (A03).
    native.ok('rv_dom_web_animation_finish', [P], animation)
    native.ok('rv_dom_web_animation_cancel', [P], animation)
    page.guard('armed timeline calls')
    probe.release_target(animation)
    for handle in (timeline, own, dt):
        probe.release_timeline(handle)
    return True


QUALIFIED = json.loads((FIXTURES / 'animation-timelines-qualified.json').read_text(encoding='utf-8'))['checks']


def compare(native, actual, wanted, failures, path='a06'):
    if isinstance(wanted, dict):
        for key, value in wanted.items():
            compare(native, actual.get(key) if isinstance(actual, dict) else None, value, failures, path + '.' + key)
    elif isinstance(wanted, list) and wanted and isinstance(wanted[0], dict):
        native.assertions += 1
        if not isinstance(actual, list) or len(actual) != len(wanted):
            failures.append({'check': path, 'native': actual, 'chromium': wanted})
            return
        for index, (a, w) in enumerate(zip(actual, wanted)):
            compare(native, a, w, failures, f'{path}[{index}]')
    else:
        native.assertions += 1
        if path in QUALIFIED:
            # Both sides: the native value is WebKit's and the oracle still records Chromium's.
            entry = QUALIFIED[path]
            if actual != entry['webkit'] or wanted != entry['chromium']:
                failures.append({'check': path + ' (qualified)', 'native': actual, 'chromium': wanted})
            return
        # A progress percentage is a ratio of two scroll offsets, which WebKit computes in single precision.
        tolerance = PROGRESS_CLOSE if path.startswith(('a07', 'a08')) else CLOSE
        close = (isinstance(actual, float) and isinstance(wanted, (int, float)) and not isinstance(wanted, bool)
                 and abs(actual - wanted) < tolerance)
        if actual != wanted and not close:
            failures.append({'check': path, 'native': actual, 'chromium': wanted})


def verify(directory, arm=True):
    spec = json.loads((FIXTURES / 'animation-timelines-cases.json').read_text(encoding='utf-8'))
    oracle = json.loads((FIXTURES / 'animation-timelines-oracle.json').read_text(encoding='utf-8'))
    native = Native(directory)
    native.expect(native.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
    has = native.bind('rv_abi_has', I, [ctypes.c_char_p])
    for capability in [b'dom:AnimationTimeline', b'dom:DocumentTimeline', b'dom-constructor:DocumentTimeline', b'dom:ScrollTimeline',
                       b'dom-constructor:ScrollTimeline']:
        native.expect(has(capability) == 1, 'rv_abi_has ' + capability.decode())
    page = Page(native, spec['markup'])
    page.directory = directory
    failures, armed, actual = [], False, {}
    try:
        title = native.text('rv_dom_document_get_title', [P], page.document)
        native.expect(title != 'script ran', 'the page script did not run')
        actual['a06'], actual['diagnostics'] = a06(native, page, spec)
        contract_errors(native, page)
        a07_contract(native, page)
        page.guard('contract errors')
        armed = arm and lock_free(native, page)
        if armed:
            control = subprocess.run([sys.executable, '-I', '-X', 'utf8', str(Path(__file__).with_name('web_animations.py')),
                                      '--native-directory', str(directory), '--vm-entry-control'], capture_output=True, text=True, timeout=120)
            native.expect(control.returncode not in (0, 3) and 'VM_ENTRY_CONTROL_SURVIVED' not in control.stdout,
                          'the armed VM-entry crash aborts a page load (control exit ' + str(control.returncode) + ')')
        native.expect(native.text('rv_dom_document_get_title', [P], page.document) == title, 'no script ran')
    finally:
        if armed:
            arm_vm_entry_crash(directory, False)
        page.close()
    actual['a06']['teardown'] = a06_teardown(native, spec)
    actual['a07'] = a07(native, spec)
    for group in ('a06', 'a07'):
        compare(native, actual[group], oracle[group], failures, group)
    return native, actual, failures, oracle['browser'], armed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence')
    parser.add_argument('--diagnose-without-vm-entry-crash', action='store_true')
    args = parser.parse_args()
    native, actual, failures, browser, armed = verify(args.native_directory, not args.diagnose_without_vm_entry_crash)
    if args.evidence:
        Path(args.evidence).write_text(json.dumps({'oracle': browser, 'assertions': native.assertions, 'failures': failures,
                                                   'vmEntryCrashArmed': armed, 'results': actual}, indent=1) + '\n', encoding='utf-8')
    for failure in failures:
        print('MISMATCH', json.dumps(failure))
    if failures:
        raise SystemExit(f'{len(failures)} checks differ from {browser}')
    print(f'PASS animation timelines: {native.assertions} assertions against {browser}; VM-entry crash armed: {armed}')


if __name__ == '__main__':
    main()
