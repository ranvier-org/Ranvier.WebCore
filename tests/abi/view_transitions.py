"""A11 same-document transitions through the native ABI, including the slim safety gate."""

import argparse
import ctypes
import sys
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
        log, releases = [], []
        update = UPDATE(lambda _: log.append(('update', None)) or 0)
        release = RELEASE(lambda _: releases.append('callback'))
        callback = n.bind('rv_view_transition_update_callback_create', P, [P, UPDATE, P, RELEASE])(page.host, update, None, release)
        n.expect(bool(callback), 'update callback created')
        options = Options(ctypes.sizeof(Options), callback, None)
        n.expect(start(page.document, ctypes.byref(options), ctypes.byref(result)) == OK and result.value, 'transition started')
        n.expect(not log, 'update is deferred from start')
        settled = SETTLED(lambda _, kind, error: log.append((kind, error.decode() if error else None)))
        observer = P()
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
