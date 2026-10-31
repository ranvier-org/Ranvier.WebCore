"""D14 form submission probe against an actual runtime directory. Replays tests/fixtures/form-submission-cases.json
through requestSubmit, submit, submitter activation, implicit submission, constraint validation and FormData edits,
records the submissions the application handler receives, and compares each case with the Chromium oracle
tests/fixtures/form-submission-oracle.json. The teardown part destroys a host with a submission pending and runs a
submission with no handler set."""

import argparse
import ctypes
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from dialog_popover import Runner, OK, UNSUPPORTED, P, I, CALLBACK
from form_collections import Entries, span_text
from utf8_inputs import Utf8

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
ABI = 54
FILE_ARM, STRING_ARM = 1, 2


class Submission(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('method', ctypes.c_char_p), ('url', ctypes.c_char_p),
                ('target', ctypes.c_char_p), ('content_type', ctypes.c_char_p), ('body', ctypes.POINTER(ctypes.c_uint8)),
                ('body_length', I), ('form', P), ('submitter', P)]


HANDLER = ctypes.CFUNCTYPE(None, P, ctypes.POINTER(Submission))


def normalized(content_type, body):
    """The content type and body with a multipart boundary replaced by BOUNDARY, as the oracle records them."""
    if content_type and 'boundary=' in content_type:
        boundary = content_type.split('boundary=', 1)[1]
        return content_type.replace(boundary, 'BOUNDARY'), body.replace(boundary, 'BOUNDARY')
    return content_type, body


class SubmissionRunner(Runner):
    def __init__(self, probe):
        super().__init__(probe)
        self.submissions = []
        self.append = None
        self.remove_on_submit = None

    def install_handler(self):
        setter = self.optional('rv_host_set_form_submission_handler', I, [P, HANDLER, P])
        if not setter:
            return False
        self.handler = HANDLER(self.received)
        self.p.expect(setter(self.p.host, self.handler, None) == OK, 'submission handler set')
        return True

    def received(self, context, submission):
        s = submission.contents
        body = bytes(s.body[:s.body_length]).decode('utf-8') if s.body_length > 0 else None
        content_type, body = normalized(s.content_type.decode() if s.content_type else None, body)
        self.submissions.append({'method': s.method.decode(), 'url': s.url.decode(), 'contentType': content_type, 'body': body,
                                 'newWindow': s.target.decode() == '_blank', 'form': self.label(s.form), 'submitter': self.label(s.submitter)})

    def entries(self, data):
        result = Entries()
        self.p.call('rv_dom_dom_form_data_entries', [P, P, ctypes.POINTER(Entries)], data, self.document, ctypes.byref(result))
        try:
            return [[span_text(result.items[i].key),
                     {'file': True} if result.items[i].value.tag == FILE_ARM else span_text(result.items[i].value.arm1)]
                    for i in range(result.count)]
        finally:
            self.p.bind('rv_dom_sequence_pair_usv_string_and_union_file_or_usv_string_release', None, [ctypes.POINTER(Entries)])(ctypes.byref(result))

    def event_fields(self, event):
        p = self.p
        flag = lambda name: (lambda value: (p.bind('rv_dom_event_get_' + name, I, [P, ctypes.POINTER(I)])(event, ctypes.byref(value)), value.value)[1])(I())
        kind = self.string(p.bind('rv_event_type', I, [P, P, I, ctypes.POINTER(I)]), event)[1]
        target = p.bind('rv_event_target', P, [P, I])(event, 0)
        entry = {'type': kind, 'target': self.label(target), 'trusted': bool(flag('is_trusted')), 'cancelable': bool(flag('cancelable'))}
        if target:
            p.bind('rv_node_release', None, [P])(target)
        if kind == 'submit':
            submitter = P()
            p.call('rv_dom_submit_event_get_submitter', [P, ctypes.POINTER(P)], event, ctypes.byref(submitter))
            entry['submitter'] = self.label(submitter.value)
            if submitter.value:
                p.bind('rv_node_release', None, [P])(submitter.value)
            if self.remove_on_submit:
                p.call('rv_dom_element_remove', [P], self.node(self.remove_on_submit))
                self.remove_on_submit = None
        if kind == 'formdata':
            data = P()
            p.call('rv_dom_form_data_event_get_form_data', [P, ctypes.POINTER(P)], event, ctypes.byref(data))
            if self.append:
                name, value = (text.encode() for text in self.append)
                p.call('rv_dom_dom_form_data_append', [P, ctypes.c_char_p, I, ctypes.c_char_p, I], data.value, name, len(name), value, len(value))
            entry['entries'] = self.entries(data.value)
            p.bind('rv_dom_dom_form_data_release', None, [P])(data.value)
        return entry

    def drain(self):
        """Cycles the run loop until three consecutive cycles deliver no event and no submission."""
        cycle = self.p.bind('rv_run_loop_cycle', I, [I])
        seen, quiet = (len(self.events), len(self.submissions)), 0
        for _ in range(200):
            cycle(1)
            now = (len(self.events), len(self.submissions))
            if now == seen:
                quiet += 1
                if quiet == 3:
                    return
            else:
                seen, quiet = now, 0
        raise AssertionError('the run loop kept delivering events or submissions')

    def record(self, context, event):
        entry = self.event_fields(event)
        if entry['type'] in self.prevent:
            self.prevent.remove(entry['type'])
            self.p.bind('rv_event_prevent_default', None, [P])(event)
            entry['prevented'] = True
        self.events.append(entry)
        return 0

    def step(self, s):
        p = self.p
        op = s['op']
        target = self.node(s['id']) if s.get('id') and op != 'removeOnSubmit' else None
        if op == 'requestSubmit':
            submitter = self.node(s['submitter']) if 'submitter' in s else None
            return self.outcome(p.bind('rv_dom_html_form_element_request_submit', I, [P, P])(target, submitter))
        if op == 'submit':
            return self.outcome(p.bind('rv_dom_html_form_element_submit', I, [P])(target))
        if op == 'submitTwice':
            request = p.bind('rv_dom_html_form_element_request_submit', I, [P, P])
            first = request(target, None)
            return self.outcome(first if first != OK else request(target, None))
        if op == 'setAttribute':
            return self.outcome(p.bind('rv_dom_element_set_attribute', I, [P, Utf8, Utf8])(target, s['name'].encode(), s['value'].encode()))
        if op == 'setValue':
            return self.outcome(p.bind('rv_dom_html_input_element_set_value', I, [P, Utf8])(target, s['value'].encode()))
        if op == 'checkValidity':
            value = I()
            return self.outcome(p.bind('rv_dom_html_form_element_check_validity', I, [P, ctypes.POINTER(I)])(target, ctypes.byref(value)), bool(value.value))
        if op == 'appendOnFormData':
            self.append = (s['name'], s['value'])
            return {'status': 'ok', 'value': None}
        if op == 'removeOnSubmit':
            self.remove_on_submit = s['id']
            return {'status': 'ok', 'value': None}
        if op == 'mouse':
            p.update()
            mouse = p.bind('rv_host_mouse', I, [P, I, I, I, I, I, I])
            results = [mouse(p.host, 0, s['x'], s['y'], -1, 0, 0), mouse(p.host, 1, s['x'], s['y'], 0, 1, 0), mouse(p.host, 2, s['x'], s['y'], 0, 1, 0)]
            return {'status': 'ok' if min(results) >= 0 else 'native:' + str(results), 'value': None}
        return super().step(s)


def replay(native_directory, cases):
    results, handled = [], True
    for case in cases['cases']:
        with SvgProbe(native_directory, *cases['viewport']) as p:
            runner = SubmissionRunner(p)
            runner.load(cases['markup'], cases['eventTypes'])
            handled = runner.install_handler() and handled
            steps = []
            for s in case['steps']:
                result = runner.step(s)
                runner.drain()
                result['events'] = runner.events[:]
                result['submissions'] = runner.submissions[:]
                runner.events.clear()
                runner.submissions.clear()
                steps.append({**s, **result})
            runner.close()
            results.append({'name': case['name'], 'steps': steps, 'assertions': p.assertions})
    return results, handled


def lifecycle(p):
    """Window capture listeners for the unload events; returns the list they append to and their callbacks."""
    fired, callbacks = [], []
    window = p.bind('rv_host_window_event_target', P, [P])(p.host)
    add = p.bind('rv_event_target_add_listener', P, [P, ctypes.c_char_p, I, CALLBACK, P])
    for kind in ['beforeunload', 'pagehide', 'unload']:
        callback = CALLBACK(lambda context, event, kind=kind: fired.append(kind) or 0)
        callbacks.append(callback)
        p.expect(bool(add(window, kind.encode(), 1, callback, None)), 'window listener ' + kind)
    return fired, callbacks


def teardown(native_directory, cases):
    """A submission with no handler set, a handler removed while a submission is pending, and a host destroyed while a
    submission is pending. Asserts that the document stays, its listeners keep receiving events, and no submission
    reaches a removed handler or outlives its host."""
    report = {}
    submitted = [{'type': 'submit', 'target': 'p', 'trusted': True, 'cancelable': True, 'submitter': None}, 'formdata']
    shape = lambda events: [e if e['type'] == 'submit' else e['type'] for e in events]
    with SvgProbe(native_directory, *cases['viewport']) as p:
        runner = SubmissionRunner(p)
        runner.load(cases['markup'], cases['eventTypes'])
        fired, callbacks = lifecycle(p)
        document = p.bind('rv_host_document', P, [P])(p.host)
        rounds = []
        for _ in range(2):
            status = runner.step({'op': 'requestSubmit', 'id': 'p'})['status']
            runner.drain()
            rounds.append({'status': status, 'events': shape(runner.events), 'submissions': len(runner.submissions)})
            runner.events.clear()
        same = I(-1)
        current = p.bind('rv_host_document', P, [P])(p.host)
        p.call('rv_dom_node_is_same_node', [P, P, ctypes.POINTER(I)], current, document, ctypes.byref(same))
        for item in (current, document):
            p.bind('rv_node_release', None, [P])(item)
        p.expect(all(r == {'status': 'ok', 'events': submitted, 'submissions': 0} for r in rounds), 'no handler: events, no submission ' + str(rounds))
        p.expect(fired == [] and same.value == 1, 'no handler: the document stays ' + str((fired, same.value)))
        report['noHandler'] = {'rounds': rounds, 'unloadEvents': fired, 'sameDocument': same.value == 1}
        p.expect(runner.install_handler(), 'handler set')
        status = runner.step({'op': 'requestSubmit', 'id': 'p'})['status']
        setter = p.bind('rv_host_set_form_submission_handler', I, [P, HANDLER, P])
        p.expect(setter(p.host, HANDLER(), None) == OK, 'handler removed with a submission pending')
        runner.drain()
        p.expect(status == 'ok' and runner.submissions == [] and fired == [], 'removed handler: no submission ' + str(runner.submissions))
        report['handlerRemovedWhilePending'] = {'status': status, 'submissions': len(runner.submissions), 'unloadEvents': fired}
        runner.events.clear()
        runner.close()
        assertions = p.assertions
    with SvgProbe(native_directory, *cases['viewport']) as p:
        runner = SubmissionRunner(p)
        runner.load(cases['markup'], cases['eventTypes'])
        form = runner.node('p')
        p.watch(form)
        p.expect(runner.install_handler(), 'handler set')
        status = runner.step({'op': 'requestSubmit', 'id': 'p'})['status']
        events = shape(runner.events)
        remove = p.bind('rv_listener_remove', I, [P])
        for listener in runner.listeners:
            p.expect(remove(listener) == OK, 'listener removal before destroy')
        runner.listeners.clear()
        p.dispose_host()
        p.collect()
        p.expect(status == 'ok' and events == submitted, 'pending at destroy: events ' + str(events))
        p.expect(runner.submissions == [], 'pending at destroy: no submission after destroy ' + str(runner.submissions))
        runner.close()
        p.release_all()
        p.collect()
        p.expect_expired()
        report['pendingAtDestroy'] = {'status': status, 'events': events, 'submissionsAfterDestroy': len(runner.submissions)}
        report['assertions'] = assertions + p.assertions
    return report


def compare(oracle, native):
    """Per-step status and value differences, and per-case differences of the event sequence and of the submission
    sequence. Events and submissions compare without their step: a scheduled submission starts at a task boundary."""
    differences = []
    keep = ('method', 'url', 'contentType', 'body', 'newWindow')
    for expected, actual in zip(oracle['cases'], native):
        for index, (e, a) in enumerate(zip(expected['steps'], actual['steps'])):
            if (e['status'], e.get('value')) != (a['status'], a.get('value')):
                differences.append({'case': expected['name'], 'step': index, 'op': e['op'], 'kind': 'value',
                                    'chromium': [e['status'], e.get('value')], 'native': [a['status'], a.get('value')]})
        events = lambda case: [ev for s in case['steps'] for ev in s['events']]
        submissions = lambda case: [{k: sub[k] for k in keep} for s in case['steps'] for sub in s['submissions']]
        for kind, measure in [('events', events), ('submissions', submissions)]:
            if measure(expected) != measure(actual):
                differences.append({'case': expected['name'], 'kind': kind, 'chromium': measure(expected), 'native': measure(actual)})
    return differences


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--report')
    parser.add_argument('--measure', action='store_true', help='record native results and differences without asserting')
    parser.add_argument('--abi', type=int, default=ABI, help='the expected ABI version of a later runtime')
    args = parser.parse_args()
    cases = json.loads((FIXTURES / 'form-submission-cases.json').read_text(encoding='utf-8'))
    oracle = json.loads((FIXTURES / 'form-submission-oracle.json').read_text(encoding='utf-8'))
    native, handled = replay(args.native_directory, cases)
    differences = compare(oracle, native)
    report = {'browser': oracle['browser'], 'handler': handled, 'differences': differences, 'cases': native}
    if args.measure:
        if args.report:
            Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(f'measured {len(native)} cases, handler {"present" if handled else "absent"}, {len(differences)} differences', flush=True)
        sys.exit(0)
    if not handled:
        raise AssertionError('rv_host_set_form_submission_handler is absent')
    qualified = json.loads((FIXTURES / 'form-submission-qualified.json').read_text(encoding='utf-8'))['differences']
    strip = lambda items: [{k: v for k, v in item.items() if k not in ('reason', 'qualification')} for item in items]
    unexpected = [d for d in differences if d not in strip(qualified)]
    absent = [q for q in strip(qualified) if q not in differences]
    if unexpected or absent:
        raise AssertionError('differences changed: unexpected ' + json.dumps(unexpected, ensure_ascii=False) + ' absent ' + json.dumps(absent, ensure_ascii=False))
    assertions = sum(case['assertions'] for case in native) + sum(len(case['steps']) for case in native) + 2 * len(native)
    with SvgProbe(args.native_directory) as p:
        p.expect(p.bind('rv_abi_version', I, [])() == args.abi, 'ABI version ' + str(args.abi))
        p.expect(p.bind('rv_abi_has', I, [ctypes.c_char_p])(b'form-submission') == 1, 'form-submission advertised')
        assertions += p.assertions
    lifetime = teardown(args.native_directory, cases)
    assertions += lifetime['assertions']
    report['teardown'] = lifetime
    report['qualified'] = len(qualified)
    report['assertions'] = assertions
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'PASS form_submission: {assertions} assertions, {len(native)} cases, {len(qualified)} qualified differences', flush=True)
