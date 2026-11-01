"""#56 (G11) intersection observation probe against an actual runtime directory. Replays
tests/fixtures/intersection-observation-cases.json through rv_host_observe_intersection_entries, rv_observer_take_records,
rv_observer_disconnect and rv_host_now, and compares each segment's deliveries, per observer and in order, and their
final entry values with the Chromium oracle tests/fixtures/intersection-observation-oracle.json. Every step that changes
layout is followed by rv_host_update. Entry times are checked against rv_host_now around each update, never against
absolute values. Also checks argument, root and thread errors, the unchanged v15 rv_host_observe_intersection, and
teardown: a target held past removal, a target released while observed, document replacement, release inside a
callback and takeRecords after disconnect. The order between observers is recorded against
tests/fixtures/intersection-observation-qualified.json."""

import argparse
import ctypes
import json
import math
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, P, I, Utf8

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
OK, NULL_ARGUMENT, WRONG_THREAD, DOM_EXCEPTION, NOT_ELEMENT, UNSUPPORTED, DETACHED, WRONG_HOST = 0, -1, -2, -3, -4, -9, -10, -12
ABI = 59
D = ctypes.c_double
RECT_TOLERANCE, RATIO_TOLERANCE, TIME_TOLERANCE = 0.01, 0.001, 0.001


class Entry(ctypes.Structure):
    _fields_ = [('size', I), ('isIntersecting', I), ('target', P), ('time', D), ('hasRootBounds', I), ('reserved', I)] + [
        (name, D) for name in ['rootX', 'rootY', 'rootWidth', 'rootHeight', 'boundsX', 'boundsY', 'boundsWidth', 'boundsHeight',
                               'intersectionX', 'intersectionY', 'intersectionWidth', 'intersectionHeight', 'intersectionRatio']]


ENTRIES = ctypes.CFUNCTYPE(None, P, P, ctypes.POINTER(Entry), I)
INTERSECT = ctypes.CFUNCTYPE(None, P, P, I, D)
RESIZE = ctypes.CFUNCTYPE(None, P, P, D, D)


def number(value):
    return int(value) if float(value).is_integer() else value


def utf8(text):
    if text is None:
        return None, 0
    data = text.encode('utf-8')
    return (ctypes.c_uint8 * max(len(data), 1)).from_buffer_copy(data or b'\0'), len(data)


class Scene:
    """A host with the cases' markup and the bindings the steps use."""

    def __init__(self, native, cases):
        n = self.n = native
        self.host = n.bind('rv_host_create', P, [I, I])(*cases['viewport'])
        n.expect(bool(self.host), 'host')
        n.ok('rv_host_load_html', [P, Utf8], self.host, cases['markup'].encode('utf-8'))
        self.by_id = n.bind('rv_document_get_element_by_id', P, [P, Utf8])
        self.release_node = n.bind('rv_node_release', None, [P])
        self.release_observer = n.bind('rv_observer_release', None, [P])
        self.create_raw = n.bind('rv_host_observe_intersection_entries', I,
                                 [P, ENTRIES, P, P, P, I, P, I, ctypes.POINTER(D), I, ctypes.POINTER(P)])
        self.take_raw = n.bind('rv_observer_take_records', I, [P, ENTRIES, P])
        self.now_raw = n.bind('rv_host_now', I, [P, ctypes.POINTER(D)])
        self.nodes, self.observers, self.names, self.callbacks = {}, {}, {}, []
        self.statuses, self.segments, self.times, self.segment = [], [], [], []
        self.pair = None
        self.held = []
        for identifier in ['far', 's', 'sp', 'u', 'x', 'c', 'cp', 'v']:
            self.nodes[identifier] = self.by_id(self.host, identifier.encode())
            n.expect(bool(self.nodes[identifier]), 'element ' + identifier)
        self.nodes['#body'] = n.bind('rv_document_body', P, [P])(self.host)

    def node_id(self, target):
        buffer, length = ctypes.create_string_buffer(64), I()
        self.n.ok('rv_element_get_attribute', [P, ctypes.c_char_p, P, I, ctypes.POINTER(I)], target, b'id', buffer, 64, ctypes.byref(length))
        return buffer.raw[:length.value].decode('utf-8') if length.value >= 0 else None

    def now(self):
        value = D()
        self.n.expect(self.now_raw(self.host, ctypes.byref(value)) == OK, 'rv_host_now')
        return value.value

    def entry(self, e):
        self.n.expect(e.size == ctypes.sizeof(Entry), 'entry size')
        self.n.expect(e.hasRootBounds == 1, 'same-origin root bounds')
        rect = lambda prefix: [number(getattr(e, prefix + k)) for k in ['X', 'Y', 'Width', 'Height']]
        return {'t': self.node_id(e.target), 'time': e.time, 'root': rect('root'), 'bounds': rect('bounds'),
                'intersection': rect('intersection'), 'intersecting': bool(e.isIntersecting), 'ratio': number(e.intersectionRatio)}

    def entries(self, pointer, count):
        return [self.entry(pointer[i]) for i in range(count)]

    def take(self, name):
        taken = []
        sink = ENTRIES(lambda c, o, p, count: taken.extend(self.entries(p, count)))
        self.n.expect(self.take_raw(self.observers[name], sink, None) == OK, 'take records ' + name)
        return taken

    def create(self, name, init):
        def deliver(context, observer, pointer, count, name=name):
            es = self.entries(pointer, count)
            if self.pair and name in self.pair:
                a, b = self.pair
                other = b if name == a else a
                self.pair = None
                taken = self.take(other)
                self.segment.append({'o': 'pair:' + a + '+' + b, 'entries': {a: es if name == a else taken, b: es if name == b else taken}})
                return
            self.segment.append({'o': name, 'entries': es})
        callback = ENTRIES(deliver)
        self.callbacks.append(callback)
        root = init.get('root')
        root_node = None if root is None else self.document() if root == '#document' else self.nodes[root]
        margin, margin_length = utf8(init.get('rootMargin'))
        scroll, scroll_length = utf8(init.get('scrollMargin'))
        thresholds = init.get('threshold')
        array = (D * len(thresholds))(*thresholds) if thresholds else None
        result = P()
        status = self.create_raw(self.host, callback, None, root_node, margin, margin_length, scroll, scroll_length, array,
                                 len(thresholds or []), ctypes.byref(result))
        if status == OK:
            self.n.expect(bool(result.value), 'observer')
            self.observers[name] = result.value
            self.statuses.append('ok')
        else:
            self.n.expect(not result.value and status == DOM_EXCEPTION, 'failed create: ' + str(status))
            self.statuses.append(self.n.exception().split(':')[0] if self.n.exception() else 'unknown')

    def document(self):
        if '#document' not in self.nodes:
            self.nodes['#document'] = self.n.bind('rv_host_document', P, [P])(self.host)
        return self.nodes['#document']

    def update(self):
        before = self.now()
        self.n.expect(self.n.call('rv_host_update', [P], self.host) == OK, 'update')
        self.times.append([before, self.now()])
        self.segments.append(self.segment)
        self.segment = []

    def step(self, step):
        n, kind, args = self.n, step[0], step[1:]
        if kind == 'create':
            self.create(*args)
        elif kind == 'observe':
            n.expect(n.call('rv_observer_observe', [P, P], self.observers[args[0]], self.nodes[args[1]]) == OK, 'observe')
        elif kind == 'unobserve':
            n.expect(n.call('rv_observer_unobserve', [P, P], self.observers[args[0]], self.nodes[args[1]]) == OK, 'unobserve')
        elif kind == 'disconnect':
            n.expect(n.call('rv_observer_disconnect', [P], self.observers[args[0]]) == OK, 'disconnect')
        elif kind == 'take':
            self.segment.append({'o': 'take:' + args[0], 'entries': self.take(args[0])})
        elif kind == 'pair':
            self.pair = (args[0], args[1])
        elif kind == 'scroll':
            n.ok('rv_host_scroll_to', [P, I, I], self.host, args[0], args[1])
        elif kind == 'scrollTop':
            n.ok('rv_dom_element_set_scroll_top', [P, I], self.nodes[args[0]], args[1])
        elif kind == 'style':
            n.ok('rv_element_set_style', [P, ctypes.c_char_p, Utf8, I], self.nodes[args[0]], args[1].encode(), args[2].encode(), 0)
        elif kind == 'element':
            element = n.bind('rv_document_create_element', P, [P, ctypes.c_char_p])(self.host, b'div')
            n.ok('rv_element_set_attribute', [P, ctypes.c_char_p, Utf8], element, b'id', args[0].encode())
            self.nodes[args[0]] = element
        elif kind == 'append':
            parent = self.nodes[args[0]] if args[0] != '#body' else self.body()
            n.ok('rv_node_append_child', [P, P], parent, self.nodes[args[1]])
        elif kind == 'remove':
            n.ok('rv_node_remove', [P], self.nodes[args[0]])
        elif kind == 'update':
            self.update()
        else:
            raise AssertionError('unknown step ' + kind)

    def body(self):
        return self.nodes['#body']

    def close(self):
        for observer in self.observers.values():
            self.release_observer(observer)
        for node in self.nodes.values():
            if node:
                self.release_node(node)
        self.n.bind('rv_host_destroy', None, [P])(self.host)


def run(native, cases, scenario):
    scene = Scene(native, cases)
    try:
        # As in the oracle: one rendering update before the first step.
        scene.update()
        scene.segments.clear(); scene.times.clear()
        for step in scenario['steps']:
            scene.step(step)
        scene.segments.append(scene.segment)
        return {'statuses': scene.statuses, 'segments': scene.segments, 'times': scene.times}
    finally:
        scene.close()


def normalized(segments):
    """Each segment's deliveries grouped by observer, in delivery order within an observer."""
    return [sorted(segment, key=lambda delivery: delivery['o']) for segment in segments]


def close_values(a, b, tolerance):
    return a is None and b is None or (a is not None and b is not None and len(a) == len(b)
                                       and all(math.isclose(x, y, abs_tol=tolerance) for x, y in zip(a, b)))


def same_entry(a, b):
    return (a['t'] == b['t'] and a['intersecting'] == b['intersecting'] and math.isclose(a['ratio'], b['ratio'], abs_tol=RATIO_TOLERANCE)
            and all(close_values(a[k], b[k], RECT_TOLERANCE) for k in ['root', 'bounds', 'intersection']))


def entry_lists(delivery):
    entries = delivery['entries']
    return list(entries.values()) if isinstance(entries, dict) else [entries]


def check_times(native, name, result):
    """Times lie within rv_host_now (performance.now) around the update that queued them and never decrease."""
    last = -math.inf
    for index, segment in enumerate(result['segments']):
        for delivery in segment:
            if delivery['o'].startswith('take:'):
                continue
            for entries in entry_lists(delivery):
                for e in entries:
                    before, after = result['times'][index]
                    native.expect(before - TIME_TOLERANCE <= e['time'] <= after + TIME_TOLERANCE, name + ': entry time within its update')
                    native.expect(e['time'] >= last - TIME_TOLERANCE, name + ': entry times never decrease')
                    last = e['time']


def compare(native, name, expected, actual, report, roots=None):
    native.expect(actual['statuses'] == expected['statuses'], name + ': statuses ' + str(actual['statuses']))
    a, e = normalized(actual['segments']), normalized(expected['segments'])
    native.expect(len(a) == len(e), name + ': segment count')
    for index, (sa, se) in enumerate(zip(a, e)):
        native.expect([d['o'] for d in sa] == [d['o'] for d in se], name + ' segment ' + str(index) + ': ' + str([d['o'] for d in sa]) + ' vs ' + str([d['o'] for d in se]))
        for da, de in zip(sa, se):
            if roots and da['o'] in roots:
                # Qualified: WebKit's root bounds include the scroll margin (intersection-observation-qualified.json).
                de = {'o': de['o'], 'entries': [dict(entry, root=roots[da['o']]) for entry in de['entries']]}
            for la, le in zip(entry_lists(da), entry_lists(de)):
                native.expect(len(la) == len(le) and all(same_entry(x, y) for x, y in zip(la, le)),
                              name + ' segment ' + str(index) + ' ' + da['o'] + ': ' + json.dumps(la) + ' vs ' + json.dumps(le))
    report['scenarios'][name] = {'segments': len(a), 'deliveries': sum(len(s) for s in a)}


def replay(native, cases, oracle, report):
    results = {}
    qualified = json.loads((FIXTURES / 'intersection-observation-qualified.json').read_text(encoding='utf-8'))
    for scenario in cases['scenarios']:
        name = scenario['name']
        results[name] = result = run(native, cases, scenario)
        compare(native, name, oracle['scenarios'][name], result, report, qualified['rootBounds'].get(name))
        check_times(native, name, result)
    for scenario in cases['qualifiedScenarios']:
        name = scenario['name']
        result = run(native, cases, scenario)
        check_times(native, name, result)
        if name == 'observerOrder':
            order = [[d['o'] for d in segment] for segment in result['segments']]
            native.expect(order == qualified[name]['webkit'], name + ': WebKit order ' + str(order))
            # Every observer's own deliveries still match Chromium's.
            compare(native, name, oracle['qualified'][name], result, report)
            report['qualified'][name] = {'webkit': order, 'chromium': [[d['o'] for d in s] for s in oracle['qualified'][name]['segments']]}
        else:
            # The recorded WebKit entries hold; Chromium's differ as the qualified file describes.
            compare(native, name, qualified[name], result, report)
            report['qualified'][name] = {'webkit': summary(result['segments']), 'chromium': summary(oracle['qualified'][name]['segments'])}
    return results


def summary(segments):
    return [[{'o': d['o'], 'entries': [{k: e[k] for k in ['t', 'intersecting', 'ratio', 'root', 'bounds', 'intersection']} for e in d['entries']]}
             for d in segment] for segment in normalized(segments)]


def errors(native, cases, report):
    """Statuses of the new exports, and thread checks."""
    scene = Scene(native, cases)
    n = native
    try:
        callback = ENTRIES(lambda c, o, p, count: None)
        result = P()
        create = scene.create_raw

        def status(host=scene.host, cb=callback, root=None, margin=(None, 0), scroll=(None, 0), thresholds=None, count=0, out=True):
            result.value = 12345
            code = create(host, cb, None, root, margin[0], margin[1], scroll[0], scroll[1], thresholds, count, ctypes.byref(result) if out else None)
            if out:
                n.expect(code != OK or bool(result.value), 'observer on OK')
                if code != OK:
                    n.expect(not result.value, 'NULL observer on error ' + str(code))
                elif result.value:
                    scene.release_observer(result.value)
            return code

        good, _ = utf8('0px')
        n.expect(status(host=None) == NULL_ARGUMENT, 'NULL host')
        n.expect(status(cb=ctypes.cast(None, ENTRIES)) == NULL_ARGUMENT, 'NULL callback')
        n.expect(status(out=False) == NULL_ARGUMENT, 'NULL observer out')
        n.expect(status(margin=(None, 3)) == NULL_ARGUMENT, 'NULL root margin with a length')
        n.expect(status(scroll=(None, 3)) == NULL_ARGUMENT, 'NULL scroll margin with a length')
        n.expect(status(margin=(good, -1)) == NULL_ARGUMENT, 'negative margin length')
        n.expect(status(count=2) == NULL_ARGUMENT, 'NULL thresholds with a count')
        n.expect(status(thresholds=(D * 1)(0.5), count=-1) == NULL_ARGUMENT, 'negative threshold count')
        bad, bad_length = utf8('bogus')
        n.expect(status(margin=(bad, bad_length)) == DOM_EXCEPTION and n.exception().startswith('SyntaxError'), 'invalid root margin')
        n.expect(status(scroll=(bad, bad_length)) == DOM_EXCEPTION and n.exception().startswith('SyntaxError'), 'invalid scroll margin')
        n.expect(status(thresholds=(D * 1)(1.5), count=1) == DOM_EXCEPTION and n.exception().startswith('RangeError'), 'threshold above 1')
        n.expect(status(thresholds=(D * 1)(float('nan')), count=1) == DOM_EXCEPTION and n.exception().startswith('RangeError'), 'NaN threshold')
        invalid = (ctypes.c_uint8 * 2)(0xff, 0xfe)
        n.expect(status(margin=(invalid, 2)) == DOM_EXCEPTION and n.exception().startswith('SyntaxError'), 'margin of invalid UTF-8')
        embedded = (ctypes.c_uint8 * 7)(*b'1px\x002px')
        n.expect(status(margin=(embedded, 7)) == DOM_EXCEPTION, 'margin with an embedded NUL')
        n.expect(status(margin=(good, 3)) == OK, 'length-delimited margin')
        n.expect(status(margin=(utf8('10px junk')[0], 4)) == OK, 'margin read to its length, not to NUL')
        text = n.bind('rv_document_create_comment', P, [P, Utf8])(scene.host, b'text')
        n.expect(status(root=text) == NOT_ELEMENT, 'comment root')
        scene.release_node(text)
        other = n.bind('rv_host_create', P, [I, I])(100, 100)
        n.ok('rv_host_load_html', [P, Utf8], other, b'<div id=o></div>')
        foreign = scene.by_id(other, b'o')
        foreign_document = n.bind('rv_host_document', P, [P])(other)
        n.expect(status(root=foreign) == WRONG_HOST, 'root of another host')
        n.expect(status(root=foreign_document) == WRONG_HOST, 'document of another host')
        n.ok('rv_host_load_html', [P, Utf8], other, b'<p></p>')
        n.expect(status(host=other, root=foreign) == DETACHED, 'root of a replaced document')
        n.expect(status(host=other, root=foreign_document) == DETACHED, 'replaced document root')
        scene.release_node(foreign); scene.release_node(foreign_document)
        n.bind('rv_host_destroy', None, [P])(other)
        n.expect(status(root=scene.document()) == OK, 'document root')
        n.expect(status(root=scene.nodes['s']) == OK, 'element root')
        # Thread checks.
        outcome = {}

        def off_thread():
            out = P()
            outcome['create'] = create(scene.host, callback, None, None, None, 0, None, 0, None, 0, ctypes.byref(out))
            outcome['observer'] = out.value
            value = D()
            outcome['now'] = scene.now_raw(scene.host, ctypes.byref(value))
            outcome['take'] = scene.take_raw(observer, callback, None)
        observer = P()
        n.expect(create(scene.host, callback, None, None, None, 0, None, 0, None, 0, ctypes.byref(observer)) == OK, 'observer for thread checks')
        observer = observer.value
        thread = threading.Thread(target=off_thread)
        thread.start(); thread.join()
        n.expect(outcome == {'create': WRONG_THREAD, 'observer': None, 'now': WRONG_THREAD, 'take': WRONG_THREAD}, 'wrong thread ' + str(outcome))
        n.expect(scene.take_raw(None, callback, None) == NULL_ARGUMENT, 'take records of NULL')
        n.expect(scene.take_raw(observer, ctypes.cast(None, ENTRIES), None) == NULL_ARGUMENT, 'take records without a sink')
        n.expect(scene.now_raw(None, ctypes.byref(D())) == NULL_ARGUMENT and scene.now_raw(scene.host, None) == NULL_ARGUMENT, 'now NULL')
        resize = n.bind('rv_host_observe_resize', P, [P, RESIZE, P])
        rcb = RESIZE(lambda c, t, w, h: None)
        ro = resize(scene.host, rcb, None)
        called = []
        sink = ENTRIES(lambda c, o, p, count: called.append(count))
        n.expect(scene.take_raw(ro, sink, None) == UNSUPPORTED and not called, 'take records of a resize observer')
        scene.release_observer(ro)
        scene.release_observer(observer)
        n.expect(n.bind('rv_abi_version', I, [])() == ABI, 'ABI version')
        n.expect(n.bind('rv_abi_has', I, [ctypes.c_char_p])(b'intersection-entries') == 1, 'intersection-entries feature')
        report['errors'] = 'checked'
    finally:
        scene.close()


def clock(native, cases, report):
    """rv_host_now is monotonic in whole milliseconds, frozen for entries of one update, and keeps its origin over a new document."""
    scene = Scene(native, cases)
    n = native
    try:
        values = [scene.now() for _ in range(50)]
        n.expect(all(b >= a for a, b in zip(values, values[1:])) and values[0] >= 0, 'monotonic now')
        n.expect(all(float(v).is_integer() for v in values), 'whole milliseconds')
        scene.create('i', {'threshold': [0]}); scene.create('j', {'root': '#document', 'threshold': [0]})
        scene.step(['observe', 'i', 'far']); scene.step(['observe', 'j', 'far']); scene.update()
        times = [e['time'] for d in scene.segments[-1] for e in d['entries']]
        n.expect(len(times) == 2 and times[0] == times[1], 'one frozen time per update')
        before = scene.now()
        n.ok('rv_host_load_html', [P, Utf8], scene.host, cases['markup'].encode('utf-8'))
        after = scene.now()
        report['clock'] = {'beforeReplacement': before, 'afterReplacement': after}
        n.expect(after >= before, 'a replaced document keeps the time origin')
        for name in ['i', 'j']:
            scene.release_observer(scene.observers.pop(name))
    finally:
        scene.close()


def legacy(native, cases, report, oracle):
    """The v15 rv_host_observe_intersection delivers as before, and its records reach rv_observer_take_records."""
    scene = Scene(native, cases)
    n = native
    try:
        log = []
        callback = INTERSECT(lambda c, t, i, r: log.append([scene.node_id(t), i, number(round(r, 4))]))
        make = n.bind('rv_host_observe_intersection', P, [P, INTERSECT, P, ctypes.c_char_p, ctypes.POINTER(D), I])
        observer = make(scene.host, callback, None, b'0px', (D * 3)(0, 0.5, 1), 3)
        n.expect(bool(observer), 'v15 observer')
        n.expect(not make(scene.host, callback, None, b'bogus', None, 0), 'v15 invalid margin')
        n.ok('rv_observer_observe', [P, P], observer, scene.nodes['far'])
        scene.update()
        n.ok('rv_host_scroll_to', [P, I, I], scene.host, 0, 200)
        scene.update()
        expected = [[e['t'], int(e['intersecting']), number(round(e['ratio'], 4))] for s in oracle['segments'][:2] for d in s for e in d['entries']]
        n.expect(log == expected, 'v15 deliveries ' + str(log))
        taken = []
        sink = ENTRIES(lambda c, o, p, count: taken.append(count))
        n.expect(scene.take_raw(observer, sink, None) == OK and taken == [0], 'v15 take records')
        scene.release_observer(observer)
        report['legacy'] = log
    finally:
        scene.close()


def teardown(native, cases, report):
    n = native
    retain = n.bind('rv_node_retain', P, [P])
    collect = n.bind('rv_collect_garbage', None, [])
    cases_run = {}

    # A target retained from an entry outlives its removal and the observer.
    scene = Scene(n, cases)
    try:
        held = []

        def keep(c, o, p, count):
            for i in range(count):
                held.append(retain(p[i].target))
        callback = ENTRIES(keep)
        out = P()
        n.expect(scene.create_raw(scene.host, callback, None, None, None, 0, None, 0, None, 0, ctypes.byref(out)) == OK, 'held observer')
        n.ok('rv_observer_observe', [P, P], out.value, scene.nodes['s'])
        scene.update()
        n.ok('rv_node_remove', [P], scene.nodes['s'])
        scene.update()
        scene.release_observer(out.value)
        collect()
        n.expect(len(held) == 2 and all(scene.node_id(h) == 's' for h in held), 'held targets readable past removal and release ' + str([len(held)] + [scene.node_id(h) for h in held]))
        for h in held:
            scene.release_node(h)
        cases_run['heldTargetPastRemoval'] = len(held)
    finally:
        scene.close()

    # A target whose every handle is released while observed and disconnected leaves no stale entry.
    scene = Scene(n, cases)
    try:
        seen = []
        callback = ENTRIES(lambda c, o, p, count: seen.extend(scene.node_id(p[i].target) for i in range(count)))
        out = P()
        n.expect(scene.create_raw(scene.host, callback, None, None, None, 0, None, 0, None, 0, ctypes.byref(out)) == OK, 'transient observer')
        element = n.bind('rv_document_create_element', P, [P, ctypes.c_char_p])(scene.host, b'div')
        n.ok('rv_element_set_attribute', [P, ctypes.c_char_p, Utf8], element, b'id', b'tmp')
        n.ok('rv_node_append_child', [P, P], scene.body(), element)
        n.ok('rv_observer_observe', [P, P], out.value, element)
        scene.update()
        n.ok('rv_node_remove', [P], element)
        watch = n.bind('rv_node_watch', P, [P])(element)
        scene.release_node(element)
        for _ in range(3):
            n.bind('rv_run_loop_cycle', I, [I])(10)
            collect()
        scene.update(); scene.update()
        alive = n.bind('rv_watch_alive', I, [P])(watch)
        n.bind('rv_watch_release', None, [P])(watch)
        n.expect(seen[0] == 'tmp' and all(s in ('tmp',) for s in seen), 'only live targets delivered ' + str(seen))
        taken = []
        sink = ENTRIES(lambda c, o, p, count: taken.append(count))
        n.expect(scene.take_raw(out.value, sink, None) == OK and taken == [0], 'no queued records for a collected target')
        scene.release_observer(out.value)
        cases_run['releasedTarget'] = {'deliveries': seen, 'targetCollected': alive == 0}
    finally:
        scene.close()

    # Document replacement: the observer of the old document never delivers again and stays releasable.
    scene = Scene(n, cases)
    try:
        seen = []
        callback = ENTRIES(lambda c, o, p, count: seen.append(count))
        out = P()
        n.expect(scene.create_raw(scene.host, callback, None, scene.nodes['s'], None, 0, None, 0, None, 0, ctypes.byref(out)) == OK, 'old-document observer')
        n.ok('rv_observer_observe', [P, P], out.value, scene.nodes['u'])
        scene.update()
        n.ok('rv_host_load_html', [P, Utf8], scene.host, cases['markup'].encode('utf-8'))
        scene.update(); scene.update()
        n.expect(seen == [1], 'no delivery after document replacement ' + str(seen))
        taken = []
        sink = ENTRIES(lambda c, o, p, count: taken.append(count))
        n.expect(scene.take_raw(out.value, sink, None) == OK and taken == [0], 'take records after replacement')
        n.expect(n.call('rv_observer_disconnect', [P], out.value) == OK, 'disconnect after replacement')
        scene.release_observer(out.value)
        cases_run['documentReplacement'] = seen
    finally:
        scene.close()

    # Release inside a callback stops it and the other observers still deliver; takeRecords after disconnect is empty.
    scene = Scene(n, cases)
    try:
        log = []
        observers = {}

        def first(c, o, p, count):
            log.append('first')
            scene.release_observer(observers.pop('first'))
        cb1 = ENTRIES(first)
        cb2 = ENTRIES(lambda c, o, p, count: log.append('second'))
        for name, cb in [('first', cb1), ('second', cb2)]:
            out = P()
            n.expect(scene.create_raw(scene.host, cb, None, None, None, 0, None, 0, None, 0, ctypes.byref(out)) == OK, name)
            observers[name] = out.value
            n.ok('rv_observer_observe', [P, P], out.value, scene.nodes['far'])
        scene.update()
        n.ok('rv_host_scroll_to', [P, I, I], scene.host, 0, 200)
        scene.update()
        n.expect(log == ['first', 'second', 'second'], 'release inside a callback ' + str(log))
        n.expect(n.call('rv_observer_disconnect', [P], observers['second']) == OK, 'disconnect')
        n.ok('rv_host_scroll_to', [P, I, I], scene.host, 0, 0)
        taken = []
        sink = ENTRIES(lambda c, o, p, count: taken.append(count))
        n.expect(scene.take_raw(observers['second'], sink, None) == OK and taken == [0], 'take records after disconnect')
        scene.update()
        n.expect(log == ['first', 'second', 'second'], 'no delivery after disconnect')
        scene.release_observer(observers.pop('second'))
        cases_run['releaseInCallback'] = log
    finally:
        scene.close()

    # Host destroy after releasing its observers; a held target stays readable.
    scene = Scene(n, cases)
    held = []
    callback = ENTRIES(lambda c, o, p, count: held.extend(retain(p[i].target) for i in range(count)))
    out = P()
    n.expect(scene.create_raw(scene.host, callback, None, scene.document(), None, 0, None, 0, None, 0, ctypes.byref(out)) == OK, 'destroy observer')
    n.ok('rv_observer_observe', [P, P], out.value, scene.nodes['v'])
    scene.update()
    scene.observers['destroy'] = out.value
    scene.close()
    n.expect(len(held) == 1, 'held target before destroy')
    scene.release_node(held[0])
    cases_run['hostDestroy'] = 'released'
    report['teardown'] = cases_run


def verify(directory):
    native = Native(directory)
    cases = json.loads((FIXTURES / 'intersection-observation-cases.json').read_text(encoding='utf-8'))
    oracle = json.loads((FIXTURES / 'intersection-observation-oracle.json').read_text(encoding='utf-8'))
    report = {'oracleBrowser': oracle['browser'], 'scenarios': {}, 'qualified': {}}
    results = replay(native, cases, oracle, report)
    errors(native, cases, report)
    clock(native, cases, report)
    legacy(native, cases, report, oracle['scenarios']['implicitRoot'])
    teardown(native, cases, report)
    report['assertions'] = native.assertions
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--report')
    args = parser.parse_args()
    report = verify(args.native_directory)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('PASS intersection_observation: ' + str(report['assertions']) + ' assertions, ' + str(len(report['qualified'])) + ' qualified', flush=True)


if __name__ == '__main__':
    main()
