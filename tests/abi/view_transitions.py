"""A11 same-document transitions through the native ABI, including the slim safety gate."""

import argparse
import ctypes
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, Case, P, I, OK

UNSUPPORTED = -9
UPDATE = ctypes.CFUNCTYPE(I, P)
RELEASE = ctypes.CFUNCTYPE(None, P)
SETTLED = ctypes.CFUNCTYPE(None, P, I, ctypes.c_char_p)


class Span(ctypes.Structure):
    _fields_ = [('data', P), ('length', I)]


class Strings(ctypes.Structure):
    _fields_ = [('present', I), ('count', I), ('items', ctypes.POINTER(Span))]


class StringValues(ctypes.Structure):
    _fields_ = [('count', I), ('items', ctypes.POINTER(Span))]


class Options(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('update', P), ('types', ctypes.POINTER(Strings))]


def run(directory, slim):
    n = Native(directory)
    slim = slim or not n.call('rv_abi_has', [ctypes.c_char_p], b'view-transitions')
    start = n.bind('rv_dom_document_start_view_transition', I, [P, ctypes.POINTER(Options), ctypes.POINTER(P)])
    page = Case(n, '<style>:root{view-transition-name:root}::view-transition-group(*){animation-duration:0.04s}</style><div id="value">old</div>')
    try:
        result = P()
        if slim:
            n.expect(start(page.document, None, ctypes.byref(result)) == UNSUPPORTED, 'slim start is safely unsupported')
            n.expect(not result.value, 'unsupported start creates no transition')
            return n.assertions
        absent_events = []
        absent_sink = SETTLED(lambda _, kind, error: absent_events.append((kind, error.decode() if error else None)))
        absent_observer = P()
        n.expect(start(page.document, None, ctypes.byref(result)) == OK and result.value, 'transition starts without an update callback')
        n.ok('rv_view_transition_observe', [P, P, SETTLED, P, ctypes.POINTER(P)], page.host, result, absent_sink, None, ctypes.byref(absent_observer))
        deadline = time.monotonic() + 5
        while len(absent_events) < 3 and time.monotonic() < deadline:
            n.call('rv_host_update', [P], page.host)
            n.call('rv_run_loop_cycle', [I], 5)
        n.expect(absent_events == [(0, None), (1, None), (2, None)], f'absent callback promise settlement: {absent_events}')
        n.bind('rv_view_transition_observer_release', None, [P])(absent_observer)
        n.bind('rv_dom_view_transition_release', None, [P])(result)
        result = P()
        log, releases = [], []
        update = UPDATE(lambda _: log.append(('update', None)) or 0)
        release = RELEASE(lambda _: releases.append('callback'))
        callback = n.bind('rv_view_transition_update_callback_create', P, [P, UPDATE, P, RELEASE])(page.host, update, None, release)
        n.expect(bool(callback), 'update callback created')
        options = Options(ctypes.sizeof(Options), callback, None)
        n.expect(start(None, None, ctypes.byref(result)) == -1, 'start rejects a null document')
        wrong_thread = []
        worker = threading.Thread(target=lambda: wrong_thread.append(start(page.document, None, ctypes.byref(P()))))
        worker.start()
        worker.join()
        n.expect(wrong_thread == [-2], 'start requires the owning thread')
        foreign = Case(n, '<div>foreign host</div>')
        foreign_tick = UPDATE(lambda _: 0)
        foreign_callback = n.bind('rv_view_transition_update_callback_create', P, [P, UPDATE, P, P])(foreign.host, foreign_tick, None, None)
        foreign_options = Options(ctypes.sizeof(Options), foreign_callback, None)
        n.expect(start(page.document, ctypes.byref(foreign_options), ctypes.byref(result)) == -12, 'update callback belongs to its creating document')
        n.bind('rv_dom_view_transition_update_callback_release', None, [P])(foreign_callback)
        n.expect(start(page.document, ctypes.byref(options), ctypes.byref(result)) == OK and result.value, 'transition started')
        n.expect(not log, 'update is deferred from start')
        active = n.handle('rv_dom_document_get_active_view_transition', [P], page.document)
        n.expect(active == result.value, 'document exposes the active transition')
        n.bind('rv_dom_view_transition_release', None, [P])(active)
        type_set = n.handle('rv_dom_view_transition_get_types', [P], result)
        n.expect(n.integer('rv_dom_view_transition_type_set_size', type_set, ctypes.c_uint32) == 0, 'initial empty types')
        for name in [b'slide', b'fade', b'slide']:
            n.ok('rv_dom_view_transition_type_set_add', [P, P, I], type_set, name, len(name))
        n.expect(n.integer('rv_dom_view_transition_type_set_size', type_set, ctypes.c_uint32) == 2, 'types deduplicate')
        snapshot = StringValues()
        n.ok('rv_dom_view_transition_type_set_values', [P, ctypes.POINTER(StringValues)], type_set, ctypes.byref(snapshot))
        n.ok('rv_dom_view_transition_type_set_clear', [P], type_set)
        n.expect([ctypes.string_at(snapshot.items[i].data, snapshot.items[i].length).decode() for i in range(snapshot.count)] == ['slide', 'fade'], 'type snapshot retains insertion order after clear')
        n.bind('rv_dom_sequence_dom_string_release', None, [ctypes.POINTER(StringValues)])(ctypes.byref(snapshot))
        n.bind('rv_dom_view_transition_type_set_release', None, [P])(type_set)
        settled = SETTLED(lambda _, kind, error: log.append((kind, error.decode() if error else None)))
        observer = P()
        n.expect(n.call('rv_view_transition_observe', [P, P, SETTLED, P, ctypes.POINTER(P)], foreign.host, result, settled, None, ctypes.byref(observer)) == -12, 'observation requires the transition document')
        foreign.close()
        n.ok('rv_view_transition_observe', [P, P, SETTLED, P, ctypes.POINTER(P)], page.host, result, settled, None, ctypes.byref(observer))
        deadline = time.monotonic() + 5
        while len(log) < 4 and time.monotonic() < deadline:
            n.call('rv_host_update', [P], page.host)
            n.call('rv_run_loop_cycle', [I], 5)
        n.expect(log == [('update', None), (0, None), (1, None), (2, None)], f'update and settlement order: {log}')
        n.expect(not n.handle('rv_dom_document_get_active_view_transition', [P], page.document), 'finished clears active transition')
        n.bind('rv_view_transition_observer_release', None, [P])(observer)
        n.bind('rv_dom_view_transition_release', None, [P])(result)
        n.bind('rv_dom_view_transition_update_callback_release', None, [P])(callback)
        n.expect(releases == ['callback'], 'callback context released once')
        for mode in ['skip', 'reject', 'observer-release', 'replacement']:
            events = []
            tick = UPDATE(lambda _, mode=mode: events.append(('update', None)) or (1 if mode == 'reject' else 0))
            released = []
            finalizer = RELEASE(lambda _: released.append(True))
            cb = n.bind('rv_view_transition_update_callback_create', P, [P, UPDATE, P, RELEASE])(page.host, tick, None, finalizer)
            transition = P()
            args = Options(ctypes.sizeof(Options), cb, None)
            n.expect(start(page.document, ctypes.byref(args), ctypes.byref(transition)) == OK, mode + ': start')
            observer = P()
            sink = SETTLED(lambda _, kind, error: events.append((kind, error.decode() if error else None)))
            n.ok('rv_view_transition_observe', [P, P, SETTLED, P, ctypes.POINTER(P)], page.host, transition, sink, None, ctypes.byref(observer))
            if mode == 'skip':
                n.ok('rv_dom_view_transition_skip_transition', [P], transition)
            if mode == 'observer-release':
                n.bind('rv_view_transition_observer_release', None, [P])(observer)
                observer = P()
            if mode == 'replacement':
                n.ok('rv_host_load_html', [P, P, I], page.host, b'<div>replacement</div>', 22)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                n.call('rv_host_update', [P], page.host)
                n.call('rv_run_loop_cycle', [I], 5)
                if len(events) >= 4 or (mode in ['observer-release', 'replacement'] and time.monotonic() > deadline - 4.8):
                    break
            if mode == 'skip':
                n.expect(events == [(1, 'AbortError'), ('update', None), (0, None), (2, None)], f'skip before update settlement: {events}')
            elif mode == 'reject':
                n.expect(events == [('update', None), (0, 'TypeError'), (1, 'TypeError'), (2, 'TypeError')], f'failed update rejects every promise: {events}')
            elif mode == 'observer-release':
                n.expect(events == [('update', None)], f'released observer stops promise delivery: {events}')
            else:
                n.expect(events == [], f'replaced document stops application callbacks and observations: {events}')
            if observer:
                n.bind('rv_view_transition_observer_release', None, [P])(observer)
            n.bind('rv_dom_view_transition_release', None, [P])(transition)
            n.bind('rv_dom_view_transition_update_callback_release', None, [P])(cb)
            if mode != 'replacement':
                n.expect(released == [True], mode + ': callback context released once')
        return n.assertions
    finally:
        page.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', nargs='?')
    parser.add_argument('--native-directory')
    parser.add_argument('--slim', action='store_true')
    args = parser.parse_args()
    count = run(args.native_directory or args.directory, args.slim)
    print(f'PASS view_transitions: {count} assertions')
