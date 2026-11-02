"""Private D02 engine seam; requires a separately linked test-only WebCore image."""

import argparse
import ctypes as C
import json
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'abi'))
from form_collections import Case, Native, P, I, OK
from utf8_inputs import Utf8


class OptionalBool(C.Structure):
    _fields_ = [('present', I), ('value', I)]


class Utf16(C.Structure):
    _fields_ = [('data', P), ('length', I)]


class OptionalStrings(C.Structure):
    _fields_ = [('present', I), ('items', C.POINTER(Utf16)), ('count', I)]


class Nodes(C.Structure):
    _fields_ = [('items', C.POINTER(P)), ('count', I)]


class Options(C.Structure):
    _fields_ = [('size', C.c_uint32), ('child_list', I), ('subtree', I),
                ('attributes', OptionalBool), ('character_data', OptionalBool),
                ('attribute_old_value', OptionalBool), ('character_data_old_value', OptionalBool),
                ('attribute_filter', OptionalStrings)]

    def __init__(self, *, child_list=False, subtree=False, attributes=None,
                 character_data=None, attribute_old_value=None,
                 character_data_old_value=None, attribute_filter=None):
        super().__init__()
        self.size = C.sizeof(self)
        self.child_list, self.subtree = child_list, subtree
        for name, value in [('attributes', attributes), ('character_data', character_data),
                            ('attribute_old_value', attribute_old_value),
                            ('character_data_old_value', character_data_old_value)]:
            setattr(self, name, OptionalBool(value is not None, bool(value)))
        self.buffers = []
        if attribute_filter is not None:
            spans = []
            for value in attribute_filter:
                data = value.encode('utf-16-le', errors='surrogatepass')
                buffer = C.create_string_buffer(data, len(data) + 2)
                self.buffers.append(buffer)
                spans.append(Utf16(C.cast(buffer, P), len(data) // 2))
            self.spans = (Utf16 * len(spans))(*spans)
            self.attribute_filter = OptionalStrings(1, self.spans, len(spans))


class Record(C.Structure):
    _fields_ = [('size', C.c_uint32), ('type', Utf16), ('target', P),
                ('added_nodes', Nodes), ('removed_nodes', Nodes),
                ('previous_sibling', P), ('next_sibling', P),
                ('attribute_name', Utf16), ('attribute_namespace', Utf16), ('old_value', Utf16)]


class Counts(C.Structure):
    _fields_ = [('size', C.c_uint32), ('observers', I), ('callbacks', I), ('contexts', I), ('batches', I)]


CALLBACK = C.CFUNCTYPE(None, P, P, P)
RELEASE = C.CFUNCTYPE(None, P)


def text(value):
    if value.length < 0:
        return None
    return C.string_at(value.data, value.length * 2).decode('utf-16-le', errors='surrogatepass')


class Probe:
    def __init__(self, directory, bridge):
        self.n = Native(directory)
        self.bridge = C.CDLL(str(Path(bridge).resolve()))
        self.functions = {}
        for suffix, args in {
            'create': [P, CALLBACK, P, RELEASE, C.POINTER(P)],
            'observe': [P, P, C.POINTER(Options)],
            'disconnect': [P], 'close': [P], 'release': [P],
            'take_records': [P, C.POINTER(P)],
            'batch_retain': [P], 'batch_release': [P],
            'batch_count': [P, C.POINTER(I)],
            'batch_record': [P, I, C.POINTER(Record)],
            'counts': [C.POINTER(Counts)],
        }.items():
            fn = getattr(self.bridge, 'ranvier_test_mutation_' + suffix)
            fn.restype, fn.argtypes = I, args
            self.functions[suffix] = fn
        self.callbacks = []
        self.live_observers = set()
        self.live_batches = set()
        self.callback_errors = []

    def call(self, name, *values):
        return self.functions[name](*values)

    def ok(self, name, *values):
        status = self.call(name, *values)
        self.n.expect(status == OK, f'{name}: {status}')

    def counts(self):
        result = Counts(C.sizeof(Counts))
        self.ok('counts', C.byref(result))
        return [result.observers, result.callbacks, result.contexts, result.batches]

    def records(self, batch):
        count = I()
        self.ok('batch_count', batch, C.byref(count))
        result = []
        for i in range(count.value):
            view = Record(C.sizeof(Record))
            self.ok('batch_record', batch, i, C.byref(view))
            result.append({
                'type': text(view.type), 'target': view.target,
                'added': [view.added_nodes.items[j] for j in range(view.added_nodes.count)],
                'removed': [view.removed_nodes.items[j] for j in range(view.removed_nodes.count)],
                'previous': view.previous_sibling, 'next': view.next_sibling,
                'name': text(view.attribute_name), 'namespace': text(view.attribute_namespace),
                'old': text(view.old_value),
            })
        return result

    def create(self, document, action=None):
        events, releases = [], []

        def delivered(_, observer, batch):
            try:
                events.append((observer, self.records(batch)))
                if action:
                    action(observer, batch)
            except BaseException as error:
                self.callback_errors.append(repr(error))

        callback = CALLBACK(delivered)
        release = RELEASE(lambda _: releases.append('release'))
        self.callbacks.extend([callback, release])
        handle = P()
        self.ok('create', document, callback, None, release, C.byref(handle))
        self.n.expect(bool(handle.value), 'created observer is non-null')
        self.live_observers.add(handle.value)
        return handle.value, events, releases

    def release(self, handle):
        self.ok('release', handle)
        self.live_observers.remove(handle)

    def observe(self, observer, target, options):
        self.ok('observe', observer, target, C.byref(options))

    def take(self, observer):
        batch = P()
        self.ok('take_records', observer, C.byref(batch))
        self.n.expect(bool(batch.value), 'takeRecords owns a batch, including an empty drain')
        self.live_batches.add(batch.value)
        return batch.value

    def release_batch(self, batch):
        self.ok('batch_release', batch)
        self.live_batches.remove(batch)

    def pump(self, done=lambda: False, timeout=0.15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            cycles = self.n.call('rv_run_loop_cycle', [I], 2)
            self.n.expect(cycles > 0, f'normal run-loop cycles: {cycles}')
            if done():
                break
        self.n.expect(not self.callback_errors, f'callback exceptions: {self.callback_errors}')

    def set_attribute(self, target, name, value):
        self.n.ok('rv_dom_element_set_attribute', [P, Utf8, Utf8], target, name, value)

    def close(self):
        for handle in list(self.live_observers):
            self.call('release', handle)
        for handle in list(self.live_batches):
            self.call('batch_release', handle)
        self.live_observers.clear()
        self.live_batches.clear()


def run(directory, bridge, report_path=None):
    p = Probe(directory, bridge)
    n = p.n
    page = Case(n, '<div id="root"><span id="a">start</span><span id="b"></span></div><div id="destination"></div>')
    initial = p.counts()
    foreign = None
    transcript = {}
    try:
        root, a, b = page.node('root'), page.node('a'), page.node('b')
        observer, events, releases = p.create(page.document)
        for options in [Options(), Options(attributes=False, attribute_old_value=True),
                        Options(attributes=False, attribute_filter=[]),
                        Options(character_data=False, character_data_old_value=True)]:
            status = p.call('observe', observer, root, C.byref(options))
            n.expect(status == -3 and n.exception() == 'TypeError', 'invalid option combination is TypeError')
        wrong_thread = []
        worker = threading.Thread(target=lambda: wrong_thread.append(p.call('disconnect', observer)))
        worker.start()
        worker.join()
        n.expect(wrong_thread == [-2], 'observer calls require the owner thread')
        p.observe(observer, a, Options(attribute_old_value=True))
        for value in ['one', '', 'three']:
            p.set_attribute(a, 'data-probe', value)
        n.expect(events == [], 'native DOM mutations do not synchronously deliver')
        p.pump(lambda: bool(events), timeout=2)
        n.expect(len(events) == 1 and events[0][0] == observer, 'ordinary run-loop pump delivers one batch with exact observer identity')
        records = events[0][1]
        n.expect([r['old'] for r in records] == [None, 'one', ''], 'null and empty attribute old values remain distinct')
        n.expect(all(r['type'] == 'attributes' and r['target'] == a and r['name'] == 'data-probe'
                     and r['namespace'] is None and not r['added'] and not r['removed'] for r in records),
                 'attribute record scalar and node fields')
        transcript['attributes'] = records
        events.clear()
        p.set_attribute(a, 'data-probe', 'drained')
        batch = p.take(observer)
        n.expect([r['old'] for r in p.records(batch)] == ['three'], 'takeRecords drains immediately')
        empty = p.take(observer)
        n.expect(p.records(empty) == [], 'second drain returns an empty owned snapshot')
        p.release_batch(empty)
        p.pump()
        n.expect(events == [], 'drained records are not delivered')
        p.set_attribute(a, 'data-probe', 'discarded')
        p.ok('disconnect', observer)
        p.pump()
        n.expect(events == [], 'disconnect discards pending records')
        p.release(observer)
        n.expect(releases == ['release'], 'observer release drops callback context once')
        n.expect(p.records(batch)[0]['old'] == 'three', 'taken records survive observer disposal')
        p.release_batch(batch)

        filtered, events, releases = p.create(page.document)
        p.observe(filtered, a, Options(attribute_filter=[]))
        p.set_attribute(a, 'data-unused', 'ignored')
        p.pump()
        n.expect(events == [], 'present empty attributeFilter observes no attribute names')
        options = Options(attribute_filter=['data-match'], attribute_old_value=True)
        p.observe(filtered, a, options)
        options.buffers[0].raw = b'x\x00' * (C.sizeof(options.buffers[0]) // 2)
        p.set_attribute(a, 'data-other', 'ignored')
        p.set_attribute(a, 'data-match', 'kept')
        p.pump(lambda: bool(events), timeout=2)
        n.expect([r['name'] for _, values in events for r in values] == ['data-match'], 'Observe copies filter contents')
        p.ok('disconnect', filtered)
        p.observe(filtered, a, Options(attribute_old_value=True))
        n.ok('rv_dom_element_set_attribute_ns', [P, Utf8, Utf8, Utf8], a, 'urn:probe', 'p:value', '')
        p.pump(lambda: len(events) > 1, timeout=2)
        n.expect(events[-1][1][0]['name'] == 'value' and events[-1][1][0]['namespace'] == 'urn:probe', 'namespaced attributes retain local name and namespace')
        p.release(filtered)

        text_node = n.handle('rv_dom_node_get_first_child', [P], a, nullable=False)
        page.owned.append(text_node)
        child, events, _ = p.create(page.document)
        p.observe(child, root, Options(child_list=True, subtree=True, character_data_old_value=True))
        removed = n.handle('rv_dom_node_remove_child', [P, P], root, a, nullable=False)
        n.bind('rv_node_release', None, [P])(removed)
        n.ok('rv_dom_character_data_set_data', [P, Utf8], text_node, 'detached change')
        p.pump(lambda: bool(events), timeout=2)
        rows = [r for _, values in events for r in values]
        n.expect([r['type'] for r in rows] == ['childList', 'characterData'], 'removed subtree remains transiently observed until delivery')
        n.expect(rows[0]['target'] == root and rows[0]['removed'] == [a] and rows[0]['next'] == b,
                 'child removal retains node order and sibling identity')
        n.expect(rows[1]['target'] == text_node and rows[1]['old'] == 'start', 'characterData old value is copied')
        events.clear()
        n.ok('rv_dom_character_data_set_data', [P, Utf8], text_node, 'after delivery')
        p.pump()
        n.expect(events == [], 'transient observation ends after delivery')
        p.release(child)

        foreign = Case(n, '<div id="foreign">foreign</div>')
        foreign_node = foreign.node('foreign')
        cross, events, _ = p.create(page.document)
        p.observe(cross, foreign_node, Options(attributes=True))
        p.set_attribute(foreign_node, 'data-cross', 'before adoption')
        p.pump(lambda: bool(events), timeout=2)
        n.expect(events and events[0][1][0]['target'] == foreign_node, 'valid foreign-document target is observable')
        events.clear()
        adopted = n.handle('rv_dom_document_adopt_node', [P, P], page.document, foreign_node, nullable=False)
        n.expect(adopted == foreign_node, 'adoption preserves native node identity')
        n.bind('rv_node_release', None, [P])(adopted)
        p.set_attribute(foreign_node, 'data-cross', 'after adoption')
        p.pump(lambda: bool(events), timeout=2)
        n.expect(events and events[0][1][0]['target'] == foreign_node, 'observation survives target adoption')
        p.release(cross)

        held = []
        order = []
        def self_release(handle, borrowed):
            p.ok('batch_retain', borrowed)
            p.live_batches.add(borrowed)
            held.append(borrowed)
            p.release(handle)
            order.append(('inside', list(self_releases)))

        self_observer, events, self_releases = p.create(page.document, self_release)
        p.observe(self_observer, b, Options(attributes=True))
        p.set_attribute(b, 'data-self', 'one')
        p.pump(lambda: bool(events), timeout=2)
        n.expect(order == [('inside', [])] and self_releases == ['release'], 'in-flight lease survives self-release until callback returns')
        n.expect(p.records(held[0])[0]['target'] == b, 'retained callback batch survives self-release')
        p.release_batch(held.pop())
        p.set_attribute(b, 'data-self', 'two')
        p.pump()
        n.expect(len(events) == 1, 'self-release suppresses later delivery')

        nested = []
        def mutate_again(_, __):
            if not nested:
                nested.append(True)
                p.set_attribute(b, 'data-reentrant', 'second')
        reentrant, events, _ = p.create(page.document, mutate_again)
        p.observe(reentrant, b, Options(attribute_old_value=True))
        p.set_attribute(b, 'data-reentrant', 'first')
        p.pump(lambda: len(events) == 2, timeout=2)
        n.expect(len(events) == 2 and [e[1][0]['old'] for e in events] == [None, 'first'], 'reentrant mutation queues a separate delivery')
        p.release(reentrant)

        stale, _, releases = p.create(foreign.document)
        p.observe(stale, foreign.document, Options(child_list=True, subtree=True))
        detached_child = n.handle('rv_dom_document_create_element', [P, Utf8, P], foreign.document, 'div', None, nullable=False)
        foreign.owned.append(detached_child)
        foreign_root = n.handle('rv_dom_document_get_document_element', [P], foreign.document, nullable=False)
        foreign.owned.append(foreign_root)
        inserted = n.handle('rv_dom_node_append_child', [P, P], foreign_root, detached_child)
        n.bind('rv_node_release', None, [P])(inserted)
        retained = p.take(stale)
        before_destroy = p.counts()
        foreign.close()
        foreign = None
        p.pump()
        after_destroy = p.counts()
        automatic_teardown = releases == ['release'] and after_destroy[1:3] == initial[1:3]
        teardown = {'before': before_destroy, 'after': after_destroy,
                    'context_releases_before_observer_access': list(releases),
                    'automatic': automatic_teardown}
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps({'partial': True, 'assertions': n.assertions,
                                               'host_teardown': teardown}, indent=2), encoding='utf-8')
        n.expect(p.call('disconnect', stale) == -10, 'stopped document closes its observer on access')
        n.expect(releases == ['release'], 'stopped-context access drops the callback lease')
        n.expect(len(p.records(retained)) == 1, 'retained record batch remains readable after host destruction')
        p.release_batch(retained)
        p.release(stale)
        p.pump()
        n.expect(p.counts() == initial, 'observer, callback, context and batch counts return to baseline')
        return {'assertions': n.assertions, 'transcript': transcript, 'counts': initial,
                'host_teardown': teardown}
    finally:
        p.close()
        if foreign is not None:
            foreign.close()
        page.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--bridge-library', required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = run(args.native_directory, args.bridge_library, args.report)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f"PASS engine mutation_probe: {result['assertions']} assertions")
    if not result['host_teardown']['automatic']:
        print('FAIL automatic host teardown: fixture requires the production host invalidation hook')
        raise SystemExit(1)
