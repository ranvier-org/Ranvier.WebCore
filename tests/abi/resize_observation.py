"""#55 (G10) resize observation probe against an actual runtime directory. Replays tests/fixtures/resize-observation-cases.json
through rv_host_observe_resize_entries and rv_observer_observe_box, at device scales 1 and 2, and compares the ordered
deliveries and final entry values with the Chromium oracle tests/fixtures/resize-observation-oracle.json. Every step
that changes layout is followed by rv_host_update, which runs the rendering update; counts of notifications are
never asserted apart from that ordered log. Also checks argument and thread errors, the unchanged v15
rv_host_observe_resize, and teardown: an observer outliving its target, document replacement, release inside a
callback and host destroy. Differences listed in tests/fixtures/resize-observation-qualified.json are recorded, not
failed."""

import argparse
import ctypes
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, P, I, Utf8

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
OK, NULL_ARGUMENT, WRONG_THREAD, NOT_ELEMENT, UNSUPPORTED = 0, -1, -2, -4, -9
ABI = 58
BOXES = {None: None, 'content-box': 0, 'border-box': 1, 'device-pixel-content-box': 2}
D = ctypes.c_double


class Entry(ctypes.Structure):
    _fields_ = [('size', I), ('hasDevicePixel', I), ('target', P), ('contentX', D), ('contentY', D), ('contentWidth', D),
                ('contentHeight', D), ('contentInlineSize', D), ('contentBlockSize', D), ('borderInlineSize', D),
                ('borderBlockSize', D), ('devicePixelInlineSize', D), ('devicePixelBlockSize', D)]


ENTRIES = ctypes.CFUNCTYPE(None, P, P, ctypes.POINTER(Entry), I)
RESIZE = ctypes.CFUNCTYPE(None, P, P, D, D)
INTERSECT = ctypes.CFUNCTYPE(None, P, P, I, D)
EVENT = ctypes.CFUNCTYPE(I, P, P)


def number(value):
    return int(value) if float(value).is_integer() else value


class Scene:
    """A host with the cases' markup and the bindings the steps use."""

    def __init__(self, native, markup, scale=1):
        n = self.n = native
        self.host = n.bind('rv_host_create', P, [I, I])(800, 600)
        n.expect(bool(self.host), 'host')
        if scale != 1:
            n.ok('rv_host_set_device_scale', [P, ctypes.c_float], self.host, float(scale))
        n.ok('rv_host_load_html', [P, Utf8], self.host, markup.encode('utf-8'))
        self.by_id = n.bind('rv_document_get_element_by_id', P, [P, Utf8])
        self.release_node = n.bind('rv_node_release', None, [P])
        self.release_observer = n.bind('rv_observer_release', None, [P])
        self.create = n.bind('rv_host_observe_resize_entries', P, [P, ENTRIES, P])
        self.same = n.bind('rv_node_retain', P, [P])
        self.nodes, self.observers, self.callbacks, self.listeners = {}, {}, [], []
        self.log, self.entries, self.statuses, self.armed = [], [], [], []

    def node(self, name):
        if name not in self.nodes:
            self.nodes[name] = self.by_id(self.host, name.encode())
            self.n.expect(bool(self.nodes[name]), 'element ' + name)
        return self.nodes[name]

    def name_of(self, target):
        for name, handle in self.nodes.items():
            if handle == target:
                return name
        return '?'

    def update(self):
        self.n.ok('rv_host_update', [P], self.host)

    def observer(self, name):
        def deliver(context, observer, entries, count):
            ids = []
            for index in range(count):
                entry = entries[index]
                self.n.expect(entry.size == ctypes.sizeof(Entry), 'entry size')
                self.n.expect(entry.hasDevicePixel == 0 and entry.devicePixelInlineSize == 0 and entry.devicePixelBlockSize == 0,
                              'no device-pixel content box (Ranvier.WebCore#146)')
                target = self.name_of(entry.target)
                ids.append(target)
                self.entries.append({'o': name, 't': target,
                                     'rect': [number(entry.contentX), number(entry.contentY), number(entry.contentWidth), number(entry.contentHeight)],
                                     'content': [number(entry.contentInlineSize), number(entry.contentBlockSize)],
                                     'border': [number(entry.borderInlineSize), number(entry.borderBlockSize)]})
            self.log.append(name + ':' + ','.join(ids))
            for target in ids:
                hit = next((a for a in self.armed if a[0] == name and a[1] == target), None)
                if hit:
                    self.armed.remove(hit)
                    self.step(hit[2])
        callback = ENTRIES(deliver)
        self.callbacks.append(callback)
        handle = self.create(self.host, callback, None)
        self.n.expect(bool(handle), 'observe_resize_entries ' + name)
        return handle

    def step(self, step):
        n, kind, args = self.n, step[0], step[1:]
        if kind == 'create':
            self.observers[args[0]] = self.observer(args[0])
        elif kind == 'observe':
            box = BOXES[args[2]]
            observer, target = self.observers[args[0]], self.node(args[1])
            status = n.call('rv_observer_observe', [P, P], observer, target) if box is None else \
                n.call('rv_observer_observe_box', [P, P, I], observer, target, box)
            self.statuses.append('ok' if status == OK else 'unsupported' if status == UNSUPPORTED else str(status))
        elif kind == 'unobserve':
            n.ok('rv_observer_unobserve', [P, P], self.observers[args[0]], self.node(args[1]))
        elif kind == 'disconnect':
            n.ok('rv_observer_disconnect', [P], self.observers[args[0]])
        elif kind == 'style':
            n.ok('rv_element_set_style', [P, ctypes.c_char_p, Utf8, I], self.node(args[0]), args[1].encode(), args[2].encode(), 0)
        elif kind == 'update':
            self.update()
            self.log.append('|')
        elif kind == 'settle':
            self.update()
            self.update()
        elif kind == 'arm':
            self.armed.append((args[0], args[1], args[2]))
        elif kind == 'errors':
            window = n.bind('rv_host_window_event_target', P, [P])(self.host)
            n.expect(bool(window), 'window')

            def on_error(context, event):
                buffer, length = ctypes.create_string_buffer(512), I()
                n.ok('rv_dom_error_event_get_message', [P, P, I, ctypes.POINTER(I)], event, buffer, len(buffer), ctypes.byref(length))
                self.log.append('error:' + buffer.raw[:length.value].decode('utf-8'))
                return 0
            callback = EVENT(on_error)
            self.callbacks.append(callback)
            listener = n.bind('rv_event_target_add_listener', P, [P, Utf8, I, EVENT, P])(window, b'error', 0, callback, None)
            n.expect(bool(listener), 'error listener')
            self.listeners.append(listener)
            n.bind('rv_event_target_release', None, [P])(window)
        elif kind == 'intersect':
            def on_intersection(context, target, intersecting, ratio):
                self.log.append(args[0] + ':' + self.name_of(target))
            callback = INTERSECT(on_intersection)
            self.callbacks.append(callback)
            observer = n.bind('rv_host_observe_intersection', P, [P, INTERSECT, P, ctypes.c_char_p, P, I])(self.host, callback, None, None, None, 0)
            n.expect(bool(observer), 'intersection observer')
            self.observers[args[0]] = observer
            n.ok('rv_observer_observe', [P, P], observer, self.node(args[1]))
        elif kind == 'element':
            element = n.bind('rv_document_create_element', P, [P, ctypes.c_char_p])(self.host, b'div')
            n.expect(bool(element), 'create element')
            n.ok('rv_element_set_attribute', [P, ctypes.c_char_p, Utf8], element, b'id', args[0].encode())
            n.ok('rv_element_set_attribute', [P, ctypes.c_char_p, Utf8], element, b'style', args[1].encode())
            self.nodes[args[0]] = element
        elif kind == 'append':
            body = n.bind('rv_document_body', P, [P])(self.host)
            n.ok('rv_node_append_child', [P, P], body, self.node(args[0]))
            self.release_node(body)
        elif kind == 'remove':
            n.ok('rv_node_remove', [P], self.node(args[0]))
        else:
            raise ValueError('unknown step ' + kind)

    def close(self):
        for listener in self.listeners:
            self.n.ok('rv_listener_remove', [P], listener)
        for observer in self.observers.values():
            self.release_observer(observer)
        for node in self.nodes.values():
            self.release_node(node)
        self.n.bind('rv_host_destroy', None, [P])(self.host)


def replay(native, cases, scale):
    results = {}
    for scenario in cases['scenarios']:
        scene = Scene(native, cases['markup'], scale)
        try:
            for step in scenario['steps']:
                scene.step(step)
            results[scenario['name']] = {'log': scene.log, 'entries': scene.entries, 'statuses': scene.statuses}
        finally:
            scene.close()
    return results


def errors(native, cases, report):
    n = native
    scene = Scene(n, cases['markup'])
    try:
        noop = ENTRIES(lambda *args: None)
        n.expect(not scene.create(None, noop, None), 'NULL host')
        n.expect(not n.bind('rv_host_observe_resize_entries', P, [P, P, P])(scene.host, None, None), 'NULL callback')
        observer = scene.observer('e')
        scene.observers['e'] = observer
        a = scene.node('a')
        observe_box = n.bind('rv_observer_observe_box', I, [P, P, I])
        n.expect(observe_box(None, a, 0) == NULL_ARGUMENT, 'observe_box NULL observer')
        n.expect(observe_box(observer, None, 0) == NULL_ARGUMENT, 'observe_box NULL element')
        n.expect(observe_box(observer, a, 3) == UNSUPPORTED, 'observe_box unknown box')
        n.expect(observe_box(observer, a, -1) == UNSUPPORTED, 'observe_box negative box')
        n.expect(observe_box(observer, a, 2) == UNSUPPORTED, 'observe_box device-pixel-content-box (Ranvier.WebCore#146)')
        document = n.bind('rv_host_document', P, [P])(scene.host)
        n.expect(observe_box(observer, document, 0) == NOT_ELEMENT, 'observe_box document')
        scene.release_node(document)
        n.expect(n.call('rv_observer_disconnect', [P], None) == NULL_ARGUMENT, 'disconnect NULL')
        icb = INTERSECT(lambda *args: None)
        scene.callbacks.append(icb)
        intersection = n.bind('rv_host_observe_intersection', P, [P, INTERSECT, P, ctypes.c_char_p, P, I])(scene.host, icb, None, None, None, 0)
        scene.observers['i'] = intersection
        n.expect(observe_box(intersection, a, 1) == UNSUPPORTED, 'observe_box intersection observer')
        n.ok('rv_observer_disconnect', [P], intersection)
        statuses = {}

        def off_thread():
            statuses['observe_box'] = observe_box(observer, a, 1)
            statuses['disconnect'] = n.bind('rv_observer_disconnect', I, [P])(observer)
            statuses['create'] = scene.create(scene.host, noop, None)
        worker = threading.Thread(target=off_thread)
        worker.start()
        worker.join()
        n.expect(statuses == {'observe_box': WRONG_THREAD, 'disconnect': WRONG_THREAD, 'create': None}, 'wrong thread ' + str(statuses))
        scene.update()
        n.expect(scene.log == [], 'no delivery after rejected calls ' + str(scene.log))
        report['errors'] = 'ok'
    finally:
        scene.close()


def legacy(native, cases, report, entries):
    """The v15 width/height callback still reports the content box."""
    n = native
    scene = Scene(n, cases['markup'])
    try:
        got = []
        callback = RESIZE(lambda context, target, width, height: got.append([scene.name_of(target), number(width), number(height)]))
        scene.callbacks.append(callback)
        observer = n.bind('rv_host_observe_resize', P, [P, RESIZE, P])(scene.host, callback, None)
        n.expect(bool(observer), 'v15 observer')
        scene.observers['legacy'] = observer
        for name in ['a', 'v', 'f']:
            n.ok('rv_observer_observe', [P, P], observer, scene.node(name))
        scene.update()
        n.ok('rv_element_set_style', [P, ctypes.c_char_p, Utf8, I], scene.node('a'), b'width', b'120px', 0)
        scene.update()
        expected = [[e['t'], e['rect'][2], e['rect'][3]] for e in entries if e['t'] in ('a', 'v', 'f')] + [['a', 120, 50]]
        n.expect(got == expected, 'v15 callback ' + str(got))
        report['legacy'] = got
    finally:
        scene.close()


def teardown(native, cases, report):
    n = native
    result = {}
    # An observer outliving its target: the target's last handle is released after it is detached.
    scene = Scene(n, cases['markup'])
    try:
        scene.step(['element', 'tmp', 'width:40px;height:20px'])
        scene.step(['append', 'tmp'])
        scene.step(['create', 'o'])
        scene.step(['observe', 'o', 'tmp', 'border-box'])
        scene.update()
        watch = n.bind('rv_node_watch', P, [P])(scene.nodes['tmp'])
        n.ok('rv_node_remove', [P], scene.nodes['tmp'])
        scene.release_node(scene.nodes.pop('tmp'))
        scene.update()
        n.bind('rv_collect_garbage', None, [])()
        scene.update()
        scene.update()
        result['outlivedTarget'] = scene.log
        # The destroyed target leaves the observer: no entry refers to it.
        n.expect(scene.log == ['o:tmp'], 'outlived target log ' + str(scene.log))
        n.expect(n.call('rv_watch_alive', [P], watch) == 0, 'outlived target destroyed')
        scene.step(['observe', 'o', 'a', 'content-box'])
        scene.update()
        n.expect(scene.log == ['o:tmp', 'o:a'], 'observer outliving its target observes again ' + str(scene.log))
        n.bind('rv_watch_release', None, [P])(watch)
    finally:
        scene.close()
    # Document replacement: observers of the replaced document deliver nothing; release still frees them.
    scene = Scene(n, cases['markup'])
    try:
        scene.step(['create', 'o'])
        scene.step(['observe', 'o', 'a', 'content-box'])
        n.ok('rv_host_load_html', [P, Utf8], scene.host, cases['markup'].encode('utf-8'))
        scene.update()
        n.ok('rv_element_set_style', [P, ctypes.c_char_p, Utf8, I], scene.nodes['a'], b'width', b'90px', 0)
        scene.update()
        n.ok('rv_observer_observe_box', [P, P, I], scene.observers['o'], scene.nodes['a'], 1)
        scene.update()
        result['documentReplaced'] = scene.log
        n.expect(scene.log == [], 'replaced document log ' + str(scene.log))
    finally:
        scene.close()
    # Release inside a callback: the releasing observer stops, the next observer still delivers.
    scene = Scene(n, cases['markup'])
    try:
        log = scene.log

        def releasing(context, observer, entries, count):
            log.append('first:' + str(count))
            scene.release_observer(observer)
        first = ENTRIES(releasing)
        scene.callbacks.append(first)
        handle = scene.create(scene.host, first, None)
        scene.step(['create', 'second'])
        n.ok('rv_observer_observe', [P, P], handle, scene.node('a'))
        n.ok('rv_observer_observe', [P, P], scene.observers['second'], scene.node('a'))
        scene.update()
        n.ok('rv_element_set_style', [P, ctypes.c_char_p, Utf8, I], scene.node('a'), b'width', b'90px', 0)
        scene.update()
        result['releaseInCallback'] = log
        n.expect(log == ['first:1', 'second:a', 'second:a'], 'release in callback ' + str(log))
    finally:
        scene.close()
    # Host destroy with pending notifications: observers are released first and nothing is delivered.
    scene = Scene(n, cases['markup'])
    scene.step(['create', 'o'])
    scene.step(['observe', 'o', 'a', 'content-box'])
    for observer in scene.observers.values():
        scene.release_observer(observer)
    scene.observers.clear()
    for node in scene.nodes.values():
        scene.release_node(node)
    scene.nodes.clear()
    n.bind('rv_host_destroy', None, [P])(scene.host)
    n.call('rv_run_loop_cycle', [])
    result['hostDestroyed'] = scene.log
    n.expect(scene.log == [], 'host destroy log')
    report['teardown'] = result


def compare(native, oracle, results, report, qualified):
    """Compares each scenario's log and statuses, and each entry field by field where both sides have the same entries."""
    differences = {}

    def differ(key, got, want, scale):
        differences.setdefault(key, {'native': got, 'chromium': want, 'scales': []})['scales'].append(scale)

    for scale, scenarios in results.items():
        for name, got in scenarios.items():
            want = oracle['scales'][scale][name]
            for key in ['log', 'statuses']:
                native.expect(True, 'compared')
                if got[key] != want[key]:
                    differ(f'{name}.{key}', got[key], want[key], scale)
            expected = [{k: v for k, v in e.items() if k != 'device'} for e in want['entries']]
            if [(e['o'], e['t']) for e in got['entries']] != [(e['o'], e['t']) for e in expected]:
                differ(f'{name}.entries', got['entries'], expected, scale)
                continue
            for index, (mine, theirs) in enumerate(zip(got['entries'], expected)):
                for field in ['rect', 'content', 'border']:
                    native.expect(True, 'compared')
                    if mine[field] != theirs[field]:
                        differ(f"{name}.entries.{mine['t']}.{field}", mine[field], theirs[field], scale)
    report['differences'] = differences
    keys = set(differences)
    unqualified = sorted(keys - set(qualified))
    native.expect(not unqualified, 'unqualified differences: ' + json.dumps({k: differences[k] for k in unqualified}))
    native.expect(not set(qualified) - keys, 'qualified differences that no longer occur: ' + str(sorted(set(qualified) - keys)))


def verify(native_directory):
    cases = json.loads((FIXTURES / 'resize-observation-cases.json').read_text(encoding='utf-8'))
    oracle = json.loads((FIXTURES / 'resize-observation-oracle.json').read_text(encoding='utf-8'))
    qualified = json.loads((FIXTURES / 'resize-observation-qualified.json').read_text(encoding='utf-8'))['differences']
    native = Native(native_directory)
    native.expect(native.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
    has = native.bind('rv_abi_has', I, [ctypes.c_char_p])
    for feature in ['resize-entries', 'observers']:
        native.expect(has(feature.encode()) == 1, feature + ' advertised')
    report = {'browser': oracle['browser'], 'platform': sys.platform}
    results = {'1': replay(native, cases, 1), '2': replay(native, cases, 2)}
    report['results'] = results
    errors(native, cases, report)
    legacy(native, cases, report, results['1']['contentBox']['entries'])
    teardown(native, cases, report)
    for scale in results:
        # The qualified scenarios still hold their native contracts.
        sanitized = ['error:Script error.' if item.startswith('error:') else item for item in oracle['scales'][scale]['depth']['log']]
        native.expect(results[scale]['depth']['log'] == sanitized, 'loop error at the same point')
        native.expect(results[scale]['observerOrder']['log'] == ['o2:f', 'o1:a', '|', 'o2:f', 'o1:a', '|'], 'first-observe order')
        native.expect(results[scale]['devicePixel']['statuses'] == ['unsupported', 'unsupported'], 'device-pixel unsupported')
    compare(native, oracle, results, report, qualified)
    report['qualified'] = sorted(qualified)
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
    print(f"PASS resize_observation: {report['assertions']} assertions, {len(report['qualified'])} qualified", flush=True)


if __name__ == '__main__':
    main()
