"""Replays tests/fixtures/animation-lifecycle-cases.json through the generated Web Animations members and the
"animation-promises" operations (rv_animation_ready, rv_animation_finished), and compares them with the Chromium oracle
tests/fixtures/animation-lifecycle-oracle.json: the state-machine walk (playState, pending, replaceState, startTime
presence, playbackRate, currentTime, promise identity) and, per scenario, the ordered promise settlements and the ordered
finish/cancel/remove playback events of each animation, plus the final states.

Completions arrive only from rv_run_loop_cycle (each one is checked to arrive inside it), while engine events dispatch
inside rv_host_update; the probe therefore compares the settlements and the events as two separate orders, per animation,
and one cross-animation order where the scenario causes it (a cancel inside a listener). It also checks the operation
contract: already-settled promises deliver on a later cycle, release and cancel deliver CANCELLED before they return,
rv_host_destroy and a new document deliver INVALIDATED, a released animation handle leaves the operation working, and the
null, thread, interface and host errors. Waits use a hang guard that raises; no count depends on frame timing."""

import argparse
import ctypes
import json
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, P, I, OK, NULL_ARGUMENT, WRONG_THREAD, WRONG_INTERFACE  # noqa: E402
import web_animations as wa  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
WRONG_HOST = -12
SUCCEEDED, CANCELLED, INVALIDATED, ABORTED = 0, 3, 4, 5
REPLACE_STATES = ['active', 'removed', 'persisted']
COMPLETION = ctypes.CFUNCTYPE(None, P, I, I, I)
LISTENER = ctypes.CFUNCTYPE(I, P, P)
KEYFRAMES = [{'props': {'opacity': '0'}}, {'props': {'opacity': '1'}}]
HANG_SECONDS = 5.0


class Probe:
    def __init__(self, native, markup):
        self.n = native
        self.page = wa.Page(native, markup)
        self.where = None        # 'cycle' inside rv_run_loop_cycle, 'release' inside rv_resource_release
        self.calls = []          # (context id, outcome, inside rv_run_loop_cycle)
        self.labels = {}         # context id -> (label, kind)
        self.operations = []
        self.listeners = []
        self.keep = []
        self.log = None
        self.completion = COMPLETION(self.complete)

    # Delivery -------------------------------------------------------------------------------------------------
    def complete(self, context, outcome, width, height):
        self.n.expect(width == 0 and height == 0, 'completion size is 0')
        self.calls.append((context or 0, outcome, self.where))
        label, kind, logged = self.labels.get(context or 0, ('?', '?', False))
        if self.log is not None and logged:
            text = label + ':' + kind + ('' if outcome == SUCCEEDED else ':AbortError' if outcome == ABORTED else ':outcome' + str(outcome))
            self.log['promises'].append(text)
            hook = self.log['hooks'].get(text)
            if hook:
                hook()

    def cycle(self):
        self.where = 'cycle'
        try:
            self.n.call('rv_run_loop_cycle', [I], 0)
        finally:
            self.where = None

    def frame(self):
        self.cycle()
        self.n.call('rv_host_update', [P], self.page.host)
        self.cycle()

    def until(self, condition, label):
        deadline = time.perf_counter() + HANG_SECONDS
        while not condition():
            if time.perf_counter() > deadline:
                raise AssertionError('hang guard: ' + label + ' ' + json.dumps(self.log))
            self.frame()
            time.sleep(0.002)

    def settle(self, rounds=6):
        """Frames past the last expected delivery, so a later extra one would still be recorded."""
        for _ in range(rounds):
            self.frame()
            time.sleep(0.004)

    # Operations -----------------------------------------------------------------------------------------------
    def observe(self, animation, label, kind, host=None, logged=False):
        context = len(self.labels) + 1
        self.labels[context] = (label, kind, logged)
        operation = ctypes.c_uint64()
        name = 'rv_animation_ready' if kind == 'ready' else 'rv_animation_finished'
        before = len(self.calls)
        status = self.n.call(name, [P, P, COMPLETION, P, ctypes.POINTER(ctypes.c_uint64)], host or self.page.host, animation,
                             self.completion, ctypes.c_void_p(context), ctypes.byref(operation))
        self.n.expect(status == OK, name + ' ' + label + ': status ' + str(status))
        self.n.expect(len(self.calls) == before, name + ' ' + label + ': no completion before the call returns')
        self.operations.append(operation.value)
        return operation.value, context

    def outcomes(self, context):
        return [outcome for ident, outcome, _ in self.calls if ident == context]

    def release_all(self):
        release = self.n.bind('rv_resource_release', I, [ctypes.c_uint64])
        self.where = 'release'
        try:
            for operation in self.operations:
                self.n.expect(release(operation) == OK, 'rv_resource_release')
        finally:
            self.where = None
        self.operations = []

    # Animations -----------------------------------------------------------------------------------------------
    def animate(self, element, options):
        return animate(self.n, self.page, element, options)

    def act(self, animation, name, *values):
        arguments = [P] + [ctypes.c_double] * len(values)
        self.n.ok('rv_dom_web_animation_' + name, arguments, animation, *values)

    def time(self, animation, member):
        value = wa.Time()
        self.n.ok('rv_dom_web_animation_get_' + member, [P, ctypes.POINTER(wa.Time)], animation, ctypes.byref(value))
        return value.arm0 if value.present else None

    def state(self, animation, timed=False):
        current = self.time(animation, 'current_time')
        rate = ctypes.c_double()
        self.n.ok('rv_dom_web_animation_get_playback_rate', [P, ctypes.POINTER(ctypes.c_double)], animation, ctypes.byref(rate))
        return {'playState': wa.play_state(self.n, animation), 'pending': bool(self.n.integer('rv_dom_web_animation_get_pending', animation)),
                'replaceState': REPLACE_STATES[self.n.integer('rv_dom_web_animation_get_replace_state', animation)],
                'currentTime': None if current is None else ('number' if timed else number(current)),
                'startTime': None if self.time(animation, 'start_time') is None else 'number', 'playbackRate': number(rate.value)}

    def watch(self, animation, label):
        for kind in ('ready', 'finished'):
            self.observe(animation, label, kind, logged=True)
        for event_type in ('finish', 'cancel', 'remove'):
            callback = LISTENER(lambda context, event, label=label: self.on_event(label, event))
            self.keep.append(callback)
            listener = self.n.bind('rv_event_target_add_listener', P, [P, ctypes.c_char_p, I, LISTENER, P])(animation, event_type.encode(), 0, callback, None)
            self.n.expect(bool(listener), 'listener ' + label + ' ' + event_type)
            self.listeners.append(listener)

    def on_event(self, label, event):
        buffer, length = ctypes.create_string_buffer(64), I()
        self.n.ok('rv_event_type', [P, P, I, ctypes.POINTER(I)], event, buffer, 64, ctypes.byref(length))
        event_type = buffer.raw[:length.value].decode()
        times = []
        for member in ('current_time', 'timeline_time'):
            value = wa.Time()
            self.n.ok('rv_dom_animation_playback_event_get_' + member, [P, ctypes.POINTER(wa.Time)], event, ctypes.byref(value))
            times.append('number' if value.present else 'null')
        text = ':'.join([label, event_type] + times)
        if self.log is not None:
            self.log['events'].append(text)
            hook = self.log['hooks'].get('event ' + text)
            if hook:
                hook()
        return 0

    def unlisten(self):
        for listener in self.listeners:
            self.n.call('rv_listener_remove', [P], listener)
        self.listeners = []

    def close(self):
        self.unlisten()
        self.release_all()
        self.page.close()


def animate(n, page, element, options):
    arena = wa.Arena()
    result = P()
    status = n.call('rv_dom_element_animate', [P, P, P, ctypes.POINTER(P)], page.element(element), arena.keyframes(KEYFRAMES),
                    arena.options(wa.AnimationOptions, wa.KeyframeAnimationOptions, options), ctypes.byref(result))
    n.expect(status == OK and result.value, 'animate ' + element + ': status ' + str(status))
    return result.value


def number(value):
    return int(value) if float(value).is_integer() else value


def run_program(probe, program, wanted):
    """Walks the program on one animation. Promise identity (sameReady, sameFinished) is checked by settlement: an
    operation taken before the step and one taken at the state step observe the same promise exactly when they settle
    identically at the next awaitReady, or at the end of the program after a cancel."""
    n = probe.n
    animation = None
    results = []
    before = {}
    deferred = []

    def resolve_deferred():
        for entry, key, old, now in deferred:
            entry[key] = probe.outcomes(old) == probe.outcomes(now) and bool(probe.outcomes(old))
        deferred.clear()

    for index, step in enumerate(program):
        op = step['op']
        following = program[index + 1] if index + 1 < len(program) else {}
        if op != 'state' and animation is not None and following.get('op') == 'state':
            for kind in ('ready', 'finished'):
                before[kind] = probe.observe(animation, 'identity', kind)[1]
        if op == 'animate':
            animation = probe.animate('a', step['duration'])
            for kind in ('ready', 'finished'):
                before[kind] = probe.observe(animation, 'identity', kind)[1]
        elif op in ('pause', 'play', 'reverse', 'finish', 'cancel', 'persist'):
            probe.act(animation, op)
        elif op == 'seek':
            wa.seek(n, animation, step['value'])
        elif op == 'updatePlaybackRate':
            probe.act(animation, 'update_playback_rate', float(step['value']))
        elif op == 'setPlaybackRate':
            probe.act(animation, 'set_playback_rate', float(step['value']))
        elif op == 'awaitReady':
            _, context = probe.observe(animation, 'program', 'ready')
            probe.until(lambda: probe.outcomes(context), 'program ready')
            n.expect(probe.outcomes(context) == [SUCCEEDED], 'program ready resolved')
            probe.cycle()
            resolve_deferred()
        elif op == 'state':
            entry = {'label': step['label'], **probe.state(animation, step.get('timed', False))}
            for key, kind in (('sameReady', 'ready'), ('sameFinished', 'finished')):
                if step.get(key):
                    deferred.append((entry, key, before[kind], probe.observe(animation, 'identity', kind)[1]))
            results.append(entry)
    probe.act(animation, 'cancel')
    probe.settle(3)
    resolve_deferred()
    n.bind('rv_event_target_release', None, [P])(animation)
    n.expect(len(results) == len(wanted), 'program states')
    for got, expected in zip(results, wanted):
        n.expect(got == expected, 'state ' + expected['label'] + ': ' + json.dumps(got) + ' != ' + json.dumps(expected))
    return results


def scenario(probe, name, body):
    probe.log = {'promises': [], 'events': [], 'hooks': {}}
    finals = body()
    log = probe.log
    probe.log = None
    probe.unlisten()
    probe.release_all()
    return {'promises': log['promises'], 'events': log['events'], 'states': finals}


def scenarios(probe):
    n = probe.n
    out = {}
    release = n.bind('rv_event_target_release', None, [P])
    def done(*labels):
        return lambda: all(any(entry.startswith(label) for entry in probe.log['promises'] + probe.log['events']) for label in labels)

    def finish_call():
        b = probe.animate('b', 1000.0)
        probe.watch(b, 'b')
        probe.act(b, 'finish')
        probe.until(done('b:finished', 'b:finish'), 'finish()')
        probe.settle()
        finals = {'b': probe.state(b)}
        probe.unlisten()
        probe.act(b, 'cancel')
        release(b)
        return finals
    out['finish()'] = scenario(probe, 'finish()', finish_call)

    def cancel_pending():
        c = probe.animate('c', 1000.0)
        probe.watch(c, 'c')
        probe.act(c, 'cancel')
        probe.until(done('c:finished', 'c:cancel'), 'cancel pending')
        probe.settle()
        finals = {'c': probe.state(c)}
        release(c)
        return finals
    out['cancel pending'] = scenario(probe, 'cancel pending', cancel_pending)

    def cancel_running():
        d = probe.animate('c', 1000.0)
        probe.watch(d, 'd')
        probe.until(done('d:ready'), 'cancel running: ready')
        probe.act(d, 'cancel')
        probe.until(done('d:finished', 'd:cancel'), 'cancel running')
        probe.settle()
        finals = {'d': probe.state(d)}
        release(d)
        return finals
    out['cancel running'] = scenario(probe, 'cancel running', cancel_running)

    def cancel_in_listener():
        e, f = probe.animate('a', 1000.0), probe.animate('b', 1000.0)
        probe.watch(e, 'e')
        probe.watch(f, 'f')
        probe.log['hooks']['event e:finish:number:number'] = lambda: probe.act(f, 'cancel')
        probe.until(done('e:ready', 'f:ready'), 'cancel in listener: ready')
        probe.act(e, 'finish')
        probe.until(done('e:finished', 'f:finished', 'e:finish', 'f:cancel'), 'cancel in listener')
        probe.settle()
        finals = {'e': probe.state(e), 'f': probe.state(f)}
        probe.unlisten()
        probe.act(e, 'cancel')
        release(e)
        release(f)
        return finals
    out['cancel in listener'] = scenario(probe, 'cancel in listener', cancel_in_listener)

    def cancel_in_ready():
        g = probe.animate('a', 1000.0)
        probe.watch(g, 'g')
        probe.log['hooks']['g:ready'] = lambda: probe.act(g, 'cancel')
        probe.until(done('g:finished', 'g:cancel'), 'cancel in ready')
        probe.settle()
        finals = {'g': probe.state(g)}
        release(g)
        return finals
    out['cancel in ready'] = scenario(probe, 'cancel in ready', cancel_in_ready)

    def replace():
        options = {'duration': 30, 'fill': 'forwards'}
        x, y = probe.animate('b', options), probe.animate('b', options)
        probe.watch(x, 'x')
        probe.watch(y, 'y')
        probe.until(done('x:remove'), 'replace')
        probe.settle()
        # A finished animation holds max(previous current time, end): past the end when an update came late.
        finals = {'x': probe.state(x, True), 'y': probe.state(y, True)}
        probe.act(x, 'persist')
        finals['xPersisted'] = probe.state(x, True)
        probe.unlisten()
        probe.act(x, 'cancel')
        probe.act(y, 'cancel')
        release(x)
        release(y)
        return finals
    out['replace'] = scenario(probe, 'replace', replace)

    def rewind():
        z = probe.animate('c', 1000.0)
        probe.act(z, 'finish')
        probe.settle(2)
        probe.watch(z, 'z')
        _, old_finished = probe.observe(z, 'old', 'finished')
        wa.seek(n, z, 0)
        probe.watch(z, 'z2')
        probe.until(done('z2:ready'), 'rewind')
        probe.settle()
        _, now_finished = probe.observe(z, 'now', 'finished')
        probe.cycle()
        # The finished promise current after the rewind is a new, pending one: an operation on it stays pending
        # while the one on the old promise has resolved.
        finals = {'z': probe.state(z, True), 'finishedReplaced': probe.outcomes(old_finished) == [SUCCEEDED] and probe.outcomes(now_finished) == []}
        probe.unlisten()
        probe.act(z, 'cancel')
        release(z)
        return finals
    out['rewind finished'] = scenario(probe, 'rewind finished', rewind)
    return out


def labels_of(entries, label):
    return [entry for entry in entries if entry.split(':', 1)[0] == label]


def compare_scenarios(n, got, wanted):
    for name, expected in wanted.items():
        actual = got[name]
        labels = sorted({entry.split(':', 1)[0] for entry in expected['promises'] + expected['events']})
        for label in labels:
            for part in ('promises', 'events'):
                left, right = labels_of(actual[part], label), labels_of(expected[part], label)
                n.expect(left == right, name + ' ' + label + ' ' + part + ': ' + json.dumps(left) + ' != ' + json.dumps(right))
        n.expect(sorted({e.split(':', 1)[0] for e in actual['promises'] + actual['events']}) == labels, name + ': labels')
        n.expect(actual['states'] == expected['states'], name + ' states: ' + json.dumps(actual['states']) + ' != ' + json.dumps(expected['states']))
    # The cancel a listener makes is settled after the finish that dispatched it.
    order = got['cancel in listener']['promises']
    n.expect(order.index('e:finished') < order.index('f:finished:AbortError'), 'cancel in listener: e finished before f aborted')


def contract(probe, directory):
    n = probe.n
    page = probe.page
    call = lambda name, *values: n.call(name, [P, P, COMPLETION, P, ctypes.POINTER(ctypes.c_uint64)], *values)
    operation = ctypes.c_uint64()
    a = probe.animate('a', 1000.0)
    # Errors.
    for name in ('rv_animation_ready', 'rv_animation_finished'):
        n.expect(call(name, None, a, probe.completion, None, ctypes.byref(operation)) == NULL_ARGUMENT, name + ': NULL host')
        n.expect(call(name, page.host, None, probe.completion, None, ctypes.byref(operation)) == NULL_ARGUMENT, name + ': NULL animation')
        n.expect(call(name, page.host, a, COMPLETION(), None, ctypes.byref(operation)) == NULL_ARGUMENT, name + ': NULL completion')
        n.expect(call(name, page.host, a, probe.completion, None, None) == NULL_ARGUMENT, name + ': NULL operation')
        target = n.bind('rv_host_create_event_target', P, [P])(page.host)
        n.expect(call(name, page.host, target, probe.completion, None, ctypes.byref(operation)) == WRONG_INTERFACE, name + ': event target')
        n.bind('rv_event_target_release', None, [P])(target)
        node = n.bind('rv_node_as_event_target', P, [P])(page.element('a'))
        n.expect(call(name, page.host, node, probe.completion, None, ctypes.byref(operation)) == WRONG_INTERFACE, name + ': node')
        n.bind('rv_event_target_release', None, [P])(node)
        statuses = []
        worker = threading.Thread(target=lambda: statuses.append(call(name, page.host, a, probe.completion, None, ctypes.byref(operation))))
        worker.start()
        worker.join()
        n.expect(statuses == [WRONG_THREAD], name + ': wrong thread')
    other = wa.Page(n, '<div id="o"></div>')
    o = animate(n, other, 'o', 1000.0)
    for name in ('rv_animation_ready', 'rv_animation_finished'):
        n.expect(call(name, page.host, o, probe.completion, None, ctypes.byref(operation)) == WRONG_HOST, name + ': another host')
    # The other host's animation is observed through its own host; destroying that host invalidates it.
    _, invalidated = probe.observe(o, 'other', 'finished', host=other.host)
    n.bind('rv_event_target_release', None, [P])(o)
    before = len(probe.calls)
    other.close()
    n.expect(probe.outcomes(invalidated) == [INVALIDATED], 'rv_host_destroy: INVALIDATED')
    n.expect(probe.calls[before][2] is None, 'INVALIDATED is delivered inside rv_host_destroy')
    # Already resolved at the call: delivered on a later cycle, never before the call returns.
    _, ready = probe.observe(a, 'settled', 'ready')
    n.expect(probe.outcomes(ready) == [], 'resolved ready: not delivered during the call')
    probe.until(lambda: probe.outcomes(ready), 'resolved ready')
    n.expect(probe.outcomes(ready) == [SUCCEEDED], 'resolved ready: SUCCEEDED')
    # Release and cancel before completion: CANCELLED before they return, then nothing.
    release = n.bind('rv_resource_release', I, [ctypes.c_uint64])
    cancel = n.bind('rv_resource_cancel', I, [ctypes.c_uint64])
    released, context = probe.observe(a, 'released', 'finished')
    n.expect(release(released) == OK and probe.outcomes(context) == [CANCELLED], 'release before completion: CANCELLED')
    n.expect(release(released) == OK, 'release twice')
    cancelled, cancel_context = probe.observe(a, 'cancelled', 'finished')
    n.expect(cancel(cancelled) == OK and probe.outcomes(cancel_context) == [CANCELLED], 'cancel before completion: CANCELLED')
    # A released animation handle leaves the operation working: the operation holds the animation.
    b = probe.animate('b', 1000.0)
    _, held = probe.observe(b, 'held', 'finished')
    probe.act(b, 'finish')
    n.bind('rv_event_target_release', None, [P])(b)
    probe.until(lambda: probe.outcomes(held), 'released handle')
    n.expect(probe.outcomes(held) == [SUCCEEDED], 'released handle: SUCCEEDED')
    probe.settle(2)
    n.expect(probe.outcomes(context) == [CANCELLED] and probe.outcomes(cancel_context) == [CANCELLED], 'no completion after release or cancel')
    # A new document invalidates pending operations.
    _, pending = probe.observe(a, 'pending', 'finished')
    n.ok('rv_host_load_html', [P, ctypes.c_char_p], page.host, b'<p>next</p>')
    n.expect(probe.outcomes(pending) == [INVALIDATED], 'new document: INVALIDATED')
    n.bind('rv_event_target_release', None, [P])(a)
    n.expect(n.call('rv_abi_has', [ctypes.c_char_p], b'animation-promises') == 1, 'rv_abi_has animation-promises')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--out')
    arguments = parser.parse_args()
    spec = json.loads((FIXTURES / 'animation-lifecycle-cases.json').read_text(encoding='utf-8'))
    oracle = json.loads((FIXTURES / 'animation-lifecycle-oracle.json').read_text(encoding='utf-8'))
    native = Native(arguments.native_directory)
    probe = Probe(native, spec['markup'])
    states = run_program(probe, spec['program'], oracle['states'])
    probe.release_all()
    got = scenarios(probe)
    compare_scenarios(native, got, oracle['scenarios'])
    # Every completion except the ones release, cancel and invalidation deliver arrived inside rv_run_loop_cycle.
    # A terminal reached and not yet delivered is delivered by rv_resource_release before it returns.
    native.expect(all(where in ('cycle', 'release') for _, outcome, where in probe.calls if outcome in (SUCCEEDED, ABORTED)), 'completions only from rv_run_loop_cycle or release')
    delivered = [where for _, outcome, where in probe.calls if outcome in (SUCCEEDED, ABORTED)]
    native.expect('cycle' in delivered, 'completions from rv_run_loop_cycle')
    native.expect(any(outcome == ABORTED for _, outcome, _ in probe.calls), 'ABORTED seen')
    contract(probe, arguments.native_directory)
    probe.close()
    if arguments.out:
        Path(arguments.out).write_text(json.dumps({'states': states, 'scenarios': got}, indent=1) + '\n', encoding='utf-8')
    print(f'PASS animation lifecycle: {native.assertions} assertions against {oracle["browser"]}')


if __name__ == '__main__':
    main()
