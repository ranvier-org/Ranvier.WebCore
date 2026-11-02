"""Focused editable text and selection snapshots for native input methods."""

import argparse
import ctypes as C
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import CALLBACK, Native, Case, P, I, U
from utf8_inputs import Utf8


def snapshot_with_token(native, host):
    data, length, cursor, anchor, state, token = C.create_string_buffer(4096), I(), I(), I(), I(), C.c_uint64()
    native.ok('rv_host_ime_surrounding', [P, P, I, C.POINTER(I), C.POINTER(I), C.POINTER(I), C.POINTER(I), C.POINTER(C.c_uint64)],
              host, data, len(data), C.byref(length), C.byref(cursor), C.byref(anchor), C.byref(state), C.byref(token))
    if state.value != 1:
        return state.value, token.value
    return (data.raw[:length.value].decode('utf8'), cursor.value, anchor.value), token.value


def snapshot(native, host):
    return snapshot_with_token(native, host)[0]


def run(directory):
    native = Native(directory)
    native.expect(native.bind('rv_abi_version', I, [])() == 63, 'snapshot ABI version')
    native.expect(native.call('rv_abi_has', [C.c_char_p], b'ime-surrounding') == 1, 'snapshot capability')
    page = Case(native, '<input id="text" value="前😀中後"><input id="secret" type="password" value="private">'
                        '<input id="readonly" readonly value="static"><textarea id="area">A😀B</textarea><button id="button">go</button>'
                        '<div id="rich" contenteditable>前<br><span id="middle">😀中</span><div>後</div>'
                        '<span style="display:none">隠</span><span contenteditable="false">固定</span></div>')
    owned = []
    try:
        field = page.node('text')
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 1, 3, b'backward')
        native.expect(snapshot(native, page.host) == ('前😀中後', 1, 3), 'backward input selection')
        tiny, length, cursor, anchor, state, token = C.create_string_buffer(1), I(), I(), I(), I(), C.c_uint64()
        args = [P, P, I, C.POINTER(I), C.POINTER(I), C.POINTER(I), C.POINTER(I), C.POINTER(C.c_uint64)]
        values = (page.host, tiny, len(tiny), C.byref(length), C.byref(cursor), C.byref(anchor), C.byref(state), C.byref(token))
        status = native.call('rv_host_ime_surrounding', args, *values)
        native.expect(status == -6 and length.value == len('前😀中後'.encode()) and state.value == 1,
                      'short buffer reports the required UTF-8 length')
        thread_result = []
        thread = threading.Thread(target=lambda: thread_result.append(native.call('rv_host_ime_surrounding', args, *values)))
        thread.start()
        thread.join()
        native.expect(thread_result == [-2], 'snapshot rejects a non-owner thread')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'かな'.encode(), 2, 2)
        native.expect(snapshot(native, page.host) == ('前😀中後', 1, 3),
                      'active composition reports the validated pre-composition context')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'かなあ'.encode(), 3, 3)
        native.expect(snapshot(native, page.host) == ('前😀中後', 1, 3),
                      'continued composition keeps the same committed context')
        native.ok('rv_host_ime_cancel', [P], page.host)
        native.expect(snapshot(native, page.host) == ('前😀中後', 1, 3), 'cancellation restores context')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'かな'.encode(), 2, 2)
        native.ok('rv_host_ime_commit', [P, Utf8], page.host, '仮'.encode())
        native.expect(snapshot(native, page.host) == ('前仮中後', 2, 2), 'commit publishes committed text and caret')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'か'.encode(), 1, 1)
        secret = page.node('secret')
        native.ok('rv_dom_html_element_focus', [P, P], secret, None)
        native.expect(snapshot(native, page.host) == 3, 'password focus never exposes the previous composition context')
        native.ok('rv_host_ime_cancel', [P], page.host)
        readonly = page.node('readonly')
        native.ok('rv_dom_html_element_focus', [P, P], readonly, None)
        native.expect(snapshot(native, page.host) == 0, 'readonly context is unavailable')
        button = page.node('button')
        native.ok('rv_dom_html_element_focus', [P, P], button, None)
        native.expect(snapshot(native, page.host) == 0, 'non-editable context is unavailable')
        area = page.node('area')
        native.ok('rv_dom_html_element_focus', [P, P], area, None)
        native.ok('rv_dom_html_text_area_element_set_selection_range', [P, U, U, Utf8], area, 1, 3, b'forward')
        native.expect(snapshot(native, page.host) == ('A😀B', 3, 1), 'forward textarea selection')
        rich, middle = page.node('rich'), page.node('middle')
        native.ok('rv_dom_html_element_focus', [P, P], rich, None)
        child = native.handle('rv_dom_node_get_first_child', [P], middle)
        owned.append(('rv_node_release', child))
        selection = native.handle('rv_dom_document_get_selection', [P], page.document)
        owned.append(('rv_dom_dom_selection_release', selection))
        native.ok('rv_dom_dom_selection_set_base_and_extent', [P, P, U, P, U], selection, child, 3, child, 0)
        native.expect(snapshot(native, page.host) == ('前\n😀中\n後\n固定', 2, 5), 'rich backward selection uses editing text')
        native.ok('rv_dom_dom_selection_set_base_and_extent', [P, P, U, P, U], selection, child, 0, child, 0)
        native.expect(snapshot(native, page.host) == ('前\n😀中\n後\n固定', 2, 2), 'rich caret uses editing text')
        native.ok('rv_dom_dom_selection_set_base_and_extent', [P, P, U, P, U], selection, child, 0, child, 2)
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, '仮'.encode(), 1, 1)
        native.expect(snapshot(native, page.host) == ('前\n😀中\n後\n固定', 4, 2),
                      'rich active composition retains the original editing context')
        native.ok('rv_host_ime_cancel', [P], page.host)
        native.ok('rv_dom_dom_selection_set_base_and_extent', [P, P, U, P, U], selection, child, 0, button, 0)
        focus_node = native.handle('rv_dom_dom_selection_get_focus_node', [P], selection)
        owned.append(('rv_node_release', focus_node))
        contained = I()
        native.ok('rv_dom_node_contains', [P, P, C.POINTER(I)], rich, focus_node, C.byref(contained))
        crossing = snapshot(native, page.host)
        native.expect(contained.value == 1 and crossing == ('前\n😀中\n後\n固定', 0, 2),
                      f'WebCore-clamped selection remains in the editable root: {crossing!r}')
    finally:
        for release, value in reversed(owned): native.bind(release, None, [P])(value)
        page.close()
    page = Case(native, '<input id="field" value="abc">')
    try:
        field = page.node('field')
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 1, 2, b'forward')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, '仮'.encode(), 1, 1)
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 0, 0, b'forward')
        native.expect(snapshot(native, page.host) != ('abc', 2, 1), 'selection change invalidates the original context')
        native.ok('rv_host_ime_cancel', [P], page.host)
        native.ok('rv_dom_html_input_element_set_value', [P, Utf8], field, b'abc')
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 1, 2, b'forward')
        observed = []
        def on_input(_context, event):
            if native.text('rv_dom_input_event_get_input_type', [P], event) == 'insertCompositionText':
                native.ok('rv_dom_html_input_element_set_value', [P, Utf8], field, b'APP')
                observed.append(snapshot(native, page.host))
            return 0
        callback = CALLBACK(on_input)
        listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(field, b'input', 0, callback, None)
        native.expect(bool(listener), 'reentrant input listener')
        page.listeners.append(listener)
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, '仮'.encode(), 1, 1)
        native.expect(observed and all(value != ('abc', 2, 1) for value in observed),
                      f'reentrant application edits cannot expose stale context: {observed!r}')
        native.ok('rv_host_ime_cancel', [P], page.host)
    finally:
        page.close()
    page = Case(native, '<input id="old" value="abc">')
    try:
        old = page.node('old')
        native.ok('rv_dom_html_element_focus', [P, P], old, None)
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], old, 1, 2, b'forward')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, '仮'.encode(), 1, 1)
        native.ok('rv_host_load_html', [P, Utf8], page.host, b'<input id="new" value="new-context">')
        replacement = page.node('new')
        native.ok('rv_dom_html_element_focus', [P, P], replacement, None)
        current = snapshot(native, page.host)
        native.expect(isinstance(current, tuple) and current[0] == 'new-context',
                      f'document replacement cannot expose the old context: {current!r}')
    finally:
        page.close()
    print('PASS IME surrounding text')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    run(parser.parse_args().native_directory)
