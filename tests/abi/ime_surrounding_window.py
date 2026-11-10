"""Bounded control context, conservative generations and legacy editing interoperability."""
import argparse
import ctypes as C
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, Case, P, I, U, CALLBACK
from utf8_inputs import Utf8


def run(directory):
    native = Native(directory)
    token_type = C.c_uint64
    query = native.bind('rv_host_ime_surrounding_window', I,
        [P, I, P, I] + [C.POINTER(I)] * 5 + [C.POINTER(token_type)])
    delete = native.bind('rv_host_ime_delete_surrounding_window', I, [P, token_type, I, I])
    page = Case(native, '<input id="text"><textarea id="area"></textarea><input id="secret" type="password" value="private"><div id="rich" contenteditable>text</div>')

    def snapshot(limit=4096):
        data = C.create_string_buffer(16384)
        length, origin, cursor, anchor, state = I(), I(), I(), I(), I()
        token = token_type()
        status = query(page.host, limit, data, len(data), C.byref(length), C.byref(origin), C.byref(cursor), C.byref(anchor), C.byref(state), C.byref(token))
        native.expect(status == 0, 'query succeeds')
        text = data.raw[:max(0, length.value)].decode('utf8')
        return text, origin.value, cursor.value, anchor.value, state.value, token.value

    def select(node, start, end, direction='forward', area=False):
        name = 'rv_dom_html_text_area_element_set_selection_range' if area else 'rv_dom_html_input_element_set_selection_range'
        native.ok(name, [P, U, U, Utf8], node, start, end, direction)

    try:
        field = page.node('text')
        native.ok('rv_node_set_string', [P, I, Utf8], field, 6, 'a' * 100000 + '前😀e\u0301אב後' + 'z' * 100000)
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        select(field, 100001, 100003, 'backward')
        text, origin, cursor, anchor, state, token = snapshot()
        native.expect(state == 1 and len(text.encode('utf-16-le')) // 2 <= 4096, 'bounded context')
        native.expect(origin > 0 and origin + cursor == 100001 and origin + anchor == 100003, 'backward selection and UTF16 origin')
        native.expect('😀e\u0301אב' in text, 'astral combining and bidi preserved')
        native.expect(delete(page.host, token, cursor, anchor) == 1, 'nonzero-origin deletion')
        native.expect('😀' not in snapshot()[0], 'window deletion maps to the control')
        native.expect(native.call('rv_host_edit', [P, I], page.host, 6) == 1, 'undo mapped deletion')
        select(field, 100001, 100003, 'backward')
        native.expect(snapshot(1)[4] == 2, 'selection cannot fit is unavailable')
        text, origin, cursor, anchor, state, token = snapshot()
        select(field, 0, 0)
        native.expect(delete(page.host, token, cursor, anchor) == -10, 'selection invalidates token')
        select(field, 100001, 100003, 'backward')
        old = snapshot()
        select(field, 0, 0)
        select(field, 100001, 100003, 'backward')
        native.expect(delete(page.host, old[5], 0, 1) == -10, 'selection roundtrip invalidates generation')
        old = snapshot()
        native.ok('rv_node_set_string', [P, I, Utf8], field, 6, 'replacement')
        native.expect(delete(page.host, old[5], 0, 1) == -10, 'value mutation invalidates token')
        native.ok('rv_node_set_string', [P, I, Utf8], field, 6, 'abcdef')
        select(field, 3, 3)
        old = snapshot()
        native.ok('rv_dom_html_element_focus', [P, P], page.node('secret'), None)
        native.expect(snapshot()[4] == 3, 'secure text never exposed')
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        select(field, 3, 3)
        native.expect(delete(page.host, old[5], 1, 2) == -10, 'focus roundtrip invalidates token')
        old = snapshot()
        native.expect(delete(page.host, old[5], 1, 2) == 1, 'delete uses window coordinates')
        native.expect(native.text('rv_node_get_string', [P, I], field, 6) == 'acdef', 'correct deletion')
        native.expect(native.call('rv_host_edit', [P, I], page.host, 6) == 1, 'deletion supports undo')
        native.expect(native.text('rv_node_get_string', [P, I], field, 6) == 'abcdef', 'undo restores text')
        old = snapshot()
        native.expect(native.call('rv_host_edit', [P, I], page.host, 7) == 1, 'redo')
        native.expect(delete(page.host, old[5], 0, 1) == -10, 'history invalidates token')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, '日本', 2, 2)
        native.expect(snapshot()[4] == 2, 'active composition explicitly unavailable')
        native.ok('rv_host_ime_cancel', [P], page.host)
        native.expect(snapshot()[4] == 1, 'cancel restores bounded context')
        area = page.node('area')
        native.ok('rv_node_set_string', [P, I, Utf8], area, 6, 'one\n前😀後\nthree\n')
        native.ok('rv_dom_html_element_focus', [P, P], area, None)
        select(area, 5, 7, area=True)
        result = snapshot()
        native.expect(result[:5] == ('one\n前😀後\nthree\n', 0, 7, 5, 1), 'multiline offsets and terminal newline')
        native.ok('rv_dom_html_element_focus', [P, P], page.node('rich'), None)
        native.expect(snapshot()[4] == 2, 'arbitrary contenteditable has no bounded-cost claim')
        native.ok('rv_node_set_string', [P, I, Utf8], area, 6, '\n'.join('line' for _ in range(1000)))
        native.ok('rv_dom_html_element_focus', [P, P], area, None)
        select(area, 0, 0, area=True)
        native.expect(snapshot()[4] == 1, 'many logical lines in flat text remain supported')
        native.ok('rv_node_set_string', [P, I, Utf8], field, 6, 'a😀b')
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        select(field, 1, 3)
        result = snapshot(2)
        native.expect(result[:5] == ('😀', 1, 2, 0, 1), 'exact astral window')
        native.expect(delete(page.host, result[5], 0, 1) == -9, 'delete cannot split a surrogate pair')
        native.ok('rv_node_set_string', [P, I, Utf8], field, 6, '')
        select(field, 0, 0)
        native.expect(snapshot()[:5] == ('', 0, 0, 0, 1), 'empty control context')
        native.ok('rv_node_set_string', [P, I, Utf8], field, 6, 'abc')
        select(field, 1, 1)
        old = snapshot()
        native.ok('rv_host_set_focused', [P, I], page.host, 0)
        native.ok('rv_host_set_focused', [P, I], page.host, 1)
        native.expect(delete(page.host, old[5], 0, 1) == -10, 'window focus roundtrip invalidates token')
        select(field, 1, 1)
        def intervene(_context, _event):
            native.ok('rv_node_set_string', [P, I, Utf8], field, 6, 'intervened')
            return 0
        callback = CALLBACK(intervene)
        listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(field, 'beforeinput', 0, callback, None)
        page.listeners.append(listener)
        old = snapshot()
        native.expect(delete(page.host, old[5], 0, 1) <= 0, 'reentrant edit is not reported as successful')
        native.expect(native.text('rv_node_get_string', [P, I], field, 6) == 'intervened', 'application mutation survives reentrant deletion')
        print('IME window assertions:', native.assertions)
    finally:
        page.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    run(parser.parse_args().native_directory)
