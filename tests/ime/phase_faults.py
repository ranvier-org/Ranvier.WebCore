"""Run one fault case against an explicitly instrumented private native image."""

import argparse
import ctypes as C
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'abi'))
from form_collections import CALLBACK, Case, Native, P, I, U
from ime_surrounding import snapshot_with_token
from utf8_inputs import Utf8

parser = argparse.ArgumentParser()
parser.add_argument('--native-directory', required=True)
parser.add_argument('--mode', required=True)
parser.add_argument('--report', required=True)
args = parser.parse_args()
stage, action = args.mode.split('-', 1)
phase_number = {'first': 1, 'middle': 1, 'final': 1, 'restored': 2, 'deleted': 3, 'rebuilt': 4, 'missing': 5}[stage]
n = Native(args.native_directory)
install = n.bind('rv_test_ime_fault_install', None, [P])
stop = n.bind('rv_test_ime_fault_stop', None, [])
kind = n.bind('rv_test_ime_set_failure_kind', None, [I])
delete = n.bind('rv_host_ime_delete_surrounding', I, [P, C.c_uint64, I, I])
page = Case(n, '<input id="other" value="P"><input id="field" value="A😀BC">')
destroyed = False
ends, phases, errors = [], [], []
observation = {}

def actual_text():
    return n.text('rv_test_ime_actual_text', [P], page.host)

try:
    other = page.node('other')
    n.ok('rv_dom_html_element_focus', [P, P], other, None)
    n.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], other, 1, 1, b'forward')
    n.expect(n.call('rv_host_key', [P, I, C.c_char_p, C.c_char_p, Utf8, I, I], page.host, 2, b'x', b'KeyX', b'x', 0, 0) > 0,
             'unrelated field has an earlier real typing edit')
    n.expect(n.call('rv_host_edit', [P, I], page.host, 6) == 1 and n.text('rv_dom_html_input_element_get_value', [P], other) == 'P',
             'earlier unrelated edit has valid undo before the transaction')
    n.expect(n.call('rv_host_edit', [P, I], page.host, 7) == 1 and n.text('rv_dom_html_input_element_get_value', [P], other) == 'Px',
             'earlier unrelated edit has valid redo before the transaction')
    field = page.node('field')
    n.ok('rv_host_set_focused', [P, I], page.host, 1)
    n.ok('rv_dom_html_element_focus', [P, P], field, None)
    n.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 3, 4, b'forward')
    n.ok('rv_host_set_accessibility', [P, I, P, P], page.host, 1, None, None)
    n.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'かな'.encode(), 2, 2)
    _, token = snapshot_with_token(n, page.host)
    n.expect(delete(page.host, token, 1, 3) == 1, 'first accepted surrounding deletion')
    for preedit in ('仮', 'かのな'):
        n.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, preedit.encode(), len(preedit), len(preedit))
    n.expect(snapshot_with_token(n, page.host)[0] == ('ABC', 2, 1), 'updated committed context before injected failure')
    ended = CALLBACK(lambda *_: ends.append('end') or 0)
    listener = n.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(field, b'compositionend', 0, ended, None)
    n.expect(bool(listener), 'terminal event listener')
    page.listeners.append(listener)

    def fault(phase, index, count):
        global destroyed
        try:
            phases.append([phase, index, count])
            if phase != phase_number or observation:
                return
            if phase == 1:
                target = 1 if stage == 'first' else (count + 1) // 2 if stage == 'middle' else count
                if index != target:
                    return
                n.expect(count >= 3, 'first/middle/final use a real compound unapply')
            observation.update(phase=phase, index=index, count=count, before=actual_text())
            if action == 'value':
                n.ok('rv_dom_html_input_element_set_value', [P, Utf8], field, b'APP')
                observation['afterCallback'] = actual_text()
                stop()
            elif action == 'replace':
                n.ok('rv_host_load_html', [P, Utf8], page.host, b'<p id="replacement">new</p>')
                stop()
            elif action == 'destroy':
                n.bind('rv_host_destroy', None, [P])(page.host)
                destroyed = True
                stop()
            elif action == 'compose':
                observation['nestedCompose'] = n.call('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, b'Z', 1, 1)
                n.expect(observation['nestedCompose'] == -9, 'suspended input follows the ordinary undo busy rule')
                stop()
            elif action == 'mismatch':
                kind({'restored': 4, 'deleted': 2, 'rebuilt': 3, 'missing': 5}[stage])
            else:
                stop()
        except BaseException as error:
            errors.append(repr(error))
            stop()

    fault_callback = C.CFUNCTYPE(None, I, I, I)(fault)
    install(C.cast(fault_callback, P))
    _, token = snapshot_with_token(n, page.host)
    result = delete(page.host, token, 2, 3)
    install(None)
    n.expect(observation and not errors, f'fault callback completed: {observation}, {errors}')
    n.expect(result == -9, f'incomplete transaction returns an explicit failure: {result}')
    n.expect(ends == ['end'], f'original composition ends once: {ends}')
    if phase_number == 1:
        n.expect(phases[-1] == phases[observation['index'] - 1], 'unapply stops immediately after failed validation')
    if action == 'destroy':
        buffer, length, cursor, anchor, state, token = C.create_string_buffer(32), I(), I(), I(), I(), C.c_uint64()
        status = n.call('rv_host_ime_surrounding', [P, P, I, C.POINTER(I), C.POINTER(I), C.POINTER(I), C.POINTER(I), C.POINTER(C.c_uint64)],
                        page.host, buffer, len(buffer), C.byref(length), C.byref(cursor), C.byref(anchor), C.byref(state), C.byref(token))
        n.expect(status == -9, 'destroyed host is detached before snapshot dereference')
    elif action == 'replace':
        replacement = n.bind('rv_document_get_element_by_id', P, [P, Utf8])(page.host, b'replacement')
        n.expect(bool(replacement), 'requested document replacement is honored')
        observation['final'] = n.text('rv_dom_node_get_text_content', [P], replacement)
        n.bind('rv_node_release', None, [P])(replacement)
        n.expect(observation['final'] == 'new', 'new application document is preserved')
        n.expect(n.call('rv_host_edit', [P, I], page.host, 6) == 0, 'old history cannot edit the new document')
    else:
        observation['final'] = actual_text()
        observation['inputValue'] = n.text('rv_dom_html_input_element_get_value', [P], field)
        n.expect(observation['inputValue'] == observation['final'], 'text control value matches its actual editing DOM on failure')
        n.expect('😀' not in observation['final'], 'already accepted surrounding deletion is not resurrected')
        if action == 'value':
            n.expect(observation['final'] == 'APP', 'new application text is preserved')
        elif action in ('stop', 'compose'):
            n.expect(observation['final'] == observation['before'], 'no old mutation follows failed context validation')
        observation['undo'] = n.call('rv_host_edit', [P, I], page.host, 6)
        n.expect(observation['undo'] == 0, 'unknown partial history is invalidated')
        n.expect(n.text('rv_dom_html_input_element_get_value', [P], other) == 'Px',
                 'partial failure preserves unrelated field content while invalidating all prior undo')
        if stage == 'rebuilt' and action in ('stop', 'mismatch'):
            before_typing = observation['final']
            n.expect(n.call('rv_host_key', [P, I, C.c_char_p, C.c_char_p, Utf8, I, I],
                            page.host, 2, b'x', b'KeyX', b'x', 0, 0) > 0, 'new ordinary typing works after failed rebuilding')
            n.expect(n.call('rv_host_edit', [P, I], page.host, 6) == 1, 'new ordinary typing creates a fresh undo step')
            n.expect(n.text('rv_dom_html_input_element_get_value', [P], field) == before_typing,
                     'fresh typing undo restores the failed-operation text')
        before_restart = len(ends)
        n.ok('rv_dom_html_input_element_set_value', [P, Utf8], field, b'restart')
        n.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 1, 2, b'forward')
        n.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, b'Z', 1, 1)
        n.ok('rv_host_ime_cancel', [P], page.host)
        n.expect(n.text('rv_dom_html_input_element_get_value', [P], field) == 'restart' and len(ends) == before_restart + 1,
                 'a fresh composition works after the failed transaction')
    print('PASS private phase fault', args.mode, n.assertions)
finally:
    install(None)
    Path(args.report).write_text(json.dumps({'mode': args.mode, 'observation': observation, 'phases': phases, 'ends': ends, 'errors': errors,
        'testOnly': 'Artifact-only phase callback and validation/failure injection; these exports are absent from production source and packages.'}, indent=2))
    if destroyed:
        for listener in page.listeners:
            n.call('rv_listener_remove', [P], listener)
        for handle in page.owned + list(page.created.values()) + [page.document]:
            n.bind('rv_node_release', None, [P])(handle)
    else:
        page.close()
