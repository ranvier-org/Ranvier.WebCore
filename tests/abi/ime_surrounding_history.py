"""Committed-coordinate history around a provisional selected composition."""

import argparse
import ctypes as C
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import CALLBACK, Case, Native, P, I, U
from ime_surrounding import snapshot_with_token
from utf8_inputs import Utf8


def width(text):
    return len(text.encode('utf-16-le')) // 2


def run(directory):
    native = Native(directory)
    delete = native.bind('rv_host_ime_delete_surrounding', I, [P, C.c_uint64, I, I])
    for preedit in ('か', 'かな', '😀', 'a😀b'):
        for order in (('before', 'after'), ('after', 'before')):
            page = Case(native, '<input id="field" value="A😀BC">')
            ax = None
            try:
                field = page.node('field')
                native.ok('rv_dom_html_element_focus', [P, P], field, None)
                native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 3, 4, b'forward')
                native.ok('rv_host_set_accessibility', [P, I, P, P], page.host, 1, None, None)
                ax = native.bind('rv_host_ax_focus', P, [P])(page.host)
                native.expect(bool(ax), 'real accessibility focus for the editable')
                def check_accessibility(expected):
                    length = native.call('rv_ax_text_length', [P], ax)
                    native.expect(length == width(expected), 'accessibility exposes committed UTF-16 text length')
                    native.expect(native.text('rv_ax_text', [P, I, I], ax, 0, length) == expected,
                                  'accessibility exposes the same final edited text')
                    start, end = I(), I()
                    native.expect(native.call('rv_ax_text_selection', [P, C.POINTER(I), C.POINTER(I)],
                                              ax, C.byref(start), C.byref(end)) == 1, 'accessibility exposes a text selection')
                    dom_start, dom_end, present_start, present_end = U(), U(), I(), I()
                    native.ok('rv_dom_html_input_element_get_selection_start', [P, C.POINTER(U), C.POINTER(I)],
                              field, C.byref(dom_start), C.byref(present_start))
                    native.ok('rv_dom_html_input_element_get_selection_end', [P, C.POINTER(U), C.POINTER(I)],
                              field, C.byref(dom_end), C.byref(present_end))
                    native.expect((present_start.value, present_end.value, start.value, end.value) ==
                                  (1, 1, dom_start.value, dom_end.value), 'accessibility and DOM selections agree')
                native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, preedit.encode(), width(preedit), width(preedit))
                values, history = ['A😀BC'], []
                handler = CALLBACK(lambda _, event: history.append(native.text('rv_dom_input_event_get_input_type', [P], event)) or 0)
                listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(field, b'beforeinput', 0, handler, None)
                native.expect(bool(listener), 'history listener')
                page.listeners.append(listener)
                for side in order:
                    value, token = snapshot_with_token(native, page.host)
                    native.expect(isinstance(value, tuple) and value[0] == values[-1], 'committed snapshot before each deletion')
                    needle = '😀' if side == 'before' else 'C'
                    index = value[0].index(needle)
                    start = width(value[0][:index])
                    native.expect(delete(page.host, token, start, start + width(needle)) == 1, 'accepted disjoint deletion')
                    values.append(value[0].replace(needle, '', 1))
                history.clear()
                native.ok('rv_host_ime_cancel', [P], page.host)
                native.expect(snapshot_with_token(native, page.host)[0] == ('AB', 2, 1),
                              f'cancel preserves both surrounding deletions: {preedit!r}, {order}')
                native.expect(history == ['historyUndo'], f'cancel uses one undo and no redo: {history}')
                check_accessibility('AB')
                for expected in reversed(values[:-1]):
                    native.expect(native.call('rv_host_edit', [P, I], page.host, 6) == 1, 'undo accepted deletion')
                    native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == expected,
                                  f'undo uses committed offsets: {preedit!r}, {order}, {expected!r}')
                    check_accessibility(expected)
                for expected in values[1:]:
                    native.expect(native.call('rv_host_edit', [P, I], page.host, 7) == 1, 'redo accepted deletion')
                    native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == expected,
                                  f'redo uses committed offsets: {preedit!r}, {order}, {expected!r}')
                    check_accessibility(expected)
            finally:
                if ax:
                    native.bind('rv_ax_release', None, [P])(ax)
                page.close()

    page = Case(native, '<div id="rich" contenteditable>A<span id="left">😀</span>'
                '<b id="first">B</b><i id="second">D</i><span>C</span></div>')
    owned = []
    try:
        rich, first, second = page.node('rich'), page.node('first'), page.node('second')
        a = native.handle('rv_dom_node_get_first_child', [P], first)
        b = native.handle('rv_dom_node_get_first_child', [P], second)
        selection = native.handle('rv_dom_document_get_selection', [P], page.document)
        owned.extend((('rv_node_release', a), ('rv_node_release', b), ('rv_dom_dom_selection_release', selection)))
        clicks, handlers = [], []
        for node, label in ((first, 'first'), (second, 'second')):
            handler = CALLBACK(lambda *_, label=label: clicks.append(label) or 0)
            handlers.append(handler)
            listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(node, b'click', 0, handler, None)
            native.expect(bool(listener), 'rich selected element listener')
            page.listeners.append(listener)
        native.ok('rv_dom_html_element_focus', [P, P], rich, None)
        native.ok('rv_dom_dom_selection_set_base_and_extent', [P, P, U, P, U], selection, a, 0, b, 1)
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'かなな'.encode(), 3, 3)
        _, token = snapshot_with_token(native, page.host)
        native.expect(delete(page.host, token, 1, 3) == 1, 'delete before multi-node selected preedit')
        native.ok('rv_host_ime_cancel', [P], page.host)
        native.expect(snapshot_with_token(native, page.host)[0][0] == 'ABDC', 'cancel restores multi-node selected contents')
        for identifier, original in ((b'first', first), (b'second', second)):
            current = native.bind('rv_document_get_element_by_id', P, [P, Utf8])(page.host, identifier)
            native.expect(bool(current), 'restored selected element is present')
            owned.append(('rv_node_release', current))
            native.expect(current == original, 'original selected element identity survives')
            native.ok('rv_dom_html_element_click', [P], current)
        native.expect(clicks == ['first', 'second'], 'selected original element listeners survive')
        native.expect(native.call('rv_host_edit', [P, I], page.host, 6) == 1, 'undo multi-node surrounding deletion')
        native.expect(snapshot_with_token(native, page.host)[0][0] == 'A😀BDC', 'rich undo restores the accepted deleted scalar')
        native.expect(native.call('rv_host_edit', [P, I], page.host, 7) == 1, 'redo multi-node surrounding deletion')
        native.expect(snapshot_with_token(native, page.host)[0][0] == 'ABDC', 'rich redo preserves restored selected nodes')
    finally:
        for release, handle in reversed(owned):
            native.bind(release, None, [P])(handle)
        page.close()
    page = Case(native, '<input id="field" value="A😀BC">')
    try:
        field = page.node('field')
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 3, 4, b'forward')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'か'.encode(), 1, 1)
        _, token = snapshot_with_token(native, page.host)
        ends, errors = [], []
        def replace_value(_context, event):
            try:
                if native.text('rv_dom_input_event_get_input_type', [P], event) == 'deleteContent':
                    native.ok('rv_dom_html_input_element_set_value', [P, Utf8], field, b'APP')
            except BaseException as error:
                errors.append(repr(error))
            return 0
        changed = CALLBACK(replace_value)
        ended = CALLBACK(lambda *_: ends.append('end') or 0)
        for name, callback in ((b'beforeinput', changed), (b'compositionend', ended)):
            listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(field, name, 0, callback, None)
            native.expect(bool(listener), 'uncancelled application-value listener')
            page.listeners.append(listener)
        native.expect(delete(page.host, token, 1, 3) == 2, 'changed admission context terminates the original preedit')
        native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == 'APP' and ends == ['end'] and not errors,
                      f'application value survives with one terminal event: {ends}, {errors}')
    finally:
        page.close()
    page = Case(native, '<input id="other" value="P"><input id="field" value="A😀BC">')
    try:
        other = page.node('other')
        native.ok('rv_dom_html_element_focus', [P, P], other, None)
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], other, 1, 1, b'forward')
        native.expect(native.call('rv_host_key', [P, I, C.c_char_p, C.c_char_p, Utf8, I, I],
                                 page.host, 2, b'x', b'KeyX', b'x', 0, 0) > 0, 'seed an unrelated prior typing edit')
        field = page.node('field')
        native.ok('rv_dom_html_element_focus', [P, P], field, None)
        native.ok('rv_dom_html_input_element_set_selection_range', [P, U, U, Utf8], field, 3, 4, b'forward')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'かな'.encode(), 2, 2)
        _, token = snapshot_with_token(native, page.host)
        native.expect(delete(page.host, token, 1, 3) == 1, 'accepted deletion precedes the readonly fault')
        native.ok('rv_host_ime_set_composition', [P, Utf8, I, I], page.host, 'か'.encode(), 1, 1)
        _, token = snapshot_with_token(native, page.host)
        ends = []
        def make_readonly(_context, event):
            if native.text('rv_dom_input_event_get_input_type', [P], event) == 'deleteContent':
                native.ok('rv_dom_element_set_attribute', [P, Utf8, Utf8], field, b'readonly', b'')
            return 0
        changed = CALLBACK(make_readonly)
        ended = CALLBACK(lambda *_: ends.append('end') or 0)
        for name, callback in ((b'beforeinput', changed), (b'compositionend', ended)):
            listener = native.bind('rv_node_add_event_listener', P, [P, Utf8, I, CALLBACK, P])(field, name, 0, callback, None)
            native.expect(bool(listener), 'readonly admission listener')
            page.listeners.append(listener)
        native.expect(delete(page.host, token, 2, 3) == -9, 'incomplete readonly transaction returns explicit failure')
        native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == 'AかC' and ends == ['end'],
                      'readonly no-op preserves the applied preedit and accepted deletion, ending once')
        native.ok('rv_dom_element_remove_attribute', [P, Utf8], field, b'readonly')
        for expected in ('ABC', 'A😀BC'):
            native.expect(native.call('rv_host_edit', [P, I], page.host, 6) == 1, 'no-op failure retains valid prior undo steps')
            native.expect(native.text('rv_dom_html_input_element_get_value', [P], field) == expected,
                          'explicit later undo restores the composition then the accepted deletion')
        native.expect(ends == ['end'], 'later undo does not send a second composition end')
        native.expect(native.call('rv_host_edit', [P, I], page.host, 6) == 1
                      and native.text('rv_dom_html_input_element_get_value', [P], other) == 'P',
                      'proven no-op failure retains unrelated prior typing history')
    finally:
        page.close()
    print('PASS surrounding history matrix', native.assertions, 'assertions')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    run(parser.parse_args().native_directory)
