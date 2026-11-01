"""Web Animations custom effects (A09): rv_custom_effect_callback_create/_revoke with the generated
rv_dom_custom_effect_create and rv_dom_document_timeline_animate.

Replays tests/fixtures/custom-effects-cases.json: each timing case drives a paused custom effect to each seek time, and
the progress its tick receives after the rendering update is compared with the Chromium oracle
tests/fixtures/custom-effects-oracle.json (the progress of a null-target KeyframeEffect of the same timing; a null
progress delivers nothing). It then checks the delivery contract: ticks are queued during rv_host_update and delivered
on rv_run_loop_cycle, updates in order and within an update in animation order; a tick may mutate the DOM, run an update
(whose ticks come on a later turn, never nested), cancel its animation, create an effect or revoke itself, which drops
its queued ticks; revoke, a new document and rv_host_destroy stop delivery; the release callback runs once; a callback
of another host returns RV_ERR_WRONG_HOST; invalid timing returns RV_ERR_DOM_EXCEPTION with Chromium's exception name.
JSC is told to crash on any VM entry the host's DisallowVMEntry refuses (Options::setOption crashOnDisallowedVMEntry)
during every custom effect call (callback create and revoke, effect creation, DocumentTimeline.animate) and inside every
tick, around the application's own calls: no custom effect path runs script. rv_host_update, rv_host_load_html and the
run-loop turns themselves stay unarmed: they attempt a refused VM entry on every page, also on the A01 parent runtime
(pre-existing; docs/animation-effects-evidence/update-vm-entry.txt)."""

import contextlib

import argparse
import ctypes
import json
import math
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, P, I, OK, NULL_ARGUMENT, WRONG_THREAD, DOM_EXCEPTION, WRONG_INTERFACE  # noqa: E402
import web_animations as wa  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
D = ctypes.c_double
WRONG_HOST = -12
TICK = ctypes.CFUNCTYPE(None, P, D)
RELEASE = ctypes.CFUNCTYPE(None, P)
# Progress agrees with Chromium to this much: the engines solve cubic-bezier easing to different precision
# (ease-in at 0.999: WebKit 0.9982844, Chromium 0.9982860); linear and step timing agree exactly.
TOLERANCE = 1e-5
# Turns of the run loop that drain every queued delivery: each delivery is one dispatched task.
DRAIN_TURNS = 4


class EffectTiming(ctypes.Structure):
    _fields_ = wa.EFFECT_TIMING


class CustomAnimationOptions(ctypes.Structure):
    _fields_ = wa.EFFECT_TIMING + [('id', wa.StringInput)]


class TimingUnion(ctypes.Structure):
    _fields_ = [('present', I), ('tag', I), ('arm0', D), ('arm1', ctypes.POINTER(EffectTiming))]


class AnimateUnion(ctypes.Structure):
    _fields_ = [('present', I), ('tag', I), ('arm0', D), ('arm1', ctypes.POINTER(CustomAnimationOptions))]


class Arena(wa.Arena):
    def timing(self, struct, options, timeline=None):
        options = {k: (float('nan') if v == 'NaN' else v) for k, v in options.items()}
        value = super().timing(struct, {k: v for k, v in options.items() if k != 'duration'})
        duration = options.get('duration')
        if isinstance(duration, str):
            data = self.keep(ctypes.create_string_buffer(duration.encode()))
            value.duration = ctypes.pointer(self.keep(wa.Duration(1, 3, 0.0, None, wa.Span(ctypes.cast(data, P), len(duration)))))
        elif duration is not None:
            value.duration = ctypes.pointer(self.keep(wa.Duration(1, 1, float(duration), None, wa.Span(None, 0))))
        if struct is CustomAnimationOptions:
            value.id = self.string(options.get('id', ''))
        return value


class Ticks:
    """The application side: one callback context per label, every delivery in order."""

    def __init__(self, native):
        self.n = native
        self.log = []          # (label, progress) in delivery order
        self.released = []     # labels whose release callback ran
        self.labels = {}
        self.actions = {}      # label -> function run inside its tick
        self.depth = 0
        self.max_depth = 0
        self.inside_call = False
        self.delivered_inside_call = 0
        self.scope = contextlib.nullcontext  # the probe's armed scope
        self.ticks_armed = 0
        self.tick = TICK(self._tick)
        self.release = RELEASE(self._release)

    def _tick(self, context, progress):
        label = self.labels[context]
        if self.inside_call:
            self.delivered_inside_call += 1
        self.depth += 1
        self.max_depth = max(self.max_depth, self.depth)
        self.log.append((label, progress))
        action = self.actions.get(label)
        try:
            with self.scope():
                self.ticks_armed += 1
                if action:
                    action(progress)
        finally:
            self.depth -= 1

    def _release(self, context):
        self.released.append(self.labels[context])

    def create(self, host, label):
        context = len(self.labels) + 1
        self.labels[context] = label
        with self.scope():
            handle = self.n.bind('rv_custom_effect_callback_create', P, [P, TICK, P, RELEASE])(host, self.tick, context, self.release)
        self.n.expect(bool(handle), label + ': callback created')
        return handle

    def take(self):
        log, self.log = self.log, []
        return log


class Probe:
    def __init__(self, native, page, ticks, directory):
        self.n, self.page, self.t, self.directory = native, page, ticks, directory
        self.arena = Arena()
        self.release_effect = native.bind('rv_dom_animation_effect_release', None, [P])
        self.release_target = native.bind('rv_event_target_release', None, [P])
        self.release_callback = native.bind('rv_dom_custom_effect_callback_release', None, [P])
        self.release_timeline = native.bind('rv_dom_animation_timeline_release', None, [P])
        self.armed = False   # arming is available
        self.level = 0       # > 0 while a scope wants the crash armed

    def call(self, name, arguments, *values):
        self.t.inside_call = True
        try:
            return self.n.call(name, arguments, *values)
        finally:
            self.t.inside_call = False

    def _set(self, value):
        # A failed set raises without counting: the number of ticks a running animation receives varies.
        if self.armed and not wa.arm_vm_entry_crash(self.directory, value):
            raise AssertionError('VM-entry crash option not set')

    @contextlib.contextmanager
    def armed_scope(self):
        """Arms the VM-entry crash for a custom effect call or a tick."""
        self.level += 1
        if self.level == 1:
            self._set(True)
        try:
            yield
        finally:
            self.level -= 1
            if self.level == 0:
                self._set(False)

    @contextlib.contextmanager
    def unarmed(self):
        """Disarms the crash for a call that attempts a refused VM entry on every page (pre-existing)."""
        saved, self.level = self.level, 0
        if saved:
            self._set(False)
        try:
            yield
        finally:
            self.level = saved
            if saved:
                self._set(True)

    def update(self, host=None):
        with self.unarmed():
            status = self.call('rv_host_update', [P], host or self.page.host)
        self.n.expect(status == OK, f'rv_host_update: {status}')

    def drain(self):
        for _ in range(DRAIN_TURNS):
            self.n.call('rv_run_loop_cycle', [I], 0)

    def effect(self, callback, timing, document=None):
        result = P()
        with self.armed_scope():
            status = self.call('rv_dom_custom_effect_create', [P, P, ctypes.POINTER(TimingUnion), ctypes.POINTER(P)],
                               document or self.page.document, callback, self.arena.options(TimingUnion, EffectTiming, timing),
                               ctypes.byref(result))
        return status, result.value

    def animation(self, effect, document=None):
        result = P()
        self.n.ok('rv_dom_web_animation_create', [P, P, P, I, ctypes.POINTER(P)], document or self.page.document, effect, None, 0,
                  ctypes.byref(result))
        return result.value

    def animate(self, callback, options, timeline):
        result = P()
        with self.armed_scope():
            status = self.call('rv_dom_document_timeline_animate', [P, P, ctypes.POINTER(AnimateUnion), ctypes.POINTER(P)], timeline,
                               callback, self.arena.options(AnimateUnion, CustomAnimationOptions, options), ctypes.byref(result))
        return status, result.value

    def paused(self, label, timing):
        """A paused animation of a new custom effect, its pending pause resolved, and the ticks so far discarded."""
        callback = self.t.create(self.page.host, label)
        status, effect = self.effect(callback, timing)
        self.n.expect(status == OK, f'{label}: rv_dom_custom_effect_create {status}')
        animation = self.animation(effect)
        self.n.ok('rv_dom_web_animation_pause', [P], animation)
        self.update()
        self.drain()
        self.t.take()
        return callback, effect, animation

    def close(self, callback, effect, animation):
        if animation:
            self.n.call('rv_dom_web_animation_cancel', [P], animation)
            self.release_target(animation)
        if effect:
            self.release_effect(effect)
        if callback:
            self.release_callback(callback)


def close(a, b):
    return a is not None and b is not None and math.isclose(a, b, rel_tol=0, abs_tol=TOLERANCE)


def seeked_cases(p, spec, oracle, failures):
    """Each paused case at each seek time: the update queues the effect's progress, the next run-loop turn delivers it."""
    results = []
    for case, wanted in zip(spec['cases'], oracle['cases']):
        assert case['name'] == wanted['name']
        callback, effect, animation = p.paused(case['name'], case['timing'])
        samples = []
        for time, expected in wanted['samples']:
            wa.seek(p.n, animation, time)
            p.update()
            p.n.expect(p.t.log == [], f"{case['name']}@{time}: nothing delivered inside rv_host_update")
            p.drain()
            got = [progress for label, progress in p.t.take()]
            samples.append([time, got])
            if expected is None:
                if got:
                    failures.append({'case': case['name'], 'time': time, 'expected': None, 'got': got})
                p.n.expect(not got, f"{case['name']}@{time}: null progress delivers nothing")
            else:
                ok = bool(got) and all(close(value, expected) for value in got)
                if not ok:
                    failures.append({'case': case['name'], 'time': time, 'expected': expected, 'got': got})
                p.n.expect(ok, f"{case['name']}@{time}: progress {got} == {expected}")
        name = p.n.text('rv_dom_animation_effect_get_interface_name', [P], effect)
        p.n.expect(name == 'CustomEffect', f"{case['name']}: interface name {name}")
        p.close(callback, effect, animation)
        results.append({'name': case['name'], 'samples': samples})
    return results


def timing_errors(p, spec, oracle, failures):
    results = []
    callback = p.t.create(p.page.host, 'errors')
    for case, wanted in zip(spec['errors'], oracle['errors']):
        status, effect = p.effect(callback, case['timing'])
        name = wa.exception_name(p.n) if status == DOM_EXCEPTION else None
        results.append({'name': case['name'], 'status': status, 'exception': name})
        ok = status == DOM_EXCEPTION and name == wanted['error']
        if not ok:
            failures.append({'error': case['name'], 'status': status, 'exception': name, 'expected': wanted['error']})
        p.n.expect(ok, f"{case['name']}: {status} {name} vs {wanted['error']}")
        p.n.expect(not effect, case['name'] + ': no effect')
        timeline = p.page.timeline()
        status, animation = p.animate(callback, case['timing'], timeline)
        name = wa.exception_name(p.n) if status == DOM_EXCEPTION else None
        p.n.expect(status == DOM_EXCEPTION and name == wanted['error'], f"animate {case['name']}: {status} {name}")
        p.n.expect(not animation, case['name'] + ': no animation')
        p.release_timeline(timeline)
    p.release_callback(callback)
    return results


def animate_contract(p):
    """DocumentTimeline.animate plays at once with the id; a running effect ticks with non-decreasing progress; cancel stops it."""
    callback = p.t.create(p.page.host, 'animate')
    timeline = p.page.timeline()
    status, animation = p.animate(callback, {'duration': 400, 'id': 'fx'}, timeline)
    p.n.expect(status == OK and bool(animation), f'animate: {status}')
    p.n.expect(p.n.text('rv_dom_web_animation_get_id', [P], animation) == 'fx', 'animate: id')
    p.n.expect(wa.play_state(p.n, animation) == 'running', 'animate: running')
    effect = p.n.handle('rv_dom_web_animation_get_effect', [P], animation, nullable=False)
    p.n.expect(p.n.text('rv_dom_animation_effect_get_interface_name', [P], effect) == 'CustomEffect', 'animate: CustomEffect')
    progress = []
    for _ in range(12):
        p.update()
        p.drain()
        progress += [value for label, value in p.t.take()]
        p.n.call('rv_run_loop_cycle', [I], 10)
    p.n.expect(len(progress) >= 2, f'animate: ticks while running ({len(progress)})')
    p.n.expect(all(0 <= v <= 1 for v in progress), 'animate: progress within [0, 1]')
    p.n.expect(all(a <= b + TOLERANCE for a, b in zip(progress, progress[1:])), 'animate: progress non-decreasing')
    p.n.ok('rv_dom_web_animation_cancel', [P], animation)
    for _ in range(3):
        p.update()
        p.drain()
    p.n.expect(p.t.take() == [], 'animate: no tick after cancel')
    # A number is the duration.
    status, second = p.animate(callback, 250, timeline)
    p.n.expect(status == OK, 'animate(number)')
    p.n.ok('rv_dom_web_animation_cancel', [P], second)
    p.release_target(second)
    p.release_effect(effect)
    p.release_target(animation)
    p.release_timeline(timeline)
    p.release_callback(callback)
    p.drain()
    p.t.take()
    return {'ticks': len(progress), 'first': progress[0] if progress else None}


def ordering(p):
    """Three effects in one update arrive in animation order; two updates arrive in update order."""
    made = [p.paused(label, {'duration': 1000}) for label in ('A', 'B', 'C')]
    for _, _, animation in made:
        wa.seek(p.n, animation, 100)
    p.update()
    p.drain()
    one = [label for label, _ in p.t.take()]
    p.n.expect(one == ['A', 'B', 'C'], f'one update in animation order: {one}')
    # Two updates before the run loop turns: the first update's ticks, then the second's.
    for _, _, animation in made:
        wa.seek(p.n, animation, 200)
    p.update()
    for _, _, animation in made:
        wa.seek(p.n, animation, 300)
    p.update()
    p.n.expect(p.t.log == [], 'two updates: nothing delivered inside the calls')
    p.drain()
    two = [(label, round(value, 6)) for label, value in p.t.take()]
    p.n.expect(two == [('A', 0.2), ('B', 0.2), ('C', 0.2), ('A', 0.3), ('B', 0.3), ('C', 0.3)], f'two updates in order: {two}')
    for item in made:
        p.close(*item)
    return {'oneUpdate': one, 'twoUpdates': two}


def reentrancy(p):
    """A tick may mutate the DOM, run an update, cancel its animation, create an effect and revoke itself."""
    out = {}
    target = p.page.element('box')
    set_style_utf8 = p.n.bind('rv_element_set_style', I, [P, ctypes.c_char_p, ctypes.c_char_p, I, I])
    set_style = lambda node, name, value: set_style_utf8(node, name, value, len(value), 0)  # utf8 length, not important
    # 1. DOM mutation inside a tick lands in the next update.
    cb, effect, anim = p.paused('mutate', {'duration': 1000})
    p.t.actions['mutate'] = lambda progress: p.n.expect(set_style(target, b'opacity', str(round(progress, 3)).encode()) == OK, 'mutate: set style')
    wa.seek(p.n, anim, 400)
    p.update()
    p.drain()
    p.n.expect(len(p.t.take()) == 1, 'mutate: one tick')
    p.update()
    out['mutated'] = wa.computed(p.n, target, 'opacity')
    p.n.expect(out['mutated'] == '0.4', f"mutate: computed opacity {out['mutated']}")
    p.t.actions.pop('mutate')
    p.close(cb, effect, anim)
    # 2. An update inside a tick: its ticks arrive on a later turn, never nested.
    cb, effect, anim = p.paused('nested', {'duration': 1000})
    count = {'n': 0}

    def nested(progress):
        count['n'] += 1
        if count['n'] == 1:
            wa.seek(p.n, anim, 600)
            p.update()
    p.t.actions['nested'] = nested
    wa.seek(p.n, anim, 500)
    p.update()
    p.drain()
    got = [round(v, 6) for _, v in p.t.take()]
    p.n.expect(got[:2] == [0.5, 0.6], f'nested: update inside a tick delivers later {got}')
    p.n.expect(p.t.max_depth == 1, f'nested: no nested tick (depth {p.t.max_depth})')
    out['nested'] = got
    p.t.actions.pop('nested')
    p.close(cb, effect, anim)
    # 3. Revoke from inside a tick drops the ticks already queued for it.
    cb, effect, anim = p.paused('selfRevoke', {'duration': 1000})
    p.t.actions['selfRevoke'] = lambda progress: p.n.ok('rv_custom_effect_callback_revoke', [P], cb)
    wa.seek(p.n, anim, 100)
    p.update()
    wa.seek(p.n, anim, 200)
    p.update()
    p.drain()
    got = p.t.take()
    p.n.expect([round(v, 6) for _, v in got] == [0.1], f'self revoke: the queued second tick is dropped {got}')
    wa.seek(p.n, anim, 300)
    p.update()
    p.drain()
    p.n.expect(p.t.take() == [], 'self revoke: no tick after revoke')
    with p.armed_scope():
        p.n.ok('rv_custom_effect_callback_revoke', [P], cb)  # a second revoke does nothing
    out['selfRevoke'] = [v for _, v in got]
    p.t.actions.pop('selfRevoke')
    p.close(cb, effect, anim)
    # 4. Cancel its own animation inside a tick: no tick after.
    cb, effect, anim = p.paused('cancel', {'duration': 1000})

    def cancel(progress):
        # Animation.cancel rejects the animation's promises, which attempts a refused VM entry (pre-existing).
        with p.unarmed():
            p.n.ok('rv_dom_web_animation_cancel', [P], anim)
    p.t.actions['cancel'] = cancel
    wa.seek(p.n, anim, 100)
    p.update()
    p.drain()
    p.n.expect(len(p.t.take()) == 1, 'cancel: one tick')
    p.n.expect(wa.play_state(p.n, anim) == 'idle', 'cancel: idle')
    for _ in range(2):
        p.update()
        p.drain()
    p.n.expect(p.t.take() == [], 'cancel: no tick after')
    p.t.actions.pop('cancel')
    p.close(cb, None, anim)
    p.release_effect(effect)
    # 5. Create an effect and an animation inside a tick; it ticks on the next update.
    cb, effect, anim = p.paused('creator', {'duration': 1000})
    made = {}

    def creator(progress):
        if made:
            return
        made['cb'] = p.t.create(p.page.host, 'created')
        status, made['effect'] = p.effect(made['cb'], {'duration': 1000})
        p.n.expect(status == OK, 'creator: effect inside a tick')
        made['anim'] = p.animation(made['effect'])
        p.n.ok('rv_dom_web_animation_pause', [P], made['anim'])
        wa.seek(p.n, made['anim'], 700)
    p.t.actions['creator'] = creator
    wa.seek(p.n, anim, 100)
    p.update()
    p.drain()
    p.update()
    p.drain()
    created = [round(v, 6) for label, v in p.t.take() if label == 'created']
    p.n.expect(created and created[-1] == 0.7, f'creator: the new effect ticks {created}')
    p.t.actions.pop('creator')
    p.close(made['cb'], made['effect'], made['anim'])
    p.close(cb, effect, anim)
    return out


def revocation(p, native):
    """Revoke before the turn drops queued ticks; a new document and host destroy stop delivery; release runs once."""
    out = {}
    cb, effect, anim = p.paused('revoke', {'duration': 1000})
    wa.seek(p.n, anim, 100)
    p.update()
    with p.armed_scope():
        p.n.ok('rv_custom_effect_callback_revoke', [P], cb)
    p.drain()
    p.n.expect(p.t.take() == [], 'revoke: queued tick dropped')
    p.close(cb, effect, anim)
    # A second host: its document replaced, then destroyed.
    with p.unarmed():
        other = wa.Page(native, '<div id="x"></div>')
    try:
        cb2 = p.t.create(other.host, 'otherHost')
        # WRONG_HOST: a callback of another host's document, for the constructor and for animate.
        status, effect2 = p.effect(cb2, {'duration': 1000})
        p.n.expect(status == WRONG_HOST and not effect2, f'wrong host: create {status}')
        timeline = p.page.timeline()
        status, anim2 = p.animate(cb2, {'duration': 1000}, timeline)
        p.n.expect(status == WRONG_HOST and not anim2, f'wrong host: animate {status}')
        p.release_timeline(timeline)
        status, effect2 = p.effect(cb2, {'duration': 1000}, other.document)
        p.n.expect(status == OK, 'other host: create')
        anim2 = p.animation(effect2, other.document)
        p.n.ok('rv_dom_web_animation_pause', [P], anim2)
        p.update(other.host)
        p.drain()
        p.t.take()
        wa.seek(p.n, anim2, 500)
        p.update(other.host)
        with p.unarmed():
            p.n.ok('rv_host_load_html', [P, ctypes.c_char_p, I], other.host, b'<p>new</p>', len(b'<p>new</p>'))  # utf8
        p.drain()
        p.n.expect(p.t.take() == [], 'new document: queued tick dropped')
        new_document = p.n.bind('rv_host_document', P, [P])(other.host)
        status, stale = p.effect(cb2, {'duration': 1000}, new_document)
        p.n.expect(status == WRONG_HOST, f'new document: old callback is another document\'s ({status})')
        p.n.bind('rv_node_release', None, [P])(new_document)
        p.n.call('rv_dom_web_animation_cancel', [P], anim2)
        p.release_target(anim2)
        p.release_effect(effect2)
        # Host destroy: a fresh callback of the new document, its tick queued, then the host destroyed.
        cb3 = p.t.create(other.host, 'destroyed')
        new_document = p.n.bind('rv_host_document', P, [P])(other.host)
        status, effect3 = p.effect(cb3, {'duration': 1000}, new_document)
        p.n.expect(status == OK, 'destroy: create')
        anim3 = p.animation(effect3, new_document)
        p.n.ok('rv_dom_web_animation_pause', [P], anim3)
        p.update(other.host)
        p.drain()
        p.t.take()
        wa.seek(p.n, anim3, 300)
        p.update(other.host)
        p.release_target(anim3)
        p.release_effect(effect3)
        p.n.bind('rv_node_release', None, [P])(new_document)
    finally:
        with p.unarmed():
            other.close()
    p.drain()
    p.n.expect(p.t.take() == [], 'destroy: queued tick dropped')
    p.release_callback(cb3)
    p.release_callback(cb2)
    p.n.call('rv_collect_garbage', [])
    p.drain()
    out['released'] = sorted(p.t.released)
    counts = {label: p.t.released.count(label) for label in set(p.t.released)}
    p.n.expect(all(count == 1 for count in counts.values()), f'release runs once per callback {counts}')
    return out


def contract_errors(p):
    n = p.n
    create = n.bind('rv_custom_effect_callback_create', P, [P, TICK, P, RELEASE])
    n.expect(not create(None, p.t.tick, None, p.t.release), 'create: NULL host')
    n.expect(not create(p.page.host, TICK(), None, p.t.release), 'create: NULL tick')
    n.expect(n.call('rv_custom_effect_callback_revoke', [P], None) == NULL_ARGUMENT, 'revoke: NULL')
    cb = p.t.create(p.page.host, 'contract')
    status, effect = p.effect(None, {'duration': 1})
    n.expect(status == NULL_ARGUMENT, 'create effect: NULL callback')
    status, effect = p.effect(cb, {'duration': 1}, p.page.element('box'))
    n.expect(status == WRONG_INTERFACE, f'create effect: element is no document ({status})')
    status, effect = p.effect(cb, None)
    n.expect(status == OK and bool(effect), 'create effect: options default {}')
    p.release_effect(effect)
    results = {}

    def other_thread():
        results['create'] = create(p.page.host, p.t.tick, None, p.t.release)
        results['revoke'] = n.call('rv_custom_effect_callback_revoke', [P], cb)
        r = P()
        results['effect'] = n.call('rv_dom_custom_effect_create', [P, P, P, ctypes.POINTER(P)], p.page.document, cb, None, ctypes.byref(r))
    thread = threading.Thread(target=other_thread)
    thread.start()
    thread.join()
    n.expect(not results['create'], 'create: wrong thread')
    n.expect(results['revoke'] == WRONG_THREAD, 'revoke: wrong thread')
    n.expect(results['effect'] == WRONG_THREAD, 'effect: wrong thread')
    n.expect(n.call('rv_abi_has', [ctypes.c_char_p], b'animation-custom-effects') == 1, 'feature animation-custom-effects')
    n.expect(n.call('rv_abi_has', [ctypes.c_char_p], b'dom:CustomEffect') == 1, 'feature dom:CustomEffect')
    p.release_callback(cb)


def verify(directory, arm=True):
    native = Native(directory)
    spec = json.loads((FIXTURES / 'custom-effects-cases.json').read_text(encoding='utf-8'))
    oracle = json.loads((FIXTURES / 'custom-effects-oracle.json').read_text(encoding='utf-8'))
    native.expect(oracle['presence'] == {'CustomEffect': False, 'timelineAnimate': False}, 'the oracle browser has no CustomEffect')
    page = wa.Page(native, '<title>t</title><div id="box" style="width:40px;height:40px;background:blue"></div>'
                           '<script>document.title = "script ran"</script>')
    ticks = Ticks(native)
    probe = Probe(native, page, ticks, directory)
    failures = []
    armed = wa.arm_vm_entry_crash(directory) if arm else False
    probe.armed = armed
    if armed:
        wa.arm_vm_entry_crash(directory, False)
    ticks.scope = probe.armed_scope
    try:
        results = {
            'cases': seeked_cases(probe, spec, oracle, failures),
            'errors': timing_errors(probe, spec, oracle, failures),
            'animate': animate_contract(probe),
            'ordering': ordering(probe),
            'reentrancy': reentrancy(probe),
            'revocation': revocation(probe, native),
        }
        contract_errors(probe)
        page.guard('custom effects')
        native.expect(ticks.delivered_inside_call == 0, f'no tick delivered inside a call ({ticks.delivered_inside_call})')
        native.expect(native.text('rv_dom_document_get_title', [P], page.document) == 't', 'no script ran')
    finally:
        if armed:
            wa.arm_vm_entry_crash(directory, False)
        page.close()
    return native, results, failures, oracle['browser'], armed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence')
    parser.add_argument('--diagnose-without-vm-entry-crash', action='store_true')
    args = parser.parse_args()
    native, results, failures, browser, armed = verify(args.native_directory, not args.diagnose_without_vm_entry_crash)
    if args.evidence:
        Path(args.evidence).write_text(json.dumps({'oracle': browser, 'assertions': native.assertions, 'failures': failures,
                                                   'vmEntryCrashArmed': armed, **results}, indent=1) + '\n', encoding='utf-8')
    for failure in failures:
        print('MISMATCH', json.dumps(failure))
    if failures:
        raise SystemExit(f'{len(failures)} checks differ from {browser}')
    print(f'PASS custom effects: {native.assertions} assertions against {browser}; VM-entry crash armed: {armed}')


if __name__ == '__main__':
    main()
