"""Due-timer probe against an actual runtime directory: rv_run_loop_cycle(0) fires the WebCore timers that are due at
its entry, also a timer armed while WebCore was firing timers, and one cycle still ends when a timer re-arms itself
with zero delay.

A popover toggle event is an event-loop task, which WebCore runs from a zero-delay timer. A toggle listener that
shows or hides a popover therefore starts a zero-delay timer while timers fire. On Windows the shared timer handed
such a timer to a timer-queue callback, which posts up to a clock tick later, and armed nothing for a task queued
before that post (patches/0083-windows-shared-timer-fire-if-due.patch)."""

import argparse
import ctypes
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, Case, I, P

ROUNDS = 20
REARMS = 50
# A cycle that never returns would otherwise run until the probe's timeout.
HANG_SECONDS = 60
CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p)


class Popovers:
    def __init__(self, native, markup):
        self.native = native
        self.case = Case(native, markup)
        self.show = native.bind('rv_dom_html_element_show_popover', I, [P, P])
        self.hide = native.bind('rv_dom_html_element_hide_popover', I, [P])
        self.nodes, self.callbacks = [], []

    def element(self, identifier):
        node = self.native.bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p, I])(
            self.case.host, identifier, len(identifier))
        self.native.expect(bool(node), 'popover element')
        self.nodes.append(node)
        return node

    def on_toggle(self, node, function):
        callback = CALLBACK(lambda event, data: function() or 0)
        listener = self.native.bind('rv_node_add_event_listener', P, [P, ctypes.c_char_p, I, I, CALLBACK, P])(
            node, b'toggle', 6, 0, callback, None)
        self.native.expect(bool(listener), 'toggle listener')
        self.callbacks.append(callback)
        self.case.listeners.append(listener)

    def close(self):
        for node in self.nodes:
            self.native.bind('rv_node_release', None, [P])(node)
        self.case.close()


def task_after_firing(native, cycle):
    """Each delivery of p's toggle event toggles q from the listener, so a zero-delay timer starts while timers fire.
    The next toggle of p is queued right after that cycle; the first cycle(0) delivers it, and q's toggle with it."""
    popovers = Popovers(native, '<div id=p popover=manual>x</div><div id=q popover=manual>y</div>')
    p, q = popovers.element(b'p'), popovers.element(b'q')
    delivered = {'p': 0, 'q': 0}
    statuses = []

    def toggled_p():
        delivered['p'] += 1
        statuses.append(popovers.show(q, None) if delivered['p'] % 2 else popovers.hide(q))

    popovers.on_toggle(p, toggled_p)
    popovers.on_toggle(q, lambda: delivered.update(q=delivered['q'] + 1))
    cycle(20)
    for index in range(ROUNDS):
        native.expect((popovers.show(p, None) if index % 2 == 0 else popovers.hide(p)) == 0, f'round {index} status')
        cycle(0)
        native.expect(delivered['p'] == index + 1,
                      f'round {index}: the task queued after timers fired was not delivered by the first cycle(0)')
        native.expect(delivered['q'] >= index,
                      f'round {index}: the zero-delay timer started while timers fired was not delivered by the next cycle(0)')
    cycle(0)
    native.expect(delivered['q'] == ROUNDS, f"toggles of q delivered: {delivered['q']} != {ROUNDS}")
    native.expect(statuses == [0] * ROUNDS, 'statuses of the toggles from the listener')
    popovers.close()


def rearming_timer(native, cycle):
    """A listener that toggles its own popover from every toggle event re-arms a zero-delay timer for ever. Each
    cycle(0) returns, and delivers the toggle that was due at its entry. Returns the most toggles one cycle
    delivered."""
    popovers = Popovers(native, '<div id=r popover=manual>x</div>')
    r = popovers.element(b'r')
    state = {'count': 0, 'active': True}
    statuses = []

    def toggled():
        state['count'] += 1
        if state['active']:
            statuses.append(popovers.hide(r) if state['count'] % 2 else popovers.show(r, None))

    popovers.on_toggle(r, toggled)
    cycle(20)
    native.expect(popovers.show(r, None) == 0, 're-arming timer: first show status')
    most = 0
    for index in range(REARMS):
        before = state['count']
        cycle(0)
        native.expect(state['count'] > before, f're-arming timer, cycle {index}: no toggle delivered')
        most = max(most, state['count'] - before)
    state['active'] = False
    cycle(20)
    settled = state['count']
    cycle(20)
    native.expect(state['count'] == settled, 're-arming timer: toggles after the listener stopped')
    native.expect(set(statuses) == {0}, 'statuses of the toggles from the listener')
    popovers.close()
    return most


def expire():
    print(f'FAIL run_loop_due_timers: a run-loop cycle did not return within {HANG_SECONDS} s', flush=True)
    os._exit(1)


def verify(native_directory):
    native = Native(native_directory)
    cycle = native.bind('rv_run_loop_cycle', I, [I])
    guard = threading.Timer(HANG_SECONDS, expire)
    guard.daemon = True
    guard.start()
    task_after_firing(native, cycle)
    most = rearming_timer(native, cycle)
    guard.cancel()
    return native.assertions, most


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    args = parser.parse_args()
    assertions, most = verify(args.native_directory)
    print(f'PASS run_loop_due_timers: {assertions} assertions (a re-arming timer fired at most {most} times in one cycle)',
          flush=True)


if __name__ == '__main__':
    main()
