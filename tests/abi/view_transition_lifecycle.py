"""Exercise application teardown/replacement from a native view-transition callback."""

import argparse
import ctypes
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, Case, P, I
from view_transitions import Options, UPDATE, RELEASE, SETTLED

MODES = ('destroy-pending', 'destroy-update', 'replace-update', 'destroy-settlement')


def run_case(directory, mode):
    n = Native(directory)
    if not n.call('rv_abi_has', [ctypes.c_char_p], b'view-transitions'):
        return {'mode': mode, 'unsupported': True, 'assertions': 0}
    page = Case(n, '<style>::view-transition-group(*){animation-duration:0s}</style><div>old</div>')
    events, releases, errors = [], [], []
    action_done = False
    transition, observer = P(), P()
    callback = None

    def close_host():
        nonlocal action_done
        host, page.host = page.host, None
        events.append('destroy-enter')
        n.bind('rv_host_destroy', None, [P])(host)
        events.append('destroy-return')
        print('LIFECYCLE destroy returned', flush=True)
        action_done = True

    def update(_):
        nonlocal action_done
        try:
            events.append('update')
            if mode == 'destroy-update':
                close_host()
            elif mode == 'replace-update':
                text = b'<div>replacement</div>'
                n.ok('rv_host_load_html', [P, P, I], page.host, text, len(text))
                events.append('replace-return')
                print('LIFECYCLE replacement returned', flush=True)
                action_done = True
            return 0
        except Exception as error:
            errors.append(str(error))
            return 1

    def settled(_, kind, error):
        try:
            events.append('settled-' + str(kind))
            if mode == 'destroy-settlement' and not action_done:
                close_host()
        except Exception as exception:
            errors.append(str(exception))

    tick = UPDATE(update)
    release = RELEASE(lambda _: releases.append('release'))
    sink = SETTLED(settled)
    try:
        callback = n.bind('rv_view_transition_update_callback_create', P, [P, UPDATE, P, RELEASE])(page.host, tick, None, release)
        n.expect(bool(callback), 'callback created')
        options = Options(ctypes.sizeof(Options), callback, None)
        n.ok('rv_dom_document_start_view_transition', [P, ctypes.POINTER(Options), ctypes.POINTER(P)], page.document, ctypes.byref(options), ctypes.byref(transition))
        n.ok('rv_view_transition_observe', [P, P, SETTLED, P, ctypes.POINTER(P)], page.host, transition, sink, None, ctypes.byref(observer))
        n.expect(not events, 'update deferred')
        if mode == 'destroy-pending':
            close_host()
        deadline = time.monotonic() + 3
        while not action_done and time.monotonic() < deadline:
            if page.host:
                n.ok('rv_host_update', [P], page.host)
            n.call('rv_run_loop_cycle', [I], 5)
        n.expect(action_done and not errors, 'requested lifecycle action completed: ' + repr(errors))
        before = list(events)
        for _ in range(20):
            n.call('rv_run_loop_cycle', [I], 1)
        n.expect(events == before, 'no late callback after context invalidation')
        n.expect(events.count('update') == (0 if mode == 'destroy-pending' else 1), 'update count')
        n.bind('rv_view_transition_observer_release', None, [P])(observer)
        observer = P()
        n.ok('rv_view_transition_update_callback_revoke', [P], callback)
        n.bind('rv_dom_view_transition_release', None, [P])(transition)
        transition = P()
        n.bind('rv_dom_view_transition_update_callback_release', None, [P])(callback)
        callback = None
        page.close()
        page = None
        for _ in range(20):
            n.call('rv_run_loop_cycle', [I], 1)
        n.expect(releases == ['release'], 'callback context released exactly once')
        with_page = Case(n, '<div>reopened</div>')
        n.ok('rv_host_update', [P], with_page.host)
        with_page.close()
        return {'mode': mode, 'events': events, 'releases': releases, 'assertions': n.assertions}
    finally:
        if observer:
            n.bind('rv_view_transition_observer_release', None, [P])(observer)
        if transition:
            n.bind('rv_dom_view_transition_release', None, [P])(transition)
        if callback:
            n.bind('rv_dom_view_transition_update_callback_release', None, [P])(callback)
        if page:
            page.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--case', choices=MODES)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.case:
        print(json.dumps(run_case(args.native_directory, args.case)), flush=True)
    else:
        rows = []
        for mode in MODES:
            command = [sys.executable, '-I', '-u', __file__, '--native-directory', args.native_directory, '--case', mode]
            child = subprocess.run(command, capture_output=True, text=True, timeout=15)
            rows.append({'mode': mode, 'exit': child.returncode, 'stdout': child.stdout, 'stderr': child.stderr})
            print(json.dumps(rows[-1]), flush=True)
        if args.report:
            args.report.write_text(json.dumps(rows, indent=2))
        sys.exit(0 if all(row['exit'] == 0 for row in rows) else 1)
