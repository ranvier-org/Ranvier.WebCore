"""Observe selected composition edits through the native mutation/event seams."""

import argparse
import ctypes as C
import json
from pathlib import Path
import sys
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parent))

from form_collections import CALLBACK, Case, P, I
from ime_surrounding import snapshot_with_token
from mutation_observation import Options, Probe
from utf8_inputs import Utf8


def run(directory, report, mode=None):
    probe = Probe(directory)
    native = probe.n
    delete = native.bind('rv_host_ime_delete_surrounding', I, [P, C.c_uint64, I, I])
    rows = []
    for action in ([mode] if mode else ('inspect', 'destroy', 'replace', 'composition', 'destroy-during-input', 'replace-during-input', 'composition-during-input')):
        operation = action.split('-')[0]
        pump_during_input = action.endswith('-during-input')
        page = Case(native, '<div id="field" contenteditable><span id="before">A😀</span>'
                    '<b id="selected">B</b><span id="after">C</span></div>')
        owned = []
        destroyed = False
        events, callbacks, errors = [], [], []
        observer, delivered, releases = None, [], []
        try:
            field, selected = page.node('field'), page.node('selected')
            original = native.handle('rv_dom_node_get_first_child', [P], selected)
            owned.append(('rv_node_release', original))
            selection = native.handle('rv_dom_document_get_selection', [P], page.document)
            owned.append(('rv_dom_dom_selection_release', selection))
            native.ok('rv_dom_html_element_focus', [P, P], field, None)
            native.ok('rv_dom_dom_selection_set_base_and_extent', [P, P, C.c_uint32, P, C.c_uint32],
                      selection, original, 0, original, 1)
            handlers = []
            listen = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])
            for name in ('beforeinput', 'input', 'compositionstart', 'compositionupdate', 'compositionend'):
                def received(_context, event, name=name):
                    try:
                        kind = native.text('rv_dom_input_event_get_input_type', [P], event) if name in ('beforeinput', 'input') else None
                        value = native.text('rv_dom_node_get_text_content', [P], field)
                        events.append({'event': name, 'kind': kind, 'value': value})
                        if pump_during_input and name == 'input' and kind == 'deleteContent':
                            probe.pump(lambda: bool(delivered), timeout=2)
                    except BaseException as error:
                        errors.append(repr(error))
                    return 0
                handler = CALLBACK(received)
                handlers.append(handler)
                listener = listen(field, name.encode(), 0, handler, None)
                native.expect(bool(listener), 'native event listener')
                page.listeners.append(listener)
            native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'かな'.encode(), 2, 2)
            click = []
            click_handler = CALLBACK(lambda *_: click.append('click') or 0)
            listener = listen(selected, b'click', 0, click_handler, None)
            native.expect(bool(listener), 'original selected node listener')
            page.listeners.append(listener)
            events_before_delete = len(events)

            def observed(_observer, _batch):
                nonlocal destroyed
                callbacks.append(native.text('rv_dom_node_get_text_content', [P], field))
                if len(callbacks) != 1:
                    return
                if operation == 'destroy':
                    native.bind('rv_host_destroy', None, [P])(page.host)
                    destroyed = True
                elif operation == 'replace':
                    native.ok('rv_host_load_html', [P, Utf8], page.host, b'<p id="replacement">new</p>')
                elif operation == 'composition':
                    native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, '仮'.encode(), 1, 1)

            observer, delivered, releases = probe.create(page.host, action=observed)
            probe.observe(observer, field, Options(child_list=True, subtree=True, character_data_old_value=True))
            _, token = snapshot_with_token(native, page.host)
            status = delete(page.host, token, 1, 3)
            native.expect(status in (0, 1) if pump_during_input else status == 1,
                          f'accepted deletion before observed selected preedit: {status}')
            during_delete = events[events_before_delete:]
            expected_kinds = ['deleteContent', 'insertCompositionText'] if pump_during_input and operation == 'composition' else ['deleteContent']
            native.expect([e['kind'] for e in during_delete if e['event'] == 'beforeinput'] == expected_kinds,
                          f'deletion admission occurs once: {during_delete}')
            native.expect([e['kind'] for e in during_delete if e['event'] == 'input'] == expected_kinds,
                          f'deletion input occurs once: {during_delete}')
            native.expect(all(e['value'] == 'AかなC' for e in during_delete if e['event'] == 'input' and e['kind'] == 'deleteContent'),
                          f'input callback sees resumed composition: {during_delete}')
            if not pump_during_input:
                native.expect(not delivered, 'mutation callbacks remain deferred until the normal pump')
                probe.pump(lambda: bool(delivered), timeout=2)
            native.expect(bool(delivered) and callbacks[0] == 'AかなC', f'mutation callback observes completed operation: {callbacks}')
            records = [record for _, batch in delivered for record in batch]
            native.expect(not any(selected in record['removed'] for record in records),
                          'the selected original element is not detached by suspension/rebuild')
            if operation == 'inspect':
                native.ok('rv_host_ime_cancel', [P], page.host)
                native.expect(native.text('rv_dom_node_get_text_content', [P], field) == 'ABC', 'observed cancellation preserves accepted deletion')
                current = native.handle('rv_dom_node_get_first_child', [P], selected)
                owned.append(('rv_node_release', current))
                native.expect(current == original, 'original selected text-node identity survives')
                native.ok('rv_dom_html_element_click', [P], selected)
                native.expect(click == ['click'], 'original selected element listener survives')
                native.expect([e['event'] for e in events if e['event'].startswith('composition')] ==
                              ['compositionstart', 'compositionupdate', 'compositionend'], f'composition events remain one series: {events}')
                probe.pump(timeout=0.03)
            elif operation == 'destroy':
                native.expect(releases == ['release'], 'real host destruction releases the observer callback context once')
            elif operation == 'replace':
                native.expect(releases == ['release'], 'real document replacement releases the observer callback context once')
            else:
                native.expect(snapshot_with_token(native, page.host)[0] == ('ABC', 2, 1), 'observer-reentrant composition retains committed context')
                native.ok('rv_host_ime_cancel', [P], page.host)
                native.expect(native.text('rv_dom_node_get_text_content', [P], field) == 'ABC', 'observer-reentrant composition cancels to selected original')
            native.expect(not errors and not probe.callback_errors, f'callback errors: {errors}, {probe.callback_errors}')
            probe.release(observer)
        finally:
            if observer in probe.live_observers:
                probe.release(observer)
            for release, handle in reversed(owned):
                native.bind(release, None, [P])(handle)
            if destroyed:
                for listener in page.listeners:
                    native.call('rv_listener_remove', [P], listener)
                for node in page.owned + list(page.created.values()) + [page.document]:
                    native.bind('rv_node_release', None, [P])(node)
            else:
                page.close()
            rows.append({'action': action, 'events': events, 'callbackValues': callbacks,
                         'records': [record for _, batch in delivered for record in batch], 'contextReleases': list(releases)})
            Path(report).write_text(json.dumps({'rows': rows, 'customElementScope': 'Script is disabled and VM entry prohibited by the native Host; no custom-element callback binding exists.'}, indent=2))
    probe.close()
    native.expect(probe.accepted_contexts == probe.released_contexts, 'all accepted native observer contexts are released')
    Path(report).write_text(json.dumps({'rows': rows, 'customElementScope': 'Script is disabled and VM entry prohibited by the native Host; no custom-element callback binding exists.'}, indent=2))
    print('PASS native IME mutation/event ownership controls')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--mode', choices=('inspect', 'destroy', 'replace', 'composition', 'destroy-during-input', 'replace-during-input', 'composition-during-input'))
    args = parser.parse_args()
    if args.mode:
        run(args.native_directory, args.report, args.mode)
    else:
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        results = []
        for mode in ('inspect', 'destroy', 'replace', 'composition', 'destroy-during-input', 'replace-during-input', 'composition-during-input'):
            target = report.with_name(report.stem + '-' + mode + report.suffix)
            command = [sys.executable, '-I', str(Path(__file__).resolve()), '--native-directory', args.native_directory,
                       '--report', str(target), '--mode', mode]
            try:
                child = subprocess.run(command, capture_output=True, timeout=30)
                code = child.returncode
                print(mode, code, child.stdout.decode(errors='replace'), child.stderr.decode(errors='replace'), flush=True)
            except subprocess.TimeoutExpired:
                code = -999
                print(mode, 'TIMEOUT', flush=True)
            results.append({'mode': mode, 'exit': code, 'report': target.name})
        report.write_text(json.dumps({'results': results}, indent=2))
        raise SystemExit(1 if any(row['exit'] for row in results) else 0)
