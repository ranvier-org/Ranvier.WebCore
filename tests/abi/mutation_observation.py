"""D02 public native observation, normal-pump delivery and host ownership."""

import argparse
import ctypes as C
import json
import subprocess
import tempfile
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
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


CALLBACK = C.CFUNCTYPE(None, P, P, P)
RELEASE = C.CFUNCTYPE(None, P)


def text(value):
    if value.length < 0:
        return None
    return C.string_at(value.data, value.length * 2).decode('utf-16-le', errors='surrogatepass')


class Probe:
    def __init__(self, directory):
        self.n = Native(directory)
        self.bridge = self.n.library
        self.n.expect(self.n.call('rv_abi_has', [C.c_char_p], b'mutation-observation') == 1, 'mutation-observation capability is available')
        self.functions = {}
        for suffix, args in {
            'create': [P, CALLBACK, P, RELEASE, C.POINTER(P)],
            'observe': [P, P, C.POINTER(Options)],
            'disconnect': [P], 'release': [P],
            'take_records': [P, C.POINTER(P)],
            'batch_retain': [P], 'batch_release': [P],
            'batch_count': [P, C.POINTER(I)],
            'batch_record': [P, I, C.POINTER(Record)],
        }.items():
            name = {'create': 'rv_host_create_mutation_observer',
                    'observe': 'rv_mutation_observer_observe',
                    'disconnect': 'rv_mutation_observer_disconnect',
                    'release': 'rv_mutation_observer_release',
                    'take_records': 'rv_mutation_observer_take_records',
                    'batch_retain': 'rv_mutation_record_batch_retain',
                    'batch_release': 'rv_mutation_record_batch_release',
                    'batch_count': 'rv_mutation_record_batch_get_count',
                    'batch_record': 'rv_mutation_record_batch_get_record'}[suffix]
            fn = getattr(self.bridge, name)
            fn.restype, fn.argtypes = I, args
            self.functions[suffix] = fn
        self.callbacks = []
        self.live_observers = set()
        self.observer_handles = {}
        self.live_batches = set()
        self.callback_errors = []
        self.accepted_contexts = 0
        self.released_contexts = 0

    def call(self, name, *values):
        return self.functions[name](*values)

    def ok(self, name, *values):
        status = self.call(name, *values)
        self.n.expect(status == OK, f'{name}: {status}')

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

    def create(self, host, action=None, on_closed=None):
        events, releases = [], []

        def delivered(_, observer, batch):
            try:
                events.append((observer, self.records(batch)))
                if action:
                    action(observer, batch)
            except BaseException as error:
                self.callback_errors.append(repr(error))

        handle = P()
        def finalized(_):
            try:
                releases.append('release')
                self.released_contexts += 1
                if on_closed and handle.value:
                    on_closed(handle.value)
            except BaseException as error:
                self.callback_errors.append(repr(error))

        callback = CALLBACK(delivered)
        release = RELEASE(finalized)
        self.callbacks.extend([callback, release])
        self.ok('create', host, callback, None, release, C.byref(handle))
        self.n.expect(bool(handle.value), 'created observer is non-null')
        self.accepted_contexts += 1
        self.live_observers.add(handle.value)
        self.observer_handles[handle.value] = handle
        return handle.value, events, releases

    def release(self, handle):
        self.observer_handles.pop(handle).value = None
        self.live_observers.remove(handle)
        self.ok('release', handle)

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
            self.observer_handles.pop(handle).value = None
            self.live_observers.remove(handle)
            self.call('release', handle)
        for handle in list(self.live_batches):
            self.call('batch_release', handle)
        self.live_observers.clear()
        self.live_batches.clear()


def run(directory, report_path=None, reentry_modes=None):
    p = Probe(directory)
    n = p.n
    page = Case(n, '<div id="root"><span id="a">start</span><span id="b"></span></div><div id="destination"></div>')
    foreign = None
    transcript = {}
    try:
        root, a, b = page.node('root'), page.node('a'), page.node('b')
        rejected_contexts = []
        rejected_callback = CALLBACK(lambda *_: None)
        rejected_release = RELEASE(lambda _: rejected_contexts.append(True))
        for host, callback, release in [(None, rejected_callback, rejected_release),
                                        (page.host, CALLBACK(), rejected_release),
                                        (page.host, rejected_callback, RELEASE())]:
            output = P(1)
            n.expect(p.call('create', host, callback, None, release, C.byref(output)) == -1 and not output.value,
                     'factory requires host/callback/context-release and clears output')
        output = P(1)
        n.expect(p.call('create', P(1), rejected_callback, None, rejected_release, C.byref(output)) == -10
                 and not output.value, 'dead host is rejected before dereference')
        n.expect(rejected_contexts == [], 'rejected factory keeps caller context ownership')
        observer, events, releases = p.create(page.host)
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
        canary_size = C.sizeof(Record) + 16
        canary = (C.c_ubyte * canary_size)(*([0xA5] * canary_size))
        C.cast(canary, C.POINTER(C.c_uint32))[0] = 4
        original = bytes(canary)
        n.expect(p.call('batch_record', batch, 0, C.cast(canary, C.POINTER(Record))) == -1
                 and bytes(canary) == original, 'invalid record output size preserves adjacent canary bytes')
        invalid_index = Record(C.sizeof(Record))
        invalid_index.target = 1
        n.expect(p.call('batch_record', batch, -1, C.byref(invalid_index)) == -1
                 and not invalid_index.target and invalid_index.type.length == 0,
                 'invalid record index clears a correctly sized output')
        count = I(7)
        n.expect(p.call('batch_count', None, C.byref(count)) == -1 and count.value == 0,
                 'null batch clears count output')
        output = P(1)
        n.expect(p.call('take_records', None, C.byref(output)) == -1 and not output.value,
                 'null observer clears takeRecords output')
        thread_outputs = []
        def check_thread_outputs():
            count = I(7)
            view = Record(C.sizeof(Record))
            view.target = 1
            thread_outputs.extend([p.call('batch_count', batch, C.byref(count)), count.value,
                                   p.call('batch_record', batch, 0, C.byref(view)), view.target])
        worker = threading.Thread(target=check_thread_outputs)
        worker.start()
        worker.join()
        n.expect(thread_outputs == [-2, 0, -2, None], 'wrong-thread batch reads clear outputs without registry access')
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

        filtered, events, releases = p.create(page.host)
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
        child, events, _ = p.create(page.host)
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
        cross, events, _ = p.create(page.host)
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

        self_observer, events, self_releases = p.create(page.host, self_release)
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
        reentrant, events, _ = p.create(page.host, mutate_again)
        p.observe(reentrant, b, Options(attribute_old_value=True))
        p.set_attribute(b, 'data-reentrant', 'first')
        p.pump(lambda: len(events) == 2, timeout=2)
        n.expect(len(events) == 2 and [e[1][0]['old'] for e in events] == [None, 'first'], 'reentrant mutation queues a separate delivery')
        p.release(reentrant)

        def provider_closed(handle):
            p.release(handle)

        stale, _, releases = p.create(foreign.host, on_closed=provider_closed)
        p.observe(stale, foreign.document, Options(child_list=True, subtree=True))
        detached_child = n.handle('rv_dom_document_create_element', [P, Utf8, P], foreign.document, 'div', None, nullable=False)
        foreign.owned.append(detached_child)
        foreign_root = n.handle('rv_dom_document_get_document_element', [P], foreign.document, nullable=False)
        foreign.owned.append(foreign_root)
        inserted = n.handle('rv_dom_node_append_child', [P, P], foreign_root, detached_child)
        n.bind('rv_node_release', None, [P])(inserted)
        retained = p.take(stale)
        foreign.close()
        foreign = None
        p.pump()
        automatic_teardown = releases == ['release'] and stale not in p.live_observers
        teardown = {'context_releases_before_observer_access': list(releases),
                    'automatic': automatic_teardown}
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps({'partial': True, 'assertions': n.assertions,
                                               'host_teardown': teardown}, indent=2), encoding='utf-8')
        n.expect(p.call('disconnect', stale) == -10, 'stopped document closes its observer on access')
        n.expect(releases == ['release'], 'stopped-context access drops the callback lease')
        n.expect(len(p.records(retained)) == 1, 'retained record batch remains readable after host destruction')
        p.release_batch(retained)
        n.expect(stale not in p.live_observers, 'provider closed notification released its native observer without caller disposal')
        p.pump()
        n.expect(automatic_teardown, f'automatic destroy ownership before explicit access: {teardown}')

        replacements = {}
        for mode in ['html', 'svg']:
            changed = Case(n, '<div id="old">old document</div>')
            try:
                target = changed.node('old')
                old_observer, old_events, old_releases = p.create(changed.host, on_closed=provider_closed)
                p.observe(old_observer, target, Options(attribute_old_value=True))
                p.set_attribute(target, 'data-before-replacement', mode)
                batch = p.take(old_observer)
                function = 'rv_host_load_html' if mode == 'html' else 'rv_host_load_svg'
                markup = '<div>replacement</div>' if mode == 'html' else '<svg xmlns="http://www.w3.org/2000/svg"><text>replacement</text></svg>'
                n.ok(function, [P, Utf8], changed.host, markup)
                p.pump()
                replacements[mode] = {'provider_token_live': old_observer in p.live_observers,
                                      'context_releases': list(old_releases)}
                n.expect(old_observer not in p.live_observers and old_releases == ['release'],
                         f'{mode} replacement automatically closes observer roots: {replacements[mode]}')
                n.expect(old_events == [], mode + ' replacement suppresses queued callback delivery')
                n.expect(p.records(batch)[0]['target'] == target, mode + ' replacement retains independent record snapshot')
                p.release_batch(batch)
                n.expect(old_observer not in p.live_observers, mode + ' replacement releases native provider token')
            finally:
                changed.close()

        doomed = Case(n, '<div id="doomed"></div>')
        doomed_closed = False
        destroy_order = []
        kept = []
        def destroy_while_delivering(_, borrowed):
            nonlocal doomed_closed
            p.ok('batch_retain', borrowed)
            p.live_batches.add(borrowed)
            kept.append(borrowed)
            doomed_closed = True
            doomed.close()
            destroy_order.append(list(doomed_releases))

        try:
            doomed_target = doomed.node('doomed')
            doomed_observer, doomed_events, doomed_releases = p.create(
                doomed.host, destroy_while_delivering, provider_closed)
            p.observe(doomed_observer, doomed_target, Options(attributes=True))
            p.set_attribute(doomed_target, 'data-destroy', 'now')
            p.pump(lambda: bool(doomed_events), timeout=2)
            n.expect(destroy_order == [[]] and doomed_releases == ['release'],
                     'host destruction during delivery preserves the in-flight context lease through callback return')
            n.expect(doomed_observer not in p.live_observers,
                     'self-destroy callback closes its provider token')
            n.expect(p.records(kept[0])[0]['target'] == doomed_target,
                     'callback snapshot survives destruction of its creating host')
            p.release_batch(kept.pop())
            p.pump()
            n.expect(len(doomed_events) == 1, 'destroyed observer never delivers again')
        finally:
            if not doomed_closed:
                doomed.close()
        raw_owner = Case(n, '<div id="raw-owner"></div>')
        raw_closed = False
        try:
            target = raw_owner.node('raw-owner')
            token, raw_events, raw_releases = p.create(raw_owner.host)
            p.observe(token, target, Options(attributes=True))
            p.set_attribute(target, 'data-retained', 'raw')
            retained = p.take(token)
            raw_closed = True
            raw_owner.close()
            p.pump()
            n.expect(raw_releases == ['release'] and token in p.live_observers and not raw_events,
                     'automatic close releases context while a raw caller still owns its closed external token')
            output = P(1)
            n.expect(p.call('take_records', token, C.byref(output)) == -10 and not output.value,
                     'closed external token is inactive, independently of its retained registry entry')
            p.release(token)
            n.expect(raw_releases == ['release'], 'explicit closed-token release does not release its context twice')
            p.release_batch(retained)
        finally:
            if not raw_closed:
                raw_owner.close()
        reentry = {}
        for mode in (['destroy', 'html', 'svg'] if reentry_modes is None else reentry_modes):
            invalidating = Case(n, '<div id="invalidating"></div>')
            invalidating_closed = False
            attempts, reloads, rejected_releases = [], [], []
            sink = CALLBACK(lambda *_: None)
            release = RELEASE(lambda _: rejected_releases.append(True))
            def attempt_admission():
                result = P(1)
                status = p.call('create', invalidating.host, sink, None, release, C.byref(result))
                attempts.append((status, result.value))
                if status == OK:
                    p.ok('release', result)
            def close_and_reenter(handle):
                p.release(handle)
                attempt_admission()
                reloads.append(n.call('rv_host_load_html', [P, Utf8], invalidating.host, '<div>nested reload</div>'))
                attempt_admission()
            try:
                target = invalidating.node('invalidating')
                token, _, _ = p.create(invalidating.host, on_closed=close_and_reenter)
                p.observe(token, target, Options(attributes=True))
                p.set_attribute(target, 'data-before-invalidation', mode)
                retained = p.take(token)
                if mode == 'destroy':
                    invalidating_closed = True
                    invalidating.close()
                else:
                    markup = '<div>outer reload</div>' if mode == 'html' else '<svg xmlns="http://www.w3.org/2000/svg"/>'
                    n.ok('rv_host_load_' + mode, [P, Utf8], invalidating.host, markup)
                    fresh, _, fresh_releases = p.create(invalidating.host)
                    p.release(fresh)
                    n.expect(fresh_releases == ['release'], 'normal replacement admits a fresh observer afterward')
                p.pump()
                p.release_batch(retained)
                reentry[mode] = {'admissions': attempts, 'reloads': reloads,
                                 'unexpected_transferred_context_releases': list(rejected_releases)}
            finally:
                if not invalidating_closed:
                    invalidating.close()
        if report_path:
            report_path.write_text(json.dumps({'partial': True, 'invalidation_reentry': reentry}, indent=2), encoding='utf-8')
        n.expect(all(row['admissions'] == [(-10, None), (-10, None)] and row['reloads'] == [-10]
                     and not row['unexpected_transferred_context_releases'] for row in reentry.values()),
                 f'invalidating contexts reject admission before and after nested reload: {reentry}')
        n.expect(not p.live_observers and not p.live_batches and p.accepted_contexts == p.released_contexts, 'all provider tokens, context leases and batches are released')
        return {'assertions': n.assertions, 'transcript': transcript, 'accepted_contexts': p.accepted_contexts, 'released_contexts': p.released_contexts,
                'host_teardown': teardown, 'replacement_teardown': replacements,
                'self_destroy_context_release_order': destroy_order, 'invalidation_reentry': reentry}
    finally:
        p.close()
        if foreign is not None:
            foreign.close()
        page.close()


def run_destroy_reentry(directory, mode, report_path):
    p = Probe(directory)
    n = p.n
    case = Case(n, '<div id="target"></div>')
    target = case.node('target')
    progress = []

    def save(stage, **values):
        progress.append({'stage': stage, **values})
        if report_path:
            report_path.write_text(json.dumps({'partial': True, 'progress': progress}, indent=2), encoding='utf-8')

    def closed(handle):
        p.release(handle)
        save('before reentrant destroy', contexts=[p.accepted_contexts, p.released_contexts], tokens=len(p.live_observers))
        n.bind('rv_host_destroy', None, [P])(case.host)
        save('after reentrant destroy', contexts=[p.accepted_contexts, p.released_contexts], tokens=len(p.live_observers))

    token, _, releases = p.create(case.host, on_closed=closed)
    p.observe(token, target, Options(attributes=True))
    p.set_attribute(target, 'data-retained', 'yes')
    batch = p.take(token)
    save('before outer transaction', mode=mode)
    if mode == 'destroy':
        case.close()
    else:
        markup = '<div>outer reload</div>' if mode == 'html' else '<svg xmlns="http://www.w3.org/2000/svg"/>'
        status = n.call('rv_host_load_' + mode, [P, Utf8], case.host, markup)
        save('after outer replacement', status=status)
        n.expect(status == -10, 'replacement honors deferred destruction before returning detached')
    save('after outer transaction', contexts=[p.accepted_contexts, p.released_contexts], tokens=len(p.live_observers))
    rejected_releases = []
    sink = CALLBACK(lambda *_: None)
    release = RELEASE(lambda _: rejected_releases.append(True))
    output = P(1)
    status = p.call('create', case.host, sink, None, release, C.byref(output))
    save('post-destroy factory', status=status, handle=output.value)
    if status == OK:
        p.ok('release', output)
    n.expect(status == -10 and not output.value and not rejected_releases,
             'destroyed host rejects creation without transferring context ownership')
    n.expect(releases == ['release'] and p.accepted_contexts == p.released_contexts and not p.live_observers,
             'reentrant destruction ends its context and external token exactly once')
    n.expect(not p.callback_errors, f'context release callback exceptions: {p.callback_errors}')
    p.release_batch(batch)
    if mode != 'destroy':
        for node in case.owned + list(case.created.values()) + [case.document]:
            n.bind('rv_node_release', None, [P])(node)
    n.bind('rv_host_destroy', None, [P])(case.host)
    p.close()
    save('final retained-batch and node cleanup')
    return {'assertions': n.assertions, 'progress': progress,
            'accepted_contexts': p.accepted_contexts, 'released_contexts': p.released_contexts}


ISOLATED_CASES = ('common', 'destroy', 'html', 'svg', 'raw-destroy', 'destroy-during-html', 'destroy-during-svg')


def run_isolated(directory):
    rows = []
    with tempfile.TemporaryDirectory(prefix='ranvier-mutation-') as temporary:
        for mode in ISOLATED_CASES:
            report = Path(temporary) / (mode + '.json')
            command = [sys.executable, '-I', '-B', '-X', 'utf8', str(Path(__file__).resolve()),
                       '--native-directory', str(directory), '--isolated-case', mode, '--report', str(report)]
            row = {'case': mode}
            try:
                process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
                row.update(exit=process.returncode, stdout=process.stdout, stderr=process.stderr)
            except subprocess.TimeoutExpired:
                row.update(exit=None, timeout=True)
            try:
                row['result'] = json.loads(report.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError) as error:
                row['report_error'] = str(error)
                if row['exit'] == 0:
                    row['exit'] = 1
            rows.append(row)
            print(f"mutation isolated {mode}: {row['exit']}", flush=True)
            if row['exit'] != 0:
                print(row.get('stdout', ''), end='')
                print(row.get('stderr', ''), end='')
    return {'cases': rows, 'assertions': sum(row.get('result', {}).get('assertions', 0) for row in rows)}, all(row['exit'] == 0 for row in rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--isolated-case', choices=ISOLATED_CASES, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
    if args.isolated_case is None:
        result, passed = run_isolated(args.native_directory)
    elif args.isolated_case in ('raw-destroy', 'destroy-during-html', 'destroy-during-svg'):
        mode = {'raw-destroy': 'destroy', 'destroy-during-html': 'html', 'destroy-during-svg': 'svg'}[args.isolated_case]
        result, passed = run_destroy_reentry(args.native_directory, mode, args.report), True
    else:
        modes = [] if args.isolated_case == 'common' else [args.isolated_case]
        result = run(args.native_directory, args.report, modes)
        passed = result['host_teardown']['automatic']
    if args.report:
        args.report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f"{'PASS' if passed else 'FAIL'} mutation_observation: {result['assertions']} assertions")
    raise SystemExit(0 if passed else 1)
