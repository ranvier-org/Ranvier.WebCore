"""D16 dialog, popover and command invoker probe against an actual runtime directory. Replays
tests/fixtures/dialog-popover-cases.json through the HTMLDialogElement, popover, popovertarget and command members,
trusted keyboard and mouse input, and ToggleEvent and CommandEvent, then compares each step with the Chromium oracle
tests/fixtures/dialog-popover-oracle.json. Steps listed in QUALIFIED carry a measured engine difference. The teardown
part holds an open modal dialog past rv_host_destroy and an open popover past document replacement."""

import argparse
import ctypes
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8, StringInput, string_input

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
OK, NULL_ARGUMENT, WRONG_THREAD, DOM_EXCEPTION, UNSUPPORTED, WRONG_INTERFACE = 0, -1, -2, -3, -9, -11
CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p)
ABI = 54
CAPTURE = 1
P, I, D = ctypes.c_void_p, ctypes.c_int32, ctypes.c_double
QUALIFIED = {}


class ShowPopoverOptions(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('source', P)]


class TogglePopoverOptions(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('source', P), ('force', ctypes.POINTER(I))]


class ToggleUnion(ctypes.Structure):
    _fields_ = [('present', I), ('tag', I), ('arm0', ctypes.POINTER(TogglePopoverOptions)), ('arm1', I)]


class EventInit(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('bubbles', I), ('cancelable', I), ('composed', I)]


class Runner:
    """Runs case steps on one probe host. Bindings absent from the runtime are recorded in `missing`."""

    def __init__(self, probe):
        self.p = probe
        self.missing = set()
        self.events = []
        self.prevent = []
        self.listeners = []
        self.keep = []

    def optional(self, name, result, arguments):
        try:
            return self.p.bind(name, result, arguments)
        except AssertionError:
            self.missing.add(name)
            return None

    def string(self, function, *values):
        buffer, length = ctypes.create_string_buffer(4096), I()
        status = function(*values, buffer, len(buffer), ctypes.byref(length))
        return status, (None if length.value < 0 else buffer.raw[:length.value].decode())

    def label(self, node):
        if not node:
            return None
        status, ident = self.string(self.p.bind('rv_dom_element_get_id', I, [P, P, I, ctypes.POINTER(I)]), node)
        if status == OK and ident:
            return ident
        return self.string(self.p.bind('rv_dom_node_get_node_name', I, [P, P, I, ctypes.POINTER(I)]), node)[1]

    def exception(self):
        return self.string(self.p.bind('rv_last_exception', I, [I, P, I, ctypes.POINTER(I)]), 0)[1]

    def outcome(self, status, value=None):
        if status == OK:
            return {'status': 'ok', 'value': value}
        if status == DOM_EXCEPTION:
            return {'status': self.exception(), 'value': None}
        return {'status': 'native:' + str(status), 'value': None}

    def node(self, ident):
        result = self.p.bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])(self.p.host, ident.encode())
        self.p.expect(bool(result), 'element ' + ident)
        self.keep.append(result)
        return result

    def load(self, markup, types):
        self.p.load(markup, standalone=False)
        self.document = self.p.bind('rv_host_document', P, [P])(self.p.host)
        self.p.expect(bool(self.document), 'document')
        self.p.call('rv_host_set_focused', [P, I], self.p.host, 1)
        add = self.p.bind('rv_node_add_event_listener', P, [P, ctypes.c_char_p, I, CALLBACK, P])
        for kind in types:
            callback = CALLBACK(self.record)
            self.keep.append(callback)
            listener = add(self.document, kind.encode(), CAPTURE, callback, None)
            self.p.expect(bool(listener), 'listener ' + kind)
            self.listeners.append(listener)
        self.p.update()

    def event_fields(self, event):
        p = self.p
        flag = lambda name: (lambda value: (p.bind('rv_dom_event_get_' + name, I, [P, ctypes.POINTER(I)])(event, ctypes.byref(value)), value.value)[1])(I())
        status, kind = self.string(p.bind('rv_event_type', I, [P, P, I, ctypes.POINTER(I)]), event)
        target = p.bind('rv_event_target', P, [P, I])(event, 0)
        label = self.label(target)
        if target:
            p.bind('rv_node_release', None, [P])(target)
        entry = {'type': kind, 'target': label,
                 'trusted': bool(flag('is_trusted')), 'cancelable': bool(flag('cancelable'))}
        if kind in ('beforetoggle', 'toggle'):
            entry.update(self.toggle_fields(event))
        if kind == 'command':
            entry.update(self.command_fields(event))
        return entry

    def toggle_fields(self, event):
        found = {}
        for field in ['old_state', 'new_state']:
            getter = self.optional('rv_dom_toggle_event_get_' + field, I, [P, P, I, ctypes.POINTER(I)])
            found['oldState' if field == 'old_state' else 'newState'] = self.string(getter, event)[1] if getter else 'absent'
        found['source'] = self.event_source('rv_dom_toggle_event_get_source', event)
        return found

    def command_fields(self, event):
        getter = self.optional('rv_dom_command_event_get_command', I, [P, P, I, ctypes.POINTER(I)])
        return {'command': self.string(getter, event)[1] if getter else 'absent',
                'source': self.event_source('rv_dom_command_event_get_source', event)}

    def event_source(self, name, event):
        getter = self.optional(name, I, [P, ctypes.POINTER(P)])
        if not getter:
            return 'absent'
        result = P()
        status = getter(event, ctypes.byref(result))
        if status != OK:
            return 'native:' + str(status)
        label = self.label(result.value)
        if result.value:
            self.p.bind('rv_node_release', None, [P])(result.value)
        return label

    def record(self, context, event):
        entry = self.event_fields(event)
        if entry['type'] in self.prevent:
            self.prevent.remove(entry['type'])
            self.p.bind('rv_event_prevent_default', None, [P])(event)
            entry['prevented'] = bool(self.p.bind('rv_event_default_prevented', I, [P])(event))
        self.events.append(entry)
        return 0

    def drain(self):
        """Cycles the run loop until the queued toggle and close tasks have run: three consecutive cycles deliver
        no event."""
        cycle = self.p.bind('rv_run_loop_cycle', I, [I])
        seen, quiet = len(self.events), 0
        for _ in range(200):
            cycle(1)
            if len(self.events) == seen:
                quiet += 1
                if quiet == 3:
                    return
            else:
                seen, quiet = len(self.events), 0
        raise AssertionError('the run loop kept delivering events')

    def flush(self):
        for _ in range(3):
            self.p.bind('rv_run_loop_cycle', I, [I])(16)
            self.p.update()

    def element_prop(self, getter, target):
        result = P()
        status = getter(target, ctypes.byref(result))
        label = self.label(result.value) if status == OK else None
        if result.value:
            self.p.bind('rv_node_release', None, [P])(result.value)
        return self.outcome(status, label)

    def interface(self, target):
        """The generated binding prefix for the element's interface."""
        name = self.label(target) and self.string(self.p.bind('rv_dom_node_get_node_name', I, [P, P, I, ctypes.POINTER(I)]), target)[1]
        return {'DIALOG': 'html_dialog_element', 'BUTTON': 'html_button_element', 'INPUT': 'html_input_element'}.get(name, 'html_element')

    def prop(self, target, name):
        p, kind = self.p, self.interface(target)
        text = lambda member: self.outcome(*self.string(p.bind('rv_dom_' + member, I, [P, P, I, ctypes.POINTER(I)]), target))
        if name == 'open':
            value = I()
            return self.outcome(p.bind('rv_dom_html_dialog_element_get_open', I, [P, ctypes.POINTER(I)])(target, ctypes.byref(value)), bool(value.value))
        if name in ('returnValue', 'closedBy'):
            return text('html_dialog_element_get_' + ('return_value' if name == 'returnValue' else 'closed_by'))
        if name == 'popover':
            return text('html_element_get_popover')
        if name == 'popoverTargetAction':
            return text(kind + '_get_popover_target_action')
        if name == 'command':
            return text('html_button_element_get_command')
        if name in ('popoverTargetElement', 'commandForElement'):
            member = kind + '_get_popover_target_element' if name == 'popoverTargetElement' else 'html_button_element_get_command_for_element'
            return self.element_prop(p.bind('rv_dom_' + member, I, [P, ctypes.POINTER(P)]), target)
        raise AssertionError('prop ' + name)

    def set(self, target, name, value):
        p, kind = self.p, self.interface(target)
        if name == 'open':
            return self.outcome(p.bind('rv_dom_html_dialog_element_set_open', I, [P, I])(target, int(value)))
        if name in ('popoverTargetElement', 'commandForElement'):
            member = kind + '_set_popover_target_element' if name == 'popoverTargetElement' else 'html_button_element_set_command_for_element'
            return self.outcome(p.bind('rv_dom_' + member, I, [P, P])(target, self.node(value) if value else None))
        member = {'returnValue': 'html_dialog_element_set_return_value', 'closedBy': 'html_dialog_element_set_closed_by',
                  'popover': 'html_element_set_popover', 'popoverTargetAction': kind + '_set_popover_target_action',
                  'command': 'html_button_element_set_command'}[name]
        return self.outcome(p.bind('rv_dom_' + member, I, [P, Utf8])(target, None if value is None else value.encode()))

    def construct(self, interface, kind, init, document):
        """Builds a ToggleEvent or CommandEvent; returns (status, event) or ('absent', None)."""
        prefix = 'rv_dom_toggle_event' if interface == 'ToggleEvent' else 'rv_dom_command_event'
        create = self.optional(prefix + '_create', I, [P, P, I, P, ctypes.POINTER(P)])
        if not create:
            return 'absent', None
        dictionary = make_init(interface, init, self.node)
        encoded = kind.encode()
        event = P()
        status = create(document, encoded, len(encoded), ctypes.byref(dictionary), ctypes.byref(event))
        return status, event.value

    def describe(self, event, interface):
        flag = lambda name: (lambda value: (self.p.bind('rv_dom_event_get_' + name, I, [P, ctypes.POINTER(I)])(event, ctypes.byref(value)), bool(value.value))[1])(I())
        kind = self.string(self.p.bind('rv_event_type', I, [P, P, I, ctypes.POINTER(I)]), event)[1]
        base = {'type': kind, 'bubbles': flag('bubbles'), 'cancelable': flag('cancelable'), 'trusted': flag('is_trusted')}
        base.update(self.toggle_fields(event) if interface == 'ToggleEvent' else self.command_fields(event))
        return base

    def step(self, s):
        p = self.p
        target = self.node(s['id']) if s.get('id') else None
        op = s['op']
        if op == 'prop':
            return self.prop(target, s['name'])
        if op == 'set':
            return {**self.set(target, s['name'], s['value']), 'value': None}
        if op == 'hasAttr':
            value = I()
            return self.outcome(p.bind('rv_dom_element_has_attribute', I, [P, Utf8, ctypes.POINTER(I)])(target, s['name'].encode(), ctypes.byref(value)), bool(value.value))
        if op == 'matches':
            value = I()
            return self.outcome(p.bind('rv_dom_element_matches', I, [P, Utf8, ctypes.POINTER(I)])(target, s['selector'].encode(), ctypes.byref(value)), bool(value.value))
        if op in ('show', 'showModal'):
            return self.outcome(p.bind('rv_dom_html_dialog_element_' + ('show' if op == 'show' else 'show_modal'), I, [P])(target))
        if op in ('close', 'requestClose'):
            value = s.get('value')
            return self.outcome(p.bind('rv_dom_html_dialog_element_' + ('close' if op == 'close' else 'request_close'), I, [P, Utf8])(target, None if value is None else value.encode()))
        if op == 'showPopover':
            options = ShowPopoverOptions(ctypes.sizeof(ShowPopoverOptions), self.node(s['source']) if 'source' in s else None)
            return self.outcome(p.bind('rv_dom_html_element_show_popover', I, [P, ctypes.POINTER(ShowPopoverOptions)])(target, ctypes.byref(options) if 'source' in s else None))
        if op == 'hidePopover':
            return self.outcome(p.bind('rv_dom_html_element_hide_popover', I, [P])(target))
        if op == 'togglePopover':
            result = I()
            union = ToggleUnion(1, 2, None, int(s['force'])) if 'force' in s else None
            status = p.bind('rv_dom_html_element_toggle_popover', I, [P, ctypes.POINTER(ToggleUnion), ctypes.POINTER(I)])(target, ctypes.byref(union) if union else None, ctypes.byref(result))
            return self.outcome(status, bool(result.value))
        if op == 'focus':
            return self.outcome(p.bind('rv_dom_html_element_focus', I, [P, P])(target, None))
        if op in ('active', 'hit'):
            p.update()
            result = P()
            if op == 'active':
                status = p.bind('rv_dom_document_get_active_element', I, [P, ctypes.POINTER(P)])(self.document, ctypes.byref(result))
            else:
                status = p.bind('rv_dom_document_element_from_point', I, [P, D, D, ctypes.POINTER(P)])(self.document, s['x'], s['y'], ctypes.byref(result))
            label = self.label(result.value)
            if result.value:
                p.bind('rv_node_release', None, [P])(result.value)
            return self.outcome(status, label)
        if op == 'click':
            return self.outcome(p.bind('rv_dom_html_element_click', I, [P])(target))
        if op == 'press':
            key = p.bind('rv_host_key', I, [P, I, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, I, I])
            name = s['key'].encode()
            down, up = key(p.host, 0, name, name, None, 0, 0), key(p.host, 1, name, name, None, 0, 0)
            return {'status': 'ok' if down >= 0 and up >= 0 else 'native:' + str((down, up)), 'value': None}
        if op == 'mouse':
            p.update()
            mouse = p.bind('rv_host_mouse', I, [P, I, I, I, I, I, I])
            results = [mouse(p.host, 0, s['x'], s['y'], 0, 0, 0), mouse(p.host, 1, s['x'], s['y'], 0, 1, 0), mouse(p.host, 2, s['x'], s['y'], 0, 1, 0)]
            return {'status': 'ok' if min(results) >= 0 else 'native:' + str(results), 'value': None}
        if op == 'flush':
            self.flush()
            return {'status': 'ok', 'value': None}
        if op == 'prevent':
            self.prevent.append(s['type'])
            return {'status': 'ok', 'value': None}
        if op in ('construct', 'dispatch'):
            status, event = self.construct(s['interface'], s['type'], s['init'], self.document)
            if status == 'absent':
                return {'status': 'absent', 'value': None}
            if status != OK:
                return self.outcome(status)
            try:
                if op == 'construct':
                    return self.outcome(OK, self.describe(event, s['interface']))
                prevented = I()
                status = p.bind('rv_node_dispatch', I, [P, P, ctypes.POINTER(I)])(target, event, ctypes.byref(prevented))
                return self.outcome(status, not prevented.value)
            finally:
                p.bind('rv_event_release', None, [P])(event)
        raise AssertionError('op ' + op)

    def close(self):
        remove = self.p.bind('rv_listener_remove', I, [P])
        for listener in self.listeners:
            self.p.expect(remove(listener) == OK, 'listener removal')
        self.listeners.clear()
        release = self.p.bind('rv_node_release', None, [P])
        for item in self.keep:
            if isinstance(item, int):
                release(item)
        if getattr(self, 'document', None):
            release(self.document)
            self.document = None
        self.keep.clear()


def make_init(interface, init, node):
    """The ctypes ToggleEventInit or CommandEventInit; the field order follows the generated header."""
    strings = {key: string_input(init.get(key, '')) for key in (['oldState', 'newState'] if interface == 'ToggleEvent' else ['command'])}
    source = node(init['source']) if init.get('source') else None
    if interface == 'ToggleEvent':
        class Init(ctypes.Structure):
            _fields_ = [('size', ctypes.c_uint32), ('bubbles', I), ('cancelable', I), ('composed', I),
                        ('old_state', StringInput), ('new_state', StringInput), ('source', P)]
        value = Init(ctypes.sizeof(Init), int(init.get('bubbles', False)), int(init.get('cancelable', False)), 0,
                     strings['oldState'], strings['newState'], source)
    else:
        class Init(ctypes.Structure):
            _fields_ = [('size', ctypes.c_uint32), ('bubbles', I), ('cancelable', I), ('composed', I), ('source', P),
                        ('command', StringInput)]
        value = Init(ctypes.sizeof(Init), int(init.get('bubbles', False)), int(init.get('cancelable', False)), 0,
                     source, strings['command'])
    value._strings = strings
    return value


def replay(native_directory, cases):
    """Runs every case on a fresh host; returns the per-case native steps and the missing bindings."""
    results, missing = [], set()
    for case in cases['cases']:
        with SvgProbe(native_directory, *cases['viewport']) as p:
            runner = Runner(p)
            runner.load(cases['markup'], cases['eventTypes'])
            steps = []
            for s in case['steps']:
                result = runner.step(s)
                # Chromium runs queued tasks between two page.evaluate calls; draining the run loop does the same here.
                runner.drain()
                result['events'] = runner.events[:]
                runner.events.clear()
                steps.append({**s, **result})
            runner.close()
            missing |= runner.missing
            results.append({'name': case['name'], 'steps': steps, 'assertions': p.assertions})
    return results, sorted(missing)


def teardown(native_directory, cases):
    """An open modal dialog and a held ToggleEvent past rv_host_destroy, and an open popover held past document
    replacement. Returns the measured statuses; asserts that held handles stay safe and inert."""
    report = {}
    allowed = (OK, UNSUPPORTED)
    with SvgProbe(native_directory, *cases['viewport']) as p:
        runner = Runner(p)
        runner.load(cases['markup'], cases['eventTypes'])
        dialog = runner.node('m')
        p.watch(dialog)
        p.expect(runner.step({'op': 'showModal', 'id': 'm'})['status'] == 'ok', 'showModal before destroy')
        runner.flush()
        status, held = runner.construct('ToggleEvent', 'toggle', {'oldState': 'closed', 'newState': 'open', 'source': 'cmodal'}, runner.document)
        p.expect(status == OK and bool(held), 'held ToggleEvent')
        runner.events.clear()
        # Listeners are removed before rv_host_destroy, as the ABI requires; the dialog stays open in the top layer.
        remove = p.bind('rv_listener_remove', I, [P])
        for listener in runner.listeners:
            p.expect(remove(listener) == OK, 'listener removal before destroy')
        runner.listeners.clear()
        p.dispose_host()
        value = I(-1)
        open_status = p.bind('rv_dom_html_dialog_element_get_open', I, [P, ctypes.POINTER(I)])(dialog, ctypes.byref(value))
        close_status = p.bind('rv_dom_html_dialog_element_close', I, [P, Utf8])(dialog, b'late')
        after = I(-1)
        after_status = p.bind('rv_dom_html_dialog_element_get_open', I, [P, ctypes.POINTER(I)])(dialog, ctypes.byref(after))
        request_status = p.bind('rv_dom_html_dialog_element_request_close', I, [P, Utf8])(dialog, b'late')
        show_status = p.bind('rv_dom_html_dialog_element_show_modal', I, [P])(dialog)
        p.expect(open_status in allowed and close_status in allowed + (DOM_EXCEPTION,) and request_status in allowed + (DOM_EXCEPTION,)
                 and show_status in allowed + (DOM_EXCEPTION,), 'dialog members after destroy ' + str((open_status, close_status, request_status, show_status)))
        held_fields = runner.toggle_fields(held)
        p.expect(held_fields['oldState'] == 'closed' and held_fields['newState'] == 'open', 'held ToggleEvent reads after destroy ' + str(held_fields))
        p.bind('rv_event_release', None, [P])(held)
        p.collect()
        p.expect(runner.events == [], 'no delivery after destroy: ' + str(runner.events))
        runner.close()
        p.release_all()
        p.collect()
        p.expect_expired()
        report['modalAtDestroy'] = {'open': [open_status, value.value], 'close': close_status, 'openAfterClose': [after_status, after.value], 'requestClose': request_status,
                                    'showModal': show_status, 'heldToggleEvent': held_fields}
    with SvgProbe(native_directory, *cases['viewport']) as p:
        runner = Runner(p)
        runner.load(cases['markup'], cases['eventTypes'])
        old = runner.node('p')
        p.watch(old)
        p.expect(runner.step({'op': 'showPopover', 'id': 'p'})['status'] == 'ok', 'showPopover before replacement')
        runner.flush()
        old_listeners, old_document = runner.listeners[:], runner.document
        runner.listeners.clear()
        runner.events.clear()
        runner.load(cases['markup'], cases['eventTypes'])
        runner.flush()
        replaced = runner.events[:]
        runner.events.clear()
        matches = I(-1)
        old_open = p.bind('rv_dom_element_matches', I, [P, Utf8, ctypes.POINTER(I)])(old, b':popover-open', ctypes.byref(matches))
        hide = p.bind('rv_dom_html_element_hide_popover', I, [P])(old)
        show = p.bind('rv_dom_html_element_show_popover', I, [P, P])(old, None)
        runner.flush()
        late = runner.events[:]
        runner.events.clear()
        p.expect(old_open == OK and hide in allowed + (DOM_EXCEPTION,) and show in allowed + (DOM_EXCEPTION,), 'old popover members ' + str((old_open, hide, show)))
        fresh = runner.step({'op': 'showPopover', 'id': 'p'})
        runner.flush()
        fresh_events = [(e['type'], e['target'], e.get('newState')) for e in runner.events]
        p.expect(fresh['status'] == 'ok' and fresh_events == [('beforetoggle', 'p', 'open'), ('toggle', 'p', 'open')], 'new document popover ' + str(fresh_events))
        remove = p.bind('rv_listener_remove', I, [P])
        for listener in old_listeners:
            p.expect(remove(listener) == OK, 'old listener removal')
        p.bind('rv_node_release', None, [P])(old_document)
        runner.close()
        p.release_all()
        p.collect()
        p.expect_expired()
        report['popoverPastReplacement'] = {'eventsAtReplacement': replaced, 'oldMatchesPopoverOpen': bool(matches.value),
                                            'oldHide': hide, 'oldShow': show, 'eventsAfterOldCalls': late, 'newDocument': fresh_events}
        report['assertions'] = p.assertions
    return report


SYNCHRONOUS = ('beforetoggle', 'cancel', 'command')


def toggle_chain(events):
    """Per target: the close count, the last toggle's newState, and whether each toggle's oldState is the previous
    toggle's newState (the first starts at "closed"). Coalescing changes the toggle count, never these."""
    result = {}
    for target in sorted({ev['target'] for ev in events}):
        toggles = [ev for ev in events if ev['target'] == target and ev['type'] == 'toggle']
        states = ['closed'] + [ev['newState'] for ev in toggles]
        result[target] = {'closes': sum(1 for ev in events if ev['target'] == target and ev['type'] == 'close'),
                          'finalState': states[-1],
                          'chained': all(ev['oldState'] == states[i] for i, ev in enumerate(toggles)),
                          'untrusted': [ev for ev in toggles if not ev['trusted'] or ev['cancelable']]}
    return result


def collapsed_order(events):
    """Per target, the queued toggle/close order with consecutive toggles merged into one."""
    result = {}
    for target in sorted({ev['target'] for ev in events}):
        order = []
        for ev in events:
            if ev['target'] == target and ev['type'] not in SYNCHRONOUS and not (order and order[-1] == ev['type'] == 'toggle'):
                order.append(ev['type'])
        result[target] = order
    return result


def compare(oracle, native):
    """The differences from the oracle, by kind: a step's status or value; the order and fields of the events
    dispatched during a call (beforetoggle, cancel, command); the queued toggle chain of each target; and its
    toggle/close order. Queued events are compared without their step, as both engines deliver them at a task
    boundary, and without their count, as a pending toggle task coalesces with the next toggle."""
    differences = []
    for expected, actual in zip(oracle['cases'], native):
        name = expected['name']
        for index, (e, a) in enumerate(zip(expected['steps'], actual['steps'])):
            if (e['status'], e.get('value')) != (a['status'], a.get('value')):
                differences.append({'case': name, 'step': index, 'op': e['op'], 'kind': 'value',
                                    'chromium': [e['status'], e.get('value')], 'native': [a['status'], a.get('value')]})
        events = lambda case: [ev for s in case['steps'] for ev in s['events']]
        sync = lambda case: [ev for ev in events(case) if ev['type'] in SYNCHRONOUS]
        queued = lambda case: toggle_chain([ev for ev in events(case) if ev['type'] not in SYNCHRONOUS])
        order = lambda case: collapsed_order(events(case))
        for kind, measure in [('dispatched', sync), ('queued', queued), ('queuedOrder', order)]:
            if measure(expected) != measure(actual):
                differences.append({'case': name, 'kind': kind, 'chromium': measure(expected), 'native': measure(actual)})
    return differences


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--report')
    parser.add_argument('--measure', action='store_true', help='record native results and differences without asserting')
    parser.add_argument('--abi', type=int, default=ABI, help='the expected ABI version of a later runtime')
    args = parser.parse_args()
    cases = json.loads((FIXTURES / 'dialog-popover-cases.json').read_text())
    oracle = json.loads((FIXTURES / 'dialog-popover-oracle.json').read_text())
    native, missing = replay(args.native_directory, cases)
    differences = compare(oracle, native)
    report = {'browser': oracle['browser'], 'missing': missing, 'differences': differences, 'cases': native}
    if args.measure:
        if args.report:
            Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
        print(f'measured {len(native)} cases, {len(missing)} missing bindings, {len(differences)} differences', flush=True)
        sys.exit(0)
    qualified = json.loads((FIXTURES / 'dialog-popover-qualified.json').read_text())['differences']
    assertions = sum(case['assertions'] for case in native)
    if missing:
        raise AssertionError('missing bindings: ' + ', '.join(missing))
    strip = lambda items: [{k: v for k, v in item.items() if k not in ('reason', 'qualification')} for item in items]
    unexpected = [d for d in differences if d not in strip(qualified)]
    absent = [q for q in strip(qualified) if q not in differences]
    if unexpected or absent:
        raise AssertionError('differences changed: unexpected ' + json.dumps(unexpected) + ' absent ' + json.dumps(absent))
    comparisons = sum(len(case['steps']) for case in native) + 3 * len(native)
    with SvgProbe(args.native_directory) as p:
        p.expect(p.bind('rv_abi_version', I, [])() == args.abi, 'ABI version ' + str(args.abi))
        for feature in [b'dom:ToggleEvent', b'dom:CommandEvent', b'dom-constructor:ToggleEvent', b'dom-constructor:CommandEvent']:
            p.expect(p.bind('rv_abi_has', I, [ctypes.c_char_p])(feature) == 1, feature.decode() + ' advertised')
        assertions += p.assertions
    lifetime = teardown(args.native_directory, cases)
    assertions += lifetime['assertions'] + comparisons
    report['teardown'] = lifetime
    report['qualified'] = len(qualified)
    report['assertions'] = assertions
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
    print(f'PASS dialog_popover: {assertions} assertions, {len(native)} cases, {len(qualified)} qualified differences', flush=True)
